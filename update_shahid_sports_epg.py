#!/usr/bin/env python3
import html
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

from epg_lib import countdown_label, countdown_step, with_live_badge

# -----------------------------------------------------------------------------
# Shahid Sports Guide EPG
# - ONE Guide channel only
# - Text/HTML sources only; NO OCR
# - Keeps "لا توجد مباريات مجدولة" when no verified matches are found
# - Every detected match appears on the EPG strip at kickoff time
# - Description shows the whole day's schedule in source time only
# -----------------------------------------------------------------------------

RIYADH_TZ = ZoneInfo("Asia/Riyadh")
LIVE_SOCCER_TV_TZ = ZoneInfo("America/New_York")  # LiveSoccerTV HTML schedule is rendered in US Eastern time
NOW = datetime.now(RIYADH_TZ)

OUT = Path("shahid_sports_epg.xml")
CHANNEL_ID = "ShahidSportsGuide"

GOAL_HOME = "https://www.goal.com/ar"
KOOORA_HOME = "https://www.kooora.com/"
SCORES365_HOME = "https://www.365scores.com/ar/news/magazine/"
LIVE_SOCCER_TV = "https://www.livesoccertv.com/channels/shahid/"
LIVE_FOOTBALL_TV = "https://www.livefootballtv.info/channel/mbc-shahid-sports"
BUNDESLIGA_MATCHDAY = "https://www.bundesliga.com/en/bundesliga/matchday/2026-2027/{matchday}"
BUNDESLIGA_PRESEASON = "https://www.bundesliga.com/en/bundesliga/news/2026-27-pre-season-plans-tours-friendly-fixtures-results-bayern-munich-37680"

KEEP_DAYS_BACK = 1
KEEP_DAYS_FORWARD = 14

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "ar,en;q=0.8",
}

SOURCE_PRIORITY = {
    "365Scores": 100,
    "Goal": 90,
    "Kooora": 85,
    "LiveSoccerTV": 80,
    "LiveFootballTV": 75,
    "BundesligaOfficial": 110,
}

TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)")
TIME_AMPM_RE = re.compile(
    r"(?<!\d)(1[0-2]|0?[1-9])[:.]([0-5]\d)\s*(am|pm|a\.m\.|p\.m\.)\b",
    re.I,
)

SHAHID_RE = re.compile(
    r"(?:\bshahid\b(?:\s*(?:vip|sports?|plus))?)"
    r"|(?:\bmbc\s*shahid\b)"
    # "MBC Sport" is the Arabic broadcaster. "MBC Sports+" is a Korean
    # channel of no relation, and livesoccertv lists it, so the plus sign
    # has to be excluded or a K-League match lands on this guide.
    r"|(?:\bmbc\s*sports?\b(?!\s*\+))"
    r"|(?:شاهد(?:\s*(?:vip|سبورت|الرياضية))?)",
    re.I,
)

AR_MONTHS = {
    "يناير": 1,
    "فبراير": 2,
    "مارس": 3,
    "أبريل": 4,
    "ابريل": 4,
    "مايو": 5,
    "يونيو": 6,
    "يوليو": 7,
    "أغسطس": 8,
    "اغسطس": 8,
    "سبتمبر": 9,
    "أكتوبر": 10,
    "اكتوبر": 10,
    "نوفمبر": 11,
    "ديسمبر": 12,
}

EN_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

NOISE_WORDS = {
    "mbc shahid sports",
    "shahid",
    "shahid vip",
    "shahid sports",
    "coppa italia",
    "bundesliga",
    "dfl-supercup",
    "dfl supercup",
    "dfb pokal",
    "copa del rey",
    "italian serie a",
    "serie a",
    "football",
}


def log(message):
    print(message, flush=True)


def warn(message):
    print(f"WARN {message}", file=sys.stderr, flush=True)


def norm(value):
    value = html.unescape(value or "")
    value = value.replace("\u200f", " ").replace("\u200e", " ").replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", value).strip()


def fetch(url, timeout=20):
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.text


def in_window(dt):
    return NOW - timedelta(days=KEEP_DAYS_BACK) <= dt <= NOW + timedelta(days=KEEP_DAYS_FORWARD)


