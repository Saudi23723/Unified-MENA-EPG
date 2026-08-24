#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone, date
from html import unescape
from urllib.parse import urljoin
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup


OUTPUT = "onsport_epg.xml"

CAIRO = ZoneInfo("Africa/Cairo")
SOURCE_TZ = CAIRO           # كل التوقيتات تُبنى على توقيت المصدر (القاهرة)
UTC = timezone.utc

DAYS_BACK = 1
DAYS_FORWARD = 14
HTTP_TIMEOUT = 20
HTTP_RETRIES = 3
HTTP_BACKOFF = 2.0

# حماية: لا يُستبدل ملف سليم موجود بملف فارغ لو تعطّلت المصادر.
KEEP_OLD_FILE_IF_EMPTY = True

# نافذة اعتبار مباراتين من مصدرين مختلفين نفس المباراة (فرق دقائق بسيط).
DEDUPE_TOLERANCE_MINUTES = 45

# مدة المباراة داخل الـEPG: 15 د استوديو قبل + 90 د لعب + 15 د راحة = 120
MATCH_MINUTES = 120
MIN_PROGRAMME_MINUTES = 5

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

LIVEFOOTBALLTV = {
    "ONSport1": "https://www.livefootballtv.info/channel/on-sport-1",
    "ONSport2": "https://www.livefootballtv.info/channel/on-sport-2",
    "ONSportMAX": "https://www.livefootballtv.info/channel/on-sport-max",
    "ONSportPLUS": "https://www.livefootballtv.info/channel/on-sport-plus",
}

# livesoccertv.com: مصدر عالمي راسخ لجداول القنوات الرياضية، ذو ترميز HTML
# منظم (tr.matchrow) وطابع زمني epoch دقيق (span.ts[dv]) — لا حاجة لتخمين
# التوقيت أو تتبّع "تاريخ سطر سابق" كما في المصادر النصية الأخرى.
LIVESOCCERTV = {
    "ONSport1": "https://www.livesoccertv.com/channels/on-sport-egypt/",
    "ONSport2": "https://www.livesoccertv.com/channels/on-sport-2-egypt/",
    "ONSportMAX": "https://www.livesoccertv.com/channels/on-sport-max/",
    "ONSportPLUS": "https://www.livesoccertv.com/channels/on-sport-plus/",
}

FILGOAL_EGYPT_SECTION = (
    "https://www.filgoal.com/section/88/articles/"
    "%D8%A7%D9%84%D8%AF%D9%88%D8%B1%D9%8A-%D8%A7%D9%84%D9%85%D8%B5%D8%B1%D9%8A"
)

EPL_HOME = "https://www.egyptianproleague.com/"

FILGOAL_FEEDS = [
    "https://www.filgoal.com/section/88/rss/الدوري-المصري",
    "https://www.filgoal.com/section/1/rss/مصر",
    "https://www.filgoal.com/section/0/rss/مصر",
]

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


def en_norm(s: str) -> str:
    """تطبيع الاسم الإنجليزي: إزالة اللواحق والبادئات الشائعة."""
    s = norm(s).casefold()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9\s-]+", " ", s)
    s = s.replace("-", " ")
    tokens = [t for t in s.split() if t not in {
        "fc", "sc", "club", "sporting", "team", "the", "of", "for",
    }]
    tokens = [re.sub(r"^(?:al|el)$", "", t) for t in tokens]
    return " ".join(t for t in tokens if t)


EN_TEAM_ALIASES = {
    "ahly": "الاهلي",
    "zamalek": "الزمالك",
    "ittihad alexandria": "الاتحاد السكندري",
    "ittihad": "الاتحاد السكندري",
    "zed": "زد",
    "wadi degla": "وادي دجله",
    "national bank": "البنك الاهلي",
    "national bank egypt": "البنك الاهلي",
    "abu qair semad": "ابو قير للاسمده",
    "abou kir fertilizers": "ابو قير للاسمده",
    "asyut petroleum": "بترول اسيوط",
    "petrojet": "منتخب السويس بتروجت",
    "geish": "طلايع الجيش",
    "tala ea geish": "طلايع الجيش",
    "mokawloon": "المقاولون العرب",
    "arab contractors": "المقاولون العرب",
    "masry": "المصري",
    "smouha": "سموحه",
    "ghazl mehalla": "غزل المحله",
    "pyramids": "بيراميدز",
    "gouna": "الجونه",
    "modern sport": "مودرن سبورت",
    "modern future": "مودرن سبورت",
    "future": "فيوتشر",
    "ceramica cleopatra": "سيراميكا كليوباترا",
    "qanah": "القناه",
    "enppi": "الشرقيه انبي",
    "ismaily": "الاسماعيلي",
    "haras el hodood": "حرس الحدود",
    "bank ahly": "البنك الاهلي",
}

