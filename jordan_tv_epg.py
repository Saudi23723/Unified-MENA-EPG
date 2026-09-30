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
- elcinema.com's page for the channel (/tvguide/1314/): the same rows
  under their Arabic names, for one day, in a clock it does not state
  (it follows the visitor's location).

So the times and descriptions come from the first, and the Arabic names
from the second, matched by the shape of the day — the run of durations
— rather than by any clock elcinema would have to be trusted for. Every
English name matched that way is remembered (read back from the guide
this file wrote last time), so the days elcinema does not show yet get
their Arabic names too, the shows being the same ones week in, week out.
A row whose Arabic name is not known yet keeps its English one.

The channel wears its own logo, the crown and "الأردني" from jrtv.gov.jo
(logos/jordan_tv.png).
"""

from __future__ import annotations

import gzip
import html as htmllib
import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone

from epg_lib import add_programme, fetch, log, warn

SOURCE = "https://epgshare01.online/epgshare01/epg_ripper_AE1.xml.gz"
SOURCE_ID = "Jordan.TV.HD.ae"
ARABIC_SOURCE = "https://elcinema.com/ar/tvguide/1314/"
AMMAN = timezone(timedelta(hours=3))
XMLTV_ID = "JordanTV.jo"
NAMES = ("Jordan TV", "Jordan TV HD", "JO| Jordan TV", "Jordan", "JRTV",
         "Al Urdun", "Al Ordon TV")
ARABIC = "التلفزيون الأردني"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/jordan_tv.png")
KEEP_BEHIND = timedelta(hours=12)
# How much of elcinema's list has to agree exactly before its names are
# used: well past what a wrong placement lines up by chance (a handful).
LEAST_MATCHED = 8
LEAST_SHARE = 0.25


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


def clean_arabic(title: str) -> str:
    title = re.sub(r"\s+", " ", htmllib.unescape(title)).strip()
    title = title.replace("ىالمتحركة", "المتحركة")   # elcinema's typo
    title = re.sub(r"^برنامج\s+", "", title)
    # A bare "برنامج" names nothing; the English name says more.
    return "" if title == "برنامج" else title


def read_arabic_day(session) -> list[tuple[str, int, int]]:
    """elcinema's day: (Arabic name, minutes from its first row, length)."""
    page = fetch(session, ARABIC_SOURCE, timeout=60).text
    out, offset, last = [], 0, None
    for box in page.split('class="boxed-category-')[1:]:
        when = re.search(r"(\d{1,2}):(\d{2})\s*(صباح|مساء)", box)
        length = re.search(r"\[(\d+)\s*دقيقة\]", box)
        name = re.search(r'<a href="/work/\d+/">([^<]+)</a>', box) or \
            re.search(r'<ul class="unstyled no-margin">\s*<li>([^<]+)</li>', box)
        if not (when and length and name):
            continue
        hour = int(when.group(1)) % 12 + (12 if when.group(3) == "مساء" else 0)
        minute = hour * 60 + int(when.group(2))
        if last is not None:
            offset += (minute - last) % (24 * 60)
        last = minute
        out.append((clean_arabic(name.group(1)), offset, int(length.group(1))))
    # A row with no usable name still marks where the day's rows fall.
    return out


def minutes(row: dict) -> int:
    return round((row["stop"] - row["start"]).total_seconds() / 60)


def match_day(rows: list[dict], day: list[tuple[str, int, int]]) -> dict[int, str]:
    """Where elcinema's days sit among the rows: the placement at which
    the most of its rows start exactly on a row of the same length. The
    two lists are not cut the same everywhere — elcinema folds a morning
    show's two halves into one block, and leaves a short filler out — so
    the placement is found on the rows that agree exactly, and then each
    elcinema row names the row that starts where it starts.
    Returns {row index: Arabic name}."""
    if not day:
        return {}
    at = {r["start"]: i for i, r in enumerate(rows)}
    best_score, best_base = 0, None
    for r in rows:
        # Every row is tried as the place elcinema's first row starts —
        # not only rows of its length: its first row is often one of the
        # blocks cut differently.
        score = 0
        for _name, offset, length in day:
            i = at.get(r["start"] + timedelta(minutes=offset))
            if i is not None and minutes(rows[i]) == length:
                score += 1
        if score > best_score:
            best_score, best_base = score, r["start"]
    if best_base is None or best_score < LEAST_MATCHED \
            or best_score < LEAST_SHARE * len(day):
        warn(f"Jordan TV: elcinema's days did not line up "
             f"({best_score}/{len(day)}), English names kept")
        return {}
    found = {}
    for name, offset, _length in day:
        i = at.get(best_base + timedelta(minutes=offset))
        if i is not None and name:
            found[i] = name
    return found


def known_names(previous_path: str) -> dict[str, str]:
    """English name -> Arabic name, as written by the last run."""
    names: dict[str, str] = {}
    if not previous_path:
        return names
    try:
        root = ET.parse(previous_path).getroot()
    except (OSError, ET.ParseError):
        return names
    for p in root.iter("programme"):
        if p.get("channel") != XMLTV_ID:
            continue
        ar = en = None
        for t in p.findall("title"):
            if t.get("lang") == "ar":
                ar = (t.text or "").strip()
            elif t.get("lang") == "en":
                en = (t.text or "").strip()
        if ar and en:
            names[en] = ar
    return names


def collect(session, previous_path: str = "") -> dict[str, list[dict]]:
    rows = read_rows(session)
    if not rows:
        warn("Jordan TV: the guide carried nothing for it this run")
        return {}
    names = known_names(previous_path)
    try:
        matched = match_day(rows, read_arabic_day(session))
    except Exception as exc:
        warn(f"Jordan TV: elcinema unavailable ({exc}), known names used")
        matched = {}
    votes: dict[str, Counter] = {}
    for i, ar in matched.items():
        votes.setdefault(rows[i]["title"], Counter())[ar] += 1
    for en, count in votes.items():
        names[en] = count.most_common(1)[0][0]
    for i, r in enumerate(rows):
        r["arabic"] = matched.get(i) or names.get(r["title"], "")
    named = sum(1 for r in rows if r["arabic"])
    log(f"  Jordan TV{'':21} {len(rows):4} programmes (epgshare01), "
        f"{named} with their Arabic name (elcinema: {len(matched)} matched)")
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
