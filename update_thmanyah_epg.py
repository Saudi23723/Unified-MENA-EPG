#!/usr/bin/env python3
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

THMANYAH_LOGO = "https://upload.wikimedia.org/wikipedia/commons/e/e9/Thmanyah_Logo.svg"

KEEP_DAYS_BACK = 1
KEEP_DAYS_FORWARD = 7
DEFAULT_CHANNELS = {1, 2, 3}
PENDING_CHANNEL_ID = "ThmanyahPending.sa"
CONFIRMED_MARKER = "THMANYAH_CONFIRMED_V2"
PENDING_MARKER = "THMANYAH_PENDING_V2"

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
    r"(?:قناة\s*)?(?:ثمانية|thmanyah)\s*[.\-:]?\s*(10|[1-9])\b",
    re.I,
)
THMANYAH_ANY_RE = re.compile(r"(?:ثمانية|thmanyah)", re.I)
MATCH_RE = re.compile(
    r"(.{2,100}?)\s*(?:🆚|⚔️|⚔|vs\.?|v\.?|ضد|[-–—])\s*(.{2,100})",
    re.I,
)

AR_MONTHS = {
    "يناير": 1, "فبراير": 2, "مارس": 3,
    "أبريل": 4, "ابريل": 4, "مايو": 5,
    "يونيو": 6, "يوليو": 7, "أغسطس": 8,
    "اغسطس": 8, "سبتمبر": 9, "أكتوبر": 10,
    "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
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
    response = requests.get(url, headers=HEADERS, timeout=35)
    response.raise_for_status()
    return response.text

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

    numeric = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b", text)
    if numeric:
        day, month, year = map(int, numeric.groups())
        try:
            return date(year, month, day)
        except ValueError:
            pass

    months_pattern = "|".join(map(re.escape, AR_MONTHS))
    arabic = re.search(
        rf"\b(\d{{1,2}})\s+({months_pattern})\s+(20\d{{2}})\b",
        text,
        re.I,
    )
    if arabic:
        day = int(arabic.group(1))
        month = AR_MONTHS[arabic.group(2)]
        year = int(arabic.group(3))
        try:
            return date(year, month, day)
        except ValueError:
            pass

    if "بعد غد" in low:
        return reference + timedelta(days=2)
    if any(x in low for x in ("غداً", "غدا", "بكرا", "بكرة")):
        return reference + timedelta(days=1)
    if "اليوم" in low:
        return reference
    return None

def make_dt(day, hour, minute):
    return datetime(
        day.year, day.month, day.day,
        int(hour), int(minute),
        tzinfo=TZ,
    )

def clean_team(value):
    value = norm(value)
    value = re.sub(r"^(?:⚽|🏆|📺|⏰|•|\||✅|🔥)+\s*", "", value)
    return value.strip(" |:-")

def fixture_from_text(text):
    match = MATCH_RE.search(norm(text))
    if not match:
        return None
    first = clean_team(match.group(1))
    second = clean_team(match.group(2))
    if not first or not second:
        return None
    if len(first) > 80 or len(second) > 80:
        return None
    return f"{first} - {second}"

def normalize_team_name(value):
    value = norm(value).casefold()
    value = re.sub(r"[^\w\u0600-\u06ff ]+", " ", value)
    value = re.sub(r"\b(?:نادي|fc|club)\b", " ", value, flags=re.I)
    return re.sub(r"\s+", " ", value).strip()

def fixture_signature(title):
    match = MATCH_RE.search(norm(title))
    if not match:
        return None
    first = normalize_team_name(match.group(1))
    second = normalize_team_name(match.group(2))
    if not first or not second:
        return None
    return frozenset((first, second))

def event_key(event):
    channel = event.get("channel")
    channel_key = int(channel) if channel is not None else 0
    return (
        channel_key,
        event["start"].strftime("%Y%m%d%H%M"),
        norm(event["title"]).casefold(),
    )

def fixture_time_key(event):
    """
    Stable key used to replace an old 'channel not announced yet' entry
    once an explicitly numbered Thmanyah channel becomes available.
    """
    signature = fixture_signature(event["title"])
    if signature:
        signature_key = tuple(sorted(signature))
    else:
        signature_key = (norm(event["title"]).casefold(),)

    return (
        event["start"].strftime("%Y%m%d%H%M"),
        signature_key,
    )

def dedupe(events):
    result = []
    seen = set()
    for event in sorted(
        events,
        key=lambda item: (
            item["start"],
            int(item["channel"]) if item.get("channel") is not None else 0,
            item["title"],
        ),
    ):
        key = event_key(event)
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return result

def discover_daily_articles(home_url, label):
    try:
        soup = BeautifulSoup(fetch(home_url), "html.parser")
    except Exception as exc:
        warn(f"{label} discovery failed: {exc}")
        return []

    urls = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        text = norm(anchor.get_text(" ", strip=True))
        href = anchor["href"]
        combined = f"{text} {href}"
        if "جدول مباريات اليوم" not in combined:
            continue
        url = urljoin(home_url, href).split("#", 1)[0]
        if url in seen:
            continue
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

    for candidate in candidates:
        parsed = parse_date(candidate, NOW.date())
        if parsed:
            return parsed
    return NOW.date()

def parse_daily_article(url):
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
    except Exception as exc:
        warn(f"Daily schedule failed {url}: {exc}")
        return []

    day = article_date(soup)
    events = []

    for row in soup.find_all("tr"):
        cells = [
            norm(cell.get_text(" ", strip=True))
            for cell in row.find_all(["td", "th"])
        ]
        cells = [cell for cell in cells if cell]
        joined = " | ".join(cells)

        if not THMANYAH_ANY_RE.search(joined):
            continue

        time_match = TIME_RE.search(joined)
        if not time_match:
            continue

        title = None
        for cell in cells:
            candidate = fixture_from_text(cell)
            if candidate:
                title = candidate
                break

        if not title:
            continue

        channel_match = THMANYAH_NUMBER_RE.search(joined)
        channel = int(channel_match.group(1)) if channel_match else None

        events.append({
            "channel": channel,
            "start": make_dt(day, time_match.group(1), time_match.group(2)),
            "title": title,
            "source": url,
        })

    if not events:
        lines = [
            norm(line)
            for line in soup.get_text("\n", strip=True).splitlines()
        ]
        lines = [line for line in lines if line]

        for index, line in enumerate(lines):
            if not THMANYAH_ANY_RE.search(line):
                continue

            block = lines[max(0, index - 4):min(len(lines), index + 4)]
            joined = " | ".join(block)
            time_match = TIME_RE.search(joined)

            title = None
            for candidate in block:
                parsed = fixture_from_text(candidate)
                if parsed:
                    title = parsed
                    break

            if not time_match or not title:
                continue

            channel_match = THMANYAH_NUMBER_RE.search(joined)
            channel = int(channel_match.group(1)) if channel_match else None

            events.append({
                "channel": channel,
                "start": make_dt(day, time_match.group(1), time_match.group(2)),
                "title": title,
                "source": url,
            })

    return events

def discover_365_articles():
    try:
        soup = BeautifulSoup(fetch(SCORES365_HOME), "html.parser")
    except Exception as exc:
        warn(f"365Scores discovery failed: {exc}")
        return []

    urls = []
    seen = set()

    for anchor in soup.find_all("a", href=True):
        url = urljoin(SCORES365_HOME, anchor["href"]).split("#", 1)[0]
        if "/ar/news/magazine/" not in url:
            continue
        if url.rstrip("/") == SCORES365_HOME.rstrip("/"):
            continue
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)

    log(f"365Scores article links discovered: {len(urls)}")
    return urls[:120]

