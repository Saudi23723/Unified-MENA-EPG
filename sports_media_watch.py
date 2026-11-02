#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The network showing each NFL game, from a page that prints one per row.

WHY THIS EXISTS, measured on the board as it stood:

    17:20  Patriots - Seahawks          (no channel)
    17:35  49ers - Rams                 (no channel)
    10:00  Falcons - Steelers           (no channel)
    13:25  Commanders - Eagles          (no channel)   … seven of seven

The games are on the board because the LEAGUE'S OWN SITE is read for
them, and it gives a real UTC instant. What it used to give as well — the
network, in its screen-reader text — is not reaching the row any more. So
seven American football games sat on a board whose whole purpose is
answering "where do I watch this".

sportsmediawatch was tried once before and is written down in
american_sport_on_tv as "404". That was a different URL. The one the
reader named answers, and answers in the shape that matters:

    cells   ['8:20 pm', 'NFL Kickoff Game New England Patriots vs Seattle
              Seahawks  NBC, Peacock , NFL+, Telemundo | TSN1/3/4, TSN+']
    instant ['2026-09-10T00:20']        <- INSIDE the row

THE INSTANT BEING INSIDE THE ROW IS THE WHOLE TEST. Counting instants on
a page proves nothing about which game each belongs to; that mistake has
its own comment on three other readers here. This one is in the row, next
to the teams and the networks.

AND ITS TIMEZONE IS NEVER ASSUMED, which is the fault this project has
paid for most — every match an hour late once, and a whole day out
another time. The attribute above looks like UTC and is not treated as
though it were. It is used ONLY to say which game a row is about, against
a kickoff that already came from the league itself:

    two NFL teams do not meet twice inside half a day

so a row whose two nicknames match a board row within twelve hours is
that game, whatever zone the attribute is written in. If the page ever
switches to local time the window still holds and nothing moves; if it
switched by more than half a day the channel would simply not attach,
which is the safe direction to fail in.

IT NAMES NO GAME OF ITS OWN. Every row here is a channel looking for a
game the league already put on the board. A page that invented a fixture
would be a page that could invent one wrongly.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from epg_lib import fetch, log, norm, warn

SOURCE = "https://www.sportsmediawatch.com/tv-schedules/nfl-tv-schedule/"

# Two teams do not meet twice in half a day, so this is wide enough that
# the page's timezone never has to be decided and narrow enough that it
# still names one game.
SAME_GAME = timedelta(hours=12)

# THE NETWORKS THIS PAGE ACTUALLY PRINTS, longest first so "FOX One" is
# read before "FOX" and "NFL Network" before "NFL+".
#
# A vocabulary, and it is the right shape here for the reason the ON
# Sport gate is: the NAME is what is being extracted, so the names are
# what it knows. Nothing is inferred from position — a word not on this
# list is left in the fixture rather than guessed at as a channel.
NETWORKS = (
    "Prime Video", "NFL Network", "CBS Sports Network", "FOX One",
    "ESPN+", "ESPN2", "ESPN", "Peacock", "Paramount+", "Telemundo",
    "Univision", "Netflix", "NFL+", "Amazon", "YouTube", "NBC", "CBS",
    "FOX", "ABC", "TSN", "DAZN",
)
A_NETWORK = re.compile(
    r"\b(" + "|".join(re.escape(one) for one in NETWORKS) + r")",
    re.I)

A_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
A_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
AN_INSTANT = re.compile(r'datetime="(20\d\d-\d\d-\d\dT\d\d:\d\d[^"]*)"')
TAGS = re.compile(r"<[^>]+>")

# What separates the American listing from the Canadian one on the same
# row. Canada's channels are kept — a row shows two, and the reader's
# order decides which — but the split has to happen before the teams are
# read, or "TSN1/3/4" ends up inside a club's name.
CANADA = " | "


def text_of(html: str) -> str:
    return norm(re.sub(r"\s+", " ", TAGS.sub(" ", html)))


def nickname(name: str) -> str:
    """The last word of an NFL club's name, which is what a board prints.

    The league's own site writes "Seahawks" and this page writes "Seattle
    Seahawks". The nickname is the last word of both, and no two clubs in
    the league share one.
    """
    words = re.findall(r"[A-Za-z0-9']+", name)
    return words[-1].casefold() if words else ""


def a_game(cell: str) -> tuple[str, set[str], list[str]]:
    """The home club's nickname, the away side's words, and the networks.

    THE AWAY SIDE IS NOT REDUCED TO A NICKNAME HERE, and that is not
    laziness — it is what the page's own shape allows. The home club ends
    where "vs" begins, so its last word is its nickname. The away club
    does not: on an international game the VENUE follows it,

        San Francisco 49ers vs Los Angeles Rams Melbourne, Australia
                                                Netflix, NFL+

    and taking the last word before the network gives "Australia". There
    is no list of venues to consult and inventing one would be a rule
    that goes stale the first time a game is played somewhere new.

    So the away side is returned as WORDS and the board's own clean
    nickname is looked for among them. The board has "Rams"; this has
    "Los Angeles Rams Melbourne Australia"; "rams" is in it. Testing
    membership needs no venue list and cannot be defeated by one.
    """
    american = cell.split(CANADA)[0]
    split = re.split(r"\s+vs\.?\s+", american, maxsplit=1, flags=re.I)
    if len(split) != 2:
        return "", set(), []

    home, rest = split
    # Everything from the first network name on is where to watch it,
    # not who is playing.
    found = A_NETWORK.search(rest)
    away = rest[:found.start()] if found else rest
    channels: list[str] = []
    for name in A_NETWORK.finditer(cell):
        spelled = name.group(1)
        if spelled not in channels:
            channels.append(spelled)
    words = {word.casefold() for word in re.findall(r"[A-Za-z0-9']+", away)}
    return nickname(home), words, channels


def broadcasts(session) -> list[dict]:
    """Every NFL game this page dates, one row per channel it names.

    A row is {start, home, away, channel}: the home club's nickname, the
    away side's words, and where to watch it. A game naming no network is
    not returned at all — this reader exists to name channels, and a row
    without one has nothing to add to a board that already has the game.
    """
    try:
        html = fetch(session, SOURCE).text
    except Exception as exc:                                  # noqa: BLE001
        warn(f"sportsmediawatch is unreachable ({exc}) — the NFL rows keep "
             f"whatever channels they already have")
        return []

    out: list[dict] = []
    rows = no_time = 0
    for row in A_ROW.findall(html):
        when = AN_INSTANT.search(row)
        if not when:
            # A heading row, or a game with no instant. Either way there
            # is nothing here to attach a channel to.
            continue
        cells = [text_of(one) for one in A_CELL.findall(row)]
        if len(cells) < 2:
            continue
        home, away, channels = a_game(cells[-1])
        if not home or not away or not channels:
            continue
        try:
            start = datetime.fromisoformat(when.group(1))
        except ValueError:
            no_time += 1
            continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        rows += 1
        for channel in channels:
            out.append({"start": start, "home": home, "away": away,
                        "channel": channel})

    log(f"  sportsmediawatch: {rows} NFL game(s) dated, "
        f"{len(out)} broadcast(s) named"
        + (f", {no_time} instant(s) unreadable" if no_time else ""))
    return out


def add_channels(session, events: list[dict]) -> int:
    """Name the network on every NFL row the board already has.

    Both nicknames must agree, inside SAME_GAME. Both, not one: the
    one-club rule the football boards use rests on a club playing once in
    two hours, and this window is half a day, so it is the pair that
    identifies the game.
    """
    rows = broadcasts(session)
    if not rows:
        return 0

    added = 0
    for event in events:
        left, _, right = (event.get("title") or "").partition(" - ")
        if not right:
            continue
        here = (nickname(left), nickname(right))
        if not all(here):
            continue
        for row in rows:
            if abs(row["start"] - event["start"]) > SAME_GAME:
                continue
            if row["home"] != here[0] or here[1] not in row["away"]:
                continue
            if row["channel"] not in event["channels"]:
                event["channels"].append(row["channel"])
                added += 1
    log(f"  sportsmediawatch: {added} channel(s) added to the board")
    return added
