#!/usr/bin/env python3
"""
Alwan Sports XMLTV updater.

Source:
  Public Telegram channel: https://t.me/s/AlwanSports

Behavior:
  • Reads only Alwan Sports Telegram (web preview pages, with pagination).
  • Extracts date + teams + time + Alwan channel number.
  • Supports posts containing several fixtures.
  • Ignores Telegram placeholders and headings such as "جدول مباريات الغد".
  • Keeps existing future EPG entries if Telegram temporarily returns no useful data.
  • Never overwrites a good XML with an empty/broken one (atomic write + validation).
  • Does NOT touch any Thmanyah files or code.

Output channel ids / display-names are IDENTICAL to the previous version,
so existing TiviMate channel mappings keep working.

Dependencies:
  requests
  beautifulsoup4
"""

import html
import os
import re
import sys
import time
from datetime import datetime, timedelta, date
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET


TZ = ZoneInfo("Asia/Riyadh")
NOW = datetime.now(TZ)

OUT = Path("alwan_sports_epg.xml")
CHANNEL_SLUG = "AlwanSports"
TELEGRAM_URL = f"https://t.me/s/{CHANNEL_SLUG}"

KEEP_DAYS_BACK = 1
KEEP_DAYS_FORWARD = 7

# How many Telegram preview pages to walk back through.
# Page 1 = newest ~20 posts. Each extra page goes ~20 posts further back.
TELEGRAM_PAGES = 3

# Abort (leave the existing XML untouched) if Telegram gives us fewer
# than this many posts. Protects against 429 / preview-disabled / landing page.
MIN_POSTS_REQUIRED = 3

# Default match length in minutes. Automatically shortened if another match
# starts sooner on the same channel.
MATCH_MINUTES = 110

# What to put in the empty slots between matches.
#
#   "next_match" : one block per gap, naming the next match and its kickoff
#                  time, e.g. "التالي 21:00 — الهلال - النصر".
#                  Falls back to "لا توجد مباراة مجدولة" when nothing is
#                  scheduled ahead on that channel.
#   "simple"     : one block per gap, always "لا توجد مباراة مجدولة".
#   "off"        : no filler at all; TiviMate shows its own "No information".
#
# NOTE: a live countdown ("2h 15m left") is impossible in XMLTV. The guide is
# a static file the player caches, so any countdown would freeze at the moment
# the file was generated. The kickoff time below never goes stale.
FILLER_MODE = "next_match"

# Filler blocks are cut at midnight so the guide reads cleanly day by day.
SPLIT_FILLER_AT_MIDNIGHT = True

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "ar,en;q=0.8",
}

# Arabic-Indic and Persian digits -> ASCII digits.
DIGIT_MAP = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)

TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)")

# Suffixes that mean PM / AM when they appear right after the time.
# The lookahead stops "م" from matching the first letter of words like "مباراة".
PM_SUFFIX_RE = re.compile(
    r"^\s*[\-–—,،]?\s*"
    r"(?:pm|p\.m\.?|مساءً|مساءاً|مساءا|مساء|ليلاً|ليلا|م)"
    r"(?![\u0621-\u064A])",
    re.I,
)

AM_SUFFIX_RE = re.compile(
    r"^\s*[\-–—,،]?\s*"
    r"(?:am|a\.m\.?|صباحاً|صباحا|صباح|فجراً|فجرا|ص)"
    r"(?![\u0621-\u064A])",
    re.I,
)

# Examples supported:
# ألوان 1 / الوان 2 / ALWAN 3 / Alwan Sports 4 / ألوان سبورت 5 / ALWAN SPORT HD 6
ALWAN_RE = re.compile(
    r"(?:ألوان|الوان|ألون|ALWAN)"
    r"(?:\s*(?:SPORTS?|سبورتس|سبورت|الرياضية|رياضة))?"
    r"(?:\s*(?:HD|SD|4K|UHD|RAW))?"
    r"\s*[.\-:#]?\s*"
    r"(10|[1-9])(?!\d)",
    re.I,
)

# Strong separators. "\bVS?\b\.?" needs the word boundary, otherwise the bare
# "V" alternative matches the v inside names like Liverpool and splits it.
SEPARATOR = r"(?:🆚|⚔️|⚔|\bVS?\b\.?|ضد|×|✖️|✖)"

