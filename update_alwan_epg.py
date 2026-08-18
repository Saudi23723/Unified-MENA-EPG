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
    Parse a Telegram line in the format:
    [NUMBER] الوان [TIME]am/pm [TEAM1] 🆚 [TEAM2]
    
    Examples:
    1️⃣ الوان 9:45pm باريس 🆚 فيتيريال
    ② الوان 5:30pm بارزل 🆚 برشلونة
    3 الوان 6:00pm شالكه 🆚 ريال مدريد
    """
    raw = normalize_keycap_digits(norm(line))

    if not raw:
        return None

    # Check if line contains "الوان" or "ألوان"
    if "الوان" not in raw.lower() and "ألوان" not in raw.lower() and "ALWAN" not in raw.upper():
        return None

    # Parse: extract channel number, time, and teams
    # Pattern: [optional number] + الوان + time + team1 VS team2
    
    # Step 1: Extract channel number (must be 1-10)
    channel = None
    channel_match = re.search(r"(10|[1-9])\s*(?:الوان|ألوان|ALWAN)", raw, re.I)
    if channel_match:
        channel = int(channel_match.group(1))
    
    if channel is None or channel not in VALID_CHANNELS:
        return None

    # Step 2: Extract time (HH:MM with optional am/pm)
    time_match = re.search(
        r"([01]?\d|2[0-3])[:.]([0-5]\d)\s*(pm|am|مساءً|مساء|صباحًا|صباحا|صباح|م|ص)?",
        raw,
        re.I
    )
    if not time_match:
        return None

    hh = int(time_match.group(1))
    mm = int(time_match.group(2))
    marker = (time_match.group(3) or "").lower()

    # Convert to 24-hour format
    if marker in ("pm", "مساءً", "مساء", "م") and 1 <= hh <= 11:
        hh += 12
    elif marker in ("am", "صباحًا", "صباحا", "صباح", "ص") and hh == 12:
        hh = 0

    # Step 3: Extract teams (text between time and VS, and after VS)
    # Remove everything before the time and after channel number to get match text
    time_pos = time_match.start()
    text_after_time = raw[time_pos:]
    
    # Find VS pattern
    vs_match = re.search(r"(?:🆚|⚔️|⚔|VS\.?|V\.?|ضد|[-–—])", text_after_time, re.I)
    if not vs_match:
        return None
    
    # Extract team names
    before_vs = text_after_time[:vs_match.start()].strip()
    after_vs = text_after_time[vs_match.end():].strip()
    
    # Clean team names
    team_a = clean_team(before_vs)
    team_b = clean_team(after_vs)

    if not team_a or not team_b or len(team_a) > 70 or len(team_b) > 70:
        return None

    # Check for bad title parts
    full_title = f"{team_a} - {team_b}"
    if any(x in full_title.lower() for x in BAD_TITLE_PARTS):
        return None

    start = datetime(day.year, day.month, day.day, hh, mm, tzinfo=TZ)
    if not in_window(start):
        return None

    return {
        "channel": channel,
        "start": start,
        "title": full_title,
    }


def parse_post(post):
    text = post_text(post)
    if not text:
        return []

    if "please open telegram" in text.lower():
        return []

    post_day = telegram_post_date(post)
    post_target_day = parse_date(text, post_day) or post_day

    # Diagnostic: print candidate raw lines even if parsing fails.
    raw_lines = [norm(x) for x in text.splitlines() if norm(x)]

    if any(
        ("الوان" in x.lower() or "ألوان" in x.lower() or "ALWAN" in x.upper())
        for x in raw_lines
    ):
        log("ALWAN DEBUG POST START")
        for raw_line in raw_lines:
            if (
                "الوان" in raw_line.lower()
                or "ألوان" in raw_line.lower()
                or "ALWAN" in raw_line.upper()
                or re.search(r"(?:🆚|⚔️|⚔|VS\.?|V\.?|ضد)", raw_line, re.I)
            ):
                log(f"ALWAN DEBUG RAW CANDIDATE: {raw_line}")
        log("ALWAN DEBUG POST END")

    events = []

    # Strategy 1: current strict same-line parser.
    for line in raw_lines:
        event = parse_fixture_line(line, post_target_day)
        if event:
            log(f"ALWAN PARSER S1: ALWAN {event['channel']} | {event['start']:%Y-%m-%d %H:%M} | {event['title']}")
            events.append(event)

    # Strategy 2: reverse logical order after Telegram RTL extraction.
    # Example logical order can become:
    # 2 الوان 10:00pm ليون 🆚 فنربخشة
    for line in raw_lines:
        raw = normalize_keycap_digits(line)
        if not re.search(r"(?:الوان|ألوان|ALWAN)", raw, re.I):
            continue
        if not re.search(r"(?:🆚|⚔️|⚔|VS\.?|V\.?|ضد)", raw, re.I):
            continue

        # Explicit channel before Alwan.
        cm = re.search(
            r"\b(10|[1-9])\s*[|:.\-]?\s*(?:الوان|ألوان|ALWAN)(?:\s+SPORTS?)?",
            raw,
            re.I,
        )
        # Or channel after Alwan.
        if not cm:
            cm = re.search(
                r"(?:الوان|ألوان|ALWAN)(?:\s+SPORTS?)?\s*[|:.\-]?\s*(10|[1-9])\b",
                raw,
                re.I,
            )
        if not cm:
            continue
        channel = int(cm.group(1))
        if channel not in VALID_CHANNELS:
            continue

        tm = re.search(
            r"([01]?\d|2[0-3])[:.]([0-5]\d)\s*(pm|am|مساءً|مساء|صباحًا|صباحا|صباح|م|ص)?",
            raw,
            re.I,
        )
        if not tm:
            continue

        hh, mm = int(tm.group(1)), int(tm.group(2))
        marker = (tm.group(3) or "").lower()
        if marker in ("pm", "مساءً", "مساء", "م") and 1 <= hh <= 11:
            hh += 12
        elif marker in ("am", "صباحًا", "صباحا", "صباح", "ص") and hh == 12:
            hh = 0

        vm = re.search(r"(?:🆚|⚔️|⚔|VS\.?|V\.?|ضد)", raw, re.I)
        if not vm:
            continue

        # Try both sides around VS; strip metadata around time/channel.
        left = raw[:vm.start()]
        right = raw[vm.end():]

        metadata = re.compile(
            r"(?:\b(?:10|[1-9])\b\s*)?"
            r"(?:الوان|ألوان|ALWAN)(?:\s+SPORTS?)?"
            r"(?:\s*\b(?:10|[1-9])\b)?"
            r"|\b(?:[01]?\d|2[0-3])[:.]([0-5]\d)\s*(?:pm|am|مساءً|مساء|صباحًا|صباحا|صباح|م|ص)?",
            re.I,
        )

        left_clean = clean_team(metadata.sub("", left))
        right_clean = clean_team(metadata.sub("", right))

        if left_clean and right_clean and len(left_clean) <= 70 and len(right_clean) <= 70:
            dt = datetime(
                post_target_day.year, post_target_day.month, post_target_day.day,
                hh, mm, tzinfo=TZ
            )
            if in_window(dt):
                candidate = {
                    "channel": channel,
                    "start": dt,
                    "title": f"{left_clean} - {right_clean}",
                }
                log(f"ALWAN PARSER S2: ALWAN {channel} | {dt:%Y-%m-%d %H:%M} | {candidate['title']}")
                events.append(candidate)

    # Strategy 3: reconstruct wrapped Telegram lines.
    # Sometimes the public preview breaks one fixture into multiple adjacent lines.
    for i in range(len(raw_lines)):
        window = " ".join(raw_lines[i:i+3])
        if not re.search(r"(?:الوان|ألوان|ALWAN)", window, re.I):
            continue
        if not re.search(r"(?:🆚|⚔️|⚔|VS\.?|V\.?|ضد)", window, re.I):
            continue

        event = parse_fixture_line(window, post_target_day)
        if event:
            log(f"ALWAN PARSER S3: ALWAN {event['channel']} | {event['start']:%Y-%m-%d %H:%M} | {event['title']}")
            events.append(event)

    # Strategy 4: metadata-driven extraction from an entire post.
    # If a post is visually a list, pair each Alwan+time occurrence with the nearest VS text.
    normalized_post = normalize_keycap_digits(" ".join(raw_lines))
    channel_time_matches = list(re.finditer(
        r"(?:(10|[1-9])\s*)?(?:الوان|ألوان|ALWAN)(?:\s+SPORTS?)?\s*(10|[1-9])?"
        r".{0,20}?"
        r"([01]?\d|2[0-3])[:.]([0-5]\d)\s*(pm|am|مساءً|مساء|صباحًا|صباحا|صباح|م|ص)?",
        normalized_post,
        re.I,
    ))

    for m in channel_time_matches:
        channel_txt = m.group(1) or m.group(2)
        if not channel_txt:
            continue
        channel = int(channel_txt)
        if channel not in VALID_CHANNELS:
            continue

        hh, mm = int(m.group(3)), int(m.group(4))
        marker = (m.group(5) or "").lower()
        if marker in ("pm", "مساءً", "مساء", "م") and 1 <= hh <= 11:
            hh += 12
        elif marker in ("am", "صباحًا", "صباحا", "صباح", "ص") and hh == 12:
            hh = 0

        # Search around this metadata for a VS pair.
        s = max(0, m.start() - 120)
        e = min(len(normalized_post), m.end() + 120)
        nearby = normalized_post[s:e]

        vm = re.search(r"(.{2,50}?)\s*(?:🆚|⚔️|⚔|VS\.?|V\.?|ضد)\s*(.{2,50}?)", nearby, re.I)
        if not vm:
            continue

        ta = clean_team(vm.group(1))
        tb = clean_team(vm.group(2))
        if not ta or not tb:
            continue

        dt = datetime(
            post_target_day.year, post_target_day.month, post_target_day.day,
            hh, mm, tzinfo=TZ
        )
        if not in_window(dt):
            continue

        candidate = {
            "channel": channel,
            "start": dt,
            "title": f"{ta} - {tb}",
        }
        log(f"ALWAN PARSER S4: ALWAN {channel} | {dt:%Y-%m-%d %H:%M} | {candidate['title']}")
        events.append(candidate)

    return dedupe(events)

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
    tv=ET.Element("tv",{"generator-info-name":"Alwan Sports Telegram EPG V2"})
    for n in range(1,11):
        cid=f"AlwanSports{n}"
        ch=ET.SubElement(tv,"channel",{"id":cid})
        ET.SubElement(ch,"display-name",{"lang":"ar"}).text=f"ألوان الرياضية {n}"
        ET.SubElement(ch,"display-name",{"lang":"en"}).text=f"Alwan Sports {n}"
    for e in dedupe(events):
        n=int(e["channel"])
        if n not in VALID_CHANNELS: continue
        cid=f"AlwanSports{n}"
        stop=e["start"]+timedelta(hours=3)
        p=ET.SubElement(tv,"programme",{
            "start":e["start"].strftime("%Y%m%d%H%M%S %z"),
            "stop":stop.strftime("%Y%m%d%H%M%S %z"),
            "channel":cid})
        ET.SubElement(p,"title",{"lang":"ar"}).text=e["title"]
        ET.SubElement(p,"category",{"lang":"en"}).text="Sports"
        ET.SubElement(p,"desc",{"lang":"ar"}).text="مباراة منقولة على قنوات ألوان الرياضية"
    ET.indent(tv,space="  ")
    ET.ElementTree(tv).write(OUT,encoding="utf-8",xml_declaration=True)


def main():
    old = read_existing()
    log(f"Existing valid Alwan programmes kept: {len(old)}")

    posts = crawl_telegram_posts()

    fresh = []
    for post in posts:
        fresh.extend(parse_post(post))

    fresh = dedupe(fresh)
    per_channel = {n: 0 for n in range(1, 11)}
    for e in fresh:
        per_channel[int(e["channel"])] += 1
    log("ALWAN PARSER SUMMARY: " + ", ".join(f"{n}:{per_channel[n]}" for n in range(1, 11)))

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
    log("No filler programmes written; real matches only")
    log(f"Real programme channels: {real_channels}")
    log(f"Placeholder-only channels: {empty_channels}")
    log(f"Written: {OUT}")


if __name__ == "__main__":
    main()
