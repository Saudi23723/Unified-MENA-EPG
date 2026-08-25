#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only: is each Alkass block on bein.com really the channel its logo
filename claims, and does its schedule match Alkass's own?

alkass_epg.py attaches every programme to the channel named by the nearest
preceding logo image, 2023_Alkass_N.png. That assumes N is the real channel
number. If beIN's page reuses or misnumbers those images, all eight
channels are mislabelled and every programme lands on the wrong one — a
failure that looks exactly like "the schedule is wrong".

Prints, for every channel block on the page, the logo filename with any
name, id or alt sitting beside it; the raw markup around the first Alkass
blocks; today's parsed schedule per channel; and, for comparison, whatever
alkass.net publishes. Changes nothing.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone

import requests

DOHA = timezone(timedelta(hours=3))
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "Accept-Language": "ar,en;q=0.8"}
URL = ("https://www.bein.com/{lang}/epg-ajax-template/?action=epg_fetch"
       "&category=sports&cdate={d}&language={LANG}&loadindex=0&mins=00"
       "&offset=0&postid={pid}&serviceidentity=bein.net")
T = (5, 20)

LOGO = re.compile(r"/(\d{4})_([A-Za-z0-9_]+)\.png")
TOKEN = re.compile(r"(?P<logo>/\d{4}_[A-Za-z0-9_]+\.png)"
                   r"|(?P<row><li(?:\s[^>]*?)?>.*?</li>)", re.S | re.I)
ALKASS = re.compile(r"/\d{4}_Alkass_(\d+)\.png", re.I)
RANGE = re.compile(r"data-start='([\d\- :]+)'\s+data-end='([\d\- :]+)'")
TITLE = re.compile(r"<p class=title>(.*?)</p>", re.S)


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def logo_map(text):
    """Every channel logo in document order with what identifies it."""
    rows = []
    for i, m in enumerate(LOGO.finditer(text)):
        before, after = text[max(0, m.start() - 900):m.start()], text[m.end():m.end() + 400]
        ids = re.findall(r"id=['\"]?(channels_\d+|slider_\d+|ch_\d+)", before + after)
        alt = re.findall(r"alt=['\"]([^'\"]{2,60})['\"]", before + after)
        # any human-readable channel name sitting in the same block
        names = re.findall(r"class=['\"]?(?:channel|channel-name|name)['\"]?[^>]*>([^<]{2,60})<",
                           before + after)
        rows.append((i, m.group(2), ids[:2], alt[:2], [clean(n) for n in names[:2]]))
    return rows


def parse(text):
    """{n: [(start, stop, title)]} exactly the way alkass_epg.py reads it."""
    out, cur = {}, None
    for m in TOKEN.finditer(text):
        if m.group("logo"):
            hit = ALKASS.match(m.group("logo"))
            cur = int(hit.group(1)) if hit else None
            continue
        if cur is None:
            continue
        row = m.group("row")
        span, title = RANGE.search(row), TITLE.search(row)
        if span and title:
            out.setdefault(cur, []).append((span.group(1), span.group(2), clean(title.group(1))))
    return out


def main():
    day = datetime.now(DOHA).strftime("%Y-%m-%d")
    print(f"Doha today: {day}   now: {datetime.now(DOHA):%H:%M}", flush=True)
    pages = {}

    for lang, pid in (("ar", "25344"), ("en", "25356")):
        section(f"bein.com {lang.upper()}")
        try:
            r = requests.get(URL.format(lang=lang, LANG=lang.upper(), pid=pid, d=day),
                             headers=H, timeout=T)
            print(f"status={r.status_code} bytes={len(r.text)}", flush=True)
            if r.status_code != 200:
                continue
            pages[lang] = r.text
        except Exception as exc:
            print(f"FAILED: {exc}", flush=True)
            continue

        print("\nchannel logos in document order (ids / alt / nearby name):", flush=True)
        for i, name, ids, alt, names in logo_map(pages[lang]):
            mark = "   <<< ALKASS" if "alkass" in name.lower() else ""
            print(f"  {i:3} {name:24} ids={ids} alt={alt} names={names}{mark}", flush=True)

    if "ar" in pages:
        section("raw markup around each Alkass logo (AR)")
        for m in ALKASS.finditer(pages["ar"]):
            w = pages["ar"][max(0, m.start() - 1000):m.end() + 120]
            print(f"\n---- {m.group(0)} ----", flush=True)
            print("TEXT:", clean(w)[-320:], flush=True)
            print("RAW :", w[-900:].replace("\n", " "), flush=True)

    for lang in ("en", "ar"):
        if lang not in pages:
            continue
        section(f"today's parsed schedule per channel ({lang.upper()})")
        got = parse(pages[lang])
        for n in sorted(got):
            rows = got[n]
            print(f"\n  Alkass {n}: {len(rows)} rows", flush=True)
            for s, e, t in rows[:40]:
                print(f"    {s[11:16]}-{e[11:16]}  {t[:70]}", flush=True)

    section("alkass.net — independent check")
    for url in ("https://alkass.net/", "https://alkass.net/schedule",
                "https://www.alkass.net/tv-guide"):
        try:
            r = requests.get(url, headers=H, timeout=T, allow_redirects=True)
            body = clean(r.text)
            print(f"\n{url} -> {r.status_code} {len(r.text)}b  final={r.url}", flush=True)
            print("  ", body[:400], flush=True)
            for kw in ("schedule", "جدول", "epg", "guide", "بث"):
                hits = re.findall(rf"href=['\"]([^'\"]*{kw}[^'\"]*)['\"]", r.text, re.I)[:6]
                if hits:
                    print(f"   links[{kw}]: {hits}", flush=True)
        except Exception as exc:
            print(f"{url} FAILED: {exc}", flush=True)


if __name__ == "__main__":
    main()
