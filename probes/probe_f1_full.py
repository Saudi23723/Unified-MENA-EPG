#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Every free field the board could carry, gathered once and printed.

The preview drew invented gaps. This gathers the real ones, and the
things beside them that cost nothing more: the fastest lap and its
sectors, the pit stops, the qualifying order, the official team colours,
and — the one worth the most on a television — the CIRCUIT'S OWN SHAPE,
which the meetings feed points at as a list of coordinates rather than a
picture, so it can be drawn rather than downloaded.
"""
from __future__ import annotations

import json
import sys
import time

sys.path.insert(0, ".")

import requests

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0"})


def get(url, tries=4):
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


def thin(points, keep=110):
    """A track drawn at 110 points looks like the track; 3000 does not."""
    if len(points) <= keep:
        return points
    step = len(points) / keep
    return [points[int(i * step)] for i in range(keep)]


def main() -> int:
    out = {}

    # ---- the circuit's own shape --------------------------------------
    for name, key in (("monza", 39), ("madrid", 41), ("madring", 40)):
        data = get(f"https://api.multiviewer.app/api/v1/circuits/{key}/2026")
        if not data or "x" not in data:
            print(f"  circuit {name} ({key}): {'no data' if not data else list(data)[:8]}")
            continue
        xs, ys = data.get("x") or [], data.get("y") or []
        pairs = thin(list(zip(xs, ys)))
        out.setdefault("circuits", {})[name] = {
            "name": data.get("circuitName"), "key": key,
            "rotation": data.get("rotation"),
            "corners": len(data.get("corners") or []),
            "points": [[int(a), int(b)] for a, b in pairs]}
        print(f"  circuit {name} ({key}): {data.get('circuitName')} — "
              f"{len(xs)} points thinned to {len(pairs)}, "
              f"{len(data.get('corners') or [])} corners")

    # ---- real gaps, fastest lap, pit stops ----------------------------
    iv = get("https://api.openf1.org/v1/intervals?session_key=latest")
    if iv:
        final = {}
        for row in iv:
            final[row["driver_number"]] = row
        out["gaps"] = sorted(
            [{"n": k, "gap": v.get("gap_to_leader")}
             for k, v in final.items() if v.get("gap_to_leader") is not None],
            key=lambda r: (r["gap"] if isinstance(r["gap"], (int, float))
                           else 999))[:10]
    laps = get("https://api.openf1.org/v1/laps?session_key=latest")
    if laps:
        timed = [l for l in laps if l.get("lap_duration")]
        if timed:
            best = min(timed, key=lambda l: l["lap_duration"])
            out["fastest_lap"] = {
                "n": best["driver_number"], "lap": best["lap_number"],
                "time": best["lap_duration"],
                "s1": best.get("duration_sector_1"),
                "s2": best.get("duration_sector_2"),
                "s3": best.get("duration_sector_3"),
                "trap": best.get("st_speed") or best.get("i2_speed")}
        speeds = [l for l in laps if l.get("st_speed")]
        if speeds:
            top = max(speeds, key=lambda l: l["st_speed"])
            out["top_speed"] = {"n": top["driver_number"],
                                "kph": top["st_speed"]}
    pit = get("https://api.openf1.org/v1/pit?session_key=latest")
    if pit:
        real = [p for p in pit if (p.get("pit_duration") or 0) < 120]
        out["pit_count"] = len(pit)
        if real:
            best = min(real, key=lambda p: p["pit_duration"])
            out["fastest_pit"] = {"n": best["driver_number"],
                                  "s": best["pit_duration"],
                                  "lap": best["lap_number"]}
    drv = get("https://api.openf1.org/v1/drivers?session_key=latest")
    if drv:
        out["drivers"] = [{"n": d["driver_number"], "code": d.get("name_acronym"),
                           "team": d.get("team_name"),
                           "colour": d.get("team_colour")} for d in drv]

    # ---- the championship, in full ------------------------------------
    j = get("https://api.jolpi.ca/ergast/f1/current/driverStandings.json")
    lists = ((j or {}).get("MRData", {}).get("StandingsTable", {})
             .get("StandingsLists") or [{}])[0]
    out["drivers_table"] = [
        {"pos": d["position"], "code": d["Driver"]["code"],
         "team": d["Constructors"][0]["name"], "points": d["points"],
         "wins": d["wins"]}
        for d in (lists.get("DriverStandings") or [])[:8]]
    q = get("https://api.jolpi.ca/ergast/f1/current/last/qualifying.json")
    race = ((q or {}).get("MRData", {}).get("RaceTable", {})
            .get("Races") or [{}])[0]
    out["qualifying"] = [
        {"pos": r["position"], "code": r["Driver"]["code"],
         "team": r["Constructor"]["name"], "q3": r.get("Q3") or r.get("Q2")
         or r.get("Q1")} for r in (race.get("QualifyingResults") or [])[:6]]

    print("\n---BEGIN---")
    print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print("---END---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
