#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filler channels — a placeholder grid for channels no source schedules.

These ride on the Jordan (Roya) guide rather than on a link of their own,
the same way الجديد and الجزيرة do, so nothing new has to be added in the
player. roya_jordan_epg.py calls collect() and emit() below after building
its own channels; a failure here costs these channels only and never
Amman's guide.

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

import os
from datetime import datetime, timedelta, timezone

import xml.etree.ElementTree as ET

from epg_lib import add_programme, log, utc_now, warn


# Mecca keeps +03:00 all year, so the block boundaries never shift.
MECCA = timezone(timedelta(hours=3))

BLOCK_HOURS = 3
DAYS_AHEAD = 7
# One day back so a player scrolling left does not fall off the grid.
DAYS_BACK = 1

TITLE = "Program 24/7"

LOGO_BASE = ("https://raw.githubusercontent.com/Saudi23723/"
             "Unified-MENA-EPG/main/logos")

# (xmltv id, logo file stem, [names])
#
# A player matches an EPG channel to a playlist channel by tvg-id when the
# playlist sets one, and by NAME when it does not. These channels are
# matched by name, so every spelling a playlist might carry is listed and
# written out as its own <display-name>: the exact name seen in the user's
# list first, then the shorter forms, the Latin transliteration and the
# provider's own "ARA: X" label.
#
# The first name is what a player shows. The rest exist only to be matched.
# One character is enough to break a match -- الاربعة and الأربعة differ by
# a hamza and are not the same string -- which is why both are here.
#
# To add a channel: a row here, a matching row in SPECS in
# make_filler_logos.py, then run that script so it gets a mark of its own.
CHANNELS = [
    ("Maraya.shahid", "maraya", [
        "مرايا ياسر العظمة", "مرايا", "Maraya", "ARA: MARAYA"]),
    ("AlKabeerAwi.shahid", "alkabeerawi", [
        "الكبير أوي", "الكبير اوي", "الكبير", "Al Kabeer Awi",
        "ARA: AL KABEER AWI"]),
    ("Aflam.shahid", "aflam", [
        "أفلام", "افلام", "Aflam", "ARA: AFLAM"]),
    ("Ayla5.shahid", "ayla5", [
        "عيلة 5 نجوم", "عيلة ٥ نجوم", "عيلة 5", "Ayla 5 Njoum", "Ayla 5",
        "ARA: AYLA 5"]),
    ("Ayla6.shahid", "ayla6", [
        "عيلة 6 نجوم", "عيلة ٦ نجوم", "عيلة 6", "Ayla 6 Njoum", "Ayla 6",
        "ARA: AYLA 6"]),
    ("FusoulArbaa1.shahid", "fusoul1", [
        "الفصول الاربعة 1", "الفصول الأربعة 1", "الفصول الاربعة ١",
        "Al Fusoul Al Arbaa 1", "ARA: الفصول الاربعة 1"]),
    ("FusoulArbaa2.shahid", "fusoul2", [
        "الفصول الاربعة 2", "الفصول الأربعة 2", "الفصول الاربعة ٢",
        "Al Fusoul Al Arbaa 2", "ARA: الفصول الاربعة 2"]),
    ("DayaaDayaa1.shahid", "dayaa1", [
        "ضيعة ضايعة 1", "ضيعة ضايعة ١", "Dayaa Dayaa 1",
        "ARA: DAYAA DAYAA 1"]),
    ("DayaaDayaa2.shahid", "dayaa2", [
        "ضيعة ضايعة 2", "ضيعة ضايعة ٢", "Dayaa Dayaa 2",
        "ARA: DAYAA DAYAA 2"]),
    ("MudeerAam1.shahid", "mudeer1", [
        "يوميات مدير عام 1", "يوميات مدير عام ١", "Yawmiyat Mudeer Aam 1",
        "ARA: YAWMIYAT MUDEER AAM 1"]),
    ("MudeerAam2.shahid", "mudeer2", [
        "يوميات مدير عام 2", "يوميات مدير عام ٢", "Yawmiyat Mudeer Aam 2",
        "ARA: YAWMIYAT MUDEER AAM 2"]),
    ("AlKhibra.shahid", "alkhibra", [
        "الخبرة", "Al Khibra", "ARA: AL KHIBRA"]),
    ("Bibasata.shahid", "bibasata", [
        "ببساطة 1", "ببساطة ١", "ببساطة", "Bibasata 1", "Bibasata",
        "ARA: BIBASATA"]),
    ("AlWaqAlWaq.shahid", "alwaq", [
        "الواق الواق", "Al Waq Al Waq", "ARA: AL WAQ AL WAQ"]),
    ("AlTawareed.shahid", "altawareed", [
        "الطواريد", "Al Tawareed", "ARA: AL TAWAREED"]),
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


def collect(session=None, previous_path: str = "") -> list[dict]:
    """The grid, computed. Signature matches the other readers so
    roya_jordan_epg.py can call every one of them the same way; neither
    argument is used, because nothing is fetched and so nothing can fail
    in a way that needs the previous file to fall back on.
    """
    grid = blocks(utc_now())
    return [{"start": start, "stop": stop} for start, stop in grid]


def emit(root: ET.Element, grid: list[dict]) -> int:
    """Declare the filler channels and write their grid into an existing <tv>."""
    if not grid:
        warn("Filler: empty grid, the placeholder channels are left out")
        return 0

    for xmltv_id, key, names in CHANNELS:
        channel = ET.SubElement(root, "channel", id=xmltv_id)
        # Every spelling gets its own display-name, so a playlist that
        # carries any of them matches. The first is what a player shows.
        for name in names:
            lang = "en" if name.isascii() else "ar"
            ET.SubElement(channel, "display-name", lang=lang).text = name
        path = os.path.join("logos", f"{key}.png")
        if os.path.exists(path):
            ET.SubElement(channel, "icon", src=f"{LOGO_BASE}/{key}.png")
        else:
            warn(f"logos/{key}.png is not in the repository yet — {names[0]} "
                 f"is published without an icon rather than pointing at a "
                 f"missing file")

    total = 0
    for xmltv_id, _key, names in CHANNELS:
        ar_name = names[0]
        for block in grid:
            add_programme(
                root, xmltv_id, block["start"], block["stop"], TITLE,
                desc=(f"{ar_name} — بث مستمر ٢٤/٧.\n"
                      "هذه ليست مواعيد برامج: القناة لا تنشر جدولاً، "
                      "وهذا الحقل موجود ليملأ الشبكة فقط."),
            )
            total += 1

    log(f"Filler: {len(CHANNELS)} channels x {len(grid)} blocks of "
        f"{BLOCK_HOURS}h = {total} programmes, "
        f"{grid[0]['start'].astimezone(MECCA):%Y-%m-%d %H:%M} to "
        f"{grid[-1]['stop'].astimezone(MECCA):%Y-%m-%d %H:%M} Mecca")
    return total