TEAM_DISPLAY_AR = {
    "الاهلي": "الأهلي",
    "الزمالك": "الزمالك",
    "الاتحاد السكندري": "الاتحاد السكندري",
    "زد": "زد",
    "وادي دجله": "وادي دجلة",
    "البنك الاهلي": "البنك الأهلي",
    "ابو قير للاسمده": "أبو قير للأسمدة",
    "بترول اسيوط": "بترول أسيوط",
    "منتخب السويس بتروجت": "بتروجت",
    "طلايع الجيش": "طلائع الجيش",
    "المقاولون العرب": "المقاولون العرب",
    "المصري": "المصري",
    "سموحه": "سموحة",
    "غزل المحله": "غزل المحلة",
    "بيراميدز": "بيراميدز",
    "الجونه": "الجونة",
    "مودرن سبورت": "مودرن سبورت",
    "فيوتشر": "فيوتشر",
    "سيراميكا كليوباترا": "سيراميكا كليوباترا",
    "القناه": "القناة",
    "الشرقيه انبي": "إنبي",
    "الاسماعيلي": "الإسماعيلي",
    "حرس الحدود": "حرس الحدود",
}


def canonical_team(s: str) -> str:
    n = ar_norm(s)
    if n in TEAM_ALIASES:
        return TEAM_ALIASES[n]
    if not re.search(r"[\u0600-\u06ff]", s or ""):
        e = en_norm(s)
        if e in EN_TEAM_ALIASES:
            return EN_TEAM_ALIASES[e]
        return e or n
    return n


def display_team(s: str) -> str:
    """يعرض الاسم بالعربي إن عُرف الفريق، وإلا يترك الاسم كما ورد من المصدر."""
    return TEAM_DISPLAY_AR.get(canonical_team(s), norm(s))


_RUN_NOW: datetime | None = None


def utc_now() -> datetime:
    global _RUN_NOW
    if _RUN_NOW is None:
        _RUN_NOW = datetime.now(UTC)
    return _RUN_NOW


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
    last: Exception | None = None
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            r = session.get(url, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            if not r.encoding or r.encoding.lower() == "iso-8859-1":
                r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except Exception as exc:
            last = exc
            if attempt < HTTP_RETRIES:
                wait = HTTP_BACKOFF * attempt
                warn(f"retry {attempt}/{HTTP_RETRIES - 1} after {wait:.0f}s | {url} | {exc}")
                time.sleep(wait)
    raise last


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


def to_24h(hh: int, period: str) -> int:
    p = period or ""
    if "صباح" in p:
        return 0 if hh == 12 else hh
    if "ظهر" in p:
        return 12 if hh == 12 else (hh + 12 if hh < 12 else hh)
    if "ليل" in p:
        return 0 if hh == 12 else (hh + 12 if hh < 12 else hh)
    return 12 if hh == 12 else (hh + 12 if hh < 12 else hh)


def fix_year(d: date, ref: date) -> date:
    for cand in (d, d.replace(year=d.year + 1), d.replace(year=d.year - 1)):
        if abs((cand - ref).days) <= 180:
            return cand
    return d


def channel_from_arabic(label: str) -> str | None:
    n = ar_norm(label)
    if "ماكس" in n or "max" in n:
        return "ONSportMAX"
    if "بلس" in n or "plus" in n:
        return "ONSportPLUS"
    if re.search(r"(?:^|\s)2(?:\s|$)", n):
        return "ONSport2"
    if re.search(r"(?:^|\s)1(?:\s|$)", n):
        return "ONSport1"
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
    "LiveSoccerTV": 115,
    "FilGoal": 105,
    "LiveFootballTV": 100,
}


def prio(ev: dict) -> int:
    return SOURCE_PRIORITY.get(ev["source_name"], 0)


def match_key(ev: dict) -> str:
    teams = sorted([canonical_team(ev["home"]), canonical_team(ev["away"])])
    d = ev["start"].astimezone(SOURCE_TZ).date()
    return f"{ev['channel_id']}|{d.isoformat()}|{teams[0]}|{teams[1]}"


