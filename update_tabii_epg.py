#!/usr/bin/env python3

import re
import html
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET


TZ = ZoneInfo("Europe/Istanbul")

# KEEP THIS NAME because your GitHub workflow already commits this file
OUT = Path("tabii_spor_1_7_epg.xml")

INDEX_URLS = [
    "https://www.trtspor.com.tr/haberleri/tabii-spor",
    "https://www.trtspor.com.tr/haberleri/tabii",
    "https://www.trtspor.com.tr/haberleri/tabii-5620",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TabiiXMLTV/4.0; GitHub-Actions)"
}

MONTHS = {
    "ocak": 1,
    "şubat": 2,
    "subat": 2,
    "mart": 3,
    "nisan": 4,
    "mayıs": 5,
    "mayis": 5,
    "haziran": 6,
    "temmuz": 7,
    "ağustos": 8,
    "agustos": 8,
    "eylül": 9,
    "eylul": 9,
    "ekim": 10,
    "kasım": 11,
    "kasim": 11,
    "aralık": 12,
    "aralik": 12,
}

CHANNEL_RE = re.compile(
    r"\bTAB(?:İ|I)İ?\s*SPOR\s*(10|[1-9])\b",
    re.IGNORECASE,
)

TIME_RE = re.compile(
    r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b"
)

DATE_NUM_RE = re.compile(
    r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b"
)

DATE_TEXT_RE = re.compile(
    r"\b(\d{1,2})\s+([a-zçğıöşü]+)(?:\s+(\d{4}))?\b",
    re.IGNORECASE,
)


