#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Amman TV (قناة عمّان) — on the Roya link, asked for from a photo of the
player (the channel showing "الأخوة بربروس" with no guide).

WHERE THE SCHEDULE IS. Every source was tried first (3 October 2026):
the channel's own site (ammantv.net) and app are built on a platform whose
channel record has its guide switched off (ItemEpgData: false) — opened in
a real browser, the schedule page is a 404 and the live page asks for no
guide; epgshare01's AE1 "Amman.TV.HD.ae" carries Al Mamlaka's shows under
Amman's name; sat.tv is behind Cloudflare. elcinema.com's page for the
channel (/tvguide/1298/) is the one real listing: its own shows by name —
بصراحة، هاتريك، مرايا 2003، صباح الخير يا أردن، Barbaros.

ITS CLOCK IS NOT STATED — elcinema prints in the visitor's clock, which
changes from runner to runner. elcinema_jo.py reads it off TV Jordan's
bulletins on the same visit, and refuses the page if they disagree.

A row elcinema names only "برنامج" (a programme, unnamed — often a
rerun) keeps that word rather than a title nobody announced.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import elcinema_jo
from epg_lib import add_programme, log

ELCINEMA_ID = 1298
XMLTV_ID = "AmmanTV.jo"
NAMES = ("Amman TV", "Amman TV HD", "JO| Amman TV", "AmmanTV", "Amman")
ARABIC = "قناة عمّان"
# The channel's own mark, from its site (ammantv.net/apple-icon.png).
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/amman_tv.png")
KEEP_BEHIND = timedelta(hours=12)


def collect(session, previous_path: str = "") -> dict[str, list[dict]]:
    rows = elcinema_jo.channel(session, ELCINEMA_ID)
    now = datetime.now(timezone.utc)
    out = [{"start": r["start"], "stop": r["stop"],
            "title": r["name"] or elcinema_jo.UNNAMED}
           for r in rows if r["stop"] > now - KEEP_BEHIND]
    if not out:
        return {}
    named = sum(1 for r in out if r["title"] != elcinema_jo.UNNAMED)
    log(f"  Amman TV{'':22} {len(out):4} programmes (elcinema), "
        f"{named} named")
    return {XMLTV_ID: out}


def emit(root: ET.Element, per_channel: dict[str, list[dict]]) -> int:
    rows = per_channel.get(XMLTV_ID) or []
    if not rows:
        return 0
    ch = ET.SubElement(root, "channel", {"id": XMLTV_ID})
    # First name in both scripts: a player lists and searches a guide
    # channel by its first name only.
    ET.SubElement(ch, "display-name", {"lang": "ar"}).text = \
        f"{NAMES[0]} | {ARABIC}"
    for name in NAMES:
        ET.SubElement(ch, "display-name", {"lang": "en"}).text = name
    ET.SubElement(ch, "display-name", {"lang": "ar"}).text = ARABIC
    ET.SubElement(ch, "icon", {"src": LOGO})
    for row in rows:
        add_programme(root, XMLTV_ID, row["start"], row["stop"],
                      row["title"], f"{ARABIC} — {row['title']}")
    return len(rows)
