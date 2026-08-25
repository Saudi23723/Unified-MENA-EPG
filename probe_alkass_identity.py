#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: Alkass publishes its own TV guide at alkass.net/tvguide.

beIN's guide — what this project currently reads — repeats Alkass 1's
schedule on Alkass 4 and Alkass 5's on Alkass 7, so four of the eight
channels cannot all be right there. Alkass is the broadcaster, so its own
guide settles it. This maps out that page: how channels and days are
addressed, where the times and titles sit, and whether English exists.
Changes nothing.
"""
from __future__ import annotations

import html
import re

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "Accept-Language": "ar,en;q=0.8"}
T = (5, 20)


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def get(url, **kw):
    try:
        return requests.get(url, headers=H, timeout=T, allow_redirects=True, **kw)
    except Exception as exc:
        print(f"  {url} FAILED: {exc}", flush=True)
        return None


def main():
    section("alkass.net/tvguide")
    r = get("https://www.alkass.net/tvguide")
    if r is None or r.status_code != 200:
        print(f"  status={getattr(r, 'status_code', '-')}", flush=True)
        return
    t = r.text
    print(f"  status={r.status_code} bytes={len(t)} final={r.url}", flush=True)

    print("\n  forms / selects / inputs (how the page is parameterised):", flush=True)
    for m in re.finditer(r"<(form|select|input|option)\b[^>]*>", t, re.I):
        print("   ", m.group(0)[:200], flush=True)

    print("\n  scripts that look like they fetch the schedule:", flush=True)
    for m in re.finditer(r"(ajax|fetch\(|\$\.get|\$\.post|url\s*[:=]\s*['\"][^'\"]+)",
                         t, re.I):
        print("   ", t[max(0, m.start() - 90):m.start() + 160].replace("\n", " "),
              flush=True)

    print("\n  internal links:", flush=True)
    links = sorted({h for h in re.findall(r"href=['\"]([^'\"#]+)['\"]", t)
                    if not h.startswith(("http", "//", "mailto"))})
    print("   ", links[:60], flush=True)

    print("\n  first 6000 chars of visible text:", flush=True)
    print(clean(t)[:6000], flush=True)

    section("raw markup of the schedule area")
    # anchor on a time-looking string and show what surrounds it
    hits = list(re.finditer(r"\b([01]\d|2[0-3]):[0-5]\d\b", t))
    print(f"  {len(hits)} clock-like strings", flush=True)
    for m in hits[:3]:
        print("\n  ----", flush=True)
        print(t[max(0, m.start() - 1400):m.start() + 900].replace("\n", " "), flush=True)

    section("other endpoints worth trying")
    for u in ("https://www.alkass.net/tvguide?lang=en",
              "https://www.alkass.net/en/tvguide",
              "https://www.alkass.net/programs",
              "https://www.alkass.net/tvguide?channel=2",
              "https://www.alkass.net/tvguide?ch=2"):
        rr = get(u)
        if rr is None:
            continue
        body = clean(rr.text)
        print(f"  {u} -> {rr.status_code} {len(rr.text)}b  same_as_tvguide="
              f"{rr.text == t}", flush=True)
        print(f"    {body[:220]}", flush=True)


if __name__ == "__main__":
    main()
