#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: alkass.net/tvguide shows only three distinct schedules across
its eight channels (1=4=8, 2=5=7, 3=6) and none of them matches what beIN
publishes for the same day. Before either source can be trusted, two
things have to be settled: which day that page is actually showing (it
carries the words "اليوم" and "غدا"), and whether each block really names
a different channel. This dumps the raw markup around the day words and
around every channel image. Changes nothing.
"""
from __future__ import annotations

import re

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "Accept-Language": "ar,en;q=0.8"}
T = (5, 25)
URL = "https://www.alkass.net/tvguide"


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def main():
    r = requests.get(URL, headers=H, timeout=T)
    t = r.text
    print(f"status={r.status_code} bytes={len(t)}", flush=True)

    section("markup around the day words")
    for word in ("اليوم", "غدا"):
        for m in re.finditer(word, t):
            print(f"\n---- {word} at {m.start()} ----", flush=True)
            print(t[max(0, m.start() - 1500):m.start() + 600].replace("\n", " "),
                  flush=True)

    section("anything that looks like a day / tab control")
    for m in re.finditer(r"<[^>]*(?:day|tab|date|nav-)[^>]*>", t, re.I):
        print("  ", m.group(0)[:220], flush=True)

    section("markup before each channel image")
    for m in re.finditer(r"assets/images/(one|two|three|four|five|six|seven|eight)_\.png",
                         t):
        print(f"\n---- {m.group(1)}_ at {m.start()} ----", flush=True)
        print(t[max(0, m.start() - 1500):m.start() + 200].replace("\n", " "), flush=True)


if __name__ == "__main__":
    main()
