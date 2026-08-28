#!/usr/bin/env python3
import html
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from difflib import SequenceMatcher
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

from epg_lib import countdown_label

from PIL import Image, ImageOps, ImageEnhance
import pytesseract
from pytesseract import Output


# Badge appended to every real match block.
#
# It marks the programme as a LIVE BROADCAST — the standard EPG meaning —
# rather than "kicking off this very second". Stamping it only while the
# match happened to be on air (the previous behaviour) meant it was
# essentially never visible: the guide is a static file, so the badge only
# existed in whichever copy was generated during the match, and TiviMate
# had to re-download in that same narrow window to ever show it. Marking
# the broadcast itself is also what makes it visible when you browse ahead.
# This mirrors update_alwan_epg.py, where the badge has always worked.
LRM = "‎"
LIVE_LABEL = "• Live \U0001F7E2"  # "• Live 🟢"


def ltr(value):
    """Wrap a Latin run so it keeps its own order inside RTL text."""
    return f"{LRM}{value}{LRM}"

# Logos are served from this repository (see fetch_logos.py). Hot-linking a
# third-party image host is what made the logos vanish in TiviMate before:
# those hosts rate-limit, block hot-linking or need a browser User-Agent.
LOGO_BASE = (
    "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/logos"
)

TZ = ZoneInfo("Asia/Riyadh")          # المصدر الرئيسي (توقيت المباراة الرسمي)
TZ_ABUDHABI = ZoneInfo("Asia/Dubai")   # توقيت أبوظبي
TZ_VEGAS = ZoneInfo("America/Los_Angeles")  # توقيت لاس فيغاس
TZ_AMMAN = ZoneInfo("Asia/Amman")      # توقيت الأردن
NOW = datetime.now(TZ)
OUT = Path("thmanyah_epg.xml")

SCRIPT_VERSION = "2026-08-21i | adaptive countdown blocks, OCR off, hourly runs"

GOAL_HOME = "https://www.goal.com/ar"
KOOORA_HOME = "https://www.kooora.com/"
SCORES365_HOME = "https://www.365scores.com/ar/news/magazine/"
RADARKORA_TELEGRAM = "https://t.me/s/matches_today2"

EXTRA_SOURCES = (
    {
        "label": "FilGoal",
        "home": "https://www.filgoal.com/matches/",
        "keywords": ("مواعيد مباريات", "جدول مباريات", "القنوات الناقلة"),
        "tz": ZoneInfo("Africa/Cairo"),
    },
    {
        "label": "Youm7",
        "home": "https://www.youm7.com/Section/%D8%A3%D8%AE%D8%A8%D8%A7%D8%B1-%D8%A7%D9%84%D8%B1%D9%8A%D8%A7%D8%B6%D8%A9/298/1",
        "keywords": ("مواعيد مباريات", "جدول مباريات", "القنوات الناقلة"),
        "tz": ZoneInfo("Africa/Cairo"),
    },
    {
        "label": "Masrawy",
        "home": "https://www.masrawy.com/sports",
        "keywords": ("مواعيد مباريات", "جدول مباريات", "القنوات الناقلة"),
        "tz": ZoneInfo("Africa/Cairo"),
    },
    {
        "label": "ElGoal",
        "home": "https://elgoal.net/",
        "keywords": ("القنوات الناقلة", "جدول مباريات", "مواعيد مباريات"),
        "tz": ZoneInfo("Africa/Cairo"),
    },
)

STATIC_CONFIRMATION_PAGES = (
    {
        "label": "ElGoal Broadcast",
        "url": "https://elgoal.net/broadcasting-channels-today-matches/",
        "tz": ZoneInfo("Africa/Cairo"),
        "per_day": None,
    },
    {
        "label": "365Scores WhereToWatch",
        "url": "https://www.365scores.com/ar/where-to-watch",
        "tz": TZ,
        "per_day": None,
    },
)

YALLAKORA_DAY_URL = "https://www.yallakora.com/matches-center?date={m:02d}/{d:02d}/{y}"
YALLAKORA_TZ = ZoneInfo("Africa/Cairo")
YALLAKORA_SAUDI_HINTS = (
    "ksa-league", "saudi", "kings-cup", "الدوري-السعودي",
    "خادم-الحرمين", "%d8%a7%d9%84%d8%af%d9%88%d8%b1%d9%8a-%d8%a7%d9%84%d8%b3%d8%b9%d9%88%d8%af%d9%8a",
)
YALLAKORA_CARD_RE = re.compile(
    r"(.+?)\s*\1\s*[-–—\s]*?(\d{1,2}:\d{2})\s*(.+?)\s*\3\s*$"
)

UNCONFIRMED_MODE = "hint"
ENABLE_TELEGRAM_OCR = False
EXTRA_LOOKAHEAD_DAYS = 4

# تم حذف اللوجو نهائياً
# THMANYAH_LOGO = ...
# THMANYAH_LOGO_SVG = ...

KEEP_DAYS_BACK = 1
KEEP_DAYS_FORWARD = 10
CHANNELS = (1, 2, 3)
GUIDE_CHANNEL_ID = "ThmanyahGuide"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "ar,en;q=0.8",
}

TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)")
THMANYAH_NUMBER_RE = re.compile(
    r"(?:قناة\s*)?(?:ثمانية|ثمانيه|ثماني|thmanyah)\s*[.\-:]?\s*([123])(?:\d)?\b",
    re.I,
)
THMANYAH_NUMBER_BEFORE_RE = re.compile(
    r"(?:قناة\s*)?([123])\s*[.\-:]?\s*(?:ثمانية|ثمانيه|thmanyah)\b",
    re.I,
)
THMANYAH_ANY_RE = re.compile(r"(?:ثمانية|ثمانيه|thmanyah)", re.I)


def channel_from_text(text):
    text = norm(text)
    for pattern in (THMANYAH_NUMBER_RE, THMANYAH_NUMBER_BEFORE_RE):
        found = pattern.search(text)
        if found:
            number = int(found.group(1))
            if number in CHANNELS:
                return number
    return None

MATCH_RE = re.compile(
    r"(.{2,100}?)\s*(?:🆚|⚔️|⚔|×|✕|[xX](?=\s)|vs\.?|v\.?|ضد|أمام|امام|[-–—])\s*(.{2,100})",
    re.I,
)

AR_MONTHS = {
    "يناير": 1, "فبراير": 2, "مارس": 3,
    "أبريل": 4, "ابريل": 4, "مايو": 5,
    "يونيو": 6, "يوليو": 7, "أغسطس": 8,
    "اغسطس": 8, "سبتمبر": 9, "أكتوبر": 10,
    "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

def log(message):
    print(message, flush=True)

def warn(message):
    print(f"WARN {message}", file=sys.stderr, flush=True)

def norm(value):
    value = html.unescape(value or "")
    value = value.replace("\u200f", " ").replace("\u200e", " ")
    value = value.replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", value).strip()

def fetch(url):
    response = requests.get(url, headers=HEADERS, timeout=35)
    response.raise_for_status()
    return response.text

def in_window(dt):
    return (
        NOW - timedelta(days=KEEP_DAYS_BACK)
        <= dt
        <= NOW + timedelta(days=KEEP_DAYS_FORWARD)
    )

def parse_date(text, reference=None):
    text = norm(text)
    low = text.lower()
    reference = reference or NOW.date()

    numeric = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b", text)
    if numeric:
        day, month, year = map(int, numeric.groups())
        try:
            return date(year, month, day)
        except ValueError:
            pass

    months_pattern = "|".join(map(re.escape, AR_MONTHS))
    arabic = re.search(
        rf"\b(\d{{1,2}})\s+({months_pattern})\s+(20\d{{2}})\b",
        text,
        re.I,
    )
    if arabic:
        day = int(arabic.group(1))
        month = AR_MONTHS[arabic.group(2)]
        year = int(arabic.group(3))
        try:
            return date(year, month, day)
        except ValueError:
            pass

    if "بعد غد" in low:
        return reference + timedelta(days=2)
    if any(x in low for x in ("غداً", "غدا", "بكرا", "بكرة")):
        return reference + timedelta(days=1)
    if "اليوم" in low:
        return reference
    return None

AR_PM_RE = re.compile(r"^\s*(?:مساء|مساءً|مساءا|م\b|ليلا|ليلاً|عصرا|عصراً|ظهرا|ظهراً|pm)", re.I)
AR_AM_RE = re.compile(r"^\s*(?:صباحا|صباحاً|صباح|ص\b|فجرا|فجراً|am)", re.I)


def time_from_text(text, search_from=0):
    text = norm(text)
    found = TIME_RE.search(text, search_from)
    if not found:
        return None

    hour = int(found.group(1))
    minute = int(found.group(2))
    tail = text[found.end():found.end() + 20]

    if AR_PM_RE.search(tail) and hour < 12:
        hour += 12
    elif AR_AM_RE.search(tail) and hour == 12:
        hour = 0

    return hour, minute


def make_dt(day, hour, minute, tz=None):
    value = datetime(
        day.year, day.month, day.day,
        int(hour), int(minute),
        tzinfo=tz or TZ,
    )
    return value.astimezone(TZ)


def three_zone_times(start):
    abudhabi = start.astimezone(TZ_ABUDHABI)
    amman = start.astimezone(TZ_AMMAN)
    vegas = start.astimezone(TZ_VEGAS)
    return (
        f"أبوظبي {abudhabi:%H:%M} ({abudhabi:%d/%m}) | "
        f"الأردن {amman:%H:%M} ({amman:%d/%m}) | "
        f"لاس فيغاس {vegas:%H:%M} ({vegas:%d/%m})"
    )

TEAM_TAIL_RES = (
    re.compile(r"\s*[-–—|/]\s*(?=\d|الساعة|ثمانية|thmanyah|قناة|على)", re.I),
    re.compile(r"\s*(?:الساعة|على\s+قناة|قناة|القناة|بتوقيت|بث\s+مباشر|مباشر)\b.*$", re.I),
    re.compile(r"\s*\d{1,2}\s*[:.]\s*\d{2}.*$"),
    re.compile(r"\s*(?:مساءً|مساء|صباحاً|صباحا|ظهراً|ظهرا|عصراً|عصرا|ليلاً|ليلا)\b.*$"),
)

def strip_trailing_noise(value):
    for pattern in TEAM_TAIL_RES:
        found = pattern.search(value)
        if found:
            value = value[:found.start()]
    return value

def clean_team(value):
    value = norm(value)
    value = re.sub(r"^(?:⚽|🏆|📺|⏰|•|\||✅|🔥)+\s*", "", value)
    value = strip_trailing_noise(value)
    value = re.sub(r"^(?:الساعة|على|قناة|القناة)\s+", "", value)
    return value.strip(" |:-–—")

def fixture_from_text(text):
    match = MATCH_RE.search(norm(text))
    if not match:
        return None
    first = clean_team(match.group(1))
    second = clean_team(match.group(2))
    if not first or not second or len(first) > 80 or len(second) > 80:
        return None
    return f"{first} - {second}"

ARABIC_FOLD = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه",
    "ـ": "",
})
ARABIC_DIACRITICS_RE = re.compile(r"[\u064b-\u0652\u0670]")

