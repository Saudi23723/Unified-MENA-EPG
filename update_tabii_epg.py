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

NEWS_INDEX_URLS = [
    "https://www.trtspor.com.tr/",
    "https://www.trtspor.com.tr/haberleri/tabii-spor",
    "https://www.trtspor.com.tr/haberleri/tabii",
]

SCHEDULE_URL = "https://www.trtspor.com.tr/yayin-akisi/tabii-spor"
SPOREKRANI_URLS = [
    "https://www.sporekrani.com/",
    "https://www.sporekrani.com/home/sport/futbol",
    "https://www.sporekrani.com/home/league/uefa-sampiyonlar-ligi",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TabiiSporXMLTV/7.0; GitHub-Actions)"
}

CHANNEL_RE = re.compile(
    r"\b(?:TRT\s*)?TAB(?:İ|I)İ?\s*SPOR\s*(10|[1-9])\b",
    re.I
)

TIME_RE = re.compile(
    r"\b([01]?\d|2[0-3])[\.:]([0-5]\d)\b"
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


def norm(s):
    return re.sub(
        r"\s+",
        " ",
        html.unescape(s or "")
    ).strip()


def get(url):
    r = requests.get(
        url,
        headers=HEADERS,
        timeout=35
    )

    r.raise_for_status()
    return r.text


def parse_iso_date(value):
    if not value:
        return None

    s = str(value).strip()

    try:
        dt = datetime.fromisoformat(
            s.replace("Z", "+00:00")
        )

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)

        return dt.astimezone(TZ).date()

    except Exception:
        pass

    m = re.search(
        r"\b(20\d{2})-(\d{2})-(\d{2})\b",
        s
    )

    if m:
        y, mo, d = map(
            int,
            m.groups()
        )

        try:
            return datetime(
                y,
                mo,
                d,
                tzinfo=TZ
            ).date()

        except ValueError:
            return None

    return None


def published_date_from_soup(soup):
    for tag in soup.find_all(
        "script",
        type="application/ld+json"
    ):
        raw = (
            tag.string
            or tag.get_text()
        )

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
                d = parse_iso_date(
                    obj.get(key)
                )

                if d:
                    return d

            for value in obj.values():
                if isinstance(
                    value,
                    (dict, list)
                ):
                    stack.append(value)

    return None


