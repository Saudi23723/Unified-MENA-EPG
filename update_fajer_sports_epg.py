#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import re
import sys
import json
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from html import unescape
from urllib.parse import urljoin, urlencode
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import pytesseract

OUTPUT = "fajer_sports_epg.xml"

UTC = timezone.utc
PALESTINE = ZoneInfo("Asia/Hebron")

HTTP_TIMEOUT = 30
DAYS_BACK = 1
DAYS_FORWARD = 7

TELEGRAM_URLS = [
    "https://t.me/s/fajersport",
    "https://telegram.me/s/fajersport",
]

TELEGRAM_MAX_PAGES = 6  # Increased from 4
TELEGRAM_RECENT_DAYS = 5  # Increased from 3

LIVEFOOTBALLTV_URL = "https://www.livefootballtv.info/"
CAIRO = ZoneInfo("Africa/Cairo")

CHANNELS = {
    n: (
        f"FajerSport{n}",
        f"Fajer Sport {n} | فجر سبورت {n}",
    )
    for n in range(1, 6)
}

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 Chrome/126 Safari/537.36"
)

session = requests.Session()
session.headers.update(
    {
        "User-Agent": UA,
        "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    }
)


def log(x):
    print(x, flush=True)


def warn(x):
    print("WARN", x, flush=True)


def norm(s):
    return re.sub(r"\s+", " ", unescape(s or "")).strip()


def now_utc():
    return datetime.now(UTC)


def in_window(dt):
    n = now_utc()

    start = (
        n - timedelta(days=DAYS_BACK)
    ).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    end = (
        n + timedelta(days=DAYS_FORWARD + 1)
    ).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    return start <= dt.astimezone(UTC) < end


def fetch(url, binary=False):
    r = session.get(
        url,
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()

    if binary:
        return r.content

    return r.text


def xmltv_time(dt):
    return dt.astimezone(UTC).strftime(
        "%Y%m%d%H%M%S +0000"
    )


# ============================================================
# OCR - IMPROVED REGEX PATTERNS
# ============================================================

DATE_RE = re.compile(
    r"(?P<y>20\d{2})[-/.]"
    r"(?P<m>\d{1,2})[-/.]"
    r"(?P<d>\d{1,2})"
)

# More flexible time patterns - handles Arabic numerals and various separators
TIME_RE = re.compile(
    r"(?P<h>\d{1,2})"
    r"\s*[:٫.٪]\s*"  # Added more Arabic separators
    r"(?P<m>\d{2})"
    r"(?:\s*(?P<ap>pm|am|p\.?m\.?|a\.?m\.?))?",
    re.I,
)

# Improved channel detection
CHAN_RE = re.compile(
    r"(?:قناة|القناة|channel)\s*([1-5])"
    r"|"
    r"\b([1-5])\s*(?:قناة|channel)\b",
    re.I,
)

# Match pair patterns - handles various separators
PAIR_RE = re.compile(
    r"([\w\u0600-\u06ff .'-]{2,40})"
    r"\s*(?:x|X|×|vs|VS|-|–|—)\s*"
    r"([\w\u0600-\u06ff .'-]{2,40})"
)

# Improved noise pattern - less aggressive filtering
NOISE = re.compile(
    r"^(?:"
    r"تشاهدون|"
    r"الأربعاء|الخميس|الجمعة|"
    r"السبت|الأحد|الاثنين|الثلاثاء|"
    r"كأس|"
    r"الأسبوع|"
    r"للمشاهدة"
    r")$",
    re.I,
)

# Common team names (to validate extracted pairs)
COMMON_TEAMS = {
    # Saudi
    "النصر", "الهلال", "الاتحاد", "الاهلي", "الشباب", "الفيحاء",
    "الريان", "الرياض", "التعاون", "الفتح", "الطائي",
    # Arab clubs
    "الأهلي", "الزمالك", "بيراميدز", "القاهرة", "الإسماعيلي",
    "برسا", "الترجي", "المقاولون", "بيراميدز", "الوحدات",
    # International
    "ريال مدريد", "برشلونة", "باريس", "ليفربول", "مانشستر",
    "ارسنال", "تشيلسي", "يوفنتوس", "ميلان", "بايرن",
}


def prep(im, scale=3):
    """Prepare image for OCR with optimal settings."""
    im = im.convert("L")
    im = ImageOps.autocontrast(im)
    im = ImageEnhance.Contrast(im).enhance(1.6)
    im = ImageEnhance.Sharpness(im).enhance(1.5)
    im = im.resize(
        (
            im.width * scale,
            im.height * scale,
        )
    )
    return im.filter(ImageFilter.SHARPEN)


def ocr(im, psm=6, lang="ara+eng"):
    """Extract text from image using OCR."""
    text = pytesseract.image_to_string(
        prep(im),
        lang=lang,
        config=f"--psm {psm}",
    )
    return norm(text)


def poster_date(im, fallback):
    """
    Read date from poster header.
    If OCR cannot read a valid date, fallback to Telegram post date.
    """
    w, h = im.size

    header = im.crop(
        (
            int(0.20 * w),
            0,
            int(0.80 * w),
            int(0.30 * h),
        )
    )

    for psm in (6, 11):
        text = ocr(header, psm)
        m = DATE_RE.search(text)

        if not m:
            continue

        try:
            return date(
                int(m["y"]),
                int(m["m"]),
                int(m["d"]),
            )
        except ValueError:
            pass

    return fallback.astimezone(PALESTINE).date()


def card_boxes(im):
    """
    Fajer daily poster layout: 2 columns x 2-3 rows.
    Adjusted for variable poster sizes.
    """
    w, h = im.size

    boxes = [
        ("TL", (0, int(0.25 * h), int(0.50 * w), int(0.52 * h))),
        ("TR", (int(0.50 * w), int(0.25 * h), w, int(0.52 * h))),
        ("BL", (0, int(0.52 * h), int(0.50 * w), int(0.80 * h))),
        ("BR", (int(0.50 * w), int(0.52 * h), w, int(0.80 * h))),
    ]
    
    # Add bottom row if poster is tall enough
    if h / w > 1.3:
        boxes.extend([
            ("BTL", (0, int(0.80 * h), int(0.50 * w), h)),
            ("BTR", (int(0.50 * w), int(0.80 * h), w, h)),
        ])
    
    return boxes


def _ocr_norm(text):
    """Normalize OCR text - convert Arabic numerals to ASCII."""
    return (
        norm(text)
        .translate(
            str.maketrans(
                "٠١٢٣٤٥٦٧٨٩",
                "0123456789",
            )
        )
        .replace("\u200f", "")
        .replace("\u200e", "")
    )


def _extract_channel_time(text):
    """Extract channel and time from OCR text with better tolerance."""
    text = _ocr_norm(text)

    channel_match = CHAN_RE.search(text)
    time_match = TIME_RE.search(text)

    if not channel_match or not time_match:
        return None

    channel = int(
        channel_match.group(1)
        or channel_match.group(2)
    )

    hour = int(time_match["h"])
    minute = int(time_match["m"])

    ampm = (
        time_match["ap"]
        or ""
    ).lower().replace(".", "")

    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None

    return (channel, (hour, minute), bool(ampm))


def channel_and_time(card):
    """
    Extract channel and time using multiple OCR passes with voting.
    Prioritizes readings with explicit AM/PM.
    """
    w, h = card.size

    regions = [
        card,
        card.crop((int(0.05 * w), int(0.20 * h), int(0.95 * w), int(0.80 * h))),
    ]

    texts = []
    votes = {}

    for region in regions:
        for psm in (6, 11):
            text = ocr(region, psm)
            texts.append(text)

            hit = _extract_channel_time(text)
            if not hit:
                continue

            channel, clock, explicit_ampm = hit
            key = (channel, clock)
            
            weight = 3 if explicit_ampm else 1
            votes[key] = votes.get(key, 0) + weight

    if not votes:
        return (None, None, " | ".join(texts))

    best = max(votes.items(), key=lambda x: x[1])[0]
    return (best[0], best[1], " | ".join(texts))


def extract_teams(text):
    """
    Extract team pair from text.
    More tolerant of spacing and formatting issues.
    """
    text = _ocr_norm(text)
    
    # Remove noise words
    text = NOISE.sub("", text)
    
    matches = PAIR_RE.findall(text)
    
    valid_pairs = []
    for team1, team2 in matches:
        t1 = norm(team1)
        t2 = norm(team2)
        
        # Skip if too short or looks like garbage
        if len(t1) < 2 or len(t2) < 2:
            continue
        
        # Filter obvious non-team text
        if re.search(r"\d{2}:\d{2}", t1) or re.search(r"\d{2}:\d{2}", t2):
            continue
            
        valid_pairs.append((t1, t2))
    
    return valid_pairs


def parse_poster(im, post_time, image_url):
    """
    Parse poster image to extract match events.
    """
    events = []
    
    try:
        poster_date_val = poster_date(im, post_time)
    except Exception as exc:
        warn(f"poster_date failed: {exc}")
        poster_date_val = post_time.astimezone(PALESTINE).date()

    boxes = card_boxes(im)
    
    for box_name, (x1, y1, x2, y2) in boxes:
        if x2 <= x1 or y2 <= y1:
            continue
            
        card = im.crop((x1, y1, x2, y2))
        
        if card.width < 100 or card.height < 80:
            continue

        channel, clock, ocr_raw = channel_and_time(card)
        
        if channel is None or clock is None:
            warn(f"No channel/time in {box_name}: {ocr_raw[:100]}")
            continue

        # Extract teams from card
        teams_text = ocr(card)
        teams = extract_teams(teams_text)

        if not teams:
            warn(f"No teams extracted from {box_name}")
            continue

        team1, team2 = teams[0]

        hour, minute = clock
        
        try:
            start = datetime(
                poster_date_val.year,
                poster_date_val.month,
                poster_date_val.day,
                hour,
                minute,
                tzinfo=PALESTINE,
            )
        except ValueError as exc:
            warn(f"Invalid datetime: {exc}")
            continue

        if not in_window(start):
            continue

        event = {
            "channel_id": f"FajerSport{channel}",
            "channel_num": channel,
            "channel_name": CHANNELS[channel][1],
            "start": start,
            "title": f"{team1} - {team2}",
            "source_name": "FajerSportOfficialTelegramPoster",
            "ocr_raw": ocr_raw,
            "teams": teams,
        }
        
        events.append(event)
        log(f"✓ Poster: {channel} @ {hour:02d}:{minute:02d} | {team1} - {team2}")

    return events


# ============================================================
# TELEGRAM TEXT PARSING - IMPROVED
# ============================================================

def parse_telegram_text(text, post_time):
    """
    Parse match info from telegram text posts.
    Looks for patterns: "الفريق الساعة القناة"
    """
    events = []
    text = norm(text)
    
    # Split into lines for processing
    lines = text.split("\n")
    
    for line in lines:
        line = line.strip()
        if not line or len(line) < 5:
            continue
        
        # Try to extract channel
        chan_match = CHAN_RE.search(line)
        if not chan_match:
            continue
        
        channel = int(chan_match.group(1) or chan_match.group(2))
        
        # Try to extract time
        time_match = TIME_RE.search(line)
        if not time_match:
            continue
        
        hour = int(time_match["h"])
        minute = int(time_match["m"])
        
        ampm = (time_match["ap"] or "").lower().replace(".", "")
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        
        # Extract teams
        teams = extract_teams(line)
        if not teams:
            continue
        
        team1, team2 = teams[0]
        
        # Calculate start time
        post_date = post_time.astimezone(PALESTINE).date()
        try:
            start = datetime(
                post_date.year,
                post_date.month,
                post_date.day,
                hour,
                minute,
                tzinfo=PALESTINE,
            )
        except ValueError:
            continue
        
        if not in_window(start):
            continue
        
        event = {
            "channel_id": f"FajerSport{channel}",
            "channel_num": channel,
            "channel_name": CHANNELS[channel][1],
            "start": start,
            "title": f"{team1} - {team2}",
            "source_name": "FajerSportOfficialTelegramText",
        }
        
        events.append(event)
        log(f"✓ Text: {channel} @ {hour:02d}:{minute:02d} | {team1} - {team2}")
    
    return events


def fetch_recent_telegram_pages(base_url):
    """Fetch recent Telegram posts with better error handling."""
    pages = []
    
    for page_num in range(1, TELEGRAM_MAX_PAGES + 1):
        try:
            url = f"{base_url}?p={page_num}"
            html = fetch(url)
            pages.append(html)
            log(f"Fetched Telegram page {page_num}")
        except Exception as exc:
            warn(f"Failed to fetch page {page_num}: {exc}")
            if page_num == 1:
                raise  # First page must succeed
    
    return pages


def image_urls(soup_msg):
    """Extract image URLs from Telegram message."""
    urls = []
    
    img_divs = soup_msg.find_all("img", class_="tgme_widget_message_image")
    for img in img_divs:
        src = img.get("src")
        if src:
            urls.append(src)
    
    return urls


def message_time(soup_msg):
    """Extract post time from Telegram message."""
    time_elem = soup_msg.find("time")
    if time_elem and time_elem.get("datetime"):
        try:
            return datetime.fromisoformat(time_elem["datetime"])
        except:
            pass
    return now_utc()


def parse_telegram_pages(pages):
    """Parse all Telegram pages for events."""
    events = []
    seen_images = set()
    
    for page_html in pages:
        try:
            soup = BeautifulSoup(page_html, "html.parser")
        except Exception as exc:
            warn(f"Failed to parse page: {exc}")
            continue
        
        messages = soup.find_all("div", class_="tgme_widget_message")
        
        for msg in messages:
            post_time = message_time(msg)
            
            # Check if within recent days
            days_old = (now_utc() - post_time).days
            if days_old > TELEGRAM_RECENT_DAYS:
                continue
            
            # Parse text content
            text_elem = msg.find("div", class_="tgme_widget_message_text")
            if text_elem:
                text = text_elem.get_text()
                events.extend(parse_telegram_text(text, post_time))
            
            # Parse images
            for image_url in image_urls(msg):
                if image_url in seen_images:
                    continue
                
                seen_images.add(image_url)
                
                try:
                    data = fetch(image_url, binary=True)
                    
                    if len(data) < 5000:  # Lowered threshold
                        continue
                    
                    im = Image.open(io.BytesIO(data)).convert("RGB")
                    
                    # Check dimensions
                    if im.width < 600 or im.height < 300:
                        continue
                    
                    events.extend(parse_poster(im, post_time, image_url))
                    
                except Exception as exc:
                    warn(f"Poster processing failed: {image_url[:60]} | {exc}")
    
    return events


def dedupe(events):
    """Remove duplicate events (same channel, time, teams)."""
    seen = {}
    unique = []
    
    for event in events:
        key = (
            event["channel_id"],
            event["start"].isoformat(),
            event["title"],
        )
        
        if key not in seen:
            seen[key] = True
            unique.append(event)
    
    return sorted(unique, key=lambda e: e["start"])


def collect():
    """Collect all events from Telegram."""
    errors = []
    
    for base in TELEGRAM_URLS:
        try:
            pages = fetch_recent_telegram_pages(base)
            events = parse_telegram_pages(pages)
            
            log(f"\n{'='*60}")
            log(f"SUCCESS: Found {len(events)} events")
            log(f"Pages processed: {len(pages)}")
            log(f"{'='*60}\n")
            
            return events
        
        except Exception as exc:
            errors.append(f"{base}: {exc}")
            warn(f"Telegram source failed: {base} | {exc}")
    
    raise RuntimeError(
        "All Telegram sources failed: " + " || ".join(errors)
    )


# ============================================================
# XMLTV OUTPUT
# ============================================================

def write_xml(events):
    """Write events to XMLTV file."""
    root = ET.Element(
        "tv",
        generator_info_name="Fajer Sport Telegram + Poster OCR EPG",
    )

    # Add channels
    for n in range(1, 6):
        channel_id, channel_name = CHANNELS[n]
        channel = ET.SubElement(root, "channel", id=channel_id)
        
        ET.SubElement(channel, "display-name", lang="ar").text = channel_name
        ET.SubElement(channel, "display-name", lang="en").text = f"Fajer Sport {n}"

    # Compute programme end times
    starts_by_channel = {}
    for item in events:
        channel_id = item["channel_id"]
        item_start = item["start"].astimezone(UTC)
        starts_by_channel.setdefault(channel_id, []).append(item_start)

    for channel_starts in starts_by_channel.values():
        channel_starts.sort()

    # Add programmes
    for event in events:
        start = event["start"].astimezone(UTC)
        default_stop = start + timedelta(minutes=110)

        next_start = next(
            (candidate for candidate in starts_by_channel[event["channel_id"]]
             if candidate > start),
            None,
        )

        stop = next_start if (next_start and next_start < default_stop) else default_stop

        programme = ET.SubElement(
            root,
            "programme",
            start=xmltv_time(start),
            stop=xmltv_time(stop),
            channel=event["channel_id"],
        )

        ET.SubElement(programme, "title", lang="ar").text = event["title"]
        ET.SubElement(programme, "category", lang="en").text = "Sports"

        local = start.astimezone(PALESTINE)

        ET.SubElement(
            programme,
            "desc",
            lang="ar",
        ).text = (
            f"{event['channel_name']}\n"
            f"{local:%Y-%m-%d %H:%M} بتوقيت فلسطين\n"
            f"المصدر: {event['source_name']}"
        )

    ET.indent(root, space="  ")
    ET.ElementTree(root).write(OUTPUT, encoding="utf-8", xml_declaration=True)
    
    # Validate XML
    ET.parse(OUTPUT)
    
    log(f"\n✅ EPG written to: {OUTPUT}")
    log(f"✅ Total events: {len(events)}")


# ============================================================
# MAIN
# ============================================================

def main():
    log("=" * 60)
    log("FAJER SPORT EPG UPDATER - IMPROVED VERSION")
    log("=" * 60)
    log("Mode: Telegram Text + Poster OCR")
    log("Channels: 1-5")
    log("Format: XMLTV")
    log("=" * 60 + "\n")

    if len(sys.argv) > 2 and sys.argv[1] == "--test-image":
        im = Image.open(sys.argv[2]).convert("RGB")
        events = parse_poster(im, now_utc(), "test")
        log(f"\n✅ Test image parsed: {len(events)} events")
        for e in events:
            log(f"  - Channel {e['channel_num']} @ {e['start']:%H:%M} | {e['title']}")
        return

    events = collect()
    events = dedupe(events)
    write_xml(events)


if __name__ == "__main__":
    main()
