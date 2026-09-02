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


def a_day_and_a_clock(header) -> datetime | None:
    """The kickoff, from the header row that introduces a fixture.

    The row prints "2026-09-03  | 19:00" with an icon between the two, so
    both are searched for in the row's text rather than taken span by
    span or by position. Nothing here can be mistaken for the other: a
    date carries no colon, and a score is written "1 - 0".
    """
    text = header.get_text(" ", strip=True)
    day, clock = A_DATE.search(text), A_CLOCK.search(text)
    if day is None or clock is None:
        return None
    try:
        return datetime(int(day.group(1)), int(day.group(2)),
                        int(day.group(3)), int(clock.group(1)),
                        int(clock.group(2)), tzinfo=AMMAN)
    except ValueError:
        return None


def competition_of(header) -> str:
    """The competition, and the age grade when the federation adds one.

    Both are needed: "تصفيات كأس آسيا" alone reads as a senior
    qualifier, and it is span.haly2 beside it — "منتخب الشباب ت20" —
    that says it is the under-20s.
    """
    return norm(" ".join(
        norm(span.get_text(" ", strip=True))
        for span in header.select("span.haly, span.haly2")))


def wanted_here(competition: str) -> bool:
    """Senior football only — the under-16 league is not what a board is for.

    The federation publishes its schools competitions beside the senior
    ones and there are more of them, so a board that fits twelve rows
    would spend them on under-16s.
    """
    if A_YOUTH_GRADE.search(competition):
        return False
    return bool(SENIOR.search(competition))


def collect(html: str) -> list[dict]:
    """Every upcoming Jordanian fixture the federation publishes.

    The shape, read off the served page rather than guessed at — which
    took four wrong guesses to stop doing:

        <tr><td colspan=5>
            <span class="haly">الدوري الأردني للمحترفين - CFI</span>
            <span class="haly1">2026-09-03 | 19:00</span>
        </td></tr>
        <tr>
            <td><span class="team1">البقعة</span></td>
            <td><span class="rrresult">VS</span></td>
            <td><span class="team2">دوقرة</span></td>
        </tr>
        <tr><td colspan=5 height=2></td></tr>      ← a rule, then repeat

    A header, then its clubs, then a separator. The pairing is by
    POSITION, which is the arrangement that once stamped 1876 fixtures
    with a single date — so the guard is that a header is CONSUMED by the
    clubs that follow it. A row of clubs with no header of its own finds
    nothing waiting and is refused; it can never inherit the time of the
    match above. Every fixture here carries its own header, including
    repeats of the same competition, so nothing legitimate is lost.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    out: list[dict] = []
    waiting: tuple[str, datetime] | None = None
    played = adrift = unwanted = 0

    for row in soup.find_all("tr"):
        if row.select_one("span.haly1"):
            start = a_day_and_a_clock(row)
            waiting = ((competition_of(row), start)
                       if start is not None else None)
            continue

        home = row.select_one("span.team1")
        away = row.select_one("span.team2")
        if home is None or away is None:
            continue

        # Whatever happens next, this header is spent.
        header, waiting = waiting, None

        verdict = row.select_one("span.rrresult")
        if verdict is None or not NOT_PLAYED_YET.match(
                norm(verdict.get_text(" ", strip=True))):
            played += 1
            continue
        if header is None:
            adrift += 1
            continue
        competition, start = header
        if not wanted_here(competition):
            unwanted += 1
            continue
        home_name = norm(home.get_text(" ", strip=True))
        away_name = norm(away.get_text(" ", strip=True))
        if not home_name or not away_name:
            adrift += 1
            continue
        out.append({
            "start": start,
            "title": f"{home_name} - {away_name}",
            "competition": competition,
            "channels": [],
        })

    log(f"  jfa.jo: {played} already played, {adrift} with no header of "
        f"their own, {unwanted} not senior, {len(out)} fixture(s) to show")
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
