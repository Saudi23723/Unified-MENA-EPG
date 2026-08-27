#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the tabii guide on the runner and check the standing notice.

Three things have to hold, and none of them can be checked from outside
the countries the sources serve:

  the linear channel is untouched — TRT schedules it a week out and it
  must never be given a notice
  no notice overlaps a real fixture — a named match always wins
  every PPV number is covered end to end, so no "No information" is left

Prints the published file beside the built one, then one PPV channel in
full so the two kinds of entry can be read side by side.

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
             "/main/tabii_spor_1_10_epg.xml")


def rows(root: ET.Element, cid: str):
    out = []
    for programme in root.findall("programme"):
        if programme.get("channel") != cid:
            continue
        out.append((
            datetime.strptime(programme.get("start"), "%Y%m%d%H%M%S %z"),
            datetime.strptime(programme.get("stop"), "%Y%m%d%H%M%S %z"),
            programme.findtext("title") or "",
        ))
    return sorted(out)


def day_matrix(label: str, root: ET.Element) -> None:
    names = [c.get("id") for c in root.findall("channel")]
    per = defaultdict(lambda: defaultdict(int))
    for programme in root.findall("programme"):
        day = datetime.strptime(programme.get("start"),
                                "%Y%m%d%H%M%S %z").astimezone(TR).date()
        per[programme.get("channel")][day] += 1
    days = sorted({d for v in per.values() for d in v})
    print(f"\n{label}: {len(names)} channels, "
          f"{len(root.findall('programme'))} programmes")
    print("  " + "channel".ljust(18) + "".join(str(d)[5:].rjust(6) for d in days))
    for cid in names:
        print("  " + cid.ljust(18)
              + "".join(str(per[cid].get(d, 0)).rjust(6) for d in days))


def main() -> int:
    published = ET.fromstring(requests.get(PUBLISHED, timeout=60).content)
    day_matrix("PUBLISHED on main", published)

    work = tempfile.mkdtemp()
    here = os.getcwd()
    for name in os.listdir(here):
        if name.endswith(".py"):
            shutil.copy(os.path.join(here, name), work)
    # The PPV rows accumulate from the file already published, so the
    # build needs it there to carry forward from.
    shutil.copy(os.path.join(here, "tabii_spor_1_10_epg.xml"), work)
    os.chdir(work)

    import update_tabii_epg as generator
    print("\n--- build ---")
    generator.build()
    built = ET.parse(generator.OUTPUT).getroot()
    os.chdir(here)
    day_matrix("BUILT here", built)

    notice = generator.STAND_IN_TITLE
    print("\n--- checks ---")

    linear = [t for _s, _e, t in rows(built, "TabiiSpor.tr") if t == notice]
    print(f"  notices on the linear channel  : {len(linear)}  "
          f"{'OK' if not linear else 'WRONG — it must never get one'}")

    bad_overlap = []
    uncovered = []
    for number in generator.PPV_NUMBERS:
        cid = generator.channel_id(number)
        entries = rows(built, cid)
        real = [(s, e) for s, e, t in entries if t != notice]
        for start, stop, title in entries:
            if title != notice:
                continue
            if any(start < e and s < stop for s, e in real):
                bad_overlap.append((cid, start, title))
        for a, b in zip(entries, entries[1:]):
            if a[1] < b[0]:
                uncovered.append((cid, a[1], b[0]))

    print(f"  notices overlapping a fixture  : {len(bad_overlap)}  "
          f"{'OK' if not bad_overlap else 'WRONG'}")
    for row in bad_overlap[:3]:
        print(f"      {row}")
    print(f"  gaps left on a PPV channel     : {len(uncovered)}  "
          f"{'OK' if not uncovered else 'gaps remain'}")
    for cid, a, b in uncovered[:3]:
        print(f"      {cid} {a.astimezone(TR):%m-%d %H:%M} .. "
              f"{b.astimezone(TR):%m-%d %H:%M}")

    for number in generator.PPV_NUMBERS:
        cid = generator.channel_id(number)
        entries = rows(built, cid)
        if any(t != notice for _s, _e, t in entries):
            print(f"\n--- {cid}, first day (a channel with real fixtures) ---")
            first = entries[0][0].astimezone(TR).date()
            for start, stop, title in entries:
                if start.astimezone(TR).date() != first:
                    break
                kind = "notice" if title == notice else "FIXTURE"
                print(f"   {start.astimezone(TR):%m-%d %H:%M}"
                      f"-{stop.astimezone(TR):%H:%M} [{kind:>7}] {title[:44]}")
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
