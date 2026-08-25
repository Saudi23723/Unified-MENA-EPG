#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tabii Spor — TRT's sports service on the tabii platform: eleven channels.

There are two different things here, and they need two different sources.

  tabii Spor            one linear channel, on air around the clock
  tabii Spor 1 .. 10    per-match PPV streams that only exist while a
                        fixture is on, so nothing schedules them a week
                        ahead the way a linear channel is scheduled

The linear channel comes from TRT's own broadcast-schedule page, which
carries a full week inside its Next.js payload:

  https://www.trtspor.com.tr/yayin-akisi/tabii-spor

with tvyayinakisi.com filling the current day where TRT publishes a
generic block instead of the fixture.

The ten PPV numbers come from Spor Ekranı, an independent Turkish
listings site, which is the only reachable source that says *which
number* a given match is on:

  https://www.sporekrani.com/

It publishes schema.org BroadcastEvent JSON-LD, one block per broadcast:

    "isLiveBroadcast": true,
    "publishedOn": {"name": "tabii Spor 3",
                    "sameAs": ".../home/channel/tabii-spor-3"},
    "broadcastOfEvent": {"name": "Türkiye - Kosova",
                         "startDate": "2026-08-25T15:00:00+03:00",
                         "endDate":   "2026-08-25T18:00:00+03:00"}

Everything else was checked and does not carry the numbering: TRT's own
index lists three slugs and none of them is numbered, tvyayinakisi 404s
on tabii-spor-1 through -10, livefootballtv has no tabii channel at all,
mackolik / ntvspor / fotomac / canlitv never print the number, and
tabii's own eu1.tabii.com/apigateway answers contentNotFound without a
token.

Why the PPV guide accumulates instead of being rebuilt: Spor Ekranı
renders today and only today — /home/day/<any date> and ?format=json all
come back as the current day. So each run merges what the source
publishes now into what this file already holds, and drops what has
aged out. Nothing is invented; every programme was read from the source
on the day it ran.

Live badge: on the PPV channels only, and only where the source sets
isLiveBroadcast. TRT publishes no live marker, so the linear channel
carries none.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone

import xml.etree.ElementTree as ET

from epg_lib import (
    add_programme, fetch, log, new_session, norm, resolve_overlaps,
    run_main, utc_now, warn, with_live_badge, write_xml_atomic,
)

OUTPUT = "tabii_spor_1_10_epg.xml"
UTC = timezone.utc

TRT_URL = "https://www.trtspor.com.tr/yayin-akisi/tabii-spor"
TVY_URL = "https://www.tvyayinakisi.com/tabii-spor-yayin-akisi/"
SPOREKRANI_URL = "https://www.sporekrani.com/"

LOGO_BASE = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG"
             "/main/logos")

# 0 is the linear channel; 1..10 are the PPV streams.
LINEAR = 0
PPV_NUMBERS = list(range(1, 11))


def channel_id(number: int) -> str:
    return "TabiiSpor.tr" if number == LINEAR else f"TabiiSpor{number}.tr"


def channel_names(number: int) -> tuple[str, str]:
    if number == LINEAR:
        return "tabii Spor", "تابي سبور"
    return f"tabii Spor {number}", f"تابي سبور {number}"


def channel_logo(number: int) -> str:
    """Each channel wears its own number.

    The marks are held in this repository, not hot-linked: no host serves a
    numbered set big enough to show. They are built from tabii's own logo
    with the number set in its place, so tabii Spor 3 reads "spor 3" and
    the linear channel carries no number at all.
    """
    name = "tabii.png" if number == LINEAR else f"tabii{number}.png"
    return f"{LOGO_BASE}/{name}"


ALL_NUMBERS = [LINEAR] + PPV_NUMBERS
PPV_IDS = {channel_id(n) for n in PPV_NUMBERS}

# TRT's own id for the linear channel. The title is matched too, so a
# re-numbering on their side costs nothing.
TABII_CHANNEL_ID = 20423462
TABII_TITLE_RE = re.compile(r"tab(?:i|İ|ı)i?\s*spor", re.I)

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
LD_JSON_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S)

