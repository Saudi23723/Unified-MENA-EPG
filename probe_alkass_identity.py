#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: extract Alkass's own guide (alkass.net/tvguide) in full.

beIN's guide repeats Alkass 1's schedule on Alkass 4 and Alkass 5's on
Alkass 7, so it cannot be right for all eight. Alkass publishes its own
guide as one page: each channel is a collapsible block keyed by
assets/images/<name>_.png with a table of programme name + start time.
Before switching this project's source over, three things have to be
known: which image means which channel, how many days the page carries,
and whether the times are Doha local. Changes nothing.
"""
from __future__ import annotations

import html
import re

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "Accept-Language": "ar,en;q=0.8"}
T = (5, 25)
URL = "https://www.alkass.net/tvguide"

BLOCK = re.compile(
    r"data-target=\"#(?P<key>[^\"]+)\".*?"
    r"assets/images/(?P<img>[^\"']+)\.png.*?"
    r"<ul class=\"collapse\" id=\"(?P=key)\">(?P<body>.*?)</ul>", re.S)
ROW = re.compile(
    r"tv-prog-name'>(?P<name>.*?)</td>\s*"
    r"<td class='team-result__status tv-prog-time'>(?P<time>[^<]*)</td>", re.S)


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def main():
    r = requests.get(URL, headers=H, timeout=T)
    t = r.text
    print(f"status={r.status_code} bytes={len(t)}", flush=True)

    section("dates / day labels anywhere on the page")
    for pat in (r"\d{4}-\d{2}-\d{2}", r"\d{1,2}/\d{1,2}/\d{4}",
                r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*day",
                r"(?:اليوم|غدا|غداً|الأحد|الإثنين|الاثنين|الثلاثاء|الأربعاء|الخميس|الجمعة|السبت)"):
        found = sorted(set(re.findall(pat, t)))[:12]
        print(f"  {pat}: {found}", flush=True)

    section("every channel block")
    blocks = list(BLOCK.finditer(t))
    print(f"{len(blocks)} blocks", flush=True)
    for b in blocks:
        rows = [(clean(m.group("time")), clean(m.group("name")))
                for m in ROW.finditer(b.group("body"))]
        print(f"\n  key={b.group('key')} img={b.group('img')}.png rows={len(rows)}",
              flush=True)
        for tm, nm in rows:
            print(f"    {tm}  {nm[:70]}", flush=True)

    section("what names sit next to each channel image")
    for m in re.finditer(r"assets/images/([A-Za-z0-9_]+)\.png", t):
        around = clean(t[max(0, m.start() - 400):m.end() + 400])
        print(f"  {m.group(1)}.png :: {around[:180]}", flush=True)


if __name__ == "__main__":
    main()