def normalize_team_name(value):
    value = norm(value).casefold()
    value = ARABIC_DIACRITICS_RE.sub("", value).translate(ARABIC_FOLD)
    value = re.sub(r"[^\w\u0600-\u06ff ]+", " ", value)
    value = re.sub(r"\b(?:ال)(?=\w)", "", value)
    value = re.sub(r"\b(?:نادي|fc|club)\b", " ", value, flags=re.I)
    return re.sub(r"\s+", " ", value).strip()

def fixture_signature(title):
    match = MATCH_RE.search(norm(title))
    if not match:
        return None
    first = normalize_team_name(match.group(1))
    second = normalize_team_name(match.group(2))
    if not first or not second:
        return None
    return frozenset((first, second))

def event_key(event):
    signature = fixture_signature(event["title"])
    title_key = "|".join(sorted(signature)) if signature else norm(event["title"]).casefold()
    return (
        event["start"].strftime("%Y%m%d%H%M"),
        title_key,
    )

def fixture_key(event):
    return (
        event["start"].strftime("%Y%m%d%H%M"),
        norm(event["title"]).casefold(),
    )

def dedupe(events):
    result = []
    seen = set()
    for event in sorted(
        events,
        key=lambda item: (
            item["start"],
            int(item["channel"]) if item.get("channel") in CHANNELS else 0,
            item["title"],
        ),
    ):
        key = event_key(event)
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return result

ARTICLE_REJECT = ("نتائج", "أهداف", "اهداف", "ملخص", "ترتيب", "تقييم")


def discover_daily_articles(home_url, label, keywords=("جدول مباريات اليوم",)):
    try:
        soup = BeautifulSoup(fetch(home_url), "html.parser")
    except Exception as exc:
        warn(f"{label} discovery failed: {exc}")
        return []

    urls = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        text = norm(anchor.get_text(" ", strip=True))
        href = anchor["href"]
        combined = f"{text} {href}"
        if not any(keyword in combined for keyword in keywords):
            continue
        if any(bad in text for bad in ARTICLE_REJECT):
            continue
        url = urljoin(home_url, href).split("#", 1)[0]
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)

    log(f"{label} schedule articles discovered: {len(urls)}")
    return urls[:12]

def article_date(soup):
    candidates = []
    for selector in ("h1", "title"):
        tag = soup.select_one(selector)
        if tag:
            candidates.append(norm(tag.get_text(" ", strip=True)))
    candidates.append(norm(soup.get_text(" ", strip=True))[:6000])

    for candidate in candidates:
        parsed = parse_date(candidate, NOW.date())
        if parsed:
            return parsed
    return NOW.date()

def parse_daily_article(url, source_tz=None, fallback_day=None):
    source_tz = source_tz or TZ
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
    except Exception as exc:
        warn(f"Daily schedule failed {url}: {exc}")
        return []

    day = article_date(soup) or fallback_day or NOW.date()
    events = []

    for row in soup.find_all("tr"):
        cells = [
            norm(cell.get_text(" ", strip=True))
            for cell in row.find_all(["td", "th"])
        ]
        cells = [cell for cell in cells if cell]
        joined = " | ".join(cells)

        if not THMANYAH_ANY_RE.search(joined):
            continue

        time_match = time_from_text(joined)
        if not time_match:
            continue

        title = None
        for cell in cells:
            candidate = fixture_from_text(cell)
            if candidate:
                title = candidate
                break

        if not title:
            continue

        channel = channel_from_text(joined)

        events.append({
            "channel": channel,
            "start": make_dt(day, time_match[0], time_match[1], source_tz),
            "title": title,
            "source": url,
            "confirmed": channel in CHANNELS,
        })

    if not events:
        lines = [
            norm(line)
            for line in soup.get_text("\n", strip=True).splitlines()
        ]
        lines = [line for line in lines if line]

        for index, line in enumerate(lines):
            if not THMANYAH_ANY_RE.search(line):
                continue

            block = lines[max(0, index - 4):min(len(lines), index + 4)]
            joined = " | ".join(block)
            time_match = time_from_text(joined)

            title = None
            for candidate in block:
                parsed = fixture_from_text(candidate)
                if parsed:
                    title = parsed
                    break

            if not time_match or not title:
                continue

            channel = channel_from_text(joined)

            events.append({
                "channel": channel,
                "start": make_dt(day, time_match[0], time_match[1], source_tz),
                "title": title,
                "source": url,
                "confirmed": channel in CHANNELS,
            })

    return dedupe(events)

def discover_365_articles():
    try:
        soup = BeautifulSoup(fetch(SCORES365_HOME), "html.parser")
    except Exception as exc:
        warn(f"365Scores discovery failed: {exc}")
        return []

    urls = []
    seen = set()

    for anchor in soup.find_all("a", href=True):
        url = urljoin(SCORES365_HOME, anchor["href"]).split("#", 1)[0]
        if "/ar/news/magazine/" not in url:
            continue
        if url.rstrip("/") == SCORES365_HOME.rstrip("/"):
            continue
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)

    log(f"365Scores article links discovered: {len(urls)}")
    return urls[:40]

def title_from_365(soup):
    candidates = []
    heading = soup.find("h1")
    if heading:
        candidates.append(norm(heading.get_text(" ", strip=True)))
    candidates.append(norm(soup.get_text(" ", strip=True))[:8000])

    pair_re = re.compile(
        r"(?:مباراة|مواجهة)\\s+"
        r"(.{2,70}?)\\s*[-–—]\\s*(.{2,70}?)"
        r"(?=\\s+(?:بالجولة|ضمن|في|لحساب|والقنوات|موعد|اليوم|غد(?:اً|ا)?|$))",
        re.I,
    )

    for candidate_text in candidates:
        pair = pair_re.search(candidate_text)
        if pair:
            first = clean_team(pair.group(1))
            second = clean_team(pair.group(2))
            if first and second:
                return f"{first} - {second}"

    for candidate_text in candidates:
        title = fixture_from_text(candidate_text)
        if title:
            return title
    return None

def parse_365_article(url):
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
    except Exception:
        return None

    text = norm(soup.get_text(" ", strip=True))
    channel = channel_from_text(text)
    if channel is None:
        return None

    day = parse_date(text, NOW.date())
    if not day:
        return None

    title = title_from_365(soup)
    if not title:
        return None

    return {
        "channel": channel,
        "date": day,
        "title": title,
        "source": url,
        "confirmed": True,
    }


def collect_numbered_365():
    confirmations = []
    seen = set()

    for url in discover_365_articles():
        confirmation = parse_365_article(url)
        if not confirmation:
            continue

        signature = fixture_signature(confirmation["title"])
        if not signature:
            continue

        key = (
            confirmation["date"],
            tuple(sorted(signature)),
            confirmation["channel"],
        )
        if key in seen:
            continue
        seen.add(key)
        confirmations.append(confirmation)

    confirmations.sort(
        key=lambda item: (
            item["date"],
            tuple(sorted(fixture_signature(item["title"]) or ())),
            item["channel"],
        )
    )

    log(
        f"365Scores channel-only confirmations detected: {len(confirmations)} "
        "| TIMES IGNORED"
    )
    return confirmations

def source_label(url, default="extra"):
    match = re.search(r"https?://(?:www\.)?([^/]+)", url or "")
    return match.group(1) if match else default


def yallakora_card(anchor, text):
    clock = re.search(r"(\d{1,2}):(\d{2})", text)
    if not clock:
        return None
    hour, minute = clock.group(1), clock.group(2)

    def dedupe_name(value):
        value = clean_team(value)
        if not value:
            return ""
        half = len(value) // 2
        for candidate in (value[:half], value[:half + 1]):
            candidate = candidate.strip()
            if candidate and value.replace(" ", "") == (candidate * 2).replace(" ", ""):
                return candidate
        return value

    names = []
    for node in anchor.find_all(True):
        classes = " ".join(node.get("class") or [])
        if "team" in classes.lower():
            name = clean_team(node.get_text(" ", strip=True))
            if name and name not in names:
                names.append(name)
    if len(names) >= 2:
        return dedupe_name(names[0]), dedupe_name(names[1]), hour, minute

    card = YALLAKORA_CARD_RE.search(text)
    if card:
        home = clean_team(card.group(1))
        away = clean_team(card.group(3))
        if home and away:
            return home, away, hour, minute

    before = text[:clock.start()]
    after = text[clock.end():]
    before = re.split(r"لم تبدأ|انتهت|جارية|مؤجلة|الأسبوع\s*\S+", before)[-1]
    home = dedupe_name(before.strip(" -–—|"))
    away = dedupe_name(after.strip(" -–—|"))
    if home and away and len(home) <= 40 and len(away) <= 40:
        return home, away, hour, minute

    return None


