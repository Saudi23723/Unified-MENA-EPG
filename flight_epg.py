#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""✈️ رحلات اليوم — channel 6, rebuilt: the Amman and Abu Dhabi airport boards.

Asked for in those words — "the flight tracker channel is a mess", then
"rebuild it from scratch", then, for what it should carry, "Amman airport
+ Abu Dhabi airport".

WHY THE OLD CHANNEL WAS WRONG. It read aircraft POSITIONS off a live map
and GUESSED every time on the board: a plane in the cruise was given an
arrival ninety minutes away, one on the ground ten, one climbing a
hundred and twenty. That is where the rows of identical "ARR 01:06", the
"SCH 00:00" and the flights marked landed an hour before their own
arrival came from. Nothing on that board had come from a timetable.

WHAT THIS READS INSTEAD. Flightradar24's own airport schedule — the feed
behind its departures and arrivals pages — measured from a runner on
26 September 2026: every row carries the SCHEDULED, ESTIMATED and REAL
instants as UNIX seconds, and the airport's own status word (Scheduled,
Estimated, Delayed, Departed, Landed, Canceled, Diverted). So every time
printed here is one an airport published, and a status is never
inferred from where a plane happens to be.

WHAT A PAGE IS. One airport, one direction — Queen Alia (AMM) and Zayed
International (AUH), departures and arrivals, from an hour ago to six
hours ahead, eight flights a page: the airport board a traveller already
knows how to read. Both links carry both airports; the first prints
every time in Amman's clock, the second in the Gulf's, exactly as every
other channel's two links do.

