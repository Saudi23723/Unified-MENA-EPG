#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""مواقيت الصلاة — the seventh channel, drawn the way the six are.

A prayer time is not a relay of anybody's page: it is a calculation, and
the four cities the reader asked for are each calculated the way their
own authority calculates them — Jordan's Awqaf method for عمّان, the
UAE's for أبو ظبي, ISNA's for هندرسون in Nevada (the North American
standard, and the one the mosques there publish by), and Diyanet's for
إسطنبول. Aladhan runs those methods; the numbers on this board are the
numbers each city's own authority publishes.

NOTHING ON THE BOARD MOVES FASTER THAN A DAY. That is the rule the whole
reel lives by: a board redrawn every pass is new bytes every pass, the
encoder renames the segments underneath it, and a television holding a
cached playlist is handed 404s. So no countdown and no clock — a day's
six times and the day they belong to, which is all a prayer board has
ever needed to say.

    python prayer_epg.py

Writes prayer_epg.xml, the boards boards/today_prayer_*.png and the
fallback reading prayer_times.json.
"""
from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from epg_lib import (
    add_programme, fetch, log, new_session, warn, write_xml_atomic,
)
from match_board import (
    H, MUTED, PAD, PANEL, PANEL_ALT, PILL, PILL_INK, RULE, W, WHITE,
    backdrop, date_chip, draw_signature, draw_text, forget_boards_past,
    progress, rule, size_that_fits,
)

UTC = timezone.utc

CHANNEL_ID = "TodayPrayer"
CHANNEL_AR = "مواقيت الصلاة"
CHANNEL_EN = "Prayer Times"
OUTPUT = "prayer_epg.xml"
BOARD_DIR = "boards"
BOARD_PREFIX = "today_prayer_"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/today_prayer.png")
RAW_BOARD = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
             "main/boards/" + BOARD_PREFIX + "{n}.png")

API = "https://api.aladhan.com/v1/timings/{date}"
SOURCE = "Aladhan"
CACHE = "prayer_times.json"

# The four cities, each with the calculation its own authority uses and
# the zone its own day is counted in. THE METHOD IS THE POINT: the same
# coordinates under another method are another mosque's minute, and a
# board that printed Jordan's عمّان by ISNA's rule would be printing a
# time nobody in عمّان prays at.
#
#   23 — Jordan, Ministry of Awqaf (awqaf.gov.jo)
#   16 — UAE, General Authority of Islamic Affairs (awqaf.gov.ae)
#    2 — ISNA, the North American standard (Henderson, Nevada)
#   13 — Diyanet, Türkiye (namazvakitleri.diyanet.gov.tr)
CITIES = (
    ("عمّان", "الأردن", "دائرة الإفتاء والأوقاف", 31.9539, 35.9106,
     23, "Asia/Amman"),
    ("أبو ظبي", "الإمارات", "الهيئة العامة للشؤون الإسلامية", 24.4539,
     54.3773, 16, "Asia/Dubai"),
    ("هندرسون · نيفادا", "أمريكا", "ISNA", 36.0397, -114.9819,
     2, "America/Los_Angeles"),
    ("إسطنبول", "تركيا", "Diyanet", 41.0082, 28.9784, 13,
     "Europe/Istanbul"),
)

# The six the board shows, in the order the day runs them. الشروق is not
# a prayer and it is on the board anyway, because it is the end of الفجر
# and the reader of a prayer board looks for it there.
PRAYERS = (
    ("Fajr", "الفجر"),
    ("Sunrise", "الشروق"),
    ("Dhuhr", "الظهر"),
    ("Asr", "العصر"),
    ("Maghrib", "المغرب"),
    ("Isha", "العشاء"),
)

ON_PAGE = 4
HOUR = timedelta(hours=1)
HOURS_AHEAD = 12

TITLE = "🕌 مواقيت الصلاة"

# The prayer board's own colour: the four beside it wear green, violet,
# blue and sky, and this one wears the gold of a mosque lamp, so five
# boards passing in a list are told apart without reading a word.
GOLD = (226, 186, 106, 255)


# ---------------------------------------------------------------- reading

def hhmm(value: str) -> str:
    """Aladhan's "05:12 (EEST)" as the five characters a board shows."""
    return (value or "").split(" ")[0].strip()[:5]