def parse_date(text, reference=None):
    text = norm(text)
    reference = reference or NOW.date()
    low = text.casefold()

    # dd/mm/yyyy or dd-mm-yyyy
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b", text)
    if m:
        d, mo, y = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            pass

    # Arabic: 19 أغسطس 2026
    months = "|".join(map(re.escape, AR_MONTHS))
    m = re.search(rf"\b(\d{{1,2}})\s+({months})(?:\s+(20\d{{2}}))?\b", text, re.I)
    if m:
        d = int(m.group(1))
        mo = AR_MONTHS[m.group(2)]
        y = int(m.group(3)) if m.group(3) else reference.year
        try:
            candidate = date(y, mo, d)
            if candidate < reference - timedelta(days=180):
                candidate = date(y + 1, mo, d)
            return candidate
        except ValueError:
            pass

    # English: Saturday, 22 August [2026] / Aug 22, 2026
    en_names = "|".join(sorted((re.escape(x) for x in EN_MONTHS), key=len, reverse=True))
    m = re.search(rf"\b(\d{{1,2}})\s+({en_names})(?:\s+(20\d{{2}}))?\b", low, re.I)
    if m:
        d = int(m.group(1))
        mo = EN_MONTHS[m.group(2).casefold()]
        y = int(m.group(3)) if m.group(3) else reference.year
        try:
            candidate = date(y, mo, d)
            if candidate < reference - timedelta(days=180):
                candidate = date(y + 1, mo, d)
            return candidate
        except ValueError:
            pass

    m = re.search(rf"\b({en_names})\s+(\d{{1,2}})(?:,?\s+(20\d{{2}}))?\b", low, re.I)
    if m:
        mo = EN_MONTHS[m.group(1).casefold()]
        d = int(m.group(2))
        y = int(m.group(3)) if m.group(3) else reference.year
        try:
            candidate = date(y, mo, d)
            if candidate < reference - timedelta(days=180):
                candidate = date(y + 1, mo, d)
            return candidate
        except ValueError:
            pass

    if "بعد غد" in low:
        return reference + timedelta(days=2)
    if any(x in low for x in ("غداً", "غدا", "بكرا", "بكرة", "tomorrow")):
        return reference + timedelta(days=1)
    if any(x in low for x in ("اليوم", "today")):
        return reference
    return None


