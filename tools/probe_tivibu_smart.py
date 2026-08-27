#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Where are Tivibu Spor and Smart Spor scheduled?

Both are Turkish sports channels carrying league football, and neither is
in this repository yet. Spor Ekranı named neither on the day it was
sampled — its sixteen channel names held no Tivibu and no Smart — but it
publishes the current day only and only the channels showing something,
so one day proves nothing about a channel with no fixture that day.

A linear channel with a published week beats a fixture row anyway, so the
schedule feeds are asked first: epgshare01, open-epg, and tvyayinakisi,
which is the broadcaster-facing guide already read here for beIN.

Prints every channel any source names that looks like either one, with
how far ahead it reaches, plus Spor Ekranı's full channel list again so a
second day's sample is on the record.

Reads only; writes nothing.
"""

from __future__ import annotations

import gzip
import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TR = timezone(timedelta(hours=3))
TODAY = datetime.now(TR).date()

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/127.0 Safari/537.36")

# "Tivibu Spor 2", "tivibuspor", "Smart Spor", "SmartSpor 2"
WANTED = re.compile(r"tivibu|smart\s*spor", re.I)

LD_JSON_ANY_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S)

FEEDS = [
    ("epgshare TR1", "https://epgshare01.online/epgshare01/epg_ripper_TR1.xml.gz"),
    ("epgshare TR3", "https://epgshare01.online/epgshare01/epg_ripper_TR3.xml.gz"),
    ("open-epg 1", "https://www.open-epg.com/files/turkey1.xml"),
    ("open-epg 2", "https://www.open-epg.com/files/turkey2.xml"),
    ("open-epg 3", "https://www.open-epg.com/files/turkey3.xml"),
    ("open-epg 4", "https://www.open-epg.com/files/turkey4.xml"),
]

# tvyayinakisi builds its URLs from a slug; these are the plausible ones.
SLUGS = [
    "tivibu-spor", "tivibu-spor-1", "tivibu-spor-2", "tivibu-spor-3",
    "tivibu-spor-4", "tivibuspor",
    "smart-spor", "smart-spor-2", "smartspor",
]


def get(session, url, **kw):
    return session.get(url, timeout=45, headers={"User-Agent": UA}, **kw)


def scan_feed(session, label: str, url: str) -> None:
    print(f"\n[{label}] {url}")
    try:
        response = get(session, url)
    except Exception as exc:
        print(f"    ERROR {type(exc).__name__}: {exc}")
        return
    print(f"    http={response.status_code} bytes={len(response.content)}")
    if response.status_code != 200 or not response.content:
        return

    raw = response.content
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    try:
        root = ET.parse(io.BytesIO(raw)).getroot()
    except Exception as exc:
        print(f"    not parseable: {exc}")
        return

    names = {}
    for channel in root.findall("channel"):
        names[channel.get("id")] = " / ".join(
            d.text or "" for d in channel.findall("display-name"))

    per = defaultdict(lambda: defaultdict(int))
    for programme in root.findall("programme"):
        try:
            day = datetime.strptime(programme.get("start"),
                                    "%Y%m%d%H%M%S %z").astimezone(TR).date()
        except Exception:
            continue
        per[programme.get("channel")][day] += 1

    hits = [cid for cid in names
            if WANTED.search(cid) or WANTED.search(names[cid])]
    if not hits:
        print(f"    {len(names)} channels, none matching Tivibu or Smart Spor")
        return
    print(f"    {len(hits)} match(es):")
    for cid in sorted(hits):
        days = sorted(per[cid])
        ahead = [d for d in days if d > TODAY]
        span = f"{days[0]}..{days[-1]}" if days else "no programmes"
        print(f"      {cid:<32} {sum(per[cid].values()):>5} progs  "
              f"{span}  ahead={len(ahead)}d  | {names[cid][:40]}")


def main() -> int:
    print(f"Tivibu Spor / Smart Spor source hunt | today={TODAY} (TR)")
    session = requests.Session()

    print("\n" + "=" * 70)
    print("1. Schedule feeds — a published week beats a fixture row")
    print("=" * 70)
    for label, url in FEEDS:
        scan_feed(session, label, url)

    print("\n" + "=" * 70)
    print("2. tvyayinakisi — does it carry a page for either?")
    print("=" * 70)
    for slug in SLUGS:
        url = f"https://www.tvyayinakisi.com/{slug}-yayin-akisi/"
        try:
            response = get(session, url)
        except Exception as exc:
            print(f"  {slug:<18} ERROR {type(exc).__name__}")
            continue
        events = 0
        if response.status_code == 200:
            for block in LD_JSON_ANY_RE.findall(response.text):
                events += block.count('"BroadcastEvent"')
        print(f"  {slug:<18} http={response.status_code} "
              f"bytes={len(response.content):>7}  BroadcastEvent~{events}")

    print("\n" + "=" * 70)
    print("3. Spor Ekranı — a second day's sample of its channel list")
    print("=" * 70)
    try:
        page = get(session, "https://www.sporekrani.com/").text
    except Exception as exc:
        print(f"  unavailable: {exc}")
        return 0

    names = Counter()
    for block in LD_JSON_ANY_RE.findall(page):
        try:
            payload = json.loads(block)
        except Exception:
            continue
        for event in (payload if isinstance(payload, list) else [payload]):
            if not isinstance(event, dict):
                continue
            published = event.get("publishedOn")
            entries = (published if isinstance(published, list)
                       else [published] if published else [])
            for entry in entries:
                if isinstance(entry, dict) and entry.get("name"):
                    names[entry["name"].strip()] += 1

    print(f"  {len(names)} channel name(s) today:")
    for name, count in names.most_common():
        mark = "  <-- WANTED" if WANTED.search(name) else ""
        print(f"    {count:>3}  {name}{mark}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