# "tabii Spor" on its own, or followed by its number.
TABII_NAME_RE = re.compile(r"tab(?:i|İ|ı)i?\s*spor(?:\s*(\d{1,2}))?", re.I)
# Spor Ekranı ends the sentence "<channels> kanal(lar)ından canlı ...",
# so the channel names are whatever sits in front of that phrase.
KANAL_RE = re.compile(r"kanal\(lar\)ından")

XMLTV_TIME = "%Y%m%d%H%M%S %z"

# Keep the file to what a guide can sensibly show.
KEEP_BEHIND = timedelta(days=1)
KEEP_AHEAD = timedelta(days=14)


def parse_utc(value) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.astimezone(UTC) if stamp.tzinfo else stamp.replace(tzinfo=UTC)


# --------------------------------------------------------------------------
# TRT — the linear channel
# --------------------------------------------------------------------------

def find_epg_days(node, depth: int = 0) -> list[dict]:
    """The list of {date, tvChannels} days, wherever TRT has put it.

    It currently sits at props.pageProps.data.rows[5].content.epg, but the
    row index moves whenever they reorder the page, so the payload is
    searched by shape instead of by path.
    """
    if depth > 14:
        return []
    if isinstance(node, dict):
        days = node.get("epg")
        if (isinstance(days, list) and days
                and all(isinstance(d, dict) and "tvChannels" in d for d in days)):
            return days
        for value in node.values():
            found = find_epg_days(value, depth + 1)
            if found:
                return found
    elif isinstance(node, list):
        for value in node[:80]:
            found = find_epg_days(value, depth + 1)
            if found:
                return found
    return []


def fetch_trt(session) -> list[dict]:
    """Every linear-channel programme TRT publishes, deduped across days."""
    page = fetch(session, TRT_URL).text
    blob = NEXT_DATA_RE.search(page)
    if not blob:
        warn("TRT: no __NEXT_DATA__ on the page")
        return []
    try:
        payload = json.loads(blob.group(1))
    except Exception as exc:
        warn(f"TRT: payload not JSON: {exc}")
        return []

    days = find_epg_days(payload)
    if not days:
        warn("TRT: no epg days in the payload")
        return []

    seen: dict[tuple, dict] = {}
    for day in days:
        for channel in day.get("tvChannels") or []:
            title = str(channel.get("title") or "")
            if channel.get("id") != TABII_CHANNEL_ID and not TABII_TITLE_RE.search(title):
                continue
            current = channel.get("current")
            shows = list(channel.get("past") or [])
            shows += [current] if isinstance(current, dict) and current else []
            shows += list(channel.get("upcoming") or [])
            for show in shows:
                start = parse_utc(show.get("starttime"))
                stop = parse_utc(show.get("endtime"))
                name = norm(show.get("title"))
                if not start or not stop or stop <= start or not name:
                    continue
                # The same programme appears in one day's `upcoming` and the
                # next day's `past`; keep it once.
                seen[(start, stop, name)] = {
                    "number": LINEAR, "start": start, "stop": stop,
                    "title": name, "desc": norm(show.get("synopsis")),
                    "live": False,
                }
    log(f"  TRT: {len(seen)} programmes across {len(days)} days")
    return list(seen.values())


def fetch_tvyayinakisi(session) -> list[dict]:
    """The current day from tvyayinakisi, as schema.org BroadcastEvents."""
    page = fetch(session, TVY_URL).text
    out: dict[tuple, dict] = {}
    for block in LD_JSON_RE.findall(page):
        try:
            payload = json.loads(block)
        except Exception:
            continue
        stack = [payload]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                if node.get("@type") in ("BroadcastEvent", "Event"):
                    start = parse_utc(node.get("startDate"))
                    stop = parse_utc(node.get("endDate"))
                    name = norm(node.get("name"))
                    if start and stop and stop > start and name:
                        out[(start, stop, name)] = {
                            "number": LINEAR, "start": start, "stop": stop,
                            "title": name, "desc": "", "live": False,
                        }
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
    log(f"  tvyayinakisi: {len(out)} programmes")
    return list(out.values())


