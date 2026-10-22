import sys, re, gzip, json, collections
sys.path.insert(0, ".")
import att_epg
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
att_epg.build()
root = ET.fromstring(gzip.open("att_epg.xml.gz").read())
now = datetime.now(timezone.utc); w = lambda x: datetime.strptime(x, "%Y%m%d%H%M%S %z")
FILL = re.compile(r"لم يُعلن البث|No listing|No Data|24/7|على مدار الساعة")
cur = {}
for p in root.findall("programme"):
    if w(p.get("start")) <= now < w(p.get("stop")): cur[p.get("channel")] = p.findtext("title")
idx = collections.defaultdict(list)
for c in root.findall("channel"):
    for d in c.findall("display-name"): idx[d.text].append(c.get("id"))
out = []
for n in ("Fr: BeIN Sports 1 FHD", "Fr: BeIN Sports 2 FHD", "Fr: BeIN Sports 3 HD", "Fr: Baby TV", "Fr: Canal+", "Fr: TF1", "Fr: RMC Sport 1", "UK: BBC One", "TR: beIN Sports 1"):
    out.append(f"{n} -> {[(i, (cur.get(i) or '')[:40]) for i in idx.get(n, [])]}")
for cid in ("beinsports1.fr", "beinsports1.tr", "babytv.pt", "BabyTV.pt"):
    c = [x for x in root.findall("channel") if x.get("id") == cid]
    out.append(f"id {cid}: {[d.text for d in c[0].findall('display-name')][:3] if c else 'absent'} now {cur.get(cid, '')[:40]}")
pc = json.load(open("playlist_cache.json"))
for k in pc:
    tot = len(pc[k]); good = sum(1 for _, n, _ in pc[k] if any(i in cur and not FILL.search(cur[i] or "") for i in idx.get(n, [])))
    out.append(f"{k}: {good}/{tot} with a real programme now")
fr = [n for k in pc for _, n, _ in pc[k] if re.match(r"\s*fr\s*[:|]", n, re.I)]
out.append(f"French: {sum(1 for n in fr if any(i in cur and not FILL.search(cur[i] or '') for i in idx.get(n, [])))}/{len(fr)}")
text = "%0A".join(out)
for s in att_epg.SECRETS:
    if s: text = text.replace(s, "***")
print("::notice::" + text[:9000])
