#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STARZPLAY — the three STARZPLAY Sports channels.

Source: STARZPLAY's own public web-EPG API, the endpoint the
starzplay.com guide widget itself calls:

  GET https://epg.aws.playco.com/api/v1.1/epg/category/events/web-epg-scraper-sp

The call is made with category=all and every channel STARZPLAY carries is
then filtered down to the three sports ones by slug, so the roster cannot
drift if STARZPLAY renames a category. Each channel arrives with its
events inline, so one request covers the whole guide.

About the Live badge: the API does send a per-event `status` of
"live" / "upcoming" / "ended", but it is computed on STARZPLAY's side at
the moment of the request — exactly one event per channel is ever "live".
Following it would badge whatever happened to be on air when the file was
generated and nothing else, which goes stale within the hour and marks
nothing you can browse ahead to. Since every event on these three
channels is sport, the badge marks them all and stays correct whenever
the guide is read.
"""

from __future__ import annotations

from datetime import datetime, timezone

import xml.etree.ElementTree as ET

from epg_lib import (
    LIVE_BADGE_PURPLE, add_programme, fetch, log, new_session,
    resolve_overlaps, run_main, utc_now, warn, with_live_badge,
    write_xml_atomic,
)

OUTPUT = "starzplay_epg.xml"
UTC = timezone.utc

API = "https://epg.aws.playco.com/api/v1.1/epg/category/events/web-epg-scraper-sp"

DAYS_BACK = 1
DAYS_FORWARD = 3
PAGE_LIMIT = 40
MAX_PAGES = 15  # hard cap so a runaway API can never hang the job

# The three sports channels, by the slug the API uses. Note the third is
# "starzplaysport1" (singular) while its title is "STARZPLAY Sports 3" —
# that is STARZPLAY's own inconsistency, not a typo here.
WANTED = {
    "starzplaysports1": "ستارز بلاي سبورتس 1",
    "starzplaysports2": "ستارز بلاي سبورتس 2",
    "starzplaysport1": "ستارز بلاي سبورتس 3",
}


def parse_unix(ts) -> datetime | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=UTC)
    except Exception:
        return None


def fetch_all_channels(session, now) -> list[dict]:
    """Walk every page of the API and return the channels it lists."""
    channels: list[dict] = []
    seen: set[str] = set()

    now_ts = int(now.timestamp())
    base = {
        "ts_start": now_ts - DAYS_BACK * 86400,
        "ts_end": now_ts + DAYS_FORWARD * 86400,
        "lang": "ar",
        "pg": 18,
        "category": "all",
        "limit": PAGE_LIMIT,
        "x-geo-country": "SA",
    }

    for page in range(1, MAX_PAGES + 1):
        try:
            data = fetch(session, API, params=dict(base, page=page)).json()
        except Exception as exc:
            warn(f"STARZPLAY page {page} failed: {exc}")
            break

        rows = data.get("data", []) or []
        if not rows:
            break

        new_here = 0
        for ch in rows:
            slug = ch.get("slug")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            channels.append(ch)
            new_here += 1

        log(f"STARZPLAY page {page}: {len(rows)} channels ({new_here} new)")
        if new_here == 0:
            break

    return channels


def channel_logo(ch: dict) -> str | None:
    images = ch.get("images") or []
    png = next((i for i in images if i.get("type") == "logo-png"), None)
    return (png or (images[0] if images else {})).get("url")


def build() -> int:
    log("STARZPLAY SPORTS EPG | official epg.aws.playco.com API | 3 sport channels")
    session = new_session()
    now = utc_now()

    discovered = fetch_all_channels(session, now)
    by_slug = {ch.get("slug"): ch for ch in discovered}
    log(f"STARZPLAY channels discovered: {len(discovered)}")

    missing = [s for s in WANTED if s not in by_slug]
    if missing:
        warn(f"STARZPLAY no longer lists: {', '.join(missing)}")

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — STARZPLAY Sports"})

    prepared = []
    for slug, name in WANTED.items():
        ch = by_slug.get(slug)
        if not ch:
            continue

        events = []
        for ev in ch.get("events", []) or []:
            start = parse_unix(ev.get("tsStart"))
            stop = parse_unix(ev.get("tsEnd"))
            if not start or not stop or stop <= start:
                continue
            images = ev.get("images") or []
            events.append({
                "start": start,
                "stop": stop,
                "title": (ev.get("title") or "").strip() or name,
                "desc": (ev.get("description") or "").strip(),
                "icon": (images[0].get("url") if images else None) or None,
            })

        # STARZPLAY's API has been seen returning overlapping events for one
        # channel, which is invalid XMLTV, so resolve before writing.
        events = resolve_overlaps(events)
        if events:
            prepared.append((slug, name, ch, events))

    for _slug, name, ch, _events in prepared:
        el = ET.SubElement(root, "channel", id=f"Starz_{_slug}")
        ET.SubElement(el, "display-name", lang="ar").text = name
        logo = channel_logo(ch)
        if logo:
            ET.SubElement(el, "icon", src=logo)

    total = 0
    for slug, name, _ch, events in prepared:
        xid = f"Starz_{slug}"
        for ev in events:
            p = add_programme(
                root, xid, ev["start"], ev["stop"],
                with_live_badge(ev["title"], LIVE_BADGE_PURPLE), ev["desc"],
                category="رياضة", icon=ev["icon"],
            )
            ET.SubElement(p, "category", lang="en").text = "Live"
            total += 1

    log(f"STARZPLAY: {len(prepared)}/{len(WANTED)} sport channels, {total} programmes")

    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — STARZPLAY Sports")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
