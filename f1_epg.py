#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""الفورمولا ١ — the eleventh channel: Formula 1, on all seven days.

WHY THIS ONE IS NOT BUILT LIKE THE OTHERS. Every other screen here is a
list of fixtures, and a list works because there is always another match
tomorrow. Formula 1 runs twenty-four weekends a year: a fixtures board
would be a black screen from Monday to Thursday, which is most of this
channel's life.

So the channel draws THREE boards and the clock decides which:

    LIVE      a session is under way — the order with real gaps, the
              flag, the track and air temperature, the fastest lap and
              its three sectors, the speed trap, the pit stops
    WEEKEND   the cars are at the circuit but not on it — every session
              of the weekend timed, the circuit, the last race
    BETWEEN   no circuit at all, five days in seven — the championship,
              the next Grand Prix with every session, the title
              arithmetic, the last qualifying

WHERE IT COMES FROM, measured before a line of this was written
(probes/probe_f1_sources.py and the three that follow it):

    ESPN            scoreboard answers, standings and calendar 403
    OpenF1          sessions, weather, intervals, laps, pit, stints,
                    race control, drivers with their OWN team colours —
                    and it RATE LIMITS, answering 429 twice in one pass
    Jolpica         what took over when Ergast froze: the full calendar
                    with every session in UTC, both championships, race
                    and qualifying classifications
    multiviewer     a circuit as a LIST OF COORDINATES rather than a
                    picture, so the outline is drawn in this board's own
                    colours instead of fetched as an image every pass

THE RATE LIMIT IS THE DESIGN CONSTRAINT. This runs every five minutes
behind the screen workflow, and a source that answers 429 twice a pass
cannot be asked twelve times an hour for everything. So every fetch is
cached to f1_state.json with its own age, the slow-moving things are
re-asked once an hour and the live ones every pass, and a pass that
gets nothing draws the last good state rather than an empty board.
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from epg_lib import add_programme, fetch, log, new_session, warn, write_xml_atomic

UTC = timezone.utc
# THE SAME CLOCK EVERY OTHER CHANNEL HERE WEARS, and it was wrong: this
# was written with Asia/Riyadh in it, so a Grand Prix that starts at
# 13:00 UTC printed 16:00 on a screen whose every neighbour would have
# printed 06:00. "بتوقيتك" means one zone across the service or it means
# nothing, and that zone is America/Los_Angeles — today_matches_epg,
# other_sports_epg, news_epg and weather_epg all say so.
VIEWER = ZoneInfo("America/Los_Angeles")
VIEWER_NAME = "بتوقيتك"

CHANNEL_ID = "Formula1"
CHANNEL_AR = "🏁 الفورمولا ١"
CHANNEL_EN = "Formula 1"
OUTPUT = "f1_epg.xml"
BOARD_PREFIX = "f1_"
BOARD_DIR = "boards"
STATE = "f1_state.json"
RAW = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
       "main/boards/f1_0.png")
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/f1.png")

# THE SECOND CLOCK. Every other channel here publishes twice — the same
# rows with every time printed in the Gulf's — and this one refused to,
# on the reasoning that a Grand Prix is one instant everywhere. That is
# true of the instant and useless to a viewer: what they read is the
# hour it lands on THEIR wall, and the Gulf's link exists to say that
# hour. So it publishes twice like the rest.
DUBAI_OUTPUT = "dubai_f1_epg.xml"
DUBAI_CHANNEL_ID = "Formula1Dubai"
DUBAI_BOARD_PREFIX = "dubai_f1_"
DUBAI_RAW = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
             "main/boards/dubai_f1_0.png")

JOLPICA = "https://api.jolpi.ca/ergast/f1"
OPENF1 = "https://api.openf1.org/v1"
CIRCUITS = "https://api.multiviewer.app/api/v1/circuits"
# THE WEATHER ON THE CIRCUIT WHEN NOBODY IS ON IT. OpenF1's
# trackside sensors only exist while a session is running, so on the
# five days a week this channel has no session the temperature it
# showed was whatever the last session left behind — a memory, not a
# reading. Open-Meteo is this repository's weather source already
# (weather_epg.py reads it), needs no key, and answered for all 23
# circuits of the season in ONE request: the calendar carries every
# round's latitude and longitude, 23 of 23.
METEO = "https://api.open-meteo.com/v1/forecast"

# HOW LONG A SESSION IS, because the calendar gives a start and no end.
# An hour for a practice or a qualifying, two for a race — and the board
# only uses these to decide WHICH of the three it is, never to print a
# time, so an approximation cannot put a wrong minute on the screen.
RUNS_FOR = {"FP1": 90, "FP2": 90, "FP3": 90, "SPRINT": 90,
            "QUALIFYING": 90, "RACE": 150}