MATCH_LINE_RE = re.compile(
    rf"(.{{2,100}}?)\s*{SEPARATOR}\s*(.{{2,100}})",
    re.I,
)

# Dash separator is far more ambiguous ("12-01-2026", "Al-Ahli"), so it needs
# real whitespace on both sides and is only tried after the strong separators.
MATCH_LINE_DASH_RE = re.compile(r"(.{2,100}?)\s+[-–—]\s+(.{2,100})")

BARE_SEPARATORS = {
    "VS",
    "VS.",
    "V",
    "V.",
    "🆚",
    "⚔",
    "⚔️",
    "ضد",
    "×",
    "✖",
    "✖️",
}

HAS_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)

# Words that never appear inside a "team vs team" line, but do appear in
# headings that happen to contain a dash ("الجولة 5 - الدوري السعودي").
# Only used to filter the ambiguous dash separator.
DASH_HEADING_WORDS = (
    "الجولة",
    "جولة",
    "الموسم",
    "المجموعة",
    "التعليق",
    "المعلق",
    "الاستوديو",
    "الأستوديو",
    "التغطية",
    "اشترك",
    "رابط",
    "تحميل",
    "تردد",
    "الترتيب",
)

AR_MONTHS = {
    "يناير": 1,
    "كانون الثاني": 1,
    "فبراير": 2,
    "شباط": 2,
    "مارس": 3,
    "آذار": 3,
    "اذار": 3,
    "أبريل": 4,
    "ابريل": 4,
    "نيسان": 4,
    "مايو": 5,
    "أيار": 5,
    "ايار": 5,
    "يونيو": 6,
    "حزيران": 6,
    "يوليو": 7,
    "تموز": 7,
    "أغسطس": 8,
    "اغسطس": 8,
    "آب": 8,
    "سبتمبر": 9,
    "أيلول": 9,
    "ايلول": 9,
    "أكتوبر": 10,
    "اكتوبر": 10,
    "تشرين الأول": 10,
    "تشرين الاول": 10,
    "نوفمبر": 11,
    "تشرين الثاني": 11,
    "ديسمبر": 12,
    "كانون الأول": 12,
    "كانون الاول": 12,
}

TOMORROW_WORDS = (
    "غداً",
    "غدا",
    "الغد",
    "بكرا",
    "بكرة",
    "بكره",
)

DAY_AFTER_WORDS = (
    "بعد غد",
    "بعد الغد",
    "بعد غداً",
    "بعد بكرا",
    "بعد بكرة",
)

AR_WEEKDAYS = (
    "الاثنين",
    "الثلاثاء",
    "الأربعاء",
    "الخميس",
    "الجمعة",
    "السبت",
    "الأحد",
)

# Category written on filler blocks. read_existing() accepts only "Sports",
# so filler can never be re-imported as if it were a real match.
FILLER_CATEGORY = "Filler"

FILLER_MARKERS = (
    "لا توجد مباريات مجدولة",
    "لا توجد مباراة مجدولة",
    "التالي ",
    "لا توجد مباراة معلنة",
    "لا توجد مباراة حالياً",
    "no information",
    "no scheduled matches",
    "no match currently",
)


def log(message):
    print(message, flush=True)


def warn(message):
    print(f"WARN {message}", file=sys.stderr, flush=True)


def norm(value):
    value = html.unescape(value or "")
    value = value.replace("\u200f", " ").replace("\u200e", " ")
    value = value.replace("\u200b", "").replace("\u0640", "")
    value = value.replace("\xa0", " ")
    value = value.translate(DIGIT_MAP)
    return re.sub(r"[ \t]+", " ", value).strip()


def fetch(url, attempts=3):
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=35)
            response.raise_for_status()
            return response.text

        except Exception as exc:
            last_error = exc

            if attempt < attempts:
                time.sleep(3 * attempt)

    raise last_error


