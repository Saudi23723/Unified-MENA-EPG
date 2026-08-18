#!/usr/bin/env python3
"""
Rolling XMLTV EPG generator for:
  • Thmanyah Sports channels
  • Alwan Sports channels

THMANYAH:
  • Goal + Kooora daily schedule articles
  • 365Scores recent magazine articles for numbered Thmanyah channels
  • Resolve unnumbered "ثمانية" fixtures by matching team names with 365Scores
  • Keep a rolling 1-day-back / 7-days-forward EPG window

ALWAN:
  • Read the public Telegram page @AlwanSports
  • Parse full rendered post text, including captions
  • Support VS / ضد / 🆚 / dash separators
  • Support multiple fixtures in one post
  • Preserve existing XML if Telegram temporarily returns zero useful fixtures

Dependencies:
  requests
  beautifulsoup4
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

THMANYAH_OUT = Path("thmanyah_epg.xml")
ALWAN_OUT = Path("alwan_sports_epg.xml")

GOAL_HOME = "https://www.goal.com/ar"
KOOORA_HOME = "https://www.kooora.com/"
SCORES365_HOME = "https://www.365scores.com/ar/news/magazine/"
ALWAN_TELEGRAM = "https://t.me/s/AlwanSports"

KEEP_DAYS_BACK = 1
KEEP_DAYS_FORWARD = 7

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
    r"(?:ثمانية|thmanyah)\s*[.\-:]?\s*([1-9]|10)\b", re.I
)
THMANYAH_ANY_RE = re.compile(r"(?:ثمانية|thmanyah)", re.I)
ALWAN_NUMBER_RE = re.compile(
    r"(?:ألوان|الوان|alwan)(?:\s+sports?)?\s*[.\-:]?\s*([1-9]|10)\b",
    re.I,
)
MATCH_RE = re.compile(
    r"(.{2,80}?)\s*(?:🆚|⚔️|⚔|vs\.?|v\.?|ضد|[-–—])\s*(.{2,80})",
    re.I,
)

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

def parse_date(text, reference=None):
    text = norm(text)
    low = text.lower()
    reference = reference or NOW.date()

    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b", text)
    if m:
        d, mth, y = map(int, m.groups())
        try:
            return date(y, mth, d)
        except ValueError:
            pass

    months_pattern = "|".join(map(re.escape, AR_MONTHS))
    m = re.search(
        rf"\b(\d{{1,2}})\s+({months_pattern})(?:/آب)?\s+(20\d{{2}})\b",
        text,
        re.I,
    )
    if m:
        d = int(m.group(1))
        mth = AR_MONTHS[m.group(2)]
        y = int(m.group(3))
        try:
            return date(y, mth, d)
        except ValueError:
            pass

    if "بعد غد" in low:
        return reference + timedelta(days=2)
    if any(x in low for x in ("غداً", "غدا", "بكرا", "بكرة")):
        return reference + timedelta(days=1)
    if "اليوم" in low:
        return reference
    return None

def make_dt(day, hh, mm):
    return datetime(day.year, day.month, day.day, int(hh), int(mm), tzinfo=TZ)

def in_keep_window(dt):
    return (NOW - timedelta(days=KEEP_DAYS_BACK)) <= dt <= (
        NOW + timedelta(days=KEEP_DAYS_FORWARD)
    )

def normalize_team_name(s):
    s = norm(s).casefold()
    s = re.sub(r"[^\w\u0600-\u06ff ]+", " ", s)
    s = re.sub(r"\b(?:نادي|fc|club)\b", " ", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()

def fixture_signature(title):
    m = MATCH_RE.search(norm(title))
    if not m:
        return None
    a = normalize_team_name(m.group(1))
    b = normalize_team_name(m.group(2))
    if not a or not b:
        return None
    return frozenset((a, b))

def programme_key(e):
    return (
        str(e["channel"]),
        e["start"].strftime("%Y%m%d%H%M"),
        norm(e["title"]).casefold(),
    )

def dedupe(events):
    out, seen = [], set()
    for e in sorted(events, key=lambda x: (x["start"], str(x["channel"]), x["title"])):
        k = programme_key(e)
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out

def read_existing_xml(path, kind):
    if not path.exists():
        return []
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        warn(f"Could not read existing {path}: {exc}")
        return []

    result = []
    for p in root.findall("programme"):
        raw = (p.get("start") or "").strip()
        try:
            dt = datetime.strptime(raw[:14], "%Y%m%d%H%M%S").replace(tzinfo=TZ)
        except Exception:
            continue
        if not in_keep_window(dt):
            continue

        title_el = p.find("title")
        if title_el is None or not norm(title_el.text):
            continue

        channel_id = p.get("channel") or ""
        if kind == "thmanyah":
            m = re.search(r"Thmanyah(\d+)", channel_id, re.I)
            if not m:
                continue
            channel = int(m.group(1))
        else:
            m = re.search(r"AlwanSports(\d+)?", channel_id, re.I)
            channel = int(m.group(1)) if m and m.group(1) else 1

        result.append({
            "channel": channel,
            "start": dt,
            "title": norm(title_el.text),
            "source": "existing XML",
        })
    return result

def discover_daily_articles(home_url, label):
    try:
        soup = BeautifulSoup(fetch(home_url), "html.parser")
    except Exception as exc:
        warn(f"{label} discovery failed: {exc}")
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

    log(f"{label} schedule articles discovered: {len(urls)}")
    return urls[:12]

def article_date(soup):
    candidates = []
    for selector in ("h1", "title"):
        tag = soup.select_one(selector)
        if tag:
            candidates.append(norm(tag.get_text(" ", strip=True)))
    candidates.append(norm(soup.get_text(" ", strip=True))[:6000])

    for c in candidates:
        d = parse_date(c, NOW.date())
        if d:
            return d
    return NOW.date()

def clean_fixture_title(value):
    value = norm(value)
    value = re.sub(r"\s+(?:السعودية|الإمارات).*$", "", value)
    return value.strip(" |")

def parse_daily_thmanyah_article(url):
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
    except Exception as exc:
        warn(f"Daily Thmanyah article failed {url}: {exc}")
        return []

    day = article_date(soup)
    events = []

    for tr in soup.find_all("tr"):
        cells = [norm(x.get_text(" ", strip=True)) for x in tr.find_all(["td", "th"])]
        cells = [x for x in cells if x]
        joined = " | ".join(cells)
        if not THMANYAH_ANY_RE.search(joined):
            continue
        tm = TIME_RE.search(joined)
        if not tm:
            continue
        title = next((c for c in cells if MATCH_RE.search(c)), None)
        if not title:
            continue
        cm = THMANYAH_NUMBER_RE.search(joined)
        events.append({
            "channel": int(cm.group(1)) if cm else None,
            "start": make_dt(day, tm.group(1), tm.group(2)),
            "title": clean_fixture_title(title),
            "source": url,
        })

    if not events:
        lines = [norm(x) for x in soup.get_text("\n", strip=True).splitlines()]
        lines = [x for x in lines if x]
        for i, line in enumerate(lines):
            if not THMANYAH_ANY_RE.search(line):
                continue
            block = lines[max(0, i - 3):min(len(lines), i + 3)]
            joined = " | ".join(block)
            tm = TIME_RE.search(joined)
            title = next((x for x in block if MATCH_RE.search(x)), None)
            if not tm or not title:
                continue
            cm = THMANYAH_NUMBER_RE.search(joined)
            events.append({
                "channel": int(cm.group(1)) if cm else None,
                "start": make_dt(day, tm.group(1), tm.group(2)),
                "title": clean_fixture_title(title),
                "source": url,
            })
    return events

def discover_365_article_links():
    try:
        soup = BeautifulSoup(fetch(SCORES365_HOME), "html.parser")
    except Exception as exc:
        warn(f"365Scores discovery failed: {exc}")
        return []

    urls, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = urljoin(SCORES365_HOME, a["href"]).split("#", 1)[0]
        if "/ar/news/magazine/" not in href:
            continue
        if href.rstrip("/") == SCORES365_HOME.rstrip("/"):
            continue
        if href not in seen:
            seen.add(href)
            urls.append(href)

    log(f"365Scores recent article links discovered: {len(urls)}")
    return urls[:80]

def extract_title_from_365(soup):
    h1 = soup.find("h1")
    h1text = norm(h1.get_text(" ", strip=True)) if h1 else ""

    patterns = [
        r"([\u0600-\u06ffA-Za-z0-9 .]+?)\s+(?:ضد|[-–—]|vs\.?)\s+"
        r"([\u0600-\u06ffA-Za-z0-9 .]+)",
        r"مباراة\s+([\u0600-\u06ffA-Za-z0-9 .]+?)\s+"
        r"(?:ضد|[-–—]|vs\.?)\s+([\u0600-\u06ffA-Za-z0-9 .]+)",
    ]

    for pattern in patterns:
        m = re.search(pattern, h1text, re.I)
        if m:
            return f"{norm(m.group(1))} - {norm(m.group(2))}"

    body = norm(soup.get_text(" ", strip=True))
    for pattern in patterns:
        m = re.search(pattern, body, re.I)
        if m:
            return f"{norm(m.group(1))} - {norm(m.group(2))}"
    return None

def parse_numbered_365_article(url):
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
    except Exception:
        return None

    text = norm(soup.get_text(" ", strip=True))
    cm = THMANYAH_NUMBER_RE.search(text)
    if not cm:
        return None

    d = parse_date(text, NOW.date())
    if not d:
        return None

    tm = re.search(
        r"(?:الساعة|التوقيت|عند|تمام)\s*(?:الساعة\s*)?"
        r"([01]?\d|2[0-3])[:.]([0-5]\d)",
        text,
        re.I,
    )
    if not tm:
        tm = TIME_RE.search(text)
    if not tm:
        return None

    title = extract_title_from_365(soup)
    if not title:
        return None

    return {
        "channel": int(cm.group(1)),
        "start": make_dt(d, tm.group(1), tm.group(2)),
        "title": title,
        "source": url,
    }

def collect_365_numbered():
    events = []
    for url in discover_365_article_links():
        e = parse_numbered_365_article(url)
        if e and in_keep_window(e["start"]):
            events.append(e)

    events = dedupe(events)
    log(f"365Scores numbered Thmanyah fixtures detected: {len(events)}")
    return events

def resolve_thmanyah(daily, numbered):
    resolved = []
    numbered_by_sig = {}

    for e in numbered:
        sig = fixture_signature(e["title"])
        if sig:
            numbered_by_sig.setdefault(sig, []).append(e)

    for e in daily:
        if e["channel"] is not None:
            resolved.append(e)
            continue

        sig = fixture_signature(e["title"])
        candidates = numbered_by_sig.get(sig, []) if sig else []
        candidates = [
            x for x in candidates
            if abs((x["start"].date() - e["start"].date()).days) <= 1
        ]

        if candidates:
            best = min(
                candidates,
                key=lambda x: abs((x["start"] - e["start"]).total_seconds())
            )
            fixed = dict(e)
            fixed["channel"] = best["channel"]
            fixed["source"] = f"{e['source']} + {best['source']}"
            resolved.append(fixed)
        else:
            log(
                "UNRESOLVED THMANYAH | "
                f"{e['start']:%Y-%m-%d %H:%M} | {e['title']}"
            )

    resolved.extend(numbered)
    return dedupe([e for e in resolved if e["channel"] is not None])

def scrape_thmanyah():
    daily_urls = (
        discover_daily_articles(GOAL_HOME, "Goal")
        + discover_daily_articles(KOOORA_HOME, "Kooora")
    )
    daily_urls = list(dict.fromkeys(daily_urls))

    daily = []
    for url in daily_urls:
        found = parse_daily_thmanyah_article(url)
        if found:
            log(f"Daily Thmanyah fixtures from {url}: {len(found)}")
            daily.extend(found)

    numbered = collect_365_numbered()
    final = resolve_thmanyah(daily, numbered)
    final = [e for e in final if in_keep_window(e["start"])]

    log(f"Thmanyah newly resolved programmes: {len(final)}")
    return final

def telegram_post_reference_date(post):
    time_tag = post.select_one("time[datetime]")
    if time_tag:
        raw = time_tag.get("datetime", "")
        try:
            return datetime.fromisoformat(
                raw.replace("Z", "+00:00")
            ).astimezone(TZ).date()
        except Exception:
            pass
    return NOW.date()

def telegram_post_text(post):
    selectors = [
        ".tgme_widget_message_text",
        ".tgme_widget_message_caption",
        ".tgme_widget_message_bubble",
    ]
    parts = []
    for selector in selectors:
        node = post.select_one(selector)
        if node:
            txt = node.get_text("\n", strip=True)
            if txt and txt not in parts:
                parts.append(txt)

    if not parts:
        parts.append(post.get_text("\n", strip=True))

    return html.unescape("\n".join(parts)).strip()

def alwan_channel_from_block(text):
    m = ALWAN_NUMBER_RE.search(text)
    if m:
        return int(m.group(1))

    m = re.search(
        r"\bALWAN(?:SPORTS?)?\s*([1-9]|10)\b",
        text,
        re.I,
    )
    if m:
        return int(m.group(1))
    return 1

def clean_side(value):
    value = norm(value)
    value = re.sub(
        r"^(?:⚽|🏆|🥅|📺|⏰|🕘|🕗|🕖|🔴|🟢|⚪|🔵|🟡|🟣|🟠|\||•)+\s*",
        "",
        value,
    )
    value = re.sub(r"\s*(?:⏰|📺|🎙|🏟).*?$", "", value)
    return value.strip(" |:-")

def extract_match_from_text(text):
    for line in text.splitlines():
        line = norm(line)
        if not line:
            continue

        m = MATCH_RE.search(line)
        if m:
            a = clean_side(m.group(1))
            b = clean_side(m.group(2))
            if a and b:
                return f"{a} - {b}"

    flat = norm(text.replace("\n", " "))
    m = MATCH_RE.search(flat)
    if m:
        a = clean_side(m.group(1))
        b = clean_side(m.group(2))
        if a and b:
            return f"{a} - {b}"
    return None

def split_alwan_blocks(text):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    if not lines:
        return []

    match_indexes = [
        i for i, line in enumerate(lines)
        if MATCH_RE.search(norm(line))
    ]

    if len(match_indexes) <= 1:
        return ["\n".join(lines)]

    blocks = []
    for pos, idx in enumerate(match_indexes):
        start = max(0, idx - 2)
        if pos + 1 < len(match_indexes):
            end = max(idx + 1, match_indexes[pos + 1] - 2)
        else:
            end = len(lines)
        blocks.append("\n".join(lines[start:end]))
    return blocks

def parse_alwan_block(block, post_day):
    title = extract_match_from_text(block)
    if not title:
        return None

    tm = TIME_RE.search(block)
    if not tm:
        return None

    day = parse_date(block, post_day) or post_day
    channel = alwan_channel_from_block(block)

    return {
        "channel": channel,
        "start": make_dt(day, tm.group(1), tm.group(2)),
        "title": title,
        "source": ALWAN_TELEGRAM,
    }

def scrape_alwan():
    try:
        soup = BeautifulSoup(fetch(ALWAN_TELEGRAM), "html.parser")
    except Exception as exc:
        warn(f"Alwan Telegram fetch failed: {exc}")
        return []

    posts = soup.select(".tgme_widget_message")
    log(f"Alwan Telegram posts visible: {len(posts)}")

    events = []
    debug_limit = 6
    debug_shown = 0

    for post in posts:
        text = telegram_post_text(post)
        if not text:
            continue

        ref_day = telegram_post_reference_date(post)
        blocks = split_alwan_blocks(text)
        post_events = []

        for block in blocks:
            event = parse_alwan_block(block, ref_day)
            if event:
                post_events.append(event)

        if post_events:
            events.extend(post_events)
        elif debug_shown < debug_limit:
            excerpt = norm(text.replace("\n", " | "))[:500]
            log(f"ALWAN DEBUG UNPARSED POST: {excerpt}")
            debug_shown += 1

    events = [
        e for e in dedupe(events)
        if in_keep_window(e["start"])
    ]
    log(f"Alwan newly detected programmes: {len(events)}")
    return events

def merge_with_existing(old, fresh):
    merged = {}
    for e in old:
        merged[programme_key(e)] = e
    for e in fresh:
        merged[programme_key(e)] = e
    return dedupe([
        e for e in merged.values()
        if in_keep_window(e["start"])
    ])

def write_xml(path, kind, events):
    if kind == "thmanyah":
        numbers = sorted({int(e["channel"]) for e in events} | {1, 2, 3})
        generator = "Thmanyah Sports rolling EPG"
    else:
        numbers = sorted({int(e["channel"]) for e in events} or {1})
        generator = "Alwan Sports rolling EPG"

    tv = ET.Element("tv", {"generator-info-name": generator})

    for n in numbers:
        if kind == "thmanyah":
            cid = f"Thmanyah{n}.sa"
            ar = f"ثمانية {n}"
            en = f"Thmanyah {n}"
        else:
            cid = "AlwanSports" if n == 1 else f"AlwanSports{n}"
            ar = "ألوان الرياضية" if n == 1 else f"ألوان الرياضية {n}"
            en = "Alwan Sports" if n == 1 else f"Alwan Sports {n}"

        ch = ET.SubElement(tv, "channel", {"id": cid})
        ET.SubElement(ch, "display-name", {"lang": "ar"}).text = ar
        ET.SubElement(ch, "display-name", {"lang": "en"}).text = en

    for e in events:
        if kind == "thmanyah":
            cid = f"Thmanyah{int(e['channel'])}.sa"
        else:
            cid = (
                "AlwanSports"
                if int(e["channel"]) == 1
                else f"AlwanSports{int(e['channel'])}"
            )

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
        ET.SubElement(p, "desc", {"lang": "ar"}).text = f"المصدر: {e['source']}"

    ET.indent(tv, space="  ")
    ET.ElementTree(tv).write(
        path,
        encoding="utf-8",
        xml_declaration=True,
    )

def main():
    old_thmanyah = read_existing_xml(THMANYAH_OUT, "thmanyah")
    old_alwan = read_existing_xml(ALWAN_OUT, "alwan")

    log(f"Existing Thmanyah programmes kept: {len(old_thmanyah)}")
    log(f"Existing Alwan programmes kept: {len(old_alwan)}")

    fresh_thmanyah = scrape_thmanyah()
    fresh_alwan = scrape_alwan()

    thmanyah = merge_with_existing(old_thmanyah, fresh_thmanyah)
    alwan = merge_with_existing(old_alwan, fresh_alwan)

    log(f"Thmanyah total programmes after merge: {len(thmanyah)}")
    for e in thmanyah:
        log(
            f"  THMANYAH {e['channel']} | "
            f"{e['start']:%Y-%m-%d %H:%M} | {e['title']}"
        )

    log(f"Alwan total programmes after merge: {len(alwan)}")
    for e in alwan:
        log(
            f"  ALWAN {e['channel']} | "
            f"{e['start']:%Y-%m-%d %H:%M} | {e['title']}"
        )

    if thmanyah or not THMANYAH_OUT.exists():
        write_xml(THMANYAH_OUT, "thmanyah", thmanyah)
        log(f"Written: {THMANYAH_OUT}")
    else:
        warn("Thmanyah returned zero; existing XML left untouched")

    if alwan or not ALWAN_OUT.exists():
        write_xml(ALWAN_OUT, "alwan", alwan)
        log(f"Written: {ALWAN_OUT}")
    else:
        warn("Alwan returned zero; existing XML left untouched")

if __name__ == "__main__":
    main()
