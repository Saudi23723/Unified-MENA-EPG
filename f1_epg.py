#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""الفورمولا 1 — one page: this race weekend, in three clocks.

Asked for in these words: a Formula 1 channel, simple, like the official
race-weekend card — one page for the current or next race, each session
in "my time / Abu Dhabi's time / the race's time". A session that is
over is struck through; when the race day is over the page turns to the
next Grand Prix.

WHERE THE TIMES COME FROM. OpenF1 (api.openf1.org), which publishes every
session of the season with its start, its end and the track's own UTC
offset — so "the race's time" is the circuit's clock as the series
prints it, not a guess from a country name. The 2026 card for Sepang
("Bahrain Grand Prix in Malaysia": FP1 04:30 UTC, 12:30 local) reads
back exactly. If OpenF1 does not answer, the Jolpica (Ergast) calendar
gives the same UTC times, and the circuit's offset is kept from the last
good reading; if neither answers, the last good reading is used whole.

"MY TIME" is the reader's own clock — Henderson, Nevada, the same city
the prayer board carries for them (America/Los_Angeles, so it follows
Pacific summer time by itself).

NOTHING ON THE BOARD MOVES FASTER THAN A SESSION. The board changes when
a session starts, when it ends and when the page turns — a handful of
times a weekend — never on a clock, so the reel's segments are not
renamed under a television every pass (prayer_epg.py says why that
matters).

    python f1_epg.py

Writes f1_epg.xml, boards/f1_0.png and the fallback reading
f1_schedule.json.
"""
from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

import board_links
from epg_lib import (
    add_programme, fetch, log, new_session, warn, write_xml_atomic,
)
from match_board import (
    H, MUTED, PAD, PANEL, PANEL_ALT, RULE, W, WHITE,
    backdrop, draw_signature, draw_text, forget_boards_past, rule,
    size_that_fits,
)

UTC = timezone.utc

CHANNEL_ID = "Formula1"
CHANNEL_AR = "الفورمولا 1"
CHANNEL_EN = "Formula 1"
OUTPUT = "f1_epg.xml"
BOARD_DIR = "boards"
BOARD_PREFIX = "f1_"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/f1.png")
RAW_BOARD = board_links.link(BOARD_PREFIX + "{n}.png")
CACHE = "f1_schedule.json"

OPENF1_SESSIONS = "https://api.openf1.org/v1/sessions"
OPENF1_MEETINGS = "https://api.openf1.org/v1/meetings"
JOLPICA = "https://api.jolpi.ca/ergast/f1/{year}.json"

# The three clocks, left to right as asked: mine, Abu Dhabi's, the race's.
MINE = ZoneInfo("America/Los_Angeles")
MINE_NAME = "وقتي · هندرسون"
ABU_DHABI = ZoneInfo("Asia/Dubai")
ABU_DHABI_NAME = "أبو ظبي"

# How each session is called on the card, the way the official card
# calls it.
SESSION_NAMES = {
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
    "Sprint Qualifying": "SPRINT QUALI",
    "Sprint Shootout": "SPRINT QUALI",
    "Sprint": "SPRINT",
    "Qualifying": "QUALI",
    "Race": "RACE",
}
SESSION_AR = {
    "FP1": "التجارب الحرة 1", "FP2": "التجارب الحرة 2",
    "FP3": "التجارب الحرة 3", "SPRINT QUALI": "تأهيل السبرينت",
    "SPRINT": "السبرينت", "QUALI": "التأهيل",
    "RACE": "السباق",
}
JOLPICA_KEYS = (
    ("FirstPractice", "FP1"), ("SecondPractice", "FP2"),
    ("ThirdPractice", "FP3"), ("SprintQualifying", "SPRINT QUALI"),
    ("SprintShootout", "SPRINT QUALI"), ("Sprint", "SPRINT"),
    ("Qualifying", "QUALI"),
)
# How long a session runs when the source gives no end.
LENGTH = {"FP1": 60, "FP2": 60, "FP3": 60, "SPRINT QUALI": 45,
          "SPRINT": 60, "QUALI": 60, "RACE": 120}

DAYS_AR = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة",
           "السبت", "الأحد")

RED = (232, 0, 45, 255)
STRUCK = (96, 110, 132, 255)
LIVE = (255, 80, 96, 255)

GUIDE_BACK = timedelta(days=1)


# ---------------------------------------------------------------- reading

def offset_of(text: str | None) -> int | None:
    """OpenF1's "08:00:00" or "-05:00:00" as minutes east of UTC."""
    if not text:
        return None
    sign = -1 if text.startswith("-") else 1
    parts = text.lstrip("+-").split(":")
    try:
        return sign * (int(parts[0]) * 60 + int(parts[1]))
    except (ValueError, IndexError):
        return None


