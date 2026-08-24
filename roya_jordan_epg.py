#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Jordan — general-programming channels EPG.

Two independent official sources feed this file:

  1) Roya TV / Roya News / Roya Sport / etc. — Roya's own backend API (the
     same API roya.tv's website widget calls to render its schedule):

       GET https://backend.roya.tv/api/v01/channels/schedule-pagination?day_number=N

     `day_number` is an offset from today (UTC day, 0 = today). Each
     response carries every Roya-group channel's full-day programme list
     (title, description, thumbnail, unix start/stop).

  2) Jordan TV (الأردني), Al Mamlaka (المملكة), Amman TV (عمان) and a few
     smaller Jordanian channels — sat.tv's own public schedule API (a
     WordPress AJAX endpoint used by the sat.tv TV-guide website), which
     republishes real satellite-lineup schedules:

       POST https://www.sat.tv/wp-content/themes/twentytwenty-child/ajax_chaines.php

     Channel identity here is a fixed (satellite, lineup, channel-name)
     triple confirmed from sat.tv's own listings; no data is invented.

Nothing here is invented — every field comes straight from these two
official APIs.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from epg_lib import (
    add_programme, fetch, log, new_session, norm, resolve_overlaps, run_main,
    utc_now, warn, write_xml_atomic,
)

OUTPUT = "roya_jordan_epg.xml"
UTC = timezone.utc
LONDON = ZoneInfo("Europe/London")  # sat.tv renders schedule times in this tz

API = "https://backend.roya.tv/api/v01/channels/schedule-pagination"

DAYS_BACK = 1
DAYS_FORWARD = 6

# ---------------------------------------------------------------------------
# sat.tv — Jordan TV / Al Mamlaka / Amman TV / smaller Jordanian channels
# ---------------------------------------------------------------------------

SAT_TV_API = "https://www.sat.tv/wp-content/themes/twentytwenty-child/ajax_chaines.php"

# (satellite, lineup) -> confirmed real Jordanian channel names on that
# sat.tv lineup (from sat.tv's own published listings). Roya TV is
# deliberately excluded here — it's already covered by the official Roya
# API above, and duplicating it from a second source risks disagreeing
# schedules for the same channel.
SAT_TV_JORDAN_LINEUPS: dict[tuple[int, int], list[str]] = {
    (1, 38): ["الأردني تي في", "المملكة تي في", "عمان تي في"],
    (1, 33): ["Alerth Alnabawi", "Azhari TV", "Kaifa TV", "Karameesh"],
}

SAT_TV_DISPLAY_NAMES = {
    "الأردني تي في": "Jordan TV",
    "المملكة تي في": "Al Mamlaka TV",
    "عمان تي في": "Amman TV",
    "Alerth Alnabawi": "Alerth Alnabawi",
    "Azhari TV": "Azhari TV",
    "Kaifa TV": "Kaifa TV",
    "Karameesh": "Karameesh",
}

TIME_RE = re.compile(r"(\d{2}:\d{2})")
DURATION_RE = re.compile(r"(\d{2})h(\d{2})")


def sat_tv_slugify_id(name: str) -> str:
    n = "".join(ch for ch in name if ch.isascii() and ch.isalnum())
    return f"JO_{n}"


SAT_TV_XID_TO_NAME = {
    sat_tv_slugify_id(display): display for display in SAT_TV_DISPLAY_NAMES.values()
}


def fetch_sat_tv_lineup_day(session, satellite: int, lineup: int, day: datetime) -> str:
    form = {
        "dateFiltre": day.strftime("%Y-%m-%d"),
        "hoursFiltre": "0",
        "satLineup": str(lineup),
        "satSatellite": str(satellite),
        "userDateTime": str(int(day.timestamp() * 1000)),
        "userTimezone": "Europe/London",
    }
    r = fetch(
        session, SAT_TV_API, method="POST", data=form,
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Cookie": "pll_language=ar",
        },
    )
    return r.text


def parse_sat_tv_lineup(html: str, channel_names: list[str], day: datetime) -> dict[str, list[dict]]:
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, list[dict]] = {name: [] for name in channel_names}

    for block in soup.select(".main-container-channels-events > .container-channel-events"):
        title_el = block.select_one(".channel-title")
        if not title_el:
            continue
        name = norm(title_el.get_text(" ", strip=True))
        if name not in out:
            continue

        for ev in block.select(".container-event"):
            date_el = ev.select_one(".event-data-date")
            info_el = ev.select_one(".event-data-info")
            title_el2 = ev.select_one(".event-data-title")
            if not date_el or not title_el2:
                continue

            tm = TIME_RE.search(date_el.get_text(" ", strip=True))
            if not tm:
                continue
            hh, mm = map(int, tm.group(1).split(":"))

            duration_min = 0
            if info_el:
                dm = DURATION_RE.search(info_el.get_text(" ", strip=True))
                if dm:
                    duration_min = int(dm.group(1)) * 60 + int(dm.group(2))
            if duration_min <= 0:
                duration_min = 30  # sat.tv sometimes omits duration; keep non-zero

            title = norm(title_el2.get_text(" ", strip=True))
            if not title:
                continue
            desc_el = ev.select_one(".event-data-desc")
            desc = norm(desc_el.get_text(" ", strip=True)) if desc_el else ""
            img_el = ev.select_one(".event-logo img")
            icon = None
            if img_el and img_el.get("src") and "no-img" not in (img_el.get("class") or []):
                src = img_el["src"]
                icon = src if src.startswith("http") else f"https://sat.tv{src}"

            local = datetime(day.year, day.month, day.day, hh, mm, tzinfo=LONDON)
            start_utc = local.astimezone(UTC)
            stop_utc = start_utc + timedelta(minutes=duration_min)

            out[name].append({
                "start": start_utc, "stop": stop_utc, "title": title,
                "desc": desc, "icon": icon,
            })

    return out


