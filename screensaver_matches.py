#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""screensaver_matches.json: today's matches, small, for the TV screensaver.

The screensaver (CleanYourTV) shows the day's matches from its last update and must
spend almost no data, so it reads this file (a few KB) instead of the whole guide.
It is cut from this repository's own today_matches_epg.xml: each match once, with
its kick-off time (UTC) and its channels. Asked for on 24 October 2026 ("على اخر
تحديث لما كان في انترنت قبل ال screensaver على الطقس و المباريات").
"""
from __future__ import annotations

import datetime as dt
import json
import re

SRC = "today_matches_epg.xml"
OUT = "screensaver_matches.json"
NOW = dt.datetime.now(dt.timezone.utc)
MARKS = re.compile("[⁦-⁩‎‏]")


def when(stamp: str) -> dt.datetime:
    return dt.datetime.strptime(stamp[:14], "%Y%m%d%H%M%S").replace(tzinfo=dt.timezone.utc) + \
        (dt.timedelta(hours=-int(stamp[16:18]), minutes=-int(stamp[18:20])) if stamp[15:16] == "+" else
         dt.timedelta(hours=int(stamp[16:18]), minutes=int(stamp[18:20])) if stamp[15:16] == "-" else dt.timedelta())


def ahead(text: str) -> dt.timedelta | None:
    """"بعد ساعتين و30 دقيقة" -> 2 h 30 min."""
    if "بعد" not in text:
        return None
    hours = 0
    if "ساعتين" in text:
        hours = 2
    elif re.search(r"(\d+)\s*ساع", text):
        hours = int(re.search(r"(\d+)\s*ساع", text).group(1))
    elif "ساعة" in text:
        hours = 1
    m = re.search(r"(\d+)\s*دقيق", text)
    return dt.timedelta(hours=hours, minutes=int(m.group(1)) if m else 0)


def main() -> None:
    xml = open(SRC, encoding="utf-8").read()
    kick: dict[str, dt.datetime] = {}
    chans: dict[str, str] = {}
    for start, title in re.findall(r'<programme start="([^"]+)"[^>]*>\s*<title[^>]*>([^<]*)<', xml):
        t = MARKS.sub("", title)
        parts = [p.strip() for p in t.split("·")]
        if len(parts) < 2 or " - " not in parts[1]:
            continue
        match, state = parts[1], parts[0]
        begin = when(start)
        lead = ahead(state)
        k = begin + lead if lead is not None else (begin if "مباشر" in state else None)
        if k and (match not in kick or k < kick[match]):
            kick[match] = k
        chans.setdefault(match, " · ".join(p for p in parts[2:4] if p and "on-demand" not in p.lower()))
    rows = [{"t": k.strftime("%Y-%m-%dT%H:%M:%SZ"), "m": m, "ch": chans.get(m, "")}
            for m, k in kick.items() if NOW - dt.timedelta(hours=3) <= k <= NOW + dt.timedelta(hours=36)]
    rows.sort(key=lambda r: r["t"])
    out = {"updated": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "matches": rows[:40]}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"{OUT}: {len(rows)} matches")


if __name__ == "__main__":
    main()
