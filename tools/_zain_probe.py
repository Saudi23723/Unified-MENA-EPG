import requests, gzip
from datetime import datetime
import xml.etree.ElementTree as ET
H = {"User-Agent": "Mozilla/5.0"}
def load(u):
    d = requests.get(u, headers=H, timeout=120).content
    if d[:2] == b"\x1f\x8b": d = gzip.decompress(d)
    return ET.fromstring(d)
w = lambda x: datetime.strptime(x, "%Y%m%d%H%M%S %z")
eg1 = load("https://www.open-epg.com/files/egypt1.xml"); ae = load("https://iptv-epg.org/files/epg-ae.xml")
def rows(r, cid): return sorted((w(p.get("start")), p.findtext("title").strip()) for p in r.findall("programme") if p.get("channel") == cid)
out = []
for egid, aeid in (("أو إس إن ياهلا.eg", "OSNTVYahala.ae"), ("أو إس إن ياهلا بالعربي.eg", "OSNTVYahalaBilArabi.ae")):
    e = rows(eg1, egid); a = rows(ae, aeid)
    ed = {}
    for s, t in e: ed.setdefault(t, []).append(s)
    offs = []
    for s, t in a:
        if t in ed: offs.append(min((int((s - x).total_seconds() // 60) for x in ed[t]), key=abs))
    out.append(f"{aeid}: eg1 rows {len(e)} (last {e[-1][0]:%m-%d %H:%M} if e else '-'), ae rows {len(a)} last {a[-1][0]:%m-%d %H:%M}, distinct {len({t for _,t in a})}, shared {len(offs)}, offsets {sorted(set(offs))[:10]}")
    out += [f"   ae {s:%m-%d %H:%M} {t}" for s, t in a if s.day in (22, 23)][:6]
print("::notice::" + "%0A".join(out))