def title_from_365(soup):
    candidates = []
    heading = soup.find("h1")
    if heading:
        candidates.append(norm(heading.get_text(" ", strip=True)))
    candidates.append(norm(soup.get_text(" ", strip=True))[:8000])

    for text in candidates:
        title = fixture_from_text(text)
        if title:
            return title
    return None

def parse_365_article(url):
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
    except Exception:
        return None

    text = norm(soup.get_text(" ", strip=True))
    channel_match = THMANYAH_NUMBER_RE.search(text)
    if not channel_match:
        return None

    day = parse_date(text, NOW.date())
    if not day:
        return None

    time_match = re.search(
        r"(?:الساعة|الموعد|التوقيت|عند|تمام)"
        r"\s*(?:الساعة\s*)?"
        r"([01]?\d|2[0-3])[:.]([0-5]\d)",
        text,
        re.I,
    )
    if not time_match:
        time_match = TIME_RE.search(text)
    if not time_match:
        return None

    title = title_from_365(soup)
    if not title:
        return None

    event = {
        "channel": int(channel_match.group(1)),
        "start": make_dt(day, time_match.group(1), time_match.group(2)),
        "title": title,
        "source": url,
    }

    return event if in_window(event["start"]) else None

def collect_numbered_365():
    events = []
    for url in discover_365_articles():
        event = parse_365_article(url)
        if event:
            events.append(event)

    events = dedupe(events)
    log(f"365Scores numbered fixtures detected: {len(events)}")
    return events

