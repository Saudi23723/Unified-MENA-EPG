#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary: will the nine empty beIN Qatar channels ever get a schedule?

The guide asks beIN for one day back and six forward. The AFC set, NBA and
4K HDR return nothing in that window. AFC and NBA are seasonal, so the
useful question is whether beIN has anything for them further out — which
a much wider query answers directly.

Runs on GitHub Actions; deleted once answered.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

UTC = timezone.utc
API = "https://www.beinsports.com/api/opta/tv-event"
H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

EMPTY = {
    "beIN SPORTS AFC":   "10A2A142-F98C-4706-9FD0-2D3C36045D63",
    "beIN SPORTS 1 AFC": "0CB3E227-4376-4545-AB64-D6C390F644D8",
    "beIN SPORTS 2 AFC": "EEB3E4E8-0F9D-4735-943C-AEA3E39C87DE",
    "beIN SPORTS 3 AFC": "A2D36A21-00D5-4001-A443-81CF2C06553F",
    "beIN SPORTS 4 AFC": "42680C3C-580F-43DA-BDD8-02651BD10F32",
    "beIN SPORTS 5 AFC": "B0DBD19A-9F44-4197-BD09-2B6A5F315F3B",
    "beIN SPORTS 6 AFC": "2BF668DF-1B76-4199-88CE-8691FD86AD8C",
    "beIN SPORTS NBA":   "2F518547-2269-4C07-93D5-2733397472BD",
    "beIN SPORTS 4K HDR": "0FDFD504-8B55-493E-843A-1BBB3877842C",
}
# One that does have a schedule, as a control: whatever the wide window does
# to it is what the window itself is doing, not the channel.
CONTROL = ("beIN SPORTS 1", "7836FEA9-6B39-4A1A-8352-DC5FCB97A16C")


def count(guid, days_forward, days_back=1):
    now = datetime.now(UTC)
    try:
        r = requests.get(API, headers=H, timeout=(5, 30), params={
            "startBefore": (now + timedelta(days=days_forward)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "endAfter": (now - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "channelIds": guid,
        })
        rows = r.json().get("rows", []) or []
    except Exception as exc:
        return None, f"{type(exc).__name__}: {str(exc)[:60]}"
    return rows, None


def main():
    windows = (6, 30, 90, 200)
    print(f"{'channel':22} " + " ".join(f"{f'+{d}d':>7}" for d in windows))
    print("-" * 60)

    name, guid = CONTROL
    line = f"{name:22} "
    for d in windows:
        rows, err = count(guid, d)
        line += f"{(len(rows) if rows is not None else err):>7} "
    print(line + "   <- control, has a schedule")
    print()

    found = {}
    for name, guid in EMPTY.items():
        line = f"{name:22} "
        for d in windows:
            rows, err = count(guid, d)
            n = len(rows) if rows is not None else -1
            line += f"{n:>7} "
            if rows:
                found.setdefault(name, (d, rows))
        print(line)

    print()
    if not found:
        print("  Nothing scheduled for any of them, even 200 days out.")
    for name, (d, rows) in found.items():
        starts = sorted(r.get("startDate", "") for r in rows)
        print(f"\n  {name}: {len(rows)} programmes appear within +{d}d")
        print(f"    earliest {starts[0][:16]}   latest {starts[-1][:16]}")
        for r in rows[:4]:
            print(f"      {r.get('startDate','')[:16]}  {str(r.get('title'))[:52]}")


if __name__ == "__main__":
    main()
