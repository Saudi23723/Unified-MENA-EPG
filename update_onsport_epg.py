#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone, date
from html import unescape
from urllib.parse import urljoin
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup


OUTPUT = "onsport_epg.xml"

CAIRO = ZoneInfo("Africa/Cairo")
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

CHANNELS = {
    "ONSport1": {"name": "ON Sport 1"},
    "ONSport2": {"name": "ON Sport 2"},
    "ONSportMAX": {"name": "ON Sport MAX"},
    "ONSportPLUS": {"name": "ON Sport PLUS"},
}

# Channel-specific schedule pages: useful for confirmed non-league football
# and as a secondary source when a fixture is explicitly listed on that page.
LIVEFOOTBALLTV = {
    "ONSport1": "https://www.livefootballtv.info/channel/on-sport-1",
    "ONSport2": "https://www.livefootballtv.info/channel/on-sport-2",
    "ONSportMAX": "https://www.livefootballtv.info/channel/on-sport-max",
    "ONSportPLUS": "https://www.livefootballtv.info/channel/on-sport-plus",
}

# Dynamic discovery of current Egyptian Premier League broadcast-assignment
# articles. These articles explicitly list the match, kickoff and channel.
FILGOAL_EGYPT_SECTION = (
    "https://www.filgoal.com/section/88/articles/"
    "%D8%A7%D9%84%D8%AF%D9%88%D8%B1%D9%8A-%D8%A7%D9%84%D9%85%D8%B5%D8%B1%D9%8A"
)

# Official Egyptian Pro League site. Used as a validation source where the
# relevant team/match page can be discovered and parsed.
EPL_HOME = "https://www.egyptianproleague.com/"

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


def ar_norm(s: str) -> str:
    s = norm(s)
    trans = str.maketrans({
        "أ": "ا", "إ": "ا", "آ": "ا",
        "ة": "ه", "ى": "ي",
        "ؤ": "و", "ئ": "ي",
        "ـ": "",
    })
    s = s.translate(trans)
    s = re.sub(r"[\u064b-\u065f\u0670]", "", s)
    s = re.sub(r"[^\w\u0600-\u06ff]+", " ", s, flags=re.UNICODE)
    return norm(s).casefold()


TEAM_ALIASES = {
    ar_norm("الأهلي"): "الاهلي",
    ar_norm("الاهل"): "الاهلي",
    ar_norm("نادي الأهلي"): "الاهلي",
    ar_norm("الزمالك"): "الزمالك",
    ar_norm("الاتحاد السكندري"): "الاتحاد السكندري",
    ar_norm("زد"): "زد",
    ar_norm("زد إف سي"): "زد",
    ar_norm("وادي دجلة"): "وادي دجله",
    ar_norm("البنك الأهلي"): "البنك الاهلي",
    ar_norm("أبو قير للأسمدة"): "ابو قير للاسمده",
    ar_norm("بترول أسيوط"): "بترول اسيوط",
    ar_norm("منتخب السويس بتروجت"): "منتخب السويس بتروجت",
    ar_norm("م.السـويس بتروجت"): "منتخب السويس بتروجت",
    ar_norm("بتروجت"): "منتخب السويس بتروجت",
    ar_norm("طلائع الجيش"): "طلايع الجيش",
    ar_norm("المقاولون العرب"): "المقاولون العرب",
    ar_norm("المصري"): "المصري",
    ar_norm("سموحة"): "سموحه",
    ar_norm("غزل المحلة"): "غزل المحله",
    ar_norm("بيراميدز"): "بيراميدز",
    ar_norm("الجونة"): "الجونه",
    ar_norm("مودرن سبورت"): "مودرن سبورت",
    ar_norm("سيراميكا كليوباترا"): "سيراميكا كليوباترا",
    ar_norm("القناة"): "القناه",
    ar_norm("الشرقية إنبي"): "الشرقيه انبي",
}


def canonical_team(s: str) -> str:
    n = ar_norm(s)
    return TEAM_ALIASES.get(n, n)


DISPLAY_TEAM_ALIASES = {
    canonical_team("الأهل"): "الأهلي",
    canonical_team("الاهل"): "الأهلي",
    canonical_team("م.السـويس بتروجت"): "منتخب السويس بتروجت",
    canonical_team("بتروجت"): "منتخب السويس بتروجت",
}


