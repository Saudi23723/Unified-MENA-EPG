#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The fourth channel: today's weather, drawn as boards and published.

It began as something else — a relay. The playlist pointed at the
AccuWeather channel through the amagi CDN, which is somebody else's URL
to rotate: a chain of redirects, token-signed variants, and one day it
stopped answering. The row was in the playlist, the channel tuned, and
nothing played. A channel whose picture lives on someone else's server
is a channel they can switch off.

So it is built the way the three channels beside it are built, which is
the way this repository knows survives: the weather is READ — live, from
Open-Meteo, the same source the old automation used, free and keyless —
DRAWN as boards with the same faces and colours as the fixtures and the
bulletin, and ENCODED into stream/weather.m3u8 by the same encoder. The
picture is this repository's own end to end, and nobody outside the
build has anything to rotate.

WHAT A PAGE SHOWS: the cities the reader asked for — Jordan first, then
the Emirates and America — each as one row: the city and its country and
its sky on the right where an Arabic eye starts, the temperature in
whole degrees on the left, the humidity and the wind beneath it. A
weather row is read at a glance like a fixtures row, not worked through
like a headline, so the page holds up to five cities and the screen
holds twenty seconds.

WHOLE DEGREES, AND NO CLOCK, FOR THE SAME REASON. A segment is named
after the hash of its board, so a board whose bytes change every pass
renames its segment every pass — the bulletin channel did exactly that
by printing the minute, and a television working through a cached
playlist was handed 404s until the fault was found. The API nudges a
decimal of a degree every fifteen minutes; rounded to whole degrees the
board changes when the WEATHER changes, a handful of times a day, and
the date it carries is the only clock it will ever print.

