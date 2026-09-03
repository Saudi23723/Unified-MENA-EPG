#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ask the sites that refused where their own feed is, instead of guessing.

The first probe asked twenty-five feeds. Fourteen answered fresh; eleven
did not, and among them is nearly all of Jordan — رؤيا 404, المملكة 404,
عمون 403, بترا HTML — plus الجزيرة, العربية, سكاي عربية and AP.

Guessing another URL for each is exactly the mistake this project keeps
paying for: a slug guessed rather than read gave a 404, and a filter
written from what a channel "should" be called matched nothing.

A site DECLARES its own feed, in its homepage head:

    <link rel="alternate" type="application/rss+xml" href="...">

So that is what is read here — the site's own declaration, followed to
whatever it points at. Nothing is invented.

Three other things are measured, each because a specific answer needs
explaining rather than assuming:

  A 403 IS OFTEN A USER-AGENT, not a closed door. Every refusal is asked
  again as a browser, and whether that changes the answer is a fact.

  TRT HABER ANSWERED 200 WITH XML AND ZERO <item>. Its shape is its own,
  so the first part of it is printed verbatim to be read.

  JORDAN NEWS DATES ITEMS IN THE FUTURE (-40 minutes old). Either its
  clock is offset or it writes local time as if it were UTC. The raw
  pubDate string decides which, so it is printed unparsed.

It prints. It writes nothing and wires nothing.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

import requests

BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                  " (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ar,en;q=0.9",
}

# The homepages of everything that refused. Reading a site's own head is
# the only honest way to learn where it publishes.
HOMES = (
    ("JO", "رؤيا", "https://royanews.tv/"),
    ("JO", "المملكة", "https://www.almamlakatv.com/"),
    ("JO", "عمون", "https://www.ammonnews.net/"),
    ("JO", "بترا", "https://petra.gov.jo/"),
    ("JO", "الغد", "https://alghad.com/"),
    ("JO", "خبرني", "https://www.khaberni.com/"),
    ("AR", "الجزيرة", "https://www.aljazeera.net/"),
    ("AR", "العربية", "https://www.alarabiya.net/"),
    ("AR", "سكاي عربية", "https://www.skynewsarabia.com/"),
    ("AR", "الشرق الأوسط", "https://aawsat.com/"),
    ("US", "AP", "https://apnews.com/"),
    ("TR", "TRT World", "https://www.trtworld.com/"),
)

# The ones that refused a plain request, asked again as a browser.
REFUSED = (
    ("JO", "عمون", "https://www.ammonnews.net/rss"),
    ("AR", "العربية", "https://www.alarabiya.net/.mrss/ar.xml"),
    ("US", "AP", "https://apnews.com/index.rss"),
    ("AR", "الجزيرة", "https://www.aljazeera.net/xml/rss/all.xml"),
    ("JO", "رؤيا", "https://royanews.tv/rss/latest_news"),
)

A_DECLARED_FEED = re.compile(
    r"<link[^>]+?(?:type=[\"']application/(?:rss|atom)\+xml[\"'][^>]*?|)"
    r"href=[\"']([^\"']+)[\"'][^>]*>", re.I)
A_FEED_LINK = re.compile(
    r"<link\b[^>]*type=[\"']application/(?:rss|atom)\+xml[\"'][^>]*>", re.I)
AN_HREF = re.compile(r"href=[\"']([^\"']+)[\"']", re.I)
A_TITLE_ATTR = re.compile(r"title=[\"']([^\"']*)[\"']", re.I)


