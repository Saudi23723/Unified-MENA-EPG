#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: read the competition heading above each match row.

The first pass proved the page names competitions, but walking back over
every element caught channel and team names out of the previous match row.
Competitions are heading rows in the same table, so walk back over <tr>
only and take the first one that is not itself a match.

Delete this file and its workflow once the question is answered.
"""
from __future__ import annotations

import re
import sys
from collections import Counter

from bs4 import BeautifulSoup

from epg_lib import fetch, new_session

SOURCE = "https://www.livefootballtv.info/"


def text(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def is_match(row) -> bool:
    return bool(row.find("td", class_="local")
                and row.find("td", class_="visitante")
                and row.find("td", class_="canales"))


def competition_of(row) -> str:
    for previous in row.find_all_previous("tr"):
        if is_match(previous):
            continue
        head = text(previous)
        if 2 < len(head) < 90:
            return head
    return ""


def main() -> int:
    soup = BeautifulSoup(fetch(new_session(), SOURCE).text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    rows = [r for r in soup.find_all("tr") if is_match(r)]
    print(f"match rows: {len(rows)}")

    # What does a heading row actually look like?
    print("\n=== the first three heading rows, raw ===")
    shown = 0
    for r in soup.find_all("tr"):
        if is_match(r) or shown >= 3:
            continue
        if 2 < len(text(r)) < 90:
            print("  tr attrs:", dict(r.attrs), "|", text(r)[:70])
            for td in r.find_all(["td", "th"]):
                print("     ", td.name, dict(td.attrs), "|", text(td)[:60])
            shown += 1

    tally = Counter()
    print("\n=== first 30 matches with the competition above them ===")
    for r in rows[:30]:
        comp = competition_of(r)
        tally[comp] += 1
        home = text(r.find("td", class_="local"))
        away = text(r.find("td", class_="visitante"))
        print(f"  {comp[:42]:<42} | {home} - {away}"[:120])

    for r in rows[30:]:
        tally[competition_of(r)] += 1

    print(f"\n=== every competition on the page today ({len(tally)}) ===")
    for comp, n in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {n:3}  {comp[:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
