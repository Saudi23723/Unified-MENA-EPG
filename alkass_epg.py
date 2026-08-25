#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alkass (الكأس) — Qatar's sports channels, from Alkass's own TV guide.

Source: https://www.alkass.net/tvguide — the broadcaster's own page.

Why this and not beIN, which this guide read before: audited channel by
channel on the same day, the two disagree almost completely. Of the slots
that even start at the same minute, beIN's title matched Alkass's on 0 of
13 for Alkass 1, 0 of 13 for Alkass 4, 1 of 15 for Alkass 2, 1 of 17 for
Alkass 3 — beIN says "Derby Tunis" where Alkass says the Qatar Stars
League match it is actually airing. beIN also repeats Alkass 1's whole
schedule on Alkass 4 (71 of 87 slots identical) and Alkass 5's on
Alkass 7 (76 of 78). Alkass is the broadcaster; its own guide is what
goes on air.

The page carries one day, in English only, so that is what this guide
publishes: no Arabic titles, no three days ahead. That is the cost of
reading the source that is actually right.

Parsing: the page renders the same guide twice. The collapsible cg1..cg8
list near the top is broken — it repeats whole channels (1=4=8, 2=5=7,
3=6) and duplicates rows inside a table — so it is ignored. The grid
under <div class="tg-content"> is the real one: a logo column
(one.png … eight.png, then online.png for the streaming service, which
publishes no schedule) beside one <table ... margin-right:10px> per
channel, in the same order. Each programme is a
<div class='programs' id='N'> holding its title and an explicit
"HH:MM - HH:MM" range, in Doha wall-clock, in chronological order.

The page's own "now" marker is rendered server-side at the current Doha
time, so the page is live rather than cached.

Alkass 9, 10, 11 and the two SHOOF channels are not on this page and are
not in this guide.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone

import xml.etree.ElementTree as ET

from epg_lib import (
    add_programme, fetch, log, new_session, resolve_overlaps, run_main,
    utc_now, warn, write_xml_atomic,
)

OUTPUT = "alkass_epg.xml"
DOHA = timezone(timedelta(hours=3))

BASE = "https://www.alkass.net/tvguide"
# The page's own day switcher: اليوم is the bare URL, غداً adds day=next.
# Alkass often serves the same page for both; a day that repeats the one
# before it is dropped rather than published twice.
DAYS = [("", 0), ("?day=next", 1)]

LOGO_BASE = "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/logos"

CHANNELS = [
    (1, "AlkassOne.qa", "Alkass 1", "الكأس 1", "alkass1"),
    (2, "AlkassTwo.qa", "Alkass 2", "الكأس 2", "alkass2"),
    (3, "AlkassThree.qa", "Alkass 3", "الكأس 3", "alkass3"),
    (4, "AlkassFour.qa", "Alkass 4", "الكأس 4", "alkass4"),
    (5, "AlkassFive.qa", "Alkass 5", "الكأس 5", "alkass5"),
    (6, "AlkassSix.qa", "Alkass 6", "الكأس 6", "alkass6"),
    (7, "AlkassSeven.qa", "Alkass 7", "الكأس 7", "alkass7"),
    (8, "AlkassEight.qa", "Alkass 8", "الكأس 8", "alkass8"),
]

GRID_START = 'class="tg-content"'
# The logo column, which names the channels the tables belong to. Reading
# it instead of assuming "first table is channel 1" is what stops a single
# missing row from renaming every channel below it.
COLUMN_RE = re.compile(
    r"assets/images/(one|two|three|four|five|six|seven|eight|online)\.png")
COLUMN_NUMBER = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                 "six": 6, "seven": 7, "eight": 8,
                 # the streaming service, which publishes no schedule
                 "online": 0}
# One table per channel. The timeline strip above them is a table too, but
# it carries no margin-right, which is what keeps it out.
CHANNEL_TABLE_RE = re.compile(
    r"<table style=\"width: ?\d+px; margin-right:10px\">(.*?)</table>", re.S)
PROGRAMME_RE = re.compile(
    r"<div class='programs[^']*' id='\d+'[^>]*>(?P<title>.*?)<br>\s*"
    r"<span[^>]*>(?P<start>\d{2}:\d{2}) - (?P<stop>\d{2}:\d{2})</span>", re.S)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(value or ""))).strip()


