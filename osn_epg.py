#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OSN's channels — a full programme guide for each, on the Roya link.

Asked for by name — "can you find OSN's, complete? ... do them with
logos" — beside MBC on the Jordan (Roya) guide, read the same way:
roya_jordan_epg.py calls collect() and emit() after its own channels, and
a failure here costs the OSN channels only.

WHERE THE SCHEDULES COME FROM. OSN publishes no open guide. open-epg's
Egypt files carry fourteen of its channels about two days ahead, and were
measured on 24 September 2026:

  open-epg egypt2   fourteen OSN channels, titles mostly in English
  open-epg egypt1   thirteen of the same under Arabic channel names —
                    the fallback when egypt2 does not answer

THE CLOCK WAS MEASURED, NOT ASSUMED. egypt2 was checked against
epgshare's AE1 on MBC 2 for the MBC guide — delta 0 on every shared
title — and egypt1 against egypt2 on OSN One (five titles) and OSN
Movies Action (fourteen): delta 0 on every one. Declared offsets are
read as they stand.

WHAT IS LEFT OUT, AND WHY. OSN Kidzone, Mezze, News and Showcase Classics
are listed by the feeds that know them with nothing, or two rows, under
them. A channel with no schedule is not given one here.

The parsing is mbc_epg's own — one reader for one feed family.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import xml.etree.ElementTree as ET

from epg_lib import add_programme, log, norm, resolve_overlaps, utc_now, warn
from mbc_epg import LOGO_BASE, XMLTV_TIME, read_feed, rows_in

UTC = timezone.utc

FEEDS = {
    "eg_en": "https://www.open-epg.com/files/egypt2.xml",
    "eg_ar": "https://www.open-epg.com/files/egypt1.xml",
    "sa_ar": "https://www.open-epg.com/files/saudiarabia1.xml",
    "sa_en": "https://www.open-epg.com/files/saudiarabia2.xml",
    "uae2": "https://www.open-epg.com/files/uae2.xml",
}

LOGO_VERSION = "v2"

# (xmltv id = the name a player shows, logo stem, [names],
#  [(feed, the feed's channel id), ... in order of preference])
CHANNELS = [
    ("OSN One", "osn_one", ["OSN One", "OSN TV One", "OSN 1", "أو إس إن وان"],
     [("eg_en", "OSN TV One.eg"), ("eg_ar", "أو إس إن وان.eg")]),
    ("OSN Showcase", "osn_showcase", ["OSN Showcase", "OSN Showcase 4k", "OSN TV Showcase", "أو إس إن شو كايس"],
     [("eg_en", "OSN TV Showcase.eg"), ("eg_ar", "أو إس إن شو كايس.eg")]),
    ("OSN Now", "osn_now", ["OSN Now", "OSN TV Now", "أو إس إن ناو"],
     [("eg_en", "OSN TV Now.eg")]),
    ("OSN Comedy", "osn_comedy", ["OSN Comedy", "OSN Comedy 4k", "OSN TV Comedy", "أو إس إن كوميدي"],
     [("eg_en", "OSN TV Comedy.eg"), ("eg_ar", "أو إس إن كوميدي.eg")]),
    ("OSN Crime", "osn_crime", ["OSN Crime", "OSN TV Crime", "أو إس إن كرايم"],
     [("eg_en", "OSN TV Crime.eg"), ("eg_ar", "أو إس إن كرايم.eg")]),
    ("OSN Kids", "osn_kids", ["OSN Kids", "OSN TV Kids", "أو إس إن كيدز"],
     [("eg_en", "OSN TV Kids.eg"), ("eg_ar", "أو إس إن كيدز.eg")]),
    ("OSN Movies Premiere", "osn_movies_premiere",
     ["OSN Movies Premiere", "OSN MOVIES Premiere", "OSN TV Movies Premiere", "أو إس إن موفيز بريميير"],
     [("eg_en", "OSN TV Movies Premiere.eg"), ("eg_ar", "أو إس إن موفيز بريميير.eg")]),
    ("OSN Movies Hollywood", "osn_movies_hollywood",
     ["OSN Movies Hollywood", "OSN MOVIES Hollywood", "OSN TV Movies Hollywood", "أو إس إن موفيز هوليوود"],
     [("eg_en", "OSN TV Movies Hollywood.eg"), ("eg_ar", "أو إس إن موفيز هوليوود.eg")]),
    ("OSN Movies Action", "osn_movies_action",
     ["OSN Movies Action", "OSN TV Movies Action", "أو إس إن موفيز أكشن"],
     [("eg_en", "OSN TV Movies Action.eg"), ("eg_ar", "أو إس إن موفيز أكشن.eg")]),
    ("OSN Movies Comedy", "osn_movies_comedy",
     ["OSN Movies Comedy", "OSN TV Movies Comedy", "أو إس إن موفيز كوميدي"],
     [("eg_en", "OSN TV Movies Comedy.eg"), ("eg_ar", "أو إس إن موفيز كوميدي.eg")]),
    ("OSN Movies Family", "osn_movies_family",
     ["OSN Movies Family", "OSN MOVIES Family", "OSN TV Movies Family", "OSN Family Movies", "أو إس إن فاميلي موفيز"],
     [("eg_en", "OSN TV Movies Family.eg"), ("eg_ar", "أو إس إن فاميلي موفيز.eg")]),
    ("OSN Ya Hala", "osn_yahala", ["OSN Ya Hala", "OSN Yahala", "OSN TV Yahala", "أو إس إن ياهلا"],
     [("eg_en", "OSN Ya Hala.eg"), ("eg_ar", "أو إس إن ياهلا.eg")]),
    ("OSN Ya Hala Aflam", "osn_yahala_aflam",
     ["OSN Ya Hala Aflam", "OSN Yahala Aflam", "أو إس إن ياهلا أفلام"],
     [("eg_en", "Osn Ya Hala Aflam.eg"), ("eg_ar", "أو إس إن ياهلا أفلام.eg")]),
    ("OSN Ya Hala Bil Arabi", "osn_yahala_bilarabi",
     ["OSN Ya Hala Bil Arabi", "OSN Yahala Bil Arabi", "OSN TV Yahala Bil Arabi",
      "أو إس إن ياهلا بالعربي"],
     [("eg_en", "OSN TV Yahala Bil Arabi.eg"), ("eg_ar", "أو إس إن ياهلا بالعربي.eg")]),
    # THREE MORE OF THE PACKAGE, asked for from a photograph of the list.
    # saudiarabia1 carries Discovery ID and Fatafeat in Arabic (its clock
    # measured for the MBC guide), uae2 carries Nick Jr — its clock
    # measured against egypt1 on OSN Ya Hala: eleven shared titles, delta
    # 0. Al Safwa, Alfa Al Yawm and Discovery Science are listed by the
    # feeds that know them with nothing under them, and are left out.
    ("Nick Jr", "nick_jr", ["Nick Jr", "OSN Nick Jr", "Nick Jr.", "نك جونيور"],
     [("uae2", "NickJr.ae")]),
    ("Discovery ID", "discovery_id",
     ["Discovery ID", "OSN Discovery ID", "OSN DISCOVERY ID", "OSN Discovery IDX", "Investigation Discovery", "ID", "ديسكفري آي دي"],
     [("sa_ar", "Discovery ID.sa"), ("sa_en", "Discovery ID.sa")]),
    ("Fatafeat", "fatafeat", ["Fatafeat", "OSN Fatafeat", "OSN FATAFET", "فتافيت"],
     [("sa_ar", "Fatafeat.sa"), ("sa_en", "Fatafeat.sa")]),
]

