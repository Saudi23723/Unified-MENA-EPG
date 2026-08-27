#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check that every Live badge on beIN Türkiye came from the broadcaster.

The badge is only as good as what stands behind it. tvyayinakisi is beIN
publishing its own listing and marking its own programmes "Canlı"; the
two aggregated feeds are neither, and this file already holds the proof
they cannot be trusted at that resolution.

So: build, then for every badged programme confirm the broadcaster's
listing is where it came from. A badge traceable to no such entry is a
failure, whatever it says about itself.

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


def main() -> int:
    work = tempfile.mkdtemp()
    here = os.getcwd()
    for name in os.listdir(here):
        if name.endswith(".py"):
            shutil.copy(os.path.join(here, name), work)
    os.chdir(work)

    import bein_sports_turkey_epg as g
    from epg_lib import new_session, utc_now

    print("--- build ---")
    g.build()
    built = ET.parse(g.OUTPUT).getroot()

    # What the broadcaster itself published, fetched again so the check
    # does not lean on the build's own bookkeeping.
    session = new_session()
    now = utc_now()
    broadcaster: dict[str, set] = {}
    for ch in g.CHANNELS:
        if not ch["slug"]:
            continue
        try:
            evs = g.fetch_tvy_channel(session, ch["slug"], now)
        except Exception as exc:
            print(f"  {ch['name']}: tvyayinakisi unavailable ({exc})")
            evs = []
        broadcaster[g.slugify_id(ch["name"])] = {
            (e["start"], e["title"]) for e in evs if e["live"]
        }
    os.chdir(here)

    badged, unbacked = [], []
    for programme in built.findall("programme"):
        title = programme.findtext("title") or ""
        if "🔵" not in title:
            continue
        cid = programme.get("channel")
        start = datetime.strptime(programme.get("start"), "%Y%m%d%H%M%S %z")
        badged.append((cid, start, title))
        bare = title.split("‎•")[0].strip()
        if not any(s == start and t == bare for s, t in broadcaster.get(cid, ())):
            unbacked.append((cid, start, title))

    print(f"\n{len(badged)} programme(s) badged Live")
    for cid, start, title in sorted(badged, key=lambda r: r[1]):
        print(f"    {cid:<20} {start.astimezone(TR):%m-%d %H:%M}  {title}")

    print(f"\nbadges with no matching 'Canlı' entry in the broadcaster's "
          f"listing: {len(unbacked)}  {'OK' if not unbacked else 'FAILURE'}")
    for row in unbacked:
        print(f"    {row}")

    channels = {c for c, _s, _t in badged}
    print(f"\nchannels carrying a badge: {sorted(channels) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