def parse_page(text: str) -> dict[int, list[tuple[str, str, str]]]:
    """{alkass number: [(start "HH:MM", stop "HH:MM", title)]}, in order."""
    cut = (text or "").find(GRID_START)
    if cut < 0:
        return {}
    grid = text[cut:]

    column = COLUMN_RE.findall(grid)
    tables = CHANNEL_TABLE_RE.findall(grid)
    if len(column) != len(tables):
        # The two run in parallel, one table per logo. If they ever stop
        # matching, every channel below the gap would be renamed, so read
        # nothing rather than publish someone else's schedule.
        warn(f"alkass.net: {len(column)} channel logos but {len(tables)} "
             f"schedule tables — layout changed, not parsing")
        return {}

    out: dict[int, list[tuple[str, str, str]]] = {}
    for name, body in zip(column, tables):
        number = COLUMN_NUMBER.get(name, 0)
        if not number:
            continue
        rows = [(m.group("start"), m.group("stop"), clean(m.group("title")))
                for m in PROGRAMME_RE.finditer(body)]
        if rows:
            out[number] = rows
    return out


def to_datetimes(rows: list[tuple[str, str, str]], day: datetime) -> list[dict]:
    """Turn one channel's "HH:MM - HH:MM" rows into absolute Doha times.

    The rows run in broadcast order from midnight, so a stop that is not
    after its start has run past midnight, and so has a start that goes
    backwards against the row before it.
    """
    events: list[dict] = []
    offset = 0
    previous: datetime | None = None

    for start_hm, stop_hm, title in rows:
        if not title:
            continue
        try:
            start = datetime.combine(
                day.date(), datetime.strptime(start_hm, "%H:%M").time(), DOHA)
            stop = datetime.combine(
                day.date(), datetime.strptime(stop_hm, "%H:%M").time(), DOHA)
        except ValueError:
            continue

        start += timedelta(days=offset)
        if previous is not None and start < previous:
            offset += 1
            start += timedelta(days=1)
        stop += timedelta(days=offset)
        if stop <= start:
            stop += timedelta(days=1)

        previous = start
        events.append({"start": start, "stop": stop, "title": title})
    return events


def fetch_day(session, suffix: str) -> dict[int, list[tuple[str, str, str]]]:
    """One page. Never raises: a page that fails costs that day only."""
    try:
        page = fetch(session, BASE + suffix).text
    except Exception as exc:
        warn(f"alkass.net{suffix or ' (today)'} failed: {exc}")
        return {}
    return parse_page(page)


def build() -> int:
    log("ALKASS (الكأس) EPG | alkass.net official guide")
    session = new_session()
    today = utc_now().astimezone(DOHA)

    per_channel: dict[int, list[dict]] = {}
    seen: list[dict[int, list[tuple[str, str, str]]]] = []

    for suffix, day_offset in DAYS:
        parsed = fetch_day(session, suffix)
        label = f"day+{day_offset}"
        if not parsed:
            log(f"  {label}: nothing published")
            continue
        if parsed in seen:
            # Alkass serves the same page for اليوم and غداً when tomorrow
            # is not ready; publishing it twice would invent a schedule.
            log(f"  {label}: same page as the day before it — skipped")
            continue
        seen.append(parsed)

        day = today + timedelta(days=day_offset)
        log(f"  {label} ({day:%Y-%m-%d}): "
            f"{sum(len(v) for v in parsed.values())} rows across "
            f"{len(parsed)} channels")
        for number, rows in parsed.items():
            per_channel.setdefault(number, []).extend(to_datetimes(rows, day))

    if not per_channel:
        # write_xml_atomic keeps the previous file rather than publishing an
        # empty one, so a bad fetch costs nothing.
        write_xml_atomic(ET.Element("tv"), OUTPUT,
                         generator_name="Unified MENA EPG — Alkass")
        return 0

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — Alkass"})
    with_data = [c for c in CHANNELS if per_channel.get(c[0])]
    missing = [c[3] for c in CHANNELS if not per_channel.get(c[0])]
    if missing:
        log(f"No schedule published for: {', '.join(missing)}")

    for _number, xid, en_name, ar_name, key in with_data:
        ch = ET.SubElement(root, "channel", id=xid)
        # English first: a player shows the first display-name it can use.
        ET.SubElement(ch, "display-name", lang="en").text = en_name
        ET.SubElement(ch, "display-name", lang="ar").text = ar_name
        ET.SubElement(ch, "icon", src=f"{LOGO_BASE}/{key}.png")

    total = 0
    for number, xid, _en_name, _ar_name, _key in with_data:
        for ev in resolve_overlaps(per_channel[number]):
            add_programme(root, xid, ev["start"], ev["stop"], ev["title"],
                          category="الرياضة")
            total += 1

    log(f"Alkass: {len(with_data)}/{len(CHANNELS)} channels, {total} programmes")
    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — Alkass")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
