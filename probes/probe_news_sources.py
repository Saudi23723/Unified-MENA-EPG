#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ask every candidate news source what it actually publishes.

A third channel was asked for: breaking news with a short explanation,
like a daily paper, hour by hour, updated by itself — Jordan, the Arab
world, America, Britain and Turkey, from strong sources, Arabic and
English mixed.

NONE OF THOSE SOURCES ARE IN THIS REPOSITORY. Every reader here is a
sport schedule; not one is a newsroom. So nothing can be written until
it is known which newsrooms answer a runner, in what shape, and how
fresh what they hand back is.

That last one decides the channel. "ساعة بساعة" is a promise about
FRESHNESS, and a feed whose newest item is two days old cannot keep it
however good the outlet is. So this prints, per source:

    the status, the size and what kind of feed it is
    how many items, and how many carry a real timestamp
    HOW OLD THE NEWEST ITEM IS          <- the one that matters
    the newest three, with their clock, their language and their summary

Every URL here is an outlet's OWN feed. No aggregator, no mirror, no
third party's dump — the rule this project has been held to all along.

It prints. It writes nothing, publishes nothing and wires nothing.
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

sys.path.insert(0, ".")

import requests

# The outlets, by the regions asked for. Each is the newsroom's own feed.
SOURCES = (
    # ── الأردن ─────────────────────────────────────────────────────
    # المملكة links this in its body; عمون answers 403 even to a browser,
    # so it is a real block on datacentre addresses and not a header.
    ("JO", "المملكة", "ar", "https://www.almamlakatv.com/rss.xml"),
    ("JO", "Jordan News", "en", "https://www.jordannews.jo/rss"),
    # ── عربي ───────────────────────────────────────────────────────
    # BOTH OF THESE ARE THE SITE'S OWN DECLARATION, read out of its head
    # rather than guessed. The guess for الجزيرة ended ...bfa02f8bd0e0 and
    # 404'd; what it actually publishes ends ...bfdff8b8cab9.
    ("AR", "الجزيرة", "ar",
     "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-9d80-"
     "a84db769f779/73d0e1b4-532f-45ef-b135-bfdff8b8cab9"),
    ("AR", "سكاي عربية", "ar", "https://www.skynewsarabia.com/rss.xml"),
    ("AR", "BBC عربي", "ar", "https://feeds.bbci.co.uk/arabic/rss.xml"),
    ("AR", "CNN عربية", "ar", "https://arabic.cnn.com/api/v1/rss/rss.xml"),
    ("AR", "France24 عربي", "ar",
     "https://www.france24.com/ar/rss"),
    # ── أمريكا ─────────────────────────────────────────────────────
    ("US", "NPR", "en", "https://feeds.npr.org/1001/rss.xml"),
    ("US", "NYT", "en",
     "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"),
    ("US", "CBS", "en", "https://www.cbsnews.com/latest/rss/main"),
    # ── بريطانيا ───────────────────────────────────────────────────
    ("GB", "BBC", "en", "https://feeds.bbci.co.uk/news/rss.xml"),
    ("GB", "Guardian", "en", "https://www.theguardian.com/international/rss"),
    ("GB", "Sky News", "en", "https://feeds.skynews.com/feeds/rss/home.xml"),
    ("GB", "Independent", "en",
     "https://www.independent.co.uk/news/uk/rss"),
    # ── تركيا ──────────────────────────────────────────────────────
    ("TR", "TRT Haber", "tr",
     "https://www.trthaber.com/xml_mobile.php?tur=xml_genel"),
    ("TR", "Anadolu", "tr", "https://www.aa.com.tr/tr/rss/default?cat=guncel"),
    ("TR", "Daily Sabah", "en", "https://www.dailysabah.com/rssFeed/homepage"),
    ("TR", "Hürriyet", "tr", "https://www.hurriyet.com.tr/rss/anasayfa"),
    ("TR", "TRT World", "en", "https://www.trtworld.com/feed/rss.xml"),
)

ARABIC = re.compile(r"[؀-ۿ]")
TAGS = re.compile(r"<[^>]+>")


def a_time(text: str):
    """Whatever instant the item carries, or None. Never a guess."""
    if not text:
        return None
    text = text.strip()
    try:
        when = parsedate_to_datetime(text)
        if when is not None:
            return when if when.tzinfo else when.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass
    try:                                        # Atom writes ISO
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def a_text(node) -> str:
    if node is None:
        return ""
    text = "".join(node.itertext())
    return re.sub(r"\s+", " ", TAGS.sub(" ", text)).strip()


