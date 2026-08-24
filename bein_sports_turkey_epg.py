#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
beIN SPORTS Türkiye — full official EPG.

Source: Digiturk's own public TV-guide AJAX endpoint (the same call
digiturk.com.tr's own website makes to render its TV guide widget):

  GET https://www.digiturk.com.tr/Ajax/GetTvGuideFromDigiturk?Day=MM/DD/YYYY+00:00:00

beIN Sports Türkiye is carried on Digiturk, and Digiturk publishes every
channel's schedule (including all beIN SPORTS TR channels) through this
one endpoint. No data is invented — every title/start/duration comes
straight from that HTML response.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from epg_lib import add_programme, fetch, log, new_session, norm, run_main, utc_now, warn, write_xml_atomic

OUTPUT = "bein_sports_turkey_epg.xml"
UTC = timezone.utc
ISTANBUL = ZoneInfo("Europe/Istanbul")

DAYS_BACK = 1
DAYS_FORWARD = 6

AJAX_URL = "https://www.digiturk.com.tr/Ajax/GetTvGuideFromDigiturk"

# Last-known-good site_id roster for every beIN-branded channel on
# Digiturk. If Digiturk ever renumbers a channel, that single channel just
# stops receiving programmes (the rest keep working) until the id is
# refreshed — it can never crash or break the other channels.
CHANNELS = {
    "193": "beIN SPORTS 1",
    "310": "beIN SPORTS 2",
    "312": "beIN SPORTS 3",
    "495": "beIN SPORTS 4",
    "506": "beIN SPORTS 5",
    "507": "beIN SPORTS MAX 1",
    "508": "beIN SPORTS MAX 2",
    "541": "beIN SPORTS HABER",
}

ONCLICK_ID_RE = re.compile(r"\s(\d+)\)")
DURATION_RE = re.compile(r"\d+")


def slugify_id(name: str) -> str:
    n = re.sub(r"[^A-Za-z0-9]+", "", name)
    return f"{n}.tr"


def fetch_day_html(session, day: datetime) -> str:
    day_param = day.strftime("%m/%d/%Y") + "+00%3A00%3A00"
    url = f"{AJAX_URL}?Day={day_param}"
    r = fetch(
        session, url,
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    return r.text


def parse_day(html: str, day: datetime) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    events: list[dict] = []

    for item in soup.select(".channelDetail"):
        title_el = item.select_one(".tvGuideResult-box-wholeDates-title")
        if not title_el:
            continue
        onclick = title_el.get("onclick") or ""
        m = ONCLICK_ID_RE.search(onclick)
        if not m:
            continue
        site_id = m.group(1)
        if site_id not in CHANNELS:
            continue

        title = norm(title_el.get_text(" ", strip=True))
        if not title:
            continue

        hour_el = item.select_one(".tvGuideResult-box-wholeDates-time-hour")
        dur_el = item.select_one(".tvGuideResult-box-wholeDates-time-totalMinute")
        if not hour_el or not dur_el:
            continue

        hour_text = norm(hour_el.get_text(" ", strip=True))
        dm = re.match(r"^([01]?\d|2[0-3]):([0-5]\d)", hour_text)
        if not dm:
            continue
        dur_m = DURATION_RE.search(norm(dur_el.get_text(" ", strip=True)))
        if not dur_m:
            continue

        hh, mm = int(dm.group(1)), int(dm.group(2))
        duration = int(dur_m.group(0))
        if duration <= 0:
            continue

        local = datetime(day.year, day.month, day.day, hh, mm, tzinfo=ISTANBUL)
        start_utc = local.astimezone(UTC)
        stop_utc = start_utc + timedelta(minutes=duration)

        events.append({
            "site_id": site_id,
            "start": start_utc,
            "stop": stop_utc,
            "title": title,
        })

    return events


def build() -> int:
    log("beIN SPORTS TÜRKİYE EPG | official digiturk.com.tr TV-guide AJAX endpoint | full channel roster")
    session = new_session()
    now = utc_now()

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — beIN Sports Türkiye"})
    for site_id, name in CHANNELS.items():
        xid = slugify_id(name)
        ch = ET.SubElement(root, "channel", id=xid)
        ET.SubElement(ch, "display-name", lang="tr").text = name

    today_ist = utc_now().astimezone(ISTANBUL)
    total = 0
    ok_days = 0

    for offset in range(-DAYS_BACK, DAYS_FORWARD + 1):
        day = today_ist + timedelta(days=offset)
        try:
            html = fetch_day_html(session, day)
            events = parse_day(html, day)
        except Exception as exc:
            warn(f"beIN Türkiye day {day.date()} failed: {exc}")
            continue

        if events:
            ok_days += 1

        for ev in events:
            name = CHANNELS[ev["site_id"]]
            xid = slugify_id(name)
            add_programme(
                root, xid, ev["start"], ev["stop"], ev["title"],
                category="Sports", live_eligible=True, now=now,
            )
            total += 1

    log(f"beIN Türkiye: {ok_days}/{DAYS_BACK + DAYS_FORWARD + 1} days fetched OK, {total} programmes total")

    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — beIN Sports Türkiye")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
