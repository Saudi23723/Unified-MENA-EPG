#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read the newsrooms, and refuse anything that cannot be placed in time.

A third channel was asked for: breaking news with a short explanation,
like a daily paper, hour by hour, updating itself — Jordan, the Arab
world, America, Britain and Turkey, strong sources, Arabic and English
mixed, and not many pages.

EVERY SOURCE HERE WAS MEASURED ON A RUNNER BEFORE A LINE WAS WRITTEN.
Twenty-five feeds were asked what they publish and how fresh it was;
what came back decided this list, and four of the refusals turned out to
be a URL guessed rather than read — the sites were asked where their own
feeds are and answered in their own <head>:

    الجزيرة      the guess ended ...bfa02f8bd0e0 and 404'd
                 it publishes  ...bfdff8b8cab9
    سكاي عربية    /rss.xml, declared
    المملكة       /rss.xml, linked
    TRT World    /feed/rss.xml, declared

THREE ARE REALLY CLOSED and are not here: عمون, العربية and AP answer
403 to a browser user-agent as well, so it is a block on datacentre
addresses and not a header this can fix. CNN's US feed is not here
either — it answers 200 and its newest item was dated APRIL, which is
worse than a refusal because it looks alive.

Every URL is an outlet's OWN feed. No aggregator, no mirror, nobody
else's dump — the rule this repository has been held to throughout.

TWO RULES DECIDE WHAT BECOMES A ROW, and both come from measurement:

  NO INSTANT, NO ROW. Never a time inferred from the day a story was
  fetched. TRT Haber has its own shape and is read on its own terms,
  and if a story there carries no <haber_tarihi> it is dropped like any
  other.

  NOTHING FROM THE FUTURE. Jordan News dates items ahead of the clock —
  '17:00:00 GMT' and '16:30:00 GMT' at 16:23 GMT — because it schedules
  posts. That is not a broken clock to correct, it is a story that has
  not happened; it gets no row until it has.

And every instant is converted to UTC before anything is done with it.
CBS writes its own timezone and Anadolu writes +03; taking either at
face value puts a story hours out.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from epg_lib import fetch, log, norm, warn

UTC = timezone.utc
ATOM = "{http://www.w3.org/2005/Atom}"
DC = "{http://purl.org/dc/elements/1.1/}"

# The five regions, in the order a reader asked for them.
REGIONS = ("JO", "AR", "US", "GB", "TR")
REGION_AR = {
    "JO": "الأردن",
    "AR": "عربي",
    "US": "أمريكا",
    "GB": "بريطانيا",
    "TR": "تركيا",
}

# (region, outlet, feed). Every one answered 200 with real timestamps and
# a newest item under two hours old when measured.
SOURCES = (
    ("JO", "المملكة", "https://www.almamlakatv.com/rss.xml"),
    ("JO", "Jordan News", "https://www.jordannews.jo/rss"),

    ("AR", "الجزيرة",
     "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-9d80-"
     "a84db769f779/73d0e1b4-532f-45ef-b135-bfdff8b8cab9"),
    ("AR", "سكاي عربية", "https://www.skynewsarabia.com/rss.xml"),
    ("AR", "BBC عربي", "https://feeds.bbci.co.uk/arabic/rss.xml"),
    ("AR", "CNN عربية", "https://arabic.cnn.com/api/v1/rss/rss.xml"),
    ("AR", "فرانس 24", "https://www.france24.com/ar/rss"),

    ("US", "NYT", "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"),
    ("US", "CBS", "https://www.cbsnews.com/latest/rss/main"),
    ("US", "NPR", "https://feeds.npr.org/1001/rss.xml"),

    ("GB", "BBC", "https://feeds.bbci.co.uk/news/rss.xml"),
    ("GB", "Guardian", "https://www.theguardian.com/international/rss"),
    ("GB", "Independent", "https://www.independent.co.uk/news/uk/rss"),
    ("GB", "Sky News", "https://feeds.skynews.com/feeds/rss/home.xml"),

    ("TR", "الأناضول", "https://www.aa.com.tr/tr/rss/default?cat=guncel"),
    ("TR", "حرييت", "https://www.hurriyet.com.tr/rss/anasayfa"),
    ("TR", "Daily Sabah", "https://www.dailysabah.com/rssFeed/homepage"),
    ("TR", "TRT World", "https://www.trtworld.com/feed/rss.xml"),
)

# TRT Haber is not RSS at all. Its shape was printed verbatim and read
# from that: <haberler><haber> with <haber_manset> for the headline,
# <haber_aciklama> for the summary and <haber_tarihi> for the time.
TRT_HABER = ("TR", "TRT Haber",
             "https://www.trthaber.com/xml_mobile.php?tur=xml_genel")

TAGS = re.compile(r"<[^>]+>")

# A headline that is not news: a live blog that never ends, a puzzle, a
# horoscope. They crowd a board that only has room for a few rows.
NOT_NEWS = re.compile(
    r"\blive\b.*\bblog\b|\bcrossword\b|\bwordle\b|\bhoroscope\b|\bquiz\b"
    r"|\bpodcast\b|\brecipe\b|\bsudoku\b|\bcartoon\b"
    r"|minute-by-minute|as it happened"
    # A LIVE BLOG ENDING IN "– live", which is the Guardian's own naming
    # and which the first version of this missed: it required the word
    # "blog" and the title never says it. Measured on the live build —
    #
    #   England beat Ireland by six wickets: second women's cricket
    #   one-day international – live
    #
    # took one of six rows on the front page, and a rolling sports
    # commentary is not the breaking news this channel promises. Anchored
    # on the END of the title, so a story that merely contains the word
    # live — "shown live on state television" — is untouched.
    r"|[–\-—]\s*live\s*$|\blive\s+updates?\s*$"
    r"|كلمات\s*متقاطعة|الأبراج|وصفة", re.I)

