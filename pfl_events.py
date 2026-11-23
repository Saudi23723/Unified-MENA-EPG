#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The PFL's own events page, read the way the league publishes it.

Asked for by name — "add PFL and BRAVE the same way" as OKTAGON: on
channel 2, updating whenever they have an event, and PPV where the
channel is not known. ESPN's scoreboard was this board's PFL calendar,
and it only lets through a card whose broadcaster is named; the league's
MENA and Africa cards rarely are, and ESPN's API also refuses some
readers outright.

TWO PAGES, EACH FOR WHAT IT IS SURE OF. pflmma.com/events lists every
upcoming card under its own "UPCOMING" tab with a link to the card's
page; the card's page prints the clock in its header, in the league's
own words:

    PFL MENA 11 FRI OCT 2 5:00 PM AST 7:00 AM PT
    PFL Chicago 2 FRI OCT 16 Main Card 11:00 PM ET Early Card 6:00 PM ET

THE ROW STARTS WHEN THE BROADCAST DOES — the earliest time the header
prints, which is the early card where there is one. Each time is read
in the zone printed beside it, through the zone database, so a card in
December is not an hour wrong by the summer clock. AST here is Arabia
Standard Time: the league's MENA cards are in Riyadh, and "5:00 PM AST
7:00 AM PT" is the header's own proof — three hours ahead of UTC.

A CLOCK THAT IS A PLACEHOLDER IS NOT A CLOCK. An announced card without
its time yet prints "12:00 AM ET"; that is not a broadcast at midnight,
it is a date with no time, so the card is left off until the league
publishes one — and it appears by itself on the pass after it does.

AND THE BROADCASTER IS NOT INVENTED. The row names no channel and the
board's own honest word for that, PPV, is what prints beside it.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from epg_lib import fetch, log, norm, warn

URL = "https://pflmma.com/events"

# The zones the league prints beside a time.
ZONES = {
    "ET": ZoneInfo("America/New_York"),
    "EST": ZoneInfo("America/New_York"),
    "EDT": ZoneInfo("America/New_York"),
    "PT": ZoneInfo("America/Los_Angeles"),
    "PST": ZoneInfo("America/Los_Angeles"),
    "PDT": ZoneInfo("America/Los_Angeles"),
    "CT": ZoneInfo("America/Chicago"),
    "AST": timezone(timedelta(hours=3)),      # Arabia Standard Time
    "GST": timezone(timedelta(hours=4)),      # Gulf Standard Time
    "GMT": timezone.utc,
    "UTC": timezone.utc,
    "+00": timezone.utc,
    "BST": ZoneInfo("Europe/London"),
    "CET": ZoneInfo("Europe/Paris"),
    "CEST": ZoneInfo("Europe/Paris"),
    "WAT": timezone(timedelta(hours=1)),
}

MONTHS = {m: i for i, m in enumerate(
    ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), start=1)}

# The upcoming tab, and the cards inside it.
UPCOMING = re.compile(r'id="nav-upcoming"(.*?)id="nav-past"', re.S)
A_CARD = re.compile(
    r"<h3[^>]*>\s*(.*?)\s*</h3>.*?href=\"(https://pflmma\.com/event/[^\"]+)\"",
    re.S)

# The card page's header: "EVENT INFO <name> FRI OCT 2 ... Where to watch".
HEADER = re.compile(r"EVENT INFO(.*?)(?:Where to watch|TICKETS|Buy Tickets)",
                    re.S | re.I)
A_DAY = re.compile(r"\b(?:MON|TUE|WED|THU|FRI|SAT|SUN)\w*,?\s+"
                   r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\w*\s+"
                   r"(\d{1,2})\b", re.I)
A_TIME = re.compile(r"\b(\d{1,2}):(\d{2})\s*([AP]M)\s*"
                    r"(ET|EST|EDT|PT|PST|PDT|CT|AST|GST|GMT|UTC|\+00|BST|CEST|CET|WAT)\b",
                    re.I)
TAGS = re.compile(r"<[^>]+>")


def text_of(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
    return norm(TAGS.sub(" ", html).replace("&amp;", "&").replace("&nbsp;", " "))


def upcoming_cards(page: str) -> list[tuple[str, str]]:
    """(name, card page URL) for every card under the UPCOMING tab."""
    tab = UPCOMING.search(page)
    if not tab:
        return []
    out, seen = [], set()
    for name, url in A_CARD.findall(tab.group(1)):
        name = norm(TAGS.sub(" ", name))
        if name and url not in seen:
            seen.add(url)
            out.append((name, url))
    return out


def start_of(card_page: str, now: datetime) -> datetime | None:
    """The earliest instant the card's header prints, or None."""
    header = HEADER.search(text_of(card_page))
    if not header:
        return None
    said = header.group(1)
    day = A_DAY.search(said)
    if not day:
        return None
    month, date = MONTHS[day.group(1).upper()[:3]], int(day.group(2))
    # The header prints no year: the card is the next such date, never
    # one more than a month in the past.
    year = now.year
    if datetime(year, month, date, tzinfo=timezone.utc) < now - timedelta(days=31):
        year += 1

    instants = []
    for hour, minute, half, zone in A_TIME.findall(said[day.end():]):
        hour, minute = int(hour) % 12, int(minute)
        if half.upper() == "PM":
            hour += 12
        local = datetime(year, month, date, hour, minute,
                         tzinfo=ZONES[zone.upper()])
        instants.append((local, hour, minute))
    if not instants:
        return None
    # "12:00 AM" with nothing else beside it is a date without its time.
    if all(hour == 0 and minute == 0 for _, hour, minute in instants):
        return None
    return min(local.astimezone(timezone.utc) for local, _, _ in instants)


def events(session, floor=None, ceiling=None) -> list[dict]:
    """The PFL's own calendar, or none if the league's page is having a bad day."""
    try:
        cards = upcoming_cards(fetch(session, URL).text)
    except Exception as exc:                                      # noqa: BLE001
        warn(f"pfl's own events page failed ({exc}) — the board keeps what "
             f"the other sources gave it")
        return []
    if not cards:
        log("  pfl: no upcoming card on the page this pass")
        return []

    now = datetime.now(timezone.utc)
    out: list[dict] = []
    for name, url in cards:
        try:
            start = start_of(fetch(session, url).text, now)
        except Exception as exc:                                  # noqa: BLE001
            warn(f"pfl: {name}'s page failed ({exc}) — left for the next pass")
            continue
        if start is None:
            log(f"  pfl: {name} has no published time yet — left off until it does")
            continue
        out.append({
            "start": start,
            "title": name,
            "sport": "MMA",
            # No broadcaster a viewer here can turn to is named; the
            # board's own PPV word prints beside the row.
            "channels": [],
            "source": "pfl",
        })
        log(f"  pfl: {name}, {start:%d.%m %H:%M} UTC")
    if floor is not None:
        out = [event for event in out if floor <= event["start"] < ceiling]
    return out
