#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print one real upcoming row from jfa.jo, whole and unedited.

The reader works on markup I wrote and returns nothing from the page:
"16 row(s), 6 already played, 0 youth, 0 fixture(s) to show". Ten
upcoming rows reach it and all ten fall out before the competition is
even considered, so either the date and the clock are not inside the row
I think they are, or the club names are not where I think they are.

Both are guesses, and I have made three about this page already. So this
prints the rows THEMSELVES — every tr inside the block that names itself
"المباريات القادمة" — at full width and with nothing summarised.
"""
from __future__ import annotations

import sys

import requests
from bs4 import BeautifulSoup


def main() -> int:
    session = requests.Session()
    session.headers.update({
        "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
        "Accept-Language": "ar,en;q=0.8",
    })
    html = session.get("https://jfa.jo/", timeout=40).text
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    block = soup.select_one("div.result2")
    print(f"div.result2 present: {block is not None}")
    if block is None:
        return 0

    rows = block.find_all("tr")
    print(f"tr inside it: {len(rows)}\n")
    for index, row in enumerate(rows[:6]):
        cells = row.find_all("td")
        print(f"--- row {index}: {len(cells)} cell(s) ---")
        print(f"    TEXT: {row.get_text(' | ', strip=True)[:240]}")
        print(f"    team1: {[s.get_text(' ', strip=True) for s in row.select('span.team1')]}")
        print(f"    team2: {[s.get_text(' ', strip=True) for s in row.select('span.team2')]}")
        print(f"    haly1: {[s.get_text(' ', strip=True) for s in row.select('span.haly1')]}")
        print(f"    rrresult: {[s.get_text(' ', strip=True) for s in row.select('span.rrresult')]}")
        print(f"    HTML: {str(row)[:1200]}\n")

    # And whatever else in the block holds the clubs, if not a tr.
    print("\n--- every span.team1 in this block, and its row ---")
    for span in block.select("span.team1")[:4]:
        tr = span.find_parent("tr")
        print(f"    {span.get_text(' ', strip=True)!r} -> "
              f"tr found: {tr is not None}")
        if tr is not None:
            print(f"        row text: {tr.get_text(' | ', strip=True)[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
