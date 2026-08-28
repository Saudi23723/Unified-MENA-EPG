#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Does al-Ahly play today, on which channel, and can FilGoal still be read?"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime, timedelta, timezone
import requests
import update_onsport_epg as O

CAIRO = timezone(timedelta(hours=3))
now = datetime.now(timezone.utc)
print("Cairo now:", now.astimezone(CAIRO).strftime("%Y-%m-%d %H:%M"))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def get(url, headers=None):
    h = {"User-Agent": UA, "Accept-Language": "ar,en;q=0.8"}
    h.update(headers or {})
    return requests.get(url, headers=h, timeout=25)


def show(label, url, needle="الأهلي", extra=("الاهلي",), span=3, limit=8):
    try:
        r = get(url)
    except Exception as exc:
        print(f"  {label}: FAILED {exc}")
        return
    if r.status_code != 200:
        print(f"  {label}: HTTP {r.status_code}")
        return
    text = re.sub(r"<script.*?</script>", " ", r.text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    hits = [i for i, l in enumerate(lines)
            if needle in l or any(e in l for e in extra)]
    print(f"  {label}: HTTP 200, {len(lines)} lines, al-Ahly on {len(hits)}")
    for i in hits[:limit]:
        print("      ", " | ".join(lines[max(0, i - span):i + span + 1])[:220])


print("\n### where today's Egyptian fixtures and their channels are listed")
for label, url in [
    ("livefootballtv home", "https://www.livefootballtv.info/"),
    ("livefootballtv today", "https://www.livefootballtv.info/matches"),
    ("EPL matches", "https://www.egyptianproleague.com/matches"),
    ("EPL home", "https://www.egyptianproleague.com/"),
    ("yallakora today", "https://www.yallakora.com/match-center"),
    ("kooora matches", "https://www.kooora.com/"),
]:
    show(label, url)

print("\n### can FilGoal be read at all, and with what")
for label, url, headers in [
    ("RSS plain", "https://www.filgoal.com/section/88/rss/الدوري-المصري", {}),
    ("RSS browser UA", "https://www.filgoal.com/section/88/rss/الدوري-المصري",
     {"Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
      "Referer": "https://www.filgoal.com/"}),
    ("section page", "https://www.filgoal.com/section/88/articles/", {}),
    ("home", "https://www.filgoal.com/", {}),
    ("matches", "https://www.filgoal.com/matches", {}),
]:
    try:
        r = get(url, headers)
        body = r.text[:200].replace("\n", " ")
        print(f"  {label:16} HTTP {r.status_code}  {len(r.content):7} bytes  {body[:90]}")
    except Exception as exc:
        print(f"  {label:16} FAILED {exc}")

print("\n### what the generator's own fetch_text says the ON Sport pages carry today")
for cid, url in O.LIVEFOOTBALLTV.items():
    try:
        page = O.fetch_text(url)
    except Exception as exc:
        print(f"  {cid}: {exc}")
        continue
    text = re.sub(r"<[^>]+>", "\n", page)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    today = now.astimezone(CAIRO).strftime("%d")
    print(f"  {cid}:")
    for l in lines:
        if re.search(r"\d{1,2}:\d{2}", l) and len(l) < 120:
            print("      ", l[:110])
