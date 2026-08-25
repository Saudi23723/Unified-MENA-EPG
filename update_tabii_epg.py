#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tabii Spor — TRT's sports streaming channel.

Primary source — TRT's own broadcast-schedule page, which carries a full
week of EPG inside its Next.js payload:

  https://www.trtspor.com.tr/yayin-akisi/tabii-spor

Each date holds a tvChannels list, and each channel a past / current /
upcoming set of programmes with `starttime` and `endtime` in UTC. It is
TRT's own guide for its own channel.

Secondary source — tvyayinakisi.com, the same Turkish TV-guide site this
repository already reads for beIN Türkiye, which publishes schema.org
BroadcastEvent JSON-LD:

  https://www.tvyayinakisi.com/tabii-spor-yayin-akisi/

It carries the current day only, but names the fixtures ("Nec Nijmegen -
Bodo Glimt") where TRT sometimes gives a generic block. It is used as
filler: an event from it is kept only where TRT scheduled nothing at that
time.

Why this replaces what was here: the previous generator read no schedule
at all. It scraped mentions of matches out of trtspor.com.tr *news*
pages and out of sporekrani.com, and split the results across ten
invented channels. The file it produced held 83 programmes with 6 still
in the future, and three of the ten channels were empty.

Why one channel and not ten: there is no source for "tabii Spor 2" and
up. TRT names exactly one channel, "Tabii Spor" (id 20423462).
tvyayinakisi 404s on tabii-spor-1 through tabii-spor-10 and serves only
the bare tabii-spor slug. The other nine were an artefact of the news
scraping.

No Live badge: neither source marks which broadcasts are live. TRT
publishes an isRepeat flag, which is not the same thing, so nothing here
claims to be live.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import xml.etree.ElementTree as ET

from epg_lib import (
    add_programme, fetch, log, new_session, norm, resolve_overlaps,
    run_main, utc_now, warn, write_xml_atomic,
)

OUTPUT = "tabii_spor_1_10_epg.xml"
UTC = timezone.utc

TRT_URL = "https://www.trtspor.com.tr/yayin-akisi/tabii-spor"
TVY_URL = "https://www.tvyayinakisi.com/tabii-spor-yayin-akisi/"

CHANNEL_ID = "TabiiSpor.tr"
CHANNEL_TR = "tabii Spor"
CHANNEL_AR = "تابي سبور"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG"
        "/main/logos/tabii.png")

# TRT's own id for the channel. The title is matched too, so a re-numbering
# on their side costs nothing.
TABII_CHANNEL_ID = 20423462
TABII_TITLE_RE = re.compile(r"tab(?:i|İ|ı)i?\s*spor", re.I)

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
LD_JSON_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S)

# Keep the file to what a guide can sensibly show.
KEEP_BEHIND = timedelta(days=1)
KEEP_AHEAD = timedelta(days=14)


def parse_utc(value) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.astimezone(UTC) if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def find_epg_days(node, depth: int = 0) -> list[dict]:
    """The list of {date, tvChannels} days, wherever TRT has put it.

    It currently sits at props.pageProps.data.rows[5].content.epg, but the
    row index moves whenever they reorder the page, so the payload is
    searched by shape instead of by path.
    """
    if depth > 14:
        return []
    if isinstance(node, dict):
        days = node.get("epg")
        if (isinstance(days, list) and days
                and all(isinstance(d, dict) and "tvChannels" in d for d in days)):
            return days
        for value in node.values():
            found = find_epg_days(value, depth + 1)
            if found:
                return found
    elif isinstance(node, list):
        for value in node[:80]:
            found = find_epg_days(value, depth + 1)
            if found:
                return found
    return []


