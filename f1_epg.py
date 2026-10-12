#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""الفورمولا 1 — one page: this race weekend, like the official card.

Asked for in these words: a Formula 1 channel, simple, like the official
race-weekend card — one page for the current or next race. Two links, as
every dashboard channel has: the main one in the reader's own time, the
UAE one in the UAE's time only. A session that is over is struck through;
when race day is over on that link's clock the page turns to the next
Grand Prix.

WHERE THE TIMES COME FROM. OpenF1 (api.openf1.org), which publishes every
session of the season with its start, its end and the track's own UTC
offset — so "the race's time" is the circuit's clock as the series
prints it, not a guess from a country name. The 2026 card for Sepang
("Bahrain Grand Prix in Malaysia": FP1 04:30 UTC, 12:30 local) reads
back exactly. If OpenF1 does not answer, the Jolpica (Ergast) calendar
gives the same UTC times, and the circuit's offset is kept from the last
good reading; if neither answers, the last good reading is used whole.

"YOUR TIME" is the reader's own clock — Henderson, Nevada, the same city
the prayer board carries for them (America/Los_Angeles, so it follows
Pacific summer time by itself). The UAE link is Asia/Dubai.

NOTHING ON THE BOARD MOVES FASTER THAN A SESSION. The board changes when
a session starts, when it ends and when the page turns — a handful of
times a weekend — never on a clock, so the reel's segments are not
renamed under a television every pass (prayer_epg.py says why that
matters).

    python f1_epg.py

