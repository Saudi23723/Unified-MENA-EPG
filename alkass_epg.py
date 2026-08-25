#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alkass (الكأس) — Qatar's sports channels.

Source: the Arabic feed epgshare01 publishes for the beIN carriage of
Alkass, already XMLTV and already Arabic:

  https://epgshare01.online/epgshare01/epg_ripper_BEIN1.xml.gz

Channels Alkass 1-8 all carry a schedule there, four days ahead. The feed
holds each channel twice, once Arabic and once English, so both are read
and paired by start time: English is written as the shown title with the
Arabic kept alongside it in the same <programme>.

The English side is thinner — 371 of 577 Arabic entries have a twin, 56%
to 79% depending on the channel — so anything with no English counterpart
keeps its Arabic title rather than being dropped or left blank.

Why not the broadcaster's own site: alkass.net's bare domain does not
answer at all, and www.alkass.net serves a 60 KB page carrying no
schedule — no JSON-LD, no embedded data, eight clock strings on the whole
page. bein.com's Arabic ajax endpoint does return the guide, but as
659 KB of markup with none of the documented class names, so it would
have to be reverse-engineered for data this feed already gives cleanly.

Alkass 9, 10, 11 and the two SHOOF channels exist, but no reachable
source publishes a schedule for them, so they are not in this guide.

No Live badge here. Neither this feed nor any other source checked marks
which broadcasts are live — no "مباشر", no "LIVE", no replay marker
anywhere in 577 programmes. An earlier version badged everything in the
"الرياضة العام" category, but that marks sport, not live, and a Live
marker that cannot be trusted is worse than none: it makes the badge
meaningless on the guides that do have real live data behind it.

The programme's own category is still written, so sport is easy to spot
without claiming anything the source never said.
"""

from __future__ import annotations

import gzip
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import xml.etree.ElementTree as ET

from epg_lib import (
    add_programme, fetch, log, new_session, resolve_overlaps, run_main,
    utc_now, warn, write_xml_atomic,
)

OUTPUT = "alkass_epg.xml"
UTC = timezone.utc
DOHA = timezone(timedelta(hours=3))

FEED = "https://epgshare01.online/epgshare01/epg_ripper_BEIN1.xml.gz"

KEEP_BEHIND = timedelta(days=1)
KEEP_AHEAD = timedelta(days=14)

# The feed's own channel ids, Arabic and English per channel. Casing is
# inconsistent upstream (Alkass_5_En against Alkass_5_EN), so ids are
# matched case-insensitively.
CHANNELS = [
    (n, f"Alkass_{n}_AR.bein", f"Alkass_{n}_EN.bein", xid, f"Alkass {n}",
     f"الكأس {n}", f"alkass{n}")
    for n, xid in enumerate(
        ["AlkassOne.qa", "AlkassTwo.qa", "AlkassThree.qa", "AlkassFour.qa",
         "AlkassFive.qa", "AlkassSix.qa", "AlkassSeven.qa", "AlkassEight.qa"],
        start=1,
    )
]

LOGO_BASE = "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/logos"

XMLTV_TS_RE = re.compile(r"^(\d{14})(?:\s*([+-]\d{4}))?$")


def parse_xmltv_time(value: str | None) -> datetime | None:
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
        dt = dt.replace(tzinfo=DOHA)
    return dt.astimezone(UTC)


def fetch_feed(session) -> ET.Element | None:
    """The gzipped XMLTV feed, or None if it cannot be read."""
    try:
        raw = fetch(session, FEED).content
        return ET.fromstring(gzip.decompress(raw).decode("utf-8", "replace"))
    except Exception as exc:
        warn(f"Alkass feed unavailable: {exc}")
        return None


def collect(root: ET.Element, now: datetime) -> tuple[dict, dict]:
    """Arabic programmes keyed by our channel id, plus the English titles
    keyed by (channel id, start) so the two can be paired."""
    arabic_of = {ar.lower(): xid for _n, ar, _en, xid, _en_name, _ar_name, _k in CHANNELS}
    english_of = {en.lower(): xid for _n, _ar, en, xid, _en_name, _ar_name, _k in CHANNELS}

    per: dict[str, list[dict]] = defaultdict(list)
    english: dict[tuple[str, datetime], str] = {}

    horizon_start = now - KEEP_BEHIND
    horizon_stop = now + KEEP_AHEAD

    for pr in root.findall("programme"):
        feed_id = (pr.get("channel") or "").lower()
        xid = arabic_of.get(feed_id)
        en_xid = english_of.get(feed_id)
        if not xid and not en_xid:
            continue
        start = parse_xmltv_time(pr.get("start"))
        stop = parse_xmltv_time(pr.get("stop"))
        if start is None or stop is None or stop <= start:
            continue
        if not (horizon_start <= start <= horizon_stop):
            continue

        title_el = pr.find("title")
        title = (title_el.text or "").strip() if title_el is not None else ""
        if not title:
            continue

        if en_xid:
            english[(en_xid, start)] = title
            continue

        cat_el = pr.find("category")
        category = (cat_el.text or "").strip() if cat_el is not None else ""

        per[xid].append({
            "start": start,
            "stop": stop,
            "title": title,
            "category": category,
        })

    return per, english


def build() -> int:
    log("ALKASS (الكأس) EPG | epgshare01 BEIN1 Arabic feed | channels 1-8")
    session = new_session()
    now = utc_now()

    root_feed = fetch_feed(session)
    if root_feed is None:
        # write_xml_atomic keeps the previous file rather than publishing an
        # empty one, so a bad fetch costs nothing.
        write_xml_atomic(ET.Element("tv"), OUTPUT,
                         generator_name="Unified MENA EPG — Alkass")
        return 0

    per, english = collect(root_feed, now)

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — Alkass"})
    with_data = [c for c in CHANNELS if per.get(c[3])]
    missing = [c[5] for c in CHANNELS if not per.get(c[3])]
    if missing:
        log(f"No schedule in the feed for: {', '.join(missing)}")

    for _n, _ar, _en, xid, en_name, ar_name, key in with_data:
        ch = ET.SubElement(root, "channel", id=xid)
        # English first: a player shows the first display-name it can use.
        ET.SubElement(ch, "display-name", lang="en").text = en_name
        ET.SubElement(ch, "display-name", lang="ar").text = ar_name
        ET.SubElement(ch, "icon", src=f"{LOGO_BASE}/{key}.png")

    total = paired = 0
    for _n, _ar, _en, xid, _en_name, _ar_name, _key in with_data:
        for ev in resolve_overlaps(per[xid]):
            en_title = english.get((xid, ev["start"]))
            if en_title:
                shown, alts = en_title, [("ar", ev["title"])]
                paired += 1
            else:
                shown, alts = ev["title"], []
            add_programme(
                root, xid, ev["start"], ev["stop"], shown,
                category=ev["category"] or "الرياضة",
                alt_titles=alts,
            )
            total += 1

    log(f"Alkass: {len(with_data)}/{len(CHANNELS)} channels, {total} programmes, "
        f"{paired} shown in English with Arabic alongside")

    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — Alkass")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
