import sys, re, gzip, json, requests
sys.path.insert(0, ".")
import att_epg
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
url, user, pw = att_epg.login("XTREAM")
secrets = [x for x in (url, user, pw, re.sub(r"^https?://", "", url or "").split(":")[0]) if x]
out = []
r = requests.get(url + "/xmltv.php", params={"username": user, "password": pw}, headers={"User-Agent": "TiviMate/4.7.0"}, timeout=300)
d = r.content
if d[:2] == b"\x1f\x8b": d = gzip.decompress(d)
out.append(f"xmltv status {r.status_code} bytes {len(d)}")
root = ET.fromstring(d)
now = datetime.now(timezone.utc); w = lambda x: datetime.strptime(x, "%Y%m%d%H%M%S %z")
ch = {c.get("id") for c in root.findall("channel")}
live = {}
for p in root.findall("programme"):
    try:
        if w(p.get("start")) <= now < w(p.get("stop")): live[p.get("channel")] = p.findtext("title")
    except Exception: pass
out.append(f"provider guide: {len(ch)} channels, {len(live)} on air now")
pc = json.load(open("playlist_cache.json"))["XTREAM"]
import collections
groups = collections.defaultdict(lambda: [0, 0])
for cat, name, epg in pc:
    g = "UK" if name.upper().startswith("UK") else "CBS" if re.search(r"\bCBS\b", name) else "ABC" if re.search(r"\bABC\b", name) else None
    if not g: continue
    groups[g][1] += 1
    if epg and epg in live: groups[g][0] += 1
for g, (a, b) in groups.items(): out.append(f"{g}: {a}/{b} have a programme now in the provider's guide")
for i in ("BBC1.uk", "ITV1.uk", "Channel4.uk", "Channel5.uk", "E4.uk", "bbc1.uk"):
    out.append(f"{i}: {live.get(i)}")
text = "%0A".join(out)
for s in secrets: text = text.replace(s, "***")
print("::notice::" + text)