def fetch_trt(session) -> list[dict]:
    """Every tabii Spor programme TRT publishes, deduped across days."""
    page = fetch(session, TRT_URL).text
    blob = NEXT_DATA_RE.search(page)
    if not blob:
        warn("TRT: no __NEXT_DATA__ on the page")
        return []
    try:
        payload = json.loads(blob.group(1))
    except Exception as exc:
        warn(f"TRT: payload not JSON: {exc}")
        return []

    days = find_epg_days(payload)
    if not days:
        warn("TRT: no epg days in the payload")
        return []

    seen: dict[tuple, dict] = {}
    for day in days:
        for channel in day.get("tvChannels") or []:
            title = str(channel.get("title") or "")
            if channel.get("id") != TABII_CHANNEL_ID and not TABII_TITLE_RE.search(title):
                continue
            current = channel.get("current")
            shows = list(channel.get("past") or [])
            shows += [current] if isinstance(current, dict) and current else []
            shows += list(channel.get("upcoming") or [])
            for show in shows:
                start = parse_utc(show.get("starttime"))
                stop = parse_utc(show.get("endtime"))
                name = norm(show.get("title"))
                if not start or not stop or stop <= start or not name:
                    continue
                # The same programme appears in one day's `upcoming` and the
                # next day's `past`; keep it once.
                seen[(start, stop, name)] = {
                    "start": start, "stop": stop, "title": name,
                    "desc": norm(show.get("synopsis")),
                }
    log(f"  TRT: {len(seen)} programmes across {len(days)} days")
    return list(seen.values())


def fetch_tvyayinakisi(session) -> list[dict]:
    """The current day from tvyayinakisi, as schema.org BroadcastEvents."""
    page = fetch(session, TVY_URL).text
    out: dict[tuple, dict] = {}
    for block in LD_JSON_RE.findall(page):
        try:
            payload = json.loads(block)
        except Exception:
            continue
        stack = [payload]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                if node.get("@type") in ("BroadcastEvent", "Event"):
                    start = parse_utc(node.get("startDate"))
                    stop = parse_utc(node.get("endDate"))
                    name = norm(node.get("name"))
                    if start and stop and stop > start and name:
                        out[(start, stop, name)] = {
                            "start": start, "stop": stop, "title": name, "desc": "",
                        }
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
    log(f"  tvyayinakisi: {len(out)} programmes")
    return list(out.values())


def build() -> int:
    log("TABII SPOR EPG | TRT's own weekly guide + tvyayinakisi for today")
    session = new_session()

    events: list[dict] = []
    try:
        events = fetch_trt(session)
    except Exception as exc:
        warn(f"TRT fetch failed: {exc}")

    filler: list[dict] = []
    try:
        filler = fetch_tvyayinakisi(session)
    except Exception as exc:
        warn(f"tvyayinakisi fetch failed: {exc}")

    # Filler only where TRT scheduled nothing: TRT is the broadcaster.
    covered = [(e["start"], e["stop"]) for e in events]
    added = 0
    for candidate in filler:
        if any(candidate["start"] < stop and start < candidate["stop"]
               for start, stop in covered):
            continue
        events.append(candidate)
        added += 1
    if added:
        log(f"  tvyayinakisi filled {added} slot(s) TRT left empty")

    now = utc_now()
    events = [e for e in events
              if now - KEEP_BEHIND <= e["stop"] and e["start"] <= now + KEEP_AHEAD]

    if not events:
        # write_xml_atomic keeps the previous file rather than publishing an
        # empty one, so a bad fetch costs nothing.
        write_xml_atomic(ET.Element("tv"), OUTPUT,
                         generator_name="Unified MENA EPG — tabii Spor")
        return 0

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — tabii Spor"})
    channel = ET.SubElement(root, "channel", id=CHANNEL_ID)
    ET.SubElement(channel, "display-name", lang="tr").text = CHANNEL_TR
    ET.SubElement(channel, "display-name", lang="ar").text = CHANNEL_AR
    ET.SubElement(channel, "icon", src=LOGO)

    total = 0
    for ev in resolve_overlaps(events):
        add_programme(root, CHANNEL_ID, ev["start"], ev["stop"], ev["title"],
                      ev.get("desc", ""), category="Spor")
        total += 1

    days = sorted({e["start"].strftime("%Y-%m-%d") for e in events})
    log(f"tabii Spor: {total} programmes over {len(days)} days "
        f"({days[0]} .. {days[-1]})")

    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — tabii Spor")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