def dedupe(events: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for ev in events:
        groups.setdefault(match_key(ev), []).append(ev)

    out: list[dict] = []
    tol = timedelta(minutes=DEDUPE_TOLERANCE_MINUTES)

    for bucket in groups.values():
        bucket.sort(key=lambda x: (-prio(x), x["start"]))
        kept: list[dict] = []
        for ev in bucket:
            if any(abs(ev["start"] - k["start"]) <= tol for k in kept):
                continue
            kept.append(ev)
        out.extend(kept)

    return sorted(out, key=lambda x: (x["channel_id"], x["start"]))


def _looks_like_assignment_headline(n: str) -> bool:
    if "القنوات الناقله" in n or "القنوات الناقل" in n:
        return True
    if "الناقله" in n and ("الجوله" in n or "مباريات" in n):
        return True
    if "مواعيد" in n and "مباريات" in n and ("الجوله" in n or "الدوري المصري" in n):
        return True
    return False


def _parse_rss_items(xml_text: str) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError:
        return items

    for it in root.iter():
        if not it.tag.endswith("item"):
            continue
        title = link = ""
        for child in it:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "title":
                title = norm(child.text or "")
            elif tag == "link":
                link = norm(child.text or "")
        if title and link:
            items.append((title, link))
    return items


def _discover_via_rss() -> tuple[list[str], int]:
    urls: list[str] = []
    scanned = 0

    for feed in FILGOAL_FEEDS:
        try:
            items = _parse_rss_items(fetch_text(feed))
        except Exception as exc:
            warn(f"FilGoal RSS تعذّر: {feed} | {exc}")
            continue

        scanned += len(items)
        if not items:
            warn(f"FilGoal RSS لم يرجّع عناصر: {feed}")
            continue

        hits = 0
        for title, link in items:
            if not _looks_like_assignment_headline(ar_norm(title)):
                continue
            if link not in urls:
                urls.append(link)
                hits += 1
        log(f"FilGoal RSS: {len(items)} خبر، {hits} مطابق | {feed}")

    return urls, scanned


def _discover_via_html() -> tuple[list[str], list[str]]:
    urls: list[str] = []
    headlines: list[str] = []

    html = fetch_text(FILGOAL_EGYPT_SECTION)
    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a", href=True):
        text = norm(a.get_text(" ", strip=True))
        if not text:
            img = a.find("img")
            text = norm(a.get("title") or (img.get("alt") if img else "") or "")
        if not text:
            continue

        headlines.append(text)
        if not _looks_like_assignment_headline(ar_norm(text)):
            continue

        href = urljoin(FILGOAL_EGYPT_SECTION, a["href"])
        if "/news/" not in href and "/article" not in href:
            continue
        if href not in urls:
            urls.append(href)

    return urls, headlines


def discover_filgoal_assignment_articles() -> list[str]:
    urls, scanned = _discover_via_rss()
    if urls:
        return urls[:8]

    try:
        urls, headlines = _discover_via_html()
    except Exception as exc:
        warn(f"FilGoal: تعذّر جلب صفحة القسم | {exc}")
        urls, headlines = [], []

    if not urls:
        warn(
            f"FilGoal: لا مقالات. RSS فحص {scanned} خبراً، "
            f"وصفحة القسم فحصت {len(headlines)} عنواناً."
        )
        for h in headlines[:8]:
            warn(f"  عيّنة عنوان: {h[:110]}")

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
    r"(صباح(?:اً|ا)?|ظهر(?:اً|ا)?|عصر(?:اً|ا)?|مساء(?:ً|ا)?|ليل(?:اً|ا)?)"
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
                    if not yy_s:
                        current_date = fix_year(current_date, now_cairo.date())
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

        hh = to_24h(int(hh_s), ampm)
        mm = int(mm_s or 0)

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
            "duration_minutes": MATCH_MINUTES,
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
            html = fetch_text(url)
            parsed = parse_filgoal_article(html, url)
            if parsed:
                log(f"FilGoal assignments from article: {len(parsed)} | {url}")
                events.extend(parsed)
            else:
                txt = unescape(html)
                warn(
                    f"FilGoal: مقال بلا مباريات | {url} | "
                    f"'ضد' {'موجودة' if ' ضد ' in txt else 'مفقودة'} | "
                    f"'الساعة' {'موجودة' if 'الساعة' in txt else 'مفقودة'} | "
                    f"'عبر قناة' {'موجودة' if 'عبر قناة' in txt else 'مفقودة'}"
                )
        except Exception as exc:
            warn(f"FilGoal article failed: {url} | {exc}")

    return dedupe(events)


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


def _official_page_contains_event(html: str, ev: dict) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    text = ar_norm(soup.get_text(" ", strip=True))

    home = canonical_team(ev["home"])
    away = canonical_team(ev["away"])
    local = ev["start"].astimezone(CAIRO)

    if home not in text or away not in text:
        return False

    month_names = [k for k, v in AR_MONTHS.items() if v == local.month]
    date_ok = any(
        ar_norm(f"{local.day:02d} {m} {local.year}") in text
        or ar_norm(f"{local.day} {m} {local.year}") in text
        for m in month_names
    )
    time_ok = (
        f"{local:%H:%M}" in text
        or f"{local.hour:02d}:{local.minute:02d}" in text
    )
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

    cache: dict[str, str] = {}
    validated = 0

    for ev in events:
        candidates = [
            pages.get(canonical_team(ev["home"])),
            pages.get(canonical_team(ev["away"])),
        ]
        ok = False

        for url in [u for u in candidates if u]:
            try:
                if url not in cache:
                    cache[url] = fetch_text(url)
                if _official_page_contains_event(cache[url], ev):
                    ok = True
                    break
            except Exception as exc:
                warn(f"EPL validation page failed: {url} | {exc}")

        if ok:
            ev["source_name"] = "FilGoal+EPL"
            validated += 1

    log(f"EPL official validations matched: {validated}/{len(events)}")
    return events


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
                    "duration_minutes": MATCH_MINUTES,
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


LSTV_VS_RE = re.compile(r"^(.+?)\s+vs\s+(.+)$", re.I)


def parse_livesoccertv_channel(html: str, channel_id: str, source_url: str) -> list[dict]:
    """يحلّل جدول livesoccertv.com الخاص بقناة واحدة.

    كل صف مباراة (tr.matchrow) يحمل طابع epoch دقيق بالمللي ثانية في
    span.ts[dv]، لذلك لا حاجة لتخمين المنطقة الزمنية أو لتتبّع "آخر
    تاريخ ظهر" كما في المصادر النصية الأخرى — كل صف مستقل وموثوق زمنياً.
    """
    channel_name = CHANNELS[channel_id]["name"]
    soup = BeautifulSoup(html, "html.parser")

    table = soup.find("table", class_="schedules")
    events: list[dict] = []
    if table is None:
        return events

    for row in table.find_all("tr", class_="matchrow"):
        ts_span = row.select_one(".timecell .ts")
        dv = ts_span.get("dv") if ts_span else None
        if not dv:
            continue
        try:
            start_utc = datetime.fromtimestamp(int(dv) / 1000, tz=UTC)
        except (ValueError, OverflowError, OSError):
            continue

        match_cell = row.find("td", class_="matchcol")
        match_link = match_cell.find("a") if match_cell else None
        title = norm(match_link.get("title", "")) if match_link else ""
        m = LSTV_VS_RE.match(title)
        if not m:
            continue
        home, away = m.group(1), m.group(2)

        comp_cell = row.find("td", class_="compcell_right")
        comp_link = comp_cell.find("a") if comp_cell else None
        competition = norm(
            (comp_link.get("title") if comp_link else "")
            or (comp_cell.get_text(" ", strip=True) if comp_cell else "")
        ) or "Football"

        if not in_window(start_utc):
            continue

        events.append({
            "channel_id": channel_id,
            "channel_name": channel_name,
            "start": start_utc,
            "home": home,
            "away": away,
            "competition": competition,
            "source_name": "LiveSoccerTV",
            "source": source_url,
            "commentator": "",
            "duration_minutes": MATCH_MINUTES,
        })

    return dedupe(events)


def collect_livesoccertv_events() -> list[dict]:
    events: list[dict] = []
    for channel_id, url in LIVESOCCERTV.items():
        try:
            parsed = parse_livesoccertv_channel(fetch_text(url), channel_id, url)
            log(f"{CHANNELS[channel_id]['name']} LiveSoccerTV fixtures detected: {len(parsed)}")
            events.extend(parsed)
        except Exception as exc:
            warn(f"{CHANNELS[channel_id]['name']} LiveSoccerTV failed: {exc}")
    return dedupe(events)


def build_day_description(channel_name: str, d: date, events: list[dict]) -> str:
    if not events:
        return (
            f"{channel_name} | {d.isoformat()}\n\n"
            "لا توجد مباراة مؤكدة مجدولة في المصادر الحالية."
        )

    lines = [f"جدول {channel_name} | {d.isoformat()}", ""]
    for ev in sorted(events, key=lambda x: x["start"]):
        local = ev["start"].astimezone(SOURCE_TZ)
        lines.append(
            f"• {local:%H:%M} — {display_team(ev['home'])} - {display_team(ev['away'])}"
        )
        lines.append(f"  {ev['competition']}")
        if ev.get("commentator"):
            lines.append(f"  المعلق: {ev['commentator']}")
    lines.extend([
        "",
        "التوقيت كما ورد في المصدر (القاهرة) ويُبَث بصيغة UTC.",
        "لا يتم تخمين القناة؛ التوزيع مأخوذ من مصدر بث يذكر القناة.",
    ])
    return "\n".join(lines)


def is_arabic(s: str) -> bool:
    return bool(re.search(r"[\u0600-\u06ff]", s or ""))


def add_programme(root, channel_id, start, stop, title, desc, category=None):
    p = ET.SubElement(
        root, "programme",
        start=xmltv_time(start),
        stop=xmltv_time(stop),
        channel=channel_id,
    )
    ET.SubElement(p, "title", lang="ar").text = title
    ET.SubElement(p, "desc", lang="ar").text = desc
    ET.SubElement(p, "category", lang="en").text = "Sports"
    if category and category.strip().lower() != "sports":
        lang = "ar" if is_arabic(category) else "en"
        ET.SubElement(p, "category", lang=lang).text = category.strip()


AR_WEEKDAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]


