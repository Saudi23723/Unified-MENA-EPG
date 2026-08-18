#!/usr/bin/env python3
"""
Alwan Sports XMLTV updater — fixed for actual Telegram format
Handles:
  • Keycap digits: 1️⃣ 2️⃣ ... 9️⃣ and circled numbers ① ② ... ⑩
  • Format: [NUMBER]️⃣ الوان [TIME]am/pm [TEAM1] 🆚 [TEAM2]
  • Uses regex that's more flexible with team names and punctuation
"""

import html
import re
import sys
from datetime import datetime, timedelta, date
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET


TZ = ZoneInfo("Asia/Riyadh")
NOW = datetime.now(TZ)

OUT = Path("alwan_sports_epg_v2.xml")
TELEGRAM_BASE = "https://t.me/s/AlwanSports"

KEEP_DAYS_BACK = 1
KEEP_DAYS_FORWARD = 7
VALID_CHANNELS = set(range(1, 11))
MAX_TELEGRAM_PAGES = 6  # up to roughly 100+ recent posts

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "ar,en;q=0.8",
}

TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)")

ALWAN_RE = re.compile(
    r"(?:ألوان|الوان|ALWAN)(?:\s+SPORTS?)?\s*[.\-:]?\s*(10|[1-9])\b",
    re.I,
)

MATCH_INLINE_RE = re.compile(
    r"(.{2,100}?)\s*(?:🆚|⚔️|⚔|VS\.?|V\.?|ضد|[-–—])\s*(.{2,100})",
    re.I,
)

VS_ONLY = {"VS", "V", "🆚", "⚔", "⚔️", "ضد"}

