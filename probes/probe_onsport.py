#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print what ON Sport's own pages carry, row by row.

Reported: ON Sport's guide does not have the Al-Ahly match. Checked, and
it is exactly so — right now that guide says

    ONSport1  ⏰ التالي غداً · AS Port - الزمالك

and it skips today's الأهلي - سموحة entirely. The words "الأهلي" and
"سموحة" appear nowhere in onsport_epg.xml.

MEANWHILE THE BOARD HAS IT, from the same site:

    10:00  الأهلي - سموحة · ON Sport

So two readers of one source disagree, and only one of them can be
right. The board reads the LISTINGS page; this guide reads the four
per-CHANNEL pages. Either those pages do not carry the match, or this
builder is dropping it — different faults with different fixes, and
this repository has a measured price for guessing between two readings.

So every ON Sport channel page is printed row by row, and each row is
searched for the match by name in both scripts. Then the same is done
for the listings page the board reads, so the two can be compared
against each other rather than against an assumption.

It prints. It writes nothing.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

import requests

BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                  " (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept-Language": "ar,en;q=0.9",
}

CHANNEL_PAGES = (
    ("ONSport1", "https://www.livefootballtv.info/channel/on-sport-1"),
    ("ONSport2", "https://www.livefootballtv.info/channel/on-sport-2"),
    ("ONSportMAX", "https://www.livefootballtv.info/channel/on-sport-max"),
    ("ONSportPLUS", "https://www.livefootballtv.info/channel/on-sport-plus"),
)
LISTINGS = "https://www.livefootballtv.info/"

# The match that is missing, in every spelling either page might use.
LOOKING_FOR = ("ahly", "ahli", "smouha", "smoha", "الأهلي", "الاهلي", "سموحة")

TAGS = re.compile(r"<[^>]+>")


def plain(html: str) -> str:
    return re.sub(r"\s+", " ", TAGS.sub(" ", html))


def rows_of(html: str) -> list[str]:
    """Every table row and list item, as text — whatever the page uses."""
    found = re.findall(r"<tr\b.*?</tr>", html, re.S | re.I)
    if not found:
        found = re.findall(r"<li\b.*?</li>", html, re.S | re.I)
    return [line for line in (plain(one).strip() for one in found) if line]


def one_page(session, name: str, url: str, show: int) -> None:
    print(f"\n── {name}")
    print(f"   {url}")
    try:
        page = session.get(url, timeout=30, headers=BROWSER)
    except Exception as exc:                                  # noqa: BLE001
        print(f"   UNREACHABLE  {str(exc)[:100]}")
        return
    print(f"   {page.status_code}  {len(page.content) // 1024} KB")
    if page.status_code != 200:
        return

    body = plain(page.text).lower()
    print("   is the missing match anywhere in this page at all?")
    for word in LOOKING_FOR:
        where = body.find(word.lower())
        print(f"      {word:<10} {'YES at ' + str(where) if where >= 0 else 'no'}")

    rows = rows_of(page.text)
    print(f"   {len(rows)} row(s); the first {show}:")
    for row in rows[:show]:
        print(f"      | {row[:150]}")

    hits = [row for row in rows
            if any(w.lower() in row.lower() for w in LOOKING_FOR)]
    print(f"   rows naming the missing match: {len(hits)}")
    for row in hits[:4]:
        print(f"      >> {row[:170]}")


def main() -> int:
    session = requests.Session()
    print(f"asked at {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC\n")
    print("=" * 70)
    print("THE FOUR PER-CHANNEL PAGES — what this guide reads")
    print("=" * 70)
    for name, url in CHANNEL_PAGES:
        one_page(session, name, url, show=12)

    print("\n" + "=" * 70)
    print("THE LISTINGS PAGE — what the board reads, and which HAS the match")
    print("=" * 70)
    one_page(session, "listings", LISTINGS, show=0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
