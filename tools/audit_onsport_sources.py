#!/usr/bin/env python3
"""Ask the three quiet sources directly what they are serving right now.

The audit of the published files raised three questions that only the
sources can answer:

  ON Sport   91% of its rows say "لا توجد مباراة مجدولة", above the 90%
             ceiling. Either a source stopped answering — the FilGoal
             failure again — or there is no Egyptian league football today.
  Tivibu     all four channels stop 4-5 hours ago while the eight beIN
             channels in the same file reach 24-67 hours ahead.
  Al Jadeed  a six-hour hole every night, 20:59 to 03:00, which is where
             "now" sits.
"""
from __future__ import annotations

import gzip
import io
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import requests  # noqa: E402
import update_onsport_epg as ON  # noqa: E402
import tivibu_spor_epg as TV  # noqa: E402

NOW = datetime.now(timezone.utc)


def onsport() -> None:
    print("=" * 70)
    print(f"ON SPORT   (now {NOW:%Y-%m-%d %H:%M} UTC)")
    try:
        html = ON.fetch(ON.LIVEFOOTBALLTV_HOME)
        print(f"  livefootballtv front page: HTTP ok, {len(html)} bytes")
    except Exception as exc:
        print(f"  livefootballtv front page: FAILED {exc}")
        return
    try:
        rows = ON.parse_lftv_home(html)
    except Exception as exc:
        print(f"  parse_lftv_home raised {exc}")
        return
    print(f"  -> {len(rows)} ON Sport rows parsed")
    for ev in rows[:20]:
        print(f"       {ev['start']:%Y-%m-%d %H:%M}  {ev.get('channel','?'):12} "
              f"{ev.get('title','')[:52]}")
    if not rows:
        print("       (the page answered and named no ON Sport match)")
    print(f"  FILGOAL_FEEDS = {ON.FILGOAL_FEEDS}  (retired in #95)")


def tivibu() -> None:
    print("=" * 70)
    print("TIVIBU SPOR")
    session = requests.Session()
    try:
        fresh = TV.fetch_feed(session, NOW)
    except Exception as exc:
        print(f"  epgshare01 TR3: FAILED {exc}")
        return
    total = sum(len(v) for v in fresh.values())
    print(f"  epgshare01 TR3 answered: {total} rows across "
          f"{len(fresh)} Tivibu channel(s)")
    for xid, rows in sorted(fresh.items()):
        rows = sorted(rows, key=lambda e: e["start"])
        last = rows[-1]["stop"]
        ahead = (last - NOW).total_seconds() / 3600
        print(f"    {xid:20} {len(rows):>4} rows  last stop {last:%m-%d %H:%M} "
              f"({ahead:+.1f}h from now)")
    if not fresh:
        print("    the feed answered and carried no Tivibu channel at all")


def aljadeed() -> None:
    print("=" * 70)
    print("AL JADEED — is the overnight hole ours or the source's?")
    try:
        import aljadeed_epg as AJ
    except Exception as exc:
        print(f"  cannot import aljadeed_epg: {exc}")
        return
    session = requests.Session()
    try:
        events = AJ.collect(session, "roya_jordan_epg.xml")
    except Exception as exc:
        print(f"  collect FAILED {exc}")
        return
    rows = sorted(events, key=lambda e: e["start"]) if isinstance(events, list) \
        else sorted((e for v in events.values() for e in v),
                    key=lambda e: e["start"])
    print(f"  collect returned {len(rows)} programmes")
    if not rows:
        return
    gaps = [(rows[i]["stop"], rows[i + 1]["start"]) for i in range(len(rows) - 1)
            if rows[i]["stop"] < rows[i + 1]["start"]]
    big = [(a, b) for a, b in gaps if b - a >= timedelta(hours=2)]
    print(f"  {len(gaps)} gaps, {len(big)} of them two hours or more:")
    for a, b in big[:6]:
        print(f"     {a:%m-%d %H:%M} -> {b:%m-%d %H:%M}  "
              f"({(b - a).total_seconds() / 3600:.1f}h)")


def main() -> int:
    for step in (onsport, tivibu, aljadeed):
        try:
            step()
        except Exception as exc:
            print(f"  {step.__name__} blew up: {exc}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