# How far back a story may be and still be news. A board that says "hour
# by hour" cannot carry yesterday.
OLDEST_HOURS = 18

# A little tolerance, because clocks differ by seconds and a story
# published this minute should not be refused for being one ahead.
FUTURE_SLACK = timedelta(minutes=2)


def a_time(text: str) -> datetime | None:
    """Whatever instant the item carries, in UTC. Never a guess."""
    from email.utils import parsedate_to_datetime
    if not text:
        return None
    text = text.strip()
    try:
        when = parsedate_to_datetime(text)
        if when is not None:
            return (when if when.tzinfo else when.replace(tzinfo=UTC)
                    ).astimezone(UTC)
    except (TypeError, ValueError, IndexError):
        pass
    try:
        when = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (when if when.tzinfo else when.replace(tzinfo=UTC)).astimezone(UTC)


def a_text(node) -> str:
    if node is None:
        return ""
    joined = "".join(node.itertext())
    return norm(re.sub(r"\s+", " ", TAGS.sub(" ", joined)))


def one_sentence(summary: str, limit: int = 150) -> str:
    """The short explanation, cut at a sentence rather than mid-word."""
    said = norm(summary)
    if not said:
        return ""
    if len(said) <= limit:
        return said
    cut = said[:limit]
    for stop in (". ", "، ", "؟ ", "! ", " — ", " - "):
        at = cut.rfind(stop)
        if at > limit // 2:
            return norm(cut[:at])
    at = cut.rfind(" ")
    return norm(cut[:at] if at > limit // 2 else cut) + "…"


def a_story(title: str, summary: str, when: datetime | None,
            region: str, outlet: str, now: datetime) -> dict | None:
    """One row, or None with the reason left in the caller's counters."""
    if not title or not when:
        return None
    if when > now + FUTURE_SLACK:
        return None                      # scheduled, not published
    if when < now - timedelta(hours=OLDEST_HOURS):
        return None
    if NOT_NEWS.search(title):
        return None
    # A summary that only repeats the headline explains nothing.
    said = one_sentence(summary)
    if said and said[:40] == norm(title)[:40]:
        said = ""
    return {
        "start": when,
        "title": norm(title),
        "summary": said,
        "region": region,
        "outlet": outlet,
    }


def from_rss(body: bytes, region: str, outlet: str,
             now: datetime) -> list[dict]:
    root = ET.fromstring(body)
    items = root.findall(".//item") or root.findall(f".//{ATOM}entry")
    out = []
    for item in items:
        when = None
        for field in ("pubDate", "published", "updated",
                      f"{ATOM}published", f"{ATOM}updated", f"{DC}date"):
            when = a_time(a_text(item.find(field)))
            if when:
                break
        story = a_story(
            a_text(item.find("title")) or a_text(item.find(f"{ATOM}title")),
            (a_text(item.find("description"))
             or a_text(item.find(f"{ATOM}summary"))
             or a_text(item.find(f"{ATOM}content"))),
            when, region, outlet, now)
        if story:
            out.append(story)
    return out


def from_trt_haber(body: bytes, region: str, outlet: str,
                   now: datetime) -> list[dict]:
    """TRT Haber's own shape, read on its own terms rather than forced."""
    root = ET.fromstring(body)
    out = []
    for story in root.findall(".//haber"):
        made = a_story(a_text(story.find("haber_manset")),
                       a_text(story.find("haber_aciklama")),
                       a_time(a_text(story.find("haber_tarihi"))),
                       region, outlet, now)
        if made:
            out.append(made)
    return out


def stories(session, now: datetime | None = None) -> list[dict]:
    """Every story every newsroom has, that can be placed in time."""
    now = now or datetime.now(UTC)
    found: list[dict] = []
    reached = 0

    for region, outlet, url in SOURCES + (TRT_HABER,):
        try:
            body = fetch(session, url).content
        except Exception as exc:                              # noqa: BLE001
            warn(f"{outlet} is unreachable ({str(exc)[:70]})")
            continue
        try:
            mine = (from_trt_haber(body, region, outlet, now)
                    if outlet == "TRT Haber"
                    else from_rss(body, region, outlet, now))
        except ET.ParseError as exc:
            warn(f"{outlet} could not be read ({str(exc)[:60]})")
            continue
        reached += 1
        found += mine
        if mine:
            newest = max(one["start"] for one in mine)
            log(f"  {REGION_AR[region]:<8} {outlet:<14} {len(mine):>3} "
                f"story(ies), newest "
                f"{(now - newest).total_seconds() / 60:.0f} min old")
        else:
            log(f"  {REGION_AR[region]:<8} {outlet:<14} nothing inside "
                f"the last {OLDEST_HOURS}h")

    # One story, however many outlets carry it — matched on the headline
    # itself, because two newsrooms writing the same words is one event.
    seen, kept = set(), []
    for story in sorted(found, key=lambda one: one["start"], reverse=True):
        key = re.sub(r"[^\w؀-ۿ]", "", story["title"].lower())[:60]
        if key in seen:
            continue
        seen.add(key)
        kept.append(story)

    log(f"  news: {reached}/{len(SOURCES) + 1} source(s) answered, "
        f"{len(found)} story(ies), {len(kept)} after de-duplication")
    return kept
