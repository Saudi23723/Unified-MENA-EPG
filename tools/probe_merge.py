#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: what the two sources actually give, merged.

The sandbox this was written in cannot reach either listings page, so the
only place the merge can be measured is a runner. This prints, for one
real pass:

  * how many matches each page saw in the window,
  * every competition the second page named, with counts, so a family
    nobody asked for cannot slip onto the board unnoticed,
  * which fixtures the merge joined, and by which pair of spellings,
  * any two same-minute fixtures it did NOT join, which is where a
    duplicate row would come from, and
  * the final list, as the board will show it.

Delete once read.
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timezone

import today_matches_epg as today
import live_football_on_tv as second
from epg_lib import fetch, new_session


def main() -> int:
    now = datetime.now(timezone.utc)
    session = new_session()
    floor = today.window_floor(now)

    primary = today.collect(fetch(session, today.SOURCE).text, now)
    secondary = second.fetch_events(session, now, today.KEEP_AHEAD, floor)
    print(f"\nprimary {len(primary)} | secondary {len(secondary)}")

    print("\n-- every competition the second page named --")
    for name, count in Counter(e["competition"] for e in secondary).most_common():
        verdict = "KEEP" if today.wanted(e := {"competition": name,
                                               "title": "", "channels": ["x"],
                                               "start": now}) else "drop"
        print(f"  {count:4d}  {verdict}  {name!r}")
    del e

    print("\n-- same kickoff on both pages: joined, or left as two rows --")
    for a in primary:
        for b in secondary:
            if abs(a["start"] - b["start"]) > today.MERGE_SLACK:
                continue
            joined = today.same_match(a["title"], b["title"])
            if joined or a["title"].casefold()[:4] == b["title"].casefold()[:4]:
                print(f"  {'JOIN' if joined else 'TWO '}  "
                      f"{a['start']:%m-%d %H:%M}Z  "
                      f"{a['title']!r}  vs  {b['title']!r}")

    everything = today.unify(primary, secondary)
    keep = [e for e in everything if today.wanted(e)]
    print(f"\n-- the board: {len(keep)} of {len(everything)} --")
    for e in keep:
        print(f"  {e['start']:%m-%d %H:%M}Z  {e['title']}"
              f"  │ {e['competition']}  │ {e['channels']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
