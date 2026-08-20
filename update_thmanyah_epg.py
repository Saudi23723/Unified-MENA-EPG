#!/usr/bin/env python3
import html
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from difflib import SequenceMatcher
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

from PIL import Image, ImageOps, ImageEnhance
import pytesseract
from pytesseract import Output

TZ = ZoneInfo("Asia/Riyadh")
NOW = datetime.now(TZ)
OUT = Path("thmanyah_epg.xml")

GOAL_HOME = "https://www.goal.com/ar"
KOOORA_HOME = "https://www.kooora.com/"
SCORES365_HOME = "https://www.365scores.com/ar/news/magazine/"
RADARKORA_TELEGRAM = "https://t.me/s/matches_today2"

THMANYAH_LOGO = "https://upload.wikimedia.org/wikipedia/commons/e/e9/Thmanyah_Logo.svg"

KEEP_DAYS_BACK = 1
KEEP_DAYS_FORWARD = 10
CHANNELS = (1, 2, 3)
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
    r"(?:قناة\s*)?(?:ثمانية|ثمانيه|ثماني|thmanyah)\s*[.\-:]?\s*([123])(?:\d)?\b",
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

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

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
    if not first or not second or len(first) > 80 or len(second) > 80:
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
    signature = fixture_signature(event["title"])
    title_key = "|".join(sorted(signature)) if signature else norm(event["title"]).casefold()
    return (
        event["start"].strftime("%Y%m%d%H%M"),
        title_key,
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
            int(item["channel"]) if item.get("channel") in CHANNELS else 0,
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
            "confirmed": channel in CHANNELS,
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
                "confirmed": channel in CHANNELS,
            })

    return dedupe(events)

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

    # 365Scores headlines often look like:
    # "القنوات الناقلة لمباراة الهلال - الفيحاء بالجولة..."
    # Extract only the two teams so the confirmation can match the daily fixture.
    pair_re = re.compile(
        r"(?:مباراة|مواجهة)\\s+"
        r"(.{2,70}?)\\s*[-–—]\\s*(.{2,70}?)"
        r"(?=\\s+(?:بالجولة|ضمن|في|لحساب|والقنوات|موعد|اليوم|غد(?:اً|ا)?|$))",
        re.I,
    )

    for candidate_text in candidates:
        pair = pair_re.search(candidate_text)
        if pair:
            first = clean_team(pair.group(1))
            second = clean_team(pair.group(2))
            if first and second:
                return f"{first} - {second}"

    for candidate_text in candidates:
        title = fixture_from_text(candidate_text)
        if title:
            return title
    return None

def parse_365_article(url):
    """
    365Scores is used ONLY to confirm the Thmanyah channel number.
    Its page time is intentionally ignored because article metadata/body times
    can be unrelated to kickoff. Kickoff always stays from Goal/Kooora.
    """
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
    except Exception:
        return None

    text = norm(soup.get_text(" ", strip=True))
    channel_match = THMANYAH_NUMBER_RE.search(text)
    if not channel_match:
        return None

    channel = int(channel_match.group(1))
    if channel not in CHANNELS:
        return None

    day = parse_date(text, NOW.date())
    if not day:
        return None

    title = title_from_365(soup)
    if not title:
        return None

    return {
        "channel": channel,
        "date": day,
        "title": title,
        "source": url,
        "confirmed": True,
    }


def collect_numbered_365():
    confirmations = []
    seen = set()

    for url in discover_365_articles():
        confirmation = parse_365_article(url)
        if not confirmation:
            continue

        signature = fixture_signature(confirmation["title"])
        if not signature:
            continue

        key = (
            confirmation["date"],
            tuple(sorted(signature)),
            confirmation["channel"],
        )
        if key in seen:
            continue
        seen.add(key)
        confirmations.append(confirmation)

    confirmations.sort(
        key=lambda item: (
            item["date"],
            tuple(sorted(fixture_signature(item["title"]) or ())),
            item["channel"],
        )
    )

    log(
        f"365Scores channel-only confirmations detected: {len(confirmations)} "
        "| TIMES IGNORED"
    )
    return confirmations

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

    if candidate < NOW.date() - timedelta(days=180):
        try:
            candidate = date(year + 1, month, day)
        except ValueError:
            pass
    return candidate

def telegram_image_url(post):
    for node in post.select(
        ".tgme_widget_message_photo_wrap, "
        ".tgme_widget_message_photo, "
        ".tgme_widget_message_document_wrap"
    ):
        style = node.get("style", "")
        m = re.search(r"background-image\s*:\s*url\(['\"]?([^'\")]+)", style)
        if m:
            return html.unescape(m.group(1))

    img = post.find("img", src=True)
    if img:
        return html.unescape(img["src"])
    return None

def ocr_image_url(url):
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
        for psm in ("3", "6", "11"):
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

        # Keep OCR line breaks. The matches_today2 image is a multi-day table,
        # so flattening the OCR destroys the relationship between each fixture,
        # its channel number and the date heading above it.
        return "\n".join(outputs).strip()

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass



def radar_day_from_ocr_line(line):
    """Extract the Gregorian day shown in a matches_today2 table heading."""
    text = normalize_ocr(line)
    months_pattern = "|".join(map(re.escape, AR_MONTHS))
    # The image format is usually: ... 20 - أغسطس - 2026 ...
    m = re.search(rf"(?<!\d)(\d{{1,2}})\s*[-–—]?\s*({months_pattern})(?:\s*[-–—]?\s*(20\d{{2}}))?", text, re.I)
    if not m:
        return None
    day = int(m.group(1))
    month = AR_MONTHS[m.group(2)]
    year = int(m.group(3)) if m.group(3) else NOW.year
    try:
        return date(year, month, day)
    except ValueError:
        return None


