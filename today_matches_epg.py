#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""مباريات اليوم — one channel that answers the day on a single page.

Every other guide here answers "what is on THIS channel". This one answers
the question a viewer starts with: what is on today, and where do I watch
it — and it answers it without the viewer pressing anything. Highlighting
the channel is enough, because the whole day lives in the description:

    ⏳ بعد 45 دقيقة · Flamengo RJ - Mirassol        <- what the grid shows
    ------------------------------------------------------------------
    مباريات الأربعاء 02/09 — بتوقيت +03:00          <- what the panel shows
      🔴  19:00  Colegiales - Midland · LPF Play
      ⏳  19:30  Flamengo RJ - Mirassol · Flamengo TV YouTube
          21:00  Al Wehda FC - Damac FC · Thmanyah 1 HD

One programme per day, not one per match, and emphatically not one per
countdown step. The first shape published 119 rows for a dozen matches:
a single match owned eight consecutive fifteen-minute blocks that differed
only in an Arabic tail, and a television truncates titles from the right,
so all eight rendered as the same cut-off name. The counter was in the
file and invisible on the screen — all of the cost, none of the benefit.
It is now one row a day, and the counter rides at the FRONT of that row's
title where truncation cannot reach it.

Two sources, because one was demonstrably not enough. livefootballtv's
front page lists the day's matches with the channels carrying them
worldwide, and it is the Gulf half of the answer — beIN, Thmanyah, SSC.
But a scores app showed three Championship matches it had never listed, so
live-footballontv.com was measured and added beside it: a British listings
page that names Sky Sports, TNT and Premier Sports against the same
fixtures. Neither page is asked to be complete on its own. A match on both
is one row naming what both said; a match on one is still a row.

On the clock, learned twice: each row carries a displayed time in td.hora
and a schema.org startDate in the markup, and the displayed time is
exactly two hours ahead of the markup, flat. The first reading of that
took the markup for the UTC instant. It is not — the displayed clock is
the Gulf's, the Gulf is three hours ahead rather than two, and the markup
is an hour fast. See GULF below for how that was settled, and what it
cost: the reader's own clock was moved an hour to hide it.

Football only, for now. The page covers other sports thinly and they can
be added later without touching what is here.
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import io

import requests
from bs4 import BeautifulSoup
from PIL import Image
import xml.etree.ElementTree as ET

import live_football_on_tv
import live_soccer_tv
import own_guides
import spor_ekrani
import yallakora
from epg_lib import (
    MATCH_ON_AIR, add_programme, arabic_count, club_skeleton, countdown_label,
    fetch, in_reading_order, isolate, log, norm, same_club, warn,
    write_xml_atomic,
)

SOURCE = "https://www.livefootballtv.info/"
OUTPUT = "today_matches_epg.xml"
# An id of its own, not a borrowed one.
#
# Nothing in a viewer's playlist carries this id, and that is deliberate:
# the viewer points whichever channel they like at this guide themselves,
# which every player worth using can do. Borrowing a real channel's id was
# tried and was wrong twice over — it guesses at a playlist nobody here
# can see, and it takes the guide away from that channel to give it here.
CHANNEL_ID = "TodayMatches"
CHANNEL_AR = "مباريات اليوم"
CHANNEL_EN = "Today's Matches"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/today_matches.png")

# The day drawn as a board, for players that show programme artwork.
#
# A guide file cannot lay anything out — it hands a player text and the
# player decides what that looks like. The one opening XMLTV leaves is the
# programme <icon>, so the page is also drawn as a picture and attached
# there. A player that shows it gets a ruled board; one that does not
# still has the text, which loses nothing.
#
# The board carries clock times and no countdown: a countdown would
# change every pass and commit a fresh copy of the image every ten
# minutes. It is written only when it actually differs from the one
# already published.
BOARD_DIR = "boards"
BOARD_URL = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
             "main/boards")
BOARD_COLOURS = 64      # flat interface art: 88 KB truecolour, 27 KB here

UTC = timezone.utc

# The zone the source prints its clock in, and the hour its markup is out.
#
# Every row carries two times: a clock in td.hora that its readers see,
# and a schema.org startDate in the markup. Measured across a page, the
# printed clock is exactly two hours ahead of the markup, flat — and the
# printed clock is the Gulf's. The site lists beIN, Thmanyah, SSC and ON
# Sport; for a Saudi league match it prints the hour Saudi Arabia kicks
# off at. So it publishes its Gulf clock minus two hours, as though the
# Gulf were two ahead of UTC, when it is three. Its markup is an hour fast.
#
# That is not an inference from one match. A second listings page was read
# for its own reasons, and on all twelve fixtures the two pages share, the
# gap is exactly sixty minutes with this page later — no spread at all.
# What settles which of them is right is British football, whose kickoff
# times are not a matter of opinion: this page puts Burnley v
# Middlesbrough on Sky at 21:00 UK and Hibernian v Hearts at 20:45, and
# nothing kicks off at either. The other page says 20:00 and 19:45, which
# is what the Championship and the Premiership actually play at.
#
# The Gulf keeps no summer time, so the error is a flat hour all year —
# but the printed clock is read directly rather than the markup corrected,
# because the printed clock is the one the site maintains and shows. If
# they ever repair the startDate, this keeps working.
GULF = ZoneInfo("Asia/Riyadh")
MARKUP_IS_FAST_BY = timedelta(hours=1)

# The clock the list is printed in — the reader's own.
#
# A player converts the programme times it positions rows by, but not one
# character of the text inside a description or drawn onto a board, so
# those have to be written in the reader's clock or they are useless.
#
# This has moved twice, and the second move undid the first for a reason
# worth writing down. It began here, went to a fixed −08:00 because three
# Saudi matches came out an hour ahead of the reader's screen, and has
# come back — because the hour was never on this side. The source's
# machine-readable startDate runs an hour fast (see kickoff_of), and
# forcing the reader's clock back by an hour hid that rather than fixing
# it: right in September, an hour wrong every winter, for no reason
# anybody would have found later.
#
# With the source's own hour corrected, the reader's report lands exactly
# on this zone: a match whose true kickoff is 15:55 UTC showed 08:55 on
# their device, which is seven hours, which is Los Angeles in September.
# Two errors of an hour each, in opposite directions, printing the right
# digits on the one day they were compared.
VIEWER = ZoneInfo("America/Los_Angeles")
VIEWER_NAME = "بتوقيتك"

ARABIC_DAY = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس",
              "الجمعة", "السبت", "الأحد")

