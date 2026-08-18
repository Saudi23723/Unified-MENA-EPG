#!/usr/bin/env python3
"""
Thmanyah Sports XMLTV updater - independent from Alwan.

Strategy:
1) Parse Goal + Kooora daily schedule tables.
2) Crawl recent Goal/Kooora/365Scores article links and extract per-match
   pages that explicitly state Thmanyah 1/2/3.
3) Resolve daily rows that say only "ثمانية" by matching the same fixture
   against a per-match article with an explicit channel number.
4) Never guess a channel number.
5) Keep 1 day back + 7 days forward.
6) Always define Thmanyah 1/2/3 and attach a logo.
"""

import html
import re
import sys
from datetime import datetime, timedelta, date
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

# Stable redirect to the Commons-hosted Thmanyah logo.
THMANYAH_LOGO = (
    "https://commons.wikimedia.org/wiki/"
    "Special:Redirect/file/Thmanyah_Logo.svg?width=512"
)

KEEP_DAYS_BACK = 1
KEEP_DAYS_FORWARD = 7
DEFAULT_CHANNELS = {1, 2, 3}

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
    r"(?:قناة\s*)?(?:ثمانية|thmanyah)"
    r"(?:\s+(?:الرياضية|sports?))?"
    r"\s*[.\-:]?\s*(?:HD\s*)?(10|[1-9])\b",
    re.I,
)
THMANYAH_ANY_RE = re.compile(r"(?:ثمانية|thmanyah)", re.I)

AR_MONTHS = {
    "يناير": 1, "فبراير": 2, "مارس": 3,
    "أبريل": 4, "ابريل": 4, "مايو": 5,
    "يونيو": 6, "يوليو": 7, "أغسطس": 8,
    "اغسطس": 8, "سبتمبر": 9, "أكتوبر": 10,
    "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}

def log(msg):
    print(msg, flush=True)

def warn(msg):
    print(f"WARN {msg}", file=sys.stderr, flush=True)

def norm(value):
    value = html.unescape(value or "")
    value = value.replace("\u200f", " ").replace("\u200e", " ")
    value = value.replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", value).strip()

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=35)
    r.raise_for_status()
    return r.text

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

    # 18/08/2026 or 18-08-2026
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b", text)
    if m:
        d, mo, y = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            pass

    # 18 أغسطس 2026
    months = "|".join(map(re.escape, AR_MONTHS))
    m = re.search(rf"\b(\d{{1,2}})\s+({months})\s+(20\d{{2}})\b", text, re.I)
    if m:
        d = int(m.group(1))
        mo = AR_MONTHS[m.group(2)]
        y = int(m.group(3))
        try:
            return date(y, mo, d)
        except ValueError:
            pass

    if "بعد غد" in low:
        return reference + timedelta(days=2)
    if any(x in low for x in ("غداً", "غدا", "بكرا", "بكرة")):
        return reference + timedelta(days=1)
    if "اليوم" in low:
        return reference
    return None