def radar_rows_from_ocr(ocr_text, fallback_day=None):
    """
    Parse the actual matches_today2 image layout line-by-line.

    Each date heading applies to the fixture rows below it until the next date
    heading. We only extract explicit numbered Thmanyah TV channels (1/2/3).
    Rows saying only "تطبيق ثمانية" are intentionally NOT assigned to a TV
    channel.
    """
    rows = []
    current_day = fallback_day
    seen = set()

    glyphs = {
        "①":"1","②":"2","③":"3","❶":"1","❷":"2","❸":"3",
        "➀":"1","➁":"2","➂":"3","➊":"1","➋":"2","➌":"3",
        "⑴":"1","⑵":"2","⑶":"3","⓵":"1","⓶":"2","⓷":"3",
    }

    for raw_line in (ocr_text or "").splitlines():
        line = normalize_ocr(raw_line)
        if not line:
            continue

        heading_day = radar_day_from_ocr_line(line)
        if heading_day:
            current_day = heading_day
            continue

        fixed = line.translate(ARABIC_DIGITS)
        for a, b in glyphs.items():
            fixed = fixed.replace(a, b)

        # OCR commonly reads "ثمانية" as "ثماني" and may append a stray
        # adjacent channel digit (e.g. "ثماني23" for visible "ثماني2").
        m = re.search(
            r"(?:قناة|قناه)?\s*(?:ثمانية|ثمانيه|ثماني|thmanyah)\s*[:：.\-]?\s*([123])(?:\d)?\b",
            fixed,
            re.I,
        )
        if not m:
            continue

        # Do not turn app-only rows into TV channel assignments.
        prefix = fixed[max(0, m.start() - 20):m.start()]
        if "تطبيق" in prefix and not re.search(r"(?:قناة|قناه)", prefix):
            continue

        channel = int(m.group(1))
        if channel not in CHANNELS:
            continue

        key = (current_day, channel, fixed)
        if key in seen:
            continue
        seen.add(key)
        rows.append((current_day, channel, fixed))

    return rows

def team_tokens(value):
    value = normalize_team_name(value)
    stop = {"نادي", "fc", "club", "ريال", "ال", "و"}
    tokens = [
        token for token in value.split()
        if len(token) >= 3 and token not in stop
    ]
    if not tokens:
        tokens = [token for token in value.split() if len(token) >= 3]
    return tokens

def fixture_match_score(title, context):
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

        context_words = [w for w in context_norm.split() if len(w) >= 3]
        hits = 0
        for token in tokens:
            if token in context_norm:
                hits += 1
                continue
            # Arabic OCR frequently substitutes one letter (e.g. الفتح -> الطتح).
            # Allow a conservative fuzzy token match so the row can still be
            # linked to the known Goal/Kooora fixture on the same date.
            best = max(
                (SequenceMatcher(None, token, word).ratio() for word in context_words),
                default=0.0,
            )
            if best >= 0.74:
                hits += 1
        team_scores.append(hits / len(tokens))

    if min(team_scores) < 0.45:
        return 0
    return sum(team_scores)

def radar_contexts(ocr_text):
    raw = html.unescape(ocr_text or "").translate(ARABIC_DIGITS)
    glyphs = {"①":"1","②":"2","③":"3","❶":"1","❷":"2","❸":"3","➀":"1","➁":"2","➂":"3","➊":"1","➋":"2","➌":"3","⑴":"1","⑵":"2","⑶":"3","⓵":"1","⓶":"2","⓷":"3"}
    for a,b in glyphs.items(): raw=raw.replace(a, f" {b} ")
    text=normalize_ocr(raw); contexts=[]; seen=set()
    def add(n,a,b):
        n=int(n)
        if n not in CHANNELS: return
        c=text[max(0,a-320):min(len(text),b+320)]
        if (n,c) not in seen: seen.add((n,c)); contexts.append((n,c))
    for m in THMANYAH_NUMBER_RE.finditer(text): add(m.group(1),m.start(),m.end())
    pats=[re.compile(r"(?:القناة|قناه|channel|ناقلة|الناقلة|الناقل)\s*[:：\-–—|]?\s*(?:ثمانية|ثمانيه|thmanyah)?\s*[\[\(\{<]?\s*([123])\s*[\]\)\}>]?",re.I),re.compile(r"(?:ثمانية|ثمانيه|thmanyah)\s*(?:sports?|sport)?\s*[:：\-–—|]?\s*[\[\(\{<]?\s*([123])\s*[\]\)\}>]?",re.I)]
    for pat in pats:
        for m in pat.finditer(text): add(m.group(1),m.start(),m.end())
    lines=[normalize_ocr(x) for x in (ocr_text or '').splitlines() if normalize_ocr(x)]
    dr=re.compile(r"^[^\w\u0600-\u06ff]{0,4}([123])[^\w\u0600-\u06ff]{0,4}$")
    for i,line in enumerate(lines):
        c=line.translate(ARABIC_DIGITS)
        for a,b in glyphs.items(): c=c.replace(a,b)
        c=normalize_ocr(c); m=dr.match(c)
        if not m: continue
        block=normalize_ocr(' '.join(lines[max(0,i-4):min(len(lines),i+5)]))
        if fixture_from_text(block) is None and not any(x in block for x in ('مباراة','مباريات','الدوري','كأس','دوري روشن','vs',' × ','ضد')): continue
        pos=text.find(c); pos=max(0,pos); add(m.group(1),pos,pos+len(c))
    return contexts


def _layout_preprocess_image(path):
    image = Image.open(path).convert("RGB")
    if image.width < 2200:
        scale = max(2, min(3, round(2200 / max(1, image.width))))
        image = image.resize(
            (image.width * scale, image.height * scale),
            Image.Resampling.LANCZOS,
        )

    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(1.45)
    return gray


def _ocr_data_lines(image):
    data = pytesseract.image_to_data(
        image,
        lang="ara+eng",
        config="--oem 1 --psm 6",
        output_type=Output.DICT,
    )

    groups = defaultdict(list)
    total = len(data.get("text", []))

    for i in range(total):
        token = normalize_ocr(data["text"][i])
        if not token:
            continue

        try:
            conf = float(str(data.get("conf", ["-1"] * total)[i]))
        except Exception:
            conf = -1

        if conf < 10:
            continue

        key = (
            data.get("block_num", [0] * total)[i],
            data.get("par_num", [0] * total)[i],
            data.get("line_num", [0] * total)[i],
        )

        left = int(data["left"][i])
        top = int(data["top"][i])
        width = int(data["width"][i])
        height = int(data["height"][i])

        groups[key].append({
            "text": token,
            "left": left,
            "top": top,
            "right": left + width,
            "bottom": top + height,
            "cy": top + height / 2.0,
        })

    lines = []

    for words in groups.values():
        y = sum(w["cy"] for w in words) / len(words)
        by_x = sorted(words, key=lambda w: w["left"])
        ltr = " ".join(w["text"] for w in by_x)
        rtl = " ".join(w["text"] for w in reversed(by_x))
        combined = normalize_ocr(f"{ltr} | {rtl}")
        lines.append((y, combined, words))

    lines.sort(key=lambda item: item[0])
    return lines


