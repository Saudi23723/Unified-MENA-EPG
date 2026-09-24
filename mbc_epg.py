#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MBC's channels — a full programme guide for each, on the Roya link.

Asked for by name: "a full programme guide for every MBC channel, updated
automatically, each with a round logo", riding on the Jordan (Roya) guide
the way الجديد, الجزيرة and the Shahid filler channels already do, so
nothing new has to be added in the player. roya_jordan_epg.py calls
collect() and emit() below after its own channels; a failure here costs
the MBC channels only and never Amman's guide.

WHERE THE SCHEDULES COME FROM. MBC publishes no open guide of its own, so
this reads the public XMLTV feeds that carry it, each for what it is best
at, measured on 24 September 2026:

  open-epg saudiarabia1   thirteen MBC channels, IN ARABIC, two days ahead
                          (MBC 1-4, Action, Bollywood, Drama, MBC+ Drama,
                          Masr, Masr 2, Max, Variety, Wanasah)
  open-epg saudiarabia2   the same thirteen in English — the fallback
  open-epg egypt2         MBC 5
  epgshare01 SA2          MBC Iraq and MBC Masr Drama, in English

THE CLOCK WAS MEASURED, NOT ASSUMED. The same site stamps Istanbul time
as UTC in its Turkish file, which cost beIN Türkiye three hours until it
was caught. So every feed here was checked against another on titles
that occur exactly once on each side: saudiarabia2 against epgshare's AE1
(which declares +0100) on MBC 2, nine titles, delta 0 minutes; against
epgshare's SA2 on MBC Max, eight titles, delta 0; egypt2 against AE1 on
MBC 2, delta 0. saudiarabia1 carries the same slots as saudiarabia2 (384
of 428 on MBC 1). Every feed's declared offset is therefore read as it
stands.

