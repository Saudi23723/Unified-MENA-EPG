#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: parse the real grid on alkass.net/tvguide and compare it with
beIN's guide for the same day.

The page's collapsible list is duplicated rubbish; the grid under
<div class="tg-content"> is the real thing: a logo column (one.png …
eight.png, online.png) beside one table per channel, each programme a
<div class='programs' id='N'> carrying its title and an explicit
"HH:MM - HH:MM" range. This reads that grid per channel, checks whether
its channels really differ, and lines it up against beIN. Changes nothing.
"""
from __future__ import annotations

import html
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

DOHA = timezone(timedelta(hours=3))
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "Accept-Language": "ar,en;q=0.8"}
T = (5, 25)
BEIN = ("https://www.bein.com/en/epg-ajax-template/?action=epg_fetch"
        "&category=sports&cdate={d}&language=EN&loadindex=0&mins=00"
        "&offset=0&postid=25356&serviceidentity=bein.net")

# alkass.net grid
CHAN_TABLE = re.compile(r"<table style=\"width: ?\d+px; margin-right:10px\">(.*?)</table>", re.S)
PROG = re.compile(
    r"<div class='programs[^']*' id='\d+'[^>]*>(?P<title>.*?)<br>\s*"
    r"<span[^>]*>(?P<range>\d{2}:\d{2} - \d{2}:\d{2})</span>", re.S)

# bein.com
TOKEN = re.compile(r"(?P<logo>/\d{4}_[A-Za-z0-9_]+\.png)"
                   r"|(?P<row><li(?:\s[^>]*?)?>.*?</li>)", re.S | re.I)
ALKASS = re.compile(r"/\d{4}_Alkass_(\d+)\.png", re.I)
RANGE = re.compile(r"data-start='([\d\- :]+)'\s+data-end='([\d\- :]+)'")
TITLE = re.compile(r"<p class=title>(.*?)</p>", re.S)


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def bein_day(d):
    out, cur = defaultdict(dict), None
    r = requests.get(BEIN.format(d=d), headers=H, timeout=T)
    for m in TOKEN.finditer(r.text):
        if m.group("logo"):
            hit = ALKASS.match(m.group("logo"))
            cur = int(hit.group(1)) if hit else None
            continue
        if cur is None:
            continue
        span, title = RANGE.search(m.group("row")), TITLE.search(m.group("row"))
        if span and title:
            out[cur][span.group(1)[11:16]] = clean(title.group(1))
    return out


def main():
    today = datetime.now(DOHA).strftime("%Y-%m-%d")
    print(f"Doha today {today} {datetime.now(DOHA):%H:%M}", flush=True)

    r = requests.get("https://www.alkass.net/tvguide", headers=H, timeout=T)
    t = r.text
    i = t.find('class="tg-content"')
    region = t[i:] if i >= 0 else ""
    print(f"tg-content at {i}", flush=True)

    logos = re.findall(r"assets/images/(one|two|three|four|five|six|seven|eight|online)\.png",
                       region)
    print(f"logo column order: {logos}", flush=True)

    tables = CHAN_TABLE.findall(region)
    print(f"{len(tables)} channel tables", flush=True)

    alkass = {}
    for n, body in enumerate(tables, start=1):
        rows = [(m.group("range")[:5], m.group("range")[8:], clean(m.group("title")))
                for m in PROG.finditer(body)]
        alkass[n] = rows

    section("alkass.net grid, per channel")
    for n, rows in alkass.items():
        print(f"\n  table {n} ({len(rows)} programmes)", flush=True)
        for a, b, ttl in rows:
            print(f"    {a}-{b}  {ttl[:62]}", flush=True)

    section("do the alkass.net tables actually differ?")
    for a in alkass:
        for b in alkass:
            if b <= a:
                continue
            same = len(set(alkass[a]) & set(alkass[b]))
            if same:
                print(f"  table {a} vs {b}: {same} identical of "
                      f"{len(alkass[a])}/{len(alkass[b])}", flush=True)

    section("alkass.net vs beIN, same day, per channel")
    try:
        bein = bein_day(today)
    except Exception as exc:
        print(f"beIN failed: {exc}", flush=True)
        return
    for n in sorted(alkass):
        mine = {a: ttl for a, _b, ttl in alkass[n]}
        theirs = bein.get(n, {})
        common = set(mine) & set(theirs)
        agree = sum(1 for s in common if mine[s].lower()[:20] == theirs[s].lower()[:20])
        print(f"  ch{n}: alkass={len(mine)} bein={len(theirs)} "
              f"same_start={len(common)} same_title={agree}", flush=True)


if __name__ == "__main__":
    main()
