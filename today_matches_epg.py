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
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import io

import requests
from bs4 import BeautifulSoup
from PIL import Image
import xml.etree.ElementTree as ET

import live_football_on_tv
from epg_lib import (
    MATCH_ON_AIR, add_programme, arabic_count, club_skeleton, countdown_label,
    fetch, in_reading_order, isolate, log, norm, warn, write_xml_atomic,
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

# How far forward to publish. The page carries a couple of days and a
# viewer scrolling ahead should find them.
KEEP_AHEAD = timedelta(days=2)

# One channel per match. The page has to fit on a television screen in one
# go, and every extra name pushes a line into wrapping onto a second — so
# the list costs two lines for one match and the day stops fitting. The
# first channel named is the one the source lists first.
MAX_CHANNELS = 1

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
    # Nowhere real to watch it is the same as not being on.
    if not real_channels(event["channels"]):
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


def window_floor(now: datetime) -> datetime:
    """Where the guide starts reading: the top of the viewer's today.

    The whole of their today, however much of it has already been played —
    the page is a list of the day, not of what is left of it. Both sources
    are held to this same edge, or a match would appear on one board and
    not the other purely by which page it came off.
    """
    return datetime.combine(now.astimezone(VIEWER).date(), time(0, 0),
                            VIEWER).astimezone(UTC)


def collect(html: str, now: datetime) -> list[dict]:
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

    floor = window_floor(now)

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

        if not (floor <= start <= now + KEEP_AHEAD):
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

    short, long = (left, right) if len(left) <= len(right) else (right, left)
    # Word for word, as far as the shorter name goes.
    if not all(same_word(word, long[at]) for at, word in enumerate(short)):
        return False
    # Whatever the shorter name left off has to be furniture, not a club.
    return all(word in TAIL_SKELETONS for word in long[len(short):])


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


def channels_of(event: dict) -> str:
    """The channel a viewer is told to turn to — a real one, or none.

    real_channels() was applied when deciding whether to KEEP a match and
    then not applied to what is printed, so a match kept because beIN
    carries it could still be labelled "OneFootball" — the pay-per-view
    app the reader asked to stop seeing, still on the screen after it was
    supposedly removed. What is shown is now filtered by the same rule
    that decided the match belonged here at all.
    """
    real = real_channels(event["channels"])
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

    everything = unify(collect(html, now),
                       live_football_on_tv.fetch_events(
                           session, now, KEEP_AHEAD, window_floor(now)))
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
    log(f"  {len(everything)} match(es) in the window, "
        f"{len(events)} in a competition worth showing")
    for event in events[:12]:
        log(f"  {event['start']:%m-%d %H:%M}Z  {event['title']}"
            f"   │ {event['competition']}")

    tv = ET.Element("tv", {"generator-info-name": "Today's Matches"})
    channel = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(channel, "icon", {"src": LOGO})
    ET.SubElement(channel, "display-name", {"lang": "ar"}).text = CHANNEL_AR
    ET.SubElement(channel, "display-name", {"lang": "en"}).text = CHANNEL_EN

    # Today first, then every further day the page reached, so a viewer
    # scrolling forward finds tomorrow rather than the end of the guide.
    today = now.astimezone(VIEWER).date()
    last = (now + KEEP_AHEAD).astimezone(VIEWER).date()
    days: list[date] = []
    day = today
    while day <= last:
        days.append(day)
        day += timedelta(days=1)

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
