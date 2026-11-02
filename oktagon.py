#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OKTAGON MMA's own events page, read the way the promotion publishes it.

Asked for by name — "add it ... on channel 2 like the UFC and the rest,
and keep it updating whenever they have an event, and where the channel
is not known write PPV". Tapology used to be the only door OKTAGON came
through, and Tapology now answers 403 to this board's reader, so the
cards stopped arriving at all.

THE PAGE CARRIES ITS OWN DATA. oktagonmma.com is a Next.js site; the
events page ships its calendar in __NEXT_DATA__, and one of its queries
is "events after now, soonest first" — every announced card, months
ahead, each with its own startDate. Nothing is scraped from the layout.

THE CLOCK IS UTC, AND THE DATA SAYS SO ITSELF: "2026-09-26T16:00:00.000Z"
is an ISO instant with its zone written on it, so it is read as exactly
that and never through a guessed local clock.

ONLY FIGHT CARDS. The same list carries the promotion's press events —
"OKTAGON TIME", public weigh-ins — under type CONFERENCE. Only type
TOURNAMENT is a card.

AND THE BROADCASTER IS NOT INVENTED. OKTAGON sells its cards on its own
oktagon.tv; the only named broadcasters in its data are regional
redirects (RTL+ for German-speaking countries, TVP for Poland) that do
not reach a viewer here. So the row names no channel and the board's own
honest word for that, PPV, is what prints beside it.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from epg_lib import fetch, log, norm, warn

URL = "https://oktagonmma.com/en/events/"

NEXT_DATA = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

# Words kept as the promotion writes them; everything else is title-cased
# out of the page's shouting capitals.
AS_WRITTEN = {"OKTAGON": "OKTAGON", "VS": "vs", "VS.": "vs.", "MMA": "MMA"}


def spelled(name: str) -> str:
    """"OKTAGON 94: ECKERLIN VS. KOZMA" -> "OKTAGON 94: Eckerlin vs. Kozma"."""
    words = []
    for word in norm(name).split():
        bare = word.rstrip(":")
        tail = word[len(bare):]
        if bare.upper() in AS_WRITTEN:
            words.append(AS_WRITTEN[bare.upper()] + tail)
        elif any(ch.isdigit() for ch in bare):
            words.append(word)
        else:
            words.append("-".join(part.capitalize() for part in bare.split("-"))
                         + tail)
    return " ".join(words)


def cards_in(node, out: list[dict]) -> None:
    """Every event object anywhere in the page's data."""
    if isinstance(node, dict):
        if "startDate" in node and "slug" in node and "title" in node:
            out.append(node)
        for value in node.values():
            cards_in(value, out)
    elif isinstance(node, list):
        for value in node:
            cards_in(value, out)


def title_of(card: dict) -> str:
    title = card.get("title") or {}
    if isinstance(title, str):
        return title
    return title.get("en") or next(iter(title.values()), "")


def collect(page: str) -> list[dict]:
    """Every fight card on the page, with its own UTC instant."""
    found = NEXT_DATA.search(page)
    if not found:
        warn("oktagon: the events page carried no __NEXT_DATA__ this pass "
             "— the board keeps what the other sources gave it")
        return []
    raw: list[dict] = []
    cards_in(json.loads(found.group(1)), raw)

    out: list[dict] = []
    seen: set[tuple] = set()
    for card in raw:
        if card.get("type") != "TOURNAMENT":
            continue
        if card.get("state") not in (None, "ACTIVE"):
            continue
        title = spelled(title_of(card))
        if not title:
            continue
        try:
            start = datetime.fromisoformat(
                card["startDate"].replace("Z", "+00:00")).astimezone(timezone.utc)
        except (ValueError, AttributeError):
            warn(f"oktagon printed a clock this reader cannot read "
                 f"('{card.get('startDate')}') — the card is left alone")
            continue
        key = (card["slug"], start)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "start": start,
            "title": title,
            "sport": "MMA",
            # Sold on oktagon.tv; no broadcaster a viewer here can turn
            # to is named, so the board's own PPV word prints beside it.
            "channels": [],
        })
    out.sort(key=lambda e: e["start"])
    for event in out:
        log(f"  oktagon: {event['title']}, {event['start']:%d.%m %H:%M} UTC")
    if not out:
        log("  oktagon: no fight card on the page this pass")
    return out


def events(session, floor=None, ceiling=None) -> list[dict]:
    """OKTAGON's own calendar, or none if the promotion's page is having a bad day."""
    try:
        page = fetch(session, URL).text
        out = collect(page)
    except Exception as exc:                                      # noqa: BLE001
        warn(f"oktagon's own events page failed ({exc}) — the board keeps "
             f"what the other sources gave it")
        return []
    for event in out:
        event["source"] = "oktagon"
    if floor is not None:
        out = [event for event in out if floor <= event["start"] < ceiling]
    return out
