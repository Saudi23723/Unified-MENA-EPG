#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""American football, from the league that has to say where to watch it.

The reader's ask for this board was plain: know that this one is on NBC
today. Eight listings pages were asked first and every one of them is
shut, which is worth writing down so none is tried twice:

    livesportsontv /league/nfl and /league/nba   200, 913 and 940 KB, and
        NOTHING holding a channel sits under anything holding a clock.
        ABC, ESPN, NBC and Peacock are in the page, attached to no game.
    tsn.ca              200, 144 KB, names only the word "TSN".
    sportsnet.ca        200, an 18 KB shell.
    cbc.ca/sports/live  404.
    nba.com/schedule    ships __NEXT_DATA__ and names no channel at all.
    livesportontv.com   every sport asked for, and no channel anywhere.
    pdc.tv, motogp.com  45 darts events and 878 MotoGP ones, no broadcaster.
    tvsportguide        refused the connection.
    sportsmediawatch    404.

All of them assemble the schedule in a browser, so a runner sees
furniture. The league's own site does not: it renders every game as one
complete line in its SCREEN-READER text, which is the most stable part of
any page, because accessibility labels are the last thing anybody
rewrites.

    <time datetime="2026-09-10T00:20:00Z">
    <span class="sr-only">
        Patriots at Seahawks, Wednesday, September 9th, 8:20 PM, NBC

Teams, day, clock, and the NETWORK — beside a real UTC instant.

AND THAT INSTANT IS WHY THIS SOURCE IS SAFE. "8:20 PM" is a printed clock
in nobody-says-which zone, and reading one of those is the single fault
this project has paid for most: every match an hour late once, and a
whole day out another time. The datetime attribute settles it outright,
so nothing here is placed in a timezone by assumption. A game whose block
carries no instant is refused rather than dated from the page around it.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from epg_lib import fetch, log, norm, warn

SOURCE = "https://www.nfl.com/schedules/"

# "Patriots at Seahawks, Wednesday, September 9th, 8:20 PM, NBC"
#
# Anchored on the whole line rather than picked apart by position: the
# two sides, then three fields of date and clock, then the network last.
# The network is what this board exists to print and it is the field the
# page puts at the end.
A_GAME = re.compile(
    r"^(?P<away>[^,]{2,40})\s+at\s+(?P<home>[^,]{2,40}),"
    r"\s*(?P<weekday>[A-Za-z]+),"
    r"\s*(?P<date>[A-Za-z]+ \d{1,2}[a-z]{0,2}),"
    r"\s*(?P<clock>\d{1,2}:\d{2}\s*[AP]M),"
    r"\s*(?P<channel>[^,]{2,40})$", re.I)

# What the page says when the network is not settled yet. It is not a
# channel, and this board would rather say nothing than say "TBD".
NOT_A_CHANNEL = re.compile(r"^(?:tbd|tba|tbc|--|n/?a)$", re.I)


def instant_in(block) -> datetime | None:
    """The kickoff as a real instant, from the block's own <time>.

    Never from "8:20 PM" beside it. That clock names no zone, and the
    attribute does — 2026-09-10T00:20:00Z for that very game.
    """
    for stamp in block.find_all("time"):
        raw = (stamp.get("datetime") or "").strip()
        if not raw:
            continue
        try:
            moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        return (moment.astimezone(timezone.utc) if moment.tzinfo
                else moment.replace(tzinfo=timezone.utc))
    return None


def collect(html: str) -> list[dict]:
    """Every game the league publishes, with the network showing it."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen = clockless = channelless = 0
    already: set[tuple] = set()

    for label in soup.find_all(string=A_GAME):
        game = A_GAME.match(norm(str(label)))
        if not game:
            continue
        seen += 1

        # Climb to the smallest ancestor that carries a timestamp. One
        # step too far reaches the block holding EVERY game and hands
        # them all the same kickoff — the fault that once stamped 1876
        # fixtures with a single date — so the climb stops at the first
        # instant it finds, and refuses the row if it finds none.
        block = label.parent
        start = None
        for _ in range(6):
            if block is None:
                break
            # The moment a block holds a SECOND game line, the climb has
            # left this game and is looking at the list. Stop there and
            # refuse the row rather than take a neighbour's kickoff.
            # Without this the very first test put "Jets at Bills" at
            # 00:20Z, which belongs to the Patriots — one step too far and
            # every game in the list gets the first time in it, the fault
            # that once stamped 1876 fixtures with a single date.
            if len(block.find_all(string=A_GAME)) > 1:
                break
            start = instant_in(block)
            if start is not None:
                break
            block = block.parent
        if start is None:
            clockless += 1
            continue

        channel = norm(game.group("channel"))
        if NOT_A_CHANNEL.match(channel):
            channel = ""
            channelless += 1

        title = f"{norm(game.group('away'))} - {norm(game.group('home'))}"
        key = (start, title)
        if key in already:
            continue
        already.add(key)

        out.append({
            "start": start,
            "title": title,
            "competition": "NFL",
            "sport": "NFL",
            "channels": [channel] if channel else [],
        })

    log(f"  nfl.com: {seen} game(s), {clockless} with no instant, "
        f"{channelless} with no network announced, {len(out)} kept")
    return out


def events(session) -> list[dict]:
    """The league's games, or none if its site is having a bad day."""
    try:
        return collect(fetch(session, SOURCE).text)
    except Exception as exc:                                  # noqa: BLE001
        warn(f"nfl.com is unreachable ({exc}) — the board keeps what the "
             f"other sources gave it")
        return []
