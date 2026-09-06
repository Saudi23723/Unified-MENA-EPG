#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""رياضات اليوم — the board for everything that is not football.

The football board answers "what match is on and where". This one answers
the same question for the sports it has no room for, and the reader named
them and put them in an order:

    F1, darts (the Premier League FIRST), boxing, MMA worldwide, MotoGP,
    tennis, NFL, NBA, FIBA, golf, the Rugby World Cup, padel — the big
    competitions only — and other events that matter.

THE ORDER IS THE READER'S, so it is the order rows appear in, not a
sorting by clock. Within one sport the clock decides, because two boxing
bouts on a Saturday are read in the order they happen.

WHERE THE ROWS COME FROM, and every one of them names a channel somebody
published:

    wheresthematch    F1, MotoGP, boxing, MMA, tennis, golf, darts and
                      the Rugby World Cup — Sky Sports, TNT, DAZN, BBC,
                      ITV, Premier Sports.
    nfl.com           the NFL, with NBC, FOX, CBS, ESPN and Netflix.

NINE OTHER SOURCES WERE ASKED AND ARE SHUT. That belongs here rather than
in a note nobody reads, because the next person to wonder "why not just
use pdc.tv" deserves the answer: pdc.tv lists 45 darts events and
motogp.com 878 MotoGP ones, and NEITHER NAMES A BROADCASTER. A calendar
is not a listing. livesportsontv, tsn.ca, sportsnet.ca, cbc.ca, nba.com
and livesportontv either assemble their schedule in a browser or name no
channel at all; tvsportguide refused the connection and sportsmediawatch
answered 404.

So this board carries no NBA yet and no Canadian channel yet, and says so
by simply not having them, rather than by inventing either.
"""
from __future__ import annotations

import io
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from PIL import Image

import american_sport_on_tv
import dubai_time
import espn_fights
import own_guides
import pbc
import real_american_freestyle
import sky_epg
import sports_media_watch
import sportsnet
import tapology
import tsn
import world_sport_on_tv
from epg_lib import (
    MATCH_ON_AIR, add_programme, arabic_count, drop_simulcasts, log,
    new_session, norm, warn, write_xml_atomic,
)
# The first board's channel manners, borrowed rather than copied. A reader
# looked at the two screens side by side and asked why this one still said
# "Sky Sports Main Event" where the other said "Sky Main Event" — and the
# answer was that this one printed whatever the source handed it, in
# whatever order the source handed it. Same rules now, from the same
# functions, so the two boards cannot drift apart in how they name a
# channel.
from today_matches_epg import in_the_readers_order as channels_in_order
from today_matches_epg import shorter

OUTPUT = "other_sports_epg.xml"

# The words a backup source uses when a card has no televising
# broadcaster — the honest "PPV" and its kin, which a listings page's
# real channel name never is. A row whose channels are only these is a
# row still waiting to be confirmed onto a channel, and where another
# row already sits at its minute, the other row is the broadcast.
PPV_WORDS = frozenset({"PPV", "PPV (Internet)", "Internet PPV"})
CHANNEL_ID = "TodaySports"
CHANNEL_AR = "رياضات اليوم"

# Its OWN mark, which it did not have. It wore the first board's for one
# afternoon and a reader saw the same picture on two channels — a logo is
# how a channel is found in a list, so two channels wearing one is two
# channels nobody can tell apart. Same shape as the first, so they read
# as a pair; its own name and its own colour, so they are not each other.
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/other_sports.png")

BOARD_DIR = "boards"
BOARD_URL = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
             "main/boards")

# THE SECOND CLOCK'S OUTPUTS — same events, same drawing, every time
# printed in the Gulf's (Asia/Dubai), asked for as a second link set.
#
# A FRESH BOARD STEM, not an extension of the first's, because the
# encoder owns its segments by prefix: a board whose name begins with
# other_sports_ rides the first clock's reel whatever its suffix says.
# A stem of its own is a screen of its own, encoded and published on
# its own link.
BOARD_PREFIX = "other_sports_"
DUBAI_OUTPUT = "dubai_sports_epg.xml"
DUBAI_CHANNEL_ID = "TodaySportsDubai"
DUBAI_BOARD_PREFIX = "dubai_sports_"
BOARD_COLOURS = 64
# EIGHT ROWS, and a day with more of them becomes two boards, or three.
#
# Asked for outright — "ما تعجق الصورة … بتنقسم على صفحتين ورا بعض عادي".
# It was twelve here and nine on the football board, and both were chosen
# when a row was one line. A row is two now: the event's name across the
# whole width, and its competition and channels underneath. Twelve of
# those in 720 pixels leaves each 43px, which is under the 46 a
# comfortable pair needs — so the board that was asked to say MORE was
# quietly saying it smaller.
#
# Eight leaves every row its full 62px, which is the height the drawing
# was designed around, so no row is ever squeezed and no name is ever
# shrunk for want of a page. The cost is another board in the loop —
# twenty seconds more before a viewer sees a given match come round — and
# that is the trade that was asked for, in those words.
MAX_ON_BOARD = 8

UTC = timezone.utc
VIEWER = ZoneInfo("America/Los_Angeles")
VIEWER_NAME = "بتوقيتك"
ARABIC_DAY = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس",
              "الجمعة", "السبت", "الأحد")

# FOUR DAYS, ROLLING, asked for in the reader's own words — "make
# schadule every 4 days" — and the build that reads this runs every ten
# minutes, so no edge of the window is ever more than ten minutes stale:
# today plus three, every card on the board days away instead of weeks,
# and the far Saturday arriving the morning it becomes one of the four.
#
# Fourteen was the reach this board carried once, and reach was the
# whole point then — a three-day window had ended before a single
# Saturday card, and nothing was ever being looked at. But reach stopped
# being the ask: a SCHEDULE was, a rolling one, refreshed from every
# source on every pass — and four days is denser, fresher, and honest
# about what a viewer can actually plan for.
#
# A day with nothing on it is not drawn (see build), and a four-day
# window is four days of DENSITY, not four empty boards.
DAYS_AHEAD = 4

# The reader's order, and the mark each sport wears on the board. A sport
# absent from here cannot reach the board at all, which is what "the big
# competitions only" means in practice.
#
# The four after Padel were asked for in the reader's own words — "Major
# CYCLING, MARATHONS", "Triathlon, Olympics or similar", "Major women's
# international VOLLEYBALL with broadcast channels", athletics with its
# world championships — and they join at the end of the order rather than
# anywhere inside it, because the twelve above were asked for first and in
# this order. Snooker was once on this list too and came off it with the
# whole sport, and baseball's MLB came on with "Add Yankees, Dodgers
# games (MLB)" and came back off the same way — "its a mess, remove
# snooker & MLB from channel 2". Inside a day the clock rules anyway and
# the sport only breaks a tie.
IN_ORDER = (
    "F1", "Darts", "Boxing", "MMA", "MotoGP", "Tennis",
    "NFL", "NBA", "FIBA", "Golf", "Rugby", "Padel",
    "Cycling", "Athletics", "Volleyball", "Triathlon",
)
RANK = {sport: place for place, sport in enumerate(IN_ORDER)}


def start_of_day(day: date) -> datetime:
    return datetime.combine(day, time(0, 0), VIEWER).astimezone(UTC)


def days_of(now: datetime) -> list[date]:
    first = now.astimezone(VIEWER).date()
    return [first + timedelta(days=n) for n in range(DAYS_AHEAD)]


def day_bounds(day: date) -> tuple[datetime, datetime]:
    return start_of_day(day), start_of_day(day + timedelta(days=1))


def wanted(event: dict) -> bool:
    """Only the sports asked for, and only ones that name a channel.

    The second half is the rule every board here obeys: an event with no
    published broadcaster is not shown, because the one thing this screen
    must never do is put a viewer on a channel that is not carrying it.
    """
    return event.get("sport") in RANK and bool(event.get("channels"))


def in_the_readers_order(events: list[dict]) -> list[dict]:
    """A day, in the order a day happens: by the clock.

    It used to sort by SPORT first — F1, then darts, then boxing, then
    MMA — and a reader photographed what that reaches a screen as:

        03:30  Italian Grand Prix Practice 1
        07:00  Italian Grand Prix Practice 2
        17:00  Live Boxing Ruiz vs Knyba
        10:30  بطولة RFC
        18:00  One Championship One Fight Night 47
        08:00  US Open 3rd Round

    Three-thirty, seven, five in the afternoon, half past ten in the
    morning. Every row correct and the list unreadable, because a board
    of a DAY is read down the clock and nothing else.

    The order of sports was asked for and it still decides — but it
    decides what this board CARRIES, which is what RANK is for: a sport
    not in it never arrives. Inside a day the clock rules, and the sport
    breaks a tie only when two things start on the same minute, so that
    at 16:00 the grand prix comes before the tennis rather than landing
    in whichever order the source happened to hand them over.
    """
    return sorted(events, key=lambda e: (e["start"], RANK[e["sport"]]))


def row_title(event: dict) -> str:
    """What one row says. No emoji, and that is the point.

    Each row used to open with its sport as an emoji — 🏁 for F1, 🥊 for
    boxing, 🏀 for basketball. A reader photographed the result: every
    row on the television began with an empty rectangle, because the
    player's font carries no glyph for any of them and draws the
    missing-character box instead. Twelve rows, twelve boxes.

    This is not fixable from here. What a player prints is chosen by the
    player's own font, on the reader's own device, and this guide hands
    it text. An emoji is a bet that the far end has a face for it, and
    that bet was lost — visibly, on every row at once.

    So the rows say their event and nothing else. Nothing is lost: the
    board is already ordered by sport, so the sports arrive in blocks,
    and every title names its own — "Italian Grand Prix Practice 2",
    "Live Boxing Ruiz vs Knyba", "US Open Men's Singles". The mark was
    decoration standing where the name already was.

    IN_ORDER still holds the reader's order of sports. That was always
    its real job; the emoji were only ever riding along with it.
    """
    return norm(event["title"])


def day_title(day: date, events: list[dict], now: datetime) -> str:
    if not events:
        return f"{CHANNEL_AR} — لا يوجد حدث"
    return f"{CHANNEL_AR} — " + arabic_count(
        len(events), "حدث", "حدثان", "أحداث", "حدثاً")


def day_page(day: date, events: list[dict], now: datetime) -> str:
    lines = [f"{CHANNEL_AR} · {ARABIC_DAY[day.weekday()]} {day:%d.%m.%Y}", ""]
    for event in events:
        when = event["start"].astimezone(VIEWER)
        channels = " · ".join(event["channels"][:3])
        lines.append(f"{when:%H:%M}  {row_title(event)}")
        lines.append(f"        {channels}")
    if not events:
        lines.append("لا يوجد حدث من الرياضات المتابَعة في هذا اليوم.")
    return "\n".join(lines)


def publish_board(index: int, day: date, events: list[dict], now: datetime,
                  *, page: int = 1, pages: int = 1) -> str | None:
    """Draw one board, keep it only if the bytes differ, return its URL."""
    name = f"{BOARD_PREFIX}{index}.png"
    path = os.path.join(BOARD_DIR, name)
    try:
        from match_board import draw_board

        drawn_rows = [dict(event, title=row_title(event)) for event in events]
        board = draw_board(
            day, drawn_rows, now, VIEWER, MATCH_ON_AIR,
            title=CHANNEL_AR, subtitle=f"سباقات ونزالات وبطولات · {VIEWER_NAME}",
            weekday=ARABIC_DAY[day.weekday()], page=page, pages=pages,
            accent=(167, 139, 250, 255))
        buffer = io.BytesIO()
        board.convert("RGB").convert(
            "P", palette=Image.ADAPTIVE, colors=BOARD_COLOURS).save(
                buffer, format="PNG", optimize=True)
        fresh = buffer.getvalue()
    except Exception as exc:                                  # noqa: BLE001
        warn(f"the board for {day} could not be drawn ({exc}) — the day "
             f"still publishes as text")
        return f"{BOARD_URL}/{name}" if os.path.exists(path) else None

    os.makedirs(BOARD_DIR, exist_ok=True)
    if not os.path.exists(path) or open(path, "rb").read() != fresh:
        with open(path, "wb") as out:
            out.write(fresh)
        log(f"  board {name} redrawn ({len(fresh) // 1024} KB)")
    return f"{BOARD_URL}/{name}"


# WHICH PART OF A CARD A ROW IS. An early prelim, a prelim and a main
# card are three broadcasts of one night and a reader asked for all
# three by name, so two rows are never folded together when one names a
# segment the other does not — however alike their titles look.
A_CARD_SEGMENT = re.compile(r"early\s*prelims?|\bprelims?\b|main\s*card", re.I)


def a_bare_title(title: str) -> str:
    """A title with only what two sources would spell the same way left."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", title.lower())).strip()


