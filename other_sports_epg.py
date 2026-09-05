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
import own_guides
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

# FOURTEEN DAYS, not three, and the number is the whole reason the
# events a reader asked for were missing.
#
# Three days is right for football, where every day has a card. It is the
# wrong shape for this board entirely: a grand prix is a weekend, a UFC
# card is a Saturday, a title fight is announced a month out. The source
# was measured and it HAD everything asked for — UFC Fight Night on the
# 5th and the 12th, UFC 331 on the 20th, Contender Series on the 9th,
# Canelo on the 12th — and the window ended before any of it. Nothing was
# being filtered out. It was never being looked at.
#
# A day with nothing on it is not drawn (see build), so fourteen days is
# fourteen days of REACH, not fourteen empty boards.
DAYS_AHEAD = 14

# The reader's order, and the mark each sport wears on the board. A sport
# absent from here cannot reach the board at all, which is what "the big
# competitions only" means in practice.
IN_ORDER = (
    "F1", "Darts", "Boxing", "MMA", "MotoGP", "Tennis",
    "NFL", "NBA", "FIBA", "Golf", "Rugby", "Padel",
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

def _a_bare_title_match(one: str, two: str) -> bool:
    """One bare title a prefix of the other — the fold's own test."""
    mine, yours = a_bare_title(one), a_bare_title(two)
    return mine.startswith(yours) or yours.startswith(mine)


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

        for already in kept:
            if already["start"] != event["start"]:
                continue
            if already.get("sport") != event.get("sport"):
                continue
            if not set(already["channels"]) & set(event["channels"]):
                continue
            mine = a_bare_title(already["title"])
            if not (mine.startswith(bare) or bare.startswith(mine)):
                continue
            if a_card_segment(already["title"]) != segment:
                continue
            into = already
            break

        if into is None:
            kept.append(dict(event, channels=list(event["channels"])))
            continue

        # THE BROADCASTER’S TITLE, not the longer one. Sky’s rows carry
        # the programme itself and no “from” word; when a listings page
        # describes the same broadcast at the same minute on a channel in
        # common, the page’s wording — however rich — is folded away
        # and the broadcaster’s stands.
        if _the_broadcaster_names_it(event, into):
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
    if can_fetch:
        everything += tsn.events(
            session, floor, ceiling,
            sports=("Tennis", "Rugby", "NFL", "Golf", "MMA", "Auto Racing"))
        everything += sportsnet.events(
            session, floor, ceiling, sports=("rugby", "mma"))

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

    # A DAY WITH NOTHING ON IT IS NOT A BOARD. The window reaches two
    # weeks now, and most of those days have no fight and no race — a
    # screen that spends eleven of its fourteen boards saying "لا يوجد
    # حدث" is worse than a shorter one, and every empty board is another
    # twenty seconds a viewer waits to see the next real thing.
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
    # to it, not less — it reaches fourteen days, and a Saturday of UFC
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