# How many days past today the guide draws a board for.
#
# Counted in the READER'S days, not in hours from now, and that distinction
# is the whole of a bug that made the last board permanently empty. It used
# to be `timedelta(days=2)` measured from the moment the build ran: the
# board list was built from that instant's DATE — giving three days — while
# the matches were filtered against the instant itself. So the last day was
# only ever admitted up to the clock time of the build. At 14:36 UTC that
# let in 7.6 of Friday's 24 hours, all of them before dawn in Los Angeles,
# and every Friday evening kickoff in Europe fell outside by hours.
#
# The board was drawn regardless and said "لا توجد مباراة معلنة" — a full
# Friday of football reported as nothing, every single day, and it read
# like a guide that had stopped updating rather than one with an
# arithmetic fault. A day that gets a board must get the whole of that day.
DAYS_AHEAD = 2

# Three channels per match — Arabic, English, American, which is the
# whole of what a viewer here is likely to be able to open.
#
# One was chosen when a match rarely had a second to show. Two was chosen
# next, and three was REFUSED on the grounds that a twelve-match day
# draws 38px rows and could not fit them. That was asserted and never
# measured, and it was wrong: drawn at twelve rows with the longest
# fixture the board carries — "Wolverhampton Wanderers - Nottingham
# Forest" — three full pills clear the title with room to spare, because
# a crowded row draws its pills smaller too.
#
# Beyond the third the count returns, honest about there being more
# without spending a line on it.
MAX_CHANNELS = 3

# How wide a line may get before a television wraps it onto a second one.
# Simultaneous kickoffs share a line only while they stay inside this:
# measured, two full fixtures came to 92 characters and wrapped, which
# spends the line the merge was meant to save. Merging is only worth doing
# when it actually removes a line.
LINE_BUDGET = 60

# Inside an hour a printed countdown is stale enough to mislead, so it is
# rounded up to one of these and stated as a bound rather than a fact.
NEAR_STEPS = (15, 30, 45, 60)

# A board holds this many rows before the day spills onto a second one.
# Nine fit at a readable size on a 720-line screen; past that the rows
# shrink toward the point where the screen is full of text nobody across
# a room can read, which is the opposite of what the board is for.
MAX_ON_BOARD = 9

# What a row says when the fixture is real and the broadcaster is not yet
# named. wanted() guarantees this only ever replaces an empty list, never
# a list of shops.
CHANNEL_UNANNOUNCED = "لم تُعلن القناة"

LIVE_MARK = "🔴"
NEXT_MARK = "⏳"

# Competitions worth a place on this channel, as the source names them.
#
# The source labels every match with its competition in a heading row
# (tr.cabeceraCompericion), so this is a list of real names read off the
# page, not a guess at club names. 539 matches across 46 competitions came
# down the wire on the day this was written; almost all of them are
# reserve, youth and third-tier football nobody asked to see.
#
# Matched exactly, because a substring would swallow the wrong thing:
# "Premier League" is also how Egypt, Bahrain, Iceland and Ukraine are
# labelled, and "Serie A" is also Brazil's — which is now the reason the
# exact match matters in the other direction, Brazil having been asked
# for and then asked to go.
WANTED_EXACT = {
    "saudi pro league", "premier league", "serie a",
    "ligue 1", "laliga", "la liga", "bundesliga", "champions league",
    "europa league", "conference league",
    "turkish süper lig", "süper lig", "super lig",
    # Asked for by name after they were seen missing. "Championship" is
    # England's second tier and has to be matched exactly, or "Caribbean
    # Club Championship" and "ASEAN Club Championship" come with it.
    "championship", "egyptian premier league",
}

# Matched anywhere in the name, for families whose members all belong:
# every FIFA and UEFA competition, the African and Asian confederations,
# the Gulf cups, Jordan, and the domestic cups of the leagues above.
WANTED_PARTS = (
    "fifa", "world cup", "uefa", "nations league",
    "caf ", "africa cup", "afcon", "afc ", "asian cup",
    "gulf cup", "arabian gulf",
    # Jordan, league and cup alike: one word covers every competition the
    # page can name for it, which is why it was already here.
    "jordan",
    # Egypt beyond the league — the cup and the super cup.
    "egypt",
    # England's cups. "efl" catches the League Cup whatever sponsor's name
    # is on it this season, which is what "carabao" alone would miss the
    # moment the sponsor changes.
    "fa cup", "efl", "carabao", "community shield",
    # Turkey's cup, in both the spellings the page might use.
    "turkish cup", "kupası", "kupasi",
    "king cup", "coppa italia", "copa del rey", "coupe de france", "dfb",
)

# What the third page is asked for, and nothing else.
#
# Every one of these is a competition the other two pages were measured
# not to carry, and each is here because a reader photographed a fixture
# missing from it: Jordan's league, Egypt's league — الأهلي v سموحة was
# on neither page — and Turkey's, where Başakşehir v Galatasaray was
# missing too. Outside these it would be adding European football both
# other pages already have, in Arabic, with no safe way to tell it is the
# same match. Widen this only against a measurement.
YALLAKORA_ONLY = (
    "الدوري المصري", "كأس مصر", "السوبر المصري",
    "الدوري الأردني", "كأس الأردن", "درع الاتحاد الأردني",
    "الدوري التركي", "كأس تركيا",
)

# The same families as WANTED_PARTS, as the third page names them.
#
# yallakora heads each block with the competition in Arabic and, in the
# heading image's enname, in English — and the English one is not always a
# form anything here recognises ("Ligue1" is not "ligue 1"). The Arabic is,
# so the Arabic is what is matched, and both are carried on the event.
#
# "الدوري المصري" is exact enough to leave "دوري القسم الثاني-أ" — Egypt's
# second tier, eight of which turned up on one day — where it belongs.
WANTED_ARABIC = (
    "الدوري المصري", "الدوري الإنجليزي", "الدوري الإسباني",
    "الدوري الإيطالي", "الدوري الألماني", "الدوري الفرنسي",
    "الدوري التركي", "الدوري السعودي", "دوري روشن",
    "دوري أبطال أوروبا", "الدوري الأوروبي", "دوري المؤتمر",
    "دوري أبطال أفريقيا", "دوري أبطال آسيا", "كأس العالم",
    "الدوري الأردني", "كأس الأردن", "كأس مصر", "السوبر المصري",
    "كأس تركيا", "كأس الملك", "كأس إنجلترا", "كأس ألمانيا",
    "كأس إيطاليا", "كأس إسبانيا", "كأس فرنسا",
)

# Clubs that belong here whatever they are playing in. Asked for by name,
# including the age groups and the women's side, which is why this guide
# has no blanket rule against "Reserva", "Femenino" or "U19" — such a rule
# would drop exactly the matches that were asked for.
WANTED_TEAMS = ("manchester united", "man united", "man utd", "manchester utd")

