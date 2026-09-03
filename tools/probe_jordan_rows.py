#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Where the FULL Jordanian fixture list is, since the homepage is shallow.

Printing the whole of jfa.jo's "المباريات القادمة" block settled why
الوحدات and الفيصلي are not on the board, and it was not the filter:

    the whole table            16 club rows
      6 already played
      7 under-16 and youth national team
      2 youth ties published under "كأس الأردن"
      1 left:  البقعة - دوقرة

    الفيصلي   0 mentions ANYWHERE on the page
    الوحدات   1 mention, and it is an under-16 row
    السلط 0   العربي 0

They never reached the reader. The homepage block shows the nearest
handful of fixtures, and a ten-club league plays five matches a round, so
the round is not on that page at all.

So this looks for the page that has the whole thing, by reading the
site's own links rather than guessing at urls — guessing is what cost
five builds on this very site.
"""
from __future__ import annotations

import re
import sys

sys.path.insert(0, ".")

from bs4 import BeautifulSoup                                  # noqa: E402

import jordan_football as jfa                                  # noqa: E402
from epg_lib import fetch, new_session, norm                   # noqa: E402

# A page of fixtures says so in its own words, in Arabic or in a slug.
LOOKS_LIKE_FIXTURES = re.compile(
    r"مباريات|جدول|الدوري|نتائج|ترتيب|match|fixture|schedule|league|result",
    re.I)


def rows_on(page: str) -> tuple[int, int]:
    """(club rows, rows still to be played) — the only two numbers that count."""
    soup = BeautifulSoup(page, "html.parser")
    clubs = upcoming = 0
    for row in soup.find_all("tr"):
        if row.select_one("span.team1") and row.select_one("span.team2"):
            clubs += 1
            verdict = row.select_one("span.rrresult")
            if verdict and jfa.NOT_PLAYED_YET.match(
                    norm(verdict.get_text(" ", strip=True))):
                upcoming += 1
    return clubs, upcoming


def main() -> int:
    session = new_session()
    home = fetch(session, jfa.SOURCE).text
    soup = BeautifulSoup(home, "html.parser")

    links, seen = [], set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].split("#")[0].strip()
        label = norm(anchor.get_text(" ", strip=True))
        if not href or href.startswith(("mailto:", "javascript:", "tel:")):
            continue
        if href.startswith("http") and "jfa.jo" not in href:
            continue
        if not (LOOKS_LIKE_FIXTURES.search(href)
                or LOOKS_LIKE_FIXTURES.search(label)):
            continue
        full = href if href.startswith("http") else \
            jfa.SOURCE.rstrip("/") + "/" + href.lstrip("/")
        if full not in seen:
            seen.add(full)
            links.append((full, label))

    print(f"the homepage links to {len(links)} page(s) that name fixtures, "
          f"a schedule or the league\n")
    for url, label in links[:28]:
        try:
            reply = session.get(url, timeout=25)
        except Exception as exc:
            print(f"  SHUT  {url}  ({type(exc).__name__})")
            continue
        if reply.status_code != 200:
            print(f"  {reply.status_code}   {url}")
            continue
        clubs, upcoming = rows_on(reply.text)
        flag = "  <== MORE THAN THE HOMEPAGE" if clubs > 16 else ""
        print(f"  200  {len(reply.text):>7}b  {clubs:>3} club row(s), "
              f"{upcoming:>3} still to play   {url}"
              f"\n           “{label[:60]}”{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
