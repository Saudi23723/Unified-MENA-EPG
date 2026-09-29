#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The Alwan channels no guide had: films, series, documentaries, songs,
children's, Quran, and the F1, WWE and UFC sports feeds.

Asked for outright, from photos of the player: every one of them sat on
"No information", with a logo from the playlist and nothing behind it.
Alwan publishes no schedule for them, so this guide says what they are —
channels that run all day — as one "24/7 Program" row a day, under the
names the playlist gives them, each with its own logo in Alwan's style
(make_alwan_channel_logos.py draws them).

The numbered Alwan Sport channels are not here: update_alwan_epg.py
carries those, with their real matches.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from epg_lib import add_programme, log, run_main, write_xml_atomic

OUTPUT = "alwan_channels_epg.xml"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/alwan_{key}.png")
TITLE = "24/7 Program"
DAYS_BACK = 1
DAYS_FORWARD = 7

# (key, names the playlist uses, the Arabic name on the logo, colour,
#  the tag above the name)
CHANNELS = (
    ("aflam1", ("Alwan Aflam 1 4K", "Alwan Aflam 1"), "أفلام 1",
     (40, 120, 230), "الوان"),
    ("aflam2", ("Alwan Aflam 2 4K", "Alwan Aflam 2"), "أفلام 2",
     (40, 120, 230), "الوان"),
    ("aflam3", ("Alwan Aflam 3 4K", "Alwan Aflam 3"), "أفلام 3",
     (40, 120, 230), "الوان"),
    ("aflam4", ("Alwan Aflam 4 4K", "Alwan Aflam 4"), "أفلام 4",
     (40, 120, 230), "الوان"),
    ("mosalsalat", ("Alwan Mosalsalat 4K", "Alwan Mosalsalat"), "مسلسلات",
     (70, 90, 225), "الوان"),
    ("mosalsalat_plus", ("Alwan Mosalsalat+ 4K", "Alwan Mosalsalat+",
                         "Alwan Mosalsalat Plus 4K"), "مسلسلات+",
     (70, 90, 225), "الوان"),
    ("turkey", ("Alwan Turkey 4K", "Alwan Turkey"), "تركي",
     (240, 60, 150), "الوان"),
    ("korea", ("Alwan Korea 4K", "Alwan Korea"), "كوريا",
     (160, 80, 225), "الوان"),
    ("bollywood", ("Alwan Bollywood 4K", "Alwan Bollywood"), "بوليوود",
     (245, 130, 30), "الوان"),
    ("anime", ("Alwan Anime 4K", "Alwan Anime"), "أنيمي",
     (20, 185, 190), "الوان"),
    ("wathaeqiya", ("Alwan Alwathaeqye 4K", "Alwan Alwathaeqye",
                    "Alwan Documentary 4K"), "الوثائقية",
     (230, 160, 30), "الوان"),
    ("aghani", ("Alwan Aghani 4K", "Alwan Aghani"), "أغاني",
     (235, 50, 50), "الوان"),
    ("atfal", ("Alwan Atfal 4K", "Alwan Atfal"), "أطفال",
     (245, 160, 30), "الوان"),
    ("quran", ("Alwan Quran 4K", "Alwan Quran"), "القرآن",
     (190, 200, 40), "الوان"),
    ("f1", ("Alwan F1 4K", "Alwan F1"), "الرياضية",
     (230, 40, 40), "F1"),
    ("wwe", ("Alwan WWE 4K", "Alwan WWE"), "الرياضية",
     (230, 40, 40), "WWE"),
    ("ufc", ("Alwan UFC 4K", "Alwan UFC"), "الرياضية",
     (230, 40, 40), "UFC"),
)


def channel_id(key: str) -> str:
    return f"Alwan_{key}"


def build() -> int:
    now = datetime.now(timezone.utc)
    first = (now - timedelta(days=DAYS_BACK)).replace(
        hour=0, minute=0, second=0, microsecond=0)

    root = ET.Element("tv", {"generator-info-name": "Alwan channels"})
    for key, names, name_ar, _colour, _tag in CHANNELS:
        ch = ET.SubElement(root, "channel", {"id": channel_id(key)})
        for name in names:
            ET.SubElement(ch, "display-name", {"lang": "en"}).text = name
        ET.SubElement(ch, "display-name", {"lang": "ar"}).text = \
            f"الوان {name_ar}"
        ET.SubElement(ch, "icon", {"src": LOGO.format(key=key)})

    count = 0
    for key, names, name_ar, _colour, _tag in CHANNELS:
        for day in range(DAYS_BACK + DAYS_FORWARD):
            start = first + timedelta(days=day)
            add_programme(root, channel_id(key), start,
                          start + timedelta(days=1), TITLE,
                          f"{names[0]} — الوان {name_ar}")
            count += 1

    write_xml_atomic(root, OUTPUT, generator_name="Alwan channels",
                     guard_regression=False, min_programmes=1)
    log(f"Alwan channels: {len(CHANNELS)} channel(s), {count} programme(s)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
