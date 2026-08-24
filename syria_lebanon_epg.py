#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Syrian & Lebanese general channels — official EPG via Shahid (MBC).

Shahid (shahid.mbc.net / api2.shahid.net) is a real regional streaming
platform that republishes a number of free-to-air Arab channels' live
schedules through its own public API — including Syria's public channel
(السورية / Al-Souriya TV) and MTV Lebanon. This script:

  1) discovers every live-channel Shahid currently republishes
     (GET /v2.1/product/filter, productSubType=LIVE_CHANNEL), then
  2) keeps only the ones whose name is clearly Syrian or Lebanese, and
  3) pulls each one's real schedule (GET /v2.1/shahid-epg-api/).

Known-good channel IDs are also kept as a hardcoded fallback so this still
works even if the discovery call is ever rate-limited or changes shape.

Honesty note: no public schedule API could be found for LBCI, OTV, Tele
Liban, Al Jadeed, or Syria TV (Fadaat) — this script does not invent data
for them, so they are not included. If a public source for those is ever
found, add it here rather than guessing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import xml.etree.ElementTree as ET

from epg_lib import add_programme, fetch, log, new_session, run_main, utc_now, warn, write_xml_atomic

OUTPUT = "syria_lebanon_epg.xml"
UTC = timezone.utc

DISCOVER_URL = "https://api2.shahid.net/proxy/v2.1/product/filter"
SCHEDULE_URL = "https://api2.shahid.net/proxy/v2.1/shahid-epg-api/"

DISCOVER_COUNTRIES = ["SA", "EG", "US"]

# Last-known-good roster (site_id is Shahid's stable internal channel id).
FALLBACK_CHANNELS = {
    "49923775805582": {"xmltv_id": "AlSouriyaTV.sy", "name": "السورية", "name_en": "Al-Souriya TV (Syria)"},
    "49923518527492": {"xmltv_id": "MTVLebanon.lb", "name": "MTV Lebanon", "name_en": "MTV Lebanon"},
}

SYRIA_MARKERS = ("سوري", "syria", "souriya")
LEBANON_MARKERS = ("لبنان", "lebanon", "lbc", "otv", "mtv", "جديد", "تلفزيون لبنان", "tele liban")


def looks_syrian_or_lebanese(name: str) -> bool:
    low = (name or "").casefold()
    return any(m in low for m in SYRIA_MARKERS) or any(m in low for m in LEBANON_MARKERS)


def slugify_id(name: str, site_id: str = "") -> str:
    """ASCII-only id (XMLTV/TiviMate channel ids are conventionally ASCII)."""
    n = "".join(ch for ch in name if ch.isascii() and ch.isalnum())
    return n or f"ShahidCh{site_id}"


def discover_channels(session) -> dict[str, dict]:
    channels: dict[str, dict] = {}
    for country in DISCOVER_COUNTRIES:
        page = 0
        while True:
            filt = (
                f'{{"pageNumber":{page},"pageSize":100,'
                f'"productType":"LIVESTREAM","productSubType":"LIVE_CHANNEL"}}'
            )
            try:
                r = fetch(
                    session, DISCOVER_URL,
                    params={
                        "filter": filt,
                        "country": country,
                        "language": "ar",
                        "Accept-Language": "ar",
                    },
                )
                data = r.json()
            except Exception as exc:
                warn(f"Shahid discovery failed (country={country}, page={page}): {exc}")
                break

            product_list = data.get("productList") or {}
            products = product_list.get("products") or []
            for p in products:
                site_id = str(p.get("id") or "")
                name = (p.get("title") or "").strip()
                if not site_id or not name:
                    continue
                if not looks_syrian_or_lebanese(name):
                    continue
                channels[site_id] = {"xmltv_id": slugify_id(name, site_id), "name": name, "name_en": name}

            if not product_list.get("hasMore"):
                break
            page += 1
            if page > 20:  # hard safety cap
                break

    return channels


def fetch_schedule(session, site_id: str, day: datetime) -> list[dict]:
    day_str = day.strftime("%Y-%m-%d")
    r = fetch(
        session, SCHEDULE_URL,
        params={
            "csvChannelIds": site_id,
            "from": f"{day_str}T00:00:00.000Z",
            "to": f"{day_str}T23:59:59.999Z",
            "country": "SA",
            "language": "ar",
            "Accept-Language": "ar",
        },
    )
    data = r.json()
    events: list[dict] = []
    for schedule in data.get("items", []) or []:
        if str(schedule.get("channelId")) != site_id:
            continue
        for item in schedule.get("items", []) or []:
            try:
                start = datetime.fromisoformat(item["actualFrom"].replace("Z", "+00:00"))
                stop = datetime.fromisoformat(item["actualTo"].replace("Z", "+00:00"))
            except Exception:
                continue
            if stop <= start:
                continue
            title = (item.get("title") or "").strip()
            if not title:
                continue
            desc = (item.get("description") or "").strip()
            icon = item.get("productPoster") or None
            events.append({
                "start": start.astimezone(UTC), "stop": stop.astimezone(UTC),
                "title": title, "desc": desc, "icon": icon,
            })
    return events


def build() -> int:
    log("SYRIA & LEBANON CHANNELS EPG | official Shahid (MBC) API | discovers real channels, no invented schedules")
    session = new_session()
    now = utc_now()

    channels = dict(FALLBACK_CHANNELS)
    try:
        discovered = discover_channels(session)
        new_count = 0
        for site_id, meta in discovered.items():
            if site_id not in channels:
                new_count += 1
            channels[site_id] = meta
        log(f"Shahid discovery OK: {len(discovered)} SY/LB channels found ({new_count} new vs fallback)")
    except Exception as exc:
        warn(f"Shahid discovery failed entirely, using fallback roster only: {exc}")

    log(f"Total channels: {len(channels)} -> {[c['name'] for c in channels.values()]}")

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — Syria & Lebanon"})
    for site_id, meta in channels.items():
        ch = ET.SubElement(root, "channel", id=meta["xmltv_id"])
        ET.SubElement(ch, "display-name", lang="ar").text = meta["name"]
        if meta["name_en"] != meta["name"]:
            ET.SubElement(ch, "display-name", lang="en").text = meta["name_en"]

    total = 0
    for offset in range(-1, 6):
        day = (now + timedelta(days=offset)).replace(hour=0, minute=0, second=0, microsecond=0)
        for site_id, meta in channels.items():
            try:
                events = fetch_schedule(session, site_id, day)
            except Exception as exc:
                warn(f"{meta['name']} schedule fetch failed for {day.date()}: {exc}")
                continue
            for ev in events:
                add_programme(
                    root, meta["xmltv_id"], ev["start"], ev["stop"], ev["title"], ev["desc"],
                    icon=ev["icon"], live_eligible=True, now=now,
                )
                total += 1

    log(f"Syria/Lebanon: {total} programmes total across {len(channels)} channels")

    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — Syria & Lebanon")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
