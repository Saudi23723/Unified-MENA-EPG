#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STARZPLAY — sport channels only.

Source: STARZPLAY's own public web-EPG API (the same endpoint the
starzplay.com website widget itself calls):

  GET https://epg.aws.playco.com/api/v1.1/epg/category/events/web-epg-scraper-sp

Paginated; we walk every page until the API returns no more channels. The
API is queried with category=all (so channel discovery still works even
if STARZPLAY's own "sport" category slug ever changes), then every
non-sport channel is filtered out client-side before writing the XML —
this keeps the output small and focused on live sport only.
"""

from __future__ import annotations

from datetime import datetime, timezone

import xml.etree.ElementTree as ET

from epg_lib import (
    add_programme, fetch, log, new_session, resolve_overlaps, run_main,
    utc_now, warn, write_xml_atomic,
)

OUTPUT = "starzplay_epg.xml"
UTC = timezone.utc

API = "https://epg.aws.playco.com/api/v1.1/epg/category/events/web-epg-scraper-sp"

DAYS_BACK = 1
DAYS_FORWARD = 3
PAGE_LIMIT = 40
MAX_PAGES = 15  # hard safety cap so a runaway API can never hang the job


def parse_unix(ts) -> datetime | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=UTC)
    except Exception:
        return None


def is_sport_channel(channel: dict) -> bool:
    hay = " ".join([
        str(channel.get("title") or ""),
        str(channel.get("slug") or ""),
        " ".join(str(c) for c in (channel.get("categories") or [])),
    ]).lower()
    return "sport" in hay


def fetch_all_channels(session, now) -> list[dict]:
    channels: list[dict] = []
    seen_slugs: set[str] = set()

    now_ts = int(now.timestamp())
    params_base = {
        "ts_start": now_ts - DAYS_BACK * 86400,
        "ts_end": now_ts + DAYS_FORWARD * 86400,
        "lang": "ar",
        "pg": 18,
        "category": "all",
        "limit": PAGE_LIMIT,
        "x-geo-country": "SA",
    }

    for page in range(1, MAX_PAGES + 1):
        params = dict(params_base, page=page)
        try:
            r = fetch(session, API, params=params)
            data = r.json()
        except Exception as exc:
            warn(f"STARZPLAY page {page} failed: {exc}")
            break

        rows = data.get("data", []) or []
        if not rows:
            break

        new_this_page = 0
        for ch in rows:
            slug = ch.get("slug")
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            channels.append(ch)
            new_this_page += 1

        log(f"STARZPLAY page {page}: {len(rows)} channels ({new_this_page} new)")
        if new_this_page == 0:
            break

    return channels


def build() -> int:
    log("STARZPLAY EPG | official epg.aws.playco.com API | sport channels only")
    session = new_session()
    now = utc_now()

    all_channels = fetch_all_channels(session, now)
    channels = [ch for ch in all_channels if is_sport_channel(ch)]
    log(f"STARZPLAY channels discovered: {len(all_channels)} total, "
        f"{len(channels)} sport channels kept")

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — STARZPLAY Sport"})

    total = 0
    for ch in channels:
        slug = ch.get("slug")
        xid = f"Starz_{slug}"
        name = (ch.get("title") or slug or "STARZPLAY").strip()

        chan_el = ET.SubElement(root, "channel", id=xid)
        ET.SubElement(chan_el, "display-name", lang="ar").text = name
        images = ch.get("images") or []
        if images:
            logo = next((img for img in images if img.get("type") == "logo-png"), images[0])
            src = logo.get("url")
            if src:
                ET.SubElement(chan_el, "icon", src=src)

        raw_events = []
        for ev in ch.get("events", []) or []:
            start = parse_unix(ev.get("tsStart"))
            stop = parse_unix(ev.get("tsEnd"))
            if not start or not stop or stop <= start:
                continue

            title = (ev.get("title") or "").strip() or name
            desc = (ev.get("description") or "").strip()
            ev_images = ev.get("images") or []
            icon = ev_images[0].get("url") if ev_images and ev_images[0].get("url") else None
            raw_events.append({"start": start, "stop": stop, "title": title, "desc": desc, "icon": icon})

        # STARZPLAY's own API sometimes returns overlapping events for one
        # channel (seen live) — invalid XMLTV, so resolve before writing.
        for ev in resolve_overlaps(raw_events):
            add_programme(
                root, xid, ev["start"], ev["stop"], ev["title"], ev["desc"],
                icon=ev["icon"], live_eligible=True, now=now,
            )
            total += 1

    log(f"STARZPLAY: {total} programmes across {len(channels)} sport channels")

    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — STARZPLAY")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
