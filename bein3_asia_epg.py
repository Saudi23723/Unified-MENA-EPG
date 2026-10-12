#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
beIN SPORTS 3 Asia, on the Roya link — asked for by name.

The Asian feed's full schedule as its Indonesian operator publishes it,
from epgshare01's ID1 guide (beIN.Sports.3.id). It keeps the id it was
first published under (RoyaPH.…), so a channel already matched to it in
the player stays matched.
"""

from __future__ import annotations

import gzip
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from epg_lib import add_programme, fetch, log, warn

SOURCE = "https://epgshare01.online/epgshare01/epg_ripper_ID1.xml.gz"
SOURCE_ID = "beIN.Sports.3.id"
XMLTV_ID = "RoyaPH.beIN_SPORTS_3_Asia"
NAMES = ("beIN SPORTS 3 Asia", "beIN Sports 3 Asia", "BEIN SPORTS 3 ASIA",
         "beIN SPORTS 3 HD Asia", "beIN Sports 3")
KEEP_BEHIND = timedelta(hours=12)


def xmltv(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw.strip(), "%Y%m%d%H%M%S %z").astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def collect(session, previous_path: str = "") -> dict:
    text = gzip.decompress(fetch(session, SOURCE, timeout=180).content).decode("utf-8", "ignore")
    esc = re.escape(SOURCE_ID)
    icon = ""
    m = re.search(r'<channel id="' + esc + r'">.*?</channel>', text, re.S)
    if m:
        found = re.search(r'<icon src="([^"]+)"', m.group(0))
        icon = found.group(1) if found else ""
    floor = datetime.now(timezone.utc) - KEEP_BEHIND
    rows = []
    for block in re.findall(r'<programme\b[^>]*channel="' + esc + r'"[^>]*>.*?</programme>',
                            text, re.S):
        node = ET.fromstring(block)
        start, stop = xmltv(node.get("start")), xmltv(node.get("stop"))
        title = (node.findtext("title") or "").strip()
        if not start or not stop or stop <= start or not title or stop < floor:
            continue
        sub = (node.findtext("sub-title") or "").strip()
        desc = (node.findtext("desc") or "").strip()
        rows.append({"start": start, "stop": stop, "title": title,
                     "desc": " — ".join(x for x in (sub, desc) if x)})
    rows.sort(key=lambda r: r["start"])
    for a, b in zip(rows, rows[1:]):
        if b["start"] < a["stop"]:
            a["stop"] = b["start"]
    rows = [r for r in rows if r["stop"] > r["start"]]
    if not rows:
        warn("beIN SPORTS 3 Asia: nothing in the guide this run")
        return {}
    log(f"  beIN SPORTS 3 Asia{'':12} {len(rows):4} programmes (epgshare ID1)")
    return {XMLTV_ID: {"icon": icon, "rows": rows}}


def emit(root: ET.Element, per_channel: dict) -> int:
    data = per_channel.get(XMLTV_ID)
    if not data:
        return 0
    ch = ET.SubElement(root, "channel", {"id": XMLTV_ID})
    for name in NAMES:
        ET.SubElement(ch, "display-name", {"lang": "en"}).text = name
    if data["icon"]:
        ET.SubElement(ch, "icon", {"src": data["icon"]})
    for r in data["rows"]:
        add_programme(root, XMLTV_ID, r["start"], r["stop"], r["title"], r["desc"])
    return len(data["rows"])
