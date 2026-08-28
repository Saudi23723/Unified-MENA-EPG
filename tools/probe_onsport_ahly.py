#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Does anything say الأهلي plays today, and on which channel?"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime, timedelta, timezone
import update_onsport_epg as O

CAIRO = timezone(timedelta(hours=3))
now = datetime.now(timezone.utc)
print("Cairo now:", now.astimezone(CAIRO).strftime("%Y-%m-%d %H:%M"))

print("\n### what the generator ends up with")
try:
    events = O.collect_filgoal_events()
    print(f"filgoal: {len(events)} events")
    for e in sorted(events, key=lambda e: e.get("start_utc") or now):
        s = e.get("start_utc")
        print("   ", s.astimezone(CAIRO).strftime("%m-%d %H:%M") if s else "?",
              e.get("channel_name"), "|", e.get("home"), "-", e.get("away"))
except Exception as exc:
    print("filgoal collect failed:", exc)

print("\n### each livefootballtv channel page, raw")
for cid, url in O.LIVEFOOTBALLTV.items():
    try:
        page = O.fetch_text(url)
    except Exception as exc:
        print(f"  {cid}: fetch failed {exc}")
        continue
    text = re.sub(r"<[^>]+>", "\n", page)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    hits = [i for i, l in enumerate(lines) if "الأهلي" in l or "الاهلي" in l]
    print(f"  {cid}: {len(lines)} lines, الأهلي on {len(hits)} of them")
    for i in hits[:6]:
        print("      ", " / ".join(lines[max(0, i - 2):i + 3])[:160])

print("\n### the Egyptian Pro League site")
try:
    page = O.fetch_text(O.EPL_HOME)
    text = re.sub(r"<[^>]+>", "\n", page)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    hits = [i for i, l in enumerate(lines) if "الأهلي" in l or "الاهلي" in l]
    print(f"  {len(lines)} lines, الأهلي on {len(hits)}")
    for i in hits[:8]:
        print("      ", " / ".join(lines[max(0, i - 3):i + 4])[:200])
except Exception as exc:
    print("  failed:", exc)