def _extract_channel_from_row_text(text):
    value = normalize_ocr(text).translate(ARABIC_DIGITS)

    glyphs = {
        "①":"1","②":"2","③":"3","❶":"1","❷":"2","❸":"3",
        "➀":"1","➁":"2","➂":"3","➊":"1","➋":"2","➌":"3",
        "⑴":"1","⑵":"2","⑶":"3","⓵":"1","⓶":"2","⓷":"3",
    }
    for a, b in glyphs.items():
        value = value.replace(a, b)

    if "تطبيق" in value and not re.search(r"(?:قناة|قناه)", value):
        return None

    patterns = (
        r"(?:قناة|قناه)\s*(?:ثمانية|ثمانيه|ثماني|thmanyah)\s*[:：.\-]?\s*([123])\b",
        r"(?:ثمانية|ثمانيه|ثماني|thmanyah)\s*[:：.\-]?\s*([123])\b",
        r"(?:ثمانية|ثمانيه|ثماني|thmanyah)([123])\b",
    )

    for pattern in patterns:
        m = re.search(pattern, value, re.I)
        if m:
            n = int(m.group(1))
            if n in CHANNELS:
                return n

    return None


def _ocr_row_crop(image, y_center, height_hint=34):
    pad = max(38, int(height_hint * 2.2))
    top = max(0, int(y_center - pad))
    bottom = min(image.height, int(y_center + pad))

    crop = image.crop((0, top, image.width, bottom))
    crop = ImageOps.autocontrast(crop, cutoff=1)

    outputs = []

    for psm in (6, 11):
        try:
            out = pytesseract.image_to_string(
                crop,
                lang="ara+eng",
                config=f"--oem 1 --psm {psm}",
            )
            if out.strip():
                outputs.append(out)
        except Exception as exc:
            warn(f"matches_today2 row OCR psm={psm} failed: {exc}")

    return "\n".join(outputs)


def ocr_table_rows_url(url, fallback_day=None):
    try:
        response = requests.get(url, headers=HEADERS, timeout=35)
        response.raise_for_status()
    except Exception as exc:
        warn(f"matches_today2 image download failed: {exc}")
        return []

    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            prefix="matches_today2_layout_",
            suffix=".jpg",
            delete=False,
        ) as tmp:
            tmp.write(response.content)
            tmp_path = tmp.name

        image = _layout_preprocess_image(tmp_path)
        lines = _ocr_data_lines(image)

        date_marks = []
        for y, line_text, _ in lines:
            day = radar_day_from_ocr_line(line_text)
            if day:
                date_marks.append((y, day))

        def day_for_y(y):
            candidates = [(dy, day) for dy, day in date_marks if dy <= y + 6]
            if candidates:
                return max(candidates, key=lambda item: item[0])[1]
            return fallback_day

        candidates = []

        for y, line_text, words in lines:
            channel = _extract_channel_from_row_text(line_text)

            if channel is None and not re.search(
                r"(?:ثمان|thmanyah)",
                line_text,
                re.I,
            ):
                continue

            h = max(
                (w["bottom"] - w["top"] for w in words),
                default=34,
            )

            row_text = _ocr_row_crop(image, y, h)
            channel = _extract_channel_from_row_text(
                f"{line_text}\n{row_text}"
            )

            if channel is None:
                continue

            candidates.append((y, channel, row_text))

        candidates.sort(key=lambda item: item[0])

        merged = []

        for y, channel, row_text in candidates:
            if (
                merged
                and abs(y - merged[-1][0]) < 40
                and channel == merged[-1][1]
            ):
                if len(normalize_ocr(row_text)) > len(
                    normalize_ocr(merged[-1][2])
                ):
                    merged[-1] = (y, channel, row_text)
                continue

            merged.append((y, channel, row_text))

        rows = []
        seen = set()

        for y, channel, row_text in merged:
            day = day_for_y(y)
            context = normalize_ocr(row_text)
            key = (day, channel, context)

            if key in seen:
                continue

            seen.add(key)
            rows.append((day, channel, context))

        return rows

    except Exception as exc:
        warn(f"matches_today2 layout OCR failed: {exc}")
        return []

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass




# v15: structured table OCR for matches_today2.
# The Telegram images are actual tables: date headings, fixture/time on the right,
# channel in the middle, commentator on the left. OCR each column separately and
# use vertical position to attach each row to the nearest date heading above it.
_OCR_TEAM_LEXICON = [
    "الهلال", "الفيحاء", "الرياض", "النصر", "الحزم", "الدرعية",
    "الفيصلي", "نيوم", "القادسية", "الاتحاد", "الفتح", "الاتفاق",
    "الخلود", "التعاون", "الخليج", "الشباب", "الأهلي", "ابها", "أبها",
    "ضمك", "العلا", "الأخدود", "الوحدة", "الرائد", "الباطن",
]

