#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Is epgshare's Alkass worth trusting where alkass.net has nothing?

Settled by the first pass: alkass.net's own grid publishes one schedule
across three channels — 1=4=8, 2=5=7, 3=6 — and serves the identical
page for ?day=next. The parser reads it correctly; the source is what is
wrong, and it has exactly one day.

epgshare's UAE feed carries Alkass One HD, Two HD, Three and Four with
four days each. Four days beats one, and separate schedules beat one
schedule three times over — if the data is right.

Today is how that is tested. Both describe it, so they can be compared
programme by programme: if epgshare agrees with the broadcaster on the
day both cover, its other three days are worth having. If it disagrees,
it is a different channel wearing the same name and must not be used.

The clock is checked the same way, because epgshare stamps +0300 in its
Turkish feed and open-epg stamps Istanbul time as +0000 in its own — a
mistake this project has already paid for once.

Reads only; writes nothing.
"""

from __future__ import annotations

import gzip
import io
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import alkass_epg as g  # noqa: E402

DOHA = timezone(timedelta(hours=3))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/127.0 Safari/537.36")
AE1 = "https://epgshare01.online/epgshare01/epg_ripper_AE1.xml.gz"

# epgshare's name for each Alkass number, as its channel list spells them.
SHARE_IDS = {
    1: "Alkass.One.HD.ae",
    2: "Alkass.Two.HD.ae",
    3: "Alkass.Three.ae",
    4: "Alkass.Four.ae",
}


def main() -> int:
    session = requests.Session()

    # --- the broadcaster, for today -------------------------------------
    page = session.get(g.BASE, timeout=45, headers={"User-Agent": UA}).text
    theirs = g.parse_page(page)
    today = datetime.now(DOHA)
    official: dict[int, list[dict]] = {
        n: g.to_datetimes(rows, today) for n, rows in theirs.items()}
    print("alkass.net today:",
          {n: len(v) for n, v in sorted(official.items())})

    # --- epgshare -------------------------------------------------------
    raw = session.get(AE1, timeout=60, headers={"User-Agent": UA}).content
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    root = ET.parse(io.BytesIO(raw)).getroot()

    share: dict[int, list[dict]] = defaultdict(list)
    for p in root.findall("programme"):
        for number, cid in SHARE_IDS.items():
            if p.get("channel") != cid:
                continue
            try:
                s = datetime.strptime(p.get("start"), "%Y%m%d%H%M%S %z")
                e = datetime.strptime(p.get("stop"), "%Y%m%d%H%M%S %z")
            except Exception:
                continue
            share[number].append(
                {"start": s, "stop": e, "title": (p.findtext("title") or "").strip()})
    print("epgshare AE1  :",
          {n: len(v) for n, v in sorted(share.items())})
    offs = Counter(p.get("start")[15:] for p in root.findall("programme")
                   if p.get("channel") in SHARE_IDS.values())
    print("offsets epgshare declares for Alkass:", dict(offs))

    print("\n--- days each source covers, Doha time ---")
    for n in sorted(SHARE_IDS):
        od = sorted({e["start"].astimezone(DOHA).date() for e in official.get(n, [])})
        sd = sorted({e["start"].astimezone(DOHA).date() for e in share.get(n, [])})
        print(f"  Alkass {n}:  alkass.net {[str(d) for d in od]}")
        print(f"             epgshare   {[str(d) for d in sd]}")

    print("\n--- do they agree on today? (title match at the same start) ---")
    for n in sorted(SHARE_IDS):
        mine = {(e["start"], e["title"].strip().lower()) for e in official.get(n, [])}
        starts_mine = {e["start"]: e["title"] for e in official.get(n, [])}
        same_day = [e for e in share.get(n, [])
                    if e["start"].astimezone(DOHA).date() == today.date()]
        exact = sum(1 for e in same_day
                    if (e["start"], e["title"].strip().lower()) in mine)
        shared_start = [e for e in same_day if e["start"] in starts_mine]
        print(f"  Alkass {n}: epgshare has {len(same_day)} rows today, "
              f"{len(shared_start)} start at the same minute, "
              f"{exact} of those have the same title")
        for e in shared_start[:3]:
            print(f"      {e['start'].astimezone(DOHA):%H:%M}  "
                  f"epgshare={e['title'][:30]:<30} alkass={starts_mine[e['start']][:30]}")

    print("\n--- what epgshare actually says, Alkass 1, first day ---")
    rows = sorted(share.get(1, []), key=lambda e: e["start"])
    for e in rows[:14]:
        mins = round((e["stop"] - e["start"]).total_seconds() / 60)
        print(f"  {e['start'].astimezone(DOHA):%m-%d %H:%M} {mins:>4}min  {e['title'][:52]}")
    distinct = len({e["title"] for e in rows})
    print(f"  distinct titles: {distinct} of {len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
