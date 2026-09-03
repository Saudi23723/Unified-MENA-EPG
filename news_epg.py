#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The third channel: a rolling bulletin, drawn as boards and published.

"breaking news مع شرح بسيط مثل جريدة يومي و ساعة بساعة و محدثة تلقائيا"
— Jordan, the Arab world, America, Britain and Turkey, strong sources,
Arabic and English mixed, not many pages.

It is built like the two boards beside it and for the same reason: a
player ignores a programme's <icon>, so the only way a picture reaches
the television is as video. The rows are also published as text in the
guide, where a reader can scroll them.

FEW PAGES, ASKED FOR OUTRIGHT. Six stories to a page and three pages at
most — eighteen headlines. That is not a limit on what is read; it is a
limit on what is SHOWN, because a board is looked at from across a room
and a lap that takes five minutes is a lap nobody waits out.

AND EVERY REGION IS ON THE FIRST PAGE. Sorting eighteen headlines by
their clock alone puts whichever newsroom posted most recently at the
top and can leave Jordan off the board entirely — which is the section
that matters most here. So each region contributes its newest stories in
turn, and only then does the clock order what is left.
"""
from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import news_board
import news_reader
from epg_lib import add_programme, log, new_session, norm, write_xml_atomic
from match_board import forget_boards_past

UTC = timezone.utc
VIEWER = ZoneInfo("America/Los_Angeles")
VIEWER_NAME = "بتوقيتك"

CHANNEL_ID = "TodayNews"
CHANNEL_AR = "أخبار اليوم"
CHANNEL_EN = "Today's News"
OUTPUT = "news_epg.xml"
BOARD_DIR = "boards"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/today_news.png")
RAW_BOARD = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
             "main/boards/today_news_{n}.png")

ON_PAGE = 6
MAX_PAGES = 3

# How long each programme in the guide runs. An hour, because that is
# what "ساعة بساعة" means and because a player showing "now" wants a
# programme that ends.
HOUR = timedelta(hours=1)

# How far the guide reaches. Short on purpose: every one of these
# programmes carries the bulletin as it stood when the build ran, and a
# guide that promised tomorrow's news would be promising something it
# cannot know. Six hours is enough that the channel is never blank
# between builds and short enough that nothing here is a forecast.
HOURS_AHEAD = 6


def in_the_readers_order(stories: list[dict]) -> list[dict]:
    """Newest first, but never all of one region before another is seen."""
    by_region: dict[str, list[dict]] = {}
    for story in sorted(stories, key=lambda one: one["start"], reverse=True):
        by_region.setdefault(story["region"], []).append(story)

    out: list[dict] = []
    round_number = 0
    while len(out) < ON_PAGE * MAX_PAGES:
        took = False
        for region in news_reader.REGIONS:
            mine = by_region.get(region) or []
            if round_number < len(mine):
                out.append(mine[round_number])
                took = True
        if not took:
            break
        round_number += 1

    # The ROUND-ROBIN ORDER is returned, not a clock order, and that
    # distinction is the whole point of this function. Sorting the
    # eighteen by time here and chunking afterwards puts the six newest
    # on page one — which is exactly what it was written to prevent, and
    # what the gate caught it doing.
    return out


def pages_of(stories: list[dict]) -> list[list[dict]]:
    """Pages that each carry the whole world, read newest-first inside.

    The chunking follows the round-robin, so page one takes one story
    from every region before any region gets a second. Only THEN does
    the clock order what is on a page, so it still reads newest-first
    without a busy newsroom being able to fill it.
    """
    chosen = in_the_readers_order(stories)[:ON_PAGE * MAX_PAGES]
    pages = [chosen[at:at + ON_PAGE]
             for at in range(0, len(chosen), ON_PAGE)] or [[]]
    return [sorted(page, key=lambda one: one["start"], reverse=True)
            for page in pages]


def named(story: dict) -> dict:
    """The story with its region written the way the board says it."""
    return dict(story,
                region_name=news_reader.REGION_AR.get(story["region"], ""))


def draw_pages(pages: list[list[dict]], now: datetime) -> int:
    os.makedirs(BOARD_DIR, exist_ok=True)
    for number, page in enumerate(pages):
        board = news_board.draw_board(
            [named(one) for one in page], now, VIEWER,
            title=CHANNEL_AR,
            subtitle=f"نشرة مستمرة · الأردن والعالم · {VIEWER_NAME}",
            page=number + 1, pages=len(pages))
        board.convert("RGB").save(
            os.path.join(BOARD_DIR, f"today_news_{number}.png"))
    forget_boards_past("today_news_", len(pages), BOARD_DIR)
    return len(pages)


def a_line(story: dict, viewer) -> str:
    when = story["start"].astimezone(viewer).strftime("%H:%M")
    head = f"{when}  {norm(story['title'])}"
    where = f"        {news_reader.REGION_AR.get(story['region'], '')}"
    if story.get("outlet"):
        where += f" · {story['outlet']}"
    said = norm(story.get("summary") or "")
    return head + "\n" + (f"        {said}\n" if said else "") + where


def a_description(pages: list[list[dict]], now: datetime) -> str:
    shown = now.astimezone(VIEWER)
    lines = [f"{CHANNEL_AR} · آخر تحديث {shown:%H:%M} — {VIEWER_NAME}", ""]
    for page in pages:
        for story in page:
            lines.append(a_line(story, VIEWER))
    if len(lines) == 2:
        lines.append("لا توجد أخبار الآن")
    return "\n".join(lines)


def a_title(pages: list[list[dict]]) -> str:
    top = pages[0][0] if pages and pages[0] else None
    if not top:
        return f"{CHANNEL_AR} — لا جديد"
    return f"{CHANNEL_AR} · {norm(top['title'])[:70]}"


def build() -> int:
    now = datetime.now(UTC)
    session = new_session()

    found = news_reader.stories(session, now)
    pages = pages_of(found)
    drawn = draw_pages(pages, now)
    log(f"  {len(found)} story(ies) read, "
        f"{sum(len(page) for page in pages)} shown on {drawn} board(s)")

    tv = ET.Element("tv", {"generator-info-name": "Today's News"})
    channel = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(channel, "icon", {"src": LOGO})
    ET.SubElement(channel, "display-name", {"lang": "ar"}).text = CHANNEL_AR
    ET.SubElement(channel, "display-name", {"lang": "en"}).text = CHANNEL_EN

    # ON THE HOUR, from the hour this build lands in. A programme that
    # started at a ragged minute makes a player show "now" against
    # something that began four minutes ago, and a bulletin channel is
    # read on the hour.
    opens = now.replace(minute=0, second=0, microsecond=0)
    title, description = a_title(pages), a_description(pages, now)

    for step in range(HOURS_AHEAD):
        start = opens + step * HOUR
        add_programme(
            tv, CHANNEL_ID, start, start + HOUR,
            title=title if step == 0 else f"{CHANNEL_AR} — نشرة مستمرة",
            desc=description,
            icon=RAW_BOARD.format(n=0))

    ok = write_xml_atomic(tv, OUTPUT, generator_name="Today's News",
                          guard_regression=False, min_programmes=1)
    log(f"{CHANNEL_AR}: {HOURS_AHEAD} programme(s), {drawn} board(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
