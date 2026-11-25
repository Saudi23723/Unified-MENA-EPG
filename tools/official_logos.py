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
    "dazn": ("appsearch", "DAZN"),                  # DAZN's own app (seller DAZN)
    "tvp3_bialystok": ("wiki", "pl:TVP3 Białystok"),
    "kabel_eins_doku": ("wiki", "de:Kabel Eins Doku"),
}


def get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def source(how: str, what: str) -> str:
    if how == "appsearch":
        q = urllib.parse.urlencode({"term": what, "entity": "software", "limit": 10, "country": "de"})
        for r in json.loads(get("https://itunes.apple.com/search?" + q))["results"]:
            if r.get("trackName", "").upper().startswith(what.upper()) and what.upper() in (r.get("sellerName") or "").upper():
                return r.get("artworkUrl512") or r["artworkUrl100"]
        raise RuntimeError("the broadcaster's own app was not found")
    if how == "appstore":
        o = json.loads(get("https://itunes.apple.com/lookup?id=" + what))
        r = o["results"][0]
        return r.get("artworkUrl512") or r["artworkUrl100"]
    lang, title = what.split(":", 1)
    api = f"https://{lang}.wikipedia.org/w/api.php?"
    q = urllib.parse.urlencode({"action": "query", "prop": "pageimages", "piprop": "name", "titles": title,
                                "format": "json", "redirects": 1})
    page = next(iter(json.loads(get(api + q))["query"]["pages"].values()))
    name = page.get("pageimage")
    if not name:  # no logo on the article: the channel's logo file on Wikimedia Commons
        api = "https://commons.wikimedia.org/w/api.php?"
        q = urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": title + " logo",
                                    "srnamespace": 6, "srlimit": 5, "format": "json"})
        hits = [h["title"] for h in json.loads(get(api + q))["query"]["search"]]
        words = [w.lower() for w in title.split() if len(w) > 2]
        hits = [h for h in hits if all(w in h.lower() for w in words)]
        if not hits:
            raise RuntimeError("no logo file found")
        name = hits[0].split(":", 1)[1]
    # always the PNG render (SVG logos included), 512 px wide
    q = urllib.parse.urlencode({"action": "query", "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 512,
                                "titles": "File:" + name, "format": "json"})
    p = next(iter(json.loads(get(api + q))["query"]["pages"].values()))
    return p["imageinfo"][0]["thumburl"]


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
