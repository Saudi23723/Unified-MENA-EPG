"""Does livefootballtv's front page name Shasha on upcoming rows? Read with
today_matches_epg's own row reader. Commits nothing."""

import re
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

import today_matches_epg as tm

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}
now = datetime.now(timezone.utc)
html = requests.get(tm.SOURCE, headers=UA, timeout=40).text
rows = tm.collect(html, now, now - timedelta(days=1), now + timedelta(days=21))
days = sorted({r["start"].astimezone(tm.GULF).date() for r in rows})
print(f"front page: {len(rows)} row(s) over {len(days)} day(s): {days[:10]}")
for r in rows:
    chans = " / ".join(r["channels"])
    if re.search(r"shasha|شاشا", chans, re.I) or re.search(r"gulf|serie a|primeira", r["competition"], re.I):
        print(f"  {r['start'].astimezone(tm.GULF):%a %d/%m %H:%M} KSA | {r['title']} | "
              f"{r['competition']} | {chans[:160]}")

soup = BeautifulSoup(html, "html.parser")
for a in soup.find_all("a", href=True):
    t = a.get_text(" ", strip=True)
    if re.search(r"gulf|shasha|شاشا|khaleeji", a["href"] + " " + t, re.I):
        print("link:", repr(t[:60]), a["href"][:120])
for path in ("/competition/arabian-gulf-cup", "/competition/gulf-cup",
             "/tournament/arabian-gulf-cup"):
    r = requests.get("https://www.livefootballtv.info" + path, headers=UA, timeout=30)
    print(path, r.status_code, len(r.text))
