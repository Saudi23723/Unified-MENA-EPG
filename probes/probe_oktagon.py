"""OSN: clock check between the two Egypt feeds, and the best logo each source offers. Never fails."""
import base64
import io
import re
from collections import Counter
from datetime import datetime

import requests
from PIL import Image

S = requests.Session()
S.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
E1 = S.get("https://www.open-epg.com/files/egypt1.xml", timeout=60).text
E2 = S.get("https://www.open-epg.com/files/egypt2.xml", timeout=60).text


def rows(t, cid):
    out = []
    for m in re.finditer(r'<programme start="([^"]+)" stop="[^"]+" channel="%s"(.*?)</programme>' % re.escape(cid), t, re.S):
        tt = re.search(r"<title[^>]*>(.*?)</title>", m.group(2), re.S)
        out.append((datetime.strptime(m.group(1), "%Y%m%d%H%M%S %z"), (tt.group(1) if tt else "").strip().casefold()))
    return out


for a, b in (("أو إس إن وان.eg", "OSN TV One.eg"), ("أو إس إن موفيز أكشن.eg", "OSN TV Movies Action.eg"),
             ("أو إس إن كوميدي.eg", "OSN TV Comedy.eg")):
    ra, rb = rows(E1, a), rows(E2, b)
    ca = Counter(t for _, t in ra); cb = Counter(t for _, t in rb)
    ua = {t: s for s, t in ra if ca[t] == 1}; ub = {t: s for s, t in rb if cb[t] == 1}
    d = Counter(int((ua[t] - ub[t]).total_seconds() // 60) for t in set(ua) & set(ub))
    print("CLOCK", b, "shared", sum(d.values()), d.most_common(3))

for t, name in ((E1, "E1"), (E2, "E2")):
    for m in re.finditer(r'<channel id="([^"]*(?:OSN|Osn|أو إس إن)[^"]*)"[^>]*>(.*?)</channel>', t, re.S):
        icon = re.search(r'<icon src="([^"]+)"', m.group(2))
        print("ICON", name, m.group(1), icon.group(1) if icon else "-")

page = S.get("https://www.elcinema.com/tvguide/", timeout=30).text
for m in re.finditer(r'href="/tvguide/(\d+)/"[^>]*>(.*?)</a>', page, re.S):
    n = re.sub(r"<[^>]+>|\s+", " ", m.group(2)).strip()
    if re.search(r"osn|أو إس إن|او اس ان", n, re.I):
        print("ELC", m.group(1), n)
imgs = sorted(set(re.findall(r'(https://media\d+\.elcinema\.com/tvguide/\d+_\d+\.(?:png|jpg))', page)))
print("ELC-IMGS", len(imgs), imgs[:5])
