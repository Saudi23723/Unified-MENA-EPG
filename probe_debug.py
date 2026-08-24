#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: find out why beIN Sports Türkiye produces 0 programmes.

Run on GitHub Actions (unrestricted network) — this sandbox cannot reach
digiturk.com.tr. Deleted once the real markup has been inspected.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

AJAX_URL = "https://www.digiturk.com.tr/Ajax/GetTvGuideFromDigiturk"
ISTANBUL = ZoneInfo("Europe/Istanbul")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "tr,en;q=0.8",
    "X-Requested-With": "XMLHttpRequest",
}

# What the current parser looks for.
EXPECTED = [
    ".channelDetail",
    ".tvGuideResult-box-wholeDates-title",
    ".tvGuideResult-box-wholeDates-time-hour",
    ".tvGuideResult-box-wholeDates-time-totalMinute",
]
KNOWN_IDS = {"193", "310", "312", "495", "506", "507", "508", "541"}


def probe(url: str, label: str, headers=HEADERS):
    print(f"\n{'='*70}\n{label}\n{'='*70}")
    try:
        r = requests.get(url, headers=headers, timeout=25)
    except Exception as exc:
        print(f"  REQUEST FAILED: {exc}")
        return None
    print(f"  status={r.status_code}  len={len(r.text)}  ctype={r.headers.get('content-type')}")
    if r.status_code != 200 or not r.text.strip():
        print("  BODY HEAD:", r.text[:600].replace("\n", " ")[:600])
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    print("\n  -- expected selectors --")
    for sel in EXPECTED:
        print(f"     {sel:52} -> {len(soup.select(sel))}")

    classes = Counter()
    for tag in soup.find_all(True):
        for c in tag.get("class", []) or []:
            classes[c] += 1
    print("\n  -- 30 most common classes actually present --")
    for c, n in classes.most_common(30):
        print(f"     {n:5}  {c}")

    onclicks = [t.get("onclick") for t in soup.find_all(attrs={"onclick": True})]
    print(f"\n  -- onclick attributes: {len(onclicks)} --")
    for o in onclicks[:5]:
        print(f"     {o[:110]}")
    ids = Counter()
    for o in onclicks:
        m = re.search(r"\s(\d+)\)", o or "")
        if m:
            ids[m.group(1)] += 1
    print(f"  distinct ids via current regex: {len(ids)}")
    print(f"  overlap with hardcoded roster : {sorted(set(ids) & KNOWN_IDS)}")
    print(f"  sample ids found              : {[i for i, _ in ids.most_common(15)]}")

    low = r.text.lower()
    print("\n  -- keyword presence --")
    for kw in ("bein", "spor", "tvguide", "channeldetail", "captcha", "cloudflare", "just a moment"):
        print(f"     {kw:16} {'YES' if kw in low else 'no'}")

    print("\n  -- body head --")
    print("   ", r.text[:700].replace("\n", " ")[:700])
    return r.text


def main():
    today = datetime.now(ISTANBUL)
    day_param = today.strftime("%m/%d/%Y") + "+00%3A00%3A00"

    probe(f"{AJAX_URL}?Day={day_param}", "A) current call (encoded +00:00:00, XHR header)")
    probe(f"{AJAX_URL}?Day={today.strftime('%m/%d/%Y')}", "B) Day without the time suffix")
    probe(f"{AJAX_URL}?Day={today.strftime('%Y-%m-%d')}", "C) ISO date")
    probe(AJAX_URL, "D) no parameters at all")

    h = {k: v for k, v in HEADERS.items() if k != "X-Requested-With"}
    probe(f"{AJAX_URL}?Day={day_param}", "E) same as A but WITHOUT the XHR header", headers=h)

    probe("https://www.digiturk.com.tr/yayin-akisi", "F) the human TV-guide page")


if __name__ == "__main__":
    main()
