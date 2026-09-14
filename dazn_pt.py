#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DAZN Portugal's official EPG, retaining only live or scheduled-live events.

The public DAZN EPG exposes linear channel tiles (DAZN 1-5 and others) and
separate event tiles. The event tiles do not carry a DAZN linear-channel
assignment, so this reader labels them honestly as ``DAZN Portugal`` rather
than duplicating one event onto every linear channel.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from epg_lib import fetch, log, norm, warn

BASE = "https://epg.discovery.indazn.com/pt/v3/epgWithDatesRange"
COUNTRY = "pt"
LANGUAGE = "pt"
CHANNEL = "DAZN Portugal"
# Confirmed by the official Portugal EPG's linear-channel tiles. More may be
# added by DAZN; the event feed must provide an explicit mapping before we
# attach an event to one of them.
LINEAR_CHANNELS = tuple(f"DAZN {n}" for n in range(1, 6))

# The official feed also labels studio/editorial programming as live or
# upcoming. The requested Portuguese channel is for games and sporting
# events, not talk shows, previews, weigh-ins, press conferences, analysis,
# or magazine blocks.
NOT_A_GAME = re.compile(
    r"\ban[áa]lise\b|\bpreview\b|\bmagazine\b|\bhighlights?\b"
    r"|\bshow\b|\bpub\b|\bconfer[êe]ncia de imprensa\b"
    r"|\bpesagem\b|\bpaddock club\b|\bgera[çc][ãa]o nfl\b"
    r"|\btop ou nem por isso\b|\bthe premier pub\b", re.I)

SPORTS = {
    "futebol": "Football", "football": "Football", "soccer": "Football",
    "basquetebol": "Basketball", "basketball": "Basketball",
    "futebol americano": "American Football", "american football": "American Football",
    "basebol": "Baseball", "baseball": "Baseball",
    "ténis": "Tennis", "tenis": "Tennis", "tennis": "Tennis",
    "motorsport": "Motorsport", "automobilismo": "Motorsport",
    "boxe": "Boxing", "boxing": "Boxing", "mma": "MMA",
    "golfe": "Golf", "golf": "Golf", "padel": "Padel",
    "rugby": "Rugby", "ciclismo": "Cycling", "cycling": "Cycling",
    "atletismo": "Athletics", "athletics": "Athletics",
    "natação": "Swimming", "swimming": "Swimming",
    "softball": "Softball", "wrestling": "Wrestling",
    "futsal": "Futsal", "voleibol": "Volleyball",
}


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _sport(tile: dict) -> str:
    sport = tile.get("Sport")
    label = sport.get("Title") if isinstance(sport, dict) else sport
    label = norm(str(label or ""))
    return SPORTS.get(label.casefold(), label.title() if label else "Sports")


def _competition(tile: dict) -> str:
    comp = tile.get("Competition")
    value = comp.get("Title") if isinstance(comp, dict) else comp
    return norm(str(value or "DAZN Portugal"))


def events(session, floor: datetime | None = None,
           ceiling: datetime | None = None) -> list[dict]:
    now = datetime.now(timezone.utc)
    start = (floor or now - timedelta(hours=6)).date()
    end = (ceiling or now + timedelta(days=7)).date()
    # DAZN rejects ranges whose date difference is greater than six. Fetch
    # adjacent six-day windows so an eight-day repository build never loses
    # its final scheduled day.
    tiles: list[dict] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=6), end)
        url = (f"{BASE}?country={COUNTRY}&languageCode={LANGUAGE}"
               f"&startDate={cursor.isoformat()}&endDate={chunk_end.isoformat()}")
        try:
            response = fetch(session, url)
            payload = response.json()
            if isinstance(payload, dict):
                tiles.extend(payload.get("Tiles", []))
        except Exception as exc:  # noqa: BLE001
            warn(f"dazn Portugal EPG window {cursor}..{chunk_end} unreadable ({exc})")
        cursor = chunk_end + timedelta(days=1)
    out: list[dict] = []
    seen: set[tuple] = set()
    for tile in tiles:
        if not isinstance(tile, dict):
            continue
        # Live = currently live; UpComing = scheduled-live. CatchUp,
        # Highlights and all other types are deliberately rejected.
        if tile.get("Type") not in {"Live", "UpComing"}:
            continue
        # Linear channel tiles are not events and have no fixture title.
        if tile.get("IsLinear") or str(tile.get("Title") or "").startswith("DAZN "):
            continue
        start = _parse(tile.get("Start"))
        if not start:
            continue
        if floor and start < floor or ceiling and start >= ceiling:
            continue
        title = norm(str(tile.get("Title") or ""))
        if not title:
            continue
        searchable = " ".join(str(tile.get(key) or "")
                               for key in ("Title", "Description", "Label"))
        if NOT_A_GAME.search(searchable):
            continue
        end = _parse(tile.get("End"))
        duration = end - start if end and end > start and end.year < 2999 else None
        key = (tile.get("EventId") or tile.get("Id"), start, title)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "start": start,
            "on_air_for": duration,
            "title": title,
            "competition": _competition(tile),
            "sport": _sport(tile),
            "channels": [CHANNEL],
        })

    log(f"dazn Portugal: {len(out)} live/scheduled event(s); official "
        f"linear channels available: {', '.join(LINEAR_CHANNELS)}")
    return sorted(out, key=lambda item: item["start"])
