#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
beIN SPORTS Türkiye — full EPG.

Primary source — tvyayinakisi.com, a Turkish TV-guide site that publishes
every channel's schedule as schema.org BroadcastEvent JSON-LD:

  https://www.tvyayinakisi.com/<slug>-yayin-akisi/

Each event carries the programme name and its startDate/endDate complete
with the +03:00 offset, so nothing has to be inferred and there are no CSS
class names to go stale — this is data the site publishes for machines to
read. How far ahead a page reaches varies by channel: HABER currently
carries a full week, most others only the current day.

Second and third sources — two public XMLTV feeds, in this order:

  https://epgshare01.online/epgshare01/epg_ripper_TR1.xml.gz
  https://www.open-epg.com/files/turkey1.xml

Both are filler and never outrank the broadcaster's own listing: an event
from either is kept only where nothing above it scheduled that channel at
that time, and epgshare is offered the gap before open-epg.

epgshare covers beIN SPORTS 4, which tvyayinakisi does not schedule at
all, and extends 1/2/3 a few days. It leaves a hole all the same: it
carries beIN SPORTS 1 and MAX 1/2 under ids that hold zero programmes, so
those three ran out at the end of the current day. open-epg schedules all
three two days ahead and is what closes that gap.

open-epg is also the reason beIN SPORTS 5 is here at all — see below.

open-epg's clock needs an override. It stamps Istanbul wall-clock and
labels it +0000:

  epgshare01   start="20260827094500 +0300"   the offset it keeps
  open-epg     start="20260827000000 +0000"   Istanbul midnight, called UTC

Read at face value every open-epg programme lands three hours late, which
looks like an ordinary schedule and is not one. Measured against
tvyayinakisi on titles the two share and that occur once on each side, the
gap was +180 minutes in all eighteen comparisons across beIN SPORTS 1, 3,
MAX 1 and HABER, with no exception; epgshare showed no such constant, so
this is open-epg alone. Its timestamps are therefore read as Istanbul
wall-clock and the declared offset is ignored.

That override is only correct while the feed stays wrong, so build()
measures the same gap on every run and warns if a constant reappears.

Why not Digiturk, which this generator used to read: digiturk.com.tr now
answers 403 from its edge gateway (Microsoft-Azure-Application-Gateway) to
every request, the plain human TV-guide page included, so the guide it
produced had eight channels and not one programme.

beIN SPORTS 5 used to be left out because no source scheduled it, and a
channel with no programmes is worse than no channel at all. open-epg does
schedule it, so it is published now. The rule has not changed: a channel
that comes back empty on a given run is still dropped from that run's
output rather than declared blank.

