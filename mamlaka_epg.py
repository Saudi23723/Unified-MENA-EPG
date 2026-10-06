#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Al Mamlaka TV (قناة المملكة) — on the Roya link, beside Amman TV, asked for
by the owner ("لاقي لي EPG ل قناة المملكة").

WHERE THE SCHEDULE IS. The channel's own page, almamlakatv.com/ourprograms
/schedule — "جدول برامج قناة المملكة", a weekly grid, one tab a day from
Saturday to Friday, "بالتوقيت المحلي الأردني (+03:00 GMT)". The site sits
behind Cloudflare's browser check, so a plain request is refused; a real
browser passes it. Every other source was tried first (6 October 2026):
sat.tv is behind the same check, elcinema has no page for the channel,
open-epg and iptv-epg have no Jordan file, and epgshare01's AE1 copies
sat.tv's listing — the same week template, its clock an hour off (it puts
"The 10th With Tarek", العاشرة مع طارق, at 21:00; the channel airs it at
22:00).

THE GRID IS KEPT IN THE REPOSITORY (mamlaka_schedule.json), read by a real
browser once a week (tools/fetch_mamlaka_schedule.py, run by
.github/workflows/update_mamlaka_schedule.yml), and every build lays the
week over the coming days from it — so a pass needs no network at all for
this channel, and a week the site cannot be read keeps the last grid.

