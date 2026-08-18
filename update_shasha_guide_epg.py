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

SOURCE_URL = "https://www.livesoccertv.com/channels/shasha/"
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


def scrape_livesoccertv():
    """
    Conservative scraper for the Shasha channel page.

    It ONLY creates events from rows that are inside the Shasha schedule
    section. It intentionally does NOT use the site's generic 'Top Matches'
    section, because those are not necessarily Shasha broadcasts.
    """
    try:
        r = requests.get(SOURCE_URL, headers=HEADERS, timeout=25)
        r.raise_for_status()
    except Exception as exc:
        warn(f"Shasha schedule fetch failed: {exc}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    text = norm(soup.get_text(" ", strip=True))

    if "There are currently no upcoming soccer listings scheduled on Shasha" in text:
        log("LiveSoccerTV currently reports no upcoming Shasha soccer listings.")
        return []

    # Try common match-row containers used by schedule sites.
    candidate_rows = []
    selectors = [
        "tr",
        ".matchrow",
        ".match-row",
        ".schedule-row",
        ".event",
        "li",
    ]
    for sel in selectors:
        candidate_rows.extend(soup.select(sel))

    events = []
    seen_html = set()

    # Date/time parser patterns seen on listing pages.
    date_re = re.compile(
        r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)?\.?\s*"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+(\d{1,2})(?:,\s*(\d{4}))?\b",
        re.I,
    )
    time_re = re.compile(r"\b(\d{1,2}):(\d{2})\s*(am|pm)\b", re.I)

    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    current_year = datetime.now(RIYADH).year

    for row in candidate_rows:
        raw = norm(row.get_text(" ", strip=True))
        if not raw or raw in seen_html:
            continue
        seen_html.add(raw)

        # Avoid generic navigation/top-matches rows.
        if len(raw) > 350:
            continue

        dm = date_re.search(raw)
        tm = time_re.search(raw)
        if not dm or not tm:
            continue

        # Require a versus-like team separator or two plausible team links.
        links = [norm(a.get_text(" ", strip=True)) for a in row.find_all("a")]
        links = [x for x in links if x and len(x) <= 80]

        team_names = []
        for x in links:
            lx = x.casefold()
            if lx in {"shasha", "live soccer tv", "channel website"}:
                continue
            if any(k in lx for k in ("serie a", "primeira", "liga", "league", "cup")):
                continue
            team_names.append(x)

        if len(team_names) < 2:
            continue

        team1, team2 = team_names[-2], team_names[-1]
        if team1 == team2:
            continue

        month = months[dm.group(1).lower()]
        day = int(dm.group(2))
        year = int(dm.group(3) or current_year)

        hh = int(tm.group(1))
        mm = int(tm.group(2))
        ap = tm.group(3).lower()
        if ap == "pm" and hh != 12:
            hh += 12
        elif ap == "am" and hh == 12:
            hh = 0

        # LiveSoccerTV renders times according to visitor locale. For a stable
        # GitHub runner we cannot safely infer that locale, so only accept rows
        # that expose a machine-readable timestamp.
        machine_dt = None

        # HTML5 time elements.
        time_el = row.find("time")
        if time_el:
            iso = time_el.get("datetime")
            if iso:
                try:
                    machine_dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                except Exception:
                    pass

        # Common data attributes.
        if machine_dt is None:
            for attr in ("data-datetime", "data-date", "data-time"):
                value = row.get(attr)
                if not value:
                    continue
                try:
                    machine_dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    break
                except Exception:
                    pass

        # Unix timestamp attributes.
        if machine_dt is None:
            for tag in row.find_all(True):
                for attr in ("data-timestamp", "data-utc", "data-epoch"):
                    value = tag.get(attr)
                    if value and str(value).isdigit():
                        try:
                            ts = int(value)
                            if ts > 10_000_000_000:
                                ts //= 1000
                            machine_dt = datetime.fromtimestamp(ts, UTC)
                            break
                        except Exception:
                            pass
                if machine_dt is not None:
                    break

        if machine_dt is None:
            # Do not guess the timezone.
            continue

        start = machine_dt.astimezone(RIYADH)
        if not in_window(start):
            continue

        competition = ""
        for x in links:
            lx = x.casefold()
            if any(k in lx for k in ("serie a", "primeira", "liga", "league", "cup")):
                competition = x
                break

        events.append({
            "title": f"{team1} - {team2}",
            "start": start,
            "competition": competition,
            "source": "LiveSoccerTV Shasha schedule",
        })

    events = dedupe(events)
    log(f"Shasha schedule events detected: {len(events)}")
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
    auto = scrape_livesoccertv()
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