KEEP_BEHIND = timedelta(days=1)


def carry_forward(path: str) -> dict[str, list[dict]]:
    """What the guide already holds for each OSN channel."""
    ours = {xmltv_id for xmltv_id, *_ in CHANNELS}
    out: dict[str, list[dict]] = {}
    if not path or not os.path.exists(path):
        return out
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:                                      # noqa: BLE001
        warn(f"OSN: previous {path} unreadable, nothing to carry: {exc}")
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
    """Every OSN channel's programmes, from the best feed that answered."""
    floor = utc_now() - KEEP_BEHIND
    feeds: dict[str, ET.Element | None] = {}

    def feed(name: str) -> ET.Element | None:
        if name not in feeds:
            try:
                feeds[name] = read_feed(session, FEEDS[name])
            except Exception as exc:                              # noqa: BLE001
                warn(f"OSN: {FEEDS[name]} failed ({exc}) — its channels fall "
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
                warn(f"OSN: no feed answered for {names[0]} — running on the "
                     f"{len(rows)} programme(s) already published")
                used = "carried"
        if rows:
            out[xmltv_id] = rows
            log(f"  {names[0]:22} {len(rows):4} programmes from {used}")
        else:
            warn(f"OSN: {names[0]} has nothing this run and is left out")
    return out


def emit(root: ET.Element, per_channel: dict[str, list[dict]]) -> int:
    """Declare the OSN channels that have programmes and write them."""
    total = 0
    for xmltv_id, key, names, _sources in CHANNELS:
        rows = per_channel.get(xmltv_id)
        if not rows:
            continue
        channel = ET.SubElement(root, "channel", id=xmltv_id)
        # "OSN One" under both language tags first — a player set to
        # Arabic shows the first Arabic name, and a search for "OSN" has
        # to find it; see the same note in mbc_epg.emit.
        ET.SubElement(channel, "display-name", lang="ar").text = names[0]
        # Every spelling a playlist uses, and each in capitals too —
        # "OSN MOVIES ACTION", "OSN Comedy 4k" — so a player matching by
        # name finds the channel whichever way the list writes it.
        seen: set[str] = set()
        for name in names + [n.upper() for n in names if n.isascii()]:
            if name in seen:
                continue
            seen.add(name)
            lang = "en" if name.isascii() else "ar"
            ET.SubElement(channel, "display-name", lang=lang).text = name
        logo = f"{key}_{LOGO_VERSION}.png"
        if os.path.exists(os.path.join("logos", logo)):
            ET.SubElement(channel, "icon", src=f"{LOGO_BASE}/{logo}")
        for event in resolve_overlaps(sorted(rows, key=lambda e: e["start"])):
            add_programme(root, xmltv_id, event["start"], event["stop"],
                          event["title"], event.get("desc", ""))
            total += 1
    log(f"OSN: {len(per_channel)}/{len(CHANNELS)} channels, {total} programmes")
    return total
