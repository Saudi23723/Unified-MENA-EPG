#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""السلة والقدم الأمريكية — the ninth channel: the NBA and the NFL, alone.

Asked for in those words — "maybe it's better if we make another channel
for NFL/NBA separately all games" — and answered in the same words: both
leagues came OFF channel 2 and every game of both is here, whether a
network is named for it or not.

Nothing about the drawing, the guide or the reel is written twice. The
other-sports generator already knows how to turn a list of events into
boards, an XML guide and a second UAE-clock set; this module hands it
this channel's name, mark, files and board stem for the length of one
build and hands them back afterwards, exactly the way the baseball
channel does. So the channels cannot drift apart in how a row is drawn,
ordered or marked live.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta

import dubai_time
import nba_espn
import nfl_espn
import other_sports_epg as base
from epg_lib import log, new_session, warn
from today_matches_epg import in_the_readers_order as channels_in_order
from today_matches_epg import shorter

CHANNEL_ID = "HoopsGridiron"
CHANNEL_AR = "السلة والقدم الأمريكية"
SUBTITLE = "الدوري الأمريكي للسلة والقدم الأمريكية"
OUTPUT = "hoops_gridiron_epg.xml"
BOARD_PREFIX = "hoops_gridiron_"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/hoops_gridiron.png")

DUBAI_OUTPUT = "dubai_hoops_gridiron_epg.xml"
DUBAI_CHANNEL_ID = "HoopsGridironDubai"
DUBAI_BOARD_PREFIX = "dubai_hoops_gridiron_"

# The only two leagues this channel carries, in the order asked for. A
# sport absent from here can never reach the board.
IN_ORDER = ("NBA", "NFL")
RANK = {sport: place for place, sport in enumerate(IN_ORDER)}


def wear_this_channel(**also):
    """Put the shared generator in this channel's clothes for a block."""
    return dubai_time.the_other_clock(
        base.__dict__,
        CHANNEL_ID=CHANNEL_ID, CHANNEL_AR=CHANNEL_AR, SUBTITLE=SUBTITLE,
        OUTPUT=OUTPUT, BOARD_PREFIX=BOARD_PREFIX, LOGO=LOGO,
        IN_ORDER=IN_ORDER, RANK=RANK, **also)


def collect(session, floor: datetime, ceiling: datetime) -> list[dict]:
    """Every timed game of both leagues inside the window — all of them.

    A game with no network keeps its row: "all games" was the ask, and a
    row with an empty broadcaster line still tells a reader the game is
    on and when.
    """
    events = nba_espn.collect(session, floor, ceiling)
    events += nfl_espn.collect(session, floor, ceiling)
    inside = [event for event in events
              if floor <= event["start"] < ceiling
              and event.get("sport") in RANK]

    # Two feeds, one broadcast, one row — the same folding the other
    # channels do, so a game listed twice keeps every channel it was
    # listed with.
    inside = base.one_row_per_ball_game(inside)
    inside = base.one_row_per_broadcast(inside)
    kept = [event for event in inside
            if base.a_live_event(event.get("title", ""))]
    log(f"  {len(events)} game(s) offered, {len(kept)} timed and live")
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
            event["channels"] = [shorter(name) for name
                                 in channels_in_order(event["channels"])]

        ok = base.publish_all(events, now) == 0

        # THE SECOND CLOCK — the same games with every time printed in
        # the Gulf's, on its own link, exactly as the other channels do.
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
                warn(f"the UAE-clock NBA/NFL guide could not be written "
                     f"({exc}) — the published one is unchanged")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