def a_card_segment(title: str) -> str:
    """"prelims", "main card" or "" — which broadcast of the night."""
    found = A_CARD_SEGMENT.search(title)
    return re.sub(r"\s+", " ", found.group(0).lower()) if found else ""



def _the_broadcaster_names_it(event: dict, into: dict) -> bool:
    """Whether `event` is the broadcaster’s own row for `into`’s broadcast.

    Sky’s guide titles are the programme itself: “UFC Fight Night”,
    “Live Boxing”, with no “Action from …” wording — that lives in the
    synopsis. A listings page enriches the same broadcast with fighters
    and venues, and enrichment is what the fold used to keep. So the row
    whose title is a PREFIX of the other’s, arriving second at the same
    minute on a channel in common, is the broadcaster’s, and its title
    replaces the page’s.
    """
    theirs = a_bare_title(into["title"])
    mine = a_bare_title(event["title"])
    return bool(theirs) and bool(mine) and theirs.startswith(mine)


# A programme about the game is not the game, and two clubs named in
# its title do not make it one. "Braves vs Phillies - Extended
# Highlights" names the same two clubs as the ninth inning does, and
# only the word in the middle tells them apart. The majors the rule was
# measured on are off the board now — "remove snooker & MLB from
# channel 2" — and the thirty-club table and the two-sides fold that
# matched one ballgame across four sources' spellings went with them.
# The guard stays because it is shared: tennis, F1 and UFC folds below
# ask it the same question — is this a programme about the event rather
# than the event — and they were never about the clubs.
A_HIGHLIGHTS = re.compile(r"highlights|preview|review|weekly|daily|"
                          r"recap|best of|plays of the (?:week|day)",
                          re.I)

