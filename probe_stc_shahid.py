#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary: STC TV and Shahid are already in this repo via
combined_epg_script.py, but it names every channel "STC Channel 92533800202"
and "Shahid 387238" — the numeric id, not the channel. If the responses
carry a real name and a logo, both can be shown properly, and the STC sport
channels can finally be identified.

Runs on GitHub Actions; deleted once answered.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import requests

H = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ar,en;q=0.8"}
T = (5, 20)
ARABIC = re.compile(r"[؀-ۿ]")


def head(x):
    print(f"\n{'='*76}\n{x}\n{'='*76}", flush=True)


def probe_stc():
    head("1) STC TV — intigral content API: what does a channel row carry?")
    date_str = datetime.now().strftime("%Y-%m-%d")
    url = (f"https://prod-cdn-content-api.intigral-ott.net/content-api-3.0.1/"
           f"channels/schedules/{date_str}/3?apikey=GDMPrdExy0sVDlZMzNDdUyZ&country=SA")
    try:
        r = requests.get(url, headers=H, timeout=T)
    except Exception as exc:
        print(f"  FAILED {type(exc).__name__}: {str(exc)[:90]}")
        return
    print(f"  status={r.status_code} len={len(r.content)}")
    if r.status_code != 200:
        return
    data = r.json()
    print(f"  channels returned: {len(data)}")
    if not data:
        return
    row = data[0]
    print(f"\n  CHANNEL ROW KEYS: {sorted(row.keys())}")
    trimmed = {k: v for k, v in row.items() if k != "listings"}
    print(f"  FULL ROW (minus listings):\n    {json.dumps(trimmed, ensure_ascii=False)[:1400]}")

    print("\n  -- which keys look like a name or a logo? --")
    for k in sorted(row):
        if k == "listings":
            continue
        v = row[k]
        if isinstance(v, (str, dict)) and any(
                t in k.lower() for t in ("name", "title", "logo", "image", "icon", "poster")):
            print(f"    {k:24} {json.dumps(v, ensure_ascii=False)[:150]}")

    # hunt for sport channels across the whole response
    print("\n  -- channels whose name mentions sport / رياض / SSC --")
    hits = 0
    for ch in data:
        blob = json.dumps({k: v for k, v in ch.items() if k != "listings"},
                          ensure_ascii=False)
        if re.search(r"sport|ssc|رياض|كأس|دوري", blob, re.I):
            cid = str(ch.get("channelId", "")).split("/")[-1]
            name = (ch.get("channelName") or ch.get("name") or
                    ch.get("title") or ch.get("localizedName") or "?")
            print(f"    {cid:20} {json.dumps(name, ensure_ascii=False)[:90]}")
            hits += 1
            if hits >= 30:
                break
    print(f"  sport-ish channels found: {hits}")


def probe_shahid():
    head("2) Shahid — does its EPG response name the channel?")
    now = datetime.now(timezone.utc)
    ids = "387238,387251,387296,400919,946945"
    url = (f"https://api3.shahid.net/proxy/v2.1/shahid-epg-api/?csvChannelIds={ids}"
           f"&language=ar&from={(now - timedelta(days=1)):%Y-%m-%dT00:00:00.000Z}"
           f"&to={(now + timedelta(days=1)):%Y-%m-%dT23:59:59.000Z}&country=SA")
    try:
        r = requests.get(url, headers=H, timeout=T)
    except Exception as exc:
        print(f"  FAILED {type(exc).__name__}: {str(exc)[:90]}")
        return
    print(f"  status={r.status_code} len={len(r.content)}")
    if r.status_code != 200:
        return
    items = r.json().get("items", [])
    print(f"  channels returned: {len(items)}")
    if not items:
        return
    row = items[0]
    print(f"\n  CHANNEL ROW KEYS: {sorted(row.keys())}")
    trimmed = {k: v for k, v in row.items() if k != "items"}
    print(f"  FULL ROW (minus items):\n    {json.dumps(trimmed, ensure_ascii=False)[:1200]}")


def main():
    for step in (probe_stc, probe_shahid):
        try:
            step()
        except Exception as exc:
            print(f"\n  !! {step.__name__}: {type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    main()
