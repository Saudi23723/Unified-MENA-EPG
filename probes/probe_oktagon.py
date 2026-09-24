"""What PFL's and BRAVE CF's own sites publish about their events, from a runner. Never fails."""
import json
import re
import traceback

import requests

S = requests.Session()
S.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

URLS = [
    "https://pflmma.com/events", "https://pflmma.com/schedule", "https://www.pflmma.com/",
    "https://pflmma.com/events/upcoming",
    "https://www.bravecf.com/events", "https://bravecf.com/events", "https://www.bravecf.com/",
    "https://www.bravecf.com/upcoming-events",
    "https://site.api.espn.com/apis/site/v2/sports/mma/pfl/scoreboard?dates=20260901-20261231",
]
for url in URLS:
    print("=" * 70, "\n--", url)
    try:
        r = S.get(url, timeout=30)
        t = r.text
        print(r.status_code, r.url, len(t), r.headers.get("content-type"))
        if "json" in (r.headers.get("content-type") or ""):
            d = r.json()
            for e in d.get("events", []):
                c = (e.get("competitions") or [{}])[0]
                print("  ESPN", e.get("date"), e.get("name"), e["status"]["type"]["name"],
                      "| broadcasts", json.dumps(c.get("broadcasts"))[:120],
                      "| timeValid", e.get("timeValid"))
            continue
        m = re.search(r"<title>(.*?)</title>", t, re.S)
        print("title:", m and m.group(1).strip()[:120])
        for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', t, re.S):
            print("LD:", re.sub(r"\s+", " ", m.group(1))[:1200])
        nd = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S)
        if nd:
            print("NEXT_DATA:", nd.group(1)[:1500])
        print("nuxt/next other:", bool(re.search(r"__NUXT__|self\.__next_f", t)))
        print("event links:", sorted(set(re.findall(r'href="([^"]*(?:event|fight)[^"]*)"', t, re.I)))[:30])
        print("ISO dates:", sorted(set(re.findall(r"20\d\d-\d\d-\d\dT\d\d:\d\d[^\"'<\s]{0,10}", t)))[:30])
        print("data-attrs:", sorted(set(re.findall(r'data-[a-z-]*(?:date|time|start)[a-z-]*="[^"]{0,60}"', t, re.I)))[:30])
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ",
                      re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S)))
        print("TEXT:", text[:2500])
    except Exception:
        traceback.print_exc()