def extract_time(text):
    text = norm(text)

    m = TIME_AMPM_RE.search(text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        ap = m.group(3).casefold()
        if ap.startswith("p") and hour != 12:
            hour += 12
        if ap.startswith("a") and hour == 12:
            hour = 0
        return hour, minute

    m = TIME_RE.search(text)
    if not m:
        return None

    hour, minute = int(m.group(1)), int(m.group(2))
    nearby = text[max(0, m.start() - 24):min(len(text), m.end() + 30)].casefold()
    if 1 <= hour <= 11 and ("مساء" in nearby or "pm" in nearby):
        hour += 12
    elif hour == 12 and ("صباح" in nearby or "am" in nearby):
        hour = 0
    return hour, minute


def extract_riyadh_time(text):
    """Prefer the time explicitly labelled Mecca/Saudi/Riyadh when a row has several times."""
    text = norm(text)
    matches = list(TIME_RE.finditer(text))
    if not matches:
        return extract_time(text)

    labels = ("مكة", "السعودية", "الرياض", "mecca", "makkah", "saudi", "riyadh")
    low = text.casefold()

    best = None
    best_distance = 10**9
    for m in matches:
        for label in labels:
            pos = low.find(label, m.end())
            if pos != -1 and pos - m.end() <= 45:
                distance = pos - m.end()
                if distance < best_distance:
                    best = m
                    best_distance = distance

    if best is None:
        # In Arabic schedule rows, Mecca/Saudi is often the LAST time shown.
        best = matches[-1]

    return int(best.group(1)), int(best.group(2))


def make_dt(day, hour, minute, source_tz=RIYADH_TZ):
    # Preserve the source timezone in XMLTV. TiviMate will convert the timestamp
    # to the device timezone from the explicit UTC offset.
    return datetime(day.year, day.month, day.day, int(hour), int(minute), tzinfo=source_tz)


def clean_side(value):
    value = norm(value)
    value = re.sub(r"^(?:⚽|🏆|📺|⏰|•|\||✅|🔥|🎙️|🎙|🗓️|🗓)+\s*", "", value)
    return value.strip(" |:-–—")


def looks_like_team(value):
    value = clean_side(value)
    if not value:
        return False
    low = value.casefold()

    bad = (
        "أغسطس", "اغسطس", "سبتمبر", "أكتوبر", "اكتوبر", "نوفمبر", "ديسمبر",
        "يناير", "فبراير", "مارس", "أبريل", "ابريل", "مايو", "يونيو", "يوليو",
        "اليوم", "غدا", "غداً", "بتوقيت", "الساعة", "موعد", "القنوات", "الناقلة",
        "المصدر", "كتب", "تحرير", "آخر تحديث", "اخر تحديث",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        # A competition heading is not a team, and one reached the guide:
        # "الدوري الفرنسي - الجولة 2" was published as though it were a
        # fixture, because it carries a dash and nothing above rejected
        # it. No club is named after a league or a matchday.
        "الدوري", "الجولة", "الأسبوع", "الاسبوع", "بطولة", "matchday",
    )
    if any(word in low for word in bad):
        return False
    if low in NOISE_WORDS:
        return False
    if SHAHID_RE.fullmatch(value):
        return False
    if re.search(r"\b20\d{2}\b", value) or TIME_RE.search(value):
        return False
    letters = sum(ch.isalpha() for ch in value)
    if letters < 2:
        return False
    if len(value) > 70 or len(value.split()) > 8:
        return False
    return True


def fixture_from_text(text):
    text = norm(text)
    separators = (
        r"🆚",
        r"⚔️?",
        r"\bvs\.?\b",
        r"\bv\.?\b",
        r"\bضد\b",
        r"\s[-–—]\s",
    )

    for sep in separators:
        m = re.search(rf"(.{{2,75}}?)\s*(?:{sep})\s*(.{{2,75}})", text, re.I)
        if not m:
            continue
        first = clean_side(m.group(1))
        second = clean_side(m.group(2))
        if looks_like_team(first) and looks_like_team(second):
            return f"{first} - {second}"
    return None


def fixture_from_cells(cells):
    # Usually the fixture is its own table cell.
    for cell in cells:
        title = fixture_from_text(cell)
        if title:
            return title

    # Some sites use two separate team cells.
    teamish = []
    for cell in cells:
        value = clean_side(cell)
        if not looks_like_team(value):
            continue
        if SHAHID_RE.search(value) or TIME_RE.search(value):
            continue
        if any(noise in value.casefold() for noise in NOISE_WORDS):
            continue
        teamish.append(value)

    if len(teamish) >= 2:
        return f"{teamish[0]} - {teamish[1]}"
    return None


TEAM_NAME_ALIASES = (
    ("münchen", "munich"),
    ("muenchen", "munich"),
    ("fc bayern", "bayern"),
    ("hamburger sv", "hamburg"),
)


def normalize_name(value):
    value = norm(value).casefold()
    for old, new in TEAM_NAME_ALIASES:
        value = value.replace(old, new)
    value = re.sub(r"[^\w\u0600-\u06ff ]+", " ", value)
    value = re.sub(r"\b(?:fc|cf|club|sv|vfb|1|نادي)\b", " ", value, flags=re.I)
    return re.sub(r"\s+", " ", value).strip()


def title_signature(title):
    parts = [normalize_name(x) for x in norm(title).split(" - ", 1)]
    if len(parts) != 2 or not all(parts):
        return norm(title).casefold()
    return "|".join(sorted(parts))


def event_group_key(event):
    # Same fixture on same Riyadh calendar date = one event.
    # Use one common calendar date only for dedupe grouping; keep the original
    # source timezone on the event timestamp itself.
    return (event["start"].astimezone(RIYADH_TZ).date().isoformat(), title_signature(event["title"]))


def choose_best_event(events):
    def rank(event):
        source = event.get("source_name", "")
        return SOURCE_PRIORITY.get(source, 0)
    return sorted(events, key=lambda e: (rank(e), e["start"]), reverse=True)[0]


def dedupe(events):
    grouped = defaultdict(list)
    for event in events:
        if in_window(event["start"]):
            grouped[event_group_key(event)].append(event)

    output = []
    for _, candidates in grouped.items():
        best = choose_best_event(candidates)
        output.append(best)

        if len(candidates) > 1:
            sources = ", ".join(sorted({x.get("source_name", "?") for x in candidates}))
            log(f"DEDUPE | {best['start']:%Y-%m-%d %H:%M} | {best['title']} | sources={sources}")

    return sorted(output, key=lambda e: (e["start"], e["title"]))


def article_date(soup):
    candidates = []
    for selector in ("h1", "title"):
        tag = soup.select_one(selector)
        if tag:
            candidates.append(norm(tag.get_text(" ", strip=True)))
    candidates.append(norm(soup.get_text(" ", strip=True))[:7000])
    for candidate in candidates:
        parsed = parse_date(candidate, NOW.date())
        if parsed:
            return parsed
    return NOW.date()


def discover_daily_articles(home_url, label):
    try:
        soup = BeautifulSoup(fetch(home_url), "html.parser")
    except Exception as exc:
        warn(f"{label} discovery failed: {exc}")
        return []

    urls, seen = [], set()
    for anchor in soup.find_all("a", href=True):
        text = norm(anchor.get_text(" ", strip=True))
        href = norm(anchor.get("href"))
        combined = f"{text} {href}"

        if label in ("Goal", "Kooora"):
            wanted = "جدول مباريات اليوم" in combined
            if not wanted:
                continue
        else:
            if "/ar/news/magazine/" not in urljoin(home_url, href):
                continue

        url = urljoin(home_url, href).split("#", 1)[0]
        if not url.startswith(("http://", "https://")):
            continue
        low_url = url.casefold()
        if any(x in low_url for x in (
            "facebook.com/sharer", "facebook.com/dialog", "content-tag/",
            "mailto:", "fb-messenger:", "/tag/", "/category/"
        )):
            continue
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)

    limit = 12 if label in ("Goal", "Kooora") else 120
    log(f"{label} schedule articles discovered: {len(urls)}")
    return urls[:limit]


