#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The channels this repository already publishes, added to the board.

Asked for directly, and right: these guides are built here, refreshed on
their own schedules, and they know something no listings page does — which
of THIS reader's channels is carrying a match.

They are used to name channels, never to add fixtures, and that is a
deliberate limit rather than a half-measure. Their titles are written for
a television grid, not for a parser: beIN Turkey writes "Super Lig (26-27)
3. Hafta Gaziantep Fk - Rizespor - Bant -", where the competition is a
prefix, the round is in the middle and "Bant" means it is a repeat. A
title read wrongly that only fails to name a channel costs nothing; one
read wrongly that ADDS a fixture puts a match on the screen that is not
being played.

Matching a guide's fixture to one already on the board is the same
cross-script problem as everywhere else, and it is answered the same way:
never by a similarity score. The board and the guide must agree on the
kickoff MINUTE, and at least one club must match exactly under epg_lib's
own strict cross-script rule. One side is enough here — and only here —
because a club cannot play two matches at once, so an exact club match at
one minute is that club's match. Measured over the nine fixtures Alwan
published on the day this was written, that reaches all nine, where
demanding both sides reaches six: ميدلزبره and Middlesbrough do not
reduce to the same skeleton, and بيرنلي and Burnley do.

The Turkish channels are marked. beIN SPORTS 1 in Istanbul and beIN
SPORTS 1 in Doha are different channels showing different football, and a
reader with both in their playlist needs to know which one the row means.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from epg_lib import club_skeleton, log, norm, same_club

# Each guide, and the mark its channels carry. An empty mark is the Gulf,
# which is this reader's default and says nothing.
# Which of this repository's own guides are read for a channel name.
#
# Only guides whose grid is FOOTBALL, and that is a decision made HERE
# rather than one the title reader can make. roya_jordan_epg.xml publishes
# 5832 programmes of which 1728 still read as a plain "A - B" —
# "مطبخ رؤيا - سلطات" is a cookery show and there is nothing in the words
# to say so. Only the club rule stops those, and one guard is not enough
# for a source that is 1728 wrong guesses deep. A general channel's
# listings do not go in this tuple.
#
# Doha's beIN carries no mark and Istanbul's carries " TR", which is the
# whole reason the mark exists: beIN SPORTS 1 is two different channels
# showing two different matches, and a viewer told the wrong one turns to
# the wrong football.
GUIDES = (
    ("alwan_sports_epg.xml", ""),
    ("bein_sports_qatar_epg.xml", ""),
    ("bein_sports_turkey_epg.xml", " TR"),
)

# How far a broadcast may sit from the kickoff and still be that match.
#
# Not a minute. A listings page gives the KICKOFF; a television grid gives
# the PROGRAMME, which starts with the studio build-up — beIN Turkey opens
# Başakşehir v Galatasaray at 16:15 for a 17:00 kick, and at a minute's
# tolerance the Turkish channel never reached the Turkish match.
#
# Wide is safe here only because of what else is required: one club has to
# match exactly. A club does not play two matches inside two hours, so an
# exact club match in this window is that club's match. Without the club
# test this window would be reckless; with it, a tighter one only loses
# broadcasts.
SLACK = timedelta(hours=2)

# Two clubs do not meet twice in a day, in one competition. Beyond the
# build-up window above, a second live-marked airing of one fixture is a
# repeat that kept its mark — which beIN's own guide publishes — and not
# a second match. A day is the window because it is longer than any
# build-up and shorter than the gap between two legs of a tie.
ONE_FIXTURE_A_DAY = timedelta(hours=24)

XMLTV_TIME = "%Y%m%d%H%M%S %z"

# Markers a grid adds to a title that are not part of the fixture.
# Every marker bolted onto a grid title, and NONE of the letters inside a
# club's name. "LIVE" without a word boundary is a substring of
# "Liverpool", which this stripped to "rpool" — so the most broadcast club
# in the world could not be matched by any guide published here, and the
# hole was invisible because a missing club only ever costs a channel
# name. A marker is a whole word.
NOISE = re.compile(r"[‎‏‎‏]|🔴|🔵|•\s*\bLIVE\b|\bLIVE\b"
                   r"|\bBant\b|\bTekrar\b", re.I)