It is built by one_pass.py with the rest of the screens, so its boards
and its reel live on hls-segments like theirs, and nothing of it is
committed to main on every redraw any more.
"""
from __future__ import annotations

import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

import board_links
from epg_lib import add_programme, log, new_session, warn, write_xml_atomic
from match_board import (
    H, MUTED, PAD, PANEL, PANEL_ALT, PILL, RULE, W, WHITE,
    backdrop, date_chip, draw_signature, draw_text, forget_boards_past,
    progress, rule, size_that_fits,
)

UTC = timezone.utc

CHANNEL_ID = "FlightTracker"
CHANNEL_AR = "رحلات اليوم"
CHANNEL_EN = "Flight Tracker"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/flight_tracker.png")
BOARD_DIR = "boards"

OUTPUT = "flight_epg.xml"
BOARD_PREFIX = "flight_tracker_"
VIEWER = ZoneInfo("Asia/Amman")
VIEWER_NAME = "بتوقيت الأردن"

DUBAI_OUTPUT = "dubai_flight_epg.xml"
DUBAI_CHANNEL_ID = "FlightTrackerDubai"
DUBAI_BOARD_PREFIX = "dubai_flight_tracker_"
DUBAI_VIEWER = ZoneInfo("Asia/Dubai")
DUBAI_VIEWER_NAME = "بتوقيت الإمارات"

# The two airports asked for, in the order asked.
AIRPORTS = (
    ("AMM", "مطار الملكة علياء الدولي", "Queen Alia International · Amman"),
    ("AUH", "مطار زايد الدولي", "Zayed International · Abu Dhabi"),
)
DIRECTIONS = (("departures", "المغادرة", "DEPARTURES"),
              ("arrivals", "القادمة", "ARRIVALS"))

API = ("https://api.flightradar24.com/common/v1/airport.json?code={code}"
       "&plugin[]=schedule&plugin-setting[schedule][mode]={mode}"
       "&plugin-setting[schedule][timestamp]={ts}&page={page}&limit=100")
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124 Safari/537.36"),
    "Accept": "application/json",
    "Origin": "https://www.flightradar24.com",
    "Referer": "https://www.flightradar24.com/",
}

# From an hour ago — the flight that just left or just landed is still the
# answer to "did it go?" — to six hours ahead, which is what an airport's
# own board shows.
BEHIND = timedelta(hours=1)
AHEAD = timedelta(hours=6)
ON_A_PAGE = 8
PAGES_EACH = 2           # per airport and direction: sixteen flights

# The last answer each airport gave, so one refused request does not take
# a whole airport off the screen for a pass.
STATE = "flight_state.json"
KEEP_STATE_FOR = timedelta(hours=3)

# The status pill: the words and the colour a traveller reads first.
GREY = (120, 136, 160, 255)
GREEN = (52, 211, 153, 255)
AMBER = (251, 191, 36, 255)
RED = (248, 113, 113, 255)
BLUE = (96, 165, 250, 255)


# ------------------------------------------------------------------ source

def _read(session, code: str, mode: str, now: datetime) -> list[dict]:
    """Every flight of one airport and direction inside the window."""
    rows, page = [], 1
    while page <= 3:
        url = API.format(code=code, mode=mode, ts=int(now.timestamp()),
                         page=page)
        got = session.get(url, headers=HEADERS, timeout=40)
        got.raise_for_status()
        schedule = (got.json()["result"]["response"]["airport"]
                    ["pluginData"]["schedule"][mode])
        data = schedule.get("data") or []
        rows += data
        last = (schedule.get("page") or {}).get("total") or 1
        if page >= last or not data:
            break
        # Stop as soon as the page is past the window: the feed is in
        # scheduled order.
        tail = data[-1]["flight"]["time"]["scheduled"]
        key = "departure" if mode == "departures" else "arrival"
        if tail.get(key) and tail[key] > (now + AHEAD).timestamp():
            break
        page += 1
        time.sleep(1.5)
    return rows


def _when(stamp) -> datetime | None:
    return datetime.fromtimestamp(stamp, UTC) if stamp else None


def one_flight(row: dict, mode: str) -> dict | None:
    """The row this board draws, from one schedule entry — or None."""
    f = row.get("flight") or {}
    ident = (f.get("identification") or {}).get("number") or {}
    number = ident.get("default") or ""
    if not number:
        return None
    times = f.get("time") or {}
    key = "departure" if mode == "departures" else "arrival"
    scheduled = _when((times.get("scheduled") or {}).get(key))
    if not scheduled:
        return None
    other = (f.get("airport") or {}).get(
        "destination" if mode == "departures" else "origin") or {}
    code = ((other.get("code") or {}).get("iata")) or ""
    city = (((other.get("position") or {}).get("region") or {}).get("city")
            or other.get("name") or code)
    airline = (f.get("airline") or {}).get("name") or ""
    status = f.get("status") or {}
    generic = ((status.get("generic") or {}).get("status") or {})
    return {
        "number": number,
        "airline": airline,
        "place": city,
        "iata": code,
        "scheduled": scheduled,
        "estimated": _when((times.get("estimated") or {}).get(key)),
        "real": _when((times.get("real") or {}).get(key)),
        "word": (generic.get("text") or "").lower(),
        "said": status.get("text") or "",
        "live": bool(status.get("live")),
        "mode": mode,
    }


def _load_state() -> dict:
    try:
        with open(STATE, encoding="utf-8") as src:
            return json.load(src)
    except (OSError, ValueError):
        return {}


def collect(session, now: datetime) -> dict:
    """Every airport and direction: the flights inside the window."""
    state = _load_state()
    out = {}
    for code, _ar, _en in AIRPORTS:
        for mode, _mar, _men in DIRECTIONS:
            key = f"{code}:{mode}"
            try:
                raw = _read(session, code, mode, now)
                state[key] = {"at": now.isoformat(), "rows": raw}
            except Exception as exc:                          # noqa: BLE001
                kept = state.get(key) or {}
                age = now - datetime.fromisoformat(kept.get("at", "1970-01-01T00:00:00+00:00"))
                if kept and age < KEEP_STATE_FOR:
                    warn(f"flights: {key} did not answer ({exc}) — the last "
                         f"answer, {int(age.total_seconds() // 60)} min old, "
                         f"stands")
                    raw = kept["rows"]
                else:
                    warn(f"flights: {key} did not answer ({exc}) and nothing "
                         f"recent is kept — that board is empty this pass")
                    raw = []
            flights = [x for x in (one_flight(r, mode) for r in raw) if x]
            flights = [x for x in flights
                       if now - BEHIND <= (x["real"] or x["estimated"]
                                           or x["scheduled"])
                       and x["scheduled"] <= now + AHEAD]
            flights.sort(key=lambda x: x["scheduled"])
            seen, kept_rows = set(), []
            for x in flights:
                if (x["number"], x["scheduled"]) not in seen:
                    seen.add((x["number"], x["scheduled"]))
                    kept_rows.append(x)
            out[key] = kept_rows[:ON_A_PAGE * PAGES_EACH]
            log(f"  flights {key}: {len(raw)} row(s) read, "
                f"{len(out[key])} on the board")
    try:
        with open(STATE + ".tmp", "w", encoding="utf-8") as dst:
            json.dump(state, dst, separators=(",", ":"))
        os.replace(STATE + ".tmp", STATE)
    except OSError as exc:
        warn(f"flights: the kept answers could not be written ({exc})")
    return out


# ------------------------------------------------------------------ board

def status_of(x: dict, zone) -> tuple[str, tuple]:
    """The pill: what an airport's own board would say, and its colour."""
    def hm(t):
        return t.astimezone(zone).strftime("%H:%M")

    word = x["word"]
    late = (x["estimated"] and x["estimated"] - x["scheduled"]
            > timedelta(minutes=15))
    if word in ("canceled", "cancelled"):
        return "ملغاة", RED
    if word == "diverted":
        return "حُوّلت", RED
    if x["mode"] == "departures":
        if x["real"]:
            return f"غادرت {hm(x['real'])}", GREEN
        if word == "delayed" or late:
            return f"متأخرة {hm(x['estimated'])}" if x["estimated"] else "متأخرة", AMBER
        if x["estimated"]:
            return f"متوقعة {hm(x['estimated'])}", BLUE
        return "في الموعد", GREY
    if x["real"] or word == "landed":
        return f"وصلت {hm(x['real'])}" if x["real"] else "وصلت", GREEN
    if x["live"] or word == "estimated" and x["estimated"]:
        if late or word == "delayed":
            return f"متأخرة · تصل {hm(x['estimated'])}", AMBER
        if x["estimated"]:
            return f"في الجو · تصل {hm(x['estimated'])}", BLUE
    if word == "delayed" or late:
        return f"متأخرة {hm(x['estimated'])}" if x["estimated"] else "متأخرة", AMBER
    return "مجدولة", GREY


