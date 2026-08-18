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


TZ = ZoneInfo("Asia/Riyadh")

THMANYAH_OUT = Path("thmanyah_epg.xml")
ALWAN_OUT = Path("alwan_sports_epg.xml")

THMANYAH_SOURCES = [
    "https://www.kooora.com/",
    "https://www.365scores.com/ar/news/magazine/",
    "https://app.thmanyah.com/",
]

ALWAN_TELEGRAM = "https://t.me/s/AlwanSports"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

THMANYAH_RE = re.compile(
    r"(?:ثمانية|thmanyah)\s*(1|2|3)",
    re.I
)

TIME_RE = re.compile(
    r"\b([01]?\d|2[0-3])[:\.]([0-5]\d)\b"
)


def norm(value):
    return re.sub(
        r"\s+",
        " ",
        html.unescape(value or "")
    ).strip()


def get(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=35
    )
    response.raise_for_status()
    return response.text
def parse_date_from_text(text):
    now = datetime.now(TZ)
    low = text.lower()

    if "اليوم" in low:
        return now.date()

    if "غداً" in low or "غدا" in low:
        return (now + timedelta(days=1)).date()

    m = re.search(
        r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b",
        text
    )

    if m:
        day, month, year = map(int, m.groups())

        try:
            return datetime(
                year,
                month,
                day,
                tzinfo=TZ
            ).date()
        except ValueError:
            return None

    arabic_months = {
        "يناير": 1,
        "فبراير": 2,
        "مارس": 3,
        "أبريل": 4,
        "ابريل": 4,
        "مايو": 5,
        "يونيو": 6,
        "يوليو": 7,
        "أغسطس": 8,
        "اغسطس": 8,
        "سبتمبر": 9,
        "أكتوبر": 10,
        "اكتوبر": 10,
        "نوفمبر": 11,
        "ديسمبر": 12,
    }

    months_pattern = "|".join(
        map(re.escape, arabic_months.keys())
    )

    m = re.search(
        rf"\b(\d{{1,2}})\s+({months_pattern})\s+(20\d{{2}})\b",
        text,
        re.I
    )

    if m:
        day = int(m.group(1))
        month = arabic_months[m.group(2)]
        year = int(m.group(3))

        try:
            return datetime(
                year,
                month,
                day,
                tzinfo=TZ
            ).date()
        except ValueError:
            return None

    return None


def find_match_title(lines, index):
    candidates = []

    for j in range(
        max(0, index - 5),
        min(len(lines), index + 6)
    ):
        candidate = norm(lines[j])

        if not candidate:
            continue

        if THMANYAH_RE.search(candidate):
            continue

        if TIME_RE.fullmatch(candidate):
            continue

        if (
            " - " in candidate
            or " – " in candidate
            or " vs " in candidate.lower()
        ):
            candidates.append(candidate)

    if candidates:
        return candidates[0]

    return None

def discover_kooora_daily_pages():
    urls = []
    seen = set()

    try:
        soup = BeautifulSoup(
            get("https://www.kooora.com/"),
            "html.parser"
        )
    except Exception as exc:
        print(
            f"WARN Kooora discovery failed: {exc}",
            file=sys.stderr
        )
        return []

    for a in soup.find_all("a", href=True):
        title = norm(
            a.get_text(" ", strip=True)
        )

        if "جدول مباريات اليوم" not in title:
            continue

        url = urljoin(
            "https://www.kooora.com/",
            a["href"]
        ).split("#", 1)[0]

        if url in seen:
            continue

        seen.add(url)
        urls.append(url)

    print(
        f"Kooora daily schedule pages discovered: "
        f"{len(urls)}"
    )

    return urls[:10]
def parse_thmanyah_page(url):
    try:
        soup = BeautifulSoup(
            get(url),
            "html.parser"
        )
    except Exception as exc:
        print(
            f"WARN Thmanyah source failed {url}: {exc}",
            file=sys.stderr
        )
        return []

    text = soup.get_text(
        "\n",
        strip=True
    )

    lines = [
        norm(x)
        for x in text.splitlines()
        if norm(x)
    ]

    events = []
    current_date = None

    for i, line in enumerate(lines):
        d = parse_date_from_text(line)

        if d:
            current_date = d

        cm = THMANYAH_RE.search(line)

        if not cm:
            continue

        tm = TIME_RE.search(line)

        if not tm:
            nearby = " ".join(
                lines[
                    max(0, i - 4):
                    min(len(lines), i + 5)
                ]
            )
            tm = TIME_RE.search(nearby)

        if not tm:
            continue

        title = find_match_title(
            lines,
            i
        )

        if not title:
            continue

        day = current_date or datetime.now(TZ).date()

        start = datetime(
            day.year,
            day.month,
            day.day,
            int(tm.group(1)),
            int(tm.group(2)),
            tzinfo=TZ
        )

        events.append({
            "channel": int(cm.group(1)),
            "start": start,
            "title": title,
            "source": url,
        })

    return events