# A title that says nothing was scheduled is not a fixture, and neither
# is a programme ABOUT football. beIN Qatar's grid carries "Preview - US
# Open 2026" and "Ligue 1 Weekly Review - 2026/2027" beside the matches;
# both are a plain "A - B" once the markers come off, and both would be
# read as a fixture between two clubs that do not exist.
#
# AND THE FRENCH FEED'S BUILD-UP AND WRAP, which are the same programme
# in another language: "Avant Match Reims vs Guingamp" and "Apres Match
# St Etienne vs Montpellier" are a studio hour either side of a match
# that is also in the guide at its own time. They read as a fixture —
# two real clubs, a "vs" between them — and each would have put a second
# row on the board for a match already there, an hour out.
NOT_A_FIXTURE = ("لا توجد", "لم يُعلن", "no listing", "no match",
                 "preview", "review", "highlights", "magazine",
                 "weekly", "classic", "best of", "top 10",
                 "avant match", "avant-match", "apres match",
                 "apres-match", "après match", "après-match",
                 "multiligue", "live studio")

# A grid also carries last season's football. beIN Turkey lists
# "Beşiktaş - Adanaspor (00-01) 21.hafta" — a match from 2000 — and a
# round number or a season in parentheses is what marks those. A repeat
# given a live match's channel is worse than a match with no channel.
A_REPEAT = re.compile(r"\(\d{2}[-–]\d{2}\)|\bhafta\b|\bözet\b|\bozet\b"
                      r"|\bmaç özetleri\b|\bhaber\b"
                      # "التالي: بيرنلي - ميدلزبره" is Alwan saying what
                      # comes AFTER the programme now on. The clubs are
                      # real and the time on the row is not theirs, so
                      # taking it hands a channel to whatever else falls
                      # inside the two-hour window. The same match is
                      # published again at its own time.
                      r"|التالي|\bnext\s*:"
                      # A season, a part or an episode belongs to a
                      # series, not to a match.
                      r"|الموسم|الجزء|الحلقة|\bseason\b|\bepisode\b", re.I)

# A ROUND IS A SERIES EPISODE IN ONE TITLE AND A CUP ROUND IN ANOTHER,
# and the two cannot be told apart by the words alone:
#
#     Longines Global Champions Tour - London Jumping - Round 1 …   ×16
#     EN Carabao Cup Highlights 2026/27 | Round 2                   × 3
#     Millwall vs Newcastle - Carabao Cup 2026 / 2027 - Round 3     × 3
#
# This lived in A_REPEAT, where it refused all twenty-two — and the last
# three are the League Cup, asked for by name. What separates them is
# not the round: it is that a fixture NAMES TWO CLUBS with the word this
# grid puts between them. A round in a title that has no "vs" in it is a
# session of something, so it is still refused; a round in one that does
# is which round of the cup this is.
#
# The highlights are refused anyway, one line up, for being highlights.
A_SERIES_ROUND = re.compile(r"\bround\s*\d|\bجولة\b", re.I)

# One channel written eight ways. Alwan publishes Sport/Sports, HD, SD, 4K
# and RAW as separate channels, and a match on all of them would fill the
# row with the same name eight times over.
QUALITY = re.compile(r"\s*\b(?:HD|SD|FHD|UHD|4K|RAW|8K)\b", re.I)


def one_channel(name: str) -> str:
    """A channel name with its quality variants folded into one.

    The fold exists because Alwan publishes Sport/Sports, HD, SD, 4K and
    RAW as separate channels and a match on all of them would fill the
    row with one name eight times. It must not run so far that the name
    stops being a channel: "beIN 4K" is Doha's own feed, and folding it
    to "beIN" printed a row telling a viewer to turn to a channel that
    does not exist under that name anywhere in the guide.

    So a quality word comes off only while something still identifies
    what is left — a number, or more than one word. "Alwan Sport 1 HD"
    keeps "Alwan Sport 1"; "beIN 4K" keeps its 4K, because 4K is the
    whole of what distinguishes it.
    """
    folded = norm(QUALITY.sub("", name).replace("Sports", "Sport"))
    if not folded:
        return norm(name)
    identified = any(ch.isdigit() for ch in folded) or len(folded.split()) > 1
    return folded if identified else norm(name)


