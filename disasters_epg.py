#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The disasters channel: storms, earthquakes, floods, volcanoes, fires.

"سوي قناة الكوارث في العالم … عواصف زلازل فيضانات و ما شابه … بس تكون
مخصصه لهيك اشياء مش اخبار و رياضة"

Built like the news channel beside it — a rolling bulletin drawn as
boards and published, with the rows also in the guide where a reader can
scroll them — and deliberately NOT fed by it. The news channel reads
newsrooms; this reads the monitors (disaster_reader.py), so nothing
reaches it that is not a disaster, and a disaster reaches it whether or
not anybody wrote a story about it.

THE WORST IS ON THE FIRST PAGE. A bulletin ordered by the clock alone
leads with whatever the seismometers logged last, which is almost always
an M5 in the middle of an ocean. So the page is ordered by how bad an
event is — the monitors' own red/orange/green, and for a quake its
magnitude and tsunami flag — and by how recent only within that. The
red and orange rows are lit, the way the news board lights a story that
is inside the hour.
"""
from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PIL import ImageDraw

import board_links
import disaster_reader
import dubai_time
import news_board
from epg_lib import add_programme, log, new_session, norm, warn, write_xml_atomic
from match_board import WHITE, forget_boards_past

UTC = timezone.utc
VIEWER = ZoneInfo("America/Los_Angeles")
VIEWER_NAME = "بتوقيتك"

CHANNEL_ID = "WorldDisasters"
CHANNEL_AR = "كوارث العالم"
CHANNEL_EN = "World Disasters"
OUTPUT = "disasters_epg.xml"
BOARD_DIR = "boards"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/world_disasters.png")
BOARD_PREFIX = "disasters_"
RAW_BOARD = board_links.link(BOARD_PREFIX + "{n}.png")

# The second clock: the same bulletin with every time in the Gulf's.
# Its own board stem, because the encoder owns a reel by prefix.
DUBAI_OUTPUT = "dubai_disasters_epg.xml"
DUBAI_CHANNEL_ID = "WorldDisastersDubai"
DUBAI_BOARD_PREFIX = "dubai_disasters_"
DUBAI_RAW_BOARD = board_links.link(DUBAI_BOARD_PREFIX + "{n}.png")

ON_PAGE = 6
MAX_PAGES = 5

HOUR = timedelta(hours=1)
HOURS_AHEAD = 6

# The channel's colour: the red of an alert, not the news board's amber,
# so the two bulletins side by side are two channels.
ACCENT = (255, 92, 72, 255)
LIT_GROUND = (52, 22, 20, 255)
# Orange and red are lit. Green is shown, and not pointed at.
LIT_RANK = 2

WORDS = ("حدث", "حدثان", "أحداث", "حدثًا")
EMPTY = "لا كوارث كبرى"


def draw_mark(pen: ImageDraw.ImageDraw, x: int, y: int, size: int,
              accent=ACCENT) -> None:
    """The channel's mark on the board: a seismograph trace in a tile."""
    ink = tuple(min(255, int(c * 0.28)) for c in accent[:3]) + (255,)
    pen.rounded_rectangle([x, y, x + size, y + size], radius=size // 5,
                          fill=ink, outline=accent, width=2)
    mid = y + size // 2
    left, right = x + size // 6, x + size - size // 6
    step = (right - left) / 8
    heights = (0, 0.1, -0.25, 0.42, -0.38, 0.2, -0.1, 0.05, 0)
    points = [(left + step * i, mid - h * size) for i, h in enumerate(heights)]
    pen.line(points, fill=WHITE, width=max(3, size // 18), joint="curve")
    pen.line([(points[3][0], mid - 0.42 * size), (points[4][0],
              mid + 0.38 * size)], fill=accent, width=max(3, size // 18))


def a_row(event: dict) -> dict:
    """An event as the board's row: kind on the left, headline, the numbers."""
    return {
        "start": event["start"],
        "title": disaster_reader.headline(event),
        "summary": disaster_reader.summary(event, VIEWER, place=False),
        "region_name": disaster_reader.KIND_AR[event["kind"]],
        "outlet": event.get("outlet") or "",
        "lit": event["rank"] >= LIT_RANK,
    }


def pages_of(events: list[dict]) -> list[list[dict]]:
    chosen = events[:ON_PAGE * MAX_PAGES]
    return [chosen[at:at + ON_PAGE]
            for at in range(0, len(chosen), ON_PAGE)] or [[]]


def draw_pages(pages: list[list[dict]], now: datetime) -> int:
    os.makedirs(BOARD_DIR, exist_ok=True)
    for number, page in enumerate(pages):
        board = news_board.draw_board(
            [a_row(one) for one in page], now, VIEWER,
            title=CHANNEL_AR,
            subtitle=f"زلازل · أعاصير · فيضانات · براكين · حرائق · {VIEWER_NAME}",
            page=number + 1, pages=len(pages),
            accent=ACCENT, mark=draw_mark, lit_ground=LIT_GROUND,
            words=WORDS, empty=EMPTY)
        board.convert("RGB").save(
            os.path.join(BOARD_DIR, f"{BOARD_PREFIX}{number}.png"))
    forget_boards_past(BOARD_PREFIX, len(pages), BOARD_DIR)
    return len(pages)


def a_line(event: dict) -> str:
    alert = disaster_reader.ALERT_AR.get(event.get("alert") or "", "")
    head = disaster_reader.headline(event)
    said = disaster_reader.summary(event, VIEWER)
    where = f"        {event.get('outlet') or ''}"
    if alert and event["kind"] == "EQ":
        where += f" · تنبيه {alert}"
    return head + "\n" + (f"        {said}\n" if said else "") + where


def a_description(pages: list[list[dict]], now: datetime) -> str:
    shown = now.astimezone(VIEWER)
    lines = [f"{CHANNEL_AR} · آخر تحديث {shown:%H:%M} — {VIEWER_NAME}", ""]
    for page in pages:
        for event in page:
            lines.append(a_line(event))
    if len(lines) == 2:
        lines.append(f"{EMPTY} الآن")
    return "\n".join(lines)


def a_title(pages: list[list[dict]]) -> str:
    top = pages[0][0] if pages and pages[0] else None
    if not top:
        return f"{CHANNEL_AR} — {EMPTY}"
    return f"{CHANNEL_AR} · {norm(disaster_reader.headline(top))[:70]}"


def publish_all(pages: list[list[dict]], now: datetime) -> int:
    drawn = draw_pages(pages, now)

    tv = ET.Element("tv", {"generator-info-name": CHANNEL_EN})
    channel = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(channel, "icon", {"src": LOGO})
    ET.SubElement(channel, "display-name", {"lang": "ar"}).text = CHANNEL_AR
    ET.SubElement(channel, "display-name", {"lang": "en"}).text = CHANNEL_EN

    opens = now.replace(minute=0, second=0, microsecond=0)
    title, description = a_title(pages), a_description(pages, now)
    for step in range(HOURS_AHEAD):
        start = opens + step * HOUR
        add_programme(
            tv, CHANNEL_ID, start, start + HOUR,
            title=title if step == 0 else f"{CHANNEL_AR} — رصد مستمر",
            desc=description,
            icon=RAW_BOARD.format(n=0))

    ok = write_xml_atomic(tv, OUTPUT, generator_name=CHANNEL_EN,
                          guard_regression=False, min_programmes=1)
    log(f"{CHANNEL_AR}: {HOURS_AHEAD} programme(s), {drawn} board(s)")
    return 0 if ok else 1


def build() -> int:
    now = datetime.now(UTC)
    found = disaster_reader.events(new_session(), now)
    pages = pages_of(found)
    log(f"  {len(found)} event(s) read, "
        f"{sum(len(page) for page in pages)} to show")

    ok = publish_all(pages, now) == 0

    with dubai_time.the_other_clock(
            globals(),
            VIEWER=dubai_time.DUBAI, VIEWER_NAME=dubai_time.DUBAI_NAME,
            OUTPUT=DUBAI_OUTPUT, CHANNEL_ID=DUBAI_CHANNEL_ID,
            BOARD_PREFIX=DUBAI_BOARD_PREFIX, RAW_BOARD=DUBAI_RAW_BOARD):
        try:
            publish_all(pages, now)
        except Exception as exc:                              # noqa: BLE001
            warn(f"the UAE-clock disasters bulletin could not be written "
                 f"({exc}) — the published one is unchanged")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
