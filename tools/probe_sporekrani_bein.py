#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
What does Spor Ekranı publish for beIN SPORTS Türkiye?

This repository already reads Spor Ekranı, but only for tabii: of the 120
broadcasts on the page a recent run took 13, and never looked at the rest.
The site states the channel of every broadcast in schema.org publishedOn,
so if it names beIN channels it is a source of exactly what the beIN
guide is thinnest on — the live fixture, under its own name, on the
channel actually carrying it.

That matters most for three things the current guide gets wrong or
cannot answer:

  MAX 1 and MAX 2   every source fills their day with the channel's own
                    name repeated, which is not a schedule
  beIN SPORTS 5     open-epg lists round 14 of the Turkish basketball
                    league, twice a day, in August. Either the channel is
                    replaying a dead season or the feed is stale, and a
                    live fixture listed here would settle it
  the replay loops  beIN 1 to 4 run last week's matches round the clock;
                    which of them is live tonight is not stated anywhere

Prints every broadcast Spor Ekranı puts on a beIN channel, with the time
and whether the site marks it live. Reads only; writes nothing.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from epg_lib import new_session  # noqa: E402
from update_tabii_epg import (  # noqa: E402
    LD_JSON_RE, SPOREKRANI_URL, fetch, parse_utc,
)

TR = timezone(timedelta(hours=3))

# "beIN SPORTS 1", "beIN Sports MAX 2", "bein sports haber" — the site's
# own spelling varies, so the match is deliberately loose.
BEIN_RE = re.compile(
    r"be\s*in\s*sports?\s*(max\s*\d|haber|\d)?", re.I)


def channels_of(event: dict) -> list[str]:
    """Every channel name the site attaches to this broadcast."""
    published = event.get("publishedOn")
    entries = (published if isinstance(published, list)
               else [published] if published else [])
    out = []
    for entry in entries:
        if isinstance(entry, dict):
            name = (entry.get("name") or "").strip()
            if name:
                out.append(name)
    return out


def main() -> int:
    session = new_session()
    page = fetch(session, SPOREKRANI_URL).text

    events = []
    for block in LD_JSON_RE.findall(page):
        try:
            payload = json.loads(block)
        except Exception:
            continue
        for event in (payload if isinstance(payload, list) else [payload]):
            if isinstance(event, dict):
                events.append(event)

    print(f"Spor Ekranı: {len(events)} broadcast(s) on the page\n")

    # Every channel the site names, so nothing is missed by a bad regex.
    names = Counter()
    for event in events:
        for name in channels_of(event):
            names[name] += 1
    print(f"--- all {len(names)} channel name(s) it publishes ---")
    for name, count in names.most_common():
        mark = "  <-- beIN" if BEIN_RE.search(name) else ""
        print(f"    {count:>3}  {name}{mark}")
    print()

    # The beIN broadcasts themselves.
    per = defaultdict(list)
    for event in events:
        slot = event.get("broadcastOfEvent")
        slot = slot if isinstance(slot, dict) else {}
        start = parse_utc(slot.get("startDate"))
        stop = parse_utc(slot.get("endDate"))
        title = (slot.get("name") or event.get("name") or "").strip()
        if not start or not title:
            continue
        for name in channels_of(event):
            if BEIN_RE.search(name):
                per[name].append({
                    "start": start, "stop": stop, "title": title,
                    "live": event.get("isLiveBroadcast") is True,
                })

    if not per:
        print("No broadcast on the page is attributed to a beIN channel.")
        return 0

    print(f"--- {sum(len(v) for v in per.values())} beIN broadcast(s) ---")
    for name in sorted(per):
        print(f"\n  {name}")
        for ev in sorted(per[name], key=lambda e: e["start"]):
            start = ev["start"].astimezone(TR)
            span = ""
            if ev["stop"]:
                span = f"-{ev['stop'].astimezone(TR):%H:%M}"
            live = "  LIVE" if ev["live"] else ""
            print(f"      {start:%m-%d %H:%M}{span}  {ev['title'][:52]}{live}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
