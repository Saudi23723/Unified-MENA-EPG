#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: is each Alkass block on bein.com really the channel its logo
filename claims?

alkass_epg.py attaches every programme to the channel named by the nearest
preceding logo image, 2023_Alkass_N.png. Today's output has Alkass 1 and
Alkass 4 carrying an identical schedule, and Alkass 5 and Alkass 7 the
same — so either those logo files are reused on the page, or a block is
being read twice. This prints every Alkass logo occurrence in document
order with what identifies it and what follows it, so the mapping can be
checked rather than assumed. Changes nothing.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone

import requests

DOHA = timezone(timedelta(hours=3))
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "Accept-Language": "ar,en;q=0.8"}
URL = ("https://www.bein.com/{lang}/epg-ajax-template/?action=epg_fetch"
       "&category=sports&cdate={d}&language={LANG}&loadindex=0&mins=00"
       "&offset=0&postid={pid}&serviceidentity=bein.net")
T = (5, 20)

LOGO = re.compile(r"/(\d{4})_([A-Za-z0-9_]+)\.png")
TOKEN = re.compile(r"(?P<logo>/\d{4}_[A-Za-z0-9_]+\.png)"
                   r"|(?P<row><li(?:\s[^>]*?)?>.*?</li>)", re.S | re.I)
RANGE = re.compile(r"data-start='([\d\- :]+)'\s+data-end='([\d\- :]+)'")
TITLE = re.compile(r"<p class=title>(.*?)</p>", re.S)


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def main():
    day = datetime.now(DOHA).strftime("%Y-%m-%d")
    print(f"Doha today: {day}  now {datetime.now(DOHA):%H:%M}", flush=True)

    for lang, pid in (("ar", "25344"), ("en", "25356")):
        section(f"bein.com {lang.upper()}")
        try:
            r = requests.get(URL.format(lang=lang, LANG=lang.upper(), pid=pid, d=day),
                             headers=H, timeout=T)
        except Exception as exc:
            print(f"FAILED: {exc}", flush=True)
            continue
        t = r.text
        print(f"status={r.status_code} bytes={len(t)}", flush=True)
        if r.status_code != 200:
            continue

        logos = list(LOGO.finditer(t))
        names = [m.group(2) for m in logos]
        print(f"{len(logos)} logo references, {len(set(names))} distinct", flush=True)

        # Walk in document order the way alkass_epg.py does, but keep every
        # occurrence separate instead of merging them by number.
        blocks, cur = [], None
        for m in TOKEN.finditer(t):
            if m.group("logo"):
                cur = {"logo": m.group("logo"), "at": m.start(), "rows": []}
                blocks.append(cur)
                continue
            span, title = RANGE.search(m.group("row")), TITLE.search(m.group("row"))
            if cur is not None and span and title:
                cur["rows"].append((span.group(1)[11:16], clean(title.group(1))))

        print("\nevery block in document order (only ones with rows, plus all Alkass):",
              flush=True)
        for i, b in enumerate(blocks):
            is_alkass = "alkass" in b["logo"].lower()
            if not b["rows"] and not is_alkass:
                continue
            before = t[max(0, b["at"] - 800):b["at"]]
            after = t[b["at"]:b["at"] + 400]
            ids = re.findall(r"id=['\"]?(channels_\d+|slider_\d+|ch_\d+)", before + after)
            alt = re.findall(r"alt=['\"]([^'\"]{2,60})['\"]", before + after)
            first = b["rows"][0] if b["rows"] else ("", "")
            print(f"  blk{i:3} {b['logo']:28} rows={len(b['rows']):3} "
                  f"first={first[0]} {first[1][:34]!r} ids={ids[:2]} alt={alt[:2]}"
                  f"{'   <<< ALKASS' if is_alkass else ''}", flush=True)

        section(f"raw markup before each Alkass logo ({lang.upper()})")
        for b in blocks:
            if "alkass" not in b["logo"].lower():
                continue
            w = t[max(0, b["at"] - 1200):b["at"] + 200]
            print(f"\n---- {b['logo']} at {b['at']} ----", flush=True)
            print("RAW:", w[-1000:].replace("\n", " "), flush=True)


if __name__ == "__main__":
    main()