A show the site hides (display: none — off the air this season) is left
out, exactly as the page leaves it out.
"""

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from epg_lib import add_programme, log

GRID = "mamlaka_schedule.json"
XMLTV_ID = "AlMamlakaTV.jo"
ARABIC = "قناة المملكة"
# Every way the owner's playlists write it, and the plain names.
NAMES = ("Al Mamlaka", "Al Mamlaka TV", "Al Mamlaka TV HD", "Almamlaka TV",
         "AR: Almamlaka TV 4K", "AR: Almamlaka TV HD", "STC: AL MAMLAKA ᴴᴰ",
         "STC: AL MAMLAKA ʰᵉᵛᶜ", "AT&T: AL MAMLAKA ᴿᴬᵂ", "Jo| Al Mamlaka HD",
         "Al Mamlaka HD", "Mamlaka TV", "المملكة")
# The channel's own mark, from its site (css/frontcss/images/logo.png).
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/al_mamlaka.png")
AMMAN = timezone(timedelta(hours=3))
# The page's tab ids, as it spells them ("wednsday"), by Python weekday.
DAYS = {"monday": 0, "tuesday": 1, "wednsday": 2, "wednesday": 2,
        "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
DAYS_BACK, DAYS_FORWARD = 1, 7
# A gap this short between two shows is the page rounding, not air time
# without a programme: the earlier show runs on to the next.
CLOSE_GAP = timedelta(minutes=10)


def parse_schedule_html(html: str) -> dict[str, list[list[str]]]:
    """{weekday 0-6 as str: [[start "HH:MM", end "HH:MM", title], ...]}."""
    grid: dict[str, list[list[str]]] = {}
    panes = list(re.finditer(r'<div id="(\w+)" data-name="\w+" class="tab-pane[^"]*">', html))
    for i, pane in enumerate(panes):
        day = DAYS.get(pane.group(1).lower())
        if day is None:
            continue
        body = html[pane.end(): panes[i + 1].start() if i + 1 < len(panes) else len(html)]
        rows = []
        for show in re.finditer(r'<div class="show\s*"(?P<attrs>[^>]*)>(?P<inner>.*?)'
                                r'<div class="show-title[^"]*">\s*<span>(?P<title>.*?)</span>',
                                body, re.S):
            if re.search(r"display:\s*none", show.group("attrs")):
                continue
            timing = re.search(r"(\d{1,2}:\d{2})\s*[-–—]\s*(\d{1,2}:\d{2})", show.group("inner"))
            title = re.sub(r"<[^>]+>", "", show.group("title"))
            title = re.sub(r"\s+", " ", title).strip()
            if not timing or not title:
                continue
            # The page writes "end – start" (it reads right to left).
            end, start = timing.group(1), timing.group(2)
            rows.append([start.zfill(5), end.zfill(5), title])
        if rows:
            grid[str(day)] = rows
    return grid


def rows_for(grid: dict, first: datetime, days: int) -> list[dict]:
    """The week grid laid over `days` days from `first` (a date in Amman)."""
    out: list[dict] = []
    for n in range(days):
        day = first + timedelta(days=n)
        shows = grid.get(str(day.weekday()), [])
        # A tab is a broadcast day: it opens in the morning and its last
        # shows (00:05, 01:05 ...) run into the next calendar day.
        opens = shows[0][0] if shows else "00:00"
        for start, end, title in shows:
            sh, sm = map(int, start.split(":"))
            eh, em = map(int, end.split(":"))
            on = day + timedelta(days=1) if start < opens else day
            s = on.replace(hour=sh % 24, minute=sm)
            e = on.replace(hour=eh % 24, minute=em)
            if e <= s:              # runs past midnight
                e += timedelta(days=1)
            out.append({"start": s.astimezone(timezone.utc),
                        "stop": e.astimezone(timezone.utc), "title": title})
    out.sort(key=lambda r: r["start"])
    # One show at a time: an overlap ends the earlier show where the next
    # begins, and a page-rounding gap is closed by the earlier show.
    clean: list[dict] = []
    for row in out:
        if clean and row["start"] < clean[-1]["stop"]:
            clean[-1]["stop"] = row["start"]
            if clean[-1]["stop"] <= clean[-1]["start"]:
                clean.pop()
        if clean and timedelta(0) < row["start"] - clean[-1]["stop"] <= CLOSE_GAP:
            clean[-1]["stop"] = row["start"]
        clean.append(dict(row))
    return [r for r in clean if r["stop"] > r["start"]]


def collect(session=None, previous_path: str = "") -> dict[str, list[dict]]:
    if not os.path.exists(GRID):
        log("  Al Mamlaka: no weekly grid yet")
        return {}
    with open(GRID, encoding="utf-8") as handle:
        grid = json.load(handle).get("week") or {}
    today = datetime.now(AMMAN).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = rows_for(grid, today - timedelta(days=DAYS_BACK), DAYS_BACK + DAYS_FORWARD)
    log(f"  Al Mamlaka{'':20} {len(rows):4} programmes (its own weekly grid)")
    return {XMLTV_ID: rows} if rows else {}


def emit(root: ET.Element, per_channel: dict[str, list[dict]]) -> int:
    rows = per_channel.get(XMLTV_ID) or []
    if not rows:
        return 0
    ch = ET.SubElement(root, "channel", {"id": XMLTV_ID})
    # EXACTLY AS MBC, the channels the owner's player is known to list on
    # this link: a player set to Arabic shows and searches a channel by its
    # FIRST Arabic name, so that is the plain "Al Mamlaka" — then the same
    # under "en", then the Arabic, then every playlist spelling (unlabelled,
    # as MBC's are). "Al Mamlaka TV | قناة المملكة" first, as Amman TV has
    # it, left the owner unable to find it ("قناة المملكة مش موجودة").
    ET.SubElement(ch, "display-name", {"lang": "ar"}).text = NAMES[0]
    ET.SubElement(ch, "display-name", {"lang": "en"}).text = NAMES[0]
    ET.SubElement(ch, "display-name", {"lang": "ar"}).text = ARABIC
    ET.SubElement(ch, "display-name", {"lang": "ar"}).text = "المملكة"
    for name in NAMES[1:]:
        if name != "المملكة":
            ET.SubElement(ch, "display-name").text = name
    if os.path.exists(os.path.join("logos", "al_mamlaka.png")):
        ET.SubElement(ch, "icon", {"src": LOGO})
    for row in rows:
        add_programme(root, XMLTV_ID, row["start"], row["stop"],
                      row["title"], f"{ARABIC} — {row['title']}")
    return len(rows)