def display_team(s: str) -> str:
    return DISPLAY_TEAM_ALIASES.get(canonical_team(s), norm(s))


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


AR_MONTHS = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "ابريل": 4, "أبريل": 4,
    "مايو": 5, "يونيو": 6, "يوليو": 7, "اغسطس": 8, "أغسطس": 8,
    "سبتمبر": 9, "اكتوبر": 10, "أكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}

EN_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def channel_from_arabic(label: str) -> str | None:
    n = ar_norm(label)
    # Explicit numbered/special channels first.
    if "ماكس" in n or "max" in n:
        return "ONSportMAX"
    if "بلس" in n or "plus" in n:
        return "ONSportPLUS"
    if re.search(r"(?:^|\s)2(?:\s|$)", n):
        return "ONSport2"
    if re.search(r"(?:^|\s)1(?:\s|$)", n):
        return "ONSport1"

    # FilGoal's current round articles call the primary linear channel simply
    # "أون سبورت" and use "أون سبورت ماكس" for the simultaneous secondary
    # match. The primary linear feed is ON Sport 1.
    if "اون سبورت" in n or "on sport" in n:
        return "ONSport1"
    return None


def event_key(ev: dict) -> str:
    start = ev["start"].astimezone(UTC).replace(second=0, microsecond=0)
    teams = sorted([canonical_team(ev["home"]), canonical_team(ev["away"])])
    return (
        f"{ev['channel_id']}|{start:%Y%m%d%H%M}|"
        f"{teams[0]}|{teams[1]}"
    )


SOURCE_PRIORITY = {
    "FilGoal+EPL": 130,
    "FilGoal": 120,
    "LiveFootballTV": 100,
}


