#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the Sky reader itself on a runner and print every row it returns.

probe_the_card.py established that Sky answers 200 and that its JSON
carries the card split into programmes. That is a fact about the feed.
It is not a fact about `sky_epg.events()`, which is the code that has to
turn the feed into board rows — channel names, sport, start, title —
and which the gate only ever exercised against a fixture.

So this runs the real function against the real feed, in the same window
the board builds, and prints what comes back. If the prelims are in the
list with a channel and a minute, the reader works where it matters. If
the list is empty, this says so instead of a board quietly losing a row.

It prints. It writes nothing and publishes nothing.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

import requests

import sky_epg


def main() -> int:
    session = requests.Session()
    now = datetime.now(timezone.utc)
    floor = now.replace(hour=0, minute=0, second=0, microsecond=0)
    ceiling = floor + timedelta(days=10)

    print(f"window {floor:%Y-%m-%d} .. {ceiling:%Y-%m-%d}\n")

    on_air = sky_epg.channels(session)
    print(f"fight channels Sky lists: {len(on_air)}")
    for sid, name in sorted(on_air, key=lambda pair: pair[1]):
        print(f"    {sid:<12} {name}")

    rows = sky_epg.events(session, floor, ceiling)
    print(f"\nrows the reader returns: {len(rows)}\n")
    for event in sorted(rows, key=lambda e: e["start"]):
        print(f"    {event['start']:%Y-%m-%d %H:%M}  {event['sport']:<7}"
              f"  {event['title'][:60]:<60}  {', '.join(event['channels'])}")

    prelims = [e for e in rows if "prelim" in e["title"].lower()]
    print(f"\nof those, prelim rows: {len(prelims)}")
    for event in sorted(prelims, key=lambda e: e["start"]):
        print(f"    {event['start']:%Y-%m-%d %H:%M}  {event['title']}")

    if not rows:
        print("\nNOTHING CAME BACK — the reader is not earning its place.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
