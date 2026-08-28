#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone, date
from html import unescape
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from io import BytesIO

from epg_lib import countdown_step, countdown_title, with_live_badge

OUTPUT = "shasha_epg.xml"

CHANNEL_ID = "ShashaGuide"
CHANNEL_NAME = "SHASHA GUIDE | شاشا"
CHANNEL_ICON = "https://www.shasha.com/favicon.ico"

UTC = timezone.utc

DAYS_BACK = 1
DAYS_FORWARD = 21

HTTP_TIMEOUT = 18
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)

LEGA_DOCS = "https://www.legaseriea.it/lega-serie-a/documentazione"
LEGA_CURRENT_PDF = (
    "https://images.legaseriea.it/image/private/fl_attachment/prd/"
    "czailts3apyt3kuxjran.pdf"
)

KFA_ZAIN_2627 = (
    "https://kuwait-fa.org/en/%D8%A3%D8%AE%D8%A8%D8%A7%D8%B1/"
    "%D8%AC%D8%AF%D9%88%D9%84-%D9%85%D8%A8%D8%A7%D8%B1%D9%8A%D8%A7%D8%AA-"
    "%D8%AF%D9%88%D8%B1%D9%8A-%D8%B2%D9%8A%D9%86-%D9%84%D9%84%D8%AF%D8%B1%D8%AC%D8%A9-"
    "%D8%A7%D9%84%D9%85%D9%85%D8%AA%D8%A7%D8%B2%D8%A9/"
)
FOTMOB_ZAIN = "https://www.fotmob.com/api/leagues?id=529&ccode3=KWT&season=2026%2F2027"
SOCCERWAY_ZAIN = "https://www.soccerway.com/kuwait/premier-league/"
ODDALERTS_ZAIN = "https://www.oddalerts.com/leagues/kuwait/zain-premier-league/fixtures"

KSW_HOME = "https://www.kswmma.com/en"

session = requests.Session()
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
})

def log(msg: str) -> None:
    print(msg, flush=True)

def warn(msg: str) -> None:
    print(f"WARN {msg}", flush=True)

def fetch_json(url: str):
    r = session.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()

def fetch_text(url: str) -> str:
    r = session.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.text

def utc_now() -> datetime:
    return datetime.now(UTC)

