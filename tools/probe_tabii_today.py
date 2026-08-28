#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ask every tabii source, today, and print what it actually says."""
import os, re, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from epg_lib import fetch, new_session, utc_now
import update_tabii_epg as T

IST = ZoneInfo("Europe/Istanbul")
s = new_session()
now = utc_now()
today = now.astimezone(IST).date()
print("Istanbul now:", now.astimezone(IST).strftime("%Y-%m-%d %H:%M"))

for name, fn in (("TRT", T.fetch_trt), ("tvyayinakisi", T.fetch_tvyayinakisi),
                 ("Spor Ekranı", T.fetch_sporekrani)):
    try:
        rows = fn(s)
    except Exception as exc:
        print(f"\n### {name}: FAILED {exc}")
        continue
    per = {}
    for r in rows:
        per.setdefault(r["number"], []).append(r)
    print(f"\n### {name}: {len(rows)} rows, channels {sorted(per)}")
    for num in sorted(per):
        tod = [r for r in per[num] if r["start"].astimezone(IST).date() == today]
        print(f"  ch {num}: {len(per[num])} rows total, {len(tod)} today")
        for r in sorted(tod, key=lambda r: r["start"])[:12]:
            print("      ", r["start"].astimezone(IST).strftime("%H:%M"),
                  (r.get("title") or "")[:70])

# raw: does sporekrani.com name a numbered tabii channel at all today?
page = fetch(s, T.SPOREKRANI_URL).text
hits = sorted(set(re.findall(r"[Tt]abii\s*Spor\s*\d{0,2}", page)))
print("\n### raw sporekrani.com channel mentions:", hits)
print("### page bytes:", len(page))