# Not a television channel, whatever the source calls it.
#
# A club's own YouTube feed, a pay-per-view app, a federation stream: the
# page lists them beside beIN and Sky as though they were the same kind of
# thing, and a guide whose whole purpose is "where do I watch this" should
# not answer with a shop. A match is dropped when EVERY name against it is
# one of these; one real channel is enough to keep it, and the real one is
# what gets shown.
NOT_A_CHANNEL = (
    "onefootball", "ppv", "youtube", "app", "tv+", "plus tv",
    "federation", "official site", "club tv",
)

# The page labels the Austrian Bundesliga with exactly the word it uses for
# the German one, so "Bundesliga" alone let Austria Vienna, Tirol, Salzburg
# and SK Rapid onto the channel on the first day this ran.
#
# The clubs are the only thing that separates them, and it is Austria's
# twelve that are listed rather than Germany's eighteen — deliberately. A
# list of the wanted side would drop a promoted German club the season it
# came up, which is losing a match somebody asked for; a list of the
# unwanted side lets a promoted Austrian club through, which is one extra
# row nobody minds. When in doubt, keep the match.
AUSTRIAN_BUNDESLIGA = (
    "salzburg", "sturm graz", "rapid", "austria vienna", "austria wien",
    "lask", "wolfsberger", "hartberg", "blau-weiß linz", "blau-weiss linz",
    "tirol", "klagenfurt", "altach", "grazer ak",
)

# Worded so the build's own honesty measure counts it: a day with nothing
# on it is the guide saying it has nothing, not a broadcast.
NOTHING_TODAY = "لا توجد مباراة معلنة — No matches listed"


def sources_of(row) -> list[str]:
    """Every channel this row says carries the match, in the page's order."""
    canales = row.find("td", class_="canales")
    if not canales:
        return []
    seen: list[str] = []
    for item in canales.select("ul.listaCanales li"):
        label = norm(item.get("title") or item.get_text(" ", strip=True))
        # The page repeats a channel across its own regional feeds; keep
        # the first spelling and drop the rest.
        if label and label not in seen:
            seen.append(label)
    return seen


def team_in(cell) -> str:
    span = cell.find("span", title=True) if cell else None
    if span and span.get("title"):
        return norm(span["title"])
    return norm(cell.get_text(" ", strip=True)) if cell else ""


def is_match(row) -> bool:
    return bool(row.find("td", class_="local")
                and row.find("td", class_="visitante")
                and row.find("td", class_="canales"))


def competition_of(row) -> str:
    """The competition heading standing above this match row.

    The page groups matches under tr.cabeceraCompericion headings, so the
    nearest <tr> above that is not itself a match is the competition. It
    has to be restricted to rows: walking back over every element instead
    lands inside the previous match and returns a channel or a club name.
    """
    for previous in row.find_all_previous("tr"):
        if is_match(previous):
            continue
        head = norm(previous.get_text(" ", strip=True))
        if 2 < len(head) < 90:
            return head
    return ""


def real_channels(channels: list[str]) -> list[str]:
    """The names among these that are actually somebody's television."""
    return [c for c in channels
            if not any(word in c.casefold() for word in NOT_A_CHANNEL)]


def wanted(event: dict) -> bool:
    """Is this a competition — or a club — that was actually asked for?"""
    # A shop is not a channel — a match whose every name is a pay-per-view
    # app, a club's YouTube feed or a federation stream is still dropped,
    # because a guide answering "where do I watch this" should not answer
    # with a shop.
    #
    # But a match that names NO channel at all is a different thing, and
    # it used to be dropped with the same line. That cost real fixtures:
    # yallakora lists Başakşehir v Galatasaray in Turkey's league with no
    # broadcaster yet, and a reader comparing against a scores app sees a
    # missing match, not a missing channel. It is shown, and says the
    # channel has not been announced.
    if event["channels"] and not real_channels(event["channels"]):
        return False

    competition = event["competition"].casefold()
    teams_folded = event["title"].casefold()

    # Austria borrows Germany's word for its league; the clubs are the only
    # thing that tells the two apart.
    if competition == "bundesliga" and any(club in teams_folded
                                           for club in AUSTRIAN_BUNDESLIGA):
        return False

    if competition in WANTED_EXACT:
        return True
    if any(part in competition for part in WANTED_PARTS):
        return True
    if any(part in event["competition"] for part in WANTED_ARABIC):
        return True
    return any(club in teams_folded for club in WANTED_TEAMS)


PRINTED_CLOCK = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")


def kickoff_of(row) -> datetime | None:
    """When this match actually starts — see GULF above for why not both.

    The markup gives the date and an hour that is one too many; the
    printed cell gives the right hour and no date at all. So the date
    comes from the markup and the hour from the cell, and the day is
    chosen as whichever of yesterday, today and tomorrow puts the two
    closest together — which is what makes a kickoff printed as 00:30,
    after the markup's midnight, land on the right side of it.
    """
    cell = row.find("td", class_="canales")
    meta = cell.find("meta", attrs={"itemprop": "startDate"}) if cell else None
    try:
        published = datetime.fromisoformat((meta.get("content") or "")
                                           if meta else "")
    except (ValueError, AttributeError):
        return None
    if published.tzinfo is None:
        published = published.replace(tzinfo=UTC)
    corrected = published.astimezone(UTC) - MARKUP_IS_FAST_BY

    clock = row.find("td", class_="hora")
    struck = PRINTED_CLOCK.search(norm(clock.get_text(" ", strip=True))) \
        if clock else None
    if not struck:
        return corrected            # no printed clock: the markup, corrected

    printed = time(int(struck.group(1)), int(struck.group(2)))
    around = corrected.astimezone(GULF).date()
    return min((datetime.combine(around + timedelta(days=step), printed,
                                 GULF).astimezone(UTC)
                for step in (-1, 0, 1)),
               key=lambda instant: abs(instant - corrected))


def start_of_day(day: date) -> datetime:
    """Midnight at the start of that day, in the reader's zone, as UTC."""
    return datetime.combine(day, time(0, 0), VIEWER).astimezone(UTC)


def window_floor(now: datetime) -> datetime:
    """Where the guide starts reading: the top of the viewer's today.

    The whole of their today, however much of it has already been played —
    the page is a list of the day, not of what is left of it. Both sources
    are held to this same edge, or a match would appear on one board and
    not the other purely by which page it came off.
    """
    return start_of_day(now.astimezone(VIEWER).date())


