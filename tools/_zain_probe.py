import sys, os; sys.path.insert(0, os.getcwd())
import gzip, json, requests, xml.etree.ElementTree as ET
from datetime import datetime, timezone
import playlist_match as pm
now = datetime.now(timezone.utc)
rows = [r for r in json.load(open("playlist_cache.json"))["XTREAM"] if r[0].startswith("AU|")]
r = requests.get("https://epgshare01.online/epgshare01/epg_ripper_AU1.xml.gz", headers={"User-Agent": "Mozilla/5.0"}, timeout=300)
root = ET.fromstring(gzip.decompress(r.content))
fut = {}
for p in root.iter("programme"):
    if datetime.strptime(p.get("stop"), "%Y%m%d%H%M%S %z") > now:
        fut[p.get("channel")] = fut.get(p.get("channel"), 0) + 1
keys = {}
for ch in root.findall("channel"):
    for k in pm.source_names([d.text or "" for d in ch.findall("display-name")]):
        keys.setdefault(k, ch.get("id"))
hit = [(n, keys[pm.source_key(n)]) for c, n, e in rows if keys.get(pm.source_key(n)) and fut.get(keys[pm.source_key(n)])]
print(f"AU shelves: {len(rows)} channels, matched {len(hit)}")
vip = [n for c, n, e in rows if c.startswith("AU| AUSTRALIA VIP")]
print("VIP matched", sum(1 for n, _ in hit if n in vip), "/", len(vip))
for n, cid in hit:
    if n in vip: print("  ", n, "->", cid)