def when(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def from_openf1(session, year: int) -> list[dict]:
    """Every Grand Prix weekend of the year, from OpenF1."""
    meetings = fetch(session, OPENF1_MEETINGS, params={"year": year}).json()
    rows = fetch(session, OPENF1_SESSIONS, params={"year": year}).json()
    named = {m["meeting_key"]: m for m in meetings}
    weekends: dict[int, dict] = {}
    for row in rows:
        code = SESSION_NAMES.get(row.get("session_name") or "")
        meeting = named.get(row.get("meeting_key"))
        if not code or not meeting or "Grand Prix" not in (
                meeting.get("meeting_name") or ""):
            continue
        start = when(row["date_start"])
        stop = when(row["date_end"]) if row.get("date_end") else \
            start + timedelta(minutes=LENGTH[code])
        weekend = weekends.setdefault(meeting["meeting_key"], {
            "name": meeting.get("meeting_name") or "",
            "official": meeting.get("meeting_official_name") or "",
            "location": meeting.get("location") or row.get("location") or "",
            "country": meeting.get("country_name") or "",
            "offset": offset_of(row.get("gmt_offset")
                                or meeting.get("gmt_offset")),
            "sessions": [],
        })
        weekend["sessions"].append({"code": code, "start": start.isoformat(),
                                    "stop": stop.isoformat()})
    out = [w for w in weekends.values()
           if any(s["code"] == "RACE" for s in w["sessions"])
           and w["offset"] is not None]
    for weekend in out:
        weekend["sessions"].sort(key=lambda s: s["start"])
    out.sort(key=lambda w: w["sessions"][-1]["start"])
    for number, weekend in enumerate(out, 1):
        weekend["round"] = number
    return out


def from_jolpica(session, year: int, known: list[dict]) -> list[dict]:
    """The same weekends from Jolpica; the track's clock from the last
    good reading, matched by race day, since Jolpica gives none."""
    body = fetch(session, JOLPICA.format(year=year)).json()
    offsets = {}
    for weekend in known:
        race = [s for s in weekend["sessions"] if s["code"] == "RACE"]
        if race:
            offsets[race[0]["start"][:10]] = weekend["offset"]
    out = []
    for race in body["MRData"]["RaceTable"]["Races"]:
        sessions = []
        for key, code in JOLPICA_KEYS + (("", "RACE"),):
            part = race if code == "RACE" else race.get(key)
            if not part or not part.get("time"):
                continue
            start = when(f"{part['date']}T{part['time']}")
            sessions.append({"code": code, "start": start.isoformat(),
                             "stop": (start + timedelta(
                                 minutes=LENGTH[code])).isoformat()})
        offset = offsets.get(race["date"])
        if offset is None or not sessions:
            continue
        circuit = race.get("Circuit", {})
        location = circuit.get("Location", {})
        sessions.sort(key=lambda s: s["start"])
        out.append({"name": race.get("raceName") or "",
                    "official": "",
                    "location": location.get("locality") or "",
                    "country": location.get("country") or "",
                    "offset": offset, "round": int(race.get("round") or 0),
                    "sessions": sessions})
    return out


def official_rounds(session, weekends: list[dict], now: datetime) -> None:
    """The series' own round numbers and names, matched by race day.

    OpenF1 lists meetings that were moved or called off beside the ones
    that replaced them, so counting its weekends is not the round. Jolpica
    numbers the calendar as raced; where it does not answer, the count
    stands.
    """
    rounds = {}
    for year in {when(race_of(w)["start"]).year for w in weekends}:
        try:
            body = fetch(session, JOLPICA.format(year=year)).json()
        except Exception as exc:                            # noqa: BLE001
            log(f"  round numbers for {year}: Jolpica did not answer ({exc})")
            continue
        for race in body["MRData"]["RaceTable"]["Races"]:
            rounds[race["date"]] = race
    for weekend in weekends:
        race = rounds.get(race_of(weekend)["start"][:10])
        if not race:
            continue
        weekend["round"] = int(race.get("round") or weekend["round"])
        # The race as the calendar names it, and where it is run. OpenF1
        # files a moved race under its old meeting: the 2026 Sepang round
        # is "Bahrain Grand Prix" in "Bahrain" there, and "Bahrain Grand
        # Prix in Malaysia" in Kuala Lumpur, Malaysia on the calendar.
        location = race.get("Circuit", {}).get("Location", {})
        weekend["name"] = race.get("raceName") or weekend["name"]
        weekend["location"] = location.get("locality") or weekend["location"]
        weekend["country"] = location.get("country") or weekend["country"]


def cached() -> list[dict]:
    if not os.path.exists(CACHE):
        return []
    try:
        with open(CACHE, encoding="utf-8") as handle:
            return json.load(handle).get("weekends") or []
    except (OSError, ValueError) as exc:
        warn(f"{CACHE} could not be read ({exc})")
        return []


def remember(weekends: list[dict], now: datetime, source: str) -> None:
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump({"updated_at": now.isoformat(timespec="seconds"),
                   "source": source, "weekends": weekends},
                  handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, CACHE)


def season(session, now: datetime) -> list[dict]:
    """This year's weekends and next year's, from the best source left."""
    known = cached()
    for name, read in (("OpenF1", lambda y: from_openf1(session, y)),
                       ("Jolpica", lambda y: from_jolpica(session, y, known))):
        weekends: list[dict] = []
        try:
            for year in (now.year, now.year + 1):
                try:
                    weekends.extend(read(year))
                except Exception as exc:                    # noqa: BLE001
                    if year == now.year:
                        raise
                    log(f"  {year}: not published yet ({exc})")
        except Exception as exc:                            # noqa: BLE001
            warn(f"{name} did not answer ({exc})")
            continue
        if weekends:
            if name == "OpenF1":
                official_rounds(session, weekends, now)
            remember(weekends, now, name)
            log(f"  {len(weekends)} Grand Prix weekend(s) from {name}")
            return weekends
    log(f"  using the last good reading in {CACHE}")
    return known


# ---------------------------------------------------------------- choosing

def race_of(weekend: dict) -> dict:
    return [s for s in weekend["sessions"] if s["code"] == "RACE"][-1]


def page_turns(weekend: dict) -> datetime:
    """The end of race day on the reader's clock — when the page turns."""
    race = race_of(weekend)
    end = max(when(race["start"]) + timedelta(hours=2), when(race["stop"]))
    day = end.astimezone(MINE).date()
    return datetime(day.year, day.month, day.day,
                    tzinfo=MINE).astimezone(UTC) + timedelta(days=1)


def on_the_page(weekends: list[dict], now: datetime) -> dict | None:
    """The weekend under way, or the next one."""
    ahead = [w for w in weekends if page_turns(w) > now]
    return min(ahead, key=page_turns) if ahead else None


def state_of(session: dict, now: datetime) -> str:
    if now >= when(session["stop"]):
        return "done"
    if now >= when(session["start"]):
        return "live"
    return "ahead"


# ---------------------------------------------------------------- drawing

def stamp(moment: datetime, zone) -> tuple[str, str]:
    here = moment.astimezone(zone)
    return DAYS_AR[here.weekday()], f"{here:%H:%M}"


def track_zone(weekend: dict):
    return timezone(timedelta(minutes=weekend["offset"]))


def utc_label(minutes: int) -> str:
    sign = "+" if minutes >= 0 else "-"
    hours, mins = divmod(abs(minutes), 60)
    return f"UTC{sign}{hours}" + (f":{mins:02d}" if mins else "")


def draw_board(weekend: dict | None, now: datetime) -> Image.Image:
    board = backdrop()
    pen = ImageDraw.Draw(board)
    draw_signature(pen)

    # The red bars either side of the title, as on the official card.
    pen.rounded_rectangle([PAD, PAD + 4, PAD + 14, PAD + 74], radius=4,
                          fill=RED)
    draw_text(pen, (PAD + 32, PAD - 2), CHANNEL_AR, 30, MUTED, thin=True)

    if weekend is None:
        draw_text(pen, (W // 2, H // 2), "لا يوجد سباق معلن", 34, MUTED,
                  anchor="mm")
        return board

    title = weekend["name"].upper()
    draw_text(pen, (PAD + 32, PAD + 34), title,
              size_that_fits(title, 46, 26, W - 2 * PAD - 330), WHITE,
              weight="heavy")
    race_day = when(race_of(weekend)["start"])
    where = " · ".join(x for x in (weekend["location"], weekend["country"])
                       if x)
    draw_text(pen, (W - PAD, PAD + 34), f"ROUND {weekend['round']} · "
              f"{race_day:%Y}", 24, RED, anchor="ra", weight="heavy")
    draw_text(pen, (W - PAD, PAD + 68), where,
              size_that_fits(where, 22, 14, 320), MUTED, anchor="ra",
              thin=True)

    top = PAD + 122
    rule(pen, top, RED)

    # Columns: the session, then the three clocks, each with its own day —
    # a session on Friday at the track is Thursday night in Nevada.
    zone = track_zone(weekend)
    columns = (
        (MINE, MINE_NAME),
        (ABU_DHABI, ABU_DHABI_NAME),
        (zone, f"وقت السباق · {utc_label(weekend['offset'])}"),
    )
    session_w = 330
    col_w = (W - 2 * PAD - session_w) // 3
    head_y = top + 26
    draw_text(pen, (PAD + 6, head_y), "SESSION", 19, MUTED, anchor="lm",
              weight="heavy")
    for index, (_zone, name) in enumerate(columns):
        cx = PAD + session_w + index * col_w + col_w // 2
        draw_text(pen, (cx, head_y), name, size_that_fits(name, 21, 14,
                  col_w - 16), MUTED, anchor="mm", weight="heavy")

    sessions = weekend["sessions"]
    room = H - (head_y + 24) - PAD
    height = min(96, room // max(1, len(sessions)))
    y = head_y + 24
    for index, session in enumerate(sessions):
        state = state_of(session, now)
        band = [PAD - 12, y, W - PAD + 12, y + height - 8]
        fill = PANEL if index % 2 == 0 else PANEL_ALT
        pen.rounded_rectangle(band, radius=12, fill=fill,
                              outline=LIVE if state == "live" else RULE,
                              width=3 if state == "live" else 1)
        mid = y + (height - 8) // 2
        ink = STRUCK if state == "done" else WHITE
        accent = STRUCK if state == "done" else RED

        code = session["code"]
        draw_text(pen, (PAD + 6, mid - 12), code, 32, ink, anchor="lm",
                  weight="heavy")
        under = SESSION_AR.get(code, "")
        if state == "live":
            under = "مباشر الآن"
        draw_text(pen, (PAD + 6, mid + 22), under, 17,
                  LIVE if state == "live" else (STRUCK if state == "done"
                                                else MUTED),
                  anchor="lm", thin=state != "live")

        start = when(session["start"])
        for slot, (clock, _name) in enumerate(columns):
            cx = PAD + session_w + slot * col_w + col_w // 2
            day, hhmm = stamp(start, clock)
            draw_text(pen, (cx, mid - 14), hhmm, 34, accent if slot == 2
                      else ink, anchor="mm", weight="heavy")
            draw_text(pen, (cx, mid + 22), day, 17, MUTED if state != "done"
                      else STRUCK, anchor="mm", thin=True)

        if state == "done":
            pen.line([(PAD, mid), (W - PAD, mid)], fill=STRUCK, width=3)
        y += height

    return board


def draw_page(weekend: dict | None, now: datetime) -> None:
    os.makedirs(BOARD_DIR, exist_ok=True)
    draw_board(weekend, now).convert("RGB").save(
        os.path.join(BOARD_DIR, f"{BOARD_PREFIX}0.png"))
    forget_boards_past(BOARD_PREFIX, 1, BOARD_DIR)


# ------------------------------------------------------------------ guide

def describe(weekend: dict) -> str:
    zone = track_zone(weekend)
    lines = [weekend["official"] or weekend["name"], ""]
    for session in weekend["sessions"]:
        start = when(session["start"])
        mine = " ".join(stamp(start, MINE))
        abu = " ".join(stamp(start, ABU_DHABI))
        local = " ".join(stamp(start, zone))
        lines.append(f"{session['code']} — وقتي {mine} · أبو ظبي {abu} · "
                     f"الحلبة {local}")
    return "\n".join(lines)


def write_guide(weekends: list[dict], now: datetime) -> bool:
    tv = ET.Element("tv", {"generator-info-name": CHANNEL_EN})
    channel = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(channel, "icon", {"src": LOGO})
    ET.SubElement(channel, "display-name", {"lang": "ar"}).text = CHANNEL_AR
    ET.SubElement(channel, "display-name", {"lang": "en"}).text = CHANNEL_EN

    icon = RAW_BOARD.format(n=0)
    floor = now - GUIDE_BACK
    cursor = floor.replace(minute=0, second=0, microsecond=0)
    for weekend in sorted(weekends, key=page_turns):
        if page_turns(weekend) <= floor:
            continue
        desc = describe(weekend)
        for session in weekend["sessions"]:
            start, stop = when(session["start"]), when(session["stop"])
            if stop <= cursor:
                continue
            start = max(start, cursor)
            if start > cursor:
                add_programme(tv, CHANNEL_ID, cursor, start,
                              title=f"🏁 {weekend['name']}", desc=desc,
                              icon=icon)
            add_programme(tv, CHANNEL_ID, start, stop,
                          title=f"🏎️ {session['code']} · {weekend['name']}",
                          desc=desc, icon=icon, live_eligible=True, now=now)
            cursor = stop
    return write_xml_atomic(tv, OUTPUT, generator_name=CHANNEL_EN,
                            guard_regression=False, min_programmes=1)


def build() -> int:
    now = datetime.now(UTC)
    weekends = season(new_session(), now)
    if not weekends:
        warn("no Formula 1 calendar to show — the published board and guide "
             "are left exactly as they were")
        return 1
    weekend = on_the_page(weekends, now)
    draw_page(weekend, now)
    if weekend:
        log(f"  on the page: {weekend['name']} (round {weekend['round']}), "
            f"turns {page_turns(weekend):%Y-%m-%d %H:%M} UTC")
    ok = write_guide(weekends, now)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
