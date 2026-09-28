#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Real American Freestyle, from the promotion's own events page.

Asked for by name — "check this and other resources for RAF" — and the
page answers with everything a board row needs, printed before a line
of this was written:

    <div class="text-block-28">RAF MOSCOW</div>            the event
    <div class="text-block-28-copy">CHIMAEV VS WOODLEY</div>   the fight
    <div class="event-card_date small">September 5, 2026</div>
    <div class="event-card_location small">Moscow, Russia</div>

and, in its own "how to watch" section, the one broadcaster that has
announced a time:

    watch on
    fox nation
    Sep 5, 2026 12:00 PM  est

That watch block is the whole door. RAF13 (Miami) and RAF14 (Las Vegas)
carry ticket links and no broadcaster, and the second board does not
show an event until somebody publishes a channel for it — the same rule
every row on it obeys — so those cards are skipped today and appear the
day RAF publishes their watch blocks, with nobody editing anything.

THE TIME IS EASTERN, WHATEVER IT SAYS BESIDE IT. The page prints "est"
as a word for Eastern Time, and the event it belongs to is in
September, when New York is on EDT. Reading the label literally would
put the card an hour late; the stream starts at noon in New York, so
noon in New York is what is built. `st`-style mistakes — a printed
clock placed in the wrong zone — are the fault this project has paid
for most, and the guard here is that only an Eastern word is accepted
at all: a label that is not est/edt/et is not a time this page can
place, and the card is left rather than guessed at.

THE WATCH TIME IS JOINED TO ITS CARD BY DATE. The watch section names
no event; it is the next thing to watch. Its date — "Sep 5, 2026" — is
matched to the card that carries the same date — "September 5, 2026" —
so a watch block can never attach itself to the wrong card, and a card
with no watch block of its own never borrows another's.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from epg_lib import fetch, log, norm, warn

SOURCE = "https://www.realamericanfreestyle.com/events-gallery"

# New York, not a fixed offset — see the module docstring.
EASTERN = "America/New_York"

# The words the page may print beside a time. Anything else is not a
# time this reader can place, and placing it anyway is the one mistake
# this file exists not to make.
AN_EASTERN_WORD = re.compile(r"^(?:est|edt|et)$", re.I)

# One event card: its name, its fight, its day, its city. The name sits
# in text-block-28 and the fight in text-block-28-copy; the date and
# location follow inside the same card.
A_CARD = re.compile(
    r'class="text-block-28">\s*([^<]+?)\s*</div>\s*'
    r'<div class="text-block-28-copy">\s*([^<]+?)\s*</div>(.*?)'
    r'class="event-card_date[^"]*">\s*([^<]+?)\s*</div>.*?'
    r'class="event-card_location[^"]*">\s*([^<]+?)\s*</div>', re.S)

# The watch block: the first text-block-76 after "watch on" is the
# broadcaster, and the pair after it is the clock and its zone word.
A_WATCH = re.compile(
    r'watch\s+on</div>.*?class="text-block-76[^"]*">\s*([^<]+?)\s*</div>'
    r'.*?class="text-block-76[^"]*">\s*'
    r'([A-Za-z]{3,9} \d{1,2}, \d{4} \d{1,2}:\d{2} [AP]M)\s*</div>\s*'
    r'<div class="text-block-76[^"]*">\s*([A-Za-z]+)\s*</div>', re.S)

# How the page writes a card's own date, and the watch block's.
A_CARD_DAY = "%B %d, %Y"
A_WATCH_DAY = "%b %d, %Y %I:%M %p"

# The one broadcaster this page names, spelled the way a board spells
# a channel. "fox nation" is the page's own lower-case; a viewer is
# told the name the channel answers to.
AS_PRINTED = {
    "fox nation": "Fox Nation",
}


def a_title(name: str, fight: str) -> str:
    """The card as one row, in the casing the board's other rows use.

    The page shouts its headlines — "RAF MOSCOW", "CHIMAEV VS
    WOODLEY" — and every other row on this board is written normally,
    so a word in full capitals becomes a word: MOSCOW to Moscow, VS to
    vs. What does not come down is the promotion's own mark, RAF and
    its numbered events, and anything with a digit in it — RAF13 is a
    name, not a sentence.
    """
    keep = {"raf"}

    def one(word: str) -> str:
        if any(ch.isdigit() for ch in word):
            return word
        if word.casefold() in keep:
            return word
        if not word.isupper():
            return word
        return "vs" if word == "VS" else word.capitalize()

    said = " ".join(one(word) for word in name.split())
    fought = " ".join(one(word) for word in fight.split())
    return norm(f"{said}: {fought}")


def collect(page: str) -> list[dict]:
    """Every card the page carries that a broadcaster has announced."""
    # The watch block first: it is the only place the page names a
    # channel and a clock, and without both a card is a calendar entry,
    # not a broadcast.
    watch = A_WATCH.search(page)
    if not watch:
        log("  realamericanfreestyle: no watch block on the page "
            "— nothing is on a channel yet")
        return []

    channel = AS_PRINTED.get(norm(watch.group(1)).casefold(),
                             norm(watch.group(1)))
    try:
        when = datetime.strptime(norm(watch.group(2)), A_WATCH_DAY)
    except ValueError:
        warn("realamericanfreestyle printed a clock this reader cannot "
             f"read ('{watch.group(2)}') — the card is left alone")
        return []
    if not AN_EASTERN_WORD.search(norm(watch.group(3))):
        warn(f"realamericanfreestyle printed '{watch.group(3)}' beside "
             "its clock, which is not an Eastern word — the card is "
             "left rather than placed in a guessed zone")
        return []

    from zoneinfo import ZoneInfo
    start = when.replace(tzinfo=ZoneInfo(EASTERN)).astimezone(timezone.utc)

    out: list[dict] = []
    for card in A_CARD.finditer(page):
        name, fight, _, day, _city = [norm(part) for part in card.groups()]
        try:
            the_day = datetime.strptime(day, A_CARD_DAY)
        except ValueError:
            continue
        # The watch block belongs to the card that carries its own date
        # — the join that keeps one card from borrowing another's night.
        if the_day.date() != when.date():
            continue
        out.append({
            "start": start,
            "title": a_title(name, fight),
            "sport": "MMA",
            "channels": [channel],
        })
        log(f"  realamericanfreestyle: {a_title(name, fight)} on "
            f"{channel}, {start:%d.%m %H:%M} UTC")
    if not out:
        log("  realamericanfreestyle: the watch block names a day no "
            "card on the page carries")
    return out


def events(session, floor=None, ceiling=None) -> list[dict]:
    """The promotion's own events, or none if its page is having a bad day."""
    try:
        page = fetch(session, SOURCE).text
    except Exception as exc:                                  # noqa: BLE001
        warn(f"realamericanfreestyle.com is unreachable ({exc}) — the "
             f"board keeps what the other sources gave it")
        return []
    found = collect(page)
    if floor is not None:
        found = [event for event in found
                 if floor <= event["start"] < ceiling]
    return found
