"""What UAE Warriors' own site publishes about its events, from a runner. Never fails."""
import re
import traceback

import requests

S = requests.Session()
S.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

for url in ("https://www.uaewarriors.com/", "https://www.uaewarriors.com/events",
            "https://uaewarriors.com/events/", "https://www.uaewarriors.com/en/events",
            "https://www.mostvaluablepromotions.com/events/?filter=upcoming"):
    print("=" * 70, "\n--", url)
    try:
        r = S.get(url, timeout=30)
        t = r.text
        print(r.status_code, r.url, len(t), r.headers.get("content-type"))
        m = re.search(r"<title>(.*?)</title>", t, re.S)
        print("title:", m and m.group(1).strip()[:120])
        for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', t, re.S):
            print("LD:", re.sub(r"\s+", " ", m.group(1))[:800])
        nd = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S)
        if nd:
            print("NEXT_DATA:", nd.group(1)[:2000])
        print("framework:", [k for k in ("__NUXT__", "self.__next_f", "wp-content", "wix", "squarespace", "webflow") if k in t])
        print("links:", sorted(set(re.findall(r'href="([^"]*(?:event|uae-warriors-\d|uaew)[^"]*)"', t, re.I)))[:40])
        print("ISO:", sorted(set(re.findall(r"20\d\d-\d\d-\d\dT\d\d:\d\d[^\"'<\s]{0,12}", t)))[:20])
        print("data-attrs:", sorted(set(re.findall(r'data-[a-z-]*(?:date|time|start)[a-z-]*="[^"]{0,40}"', t, re.I)))[:20])
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ",
                      re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S)))
        print("TEXT:", text[:2500])
    except Exception:
        traceback.print_exc()
