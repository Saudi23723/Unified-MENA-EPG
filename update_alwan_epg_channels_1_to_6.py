#!/usr/bin/env python3
"""
Alwan Sports XMLTV updater — channels 1 through 6 only.

Source:
  https://t.me/s/AlwanSports

Rules:
  • Alwan Sports has 6 live channels: 1..6
  • Channel 7 is NOT included (replay channel)
  • Extract only real fixtures that have:
      - two teams
      - a valid time
      - an explicit Alwan channel number 1..6
  • Ignore headings/placeholders such as:
      - "جدول مباريات الغد"
      - "Please open Telegram to view this post"
  • Preserve valid existing future programmes
  • Drop old invalid/placeholder programmes
  • Never touch Thmanyah files
"""

import html
import re
import sys
from datetime import datetime, timedelta, date
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET


TZ = ZoneInfo("Asia/Riyadh")
NOW = datetime.now(TZ)

OUT = Path("alwan_sports_epg.xml")
TELEGRAM_URL = "https://t.me/s/AlwanSports"

KEEP_DAYS_BACK = 1
KEEP_DAYS_FORWARD = 7
VALID_CHANNELS = {1, 2, 3, 4, 5, 6}

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
    r"(?:ألوان|الوان|ALWAN)(?:\s+SPORTS?)?\s*[.\-:]?\s*([1-6])\b",
    re.I,
)

MATCH_LINE_RE = re.compile(
    r"(.{2,100}?)\s*(?:🆚|⚔️|⚔|VS\.?|V\.?|ضد|[-–—])\s*(.{2,100})",
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

BAD_TITLE_PARTS = (
    "please open telegram",
    "view this post",
    "جدول مباريات",
    "جدول اليوم",
    "جدول الغد",
    "جدول مباريات الغد",
)


def log(message):
    print(message, flush=True)


def warn(message):
    print(f"WARN {message}", file=sys.stderr, flush=True)


def norm(value):
    value = html.unescape(value or "")
    value = value.replace("\u200f", " ").replace("\u200e", " ")
    value = value.replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", value).strip()


def fetch(url):
    response = requests.get(url, headers=HEADERS, timeout=35)
    response.raise_for_status()
    return response.text


def in_window(dt):
    return (
        NOW - timedelta(days=KEEP_DAYS_BACK)
        <= dt
        <= NOW + timedelta(days=KEEP_DAYS_FORWARD)
    )


def valid_title(title):
    low = norm(title).lower()
    if not low:
        return False
    return not any(part in low for part in BAD_TITLE_PARTS)


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

    months_pattern = "|".join(map(re.escape, AR_MONTHS))
    m = re.search(
        rf"\b(\d{{1,2}})\s+({months_pattern})\s+(20\d{{2}})\b",
        text,
        re.I,
    )
    if m:
        day = int(m.group(1))
        month = AR_MONTHS[m.group(2)]
        year = int(m.group(3))
        try:
            return date(year, month, day)
        except ValueError:
            pass

    if "بعد غد" in low:
        return reference + timedelta(days=2)

    if any(word in low for word in ("غداً", "غدا", "بكرا", "بكرة")):
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

    return value.strip(" |:-")


def fixture_from_line(line):
    line = norm(line)
    low = line.lower()

    if any(x in low for x in BAD_TITLE_PARTS):
        return None

    match = MATCH_LINE_RE.search(line)
    if not match:
        return None

    team_a = clean_team(match.group(1))
    team_b = clean_team(match.group(2))

    if not team_a or not team_b:
        return None

    if len(team_a) > 70 or len(team_b) > 70:
        return None

    return f"{team_a} - {team_b}"


def post_text(post):
    candidates = []

    for selector in (
        ".tgme_widget_message_text",
        ".tgme_widget_message_caption",
    ):
        node = post.select_one(selector)
        if node:
            text = node.get_text("\n", strip=True)
            if text:
                candidates.append(text)

    if not candidates:
        bubble = post.select_one(".tgme_widget_message_bubble")
        if bubble:
            candidates.append(bubble.get_text("\n", strip=True))

    return html.unescape("\n".join(candidates)).strip()


def split_into_fixture_blocks(text):
    lines = [norm(x) for x in text.splitlines() if norm(x)]
    blocks = []

    for index, line in enumerate(lines):
        if fixture_from_line(line):
            start = max(0, index - 3)
            end = min(len(lines), index + 6)
            blocks.append("\n".join(lines[start:end]))

    for index, line in enumerate(lines):
        if line.upper() not in {"VS", "V", "🆚", "⚔", "⚔️", "ضد"}:
            continue
        if index == 0 or index + 1 >= len(lines):
            continue

        team_a = clean_team(lines[index - 1])
        team_b = clean_team(lines[index + 1])

        if not team_a or not team_b:
            continue

        synthetic = (
            f"{team_a} VS {team_b}\n"
            + "\n".join(
                lines[
                    max(0, index - 3):
                    min(len(lines), index + 7)
                ]
            )
        )
        blocks.append(synthetic)

    return list(dict.fromkeys(blocks))


def fixture_from_block(block):
    for line in block.splitlines():
        fixture = fixture_from_line(line)
        if fixture:
            return fixture

    lines = [norm(x) for x in block.splitlines() if norm(x)]

    for index, line in enumerate(lines):
        if line.upper() in {"VS", "V", "🆚", "⚔", "⚔️", "ضد"}:
            if index > 0 and index + 1 < len(lines):
                team_a = clean_team(lines[index - 1])
                team_b = clean_team(lines[index + 1])
                if team_a and team_b:
                    return f"{team_a} - {team_b}"

    return None


def channel_from_block(block):
    match = ALWAN_RE.search(block)
    if not match:
        return None

    channel = int(match.group(1))
    return channel if channel in VALID_CHANNELS else None


def time_from_block(block):
    match = TIME_RE.search(block)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))
    low = block.lower()

    if ("pm" in low or "مساء" in low) and 1 <= hour <= 11:
        hour += 12

    if ("am" in low or "صباح" in low) and hour == 12:
        hour = 0

    return hour, minute


