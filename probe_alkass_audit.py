#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only audit: compare every Alkass channel in the published guide
against beIN's own Arabic guide, programme by programme.

Changes nothing. Fetches bein.com's guide for today and tomorrow, pulls out
each Alkass channel's slots, and lines them up against alkass_epg.xml as
published, reporting exact matches, time mismatches and anything only one
side has.

Runs on GitHub Actions; deleted once the answer is in.
"""
from __future__ import annotations

import html
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests
import xml.etree.ElementTree as ET

DOHA = timezone(timedelta(hours=3))
H = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ar,en;q=0.8"}
T = (5, 25)
BEIN = ("https://www.bein.com/ar/epg-ajax-template/?action=epg_fetch"
        "&category=sports&cdate={d}&language=AR&loadindex=0&mins=00"
        "&offset=0&postid=25344&serviceidentity=bein.net")

# Each channel block carries its logo file name, which is how beIN's markup
# identifies the channel; the slider id is only a position on the page.
CH_IMG = re.compile(r"2023_Alkass_(\d+)\.png", re.I)
LI = re.compile(r"<li\s[^>]*?>(.*?)</li>", re.S)
START = re.compile(r"data-start='(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'")
TITLE = re.compile(r"<p class=title>(.*?)</p>", re.S)


def norm(s: str) -> str:
    """Compare titles fairly: unify Arabic presentation forms, drop
    diacritics and collapse whitespace."""
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", "", s)
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[ً-ْ‎‏]", "", s)
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي")
    return re.sub(r"\s+", " ", s).strip()


def scrape_bein(day: str) -> dict[int, dict[datetime, str]]:
    """{channel number: {start (Doha): title}} from beIN's own guide."""
    r = requests.get(BEIN.format(d=day), headers=H, timeout=T)
    if r.status_code != 200:
        print(f"  bein.com {day}: status={r.status_code}")
        return {}
    text = r.text
    out: dict[int, dict[datetime, str]] = defaultdict(dict)

    # Split the page into channel blocks on the row wrapper, then keep the
    # ones whose logo says Alkass.
    blocks = re.split(r"<div class='row no-gutter' id=channels_\d+>", text)
    for block in blocks:
        m = CH_IMG.search(block)
        if not m:
            continue
        n = int(m.group(1))
        for li in LI.findall(block):
            st = START.search(li)
            ti = TITLE.search(li)
            if not st or not ti:
                continue
            dt = datetime.strptime(st.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=DOHA)
            out[n][dt] = norm(ti.group(1))
    return out


def load_ours() -> dict[int, dict[datetime, list[str]]]:
    xid_to_n = {
        "AlkassOne.qa": 1, "AlkassTwo.qa": 2, "AlkassThree.qa": 3,
        "AlkassFour.qa": 4, "AlkassFive.qa": 5, "AlkassSix.qa": 6,
        "AlkassSeven.qa": 7, "AlkassEight.qa": 8,
    }
    root = ET.parse("alkass_epg.xml").getroot()
    out: dict[int, dict[datetime, list[str]]] = defaultdict(dict)
    for p in root.findall("programme"):
        n = xid_to_n.get(p.get("channel"))
        if not n:
            continue
        dt = datetime.strptime(p.get("start"), "%Y%m%d%H%M%S %z").astimezone(DOHA)
        out[n][dt] = [norm(t.text or "") for t in p.findall("title")]
    return out


def main():
    today = datetime.now(DOHA)
    bein: dict[int, dict[datetime, str]] = defaultdict(dict)
    for off in (0, 1):
        day = (today + timedelta(days=off)).strftime("%Y-%m-%d")
        got = scrape_bein(day)
        print(f"  bein.com {day}: Alkass channels found = {sorted(got)}, "
              f"slots = {sum(len(v) for v in got.values())}")
        for n, slots in got.items():
            bein[n].update(slots)

    ours = load_ours()
    print(f"\n  our guide: channels = {sorted(ours)}, "
          f"programmes = {sum(len(v) for v in ours.values())}")

    print(f"\n{'='*82}\n  PER CHANNEL, ONLY WHERE THE TWO OVERLAP IN TIME\n{'='*82}")
    print(f"  {'ch':4} {'beIN':>6} {'ours':>6} {'common starts':>14} "
          f"{'title match':>12} {'title differs':>14}")
    tot_common = tot_match = 0
    diffs = []
    for n in range(1, 9):
        b, o = bein.get(n, {}), ours.get(n, {})
        if not b or not o:
            print(f"  {n:<4} {len(b):6} {len(o):6}   (no overlap to compare)")
            continue
        # only judge inside the window both sides cover
        lo = max(min(b), min(o))
        hi = min(max(b), max(o))
        common = [s for s in b if s in o and lo <= s <= hi]
        match = 0
        for s in common:
            if b[s] in o[s] or any(b[s] in t or t in b[s] for t in o[s] if t):
                match += 1
            else:
                diffs.append((n, s, b[s], o[s]))
        tot_common += len(common)
        tot_match += match
        pct = 100 * match / len(common) if common else 0
        print(f"  {n:<4} {len(b):6} {len(o):6} {len(common):14} "
              f"{match:12} {len(common)-match:14}  ({pct:.0f}%)")

    print(f"\n  TOTAL: {tot_match}/{tot_common} slots match on both time and title "
          f"({100*tot_match/max(tot_common,1):.0f}%)")

    if diffs:
        print(f"\n  -- {len(diffs)} slots where the time lines up but the title does not --")
        for n, s, bt, ot in diffs[:20]:
            print(f"    Alkass {n} {s:%m-%d %H:%M}")
            print(f"       beIN : {bt[:60]}")
            print(f"       ours : {' | '.join(ot)[:60]}")

    # starts one side has and the other does not, inside the shared window
    print(f"\n{'='*82}\n  STARTS PRESENT ON ONE SIDE ONLY (inside the shared window)\n{'='*82}")
    for n in range(1, 9):
        b, o = bein.get(n, {}), ours.get(n, {})
        if not b or not o:
            continue
        lo, hi = max(min(b), min(o)), min(max(b), max(o))
        only_b = sorted(s for s in b if s not in o and lo <= s <= hi)
        only_o = sorted(s for s in o if s not in b and lo <= s <= hi)
        if only_b or only_o:
            print(f"  Alkass {n}: beIN-only={len(only_b)} ours-only={len(only_o)}")
            for s in only_b[:3]:
                print(f"     beIN only {s:%m-%d %H:%M}  {b[s][:46]}")
            for s in only_o[:3]:
                print(f"     ours only {s:%m-%d %H:%M}  {' | '.join(o[s])[:46]}")


if __name__ == "__main__":
    main()