Titles ending in "/ Canlı" are the source's own marker for a live
broadcast; those, and only those, get the Live badge.
"""

from __future__ import annotations

import gzip
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import xml.etree.ElementTree as ET

from epg_lib import (
    add_programme, fetch, log, new_session, norm, resolve_overlaps,
    run_main, utc_now, warn, with_live_badge, write_xml_atomic,
)

OUTPUT = "bein_sports_turkey_epg.xml"
UTC = timezone.utc
ISTANBUL = ZoneInfo("Europe/Istanbul")

TVY_BASE = "https://www.tvyayinakisi.com"
EPGSHARE_URL = "https://epgshare01.online/epgshare01/epg_ripper_TR1.xml.gz"
OPENEPG_URL = "https://www.open-epg.com/files/turkey1.xml"

# Only keep what a TV guide can sensibly show, so a stray far-future or
# long-past event from either source can never bloat the file.
KEEP_BEHIND = timedelta(days=1)
KEEP_AHEAD = timedelta(days=14)

# Each channel names itself differently in each feed, so both id sets are
# written out rather than guessed at.
#
# `share` lists the ids the channel goes by inside epgshare01, empty where
# that feed has no usable entry. HABER is carried there twice under two
# ids, and the HD one holds programmes the other does not, so both are read
# and merged. epgshare also publishes beIN.SPORTS.1 / MAX.1 / MAX.2 ids
# that hold zero programmes; they are left out deliberately, since an id
# with nothing behind it only looks like coverage.
#
# `open` is the single id inside open-epg's turkey1 feed, which spells
# every one of them the same way the channel does.
CHANNELS = [
    {"name": "beIN SPORTS 1",     "slug": "bein-sports-1",     "share": ["Beinsports.tr"],
     "open": "beIN SPORTS 1.tr"},
    {"name": "beIN SPORTS 2",     "slug": "bein-sports-2",     "share": ["Beinsports.2.tr"],
     "open": "beIN SPORTS 2.tr"},
    {"name": "beIN SPORTS 3",     "slug": "bein-sports-3",     "share": ["Beinsports.3.tr"],
     "open": "beIN SPORTS 3.tr"},
    {"name": "beIN SPORTS 4",     "slug": "bein-sports-4",     "share": ["Beinsports.4.tr"],
     "open": "beIN SPORTS 4.tr"},
    # No tvyayinakisi page: bein-sports-5-yayin-akisi 404s. open-epg is the
    # only source that schedules this channel, which is why it is here.
    {"name": "beIN SPORTS 5",     "slug": "",                  "share": [],
     "open": "beIN SPORTS 5.tr"},
    {"name": "beIN SPORTS MAX 1", "slug": "bein-sports-max-1", "share": [],
     "open": "beIN SPORTS MAX 1.tr"},
    {"name": "beIN SPORTS MAX 2", "slug": "bein-sports-max-2", "share": [],
     "open": "beIN SPORTS MAX 2.tr"},
    {"name": "beIN SPORTS HABER", "slug": "bein-sports-haber",
     "share": ["Bein.Sports.Haber.tr", "beIN.SPORTS.HABER.HD.tr"],
     "open": "beIN SPORTS HABER.tr"},
]

LOGO_BASE = "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/logos"

# beIN SPORTS 1 is beIN SPORTS 1 either side of the border, so the Türkiye
# roster reuses the marks already fetched for Qatar rather than duplicating
# them. HABER is Türkiye-only and has its own file.
LOGO_KEYS = {
    "beIN SPORTS 1": "bein_1",
    "beIN SPORTS 2": "bein_2",
    "beIN SPORTS 3": "bein_3",
    "beIN SPORTS 4": "bein_4",
    "beIN SPORTS 5": "bein_5",
    "beIN SPORTS MAX 1": "bein_max1",
    "beIN SPORTS MAX 2": "bein_max2",
    "beIN SPORTS HABER": "bein_haber",
}

LD_JSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
# Turkish for "live". Spelled with either i so an upper-cased title still
# matches — Python's case folding does not map I to the dotless ı.
LIVE_RE = re.compile(r"canl[ıiİI]\b", re.IGNORECASE)
XMLTV_TS_RE = re.compile(r"^(\d{14})(?:\s*([+-]\d{4}))?$")


def slugify_id(name: str) -> str:
    """The channel ids this guide has always used, kept stable so an
    existing TiviMate mapping keeps working."""
    return f"{re.sub(r'[^A-Za-z0-9]+', '', name)}.tr"


def in_window(start: datetime, now: datetime) -> bool:
    return now - KEEP_BEHIND <= start <= now + KEEP_AHEAD


# --------------------------------------------------------------- tvyayinakisi
def broadcast_events(html: str) -> list[dict]:
    """Every schema.org BroadcastEvent on the page, wherever it is nested."""
    found: list[dict] = []
    for block in LD_JSON_RE.findall(html):
        try:
            data = json.loads(block)
        except Exception:
            continue  # one malformed block must not lose the others
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if node.get("@type") == "BroadcastEvent":
                    found.append(node)
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return found


def parse_iso(value) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ISTANBUL)
    return dt.astimezone(UTC)


def fetch_tvy_channel(session, slug: str, now: datetime) -> list[dict]:
    url = f"{TVY_BASE}/{slug}-yayin-akisi/"
    html = fetch(session, url).text

    events: list[dict] = []
    for node in broadcast_events(html):
        title = norm(str(node.get("name") or ""))
        start = parse_iso(node.get("startDate"))
        stop = parse_iso(node.get("endDate"))
        if not title or start is None or stop is None or stop <= start:
            continue
        if not in_window(start, now):
            continue
        events.append({
            "start": start,
            "stop": stop,
            "title": title,
            "live": bool(LIVE_RE.search(title)),
        })
    return events


# ----------------------------------------------------------------- epgshare01
def parse_xmltv_time(value: str | None,
                     assume_local: bool = False) -> datetime | None:
    """An XMLTV timestamp, as UTC.

    assume_local reads the fourteen digits as Istanbul wall-clock and
    ignores whatever offset the feed declares. It exists for one feed that
    declares an offset it does not keep — see OPENEPG_URL below.
    """
    m = XMLTV_TS_RE.match((value or "").strip())
    if not m:
        return None
    try:
        dt = datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
    except ValueError:
        return None
    offset = m.group(2)
    if offset and not assume_local:
        sign = 1 if offset[0] == "+" else -1
        dt = dt.replace(tzinfo=timezone(
            sign * timedelta(hours=int(offset[1:3]), minutes=int(offset[3:5]))
        ))
    else:
        dt = dt.replace(tzinfo=ISTANBUL)
    return dt.astimezone(UTC)


def fetch_xmltv_feed(session, url: str, label: str, now: datetime,
                     assume_local: bool = False) -> dict[str, list[dict]]:
    """An XMLTV feed, keyed by its own channel ids.

    Never raises. Both feeds read through this are filler, so one of them
    being down must cost only its own contribution — not the broadcaster's
    listing, and not the other feed.

    Compression is decided by the first two bytes rather than by the file
    extension: epgshare serves .xml.gz and open-epg serves plain .xml, and
    either could change that without changing what it means.
    """
    per: dict[str, list[dict]] = defaultdict(list)
    try:
        raw = fetch(session, url).content
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        root = ET.fromstring(raw.decode("utf-8", "replace"))
    except Exception as exc:
        warn(f"{label} unavailable, continuing without it: {exc}")
        return {}

    for pr in root.findall("programme"):
        cid = pr.get("channel")
        start = parse_xmltv_time(pr.get("start"), assume_local)
        stop = parse_xmltv_time(pr.get("stop"), assume_local)
        if not cid or start is None or stop is None or stop <= start:
            continue
        if not in_window(start, now):
            continue
        title_el = pr.find("title")
        title = norm(title_el.text or "") if title_el is not None else ""
        if not title:
            continue
        per[cid].append({
            "start": start,
            "stop": stop,
            "title": title,
            "live": bool(LIVE_RE.search(title)),
        })
    return dict(per)


# ---------------------------------------------------------------------- merge
def constant_offset(left: list[dict], right: list[dict]) -> int | None:
    """The single constant gap in minutes between two sources, if there is one.

    Only titles occurring exactly once on both sides are compared: a
    channel that fills its day with its own name repeated would otherwise
    pair every copy with every other and return the spread of a day.

    None means they either agree, share nothing comparable, or disagree in
    no single way — all three are normal. A single non-zero answer is not:
    it means one of them is being read on the wrong clock.
    """
    lc = defaultdict(int)
    rc = defaultdict(int)
    for ev in left:
        lc[ev["title"].strip().lower()] += 1
    for ev in right:
        rc[ev["title"].strip().lower()] += 1
    shared = [t for t in lc if lc[t] == 1 and rc.get(t) == 1]
    if len(shared) < 3:
        return None

    lt = {ev["title"].strip().lower(): ev["start"] for ev in left}
    rt = {ev["title"].strip().lower(): ev["start"] for ev in right}
    deltas = {round((rt[t] - lt[t]).total_seconds() / 60) for t in shared}
    if len(deltas) != 1:
        return None
    only = deltas.pop()
    return only or None


def merge_events(primary: list[dict], filler: list[dict]) -> list[dict]:
    """Primary wins outright; a filler event survives only if it occupies
    time the primary source left empty."""
    kept = resolve_overlaps(primary)
    spans = [(e["start"], e["stop"]) for e in kept]

    extra = [
        ev for ev in filler
        if not any(ev["start"] < end and begin < ev["stop"] for begin, end in spans)
    ]
    return resolve_overlaps(kept + extra)


def build() -> int:
    log("beIN SPORTS TÜRKİYE EPG | tvyayinakisi.com BroadcastEvent JSON-LD, "
        "epgshare01 TR and open-epg turkey1 as filler")
    session = new_session()
    now = utc_now()

    share = fetch_xmltv_feed(session, EPGSHARE_URL, "epgshare01 Turkish feed", now)
    if share:
        log(f"epgshare01 filler loaded: {len(share)} channels")

    openepg = fetch_xmltv_feed(session, OPENEPG_URL, "open-epg turkey1 feed",
                               now, assume_local=True)
    if openepg:
        log(f"open-epg filler loaded: {len(openepg)} channels")

    per_channel: dict[str, list[dict]] = {}
    for ch in CHANNELS:
        name, slug = ch["name"], ch["slug"]
        primary: list[dict] = []
        if slug:
            try:
                primary = fetch_tvy_channel(session, slug, now)
            except Exception as exc:
                warn(f"{name}: tvyayinakisi unavailable ({exc}) — "
                     f"falling back to filler only")

        # One channel can appear under several ids in the feed; a
        # programme listed under both is kept once.
        from_share = list({
            (ev["start"], ev["stop"], ev["title"]): ev
            for cid in ch["share"] for ev in share.get(cid, [])
        }.values())
        from_open = openepg.get(ch.get("open", ""), [])

        # open-epg is read as Istanbul wall-clock because it declares an
        # offset it does not keep. If it is ever corrected, that override
        # becomes the bug, so the disagreement is measured every run
        # rather than assumed to stay put.
        drift = constant_offset(primary, from_open)
        if drift:
            warn(f"{name}: open-epg disagrees with tvyayinakisi by a "
                 f"constant {drift:+d} minutes on every title they share. "
                 f"The assume_local override in fetch_xmltv_feed is meant "
                 f"to leave no constant gap — check whether open-epg has "
                 f"started keeping the offset it declares.")

        # Each source is offered only the time the ones above it left
        # empty, so precedence runs broadcaster, then epgshare, then
        # open-epg — never the other way round.
        merged = merge_events(merge_events(primary, from_share), from_open)
        per_channel[name] = merged
        log(f"  {name:20} tvyayinakisi={len(primary):4} "
            f"epgshare={len(from_share):4} open-epg={len(from_open):4} "
            f"-> {len(merged):4}")

    total = sum(len(v) for v in per_channel.values())
    with_data = [c for c in CHANNELS if per_channel.get(c["name"])]

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — beIN Sports Türkiye"})
    for ch in with_data:
        el = ET.SubElement(root, "channel", id=slugify_id(ch["name"]))
        ET.SubElement(el, "display-name", lang="tr").text = ch["name"]
        logo = LOGO_KEYS.get(ch["name"])
        if logo:
            ET.SubElement(el, "icon", src=f"{LOGO_BASE}/{logo}.png")

    live_badges = 0
    for ch in with_data:
        xid = slugify_id(ch["name"])
        for ev in per_channel[ch["name"]]:
            title = ev["title"]
            if ev["live"]:
                title = with_live_badge(title)
                live_badges += 1
            add_programme(
                root, xid, ev["start"], ev["stop"], title,
                category="Sports",
            )

    log(
        f"beIN Türkiye: {len(with_data)}/{len(CHANNELS)} channels with data, "
        f"{total} programmes, {live_badges} marked live"
    )

    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — beIN Sports Türkiye")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
