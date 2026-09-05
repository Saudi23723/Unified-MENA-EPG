#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sportsnet's own schedule, read from the API its own television runs on.

Asked for by name — "TSN AND SPORTSNET events matches to be added on
channels 1 and 2 find sources reliable ones from outside github" — and
the reliable source is not a listings page at all. Sportsnet's apps and
its own website read schedule-admin.sportsnet.ca, an open JSON feed that
needs no key and no session, and it prints the one thing a listings page
paraphrases: the event's name as the broadcaster itself spells it, the
channel that airs it as the broadcaster's own word for that channel, and
the start with a real timezone on it.

    https://schedule-admin.sportsnet.ca/v1/events?
        day_start=<epoch>&day_end=<epoch>

    "event_name": "Chelsea vs. Aston Villa"
    "sport": "soccer"
    "channel_id": "SNOne"
    "start_time_str": "Sat, 05 Sep 2026 07:20:00 -0400"

THE CHANNEL IS THE BROADCASTER'S OWN WORD. "SNOntario" is what Sportsnet
calls Sportsnet Ontario on its own dial, and this board prints what the
broadcaster prints, the same rule every other source here follows.

THE SPORT GATES THE BOARD. Soccer belongs on the football board, and
rugby and MMA on the other-sports board; baseball and the studio shows
have no row on either and are left where they sit. A "companion" feed —
the second hour of a broadcast split across two channels — is not a
second event and is skipped, and so is anything the feed itself marks
hidden.

THE TIME IS EASTERN, PRINTED AS OFFSET. The feed's start_time_str carries
"-0400" or "-0500" on every row, so the clock is read with strptime's
%z rather than guessed at — the DST boundary in November cannot put a
game an hour wrong, because the string says which side of it the game
is on.

THE FEED IS READ WITH A SINGLE PASS PER DAY, and a day is asked for in
the Eastern timezone the feed keeps its own days in, so a game that
starts late on an Eastern night is asked for on that night and not split
across two requests.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from epg_lib import fetch, log, warn

SOURCE = "https://schedule-admin.sportsnet.ca/v1/events"
EASTERN = "America/New_York"
A_DAY = "%a, %d %b %Y %H:%M:%S %z"

# How the feed's channel_id words are spelled the way a board spells a
# channel. The feed's own words are kept where they need no help — and
# "SNOne" is Sportsnet's own dial word, kept exactly.
AS_A_CHANNEL = {
    "snontario": "Sportsnet Ontario",
    "sn360": "Sportsnet 360",
    "snone": "Sportsnet One",
    "snworld": "Sportsnet World",
    "snpacific": "Sportsnet Pacific",
    "snwest": "Sportsnet West",
    "sneast": "Sportsnet East",
}

# The sports this repository's two boards carry. Soccer is the football
# board's; rugby and MMA are the other-sports board's. Everything else —
# baseball, the studio shows, the empty sport word — has no row to sit on.
AS_A_SPORT = {
    "soccer": "Football",
    "rugby": "Rugby",
    "mma": "MMA",
    "hockey": None,   # no NHL row on either board
    "baseball": None,
    "basketball": None,
    "football": None,
    "shows": None,
    "": None,
}


def events(session, floor: datetime, ceiling: datetime,
           sports: tuple[str, ...] = ("soccer", "rugby", "mma")) -> list[dict]:
    """Sportsnet's own events, in the window, in the sports asked for."""
    from zoneinfo import ZoneInfo
    out: list[dict] = []

    # A day asked for in the feed's own timezone, so a game late on an
    # Eastern night is asked for on that night.
    tz = ZoneInfo(EASTERN)
    first = floor.astimezone(tz).date()
    last = ceiling.astimezone(tz).date() - timedelta(days=1)
    a_day = first
    while a_day <= last:
        day_start = int(datetime(a_day.year, a_day.month, a_day.day,
                                 tzinfo=tz).timestamp())
        day_end = day_start + 86400
        try:
            page = fetch(session, SOURCE,
                         params={"day_start": day_start, "day_end": day_end},
                         retries=2)
            data = json.loads(page.text)
        except Exception as exc:                              # noqa: BLE001
            warn(f"sportsnet's feed is unreachable ({exc}) — the board "
                 f"keeps what its other sources gave it")
            return out
        for item in (data.get("data") or []):
            out.append(_as_an_event(item, sports))
        a_day += timedelta(days=1)

    out = [row for row in out if row is not None]
    out = [row for row in out if floor <= row["start"] < ceiling]
    for row in out:
        row["source"] = "sportsnet"
    log(f"  sportsnet: {len(out)} event(s) in the window")
    return out


def _as_an_event(item: dict, sports: tuple[str, ...]) -> dict | None:
    """One feed row as a board row, or None when the board has no place."""
    if item.get("hidden"):
        return None
    # A companion feed is the same broadcast's second hour on another
    # channel, not a second event.
    if item.get("game_type") == "companion":
        return None
    if item.get("game_type") == "shows":
        return None

    the_sport = (item.get("sport") or "").casefold()
    if the_sport not in sports:
        return None

    name = (item.get("event_name") or "").strip()
    when = (item.get("start_time_str") or "").strip()
    where = (item.get("channel_id") or "").strip()
    if not name or not when or not where or where == " ":
        return None

    # The feed's own sport word is not the whole truth — its studio
    # shows carry the sport of the night they talk about, and "Blair &
    # Barker" is a talk show on Sportsnet 360, not a match. A name with
    # "vs." in it names two sides; a name with a colon and a date in it
    # names a programme.
    if "vs" not in name.casefold():
        return None

    try:
        start = datetime.strptime(when, A_DAY)
    except ValueError:
        warn(f"sportsnet printed a clock this reader cannot read "
             f"('{when}') — the event is left alone")
        return None

    channel = AS_A_CHANNEL.get(where.casefold(), where)
    return {
        "start": start.astimezone(timezone.utc),
        "title": name,
        "sport": AS_A_SPORT.get(the_sport, the_sport),
        "channels": [channel],
        # The league the feed itself prints, because the board's own
        # wanted() test reads the competition and a title alone —
        # "Chelsea vs. Aston Villa" — names no league at all.
        "league": (item.get("league") or "").casefold(),
    }
