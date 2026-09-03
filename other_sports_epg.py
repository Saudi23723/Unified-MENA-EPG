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
BOARD_COLOURS = 64
MAX_ON_BOARD = 12

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


# WHO ELSE CARRIES IT, from the reader rather than from a listings page.
#
# This board's source is British and only British — measured across all
# 44 of its pages: Sky 1106 mentions, TNT 363, DAZN 226, and not one Fox,
# NBC, ESPN or beIN. So a viewer with a MENA package was being shown, on
# every row, the one set of channels they cannot turn to.
#
# The reader supplied what they can: beIN carries Formula One and the
# tennis majors, STARZPLAY carries the UFC. That is a rights fact and it
# is written down as one — named here, not scraped, and this comment is
# the citation.
#
# THREE RULES KEEP IT HONEST, and they are the same three that let
# الأردن الرياضية be written down for Jordan's league.
#
#   IT ADDS, IT NEVER REPLACES. Whatever the page published stays; this
#   goes beside it. If the two disagree, the reader sees both and can
#   judge, rather than one of them being silently deleted.
#
#   IT IS NARROW. Not "MMA" — the same page carries One Championship, and
#   nobody said STARZPLAY has that. Not "tennis" — the majors, which is
#   what was named. A wide rule here is a wrong channel on a screen.
#
#   IT NAMES A NUMBERLESS CHANNEL ON PURPOSE. "beIN" and not "beIN 3":
#   which of beIN's numbers a session lands on changes week to week and
#   nobody said. Sending a viewer to beIN is true; sending them to beIN 3
#   would be a guess wearing the clothes of a fact.
#
# Add a line only for a fact somebody stated in those terms. An event
# nobody has placed anywhere still shows no channel — that has not
# changed and is not going to.
ALSO_CARRIED_BY = (
    # (sport, what it must be called — or None for all of that sport,
    #  the channel)
    ("F1", None, "beIN SPORTS"),
    ("Tennis", re.compile(r"us open|wimbledon|australian open|roland"
                          r"|french open", re.I), "beIN SPORTS"),
    # The UFC, and what the UFC runs — not everything on a page called
    # "live UFC on TV", which also lists One Championship.
    ("MMA", re.compile(r"\bUFC\b|ultimate fighting|contender series"
                       r"|dana white|ultimate fighter", re.I),
     "STARZPLAY Sports"),
)


def also_carried_by(event: dict) -> list[str]:
    """The stated rights that apply to this event, beside what was read."""
    extra: list[str] = []
    subject = f"{event.get('competition', '')} {event.get('title', '')}"
    for sport, must_say, channel in ALSO_CARRIED_BY:
        if event.get("sport") != sport:
            continue
        if must_say is not None and not must_say.search(subject):
            continue
        if channel not in event["channels"] and channel not in extra:
            extra.append(channel)
    return extra


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
    """The reader's order of sports, and the clock inside each."""
    return sorted(events, key=lambda e: (RANK[e["sport"]], e["start"]))


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
    name = f"other_sports_{index}.png"
    path = os.path.join(BOARD_DIR, name)
    try:
        from match_board import draw_board

        drawn_rows = [dict(event, title=row_title(event)) for event in events]
        board = draw_board(
            day, drawn_rows, now, VIEWER, MATCH_ON_AIR,
            title=CHANNEL_AR, subtitle=f"سباقات ونزالات وبطولات · {VIEWER_NAME}",
            weekday=ARABIC_DAY[day.weekday()], page=page, pages=pages)
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


def collect(session, floor: datetime, ceiling: datetime) -> list[dict]:
    """Every event both sources have, inside the window, that names a channel."""
    everything = world_sport_on_tv.events(session)
    everything += american_sport_on_tv.events(session)

    inside = [dict(event, channels=drop_simulcasts(event["channels"]))
              for event in everything
              if floor <= event["start"] < ceiling]

    # Before wanted(), deliberately. A UFC card the British page has not
    # placed anywhere is still on STARZPLAY, and refusing it for want of a
    # channel the page never had would be throwing away the one fact the
    # reader supplied.
    added = 0
    for event in inside:
        extra = also_carried_by(event)
        if extra:
            event["channels"] = event["channels"] + extra
            added += 1
    if added:
        log(f"  {added} event(s) given the channel a reader named for them")

    kept = [event for event in inside if wanted(event)]
    log(f"  {len(everything)} event(s) offered, {len(inside)} in the window, "
        f"{len(kept)} in a sport asked for and naming a channel")
    return in_the_readers_order(kept)


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

        opens, closes = day_bounds(day)
        add_programme(tv, CHANNEL_ID, opens, closes,
                      day_title(day, today, now),
                      day_page(day, today, now), icon=first_board)
        log(f"  {day} -> {len(today)} event(s) over {len(chunks)} board(s)")

    ok = write_xml_atomic(tv, OUTPUT, generator_name="Today's Other Sports",
                          guard_regression=False, min_programmes=1)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
