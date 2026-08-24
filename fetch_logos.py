#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
One-shot helper: download channel logos and store them INSIDE this repository.

Why store them here instead of hot-linking a third-party image host?

Hot-linked logos (imgur, ibb, wikimedia, broadcaster CDNs) are exactly why
the logos kept disappearing in TiviMate: those hosts rate-limit, block
hot-linking, require a browser User-Agent, or simply delete the image. A
logo served from this repository's own raw.githubusercontent.com URL has
none of those problems - it is a plain static PNG, permanent, and under
this project's control.

Run it once (or again whenever a logo needs refreshing); it writes
logos/<key>.png and prints exactly which source won for each channel.
Every candidate is validated as a real, non-trivial image before being
accepted, so a 404 HTML error page can never be committed as a "logo".
"""

from __future__ import annotations

import io
import os
import sys

import requests
from PIL import Image

OUT_DIR = "logos"

HEADERS = {
    # Some image hosts (Wikimedia in particular) reject requests that do not
    # look like a browser.
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
}

# Candidates are tried in order; the first one that downloads AND validates
# as a real image wins. Sources come from the iptv-org logo database
# (github.com/iptv-org/database, data/logos.csv) unless noted.
CANDIDATES: dict[str, list[str]] = {
    # --- Thmanyah (SA) -----------------------------------------------------
    # iptv-org maps all three Thmanyah channels to the same brand logo.
    "thmanyah1": [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e9/Thmanyah_Logo.svg/500px-Thmanyah_Logo.svg.png",
    ],
    "thmanyah2": [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e9/Thmanyah_Logo.svg/500px-Thmanyah_Logo.svg.png",
    ],
    "thmanyah3": [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e9/Thmanyah_Logo.svg/500px-Thmanyah_Logo.svg.png",
    ],
    "thmanyah_guide": [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e9/Thmanyah_Logo.svg/500px-Thmanyah_Logo.svg.png",
    ],

    # --- ON Sport / OnTime Sports (EG) -------------------------------------
    "onsport1": [
        "https://i.imgur.com/NIMiorz.png",
        "https://i.ibb.co/yBgDwhKp/On-Sport-1.png",
    ],
    "onsport2": [
        "https://i.imgur.com/700xW20.png",
        "https://i.ibb.co/bMvxMxTd/on-sport-2.png",
    ],
    # iptv-org has no separate MAX/PLUS logo. They are the same broadcaster
    # brand, so the main ON Sport mark is used rather than inventing one or
    # leaving these two channels with no logo at all.
    "onsportmax": [
        "https://i.imgur.com/ISOQdOJ.png",
        "https://i.imgur.com/NIMiorz.png",
    ],
    "onsportplus": [
        "https://i.imgur.com/NIMiorz.png",
    ],
}

MIN_BYTES = 500
MIN_SIDE = 32
MAX_SIDE = 512


def try_download(url: str) -> Image.Image | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
    except Exception as exc:
        print(f"      FAIL  network: {exc}")
        return None

    if r.status_code != 200:
        print(f"      FAIL  HTTP {r.status_code}")
        return None

    if len(r.content) < MIN_BYTES:
        print(f"      FAIL  too small ({len(r.content)} bytes) - probably an error page")
        return None

    try:
        im = Image.open(io.BytesIO(r.content))
        im.load()
    except Exception as exc:
        print(f"      FAIL  not a valid image: {exc}")
        return None

    if im.width < MIN_SIDE or im.height < MIN_SIDE:
        print(f"      FAIL  image too small: {im.width}x{im.height}")
        return None

    print(f"      OK    {im.format} {im.width}x{im.height} ({len(r.content)} bytes)")
    return im


def normalise(im: Image.Image) -> Image.Image:
    """RGBA PNG, capped size - keeps the repo small and TiviMate happy."""
    im = im.convert("RGBA")
    if max(im.width, im.height) > MAX_SIDE:
        im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    return im


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)

    ok, failed = [], []

    for key, urls in CANDIDATES.items():
        print(f"\n=== {key} ===")
        winner = None
        for url in urls:
            print(f"  try {url}")
            im = try_download(url)
            if im is not None:
                winner = (im, url)
                break

        if winner is None:
            print(f"  >>> NO WORKING SOURCE for {key}")
            failed.append(key)
            continue

        im, url = winner
        path = os.path.join(OUT_DIR, f"{key}.png")
        normalise(im).save(path, "PNG", optimize=True)
        print(f"  >>> saved {path} (from {url})")
        ok.append(key)

    print("\n" + "=" * 60)
    print(f"LOGOS OK      ({len(ok)}): {', '.join(ok) if ok else '-'}")
    print(f"LOGOS FAILED  ({len(failed)}): {', '.join(failed) if failed else '-'}")
    print("=" * 60)

    # A partial result is still useful, so only fail hard if nothing worked.
    return 1 if not ok else 0


if __name__ == "__main__":
    sys.exit(main())
