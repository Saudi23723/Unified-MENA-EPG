#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the beIN Türkiye guide here on the runner and show what changed.

The point of the change under test is depth: beIN SPORTS 1 and MAX 1/2
ran out at the end of the current day, and beIN SPORTS 5 was not
published at all. This prints a day-by-day count per channel for the file
as published on main and for the file this working tree produces, so the
two can be read side by side instead of taken on trust.

Writes the guide into a scratch directory, never over the repository's
own copy, and commits nothing.
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


def matrix(root: ET.Element) -> tuple[dict, list, dict]:
    names = {c.get("id"): (c.findtext("display-name") or "")
             for c in root.findall("channel")}
    per: dict = defaultdict(lambda: defaultdict(int))
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


def main() -> int:
    today = datetime.now(TR).date()
    print(f"beIN Türkiye — published vs. this working tree | today={today} (TR)")

    published = ET.fromstring(requests.get(PUBLISHED, timeout=60).content)
    show("PUBLISHED on main", published)

    # Build into a scratch directory so the repository copy is untouched.
    work = tempfile.mkdtemp()
    here = os.getcwd()
    for name in os.listdir(here):
        if name.endswith(".py"):
            shutil.copy(os.path.join(here, name), work)
    os.chdir(work)

    import bein_sports_turkey_epg as generator
    print("\n--- build ---")
    code = generator.build()
    print(f"--- build returned {code} ---")

    built = ET.parse(generator.OUTPUT).getroot()
    os.chdir(here)
    show("BUILT here", built)

    names, days, _ = matrix(built)
    ahead = [d for d in days if d > today]
    print(f"\ndays past today in the new build: {[str(d) for d in ahead]}")
    print(f"channels in the new build: {sorted(names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
