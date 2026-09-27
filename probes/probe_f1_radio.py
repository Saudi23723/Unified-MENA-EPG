#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Team radio, and everything else a live F1 board could say.

Asked whether the live radio is there. OpenF1 publishes team radio as
recordings, and beside it the things that actually change during a
session — the flags and safety cars from race control, the gaps, the
laps, the pit stops and the tyres on the car. Each is asked once and
what it answers is printed whole.
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, ".")

import requests

TIMEOUT = 12
BASE = "https://api.openf1.org/v1"

TARGETS = [
    ("team radio",   f"{BASE}/team_radio?session_key=latest"),
    ("race control", f"{BASE}/race_control?session_key=latest"),
    ("intervals",    f"{BASE}/intervals?session_key=latest"),
    ("laps",         f"{BASE}/laps?session_key=latest&lap_number=1"),
    ("pit stops",    f"{BASE}/pit?session_key=latest"),
    ("stints",       f"{BASE}/stints?session_key=latest"),
    ("drivers",      f"{BASE}/drivers?session_key=latest"),
    ("session now",  f"{BASE}/sessions?session_key=latest"),
]


def main() -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    for name, url in TARGETS:
        print("\n" + "=" * 70)
        print(f"{name}\n  {url}")
        try:
            got = session.get(url, timeout=TIMEOUT)
        except Exception as exc:                              # noqa: BLE001
            print(f"  UNREACHABLE {type(exc).__name__}: {str(exc)[:100]}")
            continue
        print(f"  {got.status_code}  {len(got.text):>8} bytes")
        if got.status_code != 200:
            continue
        try:
            data = got.json()
        except Exception:                                     # noqa: BLE001
            print("  not JSON")
            continue
        if not isinstance(data, list):
            print(f"  {str(data)[:200]}")
            continue
        print(f"  {len(data)} row(s)")
        for row in data[:3]:
            print("   ", json.dumps(row, ensure_ascii=False)[:230])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
