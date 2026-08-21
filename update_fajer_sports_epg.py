#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import re
import sys
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


def parse_poster(im, post_time, source):
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

def image_urls(msg):
    """Extract actual post media, excluding avatars/reply/forward photos."""
    urls = []

    # Telegram photos are normally CSS background images on this anchor.
    for a in msg.select("a.tgme_widget_message_photo_wrap"):
        style = a.get("style", "")
        m = re.search(
            r"background-image\s*:\s*url\(['\"]?([^'\")]+)",
            style,
        )
        if m:
            urls.append(m.group(1))

    # Generic inline-image fallback, but never treat avatars/reply/forward
    # decorations as poster media.
    skip_ancestor_classes = {
        "tgme_widget_message_user_photo",
        "tgme_widget_message_author_photo",
        "tgme_widget_message_reply",
        "tgme_widget_message_forwarded_from",
    }

    for img in msg.select("img[src]"):
        skip = False
        node = img
        while node is not None and node is not msg:
            classes = set(node.get("class", []) or []) if hasattr(node, "get") else set()
            if classes & skip_ancestor_classes:
                skip = True
                break
            node = getattr(node, "parent", None)
        if skip:
            continue

        url = img.get("src", "")
        if not url:
            continue
        if "cdn" in url or re.search(r"\.(?:jpg|jpeg|png|webp)(?:\?|$)", url, re.I):
            urls.append(urljoin("https://t.me/", url))

    return list(dict.fromkeys(urls))

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

        for image_url in image_urls(msg):
            if image_url in seen_images:
                continue

            seen_images.add(image_url)

            try:
                data = fetch(
                    image_url,
                    True,
                )

                if len(data) < 10000:
                    continue

                im = Image.open(
                    io.BytesIO(data)
                ).convert("RGB")

                # Ignore small/random images
                if im.width < 800:
                    continue

                if (
                    im.width / im.height
                    < 1.25
                ):
                    continue

                events.extend(
                    parse_poster(
                        im,
                        post_time,
                        image_url,
                    )
                )

            except Exception as exc:
                warn(
                    "poster skipped "
                    f"{image_url[:80]} "
                    f"| {exc}"
                )

    events = dedupe(events)

    # Enrichment happens after every poster/text post has been inspected.
    events = enrich_titles(
        events,
        text_hints,
    )

    return dedupe(events)


def collect():
    errors = []

    for base in TELEGRAM_URLS:
        try:
            pages = fetch_recent_telegram_pages(base)
            events = parse_telegram_pages(pages)

            log(
                "FajerSport Telegram verified events: "
                f"{len(events)} | "
                f"pages={len(pages)} | {base}"
            )

            return events

        except Exception as exc:
            errors.append(f"{base}: {exc}")
            warn(
                "Telegram failed "
                f"{base} "
                f"| {exc}"
            )

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


def test_image(path):
    im = Image.open(path).convert("RGB")

    fake_post_time = datetime(
        2026,
        8,
        19,
        8,
        0,
        tzinfo=UTC,
    )

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

    got = {
        (
            event["channel_num"],
            event["start"]
            .astimezone(PALESTINE)
            .hour,
        )
        for event in events
    }

    expected = {
        (1, 21),
        (5, 21),
        (3, 22),
        (4, 22),
    }

    log(
        "POSTER TEST recovered="
        f"{sorted(got)}"
    )

    if not expected.issubset(got):
        raise AssertionError(
            "poster OCR failed "
            "required blocks: "
            f"missing "
            f"{expected - got}"
        )

    return events


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
        test_image(sys.argv[2])

        log(
            "SELF TEST IMAGE | PASS"
        )

        return

    events = collect()
    write_xml(events)


if __name__ == "__main__":
    main()