def fetch_posts(pages=TELEGRAM_PAGES):
    """
    Walk back through Telegram's public preview pages.

    Page 1 shows only the newest ~20 posts, which is not always enough
    when the channel posts clips or ads after the schedule.
    """
    collected = {}
    url = TELEGRAM_URL

    for page in range(1, pages + 1):
        try:
            soup = BeautifulSoup(fetch(url), "html.parser")

        except Exception as exc:
            if page == 1:
                raise

            warn(f"Alwan Telegram page {page} failed: {exc}")
            break

        posts = soup.select(".tgme_widget_message")

        if not posts:
            break

        ids = []
        new_on_page = 0

        for post in posts:
            key = post.get("data-post") or str(id(post))

            if key not in collected:
                collected[key] = post
                new_on_page += 1

            match = re.search(r"/(\d+)\s*$", key)

            if match:
                ids.append(int(match.group(1)))

        log(f"Alwan Telegram page {page}: {len(posts)} posts ({new_on_page} new)")

        if not ids or new_on_page == 0 or page == pages:
            break

        url = f"{TELEGRAM_URL}?before={min(ids)}"

    return list(collected.values())


def in_window(dt):
    return (
        NOW - timedelta(days=KEEP_DAYS_BACK)
        <= dt
        <= NOW + timedelta(days=KEEP_DAYS_FORWARD)
    )


def telegram_post_date(post):
    tag = post.select_one("time[datetime]")

    if tag:
        raw = tag.get("datetime", "")

        try:
            return datetime.fromisoformat(
                raw.replace("Z", "+00:00")
            ).astimezone(TZ).date()

        except Exception:
            pass

    return NOW.date()


def parse_explicit_date(text, reference):
    text = norm(text)
    low = text.lower()

    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b", text)

    if m:
        day, month, year = map(int, m.groups())

        try:
            return date(year, month, day)
        except ValueError:
            pass

    months_pattern = "|".join(
        map(re.escape, sorted(AR_MONTHS, key=len, reverse=True))
    )

    m = re.search(
        rf"(?<!\d)(\d{{1,2}})\s+({months_pattern})(?:\s+(20\d{{2}}))?",
        text,
        re.I,
    )

    if m:
        day = int(m.group(1))
        month = AR_MONTHS[m.group(2)]
        year = int(m.group(3)) if m.group(3) else reference.year

        try:
            found = date(year, month, day)
        except ValueError:
            found = None

        if found:
            # A bare "12 مارس" near a year boundary should roll forward.
            if not m.group(3) and (found - reference).days < -180:
                try:
                    found = date(year + 1, month, day)
                except ValueError:
                    pass

            return found

    # Important: check "بعد غد" before "غد".
    if any(word in low for word in DAY_AFTER_WORDS):
        return reference + timedelta(days=2)

    if any(word in low for word in TOMORROW_WORDS):
        return reference + timedelta(days=1)

    if "اليوم" in low:
        return reference

    return None


def clean_team(value):
    value = norm(value)

    # Remove common emoji/labels around team names.
    value = re.sub(
        r"^(?:⚽|🏆|📺|⏰|🕘|🕗|🕖|🔴|🟢|🔵|🟡|🟣|🟠|⚪|•|\||✅|🔥|▪|▫|◾|◽|➖|👈|👉)+\s*",
        "",
        value,
    )

    value = re.sub(
        r"\s*(?:📺|⏰|🎙|🏟|القناة|الساعة|التوقيت|المعلق).*$",
        "",
        value,
        flags=re.I,
    )

    return value.strip(" |:-–—")


def _valid_team(value):
    return bool(value) and len(value) <= 70 and bool(HAS_LETTER_RE.search(value))


def fixture_from_line(line, allow_dash=True):
    """
    Turn "TEAM A vs TEAM B" into "TEAM A - TEAM B", or return None.

    allow_dash=False disables the ambiguous " - " separator. Callers use this
    to prefer real separators (🆚 / VS / ضد) whenever a post contains any.
    """
    line = norm(line)

    # Explicitly reject headings/placeholders.
    bad = (
        "please open telegram",
        "view this post",
        "جدول مباريات",
        "جدول اليوم",
        "جدول الغد",
        "أهم مباريات",
        "اهم مباريات",
        "مواعيد مباريات",
    )

    low = line.lower()

    if any(x in low for x in bad):
        return None

    match = MATCH_LINE_RE.search(line)

    if match:
        team_a = clean_team(match.group(1))
        team_b = clean_team(match.group(2))

        if _valid_team(team_a) and _valid_team(team_b):
            return f"{team_a} - {team_b}"

    if not allow_dash:
        return None

    if any(word in line for word in DASH_HEADING_WORDS):
        return None

    match = MATCH_LINE_DASH_RE.search(line)

    if match:
        team_a = clean_team(match.group(1))
        team_b = clean_team(match.group(2))

        if _valid_team(team_a) and _valid_team(team_b):
            return f"{team_a} - {team_b}"

    return None


