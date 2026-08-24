#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
beIN SPORTS Türkiye — full EPG.

Primary source — tvyayinakisi.com, a Turkish TV-guide site that publishes
every channel's schedule as schema.org BroadcastEvent JSON-LD:

  https://www.tvyayinakisi.com/<slug>-yayin-akisi/

Each event carries the programme name and its startDate/endDate complete
with the +03:00 offset, so nothing has to be inferred and there are no CSS
class names to go stale — this is data the site publishes for machines to
read. How far ahead a page reaches varies by channel: HABER currently
carries a full week, most others only the current day.

Secondary source — the Turkish feed of epgshare01.online, already XMLTV:

  https://epgshare01.online/epgshare01/epg_ripper_TR1.xml.gz

It is used strictly as filler: an event from it is kept only where the
Turkish site scheduled nothing for that channel at that time. That covers
beIN SPORTS 4, which tvyayinakisi does not schedule at all, and extends
beIN SPORTS 1/2/3 a few days past the current one.

Why not Digiturk, which this generator used to read: digiturk.com.tr now
answers 403 from its edge gateway (Microsoft-Azure-Application-Gateway) to
every request, the plain human TV-guide page included, so the guide it
produced had eight channels and not one programme.

beIN SPORTS 5 is deliberately absent — neither source publishes a schedule
for it, and a channel with no programmes is worse than no channel at all.

