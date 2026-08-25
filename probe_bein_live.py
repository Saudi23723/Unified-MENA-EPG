#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: does the Live badge land on every live broadcast beIN airs?

The badge follows beIN's own per-row `live` flag. Two things could make it
miss a genuinely live match, and neither is visible from the finished XML:
the flag may not be the only or the best liveness field the API returns,
and the API may be capping how many rows it hands back — several channels
come out at exactly 100 programmes, which would truncate the guide and
drop live matches entirely rather than merely leave them unbadged.

This dumps the raw response envelope and the full field set of live and
non-live rows, and tests whether the row count can be pushed past 100.
Changes nothing.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import requests

UTC = timezone.utc
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "Accept": "application/json", "Accept-Language": "ar,en;q=0.8"}
T = (5, 25)
API_CHANNELS = "https://www.beinsports.com/api/opta/tv-channel"
API_EVENTS = "https://www.beinsports.com/api/opta/tv-event"


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def window(days_back=1, days_forward=6):
    now = datetime.now(UTC)
    return {
        "startBefore": (now + timedelta(days=days_forward)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "endAfter": (now - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    }


def is_live(row):
    f = row.get("live")
    return f is True or (isinstance(f, str) and f.strip().lower() == "true")


def get(params):
    return requests.get(API_EVENTS, headers=H, params=params, timeout=T)


def main():
    section("channel roster")
    r = requests.get(API_CHANNELS, headers=H, params={"region": "ar-mena"}, timeout=T)
    rows = r.json().get("rows", []) or []
    print(f"status={r.status_code} channels={len(rows)}", flush=True)
    guids = {}
    for c in rows:
        name = (c.get("title") or c.get("name") or "").strip()
        guid = c.get("site_id") or c.get("siteId") or c.get("id")
        if name and guid:
            guids[name] = guid
    for n in sorted(guids)[:45]:
        print(f"  {n:28} {guids[n]}", flush=True)

    pick = next((n for n in guids if n.strip().lower() in
                 ("bein sports 1", "bein sports1")), None) or sorted(guids)[0]
    guid = guids[pick]
    section(f"response envelope for {pick}")
    base = window()
    r = get({**base, "channelIds": guid})
    body = r.json()
    print(f"status={r.status_code} top-level keys={list(body.keys())}", flush=True)
    for k, v in body.items():
        if k != "rows":
            print(f"  {k} = {json.dumps(v, ensure_ascii=False)[:300]}", flush=True)
    rows = body.get("rows", []) or []
    print(f"rows returned: {len(rows)}", flush=True)

    section("is 100 a cap?")
    for extra in ({}, {"size": 500}, {"limit": 500}, {"pageSize": 500},
                  {"take": 500}, {"rows": 500}, {"page": 2}, {"offset": 100}):
        try:
            rr = get({**base, "channelIds": guid, **extra})
            got = rr.json().get("rows", []) or []
            first = got[0].get("startDate") if got else "-"
            last = got[-1].get("startDate") if got else "-"
            print(f"  {str(extra) or '(none)':22} -> {rr.status_code} "
                  f"{len(got)} rows  {first} .. {last}", flush=True)
        except Exception as exc:
            print(f"  {extra} FAILED: {exc}", flush=True)

    section("narrower windows — does the cap hide later days?")
    for back, fwd in ((1, 6), (1, 2), (0, 1), (2, 3), (5, 6)):
        try:
            w = window(back, fwd)
            got = get({**w, "channelIds": guid}).json().get("rows", []) or []
            live = sum(1 for x in got if is_live(x))
            days = sorted({(x.get("startDate") or "")[:10] for x in got})
            print(f"  -{back}d..+{fwd}d -> {len(got)} rows, {live} live, days={days}",
                  flush=True)
        except Exception as exc:
            print(f"  -{back}d..+{fwd}d FAILED: {exc}", flush=True)

    section("every field on a live row and a non-live row")
    live_row = next((x for x in rows if is_live(x)), None)
    dead_row = next((x for x in rows if not is_live(x)), None)
    for label, row in (("LIVE=True", live_row), ("LIVE=False", dead_row)):
        print(f"\n---- {label} ----", flush=True)
        if row is None:
            print("  none in this window", flush=True)
            continue
        print(json.dumps(row, ensure_ascii=False, indent=1)[:4000], flush=True)

    section("any other field that varies with liveness?")
    if rows:
        keys = sorted({k for x in rows for k in x})
        for k in keys:
            vals = {json.dumps(x.get(k), ensure_ascii=False)[:40] for x in rows}
            if 1 < len(vals) <= 6:
                print(f"  {k}: {sorted(vals)}", flush=True)


if __name__ == "__main__":
    main()
