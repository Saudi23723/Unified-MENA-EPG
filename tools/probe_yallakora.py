#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dump the real structure of the two pages that can replace FilGoal."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime, timedelta, timezone
import requests
from bs4 import BeautifulSoup

CAIRO = timezone(timedelta(hours=3))
now = datetime.now(timezone.utc)
print("Cairo now:", now.astimezone(CAIRO).strftime("%Y-%m-%d %H:%M"))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def soup(url):
    r = requests.get(url, headers={"User-Agent": UA,
                                   "Accept-Language": "ar,en;q=0.9"}, timeout=30)
    print(f"\n===== {url}  HTTP {r.status_code}  {len(r.content)} bytes")
    return BeautifulSoup(r.text, "html.parser") if r.status_code == 200 else None


d = now.astimezone(CAIRO).strftime("%m/%d/%Y")
s = soup(f"https://www.yallakora.com/match-center?date={d}")
if s:
    # find the smallest element that contains both a time and a channel name
    best = None
    for el in s.find_all(True):
        t = " ".join(el.get_text(" ", strip=True).split())
        if re.search(r"ON\s*Sport", t, re.I) and re.search(r"\d{1,2}:\d{2}", t) \
           and len(t) < 300:
            best = el
    if best is not None:
        print("\n--- innermost card containing a time and a channel ---")
        print(str(best)[:3000])
        print("\n--- its parent's classes ---")
        p = best.parent
        for _ in range(4):
            if p is None:
                break
            print("   ", p.name, p.get("class"))
            p = p.parent
    print("\n--- every card, flattened ---")
    seen = set()
    for el in s.find_all(class_=True):
        t = " ".join(el.get_text(" ", strip=True).split())
        if 20 < len(t) < 220 and re.search(r"\d{1,2}:\d{2}", t) and t not in seen:
            cls = " ".join(el.get("class"))
            if re.search(r"item|match|card|row", cls, re.I):
                seen.add(t)
                print(f"   [{cls[:34]:34}] {t[:150]}")

s = soup("https://www.livefootballtv.info/")
if s:
    print("\n--- livefootballtv home: rows naming ON Sport ---")
    seen = set()
    for el in s.find_all(True):
        t = " ".join(el.get_text(" ", strip=True).split())
        if re.search(r"On\s*Sport", t, re.I) and re.search(r"\d{1,2}:\d{2}", t) \
           and 20 < len(t) < 200 and t not in seen:
            seen.add(t)
            print(f"   <{el.name} class={el.get('class')}> {t[:150]}")
    print("\n--- one such row's markup ---")
    for el in s.find_all(True):
        t = " ".join(el.get_text(" ", strip=True).split())
        if re.search(r"Al Ahly", t, re.I) and re.search(r"\d{1,2}:\d{2}", t) \
           and len(t) < 200:
            print(str(el)[:2000])
            break
