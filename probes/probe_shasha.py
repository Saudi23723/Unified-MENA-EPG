"""Shasha's own listing on livefootballtv: its page, what it carries, and
whether each row's time is machine-readable. Commits nothing."""

import json
import re

import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}
BASE = "https://www.livefootballtv.info"

pages = set()
for src in (BASE + "/", BASE + "/channel/mbc-shahid-sports"):
    soup = BeautifulSoup(requests.get(src, headers=UA, timeout=30).text, "html.parser")
    for a in soup.find_all("a", href=True):
        t = a.get_text(" ", strip=True)
        if "shasha" in a["href"].lower() or "شاشا" in t or "shasha" in t.lower():
            href = a["href"] if a["href"].startswith("http") else BASE + a["href"]
            print(f"link on {src[-30:]}: {t!r} -> {href}")
            if "/channel/" in href:
                pages.add(href)
for guess in ("/channel/shasha", "/channel/shasha-tv", "/channel/shahid-shasha"):
    pages.add(BASE + guess)

for url in sorted(pages):
    r = requests.get(url, headers=UA, timeout=30)
    print(f"\n=== {url}  {r.status_code}  {len(r.text)} bytes")
    if r.status_code != 200:
        continue
    soup = BeautifulSoup(r.text, "html.parser")
    print("title:", soup.title.get_text(strip=True) if soup.title else "")
    # machine-readable events
    events = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except Exception:
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack.extend(x)
            elif isinstance(x, dict):
                if "startDate" in x and x.get("name"):
                    events.append((x.get("startDate"), x.get("name")))
                stack.extend(x.values())
    micro = [(m.get("content") or m.get("datetime") or m.get_text(strip=True))
             for m in soup.select('[itemprop="startDate"]')]
    print(f"ld+json events: {len(events)}   microdata startDate: {len(micro)}")
    for e in events[:25]:
        print("  ld:", e)
    for m in micro[:10]:
        print("  micro:", m)
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    lines = [re.sub(r"\s+", " ", x).strip() for x in soup.stripped_strings]
    lines = [x for x in lines if x]
    start = next((i for i, x in enumerate(lines)
                  if re.match(r"^\d{1,2}:\d{2}$", x)), 0)
    print("text walk from first time:")
    for x in lines[max(0, start - 3):start + 90]:
        print("   |", x[:100])
