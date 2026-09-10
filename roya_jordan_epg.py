#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Jordan — the whole Roya network: Roya TV, News, Sport, Comedy, Kitchen,
Kids, Documentaries, مجتمعي, حول العالم, أنا بحكيلك القصة, رؤيا فلسطين,
إنتاجات رؤيا, كرفان, قناة الشرقية, قناة الشرقية نيوز, قناة العربي 2 and
the rest — every channel Roya schedules,
plus الجديد (Al Jadeed, Lebanon) and الجزيرة (Al Jazeera).

Those two ride in this file rather than getting links of their own. Each
has its own reader — aljadeed_epg.py, aljazeera_epg.py and
filler_epg.py — which knows
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
    add_programme, fetch, log, new_session, resolve_overlaps, run_main, warn,
    write_xml_atomic,
)

import aljadeed_epg
import aljazeera_epg
import filler_epg

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

# Roya has two schedule endpoints. schedule-pagination, which this guide
# used to read, returns ten channels. /channels/schedule returns the whole
# network — twenty-seven at the last count, including Documentaries,
# مجتمعي, حول العالم, أنا بحكيلك القصة and قناة العربي 2 — with the same
# day_number parameter and the same programme fields, so reading the wider
# one costs nothing and no channel has to be listed here by hand.
API = "https://backend.roya.tv/api/v01/channels/schedule"

DAYS_BACK = 1
DAYS_FORWARD = 6

# The backend sometimes nests a programme collection under its own title
# beside the real broadcast channel that carries it. Those rows belong on
# the broadcast channel a viewer can actually tune to.
CHANNEL_ALIASES = {
    "RFC": "Roya TV",
}

# No Live badge on any Roya channel. Roya publishes no live marker of any
# kind, so the only badge possible here would be "this was on air when the
# workflow ran", read off the clock — which put Live on a cooking show and
# a comedy rerun, and went stale minutes later either way. Guessing from
# the title was tried and dropped too: on a channel whose sport line-up is
# a repeated competition block rather than named fixtures, there is nothing
# solid to guess from. The Live badge belongs on الأردن الرياضية, which has
# real fixtures to put it on.


def slugify_id(name: str, site_id: str = "") -> str:
    """ASCII-only id (XMLTV/TiviMate channel ids are conventionally ASCII).

    A name has to carry real ASCII *letters* to become the id. Counting
    digits too produced ids like Roya_2 for قناة العربي 2 and Roya_911 for
    911 — an id that says nothing about the channel and, in Al Araby's
    case, actively misleads. Those fall back to the channel number, which
    is what the Arabic-named channels have always used.
    """
    letters = "".join(ch for ch in name if ch.isascii() and ch.isalpha())
    if len(letters) >= 3:
        return "Roya_" + "".join(ch for ch in name if ch.isascii() and ch.isalnum())
    return f"Roya_Ch{site_id}"


def channel_blocks(payload) -> list[dict]:
    """Every channel object in a response, wherever the API nests it.

    The two endpoints wrap their channels differently and have changed
    shape before, so a channel is recognised by what it is — an object
    carrying a programme list and a name — rather than by the path it
    happens to sit at.
    """
    found: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            if "programs" in node and (node.get("title") or node.get("name")):
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return found


def channel_logo(xmltv_id: str, block: dict) -> str:
    """The channel's own mark when Roya publishes one, else this repo's."""
    for key in ("image", "logo", "icon", "thumbnail", "thumbnail_web", "channel_image"):
        url = (block.get(key) or "").strip() if isinstance(block.get(key), str) else ""
        if url.startswith("http"):
            return url
    key = ROYA_LOGO_KEYS.get(xmltv_id, "roya_tv")
    return f"{LOGO_BASE}/{key}.png"


def discover_channels(session) -> dict[str, dict]:
    """channel_site_id -> {xmltv_id, name, logo}"""
    blocks = channel_blocks(fetch(session, API, params={"day_number": 0}).json())
    if not blocks:
        raise ValueError("empty channel-discovery response")

    channels: dict[str, dict] = {}
    for block in blocks:
        site_id = block.get("id")
        name = (block.get("title") or block.get("name") or "").strip()
        if site_id is None or not name:
            continue
        xmltv_id = slugify_id(name, str(site_id))
        channels[str(site_id)] = {"xmltv_id": xmltv_id, "name": name,
                                  "logo": channel_logo(xmltv_id, block)}

    if not channels:
        raise ValueError("no channels discovered")
    return channels


def fetch_day(session, day_number: int) -> list[dict]:
    return channel_blocks(fetch(session, API, params={"day_number": day_number}).json())


