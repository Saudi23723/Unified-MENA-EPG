#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Find a schedule for the beIN Qatar channels that have none.

Twenty-three of beIN's forty channels come back from the ar-mena region
without a usable guide:

  nine with no rows at all   4K HDR, AFC, AFC 1-6, NBA
  fourteen with one blurb    MAX 1-6, XTRA 2-9, the same text repeated

The cheapest possible answer is that beIN schedules them, just not under
the region this guide asks for — AFC is an Asian competition and its
channels may well live under an Asian region. That is asked first,
against the same official API, before any third party is considered.

Then the aggregations, which are the fallback and not the preference:
epgshare01's Gulf feeds and open-epg's Gulf files.

Reads only; writes nothing.
"""

from __future__ import annotations

import gzip
import io
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

AST = timezone(timedelta(hours=3))
NOW = datetime.now(timezone.utc)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/127.0 Safari/537.36")

API_CHANNELS = "https://www.beinsports.com/api/opta/tv-channel"
API_EVENTS = "https://www.beinsports.com/api/opta/tv-event"

# Every region code beIN's own sites use, plus the obvious Asian ones.
REGIONS = [
    "ar-mena", "en-mena", "fr-mena",
    "en-us", "es-us", "fr-fr", "tr-tr",
    "en-au", "en-nz", "id-id", "th-th", "en-ph", "en-hk", "en-my",
    "en-sg", "ms-my", "zh-hk", "en-asia", "ar-qa", "ar-sa", "ar-ae",
]

# The channels with nothing usable today.
WANTED = ("afc", "nba", "4k hdr", "max", "xtra")

FEEDS = [
    ("epgshare QA1", "https://epgshare01.online/epgshare01/epg_ripper_QA1.xml.gz"),
    ("epgshare AE1", "https://epgshare01.online/epgshare01/epg_ripper_AE1.xml.gz"),
    ("epgshare SA1", "https://epgshare01.online/epgshare01/epg_ripper_SA1.xml.gz"),
    ("epgshare AR1", "https://epgshare01.online/epgshare01/epg_ripper_AR1.xml.gz"),
    ("epgshare IN5", "https://epgshare01.online/epgshare01/epg_ripper_IN5.xml.gz"),
    ("open-epg qatar1", "https://www.open-epg.com/files/qatar1.xml"),
    ("open-epg uae1", "https://www.open-epg.com/files/uae1.xml"),
    ("open-epg saudiarabia1", "https://www.open-epg.com/files/saudiarabia1.xml"),
]


def get(session, url, **kw):
    return session.get(url, timeout=45, headers={"User-Agent": UA}, **kw)


def rows_for(session, guid: str) -> int:
    """How many schedule rows beIN has for this channel in the next week."""
    params = {
        "startBefore": (NOW + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "endAfter": NOW.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "channelIds": guid,
        "limit": 100,
    }
    try:
        data = get(session, API_EVENTS, params=params).json()
    except Exception:
        return -1
    count = data.get("count")
    return count if isinstance(count, int) else len(data.get("rows") or [])


def main() -> int:
    session = requests.Session()
    print(f"beIN Qatar gap hunt | {NOW:%Y-%m-%d %H:%M} UTC\n")

    print("=" * 72)
    print("1. The official API, region by region")
    print("=" * 72)
    seen_guid: dict[str, str] = {}
    for region in REGIONS:
        try:
            data = get(session, API_CHANNELS, params={"region": region}).json()
            rows = data.get("rows") or []
        except Exception as exc:
            print(f"  {region:<10} ERROR {type(exc).__name__}")
            continue
        names = [(r.get("name") or "").strip() for r in rows]
        hits = [r for r in rows
                if any(w in (r.get("name") or "").lower() for w in WANTED)]
        print(f"  {region:<10} {len(rows):>3} channels, "
              f"{len(hits):>2} of interest")
        for r in hits:
            name = (r.get("name") or "").strip()
            seen_guid.setdefault(name, r.get("id"))
    print()

    if seen_guid:
        print("  asking the API for a week of rows on each:")
        for name, guid in sorted(seen_guid.items()):
            n = rows_for(session, guid)
            mark = "  <-- HAS A SCHEDULE" if n > 5 else ""
            print(f"    {name:<28} rows={n}{mark}")

    print("\n" + "=" * 72)
    print("2. Aggregated feeds covering the Gulf")
    print("=" * 72)
    for label, url in FEEDS:
        print(f"\n[{label}] {url}")
        try:
            resp = get(session, url)
        except Exception as exc:
            print(f"    ERROR {type(exc).__name__}")
            continue
        print(f"    http={resp.status_code} bytes={len(resp.content)}")
        if resp.status_code != 200 or not resp.content:
            continue
        raw = resp.content
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        try:
            root = ET.parse(io.BytesIO(raw)).getroot()
        except Exception as exc:
            print(f"    not XMLTV: {exc}")
            continue
        names = {c.get("id"): " / ".join(d.text or ""
                                         for d in c.findall("display-name"))
                 for c in root.findall("channel")}
        per = defaultdict(int)
        for p in root.findall("programme"):
            per[p.get("channel")] += 1
        hits = [c for c in names
                if any(w in (c + names[c]).lower() for w in WANTED)]
        print(f"    {len(names)} channels, {len(hits)} matching")
        for c in sorted(hits):
            print(f"      {c:<34} {per.get(c, 0):>4} progs  | {names[c][:34]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
