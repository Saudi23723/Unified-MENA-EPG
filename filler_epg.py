#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filler guide — a placeholder grid for channels no source schedules.

Some channels have no reachable schedule anywhere. مرايا and الكبير أوي are
single-series channels that exist only inside Shahid in-region; Shahid's
API refuses every listing path from outside it, and no third-party guide
carries them. The evidence is in docs/CHANNELS_NOT_AVAILABLE.md.

Without any EPG a player shows those channels as a blank strip, and some
players will not even let you set a reminder or start a recording on a
channel with no programme under the cursor. This guide gives them a grid
to sit on.

**Nothing here claims to be a real programme.** Every block is titled
"Program 24/7" precisely so that it cannot be mistaken for a schedule —
it says the channel runs around the clock and nothing more. The day is cut
into eight three-hour blocks, on the hour, so the grid lines up with what
a viewer expects and never leaves a gap.

If a real source for one of these channels ever appears, delete its row
from CHANNELS below and give it a generator of its own — a real schedule
always wins over a placeholder.

The blocks are laid out against Mecca time (+03:00, no daylight saving),
which is the clock the rest of the Arabic guides in this repository use.
That choice only decides where the boundaries fall; it says nothing about
the content, because there is no content to be wrong about.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import xml.etree.ElementTree as ET

from epg_lib import add_programme, log, run_main, utc_now, write_xml_atomic

OUTPUT = "filler_epg.xml"

# Mecca keeps +03:00 all year, so the block boundaries never shift.
MECCA = timezone(timedelta(hours=3))

BLOCK_HOURS = 3
DAYS_AHEAD = 7
# One day back so a player scrolling left does not fall off the grid.
DAYS_BACK = 1

TITLE = "Program 24/7"

LOGO_BASE = ("https://raw.githubusercontent.com/Saudi23723/"
             "Unified-MENA-EPG/main/logos")

# (xmltv id, English name, Arabic name, logo file stem)
# Add a row here to give another channel the same placeholder grid.
CHANNELS = [
    ("Maraya.shahid", "Maraya", "مرايا", "maraya"),
    ("AlKabeerAwi.shahid", "Al Kabeer Awi", "الكبير أوي", "alkabeerawi"),
    ("Aflam.shahid", "Aflam", "أفلام", "aflam"),
]


def blocks(now: datetime) -> list[tuple[datetime, datetime]]:
    """Every three-hour block from DAYS_BACK ago to DAYS_AHEAD from now.

    The first block starts at midnight Mecca so the grid always breaks on
    00:00, 03:00, 06:00 … whatever hour the generator happens to run at.
    """
    local = now.astimezone(MECCA)
    first = local.replace(hour=0, minute=0, second=0, microsecond=0) \
        - timedelta(days=DAYS_BACK)
    last = first + timedelta(days=DAYS_BACK + DAYS_AHEAD)

    out: list[tuple[datetime, datetime]] = []
    start = first
    while start < last:
        stop = start + timedelta(hours=BLOCK_HOURS)
        out.append((start, stop))
        start = stop
    return out


def build() -> int:
    log("FILLER EPG | placeholder grid for channels with no published schedule")
    now = utc_now()
    grid = blocks(now)

    root = ET.Element(
        "tv", {"generator-info-name": "Unified MENA EPG — Filler"})

    for xmltv_id, en_name, ar_name, key in CHANNELS:
        ch = ET.SubElement(root, "channel", id=xmltv_id)
        ET.SubElement(ch, "display-name", lang="ar").text = ar_name
        ET.SubElement(ch, "display-name", lang="en").text = en_name
        ET.SubElement(ch, "icon", src=f"{LOGO_BASE}/{key}.png")

    total = 0
    for xmltv_id, _en, ar_name, _key in CHANNELS:
        for start, stop in grid:
            add_programme(
                root, xmltv_id, start, stop, TITLE,
                desc=(f"{ar_name} — بث مستمر ٢٤/٧.\n"
                      "هذه ليست مواعيد برامج: القناة لا تنشر جدولاً، "
                      "وهذا الحقل موجود ليملأ الشبكة فقط."),
            )
            total += 1

    log(f"Filler: {len(CHANNELS)} channels x {len(grid)} blocks "
        f"of {BLOCK_HOURS}h = {total} programmes, "
        f"{grid[0][0]:%Y-%m-%d %H:%M} to {grid[-1][1]:%Y-%m-%d %H:%M} Mecca")

    # The grid is computed, never fetched, so it cannot come back short for
    # a reason worth protecting against — but a floor still catches a bad
    # edit to BLOCK_HOURS or DAYS_AHEAD before it reaches the guide.
    write_xml_atomic(
        root, OUTPUT, guard_regression=False,
        min_programmes=len(CHANNELS) * (24 // BLOCK_HOURS),
        generator_name="Unified MENA EPG — Filler")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
