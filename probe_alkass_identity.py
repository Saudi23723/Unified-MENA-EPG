#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: is each Alkass block on bein.com really the channel its logo
filename claims?

alkass_epg.py attaches every programme to the channel named by the nearest
preceding logo image, 2023_Alkass_N.png. That assumes N is the real channel
number. If beIN's page reuses or misnumbers those images, all eight
channels are mislabelled and every programme lands on the wrong one — a
failure that looks exactly like "the schedule is wrong".

This prints, for every Alkass block, the logo filename together with any
channel name, id or attribute sitting near it, so the mapping can be
checked rather than assumed. Changes nothing.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone

import requests

DOHA = timezone(timedelta(hours=3))
H = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ar,en;q=0.8"}
URL = ("https://www.bein.com/{lang}/epg-ajax-template/?action=epg_fetch"
       "&category=sports&cdate={d}&language={LANG}&loadindex=0&mins=00"
       "&offset=0&postid={pid}&serviceidentity=bein.net")


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()


def main():
    day = datetime.now(DOHA).strftime("%Y-%m-%d")

    for lang, pid in (("ar", "25344"), ("en", "25356")):
        r = requests.get(URL.format(lang=lang, LANG=lang.upper(), pid=pid, d=day),
                         headers=H, timeout=(5, 25))
        t = r.text
        print(f"\n{'='*80}\n{lang.upper()}  status={r.status_code} len={len(t)}\n{'='*80}")
        if r.status_code != 200:
            continue

        print("  every channel logo on the page, in document order:")
        for i, m in enumerate(re.finditer(r"/(\d{4})_([A-Za-z0-9_]+)\.png", t)):
            name = m.group(2)
            # what identifies this block? look just before and after the logo
            before = t[max(0, m.start() - 700): m.start()]
            after = t[m.end(): m.end() + 700]
            ids = re.findall(r"id=(?:'|\")?(channels_\d+|slider_\d+)", before + after)
            # any human-readable label near it
            labels = [clean(x) for x in re.findall(r"<p class=(?:channel|name|title)[^>]*>(.*?)</p>", before)]
            alt = re.search(r"alt=['\"]([^'\"]{2,40})['\"]", before + after)
            mark = "  <<< ALKASS" if "alkass" in name.lower() else ""
            print(f"    {i:3} {name:26} ids={ids[:3]} alt={alt.group(1) if alt else '-'}{mark}")

        print("\n  -- full markup around the first two Alkass logos --")
        shown = 0
        for m in re.finditer(r"/\d{4}_Alkass_\d+\.png", t):
            s = t[max(0, m.start() - 900): m.end() + 300]
            print(f"\n    ---- occurrence {shown} ----")
            print("   ", clean(s)[:500])
            print("    RAW:", s[max(0, len(s) - 1100):][:700].replace("\n", " "))
            shown += 1
            if shown >= 2:
                break


if __name__ == "__main__":
    main()
