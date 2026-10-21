import sys, re, gzip, json, collections
sys.path.insert(0, ".")
import att_epg
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
mode = sys.argv[1]
if mode == "full":
    pass
if mode == "full":
    att_epg.GUIDELESS = ("XTREAM", "XTREAM2")
att_epg.build()
d = gzip.open("att_epg.xml.gz").read()
root = ET.fromstring(d)
now = datetime.now(timezone.utc); w = lambda x: datetime.strptime(x, "%Y%m%d%H%M%S %z")
FILL = re.compile(r"لم يُعلن البث|No listing|24/7|على مدار الساعة")
live = {p.get("channel") for p in root.findall("programme") if w(p.get("start")) <= now < w(p.get("stop")) and not FILL.search(p.findtext("title") or "")}
names = {dn.text: c.get("id") for c in root.findall("channel") for dn in c.findall("display-name")}
pc = json.load(open("playlist_cache.json"))["XTREAM"]
g = collections.defaultdict(lambda: [0, 0])
for cat, name, epg in pc:
    k = "UK" if name.upper().startswith("UK") else "CBS" if re.search(r"\bCBS\b", name) else "ABC" if re.search(r"\bABC\b", name) else "ALL"
    for kk in {k, "ALL"}:
        g[kk][1] += 1
        if name in names and names[name] in live: g[kk][0] += 1
out = [f"{mode}: size {len(open('att_epg.xml.gz','rb').read())//1024} KB gz, {len(root.findall('channel'))} channels"] + [f"  {k}: {a}/{b}" for k, (a, b) in sorted(g.items())]
text = "%0A".join(out)
for s in att_epg.SECRETS:
    if s: text = text.replace(s, "***")
print("::notice::" + text)