def canonical_channels(channels: dict[str, dict]) -> dict[str, dict]:
    """Route known nested programme buckets back to the real channel."""
    by_name = {meta["name"]: meta for meta in channels.values()}
    out: dict[str, dict] = {}
    aliased = 0
    for site_id, meta in channels.items():
        target = by_name.get(CHANNEL_ALIASES.get(meta["name"], ""))
        if target is None:
            out[site_id] = meta
            continue
        out[site_id] = dict(target)
        aliased += 1
    if aliased:
        log(f"Roya channel aliases applied: {aliased}")
    return out


def build() -> int:
    log("JORDAN — ROYA TV EPG | official backend.roya.tv API | full daily schedule")
    session = new_session()

    channels = canonical_channels(discover_channels(session))
    log(f"Roya channels discovered: {len(channels)} -> {[c['name'] for c in channels.values()]}")

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — Jordan (Roya)"})
    written = set()
    for meta in channels.values():
        if meta["xmltv_id"] in written:
            continue
        written.add(meta["xmltv_id"])
        ch = ET.SubElement(root, "channel", id=meta["xmltv_id"])
        ET.SubElement(ch, "display-name", lang="ar").text = meta["name"]
        # Roya publishes a mark for only some of its channels; the rest take
        # the network mark rather than showing nothing.
        ET.SubElement(ch, "icon", src=meta["logo"])

    total = 0
    ok_days = 0
    per_channel: dict[str, list[dict]] = {}

    for offset in range(-DAYS_BACK, DAYS_FORWARD + 1):
        try:
            days = fetch_day(session, offset)
        except Exception as exc:
            warn(f"Roya day_number={offset} fetch failed: {exc}")
            continue

        if not days:
            continue
        ok_days += 1

        for ch_entry in days:
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

                # GATHERED PER CHANNEL, ACROSS EVERY DAY, and written
                # only once the whole channel is in hand — see below.
                per_channel.setdefault(meta["xmltv_id"], []).append({
                    "start": start,
                    "stop": stop,
                    "title": title,
                    "desc": (prog.get("description") or "").strip(),
                    "icon": prog.get("thumbnail_web") or None,
                })

    # AND THE OVERLAPS ARE RESOLVED BEFORE ANYTHING IS WRITTEN.
    #
    # This guide was the only one of the nine here that did not do this,
    # and it cost the whole file. write_xml_atomic refuses a tree where
    # one channel has two programmes at once — rightly, XMLTV cannot
    # express it — and it refuses the WHOLE tree, so a single clashing
    # pair out of Roya's API threw away all twenty-eight channels:
    #
    #     WARN overlapping programmes on Roya_RoyaTV
    #          at 20260910210000 +0000
    #
    # A refused write leaves the previous file exactly where it was,
    # which is the right thing to do and looks like nothing at all. So
    # the guide simply stopped advancing, and its days aged: the last
    # build that succeeded had filled its FUTURE days with stand-in, and
    # those days became the present. Measured on the published file, the
    # older a day was the more real it looked —
    #
    #     20260905  1949 rows,   73 stand-in    4%
    #     20260909  1965 rows, 1749 stand-in   89%
    #     20260910  1995 rows, 1890 stand-in   95%   today
    #
    # — which reads like a source that has gone quiet and is not one.
    # Asked directly, the API answers with 1741 programmes for today and
    # every one of them survives this file's own filter.
    #
    # Roya publishes across days, and a programme that runs past midnight
    # comes back in BOTH days' responses, so the clash is as likely to be
    # a channel against itself a day later as two rows in one payload.
    # That is why a channel is gathered whole, over every day, and
    # resolved once — resolving each day on its own would leave exactly
    # the pair that breaks this.
    for xmltv_id, rows in per_channel.items():
        for event in resolve_overlaps(rows):
            add_programme(root, xmltv_id, event["start"], event["stop"],
                          event["title"], event["desc"], icon=event["icon"])
            total += 1

    log(f"Roya: {ok_days}/{DAYS_BACK + DAYS_FORWARD + 1} days fetched OK, "
        f"{total} programmes total, no Live badge (Roya publishes no live marker)")

    # الجديد and الجزيرة share this file. Each is read after Roya, and each
    # inside its own try, so one broken source costs only its own channel.
    for name, reader in (("Al Jadeed", aljadeed_epg),
                         ("Al Jazeera", aljazeera_epg),
                         ("Filler", filler_epg)):
        try:
            total += reader.emit(root, reader.collect(session, OUTPUT))
        except Exception as exc:
            warn(f"{name} failed entirely, the guide is published without it: {exc}")

    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — Jordan (Roya)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
