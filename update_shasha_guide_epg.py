#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

SOURCES = [
    ("LiveSoccerTV", "https://www.livesoccertv.com/channels/shasha/"),
    ("SHASHA Official", "https://www.shasha.com/"),
    ("SHASHA Sports Instagram", "https://www.instagram.com/shasha_sports/"),
    ("SHASHA Sports X", "https://x.com/Shasha_Sports"),
]
OUT = Path("shasha_guide_epg.xml")
MANUAL = Path("shasha_matches.json")

RIYADH = ZoneInfo("Asia/Riyadh")
VEGAS = ZoneInfo("America/Los_Angeles")
UTC = ZoneInfo("UTC")

CHANNEL_ID = "ShashaGuide"
KEEP_DAYS_BACK = 1
KEEP_DAYS_FORWARD = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
}

AR_DAYS = {
    0: "الاثنين",
    1: "الثلاثاء",
    2: "الأربعاء",
    3: "الخميس",
    4: "الجمعة",
    5: "السبت",
    6: "الأحد",
}

AR_MONTHS = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل",
    5: "مايو", 6: "يونيو", 7: "يوليو", 8: "أغسطس",
    9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
}


def log(msg):
    print(msg, flush=True)


def warn(msg):
    print(f"WARN {msg}", flush=True)


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def in_window(dt_riyadh):
    now = datetime.now(RIYADH)
    lo = now - timedelta(days=KEEP_DAYS_BACK)
    hi = now + timedelta(days=KEEP_DAYS_FORWARD + 1)
    return lo <= dt_riyadh < hi


def event_key(e):
    return (
        e["start"].strftime("%Y%m%d%H%M"),
        norm(e["title"]).casefold(),
    )


def dedupe(events):
    out = []
    seen = set()
    for e in sorted(events, key=lambda x: (x["start"], x["title"])):
        k = event_key(e)
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out


