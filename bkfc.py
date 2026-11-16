#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BKFC's own events page, read the way the promotion publishes it.

Asked for by name — "Bkfc schedule??" — and the reason it needs its own
reader is that nothing else on this board can see it any more: ESPN's mma
scoreboard has no bare-knuckle league (both spellings answer 400), and
Tapology, which used to carry BKFC's cards, now answers 403 to this
board's reader. The promotion's own /events page is the only open,
structured place a BKFC card's clock is published.

THE CLOCK IS EASTERN, AND THE PAGE SAYS SO ITSELF. Its own countdown
script carries the sentence in plain words — "all cms dates in EST" —
and parses every published date through America/New_York before turning
it into the reader's local time. This reader does exactly the same, with
the zone database rather than a fixed offset, so a card in October is
not put an hour wrong by the summer clock.

THE NAME IS THE CARD'S OWN — "BKFC 93 HOLLYWOOD PERDOMO vs HILL" —
title-cased the way the rest of this board spells a numbered card, and
nothing is appended: the venue is not part of a name.

AND THE BROADCASTER IS NOT INVENTED. BKFC sells its own cards; the page
names no channel a viewer here can turn to, so the row leaves its channel
list empty and the board's own honest word for that — PPV — is what gets
printed beside it. The same rule every unbroadcast row here obeys.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from epg_lib import fetch, log, norm, warn

URL = "https://www.bkfc.com/events"

# The page's own words: "Parse the EST date string ... all cms dates in
# EST". Read through the zone database, not a fixed -05:00, so the
# summer clock is honoured.
THE_PROMOTIONS_CLOCK = ZoneInfo("America/New_York")

# A card and its clock, as the page prints the pair: the event's title
# sits in the same card block as its "September 11, 2026 7:00 PM".
A_CARD = re.compile(
    r'data-event-label="(BKFC[^"]{2,90}?)"'
    r'.{0,4000}?'
    r'([A-Z][a-z]+ \d{1,2}, \d{4} \d{1,2}:\d{2} [AP]M)',
    re.S)
A_CLOCK = re.compile(r'([A-Z][a-z]+ \d{1,2}, \d{4} \d{1,2}:\d{2} [AP]M)')
A_TITLE = re.compile(r'data-event-label="(BKFC[^"]{2,90}?)"')
TAGS = re.compile(r"<[^>]+>")


def spelled(name: str) -> str:
    """The card's own name, out of the page's shouting capitals."""
    name = norm(TAGS.sub(" ", name).replace("&amp;", "&"))
    words = []
    for word in name.split():
        if word.upper() in ("BKFC", "VS", "KO", "TBA", "UK", "US"):
            words.append("BKFC" if word.upper() == "BKFC" else word.lower()
                         if word.upper() == "VS" else word.upper())
        elif word.isdigit():
            words.append(word)
        else:
            words.append(word.capitalize())
    return " ".join(words)


def collect(page: str) -> list[dict]:
    """Every card on the promotion's page that names both a title and a clock."""
    out: list[dict] = []
    seen: set[tuple] = set()
    # The page repeats each card in several sliders. Walk title/clock
    # pairs in document order and keep the first clock printed after
    # each title, then fold the repeats by (title, instant).
    marks = []
    for hit in A_TITLE.finditer(page):
        marks.append(("title", hit.start(), hit.group(1)))
    for hit in A_CLOCK.finditer(page):
        marks.append(("clock", hit.start(), hit.group(1)))
    marks.sort(key=lambda mark: mark[1])

    pending: str | None = None
    for kind, _where, said in marks:
        if kind == "title":
            pending = said
            continue
        if not pending:
            continue
        title = spelled(pending)
        pending = None
        try:
            local = datetime.strptime(said, "%B %d, %Y %I:%M %p").replace(
                tzinfo=THE_PROMOTIONS_CLOCK)
        except ValueError:
            warn(f"bkfc printed a clock this reader cannot read ('{said}') "
                 f"— the card is left alone")
            continue
        start = local.astimezone(timezone.utc)
        key = (title.casefold(), start)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "start": start,
            "title": title,
            "sport": "Boxing",
            # BKFC sells its own cards; the page names no channel, so
            # the board's own PPV word is what prints beside the row.
            "channels": [],
        })
        log(f"  bkfc: {title}, {start:%d.%m %H:%M} UTC")
    if not out:
        log("  bkfc: no card with a published clock on the page this pass")
    return out


def events(session, floor=None, ceiling=None) -> list[dict]:
    """BKFC's own calendar, or none if the promotion's page is having a bad day."""
    try:
        page = fetch(session, URL).text
    except Exception as exc:                                      # noqa: BLE001
        warn(f"bkfc's own events page is unreachable ({exc}) — the board "
             f"keeps what the other sources gave it")
        return []
    out = collect(page)
    for event in out:
        event["source"] = "bkfc"
    if floor is not None:
        out = [event for event in out if floor <= event["start"] < ceiling]
    return out
