#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build beIN Türkiye and count what the self-contradiction pass removed.

Two things have to be true. Nonsense has to go: a fixture given nine
minutes because a six-minute item was listed inside it. And nothing real
may go with it — the eight-hour blocks the feed also publishes swallow
genuine matches, and a rule that dropped whatever they contain would
delete those and keep the junk.

So this prints what the pass removed, then every fixture the finished
guide gives less than half an hour, published beside built.

Builds into a scratch directory and commits nothing.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TR = timezone(timedelta(hours=3))
PUBLISHED = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG"
             "/main/bein_sports_turkey_epg.xml")


def short_fixtures(root: ET.Element) -> list[tuple]:
    """Anything that reads as a fixture and is given under half an hour."""
    out = []
    for programme in root.findall("programme"):
        title = programme.findtext("title") or ""
        if " - " not in title or len(title) > 60:
            continue
        start = datetime.strptime(programme.get("start"), "%Y%m%d%H%M%S %z")
        stop = datetime.strptime(programme.get("stop"), "%Y%m%d%H%M%S %z")
        minutes = round((stop - start).total_seconds() / 60)
        if minutes < 30:
            out.append((programme.get("channel"),
                        start.astimezone(TR), minutes, title))
    return sorted(out, key=lambda r: r[2])


def main() -> int:
    published = ET.fromstring(requests.get(PUBLISHED, timeout=60).content)

    work = tempfile.mkdtemp()
    here = os.getcwd()
    for name in os.listdir(here):
        if name.endswith(".py"):
            shutil.copy(os.path.join(here, name), work)
    os.chdir(work)
    import bein_sports_turkey_epg as generator
    print("--- build ---")
    generator.build()
    built = ET.parse(generator.OUTPUT).getroot()
    os.chdir(here)

    for label, root in (("PUBLISHED", published), ("BUILT", built)):
        rows = short_fixtures(root)
        print(f"\n{label}: {len(root.findall('programme'))} programmes, "
              f"{len(rows)} fixture(s) under 30 minutes")
        for channel, start, minutes, title in rows[:12]:
            print(f"    {channel:<20} {start:%m-%d %H:%M} {minutes:>3}min  "
                  f"{title[:40]}")

    # Nothing real may have been lost: every channel must still carry at
    # least what it did before.
    def per_channel(root):
        out = {}
        for programme in root.findall("programme"):
            out[programme.get("channel")] = out.get(programme.get("channel"), 0) + 1
        return out

    before, after = per_channel(published), per_channel(built)
    print("\nprogrammes per channel, published -> built:")
    for cid in sorted(set(before) | set(after)):
        b, a = before.get(cid, 0), after.get(cid, 0)
        print(f"    {cid:<22} {b:>4} -> {a:>4}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
