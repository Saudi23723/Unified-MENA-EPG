#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tivibu Spor — Türk Telekom's sports channels, five of them.

Source — the Turkish feed epgshare01 publishes as TR3, already XMLTV:

  https://epgshare01.online/epgshare01/epg_ripper_TR3.xml.gz

This is the only reachable source that schedules these channels at all.
Every alternative was asked and none carries them: epgshare's own TR1
feed, all four of open-epg's Turkey files, tvyayinakisi (404 on
tivibu-spor, -1 through -4 and tivibuspor alike), and Spor Ekranı, which
named no Tivibu channel on either of two days sampled.

What the feed gives is modest and worth stating: the numbered channels
reach one day past the current one, and TİVİBU SPOR itself usually only
the current day. That is what exists.

The channel ids here are new, so nothing in a player is already mapped to
them. Each channel is therefore declared under several spellings — the
feed's own, a plain-ASCII fold of it, and the Arabic name — because a
player that matches by name needs the one its playlist happens to carry.
İ and I are different letters and neither case-folds to the other, so
both forms are written out rather than one being derived.

No icons. A channel is published with no <icon> rather than with a mark
this project invented for it: a placeholder wearing a broadcaster's
identity claims to be something it is not. If a real Tivibu logo is added
to logos/ later, LOGO_KEYS below is where it gets wired in.
"""

from __future__ import annotations

import gzip
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import xml.etree.ElementTree as ET

from epg_lib import (
    add_programme, fetch, log, new_session, norm, resolve_overlaps,
    run_main, utc_now, warn, with_live_badge, write_xml_atomic,
)

OUTPUT = "tivibu_spor_epg.xml"
UTC = timezone.utc
ISTANBUL = ZoneInfo("Europe/Istanbul")

EPGSHARE_URL = "https://epgshare01.online/epgshare01/epg_ripper_TR3.xml.gz"

LOGO_BASE = "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/logos"

# Only keep what a guide can sensibly show, so a stray far-future or
# long-past event can never bloat the file.
KEEP_BEHIND = timedelta(days=1)
KEEP_AHEAD = timedelta(days=14)

# (xmltv id, the feed's own id, [names])
#
# The first name is what a player shows; the rest exist only to be
# matched against whatever a playlist carries.
CHANNELS = [
    ("TivibuSpor.tr", "TİVİBU.SPOR.tr", [
        "Tivibu Spor", "TİVİBU SPOR", "TIVIBU SPOR", "Tivibu Sport",
        "تيفيبو سبور"]),
    ("TivibuSpor1.tr", "TİVİBU.SPOR.1.tr", [
        "Tivibu Spor 1", "TİVİBU SPOR 1", "TIVIBU SPOR 1", "Tivibu Sport 1",
        "تيفيبو سبور 1", "تيفيبو سبور ١"]),
    ("TivibuSpor2.tr", "TİVİBU.SPOR.2.tr", [
        "Tivibu Spor 2", "TİVİBU SPOR 2", "TIVIBU SPOR 2", "Tivibu Sport 2",
        "تيفيبو سبور 2", "تيفيبو سبور ٢"]),
    ("TivibuSpor3.tr", "TİVİBU.SPOR.3.tr", [
        "Tivibu Spor 3", "TİVİBU SPOR 3", "TIVIBU SPOR 3", "Tivibu Sport 3",
        "تيفيبو سبور 3", "تيفيبو سبور ٣"]),
    ("TivibuSpor4.tr", "TİVİBU.SPOR.4.tr", [
        "Tivibu Spor 4", "TİVİBU SPOR 4", "TIVIBU SPOR 4", "Tivibu Sport 4",
        "تيفيبو سبور 4", "تيفيبو سبور ٤"]),
]

# Empty until a real mark exists; see the note in the module docstring.
LOGO_KEYS: dict[str, str] = {}

# Turkish for "live". Spelled with either i so an upper-cased title still
# matches — Python's case folding does not map I to the dotless ı.
LIVE_RE = re.compile(r"canl[ıiİI]\b", re.IGNORECASE)
XMLTV_TS_RE = re.compile(r"^(\d{14})(?:\s*([+-]\d{4}))?$")


def parse_xmltv_time(value: str | None) -> datetime | None:
    """An XMLTV timestamp, as UTC.

    This feed states +0300 and keeps it, so the offset is trusted. A
    stamp without one is read as Istanbul, which is the clock the feed is
    written on.
    """
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


def fetch_feed(session, now: datetime) -> dict[str, list[dict]]:
    """The TR3 feed, keyed by its own channel ids."""
    per: dict[str, list[dict]] = defaultdict(list)
    raw = fetch(session, EPGSHARE_URL).content
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    root = ET.fromstring(raw.decode("utf-8", "replace"))

    wanted = {feed_id for _xid, feed_id, _names in CHANNELS}
    for programme in root.findall("programme"):
        cid = programme.get("channel")
        if cid not in wanted:
            continue
        start = parse_xmltv_time(programme.get("start"))
        stop = parse_xmltv_time(programme.get("stop"))
        if start is None or stop is None or stop <= start:
            continue
        if not (now - KEEP_BEHIND <= start <= now + KEEP_AHEAD):
            continue
        title_el = programme.find("title")
        title = norm(title_el.text or "") if title_el is not None else ""
        if not title:
            continue
        per[cid].append({
            "start": start, "stop": stop, "title": title,
            "live": bool(LIVE_RE.search(title)),
        })
    return dict(per)


def build() -> int:
    log("TIVIBU SPOR EPG | epgshare01 TR3")
    session = new_session()
    now = utc_now()

    try:
        feed = fetch_feed(session, now)
    except Exception as exc:
        warn(f"epgshare01 TR3 unavailable: {exc}")
        # write_xml_atomic keeps the previous file rather than publishing
        # an empty one, so a bad fetch costs nothing.
        write_xml_atomic(ET.Element("tv"), OUTPUT,
                         generator_name="Unified MENA EPG — Tivibu Spor")
        return 0

    per_channel: dict[str, list[dict]] = {}
    for xmltv_id, feed_id, names in CHANNELS:
        events = resolve_overlaps(feed.get(feed_id, []))
        if events:
            per_channel[xmltv_id] = events
        log(f"  {names[0]:16} feed={len(feed.get(feed_id, [])):4} "
            f"-> {len(events):4}")

    if not per_channel:
        warn("no Tivibu channel came back with programmes — keeping the "
             "previous file rather than publishing empty channels")
        write_xml_atomic(ET.Element("tv"), OUTPUT,
                         generator_name="Unified MENA EPG — Tivibu Spor")
        return 0

    root = ET.Element("tv",
                      {"generator-info-name": "Unified MENA EPG — Tivibu Spor"})
    # A channel with nothing to show is left out entirely: an empty
    # channel is worse in a player than no channel at all.
    for xmltv_id, _feed_id, names in CHANNELS:
        if xmltv_id not in per_channel:
            continue
        channel = ET.SubElement(root, "channel", id=xmltv_id)
        for name in names:
            lang = "ar" if any("؀" <= c <= "ۿ" for c in name) else "tr"
            ET.SubElement(channel, "display-name", lang=lang).text = name
        key = LOGO_KEYS.get(xmltv_id)
        if key and os.path.exists(os.path.join("logos", f"{key}.png")):
            ET.SubElement(channel, "icon", src=f"{LOGO_BASE}/{key}.png")

    total = 0
    badged = 0
    for xmltv_id, _feed_id, _names in CHANNELS:
        for event in per_channel.get(xmltv_id, []):
            title = event["title"]
            if event["live"]:
                title = with_live_badge(title)
                badged += 1
            add_programme(root, xmltv_id, event["start"], event["stop"],
                          title, category="Spor")
            total += 1

    days = sorted({e["start"].astimezone(ISTANBUL).strftime("%Y-%m-%d")
                   for evs in per_channel.values() for e in evs})
    log(f"Tivibu Spor: {len(per_channel)}/{len(CHANNELS)} channels with data, "
        f"{total} programmes over {len(days)} days "
        f"({days[0]} .. {days[-1]}), {badged} marked live")

    write_xml_atomic(root, OUTPUT, guard_regression=False, min_programmes=10,
                     generator_name="Unified MENA EPG — Tivibu Spor")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