Writes f1_epg.xml and boards/f1_0.png (your time), dubai_f1_epg.xml and
boards/dubai_f1_0.png (the UAE's), and the fallback reading
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
CACHE = "f1_schedule.json"

OPENF1_SESSIONS = "https://api.openf1.org/v1/sessions"
OPENF1_MEETINGS = "https://api.openf1.org/v1/meetings"
JOLPICA = "https://api.jolpi.ca/ergast/f1/{year}.json"

# ONE CLOCK A LINK, as asked: the main link in the reader's own time, the
# UAE link in the UAE's time and nothing else — the same two sets every
# other dashboard channel comes in.
MINE = ZoneInfo("America/Los_Angeles")
MINE_NAME = "بتوقيتك"
DUBAI = ZoneInfo("Asia/Dubai")
DUBAI_NAME = "بتوقيت الإمارات"

DUBAI_OUTPUT = "dubai_f1_epg.xml"
DUBAI_CHANNEL_ID = "Formula1Dubai"
DUBAI_BOARD_PREFIX = "dubai_f1_"

# (clock, its name on the board, guide file, channel id, board prefix)
CLOCKS = (
    (MINE, MINE_NAME, OUTPUT, CHANNEL_ID, BOARD_PREFIX),
    (DUBAI, DUBAI_NAME, DUBAI_OUTPUT, DUBAI_CHANNEL_ID, DUBAI_BOARD_PREFIX),
)

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


def page_turns(weekend: dict, clock=MINE) -> datetime:
    """The end of race day on the viewer's clock — when the page turns."""
    race = race_of(weekend)
    end = max(when(race["start"]) + timedelta(hours=2), when(race["stop"]))
    day = end.astimezone(clock).date()
    return datetime(day.year, day.month, day.day,
                    tzinfo=clock).astimezone(UTC) + timedelta(days=1)


def on_the_page(weekends: list[dict], now: datetime,
                clock=MINE) -> dict | None:
    """The weekend under way, or the next one."""
    ahead = [w for w in weekends if page_turns(w, clock) > now]
    return min(ahead, key=lambda w: page_turns(w, clock)) if ahead else None


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


def draw_board(weekend: dict | None, now: datetime, clock=MINE,
               clock_name: str = MINE_NAME) -> Image.Image:
    """The weekend card: each session, its day and its time — one clock."""
    board = backdrop()
    pen = ImageDraw.Draw(board)
    draw_signature(pen)

    # The red bar beside the title, as on the official card.
    pen.rounded_rectangle([PAD, PAD + 4, PAD + 14, PAD + 74], radius=4,
                          fill=RED)
    draw_text(pen, (PAD + 32, PAD - 2), f"{CHANNEL_AR} · {clock_name}", 30,
              MUTED, thin=True)

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

    # SESSION · DAY · TIME, the official card's three columns.
    day_x = PAD + 470
    time_x = W - PAD - 10
    head_y = top + 26
    draw_text(pen, (PAD + 6, head_y), "SESSION", 19, MUTED, anchor="lm",
              weight="heavy")
    draw_text(pen, (day_x, head_y), "اليوم", 20, MUTED, anchor="mm",
              weight="heavy")
    draw_text(pen, (time_x, head_y), clock_name, 20, MUTED, anchor="rm",
              weight="heavy")

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

        code = session["code"]
        draw_text(pen, (PAD + 6, mid - 12), code, 32, ink, anchor="lm",
                  weight="heavy")
        under = "مباشر الآن" if state == "live" else SESSION_AR.get(code, "")
        draw_text(pen, (PAD + 6, mid + 22), under, 17,
                  LIVE if state == "live" else (STRUCK if state == "done"
                                                else MUTED),
                  anchor="lm", thin=state != "live")

        day, hhmm = stamp(when(session["start"]), clock)
        here = when(session["start"]).astimezone(clock)
        draw_text(pen, (day_x, mid - 10), day, 30, ink, anchor="mm",
                  weight="heavy")
        draw_text(pen, (day_x, mid + 22), f"{here:%d.%m}", 17,
                  STRUCK if state == "done" else MUTED, anchor="mm",
                  thin=True)
        draw_text(pen, (time_x, mid), hhmm, 44,
                  STRUCK if state == "done" else RED, anchor="rm",
                  weight="heavy")

        if state == "done":
            pen.line([(PAD, mid), (W - PAD, mid)], fill=STRUCK, width=3)
        y += height

    return board


# THE SAME PAGE, SEVEN TIMES. The channel plays La Chona under its card,
# asked for from 0:26 (audio/theme_f1.m4a, 140 s). A reel carries the
# slice of the music its board's place lands on, so a one-board reel would
# play the same twenty seconds over and over; seven copies of the page at
# twenty seconds each are the whole 140 s, played straight through and
# round again at the seam the file was built to hide. Same picture, so
# the viewer sees one page.
REPEATS = 7


def draw_page(weekend: dict | None, now: datetime, clock, clock_name: str,
              prefix: str) -> None:
    os.makedirs(BOARD_DIR, exist_ok=True)
    board = draw_board(weekend, now, clock, clock_name).convert("RGB")
    for n in range(REPEATS):
        board.save(os.path.join(BOARD_DIR, f"{prefix}{n}.png"))
    forget_boards_past(prefix, REPEATS, BOARD_DIR)


# ------------------------------------------------------------------ guide

def describe(weekend: dict, clock, clock_name: str) -> str:
    lines = [weekend["official"] or weekend["name"], clock_name, ""]
    for session in weekend["sessions"]:
        day, hhmm = stamp(when(session["start"]), clock)
        lines.append(f"{session['code']} — {day} {hhmm}")
    return "\n".join(lines)


def write_guide(weekends: list[dict], now: datetime, clock, clock_name: str,
                output: str, channel_id: str, prefix: str) -> bool:
    tv = ET.Element("tv", {"generator-info-name": CHANNEL_EN})
    channel = ET.SubElement(tv, "channel", {"id": channel_id})
    ET.SubElement(channel, "icon", {"src": LOGO})
    ET.SubElement(channel, "display-name", {"lang": "ar"}).text = CHANNEL_AR
    ET.SubElement(channel, "display-name", {"lang": "en"}).text = CHANNEL_EN

    icon = board_links.link(f"{prefix}0.png")
    floor = now - GUIDE_BACK
    cursor = floor.replace(minute=0, second=0, microsecond=0)
    for weekend in sorted(weekends, key=lambda w: page_turns(w, clock)):
        if page_turns(weekend, clock) <= floor:
            continue
        desc = describe(weekend, clock, clock_name)
        for session in weekend["sessions"]:
            start, stop = when(session["start"]), when(session["stop"])
            if stop <= cursor:
                continue
            start = max(start, cursor)
            if start > cursor:
                add_programme(tv, channel_id, cursor, start,
                              title=f"🏁 {weekend['name']}", desc=desc,
                              icon=icon)
            add_programme(tv, channel_id, start, stop,
                          title=f"🏎️ {session['code']} · {weekend['name']}",
                          desc=desc, icon=icon, live_eligible=True, now=now)
            cursor = stop
    return write_xml_atomic(tv, output, generator_name=CHANNEL_EN,
                            guard_regression=False, min_programmes=1)


def build() -> int:
    now = datetime.now(UTC)
    weekends = season(new_session(), now)
    if not weekends:
        warn("no Formula 1 calendar to show — the published boards and "
             "guides are left exactly as they were")
        return 1
    ok = True
    for clock, name, output, channel_id, prefix in CLOCKS:
        weekend = on_the_page(weekends, now, clock)
        draw_page(weekend, now, clock, name, prefix)
        if weekend:
            log(f"  {name}: {weekend['name']} (round {weekend['round']}), "
                f"turns {page_turns(weekend, clock):%Y-%m-%d %H:%M} UTC")
        ok = write_guide(weekends, now, clock, name, output, channel_id,
                         prefix) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