# The word a grid puts between two clubs. Alwan and beIN Turkey write a
# dash; beIN Qatar writes "vs", "vs." or "v" and then names the
# competition after a dash — "Ipswich Town v Liverpool - English Premier
# League 2026/2027". Split that on the dash and the fixture becomes
# "Ipswich Town v Liverpool" against "English Premier League", which is
# not two clubs and matches nothing. Where one of these words is present
# it is the separator, and the dash is the competition's.
VERSUS = re.compile(r"\s+(?:vs\.?|v|x)\s+", re.I)


def two_sides(clean: str) -> list[str]:
    """The title split where this grid actually separates its clubs."""
    if VERSUS.search(clean):
        sides = VERSUS.split(clean, maxsplit=1)
        # Whatever follows the away club's name is the competition.
        if len(sides) == 2:
            sides[1] = sides[1].split(" - ")[0]
        return [norm(side) for side in sides]
    return [norm(side) for side in clean.split(" - ")]


def fixture_in(title: str) -> tuple[str, str]:
    """The two clubs in a grid title, or a pair of empty strings.

    Deliberately unambitious. A title has to reduce to two club names once
    its markers are stripped; anything carrying a round in the middle is
    left alone rather than guessed at, because the cost of guessing
    wrongly is a channel on the wrong match.

    A season, a part or an episode is not a fixture. A general channel's
    grid is full of "حكي سياسي - الموسم الثالث" and "مطبخ رؤيا - حلويات
    غربية", which are a plain "A - B" and nothing to do with football —
    2711 of them in one guide published here. None can currently reach the
    board, because a club still has to match; the reason they must be
    refused anyway is that the club rule is the LAST line, not the first,
    and a source is one edit away from being wired in by someone who read
    the fixture count and not this comment.
    """
    clean = norm(NOISE.sub(" ", title or ""))
    if any(word in clean.casefold() for word in NOT_A_FIXTURE):
        return "", ""
    if A_REPEAT.search(clean):
        return "", ""
    if A_SERIES_ROUND.search(clean) and not VERSUS.search(clean):
        return "", ""
    sides = two_sides(clean)
    if len(sides) != 2 or not all(sides):
        return "", ""
    if any(len(side) < 2 or len(side) > 40 for side in sides):
        return "", ""
    return sides[0], sides[1]


def one_club_matches(first: str, second: str) -> bool:
    """Whether these two fixtures share a club, across the scripts.

    epg_lib's strict answer, asked of each side. One side is enough: a
    club cannot be playing two matches at the same minute, so an exact
    match at an agreed minute identifies the fixture.
    """
    left, right = fixture_in(first), fixture_in(second)
    if not all(left) or not all(right):
        return False
    return any(one_club(a, b) for a in left for b in right)


def one_club(first: str, second: str) -> bool:
    """One club, whether the two names cross the scripts or not.

    epg_lib answers across them and refuses within one, so within one this
    asks for the skeletons to be EQUAL — equality, never a ratio. That is
    what lets a guide written in Latin be matched to a board row written
    in Latin: "Galatasaray" is "Galatasaray". "Mainz" and "Monza" reduce
    to manz and manza and stay two clubs, which is the pair epg_lib names
    as the reason a ratio cannot be used here.
    """
    if same_club(first, second):
        return True
    skeleton = club_skeleton(first)
    return bool(skeleton) and skeleton == club_skeleton(second)


def broadcasts(path: str, mark: str) -> list[dict]:
    """Every fixture one published guide names, with the channel showing it."""
    if not os.path.exists(path):
        return []
    try:
        guide = ET.parse(path).getroot()
    except Exception:
        return []

    named = {}
    for channel in guide.findall("channel"):
        label = channel.find("display-name")
        named[channel.get("id")] = norm(
            label.text if label is not None and label.text else channel.get("id"))

    out = []
    for programme in guide.findall("programme"):
        title = programme.find("title")
        home, away = fixture_in(title.text if title is not None else "")
        if not home:
            continue
        try:
            start = datetime.strptime(programme.get("start", ""), XMLTV_TIME)
        except ValueError:
            continue
        channel = one_channel(named.get(programme.get("channel"), ""))
        if not channel:
            continue
        out.append({"start": start, "title": f"{home} - {away}",
                    "channel": f"{channel}{mark}"})

    # The same match on eight spellings of one channel is one broadcast.
    seen, kept = set(), []
    for row in out:
        key = (row["start"], row["title"], row["channel"])
        if key not in seen:
            seen.add(key)
            kept.append(row)
    return kept