def window_ceiling(now: datetime) -> datetime:
    """Where the guide stops reading: the END of the last day it draws.

    Not "two days from now". The last board covers a whole day of the
    reader's, so the window has to reach the end of that day or the board
    is drawn with only part of its own day available to fill it — which is
    exactly how a full Friday came to be published as an empty one.
    """
    return start_of_day(now.astimezone(VIEWER).date()
                        + timedelta(days=DAYS_AHEAD + 1))


def days_of(now: datetime) -> list[date]:
    """Every day the guide draws a board for, today first.

    The single place that decides this, so that what is drawn and what is
    collected cannot drift apart the way they did.
    """
    first = now.astimezone(VIEWER).date()
    return [first + timedelta(days=step) for step in range(DAYS_AHEAD + 1)]


def collect(html: str, now: datetime, floor: datetime,
            ceiling: datetime) -> list[dict]:
    """Every match on the page, with its kickoff, channels and competition.

    Nothing is filtered here, deliberately. A source is asked for what it
    saw, not for what is wanted — the two sources are merged first, so a
    match the first page labelled with nothing can still be recognised by
    the competition the second page gave it. Judging each page on its own
    would throw that match away before the other page could speak.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    events: list[dict] = []
    no_time = no_channel = 0

    for row in soup.find_all("tr"):
        if not is_match(row):
            continue

        home = team_in(row.find("td", class_="local"))
        away = team_in(row.find("td", class_="visitante"))
        if not home or not away:
            continue

        start = kickoff_of(row)
        if start is None:
            no_time += 1
            continue

        if not (floor <= start < ceiling):
            continue

        channels = sources_of(row)
        if not channels:
            # Without a channel this guide has nothing to say that the
            # other thirteen do not already say better.
            no_channel += 1
            continue

        events.append({
            "start": start,
            "title": f"{home} - {away}",
            "channels": channels,
            "competition": competition_of(row),
        })

    if no_time:
        log(f"  {no_time} row(s) carried no readable kickoff and were skipped")
    if no_channel:
        log(f"  {no_channel} row(s) named no channel and were skipped")

    # The same match can appear twice when the page lists it under two
    # competitions; one kickoff and one pair of names is one match.
    merged: dict[tuple, dict] = {}
    for event in sorted(events, key=lambda e: e["start"]):
        key = (event["start"], event["title"].casefold())
        if key in merged:
            for channel in event["channels"]:
                if channel not in merged[key]["channels"]:
                    merged[key]["channels"].append(channel)
        else:
            merged[key] = event

    everything = sorted(merged.values(), key=lambda e: e["start"])
    log(f"  livefootballtv: {len(everything)} match(es) in the window")
    return everything


# Two pages, two spellings, one match.
#
# epg_lib.same_fixture answers this across scripts and refuses to answer
# within one, for a measured reason: inside Latin, "Mainz"/"Monza" and
# "Al Nassr"/"Al Nasar" score at or above every similarity threshold that
# still catches a real pair. Both pages here write Latin, so that door is
# shut and it stays shut. Nothing below scores anything.
#
# What actually differs between the two pages is words: one prints
# "West Bromwich Albion" where the other prints "West Brom", one prints
# "Queens Park Rangers" where the other prints "QPR". So the comparison is
# made word by word, and a shortened word only counts as evidence when
# there is enough of it left to be sure — a rule reached by measurement,
# not by taste. The first draft compared whole names by their beginnings,
# and the gate caught it merging Mainz into Monza while failing to merge
# Man Utd into Manchester United. Both faults came from the same mistake:
# treating a name as one string when the pages differ in its words.
MERGE_SLACK = timedelta(minutes=1)
# Far enough apart to be a different kickoff, close enough to be the same
# match with one page's clock wrong. Used only to notice that.
DRIFT_WINDOW = timedelta(hours=6)

# Nicknames and contractions no structural rule can reach: nothing in the
# letters of "Wolves" leads to "Wolverhampton Wanderers". Written out
# rather than guessed at, and only where the pages were seen to disagree.
ALIASES = {
    "man utd": "manchester united",
    "man united": "manchester united",
    "man city": "manchester city",
    "wolves": "wolverhampton wanderers",
    "spurs": "tottenham hotspur",
    "west brom": "west bromwich albion",
    "west bromwich": "west bromwich albion",
    "brighton": "brighton and hove albion",
    "nott'm forest": "nottingham forest",
    "notts forest": "nottingham forest",
    "sheff utd": "sheffield united",
    "sheff wed": "sheffield wednesday",
    "qpr": "queens park rangers",
    "psg": "paris saint-germain",
    "inter": "inter milan",
    "internazionale": "inter milan",
    "atletico madrid": "atletico de madrid",
    "bayern": "bayern munich",
    "dortmund": "borussia dortmund",
}

# One word written two ways, which is not a nickname and so does not
# belong in the table above: every page that writes "Utd" means "United".
WORD_ALIASES = {"utd": "united", "utd.": "united", "atl": "atletico",
                "st": "saint", "st.": "saint"}

# Words that hang off the end of a club's name and that a listings page
# may or may not bother to print. A trailing word outside this list is
# part of the club, not furniture: dropping "Miami" turns Inter Miami into
# Inter, which is a different club in a different hemisphere.
#
# Held as skeletons, because that is what they are compared against —
# "united" is "anatad" by the time the comparison happens, and a set of
# plain words would quietly never match anything.
CLUB_TAIL = {"united", "city", "town", "county", "athletic", "albion",
             "wanderers", "rovers", "hotspur", "hotspurs", "club", "calcio"}

# Words a club's name can START with that a listings page may leave off.
#
# The comparison lines names up from the left, so a page writing "Betis"
# where the other writes "Real Betis" had nothing to line up: the first
# word of one was the second word of the other, and Betis v Real Madrid
# was published twice on one board. Spanish football is full of this —
# Real Betis, Real Sociedad, Real Valladolid — so it is worth a rule
# rather than an entry in the table above.
#
# Kept to honorifics, deliberately. "Atletico" is not here: dropping it
# would make "Atletico Madrid" and "Real Madrid" both into "Madrid", and
# they are not the same club playing itself.
CLUB_LEAD = {"real", "club"}

# A shortened word is evidence only with this much of it written, and this
# much of the full word left over. "Brom" against "Bromwich" is four
# letters written and four dropped. "Manz" against "Manza" is one letter
# apart, which is Mainz and Monza, and is not evidence of anything.
WORD_FLOOR = 3


def expand(name: str) -> str:
    """A club's name with a nickname or contraction written out in full."""
    return ALIASES.get(norm(name).casefold().replace(".", ""), name)


