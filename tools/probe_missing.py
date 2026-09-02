#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: one whole Spor Ekranı broadcast record.

The repository already reads this page in update_tabii_epg — it publishes
ld+json, with the channel in publishedOn[].name, the fixture in
broadcastOfEvent.name and a real timestamp in startDate. That is better
structured than any of the three HTML pages.

What is not known is where it names the COMPETITION, and a source whose
competition cannot be read is a source whose matches all get filtered out.
So one record is printed whole. Delete once read.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter

from epg_lib import fetch, new_session

URL = "https://www.sporekrani.com/"
LD_JSON = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.S)


def main() -> int:
    page = fetch(new_session(), URL).text
    blocks = LD_JSON.findall(page)
    print(f"{len(blocks)} ld+json block(s)")

    events = []
    for block in blocks:
        try:
            payload = json.loads(block)
        except Exception:
            continue
        for event in (payload if isinstance(payload, list) else [payload]):
            if isinstance(event, dict) and event.get("broadcastOfEvent"):
                events.append(event)
    print(f"{len(events)} broadcast record(s)\n")

    print("=== two whole records ===")
    for event in events[:2]:
        print(json.dumps(event, ensure_ascii=False, indent=2)[:1600])
        print("-" * 60)

    print("\n=== which keys ever appear ===")
    outer, inner = Counter(), Counter()
    for event in events:
        outer.update(event.keys())
        slot = event.get("broadcastOfEvent")
        if isinstance(slot, dict):
            inner.update(slot.keys())
    print(f"  outer: {dict(outer)}")
    print(f"  broadcastOfEvent: {dict(inner)}")

    print("\n=== the channels it names ===")
    chans = Counter()
    for event in events:
        published = event.get("publishedOn")
        for entry in (published if isinstance(published, list)
                      else [published] if published else []):
            if isinstance(entry, dict):
                chans[entry.get("name") or "?"] += 1
    for name, n in chans.most_common(15):
        print(f"   {n:4d}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
