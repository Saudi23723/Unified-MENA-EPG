#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Can bein.com carry the Alkass guide on its own?

The audit showed epgshare matches beIN perfectly on Alkass 1, 2 and 4 but
diverges badly on 3, 5, 6, 7 and 8. bein.com is the source of truth, so
before switching to it this checks the three things that decide whether it
can replace the feed outright:

  * how many days forward it will serve
  * whether it has an English edition (its own config suggests postid 25356
    under /en/) so English titles survive the switch
  * whether each slot gives a usable end time, not just a start

Runs on GitHub Actions; deleted once answered.
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
CH_IMG = re.compile(r"2023_Alkass_(\d+)\.png", re.I)
LI = re.compile(r"<li\s[^>]*?>(.*?)</li>", re.S)
RANGE = re.compile(r"data-start='(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'\s+"
                   r"data-end='(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'")
TITLE = re.compile(r"<p class=title>(.*?)</p>", re.S)
FORMAT = re.compile(r"<p class=format>(.*?)</p>", re.S)


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(s or ""))).strip()


def fetch(lang, pid, day):
    u = URL.format(lang=lang, LANG=lang.upper(), pid=pid, d=day)
    try:
        r = requests.get(u, headers=H, timeout=T)
    except Exception as exc:
        return None, f"{type(exc).__name__}"
    return (r.text if r.status_code == 200 else None), r.status_code


def parse(text):
    out = defaultdict(list)
    for block in re.split(r"<div class='row no-gutter' id=channels_\d+>", text or ""):
        m = CH_IMG.search(block)
        if not m:
            continue
        n = int(m.group(1))
        for li in LI.findall(block):
            rng = RANGE.search(li)
            ti = TITLE.search(li)
            if not rng or not ti:
                continue
            out[n].append((rng.group(1), rng.group(2), clean(ti.group(1)),
                           clean((FORMAT.search(li) or [None, ""])[1]) if FORMAT.search(li) else ""))
    return out


def main():
    today = datetime.now(DOHA)

    print(f"\n{'='*76}\n1) how many days forward does bein.com serve?\n{'='*76}")
    print(f"  {'date':12} {'AR slots':>9} {'EN slots':>9}  channels seen")
    reach = 0
    for off in range(0, 9):
        day = (today + timedelta(days=off)).strftime("%Y-%m-%d")
        ar, sa = fetch("ar", "25344", day)
        en, se = fetch("en", "25356", day)
        pa, pe = parse(ar), parse(en)
        na = sum(len(v) for v in pa.values())
        ne = sum(len(v) for v in pe.values())
        if na:
            reach = off
        print(f"  {day:12} {na:9} {ne:9}  AR={sorted(pa)} EN={sorted(pe)}")
    print(f"\n  furthest day with Arabic data: +{reach}d")

    print(f"\n{'='*76}\n2) does a slot give a usable end time, and is EN really English?\n{'='*76}")
    day = today.strftime("%Y-%m-%d")
    ar, _ = fetch("ar", "25344", day)
    en, _ = fetch("en", "25356", day)
    pa, pe = parse(ar), parse(en)

    rows = pa.get(1, [])
    print(f"  Alkass 1 Arabic: {len(rows)} slots")
    bad = [r for r in rows if r[0] >= r[1]]
    print(f"  slots whose end is not after the start: {len(bad)}")
    gaps = 0
    for i in range(1, len(rows)):
        if rows[i][0] != rows[i - 1][1]:
            gaps += 1
    print(f"  slots that do not butt onto the previous one: {gaps}")
    for r in rows[:6]:
        print(f"    {r[0][11:16]}-{r[1][11:16]}  {r[2][:40]:42} [{r[3][:18]}]")

    arabic = re.compile(r"[؀-ۿ]")
    en_rows = pe.get(1, [])
    en_ar = sum(1 for r in en_rows if arabic.search(r[2]))
    print(f"\n  Alkass 1 English: {len(en_rows)} slots, {en_ar} containing Arabic script")
    starts_ar = {r[0] for r in rows}
    starts_en = {r[0] for r in en_rows}
    print(f"  starts shared between AR and EN: {len(starts_ar & starts_en)}"
          f" (AR={len(starts_ar)}, EN={len(starts_en)})")
    by_start = {r[0]: r[2] for r in en_rows}
    for r in rows[:6]:
        print(f"    {r[0][11:16]}  AR={r[2][:32]:34} EN={by_start.get(r[0], '-')[:34]}")

    print(f"\n{'='*76}\n3) all eight channels, today\n{'='*76}")
    for n in range(1, 9):
        a, e = pa.get(n, []), pe.get(n, [])
        span = ""
        if a:
            span = f"{a[0][0][11:16]}..{a[-1][1][11:16]}"
        print(f"  Alkass {n}: AR={len(a):3} EN={len(e):3}  {span}")


if __name__ == "__main__":
    main()
