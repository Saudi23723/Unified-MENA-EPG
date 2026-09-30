#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Jordan TV (التلفزيون الأردني) — its real schedule, on the Roya link.

Asked for from a photo of the player: the channel sat without a guide.
jrtv.gov.jo is a single-page app with no schedule anyone can read, and
its Telegram channels are empty, so this reads the one place the real
schedule is published: epgshare01's guide for the Gulf satellite
line-ups (epg_ripper_AE1.xml.gz), channel "Jordan.TV.HD.ae". Checked on
a runner: four days of programmes with their descriptions — "Healing
Hearts" (شفاء القلوب, Dr. Zaid Al Kilani), "Eyes On Jerusalem", the
news hours — in English, as that guide writes them, with explicit
offsets.

The channel wears the logo asked for: the Jordan Football Association's
round red mark, from jfa.jo itself, on a transparent square
(logos/jordan_tv.png).
"""

from __future__ import annotations

import gzip
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from epg_lib import add_programme, fetch, log, warn

SOURCE = "https://epgshare01.online/epgshare01/epg_ripper_AE1.xml.gz"
SOURCE_ID = "Jordan.TV.HD.ae"
XMLTV_ID = "JordanTV.jo"
NAMES = ("Jordan TV", "Jordan TV HD", "JO| Jordan TV", "Jordan", "JRTV",
         "Al Urdun", "Al Ordon TV")
ARABIC = "التلفزيون الأردني"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/jordan_tv.png")
KEEP_BEHIND = timedelta(hours=12)


def when(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw.strip(), "%Y%m%d%H%M%S %z").astimezone(
            timezone.utc)
    except (ValueError, AttributeError):
        return None


def collect(session, previous_path: str = "") -> dict[str, list[dict]]:
    raw = fetch(session, SOURCE, timeout=120).content
    text = gzip.decompress(raw).decode("utf-8", "ignore")
    floor = datetime.now(timezone.utc) - KEEP_BEHIND
    rows = []
    for block in re.findall(
            r'<programme\b[^>]*channel="' + re.escape(SOURCE_ID)
            + r'"[^>]*>.*?</programme>', text, re.S):
        node = ET.fromstring(block)
        start, stop = when(node.get("start")), when(node.get("stop"))
        title = (node.findtext("title") or "").strip()
        if not start or not stop or stop <= start or not title or stop < floor:
            continue
        rows.append({"start": start, "stop": stop, "title": title,
                     "desc": (node.findtext("desc") or "").strip()})
    rows.sort(key=lambda r: r["start"])
    # No row runs over the next one's start.
    for a, b in zip(rows, rows[1:]):
        if b["start"] < a["stop"]:
            a["stop"] = b["start"]
    rows = [r for r in rows if r["stop"] > r["start"]]
    if not rows:
        warn("Jordan TV: the guide carried nothing for it this run")
        return {}
    log(f"  Jordan TV{'':21} {len(rows):4} programmes (epgshare01)")
    return {XMLTV_ID: rows}


def emit(root: ET.Element, per_channel: dict[str, list[dict]]) -> int:
    rows = per_channel.get(XMLTV_ID) or []
    if not rows:
        return 0
    ch = ET.SubElement(root, "channel", {"id": XMLTV_ID})
    for name in NAMES:
        ET.SubElement(ch, "display-name", {"lang": "en"}).text = name
    ET.SubElement(ch, "display-name", {"lang": "ar"}).text = ARABIC
    ET.SubElement(ch, "icon", {"src": LOGO})
    for row in rows:
        add_programme(root, XMLTV_ID, row["start"], row["stop"],
                      row["title"], row["desc"])
    return len(rows)