def _a_bare_title_match(one: str, two: str) -> bool:
    """One bare title a prefix of the other — the fold's own test."""
    mine, yours = a_bare_title(one), a_bare_title(two)
    return mine.startswith(yours) or yours.startswith(mine)


# ─── One event, two wordings ───────────────────────────────────────────
#
# "check channel 2 there are too many mistakes ! and duplications" — and
# the duplications that survived the fold above were measured, row by
# row, on the board this build printed. Every one of them is TWO
# SOURCES NAMING ONE BROADCAST WITH WORDINGS THE PREFIX TEST CANNOT SEE:
#
#     08:00  US Open Men's & Women's Singles Round of 16, Men's &      beIN 7 · Sky Tennis · Sky+
#            Women's Doubles 2nd Round
#     08:00  2026 US Open Tennis: Round of 16                           beIN 7 · TSN4 · TSN1
#
#     05:55  2026 Formula 1: Italian Grand Prix                         beIN 4K · TSN5 · TSN1
#     06:00  Italian Grand Prix Race - Monza Circuit, Monza             beIN 4K · Sky F1
#
#     12:00  UFC Fight Night - Silva vs. Delgado Prelims                Sportsnet 360
#     12:00  UFC Fight Night Prelims                                    TNT 2
#
# Same broadcast, same minute (the grand prix five minutes apart), a
# channel in common on the tennis pair — and not one of the six titles
# is a prefix of its twin, because the two wordings put their words in
# different orders. The fold's own answer is the one it already gives
# baseball: the EVENT'S OWN IDENTITY is the test there (the two clubs),
# and identity is the test here. A grand prix is its name and its
# session; a major is its name and its day's rounds; a UFC night is its
# card's own name and its part of the night. The identity is read with
# the competition's own words, the same regexes own_guides already uses
# to find a channel by name — nothing new is invented, and a wording
# that disagrees about the identity (Practice 1 against Practice 2, a
# men's semifinal against a women's, one card against another) is a
# disagreement the fold obeys.
#
# The identity folds are FALLBACKS: they run only where the structural
# fold above found nothing, so every pair the prefix test already folds
# keeps the title rules it has. And a row folded by identity keeps the
# LONGER title, because identity folds join two broadcasters' own grids
# — Sportsnet's against Sky's — and neither of those outranks the other
# the way a listings page is outranked; the row that names more is the
# row a viewer reads.
A_SESSION_APART = timedelta(minutes=10)

# How far apart two listings of one tennis window may sit. Measured on
# this board: Sky printed the US Open's round of 16 at 11:00 and TSN
# printed the same window at 12:00, both on beIN 7 — an hour apart, one
# coverage window. Seventy-five minutes covers that and nothing else
# measured: a major's two semifinals sit FOUR HOURS apart under the
# same title, and the quarterfinal windows six hours apart, so the
# slack is a fraction of the nearest pair that must stay two rows.
A_TENNIS_WINDOW_APART = timedelta(minutes=75)

# THE ENCORE'S CLOCK. Measured on this board: TSN2 printed the Italian
# Grand Prix race again thirteen hours after the live one — and TSN
# printed SailGP's Great Britain Grand Prix nine hours after its first
# day, which is two LIVE sailing days that must stay two rows. So the
# encore gap is floored at ten hours, one hour past the sailing tide,
# and ceiled at three days, past which no broadcaster replays a
# session. The sailing words are refused outright, because a sailing
# title passes the F1 page's own filter and the gap alone would not
# save it; and the race weekend's own studio shows — the preview and
# the review — are refused with them, the same family tsn.py refuses.
A_GRAND_PRIX_ENCORE_FROM = timedelta(hours=10)
A_GRAND_PRIX_ENCORE_TO = timedelta(days=3)
A_SAILING_WORDS = re.compile(r"sail\s*gp|sailing", re.I)
A_STUDIO_WRAPS = re.compile(r"grand prix sunday|chequered flag", re.I)

# A studio show about the event is not the event, and identity is no
# excuse for folding one onto the coverage it talks about.
A_HIGHLIGHTS_GUARD = A_HIGHLIGHTS


def _the_grand_prix_of(title: str) -> str:
    """The grand prix a title names — own_guides' own regex, casefolded."""
    found = own_guides.A_GRAND_PRIX.search(title or "")
    return found.group(1).casefold() if found else ""


def _the_session_of(title: str) -> str:
    """The session a title names — practice, qualifying, sprint or race."""
    found = own_guides.A_SESSION.search(title or "")
    return found.group(1).casefold() if found else ""


def _the_same_race(into: dict, event: dict) -> bool:
    """One grand prix, one session — the same broadcast, worded apart.

    TSN's "2026 Formula 1: Italian Grand Prix" and the listings page's
    "Italian Grand Prix Race - Monza Circuit, Monza" are one race, and
    the session word is where a broadcaster that omits it is still
    naming the same thing: the race is the broadcast a channel titles
    with the grand prix's name alone. Two DIFFERENT sessions never fold
    — Practice 1 is not Practice 2 and neither is the race — and a
    programme about the session (a preview, a highlights reel) is
    refused before it is asked.
    """
    if into.get("sport") != "F1" or event.get("sport") != "F1":
        return False
    if (A_HIGHLIGHTS_GUARD.search(into.get("title") or "")
            or A_HIGHLIGHTS_GUARD.search(event.get("title") or "")):
        return False
    mine, yours = (_the_grand_prix_of(into["title"]),
                   _the_grand_prix_of(event["title"]))
    if not mine or mine != yours:
        return False
    a, b = _the_session_of(into["title"]), _the_session_of(event["title"])
    return a == b or not (a and b)


def _an_encore_of_the_race(into: dict, event: dict) -> bool:
    """Whether the later row is a replay of the earlier row's race.

    Measured on this board: TSN2 printed "2026 Formula 1: Italian Grand
    Prix" again thirteen hours after the live one — an encore, not a
    second race, because a grand prix weekend's one race happens once.
    The identity is the same one the session fold reads — the same
    grand prix, the same session or one worded without it — and the
    guard refuses the programmes about the session. The clock is
    A_GRAND_PRIX_ENCORE_FROM to A_GRAND_PRIX_ENCORE_TO, and the sailing
    is refused outright: SailGP prints "Great Britain Grand Prix" too,
    its days are nine hours apart, and they are LIVE days that must
    stay two rows.
    """
    if into.get("sport") != "F1" or event.get("sport") != "F1":
        return False
    for wording in (into.get("title") or "", event.get("title") or ""):
        if A_SAILING_WORDS.search(wording) or A_STUDIO_WRAPS.search(wording):
            return False
    gap = event["start"] - into["start"]
    return A_GRAND_PRIX_ENCORE_FROM <= gap <= A_GRAND_PRIX_ENCORE_TO \
        and _the_same_race(into, event)


# The day's rounds, and the draws that play them — the two things a
# major's coverage block names, and the only two things two broadcasters
# disagree about when they describe the same window of the same day.
A_TENNIS_ROUND = re.compile(
    r"early round|round of \d+|\d+(?:st|nd|rd|th) round"
    r"|quarterfinals?|semifinals?|\bfinals?\b", re.I)
A_TENNIS_DRAW = re.compile(
    r"\bmen(?:'?s)?\b|\bwomen(?:'?s)?\b|\bsingles\b|\bdoubles\b|\bmixed\b",
    re.I)