AR_MONTHS = {
    "يناير": 1, "فبراير": 2, "مارس": 3,
    "أبريل": 4, "ابريل": 4, "مايو": 5,
    "يونيو": 6, "يوليو": 7, "أغسطس": 8,
    "اغسطس": 8, "سبتمبر": 9, "أكتوبر": 10,
    "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}

BAD_TITLE_PARTS = (
    "please open telegram",
    "view this post",
    "جدول مباريات",
    "جدول اليوم",
    "جدول الغد",
    "جدول مباريات الغد",
)


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


def valid_title(title):
    low = norm(title).lower()
    return bool(low) and not any(x in low for x in BAD_TITLE_PARTS)


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


def parse_date(text, reference):
    text = norm(text)
    low = text.lower()

    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b", text)
    if m:
        d, mo, y = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            pass

    months = "|".join(map(re.escape, AR_MONTHS))
    m = re.search(
        rf"\b(\d{{1,2}})\s+({months})\s+(20\d{{2}})\b",
        text,
        re.I,
    )
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


def clean_team(value):
    value = norm(value)
    value = re.sub(
        r"^(?:⚽|🏆|📺|⏰|🕘|🕗|🕖|🔴|🟢|🔵|🟡|🟣|🟠|⚪|•|\||✅|🔥)+\s*",
        "",
        value,
    )
    value = re.sub(
        r"\s*(?:📺|⏰|🎙|🏟|القناة|الساعة).*$",
        "",
        value,
        flags=re.I,
    )
    # Remove country flags at the end
    value = re.sub(r"\s*[🇦-🇿]+\s*$", "", value)
    return value.strip(" |:-")


def post_text(post):
    parts = []

    for selector in (
        ".tgme_widget_message_text",
        ".tgme_widget_message_caption",
    ):
        node = post.select_one(selector)
        if node:
            txt = node.get_text("\n", strip=True)
            if txt:
                parts.append(txt)

    if not parts:
        node = post.select_one(".tgme_widget_message_bubble")
        if node:
            parts.append(node.get_text("\n", strip=True))

    return html.unescape("\n".join(parts)).strip()


def normalize_keycap_digits(text):
    """Convert all keycap and circled digit variants to plain numbers"""
    replacements = {
        # Keycap variants
        "0⃣": "0", "1⃣": "1", "2⃣": "2", "3⃣": "3", "4⃣": "4",
        "5⃣": "5", "6⃣": "6", "7⃣": "7", "8⃣": "8", "9⃣": "9",
        "0️⃣": "0", "1️⃣": "1", "2️⃣": "2", "3️⃣": "3", "4️⃣": "4",
        "5️⃣": "5", "6️⃣": "6", "7️⃣": "7", "8️⃣": "8", "9️⃣": "9",
        # Circled numbers
        "①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5",
        "⑥": "6", "⑦": "7", "⑧": "8", "⑨": "9", "⑩": "10",
        # Double circled
        "🅐": "a", "🅑": "b", "🅒": "c", "🅣": "t",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def parse_fixture_line(line, day):
    """
    Supports:
      TEAM1 VS TEAM2 10:00pm الوان1
      1 الوان 10:00pm TEAM1 VS TEAM2
    Match, time and channel must be on the same line.
    """
    raw = normalize_keycap_digits(norm(line))
    if not raw:
        return None

    if ("الوان" not in raw.lower()
        and "ألوان" not in raw.lower()
        and "ALWAN" not in raw.upper()):
        return None

    vs_match = re.search(r"(?:🆚|⚔️|⚔|VS\\.?|V\\.?|ضد)", raw, re.I)
    if not vs_match:
        return None

    time_match = re.search(
        r"([01]?\\d|2[0-3])[:.]([0-5]\\d)\\s*"
        r"(pm|am|مساءً|مساء|صباحًا|صباحا|صباح|م|ص)?",
        raw,
        re.I,
    )
    if not time_match:
        return None

    channel = None
    m = re.search(
        r"(?:ألوان|الوان|ALWAN)(?:\\s+SPORTS?)?\\s*[.\\-:]?\\s*(10|[1-9])\\b",
        raw,
        re.I,
    )
    if m:
        channel = int(m.group(1))
    else:
        m = re.search(
            r"\\b(10|[1-9])\\s*(?:ألوان|الوان|ALWAN)(?:\\s+SPORTS?)?",
            raw,
            re.I,
        )
        if m:
            channel = int(m.group(1))

    if channel not in VALID_CHANNELS:
        return None

    hh = int(time_match.group(1))
    mm = int(time_match.group(2))
    marker = (time_match.group(3) or "").lower()

    if marker in ("pm", "مساءً", "مساء", "م") and 1 <= hh <= 11:
        hh += 12
    elif marker in ("am", "صباحًا", "صباحا", "صباح", "ص") and hh == 12:
        hh = 0

    if vs_match.start() < time_match.start():
        team_a_raw = raw[:vs_match.start()]
        team_b_raw = raw[vs_match.end():time_match.start()]
    else:
        team_a_raw = raw[time_match.end():vs_match.start()]
        team_b_raw = raw[vs_match.end():]
        team_a_raw = re.sub(
            r"^\\s*(?:ألوان|الوان|ALWAN)(?:\\s+SPORTS?)?\\s*(?:10|[1-9])?\\s*",
            "",
            team_a_raw,
            flags=re.I,
        )

    team_a = clean_team(team_a_raw)
    team_b = clean_team(team_b_raw)

    team_a = re.sub(r"^[^\\w\\u0600-\\u06FF]+|[^\\w\\u0600-\\u06FF]+$", "", team_a).strip()
    team_b = re.sub(r"^[^\\w\\u0600-\\u06FF]+|[^\\w\\u0600-\\u06FF]+$", "", team_b).strip()

    if not team_a or not team_b or len(team_a) > 70 or len(team_b) > 70:
        return None

    title = f"{team_a} - {team_b}"
    if any(x in title.lower() for x in BAD_TITLE_PARTS):
        return None

    start = datetime(day.year, day.month, day.day, hh, mm, tzinfo=TZ)
    if not in_window(start):
        return None

    return {"channel": channel, "start": start, "title": title}


def parse_post(post):
    text = post_text(post)
    if not text:
        return []

    if "please open telegram" in text.lower():
        return []

    post_day = telegram_post_date(post)
    post_target_day = parse_date(text, post_day) or post_day

    events = []

    for line in text.splitlines():
        event = parse_fixture_line(line, post_target_day)
        if event:
            events.append(event)

    return events


def event_key(e):
    return (
        int(e["channel"]),
        e["start"].strftime("%Y%m%d%H%M"),
        norm(e["title"]).casefold(),
    )


def dedupe(events):
    out = []
    seen = set()

    for e in sorted(
        events,
        key=lambda x: (
            x["start"],
            int(x["channel"]),
            x["title"],
        ),
    ):
        key = event_key(e)
        if key in seen:
            continue
        seen.add(key)
        out.append(e)

    return out


def old_channel_id(cid):
    if cid == "AlwanSports":
        return 1

    m = re.fullmatch(
        r"AlwanSports(10|[1-9])",
        cid or "",
        re.I,
    )
    return int(m.group(1)) if m else None


def read_existing():
    if not OUT.exists():
        return []

    try:
        root = ET.parse(OUT).getroot()
    except Exception as exc:
        warn(f"Existing XML unreadable: {exc}")
        return []

    events = []

    for p in root.findall("programme"):
        ch = old_channel_id(p.get("channel") or "")
        if ch not in VALID_CHANNELS:
            continue

        try:
            dt = datetime.strptime(
                (p.get("start") or "")[:14],
                "%Y%m%d%H%M%S",
            ).replace(tzinfo=TZ)
        except Exception:
            continue

        if not in_window(dt):
            continue

        t = p.find("title")
        title = norm(t.text) if t is not None else ""

        if valid_title(title) and title != "لا توجد مباريات مجدولة":
            events.append({
                "channel": ch,
                "start": dt,
                "title": title,
            })

    return events


def crawl_telegram_posts():
    """
    Crawl newest Telegram public page plus older pages via ?before=<message_id>.
    """
    all_posts = []
    seen_post_ids = set()
    before_id = None

    for page_no in range(MAX_TELEGRAM_PAGES):
        url = TELEGRAM_BASE

        if before_id:
            url = f"{TELEGRAM_BASE}?{urlencode({'before': before_id})}"

        try:
            soup = BeautifulSoup(fetch(url), "html.parser")
        except Exception as exc:
            warn(f"Telegram page {page_no + 1} failed: {exc}")
            break

        posts = soup.select(".tgme_widget_message")
        if not posts:
            break

        new_on_page = 0
        ids = []

        for post in posts:
            data_post = post.get("data-post", "")
            m = re.search(r"/(\d+)$", data_post)
            post_id = int(m.group(1)) if m else None

            if post_id is not None:
                ids.append(post_id)
                if post_id in seen_post_ids:
                    continue
                seen_post_ids.add(post_id)

            all_posts.append(post)
            new_on_page += 1

        log(
            f"Telegram page {page_no + 1}: "
            f"{len(posts)} visible / {new_on_page} new posts"
        )

        if not ids:
            break

        oldest = min(ids)

        if before_id is not None and oldest >= before_id:
            break

        before_id = oldest

    log(f"Telegram total unique posts crawled: {len(all_posts)}")
    return all_posts


def write_xml(events):
    tv = ET.Element("tv", {"generator-info-name": "Alwan Sports Telegram EPG V2"})

    for n in range(1, 11):
        cid = f"AlwanSports{n}"
        ch = ET.SubElement(tv, "channel", {"id": cid})
        ET.SubElement(ch, "display-name", {"lang": "ar"}).text = f"ألوان الرياضية {n}"
        ET.SubElement(ch, "display-name", {"lang": "en"}).text = f"Alwan Sports {n}"

    by_channel = {n: [] for n in range(1, 11)}
    for e in dedupe(events):
        n = int(e["channel"])
        if n in VALID_CHANNELS:
            by_channel[n].append(e)

    for n in by_channel:
        by_channel[n].sort(key=lambda e: e["start"])

    first_day = (NOW - timedelta(days=KEEP_DAYS_BACK)).date()
    last_day = (NOW + timedelta(days=KEEP_DAYS_FORWARD)).date()

    day = first_day
    while day <= last_day:
        day_start = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=TZ)
        day_end = day_start + timedelta(days=1)

        for n in range(1, 11):
            cid = f"AlwanSports{n}"
            real = [e for e in by_channel[n] if day_start <= e["start"] < day_end]
            cursor = day_start

            for e in real:
                event_start = max(e["start"], day_start)
                event_stop = min(e["start"] + timedelta(hours=3), day_end)

                if event_start > cursor:
                    p = ET.SubElement(tv, "programme", {
                        "start": cursor.strftime("%Y%m%d%H%M%S %z"),
                        "stop": event_start.strftime("%Y%m%d%H%M%S %z"),
                        "channel": cid,
                    })
                    ET.SubElement(p, "title", {"lang": "ar"}).text = "لا توجد مباريات مجدولة"
                    ET.SubElement(p, "category", {"lang": "en"}).text = "Sports"

                if event_stop > event_start:
                    p = ET.SubElement(tv, "programme", {
                        "start": event_start.strftime("%Y%m%d%H%M%S %z"),
                        "stop": event_stop.strftime("%Y%m%d%H%M%S %z"),
                        "channel": cid,
                    })
                    ET.SubElement(p, "title", {"lang": "ar"}).text = e["title"]
                    ET.SubElement(p, "category", {"lang": "en"}).text = "Sports"
                    ET.SubElement(p, "desc", {"lang": "ar"}).text = "مباراة منقولة على قنوات ألوان الرياضية"
                    cursor = max(cursor, event_stop)

            if cursor < day_end:
                p = ET.SubElement(tv, "programme", {
                    "start": cursor.strftime("%Y%m%d%H%M%S %z"),
                    "stop": day_end.strftime("%Y%m%d%H%M%S %z"),
                    "channel": cid,
                })
                ET.SubElement(p, "title", {"lang": "ar"}).text = "لا توجد مباريات مجدولة"
                ET.SubElement(p, "category", {"lang": "en"}).text = "Sports"

        day += timedelta(days=1)

    ET.indent(tv, space="  ")
    ET.ElementTree(tv).write(OUT, encoding="utf-8", xml_declaration=True)


def main():
    old = read_existing()
    log(f"Existing valid Alwan programmes kept: {len(old)}")

    posts = crawl_telegram_posts()

    fresh = []
    for post in posts:
        fresh.extend(parse_post(post))

    fresh = dedupe(fresh)

    log("IMPROVED parser: handles keycap digits and flexible team name extraction")
    log(f"Alwan newly detected programmes: {len(fresh)}")
    for e in fresh:
        log(
            f"  ALWAN {e['channel']} | "
            f"{e['start']:%Y-%m-%d %H:%M} | {e['title']}"
        )

    # Merge, rather than replace, so a temporarily missing Telegram post
    # cannot remove a valid future event such as tomorrow's fixture.
    merged = {}
    for e in old:
        merged[event_key(e)] = e
    for e in fresh:
        merged[event_key(e)] = e

    final = dedupe([
        e for e in merged.values()
        if in_window(e["start"])
    ])

    log(f"Alwan total real programmes written: {len(final)}")

    write_xml(final)

    real_channels = sorted({int(e["channel"]) for e in final})
    empty_channels = [n for n in range(1, 11) if n not in real_channels]

    log("Guaranteed channel definitions written: AlwanSports1 ... AlwanSports10")
    log("Safe filler guide active: لا توجد مباريات مجدولة fills only empty periods")
    log(f"Real programme channels: {real_channels}")
    log(f"Placeholder-only channels: {empty_channels}")
    log(f"Written: {OUT}")


if __name__ == "__main__":
    main()
