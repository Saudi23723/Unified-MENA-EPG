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

OUTPUT = "shasha_epg.xml"

CHANNEL_ID = "ShashaGuide"
CHANNEL_NAME = "SHASHA GUIDE | شاشا"
CHANNEL_ICON = "https://www.shasha.com/favicon.ico"

ABU_DHABI = ZoneInfo("Asia/Dubai")
LAS_VEGAS = ZoneInfo("America/Los_Angeles")
UTC = timezone.utc

DAYS_BACK = 1
DAYS_FORWARD = 21

HTTP_TIMEOUT = 18
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)

ESPN_SERIE_A = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/"
    "ita.1/scoreboard?dates={day}"
)

SOFASCORE_ZAIN_ID = 1002
SOFASCORE_NEXT = (
    "https://www.sofascore.com/api/v1/unique-tournament/"
    f"{SOFASCORE_ZAIN_ID}/events/next/{{page}}"
)
SOFASCORE_LAST = (
    "https://www.sofascore.com/api/v1/unique-tournament/"
    f"{SOFASCORE_ZAIN_ID}/events/last/{{page}}"
)

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
        "ESPN-SerieA": 110,
        "Sofascore-Zain": 110,
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
            if ev["start"].astimezone(ABU_DHABI).date() != old["start"].astimezone(ABU_DHABI).date():
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

def parse_serie_a() -> list[dict]:
    events = []
    start, end = window_bounds()
    day = start.date()
    last = end.date()

    while day <= last:
        url = ESPN_SERIE_A.format(day=day.strftime("%Y%m%d"))
        try:
            data = fetch_json(url)
            for item in data.get("events", []):
                dt_raw = item.get("date")
                if not dt_raw:
                    continue
                try:
                    start_utc = datetime.fromisoformat(dt_raw.replace("Z", "+00:00")).astimezone(UTC)
                except Exception:
                    continue

                if not in_window(start_utc):
                    continue

                comps = item.get("competitions") or []
                if not comps:
                    continue

                competitors = comps[0].get("competitors") or []
                home = away = None
                for c in competitors:
                    name = ((c.get("team") or {}).get("displayName")
                            or (c.get("team") or {}).get("shortDisplayName")
                            or "")
                    if c.get("homeAway") == "home":
                        home = team_name(name)
                    elif c.get("homeAway") == "away":
                        away = team_name(name)

                if not home or not away:
                    name = norm(item.get("name", ""))
                    if " at " in name:
                        away, home = [team_name(x) for x in name.split(" at ", 1)]
                    elif " vs " in name:
                        home, away = [team_name(x) for x in name.split(" vs ", 1)]

                if not home or not away:
                    continue

                events.append({
                    "start": start_utc,
                    "title": f"{home} - {away}",
                    "competition": "Serie A",
                    "source_name": "ESPN-SerieA",
                    "source": url,
                    "duration_minutes": 135,
                })
        except Exception as exc:
            warn(f"Serie A {day.isoformat()} failed: {exc}")

        day += timedelta(days=1)

    events = dedupe(events)
    log(f"Serie A fixtures detected: {len(events)}")
    return events

def _parse_sofascore_events(data, events):
    for item in data.get("events", []):
        tournament = item.get("tournament") or {}
        unique = tournament.get("uniqueTournament") or {}
        uid = unique.get("id")

        if uid is not None and int(uid) != SOFASCORE_ZAIN_ID:
            continue

        ts = item.get("startTimestamp")
        if not ts:
            continue
        try:
            start_utc = datetime.fromtimestamp(int(ts), UTC)
        except Exception:
            continue

        if not in_window(start_utc):
            continue

        home = team_name((item.get("homeTeam") or {}).get("name", ""))
        away = team_name((item.get("awayTeam") or {}).get("name", ""))
        if not home or not away:
            continue

        events.append({
            "start": start_utc,
            "title": f"{home} - {away}",
            "competition": "Zain Premier League",
            "source_name": "Sofascore-Zain",
            "source": "https://www.sofascore.com/football/tournament/kuwait/zain-premier-league/1002",
            "duration_minutes": 135,
        })