def attach(events: list[dict], rows: list[dict], label: str) -> int:
    """Put each broadcast's channel on the board row it belongs to."""
    found = 0
    for row in rows:
        for event in events:
            if abs(event["start"] - row["start"]) > SLACK:
                continue
            if not one_club_matches(event["title"], row["title"]):
                continue
            if row["channel"] not in event["channels"]:
                event["channels"].append(row["channel"])
                found += 1
    log(f"  {label}: {len(rows)} broadcast(s) named, "
        f"{found} channel(s) added to the board")
    return found


def add_channels(events: list[dict],
                 extra: dict[str, list[dict]] | None = None) -> int:
    """Name, on each event, any of this reader's channels carrying it.

    `extra` is for listings read over the network — Spor Ekranı, and
    livesoccertv for the American broadcasters — each named by its
    source and arriving in the same {start, title, channel} shape. They
    go through the same matching as the guides published here, because
    the rule that makes this safe is the matching, not where the rows
    came from.
    """
    added = 0
    for path, mark in GUIDES:
        added += attach(events, broadcasts(path, mark),
                        os.path.basename(path))
    for name, rows in (extra or {}).items():
        if rows:
            added += attach(events, rows, name)
    return added


# ─── The second board: events that are not two clubs ────────────────────
#
# A grand prix has no home and away, and neither has a UFC card, so
# nothing above can match them: fixture_in() wants "A - B" and returns
# nothing for "Italian Grand Prix Practice 1".
#
# The rule underneath is the same one, though, and it is the reason this
# is safe: TWO INDEPENDENT ANCHORS. There it is the kickoff minute and a
# club; here it is the start minute and a phrase that names the event.
# One alone is a coincidence — beIN shows something at 10:30 every day —
# and both together is the same broadcast written twice.
#
# WHERE THE FACT COMES FROM MATTERS MORE THAN THE MATCHING. A reader
# named beIN for Formula One and STARZPLAY for the UFC and was right, and
# it was still the wrong way to know it: a hand-written rights table is a
# claim that goes stale silently the season it stops being true. These
# guides are the broadcasters' own feeds, rebuilt every hour, and they
# say it themselves —
#
#   bein_sports_qatar_epg.xml   63 F1 programmes, 294 tennis
#   starzplay_epg.xml           14 UFC, among them Dana White's
#                               Contender Series and The Ultimate Fighter
#
# — so nothing here asserts who carries what. It reads it. The day beIN
# loses Formula One, its feed stops carrying it and this stops saying it,
# with nobody editing a line.
#
# The phrase is what stops one grand prix being mistaken for another, and
# it earns its place: STARZPLAY's guide carries "Emirates Great Britain
# Grand Prix - SailGP", which is sailing. "Italian Grand Prix" does not
# appear in it, and that is the whole test.
A_GRAND_PRIX = re.compile(r"([A-Z][\w’'-]*(?:\s+[A-Z][\w’'-]*)*\s+Grand\s+Prix)")
A_MAJOR = re.compile(r"(us open|wimbledon|australian open|roland garros"
                     r"|french open)", re.I)
A_SESSION = re.compile(r"(practice\s*\d|qualifying|sprint|\brace\b)", re.I)


def what_names_it(event: dict) -> list[str]:
    """The phrases a guide would have to print to be showing THIS event.

    Every one of them must appear, so a longer list is a stricter match.
    An event this cannot name returns nothing and is left alone — which
    is most of them, and is correct: a board may not put a channel on an
    event nobody published.
    """
    title = event.get("title", "") or ""
    sport = event.get("sport", "")

    if sport == "F1":
        prix = A_GRAND_PRIX.search(title)
        if not prix:
            return []
        wanted = [prix.group(1)]
        session = A_SESSION.search(title)
        if session:
            # Practice 1 is not Practice 2 and neither is the race.
            wanted.append(session.group(1))
        return wanted

    if sport == "Tennis":
        major = A_MAJOR.search(title)
        return [major.group(1)] if major else []

    if sport == "MMA":
        return ["UFC"] if re.search(r"\bUFC\b", title) else []

    return []