def _the_words_of(pattern, title: str) -> frozenset:
    return frozenset(found.group(0).casefold()
                     for found in pattern.finditer(title or ""))


def _the_same_tennis_window(into: dict, event: dict) -> bool:
    """One major, one day's window — the same coverage, worded apart.

    Sky titles the window by its draws ("US Open Men's & Women's Singles
    Round of 16, Men's & Women's Doubles 2nd Round"); TSN titles the
    same window "2026 US Open Tennis: Round of 16". Same major, same
    minute, and one description's rounds and draws a subset of the
    other's — that is one broadcast, and the channels join.

    What the subset rule refuses is exactly what must stay two rows: a
    men's semifinal against a women's (the draws cross), a semifinal
    against a final (the rounds cross), a doubles final against a
    singles final (both). And the minute is exact in the same-minute
    fold — a major's two semifinals are four hours apart under the SAME
    title, measured on this board, and folding those would delete a
    match; the different-minute fold's slack is A_TENNIS_WINDOW_APART,
    a fraction of that four hours.
    """
    if into.get("sport") != "Tennis" or event.get("sport") != "Tennis":
        return False
    if (A_HIGHLIGHTS_GUARD.search(into.get("title") or "")
            or A_HIGHLIGHTS_GUARD.search(event.get("title") or "")):
        return False
    mine = own_guides.A_MAJOR.search(into.get("title") or "")
    yours = own_guides.A_MAJOR.search(event.get("title") or "")
    if (not mine or not yours
            or mine.group(1).casefold() != yours.group(1).casefold()):
        return False
    for pattern in (A_TENNIS_ROUND, A_TENNIS_DRAW):
        a = _the_words_of(pattern, into.get("title") or "")
        b = _the_words_of(pattern, event.get("title") or "")
        if not (a <= b or b <= a):
            return False
    return True


# A UFC night's own name for itself — the card's family, which every
# broadcaster of it prints and nothing else does.
A_UFC_CARD = re.compile(r"\bUFC\s+(?:Fight\s+Night|\d{3})\b", re.I)


def _the_same_ufc_card(into: dict, event: dict) -> bool:
    """One card, one part of the night — the same broadcast, worded apart.

    Measured on the board: Sportsnet 360's "UFC Fight Night - Silva vs.
    Delgado" beside Sky's "UFC Fight Night", and the prelims the same
    way an hour earlier, with no channel in common because the two
    broadcasters are two countries' carriers of one card. The card's own
    family and the same part of the night are the identity — a
    "UFC 331" never folds with a "UFC Fight Night", and a prelim never
    folds with a main card, whatever the minute.
    """
    if into.get("sport") != "MMA" or event.get("sport") != "MMA":
        return False
    if (A_HIGHLIGHTS_GUARD.search(into.get("title") or "")
            or A_HIGHLIGHTS_GUARD.search(event.get("title") or "")):
        return False
    mine = A_UFC_CARD.search(into.get("title") or "")
    yours = A_UFC_CARD.search(event.get("title") or "")
    if (not mine or not yours
            or mine.group(0).casefold() != yours.group(0).casefold()):
        return False
    return a_card_segment(into.get("title") or "") \
        == a_card_segment(event.get("title") or "")


# A CARD'S OWN CLOCK, as two calendars print it. ESPN carries the
# league's own start and Tapology the promotion's, and the same card
# measured an hour apart twice in one window — the Contender Series at
# 23:00 against 00:00, Noche UFC at 18:00 against 19:00. Ninety minutes
# covers both pairs and stops short of every pair that must stay two
# rows: a UFC night's prelims sit two hours under its main card,
# measured on Sportsnet's own grid, and a card a day apart is not a
# fold at all.
A_CARD_APART = timedelta(minutes=90)

# THE MIDWEEK CARD'S OWN IDENTITY. "Dana White's Contender Series:
# Season 10, Week 5" and "Contender Series 2026: Week 5" are one
# broadcast in two spellings, and the week number is the one word both
# spell the same way.
A_CONTENDER_WEEK = re.compile(r"contender series.*?week\s*(\d+)", re.I)

# THE ONE SERIES' OWN IDENTITY, in its own card number. beIN's guide
# says "One Friday Fights - 169" and Tapology says "One Friday Fights
# 170" — same number, same card; different number, two cards a week
# apart.
A_ONE_FRIDAY = re.compile(r"one\s+friday\s+fights?\D*?(\d+)", re.I)
A_ONE_FIGHT_NIGHT = re.compile(r"one\s+fight\s+night\D*?(\d+)", re.I)

# THE HEADLINERS. "Noche UFC: Silva vs. Delgado" and "UFC Fight Night:
# Silva vs. Delgado" name the same two fighters and share no family
# word at all — the card's own two surnames are its identity, and a card
# with different headliners never folds, whatever the clock says.
A_VERSUS = re.compile(
    r"\w+(?:\s+\w+)?\s+(?:vs\.?|v)\s+\w+(?:\s+\w+)?", re.I)


# The words a card's title uses AROUND the headliners, measured on
# this board's own titles — "Live Boxing", "UFC Fight Night", "One
# Friday Fights", the segment words, the rematch digits. None of them
# is a fighter, and the pair rule below drops them from a name's side
# so that "Live Boxing Cruz vs Bravo" and "Isaac Cruz vs Nestor
# Bravo" compare as cruz/bravo against isaac cruz/nestor bravo — the
# same fight — instead of letting "boxing" sit inside a name and break
# the comparison.
AROUND_THE_NAMES = frozenset(
    "live boxing mma ufc fight fights night friday one contender series "
    "season week prelims early main card the at on of and".split())


def _the_pairs_of(title: str) -> tuple[tuple, ...]:
    """The fight(s) a title names — each side's names, per vs-pair.

    A co-main prints inside a main event's title — "Isaac Cruz vs
    Nestor Bravo, Jesus Ramos vs Meiirim Nursultanov" — and those are
    two fights, so each pair keeps its two sides apart and a pair of
    one title is compared with a pair of the other, both ways round:
    "Silva vs. Delgado" and "Delgado vs. Silva" are one fight spelled
    in two orders, and "Silva vs. Delgado" against "Silva vs.
    Pantoja" is two fights whatever the order, because a side that
    names a different opponent never matches.
    """
    pairs = []
    for found in A_VERSUS.finditer(title or ""):
        pair = found.group(0).lower()
        sides = re.split(r"\s+(?:vs\.?|v)\s+", pair)
        if len(sides) != 2:
            continue
        left = frozenset(word for word in sides[0].split()
                         if word not in AROUND_THE_NAMES
                         and not word.isdigit())
        right = frozenset(word for word in sides[1].split()
                          if word not in AROUND_THE_NAMES
                          and not word.isdigit())
        if left and right:
            pairs.append((left, right))
    return tuple(pairs)


