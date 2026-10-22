import sys, os; sys.path.insert(0, os.getcwd())
import gzip, json, requests, xml.etree.ElementTree as ET
from datetime import datetime, timezone
import playlist_match as pm
UA = {"User-Agent": "Mozilla/5.0 Chrome/128"}
now = datetime.now(timezone.utc)
names = [r[1] for r in json.load(open("playlist_cache.json"))["XTREAM"] if r[0].startswith("AU| AUSTRALIA VIP")]
for tag in ("AU1", "AU2", "AU3", "NZ1"):
    url = f"https://epgshare01.online/epgshare01/epg_ripper_{tag}.xml.gz"
    try:
        r = requests.get(url, headers=UA, timeout=300); r.raise_for_status()
        root = ET.fromstring(gzip.decompress(r.content))
    except Exception as e:
        print(f"{tag}: ERR {e}"[:150]); continue
    future = {}
    for p in root.iter("programme"):
        if datetime.strptime(p.get("stop"), "%Y%m%d%H%M%S %z") > now:
            future[p.get("channel")] = future.get(p.get("channel"), 0) + 1
    keys = {}
    for ch in root.findall("channel"):
        for k in pm.source_names([d.text or "" for d in ch.findall("display-name")]):
            keys.setdefault(k, ch.get("id"))
    hit = [n for n in names if keys.get(pm.source_key(n)) and future.get(keys[pm.source_key(n)])]
    miss = [n for n in names if n not in hit]
    print(f"{tag}: {len(root.findall('channel'))} channels, {len(future)} with future rows; AU VIP matched {len(hit)}/{len(names)}")
    print("  miss: " + "; ".join(miss[:60]))
    print("  some ids: " + ", ".join(sorted(future)[:80]))
