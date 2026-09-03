#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The sports the football board does not carry, with the channel showing them.

Asked for by name and in this order: F1, darts (the Premier League first),
boxing, MMA, MotoGP, tennis, NFL, NBA, FIBA, golf, the Rugby World Cup,
padel — the big competitions only, not every round of everything.

WHY THIS SOURCE. Eight pages were asked and six are no use, and the two
that look best are the instructive ones: pdc.tv lists 45 darts events and
motogp.com 878 MotoGP ones, and NEITHER NAMES A BROADCASTER. A calendar
is not a listing. This board may not put a channel on an event unless
somebody published it, so an official calendar cannot be its source no
matter how complete it is. livesportontv.com carries every sport asked
for and names no channel either; tvsportguide refused the connection;
sportsmediawatch answered 404.

wheresthematch publishes 44 sport pages, server-rendered, and a row that
carries everything at once:

    <tr>
      <td class="fixture-details">   Italian Grand Prix | Practice 1
      <td class="start-details">     <time datetime="2026-09-04T11:30:00+01:00">
      <td class="competition-name">  F1 2026 season
      <td class="channel-details">   Sky Sports F1 | Sky Sports Main Event

THE TIME IS AN INSTANT, NOT A CLOCK. datetime carries its own offset, so
there is no printed clock to place in a timezone — the fault that cost
this project a day and then an hour, twice, on two other sources.

WHAT IT IS NOT. It is British and only British, measured over every one
of its pages: Sky Sports 1106 mentions, TNT 363, DAZN 226, BBC 80,
Premier Sports 74, ITV 2 — and not one of Fox, NBC, ABC, CBS, ESPN, TSN,
Sportsnet, Paramount, Stan or anything Australian. It has no NFL page at
all. So NFL, NBA and the American, Canadian and Australian channels are
NOT here and are not pretended to be; livesportsontv files them under
/league/nfl and /league/nba and is the next source to read.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from epg_lib import fetch, log, norm, warn

SOURCE = "https://www.wheresthematch.com"

# Each page, and what may come off it. The page is not the filter — the
# COMPETITION is, because a page collects a sport and the reader asked for
# particular competitions inside it.
#
# The MotoGP page is the worked example and it is the same trap the
# Jordanian youth cup was: every row on it today is "FIM JuniorGP World
# Championship", filed under the competition "MotoGP 2026 season". The
# heading says MotoGP and the event is a junior championship. Reading the
# page alone would put schoolboy racing on a board asked for MotoGP.
PAGES = (
    # (path, what to call it, what must appear, what must not)
    ("/live-formula-one-on-tv/", "F1",
     re.compile(r"\bf1\b|formula\s*1|grand prix", re.I),
     re.compile(r"\bf2\b|\bf3\b|formula\s*[23]|academy", re.I)),

    ("/live-darts-on-tv/", "Darts",
     re.compile(r"premier league|world championship|world cup|world matchplay"
                r"|world grand prix|grand slam|players championship"
                r"|european championship|uk open|masters", re.I),
     None),

    ("/live-boxing-on-tv/", "Boxing", None, None),

    ("/live-ufc-on-tv/", "MMA", None, None),

    ("/live-motogp-on-tv/", "MotoGP",
     re.compile(r"motogp|moto\s*gp", re.I),
     re.compile(r"juniorgp|junior gp|\bmoto4\b|rookies", re.I)),

    ("/live-tennis-on-tv/", "Tennis",
     re.compile(r"grand slam|wimbledon|us open|australian open|roland"
                r"|french open|atp finals|wta finals|masters|davis cup"
                r"|billie jean king|united cup|olympic", re.I),
     None),

    ("/live-golf-on-tv/", "Golf",
     re.compile(r"\bthe open\b|open championship|masters tournament"
                r"|\bus open\b|pga championship|ryder cup|solheim"
                r"|presidents cup|the players", re.I),
     None),

    # The World Cup and nothing else — not the league, not the union
    # season. Asked for in those words.
    ("/live-rugby-union-on-tv/", "Rugby",
     re.compile(r"world cup", re.I), None),

    # BASKETBALL, and it is wired now on purpose so that it starts on its
    # own. The NBA season opens in October: this page reads zero rows
    # today, which is the source being right rather than broken, and the
    # day the season starts the games appear with no further work.
    #
    # The channels here are BRITISH, because this source is: an NBA game
    # comes back on Sky Sports or TNT rather than on ABC or ESPN. That is
    # a real limit and not a temporary one.
    #
    # The American networks would come from a schedule page with a
    # network column, the way the NFL's does — and that CANNOT be read
    # yet for a reason worth writing down rather than forgetting: an
    # off-season page has no games in it, so there is no markup to
    # measure. Reading it now would be guessing at a shape, which on this
    # project has never once been cheaper than waiting for the real thing.
    ("/live-basketball-on-tv/", "NBA",
     re.compile(r"\bNBA\b", re.I), None),

    ("/live-basketball-on-tv/", "FIBA",
     re.compile(r"\bFIBA\b|eurobasket|basketball world cup", re.I), None),
)

