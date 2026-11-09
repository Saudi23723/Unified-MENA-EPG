#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UFC BJJ's own page on ufc.com, read the way the promotion publishes it.

Asked for by name — "why doesn't channel 2 have the UFC BJJ events?" —
and until now no door reached them: the listings pages carry UFC's
fights and not its grappling cards, and Tapology's televised list is
read through a proxy that answers 403 from a runner.

WHERE THE CARD AND ITS CLOCK ARE. ufc.com/ufcbjj leads with the next
card, in its own words, measured from a runner on 24 September 2026:

    UFC BJJ 11: Musumeci vs Mitchell is live Thursday, September 24
    at 8pm ET/5pm PT ... Watch On UFC FIGHT PASS

The clock is the promotion's own, printed in Eastern time, and read in
America/New_York so the change to and from daylight saving is the zone's
business, not this file's. The page prints no year: the card is placed
in the year that puts it nearest to today.

AND THE BROADCASTER IS THE ONE THE PAGE NAMES. The card streams on UFC
Fight Pass, and the row says so; a card the page names no carrier for is
still shown, as PPV, like every other promotion's own card on this board.
The UFC BJJ Opens — the amateur tournament advertised under it — is a
registration, not a broadcast, and is not read.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from epg_lib import fetch, log, norm, warn

URL = "https://www.ufc.com/ufcbjj"
EASTERN = ZoneInfo("America/New_York")

MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}

# "UFC BJJ 11: Musumeci vs Mitchell is live Thursday, September 24 at
# 8pm ET" — the card's name, then its day and its Eastern clock.
A_CARD = re.compile(
    r"(UFC BJJ\s*\d+[A-Za-z]?(?::\s*[^.]*?)?)\s+(?:is|goes|streams)?\s*live\s+"
    r"(?:\w+day,?\s+)?([A-Za-z]+)\s+(\d{1,2})(?:,?\s*(\d{4}))?\s+at\s+"
    r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?\s*ET", re.I)
ON_FIGHT_PASS = re.compile(r"fight\s*pass", re.I)
TAGS = re.compile(r"<[^>]+>")


def text_of(page: str) -> str:
    page = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", page)
    return norm(TAGS.sub(" ", page).replace("&amp;", "&").replace("&nbsp;", " "))


def nearest_year(month: int, day: int, now: datetime) -> int:
    """The year that puts a yearless date closest to today."""
    return min((now.year - 1, now.year, now.year + 1),
               key=lambda y: abs((datetime(y, month, day, tzinfo=timezone.utc)
                                  - now).total_seconds()))


def collect(page: str, now: datetime) -> list[dict]:
    words = text_of(page)
    out, seen = [], set()
    for name, month, day, year, hour, minute, half in A_CARD.findall(words):
        month_no = MONTHS.get(month[:3].casefold())
        if not month_no:
            continue
        clock = int(hour) % 12 + (12 if half.casefold() == "p" else 0)
        year_no = int(year) if year else nearest_year(month_no, int(day), now)
        start = datetime(year_no, month_no, int(day), clock, int(minute or 0),
                         tzinfo=EASTERN).astimezone(timezone.utc)
        # A write-up prints the card's name twice in a row — once as its
        # heading, once in the sentence — and only the last one is the
        # name.
        title = norm(name[name.casefold().rfind("ufc bjj"):])
        if (title, start) in seen or start < now - timedelta(hours=4):
            continue
        seen.add((title, start))
        # The carrier the page names beside the card, or none at all.
        after = words[words.find(name):words.find(name) + 400]
        channels = ["UFC Fight Pass"] if ON_FIGHT_PASS.search(after) else []
        out.append({"start": start, "title": title, "sport": "MMA",
                    "competition": "UFC BJJ", "channels": channels,
                    "source": "ufcbjj"})
    return out


# EVERY CARD THE PROMOTION HAS WRITTEN UP, NOT ONLY THE NEXT ONE. Asked
# for in those words — "not just this page or this event, the whole
# future, automatically". The page leads with one card, but it links the
# UFC's own write-up of every card it is promoting ("/news/ufc-bjj-11-
# musumeci-vs-mitchell-fight-card"), and each write-up prints its card's
# day and Eastern clock the same way. So every such link is followed and
# read with the same pattern, and a card announced weeks ahead reaches
# the board the moment its window opens, with no one touching anything.
# A card that no page gives a clock for is left off, never guessed.
A_WRITE_UP = re.compile(r'href="((?:https://www\.ufc\.com)?/news/ufc-bjj-\d+[^"#?]*)"',
                        re.I)


def write_ups(page: str) -> list[str]:
    seen = []
    for link in A_WRITE_UP.findall(page):
        url = link if link.startswith("http") else "https://www.ufc.com" + link
        if url not in seen:
            seen.append(url)
    return seen


def events(session, floor=None, ceiling=None) -> list[dict]:
    """Every UFC BJJ card the promotion has a clock for, or none today."""
    now = datetime.now(timezone.utc)
    try:
        page = fetch(session, URL).text
    except Exception as exc:                                      # noqa: BLE001
        warn(f"UFC BJJ's own page failed ({exc}) — the board keeps what the "
             f"other sources gave it")
        return []
    out = collect(page, now)
    for url in write_ups(page)[:6]:
        try:
            more = collect(fetch(session, url).text, now)
        except Exception as exc:                                  # noqa: BLE001
            log(f"  ufc bjj: {url} unreadable this pass ({exc})")
            continue
        known = {(e["title"].split(":")[0].casefold(), e["start"]) for e in out}
        out += [e for e in more
                if (e["title"].split(":")[0].casefold(), e["start"]) not in known]
    for event in out:
        log(f"  ufc bjj: {event['title']}, {event['start']:%d.%m %H:%M} UTC "
            f"on {', '.join(event['channels']) or 'PPV'}")
    if floor is not None:
        out = [e for e in out if floor <= e["start"] < ceiling]
    return out
