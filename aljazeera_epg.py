#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
الجزيرة الإخبارية — Al Jazeera Arabic.

This is a reader, not a guide of its own: roya_jordan_epg.py imports it
and writes Al Jazeera into roya_jordan_epg.xml, so the channel arrives on
a link that is already in use rather than on a new one. Two workflows must
never write the same file, so Al Jazeera has no workflow of its own — it
refreshes on Roya's half-hourly run, which also suits a page that only
ever renders one day at a time.

Source: the broadcaster's own schedule page.

  https://www.aljazeera.net/schedule

It is plain server-rendered HTML, one row per programme:

    <div class="schedule__row">
      <div class="schedule__row__timeslot">00:00</div>
      <div class="schedule__row__showname">نشرة الأخبار</div>
      <div class="schedule__row__description">جولة في أهم الأحداث ...</div>
    </div>

and the page states its own clock — "كل الأوقات بتوقيت مكة" — which is
what makes it safe to publish. Every other Arabic guide reached during
this search printed bare times with no timezone anywhere on the page, and
a guide whose clock cannot be anchored is worse than no guide: it is
silently wrong for everyone outside whatever zone was guessed.

The rows sit inside a per-weekday panel, <div class="schedule__items"
aria-labelledby="wednesday">, and only the current day's panel is filled
server-side; the others are loaded by the page's own JavaScript, which a
plain fetch never runs. So this reads today and accumulates: each run
merges what the page publishes now into what the file already holds and
drops what has aged out. Nothing is invented — every programme was read
from Al Jazeera's page on the day it ran.

Where the sources for the rest went: al-arabiya.net answers 403 to every
path including its own sitemap, almamlakatv.com 403s or 404s on every
schedule path, jrtv.gov.jo serves a 2.6 KB shell, amman.tv returns the
same 16 KB page for every URL, and sama.tv has no schedule page at all.
elcinema.com does carry Jordan TV, Amman TV and Al Araby 2 — but prints
no timezone, and measuring its offset against Roya's own API matched only
a twice-daily bulletin and came back inconclusive. epgshare01 lists the
channel names with five programmes each. None of that is publishable.

