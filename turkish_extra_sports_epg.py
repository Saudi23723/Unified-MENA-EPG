#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Turkey — EXXEN SPOR, Tivibu Spor, beIN CONNECT (best-effort).

Honesty note: none of these three publish a public schedule API (unlike
beinsports.com.tr/Digiturk, which does — see bein_sports_turkey_epg.py).
They are OTT/streaming platforms, not classic linear channels, so there is
no "official EPG" for them the way there is for a satellite channel.

Instead, like this repo's existing Jordan/ON-Sport/Shahid scripts, this
reads real match-to-channel assignments from Mackolik (mackolik.com), a
long-established major Turkish football data site whose /tvprogrami page
lists which channel/platform is broadcasting each match. Parsing is
intentionally structure-agnostic (line-by-line text + broadcaster-name
markers, not brittle CSS selectors) so a layout change degrades to fewer
matches found rather than crashing.

If a channel's name isn't explicitly mentioned next to a match, no
programme is created for it — nothing here is invented.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo

import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from epg_lib import add_programme, fetch, log, new_session, norm, run_main, utc_now, warn, write_xml_atomic

OUTPUT = "turkish_extra_sports_epg.xml"
UTC = timezone.utc
ISTANBUL = ZoneInfo("Europe/Istanbul")

MACKOLIK_TV = "https://www.mackolik.com/tvprogrami"
MATCH_MINUTES = 135

# Broadcaster name -> (xmltv_id base, display name). Matched case-
# insensitively against text near each fixture. Numbered variants (e.g.
# "Tivibu Spor 2", "beIN Connect 3") are detected and get their own
# channel id; unnumbered mentions fall back to the base channel.
BROADCASTERS = [
    (re.compile(r"\bexxen\s*spor(?:\s*(\d+))?\b", re.I), "ExxenSpor", "EXXEN SPOR"),
    (re.compile(r"\btivibu\s*spor(?:\s*(\d+))?\b", re.I), "TivibuSpor", "Tivibu Spor"),
    (re.compile(r"\bbein\s*connect(?:\s*(\d+))?\b", re.I), "beINConnect", "beIN CONNECT"),
]

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
DATE_TR_RE = re.compile(
    r"\b(\d{1,2})[./](\d{1,2})[./](20\d{2})\b"
)
AR_TR_DAYS = (
    "pazartesi", "salı", "sali", "çarşamba", "carsamba", "perşembe", "persembe",
    "cuma", "cumartesi", "pazar",
)


def _channel_for_line(text: str) -> tuple[str, str] | None:
    for pattern, base_id, base_name in BROADCASTERS:
        m = pattern.search(text)
        if not m:
            continue
        num = m.group(1)
        if num:
            return f"{base_id}{num}", f"{base_name} {num}"
        return base_id, base_name
    return None


FIXTURE_RE = re.compile(
    r"^([\wÀ-ſ .]{2,40}?)\s+(?:-|–|—|vs\.?|v)\s+([\wÀ-ſ .]{2,40})$", re.I,
)


def _fixture_from_line(line: str) -> str | None:
    m = FIXTURE_RE.match(line)
    if not m:
        return None
    home, away = norm(m.group(1)), norm(m.group(2))
    if not home or not away or home.casefold() == away.casefold():
        return None
    if TIME_RE.match(home) or TIME_RE.match(away):
        return None
    return f"{home} - {away}"


def parse_mackolik(html: str, today: date) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    lines = [norm(x) for x in soup.stripped_strings if norm(x)]
    events: list[dict] = []
    current_date = today

    i = 0
    while i < len(lines):
        line = lines[i]

        dm = DATE_TR_RE.search(line)
        if dm and len(line) < 40:
            dd, mm, yy = map(int, dm.groups())
            try:
                current_date = date(yy, mm, dd)
            except ValueError:
                pass
            i += 1
            continue

        low = line.casefold()
        if len(line) < 20 and any(d in low for d in AR_TR_DAYS) and not TIME_RE.match(line):
            i += 1
            continue

        tm = TIME_RE.match(line)
        if not tm:
            i += 1
            continue

        hh, mm = map(int, tm.groups())

        # A block runs from just after this time marker up to (but not
        # including) the next time marker or date header — mirrors the
        # block-consumption pattern already used in onsport_epg.py /
        # JORDAN_SPORTS_FINAL_VERIFIED.py, so a stray line from the *next*
        # fixture can never bleed into this one.
        block: list[str] = []
        j = i + 1
        while j < len(lines) and j <= i + 20:
            if TIME_RE.match(lines[j]) or DATE_TR_RE.search(lines[j]):
                break
            block.append(lines[j])
            j += 1

        fixture = next((f for f in (_fixture_from_line(x) for x in block) if f), None)
        channel = _channel_for_line(" | ".join(block)) if fixture else None

        if fixture and channel:
            xid, name = channel
            local = datetime(current_date.year, current_date.month, current_date.day, hh, mm, tzinfo=ISTANBUL)
            start_utc = local.astimezone(UTC)
            events.append({
                "xid": xid, "name": name,
                "start": start_utc,
                "stop": start_utc + timedelta(minutes=MATCH_MINUTES),
                "title": fixture,
            })

        i = max(i + 1, j)

    return events


def build() -> int:
    log("TURKEY EXTRA SPORTS EPG | EXXEN SPOR / Tivibu Spor / beIN CONNECT | best-effort via Mackolik")
    session = new_session()
    now = utc_now()
    today = now.astimezone(ISTANBUL).date()

    events: list[dict] = []
    try:
        r = fetch(session, MACKOLIK_TV)
        events = parse_mackolik(r.text, today)
        log(f"Mackolik TV program: {len(events)} matches found for EXXEN/Tivibu/beIN Connect")
    except Exception as exc:
        warn(f"Mackolik fetch/parse failed — 0 programmes this run: {exc}")

    root = ET.Element("tv", {"generator-info-name": "Unified MENA EPG — Turkey Extra Sports"})

    channels_seen: dict[str, str] = {}
    for ev in events:
        channels_seen.setdefault(ev["xid"], ev["name"])

    # Always declare at least the three base channels, even with 0
    # programmes this run, so they're visible/mappable in TiviMate.
    for xid, name in [("ExxenSpor", "EXXEN SPOR"), ("TivibuSpor", "Tivibu Spor"), ("beINConnect", "beIN CONNECT")]:
        channels_seen.setdefault(xid, name)

    for xid, name in channels_seen.items():
        ch = ET.SubElement(root, "channel", id=xid)
        ET.SubElement(ch, "display-name", lang="tr").text = name

    total = 0
    for ev in events:
        add_programme(
            root, ev["xid"], ev["start"], ev["stop"], ev["title"],
            category="Sports", live_eligible=True, now=now,
        )
        total += 1

    log(f"Turkey extra sports: {total} programmes across {len(channels_seen)} channels")

    write_xml_atomic(root, OUTPUT, generator_name="Unified MENA EPG — Turkey Extra Sports")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_main(build, OUTPUT))
