#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Al Mashhad (المشهد) — its schedule from its own site, on the Roya link.

Asked for from a photo of the player: the channel sat on "No
information". almashhad.com/live/ shows the day's schedule under the
player, and the page reads it from the channel's own API:

    https://api.almashhad.tv/api/epg/shows?date=YYYY-MM-DD&timezone=UTC
        &page=N&limit=20

— every show with its name, description, length and a start time that
carries its own offset (asked for in UTC, answered in UTC; asked for in
Amman's zone, the same rows come back at +03:00). It publishes about
three days ahead; a day it has not published yet answers with no items,
and is simply left for a later run.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from epg_lib import add_programme, fetch, log, warn

API = "https://api.almashhad.tv/api/epg/shows"
HEADERS = {"Origin": "https://www.almashhad.com",
           "Referer": "https://www.almashhad.com/live/"}
PAGE_SIZE = 20          # the API refuses more
DAYS_BACK = 1
DAYS_FORWARD = 6
XMLTV_ID = "AlMashhad.ae"
NAMES = ("Al Mashhad", "Al Mashhad HD", "AlMashhad", "Almashhad TV",
         "Al Mashhad TV", "AR| Al Mashhad", "Al Mashhad News")
ARABIC = "المشهد"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/almashhad.png")


def length(raw: str) -> timedelta | None:
    m = re.fullmatch(r"(\d+):(\d{2}):(\d{2})", (raw or "").strip())
    if not m:
        return None
    h, mi, s = map(int, m.groups())
    return timedelta(hours=h, minutes=mi, seconds=s)


def read_day(session, day: str) -> list[dict]:
    rows, page, pages = [], 1, 1
    while page <= pages:
        data = fetch(session, API, headers=HEADERS, timeout=30, params={
            "date": day, "timezone": "UTC", "page": page,
            "limit": PAGE_SIZE}).json()
        result = (data.get("data") or {}).get("result") or {}
        pages = int(result.get("totalPages") or 0)
        for item in result.get("items") or []:
            try:
                start = datetime.fromisoformat(
                    item["ShowDateTime"]).astimezone(timezone.utc)
            except (KeyError, TypeError, ValueError):
                continue
            span = length(item.get("Duration"))
            title = re.sub(r"\s+", " ", item.get("ShowName") or "").strip()
            if not title or not span:
                continue
            rows.append({"start": start, "stop": start + span, "title": title,
                         "desc": re.sub(r"\s+", " ",
                                        item.get("ShortDescription") or "")
                         .strip()})
        page += 1
    return rows


def collect(session, previous_path: str = "") -> dict[str, list[dict]]:
    today = datetime.now(timezone.utc).date()
    rows: dict[datetime, dict] = {}
    for n in range(-DAYS_BACK, DAYS_FORWARD + 1):
        day = (today + timedelta(days=n)).isoformat()
        try:
            for r in read_day(session, day):
                rows[r["start"]] = r
        except Exception as exc:
            warn(f"Al Mashhad: {day} unreadable ({exc})")
    ordered = sorted(rows.values(), key=lambda r: r["start"])
    # A row never runs over the next one's start.
    for a, b in zip(ordered, ordered[1:]):
        if b["start"] < a["stop"]:
            a["stop"] = b["start"]
    ordered = [r for r in ordered if r["stop"] > r["start"]]
    if not ordered:
        warn("Al Mashhad: its API returned nothing this run")
        return {}
    log(f"  Al Mashhad{'':20} {len(ordered):4} programmes (api.almashhad.tv)")
    return {XMLTV_ID: ordered}


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
                      row["title"], row["desc"])
    return len(rows)
