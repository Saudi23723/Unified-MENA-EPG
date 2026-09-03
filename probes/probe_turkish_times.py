#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Which source put four Turkish fixtures on one day at one time.

A reader photographed the board showing, all at 17:00 on Saturday
05.09.2026:

    Fenerbahce - Besiktas            beIN 6
    Trabzonspor - Gençlerbirligi SK  beIN 5
    Basaksehir - Galatasaray         beIN 5
    Göztepe SK - Gaziantep           beIN 3

beIN's own schedule — which this repository already publishes, in
bein_sports_qatar_epg.xml, from beIN's own feed — says they are on four
different days:

    Fenerbahçe vs Beşiktaş        Sat 05-09  19:50 Istanbul
    Başakşehir vs Galatasaray     Fri 04-09  19:50
    Trabzonspor vs Gençlerbirliği Sun 06-09  19:50
    Göztepe vs Gaziantep          Mon 07-09  19:50

And the board carries Fenerbahçe - Beşiktaş TWICE: once in Arabic at
10:00 with no channel, which agrees with beIN, and once in Latin at
17:00, which does not. Seven hours apart, so unify() never even called
it a drift — DRIFT_WINDOW is six.

Several fixtures sharing one date and one clock is a shape this
repository has seen before and has a name for: 1876 fixtures once
carried a single date because a reader climbed one step too far and
found the whole list instead of one row.

So this asks every source that could have produced those rows what it
actually says about them, and prints the instant each one gives. It
changes nothing. The reader is fixed afterwards, against what this
prints.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, ".")
from epg_lib import new_session                             # noqa: E402

TURKISH = ("fenerbah", "besiktas", "beşiktaş", "galatasaray", "basaksehir",
           "başakşehir", "trabzon", "genclerbirligi", "gençlerbirliği",
           "gençlerbirligi", "goztepe", "göztepe", "gaziantep")
IST = ZoneInfo("Europe/Istanbul")
LA = ZoneInfo("America/Los_Angeles")


def is_turkish(title: str) -> bool:
    low = (title or "").casefold()
    return any(word in low for word in TURKISH)


def show(where: str, events) -> None:
    print(f"\n=== {where} " + "=" * (46 - len(where)))
    hits = [e for e in events if is_turkish(e.get("title", ""))]
    print(f"  {len(events)} event(s) offered, {len(hits)} Turkish")
    for e in sorted(hits, key=lambda x: x["start"])[:20]:
        start = e["start"]
        print(f"    {start.astimezone(timezone.utc):%a %d-%m %H:%M}Z"
              f"  │ {start.astimezone(IST):%H:%M} Ist"
              f"  │ {start.astimezone(LA):%a %H:%M} viewer"
              f"  │ {e['title'][:38]:<40} {e.get('channels')}")
    # The signature: several fixtures sharing one instant.
    seen: dict = {}
    for e in hits:
        seen.setdefault(e["start"], []).append(e["title"])
    stacked = {k: v for k, v in seen.items() if len(v) > 1}
    for when, titles in sorted(stacked.items()):
        print(f"  !! {len(titles)} fixtures share {when:%a %d-%m %H:%M}Z: "
              f"{titles}")
    if not stacked:
        print("  no two Turkish fixtures share an instant here")


def main() -> int:
    session = new_session()
    now = datetime.now(timezone.utc)
    floor, ceiling = now - timedelta(days=1), now + timedelta(days=6)

    # The primary page, fetched and read exactly as the guide does it.
    import today_matches_epg as today
    from epg_lib import fetch
    try:
        html = fetch(session, today.SOURCE).text
        show("livefootballtv (the first page)",
             today.collect(html, now, floor, ceiling))
    except Exception as exc:                                  # noqa: BLE001
        print(f"\nfirst page shut: {exc}")

    import live_football_on_tv
    try:
        show("live-footballontv (the second page)",
             live_football_on_tv.fetch_events(session, floor, ceiling))
    except Exception as exc:                                  # noqa: BLE001
        print(f"second page shut: {exc}")

    import spor_ekrani
    try:
        show("Spor Ekranı", spor_ekrani.fixtures(session))
    except Exception as exc:                                  # noqa: BLE001
        print(f"Spor Ekranı shut: {exc}")

    import yallakora
    try:
        show("yallakora", yallakora.fetch_events(session, floor, ceiling))
    except Exception as exc:                                  # noqa: BLE001
        print(f"yallakora shut: {exc}")

    import live_soccer_tv
    try:
        show("livesoccertv", live_soccer_tv.fetch_events(session, floor,
                                                         ceiling))
    except Exception as exc:                                  # noqa: BLE001
        print(f"livesoccertv shut: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
