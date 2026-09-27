#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What can be said about a circuit without buying a new source.

Asked for track facts. Nothing is written until each is fetched and
printed: how many corners it has, whether it is a street circuit or a
permanent one, how many laps the race runs, what year it was first
held, how many times it has been raced, and who won here last.
"""
from __future__ import annotations

import json
import sys
import time

sys.path.insert(0, ".")

import requests

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0"})
JOLPICA = "https://api.jolpi.ca/ergast/f1"


def get(url, tries=3):
    for attempt in range(tries):
        try:
            got = S.get(url, timeout=15)
            if got.status_code == 429:
                time.sleep(2 + attempt * 3)
                continue
            return got.json() if got.status_code == 200 else None
        except Exception:                                     # noqa: BLE001
            time.sleep(1)
    return None


def main() -> int:
    # The next race's circuit, as the calendar names it
    cal = get(f"{JOLPICA}/current.json")
    races = (cal or {}).get("MRData", {}).get("RaceTable", {}).get("Races") or []
    print(f"{len(races)} round(s) this season")
    for race in races[13:15]:
        cid = race["Circuit"]["circuitId"]
        print(f"\n=== {race['raceName']} — circuitId {cid} ===")

        every = get(f"{JOLPICA}/circuits/{cid}/races.json?limit=100")
        held = ((every or {}).get("MRData", {}).get("RaceTable", {})
                .get("Races") or [])
        print(f"  races ever held here : {len(held)}")
        if held:
            print(f"  first               : {held[0].get('season')} "
                  f"({held[0].get('raceName')})")
            print(f"  most recent         : {held[-1].get('season')}")

        winners = get(f"{JOLPICA}/circuits/{cid}/results/1.json?limit=100")
        wins = ((winners or {}).get("MRData", {}).get("RaceTable", {})
                .get("Races") or [])
        if wins:
            last = wins[-1]
            r = (last.get("Results") or [{}])[0]
            print(f"  last winner here    : {r.get('Driver',{}).get('code')} "
                  f"({r.get('Constructor',{}).get('name')}) in "
                  f"{last.get('season')}")
            print(f"  laps that race      : {r.get('laps')}")
            tally = {}
            for w in wins:
                who = ((w.get("Results") or [{}])[0]
                       .get("Driver", {}).get("code"))
                tally[who] = tally.get(who, 0) + 1
            best = sorted(tally.items(), key=lambda p: -p[1])[:3]
            print(f"  most wins here      : {best}")

        fast = get(f"{JOLPICA}/circuits/{cid}/fastest/1/results.json?limit=100")
        laps = ((fast or {}).get("MRData", {}).get("RaceTable", {})
                .get("Races") or [])
        if laps:
            best = None
            for row in laps:
                r = (row.get("Results") or [{}])[0]
                t = ((r.get("FastestLap") or {}).get("Time") or {}).get("time")
                if t and (best is None or t < best[0]):
                    best = (t, r.get("Driver", {}).get("code"),
                            row.get("season"))
            print(f"  lap record          : {best}")
        else:
            print("  lap record          : that endpoint gives nothing")

    # and what OpenF1's meetings say about the circuit itself
    meet = get("https://api.openf1.org/v1/meetings?year=2026")
    if meet:
        print(f"\n=== OpenF1 meetings — {len(meet)} this year ===")
        row = meet[-1]
        for key in ("meeting_name", "circuit_short_name", "circuit_type",
                    "location", "country_name", "gmt_offset",
                    "circuit_info_url"):
            print(f"  {key:<20} {row.get(key)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
