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

# Which of its competitions belong on the board, and the reader drew the
# line himself: "خلي المحترفين و مباريات الاردن المنتخب و بس".
#
# So two things and nothing else — the professional club game, and the
# national team. The federation publishes far more than that on the same
# page: the under-16s, the youth grades, and the first division, which is
# not professional football and which this channel does not carry. Those
# used to reach the board and sit there with "لم تُعلن القناة" beside
# them, taking rows from the matches somebody is actually looking for.
#
# PROFESSIONAL is the club game this channel holds the rights to — the
# league, the cup, the shield, the super cup. NATIONAL is the country's
# team, kept because the reader asked for it, and it deliberately gets NO
# channel: those qualifiers are sold competition by competition and land
# on beIN or elsewhere.
#
# Written WITHOUT the definite article, because Arabic puts a prefix in
# front of it: the federation writes "الدوري الأردني للمحترفين", and
# "المحترفين" is not inside "للمحترفين" — the ل joins the word and the
# match fails. The professional league, the one thing this file exists
# for, was silently dropped by that one letter.
PROFESSIONAL = re.compile(r"محترفين|كأس الأردن|درع الاتحاد|سوبر", re.I)
A_CUP = re.compile(r"كأس الأردن", re.I)
NATIONAL = re.compile(r"تصفيات|كأس آسيا|كأس العرب|كأس العالم|منتخب", re.I)
# No definite article in any stem, and that is not a style choice. Arabic
# glues its prefixes: the page writes "كأس الأردن للأشبال", and "الأشبال"
# is not inside "للأشبال" — ل + ل + أشبال. The same trap had already cost
# a build once, when "المحترفين" never matched "للمحترفين" and the league
# read as empty. Here it was worse than empty: the youth cup passed as
# senior football and was handed this channel.
A_YOUTH_GRADE = re.compile(r"\bت\s?\d{2}\b|ناشئين|أشبال|براعم"
                           r"|تحت\s?\d{2}", re.I)


# Who actually carries these. The Jordan Radio and Television
# Corporation's channel is the exclusive rights holder for the country's
# domestic football — the professional league, the cup, the super cup —
# so a fixture in one of them has a channel even though jfa.jo never
# prints one, and "لم تُعلن القناة" beside it was under-reporting a
# thing that IS known.
#
# The name is the one this repository already publishes for that channel
# in jordan_sports_epg.xml, so the board and the guide agree.
#
# NOT the national team. Its qualifiers are sold competition by
# competition and land on beIN or elsewhere, so those keep the
# placeholder until a listings page says otherwise.
# The ten clubs of the professional league, read off its own standings
# table, 2026/27.
#
# This exists because the competition heading LIES, and a reader caught it
# on a television: "عمان FC - الكرمل" was published as a professional
# league match and both of those are youth sides. So was "كفرسوم - جرش".
# Neither club is in the league, and neither match belonged anywhere near
# a board of professional football — but the heading above them on the
# federation's page said محترفين, and a filter that reads only the heading
# believes it.
#
# A LEAGUE HAS A FIXED MEMBERSHIP. That is the structural fact here, and
# it is the same kind of fact this repository leans on everywhere else: a
# channel shows one match at a time, a club plays one match at a time.
# Ten clubs play this league and no eleventh can appear in it, so a
# fixture claiming it between two clubs that are not in it is refused
# whatever its heading says.
#
# Written in the shape club_key() folds names into, so a prefix, an alef
# and a ta marbuta cannot break the match the way "للمحترفين" once did.
PRO_LEAGUE_CLUBS = (
    "رمثا", "جزيره", "حسين", "وحدات", "عربي",
    "فيصلي", "شباب الاردن", "بقعه", "سلط", "دوقره",
)


def club_key(name: str) -> str:
    """A club's name folded so two spellings of it are one string."""
    name = norm(name).casefold()
    name = (name.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
                .replace("ة", "ه").replace("ى", "ي"))
    name = re.sub(r"^ال", "", name)
    return norm(re.sub(r"\s+", " ", name))


def in_the_league(name: str) -> bool:
    """Is this one of the ten clubs that play the professional league?"""
    key = club_key(name)
    return any(club in key or key in club for club in PRO_LEAGUE_CLUBS)


JORDAN_SPORT = "الأردن الرياضية"
CARRIED_BY_JORDAN_SPORT = re.compile(r"محترفين|كأس الأردن|درع الاتحاد"
                                     r"|سوبر", re.I)


def carried_by(competition: str) -> list[str]:
    """The channel a Jordanian competition is known to be on, if any.

    An age grade is refused HERE, and not only by wanted_here, because
    the fact belongs beside the channel rather than beside the board's
    taste in fixtures. Youth football has no regular television at all:
    the federation's own YouTube carries selected ties, and this channel
    takes a final or a title decider and nothing else. So "كأس الأردن
    للناشئين" is not "كأس الأردن" with a suffix — it is a different
    broadcast arrangement, and matching the tournament's name alone put
    this channel on it. The only thing keeping that off the screen was
    wanted_here happening to run first, which is an ordering, not a
    guarantee: loosen the board's filter once to show a youth final and
    the wrong channel is printed the same day.
    """
    if A_YOUTH_GRADE.search(competition):
        return []
    if CARRIED_BY_JORDAN_SPORT.search(competition):
        return [JORDAN_SPORT]
    return []


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
    """The professional game and the national team. Nothing else.

    Asked for in those words, and the reason is what the rest of the page
    is: the age grades have no regular television at all, and the first
    division is not the professional league. Both used to reach the board
    — the first division with no channel beside it, because this channel
    does not carry it — and there are more of those fixtures than of the
    ones anybody opened the board to find.
    """
    if A_YOUTH_GRADE.search(competition):
        return False
    return bool(PROFESSIONAL.search(competition)
                or NATIONAL.search(competition))


def the_clubs_belong(competition: str, home: str, away: str) -> bool:
    """Do these two clubs actually play the competition claimed above them?

    The heading is not evidence on its own — that is what a reader
    photographing a youth match published as professional football taught
    this file. So the clubs are asked as well, and the two questions are
    different competitions:

    THE LEAGUE, THE SHIELD AND THE SUPER CUP are contested by the ten
    professional clubs and nobody else, so BOTH sides must be among them.

    THE CUP is not: it draws first-division and amateur clubs in with the
    professionals, and a tie like الوحدات against a lower side is real,
    televised, and exactly what a board should carry. So ONE professional
    club is enough — which still refuses a preliminary tie between two
    clubs from outside, the round this channel does not televise.

    The national team is judged on its competition alone; it has no club
    roster to be in.
    """
    if NATIONAL.search(competition) and not PROFESSIONAL.search(competition):
        return True
    if A_CUP.search(competition):
        return in_the_league(home) or in_the_league(away)
    return in_the_league(home) and in_the_league(away)


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
    played = adrift = unwanted = impostors = 0

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
        if not the_clubs_belong(competition, home_name, away_name):
            # Named, with the heading that claimed them, because this is
            # the heading lying and the next run should say so out loud
            # rather than leaving it to a photograph of a television.
            impostors += 1
            log(f"    not the professional game: {home_name} - {away_name}"
                f"  │ published under: {competition}")
            continue
        out.append({
            "start": start,
            "title": f"{home_name} - {away_name}",
            "competition": competition,
            "channels": carried_by(competition),
        })

    log(f"  jfa.jo: {played} already played, {adrift} with no header of "
        f"their own, {unwanted} not professional or national, "
        f"{impostors} between clubs that do not play it, "
        f"{len(out)} fixture(s) to show")
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
