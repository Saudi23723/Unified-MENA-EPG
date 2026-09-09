#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Turkish PPV — the tenth channel: the Turkish grid's own listings, alone.

Asked for in those words: the full Spor Ekranı grid — every sport and
every competition it carries, with tabii, S Sport / S Sport Plus and
beIN CONNECT marked PPV beside their name — was to leave channel 2 and
stand on a channel of its own, "cloned coding so it's easier".

So nothing about the drawing, the guide or the reel is written twice.
The other-sports generator already turns a list of events into boards,
an XML guide and a second UAE-clock set; this module lends it this
channel's name, mark, files and board stem for the length of one build
and hands them back after, exactly the way the baseball and NBA/NFL
channels do. The two clocks, the row geometry and the live mark cannot
drift apart from the rest of the service.

The rows come from turkish_sport_grid.py alone: the sport is the icon's
own word, the clock is Istanbul's, the channel is the one printed in
the row. A row with no broadcaster reads PPV, and a carrier a viewer
buys the event on reads "tabii PPV", "S Sport Plus PPV", "beIN CONNECT
PPV" — the same wording asked for on channel 2 and kept here with it.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta

import dubai_time
import other_sports_epg as base
import turkish_sport_grid
from epg_lib import log, new_session, warn
from today_matches_epg import in_the_readers_order as channels_in_order
from today_matches_epg import shorter

CHANNEL_ID = "TurkishPPV"
CHANNEL_AR = "🇹🇷 Turkish PPV"
SUBTITLE = "كل رياضة وكل بطولة على الشاشات التركية"
OUTPUT = "turkish_ppv_epg.xml"
BOARD_PREFIX = "turkish_ppv_"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/turkish_ppv.png")

DUBAI_OUTPUT = "dubai_turkish_ppv_epg.xml"
DUBAI_CHANNEL_ID = "TurkishPPVDubai"
DUBAI_BOARD_PREFIX = "dubai_turkish_ppv_"

# Every sport the grid can name, in the reader's order. A sport the
# grid's own icon map cannot produce never reaches the board, and one
# absent from here never reaches it either.
IN_ORDER = (
    "Olympics",
    "F1", "MotoGP", "WRC",
    "Boxing", "MMA",
    "Tennis", "Padel", "Snooker", "Darts", "Golf",
    "Volleyball", "Beach Volleyball", "Handball", "Futsal", "Rugby",
    "Cycling", "Athletics", "Swimming", "Triathlon",
)
RANK = {sport: place for place, sport in enumerate(IN_ORDER)}


def wear_this_channel(**also):
    """Put the shared generator in this channel's clothes for a block."""
    return dubai_time.the_other_clock(
        base.__dict__,
        CHANNEL_ID=CHANNEL_ID, CHANNEL_AR=CHANNEL_AR, SUBTITLE=SUBTITLE,
        OUTPUT=OUTPUT, BOARD_PREFIX=BOARD_PREFIX, LOGO=LOGO,
        IN_ORDER=IN_ORDER, RANK=RANK, BOARD_STYLE="info", **also)


def collect(session, floor: datetime, ceiling: datetime) -> list[dict]:
    """Every live row of the Turkish grid inside the window, folded once."""
    events = turkish_sport_grid.events(session)
    inside = [event for event in events
              if floor <= event["start"] < ceiling
              and event.get("sport") in RANK]

    # One row per broadcast — the same fold channel 2 does, so a fixture
    # the grid prints twice keeps every channel it was printed with.
    inside = base.one_row_per_broadcast(inside)
    kept = [event for event in inside
            if base.a_live_event(event.get("title", ""))]
    log(f"  {len(events)} row(s) offered, {len(kept)} live and inside the "
        f"window")
    return sorted(kept, key=lambda e: (e["start"], RANK[e["sport"]]))


def build() -> int:
    now = datetime.now(base.UTC)
    with wear_this_channel():
        days = base.days_of(now)
        floor = base.start_of_day(days[0])
        ceiling = base.start_of_day(days[-1] + timedelta(days=1))

        session = new_session()
        events = collect(session, floor, ceiling)
        for event in events:
            event["channels"] = [base.ppv_beside(shorter(name)) for name
                                 in channels_in_order(event["channels"])]
            if not event["channels"]:
                event["channels"] = ["PPV"]

        ok = base.publish_all(events, now) == 0

        # THE SECOND CLOCK — the same rows with every time printed in the
        # Gulf's, on its own link, exactly as the other channels do.
        with dubai_time.the_other_clock(
                base.__dict__,
                VIEWER=dubai_time.DUBAI, VIEWER_NAME=dubai_time.DUBAI_NAME,
                OUTPUT=DUBAI_OUTPUT, CHANNEL_ID=DUBAI_CHANNEL_ID,
                BOARD_PREFIX=DUBAI_BOARD_PREFIX):
            try:
                base.publish_all(events, now,
                                 days=dubai_time.days_the_events_span(
                                     now, events, dubai_time.DUBAI))
            except Exception as exc:                          # noqa: BLE001
                warn(f"the UAE-clock Turkish PPV guide could not be written "
                     f"({exc}) — the published one is unchanged")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
