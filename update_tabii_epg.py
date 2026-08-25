#!/usr/bin/env python3

import re
import html
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET


TZ = ZoneInfo("Europe/Istanbul")
OUT = Path("tabii_spor_1_10_epg.xml")

TRT_SCHEDULE_URL = "https://www.trtspor.com.tr/yayin-akisi/tabii-spor"

TRT_NEWS_INDEX_URLS = [
    "https://www.trtspor.com.tr/",
    "https://www.trtspor.com.tr/haberleri/tabii-spor",
    "https://www.trtspor.com.tr/haberleri/tabii",
]

SPOREKRANI_INDEX_URLS = [
    "https://www.sporekrani.com/",
    "https://www.sporekrani.com/home/sport/futbol",
    "https://www.sporekrani.com/home/league/uefa-sampiyonlar-ligi",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

CHANNEL_RE = re.compile(
    r"\b(?:TRT\s*)?TAB(?:İ|I)İ?\s*SPOR\s*(10|[1-9])\b",
    re.I,
)

TIME_RE = re.compile(
    r"\b([01]?\d|2[0-3])[\.:]([0-5]\d)\b"
)

DATE_IN_URL_RE = re.compile(
    r"/(20\d{2})/(\d{2})/(\d{2})/"
)

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

WEEKDAYS = {
    "pazartesi": 0,
    "salı": 1,
    "sali": 1,
    "çarşamba": 2,
    "carsamba": 2,
    "perşembe": 3,
    "persembe": 3,
    "cuma": 4,
    "cumartesi": 5,
    "pazar": 6,
}


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


def explicit_date(text, base_year):
    m = re.search(
        r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b",
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
            pass

    month_rx = "|".join(
        map(re.escape, MONTHS)
    )

    m = re.search(
        rf"\b(\d{{1,2}})\s+({month_rx})(?:\s+(20\d{{2}}))?\b",
        text.lower(),
        re.I
    )

    if m:
        day = int(m.group(1))
        month = MONTHS[m.group(2).lower()]
        year = int(m.group(3) or base_year)

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
def date_from_context(text, fallback_date=None):
    base = fallback_date or datetime.now(TZ).date()

    d = explicit_date(
        text,
        base.year
    )

    if d:
        return d

    low = text.lower()

    if "bugün" in low or "bugun" in low:
        return base

    if "yarın" in low or "yarin" in low:
        return base + timedelta(days=1)

    for name, weekday in WEEKDAYS.items():
        if re.search(
            rf"\b{re.escape(name)}\b",
            low
        ):
            return base + timedelta(
                days=(
                    weekday
                    - base.weekday()
                ) % 7
            )

    return fallback_date


def clean_title(value):
    value = CHANNEL_RE.sub(
        "",
        value
    )

    value = TIME_RE.sub(
        "",
        value
    )

    value = re.sub(
        r"\b(?:TSİ|TSI)\b",
        "",
        value,
        flags=re.I
    )

    value = re.sub(
        r"\s*(?:->|→|[-–—|:])+\s*$",
        "",
        value
    )

    value = re.sub(
        r"^\s*(?:->|→|[-–—|:])+\s*",
        "",
        value
    )

    return norm(value)


def parse_published_date(soup):
    for tag in soup.find_all(
        "script",
        type="application/ld+json"
    ):
        raw = tag.string or tag.get_text()

        if not raw:
            continue

        try:
            data = json.loads(raw)
        except Exception:
            continue

        stack = (
            data
            if isinstance(data, list)
            else [data]
        )

        while stack:
            obj = stack.pop()

            if isinstance(obj, list):
                stack.extend(obj)
                continue

            if not isinstance(obj, dict):
                continue

            for key in (
                "datePublished",
                "dateCreated",
                "uploadDate"
            ):
                value = obj.get(key)

                if not value:
                    continue

                try:
                    dt = datetime.fromisoformat(
                        str(value).replace(
                            "Z",
                            "+00:00"
                        )
                    )

                    if dt.tzinfo is None:
                        dt = dt.replace(
                            tzinfo=TZ
                        )

                    return dt.astimezone(
                        TZ
                    ).date()

                except Exception:
                    pass

            for value in obj.values():
                if isinstance(
                    value,
                    (dict, list)
                ):
                    stack.append(value)

    return None


def page_lines(url):
    soup = BeautifulSoup(
        get(url),
        "html.parser"
    )

    text = soup.get_text(
        "\n",
        strip=True
    )

    lines = [
        norm(x)
        for x in text.splitlines()
        if norm(x)
    ]

    return soup, lines
def parse_general_schedule():
    try:
        _, lines = page_lines(
            TRT_SCHEDULE_URL
        )

    except Exception as exc:
        print(
            f"WARN official TRT schedule failed: {exc}",
            file=sys.stderr
        )
        return []

    today = datetime.now(TZ).date()
    entries = []

    for i, line in enumerate(lines):
        tm = TIME_RE.fullmatch(line)

        if not tm:
            continue

        title = None

        for j in range(
            i + 1,
            min(
                len(lines),
                i + 5
            )
        ):
            candidate = lines[j]

            if not candidate:
                continue

            if TIME_RE.fullmatch(
                candidate
            ):
                continue

            if candidate.lower() in {
                "yayın akışı",
                "yayin akisi"
            }:
                continue

            title = candidate
            break

        if not title:
            continue

        start = datetime(
            today.year,
            today.month,
            today.day,
            int(tm.group(1)),
            int(tm.group(2)),
            tzinfo=TZ
        )

        entries.append({
            "start": start,
            "title": title,
            "source": TRT_SCHEDULE_URL,
        })

    print(
        f"Official Tabii Spor schedule entries: "
        f"{len(entries)}"
    )

    for e in entries[:30]:
        print(
            f"  GENERAL | "
            f"{e['start']:%Y-%m-%d %H:%M} | "
            f"{e['title']}"
        )

    return entries


def discover_sporekrani_match_pages():
    urls = []
    seen = set()

    for index_url in SPOREKRANI_INDEX_URLS:
        try:
            soup = BeautifulSoup(
                get(index_url),
                "html.parser"
            )

        except Exception as exc:
            print(
                f"WARN Spor Ekrani index failed "
                f"{index_url}: {exc}",
                file=sys.stderr
            )
            continue

        for a in soup.find_all(
            "a",
            href=True
        ):
            url = urljoin(
                index_url,
                a["href"]
            ).split("#", 1)[0]

            if "/home/match/" not in url:
                continue

            if url in seen:
                continue

            seen.add(url)
            urls.append(url)

    print(
        f"Spor Ekrani match pages discovered: "
        f"{len(urls)}"
    )

    return urls[:150]


def date_from_sporekrani_url(url):
    m = DATE_IN_URL_RE.search(url)

    if not m:
        return None

    year, month, day = map(
        int,
        m.groups()
    )

    try:
        return datetime(
            year,
            month,
            day,
            tzinfo=TZ
        ).date()

    except ValueError:
        return None
def title_from_sporekrani_page(soup):
    h1 = soup.find("h1")

    if h1:
        title = norm(
            h1.get_text(
                " ",
                strip=True
            )
        )

        title = re.sub(
            r"\s+Hangi\s+Kanalda.*$",
            "",
            title,
            flags=re.I
        )

        if title:
            return title

    og = soup.find(
        "meta",
        property="og:title"
    )

    if og and og.get("content"):
        title = norm(
            og["content"]
        )

        title = re.sub(
            r"\s+Hangi\s+Kanalda.*$",
            "",
            title,
            flags=re.I
        )

        if title:
            return title

    if soup.title:
        title = norm(
            soup.title.get_text(
                " ",
                strip=True
            )
        )

        title = re.sub(
            r"\s+Hangi\s+Kanalda.*$",
            "",
            title,
            flags=re.I
        )

        return title

    return None


def parse_sporekrani_match_page(url):
    try:
        soup, lines = page_lines(url)

    except Exception as exc:
        print(
            f"WARN Spor Ekrani match failed "
            f"{url}: {exc}",
            file=sys.stderr
        )
        return None

    joined = "\n".join(lines)

    cm = CHANNEL_RE.search(joined)

    if not cm:
        return None

    channel = int(
        cm.group(1)
    )

    day = date_from_sporekrani_url(
        url
    )

    if not day:
        day = date_from_context(
            joined,
            datetime.now(TZ).date()
        )

    if not day:
        return None

    tm = TIME_RE.search(joined)

    if not tm:
        return None

    title = title_from_sporekrani_page(
        soup
    )

    if not title:
        for line in lines:
            if (
                " - " in line
                or " – " in line
            ):
                candidate = clean_title(
                    line
                )

                if (
                    5 <= len(candidate) <= 180
                ):
                    title = candidate
                    break

    if not title:
        return None

    start = datetime(
        day.year,
        day.month,
        day.day,
        int(tm.group(1)),
        int(tm.group(2)),
        tzinfo=TZ
    )

    now = datetime.now(TZ)

    if not (
        now - timedelta(days=2)
        <= start
        <= now + timedelta(days=45)
    ):
        return None

    return {
        "channel": channel,
        "start": start,
        "title": title,
        "source": url,
    }


def parse_sporekrani():
    events = []

    for url in discover_sporekrani_match_pages():
        event = parse_sporekrani_match_page(
            url
        )

        if not event:
            continue

        print(
            f"  SPOR EKRANI | "
            f"Tabii Spor {event['channel']} | "
            f"{event['start']:%Y-%m-%d %H:%M} | "
            f"{event['title']}"
        )

        events.append(event)

    events = dedupe(events)

    print(
        f"Spor Ekrani numbered programmes: "
        f"{len(events)}"
    )

    return events
    
def discover_news_articles():
    links = []
    seen = set()

    for index_url in TRT_NEWS_INDEX_URLS:
        try:
            soup = BeautifulSoup(
                get(index_url),
                "html.parser"
            )

        except Exception as exc:
            print(
                f"WARN TRT index failed "
                f"{index_url}: {exc}",
                file=sys.stderr
            )
            continue

        for a in soup.find_all(
            "a",
            href=True
        ):
            url = urljoin(
                index_url,
                a["href"]
            ).split("#", 1)[0]

            if "/haber/" not in url:
                continue

            if url in seen:
                continue

            seen.add(url)
            links.append(url)

    print(
        f"TRT news article links discovered: "
        f"{len(links)}"
    )

    return links[:250]


def parse_news_article(url):
    raw = get(url)

    soup = BeautifulSoup(
        raw,
        "html.parser"
    )

    h1 = soup.find("h1")

    if h1:
        page_title = norm(
            h1.get_text(
                " ",
                strip=True
            )
        )
    else:
        page_title = norm(
            soup.title.get_text(
                " ",
                strip=True
            )
            if soup.title
            else ""
        )

    published = parse_published_date(
        soup
    )

    text = soup.get_text(
        "\n",
        strip=True
    )

    lines = [
        norm(x)
        for x in text.splitlines()
        if norm(x)
    ]

    joined = "\n".join(lines)

    if not CHANNEL_RE.search(
        page_title + "\n" + joined
    ):
        return []

    now = datetime.now(TZ)
    found = []

    for i, line in enumerate(lines):
        cm = CHANNEL_RE.search(line)
        tm = TIME_RE.search(line)

        if not (cm and tm):
            continue

        context = " ".join(
            lines[
                max(0, i - 10):
                min(len(lines), i + 4)
            ]
        )

        day = date_from_context(
            context,
            published
        )

        if not day:
            continue

        start = datetime(
            day.year,
            day.month,
            day.day,
            int(tm.group(1)),
            int(tm.group(2)),
            tzinfo=TZ
        )

        if not (
            now - timedelta(days=10)
            <= start
            <= now + timedelta(days=120)
        ):
            continue

        title = clean_title(line)

        if (
            len(title) < 4
            or len(title) > 220
        ):
            title = clean_title(
                page_title
            )

        found.append({
            "channel": int(cm.group(1)),
            "start": start,
            "title": title,
            "source": url,
        })

    out = []
    seen = set()

    for e in found:
        key = (
            e["channel"],
            e["start"].strftime(
                "%Y%m%d%H%M"
            ),
            e["title"].lower()
        )

        if key in seen:
            continue

        seen.add(key)
        out.append(e)

    return out
# Joins events that share a start time into one programme title, and
# splits them apart again when the guide is read back in.
MERGE_SEPARATOR = " + "


def read_existing():
    if not OUT.exists():
        return []

    try:
        root = ET.parse(
            OUT
        ).getroot()

    except Exception as exc:
        print(
            f"WARN existing XML unreadable: {exc}",
            file=sys.stderr
        )
        return []

    now = datetime.now(TZ)
    events = []

    for p in root.findall(
        "programme"
    ):
        m = re.search(
            r"TabiiSpor(10|[1-9])\.tr",
            p.get(
                "channel",
                ""
            )
        )

        if not m:
            continue

        try:
            start = datetime.strptime(
                p.get(
                    "start",
                    ""
                ),
                "%Y%m%d%H%M%S %z"
            ).astimezone(TZ)

        except Exception:
            continue

        if not (
            now - timedelta(days=14)
            <= start
            <= now + timedelta(days=150)
        ):
            continue

        title_el = p.find("title")
        desc_el = p.find("desc")

        raw_title = (
            title_el.text
            if (
                title_el is not None
                and title_el.text
            )
            else "Tabii Spor"
        )

        source = (
            desc_el.text.replace(
                "Kaynak: ",
                "",
                1
            )
            if (
                desc_el is not None
                and desc_el.text
            )
            else "saved"
        )

        # write_xml() merges events that share a start time into one
        # programme ("A + B"), so split them apart again on the way back
        # in. Without this the merged text would be re-imported as a single
        # event and merged again on the next run, growing every time.
        for part in raw_title.split(MERGE_SEPARATOR):
            part = part.strip()
            if not part:
                continue
            events.append({
                "channel": int(
                    m.group(1)
                ),
                "start": start,
                "title": part,
                "source": source,
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
            e["start"].strftime(
                "%Y%m%d%H%M"
            ),
            e["title"].lower()
        )

        if key in seen:
            continue

        seen.add(key)
        out.append(e)

    return out
def write_xml(events):
    tv = ET.Element(
        "tv",
        {
            "generator-info-name":
                "Tabii Spor 1-10 multi-source XMLTV",
            "generator-info-url":
                "https://www.trtspor.com.tr/",
        }
    )

    for n in range(1, 11):
        ch = ET.SubElement(
            tv,
            "channel",
            {
                "id":
                    f"TabiiSpor{n}.tr"
            }
        )

        ET.SubElement(
            ch,
            "display-name",
            {
                "lang":
                    "tr"
            }
        ).text = (
            f"Tabii Spor {n}"
        )

        # tabii publishes no separate mark per Spor channel, so all ten
        # carry the one brand logo rather than showing nothing.
        ET.SubElement(
            ch,
            "icon",
            {
                "src":
                    "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/logos/tabii.png"
            }
        )

    # Every event used to be written as its own <programme> with a fixed
    # 2h30m length. Two events starting together therefore produced two
    # overlapping programmes on one channel, and a long event ran straight
    # into the next one — 52 overlaps in the published guide. A player can
    # only show one programme per slot per channel, so the rest were hidden.
    #
    # Group whatever shares a start time into a single programme, then clip
    # each programme so it ends no later than the next one begins.
    slots = {}
    for e in events:
        slots.setdefault(
            (e["channel"], e["start"]),
            []
        ).append(e)

    starts_by_channel = {}
    for channel, start in slots:
        starts_by_channel.setdefault(
            channel,
            []
        ).append(start)
    for values in starts_by_channel.values():
        values.sort()

    for (channel, start), group in sorted(
        slots.items(),
        key=lambda kv: (kv[0][0], kv[0][1])
    ):
        titles = []
        for item in group:
            if item["title"] not in titles:
                titles.append(item["title"])

        stop = start + timedelta(
            hours=2,
            minutes=30
        )

        siblings = starts_by_channel[channel]
        position = siblings.index(start)
        if position + 1 < len(siblings):
            stop = min(
                stop,
                siblings[position + 1]
            )

        if stop <= start:
            continue

        e = group[0]

        p = ET.SubElement(
            tv,
            "programme",
            {
                "start":
                    start.strftime(
                        "%Y%m%d%H%M%S %z"
                    ),
                "stop":
                    stop.strftime(
                        "%Y%m%d%H%M%S %z"
                    ),
                "channel":
                    f"TabiiSpor{channel}.tr",
            }
        )

        ET.SubElement(
            p,
            "title",
            {
                "lang":
                    "tr"
            }
        ).text = MERGE_SEPARATOR.join(titles)

        ET.SubElement(
            p,
            "category",
            {
                "lang":
                    "en"
            }
        ).text = "Sports"

        ET.SubElement(
            p,
            "desc",
            {
                "lang":
                    "tr"
            }
        ).text = (
            f"Kaynak: {e['source']}"
        )

    ET.indent(
        tv,
        space="  "
    )

    ET.ElementTree(
        tv
    ).write(
        OUT,
        encoding="utf-8",
        xml_declaration=True
    )
def main():
    old = read_existing()

    print(
        f"Existing saved programmes: "
        f"{len(old)}"
    )

    general_schedule = (
        parse_general_schedule()
    )

    new = []

    sporekrani_events = (
        parse_sporekrani()
    )

    new.extend(
        sporekrani_events
    )

    matched_articles = 0

    for url in discover_news_articles():
        try:
            found = parse_news_article(
                url
            )

            if found:
                matched_articles += 1

                print(
                    f"MATCH TRT {url} -> "
                    f"{len(found)} numbered programme(s)"
                )

                for e in found:
                    print(
                        f"  TRT | "
                        f"Tabii Spor {e['channel']} | "
                        f"{e['start']:%Y-%m-%d %H:%M} | "
                        f"{e['title']}"
                    )

                new.extend(found)

        except Exception as exc:
            print(
                f"WARN TRT article failed "
                f"{url}: {exc}",
                file=sys.stderr
            )

    merged = dedupe(
        old + new
    )

    old_keys = {
        (
            e["channel"],
            e["start"].strftime(
                "%Y%m%d%H%M"
            ),
            e["title"].lower()
        )
        for e in old
    }

    new_keys = {
        (
            e["channel"],
            e["start"].strftime(
                "%Y%m%d%H%M"
            ),
            e["title"].lower()
        )
        for e in new
    }

    print(
        f"Matched TRT news articles: "
        f"{matched_articles}"
    )

    print(
        f"New numbered programmes detected: "
        f"{len(new_keys - old_keys)}"
    )

    print(
        f"Total numbered programmes kept in EPG: "
        f"{len(merged)}"
    )

    print(
        f"General schedule entries seen: "
        f"{len(general_schedule)}"
    )

    write_xml(
        merged
    )


if __name__ == "__main__":
    main()
