#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the beIN Türkiye guide on the runner and show what the four
sources together produce.

Two things are being checked. Depth: beIN SPORTS 1 and MAX 1 and 2 used
to stop at the end of the current day, and beIN SPORTS 5 was not
published. And naming: MAX 1 and MAX 2 were filled with eleven blocks a
day each titled with the channel's own name, which a named fixture from
Spor Ekranı should now displace where one exists.

So it prints the day-by-day counts for the published file and the built
one side by side, then the MAX timelines in full, where the difference is
meant to show.

Builds into a scratch directory and commits nothing.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TR = timezone(timedelta(hours=3))
PUBLISHED = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG"
             "/main/bein_sports_turkey_epg.xml")
SHOW_IN_FULL = ("beINSPORTSMAX1.tr", "beINSPORTSMAX2.tr")


def matrix(root: ET.Element):
    names = {c.get("id"): (c.findtext("display-name") or "")
             for c in root.findall("channel")}
    per = defaultdict(lambda: defaultdict(int))
    for programme in root.findall("programme"):
        try:
            day = datetime.strptime(programme.get("start"),
                                    "%Y%m%d%H%M%S %z").astimezone(TR).date()
        except Exception:
            continue
        per[programme.get("channel")][day] += 1
    days = sorted({d for v in per.values() for d in v})
    return names, days, per


def show(label: str, root: ET.Element) -> None:
    names, days, per = matrix(root)
    print(f"\n{label}: {len(names)} channels, "
          f"{len(root.findall('programme'))} programmes")
    print("  " + "channel".ljust(22) + "".join(str(d)[5:].rjust(7) for d in days))
    for cid in names:
        print("  " + cid.ljust(22)
              + "".join(str(per[cid].get(d, 0)).rjust(7) for d in days))


def timeline(label: str, root: ET.Element, cid: str) -> None:
    rows = []
    for programme in root.findall("programme"):
        if programme.get("channel") != cid:
            continue
        try:
            start = datetime.strptime(programme.get("start"),
                                      "%Y%m%d%H%M%S %z").astimezone(TR)
            stop = datetime.strptime(programme.get("stop"),
                                     "%Y%m%d%H%M%S %z").astimezone(TR)
        except Exception:
            continue
        rows.append((start, stop, programme.findtext("title") or ""))
    rows.sort()
    print(f"\n  {label} — {cid} ({len(rows)} programmes), first day:")
    if not rows:
        print("      (none)")
        return
    first = rows[0][0].date()
    for start, stop, title in rows:
        if start.date() != first:
            break
        minutes = round((stop - start).total_seconds() / 60)
        print(f"      {start:%m-%d %H:%M} {minutes:>4}min  {title[:52]}")


def main() -> int:
    print(f"beIN Türkiye — published vs. this working tree | "
          f"today={datetime.now(TR).date()} (TR)")

    published = ET.fromstring(requests.get(PUBLISHED, timeout=60).content)
    show("PUBLISHED on main", published)

    work = tempfile.mkdtemp()
    here = os.getcwd()
    for name in os.listdir(here):
        if name.endswith(".py"):
            shutil.copy(os.path.join(here, name), work)
    os.chdir(work)

    import bein_sports_turkey_epg as generator
    print("\n--- build ---")
    generator.build()
    built = ET.parse(generator.OUTPUT).getroot()
    os.chdir(here)
    show("BUILT here", built)

    for cid in SHOW_IN_FULL:
        timeline("PUBLISHED", published, cid)
        timeline("BUILT", built, cid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
