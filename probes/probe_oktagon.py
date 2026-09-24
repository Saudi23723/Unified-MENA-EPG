"""The raw shape of PFL's and BRAVE CF's event cards, from a runner. Never fails."""
import re
import traceback

import requests

S = requests.Session()
S.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def get(url):
    r = S.get(url, timeout=30)
    print("=" * 70, "\n--", url, r.status_code, len(r.text))
    return r.text


def around(t, pat, before=1500, after=1500, n=1):
    for m in list(re.finditer(pat, t))[:n]:
        print(f"[{pat}] ...", re.sub(r"\s+", " ", t[max(0, m.start() - before):m.end() + after]))


try:
    t = get("https://pflmma.com/events")
    around(t, r"PFL Chicago 2", 2500, 800)
    around(t, r"PFL MENA 11", 2500, 800)
except Exception:
    traceback.print_exc()

for slug in ("pflmena11", "pfl-morocco", "pfl-returns-to-dubai", "2026-chicago2", "pfl-lyon-2026"):
    try:
        t = get(f"https://pflmma.com/event/{slug}")
        for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', t, re.S):
            if "Event" in m.group(1) and "startDate" in m.group(1):
                print("LD:", re.sub(r"\s+", " ", m.group(1))[:1200])
        print("ISO:", sorted(set(re.findall(r"20\d\d-\d\d-\d\dT\d\d:\d\d[^\"'<\s]{0,12}", t)))[:10])
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ",
                      re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S)))
        for m in list(re.finditer(r"\b\d{1,2}(?::\d\d)?\s?[ap]m\s?(?:ET|EST|EDT|AST|GST|GMT|CET|CEST|BST|local|WAT|UTC)?", text, re.I))[:6]:
            print("TIME:", text[max(0, m.start() - 150):m.end() + 100])
    except Exception:
        traceback.print_exc()

try:
    t = get("https://www.bravecf.com/events")
    around(t, r"events/brave-cf-108", 300, 2000)
    t = get("https://www.bravecf.com/events/brave-cf-108")
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', t, re.S):
        if "startDate" in m.group(1):
            print("LD:", re.sub(r"\s+", " ", m.group(1))[:1500])
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ",
                  re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S)))
    for m in list(re.finditer(r"\b\d{1,2}(?::\d\d)?\s?[ap]m|\d\d:\d\d\s?(?:GMT|UTC|CET|CEST|local)", text, re.I))[:6]:
        print("TIME:", text[max(0, m.start() - 150):m.end() + 100])
except Exception:
    traceback.print_exc()
