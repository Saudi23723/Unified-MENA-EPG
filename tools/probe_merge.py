#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: what the two pages give once merged. Delete once read."""
from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timezone

import live_football_on_tv as second
import today_matches_epg as today
from epg_lib import fetch, new_session


def main() -> int:
    now = datetime.now(timezone.utc)
    session = new_session()
    floor = today.window_floor(now)

    primary = today.collect(fetch(session, today.SOURCE).text, now)
    secondary = second.fetch_events(session, now, today.KEEP_AHEAD, floor)
    print(f"\nprimary {len(primary)} | secondary {len(secondary)}")

    print("\n-- days the second page put in the window --")
    for day, count in sorted(Counter(
            e["start"].date() for e in secondary).items()):
        print(f"  {day}  x{count}")

    print("\n-- competitions the second page named, and the verdict --")
    kept = dropped = 0
    for name, count in Counter(
            e["competition"] for e in secondary).most_common():
        keep = today.wanted({"competition": name, "title": "",
                             "channels": ["Sky Sports"], "start": now})
        kept += count if keep else 0
        dropped += 0 if keep else count
        if keep:
            print(f"  {count:4d}  KEEP  {name!r}")
    print(f"  ... and {dropped} fixture(s) in competitions not asked for")

    print("\n-- same minute on both pages --")
    for a in primary:
        for b in secondary:
            if abs(a["start"] - b["start"]) > today.MERGE_SLACK:
                continue
            if today.same_match(a["title"], b["title"]):
                print(f"  JOIN  {a['start']:%m-%d %H:%M}Z  "
                      f"{a['title']!r} + {b['title']!r}")

    everything = today.unify(primary, secondary)
    keep = [e for e in everything if today.wanted(e)]
    print(f"\n-- the board: {len(keep)} of {len(everything)} --")
    for e in keep:
        print(f"  {e['start']:%m-%d %H:%M}Z  {e['title']}"
              f"  | {e['competition']}  | {e['channels'][:3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
