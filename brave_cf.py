#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BRAVE CF's own events pages, read the way the promotion publishes them.

Asked for by name — "add PFL and BRAVE the same way" as OKTAGON: on
channel 2, updating whenever they have an event, and PPV where the
channel is not known. Tapology was the only door BRAVE came through and
it answers 403 to this board's reader.

THE PROMOTION'S OWN SCHEMA. bravecf.com describes each card as a
schema.org Event in JSON-LD, on its upcoming page and on the card's own
page, with a startDate and an eventStatus. A card whose status says it
is completed, cancelled or postponed is not a broadcast to come.

A DATE IS NOT A CLOCK. The promotion writes its past cards' startDate as
midnight UTC — "2026-09-05T00:00:00+00:00" — which is the day, not the
time the cage door shuts. Midnight exactly is therefore read as "time
not published": the card is left off until a real time is printed,
rather than put on the board at an hour nobody announced.

AND THE BROADCASTER IS NOT INVENTED. BRAVE shows its cards on its own
BRAVE TV; the row names no channel and prints PPV.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from epg_lib import fetch, log, norm, warn

PAGES = ("https://www.bravecf.com/upcoming-events",
         "https://www.bravecf.com/events")

LD = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)
OVER = re.compile(r"Completed|Cancelled|Postponed|Rescheduled|MovedOnline", re.I)


def events_in(node, out: list[dict]) -> None:
    if isinstance(node, dict):
        if node.get("@type") == "Event" and node.get("startDate"):
            out.append(node)
        for value in node.values():
            events_in(value, out)
    elif isinstance(node, list):
        for value in node:
            events_in(value, out)


def collect(page: str, now: datetime) -> list[dict]:
    found: list[dict] = []
    for block in LD.findall(page):
        try:
            events_in(json.loads(block, strict=False), found)
        except ValueError:
            continue
    out = []
    for card in found:
        name = norm(card.get("name") or "")
        if not name or OVER.search(card.get("eventStatus") or ""):
            continue
        try:
            start = datetime.fromisoformat(card["startDate"]).astimezone(timezone.utc)
        except (ValueError, TypeError):
            continue
        if start < now:
            continue
        if (start.hour, start.minute) == (0, 0):
            log(f"  brave: {name} has only a date published — left off until "
                f"a time is")
            continue
        out.append({"start": start, "title": name, "sport": "MMA",
                    "channels": [], "source": "brave"})
    return out


def events(session, floor=None, ceiling=None) -> list[dict]:
    """BRAVE CF's own calendar, or none if the promotion's pages are having a bad day."""
    now = datetime.now(timezone.utc)
    out: dict[tuple, dict] = {}
    for url in PAGES:
        try:
            page = fetch(session, url).text
        except Exception as exc:                                  # noqa: BLE001
            warn(f"brave: {url} failed ({exc}) — the board keeps what the "
                 f"other sources gave it")
            continue
        for event in collect(page, now):
            out.setdefault((event["title"].casefold(), event["start"]), event)
    found = sorted(out.values(), key=lambda e: e["start"])
    for event in found:
        log(f"  brave: {event['title']}, {event['start']:%d.%m %H:%M} UTC")
    if not found:
        log("  brave: no upcoming card with a published time this pass")
    if floor is not None:
        found = [e for e in found if floor <= e["start"] < ceiling]
    return found
