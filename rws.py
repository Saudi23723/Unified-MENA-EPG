#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RWS — Rajadamnern World Series, the Saturday-night Muay Thai card from
Rajadamnern Stadium in Bangkok, asked for by name on channel 2.

RWS IS A WEEKLY SHOW, NOT A CALENDAR OF CARDS. Every Saturday, 19:10 to
about 22:00 Bangkok time, at the stadium, live on DAZN — the promotion's
ticketing pages print exactly that for every Saturday of the month
(muaytix.com/rws/schedule, luimuaythai.com, checked 2 October 2026:
"every Saturday ... 3rd, 10th, 17th, 24th and 31st ... starting at 7:10
PM"). No page lists the bouts ahead in a form a runner can read, so the
row is the night itself: each Saturday inside the window, on Bangkok's
clock, which keeps no summer time and so never drifts.

A Saturday the stadium is dark is a date to add to SKIPPED below.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from epg_lib import log

BANGKOK = ZoneInfo("Asia/Bangkok")
STARTS = (19, 10)
TITLE = "RWS: Rajadamnern World Series"
CHANNELS = ["DAZN"]
# Saturdays announced as dark, as "YYYY-MM-DD".
SKIPPED: set[str] = set()


def events(session=None, floor=None, ceiling=None) -> list[dict]:
    now = datetime.now(timezone.utc)
    floor = floor or now - timedelta(days=1)
    ceiling = ceiling or now + timedelta(days=8)
    day = floor.astimezone(BANGKOK).date() - timedelta(days=1)
    out = []
    while day <= ceiling.astimezone(BANGKOK).date():
        if day.weekday() == 5 and day.isoformat() not in SKIPPED:
            start = datetime(day.year, day.month, day.day, *STARTS,
                             tzinfo=BANGKOK).astimezone(timezone.utc)
            if floor <= start < ceiling:
                out.append({"start": start, "title": TITLE,
                            "sport": "Muay Thai", "competition": "RWS",
                            "channels": list(CHANNELS), "source": "rws"})
                log(f"  rws: {start:%d.%m %H:%M} UTC on DAZN")
        day += timedelta(days=1)
    return out