def post_text(post):
    """
    Telegram's public page can move text between selectors.
    Prefer the text/caption nodes; only use the whole bubble as fallback.
    """
    candidates = []

    for selector in (
        ".tgme_widget_message_text",
        ".tgme_widget_message_caption",
    ):
        for node in post.select(selector):
            text = node.get_text("\n", strip=True)

            if text and text not in candidates:
                candidates.append(text)

    if not candidates:
        bubble = post.select_one(".tgme_widget_message_bubble")

        if bubble:
            candidates.append(bubble.get_text("\n", strip=True))

    return html.unescape("\n".join(candidates)).strip()


def _is_bare_separator(line):
    return norm(line).upper().strip(" .") in {
        s.strip(" .") for s in BARE_SEPARATORS
    }


def _anchor_ranges(lines):
    """
    Locate every fixture in the post as an inclusive (start, end) line range.

    Handles both:
        TEAM A VS TEAM B          -> (i, i)
    and:
        TEAM A
        VS
        TEAM B                    -> (i-1, i+1)

    Returns non-overlapping ranges in document order.
    """
    def collect(allow_dash):
        found = []

        for index, line in enumerate(lines):
            if _is_bare_separator(line):
                if index == 0 or index + 1 >= len(lines):
                    continue

                team_a = clean_team(lines[index - 1])
                team_b = clean_team(lines[index + 1])

                if _valid_team(team_a) and _valid_team(team_b):
                    found.append((index - 1, index + 1))

                continue

            if fixture_from_line(line, allow_dash=allow_dash):
                found.append((index, index))

        return found

    # A post that uses real separators anywhere should not also have its
    # headings picked up through the ambiguous " - " separator.
    candidates = collect(allow_dash=False) or collect(allow_dash=True)

    accepted = []

    for start, end in sorted(candidates, key=lambda r: (r[0], -(r[1] - r[0]))):
        if accepted and start <= accepted[-1][1]:
            continue

        accepted.append((start, end))

    return accepted


def _has_time(text):
    return TIME_RE.search(text) is not None


def split_into_fixture_blocks(text):
    """
    Cut the post into ONE non-overlapping block per fixture.

    The previous version used a fixed window (index-3 .. index+6) around every
    fixture line. Those windows overlap, so a match could pick up the kickoff
    time or channel number belonging to the match next to it.

    Posts put the metadata either after the teams:
        TEAM A VS TEAM B
        22:00
        الوان 2
    or before them:
        ⏰ 22:00
        📺 الوان 2
        TEAM A VS TEAM B

    The orientation is detected per post by looking at where the times sit,
    then each block is cut accordingly. Each block also carries a wider
    fallback region, used only when the strict block has no time or channel.

    Returns a list of (primary_block, wide_block) string pairs.
    """
    lines = [norm(x) for x in text.splitlines() if norm(x)]
    anchors = _anchor_ranges(lines)

    if not anchors:
        return []

    regions = []

    for position, (start, end) in enumerate(anchors):
        prev_end = anchors[position - 1][1] if position > 0 else -1
        next_start = anchors[position + 1][0] if position + 1 < len(anchors) else len(lines)

        regions.append(
            {
                "start": start,
                "end": end,
                "before": lines[prev_end + 1:start],
                "after": lines[end + 1:next_start],
            }
        )

    before_hits = sum(1 for r in regions if _has_time("\n".join(r["before"])))
    after_hits = sum(1 for r in regions if _has_time("\n".join(r["after"])))
    meta_before = before_hits > after_hits

    blocks = []

    for region in regions:
        body = lines[region["start"]:region["end"] + 1]

        if meta_before:
            primary = region["before"] + body
        else:
            primary = body + region["after"]

        wide = region["before"] + body + region["after"]

        blocks.append(("\n".join(primary), "\n".join(wide)))

    return blocks


def fixture_from_block(block):
    lines = [norm(x) for x in block.splitlines() if norm(x)]

    # One-line fixture first, preferring real separators over " - ".
    for allow_dash in (False, True):
        for line in lines:
            fixture = fixture_from_line(line, allow_dash=allow_dash)

            if fixture:
                return fixture

    # Then support the "VS on its own line" layout.
    for index, line in enumerate(lines):
        if not _is_bare_separator(line):
            continue

        if index > 0 and index + 1 < len(lines):
            team_a = clean_team(lines[index - 1])
            team_b = clean_team(lines[index + 1])

            if _valid_team(team_a) and _valid_team(team_b):
                return f"{team_a} - {team_b}"

    return None


