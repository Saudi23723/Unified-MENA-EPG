#!/usr/bin/env python3
import html
import json
import re
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

# Official TRT Spor pages used to discover current Tabii Spor articles.
INDEX_URLS = [
    "https://www.trtspor.com.tr/haberleri/tabii-spor",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TabiiSporXMLTV/5.0; GitHub-Actions)"
}

MONTHS = {
    "ocak": 1,
    "şubat": 2, "subat": 2,
    "mart": 3,
    "nisan": 4,
    "mayıs": 5, "mayis": 5,
    "haziran": 6,
    "temmuz": 7,
    "ağustos": 8, "agustos": 8,
    "eylül": 9, "eylul": 9,
    "ekim": 10,
    "kasım": 11, "kasim": 11,
    "aralık": 12, "aralik": 12,
}

WEEKDAYS = {
    "pazartesi": 0,
    "salı": 1, "sali": 1,
    "çarşamba": 2, "carsamba": 2,
    "perşembe": 3, "persembe": 3,
    "cuma": 4,
    "cumartesi": 5,
    "pazar": 6,
}

CHANNEL_RE = re.compile(r"\bTAB(?:İ|I)İ?\s*SPOR\s*(10|[1-9])\b", re.I)
TIME_RE = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")
TEXT_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+"
    r"(ocak|şubat|subat|mart|nisan|mayıs|mayis|haziran|temmuz|"
    r"ağustos|agustos|eylül|eylul|ekim|kasım|kasim|aralık|aralik)"
    r"(?:\s+(\d{4}))?\b",
    re.I,
)
NUM_DATE_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b")


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def norm(s):
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


def discover_articles():
    links = []
    seen = set()

    for index_url in INDEX_URLS:
        try:
            soup = BeautifulSoup(get(index_url), "html.parser")
        except Exception as exc:
            print(f"WARN: could not open {index_url}: {exc}", file=sys.stderr)
            continue

        for a in soup.find_all("a", href=True):
            href = urljoin(index_url, a["href"])
            if "/haber/" not in href:
                continue
            href = href.split("#", 1)[0]
            if href in seen:
                continue
            seen.add(href)
            links.append(href)

    # TRT's tag page is enough for newly published items; keep a generous cap.
    print(f"TRT article links discovered: {len(links)}")
    return links[:150]


def parse_iso_date(value):
    if not value:
        return None
    value = value.strip()
    try:
        # Handles 2026-08-15T12:34:56+03:00 and plain YYYY-MM-DD.
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(TZ).date()
    except Exception:
        pass
    m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", value)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return datetime(y, mo, d, tzinfo=TZ).date()
        except ValueError:
            return None
    return None


def article_payload(url):
    soup = BeautifulSoup(get(url), "html.parser")

    title = ""
    h1 = soup.find("h1")
    if h1:
        title = norm(h1.get_text(" ", strip=True))
    elif soup.title:
        title = norm(soup.title.get_text(" ", strip=True))

    published = None

    # JSON-LD is usually the most reliable place for article publication date.
    for tag in soup.find_all("script", type="application/ld+json"):
        raw = tag.string or tag.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        objs = data if isinstance(data, list) else [data]
        for obj in objs:
            if not isinstance(obj, dict):
                continue
            for key in ("datePublished", "dateCreated", "uploadDate"):
                published = parse_iso_date(str(obj.get(key, "")))
                if published:
                    break
            if published:
                break
        if published:
            break

    # Fallback to meta tags.
    if not published:
        for meta in soup.find_all("meta"):
            key = " ".join([
                str(meta.get("name", "")),
                str(meta.get("property", "")),
                str(meta.get("itemprop", "")),
            ]).lower()
            if any(x in key for x in ("published", "datepublished", "publication", "article:published")):
                published = parse_iso_date(meta.get("content", ""))
                if published:
                    break

    text = soup.get_text("\n", strip=True)
    lines = [norm(x) for x in text.splitlines() if norm(x)]

    # Deduplicate visible lines but keep order.
    unique = []
    seen = set()
    for line in lines:
        if line not in seen:
            seen.add(line)
            unique.append(line)

    return title, published, unique


def explicit_date(text, default_year):
    m = NUM_DATE_RE.search(text)
    if m:
        d, mo, y = map(int, m.groups())
        try:
            return datetime(y, mo, d, tzinfo=TZ).date()
        except ValueError:
            pass

    m = TEXT_DATE_RE.search(text.lower())
    if m:
        day = int(m.group(1))
        month = MONTHS[m.group(2).lower()]
        year = int(m.group(3)) if m.group(3) else default_year
        try:
            candidate = datetime(year, month, day, tzinfo=TZ).date()
        except ValueError:
            return None

        # If year is omitted, choose the nearest plausible year.
        if not m.group(3):
            today = datetime.now(TZ).date()
            if candidate < today - timedelta(days=180):
                candidate = candidate.replace(year=year + 1)
            elif candidate > today + timedelta(days=300):
                candidate = candidate.replace(year=year - 1)
        return candidate
    return None


