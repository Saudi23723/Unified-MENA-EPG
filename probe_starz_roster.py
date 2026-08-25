#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary: resolve a logo URL for every channel still without one.

Alwan and Fajer are Telegram-sourced, so the broadcaster's own channel
avatar is the honest logo. Tabii and the Shahid guide channel need a brand
mark. This finds the real URLs so they can go into fetch_logos.py, which
downloads and validates them into the repo.

Runs on GitHub Actions; deleted once the URLs are in.
"""
from __future__ import annotations

import re

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
     "Accept-Language": "ar,en;q=0.8"}
TIMEOUT = (5, 15)


def head(x):
    print(f"\n{'='*74}\n{x}\n{'='*74}", flush=True)


def get(url, **kw):
    try:
        return requests.get(url, headers=H, timeout=TIMEOUT, **kw)
    except Exception as exc:
        print(f"  FAILED {url[:64]}: {type(exc).__name__}: {str(exc)[:80]}", flush=True)
        return None


def telegram_avatar(slug):
    """The channel photo Telegram puts on its own public preview page."""
    for url in (f"https://t.me/s/{slug}", f"https://t.me/{slug}"):
        r = get(url)
        if r is None or r.status_code != 200:
            print(f"  {url}: status={r.status_code if r else 'ERR'}")
            continue
        pats = [
            r'<i class="tgme_page_photo_image"[^>]*background-image:url\(\'([^\']+)\'\)',
            r'<img class="tgme_page_photo_image"[^>]*src="([^"]+)"',
            r'<meta property="og:image" content="([^"]+)"',
            r'(https://cdn\d+\.(?:telesco\.pe|cdn-telegram\.org)/file/[^"\')\s]+)',
        ]
        for p in pats:
            m = re.search(p, r.text)
            if m:
                print(f"  {url}\n     -> {m.group(1)}")
                return m.group(1)
        print(f"  {url}: page fetched ({len(r.text)} bytes) but no avatar pattern matched")
    return None


def main():
    head("1) Telegram channel avatars (Alwan, Fajer)")
    for slug in ("AlwanSports", "fajersport"):
        print(f"\n  --- {slug} ---")
        telegram_avatar(slug)

    head("2) Tabii brand + the one Spor logo iptv-org knows")
    for url in (
        "https://cms-tabii-public-image.tabii.com/int/w300/43020.jpeg",
        "https://www.tabii.com/favicon.ico",
        "https://www.tabii.com/apple-touch-icon.png",
    ):
        r = get(url)
        if r is not None:
            print(f"  {url[:70]:72} status={r.status_code} len={len(r.content)} "
                  f"ctype={(r.headers.get('content-type') or '')[:24]}")

    head("3) Shahid brand mark")
    for url in (
        "https://shahid.mbc.net/favicon.ico",
        "https://shahid.mbc.net/apple-touch-icon.png",
        "https://static.shahid.net/prod/v1/img/shahid-logo.png",
    ):
        r = get(url)
        if r is not None:
            print(f"  {url[:70]:72} status={r.status_code} len={len(r.content)} "
                  f"ctype={(r.headers.get('content-type') or '')[:24]}")
    r = get("https://shahid.mbc.net/")
    if r is not None and r.status_code == 200:
        for p in (r'<meta property="og:image" content="([^"]+)"',
                  r'<link rel="apple-touch-icon"[^>]*href="([^"]+)"'):
            m = re.search(p, r.text)
            if m:
                print(f"  from homepage -> {m.group(1)}")

    head("4) do the iptv-org URLs we plan to use actually serve images?")
    for label, url in [
        ("RoyaTV", "https://i.imgur.com/WX80rty.png"),
        ("RoyaNews", "https://i.imgur.com/afowXIe.png"),
        ("RoyaComedy", "https://i.imgur.com/oIThcM8.png"),
        ("RoyaKitchen", "https://i.imgur.com/lWfh8pP.png"),
        ("RoyaKids", "https://i.imgur.com/acuCGF8.png"),
        ("RoyaDrama", "https://i.imgur.com/V7I0MVf.png"),
        ("JordanSport", "https://i.imgur.com/2EmrZPQ.png"),
        ("beINSportsHaber.tr", "https://i.imgur.com/QWo0x7S.jpg"),
        ("beIN3Turk", "https://static.wikia.nocookie.net/logopedia/images/5/53/BeIN_Sports_3_2017_Rectangle.png/revision/latest/scale-to-width-down/1000?cb=20251213114000"),
    ]:
        r = get(url)
        if r is not None:
            print(f"  {label:20} status={r.status_code} len={len(r.content):7} "
                  f"ctype={(r.headers.get('content-type') or '')[:22]}")


if __name__ == "__main__":
    main()
