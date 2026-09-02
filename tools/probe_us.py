#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: does livesoccertv publish an instant, or only a clock?

It is the one American candidate that answers in plain HTML — 68 blocks
with a clock, 17 with a clock and a US broadcaster, where Fox, ESPN and
NBC give none. (Recorded earlier as browser-rendered; that was its
HOMEPAGE. /schedules/ is not.)

Everything now turns on one thing. It prints "9:00pm", a twelve-hour
clock in whichever zone it thinks the caller is — and a clock read in the
wrong zone is the fault that cost this guide a day, and then an hour, and
a reader's trust twice. If the markup carries a real timestamp this is
usable; if it carries only that clock, it is a trap.

Delete once read.
"""
from __future__ import annotations

import re
import sys

from bs4 import BeautifulSoup

from epg_lib import fetch, new_session, norm

URL = "https://www.livesoccertv.com/schedules/"
STAMP = re.compile(r"^\d{9,13}$")


def main() -> int:
    html = fetch(new_session(), URL).text
    soup = BeautifulSoup(html, "html.parser")

    print("=== any element carrying a timestamp-looking attribute ===")
    found = 0
    for node in soup.find_all(True):
        for key, value in (node.attrs or {}).items():
            text = value if isinstance(value, str) else " ".join(value)
            if STAMP.match(text.strip()) or "T" in text and "Z" in text[:30] \
                    and re.match(r"\d{4}-\d{2}-\d{2}T", text.strip()):
                print(f"   <{node.name} {key}={text[:40]!r}> "
                      f"text={norm(node.get_text(' ', strip=True))[:50]!r}")
                found += 1
                break
        if found >= 8:
            break
    if not found:
        print("   none")

    print("\n=== the attributes a row and its cells actually carry ===")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    rows = [r for r in soup.find_all("tr")
            if re.search(r"\d{1,2}:\d{2}\s*[ap]m", norm(r.get_text(" ", strip=True)), re.I)]
    print(f"   {len(rows)} table row(s) hold a clock")
    for row in rows[:2]:
        print(f"\n   <tr {dict(list((row.attrs or {}).items())[:6])}>")
        print(f"      {str(row)[:900]}".replace("\n", " "))

    print("\n=== is a timezone named anywhere ===")
    text = norm(soup.get_text(" ", strip=True))
    for word in ("UTC", "GMT", "timezone", "Time Zone", "EDT", "EST", "PDT",
                 "London", "New York"):
        if word.lower() in text.lower():
            at = text.lower().index(word.lower())
            print(f"   {word!r}: ...{text[max(0,at-60):at+60]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