def parse_time(text):
    """
    Prefer time phrases, and understand Arabic مساء/صباح and pm/am.
    """
    text = norm(text)

    patterns = [
        r"(?:الساعة|الموعد|التوقيت|تمام|عند)\s*(?:الساعة\s*)?"
        r"([01]?\d|2[0-3])[:.]([0-5]\d)\s*(مساءً|مساء|صباحًا|صباحا|صباح|م|ص|pm|am)?",
        r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\s*(مساءً|مساء|صباحًا|صباحا|صباح|م|ص|pm|am)\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            hh = int(m.group(1))
            mm = int(m.group(2))
            marker = (m.group(3) or "").lower()
            if marker in ("مساءً", "مساء", "م", "pm") and 1 <= hh <= 11:
                hh += 12
            if marker in ("صباحًا", "صباحا", "صباح", "ص", "am") and hh == 12:
                hh = 0
            return hh, mm

    # Last fallback only if there is exactly one plausible clock in a short field.
    matches = list(TIME_RE.finditer(text))
    if len(matches) == 1:
        return int(matches[0].group(1)), int(matches[0].group(2))

    return None

def make_dt(day, hh, mm):
    return datetime(day.year, day.month, day.day, int(hh), int(mm), tzinfo=TZ)

def clean_team(value):
    value = norm(value)
    value = re.sub(r"^(?:⚽|🏆|📺|⏰|•|\||✅|🔥)+\s*", "", value)
    value = re.sub(r"\s+(?:السعودية|الإمارات).*$", "", value)
    return value.strip(" |:-")

def fixture_from_cell(text):
    """
    Strict fixture extraction for schedule-table cells.
    """
    text = norm(text)
    patterns = [
        r"^(.{2,60}?)\s+(?:-|–|—|ضد|vs\.?|🆚)\s+(.{2,60}?)$",
        r"^(.{2,60}?)\s+[×x]\s+(.{2,60}?)$",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            a, b = clean_team(m.group(1)), clean_team(m.group(2))
            if a and b:
                return f"{a} - {b}"
    return None

def fixture_from_heading(text):
    """
    Extract match names from per-match article headlines such as:
      ما القنوات الناقلة لمباراة النجمة والاتحاد في كأس الملك...
      النصر ضد الدرعية: الموعد والقنوات...
      مباراة النصر والفتح ...
    """
    text = norm(text)

    patterns = [
        r"مباراة\s+(.{2,45}?)\s+(?:ضد|و)\s*(.{2,45}?)\s+(?:في|ضمن|بـ|بالـ|اليوم|غدًا|غدا|:|\?|$)",
        r"^(.{2,45}?)\s+ضد\s+(.{2,45}?)(?:\s*[:\-–—]|\s+في|\s+ضمن|$)",
        r"مشاهدة\s+مباراة\s+(.{2,45}?)\s+(?:ضد|و)\s*(.{2,45}?)(?:\s+في|\s+ضمن|$)",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            a, b = clean_team(m.group(1)), clean_team(m.group(2))
            if a and b and len(a) <= 50 and len(b) <= 50:
                return f"{a} - {b}"
    return None

def normalize_team_name(value):
    value = norm(value).casefold()
    value = re.sub(r"[^\w\u0600-\u06ff ]+", " ", value)
    value = re.sub(r"\b(?:نادي|نادى|fc|club)\b", " ", value, flags=re.I)
    return re.sub(r"\s+", " ", value).strip()

def fixture_signature(title):
    # Our stored titles use " - " between teams.
    parts = re.split(r"\s+[-–—]\s+", norm(title), maxsplit=1)
    if len(parts) != 2:
        return None
    a, b = normalize_team_name(parts[0]), normalize_team_name(parts[1])
    if not a or not b:
        return None
    return frozenset((a, b))

def event_key(e):
    return (
        int(e["channel"]),
        e["start"].strftime("%Y%m%d%H%M"),
        norm(e["title"]).casefold(),
    )

def dedupe(events):
    out, seen = [], set()
    for e in sorted(events, key=lambda x: (x["start"], int(x["channel"]), x["title"])):
        k = event_key(e)
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out

def discover_links(home_url, label, limit=120):
    """
    Discover article links from a homepage/magazine landing page.
    We inspect article pages themselves for explicit numbered Thmanyah channels.
    """
    try:
        soup = BeautifulSoup(fetch(home_url), "html.parser")
    except Exception as exc:
        warn(f"{label} discovery failed: {exc}")
        return []

    urls, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = urljoin(home_url, a["href"]).split("#", 1)[0]

        if href in seen:
            continue

        if label == "365Scores" and "/ar/news/magazine/" not in href:
            continue
        if label in ("Goal", "Kooora") and not (
            "/ar/" in href or "kooora.com/" in href
        ):
            continue

        seen.add(href)
        urls.append(href)

    log(f"{label} article links discovered: {len(urls)}")
    return urls[:limit]

def discover_daily_articles(home_url, label):
    try:
        soup = BeautifulSoup(fetch(home_url), "html.parser")
    except Exception as exc:
        warn(f"{label} daily discovery failed: {exc}")
        return []

    urls, seen = [], set()
    for a in soup.find_all("a", href=True):
        text = norm(a.get_text(" ", strip=True))
        href = a["href"]
        combined = f"{text} {href}"
        if "جدول مباريات اليوم" not in combined:
            continue
        url = urljoin(home_url, href).split("#", 1)[0]
        if url not in seen:
            seen.add(url)
            urls.append(url)

    log(f"{label} daily schedule articles discovered: {len(urls)}")
    return urls[:12]

def article_date(soup):
    candidates = []
    for selector in ("h1", "title"):
        tag = soup.select_one(selector)
        if tag:
            candidates.append(norm(tag.get_text(" ", strip=True)))
    candidates.append(norm(soup.get_text(" ", strip=True))[:7000])

    for c in candidates:
        d = parse_date(c, NOW.date())
        if d:
            return d
    return NOW.date()

def parse_daily_article(url):
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
    except Exception as exc:
        warn(f"Daily schedule failed {url}: {exc}")
        return []

    day = article_date(soup)
    events = []

    for tr in soup.find_all("tr"):
        cells = [norm(x.get_text(" ", strip=True)) for x in tr.find_all(["td", "th"])]
        cells = [x for x in cells if x]
        if len(cells) < 2:
            continue

        joined = " | ".join(cells)
        if not THMANYAH_ANY_RE.search(joined):
            continue

        title = None
        for cell in cells:
            title = fixture_from_cell(cell)
            if title:
                break
        if not title:
            continue

        # Prefer time from individual cells, not the full row, to avoid UAE time.
        time_value = None
        for cell in cells:
            if "السعودية" in cell or "مكة" in cell or "الموعد" in cell:
                time_value = parse_time(cell)
                if time_value:
                    break
        if not time_value:
            for cell in cells:
                time_value = parse_time(cell)
                if time_value:
                    break
        if not time_value:
            continue

        cm = THMANYAH_NUMBER_RE.search(joined)
        channel = int(cm.group(1)) if cm else None
        hh, mm = time_value

        events.append({
            "channel": channel,
            "start": make_dt(day, hh, mm),
            "title": title,
            "source": url,
        })

    return events

def parse_numbered_article(url, label):
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
    except Exception:
        return None

    h1 = soup.find("h1")
    heading = norm(h1.get_text(" ", strip=True)) if h1 else ""
    body = norm(soup.get_text(" ", strip=True))

    # Require an explicit channel number in the article.
    cm = THMANYAH_NUMBER_RE.search(body)
    if not cm:
        return None

    channel = int(cm.group(1))
    if channel < 1 or channel > 10:
        return None

    title = fixture_from_heading(heading)
    if not title:
        return None

    day = parse_date(heading, NOW.date()) or parse_date(body, NOW.date())
    if not day:
        return None

    # Prefer relevant paragraphs containing timing words.
    time_value = None
    for node in soup.find_all(["p", "td", "li"]):
        txt = norm(node.get_text(" ", strip=True))
        if any(word in txt for word in ("الساعة", "الموعد", "تنطلق", "صافرة", "بتوقيت")):
            time_value = parse_time(txt)
            if time_value:
                break

    if not time_value:
        # Short body fallback around "الساعة"
        m = re.search(r".{0,100}(?:الساعة|الموعد|تنطلق|صافرة).{0,120}", body)
        if m:
            time_value = parse_time(m.group(0))

    if not time_value:
        return None

    hh, mm = time_value
    event = {
        "channel": channel,
        "start": make_dt(day, hh, mm),
        "title": title,
        "source": f"{label}: {url}",
    }

    return event if in_window(event["start"]) else None

def collect_numbered_articles():
    # More than one provider because no single site numbers every fixture every day.
    sources = [
        (GOAL_HOME, "Goal", 100),
        (KOOORA_HOME, "Kooora", 100),
        (SCORES365_HOME, "365Scores", 140),
    ]

    events = []
    checked = set()

    for home, label, limit in sources:
        for url in discover_links(home, label, limit):
            if url in checked:
                continue
            checked.add(url)
            e = parse_numbered_article(url, label)
            if e:
                events.append(e)

    events = dedupe(events)
    log(f"Explicit numbered Thmanyah fixtures detected: {len(events)}")
    for e in events:
        log(
            f"  CONFIRMED THMANYAH {e['channel']} | "
            f"{e['start']:%Y-%m-%d %H:%M} | {e['title']}"
        )
    return events

def resolve_daily(daily, confirmations):
    by_sig = {}
    for e in confirmations:
        sig = fixture_signature(e["title"])
        if sig:
            by_sig.setdefault(sig, []).append(e)

    resolved = []

    for e in daily:
        if e["channel"] is not None:
            resolved.append(e)
            continue

        sig = fixture_signature(e["title"])
        candidates = by_sig.get(sig, []) if sig else []
        candidates = [
            x for x in candidates
            if abs((x["start"].date() - e["start"].date()).days) <= 1
        ]

        if not candidates:
            log(
                "UNRESOLVED THMANYAH | "
                f"{e['start']:%Y-%m-%d %H:%M} | {e['title']}"
            )
            continue

        # Match the closest time on the same/adjacent day.
        best = min(
            candidates,
            key=lambda x: abs((x["start"] - e["start"]).total_seconds())
        )
        fixed = dict(e)
        fixed["channel"] = best["channel"]
        fixed["source"] = f"{e['source']} + {best['source']}"
        resolved.append(fixed)

    # Also keep confirmed per-match articles if daily schedule discovery missed them.
    resolved.extend(confirmations)
    return dedupe([e for e in resolved if e["channel"] is not None])

def read_existing():
    if not OUT.exists():
        return []

    try:
        root = ET.parse(OUT).getroot()
    except Exception as exc:
        warn(f"Existing Thmanyah XML unreadable: {exc}")
        return []

    out = []
    for p in root.findall("programme"):
        cid = p.get("channel") or ""
        cm = re.search(r"Thmanyah(10|[1-9])", cid, re.I)
        if not cm:
            continue

        raw = p.get("start") or ""
        try:
            dt = datetime.strptime(raw[:14], "%Y%m%d%H%M%S").replace(tzinfo=TZ)
        except Exception:
            continue
        if not in_window(dt):
            continue

        title_el = p.find("title")
        title = norm(title_el.text) if title_el is not None else ""
        if not title or not fixture_signature(title):
            continue

        out.append({
            "channel": int(cm.group(1)),
            "start": dt,
            "title": title,
            "source": "existing XML",
        })
    return out

def merge_existing(old, fresh):
    merged = {}
    for e in old:
        merged[event_key(e)] = e
    for e in fresh:
        merged[event_key(e)] = e
    return dedupe([e for e in merged.values() if in_window(e["start"])])

def write_xml(events):
    observed = {int(e["channel"]) for e in events}
    channels = sorted(DEFAULT_CHANNELS | observed)

    tv = ET.Element("tv", {"generator-info-name": "Thmanyah Sports Verified Multi-Source EPG"})

    for n in channels:
        cid = f"Thmanyah{n}.sa"
        ch = ET.SubElement(tv, "channel", {"id": cid})
        ET.SubElement(ch, "display-name", {"lang": "ar"}).text = f"ثمانية {n}"
        ET.SubElement(ch, "display-name", {"lang": "en"}).text = f"Thmanyah {n}"
        ET.SubElement(ch, "icon", {"src": THMANYAH_LOGO})

    for e in events:
        cid = f"Thmanyah{int(e['channel'])}.sa"
        stop = e["start"] + timedelta(hours=3)

        p = ET.SubElement(
            tv,
            "programme",
            {
                "start": e["start"].strftime("%Y%m%d%H%M%S %z"),
                "stop": stop.strftime("%Y%m%d%H%M%S %z"),
                "channel": cid,
            },
        )
        ET.SubElement(p, "title", {"lang": "ar"}).text = e["title"]
        ET.SubElement(p, "category", {"lang": "en"}).text = "Sports"
        ET.SubElement(p, "desc", {"lang": "ar"}).text = "مباراة منقولة على قنوات ثمانية"

    ET.indent(tv, space="  ")
    ET.ElementTree(tv).write(OUT, encoding="utf-8", xml_declaration=True)

def main():
    old = read_existing()
    log(f"Existing valid Thmanyah programmes kept: {len(old)}")

    daily_urls = (
        discover_daily_articles(GOAL_HOME, "Goal")
        + discover_daily_articles(KOOORA_HOME, "Kooora")
    )
    daily_urls = list(dict.fromkeys(daily_urls))

    daily = []
    for url in daily_urls:
        found = parse_daily_article(url)
        if found:
            log(f"Daily fixtures from {url}: {len(found)}")
            daily.extend(found)

    confirmations = collect_numbered_articles()
    fresh = resolve_daily(daily, confirmations)
    fresh = [e for e in fresh if in_window(e["start"])]

    log(f"Thmanyah newly resolved programmes: {len(fresh)}")
    for e in fresh:
        log(
            f"  THMANYAH {e['channel']} | "
            f"{e['start']:%Y-%m-%d %H:%M} | {e['title']}"
        )

    # If fresh data was found, rebuild the XML from fresh verified data only.
    # This deliberately removes stale/incorrect programmes created by older parsers.
    if fresh:
        final_events = dedupe(fresh)
        log(f"Thmanyah total programmes written: {len(final_events)}")
        write_xml(final_events)
        log(f"Written: {OUT}")
        return

    # Safety: if every source temporarily fails, do not erase a useful existing XML.
    if old:
        warn("No fresh Thmanyah data; existing XML left untouched")
        return

    # First run with no data: still create channel definitions 1-3 + logo.
    write_xml([])
    log(f"Written empty channel-only XML: {OUT}")

if __name__ == "__main__":
    main()
