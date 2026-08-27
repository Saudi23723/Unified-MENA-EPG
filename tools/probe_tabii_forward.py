#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Read Spor Ekranı exactly the way update_tabii_epg.py reads it, and print
every tabii broadcast it publishes with the date it falls on.

The first pass of this probe found "tabii Spor 6" sitting next to
2026-08-28 on the homepage, which contradicts what the generator's own
docstring says — that the site renders the current day and only the
current day. That claim is the reason the numbered channels are empty
from tomorrow on, so it is worth settling with the parser itself rather
than with a proximity heuristic.

Same import path as the generator, so whatever it would collect is what
is printed here. Writes nothing, commits nothing.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

# The generator lives at the repository root; this probe lives one level
# down, so the root has to be on the path before it can be imported.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from epg_lib import new_session
from update_tabii_epg import (
    LD_JSON_RE, SPOREKRANI_URL, fetch, fetch_sporekrani, tabii_numbers,
)

TR = timezone(timedelta(hours=3))


def main() -> int:
    today = datetime.now(TR).date()
    print(f"Spor Ekranı, read with the generator's own parser | "
          f"today={today} (TR)\n")

    session = new_session()
    events = fetch_sporekrani(session)

    if not events:
        print("The parser collected nothing at all.")
    else:
        by_day: dict = defaultdict(list)
        for event in events:
            by_day[event["start"].astimezone(TR).date()].append(event)

        print(f"{len(events)} tabii broadcast(s), by day:\n")
        for day in sorted(by_day):
            when = "TODAY" if day == today else (
                "TOMORROW" if day == today + timedelta(days=1) else
                f"+{(day - today).days}d" if day > today else "past")
            print(f"  {day}  ({when})  {len(by_day[day])} broadcast(s)")
            for event in sorted(by_day[day], key=lambda e: e["start"]):
                local = event["start"].astimezone(TR)
                print(f"      tabii Spor {event['number']:<2} "
                      f"{local:%H:%M}  {event['title']}")
            print()

    # How much of the page never reaches the parser: every broadcast the
    # site publishes, tabii or not, with the day it belongs to. If future
    # days are present here but absent above, the limit is our filter; if
    # they are absent here too, the limit is the source.
    print("-" * 70)
    print("Every broadcast on the page, by day, whatever the channel:\n")

    import json
    page = fetch(session, SPOREKRANI_URL).text
    days: dict = defaultdict(int)
    tabii_days: dict = defaultdict(int)
    for block in LD_JSON_RE.findall(page):
        try:
            payload = json.loads(block)
        except Exception:
            continue
        for event in (payload if isinstance(payload, list) else [payload]):
            if not isinstance(event, dict):
                continue
            slot = event.get("broadcastOfEvent")
            slot = slot if isinstance(slot, dict) else {}
            raw = slot.get("startDate")
            if not isinstance(raw, str):
                continue
            try:
                start = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            day = start.astimezone(TR).date()
            days[day] += 1
            if tabii_numbers(event):
                tabii_days[day] += 1

    for day in sorted(days):
        mark = "TODAY" if day == today else (
            "TOMORROW" if day == today + timedelta(days=1) else
            f"+{(day - today).days}d" if day > today else "past")
        print(f"  {day}  ({mark:<8}) {days[day]:>4} broadcast(s), "
              f"{tabii_days.get(day, 0)} on tabii")
    return 0


if __name__ == "__main__":
    sys.exit(main())
