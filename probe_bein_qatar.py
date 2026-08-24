#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe for the beIN Qatar guide. Three questions:

  * does the official Opta API still answer, and what fields does a row
    actually carry — is there a live flag, and is there a channel logo?
  * why do nine channels (the AFC set, NBA, 4K HDR) come back with no
    programmes — stale GUIDs, or genuinely no schedule?
  * if the official API is failing, what else carries beIN MENA?

Runs on GitHub Actions; deleted once the answers are in.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import requests

UTC = timezone.utc
API_CHANNELS = "https://www.beinsports.com/api/opta/tv-channel"
API_EVENTS = "https://www.beinsports.com/api/opta/tv-event"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36")
H = {"User-Agent": UA, "Accept": "application/json"}

# The nine that produced nothing in the published guide.
EMPTY = {
    "beIN SPORTS 4K HDR": None,
    "beIN SPORTS AFC":   "10A2A142-F98C-4706-9FD0-2D3C36045D63",
    "beIN SPORTS 1 AFC": "0CB3E227-4376-4545-AB64-D6C390F644D8",
    "beIN SPORTS 2 AFC": "EEB3E4E8-0F9D-4735-943C-AEA3E39C87DE",
    "beIN SPORTS 3 AFC": "A2D36A21-00D5-4001-A443-81CF2C06553F",
    "beIN SPORTS 4 AFC": "42680C3C-580F-43DA-BDD8-02651BD10F32",
    "beIN SPORTS 5 AFC": "B0DBD19A-9F44-4197-BD09-2B6A5F315F3B",
    "beIN SPORTS 6 AFC": "2BF668DF-1B76-4199-88CE-8691FD86AD8C",
    "beIN SPORTS NBA":   "2F518547-2269-4C07-93D5-2733397472BD",
}


def head(label):
    print(f"\n{'='*74}\n{label}\n{'='*74}")


def get(url, **kw):
    try:
        r = requests.get(url, headers=H, timeout=40, **kw)
        return r
    except Exception as exc:
        print(f"  REQUEST FAILED {url}: {exc}")
        return None


def probe_channel_list():
    head("1) official channel list — is it up, and does a row carry a logo?")
    for region in ("ar-mena", "en-mena", "ar", None):
        params = {"region": region} if region else {}
        r = get(API_CHANNELS, params=params)
        if r is None:
            continue
        print(f"  region={region!r:10} status={r.status_code} len={len(r.content)}")
        if r.status_code != 200:
            print("   body:", r.text[:200])
            continue
        try:
            rows = r.json().get("rows", [])
        except Exception as exc:
            print(f"   !! not JSON: {exc}")
            continue
        print(f"   rows={len(rows)}")
        if not rows:
            continue
        print(f"   ROW KEYS: {sorted(rows[0].keys())}")
        print(f"   FULL FIRST ROW:\n     {json.dumps(rows[0], ensure_ascii=False)[:1400]}")
        names = [(x.get('name'), x.get('id')) for x in rows]
        print(f"   all names ({len(names)}):")
        for n, i in names:
            print(f"      {str(n):28} {i}")
        return rows
    return []


def probe_event_fields(guid, label):
    now = datetime.now(UTC)
    params = {
        "startBefore": (now + timedelta(days=6)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "endAfter": (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "channelIds": guid,
    }
    r = get(API_EVENTS, params=params)
    if r is None:
        return []
    try:
        rows = r.json().get("rows", []) or []
    except Exception:
        rows = []
    print(f"  {label:24} status={r.status_code} rows={len(rows)}")
    return rows


def probe_events():
    head("2) event rows — every field, hunting for a live flag")
    rows = probe_event_fields("7836FEA9-6B39-4A1A-8352-DC5FCB97A16C", "beIN SPORTS 1")
    if rows:
        print(f"\n   ROW KEYS: {sorted(rows[0].keys())}")
        for row in rows[:4]:
            print(f"\n   {json.dumps(row, ensure_ascii=False)[:1500]}")
        # which keys ever hold something boolean-ish or live-ish
        keys = {}
        for row in rows:
            for k, v in row.items():
                keys.setdefault(k, set())
                if isinstance(v, (bool, int, str)) and len(str(v)) < 40:
                    keys[k].add(str(v))
        print("\n   -- low-cardinality fields (candidates for a live/type flag) --")
        for k, vals in sorted(keys.items()):
            if 1 < len(vals) <= 12:
                print(f"      {k:24} {sorted(vals)[:12]}")
            elif len(vals) == 1:
                print(f"      {k:24} (constant) {sorted(vals)}")


def probe_empty_channels():
    head("3) the nine empty channels — stale GUIDs or genuinely no schedule?")
    for name, guid in EMPTY.items():
        if not guid:
            print(f"  {name:24} no GUID in the roster at all (came from the live list)")
            continue
        probe_event_fields(guid, name)


def probe_alternatives():
    head("4) fallbacks, in case the official API ever stops")
    for url in (
        "https://www.beinsports.com/en-us/tv-guide",
        "https://www.beinsports.com/ar-mena/tv-guide",
        "https://epgshare01.online/epgshare01/epg_ripper_BEIN1.xml.gz",
        "https://epgshare01.online/epgshare01/epg_ripper_QA1.xml.gz",
    ):
        r = get(url)
        if r is None:
            continue
        print(f"  {url:62} status={r.status_code} len={len(r.content)}")


def main():
    probe_channel_list()
    probe_events()
    probe_empty_channels()
    probe_alternatives()


if __name__ == "__main__":
    main()
