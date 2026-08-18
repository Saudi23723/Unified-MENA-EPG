#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SOURCES = [
    ("LiveSoccerTV", "https://www.livesoccertv.com/channels/shasha/"),
    ("LiveFootballTV", "https://www.livefootballtv.info/channel/shasha-tv"),
    ("365Scores Arabic", "https://www.365scores.com/ar/news"),
    ("Kooora", "https://www.kooora.com/"),
    ("Goal Arabic", "https://www.goal.com/ar"),
    ("SHASHA Official", "https://www.shasha.com/"),
    ("SHASHA Sports Instagram", "https://www.instagram.com/shasha_sports/"),
    ("SHASHA Sports X", "https://x.com/Shasha_Sports"),
]
OUT = Path("shasha_guide_epg.xml")
MANUAL = Path("shasha_matches.json")

RIYADH = ZoneInfo("Asia/Riyadh")
VEGAS = ZoneInfo("America/Los_Angeles")
UTC = ZoneInfo("UTC")

CHANNEL_ID = "ShashaGuide"
KEEP_DAYS_BACK = 1
KEEP_DAYS_FORWARD = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
}

AR_DAYS = {
    0: "الاثنين",
    1: "الثلاثاء",
    2: "الأربعاء",
    3: "الخميس",
    4: "الجمعة",
    5: "السبت",
    6: "الأحد",
}

AR_MONTHS = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل",
    5: "مايو", 6: "يونيو", 7: "يوليو", 8: "أغسطس",
    9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
}


def log(msg):
    print(msg, flush=True)


def warn(msg):
    print(f"WARN {msg}", flush=True)


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def in_window(dt_riyadh):
    now = datetime.now(RIYADH)
    lo = now - timedelta(days=KEEP_DAYS_BACK)
    hi = now + timedelta(days=KEEP_DAYS_FORWARD + 1)
    return lo <= dt_riyadh < hi


def event_key(e):
    return (
        e["start"].strftime("%Y%m%d%H%M"),
        norm(e["title"]).casefold(),
    )


def dedupe(events):
    out = []
    seen = set()
    for e in sorted(events, key=lambda x: (x["start"], x["title"])):
        k = event_key(e)
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out


