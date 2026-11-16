#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The third source: yallakora's match centre.

Added because a reader photographed four fixtures the channel was missing
— three in Jordan's league, and الأهلي v سموحة in Egypt's — and the two
existing pages turned out not to mention any of them. That was measured
rather than assumed: of 42,924 characters on the first page and 142,697 on
the second, not one carries "Smouha", "Al Ramtha", "Al Buqaa" or "Al
Wehdat", and not a single row was dropped for lacking a broadcaster. The
gap was coverage of Arab domestic football, not a filter.

Four Arabic pages were then asked the one question that decides it: how
many blocks hold a clock AND a channel together. kooora names the clubs
and never a channel — 0 of 93 blocks. filgoal manages 3. This page holds
the channel, both teams, the competition and the kickoff inside one
element, and it takes a date, so it answers for any day in the window.

It is better than a patch. Its channels are the Arabic ones a reader here
can actually tune to — "بى ان سبورت 1HD", "ON Sport" — where the other
pages say "beIN SPORTS Xtra 1" or nothing at all.

The shape, read off the page rather than guessed, because guessing markup
is what stamped 1876 fixtures with a single date the last time:

    a.tourTitle
      img[alt="الدوري المصري"][enname="Egyptian-league"]
    div.allData
      div.channel        "ON Sport"
      div.matchStatus    "لم تبدأ"
      div.teams.teamA p  "الأهلي"
      div.MResult
        span.time        "20:00"
      div.teams.teamB p  "سموحة"

The clock is Cairo's, and that is checked rather than trusted: this page
puts Toulouse v Lille at 21:45, which as Cairo time is 18:45 UTC — exactly
what the other two pages say once the first one's fast hour is taken off.
Al Ahly v Smouha at 20:00 Cairo is 10:00 on the reader's clock, which is
the figure their own app showed.
"""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from epg_lib import log, norm, warn

SOURCE = "https://www.yallakora.com/match-center/"
CAIRO = ZoneInfo("Africa/Cairo")
CLOCK = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

# A day is asked for as MM/DD/YYYY. Measured: 09/03/2026 returns the third
# of September, while 03/09/2026 returns the ninth of March.
DAY_PARAMETER = "%m/%d/%Y"


def competition_of(block) -> str:
    """The competition heading this block sits under, Arabic and English.

    Both are kept. The English one comes from the heading image's own
    enname attribute — "Egyptian-league", "Ligue1" — and the Arabic from
    its alt, and which of the two a filter can recognise depends on the
    competition. Carrying both costs nothing and loses nothing.
    """
    head = block.find_previous("a", class_="tourTitle")
    if head is None:
        return ""
    picture = head.find("img")
    if picture is None:
        return norm(head.get_text(" ", strip=True))
    arabic = norm(picture.get("alt") or "")
    english = norm((picture.get("enname") or "").replace("-", " "))
    return " | ".join(part for part in (english, arabic) if part)


def side(block, which: str) -> str:
    """One team's name, from the paragraph rather than the whole cell.

    The cell also holds the crest, whose alt repeats the name — taking the
    cell's text would give it twice.
    """
    cell = block.find("div", class_=lambda k: k and "teams" in k
                      and which in k)
    if cell is None:
        return ""
    label = cell.find("p")
    return norm(label.get_text(" ", strip=True) if label
                else cell.get_text(" ", strip=True))


def collect(html: str, day, floor: datetime, ceiling: datetime) -> list[dict]:
    """Every fixture on one day's page, in the shape the others give."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    events: list[dict] = []
    for block in soup.find_all("div", class_="allData"):
        clock = block.find("span", class_="time")
        struck = CLOCK.match(norm(clock.get_text(" ", strip=True))) \
            if clock else None
        if not struck:
            continue                    # a finished match shows its score

        home, away = side(block, "teamA"), side(block, "teamB")
        if not home or not away:
            continue

        start = datetime.combine(
            day, time(int(struck.group(1)), int(struck.group(2))),
            CAIRO).astimezone(floor.tzinfo)
        if not (floor <= start < ceiling):
            continue

        channel = block.find("div", class_="channel")
        named = norm(channel.get_text(" ", strip=True)) if channel else ""
        events.append({
            "start": start,
            "title": f"{home} - {away}",
            # A block with no channel still names a real fixture, and this
            # page is here precisely because matches were going missing.
            # What to do with a nameless one is the guide's decision, not
            # this reader's.
            "channels": [named] if named else [],
            "competition": competition_of(block),
        })
    return events


def fetch_events(session, floor: datetime, ceiling: datetime) -> list[dict]:
    """Every fixture in the window, one request per day it spans."""
    from epg_lib import fetch

    events: list[dict] = []
    day = floor.astimezone(CAIRO).date()
    last = ceiling.astimezone(CAIRO).date()
    asked = 0
    while day <= last:
        try:
            page = fetch(session, f"{SOURCE}?date={day:{DAY_PARAMETER}}").text
            events.extend(collect(page, day, floor, ceiling))
            asked += 1
        except Exception as exc:
            warn(f"yallakora would not answer for {day} ({exc}) — that day "
                 f"comes from the other two pages alone")
        day += timedelta(days=1)

    log(f"  yallakora: {asked} day(s) asked, {len(events)} fixture(s) "
        f"in the window")
    return events
