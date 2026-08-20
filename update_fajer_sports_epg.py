#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import re
import sys
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from html import unescape
from urllib.parse import urljoin
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


def title_from_card(card, raw_card):
    """
    Never invent team names.

    Only use team names if OCR
    clearly detected a matchup separator.
    """
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
                "duration_minutes": 135,
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
                    "duration_minutes": 135,
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
    urls = []

    for a in msg.select(
        "a.tgme_widget_message_photo_wrap, "
        "a[href]"
    ):
        style = a.get(
            "style",
            "",
        )

        m = re.search(
            r"background-image\s*:\s*"
            r"url\(['\"]?"
            r"([^'\")]+)",
            style,
        )

        if m:
            urls.append(m.group(1))

        href = a.get(
            "href",
            "",
        )

        if re.search(
            r"\.(?:jpg|jpeg|png|webp)"
            r"(?:\?|$)",
            href,
            re.I,
        ):
            urls.append(
                urljoin(
                    "https://t.me/",
                    href,
                )
            )

    for img in msg.select("img[src]"):
        url = img.get(
            "src",
            "",
        )

        if not url:
            continue

        if (
            "cdn" in url
            or
            re.search(
                r"\.(?:jpg|jpeg|png|webp)"
                r"(?:\?|$)",
                url,
                re.I,
            )
        ):
            urls.append(
                urljoin(
                    "https://t.me/",
                    url,
                )
            )

    return list(
        dict.fromkeys(urls)
    )


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
    for url in TELEGRAM_URLS:
        try:
            html = fetch(url)

            events = parse_telegram_html(
                html
            )

            log(
                "FajerSport Telegram "
                "verified events: "
                f"{len(events)} "
                f"| {url}"
            )

            return events

        except Exception as exc:
            warn(
                "Telegram failed "
                f"{url} "
                f"| {exc}"
            )

    return []


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

    for event in events:
        start = event["start"].astimezone(UTC)

        stop = (
            start
            + timedelta(
                minutes=event.get(
                    "duration_minutes",
                    135,
                )
            )
        )

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
        "SAFE TITLE MATCH: Telegram first, LiveFootballTV fallback | "
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
