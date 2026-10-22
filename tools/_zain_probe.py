import requests, re, gzip
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
H = {"User-Agent": "Mozilla/5.0"}
now = datetime.now(timezone.utc); w = lambda x: datetime.strptime(x, "%Y%m%d%H%M%S %z")
srcs = {"eg2": "https://www.open-epg.com/files/egypt2.xml", "eg1": "https://www.open-epg.com/files/egypt1.xml",
        "sa1": "https://www.open-epg.com/files/saudiarabia1.xml", "sa2": "https://www.open-epg.com/files/saudiarabia2.xml",
        "uae1": "https://www.open-epg.com/files/uae1.xml", "uae2": "https://www.open-epg.com/files/uae2.xml",
        "kw": "https://www.open-epg.com/files/kuwait1.xml", "qa": "https://www.open-epg.com/files/qatar1.xml",
        "jo": "https://www.open-epg.com/files/jordan1.xml", "lb": "https://www.open-epg.com/files/lebanon1.xml",
        "AE1": "https://epgshare01.online/epgshare01/epg_ripper_AE1.xml.gz", "SA1": "https://epgshare01.online/epgshare01/epg_ripper_SA1.xml.gz",
        "ipe-ae": "https://iptv-epg.org/files/epg-ae.xml", "ipe-sa": "https://iptv-epg.org/files/epg-sa.xml"}
want = re.compile(r"OSN.*(Crime|Kids|Nick|Ya ?Hala)|Nick ?Jr|Yahala|يا هلا", re.I)
out = []
for k, u in srcs.items():
    try:
        d = requests.get(u, headers=H, timeout=120).content
        if d[:2] == b"\x1f\x8b": d = gzip.decompress(d)
        r = ET.fromstring(d)
    except Exception as e:
        out.append(f"{k}: ERR {type(e).__name__}"); continue
    for c in r.findall("channel"):
        nm = " / ".join((x.text or "") for x in c.findall("display-name"))[:60]
        if want.search(nm + " " + c.get("id")):
            ps = [p for p in r.findall("programme") if p.get("channel") == c.get("id")]
            last = max((w(p.get("stop")) for p in ps), default=None)
            cur = [p.findtext("title") for p in ps if w(p.get("start")) <= now < w(p.get("stop"))]
            out.append(f"{k}: {c.get('id')} | {nm} | rows {len(ps)} | last {last:%m-%d %H:%M}" if last else f"{k}: {c.get('id')} | {nm} | rows 0")
print("::notice::" + "%0A".join(out)[:9000])