def channel_from_block(block):
    match = ALWAN_RE.search(norm(block))

    if match:
        return int(match.group(1))

    return None


def time_from_block(block):
    block = norm(block)
    match = TIME_RE.search(block)

    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))

    # Look at what directly follows the time, not the whole block, so one
    # match's "مساء" cannot flip a different match's kickoff time.
    tail = block[match.end():match.end() + 16]

    is_pm = bool(PM_SUFFIX_RE.match(tail))
    is_am = bool(AM_SUFFIX_RE.match(tail))

    if not is_pm and not is_am:
        low = block.lower()
        is_pm = "pm" in low or "مساء" in low
        is_am = "am" in low or "صباح" in low

    if is_pm and 1 <= hour <= 11:
        hour += 12

    # 12 PM stays 12; 12 AM becomes 00.
    if is_am and hour == 12:
        hour = 0

    return hour, minute


def parse_post(post):
    text = post_text(post)

    if not text:
        return []

    # Hard reject Telegram placeholders.
    if "Please open Telegram to view this post" in text:
        return []

    post_day = telegram_post_date(post)
    explicit_day = parse_explicit_date(text, post_day)
    default_day = explicit_day or post_day

    events = []

    for primary, wide in split_into_fixture_blocks(text):
        block = primary

        fixture = fixture_from_block(block)
        channel = channel_from_block(block)
        time_value = time_from_block(block)

        # Only widen when the strict block is missing something.
        if channel is None or time_value is None:
            block = wide
            fixture = fixture or fixture_from_block(block)
            channel = channel if channel is not None else channel_from_block(block)
            time_value = time_value or time_from_block(block)

        # We require ALL three pieces. No guessing.
        if not fixture or channel is None or time_value is None:
            continue

        day = parse_explicit_date(block, default_day) or default_day
        hour, minute = time_value

        start = datetime(
            day.year,
            day.month,
            day.day,
            hour,
            minute,
            tzinfo=TZ,
        )

        if not in_window(start):
            continue

        events.append(
            {
                "channel": channel,
                "start": start,
                "title": fixture,
                "source": TELEGRAM_URL,
            }
        )

    return events


def event_key(event):
    return (
        int(event["channel"]),
        event["start"].strftime("%Y%m%d%H%M"),
        norm(event["title"]).casefold(),
    )


def dedupe(events):
    output = []
    seen = set()

    for event in sorted(
        events,
        key=lambda x: (x["start"], int(x["channel"]), x["title"]),
    ):
        key = event_key(event)

        if key in seen:
            continue

        seen.add(key)
        output.append(event)

    return output


# Matches the ids this script writes (Alwan3_sports_hd) and any older
# AlwanSports3 style id, so nothing is lost when upgrading.
CHANNEL_ID_RE = re.compile(r"^Alwan(?:\s|_|-)?(10|[1-9])(?:[_\-\s]|$)", re.I)
LEGACY_ID_RE = re.compile(r"AlwanSports?[_\-\s]?(10|[1-9])(?!\d)", re.I)


def channel_number_from_id(channel_id):
    for pattern in (CHANNEL_ID_RE, LEGACY_ID_RE):
        match = pattern.search(channel_id or "")

        if match:
            return int(match.group(1))

    return None


def is_filler_title(title):
    low = (title or "").casefold()
    return any(marker.casefold() in low for marker in FILLER_MARKERS)


def read_existing():
    if not OUT.exists():
        return []

    try:
        root = ET.parse(OUT).getroot()

    except Exception as exc:
        warn(f"Existing Alwan XML unreadable: {exc}")
        return []

    events = []

    for programme in root.findall("programme"):
        channel = channel_number_from_id(programme.get("channel") or "")

        if channel is None:
            continue

        raw_start = programme.get("start") or ""

        try:
            start = datetime.strptime(raw_start[:14], "%Y%m%d%H%M%S").replace(tzinfo=TZ)

        except Exception:
            continue

        if not in_window(start):
            continue

        title_node = programme.find("title")

        if title_node is None or not norm(title_node.text):
            continue

        title = norm(title_node.text)

        # IMPORTANT:
        # Never import generated filler back as if it were a real match.
        # Otherwise every hourly run keeps recycling filler entries and
        # eventually pollutes/duplicates the EPG.
        if is_filler_title(title):
            continue

        # Keep only genuine sports programmes from the previous XML.
        category_node = programme.find("category")

        if category_node is not None:
            category = norm(category_node.text).casefold()

            if category and category != "sports":
                continue

        events.append(
            {
                "channel": channel,
                "start": start,
                "title": title,
                "source": "existing XML",
            }
        )

    return dedupe(events)