def _the_same_fight_card(into: dict, event: dict) -> bool:
    """One card, worded apart by two calendars — the same broadcast.

    Measured on the board, twice in one window: ESPN's "Dana White's
    Contender Series: Season 10, Week 5" at 23:00 beside Tapology's
    "Contender Series 2026: Week 5" at 00:00, and ESPN's "Noche UFC:
    Silva vs. Delgado" at 18:00 beside Tapology's "UFC Fight Night:
    Silva vs. Delgado" at 19:00 — one card each, printed twice, because
    two calendars never agree about the minute and neither pair shared
    a family word the UFC fold could read.

    The identity is whatever the two spellings share: the Contender
    Series' week, ONE's own card number, the UFC family, or the two
    headliners themselves. What it never folds: two parts of one night
    (the segment rule, as everywhere), two cards two hours apart (the
    ninety minutes above), a programme about a card (the guard, as
    everywhere), and a pair whose one title is a bare prefix of the
    other — that pair is the exact-minute fold's own case, and the
    minute is this fold's to refuse, never to own.
    """
    sports = {into.get("sport"), event.get("sport")}
    if sports not in ({"MMA"}, {"Boxing"}):
        return False
    if (A_HIGHLIGHTS_GUARD.search(into.get("title") or "")
            or A_HIGHLIGHTS_GUARD.search(event.get("title") or "")):
        return False
    if a_card_segment(into.get("title") or "") \
            != a_card_segment(event.get("title") or ""):
        return False
    mine, yours = into.get("title") or "", event.get("title") or ""
    # A pair whose one title is a bare prefix of the other is the
    # exact-minute fold's own case, and this fold never takes a case
    # that fold owns. The gate's own row: "UFC Fight Night Hooker vs
    # Parnasse" a minute after a bare "UFC Fight Night", same channel —
    # a minute apart is not the same broadcast, and a fold allowed
    # ninety minutes cannot inherit a case whose whole test is the
    # minute. Only a pair that names MORE on one side is refused: two
    # spellings that bare down to the same words ("UFC Fight Night:
    # Silva vs. Delgado" beside "UFC Fight Night - Silva vs Delgado")
    # are the same card with the same name, and the ladder below still
    # reads them.
    bare_one, bare_two = a_bare_title(mine), a_bare_title(yours)
    if (bare_one != bare_two
            and (bare_one.startswith(bare_two)
                 or bare_two.startswith(bare_one))):
        return False
    weeks = (A_CONTENDER_WEEK.search(mine), A_CONTENDER_WEEK.search(yours))
    if weeks[0] and weeks[1]:
        return weeks[0].group(1) == weeks[1].group(1)
    for series in (A_ONE_FRIDAY, A_ONE_FIGHT_NIGHT):
        nums = (series.search(mine), series.search(yours))
        if nums[0] and nums[1]:
            return nums[0].group(1) == nums[1].group(1)
    if _the_same_ufc_card(into, event):
        return True
    pairs = (_the_pairs_of(mine), _the_pairs_of(yours))
    if not pairs[0] or not pairs[1]:
        return False
    for (left, right) in pairs[0]:
        for (their_left, their_right) in pairs[1]:
            # The same two sides, in either order — and a side may
            # name more of a fighter than the other does ("Cruz"
            # against "Isaac Cruz"), because a surname is a name and
            # the shorter spelling is still the same fighter.
            if ((left <= their_left or their_left <= left)
                    and (right <= their_right or their_right <= right)):
                return True
            if ((left <= their_right or their_right <= left)
                    and (right <= their_left or their_left <= right)):
                return True
    return False


