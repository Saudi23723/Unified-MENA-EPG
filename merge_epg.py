#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Merge every per-source XMLTV file already committed in this repo into one
combined guide: unified_mena_epg.xml.

This script does NOT hit any network source itself — it only reads XML
files that the individual per-source workflows already produced and
validated. That keeps it trivially safe to run on its own schedule
without risking any external API. A missing or unreadable source file is
skipped with a warning; it never stops the merge.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from epg_lib import add_programme, log, warn, write_xml_atomic

OUTPUT = "unified_mena_epg.xml"

# Every XMLTV file this repository's scripts can produce. Add new sources
# here as they're introduced — nothing else needs to change.
SOURCE_FILES = [
    "bein_sports_qatar_epg.xml",
    "bein_sports_turkey_epg.xml",
    "roya_jordan_epg.xml",
    "jordan_sports_epg.xml",
    "onsport_epg.xml",
    "alwan_sports_epg.xml",
    "alkass_epg.xml",
    "starzplay_epg.xml",
    "fajer_sports_epg.xml",
    "shahid_sports_epg.xml",
    "shasha_epg.xml",
    "tabii_spor_1_10_epg.xml",
    "today_matches_epg.xml",
    # The second board — رياضات اليوم. Written by the ten-minute
    # workflow rather than by the full build, exactly like the first
    # board's guide above, and merged here for the same reason: this
    # is the file a player actually loads, so a channel missing from
    # it is a channel with no programmes on the television however
    # well its own guide was built.
    "other_sports_epg.xml",
    # The third channel — أخبار اليوم. A rolling bulletin rather than
    # a schedule, written by the same ten-minute workflow as the two
    # boards beside it.
    "news_epg.xml",
    "thmanyah_epg.xml",
    # The fourth channel — 🌤️ طقس اليوم. Written by the ten-minute
    # workflow like the two boards beside it, from live Open-Meteo
    # readings drawn as boards by weather_epg.py. The entry this
    # replaced was epg.xml — its name unquoted here on purpose —
    # committed by an automation outside that stopped updating it: a
    # guide still carrying yesterday's hours is not a guide, so this is
    # the file the channel's own build writes. A missing or unparsable
    # file is skipped with a warning below, so a pass that runs before
    # the weather's first build simply merges without it.
    "weather_epg.xml",
    # The seventh channel — مواقيت الصلاة, four cities each in its own
    # authority's calculation. Missing before its first build, and the
    # merge simply goes on without it.
    "prayer_epg.xml",
    # The fourteenth channel — الفورمولا 1, every session of the season.
    "f1_epg.xml",
    # The rest of the dashboard, both lists. The dashboard's guide is this
    # file (DASHBOARD_GUIDE.md), and until 6 October 2026 fifteen of its
    # twenty-two channels were not in it: the ball games, the Turkish PPV,
    # the multi-sport channel and every one of the Emirates-time list
    # showed nothing on the television however well their own guides were
    # built. Each id is the channel's own (…Dubai for the second list).
    "ball_sports_epg.xml",
    "hoops_gridiron_epg.xml",
    "turkish_ppv_epg.xml",
    "multi_sport_epg.xml",
    "dubai_matches_epg.xml",
    "dubai_sports_epg.xml",
    "dubai_news_epg.xml",
    "dubai_weather_epg.xml",
    "dubai_ball_sports_epg.xml",
    "dubai_hoops_gridiron_epg.xml",
    "dubai_turkish_ppv_epg.xml",
    "dubai_multi_sport_epg.xml",
    "dubai_f1_epg.xml",
]

# The dashboard channels no generator writes a guide for.
#
# Ain FM is a radio station that publishes no schedule; what is on is the
# station, live, all day. مواقيت الصلاة on the Emirates-time list is the
# same reel as the first list's under its own id (sports_dashboard_m3u.py
# says why the id differs), so it carries the same rows.
AIN_FM_IDS = ("AinFMJordan", "AinFMJordanDubai")
AIN_FM_NAME = "Ain FM 98.3"
AIN_FM_TITLE = "🎙️ Ain FM 98.3 — بث مباشر من عمّان"
AIN_FM_DESC = "راديو عين إف إم ٩٨٫٣ من الأردن — البث الحي للإذاعة على مدار الساعة."
PRAYER_COPIES = {"TodayPrayer": "TodayPrayerDubai"}
LOGO_BASE = "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/logos"


