#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What reaches the Turkish board now the two sports are mapped.

The measuring probe beside this one showed the block was never a channel
filter — it was the sport map, which had no futbol and no basketbol, so
TRT Spor, S Sport and HT Spor arrived with nothing. This one runs the
real path afterwards and prints what actually lands, and checks the one
thing that must NOT change: channel 2 still refusing both sports.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from datetime import timedelta

sys.path.insert(0, ".")

import other_sports_epg as base
import turkish_ppv_epg as turkish
import turkish_sport_grid as grid
from epg_lib import new_session

ASKED = re.compile(r"trt\s*spor|s\s*sport|ht\s*spor", re.I)


def main() -> int:
    session = new_session()
    now = base.datetime.now(base.UTC)

    with turkish.wear_this_channel():
        days = base.days_of(now)
        floor = base.start_of_day(days[0])
        ceiling = base.start_of_day(days[-1] + timedelta(days=1))
        kept = turkish.collect(session, floor, ceiling)
        for event in kept:
            event["channels"] = [
                base.ppv_beside(turkish.shorter(name))
                for name in turkish.channels_in_order(event["channels"])]

    print(f"\n=== {len(kept)} ROW(S) ON THE TURKISH BOARD ===")
    by_channel = Counter()
    for event in sorted(kept, key=lambda e: e["start"]):
        when = event["start"].astimezone(grid.ISTANBUL).strftime("%H:%M")
        mark = " <<<" if any(ASKED.search(c) for c in event["channels"]) else ""
        print(f"  {when}  {event['sport']:<12} {event['title'][:44]:<44}"
              f"  {' · '.join(event['channels'])}{mark}")
        for name in event["channels"]:
            by_channel[name] += 1

    print("\n  by channel:")
    for name, count in by_channel.most_common():
        mark = "  <<< asked for" if ASKED.search(name) else ""
        print(f"    {count:4d}  {name}{mark}")

    asked = sum(count for name, count in by_channel.items()
                if ASKED.search(name))
    print(f"\n  rows carried by TRT Spor / S Sport / HT Spor: {asked}")

    print("\n=== AND CHANNEL 2 STILL REFUSES BOTH SPORTS ===")
    for sport in ("Football", "Basketball"):
        row = {"sport": sport, "title": "Alpha - Beta",
               "channels": ["TRT Spor"], "start": now}
        print(f"  {sport:<11} in channel 2's RANK: {sport in base.RANK:<5}"
              f"  wanted() on channel 2: {base.wanted(row)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
