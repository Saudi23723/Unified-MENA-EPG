"""Do UFC BJJ cards have their own event pages on ufc.com? Never fails."""
import os, re, sys
sys.path.insert(0, os.getcwd())
from epg_lib import new_session
S = new_session()
h = S.get("https://www.ufc.com/ufcbjj", timeout=60).text
print("LINKS", sorted(set(re.findall(r'href="([^"]*(?:event|bjj|card)[^"]*)"', h, re.I)))[:60])
for slug in ("ufc-bjj-11", "ufc-bjj-12", "ufc-bjj-13", "ufc-bjj-10", "ufcbjj-11"):
    for base in ("https://www.ufc.com/event/", "https://www.ufc.com/events/"):
        try:
            r = S.get(base + slug, timeout=40)
            t = r.text
            ts = re.findall(r'data-(?:main-card-|prelims-card-|early-card-)?timestamp="(\d+)"', t)
            title = re.search(r"<title>([^<]*)", t)
            print(f"URL {base+slug} {r.status_code} final={r.url} ts={ts[:4]} title={title.group(1) if title else None}")
        except Exception as exc:
            print("URL", base + slug, "FAIL", exc)
w = S.get("https://en.wikipedia.org/w/index.php?title=UFC_BJJ&action=raw", timeout=60).text
i = w.find("List of events")
print("WIKIRAW", len(w), w[i:i+4000] if i >= 0 else w[:200])