No Live badge. Al Jazeera marks one row "يعرض الآن", which means
"on air at the moment you asked" — it is one row per fetch and stale
minutes later, the same trap that was rejected on Roya and STARZPLAY.
The channel is rolling news, so guessing that a bulletin is live would be
a rule this file invented, not something the source said.
"""

from __future__ import annotations

import html as htmllib
import os
import re
from datetime import datetime, timedelta, timezone

import xml.etree.ElementTree as ET

from epg_lib import (
    add_programme, fetch, log, norm, resolve_overlaps, utc_now, warn,
)

UTC = timezone.utc
# The page says so itself: "كل الأوقات بتوقيت مكة". Mecca keeps +03:00 all
# year — Saudi Arabia has never observed daylight saving — so this is a
# fixed offset rather than a zone that could shift under the guide.
MECCA = timezone(timedelta(hours=3))

URL = "https://www.aljazeera.net/schedule"

CHANNEL_ID = "AlJazeera.qa"
CHANNEL_AR = "الجزيرة"
CHANNEL_EN = "Al Jazeera"
LOGO_BASE = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG"
             "/main/logos")
LOGO_FILE = "aljazeera.png"

# The sentence that anchors the whole file. If Al Jazeera ever stops
# printing it, the times can no longer be trusted and nothing is read.
TIMEZONE_NOTICE = "بتوقيت مكة"

PANEL_RE = re.compile(
    r'class="schedule__items"[^>]*aria-labelledby="([a-z]+)"(.*?)(?=class="schedule__items"|\Z)',
    re.S)
# The row that is on air carries an extra "يعرض الآن" element between its
# time and its name. Anything that is not another timeslot is allowed to
# sit in that gap, so the marker cannot be mistaken for the programme.
ROW_RE = re.compile(
    r'class="schedule__row__timeslot">\s*(\d{1,2}:\d{2})\s*</div>'
    r'(?:(?!schedule__row__timeslot).){0,400}?'
    r'class="schedule__row__showname">(.*?)</div>'
    r'(?:\s*<div class="schedule__row__description">(.*?)</div>)?',
    re.S)
# Al Jazeera's own "on air now" label. It is a state, not a programme, so
# it never becomes a title and never becomes a badge.
NOW_LABEL = "يعرض الآن"

WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6}

XMLTV_TIME = "%Y%m%d%H%M%S %z"
KEEP_BEHIND = timedelta(days=1)
KEEP_AHEAD = timedelta(days=14)
# The last row of a day has no successor to end against.
TAIL_MINUTES = 60
# A row ends when the next one starts. If the page ever lists only part of
# a day, that rule would stretch one bulletin across the gap and claim it
# ran for hours, so a run is capped and the gap is left empty instead.
MAX_MINUTES = 240


def clean(value: str) -> str:
    return norm(re.sub(r"<[^>]+>", " ", htmllib.unescape(value or "")))


def date_for_weekday(name: str, today: datetime) -> datetime | None:
    """The dated day this panel is for, nearest to today in Mecca.

    The panel is labelled by weekday only. Anchoring it to the nearest
    matching date rather than assuming "today" means the file stays right
    if Al Jazeera ever fills a panel other than the current one.
    """
    want = WEEKDAYS.get(name)
    if want is None:
        return None
    for delta in (0, 1, -1, 2, -2, 3, -3):
        day = today + timedelta(days=delta)
        if day.weekday() == want:
            return day
    return None


def parse(page: str, today: datetime) -> list[dict]:
    if TIMEZONE_NOTICE not in (page or ""):
        warn("Al Jazeera: the page no longer states 'بتوقيت مكة' — its clock "
             "can no longer be anchored, so nothing is read")
        return []

    events: list[dict] = []
    panels = PANEL_RE.findall(page)
    if not panels:
        warn("Al Jazeera: no schedule panel on the page")
        return []

    for weekday, body in panels:
        day = date_for_weekday(weekday, today)
        rows = ROW_RE.findall(body)
        if day is None or not rows:
            continue

        starts: list[datetime] = []
        titles: list[tuple[str, str]] = []
        offset = 0
        previous: datetime | None = None
        for slot, showname, description in rows:
            title = clean(showname).replace(NOW_LABEL, "").strip()
            if not title:
                continue
            try:
                clock = datetime.strptime(slot, "%H:%M").time()
            except ValueError:
                continue
            start = datetime.combine(day.date(), clock, MECCA) + timedelta(days=offset)
            # The rows run from midnight in broadcast order, so a start that
            # goes backwards has crossed into the next day.
            if previous is not None and start < previous:
                offset += 1
                start += timedelta(days=1)
            previous = start
            starts.append(start)
            titles.append((title, clean(description)))

        for i, start in enumerate(starts):
            stop = starts[i + 1] if i + 1 < len(starts) else start + timedelta(minutes=TAIL_MINUTES)
            stop = min(stop, start + timedelta(minutes=MAX_MINUTES))
            if stop <= start:
                continue
            title, desc = titles[i]
            events.append({"start": start.astimezone(UTC),
                           "stop": stop.astimezone(UTC),
                           "title": title, "desc": desc})
        log(f"  {weekday} ({day:%Y-%m-%d}): {len(starts)} programmes")
    return events


def carry_forward(path: str) -> list[dict]:
    """What the guide already holds, so a one-day page accumulates.

    The file this reads is the Roya guide, which Al Jazeera now shares.
    Only rows on Al Jazeera's own channel are touched.
    """
    if not os.path.exists(path):
        return []
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        warn(f"previous {path} unreadable, starting clean: {exc}")
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
        desc_el = programme.find("desc")
        title = norm(title_el.text if title_el is not None else "")
        # An earlier run mistook the "on air now" label for a programme.
        # Dropping it here means the file cleans itself on the next run
        # rather than carrying the bad row forward forever.
        if NOW_LABEL in title:
            continue
        if not title or stop <= start:
            continue
        out.append({"start": start.astimezone(UTC), "stop": stop.astimezone(UTC),
                    "title": title,
                    "desc": norm(desc_el.text if desc_el is not None else "")})
    return out


def channel_icon() -> str | None:
    """Serve the mark from this repository, but only once it is really there.

    A guide that points at a logo file which does not exist is a broken
    image in every player and a failed health check here, so the icon is
    left off until fetch_logos.py has actually written it.
    """
    return f"{LOGO_BASE}/{LOGO_FILE}" if os.path.exists(f"logos/{LOGO_FILE}") else None


def collect(session, previous_path: str) -> list[dict]:
    """Every Al Jazeera programme worth publishing right now."""
    fresh: list[dict] = []
    try:
        fresh = parse(fetch(session, URL).text, utc_now().astimezone(MECCA))
    except Exception as exc:
        warn(f"Al Jazeera fetch failed: {exc}")

    carried = carry_forward(previous_path)
    if carried:
        log(f"  Al Jazeera carried forward: {len(carried)} already published")
    if not fresh and carried:
        warn("Al Jazeera published nothing readable — the channel is running "
             "on what was already in the guide")

    merged: dict[tuple, dict] = {}
    for event in carried + fresh:
        merged[(event["start"], event["stop"])] = event

    now = utc_now()
    return [e for e in merged.values()
            if now - KEEP_BEHIND <= e["stop"] and e["start"] <= now + KEEP_AHEAD]


def emit(root: ET.Element, events: list[dict]) -> int:
    """Declare the channel and write its programmes into an existing <tv>."""
    if not events:
        warn("Al Jazeera: nothing to publish, the channel is left out of this run")
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
                      event["title"], event.get("desc", ""), category="أخبار")
        total += 1

    days = sorted({e["start"].astimezone(MECCA).strftime("%Y-%m-%d") for e in events})
    log(f"Al Jazeera: {total} programmes over {len(days)} days "
        f"({days[0]} .. {days[-1]}), no Live badge — the source marks none")
    return total