def parse_table_article(url, label):
    """Parse schedule/news tables and keep ONLY rows locally marked Shahid/MBC Shahid."""
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
    except Exception as exc:
        warn(f"{label} article failed {url}: {exc}")
        return []

    day = article_date(soup)
    if day < NOW.date() - timedelta(days=KEEP_DAYS_BACK + 2):
        return []
    if day > NOW.date() + timedelta(days=KEEP_DAYS_FORWARD + 2):
        return []

    events = []

    # Best path: table rows.
    for row in soup.find_all("tr"):
        cells = [norm(c.get_text(" ", strip=True)) for c in row.find_all(["th", "td"])]
        cells = [c for c in cells if c]
        if not cells:
            continue

        row_text = " | ".join(cells)
        attrs = " ".join(
            norm(str(x))
            for tag in row.find_all(True)
            for x in (
                tag.get("alt"), tag.get("title"), tag.get("aria-label"),
                tag.get("src"), tag.get("href"), tag.get("class"), tag.get("id")
            )
            if x
        )
        marker_text = f"{row_text} | {attrs}"
        if not SHAHID_RE.search(marker_text):
            continue

        title = fixture_from_cells(cells)
        if not title:
            continue

        time_value = extract_riyadh_time(row_text)
        if not time_value:
            continue

        row_day = parse_date(row_text, day) or day
        start = make_dt(row_day, time_value[0], time_value[1])
        if not in_window(start):
            continue

        events.append({
            "start": start,
            "title": title,
            "source": url,
            "source_name": label,
        })

    # Local text fallback for sites that render schedule as cards instead of <tr>.
    if not events:
        lines = [norm(x) for x in soup.get_text("\n", strip=True).splitlines() if norm(x)]
        for i, line in enumerate(lines):
            if not SHAHID_RE.search(line):
                continue

            block_lines = lines[max(0, i - 3):min(len(lines), i + 4)]
            block = " | ".join(block_lines)
            if len(block) > 1200:
                continue

            title = next((fixture_from_text(x) for x in block_lines if fixture_from_text(x)), None)
            time_value = extract_riyadh_time(block)
            if not title or not time_value:
                continue

            row_day = parse_date(block, day) or day
            start = make_dt(row_day, time_value[0], time_value[1])
            if not in_window(start):
                continue

            events.append({
                "start": start,
                "title": title,
                "source": url,
                "source_name": label,
            })

    events = dedupe(events)
    if events:
        log(f"{label} Shahid fixtures from {url}: {len(events)}")
    return events


