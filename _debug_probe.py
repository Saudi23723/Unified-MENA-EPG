#!/usr/bin/env python3
"""Temporary structural probe for livesoccertv.com channel pages. Not part of the app."""
import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

URLS = {
    "ON Sport 1": "https://www.livesoccertv.com/channels/on-sport-egypt/",
    "ON Sport 2": "https://www.livesoccertv.com/channels/on-sport-2-egypt/",
    "ON Sport MAX": "https://www.livesoccertv.com/channels/on-sport-max/",
    "ON Sport PLUS": "https://www.livesoccertv.com/channels/on-sport-plus/",
}

s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,ar;q=0.8"})

for name, url in URLS.items():
    print(f"\n===== {name} | {url} =====")
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

    # 1) Any <table> present?
    tables = soup.find_all("table")
    print(f"tables found: {len(tables)}")
    for i, t in enumerate(tables[:2]):
        print(f"--- table[{i}] class={t.get('class')} id={t.get('id')} ---")
        rows = t.find_all("tr")
        print(f"  rows: {len(rows)}")
        for row in rows[:6]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            print("   ROW:", cells)

    # 2) Common list-item containers
    candidates = soup.select("[class*=match]") or []
    print(f"elements with class containing 'match': {len(candidates)}")
    seen_classes = {}
    for el in candidates[:400]:
        cls = " ".join(el.get("class", []))
        seen_classes[cls] = seen_classes.get(cls, 0) + 1
    top = sorted(seen_classes.items(), key=lambda x: -x[1])[:15]
    for cls, cnt in top:
        print(f"  class='{cls}' count={cnt}")

    # 3) Sample first plausible match-like element's raw HTML
    if candidates:
        print("--- sample element[0] outer html (truncated 800 chars) ---")
        print(str(candidates[0])[:800])
        if len(candidates) > 3:
            print("--- sample element[3] outer html (truncated 800 chars) ---")
            print(str(candidates[3])[:800])

    # 4) Fallback: dump plain stripped_strings lines (first 80) to see textual layout
    print("--- first 80 stripped_strings ---")
    for i, line in enumerate(soup.stripped_strings):
        if i >= 80:
            break
        print(f"  [{i}] {line!r}")
