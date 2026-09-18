#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Every event channel 2 was offered and did NOT publish, with the reason.

The reader asked whether channel 2 is missing any event from any source.
A source answering is only half the question. collect() prints "N offered,
M in the window, K in a sport asked for and naming a channel", and the
difference between those numbers is exactly where an event goes missing —
that line gives the size of the gap and never its contents.

So this asks the same sources collect() asks, in the same order, and then
walks each row through the same rules in the same order, naming the one
that dropped it:

    outside the window   real, just starts after the board's last day —
                         not a fault
    sport not carried    IN_ORDER does not name that sport. MLB, the WNBA,
                         the NBA and the NFL fall here BY DESIGN, each
                         having been moved to a channel of its own
    off this board       the competitions this channel was told to drop
    not a live event     a preview, a panel, a replay: refused by name
    a rebroadcast        the source's own repeat marking
    no channel named     and not one of the federation feeds allowed
                         through without one
    already over         finished before now

A row under "sport not carried" naming a sport the reader DOES want is the
real find. Everything else is the board working as written.

Reads only. Publishes nothing, writes nothing, touches no guide.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

import other_sports_epg as ch2
from epg_lib import new_session, status_of

UTC = timezone.utc
ALLOWED_WITHOUT_CHANNEL = ("worldball", "fivb", "fivb-indoor", "uww",
                          "majorgames", "bkfc")


def offered_rows(session, floor, ceiling):
    """The same collectors collect() calls, each tagged with its name."""
    import american_sport_on_tv, beach_volley_fivb, bkfc, boxing_promotions
    import espn_fights, major_games, own_guides, pbc
    import real_american_freestyle, sky_epg, spanish_sport_grid, sportsnet
    import tapology, tsn, world_ball_feed, world_sport_on_tv
    import womens_volley_fivb, wrestling_uww

    calls = [
        ("world_sport_on_tv",       lambda: world_sport_on_tv.events(session)),
        ("american_sport_on_tv",    lambda: american_sport_on_tv.events(session)),
        ("spanish_sport_grid",      lambda: spanish_sport_grid.events(session)),
        ("world_ball_feed",         lambda: world_ball_feed.events(session)),
        ("beach_volley_fivb",       lambda: beach_volley_fivb.events(session, floor, ceiling)),
        ("womens_volley_fivb",      lambda: womens_volley_fivb.events(session, floor, ceiling)),
        ("wrestling_uww",           lambda: wrestling_uww.events(session, floor, ceiling)),
        ("major_games",             lambda: major_games.events(floor, ceiling)),
        ("boxing_promotions",       lambda: boxing_promotions.collect(session, floor, ceiling)),
        ("own_guides.fights",       lambda: own_guides.fights_our_guides_have(floor, ceiling)),
        ("own_guides.events",       lambda: own_guides.events_our_guides_have(floor, ceiling)),
        ("sky_epg",                 lambda: sky_epg.events(session, floor, ceiling)),
        ("real_american_freestyle", lambda: real_american_freestyle.events(session, floor, ceiling)),
        ("pbc",                     lambda: pbc.events(session, floor, ceiling)),
        ("espn_fights",             lambda: espn_fights.events(session, floor, ceiling)),
        ("tapology",                lambda: tapology.events(session, floor, ceiling)),
        ("bkfc",                    lambda: bkfc.events(session, floor, ceiling)),
        ("tsn",                     lambda: tsn.events(session, floor, ceiling)),
        ("sportsnet",               lambda: sportsnet.events(session, floor, ceiling)),
    ]
    rows, per_source = [], {}
    for name, call in calls:
        try:
            got = call() or []
        except Exception as exc:
            per_source[name] = f"RAISED {type(exc).__name__}"
            continue
        per_source[name] = len(got)
        for event in got:
            if isinstance(event, dict):
                event.setdefault("_from", name)
                rows.append(event)
    return rows, per_source


def why_dropped(event, floor, ceiling, now):
    start = event.get("start")
    if not start or not (floor <= start < ceiling):
        return "outside the window"
    if event.get("sport") not in ch2.RANK:
        return f"sport not carried: {event.get('sport') or '—'}"
    if ch2.off_this_board(event):
        return "off this board"
    if not ch2.a_live_event(event.get("title", "")):
        return "not a live event"
    if ch2.an_obvious_rebroadcast(event):
        return "a rebroadcast"
    if not event.get("channels") and event.get("source") not in ALLOWED_WITHOUT_CHANNEL:
        return "no channel named"
    if event.get("sport") == "Snooker" and not any(
            n.casefold().startswith(ch2.SNOOKER_CHANNELS)
            for n in event.get("channels", [])):
        return "snooker off an allowed channel"
    if status_of(event, now) == "over":
        return "already over"
    return None


def main() -> int:
    now = datetime.now(UTC)
    days = ch2.days_of(now)
    floor = ch2.start_of_day(days[0])
    ceiling = ch2.start_of_day(days[-1] + timedelta(days=1))
    print(f"window {floor:%d/%m %H:%M} -> {ceiling:%d/%m %H:%M} UTC\n")

    session = new_session()
    rows, per_source = offered_rows(session, floor, ceiling)

    print(f"{'source':26} {'offered':>8}")
    print("-" * 36)
    for name, count in per_source.items():
        print(f"{name:26} {str(count):>8}")
    print("-" * 36)
    print(f"{'TOTAL':26} {len(rows):>8}\n")

    reasons = Counter()
    examples = defaultdict(list)
    kept = 0
    for event in rows:
        why = why_dropped(event, floor, ceiling, now)
        if why is None:
            kept += 1
            continue
        reasons[why] += 1
        if len(examples[why]) < 6:
            start = event.get("start")
            examples[why].append(
                f"{start:%d/%m %H:%M}" if start else "  no start  ")
            examples[why][-1] += (
                f"  {(event.get('sport') or '—'):<14}"
                f"{(event.get('title') or '')[:52]}"
                f"   [{event.get('_from')}]")

    print(f"kept through every rule: {kept} of {len(rows)}\n")
    print("DROPPED, by the rule that dropped it:")
    for why, count in reasons.most_common():
        print(f"\n  {why}  —  {count}")
        for line in examples[why]:
            print(f"      {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