def get(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    return response.text


def normalize(text):
    return re.sub(
        r"\s+",
        " ",
        html.unescape(text or ""),
    ).strip()


def discover_articles():

    links = []
    seen = set()

    for index_url in INDEX_URLS:

        try:
            soup = BeautifulSoup(
                get(index_url),
                "html.parser",
            )

        except Exception as exc:
            print(
                f"WARNING index failed: {index_url}: {exc}",
                file=sys.stderr,
            )
            continue

        for a in soup.find_all("a", href=True):

            href = urljoin(
                index_url,
                a["href"],
            )

            if "/haber/" not in href:
                continue

            if href in seen:
                continue

            seen.add(href)
            links.append(href)

    print(
        f"TRT articles discovered: {len(links)}"
    )

    return links[:150]


def parse_absolute_date(text, default_year=None):

    if default_year is None:
        default_year = datetime.now(TZ).year

    match = DATE_NUM_RE.search(text)

    if match:

        day, month, year = map(
            int,
            match.groups(),
        )

        try:
            return datetime(
                year,
                month,
                day,
                tzinfo=TZ,
            ).date()

        except ValueError:
            pass

    match = DATE_TEXT_RE.search(
        text.lower()
    )

    if (
        match
        and match.group(2) in MONTHS
    ):

        day = int(match.group(1))
        month = MONTHS[match.group(2)]

        year = (
            int(match.group(3))
            if match.group(3)
            else default_year
        )

        try:
            candidate = datetime(
                year,
                month,
                day,
                tzinfo=TZ,
            )

        except ValueError:
            return None

        now = datetime.now(TZ)

        if not match.group(3):

            if candidate < now - timedelta(days=150):
                candidate = candidate.replace(
                    year=year + 1
                )

            elif candidate > now + timedelta(days=300):
                candidate = candidate.replace(
                    year=year - 1
                )

        return candidate.date()

    return None


def article_data(url):

    soup = BeautifulSoup(
        get(url),
        "html.parser",
    )

    blocks = []

    published_date = None

    # Read publication date from metadata
    for meta in soup.find_all("meta"):

        key = " ".join([
            str(meta.get("name", "")),
            str(meta.get("property", "")),
            str(meta.get("itemprop", "")),
        ]).lower()

        value = meta.get("content")

        if not value:
            continue

        if any(
            x in key
            for x in (
                "published",
                "datepublished",
                "publication",
                "article:published",
            )
        ):

            parsed = parse_absolute_date(
                value
            )

            if parsed:
                published_date = parsed
                break

    # Title
    if soup.title:
        blocks.append(
            normalize(
                soup.title.get_text(
                    " ",
                    strip=True,
                )
            )
        )

    # Visible article text
    for tag in soup.find_all(
        [
            "h1",
            "h2",
            "h3",
            "h4",
            "p",
            "li",
            "div",
            "span",
        ]
    ):

        text = normalize(
            tag.get_text(
                " ",
                strip=True,
            )
        )

        if (
            text
            and len(text) <= 1200
        ):
            blocks.append(text)

    # Remove duplicates
    unique = []
    seen = set()

    for block in blocks:

        if block in seen:
            continue

        seen.add(block)
        unique.append(block)

    # If metadata did not work, try text near top
    if not published_date:

        for block in unique[:50]:

            date = parse_absolute_date(
                block
            )

            if date:
                published_date = date
                break

    return unique, published_date


def resolve_date(
    text,
    published_date,
):

    # Explicit date wins
    explicit = parse_absolute_date(
        text
    )

    if explicit:
        return explicit

    if not published_date:
        return None

    low = text.lower()

    if "bugün" in low or "bugun" in low:
        return published_date

    if "yarın" in low or "yarin" in low:
        return (
            published_date
            + timedelta(days=1)
        )

    return published_date


def find_context_date(
    blocks,
    index,
    published_date,
):

    # Search current and previous blocks
    for i in range(
        index,
        max(-1, index - 25),
        -1,
    ):

        explicit = parse_absolute_date(
            blocks[i]
        )

        if explicit:
            return explicit

        low = blocks[i].lower()

        if (
            "bugün" in low
            or "bugun" in low
        ) and published_date:

            return published_date

        if (
            "yarın" in low
            or "yarin" in low
        ) and published_date:

            return (
                published_date
                + timedelta(days=1)
            )

    return published_date


def clean_title(text):

    text = CHANNEL_RE.sub(
        "",
        text,
    )

    text = TIME_RE.sub(
        "",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip(
        " -–—:|"
    )


def choose_title(
    blocks,
    index,
):

    candidates = [
        blocks[index]
    ]

    for distance in (1, 2, 3):

        if index - distance >= 0:
            candidates.append(
                blocks[index - distance]
            )

        if index + distance < len(blocks):
            candidates.append(
                blocks[index + distance]
            )

    for candidate in candidates:

        title = clean_title(
            candidate
        )

        if len(title) < 4:
            continue

        if len(title) > 250:
            continue

        low = title.lower()

        bad = [
            "kullanım koşulları",
            "gizlilik politikası",
            "çerez politikası",
            "iletişim",
            "telif",
        ]

        if any(
            word in low
            for word in bad
        ):
            continue

        return title

    return "Tabii Spor"


def parse_article(url):

    blocks, published_date = article_data(
        url
    )

    if not blocks:
        return []

    events = []

    now = datetime.now(TZ)

    for index, block in enumerate(
        blocks
    ):

        channel_match = CHANNEL_RE.search(
            block
        )

        if not channel_match:
            continue

        channel = int(
            channel_match.group(1)
        )

        # Context around the channel mention
        context_blocks = blocks[
            max(0, index - 4):
            min(len(blocks), index + 5)
        ]

        context = " | ".join(
            context_blocks
        )

        # Time: same block first, nearby text second
        time_match = TIME_RE.search(
            block
        )

        if not time_match:
            time_match = TIME_RE.search(
                context
            )

        if not time_match:
            continue

        date = resolve_date(
            block,
            published_date,
        )

        if not date:
            date = find_context_date(
                blocks,
                index,
                published_date,
            )

        if not date:
            continue

        hour = int(
            time_match.group(1)
        )

        minute = int(
            time_match.group(2)
        )

        start = datetime(
            date.year,
            date.month,
            date.day,
            hour,
            minute,
            tzinfo=TZ,
        )

        # Only useful current EPG
        if start < now - timedelta(days=2):
            continue

        if start > now + timedelta(days=45):
            continue

        title = choose_title(
            blocks,
            index,
        )

        events.append({
            "channel": channel,
            "start": start,
            "title": title,
            "source": url,
        })

    return events


def deduplicate(events):

    output = []
    seen = set()

    for event in sorted(
        events,
        key=lambda e: (
            e["start"],
            e["channel"],
            e["title"].lower(),
        ),
    ):

        key = (
            event["channel"],
            event["start"].isoformat(),
            event["title"].lower(),
        )

        if key in seen:
            continue

        seen.add(key)
        output.append(event)

    return output


def xml_time(dt):

    return dt.strftime(
        "%Y%m%d%H%M%S %z"
    )


def create_xml(events):

    tv = ET.Element(
        "tv",
        {
            "generator-info-name":
                "Tabii Spor 1-10 TRT XMLTV",
            "generator-info-url":
                "https://www.trtspor.com.tr/",
        },
    )

    # TABII SPOR 1 THROUGH 10
    for number in range(
        1,
        11,
    ):

        channel = ET.SubElement(
            tv,
            "channel",
            {
                "id":
                    f"TabiiSpor{number}.tr"
            },
        )

        ET.SubElement(
            channel,
            "display-name",
            {"lang": "tr"},
        ).text = (
            f"Tabii Spor {number}"
        )

        ET.SubElement(
            channel,
            "display-name",
        ).text = (
            f"tabii Spor {number}"
        )

    for event in events:

        stop = (
            event["start"]
            + timedelta(
                hours=2,
                minutes=30,
            )
        )

        programme = ET.SubElement(
            tv,
            "programme",
            {
                "start":
                    xml_time(
                        event["start"]
                    ),
                "stop":
                    xml_time(stop),
                "channel":
                    f"TabiiSpor{event['channel']}.tr",
            },
        )

        ET.SubElement(
            programme,
            "title",
            {"lang": "tr"},
        ).text = event["title"]

        ET.SubElement(
            programme,
            "category",
            {"lang": "en"},
        ).text = "Sports"

        ET.SubElement(
            programme,
            "desc",
            {"lang": "tr"},
        ).text = (
            "Kaynak: TRT | "
            + event["source"]
        )

    ET.indent(
        tv,
        space="  ",
    )

    return ET.ElementTree(tv)


def main():

    article_links = discover_articles()

    all_events = []

    for url in article_links:

        try:

            events = parse_article(
                url
            )

            if events:

                print(
                    f"{url} -> "
                    f"{len(events)} programme(s)"
                )

                all_events.extend(
                    events
                )

        except Exception as exc:

            print(
                f"WARNING article failed: "
                f"{url}: {exc}",
                file=sys.stderr,
            )

    events = deduplicate(
        all_events
    )

    print(
        "TOTAL Tabii Spor 1-10 "
        f"programmes: {len(events)}"
    )

    # CRITICAL:
    # Never overwrite the EPG with an empty file.
    if not events:

        print(
            "ERROR: TRT currently returned "
            "no usable numbered Tabii Spor "
            "programme assignments. "
            "Existing EPG was NOT overwritten.",
            file=sys.stderr,
        )

        sys.exit(2)

    tree = create_xml(
        events
    )

    tree.write(
        OUT,
        encoding="utf-8",
        xml_declaration=True,
    )

    print(
        f"EPG successfully written: {OUT}"
    )

    for event in events:

        print(
            f"Tabii Spor "
            f"{event['channel']} | "
            f"{event['start'].strftime('%Y-%m-%d %H:%M')} | "
            f"{event['title']}"
        )


if __name__ == "__main__":
    main()
