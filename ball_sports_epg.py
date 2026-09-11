#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""بيسبول والسلة النسائية — the eighth channel: MLB and the WNBA, alone.

Asked for in those words: baseball and the WNBA came OFF channel 2 and
were to have a channel of their own. They are here, and nowhere else.

Nothing about the drawing, the guide or the reel is written twice. The
other-sports generator already knows how to turn a list of events into
boards, an XML guide and a second UAE-clock set; this module hands it
this channel's name, mark, files and board stem for the length of one
build, exactly the way the UAE clock is worn there, and hands them back
afterwards. So the two channels cannot drift apart in how a row is
drawn, ordered or marked live.

The two leagues come from their own scoreboards (mlb_espn.py and
wnba_espn.py): a real UTC instant per game, the national networks
carrying it, and the postseason — up to the World Series and the WNBA
Finals — labelled in the feed's own words.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta

import dubai_time
import mlb_espn
import other_sports_epg as base
import wnba_espn
from epg_lib import log, new_session, warn
from today_matches_epg import in_the_readers_order as channels_in_order
from today_matches_epg import shorter

CHANNEL_ID = "BallSports"
CHANNEL_AR = "بيسبول وسلة السيدات"
SUBTITLE = "الدوري الأمريكي للبيسبول ودوري السلة للسيدات"
OUTPUT = "ball_sports_epg.xml"
BOARD_PREFIX = "ball_sports_"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/ball_sports.png")

DUBAI_OUTPUT = "dubai_ball_sports_epg.xml"
DUBAI_CHANNEL_ID = "BallSportsDubai"
DUBAI_BOARD_PREFIX = "dubai_ball_sports_"

# The only two sports this channel carries, in the order they were asked
# for. A sport absent from here can never reach the board.
IN_ORDER = ("MLB", "WNBA")
RANK = {sport: place for place, sport in enumerate(IN_ORDER)}


def wear_this_channel(**also):
    """Put the shared generator in this channel's clothes for a block."""
    return dubai_time.the_other_clock(
        base.__dict__,
        CHANNEL_ID=CHANNEL_ID, CHANNEL_AR=CHANNEL_AR, SUBTITLE=SUBTITLE,
        OUTPUT=OUTPUT, BOARD_PREFIX=BOARD_PREFIX, LOGO=LOGO,
        IN_ORDER=IN_ORDER, RANK=RANK, **also)


def collect(session, floor: datetime, ceiling: datetime) -> list[dict]:
    """Every timed, broadcast game of both leagues inside the window."""
    events = mlb_espn.collect(session, floor, ceiling)
    events += wnba_espn.collect(session, floor, ceiling)
    inside = [event for event in events
              if floor <= event["start"] < ceiling
              and event.get("sport") in RANK]

    # Two feeds, one broadcast, one row — the same folding channel 2 does,
    # so a game listed twice keeps every channel it was listed with.
    inside = base.one_row_per_ball_game(inside)
    inside = base.one_row_per_broadcast(inside)
    # EVERY GAME, ANNOUNCED OR NOT. This used to require a named
    # broadcaster, and on 2026-09-11 that threw away twelve of the
    # fifteen baseball games the feed had — only the three on a national
    # network survived. The ask was "all games, every game", so a game
    # with no announced carrier stays and simply carries no channel
    # name; the board prints PPV beside a row with none, as elsewhere.
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
                warn(f"the UAE-clock baseball guide could not be written "
                     f"({exc}) — the published one is unchanged")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
