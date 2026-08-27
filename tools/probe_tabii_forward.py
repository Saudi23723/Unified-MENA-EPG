#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Look for a source that lists tabii Spor 1-10 *ahead of today*.

The ten PPV numbers currently come from Spor Ekranı, which renders the
current day and only the current day, so those channels are empty from
tomorrow on while the linear channel carries a full week. This probe asks
every candidate the same two questions:

  1. does it answer at all, from a runner in a country these hosts serve?
  2. does its answer name a numbered tabii channel on a date after today?

It writes nothing and publishes nothing. It is run from a branch, prints
what it found, and is deleted once the answer is known.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta

import requests

TODAY = date.today()
TOMORROW = TODAY + timedelta(days=1)
DAY_AFTER = TODAY + timedelta(days=2)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/127.0 Safari/537.36")

LD_JSON_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S)
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
# "tabii Spor 3" / "tabii spor3" / "Tabii Spor 10"
NUMBERED_RE = re.compile(r"tab(?:i|İ|ı)i?\s*spor\s*(\d{1,2})", re.I)
ISO_DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")


def candidates() -> list[tuple[str, str]]:
    """(label, url). Grouped by the idea being tested, not by host."""
    d1, d2 = TOMORROW.isoformat(), DAY_AFTER.isoformat()
    tr1 = TOMORROW.strftime("%d-%m-%Y")
    out = [
        # Spor Ekranı — does any path give a day other than today?
        ("sporekrani home",        "https://www.sporekrani.com/"),
        ("sporekrani day path",    f"https://www.sporekrani.com/home/day/{d1}"),
        ("sporekrani day +2",      f"https://www.sporekrani.com/home/day/{d2}"),
        ("sporekrani ?date",       f"https://www.sporekrani.com/?date={d1}"),
        ("sporekrani ?gun",        f"https://www.sporekrani.com/?gun={d1}"),
        ("sporekrani /yarin",      "https://www.sporekrani.com/yarin"),
        ("sporekrani tr date",     f"https://www.sporekrani.com/home/day/{tr1}"),
        ("sporekrani api day",     f"https://www.sporekrani.com/api/day/{d1}"),

        # tabii itself
        ("tabii tr live",          "https://www.tabii.com/tr/live"),
        ("tabii tr spor",          "https://www.tabii.com/tr/spor"),
        ("tabii epg api",          "https://eu1.tabii.com/apigateway/epg/channels"),

        # TRT — do numbered slugs exist?
        ("trt tabii-spor-1",       "https://www.trtspor.com.tr/yayin-akisi/tabii-spor-1"),
        ("trt tabii-spor-3",       "https://www.trtspor.com.tr/yayin-akisi/tabii-spor-3"),
        ("trt yayin-akisi index",  "https://www.trtspor.com.tr/yayin-akisi"),

        # Other Turkish guides
        ("tvyayinakisi tabii-1",   "https://www.tvyayinakisi.com/tabii-spor-1-yayin-akisi/"),
        ("canlitv tabii spor 1",   "https://www.canlitv.com/tabii-spor-1"),
        ("programtv",              "https://www.programtv.com.tr/"),
        ("sporx tv rehberi",       "https://www.sporx.com/tv-rehberi/"),

        # Fixture lists that sometimes name the broadcaster with its number
        ("mackolik",               "https://www.mackolik.com/"),
        ("sahadan program",        "https://www.sahadan.com/"),
    ]
    return out


def dates_near(text: str) -> set[str]:
    """Every ISO date in the text that is tomorrow or later."""
    found = set()
    for raw in ISO_DATE_RE.findall(text):
        try:
            when = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            continue
        if when >= TOMORROW:
            found.add(raw)
    return found


def forward_numbered(text: str) -> list[str]:
    """Numbered-tabii mentions that sit near a date after today.

    A page can mention "tabii Spor 5" for a match tonight and a date for
    next week in an unrelated banner; requiring the two within the same
    1500-character window is a crude but honest way to ask whether the
    page really schedules a numbered channel ahead.
    """
    hits = []
    for match in NUMBERED_RE.finditer(text):
        window = text[max(0, match.start() - 1500): match.end() + 1500]
        ahead = dates_near(window)
        if ahead:
            hits.append(f"{match.group(0).strip()} near {sorted(ahead)[:3]}")
    return hits[:8]


def structured_dates(text: str) -> set[str]:
    """Dates inside JSON-LD / __NEXT_DATA__ only — no page furniture."""
    blobs = LD_JSON_RE.findall(text) + NEXT_DATA_RE.findall(text)
    found = set()
    for blob in blobs:
        try:
            json.loads(blob)
        except Exception:
            pass
        found |= dates_near(blob)
    return found


def probe(session: requests.Session, label: str, url: str) -> None:
    try:
        response = session.get(url, timeout=25, headers={"User-Agent": UA})
    except Exception as exc:
        print(f"  {label:<24} ERROR  {type(exc).__name__}: {exc}")
        return

    text = response.text or ""
    numbered = sorted({int(n) for n in NUMBERED_RE.findall(text)})
    ahead_all = sorted(dates_near(text))[:5]
    ahead_structured = sorted(structured_dates(text))[:5]
    forward = forward_numbered(text)

    print(f"  {label:<24} http={response.status_code} "
          f"bytes={len(response.content)}")
    print(f"      numbered tabii channels named : {numbered or '—'}")
    print(f"      dates >= tomorrow, structured : {ahead_structured or '—'}")
    print(f"      dates >= tomorrow, anywhere   : {ahead_all or '—'}")
    if forward:
        print(f"      *** NUMBERED CHANNEL NEAR A FUTURE DATE ***")
        for hit in forward:
            print(f"          {hit}")


def main() -> int:
    print(f"tabii forward-source probe | today={TODAY} tomorrow={TOMORROW}")
    print("Looking for: a numbered tabii channel scheduled after today.\n")
    session = requests.Session()
    for label, url in candidates():
        print(f"{url}")
        probe(session, label, url)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