def draw_page(code, name_ar, name_en, mode_ar, mode_en, flights, zone,
              zone_name, now, page, pages) -> Image.Image:
    board = backdrop()
    pen = ImageDraw.Draw(board)
    accent = GREEN if mode_en == "DEPARTURES" else BLUE

    draw_text(pen, (PAD, PAD - 6), f"{name_ar} · {mode_ar}", 40, WHITE,
              weight="heavy")
    draw_text(pen, (PAD, PAD + 48), f"{name_en} · {mode_en} · {zone_name}",
              19, MUTED, thin=True)
    date_chip(pen, W - PAD, PAD - 6, now.astimezone(zone).strftime("%d.%m.%Y · %H:%M"))
    draw_signature(pen)

    top = PAD + 100
    rule(pen, top, accent)

    heads = ("الوقت", "الرحلة", "إلى" if mode_en == "DEPARTURES" else "من", "الحالة")
    xs = (PAD + 6, PAD + 130, PAD + 420, W - PAD - 6)
    for i, text in enumerate(heads):
        draw_text(pen, (xs[i], top + 18), text, 16, MUTED,
                  anchor="ra" if i == 3 else "la", thin=True)

    if not flights:
        draw_text(pen, (W // 2, H // 2 + 30), "لا رحلات في هذه الساعات", 30,
                  MUTED, anchor="mm")
        progress(pen, page, pages, accent)
        return board

    y = top + 46
    height = (H - y - PAD - 10) // ON_A_PAGE
    for i, x in enumerate(flights):
        band = [PAD - 12, y, W - PAD + 12, y + height - 6]
        pen.rounded_rectangle(band, radius=10,
                              fill=PANEL if i % 2 == 0 else PANEL_ALT,
                              outline=RULE, width=1)
        mid = y + (height - 6) // 2
        draw_text(pen, (xs[0], mid), x["scheduled"].astimezone(zone).strftime("%H:%M"),
                  30, accent, anchor="lm", weight="heavy")
        draw_text(pen, (xs[1], mid - 11), x["number"], 26, WHITE, anchor="lm",
                  weight="heavy")
        draw_text(pen, (xs[1], mid + 16), x["airline"],
                  size_that_fits(x["airline"], 15, 11, 270), MUTED,
                  anchor="lm", thin=True)
        place = f"{x['place']} ({x['iata']})" if x["iata"] else x["place"]
        draw_text(pen, (xs[2], mid), place, size_that_fits(place, 27, 16, 440),
                  WHITE, anchor="lm")
        said, tone = status_of(x, zone)
        size = size_that_fits(said, 21, 14, 250)
        wide = 270
        pill = [W - PAD - wide, mid - 20, W - PAD, mid + 20]
        pen.rounded_rectangle(pill, radius=20, fill=PILL, outline=tone, width=2)
        draw_text(pen, ((pill[0] + pill[2]) // 2, mid), said, size, tone,
                  anchor="mm", weight="heavy")
        y += height

    progress(pen, page, pages, accent)
    return board


def pages_of(board: dict) -> list[tuple]:
    out = []
    for code, name_ar, name_en in AIRPORTS:
        for mode, mode_ar, mode_en in DIRECTIONS:
            flights = board.get(f"{code}:{mode}") or []
            chunks = [flights[i:i + ON_A_PAGE]
                      for i in range(0, len(flights), ON_A_PAGE)] or [[]]
            for part in chunks:
                out.append((code, name_ar, name_en, mode_ar, mode_en, part))
    return out


def publish(board: dict, now: datetime, prefix: str, zone, zone_name,
            channel_id: str, output: str) -> bool:
    os.makedirs(BOARD_DIR, exist_ok=True)
    pages = pages_of(board)
    for number, (code, name_ar, name_en, mode_ar, mode_en, part) in enumerate(pages):
        picture = draw_page(code, name_ar, name_en, mode_ar, mode_en, part,
                            zone, zone_name, now, number + 1, len(pages))
        picture.convert("RGB").save(os.path.join(BOARD_DIR, f"{prefix}{number}.png"))
    forget_boards_past(prefix, len(pages), BOARD_DIR)

    tv = ET.Element("tv", {"generator-info-name": "Flight Tracker"})
    channel = ET.SubElement(tv, "channel", {"id": channel_id})
    ET.SubElement(channel, "icon", {"src": LOGO})
    ET.SubElement(channel, "display-name", {"lang": "ar"}).text = CHANNEL_AR
    ET.SubElement(channel, "display-name", {"lang": "en"}).text = CHANNEL_EN
    lines = [f"{CHANNEL_AR} · {zone_name}", ""]
    for code, name_ar, _en in AIRPORTS:
        for mode, mode_ar, _men in DIRECTIONS:
            for x in (board.get(f"{code}:{mode}") or [])[:6]:
                said, _tone = status_of(x, zone)
                lines.append(f"{name_ar} · {mode_ar} · "
                             f"{x['scheduled'].astimezone(zone):%H:%M} "
                             f"{x['number']} {x['place']} — {said}")
    link = board_links.link(prefix + "{n}.png")
    opens = now.replace(minute=0, second=0, microsecond=0)
    for step in range(6):
        start = opens + timedelta(hours=step)
        add_programme(tv, channel_id, start, start + timedelta(hours=1),
                      title=f"✈ {CHANNEL_AR} — عمّان وأبوظبي",
                      desc="\n".join(lines), icon=link.format(n=0))
    ok = write_xml_atomic(tv, output, generator_name="Flight Tracker",
                          guard_regression=False, min_programmes=1)
    log(f"{CHANNEL_AR} ({zone_name}): {len(pages)} board(s)")
    return ok


def build() -> int:
    now = datetime.now(UTC)
    board = collect(new_session(), now)
    if not any(board.values()):
        warn("flights: no airport answered and nothing is kept — the "
             "published boards stay as they are")
        return 1
    ok = publish(board, now, BOARD_PREFIX, VIEWER, VIEWER_NAME,
                 CHANNEL_ID, OUTPUT)
    try:
        publish(board, now, DUBAI_BOARD_PREFIX, DUBAI_VIEWER,
                DUBAI_VIEWER_NAME, DUBAI_CHANNEL_ID, DUBAI_OUTPUT)
    except Exception as exc:                                  # noqa: BLE001
        warn(f"the UAE-clock flight boards could not be drawn ({exc})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
