#!/usr/bin/env python3
"""Check whether ON Sport actually appears as a listed broadcaster on
kooora.com / yallakora.com, and if so, dump the exact surrounding markup
of one such match so a real parser can be written against it."""
import re
import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

NEEDLES = ["ON Sport", "اون سبورت", "أون سبورت", "اون تايم", "أون تايم", "ontime", "OnTime"]

URLS = {
    "kooora-matches-today": "https://www.kooora.com/%D9%83%D8%B1%D8%A9-%D8%A7%D9%84%D9%82%D8%AF%D9%85/%D9%85%D8%A8%D8%A7%D8%B1%D9%8A%D8%A7%D8%AA-%D8%A7%D9%84%D9%8A%D9%88%D9%85",
    "yallakora-matches-center": "https://www.yallakora.com/matches-center",
}

s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept-Language": "ar,en-US;q=0.9,en;q=0.8"})

for label, url in URLS.items():
    print(f"\n===== {label} =====")
    try:
        r = s.get(url, timeout=20)
        print("HTTP", r.status_code, "bytes", len(r.content))
    except Exception as exc:
        print("FETCH FAILED:", exc)
        continue

    html = r.text
    for needle in NEEDLES:
        count = html.count(needle)
        print(f"  '{needle}' occurrences: {count}")

    # if any needle found, show context + walk up to the nearest match-ish ancestor
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    found_any = False
    for needle in NEEDLES:
        node = soup.find(string=re.compile(re.escape(needle)))
        if not node:
            continue
        found_any = True
        print(f"\n  --- context for '{needle}' ---")
        el = node.parent
        # walk up a few levels to capture the whole match card
        for _ in range(6):
            if el and el.get("class") and any(
                k in " ".join(el.get("class", [])).lower()
                for k in ["match", "event", "fixture"]
            ):
                break
            if el and el.parent:
                el = el.parent
        print(str(el)[:2500] if el else "no ancestor found")

    if not found_any:
        print("  NO 'ON Sport' MENTIONS FOUND ANYWHERE ON THIS PAGE (today's snapshot).")

    # also dump one full raw match-card / match-list-item, whatever exists,
    # so we understand the general structure regardless of ON Sport presence
    for sel in [".fco-match-list-item", "[class*=matchCard]"]:
        el = soup.select_one(sel)
        if el:
            print(f"\n  --- full raw sample for selector '{sel}' ---")
            print(str(el)[:3000])
            break