def one_row_per_broadcast(events: list[dict],
                          the_backup_is: str | None = None) -> list[dict]:
    """Two sources naming one broadcast become one row.

    Reading Sky's guide beside a listings page means both now carry the
    same UFC night, and the board printed it twice:

        12:00  UFC Fight Night Dan Hooker vs Salahdine Parnasse  TNT 1 · HBO Max
        12:00  UFC Fight Night                                   TNT 1

    Board one merges by title similarity. That is the wrong tool here:
    "UFC Fight Night" and "UFC Fight Night Prelims" are more alike than
    either is to the row it belongs with, and folding those two together
    would delete the prelim a reader asked for three times over.

    So the test is structural, and every part of it has to hold:

        the same start, to the minute — not a window
        at least one channel in common
        one bare title a prefix of the other
        the same part of the card, or neither naming one
        the same sport

    A prelim and a main card cannot start at the same minute, and the
    segment rule refuses them even if a source ever said they did.

    THE TITLE THE KEEPER WEARS. The longer title won, because it was the
    one that named the fighters — until the day the longer one was
    WRONG and the shorter one was right:

        wheresthematch  UFC Fight Night Yair Rodriguez vs Jean Silva
        Sky             Live: UFC Fight Night

    Rodriguez withdrew; Jose Delgado took the bout. Sky, the BROADCASTER,
    corrected its title and its synopsis ("headlined by the featherweight
    bout between Jean Silva and Jose Miguel Delgado") while the listings
    page still carried the cancelled pairing weeks later — and the
    board printed the cancelled one, because it was longer:

        "Yair Rodriguez already fought Silva why is it on schadule"

    A broadcaster’s guide is the entity that has to air the event; a
    listings page is a copy of one. When both name the same broadcast at
    the same minute on a channel in common, the BROADCASTER’S title wins
    and the page’s is folded away — the same rule the football board
    already follows, where a source that does not carry a match does not
    get to date it.
    """
    kept: list[dict] = []
    folded = 0
    dropped_by_the_backup = 0

    # THE BACKUP'S ROW FALLS AWAY FIRST. The reader named Tapology a
    # backup — "for channel broadcast write PPV channel unless another
    # source can confirm channels" — so where any other source already
    # names the same broadcast, at the same minute, in the same sport,
    # with one bare title a prefix of the other and the same part of the
    # card, the other source's row is the broadcast and the backup's is
    # the duplicate. This runs BEFORE the fold and pays no mind to
    # channels: a PPV row beside a DAZN row shares no channel, so the
    # fold's own rule would have kept both and printed one fight twice.
    # A row the channel-confirmers below have already given a real
    # channel to is no longer only-PPV, and it stands with the rest.
    if the_backup_is:
        the_rest = [row for row in events
                    if row.get("source") != the_backup_is]
        survivors = []
        for row in events:
            if row.get("source") != the_backup_is:
                survivors.append(row)
                continue
            if set(row["channels"]) <= PPV_WORDS and any(
                    other["start"] == row["start"]
                    and other.get("sport") == row.get("sport")
                    and _a_bare_title_match(other["title"], row["title"])
                    and a_card_segment(other["title"])
                    == a_card_segment(row["title"])
                    for other in the_rest):
                dropped_by_the_backup += 1
                continue
            survivors.append(row)
        events = survivors

    for event in sorted(events, key=lambda one: (one["start"],
                                                 -len(one["title"]))):
        bare = a_bare_title(event["title"])
        segment = a_card_segment(event["title"])
        into = None
        # Set where an identity fold below is the one that matched, so
        # the keeper-title rule at the bottom knows which of its two
        # rules to apply: the broadcaster's title for a structural fold,
        # the longer one for an identity fold.
        by_identity = False

        for already in kept:
            if already["start"] != event["start"]:
                # ONE RACE, TWO CLOCKS. TSN prints the Italian Grand
                # Prix at 12:55Z; the listings page prints the same
                # race at 13:00Z — a race feed's own clock rounds, and
                # five minutes of slack — ten, to cover a feed that
                # counts the formation lap in — is shorter than any
                # session gap at a race weekend. The grand prix's own
                # name is the identity, the session word agrees or one
                # of the two wordings omits it, and a programme ABOUT
                # the session is refused by the guard inside the test.
                if (abs(already["start"] - event["start"]) <= A_SESSION_APART
                        and _the_same_race(already, event)):
                    into = already
                    by_identity = True
                    break
                # ONE MAJOR, ONE WINDOW, TWO CLOCKS. The same window
                # of a major's day can print an hour apart on two
                # broadcasters' clocks — Sky's US Open round of 16 at
                # 11:00 beside TSN's at 12:00, both on beIN 7 — and
                # A_TENNIS_WINDOW_APART is the measured slack that
                # covers the pair and stops short of every pair that
                # must stay two rows: a major's semifinals are four
                # hours apart under the same title, its quarterfinal
                # windows six. The rounds and draws are read by the
                # subset rule inside the test, and a programme ABOUT
                # the window is refused by the guard.
                if (abs(already["start"] - event["start"])
                        <= A_TENNIS_WINDOW_APART
                        and _the_same_tennis_window(already, event)):
                    into = already
                    by_identity = True
                    break
                # ONE CARD, TWO CALENDARS, TWO CLOCKS. ESPN carries the
                # league's own start and Tapology the promotion's, and
                # one card measured an hour apart twice in a single
                # window — Contender Series week 5, then Noche UFC —
                # with no family word in common for the UFC fold to
                # read. The identity is whatever the two spellings
                # share, and the clock is ninety minutes, past which
                # sit the prelim-and-main pairs that stay two rows.
                if (abs(already["start"] - event["start"])
                        <= A_CARD_APART
                        and _the_same_fight_card(already, event)):
                    into = already
                    by_identity = True
                    break
                continue
            if already.get("sport") != event.get("sport"):
                continue
            # ONE FEED, TWO CHANNELS. The channel-in-common rule was
            # written for two sources naming one broadcast, and it is
            # the right rule for them: a listings page and a
            # broadcaster's guide disagree about the channel because
            # they are two opinions, and a shared channel is the fact
            # that settles it. But a single feed that prints one
            # programme twice — "2026 US Open Tennis: Early Round
            # Coverage Day #7" on TSN1 and on TSN3, at the same minute —
            # is one broadcaster saying one thing twice, and demanding a
            # channel in common refused its own answer: the board
            # printed two rows and split the viewer's channels between
            # them, the one thing a guide must not do. Where both rows
            # come from the SAME source and say the same thing at the
            # same minute, the channels are one broadcast's, and they
            # join on the row that stays. No cross-source fold is
            # opened here — the rule below still holds for every pair a
            # source does not have in common.
            same_source = (event.get("source") and
                           event.get("source") == already.get("source"))
            if not same_source and not (
                    set(already["channels"]) & set(event["channels"])):
                # ONE CARD, TWO COUNTRIES. Measured on the board: a UFC
                # night's prelims and main card printed twice —
                # Sportsnet 360's rows naming the card's fighters
                # beside Sky's plain ones, at the same minute, with NO
                # channel in common because the two broadcasters are
                # two countries' carriers of one card. The card's own
                # family and the same part of the night are the
                # identity — and the only identity allowed to cross
                # the channel gap, because nothing else here names a
                # broadcast two carriers share with no channel in
                # common. Two different cards, or the same card's two
                # different parts, are refused by the test and stay
                # two rows exactly as before.
                if _the_same_ufc_card(already, event):
                    into = already
                    by_identity = True
                    break
                continue
            mine = a_bare_title(already["title"])
            if not (mine.startswith(bare) or bare.startswith(mine)):
                # ONE MAJOR, ONE WINDOW, TWO WORDINGS. Sky titles the
                # window by its draws; TSN titles the same window by
                # its rounds. The minute is exact — a major's two
                # semifinals are four hours apart under the SAME
                # title, and one minute's slack would fold them — and
                # the subset rule on rounds and draws is what refuses
                # the windows that are not the same one. The channels
                # were settled above: a channel in common, or the one
                # feed that printed one programme twice.
                if _the_same_tennis_window(already, event):
                    into = already
                    by_identity = True
                    break
                continue
            if a_card_segment(already["title"]) != segment:
                continue
            into = already
            break

        if into is None:
            kept.append(dict(event, channels=list(event["channels"])))
            continue

        # THE TITLE THE KEEPER WEARS. For a structural fold, the
        # broadcaster's won — until the day the longer one was WRONG
        # and the shorter one was right: a listings page's rich title
        # kept naming a withdrawn fighter long after the broadcaster's
        # guide had self-corrected, so a broadcaster's bare title now
        # replaces the page's. For an identity fold the two rows are
        # two broadcasters' own grids — Sky's against Sportsnet's, or
        # TSN's against the listings page's — and neither outranks the
        # other the way a listings page is outranked; the row that
        # NAMES MORE is the row a viewer reads, and the longer title
        # is kept.
        if _the_broadcaster_names_it(event, into) and not by_identity:
            into["title"] = event["title"]
        elif by_identity and len(event["title"]) > len(into["title"]):
            into["title"] = event["title"]

        for channel in event["channels"]:
            if channel not in into["channels"]:
                into["channels"].append(channel)
        folded += 1

    if folded:
        log(f"  {folded} broadcast(s) two sources both had, now one row each")
    if dropped_by_the_backup:
        log(f"  {dropped_by_the_backup} row(s) the backup had that a "
            f"listings page already carried, dropped")

    # THE ENCORE. A race is one broadcast, and the measured board
    # carried TSN2's encore of the Italian Grand Prix thirteen hours
    # after the live one. The fold above cannot drop it — the fold
    # answers "is this a second SOURCE naming the same broadcast?", and
    # the encore is one source repeating a broadcast it already gave
    # the board at its live minute — so the question is asked here,
    # after the fold, with the race's own identity: the same grand
    # prix, ten hours to three days later, is a replay and falls away.
    # The racing days that must survive — SailGP's nine-hour gap, the
    # race weekend's own studio shows — are refused inside the test.
    encore = 0
    if any(row.get("sport") == "F1" for row in kept):
        for row in kept:
            if row.get("sport") != "F1":
                continue
            if A_SAILING_WORDS.search(row.get("title") or ""):
                continue
            if any(other.get("sport") == "F1"
                   and other is not row
                   and other["start"] < row["start"]
                   and _an_encore_of_the_race(other, row)
                   for other in kept):
                encore += 1
        if encore:
            kept = [row for row in kept if not (
                row.get("sport") == "F1"
                and not A_SAILING_WORDS.search(row.get("title") or "")
                and any(other.get("sport") == "F1"
                        and other is not row
                        and other["start"] < row["start"]
                        and _an_encore_of_the_race(other, row)
                        for other in kept))]
            log(f"  {encore} encore(s) dropped, the race already on the "
                f"board at its live minute")
    return kept