def next_event_after(channel_events: list[dict], moment_utc: datetime) -> dict | None:
    for ev in channel_events:
        if ev["start"].astimezone(UTC) >= moment_utc:
            return ev
    return None


def filler_title(nxt: dict | None, gap_start_utc: datetime) -> str:
    if nxt is None:
        return "لا توجد مباراة مجدولة"

    teams = f"{display_team(nxt['home'])} - {display_team(nxt['away'])}"
    return f"القادم · {teams}"


def write_xml(events: list[dict]) -> None:
    root = ET.Element("tv", generator_info_name="ON Sport verified EPG")

    for channel_id, cfg in CHANNELS.items():
        ch = ET.SubElement(root, "channel", id=channel_id)
        ET.SubElement(ch, "display-name", lang="en").text = cfg["name"]
        ET.SubElement(ch, "display-name", lang="ar").text = cfg["name"]

    today_source = utc_now().astimezone(SOURCE_TZ).date()
    first_day = today_source - timedelta(days=DAYS_BACK)
    last_day = today_source + timedelta(days=DAYS_FORWARD)

    by_key: dict[tuple[str, date], list[dict]] = {}
    for ev in events:
        d = ev["start"].astimezone(SOURCE_TZ).date()
        by_key.setdefault((ev["channel_id"], d), []).append(ev)

    by_channel: dict[str, list[dict]] = {}
    for ev in events:
        by_channel.setdefault(ev["channel_id"], []).append(ev)
    for lst in by_channel.values():
        lst.sort(key=lambda x: x["start"])

    for channel_id, cfg in CHANNELS.items():
        ch_events = by_channel.get(channel_id, [])
        for off in range((last_day - first_day).days + 1):
            d = first_day + timedelta(days=off)
            day_events = sorted(by_key.get((channel_id, d), []), key=lambda x: x["start"])
            desc = build_day_description(cfg["name"], d, day_events)

            day_start_local = datetime(d.year, d.month, d.day, 0, 0, tzinfo=SOURCE_TZ)
            day_end_local = datetime(
                d.year, d.month, d.day, 0, 0, tzinfo=SOURCE_TZ
            ) + timedelta(days=1)
            day_start = day_start_local.astimezone(UTC)
            day_end = day_end_local.astimezone(UTC)

            if not day_events:
                add_programme(
                    root, channel_id, day_start, day_end,
                    filler_title(next_event_after(ch_events, day_start), day_start),
                    desc,
                )
                continue

            cursor = day_start
            for idx, ev in enumerate(day_events):
                ev_start = max(ev["start"].astimezone(UTC), cursor)
                if ev_start >= day_end:
                    continue

                if ev_start > cursor:
                    add_programme(
                        root, channel_id, cursor, ev_start,
                        filler_title(ev, cursor), desc,
                    )

                next_start = day_end
                if idx + 1 < len(day_events):
                    next_start = day_events[idx + 1]["start"].astimezone(UTC)

                ev_stop = min(
                    ev_start + timedelta(minutes=int(ev.get("duration_minutes", MATCH_MINUTES))),
                    next_start,
                    day_end,
                )
                if ev_stop - ev_start < timedelta(minutes=MIN_PROGRAMME_MINUTES):
                    continue

                title = f"{display_team(ev['home'])} - {display_team(ev['away'])}"
                add_programme(
                    root, channel_id, ev_start, ev_stop, title, desc,
                    category=ev["competition"],
                )
                cursor = max(cursor, ev_stop)

            if day_end - cursor >= timedelta(minutes=MIN_PROGRAMME_MINUTES):
                add_programme(
                    root, channel_id, cursor, day_end,
                    filler_title(next_event_after(ch_events, cursor), cursor), desc,
                )

    try:
        ET.indent(root, space="  ")
    except AttributeError:
        pass

    tmp = f"{OUTPUT}.tmp"
    ET.ElementTree(root).write(tmp, encoding="utf-8", xml_declaration=True)
    ET.parse(tmp)
    os.replace(tmp, OUTPUT)
    log(f"Written and XML-validated: {OUTPUT} ({os.path.getsize(OUTPUT)} bytes)")


