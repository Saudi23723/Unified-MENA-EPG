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

import dubai_time
import jordan_football
import live_football_on_tv
import live_soccer_tv
import own_guides
import spor_ekrani
import sportsnet
import tsn
import yallakora
from epg_lib import (
    MATCH_ON_AIR, add_programme, arabic_count, club_skeleton, countdown_label,
    drop_simulcasts, fetch, in_reading_order, isolate, log, norm, same_club,
    warn, write_xml_atomic,
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
BOARD_PREFIX = "today_matches_"
DUBAI_OUTPUT = "dubai_matches_epg.xml"
DUBAI_CHANNEL_ID = "TodayMatchesDubai"
DUBAI_BOARD_PREFIX = "dubai_matches_"

# THE SECOND CLOCK'S OUTPUTS — same matches, same drawing, every time
# printed in the Gulf's (Asia/Dubai): "copy full links for 4 channels +
# second link set with all times in UAE time (Asia/Dubai)".
#
# A FRESH BOARD STEM, not an extension of the first's, because the
# encoder owns its segments by prefix: a board whose name begins with
# today_matches_ rides the first clock's reel whatever its suffix says,
# and half a lap in a zone the reel never said is worse than none.
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

# What a row says when the fixture is real and the broadcaster is not yet
# named. wanted() guarantees this only ever replaces an empty list, never
# a list of shops.
CHANNEL_UNANNOUNCED = "لم تُعلن القناة"

LIVE_MARK = "🔴"
NEXT_MARK = "⏳"
# The third state wears a mark too, and for a reason a screenshot made
# plain: "التالي و المباشر مش على نفس الخط". A row whose status is
# "not yet" used to open with two spaces, which is one width on a page
# that renders it as text and another on a television that renders the
# emoji as a wide cell — so the clock after it landed one column on the
# waiting rows and another on the marked ones. A white circle is the
# same width class as the red circle beside it, on every renderer, and
# it says the same thing: not live, not next, just waiting.
WAIT_MARK = "⚪"

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
    # Turkey's second tier, asked for after three of its matches were
    # photographed on TRT Spor and found to be on no page this board read.
    "tff 1. lig", "trendyol 1. lig", "1. lig",
    # The Canadian leagues the Canadian feeds themselves name — asked
    # for with the channels that carry them, and wanted by the word the
    # broadcaster's own title prints.
    "mls", "canadian premier league", "women's super league",
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

# THE NEVER-LIST, and why it is not just an absence from the lists above.
#
# "CH1 soccer-ONLY: remove NWSL and the AFL women's series, and the
# future of these two" — removing a league from the WANTED lists is only
# half of that, because the league comes back the day any page, feed or
# guide starts naming it again. So the families that were asked off are
# refused outright, on the competition and on the title both, before any
# wanted test runs:
#
#   nwsl   the American women's league, however a page spells it —
#          "NWSL", "NWSL Women", the "NWSL+" its streaming arm prints
#   nsl    the Northern Super League, Canada's women's league in the
#          same family and new the same season — a "future of these",
#          and measured landing on this board labelled "MLS" by the
#          fallback below, which is worse than not showing: it says a
#          men's league is on
#   aflw / afl women / women's afl
#          Australia's women's football series
#   nrlw / nrl women / women's nrl
#          the women's rugby-league series the Canadian feeds carry
#          under sport names this board could one day be fed
#
# England's Women's Super League is NOT here: it was asked for by name
# and stays. FIFA's women's competitions are not here either — they are
# international football, wanted by the "fifa" and "world cup" words
# above, and a women's World Cup qualifier belongs on a soccer board as
# much as any other international.
#
# Word-bounded on purpose: "nsl" without edges would refuse a page that
# writes "Mens' League" carelessly, and "wsl" is not listed at all
# because it sits INSIDE "nwsl" — the family match is done by these
# whole words, never by scrap.
NEVER_LISTED = re.compile(
    r"\bnwsl\b|\bnsl\b|\baflw\b|\bnrlw\b"
    r"|\bafl\s+women\b|women'?s\s+afl\b"
    r"|\bnrl\s+women\b|women'?s\s+nrl\b",
    re.I)

# What the third page is asked for, and nothing else.
#
# Every one of these is a competition the other two pages were measured
# not to carry, and each is here because a reader photographed a fixture
# missing from it: Jordan's league, Egypt's league — الأهلي v سموحة was
# on neither page — and Turkey's, where Başakşehir v Galatasaray was
# missing too. Outside these it would be adding European football both
# other pages already have, in Arabic, with no safe way to tell it is the
# same match. Widen this only against a measurement.
#
# AND TURKEY IS NOT ON THIS LIST ANY MORE, which it was, and the screen
# is what took it off:
#
#     09:50   Fenerbahçe - Beşiktaş     الدوري التركي الممتاز   beIN 5
#     10:00   فنربخشة - بشكتاش          الدوري التركي           لم تُعلن القناة
#
# One match, twice, ten minutes apart, in two scripts —
# "شو هاد بتسميه؟", photographed off the television.
#
# Nothing downstream could have caught it. already_on_air settles a
# duplicate on the CHANNEL, and the second row names no channel at all;
# the names cannot settle it either, because فنربخشة against Fenerbahçe
# is a transliteration and no threshold that joins them leaves Toulon and
# تولوز apart. And the two clocks disagree by ten minutes, so nothing
# keyed on the minute sees one fixture.
#
# The rule that DOES settle it was already written, one page over:
# Turkey's fixtures come from Spor Ekranı and from this repository's own
# guides — beIN Qatar, beIN Turkey, Alwan — and not from a general
# listings page. yallakora is a general listings page. It was let in here
# because Başakşehir v Galatasaray was missing when this was measured,
# and it is not missing now: beIN's own feed carries the Süper Lig with
# the channel named and the live airing marked in beIN's own title.
YALLAKORA_ONLY = (
    "الدوري المصري", "كأس مصر", "السوبر المصري",
    "الدوري الأردني", "كأس الأردن", "درع الاتحاد الأردني",
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
    # England's two cups as beIN's own guide has them named here. The
    # Latin forms are already in WANTED_PARTS — "fa cup", "efl",
    # "carabao" — and these are the same competitions arriving in Arabic
    # from beIN's guide rather than in English from a listings page.
    "كأس الاتحاد الإنجليزي", "كأس الرابطة الإنجليزية",
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
#
# "app" is a WORD here, not a scrap of one. Measured after the MLS
# vanished: every Apple TV fixture was being refused by this list,
# because "app" sits inside "Apple" — and Apple TV is where the whole
# of Major League Soccer is, measured forty-four fixtures on the day
# this was checked, every one of them Apple's alone, not one on beIN
# or Sky or TSN. The rule this list was written for still holds, in
# the words the other two source files already use: an app is "STC
# App", "Thmanyah App", "LigaFUTVE App", the word standing by itself —
# and the word boundary is what keeps the league on the board without
# letting a single shop through. (DAZN and Amazon Prime Video are not
# apps by this test; both name themselves without the word.)
NOT_A_CHANNEL = re.compile(
    r"onefootball|ppv|youtube|\bapps?\b|tv\+|plus tv"
    r"|federation|official site|club tv"
    # "BBC Sport Website" reached the board as a channel. A page is not
    # something a television can be turned to, and it took one of three
    # slots from a broadcaster that is. Neither is a player: BBC iPlayer
    # and Premier Player are the same page with a different name on it —
    # and "iPlayer" is one word, which a word boundary on "player" alone
    # would let through, so it is named by itself.
    r"|website|\.com|\.co\.uk|\bplayer\b|iplayer", re.I)

# Australia and New Zealand, ranked above everywhere else. They are named
# only by an explicit marker, never by the brand: "Sky Sport NZ" carries
# Sky and is not Britain's, "Fox Sports Australia" carries Fox and is not
# America's, and reading either by its brand would put a channel on the
# row that the wrong half of the world can watch.
DOWN_UNDER = re.compile(r"\baustralia\b|\baustralian\b|\bfoxtel\b|\boptus\b"
                        r"|\bstan sport\b|\bkayo\b|\bnew zealand\b"
                        r"|\bNZ\b|\bAUS?\b|\bsky sport now\b", re.I)

# beIN's overflow and its other-language feeds, ranked BELOW everywhere
# else — never a first choice, always still there when nothing else is.
#
# Xtra is the same match beIN is already showing on an extra channel, and
# EN and FR are it again in another language. The reader put all three
# behind Sportsnet, behind Australia and New Zealand, behind even V Sport
# and Denmark's channels.
#
# Ranked, not deleted, and that part is measured: 268 of the 1001
# fixtures in Doha's guide name beIN SPORTS EN 1 and NOTHING else —
# Manchester United, Liverpool, Arsenal, Barcelona, Real Madrid. Deleting
# would turn every one of those rows from a channel that works into
# "لم تُعلن القناة", which is worse than the complaint.
LAST_RESORT = re.compile(r"\bbein\b.*\b(?:xtra|EN|FR)\b", re.I)

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


# The Canadian feeds' titles carry their league before their teams —
# "MLS on TSN: Vancouver vs. St. Louis", "CPL on TSN: Atletico Ottawa
# vs. Pacific FC", "2026 FIFA U-20 Women's World Cup: Canada vs. ..." —
# and the board's own wanted() test reads the competition, not the
# title, so the league the broadcaster itself printed is what the row
# is handed. FIFA's competitions are already wanted by their own word,
# and MLS and the CPL are wanted by name below, because a reader asked
# for these channels by name and their game comes with them.
#
# The NWSL pair is gone, on purpose, and with it the league. A soccer
# board that had carried it for a long time was asked to become
# soccer's page alone and to stop carrying the American women's league
# and its neighbours' women's series — and to make that stick, the
# league is refused outright in NEVER_LISTED below rather than merely
# unlisted here, so no page, feed or guide that starts carrying it
# tomorrow can put it back. The WSL pair STAYS: England's Women's Super
# League was asked for by name and is not the league going.
CANADAS_LEAGUES = (
    ("fifa", "fifa"),
    ("mls", "mls"),
    ("cpl", "canadian premier league"),
    ("wsl", "women's super league"),
    ("premier league", "premier league"),
)

# Sportsnet's grid names the league only in its own data, never in the
# title — "Chelsea vs. Aston Villa" is a Women's Super League match the
# reader would never know from the words on the screen. The word the
# broadcaster itself filed it under is handed to the board's own
# wanted() test, which keeps the final word on what belongs.
CANADAS_FEED_LEAGUES = {
    "fawsl": "women's super league",
}


def canadas_competition(event: dict) -> str:
    """The league a Canadian feed's row names, in the board's words."""
    # The never-listed leagues are answered with no league at all rather
    # than the one the fallback would invent for them: "NSL on TSN:
    # Ottawa vs. Montreal" is the Northern Super League — a women's
    # league in the family that was asked off — and the fallback below
    # would hand it "MLS" on no better evidence than " on tsn", while
    # the lead-stripper takes the real word out of the title before
    # wanted() could refuse it. Empty competition is refused by wanted()
    # on its own, which is the correct refusal: the league is not
    # mislabelled, it is not carried.
    if NEVER_LISTED.search(event.get("title") or ""):
        return ""
    by_the_feed = CANADAS_FEED_LEAGUES.get((event.get("league") or "").casefold())
    if by_the_feed:
        return by_the_feed
    lowered = event["title"].casefold()
    for word, competition in CANADAS_LEAGUES:
        if word in lowered:
            return competition
    return "mls" if " on tsn" in lowered else ""


def real_channels(channels: list[str]) -> list[str]:
    """The names among these that are actually somebody's television.

    Spelled the way this repository spells them. A channel written two
    ways is one channel — see SAME_CHANNEL below — and once the two
    spellings are known to be one, printing whichever page happened to
    win the merge is a coin toss the reader loses: قناة الأردن الرياضية
    reached a television reading "Jordan Sports", in Latin, on an Arabic
    board that sorts Arabic first. The canonical spelling is the one this
    repository already publishes for that channel elsewhere, so the board
    and the guide agree rather than carrying two names for one screen.

    Deduped afterwards, because two spellings collapsing into one name
    would otherwise print it twice.
    """
    out: list[str] = []
    for name in channels:
        if NOT_A_CHANNEL.search(name):
            continue
        spelling = canonical_channel(name)
        if spelling not in out:
            out.append(spelling)
    # And the HDR twin of a channel already on the row. Two or three names
    # fit beside a fixture; spending one of them saying "Sky Sports F1"
    # twice is a name the viewer does not get to see.
    return drop_simulcasts(out)


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

    # The never-list is checked FIRST, and on the title as well as the
    # competition, because the two disagree in exactly the families it
    # exists for: a feed hands the row a league from its title, and a
    # listings page hands it nothing at all. A league that was asked off
    # stays off whichever of the two named it.
    if NEVER_LISTED.search(competition) or NEVER_LISTED.search(teams_folded):
        return False

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
MERGE_SLACK = timedelta(minutes=12)
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
    # A page writes "Preston" where the other writes "Preston North End",
    # and "north" and "end" cannot be furniture — dropping them would
    # fold Northampton into "North" and West Ham into "End". So the one
    # club that needs it is written out here, in the table above, where
    # every other contraction the pages disagree on already lives.
    "preston": "preston north end",
    # The American game, where the two pages disagree the same way. MLS
    # and the NWSL only reached this board the day "Apple TV" stopped
    # being read as an app — and their fixtures arrived twice, one row
    # per spelling, from the two pages that both carry them:
    # "LA Galaxy" against "Los Angeles Galaxy", "Vancouver" against
    # "Vancouver Whitecaps", "Chicago Stars" against "Chicago W", and
    # "Los Angeles FC" against "Los Angeles Football Club". Every one
    # measured, the way Preston was, and none of them reachable by a
    # rule: "LA" is two capitals, which written_as_initials refuses on
    # purpose, and "Stars" is not furniture the way "FC" is not in
    # CLUB_TAIL.
    "la galaxy": "los angeles galaxy",
    "vancouver": "vancouver whitecaps",
    "chicago stars": "chicago",
    "los angeles fc": "los angeles football club",
}

# One word written two ways, which is not a nickname and so does not
# belong in the table above: every page that writes "Utd" means "United".
WORD_ALIASES = {"utd": "united", "utd.": "united", "atl": "atletico",
                # "Ath Bilbao" is how a listings page writes Athletic
                # Bilbao, and three letters is under the floor at which a
                # shortened word is allowed to be evidence on its own —
                # so it is written out here rather than the floor lowered
                # for every three-letter word in football.
                "ath": "athletic", "ath.": "athletic",
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
             "wanderers", "rovers", "hotspur", "hotspurs", "club", "calcio",
             # The women's game. Sky's row says "Arsenal Women" and
             # Sportsnet's says "Arsenal"; one club, one row, and the
             # channels of both belong on it. "W" is how one page writes
             # it ("Arsenal W"), "Ladies" how England's older listings
             # did. Trailing furniture, not a different team.
             "women", "w", "ladies"}

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


def one_side_agrees(first: str, second: str) -> bool:
    """Whether two "A - B" titles agree about EITHER club.

    Weaker than same_match on purpose, and only ever used where a kickoff
    minute is already agreed — a club plays one match in two hours, so one
    club and one minute is the fixture.

    It exists because a BROADCASTER'S GRID and a LISTINGS PAGE do not
    write clubs the same way, and same_match is built for two listings
    pages that do. Measured on one Saturday, over the fifteen matches
    beIN's guide and the board both carried:

        Nottingham - Tottenham       Nottingham Forest - Tottenham Hotspur
        Brighton - Leeds             Brighton & Hove Albion - Leeds United
        Ath Bilbao - Atl. Madrid     Athletic Bilbao - Atletico Madrid
        Lyon - Auxerre               Olympique Lyonnais - AJ Auxerre

    same_match joins eleven of the fifteen. Every one of the four it
    misses has ONE side that lines up cleanly — Tottenham/Tottenham
    Hotspur, Leeds/Leeds United, Atl. Madrid/Atletico Madrid,
    Auxerre/AJ Auxerre — and four misses is four matches on the board
    twice.

    epg_lib's exact cross-script answer is asked as well, because a grid
    and a page can also disagree about the SCRIPT.
    """
    left = [side.strip() for side in (first or "").split(" - ")]
    right = [side.strip() for side in (second or "").split(" - ")]
    if len(left) != 2 or len(right) != 2 or not all(left) or not all(right):
        return False
    return (same_side(left[0], right[0]) or same_side(left[1], right[1])
            or own_guides.one_club_matches(first, second))


def not_already_on_the_board(ours: list[dict],
                             board: list[dict]) -> list[dict]:
    """Our own broadcasters' fixtures, minus the ones the board has.

    The window is the one attach() already trusts to decide which row a
    beIN channel belongs on — two hours, wide because a grid opens with a
    studio — and the name test is one_side_agrees above. If a rule is
    good enough to put a channel ON a fixture it is good enough to say
    the fixture is that one.
    """
    unseen = []
    for event in ours:
        if any(abs(event["start"] - already["start"]) <= own_guides.SLACK
               and one_side_agrees(event["title"], already["title"])
               for already in board):
            continue
        unseen.append(event)
    if len(unseen) != len(ours):
        log(f"  our own guides: {len(ours) - len(unseen)} fixture(s) the "
            f"board already had, {len(unseen)} it did not")
    return unseen


# HOW THE CANADIAN FEEDS SPELL A FIXTURE, which no listings page shares.
# They print "A vs. B" where the pages print "A - B", and they open with
# the league the broadcaster itself puts in the title — "MLS on TSN:
# Vancouver vs. St. Louis", "CPL on TSN: Atletico Ottawa vs. Pacific FC".
# same_match() below split on " - " and nothing else, so a feed row never
# matched the listings row of the same game and the SAME match printed
# twice, its channels split between the two rows — which is the exact
# opposite of a guide: the reader is shown two rows and told two
# different places to watch one game. The league lead is cut at the
# first colon when it names the channel carrying it (" on TSN:");
# "Vancouver vs. St. Louis" is what is left, and that IS the fixture.
CANADIAN_LEAD = re.compile(
    r"^\s*(?:[\w .&\'\-]{2,40}\s+on\s+[A-Z][\w\- .]*\s*:\s*"
    r"|(?:19|20)\d{2}\s+[\w .&\'\-]{2,40}:\s*"
    r"|[A-Z][\w\- .]*:\s*)",
    re.I)


def looks_like_a_fixture(remainder: str) -> bool:
    """Whether a stripped title still holds an "A vs. B" or "A - B".

    A colon can sit at the end of the SIDES ("Brazil - Tanzania:
    FIFA Women's U20 World Cup" — a page that labels the fixture after
    the fact) and cutting the lead there would make "Brazil - Tanzania:
    FIFA" into a fixture and its tail into a club. The lead is only
    cut when what follows it names two sides.
    """
    parts = re.split(r"\s+(?:-|vs\.?|v)\s+", remainder, maxsplit=1,
                     flags=re.I)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return True
    at = re.split(r"\s+at\s+", remainder, maxsplit=1, flags=re.I)
    return len(at) == 2 and at[0].strip() and at[1].strip()


def fixture_sides(title: str) -> list[str]:
    """The two clubs of a title, whichever way the source spelled it.

    "A - B" from a listings page, "A vs. B" (and "A vs B", "A v B") from
    the Canadian feeds, and the league lead cut off the front of a feed
    title before the split. Returns two sides, or fewer when the title
    is not a fixture at all.
    """
    if not title:
        return []
    stripped = title
    lead = CANADIAN_LEAD.search(stripped)
    if lead and looks_like_a_fixture(stripped[lead.end():]):
        stripped = CANADIAN_LEAD.sub("", stripped)
    parts = re.split(r"\s+(?:-|vs\.?|v)\s+", stripped, maxsplit=1, flags=re.I)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return [parts[0].strip(), parts[1].strip()]
    # One last shape: "A at B", which the NFL and MLB grids use.
    at = re.split(r"\s+at\s+", stripped, maxsplit=1, flags=re.I)
    if len(at) == 2 and at[0].strip() and at[1].strip():
        return [at[0].strip(), at[1].strip()]
    return []


def fixture_lead_free(title: str) -> str:
    """A feed title with its league lead taken off, for the board to wear.

    The lead is real information in a feed, and noise on a board: the
    competition line under the name already says "Canadian Premier
    League", so a row opening "CPL on TSN: Atletico Ottawa vs. Pacific
    FC" says the league twice and the channel once more than it needs.
    The same CANADIAN_LEAD cut that finds the fixture strips it, and a
    title with no lead is returned untouched.

    The separator is dressed to the board's own while it is here: the
    pages print "A - B" and the feeds "A vs. B", and a board wearing
    both spellings looks like two publishers. The split in
    fixture_sides() already reads either; this is only the word on the
    screen.
    """
    lead = CANADIAN_LEAD.search(title or "")
    if lead and looks_like_a_fixture(title[lead.end():]):
        title = (title[:lead.start()] + title[lead.end():]).strip()
    return re.sub(r"\s+(?:vs\.?|v)\s+", " - ", title or "", flags=re.I)


def same_match(first: str, second: str) -> bool:
    """Whether two titles name one fixture. Both sides must agree.

    One side agreeing is a coincidence — Real Madrid plays somebody every
    week. Two sides agreeing at one kickoff minute is one match written
    twice.
    """
    left = fixture_sides(first)
    right = fixture_sides(second)
    if len(left) != 2 or len(right) != 2:
        return False
    return same_side(left[0], right[0]) and same_side(left[1], right[1])


def absorb(into: dict, extra: dict) -> None:
    """Add what the second page knew and the first one did not."""
    for channel in extra["channels"]:
        if channel not in into["channels"]:
            into["channels"].append(channel)
    if not into["competition"]:
        into["competition"] = extra["competition"]


# One channel written in two scripts, which no structural rule can reach:
# nothing in the letters of "الأردن الرياضية" leads to "Jordan Sports".
#
# It is needed because the measurement underneath the third and fourth
# pages has changed. "The Jordanian league is in none of the pages above"
# was true when it was measured — 272 fixtures offered and not one
# Jordanian — and it is not true any more: livefootballtv now carries
# الوحدات - الفيصلي as "Al Wehdat - Al Faisaly · Jordan Sports", and the
# federation carries the same fixture in Arabic on الأردن الرياضية. The
# board printed both, one under the other, at one kickoff.
#
# The club names cannot settle it and that is measured too: الفيصلي
# against Al Faisaly reduces to "fasla" and "fasala", a letter apart and
# both under the length at which resemblance is allowed to decide
# anything — and loosening that is how "Mainz" becomes "Monza". The
# CHANNEL settles it instead, on the same structural fact already_on_air
# is built on: الأردن الرياضية shows one match at a time.
#
# Written out, one pair, because it is a fact about a channel rather than
# a rule about names. Add a pair only where two pages were SEEN to spell
# one channel two ways.
SAME_CHANNEL_PAIRS = (
    ("الأردن الرياضية", "Jordan Sports"),
    ("الأردن الرياضية", "Jordan Sport"),
    ("الأردن الرياضية", "Jordan TV Sports"),
)


def _bare(name: str) -> str:
    return re.sub(r"[^a-z0-9\u0600-\u06ff]", "", name.casefold())


# Built from the pairs above so the two can never drift apart: every
# spelling points at the first one written.
SAME_CHANNEL = {_bare(other): _bare(canonical)
                for canonical, other in SAME_CHANNEL_PAIRS}

# And the spelling to print, from the same pairs: the first one written.
CANONICAL_CHANNEL = {_bare(spelling): canonical
                     for canonical, other in SAME_CHANNEL_PAIRS
                     for spelling in (canonical, other)}


def screen_key(name: str) -> str:
    """A channel name reduced to what two pages would spell the same."""
    key = _bare(name)
    return SAME_CHANNEL.get(key, key)


def canonical_channel(name: str) -> str:
    """One channel's name, spelled the way this repository spells it."""
    return CANONICAL_CHANNEL.get(_bare(name), name)


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


# A clock nobody set, wearing a kickoff's clothes.
#
# livefootballtv gave four Turkish fixtures ONE instant — 2026-09-06
# 00:00 UTC — and beIN's own schedule, which this repository builds every
# hour from beIN's feed, puts them on four different days:
#
#     Fenerbahçe vs Beşiktaş         Sat 05-09  19:50 Istanbul
#     Başakşehir vs Galatasaray      Fri 04-09  19:50
#     Trabzonspor vs Gençlerbirliği  Sun 06-09  19:50
#     Göztepe vs Gaziantep           Mon 07-09  19:50
#
# Several fixtures on one instant is not by itself wrong — a Saturday
# board legitimately carries six at 15:00 in London, five at 15:30 in
# Berlin and eight in the NFL's one o'clock window. Measured on the same
# board that carried the Turkish four:
#
#     11:30 UTC  x6      13:00 UTC  x4      13:30 UTC  x5
#     14:00 UTC  x7      16:00 UTC  x5      00:00 UTC  x4   <-- this one
#
# What separates them is MIDNIGHT. A time that was never read defaults to
# the start of a day, and that is what 00:00:00 on the dot is: not a
# kickoff several clubs happen to share, but the absence of one, repeated.
# No league on this board kicks off at exactly midnight UTC, and none of
# the five real blocks above comes near it.
#
# So a cluster there is refused rather than published. It is the narrow
# rule and not the general one — one fixture alone at midnight is left
# alone, because that could be a real late kickoff somewhere; it takes a
# CROWD at midnight to prove nobody set the clock.
MIDNIGHT_IS_NOT_A_KICKOFF = 3


# Turkey's clubs come from Spor Ekranı and from this reader's own guides
# — beIN Qatar and Alwan — and not from a general listings page. Asked
# for by name, more than once, and this is where it is enforced.
#
# The listings page is why. livefootballtv gave four Süper Lig fixtures
# ONE time, 2026-09-06 00:00 UTC, and beIN's own feed had every one of
# them on a different day, on the right channel, MARKED LIVE in beIN's
# own title. A page that gets four fixtures wrong in one block is not a
# source for that league while a broadcaster's own schedule is sitting
# in this repository.
#
# It is refused by COMPETITION, at the page, so nothing downstream has to
# know: whatever livefootballtv says about the Süper Lig does not reach
# the merge at all, and what Spor Ekranı and beIN say does.
#
# IN BOTH SCRIPTS, because the pages this now guards write in both. The
# Arabic half was added the day the board carried Fenerbahçe - Beşiktaş
# beside فنربخشة - بشكتاش: yallakora heads its blocks "الدوري التركي",
# and a Latin-only pattern let every one of them straight through.
A_TURKISH_LEAGUE = re.compile(
    r"turkish\s+s(?:ü|u)per\s+lig|s(?:ü|u)per\s+lig|turkish\s+super\s+league"
    r"|tff\s*1\.?\s*lig|turkey.*(?:cup|kupa)|kupas[ıi]"
    r"|الدوري\s*التركي|كأس\s*تركيا|السوبر\s*التركي|الدرجة\s*الأولى\s*التركية",
    re.I)


def not_from_the_listings_page(events: list[dict]) -> list[dict]:
    """Drop Turkish fixtures the listings page had no business dating."""
    kept, dropped = [], 0
    for event in events:
        if A_TURKISH_LEAGUE.search(event.get("competition", "") or ""):
            dropped += 1
            continue
        kept.append(event)
    if dropped:
        log(f"  {dropped} Turkish fixture(s) left to Spor Ekranı and beIN, "
            f"which is where they were asked to come from")
    return kept


def refuse_a_defaulted_midnight(events: list[dict]) -> list[dict]:
    """Drop fixtures dumped on midnight because their time was not read."""
    at_midnight = [event for event in events
                   if event["start"].astimezone(UTC).hour == 0
                   and event["start"].astimezone(UTC).minute == 0
                   and event["start"].astimezone(UTC).second == 0]
    if len(at_midnight) < MIDNIGHT_IS_NOT_A_KICKOFF:
        return events

    together: dict = {}
    for event in at_midnight:
        together.setdefault(event["start"], []).append(event)
    doomed = {id(event) for crowd in together.values()
              if len(crowd) >= MIDNIGHT_IS_NOT_A_KICKOFF
              for event in crowd}
    if not doomed:
        return events

    for crowd in together.values():
        if len(crowd) >= MIDNIGHT_IS_NOT_A_KICKOFF:
            log(f"  WARN {len(crowd)} fixture(s) all on "
                f"{crowd[0]['start']:%Y-%m-%d} 00:00 UTC — a time nobody "
                f"set, so none of them is published:")
            for event in crowd:
                log(f"    dropped: {event['title']}  │ {event['competition']}")
    return [event for event in events if id(event) not in doomed]


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

# BRITISH. Sky and TNT are what "English" means here — the channels that
# carry English football in England — not a beIN feed with English
# commentary, which is Doha's channel and belongs with the Arabic ones.
#
# Every brand here lets what follows be glued straight on, because that
# is how a listings page writes them: ITV1, ITV4, ITVX, BBC1, FS1,
# ESPN2, NBCSN, TSN1. A word boundary after the brand matched none of
# those and dropped them into "everywhere else" — ITV1, which carries
# England and the FA Cup, was ranked below a Danish channel. Fifteen of
# fifty-four real spellings sat in the wrong tier for this one reason.
BRITISH = re.compile(r"\bsky\w*|\btnt\w*|\bbbc\w*|\bitv\w*|\bstv\b"
                     r"|\bpremier sports\b|\bchannel\s?4\b|\bc4\b"
                     r"|\bchannel\s?5\b|\bs4c\b|\bbt sport\b", re.I)

# AMERICAN, and Canada with it — one continent, one tier, because a
# viewer who can get Fox can usually get TSN and neither is any use to
# somebody in the Gulf.
#
# "fox" also begins Foxtel, which is Australian, and "sky" begins Sky
# Sport NZ. Both are safe only because Australia and New Zealand are
# tested BEFORE these two. Keep that order.
AMERICAN = re.compile(r"\bUS\b|\bfox\w*|\bnbc\w*|\bcbs\w*|\bespn\w*"
                      r"|\bfs[12]\b|\busa network\b|\bparamount\b"
                      r"|\bpeacock\b|\btelemundo\b|\btudn\b"
                      r"|\bunivision\b"
                      # Canada
                      r"|\btsn\w*|\bsportsnet\w*|\bcbc\w*|\brds\b"
                      r"|\bonesoccer\b|\btva sports\b", re.I)

# "S Sports" as well as "S Sport": the singular alone left the Turkish
# channel written the other way in "everywhere else", the tier for
# broadcasters a viewer here cannot get.
TURKISH = re.compile(r"\bTR\b|\btabii\b|\btrt\b|\bs sports?\b", re.I)

# The names a Gulf or Levantine viewer actually has. beIN written without
# any of the marks above is Doha's, which is the whole point of marking
# the others — including "beIN SPORTS 1 EN", which is Doha's English
# commentary and not a British channel.
ARAB_CHANNEL = re.compile(r"\bbein\b|\balwan\b|\bthmanyah\b|\bon sport\b"
                          r"|\bon time\b|\bshahid\b|\bmbc\b|\bssc\b"
                          r"|\balkass\b|\bal kass\b|\bad sports\b"
                          r"|\bdubai\b|\bshasha\b|\bstarzplay\b"
                          r"|\brotana\b|\bsaudi\b|\bjordan\b|\bfajer\b",
                          re.I)


# The word a broadcaster puts in its name that carries no information,
# and the brands that are still a channel without it.
#
# A photograph of the screen settled this: "Burnley - Middles…" clipped,
# because "beIN SPORTS Xtra 1" and "beIN SPORTS 1" had eaten the row. The
# word SPORTS appears on nearly every channel here and distinguishes none
# of them from each other — it is seven characters of the fixture's space
# spent saying that a sports channel shows sport.
#
# It comes off only where what is left still names the channel. beIN, Sky,
# MBC Shahid, Thmanyah, Alwan and TNT are all names on their own. Premier
# is NOT: "Premier 1" is nothing, so Premier Sports keeps its Sports —
# and so does every broadcaster not on this list, because the cost of
# guessing wrong is a viewer told to turn to a channel that does not
# exist under the name they were given.
GENERIC_WORD = re.compile(r"\s*\b(?:sports?|channels?)\b", re.I)
#
# STARZPLAY joins them for the second board, which puts it on every UFC
# card: "STARZPLAY Sports" is two words where one says the same thing,
# and STARZPLAY is unmistakably a channel on its own.
#
# Fajer joins with Alwan: the two are published by the same generator
# family here and their names are shaped the same — "Fajer Sport 1" is
# "Alwan Sport 1" with another word for a channel, and Fajer answers to
# its own name the way Alwan does.
STANDS_ALONE = re.compile(
    r"^(?:beIN|Sky|MBC|Shahid|Thmanyah|Alwan|TNT|STARZPLAY|Fajer)\b", re.I)


def shorter(name: str) -> str:
    """A channel's name without the word that says nothing about it."""
    if not STANDS_ALONE.match(name):
        return name
    trimmed = norm(GENERIC_WORD.sub("", name))
    return trimmed if any(ch.isalpha() for ch in trimmed) else name


def where_from(name: str) -> int:
    """The reader's order, as a number that sorts.

    The marks are read before the brand, because a mark is what says
    WHOSE channel this is: beIN SPORTS 1 TR is Istanbul's, beIN SPORTS US
    is America's, beIN SPORTS FR 2 is France's, and beIN SPORTS 1 with no
    mark at all is Doha's.
    """
    if LAST_RESORT.search(name):
        return 6
    # Before the brands, because these carry Sky's name and Fox's.
    if DOWN_UNDER.search(name):
        return 4
    if TURKISH.search(name):
        return 3
    if AMERICAN.search(name):
        return 2
    if BRITISH.search(name):
        return 1
    if ARABIC_LETTERS.search(name) or ARAB_CHANNEL.search(name):
        return 0
    return 5


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
    real = [shorter(name)
            for name in in_the_readers_order(real_channels(event["channels"]))]
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
    dropped, one match per line with its channels on the line under it,
    and there is no blank line under the header. The clock sits at the
    same column on every line and the countdown phrase that used to sit
    beside it is gone — a number that is frozen the moment the file is
    written was pushing every row's clock off the column the viewer's eye
    was looking down.

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

    coming = next((e for e in left if e["start"] > now), None)
    lines = [header]
    for event in left:
        # THE CLOCK IS THE FIRST THING ON EVERY LINE, AT THE SAME COLUMN
        # ON EVERY LINE. The row used to open with a countdown phrase —
        # "06:30 الآن", "08:15 أقل من 15 دقيقة", "09:30 ساعة و25 دقيقة" —
        # so the clock landed at a different column on every row and the
        # names after it started wherever the phrase happened to end:
        # "التالي و المباشر مش على نفس الخط", said with a photograph of
        # the television. The wait is a number that goes stale the moment
        # the file is written anyway; the clock never does. The status is
        # one mark before it — 🔴 for the row on the air, ⏳ for the next
        # kickoff, ⚪ for the rest — one character of the same width class
        # on every row, so every clock, live or waiting, sits on the same
        # line. And the row carries the fixture alone: the channels go on
        # their own line under it, where they are not truncated away.
        if event["start"] <= now:
            mark = LIVE_MARK
        elif event is coming:
            mark = NEXT_MARK
        else:
            mark = WAIT_MARK
        when = event["start"].astimezone(VIEWER)
        # The row carries the fixture alone \u2014 the channels go on their
        # own line under it, where they are not truncated away.
        lines.append(in_reading_order(
            f"{mark} {when:%H:%M}  {event['title']}",
            names=event["title"]))
        # The channels under the name, indented past the clock — the name
        # line then spends its whole width on the two names, which is
        # what a viewer is reading for, and the channels are still one
        # glance away without being truncated off the end of the line.
        channels = channels_of(event)
        if channels:
            lines.append(f"        {channels}")
    return "\n".join(lines)


def publish_board(index: int, day: date, events: list[dict], now: datetime,
                  *, page: int = 1, pages: int = 1) -> str | None:
    """Draw the day's board, keep it only if it differs, return its URL.

    Rewriting an identical picture every ten minutes would commit a fresh
    copy of it every ten minutes, so the bytes are compared before
    anything is written.
    """
    name = f"{BOARD_PREFIX}{index}.png"
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


def publish_all(events: list[dict], everything: list[dict],
                now: datetime, *, days: list[date] | None = None) -> int:
    """Render and publish this channel for whichever clock the module wears.

    Every clock in the file — the day a match groups under, the hour
    printed beside it, the window a programme runs — reads the module's
    VIEWER, so one function renders the channel for any zone it is told
    to wear, and the two clocks cannot drift apart in how they draw.

    The days are a parameter because the two clocks do not agree about
    where the collected window ends: the default is the viewer's own
    days_of(), and the UAE-clock caller hands in the days the collected
    events actually span, so a match at the window's far edge is never
    dropped for landing on a date the window never named.
    """
    days = days_of(now) if days is None else days
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
    per_day: list[int] = []
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
        per_day.append(len(chunks))

        opens, closes = day_bounds(day)
        add_programme(tv, CHANNEL_ID, opens, closes,
                      day_title(day, events_today, now),
                      day_page(day, events_today, now),
                      icon=first_board)
        log(f"  {day} -> {len(events_today)} match(es) over "
            f"{len(chunks)} board(s)")

    # And the boards this pass did NOT write. The window rolls at
    # midnight — yesterday goes, a new day arrives at the far end — and
    # the count can fall, so a board the old build wrote and this one
    # did not was still on disk and still in the reel, playing a day
    # that was over.
    from match_board import forget_boards_past
    stale = forget_boards_past(BOARD_PREFIX, board_no, BOARD_DIR)
    if stale:
        log(f"  {stale} board(s) for days that have gone, deleted")

    # HOW MANY BOARDS EACH DAY TOOK, written down for the encoder.
    #
    # "ما عم بكمل جدول السبت ... و بقطع اشياء لحاله". It was: the reel
    # took the first six boards and stopped, and Saturday needed six of
    # its own. So the channel played Thursday, Friday, and the first
    # THIRD of Saturday, then went back to the top — a day cut in half,
    # mid-list, with nothing to say it had been.
    #
    # The encoder could not have known: it sees a folder of numbered
    # pictures and nothing about days. So the builder, which does know,
    # says so here — one line, one number per day, in the order the
    # boards were written. What the encoder does with it is its own
    # decision; what it can no longer do is guess.
    with open(os.path.join(BOARD_DIR, f"{BOARD_PREFIX}days.txt"), "w",
              encoding="utf-8") as handle:
        handle.write("\n".join(str(count) for count in per_day) + "\n")
    log(f"  boards per day: {per_day} (written for the encoder)")

    ok = write_xml_atomic(tv, OUTPUT, generator_name="Today's Matches",
                          guard_regression=False, min_programmes=1)
    return 0 if ok else 1



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
    everything = unify(
        not_from_the_listings_page(
            refuse_a_defaulted_midnight(collect(html, now, floor, ceiling))),
        live_football_on_tv.fetch_events(session, floor, ceiling))
    # The third page last, narrowed to what it is for — and then to what
    # is not already on the board.
    #
    # "Nothing to collide with" was wrong: the first page does carry some
    # of Egypt's league, so الجونة - المقاولون العرب arrived beside
    # El Gouna FC - El-Mokawloon and Wednesday showed both. The names
    # cannot settle it — no threshold separates تولوز from Toulon — but
    # something else can, and it is a fact rather than a guess: one channel
    # cannot show two matches at the same minute.
    # AND THROUGH THE SAME TURKISH FILTER AS THE FIRST PAGE. It is a
    # general listings page too, and Turkey was asked for by name to come
    # from Spor Ekranı and this repository's own guides. Belt and braces
    # on purpose: the competition list above no longer asks for Turkey,
    # and this refuses it even if some future block is headed differently.
    asked = [event for event in
             not_from_the_listings_page(
                 yallakora.fetch_events(session, floor, ceiling))
             if any(name in event["competition"] for name in YALLAKORA_ONLY)]
    fresh = [event for event in asked if not already_on_air(event, everything)]
    log(f"  yallakora: {len(asked)} in the competitions asked for, "
        f"{len(fresh)} the board did not already have")
    everything = unify(everything, fresh)

    # And the Jordanian league, which is in NONE of the pages above. That
    # is measured, not assumed: 272 fixtures were offered between them
    # and not one was Jordanian, matched on the clubs and not only on the
    # competition, because a competition can be renamed and الفيصلي
    # cannot. The federation publishes its own, so it is asked directly.
    #
    # It names no channel, and that is no longer a reason to refuse a
    # source: the match reaches the board with "لم تُعلن القناة" beside
    # it and picks up a channel from any later pass that learns one.
    #
    # And it is put through the same "is this already on the board" test
    # as the page above, for the reason that test was written for. The
    # sentence above is no longer true: livefootballtv has begun carrying
    # some of this league, so الوحدات - الفيصلي arrived beside Al Wehdat -
    # Al Faisaly and the board showed both at one kickoff. The names
    # cannot separate them — الفيصلي and Al Faisaly are a letter apart in
    # skeleton and too short for resemblance to be allowed to decide — and
    # the channel can: الأردن الرياضية shows one match at a time, and it
    # is the same channel however a page spells it.
    jordanian = jordan_football.fetch_events(session, floor, ceiling)
    unseen = [event for event in jordanian
              if not already_on_air(event, everything)]
    if len(unseen) != len(jordanian):
        log(f"  jfa.jo: {len(jordanian) - len(unseen)} already on the board "
            f"from another page, under another spelling")
    everything = unify(everything, unseen)

    # And Turkey's own second tier, which is in none of them either. The
    # reader photographed Iğdırspor - Manisa FK, Bodrumspor - Esenler
    # Erokspor and Bursaspor - İstanbulspor on TRT Spor; the day's
    # dropped-competitions report named eight competitions and no Turkish
    # league among them, so nothing filtered them out — they were never
    # offered. Spor Ekranı has them, with the channel named in structured
    # JSON rather than picked out of a Turkish sentence.
    turkish = [event for event in spor_ekrani.fixtures(session)
               if floor <= event["start"] < ceiling]
    everything = unify(everything, turkish)

    # AND THE CANADIAN BROADCASTERS' OWN GRIDS — TSN and Sportsnet, asked
    # for by name ("TSN AND SPORTSNET events matches to be added on
    # channels 1 and 2 find sources reliable ones from outside github").
    # What they have that no listings page here does is the Canadian
    # game a Canadian viewer watches on a Canadian channel: MLS and the
    # CPL on TSN5, the Women's World Cup U-20 on TSN4, the WSL on
    # Sportsnet One. Their soccer rows are asked for from the same feeds
    # their own television reads them, and each is given the competition
    # its own title names, so the board's own wanted() test decides
    # which belong — no league is added to this board by hand.
    canadian = []
    for feed_rows, in ((tsn.events(session, floor, ceiling,
                                   sports=("Soccer",)),),
                       (sportsnet.events(session, floor, ceiling,
                                         sports=("soccer",)),)):
        canadian += feed_rows
    dressed = [dict(event,
                     title=fixture_lead_free(event["title"]),
                     competition=canadas_competition(event))
               for event in canadian]
    everything = unify(everything, dressed)
    if dressed:
        log(f"  canadian feeds: {len(dressed)} football row(s) offered from "
            f"TSN and Sportsnet's own grids")

    # And beIN's own schedule, which marks its live airing in its own
    # title and so needs nothing inferred. Four Süper Lig fixtures on
    # four days, on the channel beIN names, against eighteen repeats of
    # the same four that it does not mark — the mark is the whole rule.
    #
    # AND EVERY OTHER COMPETITION BEIN MARKS LIVE, which this read four of
    # and now reads ninety-eight. "لما احكيلك استخدم مصدر bein sports
    # qatar و تروح تستخدم مصدر اخر شو بكون مشكلتك؟" — and the answer was
    # that beIN's guide was lending channels to rows a listings page had
    # created, and creating none of its own outside Turkey.
    #
    # What is added is only what nothing else had. The test is the one
    # already trusted to decide which row a beIN channel belongs on — one
    # club, exactly, inside two hours — because the board's own fixture
    # test misses four of fifteen real pairs when a broadcaster's grid
    # writes "Nottingham Forest" for a page's "Nottingham".
    ours = own_guides.fixtures_our_guides_have(floor, ceiling)
    everything = unify(everything,
                       not_already_on_the_board(ours, everything))
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

    # And where a listings page guessed a beIN channel number, let beIN's
    # own feed overrule it: "beIN 3" for Ipswich v Liverpool becomes the
    # "beIN SPORTS 2" beIN itself publishes. A number beIN states about
    # its own channels is a fact; the page's is a guess.
    own_guides.prefer_official_bein(events)

    # Counted before the placeholder goes in, because "لم تُعلن القناة"
    # is a sentence and not a channel, and a row wearing it has none.
    say_which_rows_are_thin(events)

    # Sorted once, here, so the printed line and the drawn board show the
    # same two names — they each take the first two and would otherwise
    # disagree about which those are.
    for event in events:
        event["channels"] = [shorter(name) for name in
                             in_the_readers_order(event["channels"])]

    for event in events:
        if not event["channels"]:
            event["channels"] = [CHANNEL_UNANNOUNCED]
    log(f"  {len(everything)} match(es) in the window, "
        f"{len(events)} in a competition worth showing")
    for event in events[:12]:
        log(f"  {event['start']:%m-%d %H:%M}Z  {event['title']}"
            f"   │ {event['competition']}")

    ok = publish_all(events, everything, now) == 0

    # THE SECOND CLOCK — the same matches, every time printed in the
    # Gulf's (Asia/Dubai), asked for outright as a second set of links.
    # The events are already on the table: no page is fetched again, the
    # module simply wears another zone for one render and puts it back
    # afterwards. The first set is written and safe before this begins,
    # and a failure here warns and leaves it exactly as it was.
    with dubai_time.the_other_clock(
            globals(),
            VIEWER=dubai_time.DUBAI, VIEWER_NAME=dubai_time.DUBAI_NAME,
            OUTPUT=DUBAI_OUTPUT, CHANNEL_ID=DUBAI_CHANNEL_ID,
            BOARD_PREFIX=DUBAI_BOARD_PREFIX):
        try:
            publish_all(events, everything, now,
                        days=dubai_time.days_the_events_span(
                            now, events, dubai_time.DUBAI))
        except Exception as exc:                              # noqa: BLE001
            warn(f"the UAE-clock guide could not be written ({exc}) — "
                 f"the published one is unchanged")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