def collect_yallakora_fixtures():
    rows = []
    day_zero_titles = None

    for offset in range(0, EXTRA_LOOKAHEAD_DAYS + 1):
        day = (NOW + timedelta(days=offset)).date()
        url = YALLAKORA_DAY_URL.format(d=day.day, m=day.month, y=day.year)

        try:
            soup = BeautifulSoup(fetch(url), "html.parser")
        except Exception as exc:
            warn(f"Yallakora day {day} failed: {exc}")
            continue

        found = 0
        seen = set()
        day_rows = []
        match_links = 0
        saudi_links = 0
        sample_failed = None

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].lower()
            if "/match/" not in href:
                continue
            match_links += 1
            if not any(hint.lower() in href for hint in YALLAKORA_SAUDI_HINTS):
                continue
            saudi_links += 1

            text = norm(anchor.get_text(" ", strip=True))
            parsed_card = yallakora_card(anchor, text)
            if not parsed_card:
                if sample_failed is None:
                    sample_failed = text[:160]
                continue

            home, away, hour, minute = parsed_card
            title = f"{home} - {away}"
            key = (day, title)
            if key in seen:
                continue
            seen.add(key)

            day_rows.append({
                "channel": channel_from_text(text),
                "start": make_dt(day, hour, minute, YALLAKORA_TZ),
                "title": title,
                "source": url,
                "label": "Yallakora",
                "confirmed": False,
            })
            found += 1

        titles = {row["title"] for row in day_rows}

        if offset == 0:
            day_zero_titles = titles
        elif titles and titles == day_zero_titles:
            warn(f"Yallakora date param ignored for {day}; rows skipped")
            continue

        rows.extend(day_rows)

        log(
            f"Yallakora {day}: match links={match_links}, "
            f"saudi={saudi_links}, parsed={found}"
        )
        if saudi_links and not found and sample_failed:
            warn(f"Yallakora unparsed card sample: {sample_failed}")

    log(f"Yallakora total fixtures collected: {len(rows)}")
    return rows


def collect_extra_source_rows():
    rows = []

    for source in EXTRA_SOURCES:
        try:
            urls = discover_daily_articles(
                source["home"],
                source["label"],
                source["keywords"],
            )
        except Exception as exc:
            warn(f"{source['label']} discovery error: {exc}")
            continue

        urls = [source["home"]] + urls

        for url in urls[:6]:
            found = parse_daily_article(url, source["tz"])
            log(f"{source['label']} scanned {url}: {len(found)} rows")
            for event in found:
                event["label"] = source["label"]
                rows.append(event)


    for page in STATIC_CONFIRMATION_PAGES:
        targets = [page["url"]]
        if page.get("per_day"):
            for offset in range(0, EXTRA_LOOKAHEAD_DAYS + 1):
                day = (NOW + timedelta(days=offset)).date()
                targets.append(
                    page["per_day"].format(d=day.day, m=day.month, y=day.year)
                )

        for index, url in enumerate(targets):
            fallback = (NOW + timedelta(days=max(index - 1, 0))).date()
            found = parse_daily_article(url, page["tz"], fallback)
            for event in found:
                event["label"] = page["label"]
                rows.append(event)
            if found:
                log(f"{page['label']} rows from {url}: {len(found)}")

    rows.extend(collect_yallakora_fixtures())

    log(f"Extra-source rows collected: {len(rows)}")
    return rows


def rows_to_confirmations(rows):
    confirmations = []
    seen = set()

    for row in rows:
        channel = row.get("channel")
        if channel not in CHANNELS:
            continue

        signature = fixture_signature(row.get("title", ""))
        if not signature:
            continue

        label = row.get("label") or source_label(row.get("source", ""))
        key = (row["start"].date(), tuple(sorted(signature)), channel, label)
        if key in seen:
            continue
        seen.add(key)

        confirmations.append({
            "channel": channel,
            "date": row["start"].date(),
            "title": row["title"],
            "source": row.get("source", label),
            "label": label,
            "confirmed": True,
        })

    log(f"Extra-source channel confirmations: {len(confirmations)}")
    return confirmations


