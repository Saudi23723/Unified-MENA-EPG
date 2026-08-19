#!/usr/bin/env python3
import html
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

TZ = ZoneInfo("Asia/Riyadh")
NOW = datetime.now(TZ)
OUT = Path("thmanyah_epg.xml")

GOAL_HOME = "https://www.goal.com/ar"
KOOORA_HOME = "https://www.kooora.com/"
SCORES365_HOME = "https://www.365scores.com/ar/news/magazine/"
YALLAKORA_HOME = "https://www.yallakora.com/"
FILGOAL_HOME = "https://www.filgoal.com/"
BTOLAT_HOME = "https://www.btolat.com/"

THMANYAH_LOGO = "https://upload.wikimedia.org/wikipedia/commons/e/e9/Thmanyah_Logo.svg"

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

HOUR_ONLY_RE = re.compile(
    r"(?<!\d)(1[0-2]|0?[1-9])\s*(?:مساءً|مساء|صباحًا|صباحا|صباح|pm|am)\b",
    re.I,
)

def extract_time(text):
    """
    Return (hour, minute) in 24-hour clock.
    Accepts:
      19:30
      7:30 مساء
      9 مساء
      9 PM
    """
    text = norm(text)
    low = text.casefold()

    m = TIME_RE.search(text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))

        # Convert only when the matched hour is clearly in 12-hour range.
        local = text[max(0, m.start() - 20):min(len(text), m.end() + 25)].casefold()

        if 1 <= hour <= 11 and (
            "مساء" in local or "pm" in local
        ):
            hour += 12
        elif hour == 12 and (
            "صباح" in local or "am" in local
        ):
            hour = 0

        return hour, minute

    m = HOUR_ONLY_RE.search(text)
    if not m:
        return None

    hour = int(m.group(1))
    minute = 0
    token = m.group(0).casefold()

    if 1 <= hour <= 11 and (
        "مساء" in token or "pm" in token
    ):
        hour += 12
    elif hour == 12 and (
        "صباح" in token or "am" in token
    ):
        hour = 0

    return hour, minute