# ---------------------------------------------------------------------------
# Self-test (بقي كما هو)
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
    <p>-سموحة ضد المصري – الساعة 1 ظهرا عبر قناة أون سبورت 2 بتعليق مدحت شلبي</p>
    <p>-بيراميدز ضد الجونة – الساعة 11 مساء عبر قناة أون سبورت بلس بتعليق خالد الغندور</p>
    </body></html>
    """

    old_window = globals()["in_window"]
    try:
        globals()["in_window"] = lambda dt: True
        parsed = parse_filgoal_article(sample_article, "self-test")
    finally:
        globals()["in_window"] = old_window

    assert len(parsed) == 6, len(parsed)
    assert parsed[0]["channel_id"] in CHANNELS

    assert to_24h(1, "ظهرا") == 13
    assert to_24h(12, "ظهرا") == 12
    assert to_24h(5, "مساء") == 17
    assert to_24h(11, "مساء") == 23
    assert to_24h(12, "صباحا") == 0
    assert to_24h(12, "ليلا") == 0

    noon = next(x for x in parsed if canonical_team(x["home"]) == canonical_team("سموحة"))
    assert noon["start"].astimezone(CAIRO).hour == 13, noon["start"]
    late = next(x for x in parsed if canonical_team(x["home"]) == canonical_team("بيراميدز"))
    assert late["start"].astimezone(CAIRO).hour == 23, late["start"]
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

    _rss_test()
    _cross_source_test()
    _dedupe_test()
    _livesoccertv_test()
    _xml_integrity_test()
    log("SELF TEST | PASS")


def _livesoccertv_test() -> None:
    # عيّنة مطابقة فعلياً لترميز livesoccertv.com (تم التحقق منها مباشرة من
    # الموقع الحي عبر GitHub Actions)، بما فيها كتلة <!-- --> المعطّلة التي
    # يجب على المحلّل تجاهلها ولا يلتقطها كعنصر حقيقي.
    sample = """
    <html><body>
    <table class="schedules blueborder">
      <tr><td colspan="3">Thursday, 27 August</td></tr>
      <tr class="matchrow" data-cid="4" data-has-tv="0"
          data-ko="2026-08-27 14:30:00" id="5738610">
        <td class="timecol">
          <div class="meta">
            <!--
                <datecell>
                <span class='ts' dv='1787855400000' df='mmm dd'>Aug 27</span>
                </datecell>
            -->
            <span class="timecell"><span class="ts" df="h:MMtt"
                dv="1787855400000" id="ko5738610"> 2:30pm</span></span>
          </div>
        </td>
        <td class="matchcol" id="match" valign="top">
          <div class="match-ch-flex"><div class="match-name-col">
            <a href="/match/x/y#5738610" id="g5738610"
               title="Ferencváros vs Trabzonspor">Ferencváros vs Trabzonspor</a>
          </div></div>
        </td>
        <td class="compcell_right" valign="top">
          <a class="flag europe" href="/x/" title="UEFA Europa League">UEFA Europa League</a>
        </td>
      </tr>
      <tr class="matchrow" data-cid="1" data-has-tv="0"
          data-ko="2026-08-23 13:00:00" id="5726974">
        <td class="timecol">
          <div class="meta">
            <span class="timecell"><span class="ts" df="h:MMtt"
                dv="1787515800000" id="ko5726974"> 1:00pm</span></span>
          </div>
        </td>
        <td class="matchcol" id="match" valign="top">
          <div class="match-ch-flex"><div class="match-name-col">
            <a href="/match/a/b#5726974" id="g5726974"
               title="Ceramica Cleopatra vs El Qanah">Ceramica Cleopatra <score>1 - 2</score> El Qanah</a>
          </div></div>
        </td>
        <td class="compcell_right" valign="top">
          <a class="flag africa" href="/y/" title="Egyptian Premier League">Egyptian Premier League</a>
        </td>
      </tr>
    </table>
    </body></html>
    """

    old_window = globals()["in_window"]
    try:
        globals()["in_window"] = lambda dt: True
        parsed = parse_livesoccertv_channel(sample, "ONSportMAX", "self-test")
    finally:
        globals()["in_window"] = old_window

    assert len(parsed) == 2, parsed
    assert all(ev["channel_id"] == "ONSportMAX" for ev in parsed)
    assert all(ev["source_name"] == "LiveSoccerTV" for ev in parsed)

    europa = next(ev for ev in parsed if "Trabzonspor" in ev["away"])
    assert europa["start"] == datetime(2026, 8, 27, 18, 30, tzinfo=UTC), europa["start"]
    assert europa["start"].astimezone(CAIRO).hour == 21, europa["start"]
    assert canonical_team(europa["home"]) == canonical_team("Ferencvaros")

    epl = next(ev for ev in parsed if "Qanah" in ev["away"])
    assert epl["home"] == "Ceramica Cleopatra", epl["home"]
    assert epl["away"] == "El Qanah", epl["away"]
    assert epl["competition"] == "Egyptian Premier League"

    # التأكد من أن الكتلة المعطّلة (<!-- ... -->) لم تُقرأ كعنصر حقيقي.
    assert "Aug 27" not in [ev["home"] for ev in parsed] + [ev["away"] for ev in parsed]

    log("LIVESOCCERTV PARSER | OK")


def _rss_test() -> None:
    feed = """<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0"><channel>
      <title>FilGoal</title>
      <item>
        <title>القنوات الناقلة لمباريات الجولة الثالثة من الدوري المصري</title>
        <link>https://www.filgoal.com/news/123456/x</link>
      </item>
      <item>
        <title>مواعيد مباريات الجولة الرابعة والقنوات الناقلة</title>
        <link>https://www.filgoal.com/news/123457/y</link>
      </item>
      <item>
        <title>الأهلي يتعاقد مع لاعب جديد</title>
        <link>https://www.filgoal.com/news/123458/z</link>
      </item>
    </channel></rss>"""

    items = _parse_rss_items(feed)
    assert len(items) == 3, items

    hits = [l for t, l in items if _looks_like_assignment_headline(ar_norm(t))]
    assert len(hits) == 2, hits
    assert "123458" not in " ".join(hits)

    assert _parse_rss_items("<html>not xml</html>") == []
    assert _parse_rss_items("") == []
    log("RSS PARSER | OK")


def _cross_source_test() -> None:
    pairs = [
        ("Zamalek SC", "الزمالك"),
        ("Al Ahly", "الأهلي"),
        ("Al Masry SC", "المصري"),
        ("Ghazl El-Mehalla", "غزل المحلة"),
        ("El-Mokawloon", "المقاولون العرب"),
        ("ENPPI Club", "الشرقية إنبي"),
        ("Ceramica Cleopatra FC", "سيراميكا كليوباترا"),
        ("Wadi Degla SC", "وادي دجلة"),
        ("Abu Qair Semad", "أبو قير للأسمدة"),
        ("El Gouna FC", "الجونة"),
        ("Pyramids FC", "بيراميدز"),
        ("ZED FC", "زد"),
    ]
    for en, ar in pairs:
        assert canonical_team(en) == canonical_team(ar), f"{en} != {ar}"

    assert canonical_team("Trabzonspor") == "trabzonspor"
    assert display_team("Trabzonspor") == "Trabzonspor"
    assert display_team("Zamalek SC") == "الزمالك"

    must_differ = [
        ("Modern Sport", "Future FC"),
        ("Al Ahly", "National Bank"),
        ("Al Masry", "Al Ahly"),
        ("Ismaily SC", "Al Ittihad Alexandria"),
        ("Smouha", "El Gouna FC"),
    ]
    for a, b in must_differ:
        assert canonical_team(a) != canonical_team(b), f"تصادم مفاتيح: {a} / {b}"

    base = datetime(2026, 8, 21, 20, 0, tzinfo=SOURCE_TZ).astimezone(UTC)
    def mk(src, h, a, delta=0):
        return {
            "channel_id": "ONSport1", "channel_name": "ON Sport 1",
            "start": base + timedelta(minutes=delta),
            "home": h, "away": a, "competition": "Egyptian Premier League",
            "source_name": src, "source": "t", "commentator": "",
            "duration_minutes": MATCH_MINUTES,
        }
    merged = dedupe([
        mk("LiveFootballTV", "Zamalek SC", "Al Ittihad Alexandria", 30),
        mk("FilGoal", "الزمالك", "الاتحاد السكندري", 0),
    ])
    assert len(merged) == 1, merged
    assert merged[0]["source_name"] == "FilGoal"
    log("CROSS-SOURCE NAMES | OK")


def _dedupe_test() -> None:
    base = datetime(2026, 8, 21, 17, 0, tzinfo=SOURCE_TZ).astimezone(UTC)

    def mk(src, delta_min, home="الزمالك", away="الاتحاد السكندري"):
        return {
            "channel_id": "ONSport1", "channel_name": "ON Sport 1",
            "start": base + timedelta(minutes=delta_min),
            "home": home, "away": away, "competition": "Egyptian Premier League",
            "source_name": src, "source": "t", "commentator": "",
            "duration_minutes": MATCH_MINUTES,
        }

    merged = dedupe([mk("LiveFootballTV", 30), mk("FilGoal+EPL", 0)])
    assert len(merged) == 1, merged
    assert merged[0]["source_name"] == "FilGoal+EPL"
    assert merged[0]["start"] == base

    merged = dedupe([mk("FilGoal", 0, home="الأهلي"), mk("LiveFootballTV", 5, home="الاهلي")])
    assert len(merged) == 1, merged

    two = dedupe([mk("FilGoal", 0), mk("FilGoal", 180, home="سموحة", away="المصري")])
    assert len(two) == 2, two
    log("DEDUPE | OK")


def _xml_integrity_test() -> None:
    today = utc_now().astimezone(SOURCE_TZ).date()
    late = datetime(today.year, today.month, today.day, 23, 30, tzinfo=SOURCE_TZ)
    fake = [{
        "channel_id": "ONSport1",
        "channel_name": "ON Sport 1",
        "start": late.astimezone(UTC),
        "home": "أ", "away": "ب",
        "competition": "Test",
        "source_name": "FilGoal",
        "source": "self-test",
        "commentator": "",
        "duration_minutes": MATCH_MINUTES,
    }]

    real_output = globals()["OUTPUT"]
    globals()["OUTPUT"] = "/tmp/_epg_selftest.xml"
    try:
        write_xml(fake)
        tree = ET.parse("/tmp/_epg_selftest.xml")
    finally:
        globals()["OUTPUT"] = real_output

    def _p(s: str) -> datetime:
        return datetime.strptime(s, "%Y%m%d%H%M%S %z")

    last_stop: dict[str, datetime] = {}
    count = 0
    for pr in tree.getroot().findall("programme"):
        ch = pr.get("channel")
        st, sp = _p(pr.get("start")), _p(pr.get("stop"))
        assert sp > st, f"مدة غير صالحة: {ch} {pr.get('start')} -> {pr.get('stop')}"
        prev = last_stop.get(ch)
        assert prev is None or st >= prev, f"تداخل في {ch} عند {pr.get('start')}"
        last_stop[ch] = sp
        count += 1
    assert count > 0
    log(f"XML INTEGRITY | {count} programmes | OK")


def main():
    log(
        "ON SPORT EPG v2 | FilGoal assignments + EPL validation + LiveSoccerTV + LiveFootballTV | "
        f"SOURCE TZ = {SOURCE_TZ.key} | UTC XMLTV | TIVIMATE AUTO-CONVERT | "
        f"MATCH = {MATCH_MINUTES} MIN | 1 + 2 + MAX + PLUS"
    )

    _self_test()

    filgoal = collect_filgoal_events()
    filgoal = validate_with_epl(filgoal)

    lstv = collect_livesoccertv_events()
    lftv = collect_lftv_events()

    events = dedupe(filgoal + lstv + lftv)

    log(f"ON Sport total verified football events: {len(events)}")
    for ev in sorted(events, key=lambda x: x["start"]):
        source_time = ev["start"].astimezone(CAIRO)
        log(
            f"  {ev['channel_name']} | "
            f"{source_time:%Y-%m-%d %H:%M} CAIRO SOURCE TIME | "
            f"{ev['home']} - {ev['away']} | "
            f"{ev['competition']} | {ev['source_name']}"
        )

    if not events and KEEP_OLD_FILE_IF_EMPTY and existing_programme_count(OUTPUT) > 0:
        warn(
            "لم يُعثر على أي مباراة والمصادر على الأرجح متعطّلة — "
            f"تم الإبقاء على {OUTPUT} السابق دون تعديل."
        )
        return 2

    write_xml(events)
    return 0


def existing_programme_count(path: str) -> int:
    try:
        if not os.path.exists(path):
            return 0
        return len(ET.parse(path).getroot().findall("programme"))
    except Exception:
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        warn(f"FATAL: {exc}")
        sys.exit(1)
