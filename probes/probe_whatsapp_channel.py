#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print, do not guess: what a WhatsApp Channel link actually serves.

"هل هاي ممكن تفيدنا؟" — asked of a WhatsApp Channel named مباريات اليوم,
which is this build's own channel-one name, so it is most likely the
reader's own channel rather than a stranger's.

That makes it a question with two halves, and they have different
answers:

  READING it as a source. Could the build take fixtures from posts on
  that channel? This asks the invite page what it serves a runner —
  size, whether any fixture-looking text is in the HTML, and whether
  there is a clock anywhere. A page of JavaScript with an install
  button is not a source.

  WRITING to it as a destination. Could the build post today's board
  there automatically? That is not a question for this probe: Meta's
  official Cloud API does not expose Channels at all, which is settled
  documentation rather than something to measure.

Fifteen seconds. Nothing is wired off this. It prints; a human reads.
"""
from __future__ import annotations

import re
import sys

sys.path.insert(0, ".")
import requests                                          # noqa: E402

LINK = "https://whatsapp.com/channel/0029VaCs02ZGufIvBhuL8y41"
LIKE_A_BROWSER = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/128.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "ar,en;q=0.9",
}
A_CLOCK = re.compile(r"\b([0-2]?\d):([0-5]\d)\b")
A_FIXTURE = re.compile(r"\bvs\b|\bv\.\b| - |ضد|مباراة|مباريات", re.I)

for label, url in (("the channel link", LINK),
                   ("without the www", LINK.replace("whatsapp.com",
                                                    "www.whatsapp.com"))):
    try:
        got = requests.get(url, headers=LIKE_A_BROWSER, timeout=15)
    except Exception as exc:                              # noqa: BLE001
        print(f"  {label:22} FAILED {type(exc).__name__}")
        continue
    body = got.text or ""
    print(f"  {label:22} {got.status_code}  {len(body):>8,}B  "
          f"{len(A_CLOCK.findall(body)):>3} clocks  "
          f"{len(A_FIXTURE.findall(body)):>3} fixture-ish")
    title = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
    desc = re.search(r'<meta[^>]+property="og:description"[^>]+'
                     r'content="([^"]*)"', body, re.I)
    print(f"  {'':22} title: {(title.group(1).strip()[:70]) if title else '—'}")
    print(f"  {'':22} og:desc: {(desc.group(1)[:70]) if desc else '—'}")

print()
print("  A source needs fixtures IN the HTML with clocks beside them.")
print("  A title and an og:description are a share card, not a schedule.")
