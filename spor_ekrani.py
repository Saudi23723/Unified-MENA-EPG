#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Spor Ekranı, read for the Turkish channel a match is on.

Named three times before it was acted on, and it deserved to be: of every
page examined for this channel it is the best structured. It publishes
schema.org ld+json, so the kickoff is a real timestamp rather than a clock
that has to be placed in a timezone — the fault that cost this guide a day
and then an hour.

The repository already reads this page in update_tabii_epg, and this
follows the shape that code proved rather than inventing one:

    { "@type": "BroadcastEvent",
      "isLiveBroadcast": true,
      "publishedOn": [ { "name": "Bein Sports 1", ... } ],
      "broadcastOfEvent": { "name": "İstanbul Başakşehir - Galatasaray",
                            "startDate": "...", "endDate": "...",
                            "homeTeam": {...}, "awayTeam": {...} } }

Used to NAME channels, never to add fixtures — the same limit as the
guides this repository publishes itself, and for the same reason. Of 133
broadcasts on the day this was written, 29 carry a structured channel in
publishedOn; the rest name it only inside a Turkish sentence, and a
channel picked out of prose is exactly the kind of guess that has cost
this channel real matches. Those are left alone.

Its channels are Turkey's, so they are marked TR. beIN SPORTS 1 in
Istanbul is not beIN SPORTS 1 in Doha, and a reader with both in their
playlist needs the row to say which one it means.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from epg_lib import log, norm, warn

SOURCE = "https://www.sporekrani.com/"
MARK = " TR"

LD_JSON = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.S)

# What the page says when it does not know where a match will be shown.
NOT_A_CHANNEL = ("yayın yok", "yayin yok", "bilinmiyor")


def instant(value) -> datetime | None:
    """A schema.org timestamp as a UTC instant, or nothing."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.astimezone(timezone.utc) if stamp.tzinfo \
        else stamp.replace(tzinfo=timezone.utc)


def side_name(value) -> str:
    """A team's name, whether it is written as an object or a string."""
    if isinstance(value, dict):
        return norm(value.get("name") or "")
    return norm(value) if isinstance(value, str) else ""


def fixture_of(slot: dict) -> str:
    """The fixture, preferring the two teams the page names outright."""
    home, away = side_name(slot.get("homeTeam")), side_name(slot.get("awayTeam"))
    if home and away:
        return f"{home} - {away}"
    return norm(slot.get("name") or "")


def channels_of(event: dict) -> list[str]:
    """Every channel named in publishedOn, and nothing read out of prose."""
    published = event.get("publishedOn")
    entries = published if isinstance(published, list) else \
        [published] if published else []
    names = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = norm(entry.get("name") or "")
        if name and name.casefold() not in NOT_A_CHANNEL and name not in names:
            names.append(name)
    return names


def collect(page: str) -> list[dict]:
    """Every broadcast the page publishes, as {start, title, channel}."""
    out: list[dict] = []
    seen_events = 0
    for block in LD_JSON.findall(page):
        try:
            payload = json.loads(block)
        except Exception:
            continue
        for event in (payload if isinstance(payload, list) else [payload]):
            if not isinstance(event, dict):
                continue
            slot = event.get("broadcastOfEvent")
            if not isinstance(slot, dict):
                continue
            seen_events += 1

            start = instant(slot.get("startDate"))
            title = fixture_of(slot)
            if not start or " - " not in title:
                continue
            for channel in channels_of(event):
                out.append({"start": start, "title": title,
                            "channel": f"{channel}{MARK}"})

    log(f"  Spor Ekranı: {seen_events} broadcast(s), "
        f"{len(out)} naming a channel")
    return out


def broadcasts(session) -> list[dict]:
    """Read the page, and treat a bad day there as no reason to fail here."""
    from epg_lib import fetch
    try:
        return collect(fetch(session, SOURCE).text)
    except Exception as exc:
        warn(f"Spor Ekranı is unreachable ({exc}) — the board keeps the "
             f"channels the other sources gave it")
        return []
