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

They ride on the Alwan guide itself (update_alwan_epg.py adds them to
alwan_sports_epg.xml, beside the numbered Alwan Sport channels and their
real matches): that is the link the player reads Alwan from, and a
separate file never reached it.
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


# Two more channels on this same link, asked for by name, with the same
# "24/7 Program" row: ShoofMax and Netflix. Not Alwan's, so they keep
# their own ids and names, and wear their own marks (logos/shoofmax.png
# and logos/netflix.png, each service's own logo from its own site, on
# the black square the other logos on this player use).
OTHERS = (
    ("ShoofMax", ("ShoofMax", "Shoof Max", "ShoofMax 4K", "ShoofMax HD",
                  "ShoofMax FHD", "Shoof Max 4K"),
     "شوف ماكس", "shoofmax.png"),
    ("Netflix", ("Netflix", "Netflix 4K", "Netflix HD", "Netflix FHD"),
     "نتفليكس", "netflix.png"),
    # One entry per Netflix channel in the playlist, each its own id: a
    # player that has matched "Netflix" to one channel stops offering it
    # for the next, so every channel needs a guide row of its own, named
    # the way the playlist names it.
    ("Netflix.BoxOffice", ("Box Office 4K", "Netflix Box Office 4K",
                           "Box Office"),
     "نتفليكس بوكس أوفيس", "netflix.png"),
) + tuple(
    (f"Netflix.ActionHD{n}", (f"Netflix Action New HD{n}",
                              f"Netflix Action HD{n}"),
     f"نتفليكس أكشن {n}", "netflix.png")
    for n in range(1, 6)
) + tuple(
    # Al Rabiaa's own channels (Iraq): no schedule is published anywhere
    # for them — alrabiaa.tv sits behind Cloudflare, the public guides
    # carry only the main news channel, and the sports channel's own
    # Telegram names its shows without times — so a 24/7 row with the
    # network's own mark (from its official Telegram), asked for outright.
    (f"AlRabiaa.{key}", tuple(f"{prefix}Al Rabiaa {name}{suffix}"
                              for prefix in ("IQ| ", "")
                              for suffix in ("", " HD", " 4K")),
     arabic, logo)
    for key, name, arabic, logo in (
        ("Sport1", "Sport 1", "الرابعة الرياضية 1", "alrabiaa_sport.png"),
        ("Sport1Plus", "Sport +1", "الرابعة الرياضية +1", "alrabiaa_sport.png"),
        ("Sport2", "Sport 2", "الرابعة الرياضية 2", "alrabiaa_sport.png"),
        ("Sport2Plus", "Sport +2", "الرابعة الرياضية +2", "alrabiaa_sport.png"),
        ("Geo", "Geo", "الرابعة جيو", "alrabiaa_geo.png"),
        ("Movies", "Movies", "الرابعة أفلام", "alrabiaa_movies.png"),
        ("Quran", "Quran", "الرابعة قرآن", "alrabiaa_quran.png"),
    )
)
LOGO_FILE = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
             "main/logos/{name}")


def channel_id(key: str) -> str:
    return f"Alwan_{key}"


def add_to(root) -> int:
    """Put the channels and their rows into `root`, a guide being built —
    the Alwan guide, alwan_sports_epg.xml, which is the link the player
    reads Alwan from. Channels go in after the guide's own channels, so
    every channel still comes before every programme."""
    now = datetime.now(timezone.utc)
    first = (now - timedelta(days=DAYS_BACK)).replace(
        hour=0, minute=0, second=0, microsecond=0)

    at = len(root.findall("channel"))
    every = ([(channel_id(key), names, f"الوان {name_ar}",
               LOGO.format(key=key))
              for key, names, name_ar, _colour, _tag in CHANNELS]
             + [(xid, names, arabic, LOGO_FILE.format(name=logo))
                for xid, names, arabic, logo in OTHERS])
    for xid, names, arabic, icon in every:
        ch = ET.Element("channel", {"id": xid})
        for name in names:
            ET.SubElement(ch, "display-name", {"lang": "en"}).text = name
        ET.SubElement(ch, "display-name", {"lang": "ar"}).text = arabic
        ET.SubElement(ch, "icon", {"src": icon})
        root.insert(at, ch)
        at += 1

    count = 0
    for xid, names, arabic, _icon in every:
        for day in range(DAYS_BACK + DAYS_FORWARD):
            start = first + timedelta(days=day)
            add_programme(root, xid, start, start + timedelta(days=1), TITLE,
                          f"{names[0]} — {arabic}")
            count += 1
    log(f"Alwan channels: {len(every)} channel(s), {count} programme(s)")
    return count


def add_others_to(root, prefix: str) -> int:
    """ShoofMax and Netflix alone, on another link — the beIN Qatar guide
    carries them too, under its own ids (prefix) so the merged link never
    holds one id twice."""
    now = datetime.now(timezone.utc)
    first = (now - timedelta(days=DAYS_BACK)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    count = 0
    for xid, names, arabic, logo in OTHERS:
        ch = ET.SubElement(root, "channel", {"id": prefix + xid})
        for name in names:
            ET.SubElement(ch, "display-name", {"lang": "en"}).text = name
        ET.SubElement(ch, "display-name", {"lang": "ar"}).text = arabic
        ET.SubElement(ch, "icon", {"src": LOGO_FILE.format(name=logo)})
        for day in range(DAYS_BACK + DAYS_FORWARD):
            start = first + timedelta(days=day)
            add_programme(root, prefix + xid, start, start + timedelta(days=1),
                          TITLE, f"{names[0]} — {arabic}")
            count += 1
    return count


def build() -> int:
    """Standalone: these channels alone, for a look at them."""
    root = ET.Element("tv", {"generator-info-name": "Alwan channels"})
    add_to(root)
    write_xml_atomic(root, OUTPUT, generator_name="Alwan channels",
                     guard_regression=False, min_programmes=1)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