# A row says it does not know yet. It is not a channel and never reaches
# the screen as one.
NOT_A_CHANNEL = re.compile(
    r"^(?:tbc|tba|channel tbc|not announced)$|website|\bapp\b|iplayer"
    r"|\bplayer\b|\.com|\.co\.uk|youtube"
    # The site's own paywall, which reads exactly like a channel name in
    # the channel column and is not one. Measured on the UFC page: "UFC
    # Fight Night Rosas Jr. vs Barcelos" came back with a single
    # broadcaster called "Log in to view", and it would have gone to a
    # television as the answer to "where do I watch this".
    r"|log in|sign in|subscribe to", re.I)

# "TNT Sports TBC" — the broadcaster is known and the channel number is
# not. Measured on the UFC page, against UFC 331.
#
# Refusing it outright loses a true fact: TNT Sports IS showing that
# card. Keeping it whole puts three letters on the screen that a viewer
# will look for on their television and not find. So the unconfirmed part
# is trimmed and the part that is known is kept — and a name that is
# nothing BUT the unconfirmed part is refused by the rule above, which is
# where it belongs.
AN_UNCONFIRMED_NUMBER = re.compile(r"\s+(?:tbc|tba|tbd)\.?$", re.I)


def when(cell) -> datetime | None:
    """The kickoff as an instant, from the cell's own <time datetime>.

    Never from the printed clock beside it. The printed clock is London's
    and says so nowhere; the attribute carries its offset, and reading a
    clock instead of an instant is the single fault this repository has
    paid for most.
    """
    stamp = cell.find("time") if cell else None
    raw = (stamp.get("datetime") if stamp else "") or ""
    if not raw.strip():
        return None
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (moment.astimezone(timezone.utc) if moment.tzinfo
            else moment.replace(tzinfo=timezone.utc))


def channels_of(cell) -> list[str]:
    """Every channel the row names, and nothing that is not one."""
    if cell is None:
        return []
    def keep(name: str, out: list[str]) -> None:
        name = norm(name)
        if not name or NOT_A_CHANNEL.search(name):
            return
        name = norm(AN_UNCONFIRMED_NUMBER.sub("", name))
        if name and not NOT_A_CHANNEL.search(name) and name not in out:
            out.append(name)

    out: list[str] = []
    for piece in cell.find_all(["a", "span", "li"]) or []:
        keep(piece.get_text(" ", strip=True), out)
    if not out:
        for name in re.split(r"\s{2,}|\n", cell.get_text("\n", strip=True)):
            keep(name, out)
    return out


def title_of(row, fixture_cell) -> str:
    """Two sides where the sport has them, the event's own name where not.

    A grand prix practice session has no teams and its name IS the event;
    an NRL match has two and its name is the pair. Both shapes are on this
    site, in the same markup, so the row is asked rather than assumed.
    """
    home = row.select_one("td.home-team")
    away = row.select_one("td.away-team")
    home = norm(home.get_text(" ", strip=True)) if home else ""
    away = norm(away.get_text(" ", strip=True)) if away else ""
    if home and away:
        return f"{home} - {away}"
    return norm(fixture_cell.get_text(" ", strip=True)) if fixture_cell else ""


def collect(html: str, sport: str, keep, refuse) -> list[dict]:
    """Every event on one sport page that belongs on this board."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen = clockless = unwanted = 0

    for row in soup.find_all("tr"):
        fixture = row.select_one("td.fixture-details")
        start = when(row.select_one("td.start-details"))
        competition_cell = row.select_one("td.competition-name")
        channels = channels_of(row.select_one("td.channel-details"))
        if fixture is None and competition_cell is None:
            continue
        seen += 1

        if start is None:
            # No instant, no row. A guessed time is worse than no row.
            clockless += 1
            continue

        competition = norm(competition_cell.get_text(" ", strip=True)) \
            if competition_cell else ""
        title = title_of(row, fixture)
        both = f"{competition} {title}"
        if refuse is not None and refuse.search(both):
            unwanted += 1
            continue
        if keep is not None and not keep.search(both):
            unwanted += 1
            continue
        if not title:
            continue

        out.append({
            "start": start,
            "title": title,
            "competition": competition or sport,
            "sport": sport,
            "channels": channels,
        })

    log(f"  wheresthematch {sport}: {seen} row(s), {clockless} with no "
        f"instant, {unwanted} not a competition asked for, "
        f"{len(out)} kept")
    return out


def events(session) -> list[dict]:
    """Every event this source has, for the sports the board was asked for."""
    out: list[dict] = []
    for path, sport, keep, refuse in PAGES:
        try:
            page = fetch(session, SOURCE + path).text
        except Exception as exc:                              # noqa: BLE001
            warn(f"wheresthematch {sport} is unreachable ({exc}) — the "
                 f"board keeps what the other pages gave it")
            continue
        out.extend(collect(page, sport, keep, refuse))
    log(f"  wheresthematch: {len(out)} event(s) over "
        f"{len(PAGES)} sport page(s)")
    return out
