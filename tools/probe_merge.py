#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: which page has the right clock? Delete once read.

Every fixture the two pages share came out an hour apart, the first page
later. One of them is wrong for every match on the channel, so this
measures the gap across every shared fixture rather than the handful that
happened to print, and shows the first page's own displayed clock beside
the markup it publishes.
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timezone

from bs4 import BeautifulSoup

import live_football_on_tv as second
import today_matches_epg as today
from epg_lib import fetch, new_session, norm


def main() -> int:
    now = datetime.now(timezone.utc)
    session = new_session()
    html = fetch(session, today.SOURCE).text

    primary = today.collect(html, now)
    secondary = second.fetch_events(session, now, today.KEEP_AHEAD,
                                    today.window_floor(now))

    print("\n-- the same fixture on both pages, matched on clubs alone --")
    gaps: Counter[int] = Counter()
    for a in primary:
        for b in secondary:
            if not today.same_match(a["title"], b["title"]):
                continue
            gap = round((a["start"] - b["start"]).total_seconds() / 60)
            if abs(gap) > 6 * 60:
                continue                    # a different week, not this match
            gaps[gap] += 1
            print(f"  {gap:+4d} min  {a['title']!r}  "
                  f"first {a['start']:%m-%d %H:%M}Z  "
                  f"second {b['start']:%m-%d %H:%M}Z  | {a['competition']}")
    print(f"\n  gap in minutes -> how many fixtures: {dict(gaps)}")

    print("\n-- the first page: its own printed clock beside its markup --")
    soup = BeautifulSoup(html, "html.parser")
    shown = 0
    for row in soup.find_all("tr"):
        if not today.is_match(row):
            continue
        cell = row.find("td", class_="canales")
        meta = cell.find("meta", attrs={"itemprop": "startDate"}) if cell \
            else None
        clock = row.find("td", class_="hora")
        if not (meta and clock):
            continue
        print(f"  printed {norm(clock.get_text(' ', strip=True))!r:>10}  "
              f"markup {meta.get('content')!r}  "
              f"{today.team_in(row.find('td', class_='local'))} - "
              f"{today.team_in(row.find('td', class_='visitante'))}")
        shown += 1
        if shown >= 8:
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
