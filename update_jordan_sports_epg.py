#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone, date
from html import unescape
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup


OUTPUT = "jordan_sports_epg.xml"

CHANNEL_ID = "JordanSports"
CHANNEL_NAME = "Jordan Sport | الأردن الرياضية"

AMMAN = ZoneInfo("Asia/Amman")
ABU_DHABI = ZoneInfo("Asia/Dubai")
LAS_VEGAS = ZoneInfo("America/Los_Angeles")
UTC = timezone.utc

DAYS_BACK = 1
DAYS_FORWARD = 21
HTTP_TIMEOUT = 20

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)

# Official JRTV homepage currently publishes programme cards including:
# "رياضة كافيه - يوم الثلاثاء الساعة 5:00 مساءً".
JRTV_HOME = "https://www.jrtv.gov.jo/"

# Channel-specific football listing. It is intentionally used only when the
# match row explicitly belongs to Jordan Sports.
LFTV_JORDAN_SPORTS = "https://www.livefootballtv.info/channel/jordan-sports"

JFA_SUPER_CUP = (
    "https://jfa.jo/tourn.php?id=10&idcat=6&idsubcat=34&"
    "title=%D9%83%D8%A3%D8%B3-%D8%A7%D9%84%D8%B3%D9%88%D8%A8%D8%B1"
)
SPORT24_SUPER_CUP = "https://www.sport24.rest/competition/18668"
SPORT24_BASE = "https://www.sport24.rest"

session = requests.Session()
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
})


def log(msg: str) -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    print(f"WARN {msg}", flush=True)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(s or "")).strip()


def utc_now() -> datetime:
    return datetime.now(UTC)