NOTHING IS INVENTED. A row the feed calls "TV guide is not available" is
dropped rather than published as a programme. A channel whose feeds all
fail this run keeps what it already had in the guide, so an outage costs
freshness, not the channel.
"""
from __future__ import annotations

import gzip
import os
import re
from datetime import datetime, timedelta, timezone

import xml.etree.ElementTree as ET

from epg_lib import add_programme, fetch, log, norm, resolve_overlaps, utc_now, warn

UTC = timezone.utc
XMLTV_TIME = "%Y%m%d%H%M%S %z"

FEEDS = {
    "sa_ar": "https://www.open-epg.com/files/saudiarabia1.xml",
    "sa_en": "https://www.open-epg.com/files/saudiarabia2.xml",
    "eg": "https://www.open-epg.com/files/egypt2.xml",
    "share_sa": "https://epgshare01.online/epgshare01/epg_ripper_SA2.xml.gz",
}

LOGO_BASE = ("https://raw.githubusercontent.com/Saudi23723/"
             "Unified-MENA-EPG/main/logos")

# (xmltv id, logo stem, [names — the first is what a player shows],
#  [(feed, the feed's channel id), ... in order of preference])
CHANNELS = [
    ("MBC1.mbc", "mbc1", ["MBC 1", "MBC1", "MBC 1 HD", "ام بي سي 1", "ARA: MBC 1"],
     [("sa_ar", "MBC 1 HD.sa"), ("sa_en", "MBC 1 HD.sa")]),
    ("MBC2.mbc", "mbc2", ["MBC 2", "MBC2", "MBC 2 HD", "ام بي سي 2", "ARA: MBC 2"],
     [("sa_ar", "MBC 2 HD.sa"), ("sa_en", "MBC 2 HD.sa")]),
    ("MBC3.mbc", "mbc3", ["MBC 3", "MBC3", "MBC 3 HD", "ام بي سي 3", "ARA: MBC 3"],
     [("sa_ar", "MBC 3.sa"), ("sa_en", "MBC 3.sa")]),
    ("MBC4.mbc", "mbc4", ["MBC 4", "MBC4", "MBC 4 HD", "ام بي سي 4", "ARA: MBC 4"],
     [("sa_ar", "MBC 4 HD.sa"), ("sa_en", "MBC 4 HD.sa")]),
    ("MBC5.mbc", "mbc5", ["MBC 5", "MBC5", "MBC 5 HD", "ام بي سي 5", "ARA: MBC 5"],
     [("eg", "MBC 5.eg")]),
    ("MBCAction.mbc", "mbc_action",
     ["MBC Action", "MBC ACTION", "MBC Action HD", "ام بي سي أكشن", "ARA: MBC ACTION"],
     [("sa_ar", "MBC Action HD.sa"), ("sa_en", "MBC Action HD.sa")]),
    ("MBCBollywood.mbc", "mbc_bollywood",
     ["MBC Bollywood", "MBC BOLLYWOOD", "MBC Bollywood HD", "ام بي سي بوليوود",
      "ARA: MBC BOLLYWOOD"],
     [("sa_ar", "MBC Bollywood.sa"), ("sa_en", "MBC Bollywood.sa")]),
    ("MBCDrama.mbc", "mbc_drama",
     ["MBC Drama", "MBC DRAMA", "MBC Drama HD", "ام بي سي دراما", "ARA: MBC DRAMA"],
     [("sa_ar", "MBC Drama HD.sa"), ("sa_en", "MBC Drama HD.sa")]),
    ("MBCPlusDrama.mbc", "mbc_plus_drama",
     ["MBC+ Drama", "MBC Drama+", "MBC Drama Plus", "MBC+ DRAMA", "ARA: MBC+ DRAMA"],
     [("sa_ar", "MBC+ Drama HD.sa"), ("sa_en", "MBC+ Drama HD.sa")]),
    ("MBCMasr.mbc", "mbc_masr",
     ["MBC Masr", "MBC MASR", "MBC Masr HD", "ام بي سي مصر", "ARA: MBC MASR"],
     [("sa_ar", "MBC MASR.sa"), ("sa_en", "MBC MASR.sa")]),
    ("MBCMasr2.mbc", "mbc_masr2",
     ["MBC Masr 2", "MBC MASR 2", "MBC Masr 2 HD", "ام بي سي مصر 2", "ARA: MBC MASR 2"],
     [("sa_ar", "MBC MASR 2.sa"), ("sa_en", "MBC MASR 2.sa")]),
    ("MBCMasrDrama.mbc", "mbc_masr_drama",
     ["MBC Masr Drama", "MBC MASR DRAMA", "ام بي سي مصر دراما", "ARA: MBC MASR DRAMA"],
     [("share_sa", "EN:.MBC.Masr.Drama.sa")]),
    ("MBCIraq.mbc", "mbc_iraq",
     ["MBC Iraq", "MBC IRAQ", "MBC Iraq HD", "ام بي سي العراق", "ARA: MBC IRAQ"],
     [("share_sa", "EN:.MBC1.Iraq.sa")]),
    ("MBCMax.mbc", "mbc_max",
     ["MBC Max", "MBC MAX", "MBC Max HD", "ام بي سي ماكس", "ARA: MBC MAX"],
     [("sa_ar", "MBC Max HD.sa"), ("sa_en", "MBC Max HD.sa")]),
    ("MBCVariety.mbc", "mbc_variety",
     ["MBC Variety", "MBC VARIETY", "MBC+ Variety", "ام بي سي فارايتي", "ARA: MBC VARIETY"],
     [("sa_ar", "MBC VARIETY.sa"), ("sa_en", "MBC VARIETY.sa")]),
    ("Wanasah.mbc", "wanasah",
     ["Wanasah", "وناسة", "WANASAH", "ARA: WANASAH"],
     [("sa_ar", "Wanasah.sa"), ("sa_en", "Wanasah.sa")]),
]

# What a feed writes where it has no programme to name.
NOT_A_PROGRAMME = re.compile(r"TV guide is not available|^\s*$", re.I)

KEEP_BEHIND = timedelta(days=1)


def title_of(raw: str) -> str:
    """"ليلى:الحلقة 193" -> "ليلى — الحلقة 193"; "Nadina:Episode 36" likewise."""
    head, colon, tail = norm(raw).partition(":")
    if colon and re.match(r"\s*(?:الحلقة|Episode)\b", tail):
        return f"{head.strip()} — {tail.strip()}"
    return norm(raw)


def read_feed(session, url: str) -> ET.Element:
    raw = fetch(session, url).content
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return ET.fromstring(raw)


def rows_in(root: ET.Element, cid: str, floor: datetime) -> list[dict]:
    out = []
    for programme in root.iter("programme"):
        if programme.get("channel") != cid:
            continue
        try:
            start = datetime.strptime(programme.get("start"), XMLTV_TIME).astimezone(UTC)
            stop = datetime.strptime(programme.get("stop"), XMLTV_TIME).astimezone(UTC)
        except (TypeError, ValueError):
            continue
        if stop <= start or stop < floor:
            continue
        title = title_of(programme.findtext("title") or "")
        if NOT_A_PROGRAMME.search(title):
            continue
        out.append({"start": start, "stop": stop, "title": title,
                    "desc": norm(programme.findtext("desc") or "")})
    return out


def carry_forward(path: str) -> dict[str, list[dict]]:
    """What the guide already holds for each MBC channel."""
    ours = {xmltv_id for xmltv_id, *_ in CHANNELS}
    out: dict[str, list[dict]] = {}
    if not path or not os.path.exists(path):
        return out
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:                                      # noqa: BLE001
        warn(f"MBC: previous {path} unreadable, nothing to carry: {exc}")
        return out
    for programme in root.iter("programme"):
        cid = programme.get("channel")
        if cid not in ours:
            continue
        try:
            start = datetime.strptime(programme.get("start"), XMLTV_TIME).astimezone(UTC)
            stop = datetime.strptime(programme.get("stop"), XMLTV_TIME).astimezone(UTC)
        except (TypeError, ValueError):
            continue
        out.setdefault(cid, []).append({
            "start": start, "stop": stop,
            "title": norm(programme.findtext("title") or ""),
            "desc": norm(programme.findtext("desc") or "")})
    return out


def collect(session, previous_path: str = "") -> dict[str, list[dict]]:
    """Every MBC channel's programmes, from the best feed that answered."""
    floor = utc_now() - KEEP_BEHIND
    feeds: dict[str, ET.Element | None] = {}

    def feed(name: str) -> ET.Element | None:
        if name not in feeds:
            try:
                feeds[name] = read_feed(session, FEEDS[name])
            except Exception as exc:                              # noqa: BLE001
                warn(f"MBC: {FEEDS[name]} failed ({exc}) — its channels fall "
                     f"back to the next feed or to what is already published")
                feeds[name] = None
        return feeds[name]

    carried = carry_forward(previous_path)
    out: dict[str, list[dict]] = {}
    for xmltv_id, _key, names, sources in CHANNELS:
        rows: list[dict] = []
        used = ""
        for name, cid in sources:
            root = feed(name)
            if root is None:
                continue
            rows = rows_in(root, cid, floor)
            if rows:
                used = name
                break
        if not rows:
            rows = [r for r in carried.get(xmltv_id, []) if r["stop"] >= floor]
            if rows:
                warn(f"MBC: no feed answered for {names[0]} — running on the "
                     f"{len(rows)} programme(s) already published")
                used = "carried"
        if rows:
            out[xmltv_id] = rows
            log(f"  {names[0]:16} {len(rows):4} programmes from {used}")
        else:
            warn(f"MBC: {names[0]} has nothing this run and is left out")
    return out


def emit(root: ET.Element, per_channel: dict[str, list[dict]]) -> int:
    """Declare the MBC channels that have programmes and write them."""
    total = 0
    for xmltv_id, key, names, _sources in CHANNELS:
        rows = per_channel.get(xmltv_id)
        if not rows:
            continue
        channel = ET.SubElement(root, "channel", id=xmltv_id)
        for name in names:
            lang = "en" if name.isascii() else "ar"
            ET.SubElement(channel, "display-name", lang=lang).text = name
        if os.path.exists(os.path.join("logos", f"{key}.png")):
            ET.SubElement(channel, "icon", src=f"{LOGO_BASE}/{key}.png")
        for event in resolve_overlaps(sorted(rows, key=lambda e: e["start"])):
            add_programme(root, xmltv_id, event["start"], event["stop"],
                          event["title"], event.get("desc", ""))
            total += 1
    log(f"MBC: {len(per_channel)}/{len(CHANNELS)} channels, {total} programmes")
    return total
