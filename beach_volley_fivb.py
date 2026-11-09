#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAJOR INTERNATIONAL WOMEN'S BEACH VOLLEYBALL, from the sport's own
governing body — asked for by name ("major international Beach volleyball
for women's").

The source is FIVB's VIS service, the same one the federation's own site
reads. It answers plain XML with no key and no browser:

    GetBeachTournamentList   every tournament, its dates and its GENDER
    GetBeachMatchList        every match of one tournament, with the
                             local date, the local time and both pairs

WOMEN ONLY: the tournament list stamps Gender="1" for the women's draw,
so the half of the sport shown is the feed's own word for it and never a
guess from a title.

THE CLOCK, CAREFULLY. VIS prints a LOCAL time with no offset beside it,
which is the exact shape that once put this project an hour out. So the
zone is not guessed: the tournament's own CountryCode is read and turned
into a zone through the tz database, and a country that spans more than
one zone is SKIPPED rather than shown at a time that might be wrong. A
match with no printed time is skipped too.

NO BROADCASTER. The federation names none, so the row names none.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

from epg_lib import log, norm, warn

VIS = "https://www.fivb.org/vis2009/XmlRequest.asmx?Request="

# One zone each, so a printed local clock is unambiguous. A country not
# on this list is not shown rather than shown at a guessed hour.
ONE_ZONE = {
    "NL": "Europe/Amsterdam", "DE": "Europe/Berlin", "FR": "Europe/Paris",
    "IT": "Europe/Rome", "ES": "Europe/Madrid", "PT": "Europe/Lisbon",
    "PL": "Europe/Warsaw", "CZ": "Europe/Prague", "AT": "Europe/Vienna",
    "CH": "Europe/Zurich", "BE": "Europe/Brussels", "NO": "Europe/Oslo",
    "SE": "Europe/Stockholm", "DK": "Europe/Copenhagen", "FI": "Europe/Helsinki",
    "GR": "Europe/Athens", "TR": "Europe/Istanbul", "HU": "Europe/Budapest",
    "RO": "Europe/Bucharest", "BG": "Europe/Sofia", "HR": "Europe/Zagreb",
    "SI": "Europe/Ljubljana", "RS": "Europe/Belgrade", "SK": "Europe/Bratislava",
    "GB": "Europe/London", "IE": "Europe/Dublin", "LV": "Europe/Riga",
    "LT": "Europe/Vilnius", "EE": "Europe/Tallinn", "QA": "Asia/Qatar",
    "AE": "Asia/Dubai", "SA": "Asia/Riyadh", "BH": "Asia/Bahrain",
    "KW": "Asia/Kuwait", "OM": "Asia/Muscat", "EG": "Africa/Cairo",
    "MA": "Africa/Casablanca", "TN": "Africa/Tunis", "ZA": "Africa/Johannesburg",
    "JP": "Asia/Tokyo", "CN": "Asia/Shanghai", "SG": "Asia/Singapore",
    "TH": "Asia/Bangkok", "IN": "Asia/Kolkata", "MX": "America/Mexico_City",
    "BR": "America/Sao_Paulo", "AR": "America/Argentina/Buenos_Aires",
    "CL": "America/Santiago", "PE": "America/Lima", "CO": "America/Bogota",
}

# Major and international: the world and continental championships, the
# elite tour, the Olympic and world tours. A national or age-group event
# is not what was asked for.
A_MAJOR = re.compile(
    r"world championship|wchs|world tour|elite ?16|challenge"
    r"|european championship|eurobeach|olympic|nations|world cup"
    r"|major|finals",
    re.I)

A_YOUTH = re.compile(r"\bu1[0-9]\b|\bu2[0-3]\b|youth|junior|university|test",
                     re.I)


def _ask(session, request: str) -> str:
    got = session.get(VIS + quote(request), timeout=40)
    got.raise_for_status()
    return got.text


def _attributes(xml: str, tag: str) -> list[dict]:
    return [dict(re.findall(r'(\w+)="([^"]*)"', piece))
            for piece in re.findall(rf"<{tag}\b([^>]*)/?>", xml)]


def events(session, floor: datetime, ceiling: datetime) -> list[dict]:
    """Every women's match of a major beach tournament inside the window."""
    first = floor.date().isoformat()
    last = ceiling.date().isoformat()
    try:
        listing = _ask(session,
                       '<Request Type="GetBeachTournamentList" '
                       'Fields="No Title StartDateMainDraw EndDateMainDraw '
                       'Gender CountryCode">'
                       f'<Filter FirstDate="{first}" LastDate="{last}"/>'
                       "</Request>")
    except Exception as exc:                                   # noqa: BLE001
        warn(f"fivb beach is unreachable ({exc}) — the board keeps the rest")
        return []

    out: list[dict] = []
    for tournament in _attributes(listing, "BeachTournament"):
        if tournament.get("Gender") != "1":          # women's draw only
            continue
        title = norm(tournament.get("Title", ""))
        if A_YOUTH.search(title) or not A_MAJOR.search(title):
            continue
        zone_name = ONE_ZONE.get((tournament.get("CountryCode") or "").upper())
        if not zone_name:
            continue
        zone = ZoneInfo(zone_name)
        try:
            matches = _ask(session,
                           '<Request Type="GetBeachMatchList" '
                           'Fields="No LocalDate LocalTime TeamAName '
                           'TeamBName">'
                           f'<Filter NoTournament="{tournament["No"]}"/>'
                           "</Request>")
        except Exception as exc:                               # noqa: BLE001
            warn(f"fivb beach matches unreachable ({exc})")
            continue

        for match in _attributes(matches, "BeachMatch"):
            day, clock = match.get("LocalDate", ""), match.get("LocalTime", "")
            home, away = norm(match.get("TeamAName", "")), norm(
                match.get("TeamBName", ""))
            if not (day and clock and home and away):
                continue
            try:
                start = datetime.fromisoformat(f"{day}T{clock}").replace(
                    tzinfo=zone).astimezone(timezone.utc)
            except ValueError:
                continue
            if not floor <= start < ceiling:
                continue
            out.append({
                "start": start,
                "title": f"{home} vs {away}",
                "competition": title,
                "sport": "Beach Volleyball",
                "channels": [],
                "source": "fivb",
            })

    log(f"  fivb beach: {len(out)} women's match(es) of a major tournament")
    return out