def window_bounds():
    now = utc_now()
    start = (now - timedelta(days=DAYS_BACK)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end = (now + timedelta(days=DAYS_FORWARD + 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start, end


def in_window(dt_utc: datetime) -> bool:
    start, end = window_bounds()
    return start <= dt_utc < end


def fetch_text(url: str) -> str:
    r = session.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.text


def xmltv_time(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%d%H%M%S +0000")


# ---------------------------------------------------------------------------
# Official JRTV recurring programme parsing
# ---------------------------------------------------------------------------

AR_WEEKDAYS = {
    "الاثنين": 0,
    "الثلاثاء": 1,
    "الأربعاء": 2,
    "الاربعاء": 2,
    "الخميس": 3,
    "الجمعة": 4,
    "السبت": 5,
    "الأحد": 6,
    "الاحد": 6,
}

# We keep the accepted programme list deliberately conservative. More titles
# can be added only after JRTV itself publishes a stable schedule for them.
KNOWN_JRTV_SPORT_PROGRAMMES = {
    "رياضة كافيه",
}

# Official JRTV schedule verified on 2026-08-19.
# This is used only when the JRTV JavaScript shell hides programme cards
# from a normal HTTP client. Keeping it explicit is safer than inventing
# additional programme times.
OFFICIAL_JRTV_FALLBACK = [
    {
        "title": "رياضة كافيه",
        "weekday": 1,          # Tuesday
        "hour": 17,
        "minute": 0,
        "duration_minutes": 60,
        "source_name": "JRTVOfficialFallback",
        "source": JRTV_HOME,
        "category": "Sports Programme",
    },
]

JRTV_PROGRAM_RE = re.compile(
    r"(?P<title>رياضة\s+كافيه).*?"
    r"(?:يوم\s+)?(?P<weekday>الاثنين|الثلاثاء|الأربعاء|الاربعاء|الخميس|الجمعة|السبت|الأحد|الاحد)"
    r".*?الساعة\s+"
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*"
    r"(?P<ampm>صباح(?:اً|ا)?|مساء(?:ً|ا)?)",
    re.S,
)


def parse_official_jrtv_programmes(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    text = norm(soup.get_text(" ", strip=True))
    recurring: list[dict] = []

    for m in JRTV_PROGRAM_RE.finditer(text):
        title = norm(m.group("title"))
        if title not in KNOWN_JRTV_SPORT_PROGRAMMES:
            continue

        weekday_name = m.group("weekday")
        weekday = AR_WEEKDAYS[weekday_name]
        hh = int(m.group("hour"))
        mm = int(m.group("minute") or 0)
        ampm = m.group("ampm")

        if "مساء" in ampm:
            if hh != 12:
                hh += 12
        elif hh == 12:
            hh = 0

        recurring.append({
            "title": title,
            "weekday": weekday,
            "hour": hh,
            "minute": mm,
            "duration_minutes": 60,
            "source_name": "JRTVOfficial",
            "source": JRTV_HOME,
            "category": "Sports Programme",
        })

    # Deduplicate identical recurring cards if the homepage repeats them.
    seen = set()
    out = []
    for item in recurring:
        key = (
            item["title"],
            item["weekday"],
            item["hour"],
            item["minute"],
        )
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def get_official_jrtv_recurring(html: str) -> tuple[list[dict], str]:
    """
    Prefer live parsing from JRTV. If JRTV serves only its JavaScript app shell
    to requests/GitHub Actions, use the single currently verified official
    recurring sports slot instead of returning an empty guide.
    """
    parsed = parse_official_jrtv_programmes(html)
    if parsed:
        return parsed, "live"

    shell_markers = (
        "you need to enable javascript",
        '<div id="root"',
        '<div id="app"',
    )
    low = html.casefold()
    shell_only = any(marker in low for marker in shell_markers)

    # JRTV is currently a JS-rendered site, so a zero-result HTML response is
    # not evidence that the published programme was removed. Use only the
    # explicitly verified official fallback; never invent other programmes.
    if shell_only or not parsed:
        return [dict(x) for x in OFFICIAL_JRTV_FALLBACK], "fallback"

    return [], "none"


def expand_recurring_programmes(recurring: list[dict]) -> list[dict]:
    start, end = window_bounds()
    first_local = start.astimezone(AMMAN).date() - timedelta(days=1)
    last_local = end.astimezone(AMMAN).date() + timedelta(days=1)

    events: list[dict] = []
    d = first_local
    while d <= last_local:
        for item in recurring:
            if d.weekday() != item["weekday"]:
                continue
            local = datetime(
                d.year, d.month, d.day,
                item["hour"], item["minute"],
                tzinfo=AMMAN,
            )
            start_utc = local.astimezone(UTC)
            if not in_window(start_utc):
                continue
            events.append({
                "start": start_utc,
                "title": item["title"],
                "category": item["category"],
                "source_name": item["source_name"],
                "source": item["source"],
                "duration_minutes": item["duration_minutes"],
                "priority": 100,
            })
        d += timedelta(days=1)
    return events


# ---------------------------------------------------------------------------
# Jordan Sports football listings
# ---------------------------------------------------------------------------

DATE_NUMERIC = re.compile(
    r"(?:(?:today|tomorrow)\s+)?"
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s*"
    r"(\d{1,2})/(\d{1,2})/(20\d{2})",
    re.I,
)

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

BAD_TEXT = re.compile(
    r"^(?:live football on|football on tv|change to your time zone|"
    r"ranking by|statistical data|number of|view full ranking|"
    r"as of today|in this moment|the next match|"
    r"image:|button:|menu|teams|competitions|tv channels|news|free widget|"
    r"arab mena|all teams|all competitions|all channels|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
    re.I,
)

STAGE_TEXT = re.compile(
    r"^(?:playoffs?|final|semi-?finals?|quarter-?finals?|"
    r"group stage|round of \d+|qualifiers?|friendly)$",
    re.I,
)

BROADCASTER_HINTS = re.compile(
    r"(?:sport|sports|tv|youtube|app|bein|dazn|alkass|الكأس|"
    r"ssc|jordan fa|ppv)",
    re.I,
)


def parse_lftv_date(line: str) -> date | None:
    s = norm(line)
    m = DATE_NUMERIC.search(s)
    if m:
        dd, mm, yy = map(int, m.groups())
        try:
            return date(yy, mm, dd)
        except ValueError:
            return None

    if "football on tv today" in s.casefold():
        m = re.search(r"(\d{1,2})/(\d{1,2})/(20\d{2})", s)
        if m:
            dd, mm, yy = map(int, m.groups())
            try:
                return date(yy, mm, dd)
            except ValueError:
                return None
    return None


def _clean_lftv_line(s: str) -> str:
    return re.sub(r"^Image:\s*", "", norm(s), flags=re.I)


def _plausible_name(s: str) -> bool:
    if not s or len(s) > 80:
        return False
    if BAD_TEXT.search(s) or TIME_RE.match(s) or s.isdigit():
        return False
    return True


def _extract_match_block(block: list[str]) -> tuple[str, str, str] | None:
    cleaned = [_clean_lftv_line(x) for x in block]
    cleaned = [x for x in cleaned if x and _plausible_name(x)]

    # Require an explicit Jordan Sports broadcaster marker in this row.
    channel_idx = next(
        (
            i for i, x in enumerate(cleaned)
            if x.casefold() in {
                "jordan sports",
                "jordan tv sport",
                "jordan sport",
            }
        ),
        None,
    )
    if channel_idx is None:
        return None

    # Everything before the first broadcaster-like field belongs to the
    # competition/stage/teams section.
    first_broadcaster = next(
        (
            i for i, x in enumerate(cleaned[:channel_idx + 1])
            if BROADCASTER_HINTS.search(x)
        ),
        channel_idx,
    )

    core = cleaned[:first_broadcaster]
    if len(core) < 3:
        core = [
            x for x in cleaned[:channel_idx]
            if not BROADCASTER_HINTS.search(x)
        ]
    if len(core) < 3:
        return None

    non_stage = [x for x in core if not STAGE_TEXT.match(x)]
    if len(non_stage) < 3:
        return None

    home, away = non_stage[-2], non_stage[-1]
    competition = non_stage[-3]

    if home.casefold() == away.casefold():
        return None
    if BROADCASTER_HINTS.search(home) or BROADCASTER_HINTS.search(away):
        return None

    return norm(competition), norm(home), norm(away)


def parse_lftv_jordan_sports(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    lines = [norm(x) for x in soup.stripped_strings if norm(x)]
    events: list[dict] = []
    current_date: date | None = None

    i = 0
    while i < len(lines):
        d = parse_lftv_date(lines[i])
        if d:
            current_date = d
            i += 1
            continue

        tm = TIME_RE.match(lines[i])
        if not tm or current_date is None:
            i += 1
            continue

        hh, mm = map(int, tm.groups())
        block: list[str] = []
        j = i + 1

        while j < len(lines) and j <= i + 30:
            if TIME_RE.match(lines[j]) or parse_lftv_date(lines[j]):
                break
            block.append(lines[j])
            j += 1

        parsed = _extract_match_block(block)
        if parsed:
            competition, home, away = parsed

            # livefootballtv.info's Arab-MENA guide is interpreted in the
            # broadcaster's local wall-clock here. The EPG stores UTC after
            # converting from Asia/Amman, so TiviMate can convert correctly.
            local = datetime(
                current_date.year,
                current_date.month,
                current_date.day,
                hh, mm,
                tzinfo=AMMAN,
            )
            start_utc = local.astimezone(UTC)

            if in_window(start_utc):
                events.append({
                    "start": start_utc,
                    "title": f"{home} - {away}",
                    "category": competition,
                    "source_name": "LiveFootballTV",
                    "source": LFTV_JORDAN_SPORTS,
                    "duration_minutes": 135,
                    "priority": 200,
                })

        i = max(i + 1, j)

    return dedupe(events)



# ---------------------------------------------------------------------------
# JFA official fixture + Sport24 Jordan Sports confirmation
# ---------------------------------------------------------------------------

AR_MONTHS = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "ابريل": 4,
    "مايو": 5, "يونيو": 6, "يوليو": 7, "أغسطس": 8, "اغسطس": 8,
    "سبتمبر": 9, "أكتوبر": 10, "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}


def _team_key(s: str) -> str:
    s = norm(s).casefold()
    s = s.replace("إ", "ا").replace("أ", "ا").replace("آ", "ا")
    s = s.replace("ة", "ه").replace("ى", "ي")
    s = re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", s)
    s = norm(s)
    aliases = {
        "الحسين اربد": "الحسين",
        "نادي الوحدات": "الوحدات",
        "al wehdat": "الوحدات",
        "al faisaly": "الفيصلي",
        "al faysali": "الفيصلي",
        "al ramtha": "الرمثا",
        "al hussein irbid": "الحسين",
    }
    return aliases.get(s, s)


def parse_jfa_super_cup(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    raw = re.sub(r"\s+", " ", unescape(soup.get_text(" | ", strip=True)))
    rx = re.compile(
        r"([\u0600-\u06ffA-Za-z][^|]{1,55})\s*\|\s*"
        r"(?:[^|]*\|\s*){0,3}VS\s*\|\s*"
        r"(?:[^|]*\|\s*){0,3}([\u0600-\u06ffA-Za-z][^|]{1,55})"
        r".{0,260}?(\d{4}-\d{2}-\d{2})\s*-\s*(\d{1,2}:\d{2})",
        re.I,
    )

    events = []
    for m in rx.finditer(raw):
        home = norm(m.group(1))
        away = norm(m.group(2))
        if not home or not away or home == away:
            continue

        try:
            d = datetime.strptime(m.group(3), "%Y-%m-%d").date()
            hh, mm = map(int, m.group(4).split(":"))
            local = datetime(d.year, d.month, d.day, hh, mm, tzinfo=AMMAN)
        except Exception:
            continue

        start_utc = local.astimezone(UTC)
        if not in_window(start_utc):
            continue

        events.append({
            "start": start_utc,
            "date": d,
            "home": home,
            "away": away,
            "title": f"{home} - {away}",
            "category": "كأس السوبر الأردني",
            "source_name": "JFAOfficial",
            "source": JFA_SUPER_CUP,
            "duration_minutes": 135,
            "priority": 350,
        })

    return events


def _sport24_date_from_text(text: str) -> date | None:
    m = re.search(
        r"(\d{1,2})\s+(" + "|".join(map(re.escape, AR_MONTHS)) + r")\s+(20\d{2})",
        text,
    )
    if not m:
        return None
    try:
        return date(int(m.group(3)), AR_MONTHS[m.group(2)], int(m.group(1)))
    except ValueError:
        return None


def discover_sport24_super_cup_matches(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not re.search(r"/match/\d+", href):
            continue
        if href.startswith("/"):
            href = SPORT24_BASE + href
        elif not href.startswith("http"):
            href = SPORT24_BASE + "/" + href.lstrip("/")
        if href not in seen:
            seen.add(href)
            urls.append(href)
    return urls


def parse_sport24_jordan_confirmation(html: str, url: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    text = norm(soup.get_text(" ", strip=True))

    if "الأردن الرياضية" not in text:
        return None

    d = _sport24_date_from_text(text)
    if d is None:
        return None

    h1 = soup.find("h1")
    heading = norm(h1.get_text(" ", strip=True) if h1 else "")
    m = re.search(
        r"مباراة\s+(.+?)\s+(?:و|–|-)\s*(.+?)\s+في\s+كأس\s+السوبر",
        heading,
    )
    if not m:
        m = re.search(r"مباراة\s+(.+?)\s+مع\s+نظيره\s+(.+?)\s+في\s+لقاء", text)
    if not m:
        return None

    return {
        "date": d,
        "home": norm(m.group(1)),
        "away": norm(m.group(2)),
        "source": url,
    }


def get_jfa_sport24_confirmed_super_cup() -> list[dict]:
    official = parse_jfa_super_cup(fetch_text(JFA_SUPER_CUP))
    log(f"JFA Super Cup upcoming fixtures detected: {len(official)}")

    match_urls = discover_sport24_super_cup_matches(fetch_text(SPORT24_SUPER_CUP))
    log(f"Sport24 Super Cup match pages discovered: {len(match_urls)}")

    confirmations = []
    for url in match_urls:
        try:
            c = parse_sport24_jordan_confirmation(fetch_text(url), url)
            if c:
                confirmations.append(c)
                log(
                    f"SPORT24 JORDAN SPORTS CONFIRMATION | "
                    f"{c['date']} | {c['home']} - {c['away']}"
                )
        except Exception as exc:
            warn(f"Sport24 match confirmation failed: {url} | {exc}")

    out = []
    for ev in official:
        eh, ea = _team_key(ev["home"]), _team_key(ev["away"])
        matched = None
        for c in confirmations:
            if c["date"] != ev["date"]:
                continue
            ch, ca = _team_key(c["home"]), _team_key(c["away"])
            if (eh == ch and ea == ca) or (eh == ca and ea == ch):
                matched = c
                break

        if matched:
            ev = dict(ev)
            ev["source_name"] = "JFAOfficial+Sport24JordanSports"
            ev["source"] = f"{JFA_SUPER_CUP} | {matched['source']}"
            out.append(ev)
            am = ev["start"].astimezone(AMMAN)
            log(
                f"CONFIRMED JORDAN SPORTS | {am:%Y-%m-%d %H:%M} Amman | "
                f"{ev['title']} | كأس السوبر الأردني"
            )
        else:
            log(
                f"NOT ADDED - no Jordan Sports confirmation | "
                f"{ev['date']} | {ev['title']}"
            )

    return out


# ---------------------------------------------------------------------------
# Event handling / XML
# ---------------------------------------------------------------------------

def event_key(ev: dict) -> str:
    start = ev["start"].astimezone(UTC).replace(second=0, microsecond=0)
    title = re.sub(
        r"[^a-z0-9\u0600-\u06ff]+",
        " ",
        ev["title"].casefold(),
    )
    return f"{start:%Y%m%d%H%M}|{norm(title)}"


def dedupe(events: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for ev in events:
        k = event_key(ev)
        old = best.get(k)
        if old is None or ev.get("priority", 0) > old.get("priority", 0):
            best[k] = ev
    return sorted(best.values(), key=lambda x: x["start"])


def collect_events() -> list[dict]:
    events: list[dict] = []

    # Official ordinary programme(s)
    try:
        jrtv_html = fetch_text(JRTV_HOME)
        recurring, mode = get_official_jrtv_recurring(jrtv_html)
        log(
            f"JRTV official recurring sports programmes detected: "
            f"{len(recurring)} | mode={mode}"
        )
        for item in recurring:
            log(
                f"  JRTV | {item['title']} | weekday={item['weekday']} | "
                f"{item['hour']:02d}:{item['minute']:02d} Amman | "
                f"{item['source_name']}"
            )
        events.extend(expand_recurring_programmes(recurring))
    except Exception as exc:
        warn(f"JRTV official programme fetch failed: {exc}")
        # Network failure must not erase a schedule that was explicitly
        # verified from JRTV. Use only the documented fallback.
        recurring = [dict(x) for x in OFFICIAL_JRTV_FALLBACK]
        log(
            f"JRTV fallback recurring sports programmes used after fetch error: "
            f"{len(recurring)}"
        )
        events.extend(expand_recurring_programmes(recurring))

    # Official JFA fixtures cross-confirmed as Jordan Sports broadcasts.
    try:
        jfa_confirmed = get_jfa_sport24_confirmed_super_cup()
        log(
            f"JFA + Sport24 confirmed Jordan Sports matches detected: "
            f"{len(jfa_confirmed)}"
        )
        events.extend(jfa_confirmed)
    except Exception as exc:
        warn(f"JFA/Sport24 cross-confirmation failed: {exc}")

    # Confirmed football matches from LiveFootballTV
    try:
        football = parse_lftv_jordan_sports(fetch_text(LFTV_JORDAN_SPORTS))
        log(f"Jordan Sports confirmed football matches detected: {len(football)}")
        events.extend(football)
    except Exception as exc:
        warn(f"Jordan Sports football parsing failed: {exc}")

    return dedupe(events)


def build_day_description(d: date, events: list[dict]) -> str:
    if not events:
        return (
            f"الأردن الرياضية | {d.isoformat()}\n\n"
            "لا يوجد برنامج أو مباراة بموعد موثق في المصادر الحالية."
        )

    lines = [f"جدول الأردن الرياضية | {d.isoformat()}", ""]
    for ev in sorted(events, key=lambda x: x["start"]):
        am = ev["start"].astimezone(AMMAN)
        ad = ev["start"].astimezone(ABU_DHABI)
        lv = ev["start"].astimezone(LAS_VEGAS)
        lines.append(f"• {ev['title']} — {ev['category']}")
        lines.append(
            f"  {am:%H:%M} الأردن | "
            f"{ad:%H:%M} أبو ظبي | "
            f"{lv:%H:%M} لاس فيغاس"
        )
    return "\n".join(lines)


def add_programme(
    root,
    start: datetime,
    stop: datetime,
    title: str,
    desc: str,
    category: str = "Sports",
):
    p = ET.SubElement(
        root,
        "programme",
        start=xmltv_time(start),
        stop=xmltv_time(stop),
        channel=CHANNEL_ID,
    )
    ET.SubElement(p, "title", lang="ar").text = title
    ET.SubElement(p, "desc", lang="ar").text = desc
    ET.SubElement(p, "category", lang="en").text = category


def write_xml(events: list[dict]) -> None:
    root = ET.Element(
        "tv",
        generator_info_name="Jordan Sports conservative EPG",
    )

    ch = ET.SubElement(root, "channel", id=CHANNEL_ID)
    ET.SubElement(ch, "display-name", lang="ar").text = CHANNEL_NAME
    ET.SubElement(ch, "display-name", lang="en").text = "Jordan Sport"

    today_amman = utc_now().astimezone(AMMAN).date()
    first_day = today_amman - timedelta(days=DAYS_BACK)
    last_day = today_amman + timedelta(days=DAYS_FORWARD)

    by_day: dict[date, list[dict]] = {}
    for ev in events:
        d = ev["start"].astimezone(AMMAN).date()
        by_day.setdefault(d, []).append(ev)

    for off in range((last_day - first_day).days + 1):
        d = first_day + timedelta(days=off)
        day_events = sorted(by_day.get(d, []), key=lambda x: x["start"])
        desc = build_day_description(d, day_events)

        day_start_local = datetime(
            d.year, d.month, d.day, 0, 0, tzinfo=AMMAN
        )
        day_end_local = day_start_local + timedelta(days=1)
        day_start = day_start_local.astimezone(UTC)
        day_end = day_end_local.astimezone(UTC)

        if not day_events:
            add_programme(
                root,
                day_start,
                day_end,
                "الأردن الرياضية",
                desc,
                category="Sports",
            )
            continue

        cursor = day_start

        for ev in day_events:
            ev_start = ev["start"].astimezone(UTC)

            # If a live match overlaps a lower-priority ordinary programme,
            # the higher-priority event starts at its actual time; XML remains
            # non-overlapping by trimming/skipping the filler around it.
            if ev_start > cursor:
                add_programme(
                    root,
                    cursor,
                    ev_start,
                    "الأردن الرياضية",
                    desc,
                    category="Sports",
                )

            duration = int(ev.get("duration_minutes", 60))
            ev_stop = min(
                ev_start + timedelta(minutes=duration),
                day_end,
            )
            if ev_stop <= cursor:
                continue

            if ev_start < cursor:
                ev_start = cursor

            am = ev_start.astimezone(AMMAN)
            title = f"{ev['title']} | {am:%H:%M} الأردن"

            add_programme(
                root,
                ev_start,
                ev_stop,
                title,
                desc,
                category=ev["category"],
            )
            cursor = max(cursor, ev_stop)

        if cursor < day_end:
            add_programme(
                root,
                cursor,
                day_end,
                "الأردن الرياضية",
                desc,
                category="Sports",
            )

    try:
        ET.indent(root, space="  ")
    except AttributeError:
        pass

    ET.ElementTree(root).write(
        OUTPUT,
        encoding="utf-8",
        xml_declaration=True,
    )

    # Refuse to silently produce malformed XML.
    ET.parse(OUTPUT)
    log(f"Written and XML-validated: {OUTPUT}")


# ---------------------------------------------------------------------------
# Offline self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    jrtv_sample = """
    <html><body>
    <div>رياضة كافيه . يوم الثلاثاء الساعة 5:00 مساءً. رياضي</div>
    </body></html>
    """
    recurring = parse_official_jrtv_programmes(jrtv_sample)
    assert len(recurring) == 1
    assert recurring[0]["title"] == "رياضة كافيه"
    assert recurring[0]["weekday"] == 1
    assert recurring[0]["hour"] == 17
    assert recurring[0]["minute"] == 0

    shell_sample = """
    <html><body><div id="root"></div>
    <p>You need to enable JavaScript to run this app.</p></body></html>
    """
    fallback, mode = get_official_jrtv_recurring(shell_sample)
    assert mode == "fallback"
    assert len(fallback) == 1
    assert fallback[0]["title"] == "رياضة كافيه"
    assert fallback[0]["weekday"] == 1
    assert fallback[0]["hour"] == 17

    lftv_sample = """
    <html><body>
    <div>Football on TV today wednesday, 19/08/2026</div>
    <div>20:45</div>
    <div>Jordan League</div>
    <div>Al Faisaly</div>
    <div>Al Wihdat</div>
    <div>Jordan Sports</div>
    </body></html>
    """

    old_in_window = globals()["in_window"]
    try:
        globals()["in_window"] = lambda dt: True
        matches = parse_lftv_jordan_sports(lftv_sample)
    finally:
        globals()["in_window"] = old_in_window

    assert len(matches) == 1
    assert matches[0]["title"] == "Al Faisaly - Al Wihdat"
    assert matches[0]["category"] == "Jordan League"
    assert matches[0]["start"].astimezone(AMMAN).hour == 20
    assert matches[0]["start"].astimezone(AMMAN).minute == 45

    log("SELF TEST | PASS")


def main():
    log(
        "JORDAN SPORTS EPG | JRTV + JFA official fixtures + Sport24 broadcaster confirmation "
        "+ LiveFootballTV backup | NO INVENTED PROGRAMME TIMES"
    )

    _self_test()
    events = collect_events()

    log(f"Jordan Sports total verified timed events: {len(events)}")
    for ev in events:
        am = ev["start"].astimezone(AMMAN)
        ad = ev["start"].astimezone(ABU_DHABI)
        lv = ev["start"].astimezone(LAS_VEGAS)
        log(
            f"  JORDAN SPORTS | {am:%Y-%m-%d %H:%M} الأردن | "
            f"{ad:%Y-%m-%d %H:%M} أبو ظبي | "
            f"{lv:%Y-%m-%d %H:%M} لاس فيغاس | "
            f"{ev['title']} | {ev['source_name']}"
        )

    write_xml(events)


if __name__ == "__main__":
    main()
