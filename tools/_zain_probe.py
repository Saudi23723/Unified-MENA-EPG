import requests, gzip
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET
H = {"User-Agent": "Mozilla/5.0"}
def load(u):
    d = requests.get(u, headers=H, timeout=120).content
    if d[:2] == b"\x1f\x8b": d = gzip.decompress(d)
    return ET.fromstring(d)
w = lambda x: datetime.strptime(x, "%Y%m%d%H%M%S %z")
eg = load("https://www.open-epg.com/files/egypt2.xml"); ae = load("https://iptv-epg.org/files/epg-ae.xml"); sa = load("https://iptv-epg.org/files/epg-sa.xml")
out = []
def rows(r, cid): return sorted((w(p.get("start")), w(p.get("stop")), p.findtext("title")) for p in r.findall("programme") if p.get("channel") == cid)
for egid, aeid in (("OSN TV Crime.eg", "OSNTVCrime.ae"), ("OSN Ya Hala.eg", "OSNTVYahala.ae"), ("Osn Ya Hala Aflam.eg", "OSNTVYahalaAflam.ae")):
    e = rows(eg, egid); a = rows(ae, aeid)
    out.append(f"== {aeid}: distinct titles {len({t for _,_,t in a})}/{len(a)}")
    out += [f"  AE {s:%m-%d %H:%M}-{t2:%H:%M} {t}" for s, t2, t in a[:6]]
    # clock check: same title in both, start offset
    ed = {t: s for s, _, t in e}
    offs = sorted({int((s - ed[t]).total_seconds() // 60) for s, _, t in a if t in ed})
    out.append(f"  shared titles {sum(1 for _,_,t in a if t in ed)}, start offset minutes vs open-epg egypt2: {offs[:8]}")
for cid in ("OSNTVKids.ae", "NickJr.ae"):
    a = rows(ae, cid); out.append(f"== {cid}: distinct titles {len({t for _,_,t in a})}/{len(a)}"); out += [f"  AE {s:%m-%d %H:%M}-{t2:%H:%M} {t}" for s, t2, t in a[:5]]
a = rows(sa, "OSNTVKids.sa"); out.append(f"== OSNTVKids.sa distinct {len({t for _,_,t in a})}/{len(a)}"); out += [f"  SA {s:%m-%d %H:%M} {t}" for s, _, t in a[:4]]
print("::notice::" + "%0A".join(out)[:9000])
