#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STARZPLAY — every sport channel STARZPLAY carries.

Source: STARZPLAY's own public web-EPG API, the endpoint the
starzplay.com guide widget itself calls:

  GET https://epg.aws.playco.com/api/v1.1/epg/category/events/web-epg-scraper-sp

The call is made with category=all and the sport channels are then picked
out by STARZPLAY's own classification — a channel counts when its genres
include "Sports" or its category is "sports". Nothing is matched by a
hand-written list of slugs, so a channel added or renamed upstream is
picked up on the next run rather than silently missed. That currently
yields 20 channels, among them AD Sports 1 and 2, AD Sports Premium 2,
AD Sports Extra, Yas TV and AD Fight alongside the STARZPLAY-branded ones.

Names and logos come from the API too, never invented here: an earlier
version of this file called starzplaysports2 "ستارز بلاي سبورتس 2" when
STARZPLAY itself titles it "أبوظبي الرياضية بريميوم 2 - الدوري الإيطالي".

The API answers in whichever language is asked for, so it is called twice
— once with lang=en and once with lang=ar — and both are written: English
as the shown title and channel name, Arabic alongside it. The two runs
return the same events, so they pair exactly on channel and start time.

No Live badge here. The API does send a per-event `status` of
"live" / "upcoming" / "ended", but it is computed on STARZPLAY's side at
the moment of the request — exactly one event per channel is ever "live" —
so following it would badge whatever happened to be on air when the file
was generated and nothing else, going stale within the hour.

An earlier version badged every event instead, on the grounds that these
channels carry nothing but sport. That is true and still useless: a marker
on all 1487 programmes distinguishes nothing, and it devalues the badge on
the guides that do carry a real live flag. Nothing here is marked live
unless the source says which broadcasts are.
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
MAX_PAGES = 15  # hard cap so a runaway API can never hang the job

def is_sport(channel: dict) -> bool:
    """STARZPLAY's own verdict, not a guess from the title."""
    genres = {str(g).strip().lower() for g in (channel.get("genres") or [])}
    category = str(channel.get("category") or "").strip().lower()
    return "sports" in genres or category == "sports"


def parse_unix(ts) -> datetime | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=UTC)
    except Exception:
        return None


def fetch_all_channels(session, now, lang: str = "en") -> list[dict]:
    """Walk every page of the API and return the channels it lists."""
    channels: list[dict] = []
    seen: set[str] = set()

    now_ts = int(now.timestamp())
    base = {
        "ts_start": now_ts - DAYS_BACK * 86400,
        "ts_end": now_ts + DAYS_FORWARD * 86400,
        "lang": lang,
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

        log(f"STARZPLAY[{lang}] page {page}: {len(rows)} channels ({new_here} new)")
        if new_here == 0:
            break

    return channels


def channel_logo(ch: dict) -> str | None:
    images = ch.get("images") or []
    png = next((i for i in images if i.get("type") == "logo-png"), None)
    return (png or (images[0] if images else {})).get("url")


def build() -> int:
    log("STARZPLAY SPORTS EPG | official epg.aws.playco.com API | sport channels")
    session = new_session()
    now = utc_now()

    discovered = fetch_all_channels(session, now, lang="en")
    log(f"STARZPLAY channels discovered: {len(discovered)}")

    # The Arabic pass is a bonus: if it fails the guide is still complete in
    # English, just without the Arabic titles alongside.
    arabic_names: dict[str, str] = {}
    arabic_titles: dict[tuple[str, int], str] = {}
    try:
        for ch in fetch_all_channels(session, now, lang="ar"):
            slug = ch.get("slug")
            if not slug:
                continue
            arabic_names[slug] = (ch.get("title") or "").strip()
            for ev in ch.get("events", []) or []:
                ts = ev.get("tsStart")
                if ts is not None:
                    arabic_titles[(slug, int(ts))] = (ev.get("title") or "").strip()
        log(f"Arabic pass: {len(arabic_names)} channel names, "
            f"{len(arabic_titles)} event titles")
    except Exception as exc:
        warn(f"Arabic pass failed, continuing in English only: {exc}")

    sport = [ch for ch in discovered if is_sport(ch)]
    log(f"Sport by STARZPLAY's own classification: {len(sport)}")

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — STARZPLAY Sports"})

    prepared = []
    for ch in sport:
        slug = ch.get("slug")
        if not slug:
            continue
        name = (ch.get("title") or "").strip() or slug

        events = []
        for ev in ch.get("events", []) or []:
            start = parse_unix(ev.get("tsStart"))
            stop = parse_unix(ev.get("tsEnd"))
            if not start or not stop or stop <= start:
                continue
            images = ev.get("images") or []
            ts = ev.get("tsStart")
            events.append({
                "start": start,
                "stop": stop,
                "title": (ev.get("title") or "").strip() or name,
                "title_ar": arabic_titles.get((slug, int(ts))) if ts is not None else None,
                "desc": (ev.get("description") or "").strip(),
                "icon": (images[0].get("url") if images else None) or None,
            })

        # STARZPLAY's API has been seen returning overlapping events for one
        # channel, which is invalid XMLTV, so resolve before writing.
        events = resolve_overlaps(events)
        if events:
            prepared.append((slug, name, ch, events))

    for slug, name, ch, _events in prepared:
        el = ET.SubElement(root, "channel", id=f"Starz_{slug}")
        # English first: a player shows the first display-name it can use.
        ET.SubElement(el, "display-name", lang="en").text = name
        ar_name = arabic_names.get(slug)
        if ar_name and ar_name != name:
            ET.SubElement(el, "display-name", lang="ar").text = ar_name
        logo = channel_logo(ch)
        if logo:
            ET.SubElement(el, "icon", src=logo)

    total = paired = 0
    for slug, _name, _ch, events in prepared:
        xid = f"Starz_{slug}"
        for ev in events:
            alts = [("ar", ev["title_ar"])] if ev["title_ar"] else []
            if alts:
                paired += 1
            add_programme(
                root, xid, ev["start"], ev["stop"], ev["title"], ev["desc"],
                category="Sport", icon=ev["icon"], alt_titles=alts,
            )
            total += 1

    icons = sum(1 for c in root.findall("channel") if c.find("icon") is not None)
    log(f"STARZPLAY: {len(prepared)} sport channels, {total} programmes, "
        f"{icons} logos, {paired} with an Arabic title alongside")

    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — STARZPLAY Sports")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
