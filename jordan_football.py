#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The Jordan Football Association's own fixtures — the league nobody else has.

Asked for repeatedly, and absent from every general source. Measured, not
assumed: livefootballtv offered 97 fixtures, live-footballontv 54,
yallakora 36, livesoccertv 79 and kooora 6 — 272 between them, and not
one Jordanian. This repository's own jordan_sports_epg.xml holds 31
programmes and no fixture at all, being 27 copies of "الأردن الرياضية"
and a talk show.

Eight Jordan-specific candidates were then asked. soccerway answers but
renders in a browser, besoccer refuses with a 406, flashscore and
livesoccertv's Jordan page 404, worldfootball never replied. The
federation answers, and it publishes its own league.

The block is named on the page — "المباريات القادمة" — and a row is:

    <tr>
      <td>… competition …</td>
      <td><span class="haly1">2026-09-03</span></td>
      <td><span class="haly1">|&nbsp;19:00</span></td>
      <td><span class="team1">البقعة</span></td>
      <td><span class="rrresult">VS</span></td>
      <td><span class="team2">دوقرة</span></td>
    </tr>

Two things make this safe to read.

THE DATE IS ALREADY A DATE. It is written 2026-09-03, so there is no day
to infer from a divider and no ordering to trust — the fault that once
stamped 1876 fixtures with a single date cannot happen here.

"VS" IS THE FIXTURE, A SCORE IS NOT. The same markup carries finished
matches, where rrresult holds "1 - 0" instead. A finished match
published as an upcoming one would put a match on the screen that has
already been played, so a row is refused unless rrresult is VS.

The clock is Amman's. That is an assumption and it is named as one — but
it is the narrow kind: a national federation publishing its own domestic
league in its own country's time, not a global site rendering for
whoever asked. Everything else here is read off the page.

This NAMES NO CHANNEL, and that is fine now: a fixture is worth showing
before anybody has said where to watch it. It reaches the board with
"لم تُعلن القناة" beside it and picks up a channel from any later pass
that learns one.
"""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from epg_lib import fetch, log, norm, warn

SOURCE = "https://jfa.jo/"

# Amman. Named as the one assumption in this file.
AMMAN = ZoneInfo("Asia/Amman")

A_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
A_CLOCK = re.compile(r"(\d{1,2}):(\d{2})")

# What the federation writes between two clubs when the match has not
# been played. Anything else in that cell is a score.
NOT_PLAYED_YET = re.compile(r"^\s*(?:VS|vs\.?|ضد)\s*$", re.I)

# Which of its competitions belong on a guide of today's football. The
# federation publishes its under-16 league beside the senior one, and a
# board that fits twelve rows should not spend them on schools.
# Written WITHOUT the definite article, because Arabic puts a prefix in
# front of it: the federation writes "الدوري الأردني للمحترفين", and
# "المحترفين" is not inside "للمحترفين" — the ل joins the word and the
# match fails. The professional league, the one thing this file exists
# for, was silently dropped by that one letter.
SENIOR = re.compile(r"محترفين|كأس الأردن|درع الاتحاد|درجة الأولى"
                    r"|سوبر|كأس آسيا|كأس العرب|تصفيات", re.I)
A_YOUTH_GRADE = re.compile(r"\bت\s?\d{2}\b|الناشئين|الأشبال|البراعم"
                           r"|تحت\s?\d{2}", re.I)


def a_day_and_a_clock(row) -> datetime | None:
    """The kickoff, from the date and the time this row prints.

    Read from the ROW's whole text rather than span by span. The
    federation puts both inside one span.haly1 — "2026-09-03" and
    "|\u00a017:00" are separate text nodes of the same element — and
    code that took the first span as the date and the NEXT as the time
    found a date, never found a clock, and threw the row away. Ten of the
    ten upcoming fixtures were lost that way, silently, because a fixture
    that fails to parse looks exactly like a fixture that is not there.

    A row's text cannot confuse the two: a date here has no colon and a
    clock has nothing else that looks like one — a score is written
    "1 - 0".
    """
    text = row.get_text(" ", strip=True)
    day, clock = A_DATE.search(text), A_CLOCK.search(text)
    if day is None or clock is None:
        return None
    try:
        return datetime(int(day.group(1)), int(day.group(2)),
                        int(day.group(3)), int(clock.group(1)),
                        int(clock.group(2)), tzinfo=AMMAN)
    except ValueError:
        return None


def competition_of(row) -> str:
    """The competition, which the federation prints in the row's first cell."""
    cells = row.find_all("td")
    for cell in cells[:2]:
        text = norm(cell.get_text(" ", strip=True))
        if text and not A_DATE.search(text) and not A_CLOCK.search(text):
            return text
    return ""


def wanted_here(competition: str) -> bool:
    """Senior football only — the under-16 league is not what a board is for."""
    if A_YOUTH_GRADE.search(competition):
        return False
    return bool(SENIOR.search(competition))


def collect(html: str) -> list[dict]:
    """Every upcoming Jordanian fixture the federation publishes."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    out: list[dict] = []
    rows = [row for row in soup.find_all("tr")
            if row.select_one("span.team1") and row.select_one("span.team2")]
    played, youth = 0, 0
    for row in rows:
        verdict = row.select_one("span.rrresult")
        if verdict is None or not NOT_PLAYED_YET.match(
                norm(verdict.get_text(" ", strip=True))):
            played += 1
            continue
        start = a_day_and_a_clock(row)
        home = norm(row.select_one("span.team1").get_text(" ", strip=True))
        away = norm(row.select_one("span.team2").get_text(" ", strip=True))
        if start is None or not home or not away:
            continue
        competition = competition_of(row)
        if not wanted_here(competition):
            youth += 1
            continue
        out.append({
            "start": start,
            "title": f"{home} - {away}",
            "competition": competition,
            "channels": [],
        })

    log(f"  jfa.jo: {len(rows)} row(s), {played} already played, "
        f"{youth} youth, {len(out)} fixture(s) to show")
    return out


def fetch_events(session, floor: datetime, ceiling: datetime) -> list[dict]:
    """The fixtures inside the guide's window, or none if the site is down."""
    try:
        everything = collect(fetch(session, SOURCE).text)
    except Exception as exc:                                  # noqa: BLE001
        warn(f"jfa.jo is unreachable ({exc}) — the board keeps the "
             f"fixtures the other sources gave it")
        return []
    inside = [event for event in everything
              if floor <= event["start"] < ceiling]
    log(f"  jfa.jo: {len(inside)} inside the window")
    return inside