def parse_post(post):
    text = post_text(post)
    if not text:
        return []

    low = text.lower()

    if "please open telegram" in low:
        return []

    post_day = telegram_post_date(post)
    explicit_day = parse_explicit_date(text, post_day)
    default_day = explicit_day or post_day

    events = []

    for block in split_into_fixture_blocks(text):
        fixture = fixture_from_block(block)
        channel = channel_from_block(block)
        time_value = time_from_block(block)

        if not fixture or channel is None or time_value is None:
            continue

        if not valid_title(fixture):
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
        key=lambda x: (
            x["start"],
            int(x["channel"]),
            x["title"],
        ),
    ):
        key = event_key(event)
        if key in seen:
            continue
        seen.add(key)
        output.append(event)

    return output


def channel_number_from_id(channel_id):
    if channel_id == "AlwanSports":
        return 1

    m = re.fullmatch(r"AlwanSports([1-6])", channel_id or "", re.I)
    if m:
        return int(m.group(1))

    return None


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
        if channel not in VALID_CHANNELS:
            continue

        raw_start = programme.get("start") or ""

        try:
            start = datetime.strptime(
                raw_start[:14],
                "%Y%m%d%H%M%S",
            ).replace(tzinfo=TZ)
        except Exception:
            continue

        if not in_window(start):
            continue

        title_node = programme.find("title")
        title = norm(title_node.text) if title_node is not None else ""

        if not valid_title(title):
            continue

        events.append(
            {
                "channel": channel,
                "start": start,
                "title": title,
                "source": "existing XML",
            }
        )

    return events


def merge_existing(existing, fresh):
    combined = {}

    for event in existing:
        combined[event_key(event)] = event

    for event in fresh:
        combined[event_key(event)] = event

    return dedupe(
        [
            event
            for event in combined.values()
            if in_window(event["start"])
            and int(event["channel"]) in VALID_CHANNELS
            and valid_title(event["title"])
        ]
    )


def write_xml(events):
    tv = ET.Element(
        "tv",
        {"generator-info-name": "Alwan Sports Telegram EPG"},
    )

    # Always publish exactly six channels: 1..6.
    for number in range(1, 7):
        channel_id = f"AlwanSports{number}"

        channel = ET.SubElement(
            tv,
            "channel",
            {"id": channel_id},
        )

        ET.SubElement(
            channel,
            "display-name",
            {"lang": "ar"},
        ).text = f"ألوان الرياضية {number}"

        ET.SubElement(
            channel,
            "display-name",
            {"lang": "en"},
        ).text = f"Alwan Sports {number}"

    for event in events:
        number = int(event["channel"])

        if number not in VALID_CHANNELS:
            continue

        channel_id = f"AlwanSports{number}"
        stop = event["start"] + timedelta(hours=3)

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
        ).text = f"المصدر: {event['source']}"

    ET.indent(tv, space="  ")
    ET.ElementTree(tv).write(
        OUT,
        encoding="utf-8",
        xml_declaration=True,
    )


def main():
    existing = read_existing()

    log(f"Existing valid Alwan programmes kept: {len(existing)}")

    try:
        soup = BeautifulSoup(fetch(TELEGRAM_URL), "html.parser")
    except Exception as exc:
        warn(f"Alwan Telegram fetch failed: {exc}")
        return

    posts = soup.select(".tgme_widget_message")
    log(f"Alwan Telegram posts visible: {len(posts)}")

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
            f"{event['start']:%Y-%m-%d %H:%M} | {event['title']}"
        )

    merged = merge_existing(existing, fresh)

    log(f"Alwan total programmes after merge: {len(merged)}")

    # Always rewrite so channel definitions become exactly 1..6
    # and old invalid entries are removed.
    write_xml(merged)
    log(f"Written: {OUT}")


if __name__ == "__main__":
    main()
