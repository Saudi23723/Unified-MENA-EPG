#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: why is Thursday thin and Friday empty?

Friday is answered already — the window ended at the clock time of the
build, so the last board only ever saw the small hours of its own day.
That is fixed; this measures what the two pages actually offer for each
day of the fixed window, and — the part no log has ever shown — WHICH
COMPETITIONS ARE BEING DROPPED, day by day, with counts.

A guide that quietly discards a whole family of football looks exactly
like a guide with no data. The difference has to be visible.

Delete once read.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

import live_football_on_tv as second
import today_matches_epg as today
from epg_lib import fetch, new_session


def main() -> int:
    now = datetime.now(timezone.utc)
    session = new_session()
    floor, ceiling = today.window_floor(now), today.window_ceiling(now)
    print(f"window {floor:%m-%d %H:%M}Z .. {ceiling:%m-%d %H:%M}Z  "
          f"({(ceiling - floor).days} whole days)")
    print(f"boards for {[str(d) for d in today.days_of(now)]}")

    primary = today.collect(fetch(session, today.SOURCE).text, now,
                            floor, ceiling)
    secondary = second.fetch_events(session, floor, ceiling)
    print(f"\nprimary {len(primary)} | secondary {len(secondary)}")

    everything = today.unify(primary, secondary)

    per_day: dict = defaultdict(lambda: {"keep": Counter(), "drop": Counter()})
    for e in everything:
        day = e["start"].astimezone(today.VIEWER).date()
        side = "keep" if today.wanted(e) else "drop"
        per_day[day][side][e["competition"] or "(no competition named)"] += 1

    for day in today.days_of(now):
        rows = per_day.get(day, {"keep": Counter(), "drop": Counter()})
        kept = sum(rows["keep"].values())
        lost = sum(rows["drop"].values())
        print(f"\n===== {day}  —  {kept} shown, {lost} dropped =====")
        if rows["keep"]:
            print("  SHOWN:")
            for name, n in rows["keep"].most_common():
                print(f"    {n:3d}  {name}")
        if rows["drop"]:
            print("  DROPPED:")
            for name, n in rows["drop"].most_common(40):
                print(f"    {n:3d}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
