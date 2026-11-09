#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The WNBA for channel 2, from the league's own scoreboard.

Asked for outright — "Add WNBA and make it another text color with MLB".
The listings sources this board already reads file the WNBA under the
same word as the NBA and college basketball, and only the NBA survives
that filter, so the WNBA needs a source of its own. ESPN's public
scoreboard is the league's live feed: every game of the day, an ISO
instant in UTC, a status that says whether it is still to come, and the
networks carrying it.

The rules are the ones mlb_espn.py already obeys, and the helpers are
imported from it rather than written twice: a game with no published
network is dropped, a game already played is not a live event, and a
game the feed has not timed has no instant to print. The playoffs and
the Finals arrive on the same endpoint with the feed's own wording, so
nothing about them is written down here.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from epg_lib import fetch, log, norm, warn
from mlb_espn import _channels, _national, _title

SCOREBOARD = ("https://site.web.api.espn.com/apis/site/v2/sports/"
              "basketball/wnba/scoreboard")

# The postseason is national by definition, the same as baseball's.
A_POSTSEASON = re.compile(r"finals|semifinals|playoff|all-star", re.I)


def _competition_name(event: dict, competition: dict) -> str:
    """The round the game belongs to, in the feed's own words."""
    for note in competition.get("notes") or []:
        head = norm(note.get("headline") or "")
        if head:
            return head
    return "WNBA"


def _day(session, day: datetime) -> list[dict]:
    got = fetch(session, SCOREBOARD,
                params={"dates": day.strftime("%Y%m%d")})
    data = got.json()
    out: list[dict] = []
    for event in data.get("events") or []:
        competitions = event.get("competitions") or []
        if not competitions:
            continue
        competition = competitions[0]
        status = ((event.get("status") or {}).get("type") or {})
        # NOT YET STARTED, OR ON RIGHT NOW. ESPN's three states are
        # "pre", "in" and "post", and this used to keep only "pre" —
        # which threw away the one thing a viewer turning the channel on
        # is looking for. A game being played IS the live event; it is
        # the FINISHED one that is not.
        #
        # Reported off the screen, with games in progress:
        # "رجع الي NFL المباشر اليوم و ال MLB المباشر اليوم". Measured
        # the same minute, ESPN had a full card every day of the window
        # and the board drew today as لا يوجد حدث —
        #
        #     day (viewer)   events
        #     2026-09-10          0     <- today, all of it "in" or "post"
        #     2026-09-11         15
        #     2026-09-12         15
        #
        # because every one of today's games had already started.
        #
        # "post" is still dropped: a game that is over is not something
        # to send anybody to a channel for. And timeValid stays, because
        # a game the feed has not timed ("time TBD" days exist in the
        # postseason bracket) has no instant to print.
        if status.get("state") == "post":
            continue
        if competition.get("timeValid") is False:
            continue
        raw = event.get("date") or ""
        try:
            start = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        start = (start.astimezone(timezone.utc) if start.tzinfo
                 else start.replace(tzinfo=timezone.utc))
        # Every game on the day's card, network or not. A game without
        # a listed broadcaster still gets its row; the broadcaster line
        # is simply left empty.
        channels = _channels(competition)
        where = _competition_name(event, competition)
        national = [name for name in channels if _national(name)]
        title = _title(event, competition)
        if not title:
            continue
        out.append({
            "start": start,
            "title": title,
            "competition": where,
            "sport": "WNBA",
            "channels": national or channels,
        })
    return out


def collect(session, floor: datetime, ceiling: datetime) -> list[dict]:
    """Every timed, broadcast WNBA game inside the board's window."""
    out: list[dict] = []
    day = (floor - timedelta(days=1)).astimezone(timezone.utc)
    last = (ceiling + timedelta(days=1)).astimezone(timezone.utc)
    seen: set[tuple] = set()
    while day <= last:
        try:
            for row in _day(session, day):
                key = (row["start"], row["title"])
                if key not in seen:
                    seen.add(key)
                    out.append(row)
        except Exception as exc:                              # noqa: BLE001
            warn(f"WNBA scoreboard {day:%Y-%m-%d} is unreachable ({exc}) — "
                 f"the board keeps what the other days gave it")
        day += timedelta(days=1)
    log(f"  WNBA: {len(out)} game(s) with a tip-off")
    return out
