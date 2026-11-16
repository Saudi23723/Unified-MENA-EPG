#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Jordan TV (التلفزيون الأردني) — its real schedule, on the Roya link.

Asked for from a photo of the player: the channel sat without a guide.
The channel's own site (jrtv.gov.jo) has a schedule panel, but it is fed
by global-epg-prod.erstream.com, which answers every hour of every day
with "معلومات البرنامج غير متوفرة" — nothing is published there. Two
places do carry the real schedule, and each has half of it:

- epgshare01's guide for the Gulf satellite line-ups
  (epg_ripper_AE1.xml.gz, channel "Jordan.TV.HD.ae"): four days, with
  descriptions, in English. Its clock is Amman's wall clock labelled
  "+0100" — read at face value every row landed two hours late, which
  the viewer caught ("شفاء القلوب" on screen while the guide still showed
  the Quran). The day signs on with the royal anthem at 06:00 Amman, and
  elcinema's copy of the same day lines up with it once the rows are
  read as Amman time (+03:00, Jordan's clock all year since 2022).
- elcinema.com's page for the channel (/tvguide/1314/): the channel's own
  rows under their Arabic names, about a day and a half of them.

Where elcinema covers the day, its rows are published — on a clock read
off the page's own news bulletins (see elcinema_jo.py), because the page
prints in the visitor's clock and that drifts from runner to runner. The
names used to be matched onto the English rows by the run of durations
and remembered week to week; that placement followed the drift and put
"صلاة الجمعة" on a Saturday and Arabic names on the wrong shows (3
October 2026), so neither the matching nor the memory is used any more.
The English guide fills the rest of the week, and lends its description
to an elcinema row of the same start and length.

The channel wears its own logo, the crown and "الأردني" from jrtv.gov.jo
(logos/jordan_tv.png).
"""

from __future__ import annotations

import gzip
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import elcinema_jo
from epg_lib import add_programme, fetch, log, warn

SOURCE = "https://epgshare01.online/epgshare01/epg_ripper_AE1.xml.gz"
SOURCE_ID = "Jordan.TV.HD.ae"
AMMAN = timezone(timedelta(hours=3))
XMLTV_ID = "JordanTV.jo"
NAMES = ("Jordan TV", "Jordan TV HD", "JO| Jordan TV", "Jordan", "JRTV",
         "Al Urdun", "Al Ordon TV")
ARABIC = "التلفزيون الأردني"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/jordan_tv.png")
KEEP_BEHIND = timedelta(hours=12)


def amman_wall_clock(raw: str) -> datetime | None:
    """The row's time as written, read as Amman's clock (the label the
    source puts on it is not)."""
    try:
        wall = datetime.strptime(raw.strip()[:14], "%Y%m%d%H%M%S")
    except (ValueError, AttributeError):
        return None
    return wall.replace(tzinfo=AMMAN).astimezone(timezone.utc)


def read_rows(session) -> list[dict]:
    raw = fetch(session, SOURCE, timeout=120).content
    text = gzip.decompress(raw).decode("utf-8", "ignore")
    floor = datetime.now(timezone.utc) - KEEP_BEHIND
    rows = []
    for block in re.findall(
            r'<programme\b[^>]*channel="' + re.escape(SOURCE_ID)
            + r'"[^>]*>.*?</programme>', text, re.S):
        node = ET.fromstring(block)
        start = amman_wall_clock(node.get("start"))
        stop = amman_wall_clock(node.get("stop"))
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
    return [r for r in rows if r["stop"] > r["start"]]


def collect(session, previous_path: str = "") -> dict[str, list[dict]]:
    rows = read_rows(session)
    try:
        arabic = elcinema_jo.channel(session, elcinema_jo.JORDAN_TV)
    except Exception as exc:                                  # noqa: BLE001
        warn(f"Jordan TV: elcinema unavailable ({exc}) — English rows only")
        arabic = []
    if arabic:
        # Where elcinema covers the day, its rows ARE the day: the channel's
        # own Arabic names, on a clock its bulletins set. The English guide
        # fills the rest of the week, and lends its description (and its
        # name, for a row elcinema leaves unnamed) to an elcinema row of the
        # same start and length.
        lo, hi = arabic[0]["start"], arabic[-1]["stop"]
        english = {r["start"]: r for r in rows}
        inside = []
        for a in arabic:
            twin = english.get(a["start"])
            # Same minute AND same length, or it is not the same show: the
            # English guide repeats a stale day now and then ("Friday's
            # Talks" on a Saturday), and its name beside the right Arabic
            # one would mislead.
            if twin and twin["stop"] - twin["start"] != a["stop"] - a["start"]:
                twin = None
            inside.append({"start": a["start"], "stop": a["stop"],
                           "arabic": a["name"],
                           "title": twin["title"] if twin else
                           (a["name"] or elcinema_jo.UNNAMED),
                           "desc": twin["desc"] if twin else ""})
        rows = [r for r in rows if r["stop"] <= lo] + inside + \
            [r for r in rows if r["start"] >= hi]
    if not rows:
        warn("Jordan TV: the guide carried nothing for it this run")
        return {}
    for r in rows:
        r.setdefault("arabic", "")
    named = sum(1 for r in rows if r["arabic"])
    log(f"  Jordan TV{'':21} {len(rows):4} programmes, {named} under their "
        f"Arabic name from elcinema ({len(arabic)} on its page)")
    return {XMLTV_ID: rows}


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
        if row.get("arabic"):
            add_programme(root, XMLTV_ID, row["start"], row["stop"],
                          row["arabic"], row["desc"],
                          alt_titles=[("en", row["title"])])
        else:
            add_programme(root, XMLTV_ID, row["start"], row["stop"],
                          row["title"], row["desc"])
    return len(rows)
