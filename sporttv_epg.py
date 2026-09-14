#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SPORT TV Portugal — the twelfth channel: its six screens, live only.

Asked for in those words: "Sport tv portogues ضيف جميع ال مباشر عندهم
... كل المباريات و ال events ال live او scheduled Live", then "او
اعملهم قناة لحالهم", then "+ و ١ و ٢ و ٣ و ٤ و ٥ و البلس", then "بس
المباشر !".

So: a channel of its own, the way the Turkish grid got one, carrying
what SPORT TV 1 to 5 and SPORT TV+ are actually playing.

NOTHING ABOUT THE DRAWING, THE GUIDE OR THE REEL IS WRITTEN TWICE. The
other-sports generator already turns a list of events into boards, an
XML guide and a second UAE-clock set; this module lends it this
channel's name, mark, files and board stem for the length of one build
and hands them back after — exactly as the Turkish, baseball and
NBA/NFL channels do. The two clocks, the row geometry and the live mark
cannot drift from the rest of the service.

The rows come from sporttv_pt.py alone, which says what five rounds of
probes had to establish before a line of it could be written: the site's
own guide page is drawn in the browser and holds nothing, /jogos is an
empty shell, and what answers is each channel's live page — carrying a
store whose fields are INDICES into a flat table rather than values.

WHY IT NAMES A REAL LENGTH. Every row carries the duration SPORT TV
published for it, and epg_lib prefers that over the sport's table, so
مباشر comes off a row when the broadcast ends rather than when a guess
says it should. This is the only channel here whose source states one.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta

import dubai_time
import other_sports_epg as base
import sporttv_pt
from epg_lib import log, new_session, on_air_span, warn

CHANNEL_ID = "SportTVPT"
CHANNEL_AR = "🇵🇹 Sport TV"
SUBTITLE = "المباشر على Sport TV البرتغالية"
OUTPUT = "sporttv_epg.xml"
BOARD_PREFIX = "sporttv_"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/sporttv.png")

DUBAI_OUTPUT = "dubai_sporttv_epg.xml"
DUBAI_CHANNEL_ID = "SportTVPTDubai"
DUBAI_BOARD_PREFIX = "dubai_sporttv_"

# Keep a real multi-day EPG while excluding programmes that already ended.
# The source feed supplies current and scheduled broadcasts; a live-only
# snapshot was the reason this channel appeared to contain one day only.
PORTUGAL_DAYS = 3

# The sports this channel may carry, in the order it shows them. A sport
# absent here can never reach the board — the same rule every channel
# wearing this generator follows. Football leads because it is most of
# what these six screens play; the rest are in the order the reader's
# other channels use.
IN_ORDER = (
        "Football", "American Football", "Baseball", "Softball",
        "Wrestling", "Futsal", "Handball", "Basketball", "Volleyball",
        "Motorsport", "Tennis", "Padel", "Golf", "Snooker", "Darts",
        "Rugby", "Hockey", "Boxing", "MMA",
        "Cycling", "Athletics", "Swimming", "Triathlon", "Sailing",
    )
RANK = {sport: place for place, sport in enumerate(IN_ORDER)}


def wear_this_channel(**also):
    """Put the shared generator in this channel's clothes for a block."""
    return dubai_time.the_other_clock(
        base.__dict__,
        CHANNEL_ID=CHANNEL_ID, CHANNEL_AR=CHANNEL_AR, SUBTITLE=SUBTITLE,
        OUTPUT=OUTPUT, BOARD_PREFIX=BOARD_PREFIX, LOGO=LOGO,
        IN_ORDER=IN_ORDER, RANK=RANK, BOARD_STYLE="vsport",
        SHOW_PAGE_COUNT=True, **also)


def collect(session, floor: datetime, ceiling: datetime) -> list[dict]:
    """Every live contest the six screens carry inside the window."""
    events = sporttv_pt.events(session, floor, ceiling)
    # Do not discard a valid live/upcoming event merely because a source
    # introduces a new sport label. The source parsers already reject rows
    # without a contest or with editorial content; this mapping is only for
    # display order, not an eligibility gate.
    source_sports = sorted({event.get("sport") for event in events
                            if event.get("sport")})
    new_sports = [sport for sport in source_sports if sport not in RANK]
    for sport in new_sports:
        RANK[sport] = len(RANK)
    sport_kept = [event for event in events if event.get("sport")]
    if new_sports:
        log("  sporttv: retained new source sport label(s): "
            + ", ".join(new_sports))

    # Keep current and upcoming SPORTS broadcasts for the EPG. The source
    # marks scheduled rows as DIRETO too; that is useful here because an EPG
    # must show the next games, but finished rows must never remain published.
    # DAZN applies the same rule after its own Live/UpComing and editorial
    # filters, so both sources share one final time-window gate.
    now = datetime.now(base.UTC)
    current_or_upcoming = [
        event for event in sport_kept
        if event["start"] + on_air_span(event) > now
    ]
    removed = len(sport_kept) - len(current_or_upcoming)
    if removed:
        log(f"  sporttv: removed {removed} finished row(s); "
            f"{len(current_or_upcoming)} current/upcoming sports row(s)")
    return sorted(current_or_upcoming,
                  key=lambda e: (e["start"], RANK[e["sport"]]))


def build() -> int:
    now = datetime.now(base.UTC)
    with wear_this_channel():
        viewer_day = now.astimezone(base.VIEWER).date()
        days = [viewer_day + timedelta(days=n)
                for n in range(PORTUGAL_DAYS)]
        floor = base.start_of_day(days[0])
        ceiling = base.start_of_day(days[-1] + timedelta(days=1))

        session = new_session()
        events = collect(session, floor, ceiling)
        ok = base.publish_all(events, now, days=days) == 0

        # THE SECOND CLOCK — the same rows with every time printed in the
        # Gulf's, on its own link, exactly as the other channels do.
        with dubai_time.the_other_clock(
                base.__dict__,
                VIEWER=dubai_time.DUBAI, VIEWER_NAME=dubai_time.DUBAI_NAME,
                OUTPUT=DUBAI_OUTPUT, CHANNEL_ID=DUBAI_CHANNEL_ID,
                BOARD_PREFIX=DUBAI_BOARD_PREFIX, SHOW_PAGE_COUNT=True):
            try:
                base.publish_all(events, now,
                                 days=[
                                     now.astimezone(dubai_time.DUBAI).date()
                                     + timedelta(days=n)
                                     for n in range(PORTUGAL_DAYS)
                                 ])
            except Exception as exc:                          # noqa: BLE001
                warn(f"the UAE-clock Sport TV guide could not be written "
                     f"({exc}) — the published one is unchanged")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
