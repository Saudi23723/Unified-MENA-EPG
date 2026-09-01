#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tivibu Spor — Türk Telekom's sports channels, five of them.

This is not a guide of its own. It has no output file and no workflow:
collect() and emit() are called from bein_sports_turkey_epg.build(), so
the five channels come down the beIN SPORTS Türkiye link that is already
in the player. Both are Turkish sports guides and a player needs one URL
for them, not two.

Source — the Turkish feed epgshare01 publishes as TR3, already XMLTV:

  https://epgshare01.online/epgshare01/epg_ripper_TR3.xml.gz

This is the only reachable source that schedules these channels at all.
Every alternative was asked and none carries them: epgshare's own TR1
feed, all four of open-epg's Turkey files, tvyayinakisi (404 on
tivibu-spor, -1 through -4 and tivibuspor alike), and Spor Ekranı, which
named no Tivibu channel on either of two days sampled.

What the feed gives is modest and worth stating: the numbered channels
reach one day past the current one, and TİVİBU SPOR itself usually only
the current day. That is what exists. Because that is so little, what was
published last run is read back out of the beIN Türkiye file and merged
in, so a single failed fetch empties nothing.

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
    close_channel_gaps,
    LIVE_BADGE, LIVE_BADGE_GREEN, LIVE_BADGE_PURPLE,
    add_programme, fetch, log, norm, resolve_overlaps, utc_now, warn,
    with_live_badge,
)

UTC = timezone.utc
ISTANBUL = ZoneInfo("Europe/Istanbul")

EPGSHARE_URL = "https://epgshare01.online/epgshare01/epg_ripper_TR3.xml.gz"

LOGO_BASE = "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/logos"

# Only keep what a guide can sensibly show, so a stray far-future or
# long-past event can never bloat the file.
KEEP_BEHIND = timedelta(days=1)
KEEP_AHEAD = timedelta(days=14)

# What a Tivibu channel says when the feed has run out. Better than
# a blank row, which a player renders as a dead channel.
NOTHING_ANNOUNCED = "Yayın akışı açıklanmadı — لم يُعلن البث"