def words_of(name: str) -> list[str]:
    """The name broken into words, each reduced to its skeleton."""
    words = [word for word in
             re.split(r"[^0-9A-Za-z\u00C0-\u024F]+", name) if word]
    skeletons = [club_skeleton(WORD_ALIASES.get(word.casefold(), word))
                 for word in words]
    return [skeleton for skeleton in skeletons if skeleton]


# Built once, from the words above, so the two can never drift apart.
TAIL_SKELETONS = {club_skeleton(word) for word in CLUB_TAIL}
LEAD_SKELETONS = {club_skeleton(word) for word in CLUB_LEAD}


def initials_of(name: str) -> str:
    """The first letter of every word, which is what an initialism is."""
    return "".join(word[0] for word in re.split(r"[^A-Za-z]+", name)
                   if word).casefold()


def written_as_initials(name: str) -> str:
    """The letters of a name written the way QPR and PSG are written.

    Capitals only, three or four of them. A name in mixed case is a name,
    and two capitals are too few to be evidence — "AC" opens Milan,
    Ajaccio and a dozen others.
    """
    letters = re.sub(r"[^A-Za-z]", "", name)
    return letters.casefold() if letters.isupper() and 3 <= len(letters) <= 4 \
        else ""


def same_word(short: str, long: str) -> bool:
    """One word against another, the first possibly written shorter."""
    if short == long:
        return True
    return (long.startswith(short) and len(short) >= WORD_FLOOR
            and len(long) - len(short) >= WORD_FLOOR)


def same_side(first: str, second: str) -> bool:
    """Whether two Latin spellings name one club, one of them shortened."""
    for short, long in ((first, second), (second, first)):
        as_initials = written_as_initials(short)
        if as_initials and as_initials == initials_of(long):
            return True

    first, second = expand(first), expand(second)
    left, right = words_of(first), words_of(second)
    if not left or not right:
        return False
    if left == right:
        return True

    if lines_up(left, right):
        return True
    # And again with an honorific dropped from the front of either — see
    # CLUB_LEAD. Tried second so a name that already matches is never
    # shortened, and only ever ONE step, so nothing is whittled down to
    # its last word.
    if lines_up(without_lead(left), without_lead(right)):
        return True
    # And across the scripts. The third page writes its clubs in Arabic,
    # and epg_lib answers that question properly — measured thresholds,
    # cross-script only, and it refuses within one script, which is why
    # everything above exists at all.
    return same_club_across_scripts(first, second)


def without_lead(words: list[str]) -> list[str]:
    """The name with a leading honorific removed, if it has one to spare."""
    return words[1:] if len(words) > 1 and words[0] in LEAD_SKELETONS \
        else words


def lines_up(left: list[str], right: list[str]) -> bool:
    """Whether one list of words is the other with words left off the end."""
    if not left or not right:
        return False
    short, long = (left, right) if len(left) <= len(right) else (right, left)
    # Word for word, as far as the shorter name goes.
    if not all(same_word(word, long[at]) for at, word in enumerate(short)):
        return False
    # Whatever the shorter name left off has to be furniture, not a club.
    return all(word in TAIL_SKELETONS for word in long[len(short):])


def same_club_across_scripts(first: str, second: str) -> bool:
    """One club written in Arabic and in Latin — epg_lib's own answer.

    Strictly epg_lib's, and it stays that way. The obvious next move was
    to loosen it here, where a kickoff minute is already agreed and could
    carry a weaker name test — so the thresholds were measured over
    thirteen real cross-script pairs and ten false ones before writing
    any. They overlap, badly: تولوز against Toulon scores 0.800 while
    باشاكشهير against Basaksehir scores 0.640, and الهلال against Al Ahly
    reaches 0.750. No ratio separates them, which is precisely what
    epg_lib says in its own comments.

    So this catches only what an exact skeleton catches — الأهلي/Al Ahly,
    كولن/Koln, موناكو/Monaco — and the third page is kept to competitions
    the other two do not carry, where there is nothing to collide with.
    """
    return same_club(first, second)


def same_match(first: str, second: str) -> bool:
    """Whether two "A - B" titles name one fixture. Both sides must agree.

    One side agreeing is a coincidence — Real Madrid plays somebody every
    week. Two sides agreeing at one kickoff minute is one match written
    twice.
    """
    left = [side.strip() for side in (first or "").split(" - ")]
    right = [side.strip() for side in (second or "").split(" - ")]
    if len(left) != 2 or len(right) != 2 or not all(left) or not all(right):
        return False
    return same_side(left[0], right[0]) and same_side(left[1], right[1])


def absorb(into: dict, extra: dict) -> None:
    """Add what the second page knew and the first one did not."""
    for channel in extra["channels"]:
        if channel not in into["channels"]:
            into["channels"].append(channel)
    if not into["competition"]:
        into["competition"] = extra["competition"]


def screen_key(name: str) -> str:
    """A channel name reduced to what two pages would spell the same."""
    return re.sub(r"[^a-z0-9\u0600-\u06ff]", "", name.casefold())


def already_on_air(event: dict, collected: list[dict]) -> bool:
    """Is this fixture already on the board, under another spelling?

    Decided on the broadcaster and the minute, never on the club names.
    A channel showing two different matches at one minute is not a thing
    that happens, so a match already listed at that minute on that channel
    is this match — however the two pages spell its teams.

    Used only for the third page, and deliberately. Within the other two,
    a channel name is sometimes a bouquet rather than a channel —
    "Thmanyah Channels" carries Al Shabab and Al Ahli at the same minute —
    and this rule would fold two real matches into one. The third page
    names single channels.
    """
    keys = {screen_key(name) for name in event["channels"] if screen_key(name)}
    if not keys:
        return False                # nothing to compare; keep the fixture
    for other in collected:
        if abs(other["start"] - event["start"]) > MERGE_SLACK:
            continue
        if keys & {screen_key(name) for name in other["channels"]}:
            return True
    return False