def _arabic_loose(value):
    value = normalize_ocr(value).translate(ARABIC_DIGITS)
    value = (value.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
                  .replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و")
                  .replace("ئ", "ي"))
    value = re.sub(r"[^\u0600-\u06ff ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def _repair_ocr_team(raw):
    raw = normalize_ocr(raw)
    target = _arabic_loose(raw)
    if not target:
        return None, 0.0
    ranked = []
    for team in _OCR_TEAM_LEXICON:
        candidate = _arabic_loose(team)
        score = SequenceMatcher(None, target, candidate).ratio()
        if candidate in target or target in candidate:
            score = max(score, 0.82)
        ranked.append((score, team))
    ranked.sort(reverse=True)
    score, team = ranked[0]
    if score < 0.42:
        return raw.strip(), score
    # Prefer normal Arabic spelling with hamza where known.
    if team == "ابها":
        team = "أبها"
    return team, score

def _fixture_from_right_column(text):
    value = normalize_ocr(text)
    # Restrict both sides to Arabic words around the actual dash. This prevents
    # the kickoff/commentator text from being mistaken for a team name.
    matches = list(re.finditer(
        r"([\u0600-\u06ff][\u0600-\u06ff\s]{1,24})\s*[-–—]\s*"
        r"([\u0600-\u06ff][\u0600-\u06ff\s]{1,24})",
        value,
    ))
    best = None
    for match in matches:
        left_raw = match.group(1).strip()
        right_raw = match.group(2).strip()
        left, ls = _repair_ocr_team(left_raw)
        right, rs = _repair_ocr_team(right_raw)
        score = ls + rs
        if left and right and (best is None or score > best[0]):
            best = (score, left, right)
    if not best:
        return None
    _, left, right = best
    return f"{left} - {right}"

def _channel_from_middle_column(text):
    value = normalize_ocr(text).translate(ARABIC_DIGITS)
    if "تطبيق" in value and not re.search(r"(?:قناة|قناه)", value):
        return None
    # Tesseract commonly reads e.g. ثماني23 or ثمانين1. Take the FIRST valid
    # digit immediately following the Thmanyah word instead of rejecting it.
    patterns = (
        r"(?:قناة|قناه)?\s*ثمان[^\s0-9]{0,7}\s*([123])",
        r"(?:قناة|قناه)[^\n]{0,22}?([123])",
    )
    for pattern in patterns:
        match = re.search(pattern, value, re.I)
        if match:
            return int(match.group(1))
    return _extract_channel_from_row_text(value)

def _kickoff_from_right_column(text):
    value = normalize_ocr(text).translate(ARABIC_DIGITS)
    candidates = []
    # Tables use 12-hour source times. Extract one digit before the separator too,
    # so OCR garbage like 519:00 still yields the real printed 9:00 candidate.
    for match in re.finditer(r"[:.]", value):
        pos = match.start()
        after = re.match(r"\s*([0-9]{2})", value[pos + 1:])
        if not after:
            continue
        minute = int(after.group(1))
        if minute > 59:
            continue
        before = re.sub(r"\s+", "", value[max(0, pos - 4):pos])
        digits = re.findall(r"[0-9]", before)
        for width in (1, 2):
            if len(digits) < width:
                continue
            hour = int("".join(digits[-width:]))
            if 1 <= hour <= 12:
                candidates.append((hour, minute))
    if not candidates:
        # OCR often drops the separator in times such as 7:15 and emits 7115
        # or 7215. For short isolated digit runs, trust the first digit as the
        # printed 12-hour hour and the last two digits as minutes.
        compact = []
        for m in re.finditer(r"(?<![0-9])([0-9]{3,4})(?![0-9])", value):
            digits = m.group(1)
            minute = int(digits[-2:])
            hour = int(digits[0])
            if 1 <= hour <= 9 and 0 <= minute <= 59:
                compact.append((hour, minute))
        if compact:
            candidates.extend(compact)
    if not candidates:
        return None
    counts = defaultdict(int)
    for item in candidates:
        counts[item] += 1
    hour, minute = max(counts, key=lambda item: (counts[item], -item[0]))
    if 1 <= hour <= 11:
        hour += 12
    return hour, minute

def _kickoff_from_time_crop(gray, y):
    pad = max(38, int(gray.height * 0.014))
    votes = defaultdict(int)
    for offset in (0, 20, 40, 60):
        cy = y + offset
        top = max(0, int(cy - pad))
        bottom = min(gray.height, int(cy + pad))
        crop = gray.crop((int(gray.width * 0.78), top, gray.width, bottom))
        variants = [
            ImageOps.autocontrast(crop, cutoff=1),
            ImageEnhance.Contrast(ImageOps.autocontrast(crop, cutoff=1)).enhance(2.0),
        ]
        for variant in variants:
            for psm in (7, 13):
                try:
                    raw = pytesseract.image_to_string(
                        variant,
                        lang="eng",
                        config=(
                            f"--oem 1 --psm {psm} "
                            "-c tessedit_char_whitelist=0123456789:."
                        ),
                    )
                except Exception:
                    continue
                text = normalize_ocr(raw).translate(ARABIC_DIGITS)
                for m in re.finditer(r"([0-9]{1,3})\s*[:.]\s*([0-9]{2})", text):
                    raw_hour = m.group(1)
                    minute = int(m.group(2))
                    if minute > 59:
                        continue
                    # Source table is 12-hour. Consider the last digit as the
                    # printed hour when OCR prefixes garbage (29:00 -> 9:00).
                    opts = [int(raw_hour[-1])]
                    if len(raw_hour) <= 2:
                        opts.append(int(raw_hour))
                    for hour in set(opts):
                        if 1 <= hour <= 12:
                            votes[(hour, minute)] += 2
                digits = re.sub(r"\D", "", text)
                if len(digits) >= 3:
                    tail = digits[-3:]
                    hour = int(tail[0])
                    minute = int(tail[1:])
                    if 1 <= hour <= 9 and 0 <= minute <= 59:
                        votes[(hour, minute)] += 1
    if not votes:
        return None
    hour, minute = max(votes, key=lambda item: (votes[item], -item[0]))
    if 1 <= hour <= 11:
        hour += 12
    return hour, minute

def _structured_rows_from_image(image, fallback_day=None):
    if image.width < 1800:
        scale = 2
        image = image.resize(
            (image.width * scale, image.height * scale),
            Image.Resampling.LANCZOS,
        )
    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(1.45)

    data = pytesseract.image_to_data(
        gray,
        lang="ara+eng",
        config="--oem 1 --psm 6",
        output_type=Output.DICT,
    )
    groups = defaultdict(list)
    total = len(data.get("text", []))
    for i in range(total):
        token = normalize_ocr(data["text"][i])
        if not token:
            continue
        try:
            conf = float(str(data.get("conf", ["-1"] * total)[i]))
        except Exception:
            conf = -1
        if conf < 8:
            continue
        key = (
            data.get("block_num", [0] * total)[i],
            data.get("par_num", [0] * total)[i],
            data.get("line_num", [0] * total)[i],
        )
        top = int(data["top"][i])
        height = int(data["height"][i])
        left = int(data["left"][i])
        groups[key].append((top + height / 2.0, left, token))

    lines = []
    for words in groups.values():
        y = sum(item[0] for item in words) / len(words)
        text = " ".join(item[2] for item in sorted(words, key=lambda x: x[1]))
        lines.append((y, normalize_ocr(text)))
    lines.sort(key=lambda x: x[0])

    date_marks = []
    for y, text in lines:
        day = radar_day_from_ocr_line(text)
        if day:
            date_marks.append((y, day))
            continue
        # Fallback for OCR such as: "2026 - أغسطس - 22 ...".
        v = text.translate(ARABIC_DIGITS)
        m = re.search(r"2026[^0-9]{0,30}(1[8-9]|2[0-9]|3[0-1])", v)
        if m and ("اغسطس" in _arabic_loose(v) or "أغسطس" in v):
            try:
                date_marks.append((y, date(2026, 8, int(m.group(1)))))
            except ValueError:
                pass

    def day_for_y(y):
        previous = [(dy, d) for dy, d in date_marks if dy < y]
        if previous:
            return max(previous, key=lambda x: x[0])[1]
        return fallback_day

    rows = []
    used_y = []
    for y, line_text in lines:
        row_day = day_for_y(y)
        if not row_day:
            continue
        # Fixture rows have a dash. Exclude date/header/separator lines.
        if not re.search(r"[-–—]", line_text):
            continue
        if "Twitter" in line_text or "2026" in line_text:
            continue
        if any(word in line_text for word in ("القنوات", "المعلقين", "تنبيه", "الواتساب", "تيليجرام")):
            continue
        if any(abs(y - old) < 24 for old in used_y):
            continue

        pad = max(42, int(gray.height * 0.014))
        top = max(0, int(y - pad))
        bottom = min(gray.height, int(y + pad))
        middle = gray.crop((int(gray.width * 0.32), top, int(gray.width * 0.65), bottom))
        right = gray.crop((int(gray.width * 0.73), top, gray.width, bottom))
        right_wide = gray.crop((int(gray.width * 0.55), top, gray.width, bottom))

        middle_outputs = []
        right_outputs = []

        # CHANNEL SAFETY: read ONLY the visual channel column.
        # Never infer a channel number from the full row because times, dates,
        # commentator text, or neighbouring cells can contain 1/2/3 and create
        # a false Thmanyah channel. Tesseract's own docs recommend OCRing the
        # small target region with a matching PSM for table-like layouts.
        for psm in (6, 7, 11, 13):
            try:
                mt = normalize_ocr(pytesseract.image_to_string(
                    middle, lang="ara+eng", config=f"--oem 1 --psm {psm}"
                ))
                if mt:
                    middle_outputs.append(mt)
            except Exception as exc:
                warn(f"matches_today2 middle-column OCR psm={psm} failed: {exc}")

        # Always OCR the right fixture/time column separately. Use several
        # very small vertical offsets because Tesseract can drop one team when
        # the crop boundary lands on Arabic ascenders/descenders.
        fast_title = None
        for offset in (-4, 0, 4):
            rtop = max(0, int(y + offset - pad))
            rbottom = min(gray.height, int(y + offset + pad))
            shifted_right = gray.crop((int(gray.width * 0.55), rtop, gray.width, rbottom))
            for psm in (6, 7, 11, 13):
                try:
                    rt = normalize_ocr(pytesseract.image_to_string(
                        shifted_right, lang="ara+eng", config=f"--oem 1 --psm {psm}"
                    ))
                    if rt:
                        right_outputs.append(rt)
                except Exception as exc:
                    warn(f"matches_today2 right-column OCR psm={psm} failed: {exc}")

        middle_text = " | ".join(middle_outputs)
        right_text = " | ".join(right_outputs + [line_text])

        # Require explicit Thmanyah+number evidence from the middle column itself.
        # Do not append line_text here: that was the source of cross-column false
        # positives (e.g. reading a 1 from another cell as Thmanyah 1).
        channel_votes = []
        for mt in middle_outputs:
            ch = _extract_channel_from_row_text(mt)
            if ch not in CHANNELS:
                ch = _channel_from_middle_column(mt)
            if ch in CHANNELS:
                channel_votes.append(ch)
        if not channel_votes:
            continue
        # Accept only a unique majority. A tie means OCR is unsafe, so skip it.
        counts = {n: channel_votes.count(n) for n in CHANNELS}
        best_count = max(counts.values())
        winners = [n for n, c in counts.items() if c == best_count and c > 0]
        if len(winners) != 1:
            continue
        channel = winners[0]

        fixture_candidates = []
        for candidate_text in right_outputs:
            match = re.search(
                r"([\u0600-\u06ff][\u0600-\u06ff\s]{1,24})\s*[-–—]\s*"
                r"([\u0600-\u06ff][\u0600-\u06ff\s]{1,24})",
                normalize_ocr(candidate_text),
            )
            if not match:
                continue
            left, ls = _repair_ocr_team(match.group(1).strip())
            right_team, rs = _repair_ocr_team(match.group(2).strip())
            if left and right_team:
                fixture_candidates.append((ls + rs, f"{left} - {right_team}"))
        if not fixture_candidates:
            fallback_title = _fixture_from_right_column(line_text)
            if fallback_title:
                parts = fallback_title.split(" - ", 1)
                if len(parts) == 2:
                    a, sa = _repair_ocr_team(parts[0])
                    b, sb = _repair_ocr_team(parts[1])
                    if a and b:
                        fixture_candidates.append((sa + sb - 0.15, f"{a} - {b}"))

        # Some Telegram rows are split by Tesseract across multiple OCR passes:
        # one pass reads team A and another reads team B. When no single pass
        # contains both sides of the dash, recover the two high-confidence team
        # names from all right-column OCR outputs instead of discarding the row.
        if not fixture_candidates:
            team_hits = {}
            combined_team_text = " | ".join(right_outputs + [line_text])
            for token in re.findall(r"[\u0600-\u06ff]{3,18}", combined_team_text):
                team, score = _repair_ocr_team(token)
                if team in _OCR_TEAM_LEXICON and score >= 0.68:
                    prev = team_hits.get(team, 0.0)
                    if score > prev:
                        team_hits[team] = score
            if len(team_hits) >= 2:
                ranked_teams = sorted(
                    team_hits.items(), key=lambda item: item[1], reverse=True
                )[:2]
                a, sa = ranked_teams[0]
                b, sb = ranked_teams[1]
                if a != b:
                    fixture_candidates.append((sa + sb - 0.25, f"{a} - {b}"))

        if not fixture_candidates:
            continue
        fixture_candidates.sort(key=lambda x: x[0], reverse=True)
        title = fixture_candidates[0][1]

        kickoff = _kickoff_from_right_column(" | ".join(right_outputs))
        if not kickoff:
            kickoff = _kickoff_from_time_crop(gray, y)
        if not kickoff:
            kickoff = _kickoff_from_right_column(line_text)
        if not kickoff:
            continue
        hour, minute = kickoff
        start = datetime(
            row_day.year, row_day.month, row_day.day,
            hour, minute, tzinfo=TZ,
        )
        rows.append({
            "date": row_day,
            "channel": channel,
            "title": title,
            "start": start,
            "context": normalize_ocr(right_text + " | " + middle_text),
        })
        used_y.append(y)

    # Keep unique date/time/title/channel rows only.
    unique = []
    seen = set()
    for row in rows:
        sig = (row["start"], norm(row["title"]).casefold(), row["channel"])
        if sig in seen:
            continue
        seen.add(sig)
        unique.append(row)
    return unique

def ocr_structured_table_url(url, fallback_day=None):
    try:
        response = requests.get(url, headers=HEADERS, timeout=35)
        response.raise_for_status()
        image = Image.open(__import__("io").BytesIO(response.content)).convert("RGB")
        return _structured_rows_from_image(image, fallback_day=fallback_day)
    except Exception as exc:
        warn(f"matches_today2 structured table OCR failed: {exc}")
        return []


def collect_radarkora_confirmations(daily):
    confirmations = []
    direct_events = []
    max_pages = 12
    before_id = None
    seen_message_ids = set()

    window_floor = (NOW - timedelta(days=KEEP_DAYS_BACK + 1)).date()
    window_ceiling = (NOW + timedelta(days=KEEP_DAYS_FORWARD + 1)).date()

    for page_index in range(max_pages):
        page_url = (
            RADARKORA_TELEGRAM
            if before_id is None
            else f"{RADARKORA_TELEGRAM}?before={before_id}"
        )

        try:
            soup = BeautifulSoup(fetch(page_url), "html.parser")
        except Exception as exc:
            warn(f"RadarKora Telegram page {page_index + 1} fetch failed: {exc}")
            break

        posts = soup.select(".tgme_widget_message")
        if not posts:
            break

        page_ids = []
        page_days = []

        for post in posts:
            data_post = post.get("data-post", "")
            id_match = re.search(r"/(\d+)$", data_post)

            if id_match:
                message_id = int(id_match.group(1))
                page_ids.append(message_id)
                if message_id in seen_message_ids:
                    continue
                seen_message_ids.add(message_id)

            caption_node = post.select_one(
                ".tgme_widget_message_text, .tgme_widget_message_caption"
            )
            caption = (
                caption_node.get_text(" ", strip=True)
                if caption_node else ""
            )
            caption_norm = normalize_ocr(caption)

            # matches_today2 is a schedule/broadcaster channel. Accept the common
            # schedule wording and also image posts whose captions mention matches.
            if caption_norm and not any(
                marker in caption_norm
                for marker in (
                    "مباريات_اليوم",
                    "مباريات اليوم",
                    "المباريات",
                    "جدول المباريات",
                    "مباريات",
                )
            ):
                continue

            post_day = radar_post_day(caption_norm)
            if post_day:
                page_days.append(post_day)

            # IMPORTANT: matches_today2 also publishes league-specific table
            # images (for example a Roshn League round) whose caption has NO
            # Gregorian date. The dates are printed inside the image itself.
            # Older versions skipped those posts before OCR and therefore
            # always returned zero numbered confirmations.
            image_url = telegram_image_url(post)
            if not image_url:
                continue

            # If the caption has an explicit day outside our window, skip it.
            # If there is no caption day, OCR the image and let the table
            # headings (e.g. 20 - أغسطس - 2026) determine each row's date.
            if post_day and not (window_floor <= post_day <= window_ceiling):
                continue

            # Structured image OCR is CHANNEL evidence only.
            # It must NEVER create a standalone EPG event or replace kickoff time.
            # Goal/Kooora owns date/time/title; the image only confirms the numbered
            # Thmanyah feed after a same-day two-team fixture match.
            structured_rows = ocr_structured_table_url(
                image_url,
                fallback_day=post_day,
            )
            if structured_rows:
                log(f"matches_today2 STRUCTURED TABLE: {len(structured_rows)} candidate numbered rows")
            for srow in structured_rows:
                candidate_events = [
                    event for event in daily
                    if event["start"].date() == srow["date"]
                ]
                scored = []
                for event in candidate_events:
                    score = fixture_match_score(event["title"], srow["title"])
                    if score > 0:
                        scored.append((score, event))
                scored.sort(key=lambda item: item[0], reverse=True)
                if not scored:
                    log(
                        "STRUCTURED OCR UNMATCHED | "
                        f"{srow['date']} | {srow['title']} | THMANYAH {srow['channel']}"
                    )
                    continue
                best_score, best = scored[0]
                second_score = scored[1][0] if len(scored) > 1 else 0
                if second_score and abs(best_score - second_score) < 1e-9:
                    log(
                        "STRUCTURED OCR AMBIGUOUS | "
                        f"{srow['date']} | {srow['title']} | THMANYAH {srow['channel']}"
                    )
                    continue
                confirmations.append({
                    "channel": srow["channel"],
                    "date": best["start"].date(),
                    "title": best["title"],
                    "source": "matches_today2 structured image OCR CHANNEL-ONLY",
                    "confirmed": True,
                })
                log(
                    "STRUCTURED OCR CHANNEL CONFIRMATION | "
                    f"{best['start']:%Y-%m-%d %H:%M} | "
                    f"{best['title']} | THMANYAH {srow['channel']} | SOURCE KICKOFF KEPT"
                )

            # Run BOTH legacy OCR strategies too, as a backup.
            # The layout-aware pass is useful for difficult images, but it can
            # return a non-empty *partial* result. Older versions treated that
            # as success and skipped the full-image OCR, which is exactly why
            # clear rows such as "الفيحاء - الهلال | ثمانية 2" could be lost.
            layout_rows = ocr_table_rows_url(
                image_url,
                fallback_day=post_day,
            )

            full_rows = []
            ocr_text = ocr_image_url(image_url)
            if ocr_text:
                full_rows = radar_rows_from_ocr(
                    ocr_text,
                    fallback_day=post_day,
                )

            rows = []
            row_seen = set()
            for row_day, channel, context in layout_rows + full_rows:
                # Deduplicate by date/channel plus normalized row text. Keep
                # both strategies available so one can recover what the other
                # misses.
                normalized_context = normalize_ocr(context)
                key = (row_day, channel, normalized_context)
                if key in row_seen:
                    continue
                row_seen.add(key)
                rows.append((row_day, channel, context))

            log(
                "matches_today2 OCR merge | "
                f"layout={len(layout_rows)} full={len(full_rows)} "
                f"merged={len(rows)}"
            )

            # Dates discovered inside the image also help pagination stop at
            # the correct point even when the Telegram caption had no date.
            for row_day, _, _ in rows:
                if row_day:
                    page_days.append(row_day)

            log(
                f"matches_today2 image "
                f"{post_day.isoformat() if post_day else '[date from image]'}: "
                f"{len(rows)} numbered Thmanyah table rows found"
            )

            for row_day, channel, context in rows:
                # The Telegram image itself is authoritative for TEAM + CHANNEL.
                # Some matches_today2 tables OCR perfectly for the fixture row but
                # Tesseract misses the date heading. Older versions discarded those
                # rows here, which is why logs could show 4 numbered rows found and
                # still end with 0 confirmations.
                #
                # If the image date is known, restrict matching to that day. If the
                # date heading was not OCR'd, match the row against all Goal/Kooora
                # fixtures already collected inside our normal EPG window and infer
                # the date from the uniquely matched fixture. fixture_match_score()
                # returns >0 only when BOTH teams have meaningful evidence in the OCR
                # row, so this still requires team+channel agreement from the image.
                if row_day and not (window_floor <= row_day <= window_ceiling):
                    continue

                if row_day:
                    candidate_events = [
                        event for event in daily
                        if event["start"].date() == row_day
                    ]
                else:
                    candidate_events = [
                        event for event in daily
                        if window_floor <= event["start"].date() <= window_ceiling
                    ]

                scored = []

                for event in candidate_events:
                    score = fixture_match_score(event["title"], context)
                    if score > 0:
                        scored.append((score, event))

                scored.sort(key=lambda item: item[0], reverse=True)
                if not scored:
                    log(
                        "OCR ROW UNMATCHED | "
                        f"{row_day.isoformat() if row_day else '[DATE INFER]'} | "
                        f"THMANYAH {channel} | {normalize_ocr(context)[:180]}"
                    )
                    continue

                # OCR-AUTHORITATIVE RULE:
                # Once the image row itself contains a valid Thmanyah channel
                # number and both teams can be linked to a same-day Goal/Kooora
                # fixture, trust the image.  Do NOT discard it because of the old
                # arbitrary >=1.0 score or 0.25 winner-gap thresholds.
                # fixture_match_score already returns 0 unless BOTH teams have
                # meaningful token/fuzzy evidence in the OCR row.
                best_score, best = scored[0]
                second_score = scored[1][0] if len(scored) > 1 else 0

                # Only an exact top-score tie is unsafe: the OCR row does not
                # uniquely identify one fixture. Everything else is accepted.
                if second_score and abs(best_score - second_score) < 1e-9:
                    log(
                        "OCR ROW AMBIGUOUS TIE | "
                        f"{row_day.isoformat() if row_day else '[DATE INFER]'} | "
                        f"THMANYAH {channel} | "
                        f"best={best_score:.3f} | {normalize_ocr(context)[:180]}"
                    )
                    continue

                confirmations.append({
                    "channel": channel,
                    "date": best["start"].date(),
                    "title": best["title"],
                    "source": "matches_today2 Telegram OCR AUTHORITATIVE",
                    "confirmed": True,
                })

                log(
                    "OCR AUTHORITATIVE CONFIRMATION | "
                    f"{best['start']:%Y-%m-%d %H:%M} | "
                    f"{best['title']} | THMANYAH {channel}"
                    + (" | DATE INFERRED FROM FIXTURE" if row_day is None else "")
                )

        if not page_ids:
            break

        next_before = min(page_ids)
        if before_id is not None and next_before >= before_id:
            break

        before_id = next_before

        if page_days and max(page_days) < window_floor:
            break

    unique = []
    seen = set()
    for item in confirmations:
        signature = fixture_signature(item["title"])
        key = (
            item.get("date"),
            tuple(sorted(signature)) if signature else norm(item["title"]).casefold(),
            item.get("channel"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    direct_events = dedupe(direct_events)
    log(f"matches_today2 numbered confirmations detected: {len(unique)}")
    log(f"matches_today2 direct structured EPG events detected: {len(direct_events)}")
    return unique, direct_events

def confirmation_map(confirmations):
    result = defaultdict(list)
    for event in confirmations:
        signature = fixture_signature(event["title"])
        if signature:
            result[signature].append(event)
    return result


def apply_confirmations(daily, confirmations):
    """
    Attach only a verified channel number from 365Scores to an existing
    Goal/Kooora fixture. Never import or replace kickoff time from 365Scores.
    A confirmation must match the same normalized fixture and same calendar day.
    """
    by_signature = confirmation_map(confirmations)
    result = []

    for event in daily:
        current = dict(event)

        if current.get("channel") in CHANNELS:
            current["confirmed"] = True
            result.append(current)
            continue

        signature = fixture_signature(current["title"])
        candidates = by_signature.get(signature, []) if signature else []
        candidates = [
            candidate
            for candidate in candidates
            if candidate.get("date") == current["start"].date()
        ]

        channels = sorted({
            int(candidate["channel"])
            for candidate in candidates
            if candidate.get("channel") in CHANNELS
        })

        if len(channels) == 1:
            original_start = current["start"]
            current["channel"] = channels[0]
            current["confirmed"] = True
            current["source"] = (
                f"{current['source']} + verified channel-only confirmation"
            )

            # Hard safety invariant: channel confirmation may never alter time.
            if current["start"] != original_start:
                raise RuntimeError("Channel confirmation altered kickoff time")

            log(
                "CHANNEL CONFIRMATION | "
                f"{current['start']:%Y-%m-%d %H:%M} | "
                f"{current['title']} | THMANYAH {current['channel']} | "
                "kickoff kept from Goal/Kooora"
            )

        result.append(current)

    # IMPORTANT: do NOT append standalone 365Scores records here.
    # They carry no trusted kickoff time and exist only as channel metadata.
    return dedupe([
        event for event in result
        if in_window(event["start"])
    ])

def assign_unconfirmed(events):
    """
    Never guess Thmanyah 1/2/3.
    Confirmed channel numbers stay on 1/2/3.
    Unknown channel numbers stay on the Guide channel.
    """
    output = []

    for event in dedupe(events):
        item = dict(event)

        if item.get("channel") in CHANNELS:
            item["confirmed"] = True
            output.append(item)
            continue

        item["channel"] = None
        item["confirmed"] = False
        item["source"] = f"{item['source']} + channel unknown"
        output.append(item)

        log(
            "THMANYAH GUIDE | "
            f"{item['start']:%Y-%m-%d %H:%M} | {item['title']}"
        )

    return dedupe(output)

def read_existing():
    return []

def merge_existing(existing, fresh):
    return dedupe([
        event for event in fresh
        if in_window(event["start"])
    ])

def write_xml(events):
    tv = ET.Element(
        "tv",
        {"generator-info-name": "Thmanyah Sports EPG FINAL v15"},
    )

    for number in CHANNELS:
        channel_id = f"Thmanyah{number}.sa"
        channel = ET.SubElement(tv, "channel", {"id": channel_id})
        ET.SubElement(channel, "display-name", {"lang": "en"}).text = f"Thmanyah {number}"
        ET.SubElement(channel, "display-name", {"lang": "ar"}).text = f"ثمانية {number}"
        ET.SubElement(channel, "icon", {"src": THMANYAH_LOGO})

    guide = ET.SubElement(tv, "channel", {"id": GUIDE_CHANNEL_ID})
    ET.SubElement(guide, "display-name", {"lang": "en"}).text = "Thmanyah | Guide"
    ET.SubElement(guide, "display-name", {"lang": "ar"}).text = "ثمانية | Guide"
    ET.SubElement(guide, "icon", {"src": THMANYAH_LOGO})

    events = dedupe(events)

    by_day = defaultdict(list)
    for event in events:
        by_day[event["start"].date()].append(event)

    real_by_id = {
        "Thmanyah1.sa": [],
        "Thmanyah2.sa": [],
        "Thmanyah3.sa": [],
        GUIDE_CHANNEL_ID: [],
    }

    def time_text(event):
        # Keep the source time/offset. TiviMate converts XMLTV time to the device timezone.
        return f"وقت المصدر {event["start"]:%H:%M}"

    def day_summary(day):
        day_events = sorted(by_day.get(day, []), key=lambda x: (x["start"], x["title"]))
        if not day_events:
            return "لا توجد مباريات معلنة على شبكة ثمانية لهذا اليوم."

        lines = []
        for event in day_events:
            channel = event.get("channel")
            channel_text = f"ثمانية {channel}" if channel in CHANNELS else "رقم القناة لم يعلن"
            lines.append(f"{time_text(event)} | {event['title']} | {channel_text}")
        return "\n".join(lines)

    for event in events:
        stop = event["start"] + timedelta(hours=3)
        channel = event.get("channel")

        # Always show every match on Guide.
        real_by_id[GUIDE_CHANNEL_ID].append((event["start"], stop))
        gp = ET.SubElement(
            tv,
            "programme",
            {
                "start": event["start"].strftime("%Y%m%d%H%M%S %z"),
                "stop": stop.strftime("%Y%m%d%H%M%S %z"),
                "channel": GUIDE_CHANNEL_ID,
            },
        )
        ET.SubElement(gp, "title", {"lang": "ar"}).text = event["title"]
        ET.SubElement(gp, "category", {"lang": "en"}).text = "Sports"
        channel_text = f"القناة: ثمانية {channel}." if channel in CHANNELS else "رقم القناة لم يعلن بعد."
        ET.SubElement(gp, "desc", {"lang": "ar"}).text = (
            f"{channel_text} {time_text(event)}.\n\n"
            f"مباريات اليوم:\n{day_summary(event['start'].date())}"
        )

        # Only confirmed channel assignments go to 1/2/3.
        if channel in CHANNELS:
            channel_id = f"Thmanyah{channel}.sa"
            real_by_id[channel_id].append((event["start"], stop))
            p = ET.SubElement(
                tv,
                "programme",
                {
                    "start": event["start"].strftime("%Y%m%d%H%M%S %z"),
                    "stop": stop.strftime("%Y%m%d%H%M%S %z"),
                    "channel": channel_id,
                },
            )
            ET.SubElement(p, "title", {"lang": "ar"}).text = event["title"]
            ET.SubElement(p, "category", {"lang": "en"}).text = "Sports"
            ET.SubElement(p, "desc", {"lang": "ar"}).text = (
                f"القناة: ثمانية {channel}. {time_text(event)}."
            )

    window_start = NOW.astimezone(TZ).replace(
        hour=0, minute=0, second=0, microsecond=0
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

            if channel_id == GUIDE_CHANNEL_ID:
                ET.SubElement(p, "title", {"lang": "ar"}).text = "مباريات ثمانية اليوم"
                ET.SubElement(p, "category", {"lang": "en"}).text = "Sports"
                ET.SubElement(p, "desc", {"lang": "ar"}).text = day_summary(cursor.date())
            else:
                ET.SubElement(p, "title", {"lang": "ar"}).text = "لا توجد مباراة حالياً"
                ET.SubElement(p, "category", {"lang": "en"}).text = "Sports"
                ET.SubElement(p, "desc", {"lang": "ar"}).text = "لا توجد مباراة معلنة على هذه القناة حالياً."

            cursor = stop

    for channel_id, intervals in real_by_id.items():
        clean_intervals = []

        for s, e in sorted(intervals):
            s = max(s, window_start)
            e = min(e, window_end)
            if e > s:
                clean_intervals.append((s, e))

        merged_intervals = []
        for s, e in clean_intervals:
            if not merged_intervals or s > merged_intervals[-1][1]:
                merged_intervals.append([s, e])
            else:
                merged_intervals[-1][1] = max(merged_intervals[-1][1], e)

        cursor = window_start
        for s, e in merged_intervals:
            if s > cursor:
                add_hourly_filler(channel_id, cursor, s)
            cursor = max(cursor, e)

        if cursor < window_end:
            add_hourly_filler(channel_id, cursor, window_end)

    ET.indent(tv, space="  ")
    ET.ElementTree(tv).write(OUT, encoding="utf-8", xml_declaration=True)

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
    required = {channel_id: False for channel_id in expected_ids}

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
            for key, ok in sorted(required.items())
        )
    )

    missing = [key for key, ok in required.items() if not ok]
    if missing:
        raise RuntimeError(
            "Thmanyah XML validation failed; missing current coverage: "
            + ", ".join(missing)
        )

    log(
        "THMANYAH GUIDE DAYS | "
        + ", ".join(
            f"{day}:{len(items)}"
            for day, items in sorted(by_day.items())
        )
    )



def dedupe_fixture_day(events):
    """Keep one event per calendar-day fixture, regardless of conflicting times."""
    out = []
    index = {}
    for event in sorted(events, key=lambda e: e["start"]):
        sig = fixture_signature(event.get("title", ""))
        fixture_key = tuple(sorted(sig)) if sig else norm(event.get("title", "")).casefold()
        key = (event["start"].date(), fixture_key)
        if key not in index:
            index[key] = len(out)
            out.append(dict(event))
            continue
        old = out[index[key]]
        # Prefer a confirmed numbered-channel event. Otherwise prefer the first
        # Goal/Kooora fixture already present; never create a second kickoff.
        if event.get("confirmed") and event.get("channel") in CHANNELS and not (old.get("confirmed") and old.get("channel") in CHANNELS):
            old["channel"] = event.get("channel")
            old["confirmed"] = True
            old["source"] = event.get("source", old.get("source"))
    return out

def main():
    log("THMANYAH FINAL FIXED | OCR CHANNEL-ONLY | GOAL/KOOORA KICKOFF | NO DIRECT OCR EVENTS | FIXTURE-DAY DEDUPE")
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
    confirmations_telegram, _ignored_direct_events = collect_radarkora_confirmations(daily)

    # SAFETY: Telegram/OCR never supplies a standalone kickoff. Keep the fixture
    # pool exclusively from Goal/Kooora so one match cannot appear twice with two
    # OCR-derived times.

    # Confirmation records intentionally contain date + fixture + channel only.
    # Kickoff always remains the Goal/Kooora time.
    confirmations = confirmations_365 + confirmations_telegram

    log(
        "Thmanyah numbered confirmations total: "
        f"{len(confirmations)} "
        f"(365Scores={len(confirmations_365)}, "
        f"matches_today2 OCR={len(confirmations_telegram)})"
    )

    resolved = apply_confirmations(daily, confirmations)
    resolved = dedupe_fixture_day(resolved)
    fresh = assign_unconfirmed(resolved)
    fresh = dedupe_fixture_day(fresh)

    fresh = [
        event
        for event in fresh
        if in_window(event["start"])
    ]

    log(f"Thmanyah newly resolved programmes: {len(fresh)}")

    for event in fresh:
        if event.get("channel") in CHANNELS:
            log(
                f"  THMANYAH {event['channel']} [CONFIRMED] | "
                f"{event['start']:%Y-%m-%d %H:%M} | "
                f"{event['title']}"
            )
        else:
            log(
                f"  THMANYAH GUIDE [CHANNEL UNKNOWN] | "
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
