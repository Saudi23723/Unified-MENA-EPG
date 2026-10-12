#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""الألعاب الكبرى — the thirteenth channel: the multi-sport games, alone.

Asked for in those words: a new channel on the dashboard, on both links,
"only for multi-sport events, like the Olympics or Asian Nagoya or other
championships", with those events moved OFF channel 2, built from scratch
and like the others, and channel 2 kept "for the rest of the sports like
boxing" with nothing mixed up.

WHERE THE ROWS COME FROM. Channel 2 already reads every door these
events come through — the listings pages that mark a fixture Olympic,
beIN's own guide for the Asian Games, the checked-in official session
schedules in major_games.py — and folds two sources of one broadcast into
one row. Reading all of them a second time would double the slowest part
of every pass for the same rows. So channel 2 collects them as it always
did, judges them by the same wanted(), and hands them over in a file
(other_sports_epg.hand_off_the_games); this build runs straight after it
and publishes them. If the hand-off is missing or stale — channel 2
failed, or this was run alone — this build collects them itself through
the very same collector, wearing this channel's list of sports.

Nothing about the drawing, the guide or the reel is written twice: this
module lends the other-sports generator this channel's name, mark, files
and board stem for one build, exactly the way the NBA/NFL, baseball and
Turkish channels do, and the second set in the Gulf's clock is drawn the
same way theirs is.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta

import dubai_time
import other_sports_epg as base
from epg_lib import log, new_session, warn
from today_matches_epg import in_the_readers_order as channels_in_order
from today_matches_epg import shorter

CHANNEL_ID = "MultiSport"
CHANNEL_AR = "الألعاب الكبرى"
SUBTITLE = "الأولمبياد والدورات الرياضية الكبرى"
OUTPUT = "multi_sport_epg.xml"
BOARD_PREFIX = "multi_sport_"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/multi_sport.png")

DUBAI_OUTPUT = "dubai_multi_sport_epg.xml"
DUBAI_CHANNEL_ID = "MultiSportDubai"
DUBAI_BOARD_PREFIX = "dubai_multi_sport_"

# The only events this channel carries, in the order channel 2 carried
# them. A sport absent from here can never reach the board.
IN_ORDER = base.MULTI_SPORT
RANK = dict(base.MULTI_SPORT_RANK)

# A hand-off older than this is not the pass this build belongs to.
FRESH = timedelta(hours=2)


def wear_this_channel(**also):
    """Put the shared generator in this channel's clothes for a block."""
    return dubai_time.the_other_clock(
        base.__dict__,
        CHANNEL_ID=CHANNEL_ID, CHANNEL_AR=CHANNEL_AR, SUBTITLE=SUBTITLE,
        OUTPUT=OUTPUT, BOARD_PREFIX=BOARD_PREFIX, LOGO=LOGO,
        IN_ORDER=IN_ORDER, RANK=RANK, **also)


def collect(session, floor: datetime, ceiling: datetime) -> list[dict]:
    """The games channel 2 handed on, or the same rows collected here."""
    handed = base.games_handed_off(FRESH)
    if handed is None:
        log("  multi-sport games: no fresh hand-off from channel 2 — "
            "collecting them here through the same collector")
        return base.collect(session, floor, ceiling)
    inside = [event for event in handed
              if floor <= event["start"] < ceiling
              and event.get("sport") in RANK]
    log(f"  multi-sport games: {len(inside)} row(s) from channel 2's "
        f"collection")
    return base.in_the_readers_order(inside)


def build() -> int:
    now = datetime.now(base.UTC)
    with wear_this_channel():
        days = base.days_of(now)
        floor = base.start_of_day(days[0])
        ceiling = base.start_of_day(days[-1] + timedelta(days=1))

        events = collect(new_session(), floor, ceiling)
        for event in events:
            event["channels"] = [base.ppv_beside(shorter(name)) for name
                                 in channels_in_order(event["channels"])]
            # The same wording channel 2 gave these rows: an official
            # schedule names no broadcaster, and the line says PPV rather
            # than standing empty.
            if not event["channels"]:
                event["channels"] = ["PPV"]

        ok = base.publish_all(events, now) == 0

        # THE SECOND CLOCK — the same events with every time printed in
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
                warn(f"the UAE-clock multi-sport guide could not be written "
                     f"({exc}) — the published one is unchanged")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