def dedupe(events: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for ev in events:
        k = event_key(ev)
        old = best.get(k)
        if old is None or SOURCE_PRIORITY.get(ev["source_name"], 0) > SOURCE_PRIORITY.get(old["source_name"], 0):
            best[k] = ev
    return sorted(best.values(), key=lambda x: (x["channel_id"], x["start"]))


# ---------------------------------------------------------------------------
# FilGoal: current Egyptian Premier League channel assignments
# ---------------------------------------------------------------------------

def discover_filgoal_assignment_articles() -> list[str]:
    html = fetch_text(FILGOAL_EGYPT_SECTION)
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []

    for a in soup.find_all("a", href=True):
        text = norm(a.get_text(" ", strip=True))
        n = ar_norm(text)
        if "القنوات الناقله" not in n:
            continue
        if "الدوري المصري" not in n:
            continue
        href = urljoin(FILGOAL_EGYPT_SECTION, a["href"])
        if href not in urls:
            urls.append(href)

    return urls[:8]


AR_DAY_HEADER_RE = re.compile(
    r"^(?:الجمعة|السبت|الأحد|الاحد|الاثنين|الثلاثاء|الأربعاء|الاربعاء|الخميس)"
    r"\s+(\d{1,2})\s+([اأإآء-ي]+)"
    r"(?:\s+(20\d{2}))?\s*:?\s*$"
)

FILGOAL_MATCH_RE = re.compile(
    r"[-–—]*\s*"
    r"(.+?)\s+ضد\s+(.+?)"
    r"\s*[–—-]\s*"
    r"الساعة\s+(\d{1,2})(?::(\d{2}))?\s*"
    r"(صباح(?:اً|ا)?|مساء(?:ً|ا)?)"
    r".*?"
    r"عبر\s+قناة\s+"
    r"(أون\s+سبورت(?:\s+(?:1|2|ماكس|بلس))?)"
    r"(?:\s+بتعليق\s+(.+))?$",
    re.I,
)


def parse_filgoal_article(html: str, source_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    lines = [norm(x) for x in soup.stripped_strings if norm(x)]
    events: list[dict] = []
    current_date: date | None = None
    now_cairo = utc_now().astimezone(CAIRO)

    for line in lines:
        hd = AR_DAY_HEADER_RE.match(line)
        if hd:
            dd_s, mon_s, yy_s = hd.groups()
            month = AR_MONTHS.get(mon_s)
            if month is None:
                month = AR_MONTHS.get(ar_norm(mon_s))
            if month is not None:
                year = int(yy_s) if yy_s else now_cairo.year
                try:
                    current_date = date(year, month, int(dd_s))
                except ValueError:
                    current_date = None
            continue

        if current_date is None:
            continue

        m = FILGOAL_MATCH_RE.search(line)
        if not m:
            continue

        home, away, hh_s, mm_s, ampm, channel_label, commentator = m.groups()
        channel_id = channel_from_arabic(channel_label)
        if not channel_id:
            continue

        hh = int(hh_s)
        mm = int(mm_s or 0)
        if "مساء" in ampm:
            if hh != 12:
                hh += 12
        else:
            if hh == 12:
                hh = 0

        try:
            local = datetime(
                current_date.year, current_date.month, current_date.day,
                hh, mm, tzinfo=CAIRO,
            )
            start_utc = local.astimezone(UTC)
        except Exception:
            continue

        if not in_window(start_utc):
            continue

        events.append({
            "channel_id": channel_id,
            "channel_name": CHANNELS[channel_id]["name"],
            "start": start_utc,
            "home": norm(home),
            "away": norm(away),
            "competition": "Egyptian Premier League",
            "source_name": "FilGoal",
            "source": source_url,
            "commentator": norm(commentator or ""),
            "duration_minutes": 135,
        })

    return dedupe(events)


def collect_filgoal_events() -> list[dict]:
    events: list[dict] = []
    try:
        articles = discover_filgoal_assignment_articles()
        log(f"FilGoal assignment articles discovered: {len(articles)}")
    except Exception as exc:
        warn(f"FilGoal article discovery failed: {exc}")
        return events

    for url in articles:
        try:
            parsed = parse_filgoal_article(fetch_text(url), url)
            if parsed:
                log(f"FilGoal assignments from article: {len(parsed)} | {url}")
                events.extend(parsed)
        except Exception as exc:
            warn(f"FilGoal article failed: {exc}")

    return dedupe(events)


# ---------------------------------------------------------------------------
# Egyptian Pro League official validation
# ---------------------------------------------------------------------------

def discover_epl_team_pages() -> dict[str, str]:
    html = fetch_text(EPL_HOME)
    soup = BeautifulSoup(html, "html.parser")
    pages: dict[str, str] = {}

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/team/" not in href:
            continue
        label = norm(a.get_text(" ", strip=True))
        if not label:
            continue
        url = urljoin(EPL_HOME, href)
        if not url.rstrip("/").endswith("/matches"):
            url = url.rstrip("/") + "/matches"
        pages.setdefault(canonical_team(label), url)

    return pages


def _official_time_tokens(local: datetime) -> set[str]:
    """
    EPL pages currently render evening kickoffs like 17:00/20:00 as
    05:00/08:00 in the extracted HTML. Accept both representations while
    still requiring the exact official date and both teams.
    """
    tokens = {
        f"{local.hour:02d}:{local.minute:02d}",
        f"{local.hour}:{local.minute:02d}",
    }
    h12 = local.hour % 12
    if h12 == 0:
        h12 = 12
    tokens.add(f"{h12:02d}:{local.minute:02d}")
    tokens.add(f"{h12}:{local.minute:02d}")
    return tokens


def _official_page_contains_event(html: str, ev: dict) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    raw = norm(soup.get_text(" ", strip=True))
    text = ar_norm(raw)

    home = canonical_team(ev["home"])
    away = canonical_team(ev["away"])
    local = ev["start"].astimezone(CAIRO)

    if home not in text or away not in text:
        return False

    month_names = [k for k, v in AR_MONTHS.items() if v == local.month]
    date_variants = []
    for m in month_names:
        date_variants.extend([
            ar_norm(f"{local.day:02d} {m} {local.year}"),
            ar_norm(f"{local.day} {m} {local.year}"),
        ])
    date_ok = any(v in text for v in date_variants)

    time_ok = any(token in raw for token in _official_time_tokens(local))
    return date_ok and time_ok


def validate_with_epl(events: list[dict]) -> list[dict]:
    if not events:
        return events

    try:
        pages = discover_epl_team_pages()
        log(f"EPL official team pages discovered: {len(pages)}")
    except Exception as exc:
        warn(f"EPL official discovery failed: {exc}")
        return events

    # Fetch each unique official page once.
    cache: dict[str, str] = {}
    unique_urls = list(dict.fromkeys(pages.values()))
    for url in unique_urls:
        try:
            cache[url] = fetch_text(url)
        except Exception as exc:
            warn(f"EPL validation page failed: {url} | {exc}")

    validated = 0
    for ev in events:
        ok = False

        # Prefer the two team's own pages when labels were discovered.
        preferred = [
            pages.get(canonical_team(ev["home"])),
            pages.get(canonical_team(ev["away"])),
        ]
        candidates = [u for u in preferred if u and u in cache]

        # If homepage link labels do not map cleanly, fall back to all cached
        # official team pages. This is still official-source validation.
        if not candidates:
            candidates = list(cache.keys())

        for url in candidates:
            if _official_page_contains_event(cache[url], ev):
                ok = True
                break

        if ok:
            ev["source_name"] = "FilGoal+EPL"
            validated += 1

    log(f"EPL official validations matched: {validated}/{len(events)}")
    return events


# ---------------------------------------------------------------------------
# LiveFootballTV: confirmed channel-specific football beyond league articles
# ---------------------------------------------------------------------------

DATE_NUMERIC = re.compile(
    r"(?:(?:today|tomorrow)\s+)?"
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s*"
    r"(\d{1,2})/(\d{1,2})/(20\d{2})",
    re.I,
)

DATE_TEXTUAL = re.compile(
    r"(?:(?:today|tomorrow)\s+)?"
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s*"
    r"(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"(?:\s+(20\d{2}))?",
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
    r"riyadiya|sharjah|oman|dubai|abu dhabi|ssc|ktv|fifa\+|ppv)",
    re.I,
)


def parse_lftv_date(line: str, now_local: datetime) -> date | None:
    s = norm(line)

    m = DATE_NUMERIC.search(s)
    if m:
        dd, mm, yy = map(int, m.groups())
        try:
            return date(yy, mm, dd)
        except ValueError:
            return None

    m = DATE_TEXTUAL.search(s)
    if m:
        dd, mon, yy = m.groups()
        month = EN_MONTHS.get(mon.casefold())
        if not month:
            return None
        year = int(yy) if yy else now_local.year
        try:
            return date(year, month, int(dd))
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
    s = norm(s)
    return re.sub(r"^Image:\s*", "", s, flags=re.I)


def _plausible_lftv_name(s: str) -> bool:
    if not s or len(s) > 70:
        return False
    if BAD_TEXT.search(s) or TIME_RE.match(s) or s.isdigit():
        return False
    return True


def _extract_lftv_event(block: list[str], channel_name: str):
    cleaned = [_clean_lftv_line(x) for x in block]
    cleaned = [x for x in cleaned if x and _plausible_lftv_name(x)]

    own_idx = next(
        (i for i, x in enumerate(cleaned) if x.casefold() == channel_name.casefold()),
        None,
    )
    if own_idx is None:
        return None

    first_broadcaster = next(
        (i for i, x in enumerate(cleaned[:own_idx + 1]) if BROADCASTER_HINTS.search(x)),
        own_idx,
    )
    core = cleaned[:first_broadcaster]
    if len(core) < 3:
        core = [x for x in cleaned[:own_idx] if not BROADCASTER_HINTS.search(x)]
    if len(core) < 3:
        return None

    non_stage = [x for x in core if not STAGE_TEXT.match(x)]
    if len(non_stage) < 3:
        return None

    home, away = non_stage[-2], non_stage[-1]
    competition = non_stage[-3]
    if BROADCASTER_HINTS.search(home) or BROADCASTER_HINTS.search(away):
        return None
    return competition, home, away


def parse_lftv_channel(html: str, channel_id: str, source_url: str) -> list[dict]:
    channel_name = CHANNELS[channel_id]["name"]
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    lines = [norm(x) for x in soup.stripped_strings if norm(x)]
    now_cairo = utc_now().astimezone(CAIRO)
    current_date: date | None = None
    events: list[dict] = []

    i = 0
    while i < len(lines):
        d = parse_lftv_date(lines[i], now_cairo)
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
            if TIME_RE.match(lines[j]) or parse_lftv_date(lines[j], now_cairo):
                break
            block.append(lines[j])
            j += 1

        parsed = _extract_lftv_event(block, channel_name)
        if parsed:
            competition, home, away = parsed
            try:
                local = datetime(
                    current_date.year, current_date.month, current_date.day,
                    hh, mm, tzinfo=CAIRO,
                )
                start_utc = local.astimezone(UTC)
            except Exception:
                start_utc = None

            if start_utc and in_window(start_utc):
                events.append({
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "start": start_utc,
                    "home": norm(home),
                    "away": norm(away),
                    "competition": norm(competition),
                    "source_name": "LiveFootballTV",
                    "source": source_url,
                    "commentator": "",
                    "duration_minutes": 135,
                })

        i = max(i + 1, j)

    return dedupe(events)


def collect_lftv_events() -> list[dict]:
    events: list[dict] = []
    for channel_id, url in LIVEFOOTBALLTV.items():
        try:
            parsed = parse_lftv_channel(fetch_text(url), channel_id, url)
            log(f"{CHANNELS[channel_id]['name']} LFTV fixtures detected: {len(parsed)}")
            events.extend(parsed)
        except Exception as exc:
            warn(f"{CHANNELS[channel_id]['name']} LFTV failed: {exc}")
    return dedupe(events)


# ---------------------------------------------------------------------------
# XML
# ---------------------------------------------------------------------------

def build_day_description(channel_name: str, d: date, events: list[dict]) -> str:
    if not events:
        return (
            f"{channel_name} | {d.isoformat()}\n\n"
            "لا توجد مباراة مؤكدة مجدولة في المصادر الحالية."
        )

    lines = [f"جدول {channel_name} | {d.isoformat()}", ""]
    for ev in sorted(events, key=lambda x: x["start"]):
        ad = ev["start"].astimezone(ABU_DHABI)
        lv = ev["start"].astimezone(LAS_VEGAS)
        lines.append(f"• {display_team(ev['home'])} - {display_team(ev['away'])} — {ev['competition']}")
        lines.append(f"  {ad:%H:%M} أبو ظبي | {lv:%H:%M} لاس فيغاس")
        if ev.get("commentator"):
            lines.append(f"  المعلق: {ev['commentator']}")
    lines.extend(["", "لا يتم تخمين القناة؛ التوزيع مأخوذ من مصدر بث يذكر القناة."])
    return "\n".join(lines)


def add_programme(root, channel_id, start, stop, title, desc, category="Sports"):
    p = ET.SubElement(
        root, "programme",
        start=xmltv_time(start),
        stop=xmltv_time(stop),
        channel=channel_id,
    )
    ET.SubElement(p, "title", lang="ar").text = title
    ET.SubElement(p, "desc", lang="ar").text = desc
    ET.SubElement(p, "category", lang="en").text = category


def write_xml(events: list[dict]) -> None:
    root = ET.Element("tv", generator_info_name="ON Sport verified EPG")

    for channel_id, cfg in CHANNELS.items():
        ch = ET.SubElement(root, "channel", id=channel_id)
        ET.SubElement(ch, "display-name", lang="en").text = cfg["name"]
        ET.SubElement(ch, "display-name", lang="ar").text = cfg["name"]

    today_ad = utc_now().astimezone(ABU_DHABI).date()
    first_day = today_ad - timedelta(days=DAYS_BACK)
    last_day = today_ad + timedelta(days=DAYS_FORWARD)

    by_key: dict[tuple[str, date], list[dict]] = {}
    for ev in events:
        d = ev["start"].astimezone(ABU_DHABI).date()
        by_key.setdefault((ev["channel_id"], d), []).append(ev)

    for channel_id, cfg in CHANNELS.items():
        for off in range((last_day - first_day).days + 1):
            d = first_day + timedelta(days=off)
            day_events = sorted(by_key.get((channel_id, d), []), key=lambda x: x["start"])
            desc = build_day_description(cfg["name"], d, day_events)

            day_start_ad = datetime(d.year, d.month, d.day, 0, 0, tzinfo=ABU_DHABI)
            day_end_ad = day_start_ad + timedelta(days=1)
            day_start = day_start_ad.astimezone(UTC)
            day_end = day_end_ad.astimezone(UTC)

            if not day_events:
                add_programme(
                    root, channel_id, day_start, day_end,
                    "لا توجد مباراة مؤكدة مجدولة", desc,
                )
                continue

            cursor = day_start
            for ev in day_events:
                ev_start = ev["start"].astimezone(UTC)
                if ev_start > cursor:
                    add_programme(
                        root, channel_id, cursor, ev_start,
                        f"جدول {cfg['name']} اليوم", desc,
                    )

                ev_stop = min(
                    ev_start + timedelta(minutes=int(ev.get("duration_minutes", 135))),
                    day_end,
                )
                ad = ev_start.astimezone(ABU_DHABI)
                lv = ev_start.astimezone(LAS_VEGAS)
                title = (
                    f"{display_team(ev['home'])} - {display_team(ev['away'])} | "
                    f"{ad:%H:%M} أبو ظبي | {lv:%H:%M} لاس فيغاس"
                )
                add_programme(
                    root, channel_id, ev_start, ev_stop, title, desc,
                    category=ev["competition"],
                )
                cursor = max(cursor, ev_stop)

            if cursor < day_end:
                add_programme(
                    root, channel_id, cursor, day_end,
                    f"جدول {cfg['name']} اليوم", desc,
                )

    try:
        ET.indent(root, space="  ")
    except AttributeError:
        pass

    ET.ElementTree(root).write(OUTPUT, encoding="utf-8", xml_declaration=True)
    ET.parse(OUTPUT)
    log(f"Written and XML-validated: {OUTPUT}")


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    sample_article = """
    <html><body>
    <p>الجمعة 21 أغسطس:</p>
    <p>-وادي دجلة ضد زد – الساعة 5 مساء عبر قناة أون سبورت بتعليق أيمن الكاشف</p>
    <p>-الزمالك ضد الاتحاد السكندري – الساعة 8 مساء عبر قناة أون سبورت بتعليق بلال علام</p>
    <p>--أبو قير للأسمدة ضد البنك الأهلي – الساعة 8 مساء عبر قناة أون سبورت ماكس بتعليق محمد عفيفي</p>
    <p>السبت 22 أغسطس:</p>
    <p>-طلائع الجيش ضد المقاولون العرب – الساعة 5 مساء عبر قناة أون سبورت ماكس بتعليق طارق حسن</p>
    </body></html>
    """

    # Structural parser test independent of current runtime window.
    old_window = globals()["in_window"]
    try:
        globals()["in_window"] = lambda dt: True
        parsed = parse_filgoal_article(sample_article, "self-test")
    finally:
        globals()["in_window"] = old_window

    assert len(parsed) == 4
    assert parsed[0]["channel_id"] in CHANNELS
    assert any(
        x["channel_id"] == "ONSportMAX"
        and canonical_team(x["home"]) == canonical_team("أبو قير للأسمدة")
        for x in parsed
    )
    assert any(
        x["channel_id"] == "ONSport1"
        and canonical_team(x["home"]) == canonical_team("الزمالك")
        for x in parsed
    )
    assert channel_from_arabic("أون سبورت") == "ONSport1"
    assert channel_from_arabic("أون سبورت ماكس") == "ONSportMAX"

    official_sample = """
    <html><body>
    الزمالك الاتحاد السكندري
    08:00 الجولة 1 الجمعة 21 أغسطس 2026
    </body></html>
    """
    official_ev = {
        "home": "الزمالك",
        "away": "الاتحاد السكندري",
        "start": datetime(2026, 8, 21, 20, 0, tzinfo=CAIRO).astimezone(UTC),
    }
    assert _official_page_contains_event(official_sample, official_ev)

    log("SELF TEST | PASS")


def main():
    log(
        "ON SPORT EPG | FilGoal Egyptian League assignments + EPL official validation "
        "+ channel-specific LiveFootballTV | 1 + 2 + MAX + PLUS"
    )

    _self_test()

    filgoal = collect_filgoal_events()
    filgoal = validate_with_epl(filgoal)

    lftv = collect_lftv_events()

    events = dedupe(filgoal + lftv)

    log(f"ON Sport total verified football events: {len(events)}")
    for ev in sorted(events, key=lambda x: x["start"]):
        ad = ev["start"].astimezone(ABU_DHABI)
        lv = ev["start"].astimezone(LAS_VEGAS)
        log(
            f"  {ev['channel_name']} | "
            f"{ad:%Y-%m-%d %H:%M} أبو ظبي | "
            f"{lv:%Y-%m-%d %H:%M} لاس فيغاس | "
            f"{display_team(ev['home'])} - {display_team(ev['away'])} | "
            f"{ev['competition']} | {ev['source_name']}"
        )

    write_xml(events)


if __name__ == "__main__":
    main()
