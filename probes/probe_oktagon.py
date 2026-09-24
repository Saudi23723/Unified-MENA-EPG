"""What oktagonmma.com publishes about its events, from a runner. Never fails."""
import json
import re
import traceback

import requests

S = requests.Session()
S.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def show(url, pats=()):
    print("=" * 70, "\n--", url)
    try:
        r = S.get(url, timeout=30)
        t = r.text
        print(r.status_code, r.url, len(t), r.headers.get("content-type"))
        print("title:", re.search(r"<title>(.*?)</title>", t, re.S) and
              re.search(r"<title>(.*?)</title>", t, re.S).group(1)[:120])
        for m in re.finditer(r'<script[^>]*type="application/(?:ld\+)?json"[^>]*>(.*?)</script>', t, re.S):
            print("JSON script:", m.group(1)[:1500])
        nd = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S)
        if nd:
            print("NEXT_DATA:", nd.group(1)[:3000])
        print("event links:", sorted(set(re.findall(r'href="([^"]*/events/[^"]+)"', t)))[:40])
        print("startDate:", re.findall(r'"startDate"\s*:\s*"[^"]+"', t)[:20])
        print("datetime attrs:", re.findall(r'datetime="[^"]+"', t)[:20])
        for p in pats:
            for m in list(re.finditer(p, t, re.I))[:8]:
                s = max(0, m.start() - 200)
                print(f"[{p}]", re.sub(r"\s+", " ", t[s:m.end() + 300]))
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S)))
        print("TEXT:", text[:3000])
        return t
    except Exception:
        traceback.print_exc()
        return ""


show("https://lnk.bio/oktagonmma")
show("https://oktagonmma.com/en/events/", (r"\b\d{1,2}[./]\s?\d{1,2}[./]\s?20\d\d", r"\d{1,2}:\d{2}"))
show("https://oktagonmma.com/en/events/oktagon-94-frankfurt/",
     (r"\d{1,2}:\d{2}", r"CET|CEST|UTC|GMT", r"oktagon\.tv|dazn|voyo|stream|broadcast|tv"))
for u in ("https://oktagonmma.com/api/events", "https://oktagonmma.com/en/api/events",
          "https://api.oktagonmma.com/events", "https://oktagon.tv/", "https://oktagonmma.com/sitemap.xml"):
    show(u)
