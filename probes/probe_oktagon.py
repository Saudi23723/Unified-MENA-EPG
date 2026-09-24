"""UFC BJJ's own page and Wikipedia's event list, printed. Never fails."""
import os, re, sys, html
sys.path.insert(0, os.getcwd())
from epg_lib import new_session
S = new_session()
def text(h):
    h = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))
r = S.get("https://www.ufc.com/ufcbjj", timeout=60)
h = r.text
print("UFCBJJ", r.status_code, len(h))
for m in re.finditer(r'data-[a-z-]*timestamp="(\d+)"', h):
    print("  TS", m.group(0), h[max(0,m.start()-300):m.start()].replace("\n"," ")[-300:])
for m in re.finditer(r'href="(/event/[^"]+)"', h):
    print("  EVENTLINK", m.group(1))
t = text(h)
for m in re.finditer(r"(?i)(upcoming|road to the title|ufc bjj \d|invitational|fight pass)", t):
    print("  TXT", t[max(0,m.start()-150):m.start()+250])
    break
print("TEXT HEAD", t[:3000])
w = S.get("https://en.wikipedia.org/wiki/UFC_BJJ", timeout=60).text
wt = text(w)
i = wt.find("Events")
for key in ("Scheduled events", "Upcoming events", "Past events", "Event list", "List of events"):
    j = wt.find(key)
    print("WIKI", key, j, wt[j:j+1500] if j >= 0 else "")