# --------------------------------------------------------------------------
# Spor Ekranı — the ten PPV numbers
# --------------------------------------------------------------------------

def numbers_in(text: str) -> set[int]:
    """Every tabii channel number named in `text`. Bare "tabii Spor" is 0."""
    out = set()
    for m in TABII_NAME_RE.finditer(text or ""):
        out.add(int(m.group(1)) if m.group(1) else LINEAR)
    return out


def tabii_numbers(event: dict) -> set[int]:
    """Which tabii channels this broadcast is on, per Spor Ekranı.

    publishedOn is the structured answer and is preferred. Some rows carry
    no publishedOn at all and name the channel only in the sentence
    "<channels> kanal(lar)ından canlı yayınlanacak", so that prefix is read
    as a fallback — never the whole description, which also holds the
    fixture name and could contain anything.
    """
    published = event.get("publishedOn")
    entries = published if isinstance(published, list) else [published] if published else []
    found: set[int] = set()
    for entry in entries:
        if isinstance(entry, dict):
            found |= numbers_in(entry.get("name") or "")
    if found:
        return found

    description = event.get("description") or ""
    cut = KANAL_RE.search(description)
    return numbers_in(description[:cut.start()]) if cut else set()


def fetch_sporekrani(session) -> list[dict]:
    """Today's PPV broadcasts, one entry per channel a match is carried on."""
    page = fetch(session, SPOREKRANI_URL).text
    blocks = LD_JSON_RE.findall(page)
    if not blocks:
        warn("Spor Ekranı: no ld+json on the page")
        return []

    events: list[dict] = []
    seen_broadcasts = 0
    off_scale: set[int] = set()

    for block in blocks:
        try:
            payload = json.loads(block)
        except Exception:
            continue
        for event in (payload if isinstance(payload, list) else [payload]):
            if not isinstance(event, dict):
                continue
            seen_broadcasts += 1
            numbers = tabii_numbers(event)
            if not numbers:
                continue

            slot = event.get("broadcastOfEvent")
            slot = slot if isinstance(slot, dict) else {}
            start = parse_utc(slot.get("startDate"))
            stop = parse_utc(slot.get("endDate"))
            title = norm(slot.get("name")) or norm(event.get("name"))
            if not start or not stop or stop <= start or not title:
                continue
            live = event.get("isLiveBroadcast") is True

            for number in sorted(numbers):
                if number == LINEAR:
                    # The linear channel is TRT's to schedule; Spor Ekranı
                    # only lists the match it happens to be showing, which
                    # would collide with TRT's own full-day grid.
                    continue
                if number not in PPV_NUMBERS:
                    off_scale.add(number)
                    continue
                events.append({"number": number, "start": start, "stop": stop,
                               "title": title, "desc": "", "live": live})

    if off_scale:
        warn(f"Spor Ekranı named tabii channel(s) outside 1-10: "
             f"{sorted(off_scale)} — not published, the guide declares ten")

    used = sorted({e["number"] for e in events})
    log(f"  Spor Ekranı: {seen_broadcasts} broadcasts published, "
        f"{len(events)} on tabii Spor {used or '—'}")
    return events


# --------------------------------------------------------------------------
# What the file already holds
# --------------------------------------------------------------------------

def load_previous(path: str) -> list[dict]:
    """PPV programmes already in the file, so a one-day source accumulates.

    Only the PPV channels are carried: the linear channel is refetched in
    full from TRT every run, so carrying it would just fight the fetch.
    """
    if not os.path.exists(path):
        return []
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        warn(f"previous {path} unreadable, starting clean: {exc}")
        return []

    out: list[dict] = []
    for programme in root.findall("programme"):
        cid = programme.get("channel")
        if cid not in PPV_IDS:
            continue
        try:
            start = datetime.strptime(programme.get("start"), XMLTV_TIME)
            stop = datetime.strptime(programme.get("stop"), XMLTV_TIME)
            number = int(cid.removeprefix("TabiiSpor").removesuffix(".tr"))
        except Exception:
            continue
        title_el = programme.find("title")
        title = norm(title_el.text if title_el is not None else "")
        if not title or stop <= start:
            continue
        out.append({"number": number,
                    "start": start.astimezone(UTC), "stop": stop.astimezone(UTC),
                    "title": title, "desc": "", "live": False, "carried": True})
    return out


