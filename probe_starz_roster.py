#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary: enumerate every channel STARZPLAY lists, so the sport roster
is chosen from what the API actually says rather than three slugs picked by
hand. Also confirms whether AD Sports Premium is among them, and whether
every channel carries a logo.

Runs on GitHub Actions; deleted once the roster is settled.
"""
from __future__ import annotations

from datetime import datetime, timezone

import requests

UTC = timezone.utc
API = "https://epg.aws.playco.com/api/v1.1/epg/category/events/web-epg-scraper-sp"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
     "Accept": "application/json"}


def main():
    now = int(datetime.now(UTC).timestamp())
    base = {"ts_start": now - 86400, "ts_end": now + 3 * 86400, "lang": "ar",
            "pg": 18, "category": "all", "limit": 40, "x-geo-country": "SA"}

    seen, rows = set(), []
    for page in range(1, 16):
        try:
            data = requests.get(API, headers=H, timeout=(5, 30),
                                params=dict(base, page=page)).json()
        except Exception as exc:
            print(f"page {page}: {type(exc).__name__}: {str(exc)[:80]}", flush=True)
            break
        chans = data.get("data") or []
        if not chans:
            break
        new = 0
        for c in chans:
            slug = c.get("slug")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            rows.append(c)
            new += 1
        print(f"page {page}: {len(chans)} rows, {new} new (total {len(rows)})", flush=True)
        if new == 0:
            break

    print(f"\n{'='*96}\nEVERY CHANNEL STARZPLAY LISTS ({len(rows)})\n{'='*96}")
    print(f"{'slug':30} {'category':11} {'events':>6} {'logo':4}  genres / title")
    sportish = []
    for c in rows:
        slug = c.get("slug") or ""
        cat = str(c.get("category") or "")
        genres = [str(g) for g in (c.get("genres") or [])]
        evs = len(c.get("events") or [])
        imgs = c.get("images") or []
        has_png = any(i.get("type") == "logo-png" for i in imgs)
        logo = "png" if has_png else ("img" if imgs else "--")
        is_sport = ("Sports" in genres) or cat == "sports"
        if is_sport:
            sportish.append(c)
        mark = " <<< SPORT" if is_sport else ""
        print(f"{slug:30} {cat:11} {evs:6} {logo:4}  {c.get('title')}{mark}")

    print(f"\n{'='*96}\nSPORT BY THE API'S OWN CLASSIFICATION: {len(sportish)}\n{'='*96}")
    for c in sportish:
        imgs = c.get("images") or []
        png = next((i.get("url") for i in imgs if i.get("type") == "logo-png"), None)
        print(f"  {c.get('slug'):26} events={len(c.get('events') or []):4} "
              f"title={c.get('title')}")
        print(f"      genres={[str(g) for g in (c.get('genres') or [])]}")
        print(f"      logo-png={png}")

    print(f"\n  slugs: {sorted(c.get('slug') for c in sportish)}")
    missing = [c.get("slug") for c in sportish
               if not any(i.get("type") == "logo-png" for i in (c.get("images") or []))]
    print(f"  sport channels with NO logo-png: {missing}")


if __name__ == "__main__":
    main()
