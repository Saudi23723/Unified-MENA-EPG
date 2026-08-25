#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: alkass.net/tvguide holds two renderings of the same guide.

The collapsible cg1..cg8 list near the top repeats itself (1=4=8, 2=5=7,
3=6) and duplicates rows inside a table, so it is not usable. After it the
page opens <div class="tvguide-full"> with a day switcher — اليوم and
tvguide?day=next — and a <div class="tg-content"> holding the real grid.
This dumps that region so its structure can be read. Changes nothing.
"""
from __future__ import annotations

import re

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "Accept-Language": "ar,en;q=0.8"}
T = (5, 25)


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def main():
    for url in ("https://www.alkass.net/tvguide",
                "https://www.alkass.net/tvguide?day=next"):
        r = requests.get(url, headers=H, timeout=T)
        t = r.text
        section(f"{url}  status={r.status_code} bytes={len(t)}")
        i = t.find('class="tvguide-full"')
        print(f"tvguide-full at {i}", flush=True)
        if i < 0:
            continue
        region = t[i:]
        print(f"region is {len(region)} bytes", flush=True)
        print("\n---- first 9000 chars of the region ----", flush=True)
        print(region[:9000], flush=True)
        print("\n---- tag inventory in the region ----", flush=True)
        tags = {}
        for m in re.finditer(r"<(\w+)([^>]*)>", region):
            key = m.group(1) + " " + " ".join(
                sorted(set(re.findall(r"(?:class|id)=['\"]?([\w\- ]+)",
                                      m.group(2)))))
            tags[key] = tags.get(key, 0) + 1
        for k, v in sorted(tags.items(), key=lambda x: -x[1])[:40]:
            print(f"  {v:5}  {k[:110]}", flush=True)


if __name__ == "__main__":
    main()
