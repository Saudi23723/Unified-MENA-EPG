#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A EUROPEAN-WIDE BACKUP for the three sports the Turkish grid alone was
carrying: men's handball, women's volleyball, and now futsal.

WHY: the Turkish grid (turkish_sport_grid.py) answers, but it holds ONE
day and one country's picture of it, and on an off-season day it returns
nothing at all. The reader asked for more: "Find more listing channels
European channels for volleyball and handball if the Turkish is not
sufficient". Measured before a line here was written, on this runner:

    sport-tv-guide.live     19 KB shell, the schedule drawn in the browser
    sportschedule.tv        1.2 MB of league NAMES and no fixture in it
    tvsportguide.com        no such host any more
    api.sofascore.com       403 to every sport
    thesportsdb             one handball fixture in the world, no TV
    eurohandball / CEV      404 on every documented feed path
    FIVB VIS                answers, and is used — for the beach, below

    flashscore feed         answers for all three sports, every day,
                            with the competition, both sides and a real
                            UNIX instant on every fixture

So this reads the flashscore day feed. NO BROADCASTER: this feed does not
name one, and a channel is never guessed here — the row reaches the board
naming no channel, exactly as the fights and races with no announced
broadcaster already do. Where the Turkish grid has the same fixture WITH
a channel, the board's own one-row-per-broadcast fold keeps the row that
names it.

THE INSTANT IS UNIX AND UTC. Not a printed clock, so no zone is assumed
and no daylight-saving change can move it — the failure that once put
this project an hour out cannot happen through this door.

MAJOR AND INTERNATIONAL ONLY. Club leagues are not what was asked for:
women's volleyball majors, men's handball majors, and the major futsal
internationals. A competition that does not name itself a World or
European championship, a World Cup, a Nations League, an Olympic
tournament or a qualifier for one of them does not come through.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from epg_lib import log, norm, warn

FEED = "https://global.flashscore.ninja/2/x/feed/f_{sport}_{day}_3_en_1"
HEADERS = {"x-fsign": "SW9D1eZo", "Referer": "https://www.flashscore.com/"}

# The feed's own sport numbers, read off its own pages.
SPORTS = {7: "Handball", 12: "Volleyball", 11: "Futsal"}

# Major international, in the words this feed prints for them.
A_MAJOR = re.compile(
    r"world championship|world cup|world league|world games"
    r"|european championship|euro\b|ehf euro|eurovolley"
    r"|nations league|olympic|grand prix"
    r"|asian championship|african championship|pan.?american"
    r"|world qualification|qualification|qualifier"
    r"|super ?globe|continental cup|intercontinental",
    re.I)

# A club competition wearing an international word — the EHF and CEV
# Champions Leagues, the club World Cup — is still a club competition.
A_CLUB = re.compile(r"champions league|ehf cup|cev cup|challenge cup"
                    r"|club world|super cup club", re.I)

# Which half of each sport was asked for: the WOMEN'S volleyball, the
# MEN'S handball. Futsal was asked for without a side, so both stand.
WOMEN_MARK = re.compile(r"\bwomen\b|\bw\b|\bfemale\b", re.I)


def _side_is_right(sport: str, competition: str, home: str, away: str) -> bool:
    words = f"{competition} {home} {away}"
    women = bool(WOMEN_MARK.search(words))
    if sport == "Volleyball":
        return women
    if sport == "Handball":
        return not women
    return True


def parse(text: str, sport: str) -> list[dict]:
    """Every fixture in one day of one sport's feed, majors only."""
    out: list[dict] = []
    competition = ""
    for chunk in text.split("¬~"):
        fields = dict(part.split("÷", 1)
                      for part in chunk.split("¬") if "÷" in part)
        if "ZA" in fields:
            competition = norm(fields["ZA"])
        stamp = fields.get("AD")
        if not stamp or not stamp.isdigit():
            continue
        home, away = norm(fields.get("AE", "")), norm(fields.get("AF", ""))
        if not home or not away:
            continue
        if A_CLUB.search(competition) or not A_MAJOR.search(competition):
            continue
        if not _side_is_right(sport, competition, home, away):
            continue
        # "EUROPE: European Championship Women" — the continent prefix is
        # the feed's filing, not the competition's name.
        name = competition.split(":", 1)[-1].strip() or competition
        out.append({
            "start": datetime.fromtimestamp(int(stamp), timezone.utc),
            "title": f"{home} vs {away}",
            "competition": name,
            "sport": sport,
            "channels": [],
            "source": "worldball",
        })
    return out


def events(session, days: int = 4) -> list[dict]:
    """The majors of all three sports across the board's own window."""
    out: list[dict] = []
    for number, sport in SPORTS.items():
        for day in range(days):
            url = FEED.format(sport=number, day=day)
            try:
                got = session.get(url, headers=HEADERS, timeout=20)
                if got.status_code != 200:
                    continue
                out += parse(got.text, sport)
            except Exception as exc:                           # noqa: BLE001
                warn(f"worldball {sport} day {day} unreachable ({exc})")
    unique, seen = [], set()
    for row in out:
        key = (row["sport"], row["start"], row["title"].casefold())
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    out = unique
    log(f"  worldball: {len(out)} major international fixture(s) "
        f"across handball, volleyball and futsal")
    return out
