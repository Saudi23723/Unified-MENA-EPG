#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the Tivibu Spor guide on the runner and show what it produced.

The feed is only reachable from inside the countries it serves, so this
is the only place the generator can be run at all before it is merged.
Prints the per-channel day coverage and the first day in full, so both
the reach and the content can be read rather than assumed.

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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TR = timezone(timedelta(hours=3))


def main() -> int:
    print(f"Tivibu Spor — first build | today={datetime.now(TR).date()} (TR)\n")

    work = tempfile.mkdtemp()
    here = os.getcwd()
    for name in os.listdir(here):
        if name.endswith(".py"):
            shutil.copy(os.path.join(here, name), work)
    os.chdir(work)

    import tivibu_spor_epg as generator
    generator.build()
    root = ET.parse(generator.OUTPUT).getroot()
    os.chdir(here)

    names = {c.get("id"): [d.text for d in c.findall("display-name")]
             for c in root.findall("channel")}
    per = defaultdict(lambda: defaultdict(int))
    for programme in root.findall("programme"):
        day = datetime.strptime(programme.get("start"),
                                "%Y%m%d%H%M%S %z").astimezone(TR).date()
        per[programme.get("channel")][day] += 1
    days = sorted({d for v in per.values() for d in v})

    print(f"\n{len(names)} channels, {len(root.findall('programme'))} programmes")
    print("  " + "channel".ljust(18) + "".join(str(d)[5:].rjust(7) for d in days))
    for cid in names:
        print("  " + cid.ljust(18)
              + "".join(str(per[cid].get(d, 0)).rjust(7) for d in days))

    print("\ndisplay names published:")
    for cid, ns in names.items():
        print(f"  {cid:<16} {ns}")

    for cid in list(names)[:2]:
        rows = sorted(
            (datetime.strptime(p.get("start"), "%Y%m%d%H%M%S %z").astimezone(TR),
             datetime.strptime(p.get("stop"), "%Y%m%d%H%M%S %z").astimezone(TR),
             p.findtext("title") or "")
            for p in root.findall("programme") if p.get("channel") == cid)
        print(f"\n  {cid} — first day:")
        if not rows:
            continue
        first = rows[0][0].date()
        for start, stop, title in rows:
            if start.date() != first:
                break
            print(f"      {start:%m-%d %H:%M} "
                  f"{round((stop - start).total_seconds() / 60):>4}min  {title[:50]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