def resolve_events(daily, confirmations):
    """
    Conservative resolver:
      - If a source explicitly says Thmanyah N, keep N and mark confirmed.
      - If a separate explicit numbered confirmation matches the same fixture
        on the same date and close to the same kickoff, use it.
      - Otherwise NEVER guess a channel. Keep the fixture as unannounced.
    """
    confirmed_by_signature = {}

    for event in confirmations:
        confirmed = dict(event)
        confirmed["channel_status"] = "confirmed"
        signature = fixture_signature(confirmed["title"])
        if signature:
            confirmed_by_signature.setdefault(signature, []).append(confirmed)

    result = []

    for event in daily:
        current = dict(event)

        # Daily source itself explicitly published a channel number.
        if current.get("channel") is not None:
            current["channel_status"] = "confirmed"
            result.append(current)
            continue

        # No channel number in the daily source. Only accept a separate,
        # explicitly numbered confirmation for the same fixture/date/time.
        signature = fixture_signature(current["title"])
        candidates = confirmed_by_signature.get(signature, []) if signature else []

        candidates = [
            candidate
            for candidate in candidates
            if candidate["start"].date() == current["start"].date()
            and abs(
                (candidate["start"] - current["start"]).total_seconds()
            ) <= 2 * 60 * 60
        ]

        if len(candidates) == 1:
            confirmed = candidates[0]
            current["channel"] = confirmed["channel"]
            current["channel_status"] = "confirmed"
            current["source"] = (
                f"{current['source']} + explicit channel confirmation: "
                f"{confirmed['source']}"
            )
            result.append(current)
            log(
                "CONFIRMED THMANYAH CHANNEL | "
                f"{current['start']:%Y-%m-%d %H:%M} | "
                f"{current['title']} | THMANYAH {current['channel']}"
            )
        else:
            # Crucial behavior: preserve the fixture, but DO NOT assign 1/2/3.
            current["channel"] = None
            current["channel_status"] = "unannounced"
            result.append(current)
            log(
                "THMANYAH CHANNEL NOT ANNOUNCED | "
                f"{current['start']:%Y-%m-%d %H:%M} | {current['title']}"
            )

    # Keep explicitly numbered confirmations even when the daily schedule missed them.
    result.extend(
        dict(event, channel_status="confirmed")
        for event in confirmations
    )

    return dedupe([
        event
        for event in result
        if in_window(event["start"])
    ])

def read_existing():
    if not OUT.exists():
        return []

    try:
        root = ET.parse(OUT).getroot()
    except Exception as exc:
        warn(f"Existing Thmanyah XML unreadable: {exc}")
        return []

    events = []

    for programme in root.findall("programme"):
        channel_id = programme.get("channel") or ""

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
        if not title:
            continue

        desc_node = programme.find("desc")
        desc = norm(desc_node.text) if desc_node is not None else ""

        pending = channel_id == PENDING_CHANNEL_ID
        channel_match = re.search(r"Thmanyah(10|[1-9])", channel_id, re.I)

        if pending:
            events.append({
                "channel": None,
                "start": start,
                "title": title,
                "source": "existing XML",
                "channel_status": "unannounced",
            })
            continue

        if not channel_match:
            continue

        # CRITICAL:
        # Numbered assignments from OLD XML are not trusted because previous
        # versions may have guessed them. Only keep a numbered assignment if
        # this exact file was previously written by the new verified system.
        if CONFIRMED_MARKER not in desc:
            log(
                "DROPPING LEGACY UNVERIFIED THMANYAH CHANNEL | "
                f"{start:%Y-%m-%d %H:%M} | {title} | "
                f"OLD THMANYAH {channel_match.group(1)}"
            )
            continue

        events.append({
            "channel": int(channel_match.group(1)),
            "start": start,
            "title": title,
            "source": "existing XML verified",
            "channel_status": "confirmed",
        })

    return events

def merge_existing(existing, fresh):
    """
    Merge without losing confirmed channel assignments.
    A newly confirmed event replaces the old pending/unannounced version.
    A new unannounced scrape NEVER overwrites an existing confirmed channel.
    """
    by_fixture = {}

    # Existing first.
    for event in existing:
        by_fixture[fixture_time_key(event)] = event

    for event in fresh:
        key = fixture_time_key(event)
        old = by_fixture.get(key)

        if old is None:
            by_fixture[key] = event
            continue

        old_confirmed = old.get("channel") is not None
        new_confirmed = event.get("channel") is not None

        if new_confirmed:
            # Explicit/new confirmed channel wins and becomes stable.
            by_fixture[key] = event
        elif not old_confirmed:
            # Both are unannounced; refresh metadata.
            by_fixture[key] = event
        else:
            # Existing is confirmed and new scrape is unannounced:
            # KEEP the confirmed assignment. Never downgrade it.
            log(
                "KEEPING CONFIRMED THMANYAH CHANNEL | "
                f"{old['start']:%Y-%m-%d %H:%M} | "
                f"{old['title']} | THMANYAH {old['channel']}"
            )

    return dedupe([
        event
        for event in by_fixture.values()
        if in_window(event["start"])
    ])