def parse_manual():
    """
    Optional manual override file format:
    [
      {
        "title": "Inter - Milan",
        "start": "2026-08-19T21:45:00+03:00",
        "competition": "Serie A"
      }
    ]
    """
    if not MANUAL.exists():
        return []

    try:
        data = json.loads(MANUAL.read_text(encoding="utf-8"))
    except Exception as exc:
        warn(f"Could not read {MANUAL}: {exc}")
        return []

    events = []
    for row in data:
        try:
            start = datetime.fromisoformat(row["start"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=RIYADH)
            start = start.astimezone(RIYADH)

            if not in_window(start):
                continue

            title = norm(row["title"])
            if not title:
                continue

            events.append({
                "title": title,
                "start": start,
                "competition": norm(row.get("competition", "")),
                "source": "manual override",
            })
        except Exception as exc:
            warn(f"Skipping invalid manual row: {exc}")

    return events


def _extract_machine_dt(node):
    """Return timezone-aware datetime if the HTML exposes one; otherwise None."""
    # HTML5 <time datetime=...>
    time_el = node.find("time")
    if time_el:
        iso = time_el.get("datetime")
        if iso:
            try:
                return datetime.fromisoformat(iso.replace("Z", "+00:00"))
            except Exception:
                pass

    # Common ISO datetime attributes
    for tag in [node] + node.find_all(True):
        for attr in ("data-datetime", "data-date-time", "datetime"):
            value = tag.get(attr)
            if not value:
                continue
            try:
                dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if dt.tzinfo is not None:
                    return dt
            except Exception:
                pass

    # Unix timestamps
    for tag in [node] + node.find_all(True):
        for attr in ("data-timestamp", "data-utc", "data-epoch"):
            value = tag.get(attr)
            if value and str(value).isdigit():
                try:
                    ts = int(value)
                    if ts > 10_000_000_000:
                        ts //= 1000
                    return datetime.fromtimestamp(ts, UTC)
                except Exception:
                    pass

    return None


def _clean_match_title(text):
    text = norm(text)
    text = re.sub(r"https?://\S+", "", text)

    # Normalize common versus markers.
    text = re.sub(r"\s*(?:🆚|⚔️|⚔|VS\.?|V\.?|ضد)\s*", " - ", text, flags=re.I)

    # Strip obvious schedule metadata.
    text = re.sub(
        r"\b(?:live|watch|stream|today|tomorrow|اليوم|غداً|غدا|مباشر)\b",
        "",
        text,
        flags=re.I,
    )
    text = norm(text)

    if " - " not in text:
        return None

    left, right = [norm(x) for x in text.split(" - ", 1)]
    if not left or not right:
        return None

    # Avoid huge social captions.
    if len(left) > 80 or len(right) > 80:
        return None

    return f"{left} - {right}"


def _generic_source_scrape(label, url):
    """
    Conservative generic scraper.
    Only creates a programme if BOTH are present in the same HTML container:
      1) a match-like 'A vs B'
      2) a machine-readable timezone-aware datetime/timestamp

    This avoids inventing kickoff times from social-media text.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
    except Exception as exc:
        warn(f"{label} fetch failed: {exc}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    events = []

    containers = []
    for selector in (
        "article",
        "tr",
        "li",
        ".matchrow",
        ".match-row",
        ".schedule-row",
        ".event",
        ".post",
        ".card",
    ):
        containers.extend(soup.select(selector))

    # If page has no obvious containers, inspect smaller DIVs too.
    if not containers:
        containers = [
            div for div in soup.find_all("div")
            if len(norm(div.get_text(" ", strip=True))) <= 500
        ]

    seen = set()

    for node in containers:
        raw = norm(node.get_text(" ", strip=True))
        if not raw or raw in seen:
            continue
        seen.add(raw)

        if not re.search(r"(?:🆚|⚔️|⚔|\bVS\.?\b|\bV\.?\b|ضد)", raw, re.I):
            continue

        dt = _extract_machine_dt(node)
        if dt is None:
            continue

        title = _clean_match_title(raw)
        if not title:
            continue

        start = dt.astimezone(RIYADH)
        if not in_window(start):
            continue

        events.append({
            "title": title,
            "start": start,
            "competition": "",
            "source": label,
        })

    events = dedupe(events)
    log(f"{label}: {len(events)} usable SHASHA match listings")
    return events


def scrape_livesoccertv():
    """
    Dedicated LiveSoccerTV parser + safe fallback to generic parser.
    """
    url = "https://www.livesoccertv.com/channels/shasha/"

    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
    except Exception as exc:
        warn(f"LiveSoccerTV fetch failed: {exc}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    text = norm(soup.get_text(" ", strip=True))

    if "There are currently no upcoming soccer listings scheduled on Shasha" in text:
        log("LiveSoccerTV currently reports no upcoming Shasha soccer listings.")
        return []

    # Use generic conservative parser on the fetched document structure.
    events = []
    for node in soup.select("tr, .matchrow, .match-row, .schedule-row, .event, li"):
        raw = norm(node.get_text(" ", strip=True))
        if not re.search(r"(?:🆚|⚔️|⚔|\bVS\.?\b|\bV\.?\b|ضد)", raw, re.I):
            continue

        dt = _extract_machine_dt(node)
        if dt is None:
            continue

        title = _clean_match_title(raw)
        if not title:
            continue

        start = dt.astimezone(RIYADH)
        if not in_window(start):
            continue

        events.append({
            "title": title,
            "start": start,
            "competition": "",
            "source": "LiveSoccerTV",
        })

    events = dedupe(events)
    log(f"LiveSoccerTV: {len(events)} usable SHASHA match listings")
    return events


def scrape_all_sources():
    """
    Merge several independent SHASHA sources.
    No source is allowed to guess a kickoff time.
    """
    events = []

    # 1) Dedicated TV-listing source
    events.extend(scrape_livesoccertv())

    # 2) Official SHASHA website
    events.extend(_generic_source_scrape(
        "SHASHA Official",
        "https://www.shasha.com/",
    ))

    # 3) Official SHASHA Sports Instagram public page
    events.extend(_generic_source_scrape(
        "SHASHA Sports Instagram",
        "https://www.instagram.com/shasha_sports/",
    ))

    # 4) Official SHASHA Sports X public page
    events.extend(_generic_source_scrape(
        "SHASHA Sports X",
        "https://x.com/Shasha_Sports",
    ))

    events = dedupe(events)
    log(f"Combined SHASHA sources: {len(events)} unique programmes")
    return events

def read_existing():
    if not OUT.exists():
        return []

    try:
        root = ET.parse(OUT).getroot()
    except Exception as exc:
        warn(f"Existing Shasha guide unreadable: {exc}")
        return []

    events = []
    for p in root.findall("programme"):
        if p.get("channel") != CHANNEL_ID:
            continue

        raw_start = p.get("start") or ""
        try:
            start = datetime.strptime(
                raw_start[:14], "%Y%m%d%H%M%S"
            ).replace(tzinfo=RIYADH)
        except Exception:
            continue

        if not in_window(start):
            continue

        title_el = p.find("title")
        title = norm(title_el.text) if title_el is not None else ""
        if not title:
            continue

        events.append({
            "title": title,
            "start": start,
            "competition": "",
            "source": "existing XML",
        })

    return events


def merge(existing, fresh):
    merged = {event_key(e): e for e in existing}
    for e in fresh:
        merged[event_key(e)] = e
    return dedupe([e for e in merged.values() if in_window(e["start"])])


def fmt_12(dt):
    hour = dt.hour
    ampm = "ص" if hour < 12 else "م"
    h = hour % 12
    if h == 0:
        h = 12
    return f"{h}:{dt.minute:02d} {ampm}"


def arabic_date(dt):
    return (
        f"{AR_DAYS[dt.weekday()]} "
        f"{dt.day} {AR_MONTHS[dt.month]} {dt.year}"
    )


def write_xml(events):
    tv = ET.Element(
        "tv",
        {"generator-info-name": "SHASHA Guide EPG"},
    )

    ch = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(ch, "display-name", {"lang": "ar"}).text = "SHASHA | Guide"
    ET.SubElement(ch, "display-name", {"lang": "en"}).text = "SHASHA | Guide"

    for e in events:
        riyadh = e["start"].astimezone(RIYADH)
        vegas = e["start"].astimezone(VEGAS)
        stop = riyadh + timedelta(hours=3)

        p = ET.SubElement(
            tv,
            "programme",
            {
                "start": riyadh.strftime("%Y%m%d%H%M%S %z"),
                "stop": stop.strftime("%Y%m%d%H%M%S %z"),
                "channel": CHANNEL_ID,
            },
        )

        ET.SubElement(p, "title", {"lang": "ar"}).text = e["title"]
        ET.SubElement(p, "category", {"lang": "en"}).text = "Sports"

        lines = [
            f"📅 {arabic_date(riyadh)}",
            f"🕘 توقيت مكة: {fmt_12(riyadh)}",
            f"🕘 توقيت لاس فيغاس: {fmt_12(vegas)}",
        ]

        if e.get("competition"):
            lines.append(f"🏆 {e['competition']}")

        if e.get("source"):
            lines.append(f"🔎 المصدر: {e['source']}")

        lines.append("📺 استخدم هذا الـGuide مع قنوات SHASHA 1 / 2 / 3.")

        ET.SubElement(
            p,
            "desc",
            {"lang": "ar"},
        ).text = "\n".join(lines)

    ET.indent(tv, space="  ")
    ET.ElementTree(tv).write(
        OUT,
        encoding="utf-8",
        xml_declaration=True,
    )


def main():
    existing = read_existing()
    auto = scrape_all_sources()
    manual = parse_manual()
    fresh = dedupe(auto + manual)

    log(f"Existing SHASHA Guide programmes kept: {len(existing)}")
    log(f"Fresh SHASHA Guide programmes: {len(fresh)}")

    merged = merge(existing, fresh)

    # Preserve old guide if the automatic source is temporarily empty.
    if not fresh and existing:
        warn("No fresh SHASHA listings; existing XML preserved.")
        return

    write_xml(merged)
    log(f"SHASHA Guide total programmes: {len(merged)}")
    log(f"Written: {OUT}")


if __name__ == "__main__":
    main()