def says_all_of(title: str, phrases: list[str]) -> bool:
    low = norm(title).casefold()
    return all(phrase.casefold() in low for phrase in phrases)


def programmes(path: str, mark: str) -> list[dict]:
    """Every programme one guide publishes, with the channel showing it.

    Unlike broadcasts() above this parses no fixture out of the title —
    the events it is for have no two sides — so the title is kept whole
    and matched against by phrase.
    """
    if not os.path.exists(path):
        return []
    try:
        guide = ET.parse(path).getroot()
    except Exception:                                         # noqa: BLE001
        return []

    named = {}
    for channel in guide.findall("channel"):
        label = channel.find("display-name")
        named[channel.get("id")] = norm(
            label.text if label is not None and label.text
            else channel.get("id"))

    out = []
    for programme in guide.findall("programme"):
        title = programme.find("title")
        text = norm(title.text if title is not None and title.text else "")
        if not text:
            continue
        try:
            start = datetime.strptime(programme.get("start", ""), XMLTV_TIME)
        except ValueError:
            continue
        channel = one_channel(named.get(programme.get("channel"), ""))
        if not channel:
            continue
        out.append({"start": start, "title": text,
                    "channel": f"{channel}{mark}"})
    return out


def add_channels_by_name(events: list[dict]) -> int:
    """Name, on each event, the channel this reader's own guides show it on."""
    named = 0
    asked = [(event, what_names_it(event)) for event in events]
    for path, mark in GUIDES:
        rows = programmes(path, mark)
        if not rows:
            continue
        found = 0
        for event, phrases in asked:
            if not phrases:
                continue
            for row in rows:
                if abs(event["start"] - row["start"]) > SLACK:
                    continue
                if not says_all_of(row["title"], phrases):
                    continue
                if row["channel"] not in event["channels"]:
                    event["channels"].append(row["channel"])
                    found += 1
                break
        if found:
            log(f"  {os.path.basename(path)}: {found} channel(s) named "
                f"from this reader's own guide")
        named += found
    return named


# ─── Fights our own guides have and no listings page does ───────────────
#
# A reader photographed RFC — an MMA promotion in Amman — announced live
# on Roya TV, and asked for it. It needed no assertion at all: Roya's own
# feed is already built here every hour, and it has the event, at the
# minute the announcement gave.
#
#     roya_jordan_epg.xml   بطولة RFC   2026-09-04 17:30 UTC
#     the announcement      الجمعة 8:30 مساءً  (+3 GMT) = 17:30 UTC
#
# So this reads it rather than being told it. The rule that makes it safe
# is that a COMPETITION is named, not a channel: a line here says "this
# guide, that competition, that sport", and the channel comes from
# whichever of the guide's own channels is showing it. Nobody writes down
# who carries what.
#
# WHY IT IS SO NARROW. Roya is a general channel — 4151 programmes, most
# of them news and drama — and that is exactly why own_guides' football
# matcher refuses to read it at all: 1728 of its titles parse as "A - B"
# and "مطبخ رؤيا - سلطات" is a cookery show. Matching a NAMED competition
# cannot make that mistake, because no cookery show is called RFC. Add a
# line only for a competition whose name is its own.
OUR_OWN_FIGHTS = (
    # (guide, mark, what the title must say, the sport, what to call it)
    ("roya_jordan_epg.xml", "",
     re.compile(r"\bRFC\b", re.I), "MMA", "RFC"),
)


