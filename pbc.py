#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Premier Boxing Champions, from the promotion's own schedule page.

Asked for in the reader's own words — "More PPV MMA/Boxing events from
more sources" — and PBC is the boxing promotion no source on this board
carried: wheresthematch's boxing page has none of its cards, Sky's
guide names none, Tapology files the UFC and the UFC only. The
promotion publishes its schedule as an open JSON-LD block on its own
page, printed before a line of this was written:

    <script type="application/ld+json">
    {
      "@type": "SportsEvent",
      "name": "Isaac Cruz vs Nestor Bravo, Jesus Ramos vs Meiirim
               Nursultanov",
      "startDate": "2026-09-19T20:00:00-05:00",
      "description": "… the 12-round main event streaming live on DAZN
                      and presented by Premier Boxing Champions on
                      Saturday, September 19 from Pechanga Arena in
                      San Diego, California."
    }

THE BROADCASTER IS THE DESCRIPTION'S OWN WORDS, because the JSON names
no channel field and the page's own prose says it plainly: "streaming
live on DAZN", "live on TNT and DAZN". The channels a viewer can be put
on are read from those words — nothing here claims a channel the
promotion did not name itself. A card whose description names no
watchable way is left alone, the same rule every row on the board
obeys: an event with no published broadcaster is not shown.

THE TIME IS THE JSON'S OWN. The startDate carries its own zone as an
offset ("-05:00"), so the clock is placed exactly where the promotion
put it and no zone word has to be guessed or corrected. A card with no
startDate is not a broadcast this reader can place, and is left rather
than guessed at.

THE NAME IS THE CARD'S OWN — the fights, in the promotion's own order,
comma-joined exactly as it prints them, with the casing every other
boxing row on this board already uses. Nothing is renamed: the reader's
rule is that a match's name is never overridden.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from epg_lib import fetch, log, norm, warn

SOURCE = "https://premierboxingchampions.com/schedule/"

# The JSON-LD blocks, wherever in the page the CMS put them. The page
# wraps each card in its own <script type="application/ld+json">, and
# only a block that calls itself a SportsEvent is a fight card.
A_BLOCK = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
A_SPORTS_EVENT = "SportsEvent"

# How the promotion's prose names where the night is watchable: "the
# 12-round main event streaming live on DAZN", "headlining the latest
# installment of “The Fight” live on TNT and DAZN". The first "live on"
# is the claim, and its sentence — as far as the first full stop — is
# the only place in the description a channel is named.
A_WATCHABLE = re.compile(r"live on ([^.]+)", re.I)

# The channel names as the descriptions spell them, in the casing a
# viewer is told. A match on a name not in here is kept in the words it
# arrived in, norm-ed, which is the same treatment every other source's
# channel list gets.
AS_PRINTED = {
    "dazn": "DAZN",
    "tnt": "TNT",
    "tnt sports": "TNT Sports",
    "tnt sports 1": "TNT Sports 1",
    "tnt sports 2": "TNT Sports 2",
    "prime video": "Prime Video",
    "prime": "Prime Video",
    "amazon prime video": "Prime Video",
    "showtime": "Showtime",
    "fs1": "FS1",
    "fox": "Fox",
    "peacock": "Peacock",
    "espn": "ESPN",
    "espn+": "ESPN+",
}


def the_channels(sentence: str) -> list[str]:
    """Every channel the promotion's own "live on" sentence names.

    The sentence names its channels and then moves on — "live on TNT
    and DAZN on Saturday, October 17 from The Chelsea…" — so a channel
    is found by its own name, on a word boundary, anywhere in the
    sentence. A name found inside a longer name ("TNT" inside "TNT
    Sports 1") is the same channel, not a second one, and the channels
    are printed in the order the promotion said them. A sentence that
    names nothing this reader recognises leaves the card with no way to
    watch it, so the card is left alone.
    """
    matches = [
        (m.start(), m.end(), AS_PRINTED[key])
        for key in AS_PRINTED
        for m in re.finditer(rf"\b{re.escape(key)}(?!\w)", sentence, re.I)]
    kept = []
    for found in sorted(matches, key=lambda m: -(m[1] - m[0])):
        if not any(s <= found[0] and found[1] <= e for s, e, _ in kept):
            kept.append(found)
    out: list[str] = []
    for _start, _end, name in sorted(kept, key=lambda m: m[0]):
        if name not in out:
            out.append(name)
    return out


def a_start(when: str):
    """The card's own clock, or None if the promotion printed none.

    The JSON carries the zone in the timestamp itself, so the time is
    placed where the promotion placed it. A startDate this reader
    cannot read is not a time to guess at — the card is left alone.
    """
    try:
        return datetime.fromisoformat(when)
    except (TypeError, ValueError):
        return None


def collect(page: str) -> list[dict]:
    """Every card on the page that names a way to watch it."""
    out: list[dict] = []
    for block in A_BLOCK.finditer(page):
        try:
            data = json.loads(block.group(1))
        except ValueError:
            continue
        if not isinstance(data, dict) or data.get("@type") != A_SPORTS_EVENT:
            continue
        name = norm(data.get("name") or "")
        when = a_start(data.get("startDate") or "")
        if not name or when is None:
            continue

        # Where the promotion's own prose says the night is watchable —
        # "streaming live on DAZN", "live on TNT and DAZN" — and only
        # there. The sentence to the first full stop is the whole claim
        # about channels; the rest of the description is the venue and
        # the date.
        watch = A_WATCHABLE.search(norm(data.get("description") or ""))
        channels = the_channels(watch.group(1)) if watch else []
        if not channels:
            log(f"  premierboxingchampions: {name} has no way to watch "
                "named yet — the card is left alone")
            continue

        # The timestamp carries its own zone, so the clock is placed
        # exactly where the promotion placed it; a bare local clock is
        # the one thing this reader will not guess at.
        if when.tzinfo is None:
            warn(f"premierboxingchampions printed a clock with no zone "
                 f"for {name} — the card is left rather than guessed at")
            continue
        start = when.astimezone(timezone.utc)
        out.append({
            "start": start,
            "title": name,
            "sport": "Boxing",
            "channels": channels,
        })
        log(f"  premierboxingchampions: {name} on "
            f"{', '.join(channels)}, {start:%d.%m %H:%M} UTC")
    if not out:
        log("  premierboxingchampions: no card on the page names a "
            "channel yet")
    return out


def events(session, floor=None, ceiling=None) -> list[dict]:
    """The promotion's own cards, or none if its page is having a bad day."""
    try:
        page = fetch(session, SOURCE).text
    except Exception as exc:                                  # noqa: BLE001
        warn(f"premierboxingchampions.com is unreachable ({exc}) — the "
             f"board keeps what the other sources gave it")
        return []
    found = collect(page)
    if floor is not None:
        found = [event for event in found
                 if floor <= event["start"] < ceiling]
    return found
