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
    H, MUTED, W, WHITE, draw_signature, draw_text, forget_boards_past,
    progress, size_that_fits,
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

# THE ROUTE ITSELF, ALL DAY. Asked for in those words — "where is the
# Etihad flight from Amman to Abu Dhabi?" EY592 left Amman at 13:25 that
# day, and a board of the next sixteen departures from 05:40 never
# reached it. So the channel opens on the route the two airports were
# chosen for: every flight between Amman and Abu Dhabi, both ways, from
# an hour ago to a day ahead, whoever flies it. Both directions are read
# from Amman's own feeds — Amman's day fits in two pages, Abu Dhabi's
# does not.
ROUTE_AHEAD = timedelta(hours=24)
ROUTE = (
    ("departures", "AUH", "عمّان إلى أبوظبي", "من عمّان إلى أبوظبي",
     "Amman to Abu Dhabi", "DEPARTURES"),
    ("arrivals", "AUH", "أبوظبي إلى عمّان", "من أبوظبي إلى عمّان",
     "Abu Dhabi to Amman", "ARRIVALS"),
)

# THE CARRIER THE PASSENGER BOOKED, NOT THE ONE THAT HIRED THE PLANE.
# The feed names the operator, and Etihad's Amman flights are flown on
# wet-leased aircraft, so "EY592 · Airhub Airlines" was on the board. The
# flight number's own two letters say whose flight it is.
CARRIERS = {
    "EY": "Etihad Airways", "RJ": "Royal Jordanian", "EK": "Emirates",
    "FZ": "flydubai", "3L": "Air Arabia Abu Dhabi", "G9": "Air Arabia",
    "QR": "Qatar Airways", "TK": "Turkish Airlines", "SV": "Saudia",
    "MS": "EgyptAir", "GF": "Gulf Air", "WY": "Oman Air",
    "KU": "Kuwait Airways", "PC": "Pegasus", "XY": "flynas",
    "F3": "flyadeal", "LH": "Lufthansa", "BA": "British Airways",
    "AF": "Air France", "KL": "KLM", "ME": "Middle East Airlines",
}

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