def add_dashboard_extras(root: ET.Element, have: set[str]) -> int:
    added = 0
    now = datetime.now(timezone.utc)
    first = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=now.hour % 6 + 6)
    for cid in AIN_FM_IDS:
        if cid in have:
            continue
        ch = new_channel(root, cid)
        ET.SubElement(ch, "display-name").text = AIN_FM_NAME
        ET.SubElement(ch, "icon", src=f"{LOGO_BASE}/ain_fm.png")
        start = first
        while start < now + timedelta(hours=54):
            add_programme(root, cid, start, start + timedelta(hours=6),
                          AIN_FM_TITLE, AIN_FM_DESC)
            start += timedelta(hours=6)
        have.add(cid)
        added += 1
    for src, copy in PRAYER_COPIES.items():
        if copy in have or src not in have:
            continue
        orig = next(c for c in root.findall("channel") if c.get("id") == src)
        ch = new_channel(root, copy)
        for child in orig:
            ch.append(copy_element(child))
        for pr in [p for p in root.findall("programme") if p.get("channel") == src]:
            dup = copy_element(pr)
            dup.set("channel", copy)
            root.append(dup)
        have.add(copy)
        added += 1
    return added


def new_channel(root: ET.Element, cid: str) -> ET.Element:
    """A <channel> placed after the last one, before every <programme>."""
    ch = ET.Element("channel", id=cid)
    root.insert(len(root.findall("channel")), ch)
    return ch


def copy_element(el: ET.Element) -> ET.Element:
    return ET.fromstring(ET.tostring(el))


def build() -> int:
    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — combined"})
    seen_channel_ids: set[str] = set()
    channel_of: dict[str, ET.Element] = {}

    total_channels = 0
    total_programmes = 0
    files_used = 0

    for path in SOURCE_FILES:
        if not os.path.exists(path):
            warn(f"skip (missing): {path}")
            continue
        try:
            tree = ET.parse(path)
        except Exception as exc:
            warn(f"skip (unparsable): {path} | {exc}")
            continue

        src_root = tree.getroot()
        file_channels = 0
        file_programmes = 0

        mine = set()
        for ch in src_root.findall("channel"):
            cid = ch.get("id")
            if not cid:
                continue
            if cid in seen_channel_ids:
                # The same channel on a second link may carry names the
                # first did not (the playlist's, on Alwan's) — keep them
                # all, so a player matching by name finds it either way.
                kept = channel_of[cid]
                names = {d.text for d in kept.findall("display-name")}
                last = kept.findall("display-name")[-1] if names else None
                for d in ch.findall("display-name"):
                    if d.text and d.text not in names:
                        names.add(d.text)
                        at = list(kept).index(last) + 1 if last is not None else 0
                        kept.insert(at, d)
                        last = d
                continue
            seen_channel_ids.add(cid)
            channel_of[cid] = ch
            mine.add(cid)
            root.append(ch)
            file_channels += 1

        # A channel two links carry (Al Jazeera, on Roya's and on Alwan's)
        # keeps the rows of the file that brought it first, so the merged
        # link never lists one programme twice.
        for pr in src_root.findall("programme"):
            if pr.get("channel") not in mine and pr.get("channel") in seen_channel_ids:
                continue
            root.append(pr)
            file_programmes += 1

        log(f"merged {path}: {file_channels} channels, {file_programmes} programmes")
        total_channels += file_channels
        total_programmes += file_programmes
        files_used += 1

    extras = add_dashboard_extras(root, seen_channel_ids)
    log(f"dashboard channels with no guide of their own: {extras} added")

    log(f"TOTAL: {files_used}/{len(SOURCE_FILES)} source files merged, "
        f"{total_channels} channels, {total_programmes} programmes")

    # Independently-sourced files are already individually validated and use
    # namespaced channel ids, so a cross-file overlap check would just be
    # noise here — skip it and only check structural validity.
    write_xml_atomic(root, OUTPUT, check_overlaps=False,
                      generator_name="Unified MENA EPG — combined")
    return 0



if __name__ == "__main__":
    raise SystemExit(build())
