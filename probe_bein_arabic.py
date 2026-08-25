#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: does beIN serve Arabic programme titles anywhere?

The guide currently calls /api/opta/tv-event with no locale at all, and the
Arabic twin inside each row is a verbatim copy of the English. But beIN's
own Arabic site clearly shows something to Arabic readers. This checks
whether the same API returns Arabic when asked properly, and what the
ar-mena TV-guide page itself actually renders.

Runs on GitHub Actions; deleted once answered.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import requests

UTC = timezone.utc
API_EVENTS = "https://www.beinsports.com/api/opta/tv-event"
G1 = "7836FEA9-6B39-4A1A-8352-DC5FCB97A16C"          # beIN SPORTS 1
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36")
ARABIC = re.compile(r"[؀-ۿ]")

now = datetime.now(UTC)
BASE = {
    "startBefore": (now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    "endAfter": (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    "channelIds": G1,
}


def head(x):
    print(f"\n{'='*74}\n{x}\n{'='*74}")


def arabic_share(rows):
    """How many rows carry genuinely Arabic text, per field."""
    out = {}
    for field, get in (
        ("title", lambda r: r.get("title")),
        ("data.Title.Arabic", lambda r: ((r.get("data") or {}).get("Title") or {}).get("Arabic")),
        ("description", lambda r: r.get("description")),
        ("categoryArabic", lambda r: r.get("categoryArabic")),
    ):
        n = sum(1 for r in rows if isinstance(get(r), str) and ARABIC.search(get(r)))
        out[field] = f"{n}/{len(rows)}"
    return out


def try_variant(label, params=None, headers=None):
    p = dict(BASE)
    p.update(params or {})
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    try:
        r = requests.get(API_EVENTS, params=p, headers=h, timeout=40)
    except Exception as exc:
        print(f"  {label:44} FAILED {exc}")
        return
    try:
        rows = r.json().get("rows", []) or []
    except Exception:
        print(f"  {label:44} status={r.status_code} not-json")
        return
    if not rows:
        print(f"  {label:44} status={r.status_code} rows=0")
        return
    print(f"  {label:44} status={r.status_code} rows={len(rows):3} {arabic_share(rows)}")
    if any(ARABIC.search(str(r_.get("title") or "")) for r_ in rows):
        print("      *** ARABIC TITLES FOUND ***")
        for r_ in rows[:3]:
            print(f"        {r_.get('title')}")


def probe_api():
    head("1) the same event API, asked for Arabic every way it might accept")
    try_variant("(current call - no locale at all)")
    for k in ("region", "lang", "language", "locale", "culture", "market", "edition"):
        for v in ("ar-mena", "ar", "ar-QA"):
            try_variant(f"?{k}={v}", params={k: v})
    try_variant("header Accept-Language: ar", headers={"Accept-Language": "ar,ar-QA;q=0.9"})
    try_variant("header + region=ar-mena",
                params={"region": "ar-mena"}, headers={"Accept-Language": "ar"})


def probe_page():
    head("2) what beIN's own Arabic TV-guide page renders")
    for url in ("https://www.beinsports.com/ar-mena/tv-guide",
                "https://www.beinsports.com/ar/tv-guide"):
        try:
            r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "ar"}, timeout=40)
        except Exception as exc:
            print(f"  {url} FAILED {exc}")
            continue
        print(f"\n  {url}  status={r.status_code} len={len(r.text)}")
        if r.status_code != 200:
            continue
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
        print(f"    __NEXT_DATA__: {bool(m)}")
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except Exception as exc:
            print(f"    bad JSON: {exc}")
            continue
        blob = json.dumps(data, ensure_ascii=False)
        print(f"    payload size={len(blob)}  contains Arabic script: {bool(ARABIC.search(blob))}")
        props = (data.get("props") or {}).get("pageProps") or {}
        print(f"    pageProps keys: {list(props)[:20]}")
        # hunt for anything that looks like a programme title
        hits = re.findall(r'"(?:title|name|programTitle)"\s*:\s*"([^"]{6,70})"', blob)
        ar_hits = [h for h in hits if ARABIC.search(h)]
        print(f"    title-ish strings: {len(hits)}, of which Arabic: {len(ar_hits)}")
        for h in ar_hits[:8]:
            print(f"       {h}")
        if not ar_hits:
            for h in hits[:8]:
                print(f"       (en) {h}")


def main():
    probe_api()
    probe_page()


if __name__ == "__main__":
    main()
