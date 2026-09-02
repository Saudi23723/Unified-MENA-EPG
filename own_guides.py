#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The channels this repository already publishes, added to the board.

Asked for directly, and right: these guides are built here, refreshed on
their own schedules, and they know something no listings page does — which
of THIS reader's channels is carrying a match.

They are used to name channels, never to add fixtures, and that is a
deliberate limit rather than a half-measure. Their titles are written for
a television grid, not for a parser: beIN Turkey writes "Super Lig (26-27)
3. Hafta Gaziantep Fk - Rizespor - Bant -", where the competition is a
prefix, the round is in the middle and "Bant" means it is a repeat. A
title read wrongly that only fails to name a channel costs nothing; one
read wrongly that ADDS a fixture puts a match on the screen that is not
being played.

Matching a guide's fixture to one already on the board is the same
cross-script problem as everywhere else, and it is answered the same way:
never by a similarity score. The board and the guide must agree on the
kickoff MINUTE, and at least one club must match exactly under epg_lib's
own strict cross-script rule. One side is enough here — and only here —
because a club cannot play two matches at once, so an exact club match at
one minute is that club's match. Measured over the nine fixtures Alwan
published on the day this was written, that reaches all nine, where
demanding both sides reaches six: ميدلزبره and Middlesbrough do not
reduce to the same skeleton, and بيرنلي and Burnley do.

The Turkish channels are marked. beIN SPORTS 1 in Istanbul and beIN
SPORTS 1 in Doha are different channels showing different football, and a
reader with both in their playlist needs to know which one the row means.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from epg_lib import club_skeleton, log, norm, same_club

# Each guide, and the mark its channels carry. An empty mark is the Gulf,
# which is this reader's default and says nothing.
GUIDES = (
    ("alwan_sports_epg.xml", ""),
    ("bein_sports_turkey_epg.xml", " TR"),
)

# How far a broadcast may sit from the kickoff and still be that match.
#
# Not a minute. A listings page gives the KICKOFF; a television grid gives
# the PROGRAMME, which starts with the studio build-up — beIN Turkey opens
# Başakşehir v Galatasaray at 16:15 for a 17:00 kick, and at a minute's
# tolerance the Turkish channel never reached the Turkish match.
#
# Wide is safe here only because of what else is required: one club has to
# match exactly. A club does not play two matches inside two hours, so an
# exact club match in this window is that club's match. Without the club
# test this window would be reckless; with it, a tighter one only loses
# broadcasts.
SLACK = timedelta(hours=2)

XMLTV_TIME = "%Y%m%d%H%M%S %z"

# Markers a grid adds to a title that are not part of the fixture.
NOISE = re.compile(r"[‎‏‎‏]|🔴|🔵|•\s*LIVE|LIVE|Bant|Tekrar", re.I)

# A title that says nothing was scheduled is not a fixture.
NOT_A_FIXTURE = ("لا توجد", "لم يُعلن", "no listing", "no match")

# A grid also carries last season's football. beIN Turkey lists
# "Beşiktaş - Adanaspor (00-01) 21.hafta" — a match from 2000 — and a
# round number or a season in parentheses is what marks those. A repeat
# given a live match's channel is worse than a match with no channel.
A_REPEAT = re.compile(r"\(\d{2}[-–]\d{2}\)|\bhafta\b|\bözet\b|\bozet\b"
                      r"|\bmaç özetleri\b|\bhaber\b", re.I)

# One channel written eight ways. Alwan publishes Sport/Sports, HD, SD, 4K
# and RAW as separate channels, and a match on all of them would fill the
# row with the same name eight times over.
QUALITY = re.compile(r"\s*\b(?:HD|SD|FHD|UHD|4K|RAW|8K)\b", re.I)


def one_channel(name: str) -> str:
    """A channel name with its quality variants folded into one."""
    return norm(QUALITY.sub("", name).replace("Sports", "Sport"))