THMANYAH_NUMBER_RE = re.compile(
    r"(?:قناة\s*)?(?:ال)?(?:ثمانية|thmanyah)"
    r"\s*(?:sports?\s*)?(?:hd\s*)?"
    r"[.\-:]?\s*([123])\b",
    re.I,
)
THMANYAH_ANY_RE = re.compile(r"(?:ثمانية|thmanyah)", re.I)
MATCH_RE = re.compile(
    r"(.{2,100}?)\s*(?:🆚|⚔️|⚔|vs\.?|v\.?|ضد|[-–—])\s*(.{2,100})",
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
    response = requests.get(url, headers=HEADERS, timeout=15)
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

def make_dt(day, hour, minute):
    return datetime(
        day.year, day.month, day.day,
        int(hour), int(minute),
        tzinfo=TZ,
    )

def clean_team(value):
    value = norm(value)
    value = re.sub(r"^(?:⚽|🏆|📺|⏰|•|\||✅|🔥)+\s*", "", value)
    return value.strip(" |:-")

def fixture_from_text(text):
    match = MATCH_RE.search(norm(text))
    if not match:
        return None
    first = clean_team(match.group(1))
    second = clean_team(match.group(2))
    if not first or not second or len(first) > 80 or len(second) > 80:
        return None
    return f"{first} - {second}"

def normalize_team_name(value):
    value = norm(value).casefold()
    value = re.sub(r"[^\w\u0600-\u06ff ]+", " ", value)
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
    channel = event.get("channel")
    channel_key = int(channel) if channel in CHANNELS else 0
    return (
        channel_key,
        event["start"].strftime("%Y%m%d%H%M"),
        norm(event["title"]).casefold(),
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

def discover_daily_articles(home_url, label):
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
        if "جدول مباريات اليوم" not in combined:
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

def parse_daily_article(url):
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
    except Exception as exc:
        warn(f"Daily schedule failed {url}: {exc}")
        return []

    day = article_date(soup)
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

        time_value = extract_time(joined)
        if not time_value:
            continue

        title = None
        for cell in cells:
            candidate = fixture_from_text(cell)
            if candidate:
                title = candidate
                break

        if not title:
            continue

        channel_match = THMANYAH_NUMBER_RE.search(joined)
        channel = int(channel_match.group(1)) if channel_match else None

        events.append({
            "channel": channel,
            "start": make_dt(day, time_value[0], time_value[1]),
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
            time_value = extract_time(joined)

            title = None
            for candidate in block:
                parsed = fixture_from_text(candidate)
                if parsed:
                    title = parsed
                    break

            if not time_value or not title:
                continue

            channel_match = THMANYAH_NUMBER_RE.search(joined)
            channel = int(channel_match.group(1)) if channel_match else None

            events.append({
                "channel": channel,
                "start": make_dt(day, time_value[0], time_value[1]),
                "title": title,
                "source": url,
                "confirmed": channel in CHANNELS,
            })

    return dedupe(events)


def discover_source_articles(home_url, label, limit=30):
    """
    Find likely schedule/broadcast articles from a site's public homepage.

    We keep this intentionally conservative:
      - article text/URL must look like a daily matches or broadcast page
      - no OCR
      - no guessed channel number
    """
    try:
        soup = BeautifulSoup(fetch(home_url), "html.parser")
    except Exception as exc:
        warn(f"{label} discovery failed: {exc}")
        return []

    urls = []
    seen = set()

    keywords = (
        "مباريات اليوم",
        "مواعيد مباريات",
        "القنوات الناقلة",
        "جدول مباريات",
        "ثمانية",
        "thmanyah",
    )

    for anchor in soup.find_all("a", href=True):
        text = norm(anchor.get_text(" ", strip=True))
        href = anchor.get("href", "")
        combined = f"{text} {href}".casefold()

        if not any(keyword.casefold() in combined for keyword in keywords):
            continue

        url = urljoin(home_url, href).split("#", 1)[0]

        if not url.startswith(("http://", "https://")):
            continue
        if url in seen:
            continue

        seen.add(url)
        urls.append(url)

    log(f"{label} candidate articles discovered: {len(urls)}")
    return urls[:limit]


def article_text_lines(soup):
    return [
        norm(line)
        for line in soup.get_text("\n", strip=True).splitlines()
        if norm(line)
    ]


def parse_text_source_article(url, label):
    """
    Parse text-only sports articles from:
      - 365Scores
      - YallaKora
      - FilGoal
      - Btolat

    A numbered confirmation is accepted only when the LOCAL text block
    contains:
      fixture + usable time + explicit Thmanyah 1/2/3.

    This prevents picking a channel number from an unrelated frequency table
    elsewhere on the same page.
    """
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
    except Exception as exc:
        warn(f"{label} article failed: {url} | {exc}")
        return []

    page_day = article_date(soup)
    lines = article_text_lines(soup)
    events = []

    for index, line in enumerate(lines):
        # Only inspect local neighborhoods that explicitly mention Thmanyah.
        if not THMANYAH_ANY_RE.search(line):
            continue

        block_lines = lines[max(0, index - 3):min(len(lines), index + 4)]
        block = " | ".join(block_lines)

        channel_match = THMANYAH_NUMBER_RE.search(block)
        if not channel_match:
            continue

        channel = int(channel_match.group(1))
        if channel not in CHANNELS:
            continue

        time_value = extract_time(block)
        if not time_value:
            continue

        title = None

        # Prefer a fixture in the same line, then nearby lines.
        for candidate in [line] + block_lines:
            parsed = fixture_from_text(candidate)
            if parsed:
                title = parsed
                break

        if not title:
            continue

        day = parse_date(block, page_day) or page_day
        start = make_dt(day, time_value[0], time_value[1])

        if not in_window(start):
            continue

        events.append({
            "channel": channel,
            "start": start,
            "title": title,
            "source": f"{label}: {url}",
            "confirmed": True,
        })

    events = dedupe(events)

    if events:
        log(f"{label} numbered fixtures from {url}: {len(events)}")

    return events


def collect_text_confirmations():
    """
    Text-only channel confirmations.

    Priority is not based on site order.  If two sources disagree on the
    channel number for the same fixture, apply_confirmations() leaves it
    unnumbered, so it stays on Thmanyah | Guide.
    """
    source_specs = (
        (SCORES365_HOME, "365Scores", 25),
        (YALLAKORA_HOME, "YallaKora", 25),
        (FILGOAL_HOME, "FilGoal", 25),
        (BTOLAT_HOME, "Btolat", 25),
    )

    all_events = []

    for home_url, label, limit in source_specs:
        urls = discover_source_articles(
            home_url,
            label,
            limit=limit,
        )

        # Also parse the landing page itself because some sites put today's
        # matches directly there.
        candidate_urls = [home_url] + urls
        candidate_urls = list(dict.fromkeys(candidate_urls))

        source_events = []

        for url in candidate_urls:
            source_events.extend(
                parse_text_source_article(
                    url,
                    label,
                )
            )

        source_events = dedupe(source_events)

        log(
            f"{label} total numbered confirmations: "
            f"{len(source_events)}"
        )

        all_events.extend(source_events)

    all_events = dedupe(all_events)

    log(
        "TEXT SOURCES numbered confirmations total: "
        f"{len(all_events)}"
    )

    return all_events


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

        # If Goal/Kooora daily table itself explicitly gave 1/2/3,
        # keep it as a direct confirmation.
        if current.get("channel") in CHANNELS:
            current["confirmed"] = True
            result.append(current)
            continue

        signature = fixture_signature(current["title"])
        candidates = by_signature.get(signature, []) if signature else []

        candidates = [
            candidate
            for candidate in candidates
            if candidate["start"].date() == current["start"].date()
            and abs(
                (candidate["start"] - current["start"]).total_seconds()
            ) <= 2 * 60 * 60
        ]

        channels = sorted({
            int(candidate["channel"])
            for candidate in candidates
            if candidate.get("channel") in CHANNELS
        })

        if len(channels) == 1:
            current["channel"] = channels[0]
            current["confirmed"] = True

            source_names = sorted({
                candidate["source"].split(":", 1)[0]
                for candidate in candidates
                if candidate.get("channel") == channels[0]
            })

            current["source"] = (
                f"{current['source']} + confirmed by "
                + ", ".join(source_names)
            )

        elif len(channels) > 1:
            # Important: conflict = Guide, never guess.
            current["channel"] = None
            current["confirmed"] = False

            warn(
                "THMANYAH CHANNEL CONFLICT -> GUIDE | "
                f"{current['start']:%Y-%m-%d %H:%M} | "
                f"{current['title']} | reported channels={channels}"
            )

        result.append(current)

    # Keep text-source fixtures that a daily page may have missed entirely.
    # But conflicting duplicate confirmations will be resolved below.
    grouped_confirmations = defaultdict(list)

    for event in confirmations:
        grouped_confirmations[fixture_key(event)].append(event)

    for key, items in grouped_confirmations.items():
        channels = sorted({
            int(item["channel"])
            for item in items
            if item.get("channel") in CHANNELS
        })

        if len(channels) == 1:
            best = dict(items[0])
            best["channel"] = channels[0]
            best["confirmed"] = True
            result.append(best)

        elif len(channels) > 1:
            # Same fixture/time has conflicting source numbers.
            best = dict(items[0])
            best["channel"] = None
            best["confirmed"] = False
            best["source"] = "conflicting text sources"
            result.append(best)

    return dedupe([
        event
        for event in result
        if in_window(event["start"])
    ])


def read_existing():
    if not OUT.exists():
        return []

    try:
        root = ET.parse(OUT).getroot()
    except Exception as exc:
        warn(f"Existing Thmanyah XML unreadable: {exc}")
        return []

    events = []

    for programme in root.findall("programme"):
        channel_id = programme.get("channel") or ""

        if channel_id == GUIDE_CHANNEL_ID:
            channel = None
        else:
            channel_match = re.fullmatch(
                r"Thmanyah([123])\.sa",
                channel_id,
                re.I,
            )
            if not channel_match:
                continue
            channel = int(channel_match.group(1))

        raw_start = programme.get("start") or ""

        try:
            start = datetime.strptime(
                raw_start[:14],
                "%Y%m%d%H%M%S",
            ).replace(tzinfo=TZ)
        except Exception:
            continue

        if not in_window(start):
            continue

        title_node = programme.find("title")
        title = norm(title_node.text) if title_node is not None else ""

        if not title:
            continue

        if title in {
            "لا توجد مباريات مجدولة",
            "لا توجد مباراة حالياً",
            "لا توجد مباراة معلنة",
            "No information",
            "No scheduled matches",
        }:
            continue

        events.append({
            "channel": channel,
            "start": start,
            "title": title,
            "source": "existing XML",
            "confirmed": channel in CHANNELS,
        })

    return dedupe(events)


def merge_existing(existing, fresh):
    merged = {}

    for event in existing:
        merged[fixture_key(event)] = event

    for event in fresh:
        key = fixture_key(event)
        old = merged.get(key)

        if old is None:
            merged[key] = event
            continue

        old_numbered = old.get("channel") in CHANNELS
        new_numbered = event.get("channel") in CHANNELS

        if new_numbered:
            merged[key] = event
        elif not old_numbered:
            merged[key] = event

    return dedupe([
        event
        for event in merged.values()
        if in_window(event["start"])
    ])


def write_xml(events):
    """
    XMLTV for:
      - Thmanyah 1
      - Thmanyah 2
      - Thmanyah 3
      - Thmanyah | Guide

    Important Guide behavior:
      1) The Guide NEVER contains overlapping programmes.
      2) The selected Guide programme description always lists ALL Thmanyah
         matches for that day with their kickoff times.
      3) When a match kickoff arrives, that match title appears on the Guide
         timeline bar.
      4) If the exact channel 1/2/3 is confirmed, the match is also written
         to that numbered channel.
      5) If the exact channel is unknown, it stays Guide-only. No guessing.
    """
    tv = ET.Element(
        "tv",
        {"generator-info-name": "Thmanyah Sports Verified EPG"},
    )

    # -------- Channel definitions --------
    for number in CHANNELS:
        channel_id = f"Thmanyah{number}.sa"
        channel = ET.SubElement(tv, "channel", {"id": channel_id})

        ET.SubElement(
            channel,
            "display-name",
            {"lang": "en"},
        ).text = f"Thmanyah {number}"

        ET.SubElement(
            channel,
            "display-name",
            {"lang": "ar"},
        ).text = f"ثمانية {number}"

        ET.SubElement(
            channel,
            "icon",
            {"src": THMANYAH_LOGO},
        )

    guide = ET.SubElement(
        tv,
        "channel",
        {"id": GUIDE_CHANNEL_ID},
    )

    ET.SubElement(
        guide,
        "display-name",
        {"lang": "en"},
    ).text = "Thmanyah | Guide"

    ET.SubElement(
        guide,
        "display-name",
        {"lang": "ar"},
    ).text = "ثمانية | Guide"

    ET.SubElement(
        guide,
        "icon",
        {"src": THMANYAH_LOGO},
    )

    window_start = NOW.astimezone(TZ).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    window_end = window_start + timedelta(days=KEEP_DAYS_FORWARD + 1)

    # -------- Numbered channels 1/2/3 --------
    numbered_intervals = {
        f"Thmanyah{number}.sa": []
        for number in CHANNELS
    }

    # Every Thmanyah fixture goes into the Guide's daily list.
    # Only confirmed 1/2/3 fixtures also go into a real numbered channel.
    guide_events_by_day = {}

    for event in sorted(events, key=lambda x: (x["start"], x["title"])):
        if not in_window(event["start"]):
            continue

        day_key = event["start"].date()
        guide_events_by_day.setdefault(day_key, []).append(event)

        channel_number = event.get("channel")

        if channel_number not in CHANNELS:
            continue

        channel_id = f"Thmanyah{channel_number}.sa"
        stop = event["start"] + timedelta(hours=3)

        numbered_intervals[channel_id].append(
            (event["start"], stop)
        )

        programme = ET.SubElement(
            tv,
            "programme",
            {
                "start": event["start"].strftime("%Y%m%d%H%M%S %z"),
                "stop": stop.strftime("%Y%m%d%H%M%S %z"),
                "channel": channel_id,
            },
        )

        ET.SubElement(
            programme,
            "title",
            {"lang": "ar"},
        ).text = event["title"]

        ET.SubElement(
            programme,
            "category",
            {"lang": "en"},
        ).text = "Sports"

        ET.SubElement(
            programme,
            "desc",
            {"lang": "ar"},
        ).text = (
            f"القناة المؤكدة: ثمانية {channel_number}\n"
            f"الموعد: {event['start']:%H:%M} بتوقيت مكة\n"
            f"المصدر: {event['source']}"
        )

    def add_numbered_filler(channel_id, gap_start, gap_stop):
        cursor = gap_start

        while cursor < gap_stop:
            stop = min(cursor + timedelta(hours=1), gap_stop)

            p = ET.SubElement(
                tv,
                "programme",
                {
                    "start": cursor.strftime("%Y%m%d%H%M%S %z"),
                    "stop": stop.strftime("%Y%m%d%H%M%S %z"),
                    "channel": channel_id,
                },
            )

            ET.SubElement(
                p,
                "title",
                {"lang": "ar"},
            ).text = "لا توجد مباراة حالياً"

            ET.SubElement(
                p,
                "category",
                {"lang": "en"},
            ).text = "Sports"

            ET.SubElement(
                p,
                "desc",
                {"lang": "ar"},
            ).text = "لا توجد مباراة معلنة على هذه القناة حالياً."

            cursor = stop

    for channel_id, intervals in numbered_intervals.items():
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
                merged_intervals[-1][1] = max(
                    merged_intervals[-1][1],
                    e,
                )

        cursor = window_start

        for s, e in merged_intervals:
            if s > cursor:
                add_numbered_filler(
                    channel_id,
                    cursor,
                    s,
                )

            cursor = max(cursor, e)

        if cursor < window_end:
            add_numbered_filler(
                channel_id,
                cursor,
                window_end,
            )

    # -------- Guide channel --------
    def guide_day_description(day, day_events):
        if not day_events:
            return (
                f"جدول ثمانية ليوم {day:%Y-%m-%d}\n"
                "لا توجد مباريات معلنة."
            )

        lines = [
            f"جدول مباريات ثمانية - {day:%Y-%m-%d}",
            "",
        ]

        for event in sorted(day_events, key=lambda x: (x["start"], x["title"])):
            channel_number = event.get("channel")

            if channel_number in CHANNELS:
                channel_text = f"ثمانية {channel_number}"
            else:
                channel_text = "رقم القناة لم يعلن"

            lines.append(
                f"{event['start']:%H:%M} | "
                f"{event['title']} | {channel_text}"
            )

        return "\n".join(lines)

    def add_guide_programme(start, stop, title, desc):
        if stop <= start:
            return

        p = ET.SubElement(
            tv,
            "programme",
            {
                "start": start.strftime("%Y%m%d%H%M%S %z"),
                "stop": stop.strftime("%Y%m%d%H%M%S %z"),
                "channel": GUIDE_CHANNEL_ID,
            },
        )

        ET.SubElement(
            p,
            "title",
            {"lang": "ar"},
        ).text = title

        ET.SubElement(
            p,
            "category",
            {"lang": "en"},
        ).text = "Sports"

        ET.SubElement(
            p,
            "desc",
            {"lang": "ar"},
        ).text = desc

    day_cursor = window_start

    while day_cursor < window_end:
        day_start = day_cursor
        day_stop = min(
            day_start + timedelta(days=1),
            window_end,
        )
        current_day = day_start.date()

        raw_day_events = [
            event
            for event in guide_events_by_day.get(current_day, [])
            if day_start <= event["start"] < day_stop
        ]

        # Remove duplicate same fixture/time records.
        # Prefer a numbered/confirmed copy.
        unique = {}

        for event in raw_day_events:
            key = (
                event["start"].strftime("%Y%m%d%H%M"),
                norm(event["title"]).casefold(),
            )

            old = unique.get(key)

            if old is None:
                unique[key] = event
            elif (
                old.get("channel") not in CHANNELS
                and event.get("channel") in CHANNELS
            ):
                unique[key] = event

        day_events = sorted(
            unique.values(),
            key=lambda x: (x["start"], x["title"]),
        )

        desc = guide_day_description(
            current_day,
            day_events,
        )

        if not day_events:
            add_guide_programme(
                day_start,
                day_stop,
                "لا توجد مباريات مجدولة",
                desc,
            )
            day_cursor = day_stop
            continue

        # GROUP matches by exact kickoff time.
        # One XMLTV row can only show ONE programme at a time, so multiple
        # matches starting at the same minute must be combined into one Guide
        # programme instead of creating overlapping programmes.
        kickoff_groups = {}

        for event in day_events:
            kickoff_groups.setdefault(
                event["start"],
                [],
            ).append(event)

        kickoff_times = sorted(kickoff_groups)

        # Before first kickoff.
        first_start = max(
            day_start,
            kickoff_times[0],
        )

        if first_start > day_start:
            add_guide_programme(
                day_start,
                first_start,
                "مباريات ثمانية اليوم",
                desc,
            )

        # Exactly ONE Guide programme per kickoff time.
        for index, kickoff in enumerate(kickoff_times):
            group = kickoff_groups[kickoff]
            segment_start = max(kickoff, day_start)

            if index + 1 < len(kickoff_times):
                segment_stop = min(
                    kickoff_times[index + 1],
                    day_stop,
                )
            else:
                segment_stop = min(
                    kickoff + timedelta(hours=3),
                    day_stop,
                )

            if segment_stop <= segment_start:
                continue

            titles = []

            for event in group:
                channel_number = event.get("channel")

                if channel_number in CHANNELS:
                    titles.append(
                        f"{event['title']} | ثمانية {channel_number}"
                    )
                else:
                    titles.append(event["title"])

            # If more than one match starts at the exact same time,
            # show all of them in the Guide bar without overlap.
            title = " / ".join(titles)

            add_guide_programme(
                segment_start,
                segment_stop,
                title,
                desc,
            )

        # Fill AFTER the last match only after its three-hour Guide window.
        last_visible_stop = min(
            kickoff_times[-1] + timedelta(hours=3),
            day_stop,
        )

        if last_visible_stop < day_stop:
            add_guide_programme(
                last_visible_stop,
                day_stop,
                "مباريات ثمانية اليوم",
                desc,
            )

        day_cursor = day_stop

    # -------- Write and validate --------
    ET.indent(tv, space="  ")

    ET.ElementTree(tv).write(
        OUT,
        encoding="utf-8",
        xml_declaration=True,
    )

    root = ET.parse(OUT).getroot()

    channel_ids = [
        channel.get("id")
        for channel in root.findall("channel")
    ]

    expected_ids = {
        "Thmanyah1.sa",
        "Thmanyah2.sa",
        "Thmanyah3.sa",
        GUIDE_CHANNEL_ID,
    }

    if (
        set(channel_ids) != expected_ids
        or len(channel_ids) != 4
    ):
        raise RuntimeError(
            "Thmanyah XML validation failed; "
            "expected exactly 4 EPG entries, got: "
            + ", ".join(channel_ids)
        )

    # Validate no overlapping Guide programmes.
    guide_programmes = []

    for programme in root.findall("programme"):
        if programme.get("channel") != GUIDE_CHANNEL_ID:
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

        guide_programmes.append((s, e))

    guide_programmes.sort()

    for index in range(1, len(guide_programmes)):
        previous_stop = guide_programmes[index - 1][1]
        current_start = guide_programmes[index][0]

        if current_start < previous_stop:
            raise RuntimeError(
                "Guide XML validation failed: overlapping programmes detected"
            )

    now_check = NOW.astimezone(TZ)

    required = {
        "Thmanyah1.sa": False,
        "Thmanyah2.sa": False,
        "Thmanyah3.sa": False,
        GUIDE_CHANNEL_ID: False,
    }

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
            for key, ok in required.items()
        )
    )

    log(
        "THMANYAH GUIDE DAYS | "
        + ", ".join(
            f"{day}:{len(items)}"
            for day, items in sorted(guide_events_by_day.items())
        )
    )

    missing = [
        key
        for key, ok in required.items()
        if not ok
    ]

    if missing:
        raise RuntimeError(
            "Thmanyah XML validation failed; "
            "missing current coverage: "
            + ", ".join(missing)
        )

def main():
    log("THMANYAH TEXT MODE | no OCR / no Tesseract")
    existing = read_existing()

    log(
        f"Existing REAL Thmanyah programmes kept: "
        f"{len(existing)}"
    )

    daily_urls = (
        discover_daily_articles(GOAL_HOME, "Goal")
        + discover_daily_articles(KOOORA_HOME, "Kooora")
    )

    daily_urls = list(dict.fromkeys(daily_urls))

    daily = []

    for url in daily_urls:
        found = parse_daily_article(url)

        if found:
            log(
                f"Daily Thmanyah fixtures from {url}: "
                f"{len(found)}"
            )
            daily.extend(found)

    daily = dedupe(daily)

    confirmations = collect_text_confirmations()

    log(
        "Thmanyah numbered confirmations total: "
        f"{len(confirmations)} "
        "(TEXT SOURCES ONLY)"
    )

    # Exact verified 1/2/3 => numbered channel.
    # No verified number => remains None => Guide.
    fresh = apply_confirmations(
        daily,
        confirmations,
    )

    fresh = [
        event
        for event in fresh
        if in_window(event["start"])
    ]

    log(
        f"Thmanyah newly resolved programmes: "
        f"{len(fresh)}"
    )

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

    merged = merge_existing(
        existing,
        fresh,
    )

    log(
        f"Thmanyah total REAL programmes after merge: "
        f"{len(merged)}"
    )

    if not fresh and existing:
        warn(
            "No fresh Thmanyah fixtures; "
            "rebuilding XML from preserved real events"
        )

    write_xml(merged)
    log(f"Written: {OUT}")


if __name__ == "__main__":
    main()