def resolve_date(text, published):
    today = datetime.now(TZ).date()
    base = published or today

    d = explicit_date(text, base.year)
    if d:
        return d

    low = text.lower()
    if "bugün" in low or "bugun" in low:
        return base
    if "yarın" in low or "yarin" in low:
        return base + timedelta(days=1)

    # "Cumartesi günü" etc., relative to the publication date.
    for name, weekday in WEEKDAYS.items():
        if re.search(rf"\b{name}\b", low):
            delta = (weekday - base.weekday()) % 7
            return base + timedelta(days=delta)

    return None


def nearest_date(lines, idx, published):
    # Search a local window because schedules are often line-by-line.
    for radius in range(0, 9):
        for j in (idx - radius, idx + radius):
            if 0 <= j < len(lines):
                d = resolve_date(lines[j], published)
                if d:
                    return d
    return published


def clean_event_title(text):
    text = CHANNEL_RE.sub("", text)
    text = TIME_RE.sub("", text)
    text = re.sub(r"\b(?:TSİ|TSI)\b", "", text, flags=re.I)
    text = re.sub(r"\s*[-–—|:]+\s*$", "", text)
    text = re.sub(r"^\s*[-–—|:]+\s*", "", text)
    return norm(text)


def title_from_context(lines, idx, article_title):
    # Same line is best for list-style schedules:
    # "16.00 Team A-Team B - TABİİ SPOR 6"
    same = clean_event_title(lines[idx])
    if len(same) >= 5 and same.lower() not in {"tabii spor", "tabii"}:
        return same

    # If article title itself contains the match name, use it.
    cleaned_article = clean_event_title(article_title)
    cleaned_article = re.sub(r"\s+maçı.*$", "", cleaned_article, flags=re.I)
    cleaned_article = re.sub(r"\s+maci.*$", "", cleaned_article, flags=re.I)
    if len(cleaned_article) >= 5:
        return cleaned_article

    # Nearby line fallback.
    for radius in (1, 2, 3):
        for j in (idx - radius, idx + radius):
            if 0 <= j < len(lines):
                c = clean_event_title(lines[j])
                if TIME_RE.fullmatch(c):
                    continue
                if len(c) >= 5 and len(c) <= 180 and not CHANNEL_RE.search(c):
                    return c

    return "Tabii Spor"


def events_from_article(url):
    article_title, published, lines = article_payload(url)
    if not lines:
        return []

    now = datetime.now(TZ)
    events = []

    # Pass 1: line-by-line schedule entries.
    for i, line in enumerate(lines):
        cm = CHANNEL_RE.search(line)
        if not cm:
            continue

        channel = int(cm.group(1))

        # Time may be on the same line or immediately nearby.
        tm = TIME_RE.search(line)
        if not tm:
            neighborhood = " | ".join(lines[max(0, i - 3): min(len(lines), i + 4)])
            tm = TIME_RE.search(neighborhood)
        if not tm:
            continue

        d = resolve_date(line, published)
        if not d:
            neighborhood = " | ".join(lines[max(0, i - 5): min(len(lines), i + 6)])
            d = resolve_date(neighborhood, published)
        if not d:
            d = nearest_date(lines, i, published)
        if not d:
            continue

        start = datetime(
            d.year, d.month, d.day,
            int(tm.group(1)), int(tm.group(2)),
            tzinfo=TZ,
        )

        # Keep current/future EPG plus a small past buffer.
        if start < now - timedelta(days=7) or start > now + timedelta(days=90):
            continue

        events.append({
            "channel": channel,
            "start": start,
            "title": title_from_context(lines, i, article_title),
            "source": url,
        })

    # Pass 2: article-title pattern where channel is in title and time/date are in body.
    # Example official TRT style: "... maçı Tabii Spor 6'da"; body: "TSİ 22.00'de başlayacak".
    title_cm = CHANNEL_RE.search(article_title)
    if title_cm and not any(e["channel"] == int(title_cm.group(1)) for e in events):
        full = " | ".join(lines[:120])
        tm = TIME_RE.search(full)
        d = resolve_date(full, published) or published
        if tm and d:
            start = datetime(
                d.year, d.month, d.day,
                int(tm.group(1)), int(tm.group(2)),
                tzinfo=TZ,
            )
            if now - timedelta(days=7) <= start <= now + timedelta(days=90):
                events.append({
                    "channel": int(title_cm.group(1)),
                    "start": start,
                    "title": title_from_context(lines, 0, article_title),
                    "source": url,
                })

    return events


