#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Jordan — Roya TV / Roya News / Roya Sport / Roya Comedy / Roya Kitchen /
Roya Kids / رؤيا فلسطين / إنتاجات رؤيا / كرفان / قناة الشرقية,
plus الجديد (Al Jadeed, Lebanon) and الجزيرة (Al Jazeera).

Those two ride in this file rather than getting links of their own. Each
has its own reader — aljadeed_epg.py and aljazeera_epg.py — which knows
its source and its clock; this generator calls them and writes their
channels alongside Roya's, so they arrive on a link that is already in
use. Because two workflows must never write one file, neither has a
workflow of its own; both refresh on this one's half-hourly run. Both are
read after the Roya channels, so a failure abroad can never cost the
Jordanian channels their guide, and both carry their own rows forward from
the file they are about to replace rather than vanishing when a source is
unreachable.

Source: Roya's own backend API (the same API roya.tv's website widget
calls to render its schedule):

  GET https://backend.roya.tv/api/v01/channels/schedule-pagination?day_number=N

`day_number` is an offset from today (UTC day, 0 = today). Each response
carries every Roya-group channel's full-day programme list (title,
description, thumbnail, unix start/stop). Nothing here is invented —
every field comes straight from that API.

Honesty note: Jordan TV (الأردني), Al Mamlaka (المملكة), Amman TV (عمان)
and other non-Roya Jordanian channels are deliberately NOT included here.
sat.tv (a general Arab satellite TV-guide site) does list them, but its
schedule endpoint sits behind Cloudflare's managed bot challenge — every
request, even from GitHub Actions' real IP, gets a 403 "Just a moment..."
JS challenge page instead of data. That can't be solved with a plain HTTP
request (it needs a real browser), so rather than ship channels that would
always be empty, they're left out until a real public source is found.
"""

from __future__ import annotations

from datetime import datetime, timezone

import xml.etree.ElementTree as ET

from epg_lib import (
    add_programme, fetch, log, new_session, run_main, warn,
    write_xml_atomic,
)

import aljadeed_epg
import aljazeera_epg

OUTPUT = "roya_jordan_epg.xml"
UTC = timezone.utc

LOGO_BASE = "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/logos"

# Roya publishes a mark for only some of its channels. Anything not listed
# here falls back to the network mark in build(), so no channel is blank.
ROYA_LOGO_KEYS = {
    "Roya_RoyaTV": "roya_tv",
    "Roya_RoyaNews": "roya_news",
    "Roya_RoyaComedy": "roya_comedy",
    "Roya_RoyaKitchen": "roya_kitchen",
    "Roya_RoyaKids": "roya_kids",
}

API = "https://backend.roya.tv/api/v01/channels/schedule-pagination"

DAYS_BACK = 1
DAYS_FORWARD = 6

# No Live badge on any Roya channel. Roya publishes no live marker of any
# kind, so the only badge possible here would be "this was on air when the
# workflow ran", read off the clock — which put Live on a cooking show and
# a comedy rerun, and went stale minutes later either way. Guessing from
# the title was tried and dropped too: on a channel whose sport line-up is
# a repeated competition block rather than named fixtures, there is nothing
# solid to guess from. The Live badge belongs on الأردن الرياضية, which has
# real fixtures to put it on.


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
    log("JORDAN — ROYA TV EPG | official backend.roya.tv API | full daily schedule")
    session = new_session()

    channels = discover_channels(session)
    log(f"Roya channels discovered: {len(channels)} -> {[c['name'] for c in channels.values()]}")

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — Jordan (Roya)"})
    for site_id, meta in channels.items():
        ch = ET.SubElement(root, "channel", id=meta["xmltv_id"])
        ET.SubElement(ch, "display-name", lang="ar").text = meta["name"]
        # Roya publishes a mark for only some of its channels; the rest take
        # the network mark rather than showing nothing.
        key = ROYA_LOGO_KEYS.get(meta["xmltv_id"], "roya_tv")
        ET.SubElement(ch, "icon", src=f"{LOGO_BASE}/{key}.png")

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
                        icon=icon,
                    )
                    total += 1

    log(f"Roya: {ok_days}/{DAYS_BACK + DAYS_FORWARD + 1} days fetched OK, "
        f"{total} programmes total, no Live badge (Roya publishes no live marker)")

    # الجديد and الجزيرة share this file. Each is read after Roya, and each
    # inside its own try, so one broken source costs only its own channel.
    for name, reader in (("Al Jadeed", aljadeed_epg), ("Al Jazeera", aljazeera_epg)):
        try:
            total += reader.emit(root, reader.collect(session, OUTPUT))
        except Exception as exc:
            warn(f"{name} failed entirely, the guide is published without it: {exc}")

    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — Jordan (Roya)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
