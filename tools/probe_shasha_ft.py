#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What does the source actually call the side this guide prints as "FT"?

The guide publishes "FT - Al Sahel" and "FT - Kazma" in the Kuwaiti Zain
league on 27 August. Al Sahel and Kazma are real clubs. FT is either a
club this reader does not know, or a status code — full time — picked up
where a team name was expected. Asserting either without looking is how
the ON Sport mistake happened, so this looks.
"""
import os, re, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import update_shasha_epg as S
from bs4 import BeautifulSoup

print("Kuwait Zain league — what each source says\n")

for label, url in [("oddalerts", S.ODDALERTS_ZAIN if hasattr(S, "ODDALERTS_ZAIN") else None),
                   ("soccerway", S.SOCCERWAY_ZAIN if hasattr(S, "SOCCERWAY_ZAIN") else None)]:
    if not url:
        continue
    print(f"===== {label}: {url}")
    try:
        html = S.fetch_text(url)
    except Exception as exc:
        print("   FAILED", exc); continue
    soup = BeautifulSoup(html, "html.parser")
    text = re.sub(r"<[^>]+>", "\n", re.sub(r"<script.*?</script>", " ", html, flags=re.S|re.I))
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for needle in ("Sahel", "Kazma"):
        idx = [i for i, l in enumerate(lines) if needle in l]
        print(f"   '{needle}' on {len(idx)} line(s)")
        for i in idx[:4]:
            print("      ", " | ".join(lines[max(0,i-4):i+5])[:200])
    ft = [l for l in lines if re.fullmatch(r"FT", l.strip())]
    print(f"   lines that are exactly 'FT': {len(ft)}")
    print()

print("===== what the generator's own readers return")
for name in ("_parse_oddalerts_zain", "_parse_soccerway_zain"):
    fn = getattr(S, name, None)
    if fn is None:
        print(f"   {name}: not present"); continue
    try:
        evs = fn()
    except Exception as exc:
        print(f"   {name}: FAILED {exc}"); continue
    print(f"   {name}: {len(evs)} events")
    for e in evs[:12]:
        print(f"      {e['start']:%m-%d %H:%M}Z  {e['title']}")
