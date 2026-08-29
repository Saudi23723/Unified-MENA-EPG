#!/usr/bin/env python3
"""Ask ON Sport's sources directly: is one dead, or is there simply no match?

The ceiling check says 91% of the guide is stand-in. That is either a
source that stopped answering — the FilGoal failure again — or a day with
no Egyptian league football in it. Only the sources can say which.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import update_onsport_epg as M  # noqa: E402


def main() -> int:
    print(f"NOW (Cairo) = {M.NOW}\n")

    checks = [
        ("LiveFootballTV home", M.LIVEFOOTBALLTV_HOME),
    ]
    for label, url in checks:
        try:
            html = M.fetch(url)
            print(f"{label:24} HTTP ok, {len(html)} bytes")
        except Exception as exc:
            print(f"{label:24} FAILED: {exc}")

    for name, fn in (("parse_lftv_home", None),):
        pass

    try:
        rows = M.parse_lftv_home(M.fetch(M.LIVEFOOTBALLTV_HOME))
        print(f"\nlivefootballtv front page -> {len(rows)} ON Sport rows")
        for ev in rows[:15]:
            print(f"   {ev['start']:%Y-%m-%d %H:%M}  {ev.get('channel')}  "
                  f"{ev.get('title')}")
    except Exception as exc:
        print(f"\nparse_lftv_home FAILED: {exc}")

    # And the whole pipeline, so the count matches what the guide would show.
    try:
        events = M.collect_events() if hasattr(M, "collect_events") else None
    except Exception as exc:
        events = None
        print(f"collect failed: {exc}")
    print(f"\nFILGOAL_FEEDS configured: {M.FILGOAL_FEEDS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
