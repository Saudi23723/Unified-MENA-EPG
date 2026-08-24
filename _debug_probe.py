#!/usr/bin/env python3
"""Temporary structural probe for livesoccertv.com channel pages. Not part of the app."""
import re
import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

URL = "https://www.livesoccertv.com/channels/on-sport-plus/"

for label, cookies in [
    ("no-cookie", {}),
    ("tz=UTC", {"tz": "UTC"}),
    ("tz=Africa/Cairo", {"tz": "Africa/Cairo"}),
    ("timezone=Africa/Cairo", {"timezone": "Africa/Cairo"}),
    ("myTimezone=Africa/Cairo", {"myTimezone": "Africa/Cairo"}),
]:
    print(f"\n===== cookies={label} =====")
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    try:
        r = s.get(URL, timeout=20, cookies=cookies)
        print("HTTP", r.status_code, "bytes", len(r.content))
    except Exception as exc:
        print("FETCH FAILED:", exc)
        continue

    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table", class_="schedules")
    if not table:
        print("no schedules table")
        continue
    rows = table.find_all("tr")
    for row in rows[:6]:
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
        print("  ROW:", cells)

# Now dig for machine-readable timestamps near the match row (data-*, datetime=, epoch, etc.)
print("\n===== searching for machine-readable time attributes =====")
s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
r = s.get(URL, timeout=20)
html = r.text

# any tag attributes that look time/date/epoch related
attr_pattern = re.compile(
    r'(data-[a-z-]*(?:time|date|utc|ts|epoch)[a-z-]*|datetime)\s*=\s*"([^"]{1,40})"',
    re.I,
)
found = attr_pattern.findall(html)
print(f"candidate time-ish attributes found: {len(found)}")
seen = {}
for name, val in found:
    seen.setdefault(name, []).append(val)
for name, vals in seen.items():
    print(f"  {name}: sample values {vals[:5]}")

# look for a JS variable holding timezone or offset info
tz_hint = re.search(r'(timezone|utcoffset|gmtoffset|tzname)["\']?\s*[:=]\s*["\']?([^,"\';\n]{1,40})', html, re.I)
print("timezone-ish JS hint:", tz_hint.group(0) if tz_hint else None)

# look for the raw <tr> HTML around the match row (id="match") to see all attrs/siblings
soup2 = BeautifulSoup(html, "html.parser")
match_td = soup2.find("td", id="match")
if match_td:
    tr = match_td.find_parent("tr")
    print("\n--- full <tr> for the match row (raw) ---")
    print(str(tr)[:2000])

# look for any element carrying the visitor's detected timezone/offset (often near a "clock" widget)
clock = soup2.find(string=re.compile(r"time zone", re.I))
if clock:
    print("\n--- 'time zone' text context ---")
    print(clock.parent.get_text(" ", strip=True)[:300])
    print(str(clock.parent)[:1000])
