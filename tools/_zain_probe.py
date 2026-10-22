import sys, os; sys.path.insert(0, os.getcwd())
import gzip, re, requests, xml.etree.ElementTree as ET
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
r = requests.get("https://epgshare01.online/epgshare01/epg_ripper_AU1.xml.gz", headers={"User-Agent": "Mozilla/5.0"}, timeout=300)
root = ET.fromstring(gzip.decompress(r.content))
fut = {}
for p in root.iter("programme"):
    if datetime.strptime(p.get("stop"), "%Y%m%d%H%M%S %z") > now:
        fut[p.get("channel")] = fut.get(p.get("channel"), 0) + 1
for ch in root.findall("channel"):
    names = " / ".join(d.text or "" for d in ch.findall("display-name"))
    if re.search(r"fox|espn|sky|racing|sbs|bein|abc news|jazeera|bloomberg|nitv|red ?bull|cna|news asia|ewtn|liv|tvsn|kayo|10 ?bold|shake|7two|channel ?7|9now|stan|optus", names + ch.get("id"), re.I):
        print(f"{ch.get('id')} | {names} | {fut.get(ch.get('id'), 0)}")
