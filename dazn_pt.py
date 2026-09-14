#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DAZN Portugal's linear EPG, retaining only genuinely live sports events.

DAZN's former ``epgWithDatesRange`` endpoint now returns HTTP 403.  The live
TV schedule moved to the public v10 Rail endpoint.  Each DAZN 1-5 tile carries
its own Now/Next/Later schedule and, crucially, every programme states both
``IsLive`` and ``ProgramType``.  Requiring ``IsLive is True`` and
``ProgramType == "Sports event"`` rejects recorded matches and live studio
shows without guessing from their titles.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from epg_lib import fetch, log, norm, warn

BASE = "https://rail-router.discovery.indazn.com/eu/v10/Rail"
COUNTRY = "pt"
LANGUAGE = "pt"
LINEAR_CHANNELS = tuple(f"DAZN {n}" for n in range(1, 6))
RAIL_PARAMS = {
    "platform": "web",
    "id": "Livetvschedule",
    "country": COUNTRY,
    "brand": "dazn",
    "languageCode": LANGUAGE,
}
RAIL_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.dazn.com/",
}

# The official feed also labels studio/editorial programming as live or
# upcoming. The requested Portuguese channel is for games and sporting
# events, not talk shows, previews, weigh-ins, press conferences, analysis,
# or magazine blocks.
NOT_A_GAME = re.compile(
        r"\ban[áa]lise\b|\bpreview\b|\bmagazine\b|\bhighlights?\b"
        r"|\bshow\b|\bpub\b|\bconfer[êe]ncia de imprensa\b"
        r"|\bpesagem\b|\bpaddock club\b|\bgera[çc][ãa]o nfl\b"
        r"|\btop ou nem por isso\b|\bthe premier pub\b|\bmanningcast\b"
        r"|\bentrevista\b|\binterview\b|\btalk\b|\best[úu]dio\b"
        r"|\bnot[íi]cias\b|\bdebate\b|\bdocument[áa]rio\b"
        r"|\bpress\s+conference\b|\breplay\b|\brecorded\b"
        r"|\bgravado\b|\brepeti[çc][ãa]o\b", re.I)

SPORTS = {
    "futebol": "Football", "football": "Football", "soccer": "Football",
    "basquetebol": "Basketball", "basketball": "Basketball",
    "futebol americano": "American Football", "american football": "American Football",
    "basebol": "Baseball", "baseball": "Baseball",
    "ténis": "Tennis", "tenis": "Tennis", "tennis": "Tennis",
    "motorsport": "Motorsport", "automobilismo": "Motorsport",
    "auto racing": "Motorsport",
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


def _sport(programme: dict) -> str:
    """Map the first recognised Rail genre to this board's sport labels."""
    genres = programme.get("Genre")
    if not isinstance(genres, list):
        genres = [genres]
    first = ""
    for genre in genres:
        label = genre.get("name") if isinstance(genre, dict) else genre
        label = norm(str(label or ""))
        if not label:
            continue
        first = first or label
        mapped = SPORTS.get(label.casefold())
        if mapped:
            return mapped
    return first.title() if first else "Sports"


def _programmes(tile: dict) -> list[dict]:
    """The ordered Now/Next/Later programmes from one linear-channel tile."""
    schedule = tile.get("LinearSchedule")
    if not isinstance(schedule, dict):
        return []
    rows = [schedule.get("Now"), schedule.get("Next")]
    later = schedule.get("Later")
    if isinstance(later, list):
        rows.extend(later)
    return [row for row in rows if isinstance(row, dict)]

def events(session, floor: datetime | None = None,
           ceiling: datetime | None = None) -> list[dict]:
    try:
        response = fetch(
            session, BASE, params=RAIL_PARAMS, headers=RAIL_HEADERS)
        payload = response.json()
        tiles = payload.get("Tiles", []) if isinstance(payload, dict) else []
    except Exception as exc:  # noqa: BLE001
        warn(f"dazn Portugal linear EPG unreadable ({exc})")
        tiles = []

    out: list[dict] = []
    seen: set[tuple] = set()
    for tile in tiles:
        if not isinstance(tile, dict):
            continue
        channel = norm(str(tile.get("Title") or ""))
        if channel not in LINEAR_CHANNELS:
            continue
        for programme in _programmes(tile):
            # IsLive alone is insufficient: DAZN marks live studio/talk
            # blocks too. ProgramType alone is insufficient: recorded games
            # are Sports event. Both together mean a live sporting event.
            if (programme.get("IsLive") is not True
                    or programme.get("ProgramType") != "Sports event"):
                continue
            start = _parse(programme.get("Start"))
            end = _parse(programme.get("End"))
            if not start or not end or end <= start:
                continue
            if floor and start < floor or ceiling and start >= ceiling:
                continue
            competition = norm(str(programme.get("Title") or "DAZN Portugal"))
            title = norm(str(programme.get("EpisodeTitle") or competition))
            searchable = " ".join(str(programme.get(key) or "")
                                  for key in ("Title", "EpisodeTitle",
                                              "Description"))
            if not title or NOT_A_GAME.search(searchable):
                continue
            key = (channel, start, title)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "start": start,
                "on_air_for": end - start,
                "title": title,
                "competition": competition,
                "sport": _sport(programme),
                "channels": [channel],
            })

    log(f"dazn Portugal: {len(out)} live/scheduled event(s); official "
        f"linear channels available: {', '.join(LINEAR_CHANNELS)}")
    return sorted(out, key=lambda item: item["start"])
