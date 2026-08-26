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

    # --- Roya (JO) ---------------------------------------------------------
    "roya_tv": ["https://i.imgur.com/WX80rty.png"],
    "roya_news": ["https://i.imgur.com/afowXIe.png"],
    "roya_comedy": ["https://i.imgur.com/oIThcM8.png"],
    "roya_kitchen": ["https://i.imgur.com/lWfh8pP.png"],
    "roya_kids": ["https://i.imgur.com/acuCGF8.png"],

    # --- Jordan Sport (JO) -------------------------------------------------
    "jordan_sport": ["https://i.imgur.com/2EmrZPQ.png"],

    # --- beIN SPORTS HABER (TR) --------------------------------------------
    # The rest of the Türkiye roster reuses the beIN marks already fetched
    # for Qatar - beIN SPORTS 1 is beIN SPORTS 1 either side of the border.
    "bein_haber": ["https://i.imgur.com/QWo0x7S.jpg"],

    # --- tabii (TR) --------------------------------------------------------
    # Deliberately not listed. The eleven tabii marks — tabii.png for the
    # linear channel and tabii1..tabii10.png for the PPV numbers — are held
    # in this repository rather than fetched, because no host publishes a
    # numbered set: sporekrani serves them at 109x19, too small to show,
    # and TRT publishes only the unnumbered wordmark. This script writes
    # only the keys it holds, so leaving tabii out is what stops a future
    # run from overwriting all eleven with one unnumbered picture.

    # --- Al Jazeera Arabic (QA) ---------------------------------------------
    # The broadcaster's own site first, then Wikimedia Commons, which serves
    # a rendered PNG of the mark and accepts a browser User-Agent.
    "aljadeed": [
        # The channel's own mark, then its touch icon as the square fallback.
        "https://www.aljadeed.tv/Images/logo.png",
        "https://www.aljadeed.tv/apple-touch-icon.png",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8e/Al_Jadeed_TV_logo.svg/512px-Al_Jadeed_TV_logo.svg.png",
        "https://upload.wikimedia.org/wikipedia/en/thumb/4/4f/Al_Jadeed_logo.png/512px-Al_Jadeed_logo.png",
        "https://www.aljadeed.tv/favicon.ico",
    ],

    "aljazeera": [
        # 932x522, the full mark; the touch icon is the square fallback.
        "https://www.aljazeera.net/images/logo_aja_social.png",
        "https://www.aljazeera.net/apple-touch-icon.png",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f2/Aljazeera.svg/512px-Aljazeera.svg.png",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e2/Aljazeera_logo.svg/512px-Aljazeera_logo.svg.png",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0b/Aljazeera_arabic.svg/512px-Aljazeera_arabic.svg.png",
        "https://www.aljazeera.net/favicon.ico",
    ],

    # --- Shahid (guide channel) --------------------------------------------
    "shahid": [
        "https://shahid.mbc.net/apple-touch-icon.png",
        "https://shahid.mbc.net/staticFiles/production/mbc-shahid-black.jpg",
    ],


    # Alwan is deliberately absent: logos/alwan.png is the mark the repo
    # owner supplied directly, so this script must not overwrite it. It only
    # ever writes the keys listed here, so leaving it out is what keeps it.

    # --- Fajer -------------------------------------------------------------
    # The guide is built from Fajer's public Telegram channel, so the
    # channel's own avatar is the broadcaster's own mark. This is a signed
    # CDN URL and can expire; re-run this script if it stops resolving.
    "fajer": ["https://cdn4.telesco.pe/file/QUybT7e4plwaf01ipo_9G4j7wpncuuj5lUHaAsE5eIEPPMdFk4wfrDAnyaXQaVWDRkYHawit-XJnK5Hb_oMMDAHvIiM-uz3WCQYqupkydLFbtkX1vJaCFmGg9iyOzkdFC0HXinHQHNY7Vr5ItLu0jqkGTWMXTIczbMkbbUGFV2fPNDdNjnEXbnPX4gllUIZ8aiW0UyDw3tSeK2uZ1_6yPHmXVJg6odS7f-Z8QrW5w8S0bTLf-MzrDgMuDJQGU6o6HVtOACAgDCu8-kcXmEmwtI0PEq-qMvYOL6d_Xa0hhjdtMdT2L922zwHaEXAgUAJFwOjo2a18qKVH4ywXjIZfUg.jpg"],

    # --- Alkass (QA) -------------------------------------------------------
    # From the iptv-org logo database. Only channels 1-8 are here because
    # only those have a schedule in any reachable source.
    "alkass1": ["https://i.imgur.com/10mmlha.png"],
    "alkass2": ["https://i.imgur.com/8w61kFX.png"],
    "alkass3": ["https://i.imgur.com/d57BdFh.png"],
    "alkass4": ["https://i.imgur.com/iDL65Wu.png"],
    "alkass5": ["https://i.imgur.com/6RGNGsM.png"],
    "alkass6": ["https://i.imgur.com/CrPSPSC.png"],
    "alkass7": ["https://i.imgur.com/3eyHP3S.png"],
    "alkass8": ["https://i.imgur.com/ADQkn9l.png"],

    # --- beIN SPORTS Qatar / MENA ------------------------------------------
    # URLs come from the iptv-org logo database, matched on the same channel
    # ids this guide emits. Where iptv-org carries no separate mark for a
    # channel (XTRA 3-9, AFC 4-6, SPORTS 9) the logo of its own brand is
    # reused rather than leaving those channels blank in TiviMate.
    "bein_4k": [
        "https://i.imgur.com/TTxh9tZ.png",
    ],
    "bein_brand": [
        "https://i.imgur.com/RLrMBlm.png",
    ],
    "bein_1": [
        "https://i.imgur.com/Vtk2cGI.png",
    ],
    "bein_2": [
        "https://i.imgur.com/vUJZSvs.png",
    ],
    "bein_3": [
        "https://i.imgur.com/UYSMao3.png",
    ],
    "bein_4": [
        "https://i.imgur.com/vwAgJNi.png",
    ],
    "bein_4khdr": [
        "https://assets.bein.com/mena/sites/3/2026/05/4K-HDR-200x200-1.png",
    ],
    "bein_5": [
        "https://i.imgur.com/2Rha5aY.png",
    ],
    "bein_6": [
        "https://i.imgur.com/0wBdLYb.png",
    ],
    "bein_7": [
        "https://i.imgur.com/iODFwZi.png",
    ],
    "bein_8": [
        "https://i.imgur.com/CaFEyVn.png",
    ],
    "bein_9": [  # same-brand reuse
        "https://i.imgur.com/RLrMBlm.png",
    ],
    "bein_afc": [
        "https://i.imgur.com/HOj98bH.png",
    ],
    "bein_afc1": [
        "https://i.imgur.com/nk3JCpg.png",
    ],
    "bein_afc2": [
        "https://i.imgur.com/WITLbxq.png",
    ],
    "bein_afc3": [
        "https://i.imgur.com/ruRe9oj.png",
    ],
    "bein_afc4": [  # same-brand reuse
        "https://i.imgur.com/HOj98bH.png",
    ],
    "bein_afc5": [  # same-brand reuse
        "https://i.imgur.com/HOj98bH.png",
    ],
    "bein_afc6": [  # same-brand reuse
        "https://i.imgur.com/HOj98bH.png",
    ],
    "bein_en1": [
        "https://i.imgur.com/uqVwDrB.png",
    ],
    "bein_en2": [
        "https://i.imgur.com/dWNbCyx.png",
    ],
    "bein_fr1": [
        "https://i.imgur.com/tXqMkzA.png",
    ],
    "bein_fr2": [
        "https://i.imgur.com/EG48QI7.png",
    ],
    "bein_max1": [
        "https://i.imgur.com/FjWQjdy.png",
    ],
    "bein_max2": [
        "https://i.imgur.com/5dBc5rn.png",
    ],
    "bein_max3": [
        "https://i.imgur.com/ThcM2LE.png",
    ],
    "bein_max4": [
        "https://i.imgur.com/j7osMfM.png",
    ],
    "bein_max5": [
        "https://i.imgur.com/L6TvXAi.png",
    ],
    "bein_max6": [
        "https://i.imgur.com/GHZHRPF.png",
    ],
    "bein_nba": [
        "https://i.imgur.com/QmSc6kh.png",
    ],
    "bein_news": [
        "https://i.imgur.com/ZNjQzR5.png",
    ],
    "bein_xtra1": [
        "https://i.imgur.com/O9lTxQA.png",
    ],
    "bein_xtra2": [
        "https://i.imgur.com/08Y2CW1.png",
    ],
    "bein_xtra3": [  # same-brand reuse
        "https://i.imgur.com/O9lTxQA.png",
    ],
    "bein_xtra4": [  # same-brand reuse
        "https://i.imgur.com/O9lTxQA.png",
    ],
    "bein_xtra5": [  # same-brand reuse
        "https://i.imgur.com/O9lTxQA.png",
    ],
    "bein_xtra6": [  # same-brand reuse
        "https://i.imgur.com/O9lTxQA.png",
    ],
    "bein_xtra7": [  # same-brand reuse
        "https://i.imgur.com/O9lTxQA.png",
    ],
    "bein_xtra8": [  # same-brand reuse
        "https://i.imgur.com/O9lTxQA.png",
    ],
    "bein_xtra9": [  # same-brand reuse
        "https://i.imgur.com/O9lTxQA.png",
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

    # Several channels legitimately share one source image (all Thmanyah
    # channels use the same brand mark). Downloading it once per channel
    # got the 4th request rejected with HTTP 429 by Wikimedia, so cache
    # every URL — success or failure — and fetch each one at most once.
    cache: dict[str, Image.Image | None] = {}

    for key, urls in CANDIDATES.items():
        print(f"\n=== {key} ===")
        winner = None
        for url in urls:
            if url in cache:
                im = cache[url]
                print(f"  reuse {url} -> {'OK (cached)' if im else 'FAILED earlier'}")
            else:
                print(f"  try {url}")
                im = try_download(url)
                cache[url] = im
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