def normalize_ocr(value):
    value = html.unescape(value or "").translate(ARABIC_DIGITS)
    value = value.replace("ـ", "")
    value = value.replace("ثمانيه", "ثمانية")
    value = value.replace("ثمانيةة", "ثمانية")
    value = value.replace("x", " × ").replace("X", " × ")
    value = value.replace("🆚", " × ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()

def radar_post_day(text):
    text = normalize_ocr(text)
    months_pattern = "|".join(map(re.escape, AR_MONTHS))
    m = re.search(rf"\b(\d{{1,2}})\s+({months_pattern})\b", text, re.I)
    if not m:
        return None

    day = int(m.group(1))
    month = AR_MONTHS[m.group(2)]
    year = NOW.year

    try:
        candidate = date(year, month, day)
    except ValueError:
        return None

    if candidate < NOW.date() - timedelta(days=180):
        try:
            candidate = date(year + 1, month, day)
        except ValueError:
            pass
    return candidate

def telegram_image_url(post):
    for node in post.select(
        ".tgme_widget_message_photo_wrap, "
        ".tgme_widget_message_photo, "
        ".tgme_widget_message_document_wrap"
    ):
        style = node.get("style", "")
        m = re.search(r"background-image\s*:\s*url\(['\"]?([^'\")]+)", style)
        if m:
            return html.unescape(m.group(1))

    img = post.find("img", src=True)
    if img:
        return html.unescape(img["src"])
    return None

def ocr_image_url(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=35)
        response.raise_for_status()
    except Exception as exc:
        warn(f"RadarKora image download failed: {exc}")
        return ""

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="radarkora_",
            suffix=".jpg",
            delete=False,
        ) as tmp:
            tmp.write(response.content)
            tmp_path = tmp.name

        outputs = []
        for psm in ("3", "6", "11"):
            try:
                proc = subprocess.run(
                    [
                        "tesseract",
                        tmp_path,
                        "stdout",
                        "-l",
                        "ara+eng",
                        "--psm",
                        psm,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=45,
                    check=False,
                )
                if proc.stdout.strip():
                    outputs.append(proc.stdout)
            except Exception as exc:
                warn(f"RadarKora OCR psm={psm} failed: {exc}")

        return "\n".join(outputs).strip()

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass



def radar_day_from_ocr_line(line):
    text = normalize_ocr(line)
    months_pattern = "|".join(map(re.escape, AR_MONTHS))
    m = re.search(rf"(?<!\d)(\d{{1,2}})\s*[-–—]?\s*({months_pattern})(?:\s*[-–—]?\s*(20\d{{2}}))?", text, re.I)
    if not m:
        return None
    day = int(m.group(1))
    month = AR_MONTHS[m.group(2)]
    year = int(m.group(3)) if m.group(3) else NOW.year
    try:
        return date(year, month, day)
    except ValueError:
        return None


def radar_rows_from_ocr(ocr_text, fallback_day=None):
    rows = []
    current_day = fallback_day
    seen = set()

    glyphs = {
        "①":"1","②":"2","③":"3","❶":"1","❷":"2","❸":"3",
        "➀":"1","➁":"2","➂":"3","➊":"1","➋":"2","➌":"3",
        "⑴":"1","⑵":"2","⑶":"3","⓵":"1","⓶":"2","⓷":"3",
    }

    for raw_line in (ocr_text or "").splitlines():
        line = normalize_ocr(raw_line)
        if not line:
            continue

        heading_day = radar_day_from_ocr_line(line)
        if heading_day:
            current_day = heading_day
            continue

        fixed = line.translate(ARABIC_DIGITS)
        for a, b in glyphs.items():
            fixed = fixed.replace(a, b)

        m = re.search(
            r"(?:قناة|قناه)?\s*(?:ثمانية|ثمانيه|ثماني|thmanyah)\s*[:：.\-]?\s*([123])(?:\d)?\b",
            fixed,
            re.I,
        )
        if not m:
            continue

        prefix = fixed[max(0, m.start() - 20):m.start()]
        if "تطبيق" in prefix and not re.search(r"(?:قناة|قناه)", prefix):
            continue

        channel = int(m.group(1))
        if channel not in CHANNELS:
            continue

        key = (current_day, channel, fixed)
        if key in seen:
            continue
        seen.add(key)
        rows.append((current_day, channel, fixed))

    return rows

def team_tokens(value):
    value = normalize_team_name(value)
    stop = {"نادي", "fc", "club", "ريال", "ال", "و"}
    tokens = [
        token for token in value.split()
        if len(token) >= 3 and token not in stop
    ]
    if not tokens:
        tokens = [token for token in value.split() if len(token) >= 3]
    return tokens

def fixture_match_score(title, context):
    signature = fixture_signature(title)
    if not signature or len(signature) != 2:
        return 0

    context_norm = normalize_team_name(context)
    teams = list(signature)
    team_scores = []

    for team in teams:
        tokens = team_tokens(team)
        if not tokens:
            team_scores.append(0)
            continue

        context_words = [w for w in context_norm.split() if len(w) >= 3]
        hits = 0
        for token in tokens:
            if token in context_norm:
                hits += 1
                continue
            best = max(
                (SequenceMatcher(None, token, word).ratio() for word in context_words),
                default=0.0,
            )
            if best >= 0.74:
                hits += 1
        team_scores.append(hits / len(tokens))

    if min(team_scores) < 0.45:
        return 0
    return sum(team_scores)

def radar_contexts(ocr_text):
    raw = html.unescape(ocr_text or "").translate(ARABIC_DIGITS)
    glyphs = {"①":"1","②":"2","③":"3","❶":"1","❷":"2","❸":"3","➀":"1","➁":"2","➂":"3","➊":"1","➋":"2","➌":"3","⑴":"1","⑵":"2","⑶":"3","⓵":"1","⓶":"2","⓷":"3"}
    for a,b in glyphs.items(): raw=raw.replace(a, f" {b} ")
    text=normalize_ocr(raw); contexts=[]; seen=set()
    def add(n,a,b):
        n=int(n)
        if n not in CHANNELS: return
        c=text[max(0,a-320):min(len(text),b+320)]
        if (n,c) not in seen: seen.add((n,c)); contexts.append((n,c))
    for m in THMANYAH_NUMBER_RE.finditer(text): add(m.group(1),m.start(),m.end())
    for m in THMANYAH_NUMBER_BEFORE_RE.finditer(text): add(m.group(1),m.start(),m.end())
    pats=[re.compile(r"(?:القناة|قناه|channel|ناقلة|الناقلة|الناقل)\s*[:：\-–—|]?\s*(?:ثمانية|ثمانيه|thmanyah)?\s*[\[\(\{<]?\s*([123])\s*[\]\)\}>]?",re.I),re.compile(r"(?:ثمانية|ثمانيه|thmanyah)\s*(?:sports?|sport)?\s*[:：\-–—|]?\s*[\[\(\{<]?\s*([123])\s*[\]\)\}>]?",re.I)]
    for pat in pats:
        for m in pat.finditer(text): add(m.group(1),m.start(),m.end())
    lines=[normalize_ocr(x) for x in (ocr_text or '').splitlines() if normalize_ocr(x)]
    dr=re.compile(r"^[^\w\u0600-\u06ff]{0,4}([123])[^\w\u0600-\u06ff]{0,4}$")
    for i,line in enumerate(lines):
        c=line.translate(ARABIC_DIGITS)
        for a,b in glyphs.items(): c=c.replace(a,b)
        c=normalize_ocr(c); m=dr.match(c)
        if not m: continue
        block=normalize_ocr(' '.join(lines[max(0,i-4):min(len(lines),i+5)]))
        if fixture_from_text(block) is None and not any(x in block for x in ('مباراة','مباريات','الدوري','كأس','دوري روشن','vs',' × ','ضد')): continue
        pos=text.find(c); pos=max(0,pos); add(m.group(1),pos,pos+len(c))
    return contexts


def _layout_preprocess_image(path):
    image = Image.open(path).convert("RGB")
    if image.width < 2200:
        scale = max(2, min(3, round(2200 / max(1, image.width))))
        image = image.resize(
            (image.width * scale, image.height * scale),
            Image.Resampling.LANCZOS,
        )

    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(1.45)
    return gray


def _ocr_data_lines(image):
    data = pytesseract.image_to_data(
        image,
        lang="ara+eng",
        config="--oem 1 --psm 6",
        output_type=Output.DICT,
    )

    groups = defaultdict(list)
    total = len(data.get("text", []))

    for i in range(total):
        token = normalize_ocr(data["text"][i])
        if not token:
            continue

        try:
            conf = float(str(data.get("conf", ["-1"] * total)[i]))
        except Exception:
            conf = -1

        if conf < 10:
            continue

        key = (
            data.get("block_num", [0] * total)[i],
            data.get("par_num", [0] * total)[i],
            data.get("line_num", [0] * total)[i],
        )

        left = int(data["left"][i])
        top = int(data["top"][i])
        width = int(data["width"][i])
        height = int(data["height"][i])

        groups[key].append({
            "text": token,
            "left": left,
            "top": top,
            "right": left + width,
            "bottom": top + height,
            "cy": top + height / 2.0,
        })

    lines = []

    for words in groups.values():
        y = sum(w["cy"] for w in words) / len(words)
        by_x = sorted(words, key=lambda w: w["left"])
        ltr = " ".join(w["text"] for w in by_x)
        rtl = " ".join(w["text"] for w in reversed(by_x))
        combined = normalize_ocr(f"{ltr} | {rtl}")
        lines.append((y, combined, words))

    lines.sort(key=lambda item: item[0])
    return lines


def _extract_channel_from_row_text(text):
    value = normalize_ocr(text).translate(ARABIC_DIGITS)

    glyphs = {
        "①":"1","②":"2","③":"3","❶":"1","❷":"2","❸":"3",
        "➀":"1","➁":"2","➂":"3","➊":"1","➋":"2","➌":"3",
        "⑴":"1","⑵":"2","⑶":"3","⓵":"1","⓶":"2","⓷":"3",
    }
    for a, b in glyphs.items():
        value = value.replace(a, b)

    if "تطبيق" in value and not re.search(r"(?:قناة|قناه)", value):
        return None

    patterns = (
        r"(?:قناة|قناه)\s*(?:ثمانية|ثمانيه|ثماني|thmanyah)\s*[:：.\-]?\s*([123])\b",
        r"(?:ثمانية|ثمانيه|ثماني|thmanyah)\s*[:：.\-]?\s*([123])\b",
        r"(?:ثمانية|ثمانيه|ثماني|thmanyah)([123])\b",
    )

    for pattern in patterns:
        m = re.search(pattern, value, re.I)
        if m:
            n = int(m.group(1))
            if n in CHANNELS:
                return n

    return None


def _ocr_row_crop(image, y_center, height_hint=34):
    pad = max(38, int(height_hint * 2.2))
    top = max(0, int(y_center - pad))
    bottom = min(image.height, int(y_center + pad))

    crop = image.crop((0, top, image.width, bottom))
    crop = ImageOps.autocontrast(crop, cutoff=1)

    outputs = []

    for psm in (6, 11):
        try:
            out = pytesseract.image_to_string(
                crop,
                lang="ara+eng",
                config=f"--oem 1 --psm {psm}",
            )
            if out.strip():
                outputs.append(out)
        except Exception as exc:
            warn(f"matches_today2 row OCR psm={psm} failed: {exc}")

    return "\n".join(outputs)


def ocr_table_rows_url(url, fallback_day=None):
    try:
        response = requests.get(url, headers=HEADERS, timeout=35)
        response.raise_for_status()
    except Exception as exc:
        warn(f"matches_today2 image download failed: {exc}")
        return []

    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            prefix="matches_today2_layout_",
            suffix=".jpg",
            delete=False,
        ) as tmp:
            tmp.write(response.content)
            tmp_path = tmp.name

        image = _layout_preprocess_image(tmp_path)
        lines = _ocr_data_lines(image)

        date_marks = []
        for y, line_text, _ in lines:
            day = radar_day_from_ocr_line(line_text)
            if day:
                date_marks.append((y, day))

        def day_for_y(y):
            candidates = [(dy, day) for dy, day in date_marks if dy <= y + 6]
            if candidates:
                return max(candidates, key=lambda item: item[0])[1]
            return fallback_day

        candidates = []

        for y, line_text, words in lines:
            channel = _extract_channel_from_row_text(line_text)

            if channel is None and not re.search(
                r"(?:ثمان|thmanyah)",
                line_text,
                re.I,
            ):
                continue

            h = max(
                (w["bottom"] - w["top"] for w in words),
                default=34,
            )

            row_text = _ocr_row_crop(image, y, h)
            channel = _extract_channel_from_row_text(
                f"{line_text}\n{row_text}"
            )

            if channel is None:
                continue

            candidates.append((y, channel, row_text))

        candidates.sort(key=lambda item: item[0])

        merged = []

        for y, channel, row_text in candidates:
            if (
                merged
                and abs(y - merged[-1][0]) < 40
                and channel == merged[-1][1]
            ):
                if len(normalize_ocr(row_text)) > len(
                    normalize_ocr(merged[-1][2])
                ):
                    merged[-1] = (y, channel, row_text)
                continue

            merged.append((y, channel, row_text))

        rows = []
        seen = set()

        for y, channel, row_text in merged:
            day = day_for_y(y)
            context = normalize_ocr(row_text)
            key = (day, channel, context)

            if key in seen:
                continue

            seen.add(key)
            rows.append((day, channel, context))

        return rows

    except Exception as exc:
        warn(f"matches_today2 layout OCR failed: {exc}")
        return []

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass




_OCR_TEAM_LEXICON = [
    "الهلال", "الفيحاء", "الرياض", "النصر", "الحزم", "الدرعية",
    "الفيصلي", "نيوم", "القادسية", "الاتحاد", "الفتح", "الاتفاق",
    "الخلود", "التعاون", "الخليج", "الشباب", "الأهلي", "ابها", "أبها",
    "ضمك", "العلا", "الأخدود", "الوحدة", "الرائد", "الباطن",
]

