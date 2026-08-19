#!/usr/bin/env python3
import html
import re
import sys
import os
import subprocess
import tempfile
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
RADARKORA_TELEGRAM = "https://t.me/s/radarkora2"

THMANYAH_LOGO = "https://upload.wikimedia.org/wikipedia/commons/e/e9/Thmanyah_Logo.svg"

KEEP_DAYS_BACK = 1
KEEP_DAYS_FORWARD = 10
DEFAULT_CHANNELS = {1, 2, 3}
GUIDE_CHANNEL_ID = "ThmanyahGuide"

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

def fixture_key(event):
    return (
        event["start"].strftime("%Y%m%d%H%M"),
        norm(event["title"]).casefold(),
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


ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

def normalize_ocr(value):
    value = html.unescape(value or "").translate(ARABIC_DIGITS)
    value = value.replace("ـ", "")
    value = value.replace("ثمانيه", "ثمانية")
    value = value.replace("ثمانيةة", "ثمانية")
    value = value.replace("x", " × ").replace("X", " × ")
    value = value.replace("🆚", " × ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()

def radar_post_day(text):
    text = normalize_ocr(text)
    months_pattern = "|".join(map(re.escape, AR_MONTHS))
    m = re.search(rf"\b(\d{{1,2}})\s+({months_pattern})\b", text, re.I)
    if not m:
        return None

    day = int(m.group(1))
    month = AR_MONTHS[m.group(2)]
    year = NOW.year

    try:
        candidate = date(year, month, day)
    except ValueError:
        return None

    # Handle year rollover around December/January.
    if candidate < NOW.date() - timedelta(days=180):
        try:
            candidate = date(year + 1, month, day)
        except ValueError:
            pass

    return candidate

def telegram_image_url(post):
    # Telegram public preview stores photos in background-image:url(...)
    for node in post.select(
        ".tgme_widget_message_photo_wrap, "
        ".tgme_widget_message_photo, "
        ".tgme_widget_message_document_wrap"
    ):
        style = node.get("style", "")
        m = re.search(r"background-image\s*:\s*url\(['\"]?([^'\")]+)", style)
        if m:
            return html.unescape(m.group(1))

    # Fallback to normal image element if Telegram changes markup.
    img = post.find("img", src=True)
    if img:
        return html.unescape(img["src"])

    return None

def ocr_image_url(url):
    """
    RadarKora publishes the detailed schedule inside an image.
    OCR is used ONLY for these RadarKora daily-schedule images.
    Requires tesseract + Arabic language pack in the workflow.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=35)
        response.raise_for_status()
    except Exception as exc:
        warn(f"RadarKora image download failed: {exc}")
        return ""

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="radarkora_",
            suffix=".jpg",
            delete=False,
        ) as tmp:
            tmp.write(response.content)
            tmp_path = tmp.name

        outputs = []

        # Two page segmentation modes improve resilience to poster layouts.
        for psm in ("6", "11"):
            try:
                proc = subprocess.run(
                    [
                        "tesseract",
                        tmp_path,
                        "stdout",
                        "-l",
                        "ara+eng",
                        "--psm",
                        psm,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=45,
                    check=False,
                )
                if proc.stdout.strip():
                    outputs.append(proc.stdout)
            except Exception as exc:
                warn(f"RadarKora OCR psm={psm} failed: {exc}")

        return normalize_ocr("\n".join(outputs))

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

def team_tokens(value):
    value = normalize_team_name(value)
    stop = {
        "نادي", "fc", "club", "ريال",  # "ريال" kept only if paired with another token
        "ال", "و",
    }
    tokens = [
        token
        for token in value.split()
        if len(token) >= 3 and token not in stop
    ]

    # If filtering became too aggressive, use original meaningful words.
    if not tokens:
        tokens = [
            token
            for token in value.split()
            if len(token) >= 3
        ]
    return tokens

def fixture_match_score(title, context):
    """
    Match a Goal/Kooora daily fixture to text around a RadarKora channel label.
    We do not invent a match: both teams need evidence in the OCR context.
    """
    signature = fixture_signature(title)
    if not signature or len(signature) != 2:
        return 0

    context_norm = normalize_team_name(context)
    teams = list(signature)
    team_scores = []

    for team in teams:
        tokens = team_tokens(team)
        if not tokens:
            team_scores.append(0)
            continue

        hits = sum(1 for token in tokens if token in context_norm)
        team_scores.append(hits / len(tokens))

    # Both teams must be represented.
    if min(team_scores) < 0.45:
        return 0

    return sum(team_scores)

def radar_contexts(ocr_text):
    """
    Return contexts around explicit ثمانية N labels.
    Only numbered channels are confirmations.
    """
    text = normalize_ocr(ocr_text)
    contexts = []

    for match in THMANYAH_NUMBER_RE.finditer(text):
        number = int(match.group(1))
        start = max(0, match.start() - 260)
        end = min(len(text), match.end() + 260)
        contexts.append((number, text[start:end]))

    return contexts

def collect_radarkora_confirmations(daily):
    """
    RadarKora confirmation source.

    Workflow:
      1) Fetch public Telegram preview.
      2) Select #مباريات_اليوم posts in our active date window.
      3) OCR the schedule image.
      4) Use explicit 'ثمانية N' labels only.
      5) Match that label to an already-known Goal/Kooora fixture.
         No random channel assignment.
    """
    try:
        soup = BeautifulSoup(fetch(RADARKORA_TELEGRAM), "html.parser")
    except Exception as exc:
        warn(f"RadarKora Telegram fetch failed: {exc}")
        return []

    confirmations = []
    posts = soup.select(".tgme_widget_message")

    for post in posts:
        caption_node = post.select_one(
            ".tgme_widget_message_text, .tgme_widget_message_caption"
        )
        caption = (
            caption_node.get_text(" ", strip=True)
            if caption_node
            else ""
        )

        caption_norm = normalize_ocr(caption)
        if "مباريات_اليوم" not in caption_norm and "مباريات اليوم" not in caption_norm:
            continue

        post_day = radar_post_day(caption_norm)
        if not post_day:
            continue

        probe = make_dt(post_day, 12, 0)
        if not in_window(probe):
            continue

        image_url = telegram_image_url(post)
        if not image_url:
            continue

        ocr_text = ocr_image_url(image_url)
        if not ocr_text:
            continue

        contexts = radar_contexts(ocr_text)
        if not contexts:
            continue

        daily_same_day = [
            event
            for event in daily
            if event["start"].date() == post_day
        ]

        for channel, context in contexts:
            scored = []
            for event in daily_same_day:
                score = fixture_match_score(event["title"], context)
                if score > 0:
                    scored.append((score, event))

            scored.sort(key=lambda item: item[0], reverse=True)

            # Require a clear winner. If OCR is ambiguous, ignore it.
            if not scored:
                continue

            best_score, best = scored[0]
            second_score = scored[1][0] if len(scored) > 1 else 0

            if best_score < 1.0:
                continue
            if second_score and best_score - second_score < 0.25:
                continue

            confirmations.append({
                "channel": channel,
                "start": best["start"],
                "title": best["title"],
                "source": "RadarKora Telegram OCR",
            })

            log(
                "RADARKORA CONFIRMATION | "
                f"{best['start']:%Y-%m-%d %H:%M} | "
                f"{best['title']} | THMANYAH {channel}"
            )

    confirmations = dedupe(confirmations)
    log(f"RadarKora numbered confirmations detected: {len(confirmations)}")
    return confirmations

def resolve_events(daily, confirmations):
    confirmed_by_signature = {}

    for event in confirmations:
        signature = fixture_signature(event["title"])
        if signature:
            confirmed_by_signature.setdefault(signature, []).append(event)

    result = []

    for event in daily:
        current = dict(event)

        # Explicitly numbered in the source -> keep on that real channel.
        if current.get("channel") is not None:
            result.append(current)
            continue

        signature = fixture_signature(current["title"])
        candidates = confirmed_by_signature.get(signature, []) if signature else []

        # Only accept a confirmation on the same date and close kickoff time.
        candidates = [
            candidate
            for candidate in candidates
            if candidate["start"].date() == current["start"].date()
            and abs((candidate["start"] - current["start"]).total_seconds()) <= 2 * 60 * 60
        ]

        if len(candidates) == 1:
            best = candidates[0]
            current["channel"] = best["channel"]
            current["source"] = f"{current['source']} + {best['source']}"
            result.append(current)
        else:
            # Do not guess. Keep it on the Guide channel.
            current["channel"] = None
            result.append(current)
            log(
                "THMANYAH GUIDE | "
                f"{current['start']:%Y-%m-%d %H:%M} | {current['title']}"
            )

    # Keep explicit numbered confirmations even if daily discovery missed them.
    result.extend(confirmations)

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

        if channel_id == GUIDE_CHANNEL_ID:
            channel = None
        else:
            channel_match = re.fullmatch(
                r"Thmanyah(10|[1-9])\.sa",
                channel_id,
                re.I,
            )
            if not channel_match:
                continue
            channel = int(channel_match.group(1))

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

        # Never recycle generated filler as a real event.
        if title in {
            "لا توجد مباريات مجدولة",
            "لا توجد مباراة حالياً",
            "لا توجد مباراة معلنة",
            "No information",
            "No scheduled matches",
        }:
            continue

        events.append({
            "channel": channel,
            "start": start,
            "title": title,
            "source": "existing XML",
        })

    return dedupe(events)

def merge_existing(existing, fresh):
    merged = {}

    for event in existing:
        merged[fixture_key(event)] = event

    for event in fresh:
        key = fixture_key(event)
        old = merged.get(key)

        if old is None:
            merged[key] = event
            continue

        old_confirmed = old.get("channel") is not None
        new_confirmed = event.get("channel") is not None

        # A confirmed real channel always wins.
        if new_confirmed or not old_confirmed:
            merged[key] = event

    return dedupe([
        event
        for event in merged.values()
        if in_window(event["start"])
    ])


def write_xml(events):
    """
    Clean TiviMate XMLTV:
      - Thmanyah 1 / 2 / 3
      - Thmanyah | Guide
      - one ID per EPG channel
      - hourly filler on all four entries so all four are indexable in Assign EPG
      - real matches never overlap filler
    """
    channels = [1, 2, 3]

    tv = ET.Element(
        "tv",
        {"generator-info-name": "Thmanyah Sports Verified EPG"},
    )

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

    guide = ET.SubElement(tv, "channel", {"id": GUIDE_CHANNEL_ID})
    ET.SubElement(
        guide,
        "display-name",
        {"lang": "ar"},
    ).text = "ثمانية | Guide"
    ET.SubElement(
        guide,
        "display-name",
        {"lang": "en"},
    ).text = "Thmanyah | Guide"

    real_by_id = {
        "Thmanyah1.sa": [],
        "Thmanyah2.sa": [],
        "Thmanyah3.sa": [],
        GUIDE_CHANNEL_ID: [],
    }

    for event in events:
        channel = event.get("channel")

        if channel in (1, 2, 3):
            channel_id = f"Thmanyah{channel}.sa"
        else:
            channel_id = GUIDE_CHANNEL_ID

        stop = event["start"] + timedelta(hours=3)
        real_by_id[channel_id].append((event["start"], stop))

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

        if channel in (1, 2, 3):
            desc = (
                f"القناة المعلنة: ثمانية {channel}. "
                f"موعد المباراة: {event['start']:%Y-%m-%d %H:%M} بتوقيت مكة. "
                f"المصدر: {event['source']}"
            )
        else:
            desc = (
                "المباراة معلنة على شبكة ثمانية، لكن رقم القناة لم يُعلن بعد. "
                f"الموعد: {event['start']:%Y-%m-%d %H:%M} بتوقيت مكة. "
                f"المصدر: {event['source']}"
            )

        ET.SubElement(
            programme,
            "desc",
            {"lang": "ar"},
        ).text = desc

    window_start = NOW.astimezone(TZ).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    window_end = window_start + timedelta(days=KEEP_DAYS_FORWARD + 1)

    def add_hourly_filler(channel_id, gap_start, gap_stop):
        cursor = gap_start
        while cursor < gap_stop:
            stop = min(cursor + timedelta(hours=1), gap_stop)

            p = ET.SubElement(
                tv,
                "programme",
                {
                    "start": cursor.strftime("%Y%m%d%H%M%S %z"),
                    "stop": stop.strftime("%Y%m%d%H%M%S %z"),
                    "channel": channel_id,
                },
            )
            ET.SubElement(
                p,
                "title",
                {"lang": "ar"},
            ).text = "لا توجد مباراة حالياً"

            ET.SubElement(
                p,
                "category",
                {"lang": "en"},
            ).text = "Sports"

            if channel_id == GUIDE_CHANNEL_ID:
                filler_desc = (
                    "لا توجد حالياً مباراة على شبكة ثمانية بانتظار إعلان رقم القناة."
                )
            else:
                filler_desc = (
                    "لا توجد مباراة معلنة على هذه القناة حالياً."
                )

            ET.SubElement(
                p,
                "desc",
                {"lang": "ar"},
            ).text = filler_desc

            cursor = stop

    for channel_id, intervals in real_by_id.items():
        clean_intervals = []

        for s, e in sorted(intervals):
            s = max(s, window_start)
            e = min(e, window_end)
            if e > s:
                clean_intervals.append((s, e))

        merged = []
        for s, e in clean_intervals:
            if not merged or s > merged[-1][1]:
                merged.append([s, e])
            else:
                merged[-1][1] = max(merged[-1][1], e)

        cursor = window_start
        for s, e in merged:
            if s > cursor:
                add_hourly_filler(channel_id, cursor, s)
            cursor = max(cursor, e)

        if cursor < window_end:
            add_hourly_filler(channel_id, cursor, window_end)

    ET.indent(tv, space="  ")
    ET.ElementTree(tv).write(
        OUT,
        encoding="utf-8",
        xml_declaration=True,
    )

    # Hard validation: all 4 EPG entries must have current-time coverage.
    root = ET.parse(OUT).getroot()

    channel_ids = [c.get("id") for c in root.findall("channel")]
    expected_ids = {
        "Thmanyah1.sa",
        "Thmanyah2.sa",
        "Thmanyah3.sa",
        GUIDE_CHANNEL_ID,
    }

    if set(channel_ids) != expected_ids or len(channel_ids) != 4:
        raise RuntimeError(
            "Thmanyah XML validation failed; expected exactly 4 channels, got: "
            + ", ".join(channel_ids)
        )

    now_check = NOW.astimezone(TZ)
    required = {
        "Thmanyah1.sa": False,
        "Thmanyah2.sa": False,
        "Thmanyah3.sa": False,
        GUIDE_CHANNEL_ID: False,
    }

    for programme in root.findall("programme"):
        channel_id = programme.get("channel") or ""
        if channel_id not in required:
            continue

        try:
            s = datetime.strptime(
                (programme.get("start") or "")[:14],
                "%Y%m%d%H%M%S",
            ).replace(tzinfo=TZ)
            e = datetime.strptime(
                (programme.get("stop") or "")[:14],
                "%Y%m%d%H%M%S",
            ).replace(tzinfo=TZ)
        except Exception:
            continue

        if s <= now_check < e:
            required[channel_id] = True

    log(
        "THMANYAH CURRENT COVERAGE | "
        + ", ".join(
            f"{key}:{'YES' if ok else 'NO'}"
            for key, ok in required.items()
        )
    )

    missing = [key for key, ok in required.items() if not ok]
    if missing:
        raise RuntimeError(
            "Thmanyah XML validation failed; missing current coverage: "
            + ", ".join(missing)
        )

def main():
    existing = read_existing()
    log(f"Existing REAL Thmanyah programmes kept: {len(existing)}")

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

    daily = dedupe(daily)

    confirmations_365 = collect_numbered_365()
    confirmations_radar = collect_radarkora_confirmations(daily)

    confirmations = dedupe(
        confirmations_radar + confirmations_365
    )

    log(
        "Thmanyah confirmations total: "
        f"{len(confirmations)} "
        f"(RadarKora={len(confirmations_radar)}, "
        f"365Scores={len(confirmations_365)})"
    )

    fresh = resolve_events(daily, confirmations)
    fresh = [
        event
        for event in fresh
        if in_window(event["start"])
    ]

    log(f"Thmanyah newly resolved programmes: {len(fresh)}")

    for event in fresh:
        if event.get("channel") in (1, 2, 3):
            log(
                f"  THMANYAH {event['channel']} | "
                f"{event['start']:%Y-%m-%d %H:%M} | "
                f"{event['title']}"
            )
        else:
            log(
                f"  THMANYAH GUIDE | "
                f"{event['start']:%Y-%m-%d %H:%M} | "
                f"{event['title']}"
            )

    merged = merge_existing(existing, fresh)
    log(f"Thmanyah total REAL programmes after merge: {len(merged)}")

    if not fresh and existing:
        warn(
            "No fresh Thmanyah fixtures; rebuilding XML from preserved real events"
        )

    write_xml(merged)
    log(f"Written: {OUT}")

if __name__ == "__main__":
    main()