def parse_livesoccertv():
    """Parse the dedicated MBC Shahid channel schedule, including upcoming day headings."""
    try:
        soup = BeautifulSoup(fetch(LIVE_SOCCER_TV), "html.parser")
    except Exception as exc:
        warn(f"LiveSoccerTV failed: {exc}")
        return []

    events = []
    current_day = None

    # Walk schedule-like blocks in document order. Day headings such as
    # 'Saturday, 22 August' set the date for following match rows.
    for node in soup.find_all(["h2", "h3", "h4", "h5", "tr", "li"]):
        text = norm(node.get_text(" ", strip=True))
        if not text:
            continue

        parsed_day = parse_date(text, NOW.date())
        if parsed_day and not TIME_RE.search(text) and len(text) < 100:
            current_day = parsed_day
            continue

        title = fixture_from_text(text)
        if not title:
            continue

        time_value = extract_time(text)
        row_day = parse_date(text, NOW.date()) or current_day
        if not time_value or not row_day:
            continue

        start = make_dt(row_day, time_value[0], time_value[1], LIVE_SOCCER_TV_TZ)
        if not in_window(start):
            continue

        # Dedicated channel page is already Shahid-specific. Still reject obvious
        # site-wide 'Top Matches' entries by requiring a schedule/table row OR
        # explicit MBC/Shahid marker in the local block.
        local_html = norm(str(node))
        if node.name != "tr" and not SHAHID_RE.search(local_html):
            continue

        events.append({
            "start": start,
            "title": title,
            "source": LIVE_SOCCER_TV,
            "source_name": "LiveSoccerTV",
        })

    # Extra fallback: identify date headings and then short text windows.
    if not events:
        lines = [norm(x) for x in soup.get_text("\n", strip=True).splitlines() if norm(x)]
        current_day = None
        for i, line in enumerate(lines):
            d = parse_date(line, NOW.date())
            if d and len(line) < 100 and not TIME_RE.search(line):
                current_day = d
                continue

            title = fixture_from_text(line)
            if not title or not current_day:
                continue

            block = " | ".join(lines[max(0, i - 2):min(len(lines), i + 3)])
            time_value = extract_time(block)
            if not time_value:
                continue

            start = make_dt(current_day, time_value[0], time_value[1], LIVE_SOCCER_TV_TZ)
            if in_window(start):
                events.append({
                    "start": start,
                    "title": title,
                    "source": LIVE_SOCCER_TV,
                    "source_name": "LiveSoccerTV",
                })

    events = dedupe(events)
    log(f"LiveSoccerTV Shahid fixtures detected: {len(events)}")
    return events


def parse_livefootballtv():
    """Parse the dedicated MBC Shahid Sports guide from LiveFootballTV."""
    try:
        soup = BeautifulSoup(fetch(LIVE_FOOTBALL_TV), "html.parser")
    except Exception as exc:
        warn(f"LiveFootballTV failed: {exc}")
        return []

    lines = [norm(x) for x in soup.get_text("\n", strip=True).splitlines() if norm(x)]
    events = []
    current_day = None
    pending_time = None
    pending_lines = []

    for line in lines:
        d = parse_date(line, NOW.date())
        # Dedicated page date headings are compact, e.g. Tuesday, 01/09/2026.
        if d and len(line) < 100 and not SHAHID_RE.search(line):
            current_day = d
            pending_time = None
            pending_lines = []
            continue

        # On this page a standalone time begins one match block.
        if re.fullmatch(r"(?:[01]?\d|2[0-3]):[0-5]\d", line):
            tv = extract_time(line)
            if tv:
                pending_time = tv
                pending_lines = []
            continue

        if pending_time is not None:
            pending_lines.append(line)

        if pending_time is None or current_day is None:
            continue

        if "mbc shahid sports" not in line.casefold():
            continue

        # Prefer an explicit vs/ضد pattern if present.
        block = " | ".join(pending_lines)
        title = fixture_from_text(block)

        # LiveFootballTV often renders competition + team1 + team2 + channel on
        # separate lines, without a VS token. In that case take the last two
        # plausible team names before the channel label.
        if not title:
            candidates = []
            for item in pending_lines[:-1]:
                value = clean_side(item)
                low = value.casefold()
                if not looks_like_team(value):
                    continue
                if low in NOISE_WORDS:
                    continue
                if SHAHID_RE.search(value):
                    continue
                candidates.append(value)
            if len(candidates) >= 2:
                title = f"{candidates[-2]} - {candidates[-1]}"

        if title:
            start = make_dt(current_day, pending_time[0], pending_time[1])
            if in_window(start):
                events.append({
                    "start": start,
                    "title": title,
                    "source": LIVE_FOOTBALL_TV,
                    "source_name": "LiveFootballTV",
                })

        pending_time = None
        pending_lines = []

    events = dedupe(events)
    log(f"LiveFootballTV Shahid fixtures detected: {len(events)}")
    return events



