#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TSN's own schedule, read from the feed its own television runs on.

Asked for by name — "TSN AND SPORTSNET events matches to be added on
channels 1 and 2 find sources reliable ones from outside github" — and
the reliable source is not a listings page at all. tsn.ca's own schedule
page is a React app whose schedule widget asks one endpoint, openly, for
everything at once:

    https://www.tsn.ca/pf/api/v3/content/fetch/
        sports-schedule-custom?query={
            "type": "scheduleQuery",
            "channelGroup": "TSN+",
            "selectedChannels": "TSN1,TSN2,TSN3,TSN4,TSN5,TSN+"}

and the answer is the broadcaster's own grid, with the one thing no
listings page carries: the exact UTC instant of every programme on every
TSN channel, in the broadcaster's own words:

    "startTime": "2026-09-05T15:00:00Z"
    "channelName": "TSN1"
    "headlines": {"basic": "2026 US Open Tennis: Early Round Coverage Day #7"}
    "itemsType": "Tennis"

THE CHANNEL IS ONLY THE TELEVISION. The feed also carries TSN+'s
streaming numbers — TSN+01 through TSN+23 — and they are left where they
sit: the boards answer "where to watch", and a streaming number is not a
channel a reader can tune to beside beIN and Sky.

THE SPORT GATES THE BOARD. Tennis, rugby, F1, MotoGP, NFL, golf, the
UFC's own words map to the other-sports board's rows; soccer maps to
the football board; basketball is judged by its title — the NBA and
FIBA's competitions were asked for, the WNBA and US college were not,
and the feed files them all under one word; the studio programmes —
SPORTSCENTRE, the news blocks, the reality shows —
are the channel's filler between events, not events, and are left
where they sit. A "vs." in a title is not required here the way it is
for Sportsnet, because a race or a tennis block is an event with no
two sides to name.

THE TIME IS UTC ALREADY. The feed prints "2026-09-05T15:00:00Z" — no
zone to guess at, no DST boundary to cross, the instant itself.

THE FEED IS ASKED WITHOUT THE PARAMETER THAT GETS IT BLOCKED. The widget
appends "&d=false&_website=tsn" to the query, and that exact URL is
refused by the wall in front of tsn.ca — measured: the same request
without "d=false" answers 200 with the whole grid. So the reader asks
the way that works, which is the way the data arrives.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import quote

from epg_lib import fetch, log, warn

SOURCE = ("https://www.tsn.ca/pf/api/v3/content/fetch/"
          "sports-schedule-custom")
A_QUERY = ("{\"type\":\"scheduleQuery\",\"channelGroup\":\"TSN+\","
           "\"selectedChannels\":\"TSN1,TSN2,TSN3,TSN4,TSN5,TSN+\"}")

# Only the television. The feed's streaming numbers are not channels a
# viewer tunes to beside beIN and Sky.
THE_TELEVISION = {"TSN1", "TSN2", "TSN3", "TSN4", "TSN5"}

# How the feed's sport words map to the other-sports board's rows.
AS_A_SPORT = {
    "Tennis": "Tennis",
    "Rugby": "Rugby",
    "Auto Racing": None,      # judged by its title below, for F1 alone
    "Sailing": None,
    "Wrestling": None,
    # Baseball on TSN is the majors — measured twice in the feed's own
    # words: "MLB on TSN: Braves vs. Phillies" and "Sunday Night
    # Baseball: Twins vs. White Sox", both on the television channels —
    # but the majors are off the board now, taken off in the reader's
    # own words ("remove snooker & MLB from channel 2"), so the sport
    # has no row to sit on and the word maps to nothing.
    "Baseball": None,
    # Basketball is judged by its title below, the way Auto Racing is:
    # the feed files the NBA, the WNBA, the FIBA World Cup and US
    # college under one word, and only two of those were asked for.
    "Basketball": None,
    "Football, U.S. College": None,
    "Soccer": "Football",     # the football board's, handed to its caller
    "News": None,
    "Miscellaneous": None,
    "Reality": None,
    "Football": None,
    "NFL": "NFL",
    "Golf": "Golf",
    "MMA": "MMA",
    "Hockey": None,
}

# How the feed's own words for the two F1 words this board spells are
# read. A title that names Formula 1 is an F1 row whatever its channel.
THE_F1_WORDS = ("formula 1", "f1", "formula one")