def collect(session, floor: datetime, ceiling: datetime) -> list[dict]:
    """Every event both sources have, inside the window, that names a channel."""
    everything = world_sport_on_tv.events(session)
    everything += american_sport_on_tv.events(session)
    can_fetch = hasattr(session, "request")

    # And the fights this repository's OWN guides have, which no listings
    # page anywhere carries. A reader asked for RFC — an MMA promotion in
    # Amman — and it needed nothing to be written down: Roya's own feed
    # is already built here every hour and it has the event, at the
    # minute the promotion's own announcement gave.
    if can_fetch:
        everything += own_guides.fights_our_guides_have(floor, ceiling)

    # AND THE EVENTS this repository's own guides have, LIVE ONLY —
    # the rule the reader set after measuring this same window: "only
    # live events". A guide's repeats carried rows the listings pages
    # never had — FIBA qualifiers, triathlon, athletics, volleyball —
    # and every one of them was a REPLAY, 46 of 49 measured, because a
    # guide repeats its week's competitions and the listings pages
    # carry only what is broadcast live. So events_our_guides_have now
    # requires the guide's own live mark (A_LIVE_AIRING) on the row's
    # raw title, and in this window only three MLB games on beIN
    # SPORTS EN 1 survive it. The table is OUR_OWN_EVENTS, the shape
    # rule (an hour to nine hours long) and the LA-day fold are in
    # own_guides.py — same door fights_our_guides_have uses.
    if can_fetch:
        everything += own_guides.events_our_guides_have(floor, ceiling)

    # AND THE CARD, SPLIT, from the broadcaster's own programme guide.
    #
    # A UFC night is early prelims, then prelims, then the main card,
    # each with its own start — asked for more than once, and no listings
    # page here had them: wheresthematch's UFC page was printed row by
    # row and carries six rows, one per event.
    #
    # Sky publishes its guide openly and has them as PROGRAMMES:
    #
    #     TNTSports1 HD · 2026-09-05
    #        1788627600  Live: UFC Fight Night Prelims   19:00 UTC
    #        1788634800  Live: UFC Fight Night           21:00 UTC
    #
    # It also recovers TNT, whose own site answers 403 to every request
    # from a runner — schedule, boxing and MMA pages alike — so the
    # channel carrying the UFC in Britain could not be read from itself.
    if can_fetch:
        everything += sky_epg.events(session, floor, ceiling)

    # AND REAL AMERICAN FREESTYLE, from the promotion's own page. No
    # listings page anywhere carries it — wheresthematch has no RAF row
    # — and the promotion publishes the one thing that matters on its
    # own events page: the card, the fight, and the broadcaster that
    # has announced a time, which is Fox Nation under the long-term
    # deal both parties announced. Its cards without a watch block
    # (RAF13 Miami, RAF14 Las Vegas — tickets only) are skipped by the
    # reader itself, so they reach this board the day RAF publishes
    # them, without anybody here editing anything.
    #
    # It is filed as MMA for the same reason Sky's own RAF programmes
    # are: this board folds two rows into one only when they agree on
    # the sport, and a card filed two ways would print twice.
    if can_fetch:
        everything += real_american_freestyle.events(
            session, floor, ceiling)

    # AND PREMIER BOXING CHAMPIONS, from the promotion's own schedule
    # page. Another "more sources" answer: PBC is the boxing promotion
    # no source on this board carried — no listings page has its cards,
    # Sky's guide names none, and the promotion publishes its schedule
    # itself as open JSON-LD on its own page, with the broadcaster in
    # its own description prose ("streaming live on DAZN", "live on TNT
    # and DAZN") and the clock in the timestamp itself. It is filed as
    # Boxing, the sport this board already carries, so a card the Sky
    # guide happens to name too folds into the one row a viewer reads.
    if can_fetch:
        everything += pbc.events(session, floor, ceiling)

    # AND ESPN'S OWN SCOREBOARD, asked for in the reader's own words —
    # "check new reliable sources similar to tapology or other websites
    # !!! FOR FUTURE LIVE ONLY EVENTS" — because what ESPN has that no
    # calendar here does is the league's own forward grid: every UFC and
    # PFL card, months ahead, with the exact UTC instant and the
    # broadcaster the league itself named, in an open page no reader has
    # to stand in front of. The Contender Series' midweek weeks are on
    # it — week by week through the season — and no listings page here
    # carries them at all. A card with no published clock (the league's
    # own "timeValid": false) or no named broadcaster never reaches the
    # board: the same rules every row here obeys, in ESPN's own
    # spelling, and "only live" is the league's own status word, "pre".
    #
    # It runs before Tapology on purpose. Tapology is the backup, and
    # where the two name one card an hour apart — the Contender Series
    # measured at 23:00 against 00:00 — the fold below reads the card's
    # own identity and the two become one row.
    if can_fetch:
        everything += espn_fights.events(session, floor, ceiling)

    # AND TAPLOGY'S FIGHTCENTER, the fights board's calendar of last
    # resort. The reader asked for it by name — "this website have all
    # the missing parts or as a backup for others if applicable" — and
    # what it has that no listings page here does is the part of fight
    # sport nobody televises: BRAVE, Pancrase, OKTAGON, BKFC, every card
    # that sells itself. Where the card is confirmed by Tapology's own
    # words — DAZN, TrillerTV, UFC Fight Pass — that channel is kept,
    # and where nothing but the promotion's own site carries it, the
    # honest word for what it is, PPV, is what the row says.
    #
    # It runs BEFORE own_guides and sports_media_watch, so a PPV-only
    # row can still be confirmed onto a real channel by them — and if
    # one of them does, the row a listings page already had wins below,
    # because Tapology is the backup, not the headline.
    if can_fetch:
        everything += tapology.events(session, floor, ceiling)

    # AND THE CANADIAN BROADCASTERS' OWN GRIDS — TSN and Sportsnet, asked
    # for by name ("TSN AND SPORTSNET events matches to be added on
    # channels 1 and 2 find sources reliable ones from outside github").
    # What they have that no listings page here does is the events a
    # Canadian viewer watches on a Canadian channel: US Open tennis on
    # TSN1, Japan-Canada rugby on TSN4, F1 qualifying on TSN5, the
    # CW-SLARS rugby on Sportsnet. Both feeds are read from the same
    # place their own television reads them, and the sport word each
    # feed prints is what gates the row to this board — soccer belongs
    # to the football board and is handed to its caller instead.
    #
    # Baseball and basketball joined the ask in the reader's own words —
    # "Add Yankees, Dodgers games (MLB)" and "Verify NBA, FIBA listed
    # with good sources and channels" — and then half the ask came back
    # off: "remove snooker & MLB from channel 2". Basketball still has
    # its door: TSN files it under "Basketball" and Sportsnet under
    # "basketball", and the judging is done where it belongs, in each
    # feed's own reader — a basketball row is the NBA or FIBA by its
    # own title or it is nothing this board asked for. Baseball no
    # longer has a door anywhere: both readers now map the word to
    # nothing, so pulling it from the wiring below is honest bookkeeping
    # for a sport that cannot arrive at all.
    if can_fetch:
        everything += tsn.events(
            session, floor, ceiling,
            sports=("Tennis", "Rugby", "NFL", "Golf", "MMA", "Auto Racing",
                    "Basketball"))
        everything += sportsnet.events(
            session, floor, ceiling,
            sports=("rugby", "mma", "basketball"))

    inside = [dict(event, channels=drop_simulcasts(event["channels"]))
              for event in everything
              if floor <= event["start"] < ceiling]

    # The channel this reader can actually turn to, taken from the
    # broadcasters' own feeds — which this repository already publishes
    # and rebuilds every hour.
    #
    # This board's source is British and only British, measured across
    # all forty-four of its pages: Sky 1106 mentions, TNT 363, DAZN 226,
    # and not one Fox, NBC, ESPN or beIN. So every row was offering a
    # viewer with a MENA package the one set of channels they cannot
    # open. beIN's own feed carries 63 Formula One programmes and 294
    # tennis; STARZPLAY's carries the UFC, Dana White's Contender Series
    # and The Ultimate Fighter. They say it themselves, so nothing here
    # has to claim it — and the day a broadcaster loses a sport, its feed
    # stops carrying it and this stops saying it, with nobody editing a
    # line.
    #
    # Before wanted(), deliberately: an event the British page has not
    # placed anywhere is still on beIN if beIN's own schedule says so,
    # and refusing it for want of a channel that page never had would
    # throw away the better source of the two.
    if can_fetch:
        own_guides.add_channels_by_name(inside)

    # AND THE NETWORK ON EVERY NFL ROW, which none of them had.
    #
    #     17:20  Patriots - Seahawks          (no channel)
    #     10:00  Falcons - Steelers           (no channel)   … seven of seven
    #
    # The games are here because the league's own site is read for them
    # and gives a real UTC instant. The network that used to sit in its
    # screen-reader text is not reaching the row any more, so seven games
    # sat on a board whose whole purpose is answering where to watch one.
    #
    # It names no game of its own — every row it returns is a channel
    # looking for a game the league already put here.
    if can_fetch:
        sports_media_watch.add_channels(session, inside)

    # Two sources, one broadcast, one row — after the channels are in, so
    # a row folded away leaves its channel behind on the row that stays.
    # And Tapology's rows fall away FIRST, because the reader named it a
    # backup: where a listings page already had the same fight at the
    # same minute in a real channel, the backup's row is the duplicate,
    # and its PPV wording is folded away rather than printed twice.
    inside = one_row_per_broadcast(
        inside, the_backup_is="tapology" if can_fetch else None)
    kept = [event for event in inside if wanted(event)]
    log(f"  {len(everything)} event(s) offered, {len(inside)} in the window, "
        f"{len(kept)} in a sport asked for and naming a channel")
    return in_the_readers_order(kept)