def parse_bundesliga_official():
    """Read the official Bundesliga matchday pages directly.

    The official English matchday page currently exposes kick-off times in UTC
    (example: Bayern-Stuttgart is 18:30 there = 20:30 CEST).
    We parse DATE -> TIME -> TEAM-CODE PAIR in document order.
    """
    events = []

    TEAM = {
        "FCB": "Bayern Munich",
        "VFB": "VfB Stuttgart",
        "BVB": "Borussia Dortmund",
        "HSV": "Hamburg",
        "FCU": "Union Berlin",
        "SGE": "Eintracht Frankfurt",
        "ELV": "Elversberg",
        "B04": "Bayer Leverkusen",
        "KOE": "Cologne",
        "TSG": "Hoffenheim",
        "M05": "Mainz",
        "SCP": "Paderborn",
        "RBL": "RB Leipzig",
        "BMG": "Borussia Mönchengladbach",
        "SCF": "Freiburg",
        "SVW": "Werder Bremen",
        "FCA": "Augsburg",
        "S04": "Schalke",
        "WOB": "Wolfsburg",
        "STP": "St. Pauli",
        "FCH": "Heidenheim",
        "KSV": "Holstein Kiel",
    }

    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }

    def add_utc(day, hh, mm, home, away, source):
        start_utc = datetime(day.year, day.month, day.day, hh, mm, tzinfo=timezone.utc)
        start = start_utc
        if in_window(start):
            events.append({
                "start": start,
                "title": f"{home} - {away}",
                "source": source,
                "source_name": "BundesligaOfficial",
            })

    # The opening four matchdays have exact dates/times confirmed.
    for md in range(1, 5):
        url = BUNDESLIGA_MATCHDAY.format(matchday=md)
        try:
            soup = BeautifulSoup(fetch(url), "html.parser")
        except Exception as exc:
            warn(f"Bundesliga official matchday {md} failed: {exc}")
            continue

        # Keep compact visible chunks in DOM order.
        lines = [norm(x) for x in soup.stripped_strings if norm(x)]
        current_day = None
        pending_time = None

        for line in lines:
            low = line.casefold()

            # e.g. "Friday 28 August" or "Saturday 5 September"
            dm = re.search(
                r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)?\s*"
                r"(\d{1,2})\s+"
                r"(january|february|march|april|may|june|july|august|september|october|november|december)"
                r"(?:\s+(2026|2027))?\b",
                low,
            )
            if dm:
                year = int(dm.group(3) or (2026 if months[dm.group(2)] >= 7 else 2027))
                try:
                    current_day = date(year, months[dm.group(2)], int(dm.group(1)))
                    pending_time = None
                except ValueError:
                    current_day = None
                continue

            tm = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", line)
            if tm and current_day:
                pending_time = (int(tm.group(1)), int(tm.group(2)))
                continue

            # Official page renders fixture as e.g. "FCB VFB".
            pair = re.fullmatch(r"([A-Z0-9]{2,4})\s+([A-Z0-9]{2,4})", line)
            if pair and current_day and pending_time:
                a, b = pair.groups()
                if a in TEAM and b in TEAM:
                    add_utc(
                        current_day,
                        pending_time[0], pending_time[1],
                        TEAM[a], TEAM[b],
                        url,
                    )
                    pending_time = None

    # Franz Beckenbauer Supercup, official Bundesliga date/time:
    # 22 Aug 2026, 20:30 CEST = 18:30 UTC.
    add_utc(
        date(2026, 8, 22), 18, 30,
        "Borussia Dortmund", "Bayern Munich",
        BUNDESLIGA_PRESEASON,
    )

    events = dedupe(events)
    log(f"BundesligaOfficial Shahid fixtures detected: {len(events)}")
    return events


