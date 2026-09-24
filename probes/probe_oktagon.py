"""The structure of oktagonmma.com's embedded event data, from a runner. Never fails."""
import json
import re
import traceback

import requests

S = requests.Session()
S.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def data(url):
    t = S.get(url, timeout=30).text
    return json.loads(re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S).group(1))


def events_in(node, out):
    if isinstance(node, dict):
        if "startDate" in node and "slug" in node:
            out.append(node)
        for v in node.values():
            events_in(v, out)
    elif isinstance(node, list):
        for v in node:
            events_in(v, out)


for url in ("https://oktagonmma.com/en/events/", "https://oktagonmma.com/en/",
            "https://oktagonmma.com/en/events/?type=upcoming"):
    print("=" * 70, "\n--", url)
    try:
        d = data(url)
        for q in d["props"]["pageProps"].get("dehydratedState", {}).get("queries", []):
            print("QUERY", json.dumps(q.get("queryKey"))[:300])
        found = []
        events_in(d, found)
        seen = set()
        for e in found:
            k = (e["slug"], e["startDate"])
            if k in seen:
                continue
            seen.add(k)
            t = e.get("title") or {}
            print(" ", e["startDate"], e["slug"], "|", t.get("en") or next(iter(t.values()), ""),
                  "| state", e.get("state"), "| type", e.get("type"), e.get("eventType"))
        if found:
            print("KEYS:", sorted(found[0].keys()))
    except Exception:
        traceback.print_exc()

print("=" * 70, "\n-- event 94 detail")
try:
    d = data("https://oktagonmma.com/en/events/oktagon-94-frankfurt/")
    e = d["props"]["pageProps"]["dehydratedState"]["queries"][0]["state"]["data"]
    for k, v in e.items():
        if k in ("description",):
            continue
        s = json.dumps(v, ensure_ascii=False)
        print(f"  {k}: {s[:400]}")
except Exception:
    traceback.print_exc()
