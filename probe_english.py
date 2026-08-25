#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary: is an English title available for Alkass and STARZPLAY?

Alkass's feed carries an Alkass_N_EN.bein twin beside every Arabic channel,
but with fewer programmes - so how well do they line up by start time?
STARZPLAY is currently called with lang=ar; does lang=en return English?

Runs on GitHub Actions; deleted once answered.
"""
from __future__ import annotations

import gzip
import re
from collections import defaultdict
from datetime import datetime, timezone

import requests

UTC = timezone.utc
H = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en,ar;q=0.8"}
T = (5, 20)
BEIN1 = "https://epgshare01.online/epgshare01/epg_ripper_BEIN1.xml.gz"
API = "https://epg.aws.playco.com/api/v1.1/epg/category/events/web-epg-scraper-sp"
ARABIC = re.compile(r"[؀-ۿ]")
PROG = re.compile(r'<programme start="([^"]+)" stop="([^"]+)" channel="([^"]+)"[^>]*>(.*?)</programme>', re.S)


def head(x):
    print(f"\n{'='*76}\n{x}\n{'='*76}", flush=True)


def probe_alkass():
    head("1) Alkass — how well do the AR and EN twins line up?")
    with requests.get(BEIN1, headers=H, timeout=T, stream=True) as r:
        buf = bytearray()
        for c in r.iter_content(65536):
            buf.extend(c)
    xml = gzip.decompress(bytes(buf)).decode("utf-8", "replace")

    per = defaultdict(dict)
    for st, sp, ch, body in PROG.findall(xml):
        low = ch.lower()
        if not low.startswith("alkass"):
            continue
        m = re.search(r"<title[^>]*>(.*?)</title>", body, re.S)
        if not m:
            continue
        n = re.match(r"alkass_(\d+)_", low)
        if not n:
            continue
        lang = "ar" if "_ar" in low else "en"
        per[(n.group(1), lang)][st] = m.group(1).strip()

    print(f"  {'channel':10} {'AR':>5} {'EN':>5} {'EN matched by start':>21} {'coverage':>9}")
    tot_ar = tot_hit = 0
    for i in map(str, range(1, 9)):
        ar = per.get((i, "ar"), {})
        en = per.get((i, "en"), {})
        hit = sum(1 for k in ar if k in en)
        tot_ar += len(ar); tot_hit += hit
        pct = (100 * hit / len(ar)) if ar else 0
        print(f"  Alkass {i:2}  {len(ar):5} {len(en):5} {hit:21} {pct:8.0f}%")
    print(f"\n  overall: {tot_hit}/{tot_ar} Arabic programmes have an English twin "
          f"({100*tot_hit/max(tot_ar,1):.0f}%)")

    print("\n  -- sample pairs (same channel, same start) --")
    ar = per.get(("1", "ar"), {}); en = per.get(("1", "en"), {})
    shown = 0
    for k in sorted(ar):
        if k in en:
            print(f"    {k[:12]}  EN={en[k][:40]:42} AR={ar[k][:34]}")
            shown += 1
            if shown >= 8:
                break
    print("\n  -- Arabic entries with NO English twin --")
    shown = 0
    for k in sorted(ar):
        if k not in en:
            print(f"    {k[:12]}  AR={ar[k][:50]}")
            shown += 1
            if shown >= 5:
                break
    # is the EN feed genuinely English?
    en_all = [v for (i, l), d in per.items() if l == "en" for v in d.values()]
    arabic_in_en = sum(1 for v in en_all if ARABIC.search(v))
    print(f"\n  EN feed sanity: {len(en_all)} titles, {arabic_in_en} contain Arabic script")


def probe_starz():
    head("2) STARZPLAY — does lang=en return English titles?")
    now = int(datetime.now(UTC).timestamp())
    base = {"ts_start": now - 86400, "ts_end": now + 3 * 86400, "pg": 18,
            "category": "all", "limit": 40, "x-geo-country": "SA", "page": 1}
    out = {}
    for lang in ("ar", "en"):
        try:
            data = requests.get(API, headers=H, timeout=(5, 30),
                                params=dict(base, lang=lang)).json()
        except Exception as exc:
            print(f"  lang={lang}: FAILED {type(exc).__name__}: {str(exc)[:70]}")
            continue
        rows = data.get("data") or []
        ch = next((c for c in rows if c.get("slug") == "starzplaysports1"), None)
        if not ch:
            print(f"  lang={lang}: starzplaysports1 not on page 1")
            continue
        evs = ch.get("events") or []
        titles = {e.get("tsStart"): (e.get("title") or "") for e in evs}
        out[lang] = titles
        arabic = sum(1 for v in titles.values() if ARABIC.search(v))
        print(f"  lang={lang:3} channel title={ch.get('title')!r}  events={len(evs)}  "
              f"titles containing Arabic: {arabic}/{len(titles)}")

    if "ar" in out and "en" in out:
        shared = set(out["ar"]) & set(out["en"])
        differ = sum(1 for k in shared if out["ar"][k] != out["en"][k])
        print(f"\n  events present in both: {len(shared)}, of which the title differs: {differ}")
        print("  -- sample pairs --")
        for k in sorted(shared)[:8]:
            print(f"    EN={out['en'][k][:44]:46} AR={out['ar'][k][:34]}")


def main():
    for step in (probe_alkass, probe_starz):
        try:
            step()
        except Exception as exc:
            print(f"\n  !! {step.__name__}: {type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    main()