def write_xml(events):
    observed_channels = {
        int(event["channel"])
        for event in events
        if event.get("channel") is not None
    }
    channels = sorted(DEFAULT_CHANNELS | observed_channels)

    tv = ET.Element(
        "tv",
        {"generator-info-name": "Thmanyah Sports Verified EPG"},
    )

    # Normal numbered Thmanyah channels.
    for number in channels:
        channel_id = f"Thmanyah{number}.sa"
        channel = ET.SubElement(tv, "channel", {"id": channel_id})

        ET.SubElement(
            channel,
            "display-name",
            {"lang": "ar"},
        ).text = f"ثمانية {number}"

        ET.SubElement(
            channel,
            "display-name",
            {"lang": "en"},
        ).text = f"Thmanyah {number}"

        ET.SubElement(
            channel,
            "icon",
            {"src": THMANYAH_LOGO},
        )

    # Dedicated non-random holding channel for fixtures where Thmanyah has
    # announced the match but has NOT announced a numbered channel yet.
    pending_channel = ET.SubElement(
        tv,
        "channel",
        {"id": PENDING_CHANNEL_ID},
    )
    ET.SubElement(
        pending_channel,
        "display-name",
        {"lang": "ar"},
    ).text = "ثمانية | Guide"
    ET.SubElement(
        pending_channel,
        "display-name",
        {"lang": "en"},
    ).text = "Thmanyah | Guide"
    ET.SubElement(
        pending_channel,
        "icon",
        {"src": THMANYAH_LOGO},
    )

    for event in events:
        channel = event.get("channel")
        if channel is None:
            channel_id = PENDING_CHANNEL_ID
        else:
            channel_id = f"Thmanyah{int(channel)}.sa"

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

        if channel is None:
            description = (
                f"{PENDING_MARKER} | "
                "القناة الناقلة على ثمانية لم تُعلن بعد. "
                f"موعد المباراة: {event['start']:%Y-%m-%d %H:%M} "
                "(بتوقيت الرياض). "
                "سيتم تثبيت رقم القناة تلقائيًا فور ظهوره في مصدر صريح."
            )
        else:
            description = (
                f"{CONFIRMED_MARKER} | "
                f"القناة المعلنة: ثمانية {int(channel)}. "
                f"موعد المباراة: {event['start']:%Y-%m-%d %H:%M} "
                "(بتوقيت الرياض). "
                "تم تثبيت رقم القناة من مصدر صريح."
            )

        ET.SubElement(
            programme,
            "desc",
            {"lang": "ar"},
        ).text = description

    ET.indent(tv, space="  ")
    ET.ElementTree(tv).write(
        OUT,
        encoding="utf-8",
        xml_declaration=True,
    )

def main():
    existing = read_existing()
    log(f"Existing Thmanyah programmes kept: {len(existing)}")

    daily_urls = (
        discover_daily_articles(GOAL_HOME, "Goal")
        + discover_daily_articles(KOOORA_HOME, "Kooora")
    )
    daily_urls = list(dict.fromkeys(daily_urls))

    daily = []
    for url in daily_urls:
        found = parse_daily_article(url)
        if found:
            log(f"Daily Thmanyah fixtures from {url}: {len(found)}")
            daily.extend(found)

    confirmations = collect_numbered_365()
    fresh = resolve_events(daily, confirmations)
    fresh = [event for event in fresh if in_window(event["start"])]

    log(f"Thmanyah newly resolved programmes: {len(fresh)}")

    for event in fresh:
        if event.get("channel") is None:
            log(
                f"  THMANYAH TBA | "
                f"{event['start']:%Y-%m-%d %H:%M} | {event['title']}"
            )
        else:
            log(
                f"  THMANYAH {event['channel']} | "
                f"{event['start']:%Y-%m-%d %H:%M} | {event['title']}"
            )

    merged = merge_existing(existing, fresh)
    log(f"Thmanyah total programmes after merge: {len(merged)}")

    if not fresh and existing:
        warn("No fresh Thmanyah programmes; existing XML left untouched")
        return

    write_xml(merged)
    log(f"Written: {OUT}")

if __name__ == "__main__":
    main()
