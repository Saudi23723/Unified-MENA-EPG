"""One Gulf Cup row on livefootballtv's front page, raw, and its match
page: where is the full channel list? Commits nothing."""

import os
import re
import sys

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import today_matches_epg as tm  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}
BASE = "https://www.livefootballtv.info"
soup = BeautifulSoup(requests.get(tm.SOURCE, headers=UA, timeout=40).text, "html.parser")
shown = 0
for row in soup.find_all("tr"):
    if not tm.is_match(row):
        continue
    if not re.search(r"gulf|serie a", tm.competition_of(row), re.I):
        continue
    shown += 1
    print("=" * 70)
    print(tm.competition_of(row), "|", tm.team_in(row.find("td", class_="local")),
          "-", tm.team_in(row.find("td", class_="visitante")))
    print("RAW ROW:", str(row)[:2500])
    link = next((a["href"] for a in row.find_all("a", href=True)
                 if "/match" in a["href"] or "/partido" in a["href"]
                 or re.search(r"/\d{4,}", a["href"])), None)
    print("match link:", link)
    if link and shown <= 3:
        url = link if link.startswith("http") else BASE + link
        page = requests.get(url, headers=UA, timeout=30)
        ps = BeautifulSoup(page.text, "html.parser")
        chans = [li.get("title") or li.get_text(" ", strip=True)
                 for li in ps.select("ul.listaCanales li")]
        print("match page", page.status_code, "channels:", chans[:40])
        print("  shasha on match page:", any(re.search(r"shasha|شاشا", c or "", re.I) for c in chans),
              "| anywhere in page:", bool(re.search(r"shasha|شاشا", page.text, re.I)))
    if shown >= 4:
        break
