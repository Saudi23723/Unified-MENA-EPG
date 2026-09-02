#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Does ANY source this guide reads publish a Jordanian match?

Temporary. The reader has asked about the Jordanian league repeatedly and
has been told it is in none of the sources. That answer came from looking
at what reached the BOARD, which cannot tell two very different things
apart:

  - no source publishes those fixtures, or
  - a source publishes them under a competition name this guide does not
    recognise, so they are dropped before anyone sees them.

"jordan" is already in WANTED_PARTS and "الدوري الأردني" in
WANTED_ARABIC, so the second can only happen if the name differs. This
asks the question the right way round: every fixture each source offers
BEFORE any filtering, matched on the competition OR on the clubs. The
clubs are the part that cannot be renamed away.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime

import requests

import live_football_on_tv
import live_soccer_tv
import today_matches_epg as today
import yallakora
from epg_lib import fetch

# A competition can be called anything; Al-Faisaly is Al-Faisaly in every
# listing that carries it.
CLUBS = re.compile(
    r"faisaly|wehdat|wihdat|ramtha|jazeera|sareeh|al[- ]?salt|aqaba"
    r"|shabab al[- ]?ordon|ahli amman|that ras|moghayer|hussein irbid"
    r"|الفيصلي|الوحدات|الرمثا|الجزيرة|صريح|السلط|العقبة|شباب الأردن"
    r"|أهلي عمان|ذات راس|مغير|الحسين إربد", re.I)
JORDAN = re.compile(r"jordan|ordon|الأردن|الاردن|أردني|اردني", re.I)


def jordanian(row: dict) -> bool:
    text = f"{row.get('competition', '')} {row.get('title', '')}"
    return bool(JORDAN.search(text) or CLUBS.search(text))


def show(name: str, rows: list[dict]) -> int:
    hits = [row for row in rows if jordanian(row)]
    print(f"\n=== {name}: {len(rows)} fixture(s) offered, "
          f"{len(hits)} look Jordanian")
    for row in hits[:25]:
        print(f"    {row.get('start')}  {row.get('title')!r}"
              f"   │ {row.get('competition', '')!r}"
              f"   │ {row.get('channels', row.get('channel', ''))}")
    return len(hits)


def main() -> int:
    now = datetime.now(today.UTC)
    floor, ceiling = today.window_floor(now), today.window_ceiling(now)
    session = requests.Session()
    session.headers.update({
        "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
        "Accept-Language": "ar,en;q=0.8,tr;q=0.6",
    })

    found = 0
    try:
        html = fetch(session, today.SOURCE).text
        found += show("livefootballtv", today.collect(html, now, floor,
                                                      ceiling))
    except Exception as exc:                              # noqa: BLE001
        print(f"=== livefootballtv unavailable: {exc}")

    found += show("live-footballontv",
                  live_football_on_tv.fetch_events(session, floor, ceiling))
    found += show("yallakora",
                  yallakora.fetch_events(session, floor, ceiling))
    found += show("livesoccertv", live_soccer_tv.broadcasts(session))

    print(f"\nTOTAL Jordanian-looking fixtures across every source: {found}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