def parse_alwan_telegram():
    try:
        soup = BeautifulSoup(
            get(ALWAN_TELEGRAM),
            "html.parser"
        )
    except Exception as exc:
        print(
            f"WARN Alwan Telegram failed: {exc}",
            file=sys.stderr
        )
        return []

    posts = soup.select(
        ".tgme_widget_message_text"
    )

    events = []
    now = datetime.now(TZ)

    for post in posts:
        text = norm(
            post.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        if "الوان" not in text and "ألوان" not in text:
            continue

        tm = TIME_RE.search(text)

        if not tm:
            continue

        day = parse_date_from_text(text)

        if not day:
            day = now.date()

        title = None

        parts = re.split(
            r"\s+[|•]\s+|\n",
            text
        )

        for part in parts:
            part = norm(part)

            if (
                " - " in part
                or " – " in part
                or " vs " in part.lower()
            ):
                title = part
                break

        if not title:
            continue

        events.append({
            "channel": 1,
            "start": datetime(
                day.year,
                day.month,
                day.day,
                int(tm.group(1)),
                int(tm.group(2)),
                tzinfo=TZ
            ),
            "title": title,
            "source": ALWAN_TELEGRAM,
        })

    return events


def dedupe(events):
    out = []
    seen = set()

    for e in sorted(
        events,
        key=lambda x: (
            x["start"],
            x["channel"],
            x["title"].lower()
        )
    ):
        key = (
            e["channel"],
            e["start"].strftime("%Y%m%d%H%M"),
            e["title"].lower()
        )

        if key in seen:
            continue

        seen.add(key)
        out.append(e)

    return out
def write_thmanyah_xml(events):
    tv = ET.Element(
        "tv",
        {
            "generator-info-name":
                "Thmanyah Sports EPG"
        }
    )

    for n in range(1, 4):
        channel = ET.SubElement(
            tv,
            "channel",
            {
                "id": f"Thmanyah{n}.sa"
            }
        )

        ET.SubElement(
            channel,
            "display-name",
            {"lang": "ar"}
        ).text = f"ثمانية {n}"

        ET.SubElement(
            channel,
            "display-name",
            {"lang": "en"}
        ).text = f"Thmanyah {n}"

    for event in events:
        programme = ET.SubElement(
            tv,
            "programme",
            {
                "start":
                    event["start"].strftime(
                        "%Y%m%d%H%M%S %z"
                    ),
                "stop":
                    (
                        event["start"]
                        + timedelta(hours=3)
                    ).strftime(
                        "%Y%m%d%H%M%S %z"
                    ),
                "channel":
                    f"Thmanyah{event['channel']}.sa",
            }
        )

        ET.SubElement(
            programme,
            "title",
            {"lang": "ar"}
        ).text = event["title"]

        ET.SubElement(
            programme,
            "category",
            {"lang": "en"}
        ).text = "Sports"

        ET.SubElement(
            programme,
            "desc",
            {"lang": "ar"}
        ).text = (
            f"المصدر: {event['source']}"
        )

    ET.indent(tv, space="  ")

    ET.ElementTree(tv).write(
        THMANYAH_OUT,
        encoding="utf-8",
        xml_declaration=True
    )


def write_alwan_xml(events):
    tv = ET.Element(
        "tv",
        {
            "generator-info-name":
                "Alwan Sports EPG"
        }
    )

    channel = ET.SubElement(
        tv,
        "channel",
        {
            "id": "AlwanSports"
        }
    )

    ET.SubElement(
        channel,
        "display-name",
        {"lang": "ar"}
    ).text = "ألوان الرياضية"

    ET.SubElement(
        channel,
        "display-name",
        {"lang": "en"}
    ).text = "Alwan Sports"

    for event in events:
        programme = ET.SubElement(
            tv,
            "programme",
            {
                "start":
                    event["start"].strftime(
                        "%Y%m%d%H%M%S %z"
                    ),
                "stop":
                    (
                        event["start"]
                        + timedelta(hours=3)
                    ).strftime(
                        "%Y%m%d%H%M%S %z"
                    ),
                "channel": "AlwanSports",
            }
        )

        ET.SubElement(
            programme,
            "title",
            {"lang": "ar"}
        ).text = event["title"]

        ET.SubElement(
            programme,
            "category",
            {"lang": "en"}
        ).text = "Sports"

        ET.SubElement(
            programme,
            "desc",
            {"lang": "ar"}
        ).text = (
            f"المصدر: {event['source']}"
        )

    ET.indent(tv, space="  ")

    ET.ElementTree(tv).write(
        ALWAN_OUT,
        encoding="utf-8",
        xml_declaration=True
    )
def main():
        thmanyah_events = []

        thmanyah_sources = THMANYAH_SOURCES + discover_kooora_daily_pages()

        for source in dict.fromkeys(thmanyah_sources):
            try:
            for source in dict.fromkeys(thmanyah_sources):
        try:
            found = parse_thmanyah_page(source)

            if found:
                print(
                    f"THMANYAH source {source} -> "
                    f"{len(found)} event(s)"
                )
                thmanyah_events.extend(found)

        except Exception as exc:
            print(
                f"WARN Thmanyah source failed "
                f"{source}: {exc}",
                file=sys.stderr
            )
    thmanyah_events = dedupe(
        thmanyah_events
    )

    print(
        f"Thmanyah programmes detected: "
        f"{len(thmanyah_events)}"
    )

    for event in thmanyah_events:
        print(
            f"  Thmanyah "
            f"{event['channel']} | "
            f"{event['start']:%Y-%m-%d %H:%M} | "
            f"{event['title']}"
        )

    alwan_events = parse_alwan_telegram()

    alwan_events = dedupe(
        alwan_events
    )

    print(
        f"Alwan programmes detected: "
        f"{len(alwan_events)}"
    )

    for event in alwan_events:
        print(
            f"  ALWAN | "
            f"{event['start']:%Y-%m-%d %H:%M} | "
            f"{event['title']}"
        )

    write_thmanyah_xml(
        thmanyah_events
    )

    write_alwan_xml(
        alwan_events
    )

    print(
        f"Written: {THMANYAH_OUT}"
    )

    print(
        f"Written: {ALWAN_OUT}"
    )


if __name__ == "__main__":
    main()  
