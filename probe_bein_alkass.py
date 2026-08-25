#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate a linear-scan parser for bein.com before the generator uses it.

The first attempt split the page on the channel row wrapper, which the
Arabic edition has and the English one apparently does not - every English
slot landed on Alkass 1 (776 of them) and the other seven came back empty.

Scanning the document in order instead and attaching each slot to the most
recent Alkass logo seen works whatever the wrapper looks like. This checks
that on both editions before a single line of it goes into the generator.
"""
from __future__ import annotations

import html
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

DOHA = timezone(timedelta(hours=3))
H = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ar,en;q=0.8"}
T = (5, 25)
URL = ("https://www.bein.com/{lang}/epg-ajax-template/?action=epg_fetch"
       "&category=sports&cdate={d}&language={LANG}&loadindex=0&mins=00"
       "&offset=0&postid={pid}&serviceidentity=bein.net")

# A slot, or a channel logo. Scanned together so document order decides
# which channel a slot belongs to.
TOKEN = re.compile(
    r"(?P<logo>2023_Alkass_(?P<n>\d+)\.png)"
    r"|(?P<li><li\s[^>]*?>.*?</li>)", re.S | re.I)
RANGE = re.compile(r"data-start='(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'\s+"
                   r"data-end='(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'")
TITLE = re.compile(r"<p class=title>(.*?)</p>", re.S)
OTHER_LOGO = re.compile(r"/(\d{4})_([A-Za-z0-9_]+)\.png", re.I)


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(s or ""))).strip()


def parse(text: str) -> dict[int, dict[str, tuple[str, str]]]:
    """{alkass number: {start: (stop, title)}}, by document order."""
    out: dict[int, dict[str, tuple[str, str]]] = defaultdict(dict)
    current: int | None = None
    for m in TOKEN.finditer(text or ""):
        if m.group("logo"):
            current = int(m.group("n"))
            continue
        # A logo for some other channel ends the current Alkass block.
        li = m.group("li")
        if current is None:
            continue
        rng, ti = RANGE.search(li), TITLE.search(li)
        if not rng or not ti:
            continue
        out[current][rng.group(1)] = (rng.group(2), clean(ti.group(1)))
    return out


def parse_scoped(text: str) -> dict[int, dict[str, tuple[str, str]]]:
    """Same, but a non-Alkass logo clears the current channel, so slots
    belonging to other channels are not swept up."""
    out: dict[int, dict[str, tuple[str, str]]] = defaultdict(dict)
    current: int | None = None
    pos = 0
    combined = re.compile(
        r"(?P<any>/\d{4}_[A-Za-z0-9_]+\.png)|(?P<li><li\s[^>]*?>.*?</li>)", re.S | re.I)
    for m in combined.finditer(text or ""):
        if m.group("any"):
            mm = re.search(r"/2023_Alkass_(\d+)\.png", m.group("any"), re.I)
            current = int(mm.group(1)) if mm else None
            continue
        if current is None:
            continue
        li = m.group("li")
        rng, ti = RANGE.search(li), TITLE.search(li)
        if not rng or not ti:
            continue
        out[current][rng.group(1)] = (rng.group(2), clean(ti.group(1)))
    return out


def main():
    today = datetime.now(DOHA).strftime("%Y-%m-%d")
    for lang, pid in (("ar", "25344"), ("en", "25356")):
        r = requests.get(URL.format(lang=lang, LANG=lang.upper(), pid=pid, d=today),
                         headers=H, timeout=T)
        print(f"\n{'='*74}\n{lang.upper()}  status={r.status_code} len={len(r.text)}\n{'='*74}")
        if r.status_code != 200:
            continue
        for name, fn in (("naive (any logo starts a block)", parse),
                         ("scoped (other logos clear it)", parse_scoped)):
            got = fn(r.text)
            counts = {n: len(got.get(n, {})) for n in range(1, 9)}
            total = sum(counts.values())
            print(f"  {name:34} per channel={counts} total={total}")

        got = parse_scoped(r.text)
        print("\n  Alkass 1, first 6 slots:")
        for s in sorted(got.get(1, {}))[:6]:
            stop, title = got[1][s]
            print(f"    {s[11:16]}-{stop[11:16]}  {title[:52]}")
        print("  Alkass 5, first 4 slots:")
        for s in sorted(got.get(5, {}))[:4]:
            stop, title = got[5][s]
            print(f"    {s[11:16]}-{stop[11:16]}  {title[:52]}")

        bad = sum(1 for n in got for s, (e, _t) in got[n].items() if e <= s)
        print(f"\n  slots with end <= start: {bad}")


if __name__ == "__main__":
    main()