def parse_manual():
    """
    Optional manual override file format:
    [
      {
        "title": "Inter - Milan",
        "start": "2026-08-19T21:45:00+03:00",
        "competition": "Serie A"
      }
    ]
    """
    if not MANUAL.exists():
        return []

    try:
        data = json.loads(MANUAL.read_text(encoding="utf-8"))
    except Exception as exc:
        warn(f"Could not read {MANUAL}: {exc}")
        return []

    events = []
    for row in data:
        try:
            start = datetime.fromisoformat(row["start"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=RIYADH)
            start = start.astimezone(RIYADH)

            if not in_window(start):
                continue

            title = norm(row["title"])
            if not title:
                continue

            events.append({
                "title": title,
                "start": start,
                "competition": norm(row.get("competition", "")),
                "source": "manual override",
            })
        except Exception as exc:
            warn(f"Skipping invalid manual row: {exc}")

    return events


def _extract_machine_dt(node):
    """Return timezone-aware datetime if the HTML exposes one; otherwise None."""
    # HTML5 <time datetime=...>
    time_el = node.find("time")
    if time_el:
        iso = time_el.get("datetime")
        if iso:
            try:
                return datetime.fromisoformat(iso.replace("Z", "+00:00"))
            except Exception:
                pass

    # Common ISO datetime attributes
    for tag in [node] + node.find_all(True):
        for attr in ("data-datetime", "data-date-time", "datetime"):
            value = tag.get(attr)
            if not value:
                continue
            try:
                dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if dt.tzinfo is not None:
                    return dt
            except Exception:
                pass

    # Unix timestamps
    for tag in [node] + node.find_all(True):
        for attr in ("data-timestamp", "data-utc", "data-epoch"):
            value = tag.get(attr)
            if value and str(value).isdigit():
                try:
                    ts = int(value)
                    if ts > 10_000_000_000:
                        ts //= 1000
                    return datetime.fromtimestamp(ts, UTC)
                except Exception:
                    pass

    return None


def _clean_match_title(text):
    text = norm(text)
    text = re.sub(r"https?://\S+", "", text)

    # Normalize common versus markers.
    text = re.sub(r"\s*(?:🆚|⚔️|⚔|VS\.?|V\.?|ضد)\s*", " - ", text, flags=re.I)

    # Strip obvious schedule metadata.
    text = re.sub(
        r"\b(?:live|watch|stream|today|tomorrow|اليوم|غداً|غدا|مباشر)\b",
        "",
        text,
        flags=re.I,
    )
    text = norm(text)

    if " - " not in text:
        return None

    left, right = [norm(x) for x in text.split(" - ", 1)]
    if not left or not right:
        return None

    # Avoid huge social captions.
    if len(left) > 80 or len(right) > 80:
        return None

    return f"{left} - {right}"


def _generic_source_scrape(label, url):
    """
    Conservative generic scraper.
    Only creates a programme if BOTH are present in the same HTML container:
      1) a match-like 'A vs B'
      2) a machine-readable timezone-aware datetime/timestamp

    This avoids inventing kickoff times from social-media text.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
    except Exception as exc:
        warn(f"{label} fetch failed: {exc}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    events = []

    containers = []
    for selector in (
        "article",
        "tr",
        "li",
        ".matchrow",
        ".match-row",
        ".schedule-row",
        ".event",
        ".post",
        ".card",
    ):
        containers.extend(soup.select(selector))

    # If page has no obvious containers, inspect smaller DIVs too.
    if not containers:
        containers = [
            div for div in soup.find_all("div")
            if len(norm(div.get_text(" ", strip=True))) <= 500
        ]

    seen = set()

    for node in containers:
        raw = norm(node.get_text(" ", strip=True))
        if not raw or raw in seen:
            continue
        seen.add(raw)

        if not re.search(r"(?:🆚|⚔️|⚔|\bVS\.?\b|\bV\.?\b|ضد)", raw, re.I):
            continue

        dt = _extract_machine_dt(node)
        if dt is None:
            continue

        title = _clean_match_title(raw)
        if not title:
            continue

        start = dt.astimezone(RIYADH)
        if not in_window(start):
            continue

        events.append({
            "title": title,
            "start": start,
            "competition": "",
            "source": label,
        })

    events = dedupe(events)
    log(f"{label}: {len(events)} usable SHASHA match listings")
    return events


def scrape_livesoccertv():
    """
    Dedicated LiveSoccerTV parser + safe fallback to generic parser.
    """
    url = "https://www.livesoccertv.com/channels/shasha/"

    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
    except Exception as exc:
        warn(f"LiveSoccerTV fetch failed: {exc}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    text = norm(soup.get_text(" ", strip=True))

    if "There are currently no upcoming soccer listings scheduled on Shasha" in text:
        log("LiveSoccerTV currently reports no upcoming Shasha soccer listings.")
        return []

    # Use generic conservative parser on the fetched document structure.
    events = []
    for node in soup.select("tr, .matchrow, .match-row, .schedule-row, .event, li"):
        raw = norm(node.get_text(" ", strip=True))
        if not re.search(r"(?:🆚|⚔️|⚔|\bVS\.?\b|\bV\.?\b|ضد)", raw, re.I):
            continue

        dt = _extract_machine_dt(node)
        if dt is None:
            continue

        title = _clean_match_title(raw)
        if not title:
            continue

        start = dt.astimezone(RIYADH)
        if not in_window(start):
            continue

        events.append({
            "title": title,
            "start": start,
            "competition": "",
            "source": "LiveSoccerTV",
        })

    events = dedupe(events)
    log(f"LiveSoccerTV: {len(events)} usable SHASHA match listings")
    return events



def _page_mentions_shasha(text):
    t = norm(text).casefold()
    return ("shasha" in t) or ("شاشا" in t)


def _extract_match_candidates_from_page(label, url):
    """
    Scan a news/listing page and keep ONLY containers that explicitly mention
    SHASHA/شاشا and contain:
      - a match-like versus marker
      - a machine-readable datetime/timestamp
    This is deliberately conservative: no broadcaster mention => no event.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
    except Exception as exc:
        warn(f"{label} fetch failed: {exc}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    events = []

    selectors = (
        "article",
        "tr",
        "li",
        ".matchrow",
        ".match-row",
        ".schedule-row",
        ".event",
        ".post",
        ".card",
        ".news-item",
    )

    containers = []
    for sel in selectors:
        containers.extend(soup.select(sel))

    if not containers:
        containers = [
            d for d in soup.find_all("div")
            if len(norm(d.get_text(" ", strip=True))) <= 700
        ]

    seen = set()

    for node in containers:
        raw = norm(node.get_text(" ", strip=True))
        if not raw or raw in seen:
            continue
        seen.add(raw)

        if not _page_mentions_shasha(raw):
            continue

        if not re.search(r"(?:🆚|⚔️|⚔|\bVS\.?\b|\bV\.?\b|ضد)", raw, re.I):
            continue

        dt = _extract_machine_dt(node)
        if dt is None:
            continue

        title = _clean_match_title(raw)
        if not title:
            continue

        start = dt.astimezone(RIYADH)
        if not in_window(start):
            continue

        events.append({
            "title": title,
            "start": start,
            "competition": "",
            "source": label,
        })

    events = dedupe(events)
    log(f"{label}: {len(events)} SHASHA-confirmed listings")
    return events


def scrape_livefootballtv():
    return _extract_match_candidates_from_page(
        "LiveFootballTV",
        "https://www.livefootballtv.info/channel/shasha-tv",
    )


def scrape_365scores():
    """
    365Scores Arabic news hub. We only accept snippets/containers that
    explicitly mention SHASHA/شاشا.
    """
    return _extract_match_candidates_from_page(
        "365Scores Arabic",
        "https://www.365scores.com/ar/news",
    )


def scrape_kooora():
    """
    Kooora main page/news containers. No SHASHA mention => ignored.
    """
    return _extract_match_candidates_from_page(
        "Kooora",
        "https://www.kooora.com/",
    )


def scrape_goal():
    """
    Goal Arabic main page/news containers. No SHASHA mention => ignored.
    """
    return _extract_match_candidates_from_page(
        "Goal Arabic",
        "https://www.goal.com/ar",
    )



AR_MONTH_NUM = {
    "يناير": 1, "كانون الثاني": 1,
    "فبراير": 2, "شباط": 2,
    "مارس": 3, "آذار": 3,
    "أبريل": 4, "ابريل": 4, "نيسان": 4,
    "مايو": 5, "أيار": 5, "ايار": 5,
    "يونيو": 6, "حزيران": 6,
    "يوليو": 7, "تموز": 7,
    "أغسطس": 8, "اغسطس": 8, "آب": 8,
    "سبتمبر": 9, "أيلول": 9,
    "أكتوبر": 10, "اكتوبر": 10, "تشرين الأول": 10,
    "نوفمبر": 11, "تشرين الثاني": 11,
    "ديسمبر": 12, "كانون الأول": 12,
}


def _arabic_article_date(text):
    """
    Extract the schedule date from an Arabic article title/body.
    Example: القنوات الناقلة لمباريات اليوم الأحد 17 مايو 2026
    """
    t = norm(text)

    # ISO dates, sometimes embedded in headings.
    m = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", t)
    if m:
        try:
            return datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                0, 0, tzinfo=RIYADH
            ).date()
        except Exception:
            pass

    month_alt = "|".join(
        sorted((re.escape(x) for x in AR_MONTH_NUM), key=len, reverse=True)
    )
    m = re.search(
        rf"\b(\d{{1,2}})\s+({month_alt})\s+(20\d{{2}})\b",
        t,
        re.I,
    )
    if m:
        try:
            return datetime(
                int(m.group(3)),
                AR_MONTH_NUM[m.group(2)],
                int(m.group(1)),
                0, 0, tzinfo=RIYADH,
            ).date()
        except Exception:
            pass

    return None


def _parse_riyadh_time(text):
    """
    Extract Saudi/Makkah kickoff time from a table row.
    Handles:
      17:30 السعودية
      01:00 ظهرًا بتوقيت القاهرة ومكة
      5:00 بتوقيت مكة المكرمة
      9:45 مساءً بتوقيت مكة
    """
    t = norm(text)
    if not re.search(r"(?:السعودية|مكة|مكة المكرمة)", t):
        return None

    # Prefer the time immediately before Saudi/Makkah wording.
    patterns = [
        r"(\d{1,2}):(\d{2})\s*(صباحًا|صباحا|صباح|ظهرًا|ظهرا|عصرًا|عصرا|مساءً|مساء|am|pm)?"
        r"\s*(?:بتوقيت\s*)?(?:السعودية|مكة(?:\s*المكرمة)?)",
        # Goal often: 17:30 السعودية، 18:30 الإمارات
        r"(\d{1,2}):(\d{2})\s*(?:السعودية|مكة(?:\s*المكرمة)?)",
    ]

    matches = []
    for pat in patterns:
        matches.extend(list(re.finditer(pat, t, re.I)))

    if not matches:
        # Some 365 rows say: 4:00 القاهرة 5:00 مكة
        makkah_pos = max(t.find("مكة"), t.find("السعودية"))
        if makkah_pos >= 0:
            before = t[:makkah_pos]
            matches = list(re.finditer(
                r"(\d{1,2}):(\d{2})\s*(صباحًا|صباحا|صباح|ظهرًا|ظهرا|عصرًا|عصرا|مساءً|مساء|am|pm)?",
                before,
                re.I,
            ))

    if not matches:
        return None

    m = matches[-1]
    hh = int(m.group(1))
    mm = int(m.group(2))
    marker = (m.group(3) or "").casefold() if m.lastindex and m.lastindex >= 3 else ""

    if marker in ("pm", "مساءً", "مساء", "عصرًا", "عصرا", "ظهرًا", "ظهرا"):
        if 1 <= hh <= 11:
            hh += 12
    elif marker in ("am", "صباحًا", "صباحا", "صباح"):
        if hh == 12:
            hh = 0

    if 0 <= hh <= 23 and 0 <= mm <= 59:
        return hh, mm

    return None


def _match_title_from_text(text):
    t = norm(text)

    # Strip broadcaster/time tails before team extraction where possible.
    for sep in (" | ", "  "):
        if sep in t:
            t = t.split(sep, 1)[0].strip()

    patterns = [
        r"(.{2,70}?)\s*[×x]\s*(.{2,70}?)(?=\s+\d{1,2}:\d{2}|\s*$)",
        r"(.{2,70}?)\s+ضد\s+(.{2,70}?)(?=\s+\d{1,2}:\d{2}|\s*$)",
        r"(.{2,70}?)\s+-\s+(.{2,70}?)(?=\s+\d{1,2}:\d{2}|\s*$)",
    ]

    for pat in patterns:
        m = re.search(pat, t, re.I)
        if not m:
            continue

        a = norm(m.group(1))
        b = norm(m.group(2))

        # Avoid headings and obvious non-team text.
        bad = (
            "المباراة", "الموعد", "القنوات", "الناقلة", "جدول",
            "الدوري", "كأس", "الجولة", "المعلق"
        )
        if not a or not b:
            continue
        if any(x in a for x in bad) or any(x in b for x in ("القنوات الناقلة", "المعلق")):
            continue
        if len(a) > 70 or len(b) > 70:
            continue

        return f"{a} - {b}"

    return None


def _discover_article_links(label, index_urls, max_links=80):
    """
    Discover daily schedule/broadcaster articles from the site's own pages.
    This replaces the old mistake of trying to parse only the homepage itself.
    """
    found = []
    seen = set()

    keywords = (
        "القنوات-الناقلة",
        "القنوات_الناقلة",
        "مباريات-اليوم",
        "مباريات_اليوم",
        "جدول-مباريات",
        "جدول_مباريات",
        "القنوات الناقلة",
        "مباريات اليوم",
        "جدول مباريات",
    )

    for index_url in index_urls:
        try:
            r = requests.get(index_url, headers=HEADERS, timeout=25)
            r.raise_for_status()
        except Exception as exc:
            warn(f"{label} article index fetch failed: {index_url} | {exc}")
            continue

        soup = BeautifulSoup(r.text, "html.parser")

        for a in soup.find_all("a", href=True):
            href = urljoin(index_url, a.get("href"))
            anchor = norm(a.get_text(" ", strip=True))
            hay = f"{href} {anchor}".casefold()

            if not any(k.casefold() in hay for k in keywords):
                continue

            # Same site only.
            try:
                if urlparse(href).netloc != urlparse(index_url).netloc:
                    continue
            except Exception:
                continue

            if href in seen:
                continue
            seen.add(href)
            found.append(href)

            if len(found) >= max_links:
                break

        if len(found) >= max_links:
            break

    log(f"{label}: discovered {len(found)} schedule/broadcaster article links")
    return found


def _parse_shasha_article(label, url):
    """
    Open a daily broadcaster article and extract ONLY rows explicitly tied
    to SHASHA/شاشا. Supports table layouts where the broadcaster appears in
    a following row because of HTML rowspan formatting.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
    except Exception as exc:
        warn(f"{label} article fetch failed: {exc}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    # Date should come from article title/heading, not publication timestamp.
    heading = ""
    for sel in ("h1", "title"):
        node = soup.select_one(sel)
        if node:
            heading += " " + norm(node.get_text(" ", strip=True))
    article_day = _arabic_article_date(heading)

    if article_day is None:
        # Fallback: inspect first ~2000 visible chars.
        article_day = _arabic_article_date(
            norm(soup.get_text(" ", strip=True))[:2000]
        )

    if article_day is None:
        return []

    now = datetime.now(RIYADH)
    day_dt = datetime(
        article_day.year, article_day.month, article_day.day,
        12, 0, tzinfo=RIYADH
    )
    if not (
        now - timedelta(days=KEEP_DAYS_BACK)
        <= day_dt
        < now + timedelta(days=KEEP_DAYS_FORWARD + 1)
    ):
        return []

    events = []

    # First: HTML tables.
    for table in soup.find_all("table"):
        current_title = None
        current_time = None

        for tr in table.find_all("tr"):
            cells = [norm(x.get_text(" ", strip=True)) for x in tr.find_all(["th", "td"])]
            row = " | ".join(x for x in cells if x)
            if not row:
                continue

            title = _match_title_from_text(row)
            tm = _parse_riyadh_time(row)

            if title:
                current_title = title
            if tm:
                current_time = tm

            if not _page_mentions_shasha(row):
                continue

            use_title = title or current_title
            use_time = tm or current_time
            if not use_title or not use_time:
                continue

            hh, mm = use_time
            start = datetime(
                article_day.year, article_day.month, article_day.day,
                hh, mm, tzinfo=RIYADH
            )

            if not in_window(start):
                continue

            events.append({
                "title": use_title,
                "start": start,
                "competition": "",
                "source": f"{label}: {url}",
            })

    # Second: paragraph/list layouts used by some articles.
    blocks = soup.select("p, li, article div")
    current_title = None
    current_time = None

    for node in blocks:
        raw = norm(node.get_text(" ", strip=True))
        if not raw or len(raw) > 900:
            continue

        title = _match_title_from_text(raw)
        tm = _parse_riyadh_time(raw)

        if title:
            current_title = title
        if tm:
            current_time = tm

        if not _page_mentions_shasha(raw):
            continue

        use_title = title or current_title
        use_time = tm or current_time

        if not use_title or not use_time:
            continue

        hh, mm = use_time
        start = datetime(
            article_day.year, article_day.month, article_day.day,
            hh, mm, tzinfo=RIYADH
        )

        if not in_window(start):
            continue

        events.append({
            "title": use_title,
            "start": start,
            "competition": "",
            "source": f"{label}: {url}",
        })

    events = dedupe(events)
    if events:
        log(f"{label}: {len(events)} SHASHA fixtures from article: {url}")
    return events


def _scrape_article_source(label, index_urls, max_articles=40):
    links = _discover_article_links(label, index_urls, max_links=max_articles)
    events = []

    for url in links:
        events.extend(_parse_shasha_article(label, url))

    events = dedupe(events)
    log(f"{label}: {len(events)} SHASHA fixtures from discovered articles")
    return events


def scrape_365scores_articles():
    return _scrape_article_source(
        "365Scores Arabic",
        [
            "https://www.365scores.com/ar/news",
            "https://www.365scores.com/ar/news/magazine",
        ],
    )


def scrape_goal_articles():
    return _scrape_article_source(
        "Goal Arabic",
        [
            "https://www.goal.com/ar",
            "https://www.goal.com/ar/أخبار",
        ],
    )


def scrape_kooora_articles():
    return _scrape_article_source(
        "Kooora",
        [
            "https://www.kooora.com/القنوات-الناقلة/1g5ur1rolvxsy10zop276pqcmi",
            "https://www.kooora.com/كرة-القدم/مباريات-اليوم",
            "https://www.kooora.com/",
        ],
    )


def scrape_all_sources():
    """
    Correct strategy:
      1) Read dedicated SHASHA TV-listing pages.
      2) Discover daily broadcaster articles on 365Scores, Goal and Kooora.
      3) Open those articles and keep rows that explicitly say SHASHA/شاشا.
      4) Keep the rolling 10-day window.
      5) Never infer a SHASHA broadcast from a generic match list.
    """
    events = []

    # Dedicated broadcast guides.
    events.extend(scrape_livesoccertv())
    events.extend(scrape_livefootballtv())

    # Daily broadcaster articles (new strategy).
    events.extend(scrape_365scores_articles())
    events.extend(scrape_goal_articles())
    events.extend(scrape_kooora_articles())

    # SHASHA-owned sources remain supplemental only.
    events.extend(_generic_source_scrape(
        "SHASHA Official",
        "https://www.shasha.com/",
    ))
    events.extend(_generic_source_scrape(
        "SHASHA Sports Instagram",
        "https://www.instagram.com/shasha_sports/",
    ))
    events.extend(_generic_source_scrape(
        "SHASHA Sports X",
        "https://x.com/Shasha_Sports",
    ))

    events = dedupe(events)
    log(f"Combined SHASHA sources: {len(events)} unique programmes")
    return events

def read_existing():
    if not OUT.exists():
        return []

    try:
        root = ET.parse(OUT).getroot()
    except Exception as exc:
        warn(f"Existing Shasha guide unreadable: {exc}")
        return []

    events = []
    for p in root.findall("programme"):
        if p.get("channel") != CHANNEL_ID:
            continue

        raw_start = p.get("start") or ""
        try:
            start = datetime.strptime(
                raw_start[:14], "%Y%m%d%H%M%S"
            ).replace(tzinfo=RIYADH)
        except Exception:
            continue

        if not in_window(start):
            continue

        title_el = p.find("title")
        title = norm(title_el.text) if title_el is not None else ""
        if not title:
            continue

        events.append({
            "title": title,
            "start": start,
            "competition": "",
            "source": "existing XML",
        })

    return events


def merge(existing, fresh):
    """
    Rolling 10-day guide:
    - Keep previously published SHASHA fixtures while they remain inside the
      10-day future window, even if a source temporarily stops showing them.
    - Freshly published fixtures replace/update the same match+kickoff.
    - Old fixtures naturally expire once they leave the keep window.
    """
    merged = {event_key(e): e for e in existing}
    for e in fresh:
        merged[event_key(e)] = e

    kept = [e for e in merged.values() if in_window(e["start"])]
    return dedupe(kept)


def fmt_12(dt):
    hour = dt.hour
    ampm = "ص" if hour < 12 else "م"
    h = hour % 12
    if h == 0:
        h = 12
    return f"{h}:{dt.minute:02d} {ampm}"


def arabic_date(dt):
    return (
        f"{AR_DAYS[dt.weekday()]} "
        f"{dt.day} {AR_MONTHS[dt.month]} {dt.year}"
    )


def write_xml(events):
    tv = ET.Element(
        "tv",
        {"generator-info-name": "SHASHA Guide EPG"},
    )

    ch = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(ch, "display-name", {"lang": "ar"}).text = "SHASHA | Guide"
    ET.SubElement(ch, "display-name", {"lang": "en"}).text = "SHASHA | Guide"

    for e in events:
        riyadh = e["start"].astimezone(RIYADH)
        vegas = e["start"].astimezone(VEGAS)
        stop = riyadh + timedelta(hours=3)

        p = ET.SubElement(
            tv,
            "programme",
            {
                "start": riyadh.strftime("%Y%m%d%H%M%S %z"),
                "stop": stop.strftime("%Y%m%d%H%M%S %z"),
                "channel": CHANNEL_ID,
            },
        )

        ET.SubElement(p, "title", {"lang": "ar"}).text = e["title"]
        ET.SubElement(p, "category", {"lang": "en"}).text = "Sports"

        lines = [
            f"📅 {arabic_date(riyadh)}",
            f"🕘 توقيت مكة: {fmt_12(riyadh)}",
            f"🕘 توقيت لاس فيغاس: {fmt_12(vegas)}",
        ]

        if e.get("competition"):
            lines.append(f"🏆 {e['competition']}")

        if e.get("source"):
            lines.append(f"🔎 المصدر: {e['source']}")

        lines.append("📺 استخدم هذا الـGuide مع قنوات SHASHA 1 / 2 / 3.")

        ET.SubElement(
            p,
            "desc",
            {"lang": "ar"},
        ).text = "\n".join(lines)

    ET.indent(tv, space="  ")
    ET.ElementTree(tv).write(
        OUT,
        encoding="utf-8",
        xml_declaration=True,
    )


def main():
    existing = read_existing()
    auto = scrape_all_sources()
    manual = parse_manual()
    fresh = dedupe(auto + manual)

    log(f"Existing SHASHA Guide programmes kept: {len(existing)}")
    log("SHASHA rolling guide window: next 10 days")
    log(f"Fresh SHASHA Guide programmes: {len(fresh)}")

    merged = merge(existing, fresh)

    # Preserve old guide if the automatic source is temporarily empty.
    if not fresh and existing:
        warn("No fresh SHASHA listings; existing XML preserved.")
        return

    write_xml(merged)
    log(f"SHASHA Guide total programmes: {len(merged)}")
    log(f"Written: {OUT}")


if __name__ == "__main__":
    main()
