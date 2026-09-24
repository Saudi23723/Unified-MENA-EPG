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


try:
    SA1 = feed("https://www.open-epg.com/files/saudiarabia1.xml")
    SA2 = feed("https://www.open-epg.com/files/saudiarabia2.xml")
    EG2 = feed("https://www.open-epg.com/files/egypt2.xml")
    AE1 = feed("https://epgshare01.online/epgshare01/epg_ripper_AE1.xml.gz")
    SH2 = feed("https://epgshare01.online/epgshare01/epg_ripper_SA2.xml.gz")
    for name, text, cid in (("SA1", SA1, "MBC 2 HD.sa"), ("SA2", SA2, "MBC 2 HD.sa"),
                            ("EG2", EG2, "MBC 2.eg"), ("AE1", AE1, "MBC.2.ae"), ("SH2", SH2, "EN:.MBC.MAX.sa")):
        r = rows(text, cid)
        print(name, cid, "raw starts:", [x[0] for x in r[:3]])
    pairs = [("SA2", SA2, "MBC 2 HD.sa", "AE1", AE1, "MBC.2.ae"),
             ("SA2", SA2, "MBC Max HD.sa", "SH2", SH2, "EN:.MBC.MAX.sa"),
             ("SA2", SA2, "MBC Action HD.sa", "AE1", AE1, "MBC.Action.ae"),
             ("SA2", SA2, "MBC 4 HD.sa", "AE1", AE1, "MBC.4.ae"),
             ("EG2", EG2, "MBC 2.eg", "AE1", AE1, "MBC.2.ae"),
             ("EG2", EG2, "MBC 5.eg", "AE1", AE1, "MBC.Masr.Drama.HD.ae"),
             ("SH2", SH2, "EN:.MBC1.Iraq.sa", "AE1", AE1, "MBC.Iraq.HD.ae"),
             ("SH2", SH2, "EN:.MBC.Masr.Drama.sa", "AE1", AE1, "MBC.Masr.Drama.HD.ae")]
    for an, at, ac, bn, bt, bc in pairs:
        a, b = rows(at, ac), rows(bt, bc)
        ca = Counter(t for _, t in a); cb = Counter(t for _, t in b)
        ua = {t: s for s, t in a if ca[t] == 1}; ub = {t: s for s, t in b if cb[t] == 1}
        deltas = Counter()
        for t in set(ua) & set(ub):
            deltas[int((instant(ua[t]) - instant(ub[t])).total_seconds() // 60)] += 1
        print(f"{an}:{ac} vs {bn}:{bc} shared-unique={sum(deltas.values())} delta-min={deltas.most_common(5)}")
    # SA1 (Arabic) vs SA2 (English): same slots?
    for cid in ("MBC 1 HD.sa", "MBC 4 HD.sa", "MBC MASR.sa"):
        s1 = {s for s, _ in rows(SA1, cid)}; s2 = {s for s, _ in rows(SA2, cid)}
        print("SA1 vs SA2 slots", cid, len(s1), len(s2), "common", len(s1 & s2))
except Exception:
    traceback.print_exc()

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
        white = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 255))
        disc.paste(white, (0, 0), mask)
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