def _read(session, code: str, mode: str, now: datetime,
          ahead: timedelta = AHEAD) -> list[dict]:
    """Every flight of one airport and direction inside the window."""
    rows, page = [], 1
    while page <= 3:
        url = API.format(code=code, mode=mode,
                         ts=int((now - BEHIND).timestamp()),
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
        if tail.get(key) and tail[key] > (now + ahead).timestamp():
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
    airline = (CARRIERS.get(number[:2].upper())
               or (f.get("airline") or {}).get("name") or "")
    status = f.get("status") or {}
    generic = ((status.get("generic") or {}).get("status") or {})
    return {
        "number": number,
        "airline": airline,
        "place": city,
        "iata": code,
        "scheduled": scheduled,
        # The other end's scheduled time: when a departure lands, when an
        # arrival took off. The route page prints it where the city would
        # only repeat itself.
        "other_end": _when((times.get("scheduled") or {}).get(
            "arrival" if mode == "departures" else "departure")),
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
                raw = _read(session, code, mode, now,
                            ROUTE_AHEAD if code == "AMM" else AHEAD)
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
                       and x["scheduled"] <= now + ROUTE_AHEAD]
            flights.sort(key=lambda x: x["scheduled"])
            seen, kept_rows = set(), []
            for x in flights:
                if (x["number"], x["scheduled"]) not in seen:
                    seen.add((x["number"], x["scheduled"]))
                    kept_rows.append(x)
            for r_mode, other, *_names in ROUTE:
                if code == "AMM" and mode == r_mode:
                    out[f"route:{mode}"] = [
                        x for x in kept_rows
                        if x["iata"] == other
                        and x["scheduled"] <= now + ROUTE_AHEAD][:ON_A_PAGE]
            kept_rows = [x for x in kept_rows if x["scheduled"] <= now + AHEAD]
            # WHAT A TRAVELLER LOOKS FOR FIRST is what has not gone yet:
            # the two flights that most recently left or landed stay on
            # top, as an airport board keeps them, and the rest of the
            # page is what is still to come.
            gone = [x for x in kept_rows if x["real"] and x["real"] <= now]
            coming = [x for x in kept_rows if x not in gone]
            out[key] = (gone[-2:] + coming)[:ROWS]
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


# THE CITIES IN THE BOARD'S OWN LANGUAGE. The feed names them in English;
# a board a reader in Amman or Abu Dhabi reads in Arabic says "القاهرة",
# not "Cairo". Every city both airports served on the day this was
# written, and a city not here is printed as the feed gives it.
CITY_AR = {
    "Abu Dhabi": "أبوظبي", "Addis Ababa": "أديس أبابا", "Ahmedabad": "أحمد آباد",
    "Aleppo": "حلب", "Algiers": "الجزائر", "Amman": "عمّان",
    "Amsterdam": "أمستردام", "Antalya": "أنطاليا", "Aqaba": "العقبة",
    "Athens": "أثينا", "Atlanta": "أتلانتا", "Baghdad": "بغداد",
    "Bahrain": "البحرين", "Baku": "باكو", "Bangkok": "بانكوك",
    "Barcelona": "برشلونة", "Beirut": "بيروت", "Bengaluru": "بنغالور",
    "Benghazi": "بنغازي", "Berlin": "برلين", "Boston": "بوسطن",
    "Budapest": "بودابست", "Cairo": "القاهرة", "Casablanca": "الدار البيضاء",
    "Charlotte": "شارلوت", "Chennai": "تشيناي", "Chicago": "شيكاغو",
    "Cochin": "كوتشي", "Colombo": "كولومبو", "Dallas": "دالاس",
    "Damascus": "دمشق", "Dammam": "الدمام", "Delhi": "دلهي",
    "Denpasar": "بالي", "Dhaka": "دكا", "Doha": "الدوحة", "Dubai": "دبي",
    "Dublin": "دبلن", "Dusseldorf": "دوسلدورف", "Erbil": "أربيل",
    "Frankfurt": "فرانكفورت", "Geneva": "جنيف", "Hamburg": "هامبورغ",
    "Hanoi": "هانوي", "Hong Kong": "هونغ كونغ", "Hyderabad": "حيدر آباد",
    "Islamabad": "إسلام آباد", "Istanbul": "إسطنبول", "Jaipur": "جايبور",
    "Jakarta": "جاكرتا", "Jeddah": "جدة", "Kabul": "كابل",
    "Karachi": "كراتشي", "Kathmandu": "كاتماندو", "Kolkata": "كلكتا",
    "Kozhikode": "كاليكوت", "Kuala Lumpur": "كوالالمبور",
    "Kuwait City": "الكويت", "Lahore": "لاهور", "Larnaca": "لارنكا",
    "London": "لندن", "Lucknow": "لكناو", "Lyon": "ليون", "Madrid": "مدريد",
    "Male": "ماليه", "Manchester": "مانشستر", "Manila": "مانيلا",
    "Medina": "المدينة المنورة", "Milan": "ميلانو", "Montreal": "مونتريال",
    "Moscow": "موسكو", "Multan": "ملتان", "Mumbai": "مومباي",
    "Munich": "ميونخ", "Muscat": "مسقط", "Nairobi": "نيروبي",
    "New York": "نيويورك", "Paris": "باريس", "Peshawar": "بيشاور",
    "Phuket": "بوكيت", "Riyadh": "الرياض", "Rome": "روما",
    "Shanghai": "شنغهاي", "Sharjah": "الشارقة", "Sialkot": "سيالكوت",
    "Sochi": "سوتشي", "Sulaimaniyah": "السليمانية", "Sydney": "سيدني",
    "Tashkent": "طشقند", "Tbilisi": "تبليسي", "Tel Aviv": "تل أبيب",
    "Thiruvananthapuram": "تريفاندرم", "Toronto": "تورونتو",
    "Trabzon": "طرابزون", "Tunis": "تونس", "Vienna": "فيينا",
    "Washington": "واشنطن", "Yerevan": "يريفان", "Zurich": "زيورخ",
    "Basra": "البصرة", "Najaf": "النجف", "Sharm el-Sheikh": "شرم الشيخ",
    "Hurghada": "الغردقة", "Alexandria": "الإسكندرية", "Tabuk": "تبوك",
    "Taif": "الطائف", "Abha": "أبها", "Salalah": "صلالة", "Ankara": "أنقرة",
    "Izmir": "إزمير", "Bodrum": "بودروم", "Bucharest": "بوخارست",
    "Prague": "براغ", "Warsaw": "وارسو", "Brussels": "بروكسل",
    "Stockholm": "ستوكهولم", "Copenhagen": "كوبنهاغن", "Seoul": "سيول",
    "Tokyo": "طوكيو", "Beijing": "بكين", "Singapore": "سنغافورة",
    "Johannesburg": "جوهانسبرغ", "Khartoum": "الخرطوم", "Tripoli": "طرابلس",
    "Mosul": "الموصل", "Kyiv": "كييف", "Almaty": "ألماتي",
    "Victoria": "سيشل", "Kannur": "كانور", "Chiang Rai": "شيانغ راي",
    "Tiruchirapalli": "تيروتشيرابالي", "Faisalabad": "فيصل آباد",
    "Nuremberg": "نورمبرغ", "Phnom Penh": "بنوم بنه", "Ezhou": "إيجو",
}

ROWS = 8                 # flights on an airport page
ROUTE_ROWS = 4           # flights each way on the route page
AIRLINE_LOGOS = "logos/airlines"

# THE LOOK OF AN AIRPORT'S OWN SCREEN. A deep ground, a solid header
# with the direction written large in both languages, a ruled table
# under bilingual column heads, the carrier's own mark on a white tile —
# the way a departures hall shows it — and the status in its colour.
INK = (8, 14, 26)
HEAD_BG = (14, 24, 42)
ROW_A = (13, 22, 38)
ROW_B = (17, 28, 48)
LINE = (34, 50, 78)
TILE = (246, 248, 251)
GOLD = (255, 204, 77, 255)


def city_of(x: dict) -> str:
    return CITY_AR.get(x["place"], x["place"])


def plane(pen, cx: int, cy: int, size: int, angle: float, fill) -> None:
    """An airliner seen from above, nose along `angle` (degrees)."""
    import math
    half = [(1.0, 0), (0.86, 0.07), (0.22, 0.08), (-0.08, 0.66),
            (-0.26, 0.66), (-0.06, 0.08), (-0.56, 0.07), (-0.74, 0.3),
            (-0.86, 0.3), (-0.76, 0.0)]
    outline = half + [(x, -y) for x, y in reversed(half[1:-1])]
    a = math.radians(angle)
    pen.polygon([(cx + size * (x * math.cos(a) - y * math.sin(a)),
                  cy + size * (x * math.sin(a) + y * math.cos(a)))
                 for x, y in outline], fill=fill)


_LOGO_CACHE: dict = {}
MARK_URL = "https://pics.avs.io/400/160/{code}@2x.png"


def _fetch_mark(code: str) -> str | None:
    """A carrier not kept in logos/airlines, fetched once for this run.

    The kept marks are the carriers both airports served when the board
    was drawn; a new one is read from the same source into the runner's
    temporary folder, and a carrier that has none is printed by name.
    """
    import tempfile
    path = os.path.join(tempfile.gettempdir(), f"airline_{code}.png")
    if os.path.exists(path):
        return path
    try:
        got = new_session().get(MARK_URL.format(code=code), timeout=15)
        if got.status_code == 200 and got.content[:4] == b"\x89PNG":
            with open(path, "wb") as dst:
                dst.write(got.content)
            return path
    except Exception as exc:                                  # noqa: BLE001
        log(f"  flights: no mark for {code} ({exc})")
    return None


def airline_mark(code: str):
    """The carrier's mark, trimmed, or None when it is not kept."""
    if code in _LOGO_CACHE:
        return _LOGO_CACHE[code]
    mark = None
    path = os.path.join(AIRLINE_LOGOS, f"{code}.png")
    if code and not os.path.exists(path):
        path = _fetch_mark(code)
    if path and os.path.exists(path):
        try:
            mark = Image.open(path).convert("RGBA")
            box = mark.getbbox()
            if box:
                mark = mark.crop(box)
        except OSError:
            mark = None
    _LOGO_CACHE[code] = mark
    return mark


def draw_carrier(board, pen, x0: int, mid: int, x: dict) -> None:
    """A white tile with the carrier's mark, or its name when none is kept."""
    wide, tall = 168, 44
    mark = airline_mark(x["number"][:2].upper())
    if mark is None:
        draw_text(pen, (x0 + wide // 2, mid), x["airline"],
                  size_that_fits(x["airline"], 16, 10, wide - 8), WHITE,
                  anchor="mm", thin=True)
        return
    pen.rounded_rectangle([x0, mid - tall // 2, x0 + wide, mid + tall // 2],
                          radius=8, fill=TILE)
    room_w, room_h = wide - 18, tall - 10
    scale = min(room_w / mark.width, room_h / mark.height)
    shown = mark.resize((max(1, int(mark.width * scale)),
                         max(1, int(mark.height * scale))), Image.LANCZOS)
    board.paste(shown, (x0 + (wide - shown.width) // 2,
                        mid - shown.height // 2), shown)


def status_tag(pen, x0: int, mid: int, said: str, tone) -> None:
    """The status as a board shows it: a lit dot and the words in colour."""
    base = ROW_A
    fill = tuple(int(base[i] * 0.78 + tone[i] * 0.22) for i in range(3))
    wide = 250
    pen.rounded_rectangle([x0, mid - 21, x0 + wide, mid + 21], radius=10,
                          fill=fill, outline=tone, width=2)
    pen.ellipse([x0 + wide - 26, mid - 6, x0 + wide - 14, mid + 6], fill=tone)
    draw_text(pen, (x0 + wide - 36, mid), said,
              size_that_fits(said, 20, 12, wide - 50), tone, anchor="rm",
              weight="heavy")


# Where each column stands, from the right: the eye starts at the time.
X_TIME = W - 44          # right edge of the time
X_PLACE = W - 186        # right edge of the city
X_FLIGHT = 640           # right edge of the flight number
X_CARRIER = 318          # left edge of the carrier tile
X_STATUS = 44            # left edge of the status


def column_heads(pen, y: int, place_ar: str, place_en: str) -> None:
    for x, ar, en, anchor in ((X_TIME, "الوقت", "TIME", "rm"),
                              (X_PLACE, place_ar, place_en, "rm"),
                              (X_FLIGHT, "الرحلة", "FLIGHT", "rm"),
                              (X_CARRIER + 168, "الناقل", "AIRLINE", "rm"),
                              (X_STATUS + 250, "الحالة", "STATUS", "rm")):
        draw_text(pen, (x, y), f"{ar}  {en}", 15, MUTED, anchor=anchor,
                  thin=True)


def flight_row(board, pen, y: int, height: int, index: int, x: dict, zone,
               *, route: bool = False) -> None:
    pen.rectangle([0, y, W, y + height - 1], fill=ROW_A if index % 2 == 0 else ROW_B)
    pen.line([(0, y + height - 1), (W, y + height - 1)], fill=LINE, width=1)
    mid = y + height // 2
    draw_text(pen, (X_TIME, mid), x["scheduled"].astimezone(zone).strftime("%H:%M"),
              32, WHITE, anchor="rm", weight="heavy")
    if route and x.get("other_end"):
        word = "الوصول" if x["mode"] == "departures" else "الإقلاع"
        draw_text(pen, (X_PLACE, mid - 11),
                  f"{word} {x['other_end'].astimezone(zone):%H:%M}", 25, WHITE,
                  anchor="rm", weight="heavy")
        draw_text(pen, (X_PLACE, mid + 16),
                  "Abu Dhabi (AUH)",
                  14, MUTED, anchor="rm", thin=True)
    else:
        city = city_of(x)
        draw_text(pen, (X_PLACE, mid - 11), city,
                  size_that_fits(city, 27, 16, 420), WHITE, anchor="rm",
                  weight="heavy")
        english = f"{x['place']} ({x['iata']})" if x["iata"] else x["place"]
        draw_text(pen, (X_PLACE, mid + 16), english, 14, MUTED, anchor="rm",
                  thin=True)
    draw_text(pen, (X_FLIGHT, mid), x["number"], 25, GOLD, anchor="rm",
              weight="heavy")
    draw_carrier(board, pen, X_CARRIER, mid, x)
    said, tone = status_of(x, zone)
    status_tag(pen, X_STATUS, mid, said, tone)


def header(pen, title_ar: str, title_en: str, line_ar: str, line_en: str,
           accent, angle: float, zone, now) -> int:
    pen.rectangle([0, 0, W, 118], fill=HEAD_BG)
    pen.rectangle([0, 118, W, 122], fill=accent)
    plane(pen, W - 84, 66, 34, angle, accent)
    draw_text(pen, (W - 136, 50), title_ar, 44, WHITE, anchor="rm",
              weight="heavy")
    draw_text(pen, (W - 136, 94), line_ar, 19, MUTED, anchor="rm", thin=True)
    draw_text(pen, (44, 50), title_en, 34, WHITE, anchor="lm", weight="heavy")
    draw_text(pen, (44, 94), f"{line_en} · {now.astimezone(zone):%d.%m.%Y}",
              17, MUTED, anchor="lm", thin=True)
    draw_signature(pen)
    return 122


def draw_airport(spec: dict, zone, zone_name, now, page, pages) -> Image.Image:
    board = Image.new("RGB", (W, H), INK)
    pen = ImageDraw.Draw(board)
    departing = spec["mode"] == "departures"
    accent = GREEN if departing else BLUE
    top = header(pen, spec["title_ar"], spec["title_en"],
                 f"{spec['airport_ar']} · {zone_name}", spec["airport_en"],
                 accent, -32 if departing else 32, zone, now)
    column_heads(pen, top + 24, "إلى" if departing else "من",
                 "TO" if departing else "FROM")
    y = top + 46
    height = (H - y - 34) // ROWS
    if not spec["rows"]:
        draw_text(pen, (W // 2, y + 160), "لا رحلات في هذه الساعات", 28,
                  MUTED, anchor="mm")
    for i, x in enumerate(spec["rows"]):
        flight_row(board, pen, y + i * height, height, i, x, zone)
    progress(pen, page, pages, accent, y=H - 16)
    return board


def draw_route(spec: dict, zone, zone_name, now, page, pages) -> Image.Image:
    board = Image.new("RGB", (W, H), INK)
    pen = ImageDraw.Draw(board)
    top = header(pen, "عمّان – أبوظبي", "AMMAN – ABU DHABI",
                 f"كل رحلات اليوم بين المدينتين · {zone_name}",
                 "All flights today, both ways", GOLD, 0, zone, now)
    y = top + 14
    height = 52
    for mode, title, accent, angle in (
            ("departures", "من عمّان إلى أبوظبي", GREEN, -32),
            ("arrivals", "من أبوظبي إلى عمّان", BLUE, 32)):
        pen.rectangle([0, y, W, y + 40], fill=HEAD_BG)
        pen.rectangle([W - 8, y, W, y + 40], fill=accent)
        plane(pen, W - 36, y + 20, 14, angle, accent)
        draw_text(pen, (W - 64, y + 20), title, 23, WHITE, anchor="rm",
                  weight="heavy")
        column_heads(pen, y + 56, "الطرف الآخر", "OTHER END")
        y += 70
        rows = spec[mode]
        if not rows:
            draw_text(pen, (W // 2, y + 40), "لا رحلات اليوم على هذا الخط", 22,
                      MUTED, anchor="mm")
            y += ROUTE_ROWS * height
        for i, x in enumerate(rows[:ROUTE_ROWS]):
            flight_row(board, pen, y, height, i, x, zone, route=True)
            y += height
        y += (ROUTE_ROWS - min(len(rows), ROUTE_ROWS)) * height if rows else 0
        y += 8
    progress(pen, page, pages, GOLD, y=H - 16)
    return board


def draw_page(spec: dict, zone, zone_name, now, page, pages) -> Image.Image:
    if spec.get("route"):
        return draw_route(spec, zone, zone_name, now, page, pages)
    return draw_airport(spec, zone, zone_name, now, page, pages)


def pages_of(board: dict) -> list[dict]:
    """The route first, then each airport's departures and arrivals."""
    out = [{"route": True,
            "departures": board.get("route:departures") or [],
            "arrivals": board.get("route:arrivals") or []}]
    for code, name_ar, name_en in AIRPORTS:
        for mode, mode_ar, mode_en in DIRECTIONS:
            out.append({"mode": mode, "title_ar": mode_ar,
                        "title_en": mode_en, "airport_ar": name_ar,
                        "airport_en": name_en,
                        "rows": board.get(f"{code}:{mode}") or []})
    return out


def publish(board: dict, now: datetime, prefix: str, zone, zone_name,
            channel_id: str, output: str) -> bool:
    os.makedirs(BOARD_DIR, exist_ok=True)
    pages = pages_of(board)
    for number, spec in enumerate(pages):
        picture = draw_page(spec, zone, zone_name, now, number + 1, len(pages))
        picture.convert("RGB").save(os.path.join(BOARD_DIR, f"{prefix}{number}.png"))
    forget_boards_past(prefix, len(pages), BOARD_DIR)

    tv = ET.Element("tv", {"generator-info-name": "Flight Tracker"})
    channel = ET.SubElement(tv, "channel", {"id": channel_id})
    ET.SubElement(channel, "icon", {"src": LOGO})
    ET.SubElement(channel, "display-name", {"lang": "ar"}).text = CHANNEL_AR
    ET.SubElement(channel, "display-name", {"lang": "en"}).text = CHANNEL_EN
    lines = [f"{CHANNEL_AR} · {zone_name}", ""]
    for mode, _other, _title, sub_ar, _en, _men in ROUTE:
        for x in board.get(f"route:{mode}") or []:
            said, _tone = status_of(x, zone)
            lines.append(f"{sub_ar} · {x['scheduled'].astimezone(zone):%H:%M} "
                         f"{x['number']} {x['airline']} — {said}")
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
