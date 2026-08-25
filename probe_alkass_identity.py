#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: does beIN itself publish near-identical schedules for Alkass 1
and 4, and for 5 and 7, or is this guide merging two channels together?

The published guide has Alkass 1 sharing 71 of its 87 programmes with
Alkass 4, and Alkass 5 sharing 76 of 78 with Alkass 7 — start, stop and
title all equal. Either beIN's own guide says that, or the parse is wrong.
This prints each channel's rows straight off beIN's page, day by day, and
counts the overlaps. Changes nothing.
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
URL = ("https://www.bein.com/{lang}/epg-ajax-template/?action=epg_fetch"
       "&category=sports&cdate={d}&language={LANG}&loadindex=0&mins=00"
       "&offset=0&postid={pid}&serviceidentity=bein.net")
T = (5, 20)

TOKEN = re.compile(r"(?P<logo>/\d{4}_[A-Za-z0-9_]+\.png)"
                   r"|(?P<row><li(?:\s[^>]*?)?>.*?</li>)", re.S | re.I)
ALKASS = re.compile(r"/\d{4}_Alkass_(\d+)\.png", re.I)
RANGE = re.compile(r"data-start='([\d\- :]+)'\s+data-end='([\d\- :]+)'")
TITLE = re.compile(r"<p class=title>(.*?)</p>", re.S)


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def parse(text):
    """{n: {start: (stop, title)}} — exactly how alkass_epg.py reads a page."""
    out, cur = defaultdict(dict), None
    for m in TOKEN.finditer(text):
        if m.group("logo"):
            hit = ALKASS.match(m.group("logo"))
            cur = int(hit.group(1)) if hit else None
            continue
        if cur is None:
            continue
        span, title = RANGE.search(m.group("row")), TITLE.search(m.group("row"))
        if span and title:
            out[cur][span.group(1)] = (span.group(2), clean(title.group(1)))
    return out


def main():
    today = datetime.now(DOHA)
    days = [(today + timedelta(days=d)).strftime("%Y-%m-%d") for d in range(4)]
    print(f"Doha now {today:%Y-%m-%d %H:%M}; days {days}", flush=True)

    for lang, pid in (("ar", "25344"), ("en", "25356")):
        merged = defaultdict(dict)
        section(f"bein.com {lang.upper()} — one day at a time")
        for d in days:
            try:
                r = requests.get(URL.format(lang=lang, LANG=lang.upper(), pid=pid, d=d),
                                 headers=H, timeout=T)
            except Exception as exc:
                print(f"  {d} FAILED: {exc}", flush=True)
                continue
            got = parse(r.text)
            counts = {n: len(got[n]) for n in sorted(got)}
            dates = sorted({s[:10] for n in got for s in got[n]})
            print(f"  {d}: status={r.status_code} rows={counts} dates_seen={dates}",
                  flush=True)
            for n, slots in got.items():
                merged[n].update(slots)

        section(f"{lang.upper()} — day 0, every row of every channel")
        day0 = {n: {s: v for s, v in merged[n].items() if s[:10] == days[0]}
                for n in sorted(merged)}
        for n in sorted(day0):
            print(f"\n  Alkass {n} ({len(day0[n])} rows)", flush=True)
            for s in sorted(day0[n]):
                stop, title = day0[n][s]
                print(f"    {s[11:16]}-{stop[11:16]}  {title[:60]}", flush=True)

        section(f"{lang.upper()} — pairwise identical rows (start+stop+title), all days")
        for a in sorted(merged):
            for b in sorted(merged):
                if b <= a:
                    continue
                A = {(s, *v) for s, v in merged[a].items()}
                B = {(s, *v) for s, v in merged[b].items()}
                shared = len(A & B)
                if shared:
                    print(f"  Alkass {a} vs {b}: {shared} identical "
                          f"of {len(A)}/{len(B)}", flush=True)


if __name__ == "__main__":
    main()