# And the words that make a basketball row one of the two basketball
# competitions the board was asked for. Both are word-bounded on
# purpose: \"wnba\" carries \"nba\" inside it as three consecutive letters,
# and the women's league was not asked for — an ordinary `in` test
# would have let it through by spelling alone. \"Raptors\" sits beside
# the league's own word because it is the NBA team a Canadian
# broadcaster carries, and the feed's own titles name the team without
# naming the league: \"Raptors vs. Celtics\" is an NBA row by every
# word on it except the one it never prints.
THE_NBA_WORDS = (re.compile(r"\bnba\b", re.I),
                 re.compile(r"\braptors\b", re.I))
THE_FIBA_WORDS = (re.compile(r"\bfiba\b", re.I),)


def events(session, floor: datetime, ceiling: datetime,
           sports: tuple[str, ...] = ("Tennis", "Rugby", "NFL", "Golf",
                                      "MMA", "Soccer", "Auto Racing",
                                      "Basketball")) -> list[dict]:
    """TSN's own grid, in the window, in the sports asked for.

    Baseball was once among the defaults and its word mapped to the
    majors; both are off in the reader's own words ("remove snooker &
    MLB from channel 2"), so the word is gone from the defaults and
    maps to nothing in the table above.
    """
    url = f"{SOURCE}?query={quote(A_QUERY)}"
    try:
        page = fetch(session, url,
                     headers={
                         "Referer": "https://www.tsn.ca/live/schedule/",
                         "Accept": "application/json",
                         "x-requested-with": "XMLHttpRequest",
                     }, retries=1)
        data = json.loads(page.text)
    except Exception as exc:                              # noqa: BLE001
        warn(f"tsn's feed is unreachable ({exc}) — the board keeps what "
             f"its other sources gave it")
        return []

    out: list[dict] = []
    for item in data:
        row = _as_an_event(item, sports)
        if row is not None:
            out.append(row)
    out = [row for row in out if floor <= row["start"] < ceiling]
    for row in out:
        row["source"] = "tsn"
    log(f"  tsn: {len(out)} event(s) in the window")
    return out


def _as_an_event(item: dict, sports: tuple[str, ...]) -> dict | None:
    """One feed row as a board row, or None when the board has no place."""
    where = (item.get("channelName") or "").strip()
    if where not in THE_TELEVISION:
        return None

    the_sport = (item.get("itemsType") or "").strip()
    name = ((item.get("headlines") or {}).get("basic") or "").strip()
    when = (item.get("startTime") or "").strip()
    if not name or not when:
        return None

    if the_sport not in sports:
        return None
    a_sport = AS_A_SPORT.get(the_sport)
    lowered = name.casefold()
    if a_sport is None:
        # A title that names Formula 1 is an F1 row whatever the feed
        # filed it under — the Italian Grand Prix arrives as "Auto
        # Racing" and the board's row is called F1.
        if the_sport == "Auto Racing" and any(
                word in lowered for word in THE_F1_WORDS):
            a_sport = "F1"
        # And a basketball row is judged the same way, because the feed
        # files the NBA, the WNBA, FIBA's competitions and US college
        # under the one word "Basketball", and only the NBA and FIBA
        # were asked for. Measured in the feed's own titles: "2026
        # FIBA Women's World Cup: Türkiye - Australia" and the NBA
        # preseason rows the season turns up, against WNBA rows the
        # word boundary refuses.
        elif the_sport == "Basketball":
            if any(word.search(name) for word in THE_NBA_WORDS):
                a_sport = "NBA"
            elif any(word.search(name) for word in THE_FIBA_WORDS):
                a_sport = "FIBA"
            else:
                return None
        else:
            return None

    # SPORTSCENTRE and the studio blocks carry the sport of the night
    # they talk about; the feed's own sport word is what separates an
    # event from the channel's filler between them. "US Open Match
    # Point" is a highlight show, "Hard Knocks" is a documentary —
    # neither has the shape of the event it talks about.
    # And a race weekend has its own pair, measured on this feed:
    # "2026 F1 Grand Prix Sunday:" is the morning-of preview and "2026
    # F1 Chequered Flag:" is the evening's review — the race is on the
    # feed between them, at its own minute, and the board prints the
    # race, not the shows about it.
    if (lowered.startswith("sc:") or "sportcentre" in lowered
            or lowered.endswith("match point") or "hard knocks" in lowered
            or "grand prix sunday" in lowered
            or "chequered flag" in lowered):
        return None

    try:
        start = datetime.strptime(when, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        warn(f"tsn printed a clock this reader cannot read ('{when}') — "
             f"the programme is left alone")
        return None

    return {
        "start": start.replace(tzinfo=timezone.utc),
        "title": name,
        "sport": a_sport,
        "channels": [where],
    }
