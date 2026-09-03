#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Does an NFL.com game carry a machine-readable time, or only a clock?

The American half is answered. nfl.com/schedules renders every game as
one complete line in its screen-reader text — the most stable part of any
page, because accessibility labels are the last thing anybody rewrites:

    Patriots at Seahawks, Wednesday, September 9th, 8:20 PM, NBC
    49ers at Rams, Thursday, September 10th, 8:35 PM, NETFLIX
    Bears at Panthers, Sunday, September 13th, 1:00 PM, FOX

Teams, weekday, date, time and the NETWORK. cbssports.com/nfl/schedule
works too, in cells: "8:20 pm | NBC".

One thing is missing from that line and it is the one that has cost this
project most: 8:20 PM in WHAT timezone. A printed clock with no offset is
exactly what put every match an hour late once and a whole day out
another time, and nfl.com may well render in the reader's own zone, which
on a runner is UTC and on a television is not.

So before a line of the reader is written: does the row carry a
timestamp — a datetime attribute, a data- field, an epoch — or is the
printed clock all there is? If it is all there is, the timezone becomes a
named assumption with a gate, the way Amman is in jordan_football.
"""
from __future__ import annotations

import re
import sys

sys.path.insert(0, ".")

from bs4 import BeautifulSoup                                  # noqa: E402
from epg_lib import new_session, norm                          # noqa: E402

SOURCE = "https://www.nfl.com/schedules/"
A_LINE = re.compile(r"\bat\b.*,.*\d{1,2}:\d{2}\s?[AP]M", re.I)


def main() -> int:
    session = new_session()
    page = session.get(SOURCE, timeout=30).text
    print(f"nfl.com/schedules — {len(page)} bytes")

    # An ISO instant anywhere in the page at all?
    iso = re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[Z+\-][\d:]*",
                     page)
    print(f"ISO-8601 timestamps in the raw page: {len(iso)}")
    for stamp in iso[:6]:
        print(f"    {stamp}")

    epochs = re.findall(r'"(?:startTime|gameTime|kickoff|utc[A-Za-z]*)"'
                        r'\s*:\s*"?([^",}]{4,40})', page)
    print(f"time-ish JSON fields: {len(epochs)}")
    for value in epochs[:6]:
        print(f"    {value}")

    soup = BeautifulSoup(page, "html.parser")
    print("\n=== the block around one game ===")
    shown = 0
    for node in soup.find_all(string=A_LINE):
        holder = node.parent
        for _ in range(4):
            if holder is None:
                break
            print(f"  <{holder.name} class="
                  f"{' '.join(holder.get('class') or []) or '-'}>")
            for attribute, value in list(holder.attrs.items()):
                if attribute in ("class",):
                    continue
                print(f"      {attribute}={str(value)[:90]}")
            for stamp in holder.find_all("time"):
                print(f"      <time datetime={stamp.get('datetime')!r}>")
            holder = holder.parent
        print(f"  line: {norm(str(node))[:120]}")
        shown += 1
        if shown >= 2:
            break
    if not shown:
        print("  no line matched — the shape has changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