def merge_existing(existing, fresh):
    combined = {}

    for event in existing:
        combined[event_key(event)] = event

    # Fresh Telegram data wins over anything already on disk.
    for event in fresh:
        combined[event_key(event)] = event

    return dedupe(
        [event for event in combined.values() if in_window(event["start"])]
    )


CHANNEL_NUMBERS = list(range(1, 11))

VARIANTS = [
    ("sport",        "Alwan Sport {n}"),
    ("sports",       "Alwan Sports {n}"),
    ("sport_hd",     "Alwan Sport {n} HD"),
    ("sport_sd",     "Alwan Sport {n} SD"),
    ("sport_4k",     "Alwan Sport {n} 4K"),
    ("sport_raw",    "Alwan Sport {n} RAW"),
    ("sports_hd",    "Alwan Sports {n} HD"),
    ("sports_sd",    "Alwan Sports {n} SD"),
    ("sports_4k",    "Alwan Sports {n} 4K"),
    ("sports_raw",   "Alwan Sports {n} RAW"),
]


def write_xml(events):
    """
    TiviMate-oriented XMLTV with REAL separate EPG entries for common
    playlist naming variants.

    For each Alwan number 1-10 we generate these separate EPG channels:
      - Alwan Sport N
      - Alwan Sports N
      - Alwan Sport N HD / SD / 4K / RAW
      - Alwan Sports N HD / SD / 4K / RAW

    All variants for the same number receive the SAME real matches and filler.
    Channel ids and display-names are unchanged from the previous version.
    """

    tv = ET.Element(
        "tv",
        {"generator-info-name": "Alwan Sports Telegram EPG"},
    )

    channel_ids_by_number = {n: [] for n in CHANNEL_NUMBERS}

    for number in CHANNEL_NUMBERS:
        for key, label_template in VARIANTS:
            channel_id = f"Alwan{number}_{key}"
            display_name = label_template.format(n=number)

            channel = ET.SubElement(tv, "channel", {"id": channel_id})
            ET.SubElement(
                channel,
                "display-name",
                {"lang": "en"},
            ).text = display_name

            channel_ids_by_number[number].append(channel_id)

    real_by_number = {number: [] for number in CHANNEL_NUMBERS}

    for event in events:
        number = int(event["channel"])

        if number in real_by_number:
            real_by_number[number].append(event)

    window_start = NOW.astimezone(TZ).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    window_end = window_start + timedelta(days=KEEP_DAYS_FORWARD + 1)

    # Give every match an end time, shortened when the next match on the same
    # channel starts sooner. Overlapping programmes confuse TiviMate.
    spans_by_number = {}

    for number in CHANNEL_NUMBERS:
        ordered = sorted(real_by_number[number], key=lambda item: item["start"])
        spans = []

        for position, event in enumerate(ordered):
            stop = event["start"] + timedelta(minutes=MATCH_MINUTES)

            if position + 1 < len(ordered):
                stop = min(stop, ordered[position + 1]["start"])

            if stop <= event["start"]:
                continue

            spans.append((event, stop))

        spans_by_number[number] = spans

    # Real programmes.
    for number in CHANNEL_NUMBERS:
        for event, stop in spans_by_number[number]:
            for channel_id in channel_ids_by_number[number]:
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
                    f"القناة: Alwan Sport {number}\n"
                    f"المصدر: {event['source']}"
                )

    def format_when(moment, reference_day):
        clock = moment.strftime("%H:%M")

        if moment.date() == reference_day:
            return clock

        weekday = AR_WEEKDAYS[moment.weekday()]
        return f"{weekday} {moment.day}/{moment.month} {clock}"

    def add_filler(number, channel_id, gap_start, gap_stop, next_event):
        """
        One block per gap (optionally cut at midnight), naming the next match.

        The kickoff time is written out in full rather than as a countdown:
        the guide is a cached static file, so a countdown would be wrong
        minutes after it was generated.
        """
        chunks = []
        cursor = gap_start

        while cursor < gap_stop:
            if SPLIT_FILLER_AT_MIDNIGHT:
                next_midnight = (cursor + timedelta(days=1)).replace(
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                stop = min(next_midnight, gap_stop)
            else:
                stop = gap_stop

            chunks.append((cursor, stop))
            cursor = stop

        for start, stop in chunks:
            if next_event is None or FILLER_MODE == "simple":
                title = "لا توجد مباراة مجدولة"
                description = (
                    f"لا توجد مباراة معلنة على Alwan Sport {number} "
                    f"في هذا الوقت."
                )
            else:
                when = format_when(next_event["start"], start.date())
                title = f"التالي {when} — {next_event['title']}"
                description = (
                    f"المباراة القادمة على Alwan Sport {number}:\n"
                    f"{next_event['title']}\n"
                    f"{format_when(next_event['start'], None)}"
                )

            programme = ET.SubElement(
                tv,
                "programme",
                {
                    "start": start.strftime("%Y%m%d%H%M%S %z"),
                    "stop": stop.strftime("%Y%m%d%H%M%S %z"),
                    "channel": channel_id,
                },
            )

            ET.SubElement(
                programme,
                "title",
                {"lang": "ar"},
            ).text = title

            ET.SubElement(
                programme,
                "category",
                {"lang": "en"},
            ).text = FILLER_CATEGORY

            ET.SubElement(
                programme,
                "desc",
                {"lang": "ar"},
            ).text = description

    # Build non-overlapping filler gaps once per channel number,
    # then duplicate those gaps to every naming variant.
    for number in CHANNEL_NUMBERS if FILLER_MODE != "off" else []:
        intervals = []

        for event, stop in spans_by_number[number]:
            s = max(event["start"], window_start)
            e = min(stop, window_end)

            if e > s:
                intervals.append((s, e))

        intervals.sort()
        merged = []

        for s, e in intervals:
            if not merged or s > merged[-1][1]:
                merged.append([s, e])
            else:
                merged[-1][1] = max(merged[-1][1], e)

        gaps = []
        cursor = window_start

        for s, e in merged:
            if s > cursor:
                gaps.append((cursor, s))

            cursor = max(cursor, e)

        if cursor < window_end:
            gaps.append((cursor, window_end))

        ordered_events = [event for event, _ in spans_by_number[number]]

        for channel_id in channel_ids_by_number[number]:
            for gap_start, gap_stop in gaps:
                # The first real match starting at or after this gap ends.
                next_event = next(
                    (
                        event
                        for event in ordered_events
                        if event["start"] >= gap_stop
                    ),
                    None,
                )

                add_filler(number, channel_id, gap_start, gap_stop, next_event)

    expected_programmes = sum(
        len(spans_by_number[number]) for number in CHANNEL_NUMBERS
    ) * len(VARIANTS)

    ET.indent(tv, space="  ")

    # Write to a temporary file first. A crash or a failed validation must
    # never leave TiviMate with a truncated or empty guide.
    tmp = OUT.with_name(OUT.name + ".tmp")

    try:
        ET.ElementTree(tv).write(tmp, encoding="utf-8", xml_declaration=True)
        validate_xml(tmp, channel_ids_by_number, expected_programmes)
        os.replace(tmp, OUT)

    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass

        raise


def validate_xml(path, channel_ids_by_number, expected_programmes):
    root = ET.parse(path).getroot()

    expected_channel_count = len(CHANNEL_NUMBERS) * len(VARIANTS)
    actual_channels = root.findall("channel")

    if len(actual_channels) != expected_channel_count:
        raise RuntimeError(
            f"Alwan XML validation failed; expected "
            f"{expected_channel_count} channel entries, got {len(actual_channels)}"
        )

    known_ids = {channel.get("id") for channel in actual_channels}

    programme_counts = {channel_id: 0 for channel_id in known_ids}
    spans = {channel_id: [] for channel_id in known_ids}
    total = 0
    real_total = 0

    for programme in root.findall("programme"):
        channel_id = programme.get("channel") or ""

        if channel_id not in known_ids:
            raise RuntimeError(
                f"Alwan XML validation failed; programme on unknown channel {channel_id}"
            )

        total += 1

        title_node = programme.find("title")

        if title_node is None or not norm(title_node.text):
            raise RuntimeError(
                f"Alwan XML validation failed; empty title on {channel_id}"
            )

        category_node = programme.find("category")
        category = norm(category_node.text) if category_node is not None else ""

        # A block counts as a real match only if BOTH signals agree.
        # Structural (category) and textual (title) checks together mean a
        # filler block can never be miscounted, or re-imported next run.
        is_filler = (
            category.casefold() != "sports"
            or is_filler_title(title_node.text)
        )

        if not is_filler:
            real_total += 1
            programme_counts[channel_id] += 1

        try:
            start_dt = datetime.strptime(
                (programme.get("start") or "")[:14],
                "%Y%m%d%H%M%S",
            ).replace(tzinfo=TZ)

            stop_dt = datetime.strptime(
                (programme.get("stop") or "")[:14],
                "%Y%m%d%H%M%S",
            ).replace(tzinfo=TZ)

        except Exception:
            raise RuntimeError(
                f"Alwan XML validation failed; bad timestamps on {channel_id}"
            )

        if stop_dt <= start_dt:
            raise RuntimeError(
                f"Alwan XML validation failed; non-positive duration on {channel_id}"
            )

        spans[channel_id].append((start_dt, stop_dt))

    # Every parsed fixture must have reached every naming variant.
    if real_total != expected_programmes:
        raise RuntimeError(
            f"Alwan XML validation failed; expected {expected_programmes} "
            f"match entries, got {real_total}"
        )

    # No two programmes on the same channel may overlap.
    for channel_id, items in spans.items():
        items.sort()

        for index in range(1, len(items)):
            if items[index][0] < items[index - 1][1]:
                raise RuntimeError(
                    f"Alwan XML validation failed; overlapping programmes on {channel_id}"
                )

    # Compact per-number log.
    for number in CHANNEL_NUMBERS:
        ids = channel_ids_by_number[number]
        per_variant = {programme_counts[i] for i in ids}

        if len(per_variant) != 1:
            raise RuntimeError(
                f"Alwan XML validation failed; naming variants of channel "
                f"{number} received different programme counts: {sorted(per_variant)}"
            )

        log(
            f"ALWAN {number} VARIANTS | "
            f"entries={len(ids)} | "
            f"matches_per_variant={per_variant.pop()}"
        )

    log(
        f"Total programme entries written: {total} "
        f"(matches: {real_total}, filler: {total - real_total})"
    )


def main():
    existing = read_existing()
    log(f"Existing REAL Alwan programmes kept: {len(existing)}")

    try:
        posts = fetch_posts()

    except Exception as exc:
        warn(f"Alwan Telegram fetch failed: {exc}")
        warn("Existing XML left untouched")
        return 0

    log(f"Alwan Telegram posts visible: {len(posts)}")

    # A landing page, a 429, or a disabled preview all look like "success"
    # with almost no posts. Never rebuild the guide from that.
    if len(posts) < MIN_POSTS_REQUIRED:
        warn(
            f"Only {len(posts)} Telegram posts returned "
            f"(expected at least {MIN_POSTS_REQUIRED}); existing XML left untouched"
        )
        return 0

    fresh = []
    debug_count = 0

    for post in posts:
        parsed = parse_post(post)

        if parsed:
            fresh.extend(parsed)

        elif debug_count < 4:
            text = post_text(post)

            if text:
                excerpt = norm(text.replace("\n", " | "))[:500]
                log("ALWAN DEBUG UNPARSED: " + excerpt)
                debug_count += 1

    fresh = dedupe(fresh)

    log(f"Alwan newly detected programmes: {len(fresh)}")

    for event in fresh:
        log(
            f"  ALWAN {event['channel']} | "
            f"{event['start']:%Y-%m-%d %H:%M} | "
            f"{event['title']}"
        )

    merged = merge_existing(existing, fresh)

    log(f"Alwan total programmes after merge: {len(merged)}")

    # Safety: if Telegram temporarily yields zero useful fixtures,
    # do not erase an already-useful XML.
    if not merged and OUT.exists():
        warn("No usable Alwan fixtures at all; existing XML left untouched")
        return 0

    if not fresh and existing:
        warn("No new usable Alwan fixtures; existing programmes reused")

    try:
        write_xml(merged)

    except Exception as exc:
        warn(f"Alwan XML not written: {exc}")
        return 1

    log(f"Written: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
