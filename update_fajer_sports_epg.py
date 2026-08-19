#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import re
import sys
from datetime import date, datetime, timedelta, timezone
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

    im = ImageEnhance.Contrast(
        im
    ).enhance(1.6)

    im = im.resize(
        (
            im.width * scale,
            im.height * scale,
        )
    )

    return im.filter(
        ImageFilter.SHARPEN
    )


def ocr(
    im,
    psm=6,
    lang="ara+eng",
):
    text = pytesseract.image_to_string(
        prep(im),
        lang=lang,
        config=f"--psm {psm}",
    )

    return norm(text)


def poster_date(
    im,
    fallback,
):
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
        text = ocr(
            header,
            psm,
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
            pass

    return fallback.astimezone(
        PALESTINE
    ).date()


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

    if not channel_match:
        return None

    if not time_match:
        return None

    channel = int(
        channel_match.group(1)
        or channel_match.group(2)
    )

    hour = int(
        time_match["h"]
    )

    minute = int(
        time_match["m"]
    )

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

            text = ocr(
                region,
                psm,
            )

            texts.append(text)

            hit = _extract_channel_time(
                text
            )

            if not hit:
                continue

            (
                channel,
                clock,
                explicit_ampm,
            ) = hit

            key = (
                channel,
                clock,
            )

            weight = (
                3
                if explicit_ampm
                else 1
            )

            votes[key] = (
                votes.get(
                    key,
                    0,
                )
                + weight
            )

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

    return s.strip(
        " .-'"
    )


def title_from_card(
    card,
    raw_card,
):
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

        if not team_a:
            continue

        if not team_b:
            continue

        if NOISE.search(
            team_a + team_b
        ):
            continue

        return (
            f"{team_a} - {team_b}",
            0.90,
        )

    return (
        None,
        0.0,
    )


def parse_poster(
    im,
    post_time,
    source,
):
    poster_day = poster_date(
        im,
        post_time,
    )

    events = []

    for (
        label,
        box,
    ) in card_boxes(im):

        card = im.crop(box)

        (
            channel,
            clock,
            raw,
        ) = channel_and_time(
            card
        )

        if not channel:
            continue

        if not clock:
            continue

        (
            title,
            confidence,
        ) = title_from_card(
            card,
            raw,
        )

        if not title:

            title = (
                "مباراة مباشرة - "
                f"فجر سبورت {channel}"
            )

            confidence = 0.0

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

        start = local.astimezone(
            UTC
        )

        if not in_window(start):
            continue

        (
            channel_id,
            channel_name,
        ) = CHANNELS[channel]

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
# TELEGRAM TEXT FALLBACK
# ============================================================

EXPLICIT_NOW_RE = re.compile(
    r"تشاهدون\s+الآن|"
    r"تشاهدون\s+الان|"
    r"الآن\s+عبر|"
    r"الان\s+عبر",
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


def parse_now(
    text,
    post_time,
):
    text = norm(text)

    if not EXPLICIT_NOW_RE.search(
        text
    ):
        return []

    pairs = list(
        MATCH_TEXT_RE.finditer(
            text
        )
    )

    events = []

    for i, match in enumerate(
        pairs
    ):

        segment_end = (
            pairs[i + 1].start()
            if i + 1 < len(pairs)
            else len(text)
        )

        segment = text[
            match.start():
            segment_end
        ]

        channel_match = (
            CHANNEL_TEXT_RE.search(
                segment
            )
        )

        if (
            not channel_match
            and
            len(pairs) == 1
        ):
            channel_match = (
                CHANNEL_TEXT_RE.search(
                    text
                )
            )

        if not channel_match:
            continue

        channel = int(
            channel_match.group(1)
        )

        team_a = clean_candidate(
            match.group(1)
        )

        team_b = clean_candidate(
            match.group(2)
        )

        if not team_a:
            continue

        if not team_b:
            continue

        (
            channel_id,
            channel_name,
        ) = CHANNELS[channel]

        events.append(
            {
                "channel_num":
                    channel,
                "channel_id":
                    channel_id,
                "channel_name":
                    channel_name,
                "start":
                    post_time.astimezone(
                        UTC
                    ),
                "title":
                    f"{team_a} - {team_b}",
                "source_name":
                    "FajerSportOfficialTelegramNow",
                "source":
                    "https://t.me/fajersport",
                "duration_minutes":
                    135,
                "time_type":
                    "observed-now",
            }
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
            urls.append(
                m.group(1)
            )

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

    for img in msg.select(
        "img[src]"
    ):

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
        dict.fromkeys(
            urls
        )
    )


def dedupe(events):
    rank = {
        "scheduled-image": 3,
        "scheduled": 2,
        "observed-now": 1,
    }

    chosen = {}

    for event in events:

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
            chosen[key].get(
                "time_type"
            ),
            0,
        )

        new_rank = rank.get(
            event.get(
                "time_type"
            ),
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
                post_time = (
                    post_time.replace(
                        tzinfo=UTC
                    )
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

        events.extend(
            parse_now(
                text,
                post_time,
            )
        )

        for image_url in image_urls(
            msg
        ):

            if image_url in seen_images:
                continue

            seen_images.add(
                image_url
            )

            try:
                data = fetch(
                    image_url,
                    True,
                )

                if len(data) < 10000:
                    continue

                im = Image.open(
                    io.BytesIO(data)
                ).convert(
                    "RGB"
                )

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

    return dedupe(events)


def collect():
    for url in TELEGRAM_URLS:

        try:
            html = fetch(url)

            events = (
                parse_telegram_html(
                    html
                )
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

    for n in range(
        1,
        6,
    ):

        (
            channel_id,
            channel_name,
        ) = CHANNELS[n]

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
        ).text = (
            f"Fajer Sport {n}"
        )

    for event in events:

        start = (
            event["start"]
            .astimezone(UTC)
        )

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
            start=xmltv_time(
                start
            ),
            stop=xmltv_time(
                stop
            ),
            channel=event[
                "channel_id"
            ],
        )

        ET.SubElement(
            programme,
            "title",
            lang="ar",
        ).text = event[
            "title"
        ]

        ET.SubElement(
            programme,
            "category",
            lang="en",
        ).text = "Sports"

        local = start.astimezone(
            PALESTINE
        )

        ET.SubElement(
            programme,
            "desc",
            lang="ar",
        ).text = (
            f"{event['channel_name']}\n"
            f"{local:%Y-%m-%d %H:%M} "
            "بتوقيت فلسطين\n"
            "المصدر: إعلان فجر سبورت "
            "الرسمي "
            f"({event['source_name']})"
        )

    ET.indent(
        root,
        space="  ",
    )

    ET.ElementTree(
        root
    ).write(
        OUTPUT,
        encoding="utf-8",
        xml_declaration=True,
    )

    # Validate generated XML
    ET.parse(
        OUTPUT
    )

    log(
        "Written and XML-validated: "
        f"{OUTPUT}"
    )


# ============================================================
# LOCAL POSTER TEST
# ============================================================

def test_image(path):
    im = Image.open(
        path
    ).convert(
        "RGB"
    )

    fake_post_time = datetime(
        2026,
        8,
        19,
        8,
        0,
        tzinfo=UTC,
    )

    old_in_window = globals()[
        "in_window"
    ]

    globals()[
        "in_window"
    ] = lambda x: True

    try:
        events = parse_poster(
            im,
            fake_post_time,
            "local-test",
        )

    finally:
        globals()[
            "in_window"
        ] = old_in_window

    got = {
        (
            event["channel_num"],
            event["start"]
            .astimezone(
                PALESTINE
            )
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

    if not expected.issubset(
        got
    ):
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
        "channels 1-5 | "
        "UTC XMLTV | "
        "fail-safe skip on unreadable cards"
    )

    if (
        len(sys.argv) > 2
        and
        sys.argv[1]
        == "--test-image"
    ):

        test_image(
            sys.argv[2]
        )

        log(
            "SELF TEST IMAGE | PASS"
        )

        return

    events = collect()

    write_xml(
        events
    )


if __name__ == "__main__":
    main()
