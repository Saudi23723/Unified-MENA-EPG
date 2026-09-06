#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The sports the football board does not carry, with the channel showing them.

Asked for by name and in this order: F1, darts (the Premier League first),
boxing, MMA, MotoGP, tennis, NFL, NBA, FIBA, golf, rugby's internationals,
padel — and, asked for later in the same words, cycling's World Tour and
athletics' world championships — the big competitions only, not every
round of everything. Baseball's MLB and snooker's ranking events were on
this list once and came off it in the reader's own words: "its a mess,
remove snooker & MLB from channel 2".

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

    # No filter at all, deliberately, and that is not laziness — it is
    # what makes the prelims arrive the day anybody publishes them.
    #
    # A UFC card is three broadcasts: early prelims, prelims, main card,
    # each with its own start. Asked for by name. This source does NOT
    # split them — its UFC page was printed row by row and carries six
    # rows, one per card, with no prelim among them; the words "prelims"
    # and "main card" appear in the page twice and four times and both
    # are in its own navigation, not in a row. Counting a word in a page
    # is not finding a row, which this project has been caught by before.
    #
    # So there is nothing to keep and nothing to refuse here, and a
    # refusal would be the thing that hurt: the moment a row says
    # "Prelims" or "Early Prelims", it is kept, because nothing here
    # asks what a row is called.
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

    # BASEBALL — off the board. The reader said so in plain words
    # ("remove snooker & MLB from channel 2"), and the wording reversed
    # the earlier ask that put the page here. The page stays measured:
    # its competition cell prints "MLB" and nothing else on the page
    # holds those letters, and on the day it was wired it carried
    # eighteen rows, four of them the Yankees and the Dodgers, on
    # TNT Sports and HBO Max. But the door it gave the sport is shut,
    # the same way the snooker page below is shut.
    # ("/live-baseball-on-tv/", "MLB",
    #  re.compile(r"\bmlb\b", re.I), None),

    # CYCLING — the World Tour: the Vuelta's stages, the Tour of Britain,
    # the one-days that carry the World Tour label. The competition cell
    # prints "UCI World Tour" for every one of them, so that is the
    # family word, and the races' own names sit beside it so a page that
    # files a stage under the race's name still names a race asked for.
    # A second-tier race — the Giro della Toscana, the Coppa Sabatini —
    # prints its own competition cell and fails the keep on its own.
    ("/live-cycling-on-tv/", "Cycling",
     re.compile(r"uci world tour|tour de france|la vuelta|tour of britain"
                r"|giro d.italia|world championship", re.I), None),

    # SNOOKER — taken off the board with its whole page. The reader has
    # said so in plain words ("remove snooker from channel 2"), and the
    # page here is the only door the sport had: no feed maps a word to
    # it and no own-guide row names it. What stays is the measurement
    # the label-drop below was built on — the Snooker English Open row
    # whose label repeats in its description — because that finding is
    # load-bearing for athletics and cycling rows too.
    # ("/live-snooker-on-tv/", "Snooker",
    #  re.compile(r"snooker", re.I), None),

    # ATHLETICS — the world championships: the World Athletics Ultimate
    # Championship on the BBC, measured three rows. The Diamond League
    # and the Olympics are named alongside, so a quiet week on the page
    # is the page having nothing to list rather than the keep having
    # forgotten a competition.
    ("/live-athletics-on-tv/", "Athletics",
     re.compile(r"world athletics|diamond league|ultimate championship"
                r"|olympic", re.I), None),

    # RUGBY'S INTERNATIONALS, and nothing that is anybody's league
    # season. "Rugby: INTERNATIONAL tournaments ONLY, not leagues" —
    # asked for in those words, and the page carries 91 rows that make
    # the rule necessary: the World Cup and the internationals beside
    # RFU Championship (21 rows), the URC (16), WXV (15), Top 14 (12),
    # Gallagher Premiership (10), NPC (6), Super Rygbi Cymru (4), the
    # Pacific Nations Cup (4) and the Premiership Rugby Cup — all
    # counted on the day this was written. The keep is the
    # internationals: the World Cup, World Rugby's WXV — the women's
    # international series, an international tournament and not a league
    # — the Pacific Nations Cup, and any row whose own competition calls
    # itself international. The refuse names the leagues by the words
    # their competition cells print, so a league is out twice over: the
    # refuse says its name, and the keep does not.
    ("/live-rugby-union-on-tv/", "Rugby",
     re.compile(r"world cup|wxv|pacific nations|international", re.I),
     re.compile(r"top 14|united rugby|\burc\b|premiership|rfu championship"
                r"|national provincial|super rygbi|gallagher", re.I)),

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

    THE EVENT'S OWN NAME is the description the cell prints beside its
    label — and where the description already says what the label says,
    the label is the page's own shorthand and is dropped, because a title
    that prints one name twice is a duplication a reader counted on the
    board. _the_label_repeats below is the whole test, measured on every
    page this source has.
    """
    home = row.select_one("td.home-team")
    away = row.select_one("td.away-team")
    home = norm(home.get_text(" ", strip=True)) if home else ""
    away = norm(away.get_text(" ", strip=True)) if away else ""
    if home and away:
        return f"{home} - {away}"
    if fixture_cell is None:
        return ""
    pieces = [norm(piece) for piece in fixture_cell.stripped_strings]
    pieces = [piece for piece in pieces if piece]
    if len(pieces) >= 2:
        label, rest = pieces[0], " ".join(pieces[1:])
        if _the_label_repeats(label, rest):
            return norm(rest)
        # A label whose own name the description does not carry but
        # whose first word it does is a SERIES WORD: the label names
        # the event, the description names its session, and the word
        # is printed by both sides. The word falls away from the
        # description and the label stays — measured on the MotoGP
        # page: "MotoGP San Marino Grand Prix" beside "MotoGP Race -
        # Misano World Circuit Marco Simoncelli" is the San Marino
        # Grand Prix race, named whole, printed once.
        left = label.casefold().split()
        rest_words = rest.split()
        if (len(left) >= 2 and rest_words
                and rest_words[0].casefold() == left[0]
                and len(left[0]) >= 3):
            return norm(f"{label} {' '.join(rest_words[1:])}")
    return norm(fixture_cell.get_text(" ", strip=True))


def _the_label_repeats(label: str, rest: str) -> bool:
    """Whether the description already names what the label says.

    The fixture cell prints two things — the event's label, then its
    description — and joining them blindly prints one name twice,
    measured on the live pages:

        Snooker English Open  | BetVictor English Open 2026 - Brentwood
        World Athletics Ultimate Championship | World Athletics Ultimate
                                 Championship 2026 in Budapest
        BMW Championship      | BMW PGA Championship - Wentworth Club

    The label is dropped only when its own words are already in the
    description: a run of two or more of the label's words inside it, or
    the same first word naming the event in both — which is the whole of
    the BMW case, where "BMW" is the only word the two share. A label the
    description does not repeat ("Italian Grand Prix" beside "Race -
    Monza Circuit, Monza", "Live Boxing" beside "Canelo Alvarez vs
    Christian M'billi") is the event's name and stays.
    """
    left = label.casefold().split()
    right = f" {norm(rest).casefold()} ".split()
    if not left or not right:
        return False
    for size in range(len(left), 1, -1):
        for i in range(len(left) - size + 1):
            run = left[i:i + size]
            for j in range(len(right) - size + 1):
                if right[j:j + size] == run:
                    return True
    # The first word shared AND every remaining word of the label in
    # the description, a plural counted as the same word: "Players
    # Championship" beside "Players Championships 29-30" is the page's
    # shorthand for one name, and the label falls away. But a label
    # whose remaining words the description does NOT carry is the
    # event's own name — "MotoGP San Marino Grand Prix" beside "MotoGP
    # Race - Misano" carries "San Marino Grand Prix" nowhere in its
    # description — and dropping the label would leave a race no grand
    # prix names.
    if not (left[0] == right[0] and len(left[0]) >= 3):
        return False
    right_words = set(right)
    for word in left[1:]:
        if (word in right_words
                or word + "s" in right_words
                or (word.endswith("s") and word[:-1] in right_words)):
            continue
        return False
    return True


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
            # THE PAGE IS UTF-8 AND SAYS SO NOWHERE. The header prints
            # "Content-Type: text/html" with no charset in it — measured
            # on the live pages — and a reader that trusts it decodes
            # the bytes as Latin-1, which turns "España" into "EspaÃ±a"
            # and "Mâ€™billi" into "Mâ€™billi" on the board. The encoding is
            # set to the one the page is actually written in before the
            # text is read, so a name arrives the way the page spells it.
            got = fetch(session, SOURCE + path)
            if (got.encoding or "").lower() in ("", "iso-8859-1",
                                                "latin-1"):
                got.encoding = "utf-8"
            page = got.text
        except Exception as exc:                              # noqa: BLE001
            warn(f"wheresthematch {sport} is unreachable ({exc}) — the "
                 f"board keeps what the other pages gave it")
            continue
        out.extend(collect(page, sport, keep, refuse))
    log(f"  wheresthematch: {len(out)} event(s) over "
        f"{len(PAGES)} sport page(s)")
    return out