def build() -> int:
    log("TABII SPOR EPG | TRT for the linear channel, Spor Ekranı for the ten PPV numbers")
    session = new_session()

    linear: list[dict] = []
    try:
        linear = fetch_trt(session)
    except Exception as exc:
        warn(f"TRT fetch failed: {exc}")

    filler: list[dict] = []
    try:
        filler = fetch_tvyayinakisi(session)
    except Exception as exc:
        warn(f"tvyayinakisi fetch failed: {exc}")

    # Filler only where TRT scheduled nothing: TRT is the broadcaster.
    covered = [(e["start"], e["stop"]) for e in linear]
    added = 0
    for candidate in filler:
        if any(candidate["start"] < stop and start < candidate["stop"]
               for start, stop in covered):
            continue
        linear.append(candidate)
        added += 1
    if added:
        log(f"  tvyayinakisi filled {added} slot(s) TRT left empty")

    ppv_fresh: list[dict] = []
    try:
        ppv_fresh = fetch_sporekrani(session)
    except Exception as exc:
        warn(f"Spor Ekranı fetch failed: {exc}")

    carried = load_previous(OUTPUT)
    if carried:
        log(f"  carried forward: {len(carried)} PPV programme(s) already published")
    if not ppv_fresh and carried:
        warn("Spor Ekranı published nothing for tabii today — the PPV channels "
             "are running on what was already in the file")

    # A fresh reading of a slot replaces the carried copy of it.
    merged: dict[tuple, dict] = {}
    for event in carried + ppv_fresh:
        merged[(event["number"], event["start"], event["stop"])] = event

    events = linear + list(merged.values())

    now = utc_now()
    events = [e for e in events
              if now - KEEP_BEHIND <= e["stop"] and e["start"] <= now + KEEP_AHEAD]

    if not events:
        # write_xml_atomic keeps the previous file rather than publishing an
        # empty one, so a bad fetch costs nothing.
        write_xml_atomic(ET.Element("tv"), OUTPUT,
                         generator_name="Unified MENA EPG — tabii Spor")
        return 0

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — tabii Spor"})
    for number in ALL_NUMBERS:
        tr_name, ar_name = channel_names(number)
        channel = ET.SubElement(root, "channel", id=channel_id(number))
        ET.SubElement(channel, "display-name", lang="tr").text = tr_name
        ET.SubElement(channel, "display-name", lang="ar").text = ar_name
        ET.SubElement(channel, "icon", src=channel_logo(number))

    per_channel: dict[int, list[dict]] = {}
    for event in events:
        per_channel.setdefault(event["number"], []).append(event)

    total = 0
    badged = 0
    for number in ALL_NUMBERS:
        rows = per_channel.get(number)
        if not rows:
            continue
        for event in resolve_overlaps(rows):
            title = event["title"]
            if event.get("live"):
                title = with_live_badge(title)
                badged += 1
            add_programme(root, channel_id(number), event["start"], event["stop"],
                          title, event.get("desc", ""), category="Spor")
            total += 1

    live_numbers = sorted(n for n in per_channel if n != LINEAR)
    days = sorted({e["start"].strftime("%Y-%m-%d") for e in events})
    log(f"tabii Spor: {total} programmes over {len(days)} days "
        f"({days[0]} .. {days[-1]}), {badged} badged Live | "
        f"linear {len(per_channel.get(LINEAR, []))} | "
        f"PPV on {live_numbers or 'no channel today'}")

    # The linear channel alone is a week of TRT's grid, so the floor is
    # about that: the PPV numbers come and go with the fixtures and are
    # not something to hold the file to.
    write_xml_atomic(root, OUTPUT, guard_regression=False, min_programmes=20,
                     generator_name="Unified MENA EPG — tabii Spor")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
