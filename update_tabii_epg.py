#!/usr/bin/env python3

import re
import html
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET


TZ = ZoneInfo("Europe/Istanbul")
OUT = Path("tabii_spor_1_7_epg.xml")

INDEX_URLS = [
    "https://www.trtspor.com.tr/haberleri/tabii-spor",
    "https://www.trtspor.com.tr/haberleri/tabii",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TabiiEPG/2.0; GitHub Actions)"
}


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def norm(text):
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def find_articles():
    links = []

    for index_url in INDEX_URLS:
        try:
            soup = BeautifulSoup(get(index_url), "html.parser")
        except Exception as e:
            print("Could not read:", index_url, e)
            continue

        for a in soup.find_all("a", href=True):
            href = a["href"]

            if "/haber/" not in href:
                continue

            full = urljoin(index_url, href)

            if full not in links:
                links.append(full)

    return links[:100]


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


def parse_date(text):
    text = text.lower()
    now = datetime.now(TZ)

    for month_name, month_number in MONTHS.items():
        m = re.search(
            rf"(\d{{1,2}})\s+{month_name}(?:\s+(\d{{4}}))?",
            text,
            re.I,
        )

        if m:
            day = int(m.group(1))
            year = int(m.group(2)) if m.group(2) else now.year

            try:
                dt = datetime(
                    year,
                    month_number,
                    day,
                    tzinfo=TZ,
                )

                if dt < now - timedelta(days=120):
                    dt = dt.replace(year=year + 1)

                return dt.date()

            except ValueError:
                pass

    return None


def clean_title(text):
    text = norm(text)

    text = re.sub(
        r"\bTABİİ\s*SPOR\s*[1-7]\b",
        "",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"\bTABII\s*SPOR\s*[1-7]\b",
        "",
        text,
        flags=re.I,
    )

    text = re.sub(r"\s+", " ", text)

    return text.strip(" -–—:|")


def parse_events(text):
    lines = [norm(x) for x in text.splitlines() if norm(x)]

    events = []

    channel_re = re.compile(
        r"\bTAB(?:İ|I)İ?\s*SPOR\s*([1-7])\b",
        re.I,
    )

    time_re = re.compile(
        r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b"
    )

    current_date = None

    for i, line in enumerate(lines):

        found_date = parse_date(line)
        if found_date:
            current_date = found_date

        cm = channel_re.search(line)

        if not cm:
            continue

        channel = int(cm.group(1))

        context = " ".join(
            lines[max(0, i - 3): min(len(lines), i + 4)]
        )

        date = parse_date(context) or current_date

        tm = time_re.search(context)

        if not date or not tm:
            continue

        hour = int(tm.group(1))
        minute = int(tm.group(2))

        start = datetime(
            date.year,
            date.month,
            date.day,
            hour,
            minute,
            tzinfo=TZ,
        )

        title = clean_title(line)

        if len(title) < 3:
            for nearby in lines[max(0, i - 2): i + 3]:
                candidate = clean_title(nearby)

                if (
                    len(candidate) > 5
                    and not channel_re.search(candidate)
                    and not time_re.fullmatch(candidate)
                ):
                    title = candidate
                    break

        if len(title) < 3:
            title = "Tabii Spor"

        events.append(
            {
                "channel": channel,
                "start": start,
                "title": title,
            }
        )

    return events


def collect_events():
    all_events = []

    urls = find_articles()

    print("Articles found:", len(urls))

    for url in urls:
        try:
            soup = BeautifulSoup(get(url), "html.parser")

            text = soup.get_text("\n", strip=True)

            events = parse_events(text)

            if events:
                print(url, "->", len(events))
                all_events.extend(events)

        except Exception as e:
            print("Error:", url, e)

    unique = {}

    for event in all_events:
        key = (
            event["channel"],
            event["start"],
            event["title"],
        )

        unique[key] = event

    events = list(unique.values())

    events.sort(
        key=lambda x: (
            x["start"],
            x["channel"],
        )
    )

    return events


def xml_time(dt):
    return dt.strftime("%Y%m%d%H%M%S %z")


def build_xml(events):

    tv = ET.Element(
        "tv",
        {
            "generator-info-name": "Tabii Spor EPG"
        },
    )

    for n in range(1, 8):

        channel_id = f"TabiiSpor{n}.tr"

        ch = ET.SubElement(
            tv,
            "channel",
            {"id": channel_id},
        )

        ET.SubElement(
            ch,
            "display-name",
            {"lang": "tr"},
        ).text = f"Tabii Spor {n}"

    grouped = {}

    for event in events:
        grouped.setdefault(
            event["channel"],
            [],
        ).append(event)

    for channel, items in grouped.items():

        items.sort(key=lambda x: x["start"])

        for i, event in enumerate(items):

            start = event["start"]

            if i + 1 < len(items):

                next_start = items[i + 1]["start"]

                if next_start > start:
                    stop = next_start
                else:
                    stop = start + timedelta(hours=2)

            else:
                stop = start + timedelta(hours=2)

            programme = ET.SubElement(
                tv,
                "programme",
                {
                    "start": xml_time(start),
                    "stop": xml_time(stop),
                    "channel": f"TabiiSpor{channel}.tr",
                },
            )

            ET.SubElement(
                programme,
                "title",
                {"lang": "tr"},
            ).text = event["title"]

            ET.SubElement(
                programme,
                "desc",
                {"lang": "tr"},
            ).text = f"Tabii Spor {channel}"

    tree = ET.ElementTree(tv)

    ET.indent(tree, space="  ")

    tree.write(
        OUT,
        encoding="utf-8",
        xml_declaration=True,
    )

    print()
    print("EPG created:", OUT)
    print("Events:", len(events))


def main():

    events = collect_events()

    build_xml(events)

    if not events:
        print(
            "WARNING: No events were found. "
            "XML channel definitions were still generated."
        )


if __name__ == "__main__":
    main()