def live_cities(session) -> list[dict] | None:
    """Every city's day, or None if any one of them failed.

    All or nothing, like the weather beside it: a board with two cities'
    times and two blank rows is not a prayer board, it is a board that
    looks broken.
    """
    out: list[dict] = []
    for city, country, authority, lat, lon, method, zone in CITIES:
        here = datetime.now(ZoneInfo(zone))
        try:
            answer = fetch(session, API.format(date=f"{here:%d-%m-%Y}"),
                           params={
                               "latitude": lat,
                               "longitude": lon,
                               "method": method,
                               "timezonestring": zone,
                           })
            body = answer.json()
            data = body["data"]
            timings = data["timings"]
            times = {key: hhmm(timings[key]) for key, _ in PRAYERS}
            if not all(len(one) == 5 for one in times.values()):
                raise ValueError("a time came back malformed")
            hijri = data["date"]["hijri"]
            out.append({
                "city": city,
                "country": country,
                "authority": authority,
                "zone": zone,
                "date": f"{here:%d.%m.%Y}",
                "hijri": f"{hijri['day']} {hijri['month']['ar']} "
                         f"{hijri['year']}",
                "times": times,
            })
        except Exception as exc:                                # noqa: BLE001
            warn(f"{city}'s prayer times did not come back ({exc}) — "
                 f"falling back to the last reading in {CACHE}")
            return None
    return out


def cached_cities() -> list[dict]:
    """The last good day, exactly as it was committed."""
    if not os.path.exists(CACHE):
        return []
    try:
        with open(CACHE, encoding="utf-8") as handle:
            kept = json.load(handle)
        cities = kept.get("cities")
        if not isinstance(cities, list) or not cities:
            warn(f"{CACHE} holds no cities — nothing to fall back on")
            return []
        return cities
    except (OSError, ValueError) as exc:
        warn(f"{CACHE} could not be read ({exc}) — nothing to fall back on")
        return []


def remember(cities: list[dict], now: datetime) -> None:
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


def pages_of(cities: list[dict]) -> list[list[dict]]:
    return [cities[i:i + ON_PAGE] for i in range(0, len(cities), ON_PAGE)] \
        or [[]]


# ---------------------------------------------------------------- drawing

