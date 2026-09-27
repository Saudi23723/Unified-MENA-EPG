#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
الجديد — Al Jadeed (Lebanon).

This is a reader, not a guide of its own: roya_jordan_epg.py imports it
and writes Al Jadeed into roya_jordan_epg.xml alongside the Roya
channels, so the channel arrives on a link that is already in use rather
than on a new one. Two workflows must never write the same file, so
Al Jadeed has no workflow of its own — it refreshes on Roya's half-hourly
run.

Source: the broadcaster's own dated schedule pages.

  https://www.aljadeed.tv/schedule-channels-date/1/YYYY/MM/DD/ar

Each programme is one card, server-rendered:

    <div class="...">  المدة: 60 دقيقة </div>
    <div class="text-title-4 padding-b-xs-15"> 09:00 </div>
    <a href='/episodes/528/...'> هنا بيروت </a>

so a run gets the start, the length and the name without guessing any of
them, and the day links on the page reach a week ahead.

Why the clock needs measuring, and how the page measures it for us
------------------------------------------------------------------
Al Jadeed prints bare times and never names a timezone, and the times it
prints are not Beirut's: the site renders them for wherever it thinks the
caller is, and from a CI runner that came out six hours behind Beirut.
Publishing that would have been silently wrong for every viewer.

But the channel names its own hourly bulletins after the hour they air —
"موجز الساعة 10:30 صباحاً" sitting in the 04:30 column — so the real clock
is written inside the page's own titles. Every run recovers the offset by
comparing the two, on each day page separately, and only accepts a whole
number of hours agreed by more than one bulletin. If a page ever stops
naming its bulletins, that day is skipped rather than published at a
guessed time. This is the same rule the Al Jazeera guide follows with
"بتوقيت مكة": no anchor, no publication.

The recovered wall time is Beirut's, so it is attached to Asia/Beirut and
converted to UTC. Lebanon does observe daylight saving, and because the
offset is re-measured on every run rather than hard-coded, both the zone
change and any change in how the site renders are absorbed automatically.

No Live badge. The word "مباشر" appears exactly four times on every day
page — including days that have not happened yet — so it is the site's own
navigation ("بث مباشر"), not a per-programme marker. Badging on that would
be this file inventing a claim the source never made, the same trap that
was rejected on Roya, STARZPLAY and Al Jazeera.

