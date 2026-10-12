#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""elcinema.com's Jordanian channel pages, on a clock this file can trust.

elcinema prints its guide in the VISITOR's clock, and a runner's clock is
neither stated nor the same from one runner to the next (measured on 3
October 2026: the same page read UTC-3 on one runner and UTC+8 on the
next). Lining the page up by its run of durations, or by names already
published, followed that drift: TV Jordan's guide went out with "صلاة
الجمعة" on a Saturday and Arabic names on the wrong shows.

The clock is read instead off the one thing on the page that states its
own hour: TV Jordan's news bulletins, named for it — نشرة أخبار السابعة
at 07:00 Amman, الثالثة at 15:00 — on the same visit, so the same clock
as any other channel's page read with it. Every bulletin must agree or
the clock is refused, and a reader with no clock publishes nothing new.

The page lists from today in that clock.
"""

from __future__ import annotations

import html as htmllib
import re
from datetime import datetime, timedelta, timezone

from epg_lib import fetch, log, warn

PAGE = "https://elcinema.com/ar/tvguide/{id}/"
JORDAN_TV = 1314
AMMAN = timezone(timedelta(hours=3))      # Jordan's clock all year since 2022
UNNAMED = "برنامج"
# The bulletins that name their hour, and that hour in Amman.
NEWS_HOURS = {"السابعة": 7, "الثالثة": 15, "العاشرة": 22, "الخامسة": 17,
              "الثامنة": 20, "التاسعة": 21}
DAY = 24 * 60


def clean(title: str) -> str:
    title = re.sub(r"\s+", " ", htmllib.unescape(title)).strip()
    title = title.replace("ىالمتحركة", "المتحركة")      # elcinema's typo
    title = re.sub(r"^برنامج\s+", "", title)
    return "" if title == UNNAMED else title


def read_page(session, channel: int) -> tuple[int, list[tuple[str, int, int]]]:
    """(first row's printed minute of day, [(name, minutes from first, length)])."""
    url = PAGE.format(id=channel)
    page = fetch(session, url, timeout=60).text
    rows, offset, last, first = [], 0, None, None
    for box in page.split('class="boxed-category-')[1:]:
        when = re.search(r"(\d{1,2}):(\d{2})\s*(صباح|مساء)", box)
        if not when:
            continue
        length = re.search(r"\[(\d+)\s*دقيقة\]", box)
        name = re.search(r'<a href="/work/\d+/">([^<]+)</a>', box) or \
            re.search(r'<ul class="unstyled no-margin">\s*<li>([^<]+)</li>', box)
        minute = (int(when.group(1)) % 12 + (12 if when.group(3) == "مساء" else 0)) \
            * 60 + int(when.group(2))
        if last is None:
            first = minute
        else:
            offset += (minute - last) % DAY
        last = minute
        rows.append((clean(name.group(1)) if name else "", offset,
                     int(length.group(1)) if length else 0))
    if first is None:
        raise ValueError(f"no rows on {url}")
    return first, rows


def bulletin_clock(first: int, rows) -> timedelta | None:
    """The page's clock (offset from UTC) from TV Jordan's bulletins."""
    shifts = set()
    for name, offset, _length in rows:
        if "اخبار" not in name.replace("أ", "ا"):
            continue
        for word, hour in NEWS_HOURS.items():
            if word in name:
                printed = (first + offset) % DAY
                shifts.add((printed - (hour * 60 - 180)) % DAY)
    if len(shifts) != 1:
        warn(f"elcinema: TV Jordan's bulletins "
             f"{'disagree' if shifts else 'are missing'} on the page's clock")
        return None
    shift = shifts.pop()
    if shift > DAY // 2:
        shift -= DAY
    log(f"  elcinema prints UTC{shift / 60:+.1f}h this visit "
        f"(set by TV Jordan's bulletins)")
    return timedelta(minutes=shift)


def timeline(first: int, rows, clock: timedelta,
             now: datetime | None = None) -> list[dict]:
    """The page's rows as UTC instants: [{start, stop, name}]."""
    now = now or datetime.now(timezone.utc)
    today = (now + clock).date()
    base = datetime(today.year, today.month, today.day, tzinfo=timezone.utc) \
        + timedelta(minutes=first) - clock
    out = []
    for name, offset, length in rows:
        start = base + timedelta(minutes=offset)
        out.append({"start": start,
                    "stop": start + timedelta(minutes=length or 30),
                    "name": name})
    for a, b in zip(out, out[1:]):
        if b["start"] < a["stop"]:
            a["stop"] = b["start"]
    return [r for r in out if r["stop"] > r["start"]]


def channel(session, channel_id: int) -> list[dict]:
    """A Jordanian channel's elcinema rows on a trusted clock, or []."""
    first, rows = read_page(session, JORDAN_TV)
    clock = bulletin_clock(first, rows)
    if clock is None:
        return []
    if channel_id != JORDAN_TV:
        first, rows = read_page(session, channel_id)
    return timeline(first, rows, clock)