def read_existing():
    events = []
    if not OUT.exists():
        return events

    try:
        root = ET.parse(OUT).getroot()
    except Exception as exc:
        print(f"WARN: existing XML could not be read: {exc}", file=sys.stderr)
        return events

    now = datetime.now(TZ)

    for p in root.findall("programme"):
        channel_id = p.get("channel", "")
        m = re.search(r"TabiiSpor(10|[1-9])\.tr", channel_id)
        if not m:
            continue

        raw_start = p.get("start", "")
        try:
            start = datetime.strptime(raw_start[:19], "%Y%m%d%H%M%S %z").astimezone(TZ)
        except Exception:
            try:
                start = datetime.strptime(raw_start[:14], "%Y%m%d%H%M%S").replace(tzinfo=TZ)
            except Exception:
                continue

        # Keep recent history and future entries. Old EPG data is not useful to TiviMate.
        if start < now - timedelta(days=7) or start > now + timedelta(days=120):
            continue

        title_el = p.find("title")
        desc_el = p.find("desc")
        events.append({
            "channel": int(m.group(1)),
            "start": start,
            "title": title_el.text if title_el is not None and title_el.text else "Tabii Spor",
            "source": (
                desc_el.text.replace("Kaynak: ", "", 1)
                if desc_el is not None and desc_el.text
                else "saved"
            ),
        })

    return events


def dedupe(events):
    result = []
    seen = set()

    for e in sorted(events, key=lambda x: (x["start"], x["channel"], x["title"].lower())):
        key = (
            e["channel"],
            e["start"].strftime("%Y%m%d%H%M"),
            norm(e["title"]).lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(e)

    return result


def xmltv_time(dt):
    return dt.strftime("%Y%m%d%H%M%S %z")


def write_xml(events):
    tv = ET.Element(
        "tv",
        {
            "generator-info-name": "Tabii Spor 1-10 incremental TRT XMLTV",
            "generator-info-url": "https://www.trtspor.com.tr/",
        },
    )

    for n in range(1, 11):
        ch = ET.SubElement(tv, "channel", {"id": f"TabiiSpor{n}.tr"})
        ET.SubElement(ch, "display-name", {"lang": "tr"}).text = f"Tabii Spor {n}"
        ET.SubElement(ch, "display-name").text = f"tabii Spor {n}"

    for e in events:
        p = ET.SubElement(
            tv,
            "programme",
            {
                "start": xmltv_time(e["start"]),
                "stop": xmltv_time(e["start"] + timedelta(hours=2, minutes=30)),
                "channel": f"TabiiSpor{e['channel']}.tr",
            },
        )
        ET.SubElement(p, "title", {"lang": "tr"}).text = e["title"]
        ET.SubElement(p, "category", {"lang": "en"}).text = "Sports"
        ET.SubElement(p, "desc", {"lang": "tr"}).text = f"Kaynak: {e['source']}"

    ET.indent(tv, space="  ")
    ET.ElementTree(tv).write(OUT, encoding="utf-8", xml_declaration=True)


def main():
    old_events = read_existing()
    print(f"Existing saved programmes: {len(old_events)}")

    new_events = []
    for url in discover_articles():
        try:
            found = events_from_article(url)
            if found:
                print(f"{url} -> {len(found)} programme(s)")
                new_events.extend(found)
        except Exception as exc:
            print(f"WARN article failed: {url}: {exc}", file=sys.stderr)

    merged = dedupe(old_events + new_events)
    added_keys = {
        (e["channel"], e["start"].strftime("%Y%m%d%H%M"), norm(e["title"]).lower())
        for e in new_events
    } - {
        (e["channel"], e["start"].strftime("%Y%m%d%H%M"), norm(e["title"]).lower())
        for e in old_events
    }

    print(f"New programmes detected: {len(added_keys)}")
    print(f"Total programmes kept in EPG: {len(merged)}")

    # Important behavior requested by the user:
    # no new TRT posts is NOT an error; preserve what is already saved.
    write_xml(merged)

    for e in merged:
        print(
            f"Tabii Spor {e['channel']} | "
            f"{e['start'].strftime('%Y-%m-%d %H:%M')} | {e['title']}"
        )


if __name__ == "__main__":
    main()
