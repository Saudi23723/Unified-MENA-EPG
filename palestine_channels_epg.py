#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Palestinian channels with no published schedule — a "24/7 Program" row a
day each, on the Roya link, asked for outright from a photo of the player.

Every official source was checked first (30 September) and none publishes
a schedule: pbc.ps (Palestine TV, Mubashir, Sport) has news and a live
player only, paltodaytv.com's programmes page is empty, alkofiya.tv lists
its shows with no times, alqudstoday.tv's schedule stopped in April 2023,
falastini.tv is clips and songs, and Hala has no schedule page. The one
listings source that names these channels (epgshare01's AE1 guide) fills
them with other channels' shows — Al Jazeera English's "Newshour" on
Palestine TV, Al Mayadeen's news on Palestine Live, and the same Quran
recitations on Falastini and Al Quds Today alike — so it is not used.

Each channel wears its own mark from its own site (logos/*.png); Mubashir
and Sport are Palestine TV's mark with their name beneath, as they appear
on screen.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from epg_lib import add_programme

TITLE = "24/7 Program"
DAYS_BACK = 1
DAYS_FORWARD = 7
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/{name}")

# (id, names the playlist uses, Arabic name, logo)
CHANNELS = (
    ("PalestineTV.ps", ("Palestine TV", "Palestine TV HD", "PS| Palestine TV"),
     "تلفزيون فلسطين", "palestine_tv.png"),
    ("PalestineMubashir.ps", ("Palestine Mubashir [ Live ]", "Palestine Mubashir",
                              "Palestine Live", "PS| Palestine Mubashir"),
     "فلسطين مباشر", "palestine_mubashir.png"),
    ("PalestineAlYawm.ps", ("Palestine Al Yawm", "Palestine Today",
                            "Palestine Al Youm", "PS| Palestine Al Yawm"),
     "فلسطين اليوم", "palestine_alyawm.png"),
    ("PalestineSport.ps", ("Palestine Sport", "Palestine Sports",
                           "PS| Palestine Sport"),
     "فلسطين الرياضية", "palestine_sport.png"),
    ("FalastiniTV.ps", ("Falastini TV", "Falastini", "PS| Falastini TV"),
     "تلفزيون فلسطيني", "falastini_tv.png"),
    ("AlKofiya.ps", ("Al Kofiya", "Al Kofiya TV", "Alkofiya", "Al Kufiya",
                     "PS| Al Kofiya"),
     "الكوفية", "alkofiya.png"),
    ("AlQudsToday.ps", ("Al Quds Today", "Al Quds Al Yawm", "Quds Today",
                        "PS| Al Quds Today"),
     "القدس اليوم", "alquds_today.png"),
    ("HalaTV.ps", ("Hala TV", "Hala", "PS| Hala TV"),
     "هلا", "hala_tv.png"),
)


def collect(session=None, previous_path: str = "") -> dict[str, list[dict]]:
    first = (datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    out = {}
    for xid, names, arabic, _logo in CHANNELS:
        out[xid] = [{"start": first + timedelta(days=n),
                     "stop": first + timedelta(days=n + 1),
                     "desc": f"{names[0]} — {arabic}"}
                    for n in range(DAYS_BACK + DAYS_FORWARD)]
    return out


def emit(root: ET.Element, per_channel: dict[str, list[dict]]) -> int:
    count = 0
    for xid, names, arabic, logo in CHANNELS:
        rows = per_channel.get(xid) or []
        if not rows:
            continue
        ch = ET.SubElement(root, "channel", {"id": xid})
        # First name in both scripts: a player lists and searches a guide
        # channel by its first name only.
        ET.SubElement(ch, "display-name", {"lang": "ar"}).text = \
            f"{names[0]} | {arabic}"
        for name in names:
            ET.SubElement(ch, "display-name", {"lang": "en"}).text = name
        ET.SubElement(ch, "display-name", {"lang": "ar"}).text = arabic
        ET.SubElement(ch, "icon", {"src": LOGO.format(name=logo)})
        for row in rows:
            add_programme(root, xid, row["start"], row["stop"], TITLE,
                          row["desc"])
            count += 1
    return count