def fights_our_guides_have(floor=None, ceiling=None) -> list[dict]:
    """Events from this repository's own guides, in the board's shape.

    Not channels for events somebody else listed — the EVENTS, from a
    broadcaster's own schedule, because for some competitions there is no
    listings page anywhere and the broadcaster is the only one who says
    it is happening at all.
    """
    out: list[dict] = []
    for path, mark, names_it, sport, competition in OUR_OWN_FIGHTS:
        found = 0
        for row in programmes(path, mark):
            if not names_it.search(row["title"]):
                continue
            if floor is not None and not (floor <= row["start"] < ceiling):
                continue
            out.append({
                "start": row["start"],
                "title": norm(row["title"]),
                "competition": competition,
                "sport": sport,
                "channels": [row["channel"]],
            })
            found += 1
        if found:
            log(f"  {os.path.basename(path)}: {found} {competition} "
                f"event(s) this repository already had")

    # One programme, however many of a broadcaster's channels carry it.
    seen, kept = set(), []
    for event in sorted(out, key=lambda one: one["start"]):
        key = (event["start"], event["title"])
        if key in seen:
            continue
        seen.add(key)
        kept.append(event)
    return kept


# ─── Turkish football, from the sources asked for by name ───────────────
#
# Asked for repeatedly and not done, so it is written down here: the
# Turkish clubs come from Spor Ekranı and from this reader's OWN guides —
# beIN Qatar and Alwan — and not from a general listings page.
#
# The listings page is why. livefootballtv gave four Süper Lig fixtures
# ONE time, 2026-09-06 00:00 UTC, and beIN's own feed had every one of
# them on a different day. And beIN does not merely have them: it MARKS
# THE LIVE AIRING, in its own title, so there is nothing to infer —
#
#   2026-09-04 16:50  beIN 5  • Live   İstanbul Başakşehir vs Galatasaray
#   2026-09-05 16:50  beIN 5  • Live   Fenerbahçe vs Beşiktaş
#   2026-09-06 16:50  beIN 5  • Live   Trabzonspor vs Gençlerbirliği
#   2026-09-07 16:50  beIN 3  • Live   Göztepe vs Gaziantep
#
# — against eighteen further entries for the same four matches, which are
# repeats. THE LIVE MARK IS THE WHOLE RULE. Without it the earliest
# airing looks like the kickoff and is often yesterday's match shown
# again at breakfast; with it there is no judgement to make.
#
# The time is beIN's own start, ten minutes before the kickoff, because
# that is when a viewer should turn it on and because inventing the
# kickoff from it would be inventing something.
A_LIVE_AIRING = re.compile(r"•\s*Live|\bLIVE\b")

# What a broadcaster's grid puts after a club's name and a board should
# not: the company form. Turkish clubs are joint-stock companies and beIN
# writes them that way — "Fenerbahçe A.Ş." — which is correct and is not
# what anybody calls them.
A_COMPANY = re.compile(
    r"\s+(?:A\.?Ş\.?|AS|FK|Fk|SK|Futbol\s+Kulübü(?:\s+A\.?Ş\.?)?)\.?$",
    re.I)

