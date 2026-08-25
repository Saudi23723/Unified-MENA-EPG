#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alkass (الكأس) — Qatar's sports channels.

Source: the Arabic feed epgshare01 publishes for the beIN carriage of
Alkass, already XMLTV and already Arabic:

  https://epgshare01.online/epgshare01/epg_ripper_BEIN1.xml.gz

Channels Alkass 1-8 all carry a schedule there, four days ahead, with
Arabic titles and Arabic categories. The Arabic feed is used rather than
the English twin that sits beside it in the same file.

Why not the broadcaster's own site: alkass.net's bare domain does not
answer at all, and www.alkass.net serves a 60 KB page carrying no
schedule — no JSON-LD, no embedded data, eight clock strings on the whole
page. bein.com's Arabic ajax endpoint does return the guide, but as
659 KB of markup with none of the documented class names, so it would
have to be reverse-engineered for data this feed already gives cleanly.

Alkass 9, 10, 11 and the two SHOOF channels exist, but no reachable
source publishes a schedule for them, so they are not in this guide.

About the Live badge: neither this feed nor any other source checked
marks which broadcasts are live — no "مباشر", no "LIVE", no replay
marker anywhere in 577 programmes. What the feed does carry is a
category per programme, so the badge marks Alkass's sport broadcasts
(category "الرياضة العام") and leaves its studio shows, news and
reality programming unbadged. That is the honest reading of the data
available: it marks sport, not verified-live.
"""

from __future__ import annotations

import gzip
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import xml.etree.ElementTree as ET

from epg_lib import (
    LIVE_BADGE_PURPLE, add_programme, fetch, log, new_session,
    resolve_overlaps, run_main, utc_now, warn, with_live_badge,
    write_xml_atomic,
)

OUTPUT = "alkass_epg.xml"
UTC = timezone.utc
DOHA = timezone(timedelta(hours=3))

FEED = "https://epgshare01.online/epgshare01/epg_ripper_BEIN1.xml.gz"

KEEP_BEHIND = timedelta(days=1)
KEEP_AHEAD = timedelta(days=14)

# The feed's own channel ids. Casing is inconsistent upstream (Alkass_5_En
# against Alkass_5_EN), so ids are matched case-insensitively.
CHANNELS = [
    ("Alkass_1_AR.bein", "AlkassOne.qa", "الكأس 1", "alkass1"),
    ("Alkass_2_AR.bein", "AlkassTwo.qa", "الكأس 2", "alkass2"),
    ("Alkass_3_AR.bein", "AlkassThree.qa", "الكأس 3", "alkass3"),
    ("Alkass_4_AR.bein", "AlkassFour.qa", "الكأس 4", "alkass4"),
    ("Alkass_5_AR.bein", "AlkassFive.qa", "الكأس 5", "alkass5"),
    ("Alkass_6_AR.bein", "AlkassSix.qa", "الكأس 6", "alkass6"),
    ("Alkass_7_AR.bein", "AlkassSeven.qa", "الكأس 7", "alkass7"),
    ("Alkass_8_AR.bein", "AlkassEight.qa", "الكأس 8", "alkass8"),
]

LOGO_BASE = "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/logos"

# The category the feed uses for Alkass's sport broadcasts, as opposed to
# "ترفيه" (studio shows), "أخبار" (news) and "برامج واقعية" (reality).
SPORT_CATEGORY = "الرياضة العام"

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


def collect(root: ET.Element, now: datetime) -> dict[str, list[dict]]:
    """Every Alkass programme in the feed, keyed by our own channel id."""
    wanted = {feed_id.lower(): xid for feed_id, xid, _, _ in CHANNELS}
    per: dict[str, list[dict]] = defaultdict(list)

    horizon_start = now - KEEP_BEHIND
    horizon_stop = now + KEEP_AHEAD

    for pr in root.findall("programme"):
        xid = wanted.get((pr.get("channel") or "").lower())
        if not xid:
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
        cat_el = pr.find("category")
        category = (cat_el.text or "").strip() if cat_el is not None else ""

        per[xid].append({
            "start": start,
            "stop": stop,
            "title": title,
            "category": category,
            "sport": category == SPORT_CATEGORY,
        })

    return per


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

    per = collect(root_feed, now)

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — Alkass"})
    with_data = [(f, x, n, k) for f, x, n, k in CHANNELS if per.get(x)]
    missing = [n for f, x, n, k in CHANNELS if not per.get(x)]
    if missing:
        log(f"No schedule in the feed for: {', '.join(missing)}")

    for _feed_id, xid, name, key in with_data:
        ch = ET.SubElement(root, "channel", id=xid)
        ET.SubElement(ch, "display-name", lang="ar").text = name
        ET.SubElement(ch, "icon", src=f"{LOGO_BASE}/{key}.png")

    total = badged = 0
    for _feed_id, xid, name, _key in with_data:
        for ev in resolve_overlaps(per[xid]):
            title = ev["title"]
            if ev["sport"]:
                title = with_live_badge(title, LIVE_BADGE_PURPLE)
                badged += 1
            p = add_programme(
                root, xid, ev["start"], ev["stop"], title,
                category=ev["category"] or "الرياضة",
            )
            if ev["sport"]:
                ET.SubElement(p, "category", lang="en").text = "Live"
            total += 1

    log(f"Alkass: {len(with_data)}/{len(CHANNELS)} channels, {total} programmes, "
        f"{badged} sport broadcasts badged")

    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — Alkass")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
