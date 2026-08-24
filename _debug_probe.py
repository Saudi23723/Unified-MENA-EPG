#!/usr/bin/env python3
"""Probe: (a) candidate OFFICIAL On Time Sports domains, (b) TheSportsDB API,
(c) sport-tv-guide.live / sat.tv channel pages. Temporary, not part of the app."""
import json
import re
import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept-Language": "ar,en-US;q=0.9,en;q=0.8"})

print("############ (A) CANDIDATE OFFICIAL DOMAINS ############")
OFFICIAL_CANDIDATES = [
    "https://www.ontimesports.com/",
    "https://ontimesports.com/",
    "https://www.ontimesports.tv/",
    "https://ontimesports.tv/",
    "https://www.ontimesports.net/",
    "https://www.onsport.tv/",
    "https://onsport.tv/",
    "https://www.on.com.eg/",
    "https://on.com.eg/",
    "https://www.ontimesports.eg/",
    "https://www.unitedmediaservices.net/",
]
for url in OFFICIAL_CANDIDATES:
    try:
        r = s.get(url, timeout=15, allow_redirects=True)
        title = ""
        try:
            t = BeautifulSoup(r.text, "html.parser").find("title")
            title = t.get_text(strip=True)[:110] if t else ""
        except Exception:
            pass
        print(f"  {url}\n     -> HTTP {r.status_code} | final={r.url[:100]} | bytes={len(r.content)} | title={title!r}")
    except Exception as exc:
        print(f"  {url}\n     -> FAILED: {type(exc).__name__}: {str(exc)[:120]}")

print("\n############ (B) THESPORTSDB API ############")
# free/community API keys historically: "3" then "123". Try both.
for key in ["3", "123"]:
    base = f"https://www.thesportsdb.com/api/v1/json/{key}"
    # 1) TV schedule endpoint for soccer on a given day
    for endpoint in [
        "/eventstv.php?d=2026-08-24&s=Soccer",
        "/eventstv.php?d=2026-08-27&s=Soccer",
    ]:
        url = base + endpoint
        try:
            r = s.get(url, timeout=20)
            print(f"  key={key} {endpoint}\n     -> HTTP {r.status_code} bytes={len(r.content)}")
            if r.status_code == 200 and r.content:
                try:
                    data = r.json()
                except Exception:
                    print(f"     non-JSON head: {r.text[:200]!r}")
                    continue
                tv = data.get("tvevents") or data.get("tvEvents") or []
                print(f"     tvevents count: {len(tv) if tv else 0}")
                if tv:
                    print(f"     sample record keys: {list(tv[0].keys())}")
                    print(f"     sample record: {json.dumps(tv[0], ensure_ascii=False)[:600]}")
                    # look for any ON Sport / ON Time channel
                    hits = [e for e in tv if "on time" in str(e.get("strChannel", "")).lower()
                            or "on sport" in str(e.get("strChannel", "")).lower()
                            or "ontime" in str(e.get("strChannel", "")).lower()]
                    print(f"     ON-Sport-ish channel rows: {len(hits)}")
                    for h in hits[:8]:
                        print(f"       {json.dumps(h, ensure_ascii=False)[:400]}")
                    # list distinct channels to see naming convention
                    chans = sorted({str(e.get("strChannel", "")) for e in tv})
                    print(f"     distinct channels ({len(chans)}): {chans[:40]}")
        except Exception as exc:
            print(f"  key={key} {endpoint} -> FAILED: {type(exc).__name__}: {str(exc)[:120]}")

    # 2) channel lookup page (the search result mentioned channel id 1013)
    for endpoint in ["/lookupchannel.php?id=1013", "/all_channels.php"]:
        url = base + endpoint
        try:
            r = s.get(url, timeout=20)
            print(f"  key={key} {endpoint} -> HTTP {r.status_code} bytes={len(r.content)} head={r.text[:200]!r}")
        except Exception as exc:
            print(f"  key={key} {endpoint} -> FAILED: {str(exc)[:100]}")

print("\n############ (C) TheSportsDB HTML channel page ############")
for url in [
    "https://www.thesportsdb.com/channel/1013-on-time-sports-eg-Schedule",
    "https://www.thesportsdb.com/channel/1013",
]:
    try:
        r = s.get(url, timeout=20)
        print(f"  {url} -> HTTP {r.status_code} bytes={len(r.content)}")
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()
            tables = soup.find_all("table")
            print(f"     tables: {len(tables)}")
            for t in tables[:2]:
                for row in t.find_all("tr")[:8]:
                    cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
                    if any(cells):
                        print("       ROW:", cells)
    except Exception as exc:
        print(f"  {url} -> FAILED: {str(exc)[:120]}")

print("\n############ (D) sport-tv-guide.live / sat.tv ############")
for url in [
    "https://sport-tv-guide.live/tv-guide-live/ontime-sports-2",
    "https://sport-tv-guide.live/tv-guide-live/ontime-sports-1",
    "https://sat.tv/chaine/ontimesports/",
]:
    try:
        r = s.get(url, timeout=20)
        print(f"\n  {url} -> HTTP {r.status_code} bytes={len(r.content)}")
        if r.status_code != 200:
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        txt = soup.get_text(" ", strip=True)
        for needle in ["ON Time", "OnTime", "ON Sport", "أون", "اون"]:
            print(f"     '{needle}': {txt.count(needle)}")
        # structural hints
        for kw in ["match", "event", "fixture", "program", "schedule"]:
            els = soup.select(f"[class*={kw}]")
            if els:
                seen = {}
                for el in els[:300]:
                    c = " ".join(el.get("class", []))
                    seen[c] = seen.get(c, 0) + 1
                print(f"     class~{kw}: {sorted(seen.items(), key=lambda x: -x[1])[:6]}")
        print("     first 40 strings:")
        for i, line in enumerate(soup.stripped_strings):
            if i >= 40:
                break
            print(f"       [{i}] {line!r}")
    except Exception as exc:
        print(f"  {url} -> FAILED: {str(exc)[:120]}")