def collect_sat_tv_jordan(session, now: datetime) -> dict[str, list[dict]]:
    """xmltv_id -> events, for the confirmed Jordanian sat.tv channels."""
    results: dict[str, list[dict]] = {}
    today = now.astimezone(LONDON).replace(hour=0, minute=0, second=0, microsecond=0)

    for (satellite, lineup), names in SAT_TV_JORDAN_LINEUPS.items():
        ok_days = 0
        by_name: dict[str, list[dict]] = {n: [] for n in names}

        for offset in range(-DAYS_BACK, DAYS_FORWARD + 1):
            day = today + timedelta(days=offset)
            try:
                html = fetch_sat_tv_lineup_day(session, satellite, lineup, day)
                parsed = parse_sat_tv_lineup(html, names, day)
            except Exception as exc:
                warn(f"sat.tv lineup {satellite}#{lineup} day {day.date()} failed: {exc}")
                continue
            got_any = False
            for name, events in parsed.items():
                if events:
                    got_any = True
                by_name[name].extend(events)
            if got_any:
                ok_days += 1

        log(f"sat.tv lineup {satellite}#{lineup}: {ok_days} days OK -> "
            f"{[(n, len(e)) for n, e in by_name.items()]}")

        for name, events in by_name.items():
            xid = sat_tv_slugify_id(SAT_TV_DISPLAY_NAMES.get(name, name))
            results[xid] = events

    return results


def slugify_id(name: str, site_id: str = "") -> str:
    """ASCII-only id (XMLTV/TiviMate channel ids are conventionally ASCII)."""
    n = "".join(ch for ch in name if ch.isascii() and ch.isalnum())
    return f"Roya_{n}" if n else f"Roya_Ch{site_id}"


def discover_channels(session) -> dict[str, dict]:
    """channel_site_id -> {xmltv_id, name}"""
    r = fetch(session, API, params={"day_number": 0})
    data = r.json()
    days = data.get("data", []) or []
    if not days:
        raise ValueError("empty channel-discovery response")

    channels: dict[str, dict] = {}
    for ch in days[0].get("channel", []) or []:
        site_id = ch.get("id")
        name = (ch.get("title") or "").strip()
        if site_id is None or not name:
            continue
        channels[str(site_id)] = {"xmltv_id": slugify_id(name, str(site_id)), "name": name}

    if not channels:
        raise ValueError("no channels discovered")
    return channels


def fetch_day(session, day_number: int) -> list[dict]:
    r = fetch(session, API, params={"day_number": day_number})
    data = r.json()
    return data.get("data", []) or []


def build() -> int:
    log("JORDAN CHANNELS EPG | Roya official API + sat.tv (Jordan TV/Al Mamlaka/Amman TV/etc.)")
    session = new_session()
    now = utc_now()

    try:
        channels = discover_channels(session)
        log(f"Roya channels discovered: {len(channels)} -> {[c['name'] for c in channels.values()]}")
    except Exception as exc:
        warn(f"Roya channel discovery failed entirely: {exc}")
        channels = {}

    sat_tv_events = collect_sat_tv_jordan(session, now)

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — Jordan"})
    for site_id, meta in channels.items():
        ch = ET.SubElement(root, "channel", id=meta["xmltv_id"])
        ET.SubElement(ch, "display-name", lang="ar").text = meta["name"]
    for xid in sat_tv_events:
        ch = ET.SubElement(root, "channel", id=xid)
        ET.SubElement(ch, "display-name", lang="en").text = SAT_TV_XID_TO_NAME.get(xid, xid)

    total = 0
    ok_days = 0

    for offset in range(-DAYS_BACK, DAYS_FORWARD + 1):
        try:
            days = fetch_day(session, offset)
        except Exception as exc:
            warn(f"Roya day_number={offset} fetch failed: {exc}")
            continue

        if not days:
            continue
        ok_days += 1

        for day_entry in days:
            for ch_entry in day_entry.get("channel", []) or []:
                site_id = str(ch_entry.get("id"))
                meta = channels.get(site_id)
                if not meta:
                    continue
                for prog in ch_entry.get("programs", []) or []:
                    try:
                        start_ts = prog.get("start_timestamp")
                        end_ts = prog.get("end_timestamp")
                        if start_ts is None or end_ts is None:
                            continue
                        start = datetime.fromtimestamp(int(start_ts), tz=UTC)
                        stop = datetime.fromtimestamp(int(end_ts), tz=UTC)
                    except Exception:
                        continue
                    if stop <= start:
                        continue
                    title = (prog.get("name") or "").strip()
                    if not title:
                        continue
                    desc = (prog.get("description") or "").strip()
                    icon = prog.get("thumbnail_web") or None

                    add_programme(
                        root, meta["xmltv_id"], start, stop, title, desc,
                        icon=icon, live_eligible=True, now=now,
                    )
                    total += 1

    log(f"Roya: {ok_days}/{DAYS_BACK + DAYS_FORWARD + 1} days fetched OK, {total} programmes total")

    sat_tv_total = 0
    for xid, events in sat_tv_events.items():
        for ev in resolve_overlaps(events):
            add_programme(
                root, xid, ev["start"], ev["stop"], ev["title"], ev["desc"],
                icon=ev["icon"], live_eligible=True, now=now,
            )
            sat_tv_total += 1
            total += 1
    log(f"sat.tv Jordan channels: {sat_tv_total} programmes total")

    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — Jordan")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
