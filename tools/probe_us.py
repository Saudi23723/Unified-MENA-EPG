#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: are the American channels already here, just hidden?

Every row on the board shows ONE channel and then "+5". If Fox, NBC, CBS
or USA Network are among those five, nothing needs finding — the guide
already knows and is simply not saying. That is a different fix from
adding a source, so it gets measured first.

Prints, for every match in the window, the WHOLE channel list from every
source, and counts how often an American broadcaster is named.

Delete once read.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from datetime import datetime, timezone

import live_football_on_tv
import own_guides
import spor_ekrani
import today_matches_epg as today
import yallakora
from epg_lib import fetch, new_session

AMERICAN = re.compile(
    r"\bfox\b|fs1|fs2|\bnbc\b|peacock|\bcbs\b|paramount|\bespn\b|"
    r"\busa network\b|\btelemundo\b|univision|tudn|\btnt\b|truTV|"
    r"\bcbc\b|sportsnet|\btsn\b|apple tv|amazon", re.I)


def main() -> int:
    now = datetime.now(timezone.utc)
    session = new_session()
    floor, ceiling = today.window_floor(now), today.window_ceiling(now)

    everything = today.unify(
        today.collect(fetch(session, today.SOURCE).text, now, floor, ceiling),
        live_football_on_tv.fetch_events(session, floor, ceiling))
    asked = [e for e in yallakora.fetch_events(session, floor, ceiling)
             if any(n in e["competition"] for n in today.YALLAKORA_ONLY)]
    everything = today.unify(
        everything, [e for e in asked if not today.already_on_air(e, everything)])

    events = [dict(e, channels=today.real_channels(e["channels"]))
              for e in everything if today.wanted(e)]
    own_guides.add_channels(events, spor_ekrani.broadcasts(session))

    print(f"\n=== every channel on every kept match ({len(events)}) ===")
    seen: Counter = Counter()
    american = 0
    for e in events:
        marks = [f"**{c}**" if AMERICAN.search(c) else c for c in e["channels"]]
        if any(AMERICAN.search(c) for c in e["channels"]):
            american += 1
        for c in e["channels"]:
            seen[c] += 1
        print(f"  {e['start']:%m-%d %H:%M}Z  {e['title'][:34]:34} "
              f"| {', '.join(marks) if marks else '—'}")

    print(f"\n{american} of {len(events)} match(es) name an American channel")
    print("\n=== every distinct channel name, by how often ===")
    for name, n in seen.most_common(60):
        mark = "  <-- US" if AMERICAN.search(name) else ""
        print(f"   {n:3d}  {name}{mark}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
