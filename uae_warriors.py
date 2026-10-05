#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UAE Warriors' own home page, read the way the promotion publishes it.

Asked for by name — "UAE Warriors?" — on channel 2 the same way as
OKTAGON, PFL and BRAVE: from the promotion's own site, updating whenever
it has an event, and PPV where the channel is not known.

WHERE THE CARD AND ITS CLOCK ARE. The home page carries an "Upcoming
Events" block, in its own words:

    Upcoming Events UAE WARRIORS 73 Lany Silva vs Michele Oliveira
    Date : Monday 05 October 2026 Location : Casino Estoril, Portugal

and beside it the countdown the page runs to the card, as a UNIX second:

    data-date="1791212400"          -> 2026-10-05 15:00 UTC

The printed date has no time; the countdown is the promotion's own
instant for the same card, so the row's start is the countdown — and
only when it falls on the printed date (a day either side, for the
zones between the venue and UTC). A countdown that belongs to some other
date is not this card's clock, and the card is left off rather than put
at an hour nobody announced.

AND THE BROADCASTER IS NOT INVENTED. UAE Warriors shows its cards on its
own app; the row names no channel and prints PPV.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from epg_lib import fetch, log, norm, warn

URL = "https://www.uaewarriors.com/"

COUNTDOWN = re.compile(r'data-date="(\d{9,11})"')
UPCOMING = re.compile(r"Upcoming Events(.*?)(?:View Latest|Previous Events|Latest news|\Z)",
                      re.S | re.I)
A_CARD = re.compile(
    r"(UAE WARRIORS\s+\d+[A-Z]?)\s+(.*?)\s+Date\s*:\s*\w+\s+"
    r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", re.I | re.S)
MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}
TAGS = re.compile(r"<[^>]+>")


def text_of(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
    return norm(TAGS.sub(" ", html).replace("&amp;", "&").replace("&nbsp;", " "))


def spelled(name: str) -> str:
    """"UAE WARRIORS 73" -> "UAE Warriors 73"."""
    return re.sub(r"(?i)^uae warriors", "UAE Warriors", norm(name))


def collect(page: str, now: datetime) -> list[dict]:
    block = UPCOMING.search(text_of(page))
    if not block:
        log("  uae warriors: no upcoming block on the page this pass")
        return []
    clocks = [datetime.fromtimestamp(int(s), timezone.utc)
              for s in COUNTDOWN.findall(page)]
    out = []
    for name, bout, day, month, year in A_CARD.findall(block.group(1)):
        month_no = MONTHS.get(month[:3].casefold())
        if not month_no:
            continue
        printed = datetime(int(year), month_no, int(day), tzinfo=timezone.utc)
        start = next((c for c in clocks
                      if abs((c.date() - printed.date()).days) <= 1), None)
        title = spelled(name)
        if start is None:
            log(f"  uae warriors: {title} has only a date published — left "
                f"off until a time is")
            continue
        if start < now:
            continue
        bout = norm(bout)
        if bout and len(bout) < 80:
            title = f"{title}: {bout}"
        out.append({"start": start, "title": title, "sport": "MMA",
                    "channels": [], "source": "uaewarriors"})
    return out


def events(session, floor=None, ceiling=None) -> list[dict]:
    """UAE Warriors' own calendar, or none if the page is having a bad day."""
    try:
        out = collect(fetch(session, URL).text, datetime.now(timezone.utc))
    except Exception as exc:                                      # noqa: BLE001
        warn(f"uae warriors' own page failed ({exc}) — the board keeps what "
             f"the other sources gave it")
        return []
    for event in out:
        log(f"  uae warriors: {event['title']}, {event['start']:%d.%m %H:%M} UTC")
    if floor is not None:
        out = [e for e in out if floor <= e["start"] < ceiling]
    return out