def unify(primary: list[dict], secondary: list[dict]) -> list[dict]:
    """One list of matches from two pages, each match appearing once.

    The first page leads: where both name a match, its title and its first
    channel are the ones a viewer sees, and the second page's channels are
    appended behind them. That ordering is not cosmetic — only one channel
    fits on a row, and the viewer asked for the one they can actually
    tune to.
    """
    merged = [dict(event, channels=list(event["channels"]))
              for event in primary]
    joined = added = 0
    drifted: list[int] = []

    for event in secondary:
        found = None
        for already in merged:
            if not same_match(already["title"], event["title"]):
                continue
            gap = already["start"] - event["start"]
            if abs(gap) <= MERGE_SLACK:
                found = already
                break
            if abs(gap) <= DRIFT_WINDOW:
                # The same fixture, at two different times. One page's
                # clock has moved; both cannot be right.
                drifted.append(round(gap.total_seconds() / 60))
        if found is not None:
            absorb(found, event)
            joined += 1
        else:
            merged.append(dict(event, channels=list(event["channels"])))
            added += 1

    log(f"  merge: {joined} match(es) on both pages, "
        f"{added} the second page had alone")

    # Two pages naming the same fixtures at times that never coincide is
    # exactly what a source silently changing its clock looks like, and it
    # is the fault that cost this channel an hour twice over. It is worth
    # saying out loud the moment it happens rather than after a reader
    # notices their match is over.
    if drifted and len(drifted) > joined:
        drifted.sort()
        log(f"  WARN the pages name {len(drifted)} of the same fixture(s) "
            f"at different times, median {drifted[len(drifted) // 2]:+d} "
            f"min apart, and agree on only {joined} — one clock has moved")
    return sorted(merged, key=lambda event: event["start"])


# Which two of a row's channels a viewer is shown, in the order a reader
# asked for: Arabic, English, American, Turkish, then everywhere else.
#
# It was source order, and source order is the order a British listings
# page happens to print its pills in. So four of the seven rows that had
# two channels spent the second on something neither the region nor
# America can open — "MBC Shahid Sports · BBC iPlayer",
# "MBC Shahid Sports · Premier Sports 1" — while the Fox or the beIN that
# WAS collected sat behind the "+1".
#
# Ordering only decides which names win the two slots. A row holding
# nothing but an Arabic channel and a British one still shows both; this
# changes what a row does with its third and fourth.
ARABIC_LETTERS = re.compile(r"[؀-ۿݐ-ݿ]")
ENGLISH_FEED = re.compile(r"\bEN\b", re.I)
AMERICAN = re.compile(r"\bUS\b|\bfox\b|\bnbc\b|\bcbs\b|\bespn\b"
                      r"|\busa network\b|\bparamount\b|\bpeacock\b"
                      r"|\btelemundo\b|\btudn\b|\bunivision\b", re.I)
TURKISH = re.compile(r"\bTR\b|\btabii\b|\btrt\b|\bs sport\b", re.I)
# The names a Gulf or Levantine viewer actually has. beIN written without
# a mark is Doha's, which is the whole point of marking the other two.
ARAB_CHANNEL = re.compile(r"\bbein\b|\balwan\b|\bthmanyah\b|\bon sport\b"
                          r"|\bon time\b|\bshahid\b|\bmbc\b|\bssc\b"
                          r"|\balkass\b|\bal kass\b|\bad sports\b"
                          r"|\bdubai\b|\bshasha\b|\bstarzplay\b"
                          r"|\brotana\b|\bsaudi\b|\bjordan\b", re.I)


def where_from(name: str) -> int:
    """The reader's order, as a number that sorts."""
    if TURKISH.search(name):
        return 3
    if AMERICAN.search(name):
        return 2
    if ENGLISH_FEED.search(name):
        return 1
    if ARABIC_LETTERS.search(name) or ARAB_CHANNEL.search(name):
        return 0
    return 4


def in_the_readers_order(channels: list[str]) -> list[str]:
    """Sorted into those tiers, with the second slot spent on something else.

    Sorting alone put the reader's own tier first and then filled the
    second slot with more of it: "beIN SPORTS 3 · beIN SPORTS 2" is one
    broadcaster twice, and the Fox that was collected for that match sat
    behind the "+6". Two slots and Arabic ranked first meant the American
    channels this guide went and found could almost never be seen.

    So the second slot goes to the best channel from a DIFFERENT tier —
    still in the reader's order, so American beats Turkish beats the
    rest. One from here, one from somewhere else you might have.

    Nothing is dropped or hidden by this; the rest keep their order
    behind the count. And a row whose channels are all of one kind is
    left exactly as it was, because there is nothing else to offer.
    """
    ordered = sorted(channels, key=where_from)
    taken, tiers = [], set()
    for index, name in enumerate(ordered):
        if len(taken) == MAX_CHANNELS:
            break
        if where_from(name) not in tiers:
            taken.append(index)
            tiers.add(where_from(name))
    shown = [ordered[index] for index in taken]
    rest = [name for index, name in enumerate(ordered) if index not in taken]
    return shown + rest


def channels_of(event: dict) -> str:
    """The channel a viewer is told to turn to — a real one, or none.

    real_channels() was applied when deciding whether to KEEP a match and
    then not applied to what is printed, so a match kept because beIN
    carries it could still be labelled "OneFootball" — the pay-per-view
    app the reader asked to stop seeing, still on the screen after it was
    supposedly removed. What is shown is now filtered by the same rule
    that decided the match belonged here at all.
    """
    real = in_the_readers_order(real_channels(event["channels"]))
    shown = real[:MAX_CHANNELS]
    more = len(real) - len(shown)
    return " · ".join(shown) + (f" +{more}" if more > 0 else "")


def fixture_of(event: dict) -> str:
    """The one line a viewer is actually after: who, and on what."""
    channels = channels_of(event)
    return f"{event['title']} · {channels}" if channels else event["title"]


def when(start: datetime, now: datetime, lead_in: bool = True) -> str:
    """How long until this kicks off, rather than the hour it kicks off at.

    Asked for outright: a viewer glancing at the page wants "in forty
    minutes", not a clock they then have to subtract from. The words are
    spelled out rather than abbreviated for the reason countdown_label
    exists — single letters drift away from their numbers on a line that
    also carries Latin club names, and "19 س و30 د" was read three
    different ways on a television.

    A printed countdown is frozen the moment the file is written, and the
    file is read minutes or tens of minutes later, so a precise number is
    a number that is wrong. Near kickoff, where being wrong matters, this
    states an upper bound instead: the time left only ever shrinks, so
    "less than an hour" written at fifty minutes is still true at five.
    Coarser, and never a lie.

    Further out the bound is pointless — the gap between the build and the
    reading is nothing beside three hours — so the exact wording stands.
    """
    if start <= now:
        return "الآن"
    minutes = (start - now).total_seconds() // 60
    lead = "بعد " if lead_in else ""
    for step in NEAR_STEPS:
        if minutes <= step:
            return f"{lead}أقل من {countdown_label(step)}"
    return f"{lead}{countdown_label(minutes)}"


