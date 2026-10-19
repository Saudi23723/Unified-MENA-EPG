#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""livesoccertv's schedule, read for the American channel a match is on.

Of thirty matches on the board, not one named Fox, NBC, CBS, USA Network,
Paramount or ESPN — the whole census was Gulf, British, French and
Turkish. They were not hidden behind the "+5"; no source here had ever
seen them. This is the page that has them.

It is also the one American candidate that answers in plain HTML: 68
blocks with a clock, 17 with a clock and a US broadcaster, where Fox's
own site, ESPN's and NBC's give none between them. (This site is recorded
elsewhere in this repository as browser-rendered. That was true of its
HOMEPAGE and not of /schedules/, and the note was never revisited.)

The shape, read off the page:

    tr.matchrow[data-ko="2026-09-02 21:00:00"]
      span.ts[dv="1788397200000"]        "9:00pm"
      td.matchcol a[title]               "Toluca vs León"
      div.mchannels a                    "Apple TV", "TUDN USA", ...

Two times, and they disagree by four hours: dv is 2026-09-03 01:00 UTC
where data-ko says 2026-09-02 21:00. data-ko is the site's Eastern wall
clock and dv is a true epoch — the same trap the first source set, where
a printed clock and a published instant were an hour apart and reading
the wrong one put every match on this channel an hour late. dv is read,
and data-ko is not.

Used to NAME channels, never to add fixtures — the limit every source of
this kind carries here, for the same reason.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from epg_lib import log, norm, warn

SOURCE = "https://www.livesoccertv.com/schedules/"

# beIN is the one brand this page and the Gulf feeds share, so it is the
# one that needs saying which. Fox, NBC, CBS, Paramount and Apple TV are
# nobody else's and are left exactly as the page writes them — a mark on
# an unambiguous name is noise on a row that has little space.
SHARED_BRAND = re.compile(r"\bbein\b", re.I)
MARK = " US"

# Streams and shops, which this page lists beside the broadcasters.
NOT_A_CHANNEL = re.compile(r"youtube|\.com\b|website|onefootball|now\b|app\b",
                           re.I)


def instant(value: str) -> datetime | None:
    """The epoch milliseconds this row publishes, as a UTC instant."""
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def fixture_of(row) -> str:
    """The two clubs, from the link that names them."""
    link = row.find("a", title=True)
    title = norm(link.get("title") or "") if link else ""
    if not title:
        return ""
    sides = [norm(side) for side in re.split(r"\s+vs?\.?\s+", title)]
    return f"{sides[0]} - {sides[1]}" if len(sides) == 2 and all(sides) else ""


def channels_of(row) -> list[str]:
    """Every broadcaster this row names, marked where the brand is shared."""
    holder = row.find("div", class_="mchannels")
    if holder is None:
        return []
    names = []
    for link in holder.find_all("a"):
        name = norm(link.get_text(" ", strip=True))
        if not name or NOT_A_CHANNEL.search(name):
            continue
        if SHARED_BRAND.search(name):
            name = f"{name}{MARK}"
        if name not in names:
            names.append(name)
    return names


def collect(html: str) -> list[dict]:
    """Every broadcast the page publishes, as {start, title, channel}."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    rows = soup.find_all("tr", class_="matchrow")
    out: list[dict] = []
    for row in rows:
        clock = row.find("span", class_="ts")
        start = instant(clock.get("dv")) if clock else None
        title = fixture_of(row)
        if start is None or not title:
            continue
        for channel in channels_of(row):
            out.append({"start": start, "title": title, "channel": channel})

    log(f"  livesoccertv: {len(rows)} row(s), {len(out)} naming a channel")
    return out


def broadcasts(session) -> list[dict]:
    """Read the page, and treat a bad day there as no reason to fail here."""
    from epg_lib import fetch
    try:
        return collect(fetch(session, SOURCE).text)
    except Exception as exc:
        warn(f"livesoccertv is unreachable ({exc}) — the board keeps the "
             f"channels the other sources gave it")
        return []
