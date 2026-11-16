#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OLYMPIC-STYLE WRESTLING, from the sport's own governing body.

Asked for by name — "Add major wrestling and Olympic wrestling, Olympic
boxing events / matches to channel 2. Find a reliable sources" — and the
sources were measured on a runner before a line of this was written:

    uww.org/api/events?year=YYYY   ANSWERS. Open JSON, no key, no
                                   browser: the federation's own
                                   calendar, every tournament of the
                                   year, with its dates, its host city
                                   and country, its TYPE (Olympic
                                   Games, World Championships,
                                   Continental Championships, Ranking
                                   Series) and whether UWW is streaming
                                   it.
    uww.org/calendar               404
    uww.org/api/v1/events          404
    wheresthematch /live-wrestling 404 — there is no wrestling page
                                   there; its WWE page is the pro side
                                   and is read separately, see
                                   world_sport_on_tv.py
    worldboxing.org                403 to every request from a runner,
                                   Cloudflare, and its competitions
                                   page carries prose rather than a
                                   dated calendar — so Olympic-style
                                   BOXING keeps the doors it already
                                   has on this board (the boxing
                                   listings page, whose keep is open,
                                   and the Turkish grid's "boks"), and
                                   nothing here guesses at it.

WHAT IS KEPT: the majors only. The Olympic tournament, the World and
Continental Championships, the Ranking Series and the World Cup, at
SENIOR level. An age-group entry — U15, U17, U20, U23 — is refused, the
same way every other board here refuses youth.

THE CLOCK. The federation's calendar is a calendar of DAYS: a
championship runs 08-11 and no hour is printed anywhere in the feed.
A day is not an instant, and this board only draws instants, so each
competition day is placed at the hour a UWW competition day opens — 10:00
in the host city, qualification rounds — in the HOST COUNTRY'S own zone,
never in UTC and never in the reader's. A country this file has no zone
for is skipped rather than guessed at, and the log says so.

THE CHANNEL. UWW streams its own competitions on UWW+ and says so in the
feed itself (streaming_available). Where it does, that is the channel;
where it does not, the row names none and the board's own rule prints
PPV beside it. Nothing is invented.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from epg_lib import fetch, log, norm, warn

# The whole year in one answer. The endpoint pages ten at a time by
# default — measured: count 105, results 10 — and its own
# items_per_page returns every one of them.
SOURCE = "https://uww.org/api/events?items_per_page=200&year="

# The hour a UWW competition day opens with its qualification rounds.
FIRST_SESSION = time(10, 0)

# The tournament types worth a board row, in the feed's own spelling.
A_MAJOR_TYPE = {
    "olympic-games",
    "world-championships",
    "continental-championships",
    "ranking-series",
    "world-cup",
}

# ...and the same idea in the title, for a type word the feed changes.
A_MAJOR_NAME = re.compile(
    r"olympic|world championships?|world cup|ranking series"
    r"|european championships?|asian championships?"
    r"|pan.?american championships?|african championships?", re.I)

# Not the majors: every age group, and the amateur side-events.
A_YOUTH = re.compile(r"\bu1\d\b|\bu2[0-3]\b|under.?\d\d|cadet|junior|youth"
                     r"|veteran|school", re.I)

# The host countries the calendar names, and their zones. A code missing
# from here is a row skipped, not a row guessed at.
A_ZONE = {
    "AL": "Europe/Tirane", "AR": "America/Argentina/Buenos_Aires",
    "AT": "Europe/Vienna", "AZ": "Asia/Baku", "BA": "Europe/Sarajevo",
    "BG": "Europe/Sofia", "BR": "America/Sao_Paulo", "BY": "Europe/Minsk",
    "CA": "America/Toronto", "CH": "Europe/Zurich", "CN": "Asia/Shanghai",
    "CO": "America/Bogota", "CU": "America/Havana", "CZ": "Europe/Prague",
    "DE": "Europe/Berlin", "DK": "Europe/Copenhagen", "DZ": "Africa/Algiers",
    "EG": "Africa/Cairo", "ES": "Europe/Madrid", "FI": "Europe/Helsinki",
    "FR": "Europe/Paris", "GB": "Europe/London", "GE": "Asia/Tbilisi",
    "GR": "Europe/Athens", "HR": "Europe/Zagreb", "HU": "Europe/Budapest",
    "ID": "Asia/Jakarta", "IN": "Asia/Kolkata", "IR": "Asia/Tehran",
    "IT": "Europe/Rome", "JP": "Asia/Tokyo", "KG": "Asia/Bishkek",
    "KZ": "Asia/Almaty", "LT": "Europe/Vilnius", "MA": "Africa/Casablanca",
    "MD": "Europe/Chisinau", "MK": "Europe/Skopje", "MN": "Asia/Ulaanbaatar",
    "MX": "America/Mexico_City", "NG": "Africa/Lagos", "NO": "Europe/Oslo",
    "PA": "America/Panama", "PL": "Europe/Warsaw", "PT": "Europe/Lisbon",
    "QA": "Asia/Qatar", "RO": "Europe/Bucharest", "RS": "Europe/Belgrade",
    "RU": "Europe/Moscow", "SA": "Asia/Riyadh", "SE": "Europe/Stockholm",
    "SK": "Europe/Bratislava", "SI": "Europe/Ljubljana", "TN": "Africa/Tunis",
    "TR": "Europe/Istanbul", "UA": "Europe/Kyiv", "US": "America/New_York",
    "UZ": "Asia/Tashkent", "WS": "Pacific/Apia", "ZA": "Africa/Johannesburg",
    "AE": "Asia/Dubai", "AM": "Asia/Yerevan", "BH": "Asia/Bahrain",
    "JO": "Asia/Amman", "KW": "Asia/Kuwait", "IQ": "Asia/Baghdad",
}


def _days(row: dict) -> list[str]:
    """Every day the tournament runs, as YYYY-MM-DD."""
    start = (row.get("start_date") or "").strip()
    end = (row.get("end_date") or "").strip() or start
    if not start:
        return []
    try:
        first = datetime.strptime(start, "%Y-%m-%d").date()
        last = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError:
        return []
    if last < first:
        last = first
    out, day = [], first
    while day <= last and len(out) < 20:
        out.append(day.isoformat())
        day += timedelta(days=1)
    return out


def _is_major(row: dict) -> bool:
    name = row.get("title") or ""
    ages = row.get("ages") or ""
    if A_YOUTH.search(name) or A_YOUTH.search(ages):
        return False
    kind = (row.get("event_type") or "").strip().casefold()
    return kind in A_MAJOR_TYPE or bool(A_MAJOR_NAME.search(name))


def _channels(row: dict) -> list[str]:
    return ["UWW+"] if str(row.get("streaming_available") or "") == "1" else []


def events(session, floor: datetime, ceiling: datetime) -> list[dict]:
    """Every day of a major wrestling championship inside the window."""
    years = sorted({floor.year, ceiling.year})
    rows: list[dict] = []
    for year in years:
        try:
            got = fetch(session, f"{SOURCE}{year}")
            rows += (json.loads(got.text) or {}).get("results") or []
        except Exception as exc:                               # noqa: BLE001
            warn(f"uww.org calendar {year} is unreachable ({exc}) — the "
                 f"board keeps what the other sources gave it")

    out: list[dict] = []
    no_zone = 0
    for row in rows:
        if not _is_major(row):
            continue
        code = (row.get("country") or "").strip().upper()
        zone = A_ZONE.get(code)
        if not zone:
            no_zone += 1
            continue
        name = norm(row.get("title") or "")
        city = norm(row.get("city") or "")
        if not name:
            continue
        for day in _days(row):
            when = datetime.combine(
                datetime.strptime(day, "%Y-%m-%d").date(),
                FIRST_SESSION, ZoneInfo(zone))
            if when < floor or when >= ceiling:
                continue
            out.append({
                "start": when,
                "title": f"{name} — {city}" if city else name,
                "competition": "United World Wrestling",
                "sport": "Wrestling",
                "channels": _channels(row),
                "source": "uww",
            })

    unique, seen = [], set()
    for row in out:
        key = (row["start"], row["title"].casefold())
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    log(f"  uww: {len(unique)} wrestling championship day(s) from "
        f"{len(rows)} calendar entry(ies), {no_zone} with a host country "
        f"this reader has no zone for")
    return unique
