#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Is open-epg's Qatar file better than the blurb beIN publishes?

beIN's own API answers for MAX 1-6 and XTRA 1-9, but every row carries
the same sentence — a channel filling its grid with one line about
itself. open-epg's qatar1 file holds different rows for the same
channels, 23 to 52 of them each.

Two questions decide whether that is worth reading, and neither may be
assumed:

  what is in it   real programme titles, or the same kind of blurb in
                  another wrapper
  what clock      open-epg stamps Istanbul wall-clock and labels it
                  +0000 in its Turkish file, which cost this project a
                  three-hour error caught only by comparison. The Qatar
                  file gets the same suspicion until it is measured.

The clock is measured against beIN's own API on a channel both describe,
which is the only comparison that settles it.

Reads only; writes nothing.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import requests

AST = timezone(timedelta(hours=3))
NOW = datetime.now(timezone.utc)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/127.0 Safari/537.36")
QATAR = "https://www.open-epg.com/files/qatar1.xml"
PUBLISHED = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG"
             "/main/bein_sports_qatar_epg.xml")


def main() -> int:
    session = requests.Session()
    open_root = ET.fromstring(
        session.get(QATAR, timeout=60, headers={"User-Agent": UA}).content)
    ours = ET.fromstring(
        session.get(PUBLISHED, timeout=60, headers={"User-Agent": UA}).content)

    print("=" * 72)
    print("1. Every channel open-epg's Qatar file carries")
    print("=" * 72)
    counts = Counter(p.get("channel") for p in open_root.findall("programme"))
    for c in open_root.findall("channel"):
        cid = c.get("id")
        print(f"  {cid:<34} {counts.get(cid, 0):>4} progs")

    print("\n" + "=" * 72)
    print("2. What it actually says — MAX 1 and XTRA 2, first day")
    print("=" * 72)
    for want in ("beIN SPORTS MAX 1.qa", "beIN SPORTS XTRA 2.qa"):
        rows = sorted(
            (datetime.strptime(p.get("start"), "%Y%m%d%H%M%S %z"),
             datetime.strptime(p.get("stop"), "%Y%m%d%H%M%S %z"),
             p.findtext("title") or "")
            for p in open_root.findall("programme") if p.get("channel") == want)
        print(f"\n  --- open-epg: {want} ({len(rows)} rows) ---")
        for s, e, t in rows[:10]:
            mins = round((e - s).total_seconds() / 60)
            print(f"      {s.astimezone(AST):%m-%d %H:%M} {mins:>4}min  {t[:52]}")
        distinct = len({t for _s, _e, t in rows})
        print(f"      distinct titles: {distinct} of {len(rows)}")

    print("\n  --- ours, from beIN's own API, same channels ---")
    for want in ("beINSportsMax1.qa", "beINSportsXtra2.qa"):
        rows = sorted(
            (datetime.strptime(p.get("start"), "%Y%m%d%H%M%S %z"),
             p.findtext("title") or "")
            for p in ours.findall("programme") if p.get("channel") == want)
        distinct = len({t for _s, t in rows})
        print(f"\n      {want}: {len(rows)} rows, {distinct} distinct title(s)")
        for s, t in rows[:4]:
            print(f"        {s.astimezone(AST):%m-%d %H:%M}  {t[:60]}")

    print("\n" + "=" * 72)
    print("3. The clock — open-epg against beIN's own API")
    print("=" * 72)
    offs = Counter(p.get("start")[15:] for p in open_root.findall("programme"))
    print(f"  offsets open-epg declares: {dict(offs)}")

    # A channel both describe, matched on titles that occur once on each side.
    pairs = [("beIN SPORTS XTRA 1.qa", "beINSportsXtra1.qa"),
             ("beIN SPORTS MAX 1.qa", "beINSportsMax1.qa")]
    for oid, mid in pairs:
        theirs = defaultdict(list)
        for p in open_root.findall("programme"):
            if p.get("channel") == oid:
                theirs[(p.findtext("title") or "").strip().lower()].append(
                    datetime.strptime(p.get("start"), "%Y%m%d%H%M%S %z"))
        mine = defaultdict(list)
        for p in ours.findall("programme"):
            if p.get("channel") == mid:
                mine[(p.findtext("title") or "").strip().lower()].append(
                    datetime.strptime(p.get("start"), "%Y%m%d%H%M%S %z"))
        shared = [t for t in theirs
                  if len(theirs[t]) == 1 and len(mine.get(t, [])) == 1]
        if not shared:
            print(f"  {oid}: no title occurs once on both sides — cannot compare")
            continue
        deltas = Counter(round((theirs[t][0] - mine[t][0]).total_seconds() / 60)
                         for t in shared)
        verdict = ("SAME CLOCK" if set(deltas) == {0} else
                   "CONSTANT OFFSET" if len(deltas) == 1 else "no single offset")
        print(f"  {oid}: {len(shared)} unique shared title(s) -> {verdict} "
              f"{deltas.most_common(4)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
