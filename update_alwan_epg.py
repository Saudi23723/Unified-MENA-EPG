#!/usr/bin/env python3
"""
Alwan Sports XMLTV updater.

Source:
  Public Telegram channel: https://t.me/s/AlwanSports

Behavior:
  • Reads only Alwan Sports Telegram.
  • Extracts date + teams + time + Alwan channel number.
  • Supports posts containing several fixtures.
  • Ignores Telegram placeholders and headings such as "جدول مباريات الغد".
  • Keeps existing future EPG entries if Telegram temporarily returns no useful data.
  • Does NOT touch any Thmanyah files or code.

Dependencies:
  requests
  beautifulsoup4
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "ar,en;q=0.8",
}

TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)")

# Examples supported:
# ألوان 1 / الوان 2 / ALWAN 3 / Alwan Sports 4
ALWAN_RE = re.compile(
    r"(?:ألوان|الوان|ALWAN)(?:\s+SPORTS?)?\s*[.\-:]?\s*(10|[1-9])\b",
    re.I,
)

# Examples supported:
# Team A VS Team B
# Team A 🆚 Team B
# Team A ضد Team B
# Team A - Team B
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
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=35,
    )
    response.raise_for_status()
    return response.text


def in_window(dt):
    return (
        NOW - timedelta(days=KEEP_DAYS_BACK)
        <= dt
        <= NOW + timedelta(days=KEEP_DAYS_FORWARD)
    )


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

    m = re.search(
        r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b",
        text,
    )

    if m:
        day, month, year = map(int, m.groups())

        try:
            return date(year, month, day)
        except ValueError:
            pass

    months_pattern = "|".join(
        map(re.escape, AR_MONTHS)
    )

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

    # Important: check "بعد غد" before "غد".
    if "بعد غد" in low:
        return reference + timedelta(days=2)

    if any(
        word in low
        for word in ("غداً", "غدا", "بكرا", "بكرة")
    ):
        return reference + timedelta(days=1)

    if "اليوم" in low:
        return reference

    return None


def clean_team(value):
    value = norm(value)

    # Remove common emoji/labels around team names.
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

    # Explicitly reject headings/placeholders.
    bad = (
        "please open telegram",
        "view this post",
        "جدول مباريات",
        "جدول اليوم",
        "جدول الغد",
    )

    low = line.lower()

    if any(x in low for x in bad):
        return None

    match = MATCH_LINE_RE.search(line)

    if not match:
        return None

    team_a = clean_team(match.group(1))
    team_b = clean_team(match.group(2))

    if not team_a or not team_b:
        return None

    # Prevent accidental very-long prose captures.
    if len(team_a) > 70 or len(team_b) > 70:
        return None

    return f"{team_a} - {team_b}"


def post_text(post):
    """
    Telegram's public page can move text between selectors.
    Prefer the text/caption nodes; only use the whole bubble as fallback.
    """
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
        bubble = post.select_one(
            ".tgme_widget_message_bubble"
        )

        if bubble:
            candidates.append(
                bubble.get_text("\n", strip=True)
            )

    return html.unescape(
        "\n".join(candidates)
    ).strip()


def split_into_fixture_blocks(text):
    """
    Build a local block around every line that looks like a fixture.
    This works well for posts formatted as:
        TEAM A
        VS
        TEAM B
        10:00 PM
        الوان 2
    as well as one-line "TEAM A VS TEAM B".
    """
    lines = [
        norm(x)
        for x in text.splitlines()
        if norm(x)
    ]

    blocks = []

    # First: normal one-line fixture markers.
    for index, line in enumerate(lines):
        if fixture_from_line(line):
            start = max(0, index - 3)
            end = min(len(lines), index + 6)
            blocks.append(
                "\n".join(lines[start:end])
            )

    # Second: Telegram designs sometimes place VS on its own line.
    for index, line in enumerate(lines):
        if line.upper() not in {
            "VS",
            "V",
            "🆚",
            "⚔",
            "⚔️",
            "ضد",
        }:
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

    # If nothing matched, return no blocks rather than inventing a programme.
    return list(dict.fromkeys(blocks))


def fixture_from_block(block):
    # One-line fixture first.
    for line in block.splitlines():
        fixture = fixture_from_line(line)

        if fixture:
            return fixture

    # Then support a synthetic/local "VS" layout.
    lines = [
        norm(x)
        for x in block.splitlines()
        if norm(x)
    ]

    for index, line in enumerate(lines):
        if line.upper() in {
            "VS",
            "V",
            "🆚",
            "⚔",
            "⚔️",
            "ضد",
        }:
            if index > 0 and index + 1 < len(lines):
                team_a = clean_team(
                    lines[index - 1]
                )
                team_b = clean_team(
                    lines[index + 1]
                )

                if team_a and team_b:
                    return (
                        f"{team_a} - {team_b}"
                    )

    return None


def channel_from_block(block):
    match = ALWAN_RE.search(block)

    if match:
        return int(match.group(1))

    return None


def time_from_block(block):
    match = TIME_RE.search(block)

    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))

    # If Telegram text explicitly says PM/مساء and hour is 1-11, convert.
    low = block.lower()

    if (
        ("pm" in low or "مساء" in low)
        and 1 <= hour <= 11
    ):
        hour += 12

    # 12 PM should remain 12.
    if (
        ("am" in low or "صباح" in low)
        and hour == 12
    ):
        hour = 0

    return hour, minute


def parse_post(post):
    text = post_text(post)

    if not text:
        return []

    # Hard reject Telegram placeholders.
    if (
        "Please open Telegram to view this post"
        in text
    ):
        return []

    post_day = telegram_post_date(post)

    explicit_day = parse_explicit_date(
        text,
        post_day,
    )

    default_day = explicit_day or post_day

    events = []

    for block in split_into_fixture_blocks(text):
        fixture = fixture_from_block(block)
        channel = channel_from_block(block)
        time_value = time_from_block(block)

        # We require ALL three pieces. No guessing.
        if (
            not fixture
            or channel is None
            or time_value is None
        ):
            continue

        day = (
            parse_explicit_date(
                block,
                default_day,
            )
            or default_day
        )

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
        event["start"].strftime(
            "%Y%m%d%H%M"
        ),
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


def read_existing():
    if not OUT.exists():
        return []

    try:
        root = ET.parse(OUT).getroot()

    except Exception as exc:
        warn(
            f"Existing Alwan XML unreadable: "
            f"{exc}"
        )
        return []

    events = []

    for programme in root.findall(
        "programme"
    ):
        channel_id = (
            programme.get("channel")
            or ""
        )

        channel_match = re.search(
            r"AlwanSports(?:([1-9]|10))?",
            channel_id,
            re.I,
        )

        if not channel_match:
            continue

        channel = (
            int(channel_match.group(1))
            if channel_match.group(1)
            else 1
        )

        raw_start = (
            programme.get("start")
            or ""
        )

        try:
            start = datetime.strptime(
                raw_start[:14],
                "%Y%m%d%H%M%S",
            ).replace(tzinfo=TZ)

        except Exception:
            continue

        if not in_window(start):
            continue

        title_node = programme.find(
            "title"
        )

        if (
            title_node is None
            or not norm(title_node.text)
        ):
            continue

        title = norm(title_node.text)

        # IMPORTANT:
        # Never import generated filler back as if it were a real match.
        # Otherwise every hourly run keeps recycling filler entries and
        # eventually pollutes/duplicates the EPG.
        filler_titles = {
            "لا توجد مباريات مجدولة",
            "لا توجد مباراة معلنة",
            "No information",
            "No scheduled matches",
        }

        # Do not recycle any generated filler as a real match.
        # Keep filler in the OUTPUT, but exclude it when reading old XML.
        if (
            title in filler_titles
            or "لا توجد مباراة حالياً" in title
            or "لا توجد مباريات مجدولة" in title
            or "No match currently" in title
        ):
            continue

        # Keep only genuine sports programmes from the previous XML.
        category_node = programme.find("category")
        if category_node is not None:
            category = norm(category_node.text).casefold()
            if category and category != "sports":
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
        ]
    )



def write_xml(events):
    """
    TiviMate-oriented XMLTV with REAL separate EPG entries for common
    playlist naming variants.

    For each Alwan number 1-10 we generate these separate EPG channels:
      - Alwan Sport N
      - Alwan Sports N
      - Alwan Sport N HD
      - Alwan Sport N SD
      - Alwan Sport N 4K
      - Alwan Sport N RAW
      - Alwan Sports N HD
      - Alwan Sports N SD
      - Alwan Sports N 4K
      - Alwan Sports N RAW

    All variants for the same number receive the SAME real matches and filler.
    Telegram parsing is unchanged.
    """

    channel_numbers = list(range(1, 11))

    variants = [
        ("sport",        "Alwan Sport {n}"),
        ("sports",       "Alwan Sports {n}"),
        ("sport_hd",     "Alwan Sport {n} HD"),
        ("sport_sd",     "Alwan Sport {n} SD"),
        ("sport_4k",     "Alwan Sport {n} 4K"),
        ("sport_raw",    "Alwan Sport {n} RAW"),
        ("sports_hd",    "Alwan Sports {n} HD"),
        ("sports_sd",    "Alwan Sports {n} SD"),
        ("sports_4k",    "Alwan Sports {n} 4K"),
        ("sports_raw",   "Alwan Sports {n} RAW"),
    ]

    tv = ET.Element(
        "tv",
        {"generator-info-name": "Alwan Sports Telegram EPG"},
    )

    # Build 100 real XMLTV channel entries: 10 numbers x 10 naming variants.
    channel_ids_by_number = {n: [] for n in channel_numbers}

    for number in channel_numbers:
        for key, label_template in variants:
            channel_id = f"Alwan{number}_{key}"
            display_name = label_template.format(n=number)

            channel = ET.SubElement(tv, "channel", {"id": channel_id})
            ET.SubElement(
                channel,
                "display-name",
                {"lang": "en"},
            ).text = display_name

            channel_ids_by_number[number].append(channel_id)

    real_by_number = {number: [] for number in channel_numbers}

    # Write every real match to every naming variant of the same channel number.
    for event in events:
        number = int(event["channel"])
        if number not in real_by_number:
            continue

        real_by_number[number].append(event)

        stop = event["start"] + timedelta(hours=3)

        for channel_id in channel_ids_by_number[number]:
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
            ).text = (
                f"القناة: Alwan Sport {number}\n"
                f"المصدر: {event['source']}"
            )

    window_start = NOW.astimezone(TZ).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    window_end = window_start + timedelta(days=KEEP_DAYS_FORWARD + 1)

    def add_filler(number, channel_id, gap_start, gap_stop):
        cursor = gap_start

        while cursor < gap_stop:
            stop = min(cursor + timedelta(hours=1), gap_stop)

            programme = ET.SubElement(
                tv,
                "programme",
                {
                    "start": cursor.strftime("%Y%m%d%H%M%S %z"),
                    "stop": stop.strftime("%Y%m%d%H%M%S %z"),
                    "channel": channel_id,
                },
            )

            ET.SubElement(
                programme,
                "title",
                {"lang": "ar"},
            ).text = f"Alwan Sport {number} — لا توجد مباريات مجدولة"

            ET.SubElement(
                programme,
                "category",
                {"lang": "en"},
            ).text = "Sports"

            ET.SubElement(
                programme,
                "desc",
                {"lang": "ar"},
            ).text = "لا توجد مباراة معلنة على هذه القناة في هذا الوقت."

            cursor = stop

    # Build non-overlapping filler gaps once per channel number,
    # then duplicate those gaps to every naming variant.
    for number in channel_numbers:
        intervals = []

        for event in sorted(
            real_by_number.get(number, []),
            key=lambda item: item["start"],
        ):
            s = max(event["start"], window_start)
            e = min(event["start"] + timedelta(hours=3), window_end)

            if e > s:
                intervals.append((s, e))

        merged = []

        for s, e in intervals:
            if not merged or s > merged[-1][1]:
                merged.append([s, e])
            else:
                merged[-1][1] = max(merged[-1][1], e)

        gaps = []
        cursor = window_start

        for s, e in merged:
            if s > cursor:
                gaps.append((cursor, s))
            cursor = max(cursor, e)

        if cursor < window_end:
            gaps.append((cursor, window_end))

        for channel_id in channel_ids_by_number[number]:
            for gap_start, gap_stop in gaps:
                add_filler(number, channel_id, gap_start, gap_stop)

    ET.indent(tv, space="  ")

    ET.ElementTree(tv).write(
        OUT,
        encoding="utf-8",
        xml_declaration=True,
    )

    # Hard validation of the actual XML output.
    root = ET.parse(OUT).getroot()

    expected_channel_count = len(channel_numbers) * len(variants)
    actual_channels = root.findall("channel")

    if len(actual_channels) != expected_channel_count:
        raise RuntimeError(
            f"Alwan XML validation failed; expected "
            f"{expected_channel_count} channel entries, got {len(actual_channels)}"
        )

    now_check = NOW.astimezone(TZ)
    current_coverage = {
        channel.get("id"): False
        for channel in actual_channels
    }

    programme_counts = {
        channel.get("id"): 0
        for channel in actual_channels
    }

    for programme in root.findall("programme"):
        channel_id = programme.get("channel") or ""

        if channel_id not in current_coverage:
            continue

        programme_counts[channel_id] += 1

        try:
            start_dt = datetime.strptime(
                (programme.get("start") or "")[:14],
                "%Y%m%d%H%M%S",
            ).replace(tzinfo=TZ)

            stop_dt = datetime.strptime(
                (programme.get("stop") or "")[:14],
                "%Y%m%d%H%M%S",
            ).replace(tzinfo=TZ)

        except Exception:
            continue

        if start_dt <= now_check < stop_dt:
            current_coverage[channel_id] = True

    # Compact per-number log.
    for number in channel_numbers:
        ids = channel_ids_by_number[number]

        log(
            f"ALWAN {number} VARIANTS | "
            f"entries={len(ids)} | "
            f"min_programmes={min(programme_counts[i] for i in ids)} | "
            f"current={'YES' if all(current_coverage[i] for i in ids) else 'NO'}"
        )

    missing = [
        channel_id
        for channel_id, ok in current_coverage.items()
        if not ok
    ]

    if missing:
        raise RuntimeError(
            "Alwan XML validation failed; missing current coverage for: "
            + ", ".join(missing)
        )

def main():
    existing = read_existing()
    log(f"Existing REAL Alwan programmes kept: {len(existing)}")

    log(
        f"Existing Alwan programmes kept: "
        f"{len(existing)}"
    )

    try:
        soup = BeautifulSoup(
            fetch(TELEGRAM_URL),
            "html.parser",
        )

    except Exception as exc:
        warn(
            f"Alwan Telegram fetch failed: "
            f"{exc}"
        )
        return

    posts = soup.select(
        ".tgme_widget_message"
    )

    log(
        f"Alwan Telegram posts visible: "
        f"{len(posts)}"
    )

    fresh = []
    debug_count = 0

    for post in posts:
        parsed = parse_post(post)

        if parsed:
            fresh.extend(parsed)

        elif debug_count < 4:
            text = post_text(post)

            if text:
                excerpt = norm(
                    text.replace(
                        "\n",
                        " | ",
                    )
                )[:500]

                log(
                    "ALWAN DEBUG UNPARSED: "
                    + excerpt
                )

                debug_count += 1

    fresh = dedupe(fresh)

    log(
        f"Alwan newly detected programmes: "
        f"{len(fresh)}"
    )

    for event in fresh:
        log(
            f"  ALWAN {event['channel']} | "
            f"{event['start']:%Y-%m-%d %H:%M} | "
            f"{event['title']}"
        )

    merged = merge_existing(
        existing,
        fresh,
    )

    log(
        f"Alwan total programmes after merge: "
        f"{len(merged)}"
    )

    # Safety: if Telegram temporarily yields zero useful fixtures,
    # do not erase an already-useful XML.
    if (
        not fresh
        and existing
    ):
        warn(
            "No new usable Alwan fixtures; "
            "existing XML left untouched"
        )
        return

    write_xml(merged)

    log(
        f"Written: {OUT}"
    )


if __name__ == "__main__":
    main()