# EVERY FOOTBALL COMPETITION beIN's OWN GUIDE MARKS LIVE, and not one
# league of it.
#
# This carried a single line — the Turkish league — and everything else
# beIN broadcasts reached the board only if some listings page happened
# to list it first. Said plainly, twice:
#
#     "لما احكيلك استخدم مصدر bein sports qatar و تروح تستخدم مصدر اخر
#      شو بكون مشكلتك؟"
#
# and the measurement agreed: beIN's guide carries 403 live-marked
# programmes, of which this read four.
#
# The competitions below are the football ones beIN actually marks live,
# counted off its own guide rather than guessed at:
#
#     16  English Premier League          10  French Ligue 1
#     10  Spanish LaLiga                   9  UEFA Champions League
#      6  EFL Championship                 4  Turkish Super League
#      4  Ligue 2                          3  UEFA Youth League
#      3  LaLiga Hypermotion              20  FIFA Women's World Cup
#
# and what is NOT here is as measured: 43 tennis, 4 baseball, 3 handball,
# a padel and seven studio hours all carry "vs" in a title and none of
# them is a fixture between two clubs. They are excluded by never being
# named, which is why this is a list of competitions and not a rule about
# titles.
#
# The board's own filter still has the last word — a competition nobody
# asked for is dropped by wanted() exactly as it is from every other
# source — so the Arabic names here are what that filter reads, and they
# are written to say what the competition IS rather than to get it past
# anything. Measured against the filter as it stands:
#
#   kept     the Premier League, LaLiga, Ligue 1, the Champions League,
#            the Süper Lig, the Women's World Cup, and the whole EFL —
#            the Championship, League One, League Two, the League Cup and
#            the FA Cup, asked for by name
#   refused  LaLiga Hypermotion and Ligue 2, exactly as they are refused
#            from every listings page, because nobody asked for Spain's
#            or France's second tier. They are listed anyway: what beIN
#            broadcasts is a fact about beIN, and the day one of them is
#            wanted it is wanted in ONE place, not here.
_BEIN = "bein_sports_qatar_epg.xml"
OUR_OWN_FIXTURES = (
    # (guide, mark, the competition in the guide's own words, what to
    #  call it on the board)
    (_BEIN, "", re.compile(r"English Premier League", re.I),
     "الدوري الإنجليزي الممتاز"),
    # Before the plain LaLiga line, which is a substring of this one.
    (_BEIN, "", re.compile(r"LaLiga Hypermotion", re.I),
     "دوري الدرجة الثانية الإسباني"),
    (_BEIN, "", re.compile(r"Spanish LaLiga|\bLiga\s*-\s*J\d+\s*-\s*FOOTBALL",
                           re.I), "الدوري الإسباني"),
    (_BEIN, "", re.compile(r"\bLigue\s*2\b", re.I),
     "دوري الدرجة الثانية الفرنسي"),
    (_BEIN, "", re.compile(r"\bLigue\s*1\b", re.I), "الدوري الفرنسي"),
    (_BEIN, "", re.compile(r"UEFA Youth League", re.I),
     "دوري أبطال أوروبا للشباب"),
    (_BEIN, "", re.compile(r"UEFA Champions League", re.I),
     "دوري أبطال أوروبا"),
    # THE EFL, ALL OF IT, AND THE LEAGUE CUP WITH IT. Asked for by name —
    # "efl , championship, fa cup كلهم هدول beIN qatar بتبثها كمان خليه
    # مرجع قوي الهم زيادة على sky sports" — and beIN's guide answers:
    #
    #     EFL - English Football League SkyBet - Championship   10 live
    #     EFL - English Football League SkyBet - League Two      2 live
    #     Carabao Cup 2026 / 2027 - Round 3                      3 live
    #     FA Cup - FOOTBALL                                      0 live
    #
    # The FA Cup is listed with none showing, and that is the point of
    # listing it: beIN carries last season's rounds in the same guide, so
    # the wording is known, and the day this season's reach the grid they
    # are read without another change.
    #
    # ANCHORED ON THE EFL's OWN PREFIX rather than on the word
    # "Championship", which beIN also puts on the FIA Formula 3
    # Championship, the Formula Regional European Championship and the
    # World Athletics U20 Championships — nineteen programmes, six of
    # them marked live. None can become a fixture, because none has a
    # "vs" in it, but a pattern that matches them is one edit away from
    # a motor race on the football board.
    (_BEIN, "", re.compile(r"SkyBet\s*-\s*Championship", re.I),
     "الدوري الإنجليزي الدرجة الأولى"),
    (_BEIN, "", re.compile(r"SkyBet\s*-\s*League\s+One", re.I),
     "الدوري الإنجليزي الدرجة الثانية"),
    (_BEIN, "", re.compile(r"SkyBet\s*-\s*League\s+Two", re.I),
     "الدوري الإنجليزي الدرجة الثالثة"),
    (_BEIN, "", re.compile(r"Carabao\s+Cup|EFL\s+Cup", re.I),
     "كأس الرابطة الإنجليزية"),
    (_BEIN, "", re.compile(r"\bFA\s+Cup\b|Emirates\s+FA\s+Cup", re.I),
     "كأس الاتحاد الإنجليزي"),
    (_BEIN, "", re.compile(r"Turkish Super League|Championnat de Turquie",
                           re.I), "الدوري التركي الممتاز"),
    (_BEIN, "", re.compile(r"Fifa Women World Cup", re.I),
     "كأس العالم للسيدات"),
)


def a_club(name: str) -> str:
    """A club's name without the company form a TV grid prints after it."""
    was = None
    while was != name:
        was = name
        name = A_COMPANY.sub("", norm(name)).strip()
    return name