Titles ending in "/ Canlı" are the source's own marker for a live
broadcast; those, and only those, get the Live badge.
"""

from __future__ import annotations

import gzip
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import xml.etree.ElementTree as ET

from epg_lib import (
    add_programme, fetch, log, new_session, norm, resolve_overlaps,
    run_main, utc_now, warn, with_live_badge, write_xml_atomic,
)

OUTPUT = "bein_sports_turkey_epg.xml"
UTC = timezone.utc
ISTANBUL = ZoneInfo("Europe/Istanbul")

TVY_BASE = "https://www.tvyayinakisi.com"
EPGSHARE_URL = "https://epgshare01.online/epgshare01/epg_ripper_TR1.xml.gz"

# Only keep what a TV guide can sensibly show, so a stray far-future or
# long-past event from either source can never bloat the file.
KEEP_BEHIND = timedelta(days=1)
KEEP_AHEAD = timedelta(days=14)

# `share` is the channel id inside the epgshare01 Turkish feed, or None
# where that feed has no entry for the channel.
CHANNELS = [
    {"name": "beIN SPORTS 1",     "slug": "bein-sports-1",     "share": "Beinsports.tr"},
    {"name": "beIN SPORTS 2",     "slug": "bein-sports-2",     "share": "Beinsports.2.tr"},
    {"name": "beIN SPORTS 3",     "slug": "bein-sports-3",     "share": "Beinsports.3.tr"},
    {"name": "beIN SPORTS 4",     "slug": "bein-sports-4",     "share": "Beinsports.4.tr"},
    {"name": "beIN SPORTS MAX 1", "slug": "bein-sports-max-1", "share": None},
    {"name": "beIN SPORTS MAX 2", "slug": "bein-sports-max-2", "share": None},
    {"name": "beIN SPORTS HABER", "slug": "bein-sports-haber", "share": "Bein.Sports.Haber.tr"},
]

LD_JSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
# Turkish for "live". Spelled with either i so an upper-cased title still
# matches — Python's case folding does not map I to the dotless ı.
LIVE_RE = re.compile(r"canl[ıiİI]\b", re.IGNORECASE)
XMLTV_TS_RE = re.compile(r"^(\d{14})(?:\s*([+-]\d{4}))?$")


def slugify_id(name: str) -> str:
    """The channel ids this guide has always used, kept stable so an
    existing TiviMate mapping keeps working."""
    return f"{re.sub(r'[^A-Za-z0-9]+', '', name)}.tr"


def in_window(start: datetime, now: datetime) -> bool:
    return now - KEEP_BEHIND <= start <= now + KEEP_AHEAD


# --------------------------------------------------------------- tvyayinakisi
def broadcast_events(html: str) -> list[dict]:
    """Every schema.org BroadcastEvent on the page, wherever it is nested."""
    found: list[dict] = []
    for block in LD_JSON_RE.findall(html):
        try:
            data = json.loads(block)
        except Exception:
            continue  # one malformed block must not lose the others
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if node.get("@type") == "BroadcastEvent":
                    found.append(node)
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return found


def parse_iso(value) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ISTANBUL)
    return dt.astimezone(UTC)


def fetch_tvy_channel(session, slug: str, now: datetime) -> list[dict]:
    url = f"{TVY_BASE}/{slug}-yayin-akisi/"
    html = fetch(session, url).text

    events: list[dict] = []
    for node in broadcast_events(html):
        title = norm(str(node.get("name") or ""))
        start = parse_iso(node.get("startDate"))
        stop = parse_iso(node.get("endDate"))
        if not title or start is None or stop is None or stop <= start:
            continue
        if not in_window(start, now):
            continue
        events.append({
            "start": start,
            "stop": stop,
            "title": title,
            "live": bool(LIVE_RE.search(title)),
        })
    return events


# ----------------------------------------------------------------- epgshare01
def parse_xmltv_time(value: str | None) -> datetime | None:
    m = XMLTV_TS_RE.match((value or "").strip())
    if not m:
        return None
    try:
        dt = datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
    except ValueError:
        return None
    offset = m.group(2)
    if offset:
        sign = 1 if offset[0] == "+" else -1
        dt = dt.replace(tzinfo=timezone(
            sign * timedelta(hours=int(offset[1:3]), minutes=int(offset[3:5]))
        ))
    else:
        dt = dt.replace(tzinfo=ISTANBUL)
    return dt.astimezone(UTC)


def fetch_epgshare(session, now: datetime) -> dict[str, list[dict]]:
    """The Turkish XMLTV feed, keyed by its own channel ids. Never raises —
    it is only filler, so a failure here must not cost us the main source."""
    per: dict[str, list[dict]] = defaultdict(list)
    try:
        raw = fetch(session, EPGSHARE_URL).content
        text = gzip.decompress(raw).decode("utf-8", "replace")
        root = ET.fromstring(text)
    except Exception as exc:
        warn(f"epgshare01 Turkish feed unavailable, continuing without filler: {exc}")
        return {}

    for pr in root.findall("programme"):
        cid = pr.get("channel")
        start = parse_xmltv_time(pr.get("start"))
        stop = parse_xmltv_time(pr.get("stop"))
        if not cid or start is None or stop is None or stop <= start:
            continue
        if not in_window(start, now):
            continue
        title_el = pr.find("title")
        title = norm(title_el.text or "") if title_el is not None else ""
        if not title:
            continue
        per[cid].append({
            "start": start,
            "stop": stop,
            "title": title,
            "live": bool(LIVE_RE.search(title)),
        })
    return dict(per)


# ---------------------------------------------------------------------- merge
def merge_events(primary: list[dict], filler: list[dict]) -> list[dict]:
    """Primary wins outright; a filler event survives only if it occupies
    time the primary source left empty."""
    kept = resolve_overlaps(primary)
    spans = [(e["start"], e["stop"]) for e in kept]

    extra = [
        ev for ev in filler
        if not any(ev["start"] < end and begin < ev["stop"] for begin, end in spans)
    ]
    return resolve_overlaps(kept + extra)


def build() -> int:
    log("beIN SPORTS TÜRKİYE EPG | tvyayinakisi.com BroadcastEvent JSON-LD, epgshare01 TR as filler")
    session = new_session()
    now = utc_now()

    share = fetch_epgshare(session, now)
    if share:
        log(f"epgshare01 filler loaded: {len(share)} channels")

    per_channel: dict[str, list[dict]] = {}
    for ch in CHANNELS:
        name, slug = ch["name"], ch["slug"]
        try:
            primary = fetch_tvy_channel(session, slug, now)
        except Exception as exc:
            warn(f"{name}: tvyayinakisi unavailable ({exc}) — falling back to filler only")
            primary = []

        filler = share.get(ch["share"] or "", [])
        merged = merge_events(primary, filler)
        per_channel[name] = merged
        log(f"  {name:20} tvyayinakisi={len(primary):4} filler={len(filler):4} -> {len(merged):4}")

    total = sum(len(v) for v in per_channel.values())
    with_data = [c for c in CHANNELS if per_channel.get(c["name"])]

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — beIN Sports Türkiye"})
    for ch in with_data:
        el = ET.SubElement(root, "channel", id=slugify_id(ch["name"]))
        ET.SubElement(el, "display-name", lang="tr").text = ch["name"]

    live_badges = 0
    for ch in with_data:
        xid = slugify_id(ch["name"])
        for ev in per_channel[ch["name"]]:
            title = ev["title"]
            if ev["live"]:
                title = with_live_badge(title)
                live_badges += 1
            add_programme(
                root, xid, ev["start"], ev["stop"], title,
                category="Sports",
            )

    log(
        f"beIN Türkiye: {len(with_data)}/{len(CHANNELS)} channels with data, "
        f"{total} programmes, {live_badges} marked live"
    )

    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — beIN Sports Türkiye")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
