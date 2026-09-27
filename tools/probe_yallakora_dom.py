#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Is yallakora's match card structured enough to parse safely?

livefootballtv is now ON Sport's only publisher. A second, independent
one would keep the guide fresh when that site changes rather than merely
frozen. yallakora states the channel per match — but a parser written off
flattened text is the fragile kind this project avoids, so the question
is whether the fields are in the markup as attributes and classes.
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime, timedelta, timezone
import requests
from bs4 import BeautifulSoup

CAIRO = timezone(timedelta(hours=3))
now = datetime.now(timezone.utc)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
d = now.astimezone(CAIRO).strftime("%m/%d/%Y")
url = f"https://www.yallakora.com/match-center?date={d}"
r = requests.get(url, headers={"User-Agent": UA,
                               "Accept-Language": "ar,en;q=0.9"}, timeout=30)
print(f"{url}\nHTTP {r.status_code}  {len(r.content)} bytes\n")
soup = BeautifulSoup(r.text, "html.parser")

cards = soup.select("li.liItem, div.liItem, .item.liItem")
print(f"match items found: {len(cards)}\n")
for card in cards[:4]:
    print("=" * 70)
    print(str(card)[:2600])
    print()

print("\n--- every ON Sport item, field by field, if the classes allow it ---")
for card in cards:
    text = " ".join(card.get_text(" ", strip=True).split())
    if not re.search(r"ON\s*Sport|أون\s*سبورت", text, re.I):
        continue
    fields = {}
    for el in card.find_all(True):
        cls = " ".join(el.get("class") or [])
        if not cls:
            continue
        val = " ".join(el.get_text(" ", strip=True).split())
        if val and len(val) < 60:
            fields.setdefault(cls, val)
    print("\n  ", text[:120])
    for k, v in list(fields.items())[:12]:
        print(f"      {k:28} {v[:44]}")
