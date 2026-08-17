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
OUT = Path("tabii_spor_1_7_epg.xml")

INDEX_URLS = [
    "https://www.trtspor.com.tr/haberleri/tabii-spor",
    "https://www.trtspor.com.tr/haberleri/tabii",
]

MONTHS = {
    "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4,
    "mayıs": 5, "mayis": 5, "haziran": 6, "temmuz": 7, "ağustos": 8,
    "agustos": 8, "eylül": 9, "eylul": 9, "ekim": 10, "kasım": 11,
    "kasim": 11, "aralık": 12, "aralik": 12
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TabiiXMLTV/1.0; +GitHub Actions)"
}

def get(url):
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r.text

def norm(s):
    return re.sub(r"\s+", " ", html.unescape(s)).strip()

def recent_article_links():
    links = []
    seen = set()
    for index_url in INDEX_URLS:
        try:
            soup = BeautifulSoup(get(index_url), "html.parser")
        except Exception as e:
            print(f"WARN index {index_url}: {e}", file=sys.stderr)
            continue
        for a in soup.find_all("a", href=True):
            href = urljoin(index_url, a["href"])
            if "/haber/" not in href:
                continue
            if href in seen:
                continue
            seen.add(href)
            links.append(href)
    return links[:50]

def article_text(url):
    soup = BeautifulSoup(get(url), "html.parser")
    # Preserve line-ish boundaries because schedules are often formatted line by line.
    chunks = []
    for tag in soup.find_all(["h1","h2","h3","p","li","div"]):
        t = norm(tag.get_text(" ", strip=True))
        if t and len(t) < 500:
            chunks.append(t)
    # De-duplicate consecutive/near exact snippets.
    out = []
    seen = set()
    for t in chunks:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return "\n".join(out)

def parse_date_from_context(lines, idx, default_year):
    # Search backwards for forms like "29 Ocak", "29 Ocak Perşembe", optionally with year.
    for j in range(idx, max(-1, idx-12), -1):
        low = lines[j].lower()
        m = re.search(r"\b(\d{1,2})\s+([a-zçğıöşü]+)(?:\s+(\d{4}))?\b", low, re.I)
        if m and m.group(2) in MONTHS:
            day = int(m.group(1))
            month = MONTHS[m.group(2)]
            year = int(m.group(3)) if m.group(3) else default_year
            # Handle Dec/Jan around year boundary.
            now = datetime.now(TZ)
            try:
                candidate = datetime(year, month, day, tzinfo=TZ)
            except ValueError:
                continue
            if not m.group(3):
                if candidate < now - timedelta(days=120):
                    candidate = candidate.replace(year=year + 1)
                elif candidate > now + timedelta(days=300):
                    candidate = candidate.replace(year=year - 1)
            return candidate.date()
    return None

def clean_title(s):
    s = re.sub(r"\bTAB[İI]İ?\s+SPOR\s*[1-7]\b", "", s, flags=re.I)
    s = re.sub(r"\b\d{1,2}[.:]\d{2}\b", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" -–—:|")

def parse_events(text, source_url):
    lines = [norm(x) for x in text.splitlines() if norm(x)]
    now = datetime.now(TZ)
    events = []

    # Common TRT pattern: "23.00 TEAM A - TEAM B TABİİ SPOR 3"
    chan_re = re.compile(r"\bTAB[İI]İ?\s+SPOR\s*([1-7])\b", re.I)
    time_re = re.compile(r"\b([01]?\d|2[0-3])[.:]([0-5]\d)\b")

    for i, line in enumerate(lines):
        cm = chan_re.search(line)
        tm = time_re.search(line)
        if not cm or not tm:
            continue

        ch = int(cm.group(1))
        date = parse_date_from_context(lines, i, now.year)
        if not date:
            continue

        hour, minute = int(tm.group(1)), int(tm.group(2))
        start = datetime(date.year, date.month, date.day, hour, minute, tzinfo=TZ)

        # Ignore old archive material; keep a useful rolling window.
        if start < now - timedelta(days=2) or start > now + timedelta(days=35):
            continue

        title = clean_title(line)
        if not title:
            continue

        events.append({
            "channel": ch,
            "start": start,
            "title": title,
            "source": source_url,
        })

    return events

def dedupe(events):
    out = []
    seen = set()
    for e in sorted(events, key=lambda x: (x["start"], x["channel"], x["title"])):
        key = (e["channel"], e["start"].isoformat(), e["title"].lower())
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out

def xmltv_time(dt):
    return dt.strftime("%Y%m%d%H%M%S %z")

def build_xml(events):
    tv = ET.Element("tv", {
        "generator-info-name": "Tabii Spor 1-7 TRT scraper",
        "generator-info-url": "https://www.trtspor.com.tr/"
    })

    for i in range(1, 8):
        ch = ET.SubElement(tv, "channel", {"id": f"TabiiSpor{i}.tr"})
        ET.SubElement(ch, "display-name", {"lang": "tr"}).text = f"tabii Spor {i}"
        ET.SubElement(ch, "display-name").text = f"Tabii Spor {i}"

    for e in events:
        # Event channels are usually match-only. Use a conservative 2h30 duration.
        stop = e["start"] + timedelta(hours=2, minutes=30)
        p = ET.SubElement(tv, "programme", {
            "start": xmltv_time(e["start"]),
            "stop": xmltv_time(stop),
            "channel": f"TabiiSpor{e['channel']}.tr"
        })
        ET.SubElement(p, "title", {"lang": "tr"}).text = e["title"]
        ET.SubElement(p, "category", {"lang": "en"}).text = "Sports"
        ET.SubElement(p, "desc", {"lang": "tr"}).text = f"Kaynak: TRT. {e['source']}"

    ET.indent(tv, space="  ")
    return ET.ElementTree(tv)

def main():
    all_events = []
    links = recent_article_links()
    print(f"Found {len(links)} TRT article links")
    for url in links:
        try:
            text = article_text(url)
            ev = parse_events(text, url)
            if ev:
                print(f"{url}: {len(ev)} event(s)")
                all_events.extend(ev)
        except Exception as e:
            print(f"WARN article {url}: {e}", file=sys.stderr)

    events = dedupe(all_events)
    tree = build_xml(events)
    tree.write(OUT, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {OUT} with {len(events)} programme(s)")

if __name__ == "__main__":
    main()
