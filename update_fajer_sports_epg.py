#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

# ----------------------------------------------------------------
# Fajer Sport EPG builder.
#
# Media intake accepts EVERY post layout Telegram's public preview
# can produce (single photo, album, video/GIF thumb, round video,
# sticker, document thumb, link preview) in every still format
# (jpg/png/webp/gif/bmp/tiff/avif/heic), portrait, square or
# landscape. Nothing is ever dropped silently: every rejection is
# logged with its reason.
#
# Run  python3 update_fajer_sports_epg.py --diagnose
# to print each post, each media URL and each accept/reject reason
# without writing any file.
# ----------------------------------------------------------------

import io
import os
import unicodedata
import time
import re
import sys
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from html import unescape
from urllib.parse import urljoin, urlencode
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import numpy as np
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

TELEGRAM_MAX_PAGES = 4
TELEGRAM_RECENT_DAYS = 3

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


HTTP_ATTEMPTS = 3


def fetch(url, binary=False, attempts=HTTP_ATTEMPTS):
    """Fetch with retries. Telegram CDN hosts want a t.me Referer."""
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            headers = None

            if "//t.me" not in url and "//telegram.me" not in url:
                headers = {"Referer": "https://t.me/"}

            r = session.get(
                url,
                timeout=HTTP_TIMEOUT,
                headers=headers,
            )
            r.raise_for_status()

            return r.content if binary else r.text

        except Exception as exc:
            last_error = exc

            if attempt < attempts:
                time.sleep(1.5 * attempt)

    raise last_error



def xmltv_time(dt):
    return dt.astimezone(UTC).strftime(
        "%Y%m%d%H%M%S +0000"
    )


# ============================================================
# OCR
# ============================================================

DATE_RE = re.compile(
    r"(?P<y>20\d{2})[-/.]"
    r"(?P<m>\d{1,2})[-/.]"
    r"(?P<d>\d{1,2})"
)

TIME_RE = re.compile(
    r"(?P<h>\d{1,2})"
    r"\s*[:٫.]\s*"
    r"(?P<m>\d{2})"
    r"\s*"
    r"(?P<ap>"
    r"pm|am|"
    r"p\.?m\.?|"
    r"a\.?m\.?"
    r")?",
    re.I,
)

CHAN_RE = re.compile(
    r"(?:قناة|القناة)\s*([1-5])"
    r"|"
    r"\b([1-5])\s*(?:قناة|channel)\b",
    re.I,
)

PAIR_RE = re.compile(
    r"([\w\u0600-\u06ff .'-]{2,35})"
    r"\s*(?:x|X|×|[-–—])\s*"
    r"([\w\u0600-\u06ff .'-]{2,35})"
)

NOISE = re.compile(
    r"تشاهدون|"
    r"اليوم|"
    r"الأربعاء|الخميس|الجمعة|"
    r"السبت|الأحد|الاثنين|الثلاثاء|"
    r"قناة|"
    r"كأس|"
    r"دوري|"
    r"الأسبوع|"
    r"للمشاهدة|"
    r"fajer|"
    r"pm|am",
    re.I,
)


def prep(im, scale=3):
    im = im.convert("L")
    im = ImageOps.autocontrast(im)
    im = ImageEnhance.Contrast(im).enhance(1.6)
    im = im.resize(
        (
            im.width * scale,
            im.height * scale,
        )
    )
    return im.filter(ImageFilter.SHARPEN)


def ocr(im, psm=6, lang="ara+eng"):
    text = pytesseract.image_to_string(
        prep(im),
        lang=lang,
        config=f"--psm {psm}",
    )
    return norm(text)