def fixture_in(title: str) -> tuple[str, str]:
    """The two clubs in a grid title, or a pair of empty strings.

    Deliberately unambitious. A title has to be a plain "A - B" once its
    markers are stripped; anything carrying a competition prefix or a
    round in the middle is left alone rather than guessed at, because the
    cost of guessing wrongly is a channel on the wrong match.
    """
    clean = norm(NOISE.sub(" ", title or ""))
    if any(word in clean.casefold() for word in NOT_A_FIXTURE):
        return "", ""
    if A_REPEAT.search(clean):
        return "", ""
    sides = [norm(side) for side in clean.split(" - ")]
    if len(sides) != 2 or not all(sides):
        return "", ""
    if any(len(side) < 2 or len(side) > 40 for side in sides):
        return "", ""
    return sides[0], sides[1]


def one_club_matches(first: str, second: str) -> bool:
    """Whether these two fixtures share a club, across the scripts.

    epg_lib's strict answer, asked of each side. One side is enough: a
    club cannot be playing two matches at the same minute, so an exact
    match at an agreed minute identifies the fixture.
    """
    left, right = fixture_in(first), fixture_in(second)
    if not all(left) or not all(right):
        return False
    return any(one_club(a, b) for a in left for b in right)


def one_club(first: str, second: str) -> bool:
    """One club, whether the two names cross the scripts or not.

    epg_lib answers across them and refuses within one, so within one this
    asks for the skeletons to be EQUAL — equality, never a ratio. That is
    what lets a guide written in Latin be matched to a board row written
    in Latin: "Galatasaray" is "Galatasaray". "Mainz" and "Monza" reduce
    to manz and manza and stay two clubs, which is the pair epg_lib names
    as the reason a ratio cannot be used here.
    """
    if same_club(first, second):
        return True
    skeleton = club_skeleton(first)
    return bool(skeleton) and skeleton == club_skeleton(second)


def broadcasts(path: str, mark: str) -> list[dict]:
    """Every fixture one published guide names, with the channel showing it."""
    if not os.path.exists(path):
        return []
    try:
        guide = ET.parse(path).getroot()
    except Exception:
        return []

    named = {}
    for channel in guide.findall("channel"):
        label = channel.find("display-name")
        named[channel.get("id")] = norm(
            label.text if label is not None and label.text else channel.get("id"))

    out = []
    for programme in guide.findall("programme"):
        title = programme.find("title")
        home, away = fixture_in(title.text if title is not None else "")
        if not home:
            continue
        try:
            start = datetime.strptime(programme.get("start", ""), XMLTV_TIME)
        except ValueError:
            continue
        channel = one_channel(named.get(programme.get("channel"), ""))
        if not channel:
            continue
        out.append({"start": start, "title": f"{home} - {away}",
                    "channel": f"{channel}{mark}"})

    # The same match on eight spellings of one channel is one broadcast.
    seen, kept = set(), []
    for row in out:
        key = (row["start"], row["title"], row["channel"])
        if key not in seen:
            seen.add(key)
            kept.append(row)
    return kept


def attach(events: list[dict], rows: list[dict], label: str) -> int:
    """Put each broadcast's channel on the board row it belongs to."""
    found = 0
    for row in rows:
        for event in events:
            if abs(event["start"] - row["start"]) > SLACK:
                continue
            if not one_club_matches(event["title"], row["title"]):
                continue
            if row["channel"] not in event["channels"]:
                event["channels"].append(row["channel"])
                found += 1
    log(f"  {label}: {len(rows)} broadcast(s) named, "
        f"{found} channel(s) added to the board")
    return found


def add_channels(events: list[dict], extra: list[dict] | None = None) -> int:
    """Name, on each event, any of this reader's channels carrying it.

    `extra` is for a broadcaster's listing read over the network — Spor
    Ekranı — which arrives in the same {start, title, channel} shape. It
    goes through the same matching as the guides published here, because
    the rule that makes this safe is the matching, not where the rows
    came from.
    """
    added = 0
    for path, mark in GUIDES:
        added += attach(events, broadcasts(path, mark),
                        os.path.basename(path))
    if extra:
        added += attach(events, extra, "Spor Ekranı")
    return added
