#!/usr/bin/env python3
"""Focused check: is ontimesports.com the real On Time Sports site with a
schedule, or a parked/spam domain? Temporary, not part of the app."""
import re
import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept-Language": "ar,en-US;q=0.9,en;q=0.8"})

url = "https://www.ontimesports.com/"
r = s.get(url, timeout=25)
print("HTTP", r.status_code, "bytes", len(r.content), "final", r.url)
print("server:", r.headers.get("server"), "| content-type:", r.headers.get("content-type"))

soup = BeautifulSoup(r.text, "html.parser")
for tag in soup(["script", "style", "noscript", "svg"]):
    tag.decompose()

text = soup.get_text(" ", strip=True)
print("visible text length:", len(text))

# Genuine-brand signals vs parked-domain signals
BRAND = ["أون تايم", "اون تايم", "On Time Sports", "OnTime Sports", "ontimesports",
         "الدوري المصري", "الأهلي", "الزمالك", "مباريات", "بث مباشر"]
PARKED = ["domain", "for sale", "parked", "buy this domain", "GoDaddy", "Sedo",
          "related searches", "sponsored listings", "This domain"]
print("\n-- brand signals --")
for k in BRAND:
    print(f"   {k!r}: {text.count(k)}")
print("-- parked/spam signals --")
for k in PARKED:
    print(f"   {k!r}: {text.lower().count(k.lower())}")

print("\n-- first 120 visible strings --")
for i, line in enumerate(soup.stripped_strings):
    if i >= 120:
        break
    print(f"  [{i}] {line!r}")

print("\n-- internal links sample (first 40) --")
seen = []
for a in soup.find_all("a", href=True):
    h = a["href"]
    if h not in seen:
        seen.append(h)
    if len(seen) >= 40:
        break
for h in seen:
    print("   ", h[:140])

# look for anything schedule-like
print("\n-- schedule-ish markers --")
for kw in ["match", "schedule", "fixture", "مباراة", "مواعيد", "جدول", "بث"]:
    els = soup.select(f"[class*={kw}]") if kw.isascii() else []
    print(f"   text '{kw}': {text.count(kw)} | class~'{kw}': {len(els)}")
