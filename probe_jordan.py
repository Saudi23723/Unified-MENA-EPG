#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: the livefootballtv page is full of fixtures; the parser sees one.

livefootballtv.info/channel/jordan-sports answers 200 with 133 clock
strings and names the Jordanian clubs dozens of times, yet the generator
extracts a single match across 24 days. So the fixtures are there and the
line-based reader is dropping them.

That reader walks soup.stripped_strings looking for a date line, then a
time line, then a block of up to 30 strings it tries to read a match out
of. This prints the same string sequence it walks, plus the markup around
a fixture, so the mismatch can be seen rather than guessed at.
Changes nothing.
"""
from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "Accept-Language": "ar,en;q=0.8"}
T = (5, 25)
URL = "https://www.livefootballtv.info/channel/jordan-sports"
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def main():
    r = requests.get(URL, headers=H, timeout=T)
    print(f"{URL} -> {r.status_code} {len(r.text)}b", flush=True)

    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    lines = [re.sub(r"\s+", " ", x).strip() for x in soup.stripped_strings]
    lines = [x for x in lines if x]

    section(f"the string sequence the parser walks ({len(lines)} strings)")
    for i, line in enumerate(lines[:220]):
        mark = ""
        if TIME_RE.match(line):
            mark = "   <<< TIME"
        elif re.search(r"\b(20\d{2}|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|"
                       r"Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b",
                       line, re.I):
            mark = "   <<< maybe DATE"
        print(f"  {i:4} {line[:96]!r}{mark}", flush=True)

    section("markup around the first fixtures")
    body = r.text
    for name in ("Faisaly", "Wehdat", "Hussein"):
        m = re.search(name, body, re.I)
        if not m:
            print(f"  {name}: not in the markup", flush=True)
            continue
        print(f"\n---- {name} at {m.start()} ----", flush=True)
        print(body[max(0, m.start() - 1600):m.start() + 800].replace("\n", " "),
              flush=True)

    section("classes that look like a fixture row")
    tally = {}
    for m in re.finditer(r'class="([^"]{2,90})"', r.text):
        for token in m.group(1).split():
            if re.search(r"match|fixture|game|event|time|date|team|row|list|day",
                         token, re.I):
                tally[token] = tally.get(token, 0) + 1
    for k, v in sorted(tally.items(), key=lambda x: -x[1])[:30]:
        print(f"  {v:5}  {k}", flush=True)


if __name__ == "__main__":
    main()
