#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Which broadcasters Spor Ekranı actually prints, and on what.

Asked for: TRT Spor 1/2/3, S Sport 1 and 2, and HT Spor, on live and
upcoming events. Before a line of that is wired, the source is asked
what it answers — every channel name it prints, spelled its own way,
and for the six asked for, the rows they carry and the sport each row
is filed under. A channel counted in a page is not a row on a board.
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, ".")

from bs4 import BeautifulSoup

from epg_lib import fetch, new_session, norm
import turkish_sport_grid as grid

ASKED = re.compile(r"trt\s*spor|s\s*sport|ht\s*spor", re.I)


def main() -> int:
    session = new_session()
    got = fetch(session, grid.SOURCE)
    if (got.encoding or "").lower() in ("", "iso-8859-1", "latin-1"):
        got.encoding = "utf-8"
    soup = BeautifulSoup(got.text, "html.parser")
    rows = grid._rows(soup)
    print(f"{len(rows)} row(s) in the grid\n")

    every = Counter()
    by_channel = defaultdict(list)
    sport_of_asked = Counter()
    mapped_of_asked = Counter()

    for row in rows:
        icon = row.select_one("img.event-list__sport-icon")
        word = (icon.get("alt") or "").strip().lower() if icon else ""
        league = grid._text(row, "p.event-list__league")
        title = grid._text(row, "p.event-list__name")
        clock = grid._text(row, "span.event-list__time")

        names = []
        for img in row.select("div[class*=channel] img"):
            name = norm(img.get("alt") or "")
            if name and name not in names:
                names.append(name)
        for name in names:
            every[name] += 1
        for name in names:
            if ASKED.search(name):
                by_channel[name].append((clock, word, title, league))
                sport_of_asked[word] += 1
                mapped_of_asked[grid.A_SPORT.get(word) or
                                f"NOT MAPPED ({word or 'no icon'})"] += 1

    print("=== EVERY CHANNEL THE GRID PRINTS, spelled its own way ===")
    for name, count in every.most_common():
        mark = "  <<< asked for" if ASKED.search(name) else ""
        print(f"  {count:4d}  {name}{mark}")

    print("\n=== THE SIX ASKED FOR: is the name there at all? ===")
    for want in ("TRT Spor", "TRT Spor 1", "TRT Spor 2", "TRT Spor 3",
                 "S Sport", "S Sport 1", "S Sport 2", "S Sport Plus",
                 "HT Spor"):
        hits = [n for n in every if n.lower() == want.lower()]
        near = [n for n in every
                if want.lower().replace(" ", "") in n.lower().replace(" ", "")]
        print(f"  {want:<14} exact: {hits or '—'}   near: {near or '—'}")

    print("\n=== WHAT SPORT THOSE ROWS ARE FILED UNDER ===")
    for word, count in sport_of_asked.most_common():
        print(f"  {count:4d}  icon alt: {word or '(none)'}")
    print("\n  after this repo's own sport map:")
    for sport, count in mapped_of_asked.most_common():
        print(f"  {count:4d}  {sport}")

    print("\n=== THE ROWS THEMSELVES ===")
    for name in sorted(by_channel):
        rows_here = by_channel[name]
        print(f"\n  --- {name} ({len(rows_here)} row(s)) ---")
        for clock, word, title, league in rows_here:
            mapped = grid.A_SPORT.get(word) or "DROPPED"
            print(f"    {clock:>5}  [{word or '?':<16}] -> {mapped:<16}"
                  f"  {title}  |  {league}")

    print("\n=== AND WHAT THE BUILDER KEEPS TODAY ===")
    kept = grid.collect(got.text)
    keeping = Counter()
    for event in kept:
        for name in event["channels"]:
            keeping[name] += 1
    print(f"  {len(kept)} row(s) kept, by channel:")
    for name, count in keeping.most_common():
        mark = "  <<< asked for" if ASKED.search(name) else ""
        print(f"    {count:4d}  {name}{mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