def parse_zain() -> list[dict]:
    events = []
    for kind, template, pages in (
        ("next", SOFASCORE_NEXT, range(0, 5)),
        ("last", SOFASCORE_LAST, range(0, 2)),
    ):
        for page in pages:
            url = template.format(page=page)
            try:
                data = fetch_json(url)
                _parse_sofascore_events(data, events)
                if data.get("hasNextPage") is False:
                    break
            except Exception as exc:
                warn(f"Zain Sofascore {kind} page {page} failed: {exc}")
                break

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

def build_day_description(day_ad: date, day_events: list[dict]) -> str:
    if not day_events:
        return (
            f"شاشا | {day_ad.isoformat()}\n\n"
            "لا توجد مباريات مجدولة على شاشا."
        )

    lines = [f"جدول شاشا الرياضي | {day_ad.isoformat()}", ""]

    for ev in sorted(day_events, key=lambda x: x["start"]):
        ad = ev["start"].astimezone(ABU_DHABI)
        lv = ev["start"].astimezone(LAS_VEGAS)
        lines.append(f"• {ev['title']} — {competition_ar(ev['competition'])}")
        lines.append(f"  {ad:%H:%M} أبو ظبي | {lv:%H:%M} لاس فيغاس")

    lines.extend(["", "الأوقات: أبو ظبي + لاس فيغاس."])
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

    today_ad = utc_now().astimezone(ABU_DHABI).date()
    first_day = today_ad - timedelta(days=DAYS_BACK)
    last_day = today_ad + timedelta(days=DAYS_FORWARD)

    by_day = {}
    for ev in events:
        d = ev["start"].astimezone(ABU_DHABI).date()
        by_day.setdefault(d, []).append(ev)

    for offset in range((last_day - first_day).days + 1):
        d = first_day + timedelta(days=offset)
        day_events = sorted(by_day.get(d, []), key=lambda x: x["start"])
        desc = build_day_description(d, day_events)

        day_start_ad = datetime(d.year, d.month, d.day, 0, 0, tzinfo=ABU_DHABI)
        day_end_ad = day_start_ad + timedelta(days=1)
        day_start = day_start_ad.astimezone(UTC)
        day_end = day_end_ad.astimezone(UTC)

        if not day_events:
            add_programme(
                root,
                day_start,
                day_end,
                "لا توجد مباريات مجدولة على شاشا",
                desc,
            )
            continue

        cursor = day_start

        for ev in day_events:
            ev_start = ev["start"].astimezone(UTC)

            if ev_start > cursor:
                add_programme(
                    root,
                    cursor,
                    ev_start,
                    "جدول مباريات شاشا اليوم",
                    desc,
                )

            duration = int(ev.get("duration_minutes", 135))
            ev_stop = min(ev_start + timedelta(minutes=duration), day_end)

            ad = ev_start.astimezone(ABU_DHABI)
            lv = ev_start.astimezone(LAS_VEGAS)
            title = (
                f"{ev['title']} | "
                f"{ad:%H:%M} أبو ظبي | {lv:%H:%M} لاس فيغاس"
            )

            add_programme(
                root,
                ev_start,
                ev_stop,
                title,
                desc,
                category=competition_ar(ev["competition"]),
            )

            cursor = max(cursor, ev_stop)

        if cursor < day_end:
            add_programme(
                root,
                cursor,
                day_end,
                "جدول مباريات شاشا اليوم",
                desc,
            )

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
        "SHASHA FINAL | Serie A structured + Zain structured + KSW official "
        "| NO OCR | Abu Dhabi + Las Vegas"
    )

    events = []
    events.extend(parse_serie_a())
    events.extend(parse_zain())
    events.extend(parse_ksw())
    events = dedupe(events)

    log(f"Shasha total verified programmes: {len(events)}")
    for ev in events:
        ad = ev["start"].astimezone(ABU_DHABI)
        lv = ev["start"].astimezone(LAS_VEGAS)
        log(
            f"  SHASHA GUIDE | {ad:%Y-%m-%d %H:%M} أبو ظبي"
            f" | {lv:%Y-%m-%d %H:%M} لاس فيغاس"
            f" | {ev['title']} | {ev['competition']} | {ev['source_name']}"
        )

    write_xml(events)

if __name__ == "__main__":
    main()
