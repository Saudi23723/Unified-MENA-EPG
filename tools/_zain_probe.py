import sys, re
sys.path.insert(0, ".")
import jordan_football as jf, epg_lib
from datetime import datetime, timedelta, timezone
s = epg_lib.new_session()
out = []
home = jf.fetch(s, jf.SOURCE).text
for ev in jf.collect(home):
    out.append(f"HOME {ev['start']:%m-%d %H:%M}Z | {ev['title']} | {ev.get('competition')} | ch={ev.get('channels')}")
for url, comp in jf.TOURNAMENTS:
    for ev in jf.collect_tournament(jf.fetch(s, url).text, comp):
        if ev["start"] > datetime.now(timezone.utc) - timedelta(days=3):
            out.append(f"TOURN {ev['start']:%m-%d %H:%M}Z | {ev['title']} | {comp} | ch={ev.get('channels')}")
for m in re.finditer(r"الفيصلي", home):
    out.append("RAW " + re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", home[max(0, m.start()-500):m.start()+300]))[:400]); 
    if len(out) > 60: break
print("::notice::" + "%0A".join(out)[:9500])
