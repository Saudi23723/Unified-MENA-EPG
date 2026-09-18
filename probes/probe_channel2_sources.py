#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ask every source channel 2 reads, one at a time, and say what it gave.

The reader asked whether channel 2 is missing any event from any of its
sources. collect() adds twenty-odd collectors into one list and prints a
single total, so a source that has quietly stopped answering is invisible
there: the total still looks healthy because the others carry it. This
calls each one separately and prints its own count, so a zero has a name.

A zero is not automatically a fault — a promotion with no card this
fortnight really does have nothing — so the point is the shape of the
row: which sources answered, which raised, and which returned nothing
while their neighbours returned plenty.

Reads only. Publishes nothing, writes nothing, touches no guide.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

import other_sports_epg as ch2
from epg_lib import new_session

UTC = timezone.utc


def main() -> int:
    now = datetime.now(UTC)
    days = ch2.days_of(now)
    floor = ch2.start_of_day(days[0])
    ceiling = ch2.start_of_day(days[-1] + timedelta(days=1))
    session = new_session()

    print(f"window {floor:%d/%m %H:%M} -> {ceiling:%d/%m %H:%M} UTC "
          f"({ch2.DAYS_AHEAD} day(s))\n")

    import american_sport_on_tv, beach_volley_fivb, bkfc, boxing_promotions
    import espn_fights, major_games, own_guides, pbc
    import real_american_freestyle, sky_epg, spanish_sport_grid, sportsnet
    import tapology, tsn, world_ball_feed, world_sport_on_tv
    import womens_volley_fivb, wrestling_uww

    calls = [
        ("world_sport_on_tv",      lambda: world_sport_on_tv.events(session)),
        ("american_sport_on_tv",   lambda: american_sport_on_tv.events(session)),
        ("spanish_sport_grid",     lambda: spanish_sport_grid.events(session)),
        ("world_ball_feed",        lambda: world_ball_feed.events(session)),
        ("beach_volley_fivb",      lambda: beach_volley_fivb.events(session, floor, ceiling)),
        ("womens_volley_fivb",     lambda: womens_volley_fivb.events(session, floor, ceiling)),
        ("wrestling_uww",          lambda: wrestling_uww.events(session, floor, ceiling)),
        ("major_games",            lambda: major_games.events(floor, ceiling)),
        ("boxing_promotions",      lambda: boxing_promotions.collect(session, floor, ceiling)),
        ("own_guides.fights",      lambda: own_guides.fights_our_guides_have(floor, ceiling)),
        ("own_guides.events",      lambda: own_guides.events_our_guides_have(floor, ceiling)),
        ("sky_epg",                lambda: sky_epg.events(session, floor, ceiling)),
        ("real_american_freestyle",lambda: real_american_freestyle.events(session, floor, ceiling)),
        ("pbc",                    lambda: pbc.events(session, floor, ceiling)),
        ("espn_fights",            lambda: espn_fights.events(session, floor, ceiling)),
        ("tapology",               lambda: tapology.events(session, floor, ceiling)),
        ("bkfc",                   lambda: bkfc.events(session, floor, ceiling)),
        ("tsn",                    lambda: tsn.events(session, floor, ceiling)),
        ("sportsnet",              lambda: sportsnet.events(session, floor, ceiling)),
    ]

    print(f"{'source':26} {'rows':>6} {'in window':>10}  note")
    print("-" * 70)
    silent, broke, total = [], [], 0
    for name, call in calls:
        try:
            rows = call() or []
        except TypeError:
            # a collector whose signature differs — try the other shape
            try:
                rows = call.__wrapped__() if hasattr(call, "__wrapped__") else []
                raise
            except Exception as exc:
                broke.append((name, f"{type(exc).__name__}: {exc}"))
                print(f"{name:26} {'—':>6} {'—':>10}  RAISED {type(exc).__name__}")
                continue
        except Exception as exc:
            broke.append((name, f"{type(exc).__name__}: {exc}"))
            print(f"{name:26} {'—':>6} {'—':>10}  RAISED {type(exc).__name__}: "
                  f"{str(exc)[:40]}")
            continue
        inside = [e for e in rows
                  if isinstance(e, dict) and e.get("start")
                  and floor <= e["start"] < ceiling]
        total += len(rows)
        mark = "  <-- SILENT" if not rows else ""
        if not rows:
            silent.append(name)
        print(f"{name:26} {len(rows):>6} {len(inside):>10}{mark}")

    print("-" * 70)
    print(f"{'TOTAL offered':26} {total:>6}")
    print(f"\nsilent: {len(silent)}  {', '.join(silent) if silent else '—'}")
    print(f"raised: {len(broke)}")
    for name, why in broke:
        print(f"   {name}: {why[:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