def clock_and_wait(start: datetime, now: datetime) -> str:
    """The hour AND the wait, which answer different questions.

    The countdown is what a viewer wants at a glance, but it is written
    once and read later, so it can only ever be as fresh as the last
    build. The clock cannot go stale at all. Carrying both means the line
    always holds one number that is certainly right, and one that is
    easier to act on.
    """
    # No "بعد" here: the clock in front of it already says these are two
    # readings of the same kickoff, and every character spent is a
    # character of club or channel name the panel truncates instead.
    return f"{start.astimezone(VIEWER):%H:%M} {when(start, now, lead_in=False)}"


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """Midnight to midnight in the viewer's clock, expressed in UTC."""
    opens = datetime.combine(day, time(0, 0), VIEWER).astimezone(UTC)
    return opens, opens + timedelta(days=1)


def day_name(day: date) -> str:
    return f"{ARABIC_DAY[day.weekday()]} {day:%d/%m}"


def day_title(day: date, events: list[dict], now: datetime) -> str:
    """What the grid shows for this day, on one line.

    The status rides at the FRONT. A television truncates a title from the
    right, so anything put after the names is thrown away before a viewer
    ever sees it — which is exactly how the previous shape lost every one
    of its countdowns.
    """
    if not events:
        return in_reading_order(f"{day_name(day)} — {NOTHING_TODAY}")

    live = [e for e in events if e["start"] <= now < e["start"] + MATCH_ON_AIR]
    if live:
        event = live[-1]
        return in_reading_order(
            f"{LIVE_MARK} مباشر {isolate('·')} {isolate(fixture_of(event))}",
            names=event["title"])

    ahead = [e for e in events if e["start"] > now]
    if ahead:
        event = ahead[0]
        minutes = (event["start"] - now).total_seconds() // 60
        return in_reading_order(
            f"{NEXT_MARK} بعد {countdown_label(minutes)} {isolate('·')} "
            f"{isolate(fixture_of(event))}",
            names=event["title"])

    # arabic_count carries the number itself — "مباراتان", "3 مباريات" —
    # so putting a numeral in front of it would say the count twice.
    count = arabic_count(len(events), "مباراة", "مباراتان", "مباريات", "مباراة")
    if day == now.astimezone(VIEWER).date():
        return in_reading_order(f"انتهت مباريات اليوم — {count}")
    return in_reading_order(f"مباريات {day_name(day)} — {count}")


def day_page(day: date, events: list[dict], now: datetime) -> str:
    """The whole day on one page — what a viewer sees without pressing.

    This is the guide. The grid row above it only says which match is next;
    everything a viewer came for is here, and highlighting the channel is
    enough to see it.

    Every line here is a line of a television screen, and a page that does
    not fit in one screenful is not one page. So: matches already over are
    dropped, kickoffs that share a time share a line, one channel is named
    per match, and there is no blank line under the header.

    Each line is then wrapped in an isolate that states its direction, for
    the same reason the title is. The header is Arabic, so a player lays
    the whole block out right to left, and a line that reads
    "07:00 in three hours  Sassuolo - Frosinone" came out on a television
    with the clock at the far end — the club names dragged the line one
    way and the countdown the other. Fixing the title alone left every
    line under it reversed.
    """
    header = f"مباريات {day_name(day)} — {VIEWER_NAME}"
    left = [e for e in events if e["start"] + MATCH_ON_AIR > now]
    if not left:
        return f"{header}\n{'انتهت مباريات اليوم' if events else NOTHING_TODAY}"

    # Kickoffs at the same minute are one entry, not one each.
    slots: list[list[dict]] = []
    for event in left:
        if slots and event["start"] == slots[-1][0]["start"]:
            slots[-1].append(event)
        else:
            slots.append([event])

    coming = next((e for e in left if e["start"] > now), None)
    lines = [header]
    for slot in slots:
        if any(e["start"] <= now for e in slot):
            mark = LIVE_MARK
        elif coming in slot:
            mark = NEXT_MARK
        else:
            mark = "  "
        opening = f"{mark} {clock_and_wait(slot[0]['start'], now)}  "
        line, named = opening, []
        for event in slot:
            fixture = fixture_of(event)
            if line != opening and len(line) + 3 + len(fixture) > LINE_BUDGET:
                lines.append(in_reading_order(line, names=" ".join(named)))
                # A continuation of the same kickoff: the time is already
                # on the line above, and repeating it reads as two slots.
                line, named = "        ", []
            line += ("" if line in (opening, "        ") else " ، ") + fixture
            named.append(event["title"])
        lines.append(in_reading_order(line, names=" ".join(named)))
    return "\n".join(lines)


def publish_board(index: int, day: date, events: list[dict], now: datetime,
                  *, page: int = 1, pages: int = 1) -> str | None:
    """Draw the day's board, keep it only if it differs, return its URL.

    Rewriting an identical picture every ten minutes would commit a fresh
    copy of it every ten minutes, so the bytes are compared before
    anything is written.
    """
    name = f"today_matches_{index}.png"
    path = os.path.join(BOARD_DIR, name)
    try:
        from match_board import draw_board

        board = draw_board(
            day, events, now, VIEWER, MATCH_ON_AIR,
            title=CHANNEL_AR, subtitle=f"بث اليوم المباشر · {VIEWER_NAME}",
            weekday=ARABIC_DAY[day.weekday()], page=page, pages=pages)
        drawn = io.BytesIO()
        board.convert("RGB").convert(
            "P", palette=Image.ADAPTIVE, colors=BOARD_COLOURS).save(
                drawn, format="PNG", optimize=True)
        fresh = drawn.getvalue()
    except Exception as exc:
        warn(f"the board for {day} could not be drawn ({exc}) — the day "
             f"still publishes as text")
        return BOARD_URL + "/" + name if os.path.exists(path) else None

    os.makedirs(BOARD_DIR, exist_ok=True)
    if not os.path.exists(path) or open(path, "rb").read() != fresh:
        with open(path, "wb") as out:
            out.write(fresh)
        log(f"  board {name} redrawn ({len(fresh) // 1024} KB)")
    return f"{BOARD_URL}/{name}"


def say_what_was_dropped(everything: list[dict], days: list[date]) -> None:
    """Name, day by day, the competitions collected and not shown.

    A reader asked why Thursday looked thin and Friday looked empty, and
    answering it took a purpose-built probe and a trip to a runner —
    because the build said only how many matches it kept, never what it
    threw away. Those are different questions with the same symptom: a
    short list. A source that has stopped answering and a filter that is
    quietly eating a whole league look identical from the sofa.

    So the build now says both. It costs a few lines in a log nobody reads
    until something is wrong, which is exactly when this is the first
    thing anybody wants.
    """
    dropped: dict[date, Counter] = defaultdict(Counter)
    for event in everything:
        if not wanted(event):
            day = event["start"].astimezone(VIEWER).date()
            dropped[day][event["competition"] or "(unnamed competition)"] += 1

    for day in days:
        names = dropped.get(day)
        if not names:
            continue
        listed = ", ".join(f"{name} ×{count}"
                           for name, count in names.most_common(8))
        rest = len(names) - min(len(names), 8)
        log(f"  {day}: {sum(names.values())} collected and not shown — "
            f"{listed}" + (f", and {rest} more" if rest else ""))