def declared_feeds(session, region, outlet, home) -> None:
    print(f"\n── {region}  {outlet}")
    print(f"   {home}")
    try:
        page = session.get(home, timeout=25, headers=BROWSER)
    except Exception as exc:                                  # noqa: BLE001
        print(f"   UNREACHABLE  {str(exc)[:90]}")
        return
    print(f"   {page.status_code}  {len(page.content) // 1024} KB")
    if page.status_code != 200:
        return

    html = page.text
    tags = A_FEED_LINK.findall(html)
    if not tags:
        print("   the page declares NO rss/atom link in its head")
        # Some sites only ever link a feed in the body.
        loose = sorted(set(re.findall(
            r"[\"'](https?://[^\"']*?(?:/rss[^\"']*|/feed/?|\.xml)[^\"']*)[\"']",
            html, re.I)))[:8]
        for one in loose:
            print(f"      body mentions: {one[:110]}")
        return

    for tag in tags[:8]:
        href = AN_HREF.search(tag)
        name = A_TITLE_ATTR.search(tag)
        print(f"      DECLARES: {href.group(1) if href else '?'}"
              f"{'   (' + name.group(1) + ')' if name else ''}")


def as_a_browser(session, region, outlet, url) -> None:
    print(f"\n── {region}  {outlet}  (refused before; asked as a browser)")
    print(f"   {url}")
    try:
        page = session.get(url, timeout=25, headers=BROWSER)
    except Exception as exc:                                  # noqa: BLE001
        print(f"   UNREACHABLE  {str(exc)[:90]}")
        return
    kind = page.headers.get("content-type", "?")[:36]
    print(f"   {page.status_code}  {len(page.content) // 1024} KB  {kind}")
    if page.status_code == 200 and "xml" in kind.lower():
        items = len(re.findall(r"<item\b", page.text, re.I))
        print(f"   IT OPENS AS A BROWSER — {items} <item>(s)")
        for title in re.findall(r"<title>(.*?)</title>", page.text,
                                re.S)[1:4]:
            plain = re.sub(r"<[^>]+>|\s+", " ", title).strip()
            print(f"      · {plain[:74]}")


def trt_haber_shape(session) -> None:
    url = "https://www.trthaber.com/xml_mobile.php?tur=xml_genel"
    print(f"\n── TR  TRT Haber — 200 and XML, but zero <item>. Its shape:")
    print(f"   {url}")
    try:
        page = session.get(url, timeout=25, headers=BROWSER)
    except Exception as exc:                                  # noqa: BLE001
        print(f"   UNREACHABLE  {str(exc)[:90]}")
        return
    text = page.text
    print(f"   {page.status_code}  {len(page.content) // 1024} KB")
    print("   ── first 900 characters, verbatim ──")
    print("   " + text[:900].replace("\n", "\n   "))
    names = sorted(set(re.findall(r"<([A-Za-z_][\w:.-]*)[\s>]", text)))
    print(f"\n   element names present: {', '.join(names[:30])}")


def jordan_news_clock(session) -> None:
    url = "https://www.jordannews.jo/rss"
    print(f"\n── JO  Jordan News — dates items 40 minutes IN THE FUTURE.")
    print(f"   {url}")
    try:
        page = session.get(url, timeout=25, headers=BROWSER)
    except Exception as exc:                                  # noqa: BLE001
        print(f"   UNREACHABLE  {str(exc)[:90]}")
        return
    stamps = re.findall(r"<pubDate>(.*?)</pubDate>", page.text, re.S)[:5]
    print(f"   now is {datetime.now(timezone.utc):%a, %d %b %Y %H:%M:%S} UTC")
    print("   its five newest pubDate strings, unparsed:")
    for stamp in stamps:
        print(f"      {stamp.strip()!r}")
    print("   (a '+0000' on a local clock is a source writing Amman time as"
          " UTC — three hours wrong, and it would put every Jordanian row on"
          " the board in the wrong hour)")


def main() -> int:
    session = requests.Session()
    print(f"asked at {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC\n")
    print("=" * 68)
    print("WHERE EACH SITE SAYS ITS OWN FEED IS")
    print("=" * 68)
    for row in HOMES:
        declared_feeds(session, *row)

    print("\n" + "=" * 68)
    print("A 403 MAY ONLY BE A USER-AGENT")
    print("=" * 68)
    for row in REFUSED:
        as_a_browser(session, *row)

    print("\n" + "=" * 68)
    print("TWO SHAPES TO READ RATHER THAN ASSUME")
    print("=" * 68)
    trt_haber_shape(session)
    jordan_news_clock(session)

    print("\nDone. Nothing was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
