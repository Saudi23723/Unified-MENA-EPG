#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: the board as it will be published. Delete once read."""
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

    primary = today.collect(fetch(session, today.SOURCE).text, now)
    secondary = second.fetch_events(session, now, today.KEEP_AHEAD,
                                    today.window_floor(now))
    print(f"\nprimary {len(primary)} | secondary {len(secondary)}")

    everything = today.unify(primary, secondary)
    keep = [dict(e, channels=today.real_channels(e["channels"]))
            for e in everything if today.wanted(e)]

    print("\n-- what each page contributed to the board --")
    print(f"  {sum(1 for e in keep if any(today.same_match(e['title'], b['title']) for b in secondary))} of "
          f"{len(keep)} kept match(es) are named by the second page too")

    print(f"\n-- the board, in the reader's own clock ({today.VIEWER.key}) --")
    for day, rows in sorted(Counter(
            e["start"].astimezone(today.VIEWER).date() for e in keep).items()):
        print(f"  {day}: {rows} match(es)")
    for e in keep:
        print(f"  {e['start'].astimezone(today.VIEWER):%m-%d %H:%M}  "
              f"{e['title']}  | {e['competition']}  | "
              f"{today.channels_of(e)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