def publish_all(events: list[dict], now: datetime,
                *, days: list[date] | None = None) -> int:
    """Render and publish this channel for whichever clock the module wears.

    Every clock in the file — the day an event groups under, the hour
    printed beside it, the window a programme runs — reads the module's
    VIEWER, so one function renders the channel for any zone it is told
    to wear, and the two clocks cannot drift apart in how they draw.

    The days are a parameter because the two clocks do not agree about
    where the collected window ends: the default is the viewer's own
    days_of(), and the UAE-clock caller hands in the days the collected
    events actually span, so an event at the window's far edge is never
    dropped for landing on a date the window never named.
    """
    days = days_of(now) if days is None else days
    tv = ET.Element("tv", {"generator-info-name": "Today's Other Sports"})
    channel = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(channel, "display-name", {"lang": "ar"}).text = CHANNEL_AR
    ET.SubElement(channel, "icon", {"src": LOGO})

    by_day: dict[date, list[dict]] = {day: [] for day in days}
    for event in events:
        day = event["start"].astimezone(VIEWER).date()
        if day in by_day:
            by_day[day].append(event)

    # A DAY WITH NOTHING ON IT IS NOT A BOARD. The window rolls four
    # days now, dense by design, and a day can still arrive with no
    # fight and no race on it — a board that says "لا يوجد حدث" is worse
    # than no board, and every empty board is another twenty seconds a
    # viewer waits to see the next real thing.
    #
    # Today is the exception and is always drawn. A viewer tuning in
    # wants to be told there is nothing on today; being shown next
    # Saturday with no word about this evening reads as a fault.
    with_something = [day for day in days if by_day[day] or day == days[0]]
    if len(with_something) < len(days):
        log(f"  {len(days) - len(with_something)} day(s) with nothing on "
            f"them, not drawn")

    board_no = 0
    per_day: list[int] = []
    for day in with_something:
        today = by_day[day]
        chunks = [today[at:at + MAX_ON_BOARD]
                  for at in range(0, len(today), MAX_ON_BOARD)] or [[]]
        first_board = None
        for page, chunk in enumerate(chunks, start=1):
            url = publish_board(board_no, day, chunk, now,
                                page=page, pages=len(chunks))
            first_board = first_board or url
            board_no += 1
        per_day.append(len(chunks))

        opens, closes = day_bounds(day)
        add_programme(tv, CHANNEL_ID, opens, closes,
                      day_title(day, today, now),
                      day_page(day, today, now), icon=first_board)
        log(f"  {day} -> {len(today)} event(s) over {len(chunks)} board(s)")

    # And the boards this pass did NOT write. The window rolls at
    # midnight — yesterday goes, a new day arrives at the far end — and
    # the count can fall, so a board the old build wrote and this one did
    # not was still on disk and still in the reel, playing a day that was
    # over.
    # HOW MANY BOARDS EACH DAY TOOK, for the same reason as the first
    # board and with the same fault waiting if it is missing: without
    # this the reel counts boards, and a day whose card runs past the end
    # of the lap is played half-way and cut. This board is more exposed
    # to it, not less — it reaches four days, and a Saturday of UFC
    # and boxing takes several boards where a quiet Tuesday takes one.
    with open(os.path.join(BOARD_DIR, f"{BOARD_PREFIX}days.txt"), "w",
              encoding="utf-8") as handle:
        handle.write("\n".join(str(count) for count in per_day) + "\n")
    log(f"  boards per day: {per_day} (written for the encoder)")

    from match_board import forget_boards_past
    stale = forget_boards_past(BOARD_PREFIX, board_no, BOARD_DIR)
    if stale:
        log(f"  {stale} board(s) for days that have gone, deleted")

    ok = write_xml_atomic(tv, OUTPUT, generator_name="Today's Other Sports",
                          guard_regression=False, min_programmes=1)
    return 0 if ok else 1



def build() -> int:
    now = datetime.now(UTC)
    days = days_of(now)
    floor, ceiling = start_of_day(days[0]), start_of_day(
        days[-1] + timedelta(days=1))

    session = new_session()
    events = collect(session, floor, ceiling)

    # Sorted and shortened once, here, so the printed line and the drawn
    # board show the same names in the same order — they each take the
    # first three and would otherwise disagree about which those are.
    # This is the first board's step, borrowed whole, and it is what puts
    # a reader's own beIN in front of a Sky they cannot tune to.
    for event in events:
        event["channels"] = [shorter(name) for name
                             in channels_in_order(event["channels"])]

    ok = publish_all(events, now) == 0

    # THE SECOND CLOCK — the same events, every time printed in the
    # Gulf's (Asia/Dubai), asked for outright as a second set of links.
    # The events were collected once for both clocks; the module wears
    # another zone for one render and puts it back afterwards. The first
    # set is written and safe before this begins, and a failure here
    # warns and leaves it exactly as it was.
    with dubai_time.the_other_clock(
            globals(),
            VIEWER=dubai_time.DUBAI, VIEWER_NAME=dubai_time.DUBAI_NAME,
            OUTPUT=DUBAI_OUTPUT, CHANNEL_ID=DUBAI_CHANNEL_ID,
            BOARD_PREFIX=DUBAI_BOARD_PREFIX):
        try:
            publish_all(events, now,
                        days=dubai_time.days_the_events_span(
                            now, events, dubai_time.DUBAI))
        except Exception as exc:                              # noqa: BLE001
            warn(f"the UAE-clock sports guide could not be written "
                 f"({exc}) — the published one is unchanged")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
