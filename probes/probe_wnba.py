#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Why channel 8 carries no WNBA row.

The published guide holds 15 MLB rows and nought WNBA. This asks the
league's own scoreboard, day by day across the board's window, and
prints what it answers before any conclusion is drawn from it: how many
events, what state each is in, and which of this module's four filters
each one dies on.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

from epg_lib import fetch, new_session
import wnba_espn
from mlb_espn import _channels


def main() -> int:
    session = new_session()
    today = datetime.now(timezone.utc)
    print(f"today is {today:%Y-%m-%d} UTC\n")
    total = 0
    for step in range(-1, 5):
        day = today + timedelta(days=step)
        try:
            got = fetch(session, wnba_espn.SCOREBOARD,
                        params={"dates": day.strftime("%Y%m%d")})
            data = got.json()
        except Exception as exc:                              # noqa: BLE001
            print(f"  {day:%Y-%m-%d}  UNREACHABLE  {type(exc).__name__} {exc}")
            continue
        events = data.get("events") or []
        print(f"  {day:%Y-%m-%d}  {len(events)} event(s) in the feed")
        total += len(events)
        for event in events:
            comps = event.get("competitions") or []
            comp = comps[0] if comps else {}
            state = ((event.get("status") or {}).get("type") or {})
            chans = _channels(comp) if comp else []
            why = []
            if not comps:
                why.append("no competition block")
            if state.get("state") != "pre":
                why.append(f"state={state.get('state')!r} not 'pre'")
            if comp.get("timeValid") is False:
                why.append("timeValid False")
            if not (event.get("date") or ""):
                why.append("no date")
            print(f"      {event.get('name','?')[:52]:<52}"
                  f"  {event.get('date','')}  chans={chans}")
            print(f"        -> {'KEPT' if not why else 'dropped: ' + '; '.join(why)}")
    print(f"\n  {total} event(s) across the window")

    # and what the module itself makes of the same window
    floor = today - timedelta(days=1)
    rows = wnba_espn.collect(session, floor, today + timedelta(days=3))
    print(f"  collect() returned {len(rows)} row(s)")
    for r in rows[:10]:
        print(f"    {r['start']:%Y-%m-%d %H:%M}  {r['title']}  {r['channels']}")

    # is the season simply over? the feed says so itself
    try:
        got = fetch(session, wnba_espn.SCOREBOARD)
        d = got.json()
        print("\n  scoreboard with no date asked:")
        print("    season:", d.get("season"))
        print("    day   :", (d.get("day") or {}).get("date"))
        print("    events:", len(d.get("events") or []))
        for lg in (d.get("leagues") or [])[:1]:
            print("    calendar entries:", len(lg.get("calendar") or []))
            cal = lg.get("calendar") or []
            if cal:
                print("    first:", cal[0], " last:", cal[-1])
    except Exception as exc:                                  # noqa: BLE001
        print("  season probe failed:", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