def explicit_date(text, base_year):
    m = re.search(
        r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b",
        text
    )

    if m:
        d, mo, y = map(
            int,
            m.groups()
        )

        try:
            return datetime(
                y,
                mo,
                d,
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
        d = int(
            m.group(1)
        )

        mo = MONTHS[
            m.group(2).lower()
        ]

        y = int(
            m.group(3)
            or base_year
        )

        try:
            return datetime(
                y,
                mo,
                d,
                tzinfo=TZ
            ).date()

        except ValueError:
            return None

    return None


def date_from_context(
    text,
    published
):
    base = (
        published
        or datetime.now(TZ).date()
    )

    d = explicit_date(
        text,
        base.year
    )

    if d:
        return d

    low = text.lower()

    if (
        "bugün" in low
        or "bugun" in low
    ):
        return base

    if (
        "yarın" in low
        or "yarin" in low
    ):
        return base + timedelta(
            days=1
        )

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

    return published


def clean_title(s):
    s = CHANNEL_RE.sub(
        "",
        s
    )

    s = TIME_RE.sub(
        "",
        s
    )

    s = re.sub(
        r"\b(?:TSİ|TSI)\b",
        "",
        s,
        flags=re.I
    )

    s = re.sub(
        r"\s*(?:->|→|[-–—|:])+\s*$",
        "",
        s
    )

    s = re.sub(
        r"^\s*(?:->|→|[-–—|:])+\s*",
        "",
        s
    )

    return norm(s)


def discover_news_articles():
    links = []
    seen = set()

    for index_url in NEWS_INDEX_URLS:
        try:
            soup = BeautifulSoup(
                get(index_url),
                "html.parser"
            )

        except Exception as exc:
            print(
                f"WARN index failed {index_url}: {exc}",
                file=sys.stderr
            )
            continue

        for a in soup.find_all(
            "a",
            href=True
        ):
            u = urljoin(
                index_url,
                a["href"]
            ).split("#", 1)[0]

            if (
                "/haber/" not in u
                or u in seen
            ):
                continue

            seen.add(u)
            links.append(u)

    print(
        f"TRT news article links discovered: {len(links)}"
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
        title = norm(
            h1.get_text(
                " ",
                strip=True
            )
        )
    else:
        title = norm(
            soup.title.get_text(
                " ",
                strip=True
            )
            if soup.title
            else ""
        )

    published = published_date_from_soup(
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
        title
        + "\n"
        + joined
    ):
        return []

    now = datetime.now(TZ)
    found = []

    for i, line in enumerate(lines):
        cm = CHANNEL_RE.search(
            line
        )

        tm = TIME_RE.search(
            line
        )

        if not (
            cm
            and tm
        ):
            continue

        context = " ".join(
            lines[
                max(0, i - 10):
                min(
                    len(lines),
                    i + 3
                )
            ]
        )

        d = date_from_context(
            context,
            published
        )

        if not d:
            continue

        start = datetime(
            d.year,
            d.month,
            d.day,
            int(tm.group(1)),
            int(tm.group(2)),
            tzinfo=TZ
        )

        if not (
            now - timedelta(days=14)
            <= start
            <= now + timedelta(days=120)
        ):
            continue

        event_title = clean_title(
            line
        )

        if (
            len(event_title) < 4
            or len(event_title) > 220
        ):
            event_title = clean_title(
                title
            )

        found.append({
            "channel":
                int(cm.group(1)),
            "start":
                start,
            "title":
                event_title,
            "source":
                url,
        })

    if not found:
        cm = (
            CHANNEL_RE.search(title)
            or CHANNEL_RE.search(joined)
        )

        tm = re.search(
            r"(?:TSİ|TSI)?\s*([01]?\d|2[0-3])[\.:]([0-5]\d)",
            joined,
            re.I
        )

        if cm and tm:
            d = date_from_context(
                title
                + " "
                + " ".join(
                    lines[:120]
                ),
                published
            )

            if d:
                start = datetime(
                    d.year,
                    d.month,
                    d.day,
                    int(tm.group(1)),
                    int(tm.group(2)),
                    tzinfo=TZ
                )

                if (
                    now - timedelta(days=14)
                    <= start
                    <= now + timedelta(days=120)
                ):
                    found.append({
                        "channel":
                            int(cm.group(1)),
                        "start":
                            start,
                        "title":
                            clean_title(title),
                        "source":
                            url,
                    })

    out = []
    seen = set()

    for e in found:
        k = (
            e["channel"],
            e["start"].strftime(
                "%Y%m%d%H%M"
            ),
            e["title"].lower()
        )

        if k not in seen:
            seen.add(k)
            out.append(e)

    return out


def parse_general_schedule():
    try:
        soup = BeautifulSoup(
            get(SCHEDULE_URL),
            "html.parser"
        )

    except Exception as exc:
        print(
            f"WARN schedule page failed: {exc}",
            file=sys.stderr
        )
        return []

    lines = [
        norm(x)
        for x in soup.get_text(
            "\n",
            strip=True
        ).splitlines()
        if norm(x)
    ]

    today = datetime.now(TZ).date()
    entries = []

    for i, line in enumerate(lines):
        tm = TIME_RE.fullmatch(
            line
        )

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

            if (
                candidate
                and not TIME_RE.fullmatch(
                    candidate
                )
                and candidate.lower()
                not in {
                    "yayın akışı",
                    "yayin akisi"
                }
            ):
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
            "source": SCHEDULE_URL,
        })

    print(
        f"Official Tabii Spor schedule entries: {len(entries)}"
    )

    for e in entries[:30]:
        print(
            f"  GENERAL | "
            f"{e['start']:%Y-%m-%d %H:%M} | "
            f"{e['title']}"
        )

    return entries


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

        title_el = p.find(
            "title"
        )

        desc_el = p.find(
            "desc"
        )

        events.append({
            "channel":
                int(m.group(1)),
            "start":
                start,
            "title":
                (
                    title_el.text
                    if (
                        title_el
                        is not None
                        and title_el.text
                    )
                    else "Tabii Spor"
                ),
            "source":
                (
                    desc_el.text.replace(
                        "Kaynak: ",
                        "",
                        1
                    )
                    if (
                        desc_el
                        is not None
                        and desc_el.text
                    )
                    else "saved"
                ),
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
        k = (
            e["channel"],
            e["start"].strftime(
                "%Y%m%d%H%M"
            ),
            e["title"].lower()
        )

        if k not in seen:
            seen.add(k)
            out.append(e)

    return out


def write_xml(events):
    tv = ET.Element(
        "tv",
        {
            "generator-info-name":
                "Tabii Spor 1-10 TRT incremental XMLTV v7",
            "generator-info-url":
                "https://www.trtspor.com.tr/",
        }
    )

    for n in range(
        1,
        11
    ):
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
            {"lang": "tr"}
        ).text = (
            f"Tabii Spor {n}"
        )

    for e in events:
        p = ET.SubElement(
            tv,
            "programme",
            {
                "start":
                    e["start"].strftime(
                        "%Y%m%d%H%M%S %z"
                    ),
                "stop":
                    (
                        e["start"]
                        + timedelta(
                            hours=2,
                            minutes=30
                        )
                    ).strftime(
                        "%Y%m%d%H%M%S %z"
                    ),
                "channel":
                    f"TabiiSpor{e['channel']}.tr",
            }
        )

        ET.SubElement(
            p,
            "title",
            {"lang": "tr"}
        ).text = e["title"]

        ET.SubElement(
            p,
            "category",
            {"lang": "en"}
        ).text = "Sports"

        ET.SubElement(
            p,
            "desc",
            {"lang": "tr"}
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
def parse_sporekrani():
    events = []
    now = datetime.now(TZ)

    for url in SPOREKRANI_URLS:
        try:
            soup = BeautifulSoup(
                get(url),
                "html.parser"
            )
        except Exception as exc:
            print(
                f"WARN Spor Ekrani failed {url}: {exc}",
                file=sys.stderr
            )
            continue

        text = soup.get_text(
            "\n",
            strip=True
        )

        lines = [
            norm(x)
            for x in text.splitlines()
            if norm(x)
        ]

        current_date = now.date()

        for i, line in enumerate(lines):
            d = explicit_date(
                line,
                now.year
            )

            if d:
                current_date = d

            low = line.lower()

            if low in ("yarın", "yarin"):
                current_date = (
                    now.date()
                    + timedelta(days=1)
                )

            if low in ("bugün", "bugun"):
                current_date = now.date()

            cm = re.search(
                r"\btabii\s*spor\s*(10|[1-9])\b",
                line,
                re.I
            )

            if not cm:
                continue

            channel = int(
                cm.group(1)
            )

            block = lines[
                max(0, i - 6):
                min(len(lines), i + 6)
            ]

            block_text = " | ".join(
                block
            )

            tm = TIME_RE.search(
                block_text
            )

            if not tm:
                continue

            title = None

            for candidate in block:
                if re.search(
                    r"\s[-–]\s",
                    candidate
                ):
                    cleaned = clean_title(
                        candidate
                    )

                    if 5 <= len(cleaned) <= 180:
                        title = cleaned
                        break

            if not title:
                continue

            start = datetime(
                current_date.year,
                current_date.month,
                current_date.day,
                int(tm.group(1)),
                int(tm.group(2)),
                tzinfo=TZ
            )

            if not (
                now - timedelta(days=2)
                <= start
                <= now + timedelta(days=30)
            ):
                continue

            events.append({
                "channel": channel,
                "start": start,
                "title": title,
                "source": url,
            })

    return dedupe(events)

def main():
    old = read_existing()

    print(
        f"Existing saved programmes: {len(old)}"
    )

    general_schedule = (
        parse_general_schedule()
    )
    new = []
    sporekrani_events = parse_sporekrani()

    print(
        f"Spor Ekrani numbered programmes: "
        f"{len(sporekrani_events)}"
    )

    for e in sporekrani_events:
        print(
            f"  SPOR EKRANI | "
            f"Tabii Spor {e['channel']} | "
            f"{e['start']:%Y-%m-%d %H:%M} | "
            f"{e['title']}"
        )

    new.extend(sporekrani_events)
    matched_articles = 0

    for url in discover_news_articles():
        try:
            found = parse_news_article(
                url
            )

            if found:
                matched_articles += 1

                print(
                    f"MATCH {url} -> "
                    f"{len(found)} numbered programme(s)"
                )

                for e in found:
                    print(
                        f"  Tabii Spor "
                        f"{e['channel']} | "
                        f"{e['start']:%Y-%m-%d %H:%M} | "
                        f"{e['title']}"
                    )

                new.extend(found)

        except Exception as exc:
            print(
                f"WARN article failed "
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
