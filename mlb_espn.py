#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Baseball for channel 2, from the league's own scoreboard.

Asked for in the reader's own words: "I want to add MLB and Baseball
world series". Baseball was on this board once, came off it, and comes
back with a source that carries the one thing the earlier one did not —
the broadcaster, published by the league's own feed, per game:

    Tampa Bay Rays at Atlanta Braves  2026-09-10T16:15Z  pre
        broadcasts: ESPN Unlmtd, MLB.TV, BravesVision, Rays.TV

WHY THIS SOURCE. ESPN's public scoreboard is the league's live feed:
every game of the day, an ISO instant in UTC (no printed clock to place
in a timezone — the fault this repository has paid for most), a status
that says whether the game is still to come, and the networks carrying
it. The postseason arrives on the same endpoint with its own series
wording, so the Wild Card, the Division Series, the Championship Series
and the WORLD SERIES need nothing written down here: the feed labels
them and the label is printed beside the game.

WHAT IT IS NOT. It is not a listings page and does not pretend to be
one: a game the feed gives no network for is dropped, exactly as every
other source on this board is made to. The board may never put a viewer
on a channel that is not carrying the game.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from epg_lib import fetch, log, norm, warn

SCOREBOARD = ("https://site.web.api.espn.com/apis/site/v2/sports/"
              "baseball/mlb/scoreboard")

# Not a broadcaster a viewer can be sent to: the league's own in-app
# products and the blackout placeholders beside them.
NOT_A_CHANNEL = ("mlb.tv", "tbd", "tba", "local", "streaming")

# A NATIONAL BROADCAST, or nothing. Baseball plays fifteen games a night
# and every one of them names a network, so reading the feed whole put
# eighty rows on a four-day board and buried the fights and the racing
# under them — which is exactly the mess that took the sport off this
# board the first time. A regional feed (Rays.TV, MASN, YES) is not a
# channel a viewer here can turn to anyway. So the regular season is
# kept to the games the whole country is shown, and October is kept
# whole: every postseason game is a national broadcast by definition.
# The names, exactly. A regional feed spells itself with the national
# broadcaster's own word in front of it — "NBC Sports Philadelphia",
# "SportsNet LA" — so the test is the WHOLE name and not a word inside
# it, or every regional feed in the league walks back in.
NATIONAL = {
    "espn", "espn2", "espn unlmtd", "espn+", "abc", "fox", "fs1", "fs2",
    "tbs", "tnt", "nbc", "peacock", "mlb network", "mlbn",
    "apple tv", "apple tv+", "prime video", "amazon prime video",
    "netflix", "roku", "sportsnet", "tsn", "bein sports", "starzplay",
}


def _national(name: str) -> bool:
    return norm(name).casefold().rstrip(".") in NATIONAL


A_POSTSEASON = re.compile(
    r"world series|championship series|division series|wild card"
    r"|postseason|all-star", re.I)


def _channels(competition: dict) -> list[str]:
    out: list[str] = []
    for block in competition.get("broadcasts") or []:
        for name in block.get("names") or []:
            name = norm(name)
            if not name or name.casefold() in NOT_A_CHANNEL:
                continue
            if name not in out:
                out.append(name)
    return out


def _competition_name(event: dict, competition: dict) -> str:
    """The series the game belongs to, in the feed's own words.

    The regular season prints "MLB"; October prints what October is —
    "World Series Game 3", "AL Championship Series" — and that is the
    line a reader wants beside a game in October.
    """
    for note in competition.get("notes") or []:
        head = norm(note.get("headline") or "")
        if head:
            return head
    season = (event.get("season") or {}).get("slug") or ""
    if "post" in season.casefold():
        return "MLB Postseason"
    return "MLB"


def _title(event: dict, competition: dict) -> str:
    """Two sides, the way every other head-to-head row here is written."""
    sides = competition.get("competitors") or []
    home = away = ""
    for side in sides:
        team = side.get("team") or {}
        name = norm(team.get("displayName") or team.get("name") or "")
        if side.get("homeAway") == "home":
            home = name
        elif side.get("homeAway") == "away":
            away = name
    if home and away:
        return f"{away} - {home}"
    return norm(event.get("name") or "")


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
        channels = national or channels
        title = _title(event, competition)
        if not title:
            continue
        out.append({
            "start": start,
            "title": title,
            "competition": where,
            "sport": "MLB",
            "channels": channels,
        })
    return out


def collect(session, floor: datetime, ceiling: datetime) -> list[dict]:
    """Every timed, broadcast MLB game inside the board's window.

    The window is walked a day at a time because the scoreboard is a
    day's endpoint, and a day either side is added so a game at the far
    edge of the window is never lost to the boundary between UTC and the
    reader's own clock.
    """
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
            warn(f"MLB scoreboard {day:%Y-%m-%d} is unreachable ({exc}) — "
                 f"the board keeps what the other days gave it")
        day += timedelta(days=1)
    log(f"  MLB: {len(out)} game(s) with a first pitch")
    return out