def _arabic_loose(value):
    value = normalize_ocr(value).translate(ARABIC_DIGITS)
    value = (value.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
                  .replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و")
                  .replace("ئ", "ي"))
    value = re.sub(r"[^\u0600-\u06ff ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def _repair_ocr_team(raw):
    raw = normalize_ocr(raw)
    target = _arabic_loose(raw)
    if not target:
        return None, 0.0
    ranked = []
    for team in _OCR_TEAM_LEXICON:
        candidate = _arabic_loose(team)
        score = SequenceMatcher(None, target, candidate).ratio()
        if candidate in target or target in candidate:
            score = max(score, 0.82)
        ranked.append((score, team))
    ranked.sort(reverse=True)
    score, team = ranked[0]
    if score < 0.42:
        return raw.strip(), score
    if team == "ابها":
        team = "أبها"
    return team, score

def _fixture_from_right_column(text):
    value = normalize_ocr(text)
    matches = list(re.finditer(
        r"([\u0600-\u06ff][\u0600-\u06ff\s]{1,24})\s*[-–—]\s*"
        r"([\u0600-\u06ff][\u0600-\u06ff\s]{1,24})",
        value,
    ))
    best = None
    for match in matches:
        left_raw = match.group(1).strip()
        right_raw = match.group(2).strip()
        left, ls = _repair_ocr_team(left_raw)
        right, rs = _repair_ocr_team(right_raw)
        score = ls + rs
        if left and right and (best is None or score > best[0]):
            best = (score, left, right)
    if not best:
        return None
    _, left, right = best
    return f"{left} - {right}"

def _channel_from_middle_column(text):
    value = normalize_ocr(text).translate(ARABIC_DIGITS)
    if "تطبيق" in value and not re.search(r"(?:قناة|قناه)", value):
        return None
    patterns = (
        r"(?:قناة|قناه)?\s*ثمان[^\s0-9]{0,7}\s*([123])",
        r"(?:قناة|قناه)[^\n]{0,22}?([123])",
    )
    for pattern in patterns:
        match = re.search(pattern, value, re.I)
        if match:
            return int(match.group(1))
    return _extract_channel_from_row_text(value)

def _kickoff_from_right_column(text):
    value = normalize_ocr(text).translate(ARABIC_DIGITS)
    candidates = []
    for match in re.finditer(r"[:.]", value):
        pos = match.start()
        after = re.match(r"\s*([0-9]{2})", value[pos + 1:])
        if not after:
            continue
        minute = int(after.group(1))
        if minute > 59:
            continue
        before = re.sub(r"\s+", "", value[max(0, pos - 4):pos])
        digits = re.findall(r"[0-9]", before)
        for width in (1, 2):
            if len(digits) < width:
                continue
            hour = int("".join(digits[-width:]))
            if 1 <= hour <= 12:
                candidates.append((hour, minute))
    if not candidates:
        compact = []
        for m in re.finditer(r"(?<![0-9])([0-9]{3,4})(?![0-9])", value):
            digits = m.group(1)
            minute = int(digits[-2:])
            hour = int(digits[0])
            if 1 <= hour <= 9 and 0 <= minute <= 59:
                compact.append((hour, minute))
        if compact:
            candidates.extend(compact)
    if not candidates:
        return None
    counts = defaultdict(int)
    for item in candidates:
        counts[item] += 1
    hour, minute = max(counts, key=lambda item: (counts[item], -item[0]))
    if 1 <= hour <= 11:
        hour += 12
    return hour, minute

def _kickoff_from_time_crop(gray, y):
    pad = max(38, int(gray.height * 0.014))
    votes = defaultdict(int)
    for offset in (0, 20, 40, 60):
        cy = y + offset
        top = max(0, int(cy - pad))
        bottom = min(gray.height, int(cy + pad))
        crop = gray.crop((int(gray.width * 0.78), top, gray.width, bottom))
        variants = [
            ImageOps.autocontrast(crop, cutoff=1),
            ImageEnhance.Contrast(ImageOps.autocontrast(crop, cutoff=1)).enhance(2.0),
        ]
        for variant in variants:
            for psm in (7, 13):
                try:
                    raw = pytesseract.image_to_string(
                        variant,
                        lang="eng",
                        config=(
                            f"--oem 1 --psm {psm} "
                            "-c tessedit_char_whitelist=0123456789:."
                        ),
                    )
                except Exception:
                    continue
                text = normalize_ocr(raw).translate(ARABIC_DIGITS)
                for m in re.finditer(r"([0-9]{1,3})\s*[:.]\s*([0-9]{2})", text):
                    raw_hour = m.group(1)
                    minute = int(m.group(2))
                    if minute > 59:
                        continue
                    opts = [int(raw_hour[-1])]
                    if len(raw_hour) <= 2:
                        opts.append(int(raw_hour))
                    for hour in set(opts):
                        if 1 <= hour <= 12:
                            votes[(hour, minute)] += 2
                digits = re.sub(r"\D", "", text)
                if len(digits) >= 3:
                    tail = digits[-3:]
                    hour = int(tail[0])
                    minute = int(tail[1:])
                    if 1 <= hour <= 9 and 0 <= minute <= 59:
                        votes[(hour, minute)] += 1
    if not votes:
        return None
    hour, minute = max(votes, key=lambda item: (votes[item], -item[0]))
    if 1 <= hour <= 11:
        hour += 12
    return hour, minute

def _structured_rows_from_image(image, fallback_day=None):
    if image.width < 1800:
        scale = 2
        image = image.resize(
            (image.width * scale, image.height * scale),
            Image.Resampling.LANCZOS,
        )
    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(1.45)

    data = pytesseract.image_to_data(
        gray,
        lang="ara+eng",
        config="--oem 1 --psm 6",
        output_type=Output.DICT,
    )
    groups = defaultdict(list)
    total = len(data.get("text", []))
    for i in range(total):
        token = normalize_ocr(data["text"][i])
        if not token:
            continue
        try:
            conf = float(str(data.get("conf", ["-1"] * total)[i]))
        except Exception:
            conf = -1
        if conf < 8:
            continue
        key = (
            data.get("block_num", [0] * total)[i],
            data.get("par_num", [0] * total)[i],
            data.get("line_num", [0] * total)[i],
        )
        top = int(data["top"][i])
        height = int(data["height"][i])
        left = int(data["left"][i])
        groups[key].append((top + height / 2.0, left, token))

    lines = []
    for words in groups.values():
        y = sum(item[0] for item in words) / len(words)
        text = " ".join(item[2] for item in sorted(words, key=lambda x: x[1]))
        lines.append((y, normalize_ocr(text)))
    lines.sort(key=lambda x: x[0])

    date_marks = []
    for y, text in lines:
        day = radar_day_from_ocr_line(text)
        if day:
            date_marks.append((y, day))
            continue
        v = text.translate(ARABIC_DIGITS)
        m = re.search(r"2026[^0-9]{0,30}(1[8-9]|2[0-9]|3[0-1])", v)
        if m and ("اغسطس" in _arabic_loose(v) or "أغسطس" in v):
            try:
                date_marks.append((y, date(2026, 8, int(m.group(1)))))
            except ValueError:
                pass

    def day_for_y(y):
        previous = [(dy, d) for dy, d in date_marks if dy < y]
        if previous:
            return max(previous, key=lambda x: x[0])[1]
        return fallback_day

    rows = []
    used_y = []
    for y, line_text in lines:
        row_day = day_for_y(y)
        if not row_day:
            continue
        if not re.search(r"[-–—]", line_text):
            continue
        if "Twitter" in line_text or "2026" in line_text:
            continue
        if any(word in line_text for word in ("القنوات", "المعلقين", "تنبيه", "الواتساب", "تيليجرام")):
            continue
        if any(abs(y - old) < 24 for old in used_y):
            continue

        pad = max(42, int(gray.height * 0.014))
        top = max(0, int(y - pad))
        bottom = min(gray.height, int(y + pad))
        middle = gray.crop((int(gray.width * 0.32), top, int(gray.width * 0.65), bottom))
        right = gray.crop((int(gray.width * 0.73), top, gray.width, bottom))
        right_wide = gray.crop((int(gray.width * 0.55), top, gray.width, bottom))

        middle_outputs = []
        right_outputs = []

        for psm in (6, 7, 11, 13):
            try:
                mt = normalize_ocr(pytesseract.image_to_string(
                    middle, lang="ara+eng", config=f"--oem 1 --psm {psm}"
                ))
                if mt:
                    middle_outputs.append(mt)
            except Exception as exc:
                warn(f"matches_today2 middle-column OCR psm={psm} failed: {exc}")

        fast_title = None
        for offset in (-4, 0, 4):
            rtop = max(0, int(y + offset - pad))
            rbottom = min(gray.height, int(y + offset + pad))
            shifted_right = gray.crop((int(gray.width * 0.55), rtop, gray.width, rbottom))
            for psm in (6, 7, 11, 13):
                try:
                    rt = normalize_ocr(pytesseract.image_to_string(
                        shifted_right, lang="ara+eng", config=f"--oem 1 --psm {psm}"
                    ))
                    if rt:
                        right_outputs.append(rt)
                except Exception as exc:
                    warn(f"matches_today2 right-column OCR psm={psm} failed: {exc}")

        middle_text = " | ".join(middle_outputs)
        right_text = " | ".join(right_outputs + [line_text])

        channel_votes = []
        for mt in middle_outputs:
            ch = _extract_channel_from_row_text(mt)
            if ch not in CHANNELS:
                ch = _channel_from_middle_column(mt)
            if ch in CHANNELS:
                channel_votes.append(ch)
        if not channel_votes:
            continue
        counts = {n: channel_votes.count(n) for n in CHANNELS}
        best_count = max(counts.values())
        winners = [n for n, c in counts.items() if c == best_count and c > 0]
        if len(winners) != 1:
            continue
        channel = winners[0]

        fixture_candidates = []
        for candidate_text in right_outputs:
            match = re.search(
                r"([\u0600-\u06ff][\u0600-\u06ff\s]{1,24})\s*[-–—]\s*"
                r"([\u0600-\u06ff][\u0600-\u06ff\s]{1,24})",
                normalize_ocr(candidate_text),
            )
            if not match:
                continue
            left, ls = _repair_ocr_team(match.group(1).strip())
            right_team, rs = _repair_ocr_team(match.group(2).strip())
            if left and right_team:
                fixture_candidates.append((ls + rs, f"{left} - {right_team}"))
        if not fixture_candidates:
            fallback_title = _fixture_from_right_column(line_text)
            if fallback_title:
                parts = fallback_title.split(" - ", 1)
                if len(parts) == 2:
                    a, sa = _repair_ocr_team(parts[0])
                    b, sb = _repair_ocr_team(parts[1])
                    if a and b:
                        fixture_candidates.append((sa + sb - 0.15, f"{a} - {b}"))

        if not fixture_candidates:
            team_hits = {}
            combined_team_text = " | ".join(right_outputs + [line_text])
            for token in re.findall(r"[\u0600-\u06ff]{3,18}", combined_team_text):
                team, score = _repair_ocr_team(token)
                if team in _OCR_TEAM_LEXICON and score >= 0.68:
                    prev = team_hits.get(team, 0.0)
                    if score > prev:
                        team_hits[team] = score
            if len(team_hits) >= 2:
                ranked_teams = sorted(
                    team_hits.items(), key=lambda item: item[1], reverse=True
                )[:2]
                a, sa = ranked_teams[0]
                b, sb = ranked_teams[1]
                if a != b:
                    fixture_candidates.append((sa + sb - 0.25, f"{a} - {b}"))

        if not fixture_candidates:
            continue
        fixture_candidates.sort(key=lambda x: x[0], reverse=True)
        title = fixture_candidates[0][1]

        kickoff = _kickoff_from_right_column(" | ".join(right_outputs))
        if not kickoff:
            kickoff = _kickoff_from_time_crop(gray, y)
        if not kickoff:
            kickoff = _kickoff_from_right_column(line_text)
        if not kickoff:
            continue
        hour, minute = kickoff
        start = datetime(
            row_day.year, row_day.month, row_day.day,
            hour, minute, tzinfo=TZ,
        )
        rows.append({
            "date": row_day,
            "channel": channel,
            "title": title,
            "start": start,
            "context": normalize_ocr(right_text + " | " + middle_text),
        })
        used_y.append(y)

    unique = []
    seen = set()
    for row in rows:
        sig = (row["start"], norm(row["title"]).casefold(), row["channel"])
        if sig in seen:
            continue
        seen.add(sig)
        unique.append(row)
    return unique

def ocr_structured_table_url(url, fallback_day=None):
    try:
        response = requests.get(url, headers=HEADERS, timeout=35)
        response.raise_for_status()
        image = Image.open(__import__("io").BytesIO(response.content)).convert("RGB")
        return _structured_rows_from_image(image, fallback_day=fallback_day)
    except Exception as exc:
        warn(f"matches_today2 structured table OCR failed: {exc}")
        return []


def collect_radarkora_confirmations(daily):
    confirmations = []
    direct_events = []
    max_pages = 12
    before_id = None
    seen_message_ids = set()

    window_floor = (NOW - timedelta(days=KEEP_DAYS_BACK + 1)).date()
    window_ceiling = (NOW + timedelta(days=KEEP_DAYS_FORWARD + 1)).date()

    for page_index in range(max_pages):
        page_url = (
            RADARKORA_TELEGRAM
            if before_id is None
            else f"{RADARKORA_TELEGRAM}?before={before_id}"
        )

        try:
            soup = BeautifulSoup(fetch(page_url), "html.parser")
        except Exception as exc:
            warn(f"RadarKora Telegram page {page_index + 1} fetch failed: {exc}")
            break

        posts = soup.select(".tgme_widget_message")
        if not posts:
            break

        page_ids = []
        page_days = []

        for post in posts:
            data_post = post.get("data-post", "")
            id_match = re.search(r"/(\d+)$", data_post)

            if id_match:
                message_id = int(id_match.group(1))
                page_ids.append(message_id)
                if message_id in seen_message_ids:
                    continue
                seen_message_ids.add(message_id)

            caption_node = post.select_one(
                ".tgme_widget_message_text, .tgme_widget_message_caption"
            )
            caption = (
                caption_node.get_text(" ", strip=True)
                if caption_node else ""
            )
            caption_norm = normalize_ocr(caption)

            if caption_norm and not any(
                marker in caption_norm
                for marker in (
                    "مباريات_اليوم",
                    "مباريات اليوم",
                    "المباريات",
                    "جدول المباريات",
                    "مباريات",
                )
            ):
                continue

            post_day = radar_post_day(caption_norm)
            if post_day:
                page_days.append(post_day)

            image_url = telegram_image_url(post)
            if not image_url:
                continue

            if post_day and not (window_floor <= post_day <= window_ceiling):
                continue

            structured_rows = ocr_structured_table_url(
                image_url,
                fallback_day=post_day,
            )
            if structured_rows:
                log(f"matches_today2 STRUCTURED TABLE: {len(structured_rows)} candidate numbered rows")
            for srow in structured_rows:
                candidate_events = [
                    event for event in daily
                    if event["start"].date() == srow["date"]
                ]
                scored = []
                for event in candidate_events:
                    score = fixture_match_score(event["title"], srow["title"])
                    if score > 0:
                        scored.append((score, event))
                scored.sort(key=lambda item: item[0], reverse=True)
                if not scored:
                    log(
                        "STRUCTURED OCR UNMATCHED | "
                        f"{srow['date']} | {srow['title']} | THMANYAH {srow['channel']}"
                    )
                    continue
                best_score, best = scored[0]
                second_score = scored[1][0] if len(scored) > 1 else 0
                if second_score and abs(best_score - second_score) < 1e-9:
                    log(
                        "STRUCTURED OCR AMBIGUOUS | "
                        f"{srow['date']} | {srow['title']} | THMANYAH {srow['channel']}"
                    )
                    continue
                confirmations.append({
                    "channel": srow["channel"],
                    "date": best["start"].date(),
                    "title": best["title"],
                    "source": "matches_today2 structured image OCR CHANNEL-ONLY",
                    "confirmed": True,
                })
                log(
                    "STRUCTURED OCR CHANNEL CONFIRMATION | "
                    f"{best['start']:%Y-%m-%d %H:%M} | "
                    f"{best['title']} | THMANYAH {srow['channel']} | SOURCE KICKOFF KEPT"
                )

            layout_rows = ocr_table_rows_url(
                image_url,
                fallback_day=post_day,
            )

            full_rows = []
            ocr_text = ocr_image_url(image_url)
            if ocr_text:
                full_rows = radar_rows_from_ocr(
                    ocr_text,
                    fallback_day=post_day,
                )

            rows = []
            row_seen = set()
            for row_day, channel, context in layout_rows + full_rows:
                normalized_context = normalize_ocr(context)
                key = (row_day, channel, normalized_context)
                if key in row_seen:
                    continue
                row_seen.add(key)
                rows.append((row_day, channel, context))

            log(
                "matches_today2 OCR merge | "
                f"layout={len(layout_rows)} full={len(full_rows)} "
                f"merged={len(rows)}"
            )

            for row_day, _, _ in rows:
                if row_day:
                    page_days.append(row_day)

            log(
                f"matches_today2 image "
                f"{post_day.isoformat() if post_day else '[date from image]'}: "
                f"{len(rows)} numbered Thmanyah table rows found"
            )

            for row_day, channel, context in rows:
                if row_day and not (window_floor <= row_day <= window_ceiling):
                    continue

                if row_day:
                    candidate_events = [
                        event for event in daily
                        if event["start"].date() == row_day
                    ]
                else:
                    candidate_events = [
                        event for event in daily
                        if window_floor <= event["start"].date() <= window_ceiling
                    ]

                scored = []

                for event in candidate_events:
                    score = fixture_match_score(event["title"], context)
                    if score > 0:
                        scored.append((score, event))

                scored.sort(key=lambda item: item[0], reverse=True)
                if not scored:
                    log(
                        "OCR ROW UNMATCHED | "
                        f"{row_day.isoformat() if row_day else '[DATE INFER]'} | "
                        f"THMANYAH {channel} | {normalize_ocr(context)[:180]}"
                    )
                    continue

                best_score, best = scored[0]
                second_score = scored[1][0] if len(scored) > 1 else 0

                if second_score and abs(best_score - second_score) < 1e-9:
                    log(
                        "OCR ROW AMBIGUOUS TIE | "
                        f"{row_day.isoformat() if row_day else '[DATE INFER]'} | "
                        f"THMANYAH {channel} | "
                        f"best={best_score:.3f} | {normalize_ocr(context)[:180]}"
                    )
                    continue

                confirmations.append({
                    "channel": channel,
                    "date": best["start"].date(),
                    "title": best["title"],
                    "source": "matches_today2 Telegram OCR AUTHORITATIVE",
                    "confirmed": True,
                })

                log(
                    "OCR AUTHORITATIVE CONFIRMATION | "
                    f"{best['start']:%Y-%m-%d %H:%M} | "
                    f"{best['title']} | THMANYAH {channel}"
                    + (" | DATE INFERRED FROM FIXTURE" if row_day is None else "")
                )

        if not page_ids:
            break

        next_before = min(page_ids)
        if before_id is not None and next_before >= before_id:
            break

        before_id = next_before

        if page_days and max(page_days) < window_floor:
            break

    unique = []
    seen = set()
    for item in confirmations:
        signature = fixture_signature(item["title"])
        key = (
            item.get("date"),
            tuple(sorted(signature)) if signature else norm(item["title"]).casefold(),
            item.get("channel"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    direct_events = dedupe(direct_events)
    log(f"matches_today2 numbered confirmations detected: {len(unique)}")
    log(f"matches_today2 direct structured EPG events detected: {len(direct_events)}")
    return unique, direct_events

def fuzzy_same_fixture(first_signature, second_signature, threshold=0.86):
    if not first_signature or not second_signature:
        return False
    if first_signature == second_signature:
        return True

    left = sorted(first_signature)
    right = sorted(second_signature)
    if len(left) != 2 or len(right) != 2:
        return False

    def close(a, b):
        if a in b or b in a:
            return True
        return SequenceMatcher(None, a, b).ratio() >= threshold

    straight = close(left[0], right[0]) and close(left[1], right[1])
    crossed = close(left[0], right[1]) and close(left[1], right[0])
    return straight or crossed


def vote_channel(candidates):
    voters = defaultdict(set)
    for candidate in candidates:
        channel = candidate.get("channel")
        if channel not in CHANNELS:
            continue
        label = candidate.get("label") or source_label(candidate.get("source", ""))
        voters[int(channel)].add(label)

    if not voters:
        return None, 0, ""

    ranked = sorted(
        voters.items(),
        key=lambda item: (len(item[1]), -item[0]),
        reverse=True,
    )

    best_channel, best_labels = ranked[0]
    if len(ranked) > 1 and len(ranked[1][1]) == len(best_labels):
        log(
            "CHANNEL CONFLICT | sources disagree: "
            + ", ".join(
                f"ثمانية {channel}={sorted(labels)}"
                for channel, labels in ranked
            )
        )
        return None, 0, ""

    return best_channel, len(best_labels), ", ".join(sorted(best_labels))


def confirmation_map(confirmations):
    result = defaultdict(list)
    for event in confirmations:
        signature = fixture_signature(event["title"])
        if signature:
            result[signature].append(event)
    return result


def apply_confirmations(daily, confirmations):
    by_signature = confirmation_map(confirmations)
    result = []

    for event in daily:
        current = dict(event)

        if current.get("channel") in CHANNELS:
            current["confirmed"] = True
            result.append(current)
            continue

        signature = fixture_signature(current["title"])
        candidates = by_signature.get(signature, []) if signature else []
        candidates = [
            candidate
            for candidate in candidates
            if candidate.get("date") == current["start"].date()
        ]

        if not candidates and signature:
            candidates = [
                candidate
                for candidate in confirmations
                if candidate.get("date") == current["start"].date()
                and fuzzy_same_fixture(signature, fixture_signature(candidate["title"]))
            ]

        chosen, votes, detail = vote_channel(candidates)

        if chosen:
            original_start = current["start"]
            current["channel"] = chosen
            current["confirmed"] = True
            current["source"] = (
                f"{current['source']} + channel confirmed by {votes} source(s): {detail}"
            )

            if current["start"] != original_start:
                raise RuntimeError("Channel confirmation altered kickoff time")

            log(
                "CHANNEL CONFIRMATION | "
                f"{current['start']:%Y-%m-%d %H:%M} | "
                f"{current['title']} | THMANYAH {current['channel']} | "
                "kickoff kept from Goal/Kooora"
            )

        result.append(current)

    return dedupe([
        event for event in result
        if in_window(event["start"])
    ])

def assign_unconfirmed(events):
    output = []

    for event in dedupe(events):
        item = dict(event)

        if item.get("channel") in CHANNELS:
            item["confirmed"] = True
            output.append(item)
            continue

        item["channel"] = None
        item["confirmed"] = False
        item["source"] = f"{item['source']} + channel unknown"
        output.append(item)

        log(
            "THMANYAH GUIDE | "
            f"{item['start']:%Y-%m-%d %H:%M} | {item['title']}"
        )

    return dedupe(output)

def read_existing():
    return []

def merge_existing(existing, fresh):
    return dedupe([
        event for event in fresh
        if in_window(event["start"])
    ])

def write_xml(events):
    tv = ET.Element(
        "tv",
        {"generator-info-name": "Thmanyah Sports EPG FINAL v15"},
    )

    for number in CHANNELS:
        channel_id = f"Thmanyah{number}.sa"
        channel = ET.SubElement(tv, "channel", {"id": channel_id})
        ET.SubElement(channel, "display-name", {"lang": "en"}).text = f"Thmanyah {number}"
        ET.SubElement(channel, "display-name", {"lang": "ar"}).text = f"ثمانية {number}"
        ET.SubElement(channel, "icon", {"src": f"{LOGO_BASE}/thmanyah{number}.png"})

    guide = ET.SubElement(tv, "channel", {"id": GUIDE_CHANNEL_ID})
    ET.SubElement(guide, "display-name", {"lang": "en"}).text = "Thmanyah | Guide"
    ET.SubElement(guide, "display-name", {"lang": "ar"}).text = "ثمانية | Guide"
    ET.SubElement(guide, "icon", {"src": f"{LOGO_BASE}/thmanyah_guide.png"})

    events = dedupe(events)

    by_day = defaultdict(list)
    for event in events:
        by_day[event["start"].date()].append(event)

    real_by_id = {
        "Thmanyah1.sa": [],
        "Thmanyah2.sa": [],
        "Thmanyah3.sa": [],
        GUIDE_CHANNEL_ID: [],
    }

    def time_text(event):
        return three_zone_times(event["start"])

    def source_time_text(event):
        return three_zone_times(event["start"])

    def day_summary(day):
        day_events = sorted(by_day.get(day, []), key=lambda x: (x["start"], x["title"]))
        if not day_events:
            return "لا توجد مباريات معلنة على شبكة ثمانية لهذا اليوم."

        lines = []
        for event in day_events:
            channel = event.get("channel")
            channel_text = f"ثمانية {channel}" if channel in CHANNELS else "رقم القناة لم يعلن"
            lines.append(
                f"{event['title']} | {channel_text}\n   {time_text(event)}"
            )
        return "\n".join(lines)

    guide_groups = []
    for event in sorted(events, key=lambda e: (e["start"], e["title"])):
        if guide_groups and guide_groups[-1]["start"] == event["start"]:
            guide_groups[-1]["events"].append(event)
        else:
            guide_groups.append({"start": event["start"], "events": [event]})

    for index, group in enumerate(guide_groups):
        stop = group["start"] + timedelta(hours=3)
        if index + 1 < len(guide_groups):
            stop = min(stop, guide_groups[index + 1]["start"])
        if stop <= group["start"]:
            continue

        real_by_id[GUIDE_CHANNEL_ID].append((group["start"], stop))
        gp = ET.SubElement(
            tv,
            "programme",
            {
                "start": group["start"].strftime("%Y%m%d%H%M%S %z"),
                "stop": stop.strftime("%Y%m%d%H%M%S %z"),
                "channel": GUIDE_CHANNEL_ID,
            },
        )

        if len(group["events"]) == 1:
            gp_title = group["events"][0]["title"]
        else:
            gp_title = " + ".join(item["title"] for item in group["events"])

        if LIVE_LABEL:
            gp_title = f"{gp_title} {ltr(LIVE_LABEL)}"

        ET.SubElement(gp, "title", {"lang": "ar"}).text = gp_title
        ET.SubElement(gp, "category", {"lang": "en"}).text = "Sports"

        head = []
        for item in group["events"]:
            item_channel = item.get("channel")
            item_text = (
                f"ثمانية {item_channel}" if item_channel in CHANNELS
                else "رقم القناة لم يعلن بعد"
            )
            head.append(f"{item['title']} | {item_text}\n{time_text(item)}")

        ET.SubElement(gp, "desc", {"lang": "ar"}).text = (
            "\n\n".join(head)
            + f"\n\nمباريات اليوم:\n{day_summary(group['start'].date())}"
        )

    for event in events:
        stop = event["start"] + timedelta(hours=3)
        channel = event.get("channel")

        if channel in CHANNELS:
            channel_id = f"Thmanyah{channel}.sa"
            real_by_id[channel_id].append((event["start"], stop))
            p = ET.SubElement(
                tv,
                "programme",
                {
                    "start": event["start"].strftime("%Y%m%d%H%M%S %z"),
                    "stop": stop.strftime("%Y%m%d%H%M%S %z"),
                    "channel": channel_id,
                },
            )
            title = event["title"]
            if LIVE_LABEL:
                title = f"{title} {ltr(LIVE_LABEL)}"
            ET.SubElement(p, "title", {"lang": "ar"}).text = title
            ET.SubElement(p, "category", {"lang": "en"}).text = "Sports"
            ET.SubElement(p, "desc", {"lang": "ar"}).text = (
                f"القناة: ثمانية {channel}\n"
                f"موعد المباراة: {source_time_text(event)}"
            )

    unconfirmed_events = [
        event for event in events
        if event.get("channel") not in CHANNELS
    ]

    if UNCONFIRMED_MODE == "placeholder":
        pending = []
        for event in sorted(unconfirmed_events, key=lambda e: e["start"]):
            start = event["start"]
            stop = start + timedelta(hours=3)
            if pending and start <= pending[-1]["stop"]:
                pending[-1]["stop"] = max(pending[-1]["stop"], stop)
                pending[-1]["events"].append(event)
            else:
                pending.append({"start": start, "stop": stop, "events": [event]})

        for number in CHANNELS:
            channel_id = f"Thmanyah{number}.sa"
            busy = sorted(real_by_id[channel_id])

            for block in pending:
                free = [(block["start"], block["stop"])]
                for b_start, b_stop in busy:
                    remaining = []
                    for f_start, f_stop in free:
                        if b_stop <= f_start or b_start >= f_stop:
                            remaining.append((f_start, f_stop))
                            continue
                        if f_start < b_start:
                            remaining.append((f_start, b_start))
                        if b_stop < f_stop:
                            remaining.append((b_stop, f_stop))
                    free = remaining

                for f_start, f_stop in free:
                    if f_stop <= f_start:
                        continue

                    lines = [
                        f"{item['title']} — {source_time_text(item)}"
                        for item in block["events"]
                    ]
                    p = ET.SubElement(
                        tv,
                        "programme",
                        {
                            "start": f_start.strftime("%Y%m%d%H%M%S %z"),
                            "stop": f_stop.strftime("%Y%m%d%H%M%S %z"),
                            "channel": channel_id,
                        },
                    )
                    if len(block["events"]) == 1:
                        title = f"مباراة محتملة: {block['events'][0]['title']}"
                    else:
                        title = "مباريات محتملة (القناة لم تُعلن)"
                    ET.SubElement(p, "title", {"lang": "ar"}).text = title
                    ET.SubElement(p, "category", {"lang": "en"}).text = "Sports"
                    ET.SubElement(p, "desc", {"lang": "ar"}).text = (
                        "لم يُعلن رقم القناة بعد. قد تُذاع على ثمانية 1 أو 2 أو 3.\n\n"
                        + "\n".join(lines)
                    )

            real_by_id[channel_id].extend(
                (block["start"], block["stop"]) for block in pending
            )

    window_start = NOW.astimezone(TZ).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    window_end = window_start + timedelta(days=KEEP_DAYS_FORWARD + 1)

    upcoming_by_channel = {GUIDE_CHANNEL_ID: sorted(events, key=lambda e: e["start"])}
    for number in CHANNELS:
        upcoming_by_channel[f"Thmanyah{number}.sa"] = sorted(
            (e for e in events if e.get("channel") == number),
            key=lambda e: e["start"],
        )

    def next_match_for(channel_id, moment):
        for item in upcoming_by_channel.get(channel_id, []):
            if item["start"] > moment:
                return item
        return None

    def countdown_title(item, moment):
        # عد تنازلي مطلق: المدة المتبقية حتى بداية المباراة، لا يتأثر بالمنطقة الزمنية
        #
        # الوحدات مكتوبة بالكلمة الكاملة لا بحرف واحد. "19 س و30 د" على
        # الشاشة قُرئت ثلاث قراءات مختلفة — 19 دقيقة، 30 دقيقة، 30 ساعة
        # و19 دقيقة — لأن الحرف المفرد لا يبقى ملاصقًا لرقمه بجانب أسماء
        # لاتينية. countdown_label يكتبها كاملة فلا تحتمل إلا قراءة واحدة،
        # ويتكفل أيضًا بحالة "أقل من دقيقة" بدل "0 د".
        minutes = max(int((item["start"] - moment).total_seconds() // 60), 0)
        left = countdown_label(minutes)

        # لا نعرض توقيت المصدر (الرياض) هنا، فقط اسم المباراة + العد التنازلي
        return f"{item['title']} · بعد {left}"

    def add_hourly_filler(channel_id, gap_start, gap_stop):
        cursor = gap_start
        while cursor < gap_stop:
            ahead = next_match_for(channel_id, cursor)
            near = ahead and (ahead["start"] - cursor) <= timedelta(hours=3)
            step = timedelta(minutes=30) if near else timedelta(hours=1)
            stop = min(cursor + step, gap_stop)
            if ahead and cursor < ahead["start"] < stop:
                stop = ahead["start"]
            p = ET.SubElement(
                tv,
                "programme",
                {
                    "start": cursor.strftime("%Y%m%d%H%M%S %z"),
                    "stop": stop.strftime("%Y%m%d%H%M%S %z"),
                    "channel": channel_id,
                },
            )

            upcoming = next_match_for(channel_id, cursor)

            if channel_id == GUIDE_CHANNEL_ID:
                if upcoming:
                    ET.SubElement(p, "title", {"lang": "ar"}).text = countdown_title(
                        upcoming, cursor
                    )
                else:
                    ET.SubElement(p, "title", {"lang": "ar"}).text = (
                        "لا توجد مباراة مجدولة"
                    )
                ET.SubElement(p, "category", {"lang": "en"}).text = "Sports"

                body = day_summary(cursor.date())
                if upcoming:
                    body = (
                        f"المباراة القادمة: {upcoming['title']}\n"
                        f"{time_text(upcoming)}\n\n"
                        f"مباريات اليوم:\n{body}"
                    )
                ET.SubElement(p, "desc", {"lang": "ar"}).text = body
            else:
                pending_now = [
                    item for item in unconfirmed_events
                    if item["start"] < stop
                    and item["start"] + timedelta(hours=3) > cursor
                ] if UNCONFIRMED_MODE == "hint" else []

                if pending_now:
                    ET.SubElement(p, "title", {"lang": "ar"}).text = (
                        "مباراة لم تُعلن قناتها بعد"
                    )
                    ET.SubElement(p, "category", {"lang": "en"}).text = "Sports"
                    ET.SubElement(p, "desc", {"lang": "ar"}).text = (
                        "هناك مباراة جارية على شبكة ثمانية لم يُعلن رقم قناتها بعد.\n"
                        "التفاصيل الكاملة في قناة «ثمانية | Guide».\n\n"
                        + "\n".join(
                            f"{item['title']} — {source_time_text(item)}"
                            for item in pending_now
                        )
                    )
                elif upcoming:
                    ET.SubElement(p, "title", {"lang": "ar"}).text = countdown_title(
                        upcoming, cursor
                    )
                    ET.SubElement(p, "category", {"lang": "en"}).text = "Sports"
                    ET.SubElement(p, "desc", {"lang": "ar"}).text = (
                        f"المباراة القادمة على ثمانية {upcoming['channel']}: "
                        f"{upcoming['title']}\n"
                        f"{source_time_text(upcoming)}"
                    )
                else:
                    ET.SubElement(p, "title", {"lang": "ar"}).text = (
                        "لا توجد مباراة مجدولة"
                    )
                    ET.SubElement(p, "category", {"lang": "en"}).text = "Sports"
                    ET.SubElement(p, "desc", {"lang": "ar"}).text = (
                        "لا توجد مباراة مجدولة على هذه القناة."
                    )

            cursor = stop

    for channel_id, intervals in real_by_id.items():
        clean_intervals = []

        for s, e in sorted(intervals):
            s = max(s, window_start)
            e = min(e, window_end)
            if e > s:
                clean_intervals.append((s, e))

        merged_intervals = []
        for s, e in clean_intervals:
            if not merged_intervals or s > merged_intervals[-1][1]:
                merged_intervals.append([s, e])
            else:
                merged_intervals[-1][1] = max(merged_intervals[-1][1], e)

        cursor = window_start
        for s, e in merged_intervals:
            if s > cursor:
                add_hourly_filler(channel_id, cursor, s)
            cursor = max(cursor, e)

        if cursor < window_end:
            add_hourly_filler(channel_id, cursor, window_end)

    ET.indent(tv, space="  ")
    ET.ElementTree(tv).write(OUT, encoding="utf-8", xml_declaration=True)

    root = ET.parse(OUT).getroot()
    channel_ids = [c.get("id") for c in root.findall("channel")]
    expected_ids = {
        "Thmanyah1.sa",
        "Thmanyah2.sa",
        "Thmanyah3.sa",
        GUIDE_CHANNEL_ID,
    }

    if set(channel_ids) != expected_ids or len(channel_ids) != 4:
        raise RuntimeError(
            "Thmanyah XML validation failed; expected exactly 4 channels, got: "
            + ", ".join(channel_ids)
        )

    now_check = NOW.astimezone(TZ)
    required = {channel_id: False for channel_id in expected_ids}

    for programme in root.findall("programme"):
        channel_id = programme.get("channel") or ""
        if channel_id not in required:
            continue

        try:
            s = datetime.strptime(
                (programme.get("start") or "")[:14],
                "%Y%m%d%H%M%S",
            ).replace(tzinfo=TZ)
            e = datetime.strptime(
                (programme.get("stop") or "")[:14],
                "%Y%m%d%H%M%S",
            ).replace(tzinfo=TZ)
        except Exception:
            continue

        if s <= now_check < e:
            required[channel_id] = True

    log(
        "THMANYAH CURRENT COVERAGE | "
        + ", ".join(
            f"{key}:{'YES' if ok else 'NO'}"
            for key, ok in sorted(required.items())
        )
    )

    missing = [key for key, ok in required.items() if not ok]
    if missing:
        raise RuntimeError(
            "Thmanyah XML validation failed; missing current coverage: "
            + ", ".join(missing)
        )

    log(
        "THMANYAH GUIDE DAYS | "
        + ", ".join(
            f"{day}:{len(items)}"
            for day, items in sorted(by_day.items())
        )
    )



def dedupe_fixture_day(events):
    out = []
    index = {}
    for event in sorted(events, key=lambda e: e["start"]):
        sig = fixture_signature(event.get("title", ""))
        fixture_key = tuple(sorted(sig)) if sig else norm(event.get("title", "")).casefold()
        key = (event["start"].date(), fixture_key)

        if key not in index and sig:
            for existing_key, position in index.items():
                if existing_key[0] != event["start"].date():
                    continue
                other = fixture_signature(out[position].get("title", ""))
                if fuzzy_same_fixture(sig, other, threshold=0.8):
                    key = existing_key
                    break

        if key not in index:
            index[key] = len(out)
            out.append(dict(event))
            continue
        old = out[index[key]]
        if event.get("confirmed") and event.get("channel") in CHANNELS and not (old.get("confirmed") and old.get("channel") in CHANNELS):
            old["channel"] = event.get("channel")
            old["confirmed"] = True
            old["source"] = event.get("source", old.get("source"))
    return out

def inject_verified_fallback_fixtures(events):
    verified = []
    existing_keys = {
        (e["start"].date(), fixture_signature(e.get("title", "")))
        for e in events
    }
    for event in verified:
        key = (event["start"].date(), fixture_signature(event["title"]))
        if key not in existing_keys and in_window(event["start"]):
            events.append(event)
            existing_keys.add(key)
            log(
                "VERIFIED FALLBACK FIXTURE | "
                f"{event['start']:%Y-%m-%d %H:%M} | {event['title']} | "
                f"THMANYAH {event['channel']}"
            )
    return dedupe(events)


def main():
    log(f"SCRIPT VERSION | {SCRIPT_VERSION}")
    log(f"CONFIG | unconfirmed={UNCONFIRMED_MODE} | lookahead={EXTRA_LOOKAHEAD_DAYS} days")
    log("THMANYAH | GOAL/KOOORA KICKOFF | CHANNEL-ONLY CONFIRMATIONS | FIXTURE-DAY DEDUPE")
    existing = read_existing()
    log(f"Existing REAL Thmanyah programmes kept: {len(existing)}")

    daily_urls = (
        discover_daily_articles(GOAL_HOME, "Goal")
        + discover_daily_articles(KOOORA_HOME, "Kooora")
    )
    daily_urls = list(dict.fromkeys(daily_urls))

    daily = []
    for url in daily_urls:
        found = parse_daily_article(url)
        if found:
            log(f"Daily Thmanyah fixtures from {url}: {len(found)}")
            daily.extend(found)

    daily = dedupe(daily)

    extra_rows = collect_extra_source_rows()
    confirmations_extra = rows_to_confirmations(extra_rows)

    covered_days = {event["start"].date() for event in daily}
    fallback_added = 0
    for row in extra_rows:
        if row["start"].date() in covered_days:
            continue
        if not in_window(row["start"]):
            continue
        daily.append({
            "channel": row.get("channel"),
            "start": row["start"],
            "title": row["title"],
            "source": f"{row.get('label', 'extra')} fallback: {row.get('source', '')}",
            "confirmed": row.get("channel") in CHANNELS,
        })
        fallback_added += 1

    if fallback_added:
        log(f"Fixtures added from extra sources (days missing in Goal/Kooora): {fallback_added}")

    daily = dedupe(daily)
    daily = inject_verified_fallback_fixtures(daily)

    confirmations_365 = collect_numbered_365()
    if ENABLE_TELEGRAM_OCR:
        confirmations_telegram, _ignored_direct_events = collect_radarkora_confirmations(daily)
    else:
        confirmations_telegram = []
        log("Telegram OCR disabled by config")

    for confirmation in confirmations_365:
        confirmation.setdefault("label", "365scores.com")
    for confirmation in confirmations_telegram:
        confirmation.setdefault("label", "matches_today2")

    confirmations = confirmations_365 + confirmations_telegram + confirmations_extra

    log(
        "Thmanyah numbered confirmations total: "
        f"{len(confirmations)} "
        f"(365Scores={len(confirmations_365)}, "
        f"matches_today2 OCR={len(confirmations_telegram)}, "
        f"extra sources={len(confirmations_extra)})"
    )

    resolved = apply_confirmations(daily, confirmations)
    resolved = dedupe_fixture_day(resolved)
    fresh = assign_unconfirmed(resolved)
    fresh = dedupe_fixture_day(fresh)

    fresh = [
        event
        for event in fresh
        if in_window(event["start"])
    ]

    log(f"Thmanyah newly resolved programmes: {len(fresh)}")

    for event in fresh:
        if event.get("channel") in CHANNELS:
            log(
                f"  THMANYAH {event['channel']} [CONFIRMED] | "
                f"{event['start']:%Y-%m-%d %H:%M} | "
                f"{event['title']}"
            )
        else:
            log(
                f"  THMANYAH GUIDE [CHANNEL UNKNOWN] | "
                f"{event['start']:%Y-%m-%d %H:%M} | "
                f"{event['title']}"
            )

    merged = merge_existing(existing, fresh)
    log(f"Thmanyah total REAL programmes after merge: {len(merged)}")

    if not fresh and existing:
        warn(
            "No fresh Thmanyah fixtures; rebuilding XML from preserved real events"
        )

    write_xml(merged)
    log(f"Written: {OUT}")

if __name__ == "__main__":
    main()