def draw_mark(pen, x: int, y: int, size: int, accent=GOLD) -> None:
    """The channel's mark: a dome and a minaret, in the lamp's gold."""
    ink = tuple(min(255, int(c * 0.28)) for c in accent[:3]) + (255,)
    pen.rounded_rectangle([x, y, x + size, y + size],
                          radius=size // 5, fill=ink, outline=accent, width=2)
    inset = size // 5
    base = y + size - inset
    dome_w = size // 2
    centre = x + size // 2
    pen.pieslice([centre - dome_w // 2, base - dome_w,
                  centre + dome_w // 2, base + dome_w // 2],
                 180, 360, fill=accent)
    pen.line([(centre - dome_w // 2, base), (centre + dome_w // 2, base)],
             fill=WHITE, width=max(2, size // 22))
    # The minaret at the side, with its little finial.
    tower = max(4, size // 12)
    top = y + inset - 2
    pen.rectangle([x + inset - 2, top, x + inset - 2 + tower, base],
                  fill=WHITE)
    pen.ellipse([x + inset - 4, top - tower, x + inset - 4 + tower * 2, top],
                fill=accent)


def draw_board(cities: list[dict], *, page: int = 1, pages: int = 1) -> Image.Image:
    """One page of prayer times: a city a row, its six times in pills."""
    board = backdrop()
    pen = ImageDraw.Draw(board)
    accent = GOLD

    draw_mark(pen, PAD, PAD - 6, 76, accent)
    x = PAD + 76 + 24
    draw_text(pen, (x, PAD - 4), CHANNEL_AR, 46, WHITE)
    draw_text(pen, (x, PAD + 52),
              "الأردن · الإمارات · أمريكا · تركيا — بتوقيت كل مدينة",
              21, MUTED, thin=True)

    right = W - PAD
    if cities:
        date_chip(pen, right, PAD - 6, cities[0]["date"])
        draw_text(pen, (right, PAD + 64), cities[0]["hijri"], 19, accent,
                  anchor="ra")
    draw_signature(pen)

    top = PAD + 122
    rule(pen, top, accent)

    if not cities:
        draw_text(pen, (W // 2, H // 2), "لا توجد مواقيت الآن", 32, MUTED,
                  anchor="mm")
        progress(pen, page, pages, accent)
        return board

    room = H - top - PAD
    height = min(126, room // len(cities))
    y = top + 8

    for index, city in enumerate(cities):
        band = [PAD - 12, y, W - PAD + 12, y + height - 8]
        fill = PANEL if index % 2 == 0 else PANEL_ALT
        pen.rounded_rectangle(band, radius=12, fill=fill,
                              outline=RULE, width=1)

        name = city["city"]
        at = size_that_fits(name, 26, 17, 300)
        draw_text(pen, (W - PAD - 6, y + 32), name, at, WHITE, anchor="rm")
        under = f"{city['country']} · {city['authority']}"
        draw_text(pen, (W - PAD - 6, y + 62),
                  under, size_that_fits(under, 15, 12, 320), MUTED,
                  anchor="rm", thin=True)

        # The six times, laid left to right in the order the day runs
        # them — a number reads the same in every script, so the row of
        # them is the part of the board a reader across the room uses.
        wide = 128
        gap = 8
        left = PAD + 6
        pill_y = y + 26
        pill_h = height - 8 - 52
        for slot, (key, label) in enumerate(PRAYERS):
            px = left + slot * (wide + gap)
            pen.rounded_rectangle([px, pill_y, px + wide, pill_y + pill_h],
                                  radius=10, fill=PILL, outline=RULE, width=1)
            draw_text(pen, (px + wide // 2, pill_y + 20), label, 17,
                      PILL_INK, anchor="mm", thin=True)
            draw_text(pen, (px + wide // 2, pill_y + pill_h - 24),
                      city["times"][key], 27, accent, anchor="mm",
                      weight="heavy")

        y += height

    progress(pen, page, pages, accent)
    return board


def draw_pages(pages: list[list[dict]]) -> int:
    os.makedirs(BOARD_DIR, exist_ok=True)
    for number, page in enumerate(pages):
        board = draw_board(page, page=number + 1, pages=len(pages))
        board.convert("RGB").save(
            os.path.join(BOARD_DIR, f"{BOARD_PREFIX}{number}.png"))
    forget_boards_past(BOARD_PREFIX, len(pages), BOARD_DIR)
    return len(pages)


# ------------------------------------------------------------------ guide

def a_line(city: dict) -> str:
    times = " · ".join(f"{label} {city['times'][key]}"
                       for key, label in PRAYERS)
    return f"{city['city']} — {times}"


def a_description(cities: list[dict], fallback: bool) -> str:
    lines = [f"{CHANNEL_AR} — كل مدينة بتوقيتها المحلي"]
    if fallback:
        lines.append("المواقيت محفوظة — المصدر لم يجب هذا التحديث")
    lines.append("")
    for city in cities:
        lines.append(a_line(city))
    lines.append("")
    lines.append(f"المصدر: {SOURCE} — طرق الحساب الرسمية لكل بلد")
    return "\n".join(lines)


def build() -> int:
    now = datetime.now(UTC)
    session = new_session()

    cities = live_cities(session)
    if cities is not None:
        remember(cities, now)
        fallback = False
    else:
        cities = cached_cities()
        if not cities:
            warn("no prayer times to show — the published boards and guide "
                 "are left exactly as they were")
            return 1
        fallback = True

    pages = pages_of(cities)
    drawn = draw_pages(pages)
    log(f"  {len(cities)} cit(ies) shown on {drawn} board(s)")

    tv = ET.Element("tv", {"generator-info-name": "Prayer Times"})
    channel = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(channel, "icon", {"src": LOGO})
    ET.SubElement(channel, "display-name", {"lang": "ar"}).text = CHANNEL_AR
    ET.SubElement(channel, "display-name", {"lang": "en"}).text = CHANNEL_EN

    opens = now.replace(minute=0, second=0, microsecond=0)
    description = a_description(cities, fallback)
    for step in range(HOURS_AHEAD):
        start = opens + step * HOUR
        add_programme(tv, CHANNEL_ID, start, start + HOUR,
                      title=TITLE, desc=description,
                      icon=RAW_BOARD.format(n=0))

    ok = write_xml_atomic(tv, OUTPUT, generator_name="Prayer Times",
                          guard_regression=False, min_programmes=1)
    log(f"{CHANNEL_AR}: {HOURS_AHEAD} programme(s), {drawn} board(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
