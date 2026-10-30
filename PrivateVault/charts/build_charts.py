"""Official FAA VFR charts for SSEFB, offline: the FAA's own GeoTIFF of each
chart (aeronav.faa.gov), reprojected for web maps and cut into WebP tiles in
one MBTiles file per chart, published as a GitHub release with a manifest of
the edition. Run by .github/workflows/vfr_charts.yml; does nothing when the
release already holds the edition in force.

Charts are listed in CHARTS; adding one is one line.
"""

import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.request
import zipfile

# (key, FAA file stem, kind): kind is the folder on aeronav ("sectional-files" or "tac-files").
CHARTS = [
    ("sec_las_vegas", "Las_Vegas", "sectional-files", "Las Vegas Sectional"),
    ("tac_las_vegas", "Las_Vegas_TAC", "tac-files", "Las Vegas TAC"),
]
TAG = "vfr-charts"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) SSEFB chart builder"}
WORK = os.path.abspath("charts-work")


def edition(day=None):
    """The 56-day VFR chart edition in force: (start, end)."""
    day = day or dt.date.today()
    s = dt.date(2025, 2, 20)  # a VFR edition date (29 Oct 2026 is one); the FAA page confirmed it
    while s + dt.timedelta(days=56) <= day:
        s += dt.timedelta(days=56)
    while s > day:
        s -= dt.timedelta(days=56)
    return s, s + dt.timedelta(days=56)


def sh(*cmd):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def released_edition():
    try:
        out = subprocess.run(["gh", "release", "download", TAG, "-p", "manifest.json", "-O", "-"],
                             check=True, capture_output=True, text=True).stdout
        return json.loads(out).get("edition")
    except Exception:
        return None


def fetch(url, dest):
    print("GET", url, flush=True)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    return dest


def find_zip(stem, kind, start):
    """The chart's zip on aeronav for the edition; the FAA's VFR page is read when the usual address fails."""
    tries = [f"https://aeronav.faa.gov/visual/{start:%m-%d-%Y}/{kind}/{stem}.zip"]
    for url in tries:
        try:
            req = urllib.request.Request(url, headers=UA, method="HEAD")
            with urllib.request.urlopen(req, timeout=60) as r:
                if r.status == 200:
                    return url
        except Exception as e:
            print("  no:", url, e, flush=True)
    page = urllib.request.urlopen(urllib.request.Request(
        "https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/vfr/", headers=UA), timeout=60).read().decode("utf-8", "replace")
    links = [u for u in re.findall(r'href=["\']([^"\']+\.zip)["\']', page, re.I)
             if re.search(r'(^|/)' + re.escape(stem) + r'\.zip$', u, re.I)]
    if not links:
        # What the page holds, to see how the FAA names things now.
        zips = re.findall(r'href=["\']([^"\']+\.zip)["\']', page, re.I)
        print("zip links on the page:", len(zips), zips[:30], flush=True)
        print("dates on the page:", sorted(set(re.findall(r'\d{2}-\d{2}-\d{4}', page)))[:20], flush=True)
        raise RuntimeError(f"no zip for {stem} on the FAA's VFR page")
    url = links[0]
    return url if url.startswith("http") else "https://aeronav.faa.gov" + url


def build(key, stem, kind, title, start, end):
    os.makedirs(WORK, exist_ok=True)
    z = fetch(find_zip(stem, kind, start), os.path.join(WORK, key + ".zip"))
    with zipfile.ZipFile(z) as zf:
        tif = next(n for n in zf.namelist() if n.lower().endswith(".tif"))
        zf.extract(tif, WORK)
    src = os.path.join(WORK, tif)
    rgb = os.path.join(WORK, key + "_rgb.vrt")
    warped = os.path.join(WORK, key + "_3857.tif")
    out = os.path.abspath(key + ".mbtiles")
    # The FAA's charts are paletted: colours first, then onto the web map's projection.
    sh("gdal_translate", "-of", "VRT", "-expand", "rgb", src, rgb)
    sh("gdalwarp", "-t_srs", "EPSG:3857", "-r", "bilinear", "-dstalpha", "-multi", "-wo", "NUM_THREADS=ALL_CPUS",
       "-co", "TILED=YES", "-co", "COMPRESS=DEFLATE", "-co", "BIGTIFF=IF_SAFER", rgb, warped)
    if os.path.exists(out):
        os.remove(out)
    sh("gdal_translate", "-of", "MBTILES", "-co", "TILE_FORMAT=WEBP", "-co", "QUALITY=65",
       "-co", "ZOOM_LEVEL_STRATEGY=UPPER", "-co", f"NAME={title}", warped, out)
    sh("gdaladdo", "-r", "average", out, "2", "4", "8", "16", "32", "64")
    db = sqlite3.connect(out)
    meta = dict(db.execute("SELECT name, value FROM metadata").fetchall())
    for k, v in {"description": f"FAA {title}, edition effective {start:%d %b %Y}, until {end - dt.timedelta(days=1):%d %b %Y}",
                 "attribution": "FAA Aeronautical Information Services (aeronav.faa.gov)",
                 "edition": start.isoformat()}.items():
        db.execute("INSERT OR REPLACE INTO metadata (name, value) VALUES (?, ?)", (k, v))
    zooms = db.execute("SELECT MIN(zoom_level), MAX(zoom_level) FROM tiles").fetchone()
    db.commit()
    db.execute("VACUUM")
    db.close()
    size = os.path.getsize(out)
    print(f"{key}: {size / 1e6:.1f} MB, zoom {zooms}, bounds {meta.get('bounds')}", flush=True)
    return {"key": key, "title": title, "file": os.path.basename(out), "size": size,
            "minzoom": zooms[0], "maxzoom": zooms[1], "bounds": meta.get("bounds", "")}


def main():
    start, end = edition()
    force = "--force" in sys.argv
    if not force and released_edition() == start.isoformat():
        print("Release already holds the edition of", start, flush=True)
        return
    charts = [build(*c, start, end) for c in CHARTS]
    manifest = {"edition": start.isoformat(), "expires": end.isoformat(), "built": dt.datetime.utcnow().isoformat() + "Z",
                "source": "FAA Aeronautical Information Services, GeoTIFF (aeronav.faa.gov)", "charts": charts}
    with open("manifest.json", "w") as f:
        json.dump(manifest, f, indent=1)
    notes = f"Official FAA VFR charts, edition {start:%d %b %Y} to {end - dt.timedelta(days=1):%d %b %Y}, as WebP MBTiles for SSEFB."
    if subprocess.run(["gh", "release", "view", TAG], capture_output=True).returncode != 0:
        sh("gh", "release", "create", TAG, "--title", "Official FAA VFR charts", "--notes", notes, "--target", os.environ.get("GITHUB_SHA", "HEAD"))
    else:
        sh("gh", "release", "edit", TAG, "--notes", notes)
    sh("gh", "release", "upload", TAG, "--clobber", "manifest.json", *[c["file"] for c in charts])


if __name__ == "__main__":
    main()
