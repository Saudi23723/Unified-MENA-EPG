#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What an F1 channel could actually be fed with.

Half of it — the race listings — this project already has: F1 sessions
with their broadcasters arrive on world_sport_on_tv and the Turkish
grid, and "F1" is already a sport both boards rank. What has no source
here is the OTHER half: the standings, the session results, the weather
at the circuit, the state of the session on now.

So the four candidates are asked directly and what each answers is
printed — not counted, printed, because the question is whether the
fields a board needs are in there.
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, ".")

import requests

TIMEOUT = 12
HEAD = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

TARGETS = [
    # ESPN — the family this repo already reads for MLB, NBA and the WNBA
    ("ESPN scoreboard",
     "https://site.web.api.espn.com/apis/site/v2/sports/racing/f1/scoreboard"),
    ("ESPN standings",
     "https://site.api.espn.com/apis/v2/sports/racing/f1/standings"),
    ("ESPN calendar",
     "https://site.api.espn.com/apis/site/v2/sports/racing/f1/scoreboard"),
    # OpenF1 — a public live-timing service
    ("OpenF1 sessions",  "https://api.openf1.org/v1/sessions?year=2026"),
    ("OpenF1 meetings",  "https://api.openf1.org/v1/meetings?year=2026"),
    ("OpenF1 weather",   "https://api.openf1.org/v1/weather?session_key=latest"),
    ("OpenF1 position",  "https://api.openf1.org/v1/position?session_key=latest"),
    # Jolpica — what took over from Ergast when it froze
    ("Jolpica season",   "https://api.jolpi.ca/ergast/f1/current.json"),
    ("Jolpica standings",
     "https://api.jolpi.ca/ergast/f1/current/driverStandings.json"),
    ("Jolpica last race",
     "https://api.jolpi.ca/ergast/f1/current/last/results.json"),
]


def show(data, depth: int = 0, limit: int = 1400) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=1)
    print("    " + text[:limit].replace("\n", "\n    "))
    if len(text) > limit:
        print(f"    ... ({len(text)} chars)")


def main() -> int:
    session = requests.Session()
    session.headers.update(HEAD)
    for name, url in TARGETS:
        print("\n" + "=" * 72)
        print(f"{name}\n  {url}")
        try:
            got = session.get(url, timeout=TIMEOUT)
        except Exception as exc:                              # noqa: BLE001
            print(f"  UNREACHABLE  {type(exc).__name__}: {str(exc)[:110]}")
            continue
        print(f"  {got.status_code}  {len(got.text):>9} bytes  "
              f"{got.headers.get('content-type','')[:34]}")
        if got.status_code != 200:
            continue
        try:
            data = got.json()
        except Exception:                                     # noqa: BLE001
            print("  not JSON")
            continue
        if isinstance(data, list):
            print(f"  a list of {len(data)}")
            if data:
                show(data[0])
        elif isinstance(data, dict):
            print(f"  keys: {list(data)[:12]}")
            # the one branch worth seeing whole
            for key in ("events", "children", "MRData", "standings"):
                if key in data:
                    node = data[key]
                    if isinstance(node, list) and node:
                        print(f"  {key}: {len(node)} — first one:")
                        show(node[0])
                    elif isinstance(node, dict):
                        print(f"  {key}:")
                        show(node)
                    break
            else:
                show(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
