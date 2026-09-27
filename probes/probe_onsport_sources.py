#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Which reader actually names an ON Sport channel — asked, not assumed.

ON Sport's four per-channel pages are archives; that was measured. The
fix added live-footballontv.com because it was the one source the BOARD
reads that this guide did not, and the board had the missing fixture.

A FULL BUILD HAS RUN WITH THAT FIX AND THE GUIDE IS UNCHANGED — still
four matches, none of them tonight's. So the deduction was probably
wrong: live-footballontv is a British listings site, and the board also
reads yallakora, which is Egyptian and names Egyptian channels.

That is a guess about which of two readers carried it, and guessing
between two readings is what this repository has paid for most today.
So both are run, and every label each of them produces is printed
beside what onsport_channel_from_label makes of it. Three answers are
possible and they need different fixes:

    live-footballontv names ON Sport, but the label is refused
        -> the name gate is too strict for the spelling it uses
    live-footballontv never names ON Sport at all
        -> the wrong source was added; it costs a fetch and gives nothing
    yallakora names it
        -> that is the source this guide was missing

It prints. It writes nothing.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

import live_football_on_tv
import yallakora
from epg_lib import new_session
from update_onsport_epg import ON_SPORT_NAME, onsport_channel_from_label

UTC = timezone.utc


def look(name: str, events: list[dict]) -> None:
    print(f"\n── {name}: {len(events)} fixture(s) in the window")

    named = [one for one in events if one.get("channels")]
    print(f"   {len(named)} name at least one channel")

    labels: dict[str, int] = {}
    for one in events:
        for label in one.get("channels") or []:
            labels[label] = labels.get(label, 0) + 1

    # Anything whose label so much as mentions ON Sport, and what the
    # guide's own gate does with it. This is the whole question.
    mentions = {label: n for label, n in labels.items()
                if ON_SPORT_NAME.search(label or "")}
    print(f"   labels mentioning ON Sport: {len(mentions)}")
    for label, n in sorted(mentions.items(), key=lambda kv: -kv[1]):
        print(f"      {label!r:<40} x{n}  -> "
              f"{onsport_channel_from_label(label)}")
    if not mentions:
        print("      NONE. This source cannot feed ON Sport's guide at all.")
        egypt = [one for one in events
                 if "egypt" in (one.get("competition") or "").lower()
                 or "مصر" in (one.get("competition") or "")]
        print(f"      (it does carry {len(egypt)} Egyptian fixture(s); "
              f"their channels are:)")
        for one in egypt[:6]:
            print(f"         {one['start']:%m-%d %H:%M} {one['title'][:38]:<38}"
                  f" {one.get('channels')}")

    print(f"   its twelve commonest labels, for comparison:")
    for label, n in sorted(labels.items(), key=lambda kv: -kv[1])[:12]:
        print(f"      {label!r:<44} x{n}")


def main() -> int:
    session = new_session()
    now = datetime.now(UTC)
    floor = now.replace(hour=0, minute=0, second=0, microsecond=0)
    ceiling = floor + timedelta(days=4)
    print(f"window {floor:%Y-%m-%d} .. {ceiling:%Y-%m-%d}")

    try:
        look("live-footballontv (the source that was added)",
             live_football_on_tv.fetch_events(session, floor, ceiling))
    except Exception as exc:                                  # noqa: BLE001
        print(f"   UNREACHABLE {str(exc)[:100]}")

    try:
        look("yallakora (Egyptian, and reads a channel per block)",
             yallakora.fetch_events(session, floor, ceiling))
    except Exception as exc:                                  # noqa: BLE001
        print(f"   UNREACHABLE {str(exc)[:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
