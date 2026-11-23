#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fútbol en la TV's grid, read for handball, volleyball and futsal.

WHY A SPANISH GRID BESIDE THE TURKISH ONE. Spor Ekranı serves one day —
the date is applied in the browser, so its /day/ links all return the
same rows — and a World Cup runs a fortnight. This grid prints a DATE
HEADER above each block, so the same read reaches every day the board
shows, and it names the broadcaster IN THE ROW, which is the one thing
the federation feeds behind it cannot give.

Measured against the others asked for (probes run before this file):

    tv-sport.de, tvsportguide     no such host any more
    sportowefakty (Poland)        404 on both transmisje paths
    programme-tv.net (France)     404 on its sport programme path
    tvkampen (Norway)             answers, but its schedule is drawn in
                                  the browser: two <time> in half a
                                  megabyte, no table row at all

Fútbol en la TV answers with 286 handball rows, 473 futsal and a
volleyball page, each one carrying:

    td.hora                clock, Madrid's
    td.detalles label      the competition
    td.local / td.visitante  the two sides
    td.canales li          THE BROADCASTERS, all of them

THE CLOCK IS MADRID'S and is read from the tz database, never written
down as a number, so the hour stays right across a daylight-saving
change. The date comes from the block header above the row, not from
today, so a Saturday row is not published on Wednesday.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from epg_lib import fetch, log, norm, warn

BASE = "https://www.futbolenlatv.es/deporte/"

MADRID = ZoneInfo("Europe/Madrid")

# The page tells us the sport by which page it is; nothing is guessed
# from a title.
PAGES = {
    "balonmano": "Handball",
    "voleibol": "Volleyball",
    "futbol-sala": "Futsal",
}

# MAJOR AND INTERNATIONAL, in this site's own Spanish and in the English
# some of its competition names keep. Everything else these pages carry
# is a club league — the ASOBAL, the Liga Prime, the Champions League —
# and none of it was asked for.
A_MAJOR = re.compile(
    r"campeonato de europa|campeonato del mundo|campeonato mundial"
    r"|mundial|eurocopa|europeo"
    r"|liga de naciones|nations league"
    r"|juegos ol[ií]mpicos|olimp|olympic"
    r"|copa del mundo|world cup|world championship"
    r"|european championship|euro\b"
    r"|clasificaci[óo]n para|clasificatorio",
    re.I)

# WHOSE COMPETITION. Spanish names the side outright. The reader asked
# for the WOMEN'S volleyball and the MEN'S handball; futsal was asked
# for as a major international with no side named, so both are kept
# there. A volleyball or handball row naming neither side is refused
# rather than placed in one by guess.
FEM = re.compile(r"femenin|women", re.I)
MASC = re.compile(r"masculin|men\b", re.I)

SIDE = {"Volleyball": FEM, "Handball": MASC, "Futsal": None}

# A friendly is not a major, whatever else the line says.
A_FRIENDLY = re.compile(r"amistoso|friendly", re.I)

DAY = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def _title(cell) -> str:
    if not cell:
        return ""
    span = cell.find("span")
    return norm(span.get("title") or span.get_text(" ", strip=True)) if span \
        else norm(cell.get_text(" ", strip=True))


def collect(html: str, sport: str) -> list[dict]:
    """Every row of one sport's page that is a major international."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    date = None
    seen = not_major = wrong_side = no_channel = 0

    for row in soup.select("tr"):
        classes = row.get("class") or []
        if "cabeceraTabla" in classes:
            found = DAY.search(row.get_text(" ", strip=True))
            date = (int(found.group(3)), int(found.group(2)),
                    int(found.group(1))) if found else None
            continue
        clock = row.select_one("td.hora")
        if not clock or date is None:
            continue
        seen += 1

        label = row.select_one("td.detalles label")
        comp = norm(label.get("title") or label.get_text(strip=True)) \
            if label else ""
        stage = ""
        extra = row.select_one("td.detalles span span")
        if extra:
            stage = norm(extra.get_text(strip=True))

        if A_FRIENDLY.search(comp) or not A_MAJOR.search(comp):
            not_major += 1
            continue
        side = SIDE[sport]
        if side is not None and not side.search(f"{comp} {stage}"):
            wrong_side += 1
            continue

        channels = []
        for item in row.select("td.canales li"):
            name = norm(item.get("title") or item.get_text(strip=True))
            if name and name not in channels:
                channels.append(name)
        if not channels:
            no_channel += 1
            continue

        home = _title(row.select_one("td.local"))
        away = _title(row.select_one("td.visitante"))
        title = f"{home} - {away}" if home and away else comp

        stamp = re.match(r"^([01]?\d|2[0-3])[:.]([0-5]\d)$",
                         norm(clock.get_text(strip=True)))
        if not stamp:
            continue
        start = datetime(date[0], date[1], date[2], int(stamp.group(1)),
                         int(stamp.group(2)), tzinfo=MADRID)

        out.append({
            "start": start.astimezone(timezone.utc),
            "title": title,
            "competition": comp,
            "sport": sport,
            "channels": channels,
            "source": "futbolenlatv",
        })

    log(f"  futbolenlatv {sport}: {seen} row(s), {not_major} not a major, "
        f"{wrong_side} the other side of the sport, {no_channel} with no "
        f"broadcaster, {len(out)} kept")
    return out


def events(session) -> list[dict]:
    """The grid's major internationals across the three sports, or nothing."""
    out: list[dict] = []
    for page, sport in PAGES.items():
        try:
            got = fetch(session, BASE + page)
            if (got.encoding or "").lower() in ("", "iso-8859-1", "latin-1"):
                got.encoding = "utf-8"
            out += collect(got.text, sport)
        except Exception as exc:                                   # noqa: BLE001
            warn(f"futbolenlatv {page} is unreachable ({exc}) — the board "
                 f"keeps what the other sources gave it")
    return out
