#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Everything the F1 board needs, in one compact block to draw from.

So the preview is drawn from what the sources actually say rather than
from anything invented: the standings, the next race and its sessions,
the last race's result, and the last session's track conditions, flags
and tyres. Printed as one JSON object.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, ".")

import requests

T = 12
S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0"})


def get(url, tries=3):
    for attempt in range(tries):
        try:
            got = S.get(url, timeout=T)
            if got.status_code == 429:
                time.sleep(2 + attempt * 3)
                continue
            if got.status_code == 200:
                return got.json()
            return None
        except Exception:                                     # noqa: BLE001
            time.sleep(1)
    return None


def main() -> int:
    out = {}
    j = get("https://api.jolpi.ca/ergast/f1/current/driverStandings.json")
    lists = ((j or {}).get("MRData", {}).get("StandingsTable", {})
             .get("StandingsLists") or [{}])[0]
    out["round"] = lists.get("round")
    out["drivers"] = [
        {"pos": d["position"], "code": d["Driver"]["code"],
         "name": f"{d['Driver']['givenName']} {d['Driver']['familyName']}",
         "team": d["Constructors"][0]["name"],
         "points": d["points"], "wins": d["wins"]}
        for d in (lists.get("DriverStandings") or [])[:10]]

    j = get("https://api.jolpi.ca/ergast/f1/current/constructorStandings.json")
    lists = ((j or {}).get("MRData", {}).get("StandingsTable", {})
             .get("StandingsLists") or [{}])[0]
    out["teams"] = [
        {"pos": c["position"], "name": c["Constructor"]["name"],
         "points": c["points"], "wins": c["wins"]}
        for c in (lists.get("ConstructorStandings") or [])[:6]]

    j = get("https://api.jolpi.ca/ergast/f1/current/last/results.json")
    race = ((j or {}).get("MRData", {}).get("RaceTable", {})
            .get("Races") or [{}])[0]
    out["last_race"] = {
        "name": race.get("raceName"), "round": race.get("round"),
        "circuit": race.get("Circuit", {}).get("circuitName"),
        "locality": race.get("Circuit", {}).get("Location", {}).get("locality"),
        "country": race.get("Circuit", {}).get("Location", {}).get("country"),
        "date": race.get("date"),
        "top": [{"pos": r["position"], "code": r["Driver"]["code"],
                 "name": f"{r['Driver']['givenName']} {r['Driver']['familyName']}",
                 "team": r["Constructor"]["name"], "grid": r.get("grid"),
                 "points": r.get("points"), "status": r.get("status")}
                for r in (race.get("Results") or [])[:6]]}

    j = get("https://api.jolpi.ca/ergast/f1/current.json")
    races = (j or {}).get("MRData", {}).get("RaceTable", {}).get("Races") or []
    now = datetime.now(timezone.utc)
    nxt = None
    for r in races:
        when = f"{r['date']}T{r.get('time','12:00:00Z')}".replace("Z", "+00:00")
        try:
            if datetime.fromisoformat(when) > now:
                nxt = r
                break
        except ValueError:
            continue
    if nxt:
        out["next_race"] = {
            "name": nxt.get("raceName"), "round": nxt.get("round"),
            "circuit": nxt.get("Circuit", {}).get("circuitName"),
            "locality": nxt.get("Circuit", {}).get("Location", {}).get("locality"),
            "country": nxt.get("Circuit", {}).get("Location", {}).get("country"),
            "sessions": {k: f"{v['date']} {v['time']}" for k, v in (
                ("FP1", nxt.get("FirstPractice")),
                ("FP2", nxt.get("SecondPractice")),
                ("FP3", nxt.get("ThirdPractice")),
                ("Sprint", nxt.get("Sprint")),
                ("Qualifying", nxt.get("Qualifying"))) if v},
            "race": f"{nxt.get('date')} {nxt.get('time')}"}

    w = get("https://api.openf1.org/v1/weather?session_key=latest")
    if w:
        out["weather"] = w[-1]
    rc = get("https://api.openf1.org/v1/race_control?session_key=latest")
    if rc:
        out["flags"] = [r for r in rc if r.get("flag")][-4:]
    st = get("https://api.openf1.org/v1/stints?session_key=latest")
    if st:
        out["tyres"] = st[-6:]
    se = get("https://api.openf1.org/v1/sessions?session_key=latest")
    if se:
        out["session"] = se[-1]

    print("---BEGIN---")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print("---END---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