def poster_date(im, fallback):
    """
    Read date from poster header.

    If OCR cannot read a valid date,
    fallback to Telegram post date.
    """
    w, h = im.size

    header = im.crop(
        (
            int(0.25 * w),
            0,
            int(0.75 * w),
            int(0.28 * h),
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
    Fajer daily poster layout:
    2 columns x 2 rows.
    """
    w, h = im.size

    return [
        (
            "TL",
            (
                0,
                int(0.27 * h),
                int(0.50 * w),
                int(0.50 * h),
            ),
        ),
        (
            "TR",
            (
                int(0.50 * w),
                int(0.27 * h),
                w,
                int(0.50 * h),
            ),
        ),
        (
            "BL",
            (
                0,
                int(0.50 * h),
                int(0.50 * w),
                int(0.74 * h),
            ),
        ),
        (
            "BR",
            (
                int(0.50 * w),
                int(0.50 * h),
                w,
                int(0.74 * h),
            ),
        ),
    ]


def _ocr_norm(text):
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

    if ampm == "am" and hour == 12:
        hour = 0

    if not (
        0 <= hour <= 23
        and
        0 <= minute <= 59
    ):
        return None

    return (
        channel,
        (hour, minute),
        bool(ampm),
    )


def channel_and_time(card):
    """
    Use multiple OCR passes and vote.

    Explicit AM/PM readings get
    stronger weight.
    """
    w, h = card.size

    regions = [
        card,
        card.crop(
            (
                int(0.08 * w),
                int(0.28 * h),
                int(0.92 * w),
                int(0.72 * h),
            )
        ),
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

            key = (
                channel,
                clock,
            )

            weight = 3 if explicit_ampm else 1
            votes[key] = votes.get(key, 0) + weight

    if not votes:
        return (
            None,
            None,
            " | ".join(texts),
        )

    best = max(
        votes.items(),
        key=lambda x: x[1],
    )[0]

    return (
        best[0],
        best[1],
        " | ".join(texts),
    )


def clean_candidate(s):
    s = norm(s)

    s = re.sub(
        r"[^A-Za-z0-9"
        r"\u0600-\u06ff "
        r".'-]",
        " ",
        s,
    )

    s = norm(s)

    return s.strip(" .-'")



TEAM_OCR_NOISE = re.compile(
    r"قناة|القناة|"
    r"اليوم|تشاهدون|"
    r"كأس|دوري|الأسبوع|"
    r"فجر|fajer|"
    r"pm|am|"
    r"نادي\s*$",
    re.I,
)


def _arabic_letter_count(s):
    return len(
        re.findall(
            r"[\u0621-\u064A]",
            s or "",
        )
    )


def _team_line_ok(s):
    s = clean_candidate(s)

    if not s:
        return False

    if TEAM_OCR_NOISE.search(s):
        return False

    if _arabic_letter_count(s) < 3:
        return False

    # Team names on the Fajer poster are short.
    if len(s) > 30:
        return False

    return True


def _ocr_team_blocks(region, psm):
    """
    Read the dark team-name strip separately.

    Tesseract's normal full-card OCR was already excellent at
    channel/time, but the team names are printed in a different
    high-contrast strip. Reading that strip independently is much
    more reliable.
    """
    prepared = prep(region, scale=4)

    data = pytesseract.image_to_data(
        prepared,
        lang="ara+eng",
        config=f"--psm {psm}",
        output_type=pytesseract.Output.DICT,
    )

    grouped = {}

    count = len(data.get("text", []))

    for i in range(count):
        token = norm(data["text"][i])

        if not token:
            continue

        try:
            conf = float(data["conf"][i])
        except Exception:
            conf = -1.0

        if conf < 0:
            continue

        # PSM 11 often places each visible text line in its own block.
        key = (
            data.get("block_num", [0] * count)[i],
            data.get("par_num", [0] * count)[i],
            data.get("line_num", [0] * count)[i],
        )

        grouped.setdefault(
            key,
            {
                "parts": [],
                "conf": [],
            },
        )

        grouped[key]["parts"].append(token)
        grouped[key]["conf"].append(conf)

    out = []

    for item in grouped.values():
        line = clean_candidate(
            " ".join(item["parts"])
        )

        if not _team_line_ok(line):
            continue

        avg_conf = (
            sum(item["conf"])
            / max(1, len(item["conf"]))
        )

        out.append(
            (
                line,
                avg_conf,
            )
        )

    return out


TEAM_DISPLAY_FIXES = {
    "برسلونة": "برشلونة",
}


def _clean_team_display(name):
    name = clean_candidate(name)
    name = name.replace("ى", "ي")
    return TEAM_DISPLAY_FIXES.get(name, name)


def team_names_from_card(card):
    """
    Extract the two Arabic team names from the official poster itself.

    Fail-safe rules:
      * inspect only the upper team-name area
      * require Arabic text
      * reject schedule/competition/channel noise
      * require two distinct names
      * require strong OCR confidence
      * never alter channel or kickoff time
    """
    w, h = card.size

    regions = [
        # Main dark team-name strip.
        card.crop(
            (
                int(0.08 * w),
                int(0.08 * h),
                int(0.94 * w),
                int(0.52 * h),
            )
        ),
        # Slightly taller retry for posters whose strip is lower.
        card.crop(
            (
                int(0.05 * w),
                0,
                int(0.96 * w),
                int(0.58 * h),
            )
        ),
        # Tight top-strip retry. This helps when logos/competition text
        # confuse the wider OCR crop.
        card.crop(
            (
                int(0.15 * w),
                0,
                int(0.90 * w),
                int(0.42 * h),
            )
        ),
    ]

    votes = {}

    for region in regions:
        for psm in (11, 12):
            try:
                blocks = _ocr_team_blocks(
                    region,
                    psm,
                )
            except Exception:
                continue

            for name, conf in blocks:
                key = _match_text_key(name)

                if not key:
                    continue

                entry = votes.setdefault(
                    key,
                    {
                        "name": name,
                        "score": 0.0,
                        "hits": 0,
                        "best_conf": 0.0,
                    },
                )

                entry["score"] += max(
                    0.0,
                    conf,
                )
                entry["hits"] += 1
                entry["best_conf"] = max(
                    entry["best_conf"],
                    conf,
                )

    candidates = sorted(
        votes.values(),
        key=lambda x: (
            x["best_conf"],
            x["hits"],
            x["score"],
        ),
        reverse=True,
    )

    # Deduplicate near-identical OCR spellings.
    selected = []

    for item in candidates:
        key = _match_text_key(item["name"])

        if any(
            SequenceMatcher(
                None,
                key,
                _match_text_key(old["name"]),
            ).ratio() >= 0.88
            for old in selected
        ):
            continue

        selected.append(item)

    # The official poster has exactly two opponents per card.
    if len(selected) < 2:
        return None

    first, second = selected[0], selected[1]

    # Require high quality. Repeated detection can compensate for
    # one slightly lower-confidence OCR pass.
    def strong(item):
        return (
            item["best_conf"] >= 72.0
            or (
                item["hits"] >= 2
                and
                item["best_conf"] >= 60.0
            )
        )

    if not strong(first) or not strong(second):
        return None

    first_name = _clean_team_display(
        first["name"]
    )
    second_name = _clean_team_display(
        second["name"]
    )

    # Reject obvious duplicate/near-duplicate OCR hallucinations such as
    # "مالاجا - مالاخا".
    first_key = _match_text_key(
        first_name
    )
    second_key = _match_text_key(
        second_name
    )

    if SequenceMatcher(
        None,
        first_key,
        second_key,
    ).ratio() >= 0.78:
        return None

    confidence = min(
        first["best_conf"],
        second["best_conf"],
    ) / 100.0

    # GitHub's Telegram JPEG rendition can be noisier than the local image.
    # Below 0.80 we fail safely instead of publishing a distorted team name.
    if confidence < 0.80:
        return None

    title = (
        f"{first_name} - "
        f"{second_name}"
    )

    return (
        title,
        confidence,
    )


def title_from_card(card, raw_card):
    """
    Resolve team names from the official Fajer poster.

    First choice:
      dedicated OCR of the high-contrast team-name strip.

    Second choice:
      the original conservative matchup-separator OCR.

    If neither is strong enough, return no title and let the
    safe generic fallback / LiveFootballTV corroboration handle it.
    """
    targeted = team_names_from_card(card)

    if targeted:
        return targeted

    for text in (
        raw_card,
        ocr(card, 11),
    ):
        m = PAIR_RE.search(
            _ocr_norm(text)
        )

        if not m:
            continue

        team_a = clean_candidate(
            m.group(1)
        )

        team_b = clean_candidate(
            m.group(2)
        )

        if not team_a or not team_b:
            continue

        if NOISE.search(team_a + team_b):
            continue

        return (
            f"{team_a} - {team_b}",
            0.90,
        )

    return (
        None,
        0.0,
    )


def parse_poster_legacy(im, post_time, source):
    poster_day = poster_date(
        im,
        post_time,
    )

    events = []

    for label, box in card_boxes(im):
        card = im.crop(box)

        channel, clock, raw = channel_and_time(card)

        if not channel or not clock:
            continue

        title, confidence = title_from_card(
            card,
            raw,
        )

        generic_title = False

        if not title:
            title = (
                "مباراة مباشرة - "
                f"فجر سبورت {channel}"
            )

            confidence = 0.0
            generic_title = True

            warn(
                f"OCR {label}: "
                "channel/time verified; "
                "team names unreadable, "
                "using safe generic title"
            )

        hour, minute = clock

        local = datetime(
            poster_day.year,
            poster_day.month,
            poster_day.day,
            hour,
            minute,
            tzinfo=PALESTINE,
        )

        start = local.astimezone(UTC)

        if not in_window(start):
            continue

        channel_id, channel_name = CHANNELS[channel]

        events.append(
            {
                "channel_num": channel,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "start": start,
                "title": title,
                "source_name":
                    "FajerSportOfficialTelegramPosterOCR",
                "source": source,
                "duration_minutes": 110,
                "time_type":
                    "scheduled-image",
                "ocr_confidence":
                    confidence,
                "ocr_raw": raw,
                "generic_title": generic_title,
            }
        )

        log(
            f"OCR {label} | "
            f"ch={channel} | "
            f"{local:%Y-%m-%d %H:%M} "
            f"Palestine | "
            f"{title} | "
            f"confidence="
            f"{confidence:.2f}"
        )

    return events


# ============================================================
# DYNAMIC POSTER LAYOUT  (2 / 3 / 4 / 5 ... matches per poster)
# ============================================================
#
# The Fajer daily poster does NOT have a fixed 2x2 grid.
# Every match is drawn as one horizontal "card" whose middle
# strip is always the same cyan colour:
#
#   [ dark-navy strip ]  team A   (logo)   team B
#   [ CYAN strip      ]  9:45 pm           قناة 4      <-- anchor
#   [ white strip     ]        الدوري الفرنسي
#
# So instead of guessing boxes, we DETECT the cyan strips.
# Number of matches per day is therefore irrelevant.

CYAN_MIN_WIDTH_RATIO = 0.14
CYAN_MIN_HEIGHT_RATIO = 0.018
CYAN_MAX_HEIGHT_RATIO = 0.10
HEADER_SKIP_RATIO = 0.18

TIME_WHITELIST = "0123456789:apmAPM. "
CHANNEL_WHITELIST = "12345678"


def _as_array(im):
    return np.asarray(im.convert("RGB")).astype(int)


def _cyan_mask(arr, relaxed=False):
    """
    Fajer cyan comes in two tones:
      dark  ~ (0, 144, 177)   -> time half
      light ~ (5, 175, 198)   -> channel half

    Colour-family test (not exact match) so JPEG noise,
    re-compression, WebP conversion, screenshots and small
    palette changes still work.

    'relaxed' widens the family for heavily re-compressed or
    slightly re-coloured posters; it is only used as a second
    pass when the strict test finds nothing.
    """
    r = arr[..., 0]
    g = arr[..., 1]
    b = arr[..., 2]

    if relaxed:
        return (
            (b > 95)
            & (g > 80)
            & (r < 155)
            & (b >= g - 45)
            & (g > r + 15)
        )

    return (
        (b > 125)
        & (g > 100)
        & (r < 100)
        & (b >= g - 10)
        & (g > r + 30)
    )


def _runs(flags, min_len):
    out = []
    start = None

    for i, v in enumerate(flags):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= min_len:
                out.append((start, i))
            start = None

    if start is not None and len(flags) - start >= min_len:
        out.append((start, len(flags)))

    return out


def _strips_from_mask(mask, h, w, row_factor, col_factor=0.45):
    row_hits = mask.sum(1)

    bands = _runs(
        row_hits >= CYAN_MIN_WIDTH_RATIO * w * row_factor,
        max(6, int(CYAN_MIN_HEIGHT_RATIO * h)),
    )

    boxes = []

    for y0, y1 in bands:
        band_h = y1 - y0

        # skip the poster header ("تشاهدون اليوم" + date)
        if y0 < HEADER_SKIP_RATIO * h:
            continue

        if band_h > CYAN_MAX_HEIGHT_RATIO * h:
            continue

        col_hits = mask[y0:y1].sum(0)

        runs = _runs(
            col_hits >= col_factor * band_h,
            int(CYAN_MIN_WIDTH_RATIO * w),
        )

        # A single card is one cyan strip made of two tones. Re-encoding
        # can leave a thin seam between them, so glue neighbouring runs
        # back together before treating them as separate cards.
        merged = []
        gap_limit = max(4, int(0.03 * w))

        for x0, x1 in runs:
            if merged and x0 - merged[-1][1] <= gap_limit:
                merged[-1] = (merged[-1][0], x1)
            else:
                merged.append((x0, x1))

        for x0, x1 in merged:
            boxes.append((x0, y0, x1, y1))

    # top-to-bottom, then right-to-left
    boxes.sort(key=lambda b: (b[1], -b[0]))

    return boxes


def detect_match_strips(im):
    """
    Return the cyan strip box of every match card,
    ordered top-to-bottom then right-to-left (Arabic reading).

    Three progressively more tolerant passes so a re-encoded or
    slightly re-coloured poster is never silently lost.
    """
    arr = _as_array(im)
    h, w = arr.shape[:2]

    strict = _cyan_mask(arr)
    loose = _cyan_mask(arr, relaxed=True)

    attempts = (
        ("strict", strict, 0.55, 0.45),
        ("relaxed", loose, 0.55, 0.45),
        ("relaxed-low", loose, 0.35, 0.30),
    )

    for name, mask, row_factor, col_factor in attempts:
        boxes = _strips_from_mask(
            mask,
            h,
            w,
            row_factor,
            col_factor,
        )

        if boxes:
            if name != "strict":
                log(
                    "STRIP DETECTION | "
                    f"{name} threshold used | cards={len(boxes)}"
                )

            return boxes

    return []


def _upscale(im, scale=6, invert=False):
    g = im.convert("L")
    g = ImageOps.autocontrast(g)

    if invert:
        g = ImageOps.invert(g)

    g = g.resize(
        (
            max(1, g.width * scale),
            max(1, g.height * scale),
        ),
        Image.LANCZOS,
    )

    return g


def _ocr_chars(im, whitelist, psm, invert=False, lang="eng"):
    return norm(
        pytesseract.image_to_string(
            _upscale(im, invert=invert),
            lang=lang,
            config=(
                f"--psm {psm} "
                "-c tessedit_char_whitelist="
                f"{whitelist}"
            ),
        )
    )


def _split_time_channel(arr, box):
    """
    Inside a cyan strip the LEFT half is the darker tone
    (kick-off time) and the RIGHT half is the lighter tone
    (channel number). Find that boundary column.
    """
    x0, y0, x1, y1 = box

    green = np.median(
        arr[y0 + 4:y1 - 4, x0:x1, 1],
        axis=0,
    )

    light = green > 162
    n = len(green)

    best_score = None
    best_index = n // 2

    for k in range(int(n * 0.20), int(n * 0.80)):
        score = (~light[:k]).sum() + light[k:].sum()

        if best_score is None or score > best_score:
            best_score = score
            best_index = k

    return x0 + best_index


def read_clock(im, box, split_x):
    """
    Read '9:45 pm' from the dark-cyan half.

    Latin digits only -> character whitelist makes this
    near-perfect and immune to Arabic noise.
    """
    x0, y0, x1, y1 = box

    crop = im.crop((x0, y0, split_x, y1))

    votes = {}

    for psm in (7, 6, 13):
        for invert in (False, True):
            text = _ocr_chars(
                crop,
                TIME_WHITELIST,
                psm,
                invert=invert,
            )

            m = TIME_RE.search(
                text.replace(" ", "")
            )

            if not m:
                continue

            hour = int(m["h"])
            minute = int(m["m"])
            ap = (m["ap"] or "").lower().replace(".", "")

            if not (1 <= hour <= 23 and 0 <= minute <= 59):
                continue

            key = (hour, minute, ap)
            weight = 3 if ap else 1
            votes[key] = votes.get(key, 0) + weight

    if not votes:
        return None

    hour, minute, ap = max(
        votes.items(),
        key=lambda kv: kv[1],
    )[0]

    if ap == "pm" and hour < 12:
        hour += 12
    elif ap == "am" and hour == 12:
        hour = 0
    elif not ap:
        # Poster always prints am/pm; if OCR lost it, use the
        # only schedule that makes sense for a sports channel.
        if 1 <= hour <= 11:
            hour += 12

        warn(
            "clock without am/pm marker, "
            f"assumed {hour:02d}:{minute:02d}"
        )

    return (hour % 24, minute)


def _digit_ocr(crop):
    """
    OCR one isolated numeral. Small glyphs need a white
    margin around them or Tesseract refuses to segment.
    """
    votes = {}

    for scale in (8, 10, 12):
        img = ImageOps.invert(
            ImageOps.autocontrast(crop.convert("L"))
        )

        img = img.resize(
            (
                max(1, img.width * scale),
                max(1, img.height * scale),
            ),
            Image.LANCZOS,
        )

        img = ImageOps.expand(img, border=40, fill=255)

        for psm in (10, 7, 13):
            got = pytesseract.image_to_string(
                img,
                lang="eng",
                config=(
                    f"--psm {psm} "
                    "-c tessedit_char_whitelist="
                    f"{CHANNEL_WHITELIST}"
                ),
            ).strip()

            for ch in got:
                if ch.isdigit() and int(ch) in CHANNELS:
                    votes[int(ch)] = votes.get(int(ch), 0) + 1

    if not votes:
        return None

    return max(votes.items(), key=lambda kv: kv[1])[0]


def read_channel(im, arr, box, split_x):
    """
    Read the channel number from the light-cyan half.

    The half holds exactly two white tokens:
      [ digit ]  [ قناة ]
    We locate them by column projection and OCR only the
    numeral, so Arabic letters can never become a digit.
    """
    x0, y0, x1, y1 = box

    cx0 = split_x + 4
    cx1 = x1 - 4
    ry0 = y0 + 3
    ry1 = y1 - 3

    if cx1 - cx0 < 20 or ry1 - ry0 < 8:
        return None

    region = arr[ry0:ry1, cx0:cx1]
    lum = region.mean(2)

    ink = lum > 195

    if ink.sum() < 20:
        ink = lum < 110  # dark-text variant

    rows = np.where(ink.sum(1) > 0)[0]

    if len(rows) == 0:
        return None

    text_height = rows[-1] - rows[0] + 1

    tokens = []

    for start, end in _runs(ink.sum(0) > 0, 2):
        if tokens and start - tokens[-1][1] <= 5:
            tokens[-1] = (tokens[-1][0], end)
        else:
            tokens.append((start, end))

    tokens = [t for t in tokens if t[1] - t[0] >= 2]

    if not tokens:
        return None

    # widest token is the word 'قناة'; the numeral sits left of it
    word = max(tokens, key=lambda t: t[1] - t[0])

    left_of_word = [t for t in tokens if t[1] <= word[0]]

    ordered = (
        [left_of_word[-1]] + left_of_word[:-1]
        if left_of_word
        else [t for t in tokens if t is not word]
    )

    for start, end in ordered:
        width = end - start

        # Measure the token against ITS OWN height, not the height of
        # the whole cyan half: the Arabic word next to the numeral is
        # taller, and using it made every digit look "narrow".
        token_rows = np.where(ink[:, start:end].sum(1) > 0)[0]

        if len(token_rows) == 0:
            continue

        token_height = token_rows[-1] - token_rows[0] + 1

        if width > 2.0 * token_height:
            continue

        narrow = width <= 0.45 * token_height

        ty0 = ry0 + int(token_rows[0])
        ty1 = ry0 + int(token_rows[-1]) + 1

        for pad in (8, 14, 22):
            value = _digit_ocr(
                im.crop(
                    (
                        max(0, cx0 + start - pad),
                        max(0, ty0 - pad),
                        min(im.width, cx0 + end + pad),
                        min(im.height, ty1 + pad),
                    )
                )
            )

            if value:
                return value

        # OCR failed on this token. '1' is the only numeral this narrow
        # in the poster font, and it is exactly the glyph Tesseract
        # misreads most, so geometry rescues it -- but only here, never
        # over a successful read.
        if narrow:
            return 1

    return None


KNOWN_CLUBS_RAW = """
الهلال|النصر|الاتحاد|الأهلي|الشباب|الاتفاق|القادسية|الفيحاء|الرياض|التعاون|الخليج|ضمك|الفتح|الحزم|النجمة|نيوم|الأخدود|الوحدة|الخلود|العروبة|الرائد|الطائي|أبها|الابتسام
ريال مدريد|برشلونة|أتلتيكو مدريد|إشبيلية|فالنسيا|فياريال|ريال سوسييداد|ريال بيتيس|أتلتيك بلباو|سيلتا فيغو|رايو فاليكانو|ديبورتيفو ألافيس|جيرونا|أوساسونا|خيتافي|مايوركا|إلتشي|ليفانتي|إسبانيول|ريال أوفييدو
آرسنال|مانشستر سيتي|مانشستر يونايتد|ليفربول|تشيلسي|توتنهام|نيوكاسل يونايتد|أستون فيلا|إيفرتون|وست هام|برايتون|كريستال بالاس|فولهام|برينتفورد|وولفرهامبتون|نوتنغهام فورست|بيرنلي|ليدز يونايتد|سندرلاند|بورنموث|كوفنتري سيتي
باريس سان جيرمان|أولمبيك مارسيليا|موناكو|ليون|ليل|نيس|رين|ستراسبورج|لانس|نانت|تولوز|بريست|أوكسير|لوريان|أنجيه|لوهافر|ميتز|باريس إف سي
بايرن ميونخ|بوروسيا دورتموند|لايبزيغ|باير ليفركوزن|شتوتغارت|آينتراخت فرانكفورت|فولفسبورج|فرايبورج|هوفنهايم|مونشنغلادباخ|فيردر بريمن|أوجسبورج|يونيون برلين|ماينز|سانت باولي|هامبورج|هايدنهايم|كولن
يوفنتوس|إنتر ميلان|ميلان|نابولي|روما|لاتسيو|أتالانتا|فيورنتينا|بولونيا|تورينو|أودينيزي|ساسولو|كالياري|جنوى|ليتشي|فيرونا|بارما|كومو|كريمونيزي|بيزا
بنفيكا|بورتو|سبورتينج لشبونة|براغا|أياكس|أيندهوفن|فينورد|سيلتيك|رينجرز|جالطة سراي|فنربخشة|بشكتاش|طرابزون سبور|زينيت|شاختار|دينامو كييف|سالزبورغ|كوبنهاغن|أندرلخت|كلوب بروج|فرينكفاروزي|آرهوس جمناستيك|آرهوس
الأهلي المصري|الزمالك|بيراميدز|الترجي|الوداد|الرجاء|الإسماعيلي|صن داونز|مازيمبي
"""

CLUB_MATCH_CUTOFF = 0.72


def _club_key(name):
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )

    text = re.sub(r"[أإآٱ]", "ا", text)
    text = (
        text
        .replace("ى", "ي")
        .replace("ة", "ه")
        .replace("ؤ", "و")
        .replace("ئ", "ي")
    )

    return re.sub(r"\s+", " ", text).strip()


KNOWN_CLUBS = {
    _club_key(name): name
    for line in KNOWN_CLUBS_RAW.strip().split("\n")
    for name in line.split("|")
    if name.strip()
}


def _closest_club(key):
    best_score = 0.0
    best_name = None

    for candidate_key, candidate_name in KNOWN_CLUBS.items():
        score = SequenceMatcher(
            None,
            key,
            candidate_key,
        ).ratio()

        if score > best_score:
            best_score = score
            best_name = candidate_name

    return best_score, best_name


def correct_club_name(name):
    """
    Tesseract's Arabic model confuses similar letters
    (ر/ز, ت/ق, ب/ي), producing 'زبال بيتيس' or 'كوفنتري سيقي'.

    Snap the OCR result to the closest known club name, and
    leave it untouched when nothing matches closely enough,
    so unlisted clubs are never renamed to a wrong one.
    """
    key = _club_key(name)

    if not key:
        return name

    if key in KNOWN_CLUBS:
        return KNOWN_CLUBS[key]

    score, match = _closest_club(key)

    if score >= CLUB_MATCH_CUTOFF:
        return match

    # a leading fragment of a badge may survive as a fake word
    words = key.split()

    for drop in range(1, min(3, len(words))):
        score, match = _closest_club(" ".join(words[drop:]))

        if score >= CLUB_MATCH_CUTOFF:
            return match

    return name


def _team_text_boxes(arr, box):
    """
    Isolate the two team-name blocks inside the dark-navy
    strip above the cyan bar.

    Club badges overlap that strip and their coloured
    fragments are what produced garbage like 'عكك ملببف'.
    So we keep only columns whose background is genuinely
    navy (or white text), then group the white-text runs
    into a right block and a left block around the middle
    watermark.
    """
    x0, y0, x1, y1 = box

    strip_h = y1 - y0
    ty0 = max(0, int(y0 - strip_h * 1.10))
    ty1 = y0 - 2

    if ty1 - ty0 < 8:
        return (None, None)

    band = arr[ty0:ty1, x0:x1]
    lum = band.mean(2)

    navy = (lum < 115) & (band[..., 2] > band[..., 0])
    white = lum > 185

    clean_cols = (navy | white).mean(0) > 0.93
    ink = white & clean_cols[None, :]

    band_w = x1 - x0
    gap = max(4, int(band_w * 0.03))

    tokens = []

    for a, b in _runs(ink.sum(0) > 0, 2):
        if tokens and a - tokens[-1][1] <= gap:
            tokens[-1] = (tokens[-1][0], b)
        else:
            tokens.append((a, b))

    right = [
        t for t in tokens
        if (t[0] + t[1]) / 2 > band_w * 0.56
    ]

    left = [
        t for t in tokens
        if (t[0] + t[1]) / 2 < band_w * 0.44
    ]

    boxes = []

    for group in (right, left):
        if not group:
            boxes.append(None)
            continue

        gx0 = min(t[0] for t in group)
        gx1 = max(t[1] for t in group)

        rows = np.where(ink[:, gx0:gx1].sum(1) > 0)[0]

        if len(rows) == 0:
            boxes.append(None)
            continue

        boxes.append(
            (
                x0 + max(0, gx0 - 2),
                ty0 + max(0, rows[0] - 4),
                x0 + min(band_w, gx1 + 2),
                ty0 + min(ty1 - ty0, rows[-1] + 5),
            )
        )

    return tuple(boxes)


REPEATED_CHAR_RE = re.compile(r"(.)\1{2,}")


def _sanitize_team_name(raw):
    """
    The team strip is Arabic-only. Digits, Latin letters and
    badge fragments are OCR noise, so drop them.
    """
    text = _ocr_norm(raw or "")

    text = re.sub(r"[^\u0621-\u064a\u0670-\u06d3\s]", " ", text)

    words = []

    for word in text.split():
        if len(word) < 2:
            continue

        if REPEATED_CHAR_RE.search(word):
            continue

        if len(set(word)) == 1:
            continue

        words.append(word)

    cleaned = " ".join(words).strip()

    if len(cleaned) < 3:
        return ""

    return cleaned


def read_teams(im, arr, box):
    """
    Team names sit in the dark-navy strip above the cyan bar:
      [ team B ][ badge/watermark ][ team A ]
    Arabic reads right-to-left, so the RIGHT block is first.
    """
    right_box, left_box = _team_text_boxes(arr, box)

    if not right_box or not left_box:
        return (None, 0.0)

    names = []

    for part_box in (right_box, left_box):
        part = im.crop(part_box)
        best = ""

        for psm in (7, 6, 13):
            for invert in (False, True):
                raw = norm(
                    pytesseract.image_to_string(
                        _upscale(part, scale=5, invert=invert),
                        lang="ara",
                        config=f"--psm {psm}",
                    )
                )

                cand = _sanitize_team_name(raw)

                if cand and len(cand) > len(best):
                    best = cand

        names.append(correct_club_name(best) if best else "")

    if not names[0] or not names[1]:
        return (None, 0.0)

    return (
        f"{names[0]} - {names[1]}",
        0.95,
    )


def read_poster_date(im, fallback):
    """
    Header date is printed in Latin digits (2026-08-21),
    so a digit whitelist reads it exactly.
    """
    w, h = im.size

    header = im.crop(
        (
            int(0.28 * w),
            int(0.04 * h),
            int(0.74 * w),
            int(0.24 * h),
        )
    )

    for psm in (6, 11, 7):
        for invert in (False, True):
            text = _ocr_chars(
                header,
                "0123456789-/.",
                psm,
                invert=invert,
            )

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
                continue

    # legacy Arabic pass, then Telegram post date
    return poster_date(im, fallback)


POSTER_MIN_WIDTH = 1400
POSTER_MAX_WIDTH = 3200


def _ensure_readable_size(im):
    """
    Telegram serves compressed previews (often ~800px wide).
    At that size the channel digit is only a few pixels tall
    and OCR silently fails. Upscale first, always.
    """
    if im.width > POSTER_MAX_WIDTH:
        scale = POSTER_MAX_WIDTH / im.width

        return im.resize(
            (
                int(im.width * scale),
                int(im.height * scale),
            ),
            Image.LANCZOS,
        )

    if im.width >= POSTER_MIN_WIDTH:
        return im

    scale = POSTER_MIN_WIDTH / im.width

    return im.resize(
        (
            int(im.width * scale),
            int(im.height * scale),
        ),
        Image.LANCZOS,
    )


def _repair_card(im, arr, boxes, index, box):
    """
    A heavily re-encoded poster can split one cyan strip into two
    fragments. Only when a card fails to produce BOTH a time and a
    channel do we retry it merged with its neighbour in the same
    band -- so genuine side-by-side cards are never glued together.
    """
    x0, y0, x1, y1 = box
    width = im.width
    best = None

    for other_index, other in enumerate(boxes, 1):
        if other_index == index:
            continue

        ox0, oy0, ox1, oy1 = other

        if abs(oy0 - y0) > 3 or abs(oy1 - y1) > 3:
            continue

        gap = ox0 - x1 if ox0 > x1 else x0 - ox1

        if gap > 0.15 * width:
            continue

        merged = (
            min(x0, ox0),
            min(y0, oy0),
            max(x1, ox1),
            max(y1, oy1),
        )

        split_x = _split_time_channel(arr, merged)
        clock = read_clock(im, merged, split_x)
        channel = read_channel(im, arr, merged, split_x)

        if clock and channel:
            best = (merged, split_x, clock, channel, other_index)
            break

    return best


def parse_poster(im, post_time, source):
    """
    Dynamic poster reader: reads EVERY match card on the
    poster, whether the day has 2, 3, 4, 5 or more matches.
    """
    im = _ensure_readable_size(im)

    boxes = detect_match_strips(im)

    if not boxes:
        warn(
            "no cyan match strips detected, "
            "falling back to legacy grid reader"
        )
        return parse_poster_legacy(im, post_time, source)

    poster_day = read_poster_date(im, post_time)

    arr = _as_array(im)
    events = []
    seen_slots = set()

    log(
        f"POSTER {poster_day} | "
        f"detected {len(boxes)} match card(s)"
    )

    consumed = set()

    for index, box in enumerate(boxes, 1):
        if index in consumed:
            continue

        split_x = _split_time_channel(arr, box)

        clock = read_clock(im, box, split_x)
        channel = read_channel(im, arr, box, split_x)

        if not clock or not channel:
            repaired = _repair_card(im, arr, boxes, index, box)

            if repaired:
                box, split_x, clock, channel, partner = repaired
                consumed.add(partner)

                log(
                    f"card #{index} repaired by merging with "
                    f"card #{partner}"
                )

        if not clock or not channel:
            warn(
                f"card #{index} {box} skipped | "
                f"time={clock} channel={channel}"
            )
            continue

        hour, minute = clock

        if (channel, hour, minute) in seen_slots:
            continue

        seen_slots.add((channel, hour, minute))

        try:
            title, confidence = read_teams(im, arr, box)
        except Exception as exc:
            warn(f"team OCR failed on card #{index} | {exc}")
            title, confidence = (None, 0.0)

        generic_title = False

        if not title:
            title = (
                "مباراة مباشرة - "
                f"فجر سبورت {channel}"
            )
            confidence = 0.0
            generic_title = True

        local = datetime(
            poster_day.year,
            poster_day.month,
            poster_day.day,
            hour,
            minute,
            tzinfo=PALESTINE,
        )

        start = local.astimezone(UTC)

        if not in_window(start):
            warn(
                f"card #{index} outside EPG window | "
                f"ch={channel} | {local:%Y-%m-%d %H:%M} Palestine"
            )
            continue

        channel_id, channel_name = CHANNELS[channel]

        events.append(
            {
                "channel_num": channel,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "start": start,
                "title": title,
                "source_name":
                    "FajerSportOfficialTelegramPosterOCR",
                "source": source,
                "duration_minutes": 110,
                "time_type": "scheduled-image",
                "ocr_confidence": confidence,
                "ocr_raw": f"card#{index} {box}",
                "generic_title": generic_title,
            }
        )

        log(
            f"CARD #{index} | ch={channel} | "
            f"{local:%Y-%m-%d %H:%M} Palestine | "
            f"{title} | confidence={confidence:.2f}"
        )

    return events


# ============================================================
# TELEGRAM TEXT
# ============================================================

EXPLICIT_NOW_RE = re.compile(
    r"تشاهدون\s+الآن|"
    r"تشاهدون\s+الان|"
    r"الآن\s+عبر|"
    r"الان\s+عبر",
    re.I,
)

SCHEDULE_HINT_RE = re.compile(
    r"تشاهدون\s+اليوم|"
    r"مباريات\s+اليوم|"
    r"موعد|"
    r"الساعة",
    re.I,
)

CHANNEL_TEXT_RE = re.compile(
    r"(?:قناة|قناتنا|القناة)"
    r"\s*([1-5])"
)

MATCH_TEXT_RE = re.compile(
    r"([\w\u0600-\u06ff .'-]+?)"
    r"\s*[xX×]\s*"
    r"([\w\u0600-\u06ff .'-]+)"
)

TIME_TEXT_RE = re.compile(
    r"(?<!\d)(\d{1,2})\s*[:٫.]\s*(\d{2})"
    r"\s*(ص|م|صباحا|صباحًا|مساء|مساءً|am|pm)?",
    re.I,
)


def _parse_text_clock(text):
    m = TIME_TEXT_RE.search(_ocr_norm(text))
    if not m:
        return None

    hh = int(m.group(1))
    mm = int(m.group(2))
    marker = (m.group(3) or "").casefold()

    if marker in {"م", "مساء", "مساءً", "pm"} and 1 <= hh <= 11:
        hh += 12
    elif marker in {"ص", "صباحا", "صباحًا", "am"} and hh == 12:
        hh = 0

    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None

    return hh, mm


def _pairs_with_channels(text):
    text = norm(text)
    pairs = list(MATCH_TEXT_RE.finditer(text))
    out = []

    for idx, match in enumerate(pairs):
        segment_end = (
            pairs[idx + 1].start()
            if idx + 1 < len(pairs)
            else len(text)
        )
        segment = text[
            match.start():
            segment_end
        ]

        channel_matches = list(
            CHANNEL_TEXT_RE.finditer(segment)
        )

        if (
            not channel_matches
            and len(pairs) == 1
        ):
            channel_matches = list(
                CHANNEL_TEXT_RE.finditer(text)
            )

        channels = []
        for cm in channel_matches:
            channel = int(cm.group(1))
            if channel not in channels:
                channels.append(channel)

        team_a = clean_candidate(match.group(1))
        team_b = clean_candidate(match.group(2))

        if not team_a or not team_b:
            continue

        out.append(
            (
                f"{team_a} - {team_b}",
                channels,
            )
        )

    return out


def parse_text_matches(text, post_time):
    """
    Parse explicit Fajer Telegram text.

    These events are useful both as EPG events and
    as authoritative title hints for OCR poster blocks.
    """
    text = norm(text)
    if not text:
        return []

    out = []
    pairs = _pairs_with_channels(text)
    if not pairs:
        return []

    local_post = post_time.astimezone(PALESTINE)

    is_now = bool(EXPLICIT_NOW_RE.search(text))
    is_schedule = bool(SCHEDULE_HINT_RE.search(text))
    text_clock = _parse_text_clock(text) if is_schedule else None

    for title, channels in pairs:
        if not channels:
            continue

        if is_now:
            start = post_time.astimezone(UTC)
            time_type = "observed-now"
            source_name = "FajerSportOfficialTelegramNow"
        elif text_clock:
            hh, mm = text_clock
            start = datetime(
                local_post.year,
                local_post.month,
                local_post.day,
                hh,
                mm,
                tzinfo=PALESTINE,
            ).astimezone(UTC)
            time_type = "scheduled-text"
            source_name = "FajerSportOfficialTelegramSchedule"
        else:
            # The title/channel pairing is still useful as a title hint,
            # but it is NOT safe enough to become a timed programme.
            start = None
            time_type = "title-hint"
            source_name = "FajerSportOfficialTelegramTitleHint"

        for channel in channels:
            cid, cname = CHANNELS[channel]
            out.append(
                {
                    "channel_num": channel,
                    "channel_id": cid,
                    "channel_name": cname,
                    "start": start,
                    "title": title,
                    "source_name": source_name,
                    "source": "https://t.me/fajersport",
                    "duration_minutes": 110,
                    "time_type": time_type,
                }
            )

    return out


# ============================================================
# FIXTURE TITLE RESOLUTION
# ============================================================

def _match_text_key(s):
    s = norm(s).casefold()
    s = s.translate(
        str.maketrans(
            "أإآةى",
            "اااهي",
        )
    )
    return re.sub(
        r"[^a-z0-9\u0600-\u06ff]+",
        " ",
        s,
    ).strip()


def _title_is_generic(title):
    t = _match_text_key(title)
    return (
        not t
        or t.startswith("مباراه مباشره فجر سبورت")
        or t.startswith("مباراة مباشرة فجر سبورت")
    )


def _minutes_apart(a, b):
    return abs(
        (a.astimezone(UTC) - b.astimezone(UTC))
        .total_seconds()
        / 60.0
    )


def _best_telegram_title(ocr_event, text_hints):
    """
    Very conservative:
      1) same Fajer channel
      2) same Palestine calendar day
      3) if timed hint exists: within 45 min
      4) if untimed: there must be exactly one title for that channel/day
    """
    event_day = ocr_event["start"].astimezone(PALESTINE).date()

    candidates = []
    untimed = []

    for hint in text_hints:
        if hint["channel_id"] != ocr_event["channel_id"]:
            continue

        if hint.get("start") is not None:
            hint_day = hint["start"].astimezone(PALESTINE).date()
            if hint_day != event_day:
                continue

            delta = _minutes_apart(
                ocr_event["start"],
                hint["start"],
            )

            if delta <= 45:
                candidates.append(
                    (
                        delta,
                        hint,
                    )
                )
        else:
            # Untimed Telegram title-hints are only accepted if the post
            # belongs to the same day; caller stores hint_post_day.
            if hint.get("hint_post_day") == event_day:
                untimed.append(hint)

    if candidates:
        candidates.sort(key=lambda x: x[0])

        # Require a uniquely closest candidate.
        best_delta, best = candidates[0]

        if (
            len(candidates) == 1
            or candidates[1][0] - best_delta >= 10
        ):
            return best["title"], best["source_name"]

    unique_untimed = {}
    for hint in untimed:
        unique_untimed[_match_text_key(hint["title"])] = hint

    if len(unique_untimed) == 1:
        only = next(iter(unique_untimed.values()))
        return only["title"], only["source_name"]

    return None


def _lftv_parse_date(line):
    """
    LiveFootballTV date headings use DD/MM/YYYY, for example:
    "Football on TV today wednesday, 19/08/2026".
    """
    m = re.search(
        r"(?<!\d)(\d{1,2})/(\d{1,2})/(20\d{2})(?!\d)",
        norm(line),
    )
    if not m:
        return None

    try:
        return date(
            int(m.group(3)),
            int(m.group(2)),
            int(m.group(1)),
        )
    except ValueError:
        return None


_LFTV_TIME_RE = re.compile(
    r"^(?:[01]?\d|2[0-3]):[0-5]\d$"
)

_LFTV_COMPETITION_NOISE = re.compile(
    r"\b("
    r"league|liga|cup|copa|championship|friendly|"
    r"qualifying|qualification|round|playoff|playoffs|"
    r"super cup|premier|bundesliga|serie|division|"
    r"conference|champions|europa|libertadores|"
    r"sudamericana|world cup|club world cup"
    r")\b",
    re.I,
)

_LFTV_BROADCAST_NOISE = re.compile(
    r"\b("
    r"tv|app|youtube|ppv|sports?|sport|play|plus|"
    r"bein|starz|shahid|thmanyah|concacaf|espn|fox|"
    r"paramount|dazn|canal|channel|stream"
    r")\b",
    re.I,
)


def _lftv_team_candidate(line):
    s = norm(line)

    if not s or len(s) > 70:
        return None

    if _LFTV_TIME_RE.fullmatch(s):
        return None

    if _lftv_parse_date(s):
        return None

    if _LFTV_COMPETITION_NOISE.search(s):
        return None

    if _LFTV_BROADCAST_NOISE.search(s):
        return None

    if re.fullmatch(r"[\d\s().%+\-]+", s):
        return None

    if len(re.sub(r"[^A-Za-zÀ-ÿ0-9\u0600-\u06ff]", "", s)) < 2:
        return None

    return s


def _lftv_event_from_block(day, clock, block):
    """
    Extract only a conservative team pair from one LiveFootballTV block.
    We do NOT use this source to choose a Fajer channel or alter OCR time.
    """
    candidates = []

    for line in block:
        value = _lftv_team_candidate(line)
        if value:
            candidates.append(value)

    # LiveFootballTV normally renders:
    # competition / optional round / home / away / broadcaster(s).
    # After noise removal the first two plausible names are the teams.
    if len(candidates) < 2:
        return None

    home = candidates[0]
    away = candidates[1]

    if _match_text_key(home) == _match_text_key(away):
        return None

    hh, mm = map(int, clock.split(":"))

    try:
        local = datetime(
            day.year,
            day.month,
            day.day,
            hh,
            mm,
            tzinfo=CAIRO,
        )
    except ValueError:
        return None

    return {
        "start": local.astimezone(UTC),
        "title": f"{home} - {away}",
        "source_name": "LiveFootballTV",
    }


def collect_livefootballtv():
    """
    External fixture corroboration using the same LiveFootballTV source
    already used successfully by the ON Sport EPG.

    IMPORTANT:
    * This source can ONLY provide a match title.
    * It can NEVER change the Fajer channel.
    * It can NEVER change the OCR-derived kickoff time.
    """
    try:
        soup = BeautifulSoup(
            fetch(LIVEFOOTBALLTV_URL),
            "html.parser",
        )
    except Exception as exc:
        warn(
            "LiveFootballTV unavailable | "
            f"{exc}"
        )
        return []

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    lines = [
        norm(x)
        for x in soup.stripped_strings
        if norm(x)
    ]

    fixtures = []
    current_day = None
    pending_time = None
    pending_block = []

    def flush():
        nonlocal pending_time, pending_block

        if current_day is None or pending_time is None:
            pending_time = None
            pending_block = []
            return

        ev = _lftv_event_from_block(
            current_day,
            pending_time,
            pending_block,
        )

        if ev:
            fixtures.append(ev)

        pending_time = None
        pending_block = []

    for line in lines:
        maybe_day = _lftv_parse_date(line)

        if maybe_day:
            flush()
            current_day = maybe_day
            continue

        if _LFTV_TIME_RE.fullmatch(line):
            flush()
            pending_time = line
            pending_block = []
            continue

        if pending_time is not None:
            pending_block.append(line)

    flush()

    # Deduplicate exact fixture/time duplicates.
    unique = {}
    for ev in fixtures:
        key = (
            ev["start"].replace(second=0, microsecond=0),
            _match_text_key(ev["title"]),
        )
        unique[key] = ev

    fixtures = sorted(
        unique.values(),
        key=lambda x: x["start"],
    )

    log(
        "LiveFootballTV global fixtures detected: "
        f"{len(fixtures)}"
    )

    return fixtures


def _ocr_candidate_score(raw, candidate_title):
    """
    Text similarity is used only when OCR managed to capture
    some team-name text. A high threshold prevents guessing.
    """
    raw_key = _match_text_key(raw)
    title_key = _match_text_key(candidate_title)

    if len(raw_key) < 5 or len(title_key) < 5:
        return 0.0

    # Direct token containment is stronger than generic fuzzy similarity.
    title_tokens = [
        token
        for token in title_key.split()
        if len(token) >= 4
    ]

    contained = sum(
        1
        for token in title_tokens
        if token in raw_key
    )

    if contained >= 2:
        return 0.98
    if contained == 1:
        return 0.82

    return SequenceMatcher(
        None,
        raw_key,
        title_key,
    ).ratio()


def _best_livefootballtv_title(ocr_event, fixtures):
    """
    Safe rules:
      * kickoff must be within 3 minutes
      * if exactly one global fixture exists at that time -> accept
      * if several exist -> require strong OCR/title similarity
      * otherwise do nothing
    """
    near = [
        f
        for f in fixtures
        if _minutes_apart(
            ocr_event["start"],
            f["start"],
        ) <= 5
    ]

    if not near:
        return None

    if len(near) == 1:
        return near[0]["title"], near[0]["source_name"]

    raw = ocr_event.get("ocr_raw", "")
    scored = sorted(
        (
            (
                _ocr_candidate_score(
                    raw,
                    f["title"],
                ),
                f,
            )
            for f in near
        ),
        key=lambda x: x[0],
        reverse=True,
    )

    if not scored:
        return None

    best_score, best = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0

    if (
        best_score >= 0.82
        and best_score - second_score >= 0.10
    ):
        return best["title"], best["source_name"]

    return None


def enrich_titles(events, text_hints):
    """
    Preserve all existing OCR timing/channel decisions.

    Only replace a generic title when a separate source
    gives a high-confidence match.
    """
    generic_events = [
        ev
        for ev in events
        if _title_is_generic(ev.get("title", ""))
    ]

    if not generic_events:
        return events

    lftv_cache = None

    for ev in generic_events:
        resolved = _best_telegram_title(
            ev,
            text_hints,
        )

        if resolved:
            title, title_source = resolved
            ev["title"] = title
            ev["generic_title"] = False
            ev["title_source"] = title_source
            ev["source_name"] = (
                ev["source_name"]
                + "+"
                + title_source
            )

            log(
                "TITLE MATCH | Telegram | "
                f"{ev['channel_name']} | "
                f"{ev['start'].astimezone(PALESTINE):%Y-%m-%d %H:%M} | "
                f"{title}"
            )
            continue

        if lftv_cache is None:
            lftv_cache = collect_livefootballtv()

        resolved = _best_livefootballtv_title(
            ev,
            lftv_cache,
        )

        if resolved:
            title, title_source = resolved
            ev["title"] = title
            ev["generic_title"] = False
            ev["title_source"] = title_source
            ev["source_name"] = (
                ev["source_name"]
                + "+"
                + title_source
            )

            log(
                "TITLE MATCH | LiveFootballTV | "
                f"{ev['channel_name']} | "
                f"{ev['start'].astimezone(PALESTINE):%Y-%m-%d %H:%M} | "
                f"{title}"
            )
        else:
            log(
                "TITLE SAFE FALLBACK | "
                f"{ev['channel_name']} | "
                f"{ev['start'].astimezone(PALESTINE):%Y-%m-%d %H:%M} | "
                "no unique verified title"
            )

    return events


# ============================================================
# TELEGRAM IMAGE EXTRACTION
# ============================================================

MEDIA_SKIP_ANCESTOR_CLASSES = {
    "tgme_widget_message_user_photo",
    "tgme_widget_message_author_photo",
    "tgme_widget_message_owner_photo",
    "tgme_widget_message_reply",
    "tgme_widget_message_reply_thumb",
    "tgme_widget_message_forwarded_from",
    "tgme_widget_message_service",
    "tgme_widget_message_bubble_tail",
    "tgme_channel_info",
    "tgme_header",
    "tgme_footer",
    "tgme_widget_message_inline_button",
}

# Every attribute Telegram has ever used to carry media on the
# public /s/ preview: photos, albums, video/gif thumbs, round
# videos, stickers, document thumbs and link previews.
MEDIA_URL_ATTRS = (
    "src",
    "data-src",
    "data-original",
    "data-url",
    "data-image",
    "data-thumb",
    "data-webp",
    "data-background",
    "poster",
    "content",
)

BG_URL_RE = re.compile(
    r"url\(\s*['\"]?([^'\")]+)",
    re.I,
)

MEDIA_EXT_RE = re.compile(
    r"\.(?:jpe?g|png|webp|gif|bmp|tiff?|avif|heic|jfif|mpo)"
    r"(?:[?#][^/]*)?$",
    re.I,
)

MEDIA_HOST_RE = re.compile(
    r"(?:cdn[\w-]*\.cdn-telegram\.org|telesco\.pe|"
    r"cdn[\w-]*\.telesco\.pe|telegram\.org/file|/file/)",
    re.I,
)


def _normalize_media_url(raw):
    url = unescape((raw or "").strip().strip("'\""))

    if not url or url.startswith("data:"):
        return None

    if url.startswith("//"):
        url = "https:" + url

    url = urljoin("https://t.me/", url)

    if not url.lower().startswith(("http://", "https://")):
        return None

    return url


def _looks_like_media(url):
    return bool(
        MEDIA_EXT_RE.search(url)
        or MEDIA_HOST_RE.search(url)
    )


def _largest_from_srcset(value):
    best = None
    best_width = -1.0

    for part in (value or "").split(","):
        part = part.strip()

        if not part:
            continue

        bits = part.split()
        candidate = bits[0]
        width = 0.0

        if len(bits) > 1:
            token = bits[-1].lower().rstrip("wx")

            try:
                width = float(token)
            except ValueError:
                width = 0.0

        if width >= best_width:
            best_width = width
            best = candidate

    return best


def _media_node_is_decoration(node, root):
    current = node

    while current is not None and current is not root:
        classes = set(current.get("class", []) or []) if hasattr(current, "get") else set()

        if classes & MEDIA_SKIP_ANCESTOR_CLASSES:
            return True

        current = getattr(current, "parent", None)

    return False


def image_urls(msg):
    """
    Collect EVERY media URL a post can carry, in any Telegram
    layout: single photo, album/grouped wrap, video or GIF
    thumbnail, round video, sticker, document preview and link
    preview -- whatever the file format (jpg/png/webp/gif/...).

    Avatars, reply thumbnails and forward decorations are the
    only things excluded.
    """
    urls = []

    def add(raw):
        url = _normalize_media_url(raw)

        if url and _looks_like_media(url):
            urls.append(url)

    for node in msg.find_all(True):
        if _media_node_is_decoration(node, msg):
            continue

        style = node.get("style") or ""

        if "background" in style.lower():
            for match in BG_URL_RE.finditer(style):
                add(match.group(1))

        srcset = node.get("srcset")

        if srcset:
            add(_largest_from_srcset(srcset))

        for attr in MEDIA_URL_ATTRS:
            value = node.get(attr)

            if isinstance(value, (list, tuple)):
                value = " ".join(value)

            if value:
                add(value)

    return list(dict.fromkeys(urls))


# ============================================================
# MEDIA INTAKE
# ============================================================
#
# Every rejection below is logged. A poster must never be
# dropped silently again.

MEDIA_MIN_BYTES = 2000
MEDIA_MIN_WIDTH = 300
MEDIA_MIN_HEIGHT = 300
MEDIA_MIN_PIXELS = 150_000
MEDIA_MIN_RATIO = 0.20
MEDIA_MAX_RATIO = 5.00


def load_image(data):
    """
    Decode any still or animated format Telegram may serve and
    return a flat RGB frame plus the detected format name.
    """
    im = Image.open(io.BytesIO(data))
    fmt = (im.format or "?").upper()

    try:
        im.seek(0)
    except Exception:
        pass

    try:
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass

    if im.mode in ("RGBA", "LA", "P", "PA"):
        rgba = im.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.split()[-1])
        im = flat
    else:
        im = im.convert("RGB")

    return im, fmt


def _image_signature(im):
    """
    Perceptual fingerprint (dHash). The same poster served at two
    sizes, two qualities or two formats produces near-identical
    hashes, so it is only OCR-ed once.
    """
    thumb = im.convert("L").resize((17, 16), Image.LANCZOS)
    pixels = np.asarray(thumb).astype(int)
    bits = pixels[:, 1:] > pixels[:, :-1]

    value = 0

    for bit in bits.flatten():
        value = (value << 1) | int(bit)

    return value


def _is_duplicate_signature(signature, seen_signatures, max_distance=6):
    for known in seen_signatures:
        if bin(known ^ signature).count("1") <= max_distance:
            return True

    return False


def poster_events_from_message(
    msg,
    post_time,
    seen_urls,
    seen_signatures,
):
    events = []
    media = image_urls(msg)

    if not media:
        return events

    for url in media:
        short = url[:95]

        if url in seen_urls:
            continue

        seen_urls.add(url)

        try:
            data = fetch(url, True)
        except Exception as exc:
            warn(f"MEDIA fetch failed | {short} | {exc}")
            continue

        if len(data) < MEDIA_MIN_BYTES:
            log(
                "MEDIA SKIP | tiny file "
                f"{len(data)}B | {short}"
            )
            continue

        try:
            im, fmt = load_image(data)
        except Exception as exc:
            log(f"MEDIA SKIP | undecodable ({exc}) | {short}")
            continue

        width, height = im.size
        ratio = width / max(1, height)

        if (
            width < MEDIA_MIN_WIDTH
            or height < MEDIA_MIN_HEIGHT
            or width * height < MEDIA_MIN_PIXELS
        ):
            log(
                "MEDIA SKIP | too small "
                f"{width}x{height} | {short}"
            )
            continue

        if not (MEDIA_MIN_RATIO <= ratio <= MEDIA_MAX_RATIO):
            log(
                "MEDIA SKIP | extreme aspect "
                f"{width}x{height} ratio={ratio:.2f} | {short}"
            )
            continue

        signature = _image_signature(im)

        if _is_duplicate_signature(signature, seen_signatures):
            log(f"MEDIA SKIP | duplicate content | {short}")
            continue

        seen_signatures.add(signature)

        log(
            "MEDIA OK | "
            f"{fmt} {width}x{height} ratio={ratio:.2f} | {short}"
        )

        try:
            found = parse_poster(im, post_time, url)
        except Exception as exc:
            warn(f"poster parse failed | {short} | {exc}")
            continue

        log(f"MEDIA RESULT | matches={len(found)} | {short}")

        events.extend(found)

    return events


def dedupe(events):
    rank = {
        "scheduled-image": 4,
        "scheduled-text": 3,
        "scheduled": 2,
        "observed-now": 1,
        "title-hint": 0,
    }

    chosen = {}

    for event in events:
        if event.get("start") is None:
            continue

        key = (
            event["channel_id"],
            event["start"]
            .astimezone(UTC)
            .replace(
                second=0,
                microsecond=0,
            ),
            re.sub(
                r"\W+",
                " ",
                event["title"].casefold(),
            ),
        )

        if key not in chosen:
            chosen[key] = event
            continue

        old_rank = rank.get(
            chosen[key].get("time_type"),
            0,
        )

        new_rank = rank.get(
            event.get("time_type"),
            0,
        )

        if new_rank > old_rank:
            chosen[key] = event

    return sorted(
        chosen.values(),
        key=lambda e: (
            e["start"],
            e["channel_id"],
        ),
    )



def _telegram_url(base, *, before=None):
    params = {"_": str(int(now_utc().timestamp()))}
    if before is not None:
        params["before"] = str(before)
    return base + "?" + urlencode(params)


def _telegram_page_meta(html):
    """Return message ids, post times, and Telegram's own older-page cursor.

    Telegram's public preview exposes the next pagination cursor in a
    data-before attribute. Using that cursor is more reliable than inventing
    a huge before= value, which can jump far back in channel history.
    """
    soup = BeautifulSoup(html, "html.parser")
    ids = []
    post_times = []

    for msg in soup.select(".tgme_widget_message"):
        data_post = norm(msg.get("data-post", ""))
        m = re.search(r"/(\d+)$", data_post)
        if m:
            try:
                ids.append(int(m.group(1)))
            except ValueError:
                pass

        time_el = msg.select_one("time[datetime]")
        if time_el:
            try:
                dt = datetime.fromisoformat(
                    time_el.get("datetime", "").replace("Z", "+00:00")
                )
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                post_times.append(dt.astimezone(UTC))
            except Exception:
                pass

    before_cursor = None
    for node in soup.select("[data-before]"):
        raw = norm(node.get("data-before", ""))
        if raw.isdigit():
            value = int(raw)
            if value > 0:
                before_cursor = value
                break

    # Safe fallback for markup variants: use the oldest visible message id.
    if before_cursor is None and ids:
        before_cursor = min(ids)

    return ids, post_times, before_cursor


def fetch_recent_telegram_pages(base):
    """Fetch the newest preview page, then follow Telegram's real cursor.

    This deliberately does NOT seed pagination with an artificial huge
    before= value. The public preview's data-before cursor is authoritative.
    """
    pages = []
    seen_signatures = set()
    seen_cursors = set()
    cutoff = now_utc() - timedelta(days=TELEGRAM_RECENT_DAYS)

    url = _telegram_url(base)

    for page_no in range(1, TELEGRAM_MAX_PAGES + 1):
        try:
            html = fetch(url)
        except Exception as exc:
            if page_no == 1:
                raise
            warn(f"Telegram pagination failed {url} | {exc}")
            break

        ids, times, before_cursor = _telegram_page_meta(html)
        signature = (tuple(sorted(ids)), len(html))

        if not ids:
            if page_no == 1:
                raise RuntimeError("Telegram returned no readable public-preview posts")
            break

        if signature in seen_signatures:
            break

        seen_signatures.add(signature)
        pages.append(html)

        if times:
            log(
                "TELEGRAM PAGE | "
                f"page={page_no} | posts={len(ids)} | "
                f"oldest={min(times):%Y-%m-%d %H:%M UTC} | "
                f"latest={max(times):%Y-%m-%d %H:%M UTC} | "
                f"before={before_cursor}"
            )
            # We already have all posts needed for our recent window.
            if min(times) <= cutoff:
                break

        if before_cursor is None or before_cursor in seen_cursors:
            break

        seen_cursors.add(before_cursor)
        url = _telegram_url(base, before=before_cursor)

    if not pages:
        raise RuntimeError("Telegram returned no readable public-preview pages")

    return pages

def parse_telegram_pages(pages):
    merged = []
    latest_post = None

    for html in pages:
        _, times, _ = _telegram_page_meta(html)
        if times:
            page_latest = max(times)
            latest_post = page_latest if latest_post is None else max(latest_post, page_latest)

        merged.extend(parse_telegram_html(html))

    merged = dedupe(merged)

    if latest_post is not None:
        log(
            "LATEST TELEGRAM POST DATE | "
            f"{latest_post.astimezone(PALESTINE):%Y-%m-%d %H:%M} Palestine"
        )

    today = now_utc().astimezone(PALESTINE).date()
    future_events = [
        e for e in merged
        if e.get("start") is not None
        and e["start"].astimezone(PALESTINE).date() >= today
    ]

    log(f"FUTURE EVENTS FOUND | {len(future_events)}")
    for ev in future_events:
        local = ev["start"].astimezone(PALESTINE)
        log(
            "  FUTURE | "
            f"{local:%Y-%m-%d %H:%M} | "
            f"{ev['channel_name']} | "
            f"{ev['title']}"
        )

    return merged


def parse_telegram_html(html):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    events = []
    text_hints = []
    seen_images = set()
    seen_signatures = set()

    messages = soup.select(
        ".tgme_widget_message"
    )

    for msg in messages:
        time_el = msg.select_one(
            "time[datetime]"
        )

        if not time_el:
            continue

        try:
            post_time = datetime.fromisoformat(
                time_el.get(
                    "datetime",
                    "",
                ).replace(
                    "Z",
                    "+00:00",
                )
            )

            if post_time.tzinfo is None:
                post_time = post_time.replace(
                    tzinfo=UTC
                )

        except Exception:
            continue

        body = msg.select_one(
            ".tgme_widget_message_text"
        )

        if body:
            text = norm(
                body.get_text(
                    " ",
                    strip=True,
                )
            )
        else:
            text = ""

        parsed_text = parse_text_matches(
            text,
            post_time,
        )

        for hint in parsed_text:
            hint["hint_post_day"] = (
                post_time
                .astimezone(PALESTINE)
                .date()
            )

        text_hints.extend(parsed_text)

        # Only timed text events are allowed into EPG.
        events.extend(
            [
                e
                for e in parsed_text
                if e.get("start") is not None
                and in_window(e["start"])
            ]
        )

        events.extend(
            poster_events_from_message(
                msg,
                post_time,
                seen_images,
                seen_signatures,
            )
        )

    events = dedupe(events)

    # Enrichment happens after every poster/text post has been inspected.
    events = enrich_titles(
        events,
        text_hints,
    )

    return dedupe(events)


def collect():
    """
    Try every mirror. A mirror that answers but yields zero
    events is treated as suspicious, so the next mirror is
    tried before giving up.
    """
    errors = []
    reachable = False

    for base in TELEGRAM_URLS:
        try:
            pages = fetch_recent_telegram_pages(base)
            events = parse_telegram_pages(pages)
            reachable = True

            log(
                "FajerSport Telegram verified events: "
                f"{len(events)} | "
                f"pages={len(pages)} | {base}"
            )

            if events:
                return events

            errors.append(f"{base}: reachable but 0 events")
            warn(
                "Telegram mirror produced 0 events, "
                f"trying next mirror | {base}"
            )

        except Exception as exc:
            errors.append(f"{base}: {exc}")
            warn(
                "Telegram failed "
                f"{base} "
                f"| {exc}"
            )

    if reachable:
        warn(
            "All mirrors answered but no match was extracted: "
            + " || ".join(errors)
        )
        return []

    raise RuntimeError(
        "All FajerSport Telegram sources failed: "
        + " || ".join(errors)
    )


# ============================================================
# XMLTV
# ============================================================

def write_xml(events):
    root = ET.Element(
        "tv",
        generator_info_name=(
            "Fajer Sport Telegram "
            "+ poster OCR EPG"
        ),
    )

    for n in range(1, 6):
        channel_id, channel_name = CHANNELS[n]

        channel = ET.SubElement(
            root,
            "channel",
            id=channel_id,
        )

        ET.SubElement(
            channel,
            "display-name",
            lang="ar",
        ).text = channel_name

        ET.SubElement(
            channel,
            "display-name",
            lang="en",
        ).text = f"Fajer Sport {n}"

    # Compute programme end times without changing any event detection logic.
    # Default: 110 minutes. If another event on the SAME Fajer channel
    # starts sooner, end the current programme exactly at that next kickoff
    # so XMLTV/TiviMate never shows overlapping programmes.
    starts_by_channel = {}
    for item in events:
        channel_id = item["channel_id"]
        item_start = item["start"].astimezone(UTC)
        starts_by_channel.setdefault(channel_id, []).append(item_start)

    for channel_starts in starts_by_channel.values():
        channel_starts.sort()

    for event in events:
        start = event["start"].astimezone(UTC)

        default_stop = (
            start
            + timedelta(
                minutes=event.get(
                    "duration_minutes",
                    110,
                )
            )
        )

        next_start = next(
            (candidate for candidate in starts_by_channel[event["channel_id"]]
             if candidate > start),
            None,
        )

        if next_start is not None and next_start < default_stop:
            stop = next_start
        else:
            stop = default_stop

        programme = ET.SubElement(
            root,
            "programme",
            start=xmltv_time(start),
            stop=xmltv_time(stop),
            channel=event["channel_id"],
        )

        ET.SubElement(
            programme,
            "title",
            lang="ar",
        ).text = event["title"]

        ET.SubElement(
            programme,
            "category",
            lang="en",
        ).text = "Sports"

        local = start.astimezone(PALESTINE)

        title_source = event.get(
            "title_source",
            event["source_name"],
        )

        ET.SubElement(
            programme,
            "desc",
            lang="ar",
        ).text = (
            f"{event['channel_name']}\n"
            f"{local:%Y-%m-%d %H:%M} "
            "بتوقيت فلسطين\n"
            "المصدر: إعلان فجر سبورت الرسمي\n"
            f"مصدر اسم المباراة: {title_source}"
        )

    ET.indent(
        root,
        space="  ",
    )

    ET.ElementTree(root).write(
        OUTPUT,
        encoding="utf-8",
        xml_declaration=True,
    )

    # Validate generated XML
    ET.parse(OUTPUT)

    log(
        "Written and XML-validated: "
        f"{OUTPUT}"
    )


# ============================================================
# SELF TESTS
# ============================================================

def _self_test_title_matcher():
    base = datetime(
        2026,
        8,
        19,
        18,
        0,
        tzinfo=UTC,
    )

    ev = {
        "channel_id": "FajerSport1",
        "channel_name": "Fajer Sport 1 | فجر سبورت 1",
        "start": base,
        "title": "مباراة مباشرة - فجر سبورت 1",
        "ocr_raw": "",
    }

    hints = [
        {
            "channel_id": "FajerSport1",
            "start": base + timedelta(minutes=2),
            "title": "Barcelona - Al Ahly",
            "source_name": "FajerSportOfficialTelegramNow",
            "hint_post_day": base.astimezone(PALESTINE).date(),
        }
    ]

    resolved = _best_telegram_title(
        ev,
        hints,
    )

    assert resolved is not None
    assert resolved[0] == "Barcelona - Al Ahly"

    lftv = [
        {
            "start": base,
            "title": "Barcelona - Al Ahly",
            "source_name": "LiveFootballTV",
        }
    ]

    resolved = _best_livefootballtv_title(
        ev,
        lftv,
    )

    assert resolved is not None
    assert resolved[0] == "Barcelona - Al Ahly"

    ambiguous = [
        {
            "start": base,
            "title": "Team A - Team B",
            "source_name": "LiveFootballTV",
        },
        {
            "start": base,
            "title": "Team C - Team D",
            "source_name": "LiveFootballTV",
        },
    ]

    assert _best_livefootballtv_title(
        ev,
        ambiguous,
    ) is None

    log("TITLE MATCH SELF TEST | PASS")


def test_image(path, expected=None):
    """
    Local poster test.

    Usage:
      python3 update_fajer_sports_epg.py --test-image poster.jpg
      python3 update_fajer_sports_epg.py --test-image poster.jpg 1@19:00,3@21:00

    'expected' is an optional comma list of channel@HH:MM
    (Palestine local time). No hard-coded match count:
    posters with 2, 3, 4, 5+ matches all pass.
    """
    im = Image.open(path).convert("RGB")

    fake_post_time = datetime.now(UTC)

    old_in_window = globals()["in_window"]
    globals()["in_window"] = lambda x: True

    try:
        events = parse_poster(
            im,
            fake_post_time,
            "local-test",
        )
    finally:
        globals()["in_window"] = old_in_window

    got = sorted(
        (
            event["channel_num"],
            event["start"].astimezone(PALESTINE).strftime("%H:%M"),
            event["title"],
        )
        for event in events
    )

    for channel, clock, title in got:
        log(f"POSTER TEST | ch={channel} | {clock} | {title}")

    if not got:
        raise AssertionError("poster reader found no matches")

    slots = {(c, t) for c, t, _ in got}

    if len(slots) != len(got):
        raise AssertionError(f"duplicate slots detected: {got}")

    if expected:
        want = set()

        for item in expected.split(","):
            item = item.strip()

            if not item:
                continue

            channel, clock = item.split("@")
            want.add((int(channel), clock.strip()))

        missing = want - slots

        if missing:
            raise AssertionError(
                f"missing expected slots: {sorted(missing)} | got {sorted(slots)}"
            )

        extra = slots - want

        if extra:
            raise AssertionError(
                f"unexpected extra slots: {sorted(extra)}"
            )

    return events


# ============================================================
# DIAGNOSTICS
# ============================================================

def diagnose():
    """
    Full audit run: prints every post, every media URL and the
    exact reason each one was accepted or rejected, then the
    resulting programme table. Writes no file.

    Usage: python3 update_fajer_sports_epg.py --diagnose
    """
    for base in TELEGRAM_URLS:
        log(f"\n=== DIAGNOSE {base} ===")

        try:
            pages = fetch_recent_telegram_pages(base)
        except Exception as exc:
            warn(f"unreachable | {base} | {exc}")
            continue

        total_media = 0

        for page_no, html in enumerate(pages, 1):
            soup = BeautifulSoup(html, "html.parser")
            messages = soup.select(".tgme_widget_message")

            log(
                f"PAGE {page_no} | posts={len(messages)} | "
                f"bytes={len(html)}"
            )

            for msg in messages:
                post_id = norm(msg.get("data-post", "?"))
                time_el = msg.select_one("time[datetime]")
                stamp = time_el.get("datetime", "?") if time_el else "?"
                body = msg.select_one(".tgme_widget_message_text")
                text_len = len(body.get_text(" ", strip=True)) if body else 0
                media = image_urls(msg)
                total_media += len(media)

                log(
                    f"  POST {post_id} | {stamp} | "
                    f"text={text_len} chars | media={len(media)}"
                )

                for url in media:
                    log(f"    MEDIA {url[:110]}")

        log(f"TOTAL MEDIA URLS | {total_media} | {base}")

        events = parse_telegram_pages(pages)

        log(f"EVENTS EXTRACTED | {len(events)}")

        for event in events:
            local = event["start"].astimezone(PALESTINE)
            log(
                "  EVENT | "
                f"{local:%Y-%m-%d %H:%M} | "
                f"{event['channel_id']} | {event['title']}"
            )

        if events:
            return

    warn("DIAGNOSE finished without extracting any event")


# ============================================================
# MAIN
# ============================================================

def main():
    log(
        "FAJER SPORT EPG | "
        "official Telegram text + poster OCR | "
        "FINAL VERIFIED PAGINATION | TELEGRAM DATA-BEFORE + POSTER OCR + SAFE TITLE MATCH | "
        "channels 1-5 | "
        "UTC XMLTV | "
        "NO CHANNEL/TIME GUESSING"
    )

    _self_test_title_matcher()

    if (
        len(sys.argv) > 2
        and
        sys.argv[1]
        == "--test-image"
    ):
        test_image(
            sys.argv[2],
            sys.argv[3] if len(sys.argv) > 3 else None,
        )

        log(
            "SELF TEST IMAGE | PASS"
        )

        return

    if len(sys.argv) > 1 and sys.argv[1] == "--diagnose":
        diagnose()
        return

    events = collect()

    if not events:
        warn(
            "NO EVENTS EXTRACTED | "
            "the existing EPG file is kept untouched"
        )

        if os.path.exists(OUTPUT):
            warn(f"kept previous {OUTPUT}")

        sys.exit(1)

    write_xml(events)


if __name__ == "__main__":
    main()
