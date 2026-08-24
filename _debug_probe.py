#!/usr/bin/env python3
"""Temporary structural probe for kooora.com and yallakora.com. Not part of the app."""
import re
import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

URLS = {
    "kooora-tv": "https://www.kooora.com/%D8%A3%D8%AD%D8%AF%D8%A7%D8%AB-%D8%B1%D9%8A%D8%A7%D8%B6%D9%8A%D8%A9/%D9%83%D8%B1%D8%A9-%D8%A7%D9%84%D9%82%D8%AF%D9%85",
    "kooora-matches-today": "https://www.kooora.com/%D9%83%D8%B1%D8%A9-%D8%A7%D9%84%D9%82%D8%AF%D9%85/%D9%85%D8%A8%D8%A7%D8%B1%D9%8A%D8%A7%D8%AA-%D8%A7%D9%84%D9%8A%D9%88%D9%85",
    "yallakora-matches-center": "https://www.yallakora.com/matches-center",
}

s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept-Language": "ar,en-US;q=0.9,en;q=0.8"})

for label, url in URLS.items():
    print(f"\n===== {label} | {url} =====")
    try:
        r = s.get(url, timeout=20)
        print("HTTP", r.status_code, "bytes", len(r.content))
        r.raise_for_status()
    except Exception as exc:
        print("FETCH FAILED:", exc)
        continue

    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    tables = soup.find_all("table")
    print(f"tables found: {len(tables)}")
    for i, t in enumerate(tables[:3]):
        rows = t.find_all("tr")
        print(f"--- table[{i}] class={t.get('class')} rows={len(rows)} ---")
        for row in rows[:5]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            print("   ROW:", cells)

    # containers commonly used for match cards
    for kw in ["match", "fixture", "game", "event"]:
        els = soup.select(f"[class*={kw}]")
        if not els:
            continue
        seen = {}
        for el in els[:500]:
            cls = " ".join(el.get("class", []))
            seen[cls] = seen.get(cls, 0) + 1
        top = sorted(seen.items(), key=lambda x: -x[1])[:12]
        print(f"-- class contains '{kw}': {len(els)} elements --")
        for cls, cnt in top:
            print(f"   class='{cls}' count={cnt}")

    # look for channel-ish text/class
    ch_els = soup.select("[class*=channel], [class*=tv], [class*=chanel]")
    print(f"channel-ish elements: {len(ch_els)}")
    for el in ch_els[:10]:
        print("   ", str(el)[:200])

    # raw attribute scan for time/date machine-readable data
    attr_pattern = re.compile(
        r'(data-[a-z-]*(?:time|date|utc|ts|epoch)[a-z-]*)\s*=\s*"([^"]{1,40})"', re.I
    )
    found = attr_pattern.findall(r.text)
    seen2 = {}
    for name, val in found:
        seen2.setdefault(name, []).append(val)
    print(f"time-ish data-attrs: { {k: v[:5] for k, v in seen2.items()} }")

    print("--- first 60 stripped_strings ---")
    for i, line in enumerate(soup.stripped_strings):
        if i >= 60:
            break
        print(f"  [{i}] {line!r}")

    # if a plausible match-card container was found, dump raw html of first instance
    for kw in ["match-item", "matchCard", "match_card", "MatchCard", "fixture", "game-card"]:
        el = soup.select_one(f"[class*={kw}]")
        if el:
            print(f"--- raw html sample for '{kw}' (truncated 1200) ---")
            print(str(el)[:1200])
            break
