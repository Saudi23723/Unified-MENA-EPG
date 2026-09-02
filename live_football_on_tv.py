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

The shape, read off the page rather than assumed — and read twice, because
the first reading was wrong in a way that matters:

    div.fixture-group                 <- NOT a day. There are two of them
      div.fixture-date                   for 1896 fixtures.
        "Wednesday 2nd September 2026"
      div.fixture
        div.fixture__time         "01:00"
        div.fixture__teams        "Atletico Mineiro v Cruzeiro"
        div.fixture__competition  "Copa do Brasil Quarter-Final 2nd Leg"
        div.fixture__channel
          div.span3.channels
            span.channel-pill     "Premier Sports 2"
      div.fixture ...
      div.fixture-date                <- the next day starts here
        "Thursday 3rd September 2026"
      div.fixture ...

The day is a DIVIDER between fixtures, not a container around them. Taking
the first date inside a group and giving it to everything in that group
stamped 1876 fixtures — the whole autumn, Champions League league phase
and all — with one date, and a probe of the result put them all on
tomorrow's board. So the fixtures are walked in the order they are
written, and the date changes when a divider says it does.

The channels are pills, one per broadcaster, and their text has to be
taken pill by pill: reading the cell whole ran three of them together into
"HBO Max TNT Sports TBC", which is not the name of anything. "TBC" is not
a channel either — it is the page saying it does not know yet.

The clock is London's, confirmed on the runner rather than presumed — a
source read in the wrong timezone is the exact fault that cost a day here
already. It is a British listings site, so its channels are British:
Sky Sports, TNT, Premier Sports, BBC, ITV. That is a gain, not a
mismatch — those were asked for by name — and the Gulf channels keep
coming from the first source. A match on both is one row naming both.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
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


# What a divider says when it does not know the broadcaster yet.
UNKNOWN = {"tbc", "tba", "n/a"}


def day_of(divider) -> datetime | None:
    """The date a fixture-date divider announces."""
    found = DAY_LINE.search(norm(divider.get_text(" ", strip=True)))
    if not found:
        return None
    day, month, year = found.groups()
    number = MONTHS.get(month.lower())
    if not number:
        return None
    return datetime(int(year), number, int(day), tzinfo=LONDON)


def channels_of(fixture) -> list[str]:
    """Every broadcaster named against this fixture, one pill at a time."""
    cell = fixture.find("div", class_="fixture__channel")
    if not cell:
        return []
    pills = cell.find_all("span", class_="channel-pill")
    parts = [norm(pill.get_text(" ", strip=True)) for pill in pills] or \
        [norm(cell.get_text(" ", strip=True))]

    names: list[str] = []
    for part in parts:
        # One pill can still hold two, written with a separator.
        for name in re.split(r",|/|\bor\b", part):
            name = norm(name)
            name = mended(name)
            if name and name.casefold() not in UNKNOWN and name not in names:
                names.append(name)
    return names


def mended(text: str) -> str:
    """Undo one round of UTF-8 read as Latin-1, where that is what happened.

    The page reached the board as "VfB Stuttgart - FC KÃ¶ln", which is
    "Köln" written in UTF-8 and then read a byte at a time. It cost more
    than an ugly row: the same fixture off the other page says "FC Koln",
    and two spellings that differ by mojibake are two clubs to any
    comparison, so the match was published twice.

    Guarded twice over, because a repair that fires on good text is worse
    than the damage. It runs only on strings carrying the marks this
    specific damage leaves, and only keeps the result if the round trip
    actually completes — "Liga 1 Perú" raises on the way back and is
    handed over untouched, and Arabic cannot even be encoded as Latin-1.
    """
    if not any(mark in text for mark in ("Ã", "Â", "â€")):
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def is_a(tag, name: str) -> bool:
    """Whether this element carries exactly that class."""
    return tag.name == "div" and name in (tag.get("class") or [])


def collect(html: str, floor: datetime, ceiling: datetime) -> list[dict]:
    """Every fixture on the page, in the same shape the first source gives."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    events: list[dict] = []
    day: datetime | None = None
    days = 0

    # Dividers and fixtures together, in the order the page writes them.
    for tag in soup.find_all(
            lambda t: is_a(t, "fixture-date") or is_a(t, "fixture")):
        if is_a(tag, "fixture-date"):
            said = day_of(tag)
            if said is not None:
                day = said
                days += 1
            continue
        if day is None:
            continue                        # a fixture before any date

        fixture = tag
        clock = fixture.find("div", class_="fixture__time")
        teams = fixture.find("div", class_="fixture__teams")
        if not (clock and teams):
            continue
        struck = CLOCK.match(norm(clock.get_text(" ", strip=True)))
        if not struck:
            continue                        # "TBC", "Postponed", and the like
        sides = [mended(norm(side)) for side in
                 re.split(r"\s+v\s+", norm(teams.get_text(" ", strip=True)))]
        if len(sides) != 2 or not all(sides):
            continue

        start = day.replace(hour=int(struck.group(1)),
                            minute=int(struck.group(2))).astimezone(
                                timezone.utc)
        if not (floor <= start < ceiling):
            continue

        channels = channels_of(fixture)
        if not channels:
            continue                        # nowhere to watch it is not on
        competition = fixture.find("div", class_="fixture__competition")
        events.append({
            "start": start,
            "title": f"{sides[0]} - {sides[1]}",
            "channels": channels,
            "competition": mended(norm(
                competition.get_text(" ", strip=True))) if competition else "",
        })

    log(f"  live-footballontv: {days} day(s) on the page, "
        f"{len(events)} fixture(s) in the window")
    return events


def fetch_events(session, floor: datetime, ceiling: datetime) -> list[dict]:
    """Read the page, and treat a bad day there as no reason to fail here."""
    from epg_lib import fetch
    try:
        html = fetch(session, SOURCE).text
    except Exception as exc:
        warn(f"live-footballontv is unreachable ({exc}) — the guide is "
             f"built from the first source alone this pass")
        return []
    try:
        return collect(html, floor, ceiling)
    except Exception as exc:
        warn(f"live-footballontv could not be read ({exc}) — the guide is "
             f"built from the first source alone this pass")
        return []