def fixtures_our_guides_have(floor=None, ceiling=None) -> list[dict]:
    """Fixtures from this reader's own guides, live airings only."""
    out: list[dict] = []
    for path, mark, names_it, competition in OUR_OWN_FIXTURES:
        found = repeats = 0
        for row in programmes(path, mark):
            if not names_it.search(row["title"]):
                continue
            if not A_LIVE_AIRING.search(row["title"]):
                repeats += 1
                continue
            # EXACTLY ONE SEPARATOR, because beIN Qatar writes every
            # fixture as "A vs B - Competition" and a title that does not
            # is not a fixture in that grid. Two of the day's live-marked
            # titles prove both directions:
            #
            #   "Bein Champions - UEFA Champions League 2026-2027"
            #        no "vs" at all — a studio hour, read as a fixture
            #        between a club called Bein Champions and one called
            #        UEFA Champions League
            #   "Olympique Lyonnais vs Lyon vs Auxerre - French Ligue 1"
            #        two of them — beIN's own slip, and no way to know
            #        which two of the three names are the clubs
            #
            # A row that reaches the board is a row a viewer is told to
            # turn to a channel for, so an ambiguous one is refused
            # rather than guessed at.
            if len(VERSUS.findall(f" {norm(NOISE.sub(' ', row['title']))} ")) != 1:
                continue
            home, away = fixture_in(row["title"])
            home, away = a_club(home), a_club(away)
            if not home or not away:
                continue
            if floor is not None and not (floor <= row["start"] < ceiling):
                continue
            out.append({
                "start": row["start"],
                "title": f"{home} - {away}",
                "competition": competition,
                "channels": [row["channel"]],
            })
            found += 1
        if found or repeats:
            log(f"  {os.path.basename(path)}: {found} live {competition}, "
                f"{repeats} repeat(s) of them ignored")

    return one_row_per_fixture(out)


def one_row_per_fixture(out: list[dict]) -> list[dict]:
    """One row per match, however many of beIN's own feeds carry it.

    beIN shows a match on its Arabic channel, its English one, its French
    one and sometimes in 4K, each as its own programme starting at its own
    minute. Counted on one Saturday: Manchester City v Coventry on beIN 1
    at 13:45 and beIN EN 1 at 14:00, Real Madrid v Inter on beIN 1 at
    18:30 and beIN EN 1 at 19:00, Arsenal v Chelsea on two. Left alone
    they are two rows for one match, which is the fault this week began
    with, arriving from a new direction.

    They are folded on the same two anchors used everywhere else here —
    ONE CLUB, EXACTLY, and the competition — inside the window a grid's
    build-up can occupy. A club plays one match in two hours, so two rows
    of one competition sharing a club inside that window are one match.

    THE LATEST START WINS, and that is not arbitrary. The build-up is what
    makes the starts differ: the Arabic feed opens with a studio and the
    English one joins at the whistle, so the later of the two is the one
    nearer the kickoff.
    """
    kept: list[dict] = []
    for event in sorted(out, key=lambda one: one["start"]):
        for already in kept:
            if already["competition"] != event["competition"]:
                continue
            if abs(already["start"] - event["start"]) > ONE_FIXTURE_A_DAY:
                continue
            if not one_club_matches(already["title"], event["title"]):
                continue
            if abs(already["start"] - event["start"]) <= SLACK:
                # One match on several of beIN's feeds. The later start is
                # nearer the kickoff — the earlier one opened with a
                # studio — and every feed carrying it is a place to watch.
                already["start"] = max(already["start"], event["start"])
                for channel in event["channels"]:
                    if channel not in already["channels"]:
                        already["channels"].append(channel)
            # Further out it is a REPEAT THAT KEPT THE LIVE MARK, which
            # beIN's own guide does: Burnley v Bristol City is marked live
            # on beIN XTRA 4 at 13:50 and again on beIN EN 1 twelve hours
            # later. The first is the match. The second is neither a
            # second row nor a channel to send anybody to at 13:50, so it
            # is dropped whole.
            break
        else:
            kept.append(dict(event, channels=list(event["channels"])))
    return sorted(kept, key=lambda one: one["start"])