Where the neighbouring channels went: elcinema.com does list Jordan TV,
Amman TV and Al Araby 2, but it renders times the same geolocated way and
carries no self-anchor at all — measured against Roya's own API its rows
came out a flat six hours off, i.e. UTC-03:00, which is nobody's
broadcast clock. Al Araby publishes no schedule on either alaraby.com or
alaraby2.com, sitemaps included. None of that is publishable.
"""

from __future__ import annotations

import html as htmllib
import os
import re
from datetime import date, datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

import xml.etree.ElementTree as ET

from epg_lib import (
    add_programme, close_channel_gaps, fetch, log, norm, resolve_overlaps,
    utc_now, warn,
)

UTC = timezone.utc
# Lebanon observes daylight saving, so this has to be the real zone rather
# than a fixed offset. The wall time handed to it is recovered from the
# page on every run, so a DST switch needs no change here.
BEIRUT = ZoneInfo("Asia/Beirut")

# Channel 1 on the site is الجديد itself.
DAY_URL = "https://www.aljadeed.tv/schedule-channels-date/1/{0:%Y/%m/%d}/ar"
# The page's own day navigation reaches about a week out.
DAYS_AHEAD = 6

CHANNEL_ID = "AlJadeed.lb"
CHANNEL_AR = "الجديد"
CHANNEL_EN = "Al Jadeed"

# The site publishes 03:00 to 20:59 and leaves the rest of the night
# unwritten, so the channel went blank every night between 20:59 and
# 03:00 — six hours in which a player showed a dead row. The station
# is on air; it is the listing that stops, and this says so.
OVERNIGHT = "برامج الجديد — لم تُعلن التفاصيل"
LOGO_BASE = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG"
             "/main/logos")
LOGO_FILE = "aljadeed.png"

# duration, then the time column, then the programme's own link.
CARD_RE = re.compile(
    r'المدة:\s*(\d{1,4})\s*دقيقة\s*</div>\s*'
    r'<div[^>]*>\s*(\d{1,2}):(\d{2})\s*</div>\s*'
    r'<a [^>]*>(.*?)</a>',
    re.S)
# "موجز الساعة 10:30 صباحاً" — the bulletin that names its own hour, which
# is what anchors the whole file.
BULLETIN_RE = re.compile(r'موجز\s+الساعة\s+(\d{1,2}):(\d{2})\s*(صباح|مساء)?')

XMLTV_TIME = "%Y%m%d%H%M%S %z"
KEEP_BEHIND = timedelta(days=1)
KEEP_AHEAD = timedelta(days=14)
# Longest run the page is trusted to be describing. Al Jadeed's own cards
# top out at a two-hour morning show.
MAX_MINUTES = 300

NEWS_WORDS = ("نشرة", "موجز", "الأخبار", "أخبار")


def clean(value: str) -> str:
    return norm(re.sub(r"<[^>]+>", " ", htmllib.unescape(value or "")))


def cards(page: str) -> list[tuple[int, int, str]]:
    """(column minutes, duration, title), each card once.

    The page renders every card twice, once for the desktop layout and
    once for the mobile one, so identical cards collapse.
    """
    seen: set[tuple[int, int, str]] = set()
    out: list[tuple[int, int, str]] = []
    for duration, hour, minute, title in CARD_RE.findall(page):
        row = (int(hour) * 60 + int(minute), int(duration), clean(title))
        if not row[2] or not 0 < row[1] <= MAX_MINUTES or row in seen:
            continue
        seen.add(row)
        out.append(row)
    return out


def measure_offset(rows: list[tuple[int, int, str]]) -> int | None:
    """Minutes to add to the time column so it reads Beirut wall time.

    Recovered from the bulletins that carry their own hour in their name.
    A bulletin written "10:30 صباحاً" says which half of the day it means
    and counts double; one written "5:30" could be either, so it votes for
    both readings and only helps confirm what the unambiguous ones say.
    """
    votes: dict[int, int] = {}
    for column, _duration, title in rows:
        found = BULLETIN_RE.search(title)
        if not found:
            continue
        hour, minute, half = int(found.group(1)), int(found.group(2)), found.group(3)
        if half == "صباح":
            named = [(0 if hour == 12 else hour) * 60 + minute]
        elif half == "مساء":
            named = [(12 if hour == 12 else hour + 12) * 60 + minute]
        else:
            named = [hour * 60 + minute, ((hour + 12) % 24) * 60 + minute]
        weight = 2 if half else 1
        for candidate in named:
            key = (candidate - column) % 1440
            votes[key] = votes.get(key, 0) + weight

    if not votes:
        return None
    best, score = max(votes.items(), key=lambda kv: kv[1])
    # A real timezone difference is whole hours, and one lone ambiguous
    # bulletin is not enough to publish a whole day on.
    if best % 60 or score < 2:
        return None
    return best


def parse_day(page: str, day: date) -> list[dict]:
    rows = cards(page)
    if not rows:
        warn(f"Al Jadeed {day}: no programme cards on the page")
        return []

    offset = measure_offset(rows)
    if offset is None:
        warn(f"Al Jadeed {day}: the page names no bulletin hour, so its clock "
             f"cannot be anchored — the day is skipped rather than guessed")
        return []

    midnight = datetime.combine(day, dtime(0, 0))
    events: list[dict] = []
    for column, duration, title in rows:
        start = (midnight + timedelta(minutes=column + offset)).replace(tzinfo=BEIRUT)
        stop = (midnight + timedelta(minutes=column + offset + duration)).replace(tzinfo=BEIRUT)
        events.append({"start": start.astimezone(UTC), "stop": stop.astimezone(UTC),
                       "title": title})
    log(f"  {day}: {len(events)} programmes, clock recovered as {offset / 60:+.0f}h "
        f"off the column")
    return events


def carry_forward(path: str) -> list[dict]:
    """Al Jadeed rows already in the guide, so one bad fetch costs nothing.

    The file this reads is the Roya guide, which Al Jadeed now shares. Only
    rows on Al Jadeed's own channel are touched; the Roya channels are
    written by their own generator and never read back here.
    """
    if not os.path.exists(path):
        return []
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        warn(f"previous {path} unreadable, Al Jadeed starts clean: {exc}")
        return []

    out: list[dict] = []
    for programme in root.findall("programme"):
        if programme.get("channel") != CHANNEL_ID:
            continue
        try:
            start = datetime.strptime(programme.get("start"), XMLTV_TIME)
            stop = datetime.strptime(programme.get("stop"), XMLTV_TIME)
        except Exception:
            continue
        title_el = programme.find("title")
        title = norm(title_el.text if title_el is not None else "")
        if not title or stop <= start:
            continue
        out.append({"start": start.astimezone(UTC), "stop": stop.astimezone(UTC),
                    "title": title})
    return out


def channel_icon() -> str | None:
    """Serve the mark from this repository, but only once it is really there."""
    return f"{LOGO_BASE}/{LOGO_FILE}" if os.path.exists(f"logos/{LOGO_FILE}") else None


def category_for(title: str) -> str:
    return "أخبار" if any(word in title for word in NEWS_WORDS) else "منوعات"


def collect(session, previous_path: str) -> list[dict]:
    """Every Al Jadeed programme worth publishing right now."""
    today = utc_now().astimezone(BEIRUT).date()
    fresh: list[dict] = []
    for step in range(DAYS_AHEAD):
        day = today + timedelta(days=step)
        try:
            fresh += parse_day(fetch(session, DAY_URL.format(day)).text, day)
        except Exception as exc:
            warn(f"Al Jadeed {day} fetch failed: {exc}")

    carried = carry_forward(previous_path)
    if carried:
        log(f"  Al Jadeed carried forward: {len(carried)} already published")
    if not fresh and carried:
        warn("Al Jadeed published nothing readable — the channel is running on "
             "what was already in the guide")

    merged: dict[tuple, dict] = {}
    for event in carried + fresh:
        merged[(event["start"], event["stop"], event["title"])] = event

    now = utc_now()
    kept = [e for e in merged.values()
            if now - KEEP_BEHIND <= e["stop"] and e["start"] <= now + KEEP_AHEAD]
    if not kept:
        return kept

    # No hole anywhere in what we publish — see close_channel_gaps.
    rows = resolve_overlaps(sorted(kept, key=lambda e: e["start"]))
    return close_channel_gaps(
        rows, min(rows[0]["start"], now), max(rows[-1]["stop"], now), OVERNIGHT)


def emit(root: ET.Element, events: list[dict]) -> int:
    """Declare the channel and write its programmes into an existing <tv>."""
    if not events:
        warn("Al Jadeed: nothing to publish, the channel is left out of this run")
        return 0

    channel = ET.SubElement(root, "channel", id=CHANNEL_ID)
    ET.SubElement(channel, "display-name", lang="ar").text = CHANNEL_AR
    ET.SubElement(channel, "display-name", lang="en").text = CHANNEL_EN
    icon = channel_icon()
    if icon:
        ET.SubElement(channel, "icon", src=icon)
    else:
        warn(f"logos/{LOGO_FILE} is not in the repository yet — publishing "
             f"without an icon rather than pointing at a missing file")

    total = 0
    for event in resolve_overlaps(sorted(events, key=lambda e: e["start"])):
        add_programme(root, CHANNEL_ID, event["start"], event["stop"],
                      event["title"], "", category=category_for(event["title"]))
        total += 1

    days = sorted({e["start"].astimezone(BEIRUT).strftime("%Y-%m-%d") for e in events})
    log(f"Al Jadeed: {total} programmes over {len(days)} days "
        f"({days[0]} .. {days[-1]}), no Live badge — the source marks none")
    return total