# (xmltv id, the feed's own id, [names])
#
# The first name is what a player shows; the rest exist only to be
# matched against whatever a playlist carries.
CHANNELS = [
    ("TivibuSpor.tr", "TİVİBU.SPOR.tr", [
        "Tivibu Spor", "TİVİBU SPOR", "TIVIBU SPOR", "Tivibu Sport",
        "تيفيبو سبور"]),
    # Tivibu Spor 1 is deliberately absent: today_matches_epg publishes
    # under that id now. Its feed had stopped carrying real programming and
    # the channel was showing nothing but a row saying so, while the
    # today's-matches guide had no id any playlist would recognise. One
    # file must own an id, so this one gives it up.
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

CHANNEL_IDS = {xid for xid, _feed_id, _names in CHANNELS}

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


def strip_badge(title: str) -> str:
    """A title as the feed wrote it, with any Live mark this project added.

    Rows read back out of the published file already carry the badge emit()
    put there. Leaving it on would let it be re-appended, and would freeze a
    "live" claim onto a programme long after it aired; the badge is decided
    again on every run from the feed's own wording.
    """
    out = title or ""
    for badge in (LIVE_BADGE, LIVE_BADGE_GREEN, LIVE_BADGE_PURPLE):
        out = out.replace(badge, "")
    return norm(out.replace("‎", ""))


def fetch_feed(session, now: datetime) -> dict[str, list[dict]]:
    """The TR3 feed, keyed by this project's channel ids."""
    per: dict[str, list[dict]] = defaultdict(list)
    raw = fetch(session, EPGSHARE_URL).content
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    root = ET.fromstring(raw.decode("utf-8", "replace"))

    by_feed_id = {feed_id: xid for xid, feed_id, _names in CHANNELS}
    for programme in root.findall("programme"):
        xid = by_feed_id.get(programme.get("channel"))
        if xid is None:
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
        per[xid].append({"start": start, "stop": stop, "title": title})
    return dict(per)


def carry_forward(path: str) -> dict[str, list[dict]]:
    """Tivibu rows already in the beIN Türkiye guide.

    Only the five channel ids above are read back; every other channel in
    that file is written by its own generator and is never touched here.
    """
    per: dict[str, list[dict]] = defaultdict(list)
    if not path or not os.path.exists(path):
        return {}
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        warn(f"previous {path} unreadable, Tivibu starts clean: {exc}")
        return {}

    for programme in root.findall("programme"):
        xid = programme.get("channel")
        if xid not in CHANNEL_IDS:
            continue
        start = parse_xmltv_time(programme.get("start"))
        stop = parse_xmltv_time(programme.get("stop"))
        if start is None or stop is None or stop <= start:
            continue
        title_el = programme.find("title")
        title = strip_badge(title_el.text if title_el is not None else "")
        if not title:
            continue
        per[xid].append({"start": start, "stop": stop, "title": title})
    return dict(per)


def collect(session, previous_path: str = "") -> dict[str, list[dict]]:
    """Every Tivibu Spor programme worth publishing right now, per channel."""
    now = utc_now()

    fresh: dict[str, list[dict]] = {}
    try:
        fresh = fetch_feed(session, now)
    except Exception as exc:
        warn(f"epgshare01 TR3 unavailable ({exc}) — Tivibu runs on what was "
             f"already in the guide")

    carried = carry_forward(previous_path)
    if not fresh and carried:
        warn("Tivibu Spor got nothing readable from the feed — the five "
             "channels are running on what was already published")

    per: dict[str, list[dict]] = {}
    for xid, _feed_id, _names in CHANNELS:
        merged: dict[tuple, dict] = {}
        for event in carried.get(xid, []) + fresh.get(xid, []):
            merged[(event["start"], event["stop"], event["title"])] = event
        kept = [e for e in merged.values()
                if now - KEEP_BEHIND <= e["stop"] and e["start"] <= now + KEEP_AHEAD]
        if kept:
            rows = resolve_overlaps(sorted(kept, key=lambda e: e["start"]))
            # The upstream feed stops supplying Tivibu at some point each
            # evening, so by the small hours these channels had nothing
            # covering "now" and a player showed four blank rows. A blank
            # row reads as a dead channel; say it out loud instead.
            per[xid] = close_channel_gaps(
                rows, min(rows[0]["start"], now), max(rows[-1]["stop"], now),
                NOTHING_ANNOUNCED)
        log(f"  {_names[0]:16} feed={len(fresh.get(xid, [])):4} "
            f"carried={len(carried.get(xid, [])):4} -> {len(per.get(xid, [])):4}")
    return per


def emit(root: ET.Element, per_channel: dict[str, list[dict]]) -> int:
    """Declare the channels and write their programmes into an existing <tv>.

    The elements are appended wherever this is called from; write_xml_atomic
    reorders the file into the channel-then-programme shape XMLTV requires.
    """
    if not per_channel:
        warn("Tivibu Spor: nothing to publish, the five channels are left "
             "out of this run")
        return 0

    # A channel with nothing to show is left out entirely: an empty
    # channel is worse in a player than no channel at all.
    for xid, _feed_id, names in CHANNELS:
        if xid not in per_channel:
            continue
        channel = ET.SubElement(root, "channel", id=xid)
        for name in names:
            lang = "ar" if any("؀" <= c <= "ۿ" for c in name) else "tr"
            ET.SubElement(channel, "display-name", lang=lang).text = name
        key = LOGO_KEYS.get(xid)
        if key and os.path.exists(os.path.join("logos", f"{key}.png")):
            ET.SubElement(channel, "icon", src=f"{LOGO_BASE}/{key}.png")

    total = 0
    badged = 0
    for xid, _feed_id, _names in CHANNELS:
        for event in per_channel.get(xid, []):
            title = event["title"]
            if LIVE_RE.search(title):
                title = with_live_badge(title)
                badged += 1
            add_programme(root, xid, event["start"], event["stop"], title,
                          category="Spor")
            total += 1

    days = sorted({e["start"].astimezone(ISTANBUL).strftime("%Y-%m-%d")
                   for evs in per_channel.values() for e in evs})
    log(f"Tivibu Spor: {len(per_channel)}/{len(CHANNELS)} channels with data, "
        f"{total} programmes over {len(days)} days "
        f"({days[0]} .. {days[-1]}), {badged} marked live")
    return total