def window_bounds():
    now = utc_now()
    start = (now - timedelta(days=DAYS_BACK)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end = (now + timedelta(days=DAYS_FORWARD + 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start, end

def in_window(dt_utc: datetime) -> bool:
    start, end = window_bounds()
    return start <= dt_utc < end

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(s or "")).strip()

def team_name(s: str) -> str:
    s = norm(s)
    aliases = {
        "Internazionale": "Inter",
        "Internazionale Milano": "Inter",
        "Inter Milan": "Inter",
        "AC Milan": "Milan",
        "AS Roma": "Roma",
        "Hellas Verona": "Verona",
        "Al Kuwait SC": "Kuwait SC",
        "Al-Arabi SC Kuwait": "Al Arabi",
        "Al Arabi SC Kuwait": "Al Arabi",
        "Qadsia SC": "Al Qadsia",
        "Al-Qadsia SC": "Al Qadsia",
        "Al Salmiya SC": "Al Salmiya",
        "Al-Salmiya SC": "Al Salmiya",
        "Tadhamon SC": "Al Tadhamon",
        "Kazma SC": "Kazma",
        "Al Jahra SC": "Al Jahra",
        "Al Nasr SC": "Al Nasr",
    }
    return aliases.get(s, s)

def event_key(ev: dict) -> str:
    start = ev["start"].astimezone(UTC).replace(second=0, microsecond=0)
    t = re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", ev["title"].casefold())
    words = sorted(w for w in t.split() if len(w) > 1)
    return f"{start:%Y%m%d%H%M}|{' '.join(words)}"

def dedupe(events: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for ev in sorted(events, key=lambda x: x["start"]):
        k = event_key(ev)
        if k in seen:
            continue
        seen.add(k)
        out.append(ev)

    priority = {
        "KSWOfficial": 120,
        "LegaSerieAOfficial": 120,
        "FotMob-Zain": 105,
        "Soccerway-Zain": 100,
        "OddAlerts-Zain": 95,
    }

    def tokens(title):
        s = title.casefold()
        s = re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", s)
        return {x for x in s.split() if len(x) >= 3}

    final = []
    for ev in out:
        merged = False
        for i, old in enumerate(final):
            if ev.get("competition") != old.get("competition"):
                continue
            if ev["start"].astimezone(UTC).date() != old["start"].astimezone(UTC).date():
                continue
            a, b = tokens(ev["title"]), tokens(old["title"])
            if not a or not b:
                continue
            overlap = len(a & b) / max(1, min(len(a), len(b)))
            hours = abs((ev["start"] - old["start"]).total_seconds()) / 3600
            if overlap >= 0.75 and hours <= 3:
                if priority.get(ev["source_name"], 0) > priority.get(old["source_name"], 0):
                    final[i] = ev
                merged = True
                break
        if not merged:
            final.append(ev)

    return sorted(final, key=lambda x: x["start"])

def xmltv_time(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%d%H%M%S +0000")

def competition_ar(c: str) -> str:
    return {
        "Serie A": "الدوري الإيطالي Serie A",
        "Zain Premier League": "دوري زين الكويتي",
        "KSW": "KSW MMA",
    }.get(c, c)

def _pdf_text(url: str) -> str:
    r = session.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    reader = PdfReader(BytesIO(r.content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _discover_lega_schedule_pdfs() -> list[str]:
    urls = [LEGA_CURRENT_PDF]
    try:
        soup = BeautifulSoup(fetch_text(LEGA_DOCS), "html.parser")
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            label = norm(a.get_text(" ", strip=True))
            parent_label = norm(a.parent.get_text(" ", strip=True)) if a.parent else label
            hay = f"{label} {parent_label}".casefold()
            if not href.lower().endswith(".pdf"):
                continue
            if "serie a enilive" not in hay or "2026" not in hay:
                continue
            if not any(k in hay for k in ("anticip", "posticip", "programmazione", "date e orari")):
                continue
            if href.startswith("/"):
                href = "https://www.legaseriea.it" + href
            if href.startswith("http"):
                urls.append(href)
    except Exception as exc:
        warn(f"Lega documentation discovery failed: {exc}")
    return list(dict.fromkeys(urls))


def _parse_lega_pdf(pdf_text: str, source_url: str) -> list[dict]:
    events = []
    row = re.compile(
        r"(\d{2}/\d{2}/20\d{2})\s+"
        r"[A-Za-zÀ-ÿ]+\s+"
        r"(\d{1,2}[.:]\d{2})\s+"
        r"([A-Za-zÀ-ÿ\'’ .]+?)\s*-\s*"
        r"([A-Za-zÀ-ÿ\'’ .]+?)\s*(?:\*{1,3})?\s+"
        r"(?:DAZN(?:/SKY)?|SKY)",
        re.I,
    )
    rome = ZoneInfo("Europe/Rome")
    for m in row.finditer(pdf_text):
        d_raw, t_raw, home, away = m.groups()
        try:
            d = datetime.strptime(d_raw, "%d/%m/%Y").date()
            hh, mm = map(int, re.split(r"[.:]", t_raw))
            local = datetime(d.year, d.month, d.day, hh, mm, tzinfo=rome)
            start_utc = local.astimezone(UTC)
        except Exception:
            continue
        if not in_window(start_utc):
            continue
        events.append({
            "start": start_utc,
            "title": f"{team_name(home)} - {team_name(away)}",
            "competition": "Serie A",
            "source_name": "LegaSerieAOfficial",
            "source": source_url,
            "duration_minutes": 135,
        })
    return events


def parse_serie_a() -> list[dict]:
    events = []
    for url in _discover_lega_schedule_pdfs():
        try:
            events.extend(_parse_lega_pdf(_pdf_text(url), url))
        except Exception as exc:
            warn(f"Lega Serie A PDF failed {url}: {exc}")
    events = dedupe(events)
    log(f"Serie A fixtures detected: {len(events)}")
    return events


def _zain_add(events, start_utc, home, away, source_name, source_url):
    if not in_window(start_utc):
        return
    home, away = team_name(home), team_name(away)
    if not home or not away:
        return
    events.append({
        "start": start_utc.astimezone(UTC),
        "title": f"{home} - {away}",
        "competition": "Zain Premier League",
        "source_name": source_name,
        "source": source_url,
        "duration_minutes": 135,
    })


def _parse_oddalerts_zain() -> list[dict]:
    """
    Parse each visible OddAlerts fixture row independently:
      Tue 25 Aug, 20:00
      Kazma
      Al Tadhamon

    We do NOT infer one page-level time and reuse it for all fixtures.
    If the page lists the same kickoff time for several matches, each match
    must still have its own explicit date/time row.
    """
    events = []
    soup = BeautifulSoup(fetch_text(ODDALERTS_ZAIN), "html.parser")
    text = soup.get_text("\n", strip=True)

    # Normalize to non-empty lines while preserving row order.
    lines = [norm(x) for x in text.splitlines() if norm(x)]

    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    date_re = re.compile(
        r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+"
        r"(\d{1,2})\s+"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec),\s*"
        r"(\d{1,2}):(\d{2})$",
        re.I,
    )

    # Filter out obvious non-team UI/stat lines that can follow a fixture.
    bad = re.compile(
        r"^(?:1\s+\d|X\s+\d|2\s+\d|Season|Upcoming|Results|No fixtures|"
        r"Zain Premier League|Every Zain|Overview|Fixtures|Predictions|Standings|"
        r"Explore|Sign In|Login|Join The Team|Create|Pro\b|Monthly|Weekly|Quarterly)",
        re.I,
    )

    # A finished row carries a status column between the kickoff and the
    # teams, and then each side's goals:
    #
    #   Thu 27 Aug, 16:45 | FT | Al Sahel | 1 | Al Sulaibikhat | 0
    #   Thu 27 Aug, 19:00 | FT | Kazma    | 3 | Al Tadhamon    | 1
    #
    # Taking the first two plausible lines makes that "FT - Al Sahel":
    # a status code standing in for the home side, the real home side
    # demoted to away, and the away side dropped off the end entirely.
    # This guide published exactly that for thirty-one rows. An upcoming
    # row has no status column, which is why only finished matches were
    # wrong and the error looked like an odd team name rather than a
    # parser losing a column.
    #
    # Skipped like any other furniture, so the pair becomes the two clubs.
    status_line = re.compile(
        r"(?:FT|HT|AET|ET|Pen|Pens|Postp|Canc|Abd|Susp|Live|vs)\.?", re.I)

    kwt = ZoneInfo("Asia/Kuwait")
    now_kwt = utc_now().astimezone(kwt)

    i = 0
    while i < len(lines):
        m = date_re.match(lines[i])
        if not m:
            i += 1
            continue

        dd, mon, hh, mm = m.groups()
        # Find the next two plausible team-name lines.
        teams = []
        j = i + 1
        while j < len(lines) and len(teams) < 2 and j <= i + 8:
            candidate = lines[j]
            if date_re.match(candidate):
                break
            if (
                not bad.match(candidate)
                and not status_line.fullmatch(candidate)
                and "%" not in candidate
                and len(candidate) <= 60
                and not candidate.isdigit()
            ):
                teams.append(candidate)
            j += 1

        if len(teams) == 2:
            year = now_kwt.year
            try:
                local = datetime(
                    year,
                    months[mon.casefold()],
                    int(dd),
                    int(hh),
                    int(mm),
                    tzinfo=kwt,
                )
                # Season starts in Aug 2026 and runs into 2027.
                if local < now_kwt - timedelta(days=120):
                    local = local.replace(year=year + 1)
                _zain_add(
                    events,
                    local.astimezone(UTC),
                    teams[0],
                    teams[1],
                    "OddAlerts-Zain",
                    ODDALERTS_ZAIN,
                )
            except Exception:
                pass

        i = max(i + 1, j)

    if not events:
        warn("OddAlerts returned no Zain fixture — the Kuwaiti league is "
             "running on whatever else answered")
    return events


def _parse_soccerway_zain() -> list[dict]:
    """
    Conservative fallback. Only accept fixtures when Soccerway exposes
    an ISO/date-time together with both teams in embedded structured JSON.
    """
    import json
    events = []
    soup = BeautifulSoup(fetch_text(SOCCERWAY_ZAIN), "html.parser")

    def walk(obj):
        if isinstance(obj, dict):
            home = away = None
            for hk in ("homeTeam", "home", "home_name", "homeName"):
                v = obj.get(hk)
                if isinstance(v, dict):
                    home = v.get("name") or v.get("displayName")
                elif isinstance(v, str):
                    home = v
                if home:
                    break

            for ak in ("awayTeam", "away", "away_name", "awayName"):
                v = obj.get(ak)
                if isinstance(v, dict):
                    away = v.get("name") or v.get("displayName")
                elif isinstance(v, str):
                    away = v
                if away:
                    break

            dt_raw = None
            for dk in ("startDate", "startTime", "utcTime", "kickoff", "start"):
                if isinstance(obj.get(dk), str):
                    dt_raw = obj[dk]
                    break

            if home and away and dt_raw:
                try:
                    dt = datetime.fromisoformat(dt_raw.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=ZoneInfo("Asia/Kuwait"))
                    _zain_add(
                        events,
                        dt.astimezone(UTC),
                        home,
                        away,
                        "Soccerway-Zain",
                        SOCCERWAY_ZAIN,
                    )
                except Exception:
                    pass

            for v in obj.values():
                walk(v)

        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    for s in soup.find_all("script"):
        if not s.string:
            continue
        typ = (s.get("type") or "").casefold()
        if "json" not in typ:
            continue
        try:
            walk(json.loads(s.string))
        except Exception:
            pass

    return events


def parse_zain() -> list[dict]:
    # Official KFA page is the season/competition validation source.
    try:
        official = fetch_text(KFA_ZAIN_2627)
        if "2026-2027" not in official and "2026–2027" not in official:
            warn("KFA Zain 2026/27 validation page did not contain expected season marker")
    except Exception as exc:
        warn(f"KFA Zain official validation failed: {exc}")

    events = []

    # Primary fixture-time source: every accepted match must carry its own
    # visible date/time line.
    try:
        events.extend(_parse_oddalerts_zain())
    except Exception as exc:
        warn(f"Zain OddAlerts failed: {exc}")

    # Structured fallback only if primary produced nothing.
    if not events:
        try:
            events.extend(_parse_soccerway_zain())
        except Exception as exc:
            warn(f"Zain Soccerway failed: {exc}")

    events = dedupe(events)
    log(f"Zain Premier League fixtures detected: {len(events)}")
    return events


def parse_ksw() -> list[dict]:
    events = []
    try:
        soup = BeautifulSoup(fetch_text(KSW_HOME), "html.parser")
        text = norm(soup.get_text(" ", strip=True))

        pat = re.compile(
            r"(XTB\s+KSW\s+\d+).*?"
            r"(20\d{2})-(\d{2})-(\d{2})\s*\|\s*(\d{1,2}):(\d{2})",
            re.I
        )

        central_europe = ZoneInfo("Europe/Warsaw")

        for m in pat.finditer(text):
            title = norm(m.group(1)).upper()
            y, mo, d, hh, mm = map(int, m.groups()[1:])
            try:
                local = datetime(y, mo, d, hh, mm, tzinfo=central_europe)
                start_utc = local.astimezone(UTC)
            except Exception:
                continue

            if not in_window(start_utc):
                continue

            events.append({
                "start": start_utc,
                "title": title,
                "competition": "KSW",
                "source_name": "KSWOfficial",
                "source": KSW_HOME,
                "duration_minutes": 240,
            })

    except Exception as exc:
        warn(f"KSW official failed: {exc}")

    events = dedupe(events)
    log(f"KSW events detected in window: {len(events)}")
    return events

def build_day_description(day_utc: date, day_events: list[dict]) -> str:
    if not day_events:
        return (
            f"شاشا | {day_utc.isoformat()}\n\n"
            "لا توجد مباريات مجدولة على شاشا."
        )

    lines = [f"جدول شاشا الرياضي | {day_utc.isoformat()}", ""]

    for ev in sorted(day_events, key=lambda x: x["start"]):
        lines.append(f"• {ev['title']} — {competition_ar(ev['competition'])}")

    return "\n".join(lines)

def add_programme(root, start, stop, title, desc, category="Sports"):
    p = ET.SubElement(
        root, "programme",
        start=xmltv_time(start),
        stop=xmltv_time(stop),
        channel=CHANNEL_ID,
    )
    ET.SubElement(p, "title", lang="ar").text = title
    ET.SubElement(p, "desc", lang="ar").text = desc
    ET.SubElement(p, "category", lang="en").text = category

def write_xml(events: list[dict]) -> None:
    root = ET.Element("tv", generator_info_name="Shasha Sports Guide FINAL")

    ch = ET.SubElement(root, "channel", id=CHANNEL_ID)
    ET.SubElement(ch, "display-name", lang="ar").text = CHANNEL_NAME
    ET.SubElement(ch, "display-name", lang="en").text = "SHASHA GUIDE"
    ET.SubElement(ch, "icon", src=CHANNEL_ICON)

    today_utc = utc_now().date()
    first_day = today_utc - timedelta(days=DAYS_BACK)
    last_day = today_utc + timedelta(days=DAYS_FORWARD)

    # Matches kicking off at the same moment must share ONE programme: this
    # is a single guide channel, so emitting them separately produced
    # overlapping entries and the player showed only one of them.
    slots: dict[datetime, list[dict]] = {}
    for ev in events:
        slots.setdefault(ev["start"].astimezone(UTC), []).append(ev)
    slot_starts = sorted(slots)

    def next_slot_after(moment: datetime) -> datetime | None:
        return next((s for s in slot_starts if s >= moment), None)

    def slot_title(slot_start: datetime) -> str:
        return " + ".join(ev["title"] for ev in slots[slot_start])

    def add_countdown(gap_start: datetime, gap_stop: datetime, desc: str) -> None:
        """Fill a gap with consecutive blocks counting down to the next match."""
        cursor = gap_start
        while cursor < gap_stop:
            upcoming = next_slot_after(cursor)
            if upcoming is None:
                add_programme(
                    root, cursor, gap_stop,
                    "لا توجد مباراة قادمة على شاشا", desc,
                )
                return

            remaining = upcoming - cursor
            stop = min(cursor + countdown_step(remaining), gap_stop, upcoming)
            if stop <= cursor:
                return

            add_programme(
                root, cursor, stop,
                countdown_title(slot_title(upcoming),
                                remaining.total_seconds() // 60),
                desc,
            )
            cursor = stop

    by_day: dict[date, list[dict]] = {}
    for ev in events:
        d = ev["start"].astimezone(UTC).date()
        by_day.setdefault(d, []).append(ev)

    for offset in range((last_day - first_day).days + 1):
        d = first_day + timedelta(days=offset)
        day_events = sorted(by_day.get(d, []), key=lambda x: x["start"])
        desc = build_day_description(d, day_events)

        day_start = datetime(d.year, d.month, d.day, 0, 0, tzinfo=UTC)
        day_end = day_start + timedelta(days=1)

        day_slots = [s for s in slot_starts if day_start <= s < day_end]

        if not day_slots:
            add_countdown(day_start, day_end, desc)
            continue

        cursor = day_start

        for index, slot_start in enumerate(day_slots):
            if slot_start > cursor:
                add_countdown(cursor, slot_start, desc)

            group = slots[slot_start]
            duration = max(int(ev.get("duration_minutes", 135)) for ev in group)

            limit = day_end
            if index + 1 < len(day_slots):
                limit = min(limit, day_slots[index + 1])

            slot_stop = min(slot_start + timedelta(minutes=duration), limit)
            if slot_stop <= cursor:
                continue

            add_programme(
                root,
                max(slot_start, cursor),
                slot_stop,
                with_live_badge(slot_title(slot_start)),
                desc,
                category=competition_ar(group[0]["competition"]),
            )

            cursor = max(cursor, slot_stop)

        if cursor < day_end:
            add_countdown(cursor, day_end, desc)

    try:
        ET.indent(root, space="  ")
    except AttributeError:
        pass

    ET.ElementTree(root).write(OUTPUT, encoding="utf-8", xml_declaration=True)

    log("SHASHA CURRENT COVERAGE | YES")
    days = []
    for d in sorted(by_day):
        if first_day <= d <= last_day:
            days.append(f"{d.isoformat()}:{len(by_day[d])}")
    log("SHASHA GUIDE DAYS | " + (", ".join(days) if days else "NO EVENTS IN WINDOW"))
    log(f"Written: {OUTPUT}")

def main():
    log(
        "SHASHA FINAL vTIMEFIX | SOURCE-AWARE INPUT TIMES | UTC XMLTV | "
        "TIVIMATE AUTO-CONVERT | NO ABU DHABI/LAS VEGAS"
    )

    events = []
    events.extend(parse_serie_a())
    events.extend(parse_zain())
    events.extend(parse_ksw())
    events = dedupe(events)

    log(f"Shasha total verified programmes: {len(events)}")
    for ev in events:
        src_dt = ev["start"]
        log(
            f"  SHASHA GUIDE | {src_dt.isoformat()} | "
            f"{ev['title']} | {ev['competition']} | {ev['source_name']}"
        )

    write_xml(events)

if __name__ == "__main__":
    main()
