#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Viaplay Denmark's sport guide, printed whole for the next three days.

Asked for a preview. So every block on the sport page is walked, every
product in it read, and the rows printed grouped by day — the clock in
Copenhagen's own zone, the title, and the channel where the feed names
one. One product is dumped whole first, because the channel field is
the one this project refuses to guess at and round two found it null on
the block it sampled.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, ".")

import requests

TIMEOUT = 15
COPENHAGEN = ZoneInfo("Europe/Copenhagen")
HEAD = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "da,en;q=0.8"}
ROOT = "https://content.viaplay.dk/pcdash-dk"


def products(block: dict) -> list:
    return ((block.get("_embedded") or {}).get("viaplay:products") or [])


def walk(session, url: str, seen: set) -> list[dict]:
    """Every product behind this page, following block links once."""
    out = []
    got = session.get(url, timeout=TIMEOUT)
    if got.status_code != 200:
        return out
    data = got.json()
    blocks = (data.get("_embedded") or {}).get("viaplay:blocks") or []
    if not blocks and (data.get("_embedded") or {}).get("viaplay:products"):
        blocks = [data]
    for block in blocks:
        items = products(block)
        title = block.get("title") or block.get("type") or "?"
        if items:
            print(f"    block {str(title)[:44]:<44} {len(items):>3} item(s)")
        out.extend(items)
        # a block that carries only a link to itself is followed once
        if not items:
            href = (((block.get("_links") or {}).get("self") or {})
                    .get("href") or "")
            if href and href not in seen and "viaplay" in href:
                seen.add(href)
                out.extend(walk(session, href, seen))
    return out


def field(item: dict, *path):
    node = item
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def main() -> int:
    session = requests.Session()
    session.headers.update(HEAD)

    print("=" * 72)
    print("ONE PRODUCT, WHOLE — to find where the channel is named")
    print("=" * 72)
    first = session.get(f"{ROOT}/sport", timeout=TIMEOUT).json()
    sample = None
    for block in (first.get("_embedded") or {}).get("viaplay:blocks") or []:
        items = products(block)
        if items:
            sample = items[0]
            break
    if sample:
        text = json.dumps(sample, ensure_ascii=False, indent=1)
        print(text[:2600])
        print(f"  ... ({len(text)} chars total)")

    print()
    print("=" * 72)
    print("THE GUIDE")
    print("=" * 72)
    every = walk(session, f"{ROOT}/sport", set())
    print(f"\n  {len(every)} product(s) gathered\n")

    rows = []
    for item in every:
        start = (field(item, "epg", "start")
                 or field(item, "system", "availability", "start"))
        if not start:
            continue
        try:
            when = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        except ValueError:
            continue
        rows.append({
            "start": when.astimezone(COPENHAGEN),
            "title": field(item, "content", "title") or "?",
            "sub": (field(item, "content", "series", "title")
                    or field(item, "content", "format", "title") or ""),
            "channel": (field(item, "epg", "channel")
                        or field(item, "content", "channel")
                        or field(item, "epg", "channelName") or ""),
            "sport": (field(item, "content", "categories") or
                      field(item, "content", "sport") or ""),
        })
    rows.sort(key=lambda r: r["start"])

    today = datetime.now(COPENHAGEN).date()
    for step in range(0, 3):
        day = today + timedelta(days=step)
        here = [r for r in rows if r["start"].date() == day]
        print(f"\n  ---- {day:%A %d.%m.%Y} — {len(here)} broadcast(s) ----")
        for r in here:
            chan = f"  [{r['channel']}]" if r["channel"] else "  [no channel named]"
            extra = f"  ({r['sub']})" if r["sub"] else ""
            print(f"    {r['start']:%H:%M}  {r['title'][:52]:<52}{extra}{chan}")
    outside = [r for r in rows if not (today <= r["start"].date()
                                       <= today + timedelta(days=2))]
    print(f"\n  {len(outside)} row(s) outside the three days")
    named = sum(1 for r in rows if r["channel"])
    print(f"  {named} of {len(rows)} row(s) name a channel")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