def say_which_rows_are_thin(events: list[dict]) -> None:
    """Name the matches that ended with fewer than two channels.

    A reader asked for two channels on every row, and whether that
    happens is not a thing anybody can settle by adding a source and
    hoping. Some matches have two, some have one, some have none, and
    which is which changes every hour as broadcasters publish.

    Counting them is how the next source gets chosen: a run that says
    "9 of 30 name one channel, 2 name none" points at the gap, and the
    fixtures it lists say which competition to go looking for. The
    alternative is what happened before — a photograph from the sofa.
    """
    thin = [event for event in events
            if len(real_channels(event["channels"])) < 2]
    none_at_all = [event for event in thin
                   if not real_channels(event["channels"])]
    if not thin:
        log(f"  every one of {len(events)} match(es) names two channels")
        return
    log(f"  {len(events) - len(thin)} of {len(events)} match(es) name two "
        f"channels; {len(thin) - len(none_at_all)} name one and "
        f"{len(none_at_all)} name none")
    for event in thin[:12]:
        named = real_channels(event["channels"])
        log(f"    thin  {event['start']:%m-%d %H:%M}Z  {event['title']}"
            f"   │ {event['competition']} │ {', '.join(named) or '—'}")


def build() -> int:
    now = datetime.now(UTC)
    session = requests.Session()
    session.headers.update({
        "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
        "Accept-Language": "ar,en;q=0.8,tr;q=0.6",
    })
    try:
        html = fetch(session, SOURCE).text
    except Exception as exc:
        warn(f"livefootballtv is unreachable ({exc}) — the previous guide "
             f"stays exactly as it is")
        return 1

    # One window, computed once, handed to both pages and to the board
    # list alike. Two places deciding this independently is what put an
    # empty board on the screen for a full day of football.
    floor, ceiling = window_floor(now), window_ceiling(now)
    everything = unify(collect(html, now, floor, ceiling),
                       live_football_on_tv.fetch_events(
                           session, floor, ceiling))
    # The third page last, narrowed to what it is for — and then to what
    # is not already on the board.
    #
    # "Nothing to collide with" was wrong: the first page does carry some
    # of Egypt's league, so الجونة - المقاولون العرب arrived beside
    # El Gouna FC - El-Mokawloon and Wednesday showed both. The names
    # cannot settle it — no threshold separates تولوز from Toulon — but
    # something else can, and it is a fact rather than a guess: one channel
    # cannot show two matches at the same minute.
    asked = [event for event in yallakora.fetch_events(session, floor, ceiling)
             if any(name in event["competition"] for name in YALLAKORA_ONLY)]
    fresh = [event for event in asked if not already_on_air(event, everything)]
    log(f"  yallakora: {len(asked)} in the competitions asked for, "
        f"{len(fresh)} the board did not already have")
    everything = unify(everything, fresh)
    # Kept, and stripped of what is not a channel in the same breath.
    #
    # real_channels() decided which matches belonged here and was then not
    # applied to what those matches SAY, so a match kept because beIN
    # carries it went to the screen labelled "OneFootball" — removed in
    # one place and still on the television. Filtering here, once, is what
    # makes it true everywhere: the board, the panel and the playlist all
    # read this list and none of them can now forget.
    events = [dict(event, channels=real_channels(event["channels"]))
              for event in everything if wanted(event)]

    # And the channels this repository already publishes for itself. They
    # know something no listings page does — which of THIS reader's
    # channels is carrying a match — and beIN SPORTS 1 in Istanbul is
    # marked TR so it is not mistaken for beIN SPORTS 1 in Doha.
    #
    # Applied after the filtering, because a guide of ours is not evidence
    # that a match belongs on the channel; it is evidence of where to
    # watch one that already does.
    own_guides.add_channels(events, {
        "Spor Ekranı": spor_ekrani.broadcasts(session),
        "livesoccertv": live_soccer_tv.broadcasts(session),
    })

    # Counted before the placeholder goes in, because "لم تُعلن القناة"
    # is a sentence and not a channel, and a row wearing it has none.
    say_which_rows_are_thin(events)

    # Sorted once, here, so the printed line and the drawn board show the
    # same two names — they each take the first two and would otherwise
    # disagree about which those are.
    for event in events:
        event["channels"] = in_the_readers_order(event["channels"])

    for event in events:
        if not event["channels"]:
            event["channels"] = [CHANNEL_UNANNOUNCED]
    log(f"  {len(everything)} match(es) in the window, "
        f"{len(events)} in a competition worth showing")
    for event in events[:12]:
        log(f"  {event['start']:%m-%d %H:%M}Z  {event['title']}"
            f"   │ {event['competition']}")

    days = days_of(now)
    say_what_was_dropped(everything, days)

    tv = ET.Element("tv", {"generator-info-name": "Today's Matches"})
    channel = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(channel, "icon", {"src": LOGO})
    ET.SubElement(channel, "display-name", {"lang": "ar"}).text = CHANNEL_AR
    ET.SubElement(channel, "display-name", {"lang": "en"}).text = CHANNEL_EN

    # Today first, then every further day the page reached, so a viewer
    # scrolling forward finds tomorrow rather than the end of the guide.
    by_day: dict[date, list[dict]] = {day: [] for day in days}
    for event in events:
        day = event["start"].astimezone(VIEWER).date()
        if day in by_day:
            by_day[day].append(event)

    # A day with more matches than a screen holds is drawn over as many
    # boards as it takes, numbered straight through, so the slideshow runs
    # them in order without knowing anything about days.
    board_no = 0
    for day in days:
        events_today = by_day[day]
        chunks = [events_today[at:at + MAX_ON_BOARD]
                  for at in range(0, len(events_today), MAX_ON_BOARD)] or [[]]
        first_board = None
        for page, chunk in enumerate(chunks, start=1):
            url = publish_board(board_no, day, chunk, now,
                                page=page, pages=len(chunks))
            first_board = first_board or url
            board_no += 1

        opens, closes = day_bounds(day)
        add_programme(tv, CHANNEL_ID, opens, closes,
                      day_title(day, events_today, now),
                      day_page(day, events_today, now),
                      icon=first_board)
        log(f"  {day} -> {len(events_today)} match(es) over "
            f"{len(chunks)} board(s)")

    ok = write_xml_atomic(tv, OUTPUT, generator_name="Today's Matches",
                          guard_regression=False, min_programmes=1)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
