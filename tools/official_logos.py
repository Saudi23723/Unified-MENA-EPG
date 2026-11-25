#!/usr/bin/env python3
"""Official logos for playlist channels that come without one (owner, 25 Nov 2026: "put its official logo").

Each logo is taken from the broadcaster itself: its own app's icon on the App Store (Apple's lookup API), or the
logo file of its Wikipedia article (the channel's own logo). Saved square as logos/<key>.png on main.
Run by .github/workflows/official_logos.yml; prints what it got.
"""
import io
import json
import sys
import urllib.parse
import urllib.request

from PIL import Image

UA = {"User-Agent": "Unified-MENA-EPG logo fetch (github.com/Saudi23723/Unified-MENA-EPG)"}

# key: (how, what)
LOGOS = {
    "looloo_kids": ("appstore", "1441645173"),     # LooLoo Kids - Nursery Rhymes (the channel's own app)
    "ytn_radio": ("appstore", "695481841"),        # YTN 라디오 (YTN's own radio app)
    "tvp3_bialystok": ("wiki", "pl:TVP3 Białystok"),
    "kabel_eins_doku": ("wiki", "de:Kabel Eins Doku"),
}


def get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def source(how: str, what: str) -> str:
    if how == "appstore":
        o = json.loads(get("https://itunes.apple.com/lookup?id=" + what))
        r = o["results"][0]
        return r.get("artworkUrl512") or r["artworkUrl100"]
    lang, title = what.split(":", 1)
    q = urllib.parse.urlencode({"action": "query", "prop": "pageimages", "piprop": "original", "titles": title,
                                "format": "json", "redirects": 1})
    pages = json.loads(get(f"https://{lang}.wikipedia.org/w/api.php?{q}"))["query"]["pages"]
    page = next(iter(pages.values()))
    if "original" not in page:
        raise RuntimeError("no logo on the article")
    src = page["original"]["source"]
    if src.lower().endswith(".svg"):     # the rendered PNG of an SVG logo
        name = src.rsplit("/", 1)[1]
        q = urllib.parse.urlencode({"action": "query", "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 512,
                                    "titles": "File:" + urllib.parse.unquote(name), "format": "json"})
        p = next(iter(json.loads(get(f"https://{lang}.wikipedia.org/w/api.php?{q}"))["query"]["pages"].values()))
        src = p["imageinfo"][0]["thumburl"]
    return src


def square(raw: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(raw)).convert("RGBA")
    im.thumbnail((448, 448), Image.LANCZOS)
    out = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    out.paste(im, ((512 - im.width) // 2, (512 - im.height) // 2), im)
    return out


bad = 0
for key, (how, what) in LOGOS.items():
    try:
        url = source(how, what)
        img = square(get(url))
        img.save(f"logos/{key}.png", optimize=True)
        print(f"{key}: ok from {urllib.parse.urlparse(url).netloc}")
    except Exception as e:  # noqa: BLE001
        bad += 1
        print(f"{key}: FAILED {type(e).__name__}: {e}")
sys.exit(1 if bad == len(LOGOS) else 0)
