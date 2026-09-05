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

TWO ARE REALLY CLOSED and are not here: عمون and AP answer
403 to a browser user-agent as well, so it is a block on datacentre
addresses and not a header this can fix. CNN's US feed is not here
either — it answers 200 and its newest item was dated APRIL, which is
worse than a refusal because it looks alive. العربية is the third
closed one, and it is read anyway — see the exception below.

Every URL is an outlet's OWN feed. No aggregator, no mirror, nobody
else's dump — the rule this repository has been held to throughout.

THE ONE EXCEPTION IS العربية, and it is here because its own site
closes every door to a runner — 403 on its feeds, its homepage, its
sitemap, measured before this line was written — while the news feed
restricted to its own domain carries its headlines as its newsroom
wrote them, with the newsroom's name appended for the reader to take
off. It is a mirror of one newsroom and nothing else, and the day
العربية opens its own feed again this line is deleted, not widened.

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
    # AL ARABIYA'S OWN SITE answers 403 to every URL a runner can send
    # — its feeds, its homepage, its sitemap alike — measured before
    # this line was written. The one door it leaves open is the news
    # feed restricted to its own domain, which carries its headlines
    # as it wrote them and is the closest thing to the newsroom's own
    # feed that can be read from here. Every headline arrives with the
    # newsroom's name appended — "… - العربية" — and a_story takes
    # that label off, because it is the feed's, not the headline's.
    ("AR", "العربية",
     "https://news.google.com/rss/search?q=site:alarabiya.net%20when:2d"
     "&hl=ar&gl=SA&ceid=SA:ar"),
    # AL JADEED's own feed, the third newsroom asked for by name:
    # "Add Breaking news from ALJAZEERA ARABIC, AL ARABIYA, ALJADEED".
    # Al Jazeera is above; this one answered with 20 items, the newest
    # eleven minutes old when measured.
    ("AR", "الجديد", "https://www.aljadeed.tv/Rss/NewsHighlights/ar"),
    # سكاي عربية answered 404 on the last two passes and is out until
    # it answers again. الشرق الأوسط replaces it: 300 items, newest
    # six minutes old when measured.
    ("AR", "الشرق الأوسط", "https://aawsat.com/feed"),
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

    # TURKEY, IN ARABIC. "المصادر باللغة التركية شيلها ... بس خلي كل
    # الأخبار التركية و الشرق الأوسط بالعربي" — so الأناضول's Turkish
    # feed, حرييت and TRT Haber are gone, and the same newsrooms are read
    # in Arabic instead. Measured before the swap, not after:
    #
    #   TRT عربي        200 · 100 items · newest 34 min · 41 name Turkey
    #   الأناضول عربي    200 ·  30 items · newest 25 min
    #
    # TRT's Arabic service is the same broadcaster whose Turkish feed was
    # dropped, so nothing is lost but the language.
    ("TR", "TRT عربي", "https://www.trtarabi.com/feed/rss.xml"),
    ("TR", "الأناضول", "https://www.aa.com.tr/ar/rss/default?cat=guncel"),
)

# TRT Haber is gone with the rest of the Turkish-language sources, and
# with it the only reader here that was not RSS. Its shape was measured
# and read correctly; it is dropped for its language, not its markup.

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
    # A feed that aggregates a newsroom appends the newsroom's own name
    # to every headline — "… للسعادة - العربية" — and that name is the
    # feed's label, not the headline the newsroom wrote. It comes off
    # the END of the title, where the feed puts it, and only when it
    # matches the outlet the feed was asked for: a dash in a headline's
    # own words is a headline, and stays.
    if " - " in title:
        head, _, tail = title.rpartition(" - ")
        if head and norm(tail).casefold() == outlet.casefold():
            title = head
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


def stories(session, now: datetime | None = None) -> list[dict]:
    """Every story every newsroom has, that can be placed in time."""
    now = now or datetime.now(UTC)
    found: list[dict] = []
    reached = 0

    for region, outlet, url in SOURCES:
        try:
            body = fetch(session, url).content
        except Exception as exc:                              # noqa: BLE001
            warn(f"{outlet} is unreachable ({str(exc)[:70]})")
            continue
        try:
            mine = from_rss(body, region, outlet, now)
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

# SPORT IS NEWS, BUT NOT THE NEWS THIS CHANNEL LEADS WITH.
#
# "في أشياء هبله محطوطة" — and there were. The board led with "Spurs
# omit Richarlison from Premier League squad" and "أندية كروية أنفقت
# أكبر مبالغ" while a strike on Gaza sat below them, because the only
# thing ordering the page was the clock and a transfer story is posted
# as often as a war.
#
# Measured on the sources themselves: the three newest items from
# الشرق الأوسط were Hamilton at Monza, Germany's Olympic bid and a Hilal
# signing; the three newest from الجزيرة were all sport too.
#
# It is NOT thrown away — "خلي اخبار الرياضة بس لحال اخر صفحة". It goes
# to the last page, on its own, and the pages before it are the news.
A_SPORT = re.compile(
    r"\b(?:football|soccer|premier\s*league|la\s*liga|serie\s*a|"
    r"bundesliga|champions\s*league|transfer|striker|midfielder|goalkeeper|"
    r"fixture|kick-?off|f1|formula\s*1|grand\s*prix|nba|nfl|mlb|ufc|"
    r"boxing|cricket|tennis|golf|olympic|athletics|wicket|touchdown|"
    r"manager|coach|squad|dressing\s*room)\b"
    r"|كرة\s*القدم|الدوري|دوري\s|مباراة|مباريات|المنتخب|النادي|نادي\s|"
    r"لاعب|اللاعب|صفقة|انتقالات|هدف|أهداف|تشكيلة|المدرب|بطولة\s*العالم|"
    r"الفورمولا|أولمبي|أولمبياد|ملاكمة|تنس|كأس\s"
    # "هاميلتون يخوض جائزة إيطاليا الكبرى" names no sport at all —
    # a grand prix in Arabic is "الجائزة الكبرى", and a reader knows
    # what it is from the driver. So the phrase itself is a sport.
    # "هاميلتون يخوض جائزة إيطاليا الكبرى" names no sport at all — a
    # grand prix in Arabic is "جائزة <country> الكبرى", with the
    # country in the middle, so the two words are not adjacent.
    #
    # And a bare "سباق" is NOT a sport: "سباق التسلح النووي" is an
    # arms race, and it was matched by the first version of this.
    # Only the phrases that can be nothing else are here.
    r"|جائزة\s+\S+\s+الكبرى|سباق\s+الجائزة|سائق\s+(?:فيراري|مرسيدس)"
    r"|الدوري\s*الإنجليزي|الدوري\s*الإسباني|دوري\s*أبطال", re.I)


def is_sport(story: dict) -> bool:
    """Whether a story belongs on the sport page rather than the news."""
    return bool(A_SPORT.search(story["title"])
                or A_SPORT.search(story.get("summary") or ""))

