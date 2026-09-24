"""MBC: measure each feed's clock against another, and draw round logos. Never fails."""
import base64
import gzip
import io
import re
import traceback
from collections import Counter
from datetime import datetime

import requests
from PIL import Image, ImageDraw

S = requests.Session()
S.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def feed(url):
    raw = S.get(url, timeout=90).content
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", "replace")


def rows(text, cid):
    out = []
    for m in re.finditer(r'<programme start="([^"]+)" stop="([^"]+)" channel="%s"(.*?)</programme>'
                         % re.escape(cid), text, re.S):
        t = re.search(r"<title[^>]*>(.*?)</title>", m.group(3), re.S)
        title = re.sub(r":Episode.*$", "", (t.group(1) if t else "")).replace("&apos;", "'").strip().casefold()
        out.append((m.group(1), title))
    return out


def instant(s):
    return datetime.strptime(s, "%Y%m%d%H%M%S %z")


LOGOS = {
    "mbc1": "https://i.imgur.com/CiA3plN.png", "mbc2": "https://i.imgur.com/n9mSHuP.png",
    "mbc3": "https://i.imgur.com/PVt8OPN.png", "mbc4": "https://i.imgur.com/BcXASJp.png",
    "mbc5": "https://i.imgur.com/fRWaDyF.png", "mbc_action": "https://i.imgur.com/OWZAghw.png",
    "mbc_bollywood": "https://i.imgur.com/TTAGFHG.png", "mbc_drama": "https://i.imgur.com/g5PWnqp.png",
    "mbc_iraq": "https://i.imgur.com/D0LxiPE.png", "mbc_masr": "https://i.imgur.com/o2elx0u.png",
    "mbc_masr2": "https://i.imgur.com/KHo7Gtn.png", "mbc_masr_drama": "https://media0070.elcinema.com/tvguide/1399_1.png",
    "mbc_max": "https://i.imgur.com/A02CptP.png", "mbc_plus_drama": "https://i.imgur.com/lxWdjXG.png",
    "mbc_variety": "https://i.imgur.com/SfA0YaR.png", "wanasah": "https://i.imgur.com/nLtiXNf.png",
}
SIZE = 400
for key, url in LOGOS.items():
    try:
        r = S.get(url, timeout=30)
        src = Image.open(io.BytesIO(r.content)).convert("RGBA")
        bbox = src.getbbox()
        if bbox:
            src = src.crop(bbox)
        disc = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        mask = Image.new("L", (SIZE, SIZE), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, SIZE - 1, SIZE - 1], fill=255)
        px = [p for p in src.getdata() if p[3] > 128]
        light = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b, _ in px) / max(1, len(px))
        ground = (22, 24, 34, 255) if light > 165 else (255, 255, 255, 255)
        print("LIGHT", key, round(light))
        disc.paste(Image.new("RGBA", (SIZE, SIZE), ground), (0, 0), mask)
        box = int(SIZE * 0.66)
        src.thumbnail((box, box), Image.LANCZOS)
        disc.alpha_composite(src, ((SIZE - src.width) // 2, (SIZE - src.height) // 2))
        ring = ImageDraw.Draw(disc)
        ring.ellipse([3, 3, SIZE - 4, SIZE - 4], outline=(210, 210, 210, 255), width=5)
        out = io.BytesIO()
        disc.save(out, format="PNG", optimize=True)
        print(f"LOGO {key} {base64.b64encode(out.getvalue()).decode()}")
    except Exception as exc:
        print("LOGO-ERR", key, url, type(exc).__name__, str(exc)[:100])