def items_of(root):
    """Every entry, whether the feed is RSS or Atom."""
    found = root.findall(".//item")
    if found:
        return found, "RSS"
    atom = "{http://www.w3.org/2005/Atom}"
    found = root.findall(f".//{atom}entry")
    return found, "Atom" if found else "?"


def one(session, region, outlet, tongue, url) -> None:
    print(f"\n── {region}  {outlet}  ({tongue})")
    print(f"   {url}")
    try:
        page = session.get(url, timeout=25, headers={
            "User-Agent": "Mozilla/5.0 (compatible; UnifiedMENAEPG/1.0)"})
    except Exception as exc:                                  # noqa: BLE001
        print(f"   UNREACHABLE  {str(exc)[:100]}")
        return

    print(f"   {page.status_code}  {len(page.content) // 1024} KB  "
          f"{page.headers.get('content-type', '?')[:40]}")
    if page.status_code != 200:
        return

    try:
        root = ET.fromstring(page.content)
    except ET.ParseError as exc:
        print(f"   NOT XML  {str(exc)[:80]}")
        return

    entries, kind = items_of(root)
    atom = "{http://www.w3.org/2005/Atom}"

    dated = []
    for entry in entries:
        stamp = None
        for field in ("pubDate", "published", "updated",
                      f"{atom}published", f"{atom}updated",
                      "{http://purl.org/dc/elements/1.1/}date"):
            stamp = a_time(a_text(entry.find(field)))
            if stamp:
                break
        title = a_text(entry.find("title")) or a_text(entry.find(f"{atom}title"))
        summary = (a_text(entry.find("description"))
                   or a_text(entry.find(f"{atom}summary"))
                   or a_text(entry.find(f"{atom}content")))
        if title:
            dated.append((stamp, title, summary))

    with_time = [row for row in dated if row[0]]
    print(f"   {kind}: {len(entries)} item(s), {len(dated)} with a title, "
          f"{len(with_time)} with a real timestamp")

    if not with_time:
        print("   NO INSTANT ON ANY ITEM — cannot be placed on an hourly board")
        for stamp, title, summary in dated[:2]:
            print(f"      · {title[:70]}")
        return

    with_time.sort(key=lambda row: row[0], reverse=True)
    now = datetime.now(timezone.utc)
    age = (now - with_time[0][0]).total_seconds() / 60
    verdict = ("FRESH" if age <= 120 else
               "SLOW" if age <= 720 else "STALE — not hour by hour")
    print(f"   NEWEST IS {age:.0f} MIN OLD   {verdict}")

    for stamp, title, summary in with_time[:3]:
        script = "عربي" if ARABIC.search(title) else "latin"
        mins = (now - stamp).total_seconds() / 60
        print(f"      {stamp:%m-%d %H:%M}  ({mins:>4.0f}m, {script})  "
              f"{title[:66]}")
        print(f"          summary {len(summary):>4} chars: {summary[:78]}")


def trt_haber(session) -> None:
    """TRT Haber writes its own shape, so it is read on its own terms.

    Not RSS: <haberler><haber> with <haber_manset> for the headline,
    <haber_aciklama> for the summary and <haber_tarihi> for the time.
    Whether that time is usable is the whole question, so it is printed
    unparsed beside the clock.
    """
    url = "https://www.trthaber.com/xml_mobile.php?tur=xml_genel"
    print(f"\n── TR  TRT Haber  (tr)  — its own shape, not RSS")
    print(f"   {url}")
    try:
        page = session.get(url, timeout=25, headers={
            "User-Agent": "Mozilla/5.0 (compatible; UnifiedMENAEPG/1.0)"})
        root = ET.fromstring(page.content)
    except Exception as exc:                                  # noqa: BLE001
        print(f"   UNREACHABLE  {str(exc)[:90]}")
        return

    stories = root.findall(".//haber")
    dated = [one for one in stories if a_text(one.find("haber_tarihi"))]
    print(f"   {len(stories)} <haber>, {len(dated)} carrying <haber_tarihi>")
    if not dated:
        print("   NO DATE ON ANY STORY — cannot be placed on an hourly board")
        return
    print(f"   now is {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    for one in dated[:4]:
        raw = a_text(one.find("haber_tarihi"))
        title = a_text(one.find("haber_manset"))
        summary = a_text(one.find("haber_aciklama"))
        print(f"      date {raw!r}")
        print(f"           {title[:66]}")
        print(f"           summary {len(summary):>4} chars")


def main() -> int:
    session = requests.Session()
    print(f"asked at {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC, "
          f"{len(SOURCES)} source(s), every one an outlet's own feed\n")
    for row in SOURCES:
        one(session, *row)
    trt_haber(session)
    print("\nDone. Nothing was written; the reader is written against what "
          "this printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