def collect_all_sources():
    events = []

    # 365Scores is CONFIRMATION-ONLY for Shahid.
    # IMPORTANT: never create an XMLTV programme from a 365Scores timestamp.
    # Its magazine pages can contain article publish/update times that are not
    # match kick-off times. We still discover the source for visibility, but
    # its times are deliberately ignored.
    discover_daily_articles(SCORES365_HOME, "365Scores")
    log("365Scores confirmation-only mode | TIMES IGNORED | no programme creation")

    # Daily Arabic schedule tables whose locally-labelled kick-off times may
    # create programmes.
    for label, home in (
        ("Goal", GOAL_HOME),
        ("Kooora", KOOORA_HOME),
    ):
        urls = discover_daily_articles(home, label)
        for url in urls:
            events.extend(parse_table_article(url, label))

    events.extend(parse_bundesliga_official())

    # Dedicated Shahid/MBC Shahid channel schedule pages.
    events.extend(parse_livesoccertv())
    events.extend(parse_livefootballtv())

    # A single unified pass groups every source's fixtures by (Riyadh
    # calendar day, normalized team pair) and keeps only the highest
    # -priority source per fixture -- see normalize_name/title_signature.
    # This is what previously caught only LiveSoccerTV/LiveFootballTV
    # duplicates against BundesligaOfficial and missed Goal/Kooora
    # duplicates with spelling variants (e.g. "Munich" vs "München").
    return dedupe(events)