A SOURCE THAT DOES NOT ANSWER IS NOT A FAILURE WORTH AN EMAIL. If
Open-Meteo is unreachable the pass falls back to weather.json — the
last good reading, committed — which draws the same boards it drew
before, so the segment names do not move and the channel keeps playing
what it was playing. The guide says when the reading was taken, so a
stale board is an honest one rather than a silent one.
"""
from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from epg_lib import add_programme, fetch, log, new_session, warn, write_xml_atomic
from match_board import (
    ACCENT, ARABIC, H, INK, MUTED, PAD, PANEL, RULE, W, WHITE,
    draw_text, forget_boards_past, size_that_fits,
)

UTC = timezone.utc
VIEWER = ZoneInfo("America/Los_Angeles")
VIEWER_NAME = "بتوقيتك"

CHANNEL_ID = "TodayWeather"
CHANNEL_AR = "طقس اليوم"
CHANNEL_EN = "Today's Weather"
OUTPUT = "weather_epg.xml"
BOARD_DIR = "boards"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/today_weather.png")
RAW_BOARD = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
             "main/boards/today_weather_{n}.png")

# Where the weather comes from. Open-Meteo needs no key, answers one
# request for every city at once, and is the source the old automation
# read too — so the numbers on this board are the numbers the channel
# always showed, gathered the same way.
API = "https://api.open-meteo.com/v1/forecast"
SOURCE = "Open-Meteo"
CACHE = "weather.json"

# The cities the reader asked for, in the order the pages show them.
# JORDAN FIRST, for the same reason the bulletin puts it first: it is
# the section that matters most here, and a page order that led with
# wherever the alphabet happens to start could leave it off the first
# board entirely.
CITIES = (
    ("عمّان", "الأردن", 31.9454, 35.9284),
    ("إربد", "الأردن", 32.5556, 35.85),
    ("الزرقاء", "الأردن", 32.0728, 36.088),
    ("العقبة", "الأردن", 29.532, 35.006),
    ("أبو ظبي", "الإمارات", 24.4539, 54.3773),
    ("دبي", "الإمارات", 25.2048, 55.2708),
    ("نيويورك", "أمريكا", 40.7128, -74.006),
    ("لوس أنجلوس", "أمريكا", 34.0522, -118.2437),
    ("شيكاغو", "أمريكا", 41.8781, -87.6298),
)
COUNTRY_ORDER = ("الأردن", "الإمارات", "أمريكا")

# The WMO weather codes, said in Arabic. The two the old file carried
# are kept byte for byte — "صافٍ" and "غائم جزئياً" — so a reader who
# knew the channel before finds the same words on it now.
WMO_AR = {
    0: "صافٍ", 1: "صافٍ غالباً", 2: "غائم جزئياً", 3: "غائم",
    45: "ضباب", 48: "ضباب متجمد",
    51: "رذاذ خفيف", 53: "رذاذ", 55: "رذاذ كثيف",
    56: "رذاذ متجمد", 57: "رذاذ متجمد كثيف",
    61: "مطر خفيف", 63: "مطر", 65: "مطر غزير",
    66: "مطر متجمد", 67: "مطر متجمد غزير",
    71: "ثلج خفيف", 73: "ثلج", 75: "ثلج كثيف", 77: "حبيبات ثلج",
    80: "وابل خفيف", 81: "وابل", 82: "وابل عنيف",
    85: "وابل ثلجي", 86: "وابل ثلجي كثيف",
    95: "عاصفة رعدية",
    96: "عاصفة رعدية مع برد", 99: "عاصفة رعدية مع برد غزير",
}

# How many cities a page holds, and how far the guide reaches. A row is
# a glance; five of them is a page somebody reads through without
# waiting. The guide reaches six hours for the same reason the
# bulletin's does — every programme carries the reading as it stood when
# the build ran, and a guide that promised tomorrow's weather would be
# promising something it cannot know.
ON_PAGE = 5
HOUR = timedelta(hours=1)
HOURS_AHEAD = 6

TITLE = "🌡️ طقس اليوم للمدن"


# ---------------------------------------------------------------- reading

def live_cities(session) -> list[dict] | None:
    """Every city's reading in one request, or None if the source failed.

    All or nothing: a page with three cities' weather and six blanks is
    not a page with the weather on it, so one malformed row sends the
    whole pass to the fallback rather than publishing a board that is
    half a lie.
    """
    params = {
        "latitude": ",".join(str(one[2]) for one in CITIES),
        "longitude": ",".join(str(one[3]) for one in CITIES),
        "current": ("temperature_2m,relative_humidity_2m,"
                    "weather_code,wind_speed_10m"),
        "timezone": "auto",
    }
    try:
        answer = fetch(session, API, params=params)
        rows = answer.json()
    except Exception as exc:                                # noqa: BLE001
        warn(f"Open-Meteo did not answer ({exc}) — falling back to the "
             f"last reading in {CACHE}")
        return None

    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list) or len(rows) != len(CITIES):
        warn("Open-Meteo answered with something this does not recognise "
             "— falling back to the last reading")
        return None

    out: list[dict] = []
    for (city, country, lat, lon), row in zip(CITIES, rows):
        try:
            current = row["current"]
            code = int(current["weather_code"])
            out.append({
                "city": city,
                "country": country,
                "latitude": lat,
                "longitude": lon,
                "temperature_c": current["temperature_2m"],
                "humidity": int(current["relative_humidity_2m"]),
                "wind_speed": round(float(current["wind_speed_10m"]), 1),
                "condition": WMO_AR.get(code, "غير معروف"),
                "weather_code": code,
                "observed_at": current["time"],
            })
        except (KeyError, TypeError, ValueError):
            warn(f"{city}'s reading was malformed — falling back to the "
                 f"last reading rather than showing a board without it")
            return None
    return out


def cached_cities() -> tuple[list[dict], datetime | None]:
    """The last good reading, exactly as it was committed.

    The file is the schema the old automation wrote, and it is kept that
    way on purpose: the fallback is not a new invention, it is the same
    record the channel has always kept, so a pass that falls back draws
    the boards the pass before it drew.
    """
    if not os.path.exists(CACHE):
        return [], None
    try:
        with open(CACHE, encoding="utf-8") as handle:
            kept = json.load(handle)
        cities = kept["cities"]
        when = kept.get("updated_at") or ""
        stamp = None
        try:
            stamp = datetime.fromisoformat(when.replace("Z", "+00:00"))
        except ValueError:
            stamp = None
        if not isinstance(cities, list) or not cities:
            warn(f"{CACHE} holds no cities — nothing to fall back on")
            return [], None
        return cities, stamp
    except (OSError, ValueError, KeyError) as exc:
        warn(f"{CACHE} could not be read ({exc}) — nothing to fall back on")
        return [], None


def remember(cities: list[dict], now: datetime) -> None:
    """Write the reading back, so the next pass that loses the source
    falls back to this one and not to one from weeks ago."""
    payload = {
        "updated_at": now.isoformat(timespec="milliseconds")
                        .replace("+00:00", "Z"),
        "source": SOURCE,
        "cities": cities,
    }
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, CACHE)


# ----------------------------------------------------------------- pages

def pages_of(cities: list[dict]) -> list[list[dict]]:
    """Country by country, Jordan first, and a country never split.

    Chunking the nine by count alone would put أبو ظبي on the Jordan
    page and دبي on the American one, which reads as a mistake rather
    than as a mix: a page is scanned for the place it shows, and half a
    country is not a place. So each country's cities travel together,
    and a country that does not fit whole starts the next page.
    """
    groups: list[list[dict]] = []
    for country in COUNTRY_ORDER:
        mine = [one for one in cities if one["country"] == country]
        if mine:
            groups.append(mine)
    for one in cities:
        if one["country"] not in COUNTRY_ORDER:
            groups.append([one])

    pages: list[list[dict]] = []
    page: list[dict] = []
    for group in groups:
        if page and len(page) + len(group) > ON_PAGE:
            pages.append(page)
            page = []
        page += group
    pages.append(page)
    return [one for one in pages if one]


# ---------------------------------------------------------------- drawing

# ARABIC IS DRAWN SMALLER THAN LATIN AT THE SAME NOMINAL SIZE, and on a
# board read from across a room that is the difference between a city
# and a smudge. The bulletin carries the same lift for the same reason.
ARABIC_LIFT = 1.22


def for_script(text: str, size: int) -> int:
    """The size this text needs to LOOK like `size` on this board."""
    return int(round(size * ARABIC_LIFT)) if ARABIC.search(text or "") else size


def draw_mark(pen, x: int, y: int, size: int) -> None:
    """The channel's own mark: a ring with the sun in the middle of it."""
    pen.rounded_rectangle([x, y, x + size, y + size], radius=size // 4,
                          fill=PANEL)
    pad = size // 5
    pen.ellipse([x + pad, y + pad, x + size - pad, y + size - pad],
                outline=ACCENT, width=max(3, size // 12))
    sun = size // 5
    pen.ellipse([x + size // 2 - sun, y + size // 2 - sun,
                 x + size // 2 + sun, y + size // 2 + sun], fill=ACCENT)


def draw_board(cities: list[dict], now: datetime, viewer, *,
               page: int = 1, pages: int = 1,
               countries: str = "") -> Image.Image:
    """One page of the weather: a city a row, the numbers on the left.

    THE RIGHT SIDE IS WHERE AN ARABIC EYE STARTS, so that is where the
    city is, with its country and its sky beneath it; the temperature is
    a number, which every script reads the same way, and it takes the
    left at the size a board is watched for.
    """
    board = Image.new("RGBA", (W, H), INK)
    pen = ImageDraw.Draw(board)

    draw_mark(pen, PAD, PAD - 4, 72)
    x = PAD + 72 + 22
    draw_text(pen, (x, PAD - 2), CHANNEL_AR, 40, WHITE)
    subtitle = f"{countries} · من {SOURCE}" if countries else f"من {SOURCE}"
    draw_text(pen, (x, PAD + 46), subtitle, 21, MUTED, thin=True)

    right = W - PAD
    # A DATE, NOT A CLOCK — the one thing on this board that may change
    # daily and never sooner, for the reason at the top of this file.
    draw_text(pen, (right, PAD - 2),
              now.astimezone(viewer).strftime("%d.%m.%Y"), 30, WHITE,
              anchor="ra")
    draw_text(pen, (right, PAD + 40),
              f"طقس اليوم · {page}/{pages}" if pages > 1 else "طقس اليوم",
              19, MUTED, anchor="ra", thin=True)

    top = PAD + 92
    pen.line([PAD, top, W - PAD, top], fill=RULE, width=2)

    if not cities:
        draw_text(pen, (W // 2, H // 2), "لا توجد بيانات طقس الآن", 32,
                  MUTED, anchor="mm")
        return board

    room = H - top - PAD
    height = min(104, room // len(cities))
    y = top + 8

    for index, city in enumerate(cities):
        band = [PAD - 12, y, W - PAD + 12, y + height - 8]
        if index % 2 == 0:
            pen.rounded_rectangle(band, radius=12, fill=PANEL)

        name = city["city"]
        where = f"{city['country']} · {city['condition']}"
        temp = int(round(city["temperature_c"]))
        wind = int(round(city["wind_speed"]))

        at = size_that_fits(name, for_script(name, 25),
                            for_script(name, 18), 320)
        draw_text(pen, (W - PAD - 6, y + 34), name, at, WHITE, anchor="rm")
        under = size_that_fits(where, for_script(where, 16),
                               for_script(where, 12), 400)
        draw_text(pen, (W - PAD - 6, y + 66), where, under, MUTED,
                  anchor="rm", thin=True)

        draw_text(pen, (PAD + 18, y + 44), f"{temp}°", 42, WHITE,
                  anchor="lm")
        air = f"رطوبة {city['humidity']}% · رياح {wind} كم/سا"
        draw_text(pen, (PAD + 18, y + 76), air, 15, MUTED,
                  anchor="lm", thin=True)

        y += height

    return board


def draw_pages(pages: list[list[dict]], now: datetime) -> int:
    os.makedirs(BOARD_DIR, exist_ok=True)
    for number, page in enumerate(pages):
        countries = " و".join(
            dict.fromkeys(one["country"] for one in page))
        board = draw_board(page, now, VIEWER,
                           page=number + 1, pages=len(pages),
                           countries=countries)
        board.convert("RGB").save(
            os.path.join(BOARD_DIR, f"today_weather_{number}.png"))
    forget_boards_past("today_weather_", len(pages), BOARD_DIR)
    return len(pages)


# ------------------------------------------------------------------ guide

def a_line(city: dict) -> str:
    """One city as a reader scrolls it in the guide.

    The same rounded numbers the board shows, because the guide and the
    board are the same reading said twice; a guide that carried decimals
    the television did not would disagree with the channel it belongs to.
    """
    temp = int(round(city["temperature_c"]))
    wind = int(round(city["wind_speed"]))
    return (f"{city['city']} {temp}° · {city['condition']} · "
            f"رطوبة {city['humidity']}% · رياح {wind} كم/سا")


def a_description(pages: list[list[dict]], as_of: datetime,
                  fallback: bool) -> str:
    shown = as_of.astimezone(VIEWER)
    lines = [f"{CHANNEL_AR} · آخر تحديث {shown:%H:%M} — {VIEWER_NAME}"]
    if fallback:
        lines.append("القراءة محفوظة — المصدر لم يجب هذا التحديث")
    lines.append("")
    country = ""
    for page in pages:
        for city in page:
            if city["country"] != country:
                country = city["country"]
                lines.append(country)
            lines.append(a_line(city))
    return "\n".join(lines)


def build() -> int:
    now = datetime.now(UTC)
    session = new_session()

    cities = live_cities(session)
    if cities is not None:
        remember(cities, now)
        as_of, fallback = now, False
    else:
        cities, stamp = cached_cities()
        if not cities:
            warn("no weather to show — the published boards and guide "
                 "are left exactly as they were")
            return 1
        as_of, fallback = (stamp or now), True

    pages = pages_of(cities)
    drawn = draw_pages(pages, now)
    log(f"  {len(cities)} cit(ies) read, shown on {drawn} board(s)")

    tv = ET.Element("tv", {"generator-info-name": "Today's Weather"})
    channel = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(channel, "icon", {"src": LOGO})
    ET.SubElement(channel, "display-name", {"lang": "ar"}).text = CHANNEL_AR
    ET.SubElement(channel, "display-name", {"lang": "en"}).text = CHANNEL_EN

    # ON THE HOUR, from the hour this build lands in, exactly like the
    # bulletin beside it: a programme that started at a ragged minute
    # makes a player show "now" against something that began four
    # minutes ago.
    opens = now.replace(minute=0, second=0, microsecond=0)
    description = a_description(pages, as_of, fallback)

    for step in range(HOURS_AHEAD):
        start = opens + step * HOUR
        add_programme(
            tv, CHANNEL_ID, start, start + HOUR,
            title=TITLE,
            desc=description,
            icon=RAW_BOARD.format(n=0))

    ok = write_xml_atomic(tv, OUTPUT, generator_name="Today's Weather",
                          guard_regression=False, min_programmes=1)
    log(f"{CHANNEL_AR}: {HOURS_AHEAD} programme(s), {drawn} board(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
