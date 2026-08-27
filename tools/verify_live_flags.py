#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prove the Spor Ekranı live flags change flags and nothing else.

The whole safety of this rests on one property: it may set a flag, and it
may not schedule. An earlier attempt to schedule from the same site
removed a placeholder and left an hour of nothing, so this time the
property is asserted rather than intended.

Builds twice from the same working tree, once with the flags suppressed
and once with them, and compares. Every programme must be identical in
channel, start, stop and title; only the badge may differ, and only by
appearing.

Builds into a scratch directory and commits nothing.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TR = timezone(timedelta(hours=3))
BADGE = "🔵"


def shape(root: ET.Element) -> dict:
    """Every programme by identity, with the badge stripped from the title."""
    out = {}
    for programme in root.findall("programme"):
        title = programme.findtext("title") or ""
        bare = title.split("‎•")[0].strip()
        out[(programme.get("channel"), programme.get("start"),
             programme.get("stop"), bare)] = BADGE in title
    return out


def main() -> int:
    work = tempfile.mkdtemp()
    here = os.getcwd()
    for name in os.listdir(here):
        if name.endswith(".py"):
            shutil.copy(os.path.join(here, name), work)
    os.chdir(work)

    import bein_sports_turkey_epg as g

    real = g.fetch_live_windows
    g.fetch_live_windows = lambda session, now: {}
    print("--- build WITHOUT Spor Ekranı flags ---")
    g.build()
    without = shape(ET.parse(g.OUTPUT).getroot())

    g.fetch_live_windows = real
    print("\n--- build WITH Spor Ekranı flags ---")
    g.build()
    with_flags = shape(ET.parse(g.OUTPUT).getroot())
    os.chdir(here)

    print("\n--- checks ---")
    same_set = set(without) == set(with_flags)
    print(f"  identical programmes (channel, start, stop, title): "
          f"{len(without)} vs {len(with_flags)}  "
          f"{'OK' if same_set else 'FAILURE — scheduling changed'}")
    if not same_set:
        for row in list(set(without) ^ set(with_flags))[:5]:
            print(f"      {row}")
        return 1

    lost = [k for k in without if without[k] and not with_flags[k]]
    gained = [k for k in without if not without[k] and with_flags[k]]
    print(f"  badges removed: {len(lost)}  {'OK' if not lost else 'FAILURE'}")
    print(f"  badges added  : {len(gained)}")
    for channel, start, _stop, title in gained:
        when = datetime.strptime(start, "%Y%m%d%H%M%S %z").astimezone(TR)
        print(f"      {channel:<20} {when:%m-%d %H:%M}  {title[:44]}")
    return 0 if not lost else 1


if __name__ == "__main__":
    sys.exit(main())