# The weekend opens two hours before the first session and closes three
# after the race, which is when a circuit stops being the answer.
OPENS_BEFORE = timedelta(hours=2)
CLOSES_AFTER = timedelta(hours=3)
# How old a cached answer may be before it is asked for again.
SLOWLY = timedelta(hours=1)          # calendar, standings, results
QUICKLY = timedelta(minutes=4)       # the session on now
# The weather is asked for every quarter of an hour. Open-Meteo's
# own reading only moves on the quarter hour, so asking every four
# minutes would be four requests for one number.
WEATHER_EVERY = timedelta(minutes=15)
HOURS_AHEAD = 12


def _state() -> dict:
    try:
        with open(STATE, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:                                         # noqa: BLE001
        return {}


def _keep(state: dict) -> None:
    try:
        with open(STATE, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False)
    except Exception as exc:                                  # noqa: BLE001
        warn(f"the F1 state could not be written ({exc})")


def _stale(state: dict, key: str, now: datetime, older_than) -> bool:
    stamp = (state.get(key) or {}).get("at")
    if not stamp:
        return True
    try:
        return datetime.fromisoformat(stamp) + older_than < now
    except ValueError:
        return True


def _ask(session, url, state, key, now, older_than):
    """Fetch, or hand back what the last good pass got.

    A SOURCE THAT RATE LIMITS IS NOT A SOURCE THAT FAILED. OpenF1
    answers 429 under a five-minute cadence, and a board drawn from a
    429 is a board with nothing on it — so the cached answer stands
    until it is older than this caller is willing to accept.
    """
    if not _stale(state, key, now, older_than):
        return (state[key] or {}).get("was")
    try:
        got = fetch(session, url)
        data = got.json()
        state[key] = {"at": now.isoformat(), "was": data}
        return data
    except Exception as exc:                                  # noqa: BLE001
        held = (state.get(key) or {}).get("was")
        warn(f"F1: {key} is unreachable ({type(exc).__name__}) — "
             f"{'the last answer stands' if held else 'nothing to stand on'}")
        return held


def _at(day: str, clock: str) -> datetime | None:
    try:
        return datetime.fromisoformat(
            f"{day}T{clock}".replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def the_calendar(session, state, now) -> list[dict]:
    """Every round of the season, each with its sessions timed in UTC."""
    data = _ask(session, f"{JOLPICA}/current.json", state, "calendar", now,
                SLOWLY)
    races = ((data or {}).get("MRData", {}).get("RaceTable", {})
             .get("Races") or [])
    out = []
    for race in races:
        sessions = []
        for name, block in (("FP1", race.get("FirstPractice")),
                            ("FP2", race.get("SecondPractice")),
                            ("FP3", race.get("ThirdPractice")),
                            ("SPRINT", race.get("Sprint")),
                            ("QUALIFYING", race.get("Qualifying"))):
            if block:
                when = _at(block.get("date"), block.get("time"))
                if when:
                    sessions.append((name, when))
        started = _at(race.get("date"), race.get("time") or "12:00:00Z")
        if started:
            sessions.append(("RACE", started))
        sessions.sort(key=lambda pair: pair[1])
        circuit = race.get("Circuit") or {}
        place = circuit.get("Location") or {}
        out.append({
            "round": race.get("round"), "name": race.get("raceName"),
            "circuit": circuit.get("circuitName") or "",
            "circuit_id": circuit.get("circuitId") or "",
            "locality": place.get("locality") or "",
            "country": place.get("country") or "",
            # WHERE THE CIRCUIT IS, so a forecast can be asked about it.
            "lat": place.get("lat"), "lon": place.get("long"),
            "sessions": sessions,
            "race_at": started})
    return out


def the_shape(session, state, now, meeting) -> tuple[list, int, int]:
    """The circuit as coordinates, from the key the meetings feed names."""
    key = (meeting or {}).get("circuit_key")
    if not key:
        return [], 0, 0
    data = _ask(session, f"{CIRCUITS}/{key}/{now.year}", state,
                f"shape:{key}", now, timedelta(days=7))
    if not data or "x" not in data:
        return [], 0, 0
    xs, ys = data.get("x") or [], data.get("y") or []
    pairs = list(zip(xs, ys))
    if len(pairs) > 110:
        step = len(pairs) / 110
        pairs = [pairs[int(i * step)] for i in range(110)]
    return ([[int(a), int(b)] for a, b in pairs],
            int(data.get("rotation") or 0),
            len(data.get("corners") or []))


def the_track_facts(session, state, now, circuit_id, meeting,
                    corners) -> dict:
    """What can be said about a circuit without buying a source.

    Every one of these is already paid for. The corner count falls out
    of the shape this board already draws. Whether it is a street
    circuit or a permanent one is a field in the meetings feed. And the
    rest is the same calendar this channel already reads, asked about
    one circuit instead of one season: how many Grands Prix have been
    held here, the year of the first, who won the last one and in how
    many laps, and who has won here more than anyone.

    CACHED FOR A WEEK, because none of it can change inside one. A
    circuit's history is the slowest-moving thing this channel knows.
    """
    out = {"corners": corners or 0,
           "type": (meeting or {}).get("circuit_type") or ""}
    if not circuit_id:
        return out
    week = timedelta(days=7)

    held = _ask(session, f"{JOLPICA}/circuits/{circuit_id}/races.json"
                f"?limit=100", state, f"held:{circuit_id}", now, week)
    races = ((held or {}).get("MRData", {}).get("RaceTable", {})
             .get("Races") or [])
    if races:
        out["held"] = len(races)
        out["first"] = races[0].get("season")

    won = _ask(session, f"{JOLPICA}/circuits/{circuit_id}/results/1.json"
               f"?limit=100", state, f"won:{circuit_id}", now, week)
    wins = ((won or {}).get("MRData", {}).get("RaceTable", {})
            .get("Races") or [])
    if wins:
        last = wins[-1]
        row = (last.get("Results") or [{}])[0]
        out["last_winner"] = row.get("Driver", {}).get("code")
        out["last_winner_team"] = row.get("Constructor", {}).get("name")
        out["last_winner_year"] = last.get("season")
        out["laps"] = row.get("laps")
        tally: dict[str, int] = {}
        for race in wins:
            code = ((race.get("Results") or [{}])[0]
                    .get("Driver", {}).get("code"))
            if code:
                tally[code] = tally.get(code, 0) + 1
        best = sorted(tally.items(), key=lambda pair: -pair[1])[:1]
        if best and best[0][1] > 1:
            out["most_wins"] = best[0]
    return out


def the_track_weather(session, state, now, race) -> dict:
    """The weather ON THE CIRCUIT, on a day with no car on it.

    WHY THIS IS NOT THE LIVE PANEL'S WEATHER. That one comes from
    OpenF1, which reads the sensors AT the track — the real surface
    temperature, measured. It is the better number and it stays where
    it is. But it exists only while a session is running. This one is a
    forecast at the circuit's own latitude and longitude, so the track
    page has weather on the five days a week the sensors are silent.

    IT SAYS WHICH IS WHICH. The surface figure here is the ground
    temperature at those coordinates, not a reading off the tarmac, and
    the board labels it SURFACE rather than the trackside TRACK so the
    two are never mistaken for each other.

    A READING THAT DOES NOT COME BACK IS LEFT OUT, never zeroed —
    "0°" on a television is a lie a blank space does not tell.
    """
    lat, lon = (race or {}).get("lat"), (race or {}).get("lon")
    if not lat or not lon:
        return {}
    url = (f"{METEO}?latitude={lat}&longitude={lon}"
           f"&current=temperature_2m,apparent_temperature,"
           f"relative_humidity_2m,weather_code,wind_speed_10m,"
           f"precipitation,is_day"
           f"&hourly=precipitation_probability,soil_temperature_0cm"
           f"&forecast_days=1&timezone=auto")

    # ONE CIRCUIT'S WEATHER IS KEPT, NOT THE SEASON'S. This state file
    # is committed on every pass, and a key for each of 23 rounds would
    # be 23 forecasts of dead weight in it. But a single key must never
    # hand Madrid's weather to Monza the week the calendar moves on —
    # so the coordinates it was fetched for are kept beside it, and a
    # different circuit throws the cached answer away rather than
    # waiting a quarter of an hour to stop being wrong.
    for stale in [k for k in state if k.startswith("weather:")]:
        state.pop(stale, None)                     # keys from before this
    if state.get("weather_at") != f"{lat},{lon}":
        state.pop("weather", None)
        state["weather_at"] = f"{lat},{lon}"
    data = _ask(session, url, state, "weather", now, WEATHER_EVERY)
    current = (data or {}).get("current") or {}
    if current.get("temperature_2m") is None:
        return {}

    # THE HOUR THE READING ITSELF SITS IN, not the hour after it. The
    # chance of rain and the ground temperature are hourly figures, and
    # the one that belongs beside a 15:30 reading is 15:00's.
    out = {}
    hourly = (data or {}).get("hourly") or {}
    times = hourly.get("time") or []
    cut = (current.get("time") or "")[:13]
    at = next((i for i, one in enumerate(times) if one[:13] == cut), None)
    if at is not None:
        for key, field in (("rain_chance", "precipitation_probability"),
                           ("surface_c", "soil_temperature_0cm")):
            column = hourly.get(field) or []
            if at < len(column) and column[at] is not None:
                out[key] = column[at]

    out.update({
        "air_c": current["temperature_2m"],
        "feels_c": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "wind_kmh": current.get("wind_speed_10m"),
        "rain_mm": current.get("precipitation"),
        "code": current.get("weather_code"),
        "day": bool(current.get("is_day")),
        # The clock AT THE CIRCUIT, which Open-Meteo hands back because
        # the request asks for its own timezone. A viewer reading
        # "27° at 23:30" knows why it is not hotter.
        "observed": current.get("time"),
        "zone": (data or {}).get("timezone_abbreviation") or "",
        "where": f"{race.get('locality', '')}, {race.get('country', '')}",
    })
    return {k: v for k, v in out.items() if v is not None}


def the_colours(session, state, now) -> dict:
    """Each driver's code and the team's OWN colour, from the feed."""
    data = _ask(session, f"{OPENF1}/drivers?session_key=latest", state,
                "drivers", now, SLOWLY)
    out = {}
    for row in data or []:
        code = row.get("name_acronym")
        if code:
            out[code] = {"team": row.get("team_name") or "",
                         "colour": row.get("team_colour") or "",
                         "number": row.get("driver_number")}
    return out


def the_championship(session, state, now, colours) -> tuple[list, list]:
    drivers = _ask(session, f"{JOLPICA}/current/driverStandings.json", state,
                   "drivers_table", now, SLOWLY)
    lists = ((drivers or {}).get("MRData", {}).get("StandingsTable", {})
             .get("StandingsLists") or [{}])[0]
    # EVERY DRIVER, NOT THE FIRST EIGHT. The source hands back the whole
    # championship in the one answer that was already being paid for, and
    # a table cut at eight is twelve drivers thrown away before the board
    # ever gets a chance to draw them. What fits is the board's decision,
    # made where there is a page size to decide it against — not here.
    table = []
    for row in (lists.get("DriverStandings") or []):
        who = row["Driver"]
        code = who.get("code") or (who.get("familyName") or "")[:3].upper()
        table.append({"pos": row["position"], "code": code,
                      "team": row["Constructors"][0]["name"],
                      "points": row["points"], "wins": row["wins"],
                      # THE NAME, which the source carries and the board
                      # had no way to show because it never arrived.
                      "name": f"{who.get('givenName','')} "
                              f"{who.get('familyName','')}".strip(),
                      "number": who.get("permanentNumber") or "",
                      "nationality": who.get("nationality") or "",
                      "colour": (colours.get(code) or {}).get("colour", "")})
    teams = _ask(session, f"{JOLPICA}/current/constructorStandings.json",
                 state, "teams_table", now, SLOWLY)
    lists = ((teams or {}).get("MRData", {}).get("StandingsTable", {})
             .get("StandingsLists") or [{}])[0]
    return table, [{"pos": r["position"], "name": r["Constructor"]["name"],
                    "points": r["points"], "wins": r.get("wins") or "0",
                    "nationality": r["Constructor"].get("nationality") or ""}
                   for r in (lists.get("ConstructorStandings") or [])]


def the_last_race(session, state, now, colours) -> dict:
    data = _ask(session, f"{JOLPICA}/current/last/results.json", state,
                "last_race", now, SLOWLY)
    race = ((data or {}).get("MRData", {}).get("RaceTable", {})
            .get("Races") or [{}])[0]
    # THE WHOLE CLASSIFICATION, AND EVERYTHING ON EACH ROW. The answer
    # carries the gap to the winner, the finishing status, the points
    # scored, the laps completed and the grid slot each driver started
    # from — and six rows of code and team were all that was being kept
    # out of it. None of the rest costs another request.
    top = []
    for row in (race.get("Results") or []):
        who = row["Driver"]
        code = who.get("code") or (who.get("familyName") or "")[:3].upper()
        clock = (row.get("Time") or {}).get("time") or ""
        status = row.get("status") or ""
        top.append({
            "pos": row["position"], "code": code,
            "team": row["Constructor"]["name"],
            "grid": row.get("grid", "?"),
            "laps": row.get("laps") or "",
            "points": row.get("points") or "0",
            "name": f"{who.get('givenName','')} "
                    f"{who.get('familyName','')}".strip(),
            # THE GAP IF THEY FINISHED, THE REASON IF THEY DID NOT. A
            # classification that says "18" and nothing else does not
            # tell a viewer whether the car broke or the driver was
            # simply slow, and the source says which.
            "gap": clock or ("" if status.startswith("Finished") else status),
            "status": status,
            "colour": (colours.get(code) or {}).get("colour", "")})

    # THE FASTEST LAP OF THAT RACE, which is on the row that set it.
    quickest = None
    for row in (race.get("Results") or []):
        best = row.get("FastestLap") or {}
        if best.get("rank") == "1":
            who = row["Driver"]
            quickest = {
                "code": who.get("code") or "",
                "time": (best.get("Time") or {}).get("time") or "",
                "lap": best.get("lap") or "",
                "kph": (best.get("AverageSpeed") or {}).get("speed") or "",
                "colour": (colours.get(who.get("code")) or {}).get("colour",
                                                                   "")}
            break

    quali = _ask(session, f"{JOLPICA}/current/last/qualifying.json", state,
                 "last_quali", now, SLOWLY)
    lap = ((quali or {}).get("MRData", {}).get("RaceTable", {})
           .get("Races") or [{}])[0]
    order = []
    for row in (lap.get("QualifyingResults") or []):
        who = row["Driver"]
        code = who.get("code") or (who.get("familyName") or "")[:3].upper()
        # EACH OF THE THREE PARTS, not just the last one a driver
        # reached. Q1 and Q2 are how the grid's back half was decided,
        # and they were being dropped on the floor.
        order.append({"pos": row["position"], "code": code,
                      "team": (row.get("Constructor") or {}).get("name", ""),
                      "q1": row.get("Q1") or "", "q2": row.get("Q2") or "",
                      "q3": row.get("Q3") or "",
                      "time": row.get("Q3") or row.get("Q2")
                      or row.get("Q1") or "",
                      "colour": (colours.get(code) or {}).get("colour", "")})
    return {"at": race.get("raceName") or "", "top": top,
            "round": race.get("round"), "qualifying": order,
            "circuit": ((race.get("Circuit") or {}).get("circuitName") or ""),
            "date": race.get("date") or "", "fastest": quickest}


def _by_number(colours: dict) -> dict:
    return {c["number"]: (code, c) for code, c in colours.items()
            if c.get("number")}


def the_session_now(session, state, now, colours) -> dict | None:
    """What is happening on the track this minute, or nothing."""
    live = _ask(session, f"{OPENF1}/sessions?session_key=latest", state,
                "session_now", now, QUICKLY)
    if not live:
        return None
    row = live[-1] if isinstance(live, list) else live
    start = _at(*(row.get("date_start") or "").split("T")[:1] + ["00:00:00Z"])
    try:
        start = datetime.fromisoformat(row["date_start"])
        end = datetime.fromisoformat(row["date_end"])
    except (KeyError, ValueError):
        return None
    if not start <= now <= end:
        return None                      # the feed's "latest" is the LAST one

    numbers = _by_number(colours)
    weather = _ask(session, f"{OPENF1}/weather?session_key=latest", state,
                   "weather", now, QUICKLY) or []
    gaps = _ask(session, f"{OPENF1}/intervals?session_key=latest", state,
                "intervals", now, QUICKLY) or []
    final = {}
    for line in gaps:
        final[line.get("driver_number")] = line
    order = []
    for number, line in sorted(
            final.items(),
            key=lambda pair: (pair[1].get("gap_to_leader")
                              if isinstance(pair[1].get("gap_to_leader"),
                                            (int, float)) else 9e9)):
        code, who = numbers.get(number, (str(number), {}))
        gap = line.get("gap_to_leader")
        order.append({"code": code, "team": who.get("team", ""),
                      "colour": who.get("colour", ""),
                      "gap": "LEADER" if gap in (0, 0.0)
                      else (f"+{gap:.3f}" if isinstance(gap, (int, float))
                            else str(gap))})
    control = _ask(session, f"{OPENF1}/race_control?session_key=latest",
                   state, "race_control", now, QUICKLY) or []
    flags = [r for r in control if r.get("flag")]
    return {
        "session": row.get("session_name") or row.get("session_type") or "",
        "circuit": row.get("circuit_short_name") or "",
        "country": row.get("country_name") or "",
        "meeting": row,
        "weather": weather[-1] if weather else {},
        "order": order[:9],
        "flag": (flags[-1].get("flag") if flags else "GREEN"),
        "lap": (flags[-1].get("lap_number") if flags else None)}


def the_session_detail(session, state, now, colours) -> dict:
    """Fastest lap, trap and pit stops — the numbers argued about after."""
    numbers = _by_number(colours)
    out = {}
    laps = _ask(session, f"{OPENF1}/laps?session_key=latest", state, "laps",
                now, QUICKLY) or []
    timed = [l for l in laps if l.get("lap_duration")]
    if timed:
        best = min(timed, key=lambda l: l["lap_duration"])
        code, who = numbers.get(best["driver_number"], ("?", {}))
        out["fastest"] = {
            "code": code, "colour": who.get("colour", ""),
            "lap": best.get("lap_number"), "time": best["lap_duration"],
            "sectors": [best.get(f"duration_sector_{n}") for n in (1, 2, 3)
                        if best.get(f"duration_sector_{n}")],
            "trap": best.get("st_speed") or best.get("i2_speed")}
    fast = [l for l in laps if l.get("st_speed")]
    if fast:
        top = max(fast, key=lambda l: l["st_speed"])
        code, who = numbers.get(top["driver_number"], ("?", {}))
        out["top_speed"] = {"code": code, "kph": top["st_speed"],
                            "colour": who.get("colour", "")}
    stints = _ask(session, f"{OPENF1}/stints?session_key=latest", state,
                  "stints", now, QUICKLY) or []
    latest: dict = {}
    for stint in stints:
        latest[stint.get("driver_number")] = stint
    out["tyres"] = [
        {"compound": s.get("compound"),
         "code": numbers.get(n, (f"#{n}", {}))[0],
         "laps": (s.get("lap_end") or 0) - (s.get("lap_start") or 0) + 1}
        for n, s in list(latest.items())[:12] if s.get("compound")]

    pit = _ask(session, f"{OPENF1}/pit?session_key=latest", state, "pit",
               now, QUICKLY) or []
    if pit:
        real = [p for p in pit if 0 < (p.get("pit_duration") or 0) < 120]
        best = min(real, key=lambda p: p["pit_duration"]) if real else None
        out["pits"] = {
            "count": len(pit),
            "best": (numbers.get(best["driver_number"], ("?", {}))[0]
                     if best else ""),
            "s": best["pit_duration"] if best else 0}
    return out


def the_meeting(session, state, now) -> dict | None:
    """The meeting the paddock is at, for the circuit key and its type.

    Between weekends OpenF1's "latest" is the LAST meeting rather than
    the next, so this is only ever asked for the circuit's own shape and
    its type — never for a time, which is the one thing it would be
    wrong about.
    """
    data = _ask(session, f"{OPENF1}/meetings?year={now.year}", state,
                "meetings", now, SLOWLY)
    return (data or [None])[-1] if isinstance(data, list) else None


def which_board(now, calendar) -> tuple[str, dict | None, tuple | None]:
    """LIVE, WEEKEND or BETWEEN — decided by the clock, not a setting."""
    for race in calendar:
        if not race["sessions"]:
            continue
        opens = race["sessions"][0][1] - OPENS_BEFORE
        closes = race["sessions"][-1][1] + CLOSES_AFTER
        if opens <= now <= closes:
            for name, when in race["sessions"]:
                runs = timedelta(minutes=RUNS_FOR.get(name, 90))
                if when <= now <= when + runs:
                    return "live", race, (name, when)
            ahead = [(n, w) for n, w in race["sessions"] if w > now]
            return "weekend", race, (ahead[0] if ahead else None)
    ahead = [r for r in calendar if r["race_at"] and r["race_at"] > now]
    return "between", (ahead[0] if ahead else None), None


def _sky_words(code) -> str:
    """The sky in Arabic, in the words the weather channel already uses.

    Borrowed from weather_epg rather than written again: a reader who
    knows "غائم جزئياً" from channel 9 reads the same two words here.
    """
    try:
        from weather_epg import WMO_AR
        return WMO_AR.get(int(code), "")
    except Exception:                                         # noqa: BLE001
        return ""


def a_page(mode, state) -> str:
    """The day in words, for a player that shows no artwork at all."""
    lines = [f"{CHANNEL_AR} · {VIEWER_NAME}", ""]
    if mode == "live":
        live = state["live"]
        lines.append(f"🔴 {live['session']} — {live['circuit']}, "
                     f"{live['country']}")
        weather = live.get("weather") or {}
        if weather:
            lines.append(f"    الحلبة {weather.get('track_temperature',0):.0f}° · "
                         f"الجو {weather.get('air_temperature',0):.0f}°")
        for index, row in enumerate(live.get("order", [])[:10], start=1):
            lines.append(f"  {index:>2}. {row['code']:<4} {row['gap']}")
        return "\n".join(lines)
    nxt = state.get("next")
    if nxt:
        lines.append(f"الجولة {nxt['round']} — {nxt['name']}")
        lines.append(f"    {nxt['circuit']}, {nxt['country']}")
        lines.append("")
        for name, when in nxt["sessions"]:
            local = when.astimezone(VIEWER)
            lines.append(f"  {name:<11} {local:%a %d.%m}  {local:%H:%M}")
    facts = state.get("facts") or {}
    told = []
    if facts.get("corners"):
        told.append(f"{facts['corners']} منعطف")
    if facts.get("laps"):
        told.append(f"{facts['laps']} لفة")
    if facts.get("type"):
        told.append(facts["type"])
    if facts.get("first"):
        told.append(f"منذ {facts['first']}")
    if facts.get("held"):
        told.append(f"{facts['held']} سباق هنا")
    if told:
        lines += ["", "الحلبة:", "  " + "  ·  ".join(told)]
    if facts.get("last_winner"):
        lines.append(f"  آخر فائز هنا: {facts['last_winner']} "
                     f"({facts.get('last_winner_year', '')})")
    most = facts.get("most_wins")
    if most:
        lines.append(f"  الأكثر فوزاً هنا: {most[0]} — {most[1]}")

    # THE WEATHER ON THE CIRCUIT, on the page a player with no artwork
    # shows. Said in Arabic here because everything around it is, and
    # in the words the weather channel already uses for the same codes.
    sky = state.get("weather") or {}
    if sky.get("air_c") is not None:
        said = [f"الجو {sky['air_c']:.0f}°"]
        if sky.get("surface_c") is not None:
            said.append(f"سطح الأرض {sky['surface_c']:.0f}°")
        if sky.get("rain_chance") is not None:
            said.append(f"احتمال المطر {sky['rain_chance']:.0f}%")
        if sky.get("humidity") is not None:
            said.append(f"رطوبة {sky['humidity']:.0f}%")
        if sky.get("wind_kmh") is not None:
            said.append(f"رياح {sky['wind_kmh']:.0f} كم/س")
        lines += ["", f"🌡️ طقس الحلبة — {_sky_words(sky.get('code'))}",
                  "  " + "  ·  ".join(said)]

    # THE LAST RACE AND THE LAST QUALIFYING, which this page never said
    # a word about even while the channel was paying for both.
    last = state.get("last") or {}
    if last.get("top"):
        lines += ["", f"نتيجة آخر سباق — {last.get('at', '')}:"]
        for row in last["top"][:10]:
            said = row.get("gap") or ""
            lines.append(f"  {row['pos']:>2}. {row['code']:<4} "
                         f"{row['team']:<18} {said:<14} {row.get('points','0'):>3}")
        best = last.get("fastest") or {}
        if best.get("time"):
            lines.append(f"  أسرع لفة: {best.get('code','')} {best['time']}"
                         + (f" (لفة {best['lap']})" if best.get("lap") else ""))
    grid = state.get("qualifying") or last.get("qualifying") or []
    if grid:
        lines += ["", "نتيجة التجارب:"]
        for row in grid[:10]:
            lines.append(f"  {row['pos']:>2}. {row['code']:<4} "
                         f"{row.get('time', ''):<12}")

    table = state.get("drivers") or []
    if table:
        lines += ["", "ترتيب السائقين:"]
        for row in table:
            lines.append(f"  {row['pos']:>2}. {row['code']:<4} "
                         f"{row['team']:<18} {row['points']:>4}")
    teams = state.get("teams") or []
    if teams:
        lines += ["", "ترتيب الفرق:"]
        for row in teams:
            lines.append(f"  {row['pos']:>2}. {row['name']:<20} "
                         f"{row['points']:>4}")
    return "\n".join(lines)


def the_pages(now, mode, state) -> list:
    """Which boards this pass draws, in the order the reel plays them.

    ONE BOARD WAS LOSING THINGS. The championship, the circuit and a
    session's own numbers were being squeezed onto one screen and
    dropping off the bottom of it. This channel is a reel like every
    other one here: each page carries one subject at a size a
    television can read, and nothing has to be left out to fit.
    """
    import f1_board
    pages = []
    if mode == "live":
        live = dict(state["live"], **state["detail"],
                    shape=state.get("shape") or [],
                    rotation=state.get("rotation", 0),
                    corners=state.get("corners", 0))
        pages.append(f1_board.draw_live(now, live))
        pages.append(f1_board.page_session(now, live))
    elif mode == "weekend":
        pages.append(f1_board.draw_weekend(now, VIEWER, state))
    else:
        pages.append(f1_board.draw_between(now, VIEWER, state))
    # THE TRACK AND THE CHAMPIONSHIP FOLLOW ON EVERY MODE, because they
    # are true whether or not a car is on the circuit — and they are
    # what this channel has on the five days it has nothing else.
    if state.get("shape") or state.get("facts") or state.get("weather"):
        pages.append(f1_board.page_track(now, state))
    if state.get("drivers"):
        pages.append(f1_board.page_championship(now, state))
    if state.get("teams"):
        pages.append(f1_board.page_constructors(now, state))
    # AND WHAT THE LAST WEEKEND ACTUALLY DID. The classification and the
    # grid were both being fetched and both being thrown away at six
    # rows and four; they get a page each now, whole.
    if (state.get("last") or {}).get("top"):
        pages.append(f1_board.page_last(now, state))
    if state.get("qualifying") or (state.get("last") or {}).get("qualifying"):
        pages.append(f1_board.page_qualifying(now, state))
    return pages


def publish(now, mode, state) -> int:
    import io

    from PIL import Image

    from match_board import forget_boards_past

    os.makedirs(BOARD_DIR, exist_ok=True)
    pages = the_pages(now, mode, state)
    for number, board in enumerate(pages):
        path = os.path.join(BOARD_DIR, f"{BOARD_PREFIX}{number}.png")
        buffer = io.BytesIO()
        board.convert("RGB").convert(
            "P", palette=Image.ADAPTIVE, colors=64).save(buffer, format="PNG",
                                                         optimize=True)
        fresh = buffer.getvalue()
        if not os.path.exists(path) or open(path, "rb").read() != fresh:
            with open(path, "wb") as out:
                out.write(fresh)
            log(f"  board {BOARD_PREFIX}{number}.png redrawn "
                f"({len(fresh) // 1024} KB)")
    # A BOARD THIS PASS DID NOT WRITE IS A BOARD PLAYING SOMETHING OVER.
    # The page count moves with the mode — a live session draws five
    # where a quiet Tuesday draws three — so the ones past the end go.
    forget_boards_past(BOARD_PREFIX, len(pages), BOARD_DIR)

    if mode == "live":
        title = f"🔴 {state['live']['session']} — {state['live']['circuit']}"
    elif mode == "weekend":
        title = f"{state['next']['name']} — نهاية الأسبوع"
    else:
        title = (state["next"]["name"] if state.get("next") else CHANNEL_EN)

    tv = ET.Element("tv", {"generator-info-name": "Formula 1"})
    channel = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(channel, "icon", {"src": LOGO})
    ET.SubElement(channel, "display-name", {"lang": "ar"}).text = CHANNEL_AR
    ET.SubElement(channel, "display-name", {"lang": "en"}).text = CHANNEL_EN

    opens = now.replace(minute=0, second=0, microsecond=0)
    page = a_page(mode, state)
    for step in range(HOURS_AHEAD):
        start = opens + timedelta(hours=step)
        add_programme(tv, CHANNEL_ID, start, start + timedelta(hours=1),
                      title=title, desc=page, icon=RAW)
    ok = write_xml_atomic(tv, OUTPUT, generator_name="Formula 1",
                          guard_regression=False, min_programmes=1)
    log(f"{CHANNEL_AR}: {mode}, {len(pages)} board(s), "
        f"{HOURS_AHEAD} programme(s)")
    return 0 if ok else 1


def build() -> int:
    now = datetime.now(UTC)
    session = new_session()
    state = _state()

    colours = the_colours(session, state, now)
    calendar = the_calendar(session, state, now)
    if not calendar:
        warn("F1: no calendar to draw from — nothing published this pass")
        _keep(state)
        return 1

    mode, race, ahead = which_board(now, calendar)
    table, teams = the_championship(session, state, now, colours)
    last = the_last_race(session, state, now, colours)

    page = {"round": last.get("round") or "0", "rounds": len(calendar),
            "drivers": table, "teams": teams, "last": last,
            "qualifying": last.get("qualifying") or []}
    if race:
        page["next"] = race
        page["next_session"] = ahead
        shape, rotation, corners = [], 0, 0
        live = the_session_now(session, state, now, colours) if mode == "live" else None
        meeting = live["meeting"] if live else the_meeting(session, state, now)
        if meeting:
            shape, rotation, corners = the_shape(session, state, now, meeting)
        if live:
            page["live"] = live
            page["detail"] = the_session_detail(session, state, now, colours)
        page["shape"], page["rotation"], page["corners"] = (shape, rotation,
                                                            corners)
        page["facts"] = the_track_facts(session, state, now,
                                        race.get("circuit_id"), meeting,
                                        corners)
        page["weather"] = the_track_weather(session, state, now, race)
    if mode == "live" and "live" not in page:
        # THE CLOCK SAID A SESSION WAS ON AND THE FEED DID NOT AGREE.
        # A board that says LIVE with nothing under it is worse than one
        # that says what is coming, so it steps back to the weekend.
        mode = "weekend"
    log(f"  F1: {mode} — round {page['round']} of {page['rounds']}")
    result = publish(now, mode, page)

    # AND AGAIN IN THE GULF'S CLOCK, on its own link, exactly as every
    # other channel does. Wrapped so a failure in the second render
    # cannot take the first one's guide down with it — the published
    # board is already on disk by the time this runs.
    import dubai_time
    try:
        with dubai_time.the_other_clock(
                globals(), VIEWER=dubai_time.DUBAI,
                VIEWER_NAME=dubai_time.DUBAI_NAME, OUTPUT=DUBAI_OUTPUT,
                CHANNEL_ID=DUBAI_CHANNEL_ID, BOARD_PREFIX=DUBAI_BOARD_PREFIX,
                RAW=DUBAI_RAW):
            publish(now, mode, page)
    except Exception as exc:                                  # noqa: BLE001
        warn(f"the UAE-clock F1 guide could not be written ({exc}) — "
             f"the published one is unchanged")
    _keep(state)
    return result


if __name__ == "__main__":
    raise SystemExit(build())