def write_xml(events):
    tv = ET.Element("tv", {"generator-info-name": "Shahid Sports Guide FINAL"})
    channel = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(channel, "icon", {"src": "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/logos/shahid.png"})
    ET.SubElement(channel, "display-name", {"lang": "en"}).text = "Shahid | Guide"
    ET.SubElement(channel, "display-name", {"lang": "ar"}).text = "شاهد | Guide"

    window_start = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
    window_end = window_start + timedelta(days=KEEP_DAYS_FORWARD + 1)

    by_day = defaultdict(list)
    for event in dedupe(events):
        if in_window(event["start"]):
            by_day[event["start"].astimezone(RIYADH_TZ).date()].append(event)

    def source_time(event):
        # Show only the time supplied by that source. No Abu Dhabi / Las Vegas
        # conversions are embedded in the guide; TiviMate handles local display.
        return event["start"].strftime("%H:%M")

    def day_description(day, day_events):
        if not day_events:
            return f"مباريات Shahid Sports - {day:%Y-%m-%d}\n\nلا توجد مباريات مجدولة."

        lines = [f"مباريات Shahid Sports - {day:%Y-%m-%d}", ""]
        for event in sorted(day_events, key=lambda x: (x["start"], x["title"])):
            lines.append(f"{source_time(event)} | {event['title']}")
        return "\n".join(lines)

    def add_programme(start, stop, title, description):
        # Boundaries mix datetimes from different source timezones (Riyadh,
        # US Eastern, UTC...); min()/comparisons keep whichever operand's
        # tzinfo "won", so normalize to one timezone before formatting or
        # adjacent <programme> tags render with inconsistent UTC offsets.
        start = start.astimezone(RIYADH_TZ)
        stop = stop.astimezone(RIYADH_TZ)
        if stop <= start:
            return
        p = ET.SubElement(tv, "programme", {
            "start": start.strftime("%Y%m%d%H%M%S %z"),
            "stop": stop.strftime("%Y%m%d%H%M%S %z"),
            "channel": CHANNEL_ID,
        })
        ET.SubElement(p, "title", {"lang": "ar"}).text = title
        ET.SubElement(p, "category", {"lang": "en"}).text = "Sports"
        ET.SubElement(p, "desc", {"lang": "ar"}).text = description

    # Every kickoff across the whole window, so a countdown near the end of a
    # day can still point at tomorrow's first match instead of going blank.
    all_kickoffs = sorted({
        e["start"] for day in by_day.values() for e in day
    })
    # Joined with " + " for the same reason the slot titles are, so a
    # countdown names the coming matches exactly as the row it counts down
    # to will name them.
    titles_at = {
        k: " + ".join(sorted(
            e["title"] for day in by_day.values() for e in day if e["start"] == k
        ))
        for k in all_kickoffs
    }

    def next_kickoff_after(moment):
        return next((k for k in all_kickoffs if k >= moment), None)

    def add_countdown(gap_start, gap_stop, description):
        """Fill a gap with consecutive blocks counting down to the next match.

        A countdown baked into a static file would go stale immediately, so
        the gap is split into blocks each labelled with the time left at its
        own start. The player always shows the block covering "now", so the
        figure stays right without re-downloading; blocks shorten as kickoff
        approaches so it is never more than one step out of date.
        """
        block = gap_start
        while block < gap_stop:
            upcoming = next_kickoff_after(block)
            if upcoming is None:
                add_programme(block, gap_stop, "لا توجد مباراة قادمة", description)
                return

            remaining = upcoming - block
            stop = min(block + countdown_step(remaining), gap_stop, upcoming)
            if stop <= block:
                return

            left = countdown_label(remaining.total_seconds() // 60)
            add_programme(
                block, stop,
                f"{titles_at[upcoming]} · بعد {left}", description,
            )
            block = stop

    cursor = window_start
    while cursor < window_end:
        day_start = cursor
        day_stop = min(day_start + timedelta(days=1), window_end)
        current_day = day_start.date()

        # One event per fixture after strong dedupe.
        day_events = dedupe([
            e for e in by_day.get(current_day, [])
            if day_start <= e["start"] < day_stop
        ])
        desc = day_description(current_day, day_events)

        if not day_events:
            add_countdown(day_start, day_stop, desc)
            cursor = day_stop
            continue

        # Multiple simultaneous matches are combined in one strip cell to avoid
        # XMLTV overlap while the description still lists each match separately.
        groups = defaultdict(list)
        for event in day_events:
            groups[event["start"]].append(event)

        kickoff_times = sorted(groups)

        if kickoff_times[0] > day_start:
            add_countdown(day_start, kickoff_times[0], desc)

        for index, kickoff in enumerate(kickoff_times):
            next_kickoff = kickoff_times[index + 1] if index + 1 < len(kickoff_times) else None
            natural_stop = kickoff + timedelta(hours=3)
            stop = min(next_kickoff, natural_stop, day_stop) if next_kickoff else min(natural_stop, day_stop)
            # Matches kicking off at the same minute share one row, because
            # a single guide channel cannot show them side by side. They are
            # joined with " + ", the same separator Shasha's guide uses, so
            # the two read alike: "A - B + C - D" is two matches, and the
            # dash always separates the sides of one.
            title = " + ".join(
                event["title"] for event in sorted(groups[kickoff], key=lambda x: x["title"])
            )
            add_programme(kickoff, stop, with_live_badge(title), desc)

        last_stop = min(kickoff_times[-1] + timedelta(hours=3), day_stop)
        if last_stop < day_stop:
            add_countdown(last_stop, day_stop, desc)

        cursor = day_stop

    ET.indent(tv, space="  ")
    ET.ElementTree(tv).write(OUT, encoding="utf-8", xml_declaration=True)

    # Validation: one channel, no overlaps, current-time coverage.
    root = ET.parse(OUT).getroot()
    channels = root.findall("channel")
    if len(channels) != 1 or channels[0].get("id") != CHANNEL_ID:
        raise RuntimeError("Shahid Guide validation failed: expected exactly one Guide channel")

    slots = []
    for p in root.findall("programme"):
        if p.get("channel") != CHANNEL_ID:
            continue
        s = datetime.strptime(p.get("start") or "", "%Y%m%d%H%M%S %z")
        e = datetime.strptime(p.get("stop") or "", "%Y%m%d%H%M%S %z")
        slots.append((s, e))

    slots.sort()
    for i in range(1, len(slots)):
        if slots[i][0] < slots[i - 1][1]:
            raise RuntimeError("Shahid Guide validation failed: overlapping programmes")

    current = any(s <= NOW < e for s, e in slots)
    log("SHAHID CURRENT COVERAGE | " + ("YES" if current else "NO"))
    log(
        "SHAHID GUIDE DAYS | "
        + ", ".join(f"{day}:{len(items)}" for day, items in sorted(by_day.items()))
    )
    if not current:
        raise RuntimeError("Shahid Guide validation failed: no current coverage")


def main():
    log("SHAHID FINAL vTIMEFIX-365SAFE | 365 TIMES IGNORED | SOURCE TIME XMLTV | TIVIMATE AUTO-CONVERT | NO ABU DHABI/LAS VEGAS | NO OCR")
    fresh = collect_all_sources()

    log(f"Shahid total verified programmes: {len(fresh)}")
    for event in fresh:
        log(
            f"  SHAHID GUIDE | {event['start']:%Y-%m-%d %H:%M %z} SOURCE TIME | "
            f"{event['title']} | {event.get('source_name', '?')}"
        )

    write_xml(fresh)
    log(f"Written: {OUT}")


if __name__ == "__main__":
    main()
