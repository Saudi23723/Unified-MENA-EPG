"""Where UFC BJJ publishes its upcoming events, from a runner. Never fails."""
import os, re, sys
sys.path.insert(0, os.getcwd())
from epg_lib import new_session
S = new_session()
URLS = [
    "https://www.ufc.com/events",
    "https://www.ufcbjj.com/",
    "https://www.ufcbjj.com/events",
    "https://ufcfightpass.com/",
    "https://r.jina.ai/https://www.tapology.com/search?term=UFC+BJJ&mainSearchFilter=events",
    "https://r.jina.ai/https://www.tapology.com/fightcenter?group=tv",
    "https://r.jina.ai/https://www.tapology.com/fightcenter",
    "https://r.jina.ai/https://www.ufc.com/events",
    "https://r.jina.ai/https://ufcfightpass.com/schedule",
    "https://en.wikipedia.org/wiki/UFC_BJJ",
    "https://www.sherdog.com/organizations/UFC-BJJ",
]
for url in URLS:
    try:
        r = S.get(url, timeout=60)
        t = r.text
        hits = [m.start() for m in re.finditer(r"(?i)ufc\s*bjj|road to the title|fight pass invitational", t)]
        print(f"URL {url} status={r.status_code} bytes={len(t)} hits={len(hits)}")
        seen = 0
        for h in hits:
            snip = re.sub(r"\s+", " ", t[max(0, h-200):h+300])
            print("   ...", snip[:500])
            seen += 1
            if seen >= 6:
                break
    except Exception as exc:
        print(f"URL {url} FAIL {exc}")
