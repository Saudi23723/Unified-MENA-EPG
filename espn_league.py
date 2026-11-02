#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One reader for any ESPN league scoreboard — every game, timed, whole.

mlb_espn.py was written first and taught this repository the shape of
these feeds: a day's endpoint, an ISO instant in UTC per game (no printed
clock to place in a timezone — the fault this repository has paid for
most), a status that says whether the game is still to come, the two
sides, and whatever networks carry it.

This module is that reading, with the league left as an argument, so the
NBA and the NFL cannot drift apart from each other or from baseball in
how a game becomes a row.

WHAT IS KEPT. Every game on the card. The reader asked for "all games",
so a game with only a local broadcaster keeps its row, and a game the
feed names no network for keeps its row too — with an empty broadcaster
line rather than none at all.

WHAT IS DROPPED. A game already played (this board is live listings, not
a results page) and a game the feed has not given a real start to.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from epg_lib import fetch, log, norm, warn

# Not a broadcaster a viewer can be sent to: the in-app products and the
# blackout placeholders the feeds print beside a real network.
NOT_A_CHANNEL = ("tbd", "tba", "local", "streaming", "nba tv app",
                 "nfl+", "nba league pass")


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


def _competition_name(event: dict, competition: dict, default: str) -> str:
    """The round a game belongs to, in the feed's own words."""
    for note in competition.get("notes") or []:
        head = norm(note.get("headline") or "")
        if head:
            return head
    season = (event.get("season") or {}).get("slug") or ""
    if "post" in season.casefold():
        return f"{default} Postseason"
    return default


def _title(event: dict, competition: dict) -> str:
    """Two sides, the way every other head-to-head row here is written."""
    home = away = ""
    for side in competition.get("competitors") or []:
        team = side.get("team") or {}
        name = norm(team.get("displayName") or team.get("name") or "")
        if side.get("homeAway") == "home":
            home = name
        elif side.get("homeAway") == "away":
            away = name
    if home and away:
        return f"{away} - {home}"
    return norm(event.get("name") or "")


def _day(session, day: datetime, url: str, sport: str,
         default: str) -> list[dict]:
    got = fetch(session, url, params={"dates": day.strftime("%Y%m%d")})
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
        title = _title(event, competition)
        if not title:
            continue
        out.append({
            "start": start,
            "title": title,
            "competition": _competition_name(event, competition, default),
            "sport": sport,
            "channels": _channels(competition),
        })
    return out


def collect_league(session, floor: datetime, ceiling: datetime, url: str,
                   sport: str, default: str) -> list[dict]:
    """Every timed game of one league inside the board's window.

    The window is walked a day at a time because these are a day's
    endpoints, and a day either side is added so a game at the far edge
    is never lost to the boundary between UTC and the reader's clock.
    """
    out: list[dict] = []
    day = (floor - timedelta(days=1)).astimezone(timezone.utc)
    last = (ceiling + timedelta(days=1)).astimezone(timezone.utc)
    seen: set[tuple] = set()
    while day <= last:
        try:
            for row in _day(session, day, url, sport, default):
                key = (row["start"], row["title"])
                if key not in seen:
                    seen.add(key)
                    out.append(row)
        except Exception as exc:                              # noqa: BLE001
            warn(f"{sport} scoreboard {day:%Y-%m-%d} is unreachable ({exc})"
                 f" — the board keeps what the other days gave it")
        day += timedelta(days=1)
    log(f"  {sport}: {len(out)} game(s) with a tip-off")
    return out
