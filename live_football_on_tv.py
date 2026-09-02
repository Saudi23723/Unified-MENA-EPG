#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The second source: live-footballontv.com.

livefootballtv, the first source, is the only one of a dozen candidates
that hands over a channel with each match in plain HTML — but a scores app
showed three Championship matches it had never listed, so it is not
complete. This is the one page found that carries the same three, with the
competition and the broadcaster attached:

    19:45  Millwall v Wrexham        Championship  Sky Sports+
    19:45  QPR v Cardiff City        Championship  Sky Sports+
    19:45  West Brom v Charlton      Championship  Sky Sports+

Measured before a line of this was written: 1884 fixtures on the page,
1283 of them holding a clock and a broadcaster in the same block. Every
other candidate either builds its rows in the browser — leaving HTML with
nothing in it — or lists matches and never says where to watch them.

The shape, read off the page rather than assumed:

    div.fixture-group          "Wednesday 2nd September 2026"
      div.fixture
        div.fixture__time         "19:45"
        div.fixture__teams        "Millwall v Wrexham"
        div.fixture__competition  "Championship"
        div.fixture__channel      "Sky Sports+"

The clock is London's, confirmed on the runner rather than presumed — a
source read in the wrong timezone is the exact fault that cost a day here
already. It is a British listings site, so its channels are British:
Sky Sports, TNT, Premier Sports, BBC, ITV. That is a gain, not a
mismatch — those were asked for by name — and the Gulf channels keep
coming from the first source. A match on both is one row naming both.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from epg_lib import log, norm, warn

SOURCE = "https://www.live-footballontv.com/"
LONDON = ZoneInfo("Europe/London")

# "Wednesday 2nd September 2026"
DAY_LINE = re.compile(
    r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\s+"
    r"(\d{1,2})(?:st|nd|rd|th)\s+([A-Za-z]+)\s+(\d{4})", re.I)
CLOCK = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

MONTHS = {m.lower(): n for n, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}


def day_of(group) -> datetime | None:
    """The date this group of fixtures belongs to, from its own heading."""
    found = DAY_LINE.search(norm(group.get_text(" ", strip=True)))
    if not found:
        return None
    day, month, year = found.groups()
    number = MONTHS.get(month.lower())
    if not number:
        return None
    return datetime(int(year), number, int(day), tzinfo=LONDON)


def channels_of(fixture) -> list[str]:
    """Every broadcaster named against this fixture, in the page's order."""
    cell = fixture.find("div", class_="fixture__channel")
    if not cell:
        return []
    parts = [norm(kid.get_text(" ", strip=True))
             for kid in cell.find_all(True, recursive=False)]
    if not any(parts):
        parts = [norm(cell.get_text(" ", strip=True))]
    names: list[str] = []
    for part in parts:
        # One cell can hold several, written one after another.
        for name in re.split(r"\s{2,}|,|/|\bor\b", part):
            name = norm(name)
            if name and name not in names:
                names.append(name)
    return names


def collect(html: str, now: datetime, keep_ahead: timedelta,
            floor: datetime) -> list[dict]:
    """Every fixture on the page, in the same shape the first source gives."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    events: list[dict] = []
    groups = soup.find_all("div", class_="fixture-group")
    for group in groups:
        day = day_of(group)
        if day is None:
            continue
        for fixture in group.find_all("div", class_="fixture"):
            clock = fixture.find("div", class_="fixture__time")
            teams = fixture.find("div", class_="fixture__teams")
            if not (clock and teams):
                continue
            struck = CLOCK.match(norm(clock.get_text(" ", strip=True)))
            if not struck:
                continue                    # "TBC", "Postponed", and the like
            sides = [norm(side) for side in
                     re.split(r"\s+v\s+", norm(teams.get_text(" ", strip=True)))]
            if len(sides) != 2 or not all(sides):
                continue

            start = day.replace(hour=int(struck.group(1)),
                                minute=int(struck.group(2))).astimezone(
                                    timezone.utc)
            if not (floor <= start <= now + keep_ahead):
                continue

            channels = channels_of(fixture)
            if not channels:
                continue                    # nowhere to watch it is not on
            competition = fixture.find("div", class_="fixture__competition")
            events.append({
                "start": start,
                "title": f"{sides[0]} - {sides[1]}",
                "channels": channels,
                "competition": norm(competition.get_text(" ", strip=True))
                if competition else "",
            })

    log(f"  live-footballontv: {len(groups)} day group(s), "
        f"{len(events)} fixture(s) in the window")
    return events


def fetch_events(session, now: datetime, keep_ahead: timedelta,
                 floor: datetime) -> list[dict]:
    """Read the page, and treat a bad day there as no reason to fail here."""
    from epg_lib import fetch
    try:
        html = fetch(session, SOURCE).text
    except Exception as exc:
        warn(f"live-footballontv is unreachable ({exc}) — the guide is "
             f"built from the first source alone this pass")
        return []
    try:
        return collect(html, now, keep_ahead, floor)
    except Exception as exc:
        warn(f"live-footballontv could not be read ({exc}) — the guide is "
             f"built from the first source alone this pass")
        return []
