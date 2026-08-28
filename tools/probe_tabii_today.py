#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the tabii generator now and report what lands on channels 1-10."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import update_tabii_epg as T

IST = ZoneInfo("Europe/Istanbul")
rc = T.build()
print("\n=== build returned", rc, "===\n")

root = ET.parse(T.OUTPUT).getroot()
today = datetime.now(timezone.utc).astimezone(IST).date()
per = {}
for p in root.findall("programme"):
    raw = p.get("start")
    st = datetime.strptime(raw[:14], "%Y%m%d%H%M%S").replace(
        tzinfo=timezone(timedelta(hours=int(raw[-5:-2]))))
    per.setdefault(p.get("channel"), []).append(
        (st.astimezone(IST), p.findtext("title") or ""))

for cid in sorted(per):
    rows = sorted(r for r in per[cid] if r[0].date() == today)
    real = [r for r in rows if "PPV" not in r[1]]
    print(f"{cid}: {len(rows)} today, {len(real)} real")
    for s, t in real:
        print("     ", s.strftime("%H:%M"), t[:70])
