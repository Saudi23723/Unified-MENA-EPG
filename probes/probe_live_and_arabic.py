#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Two questions, both about believing a source rather than guessing it.

ONE — WHICH SKY PROGRAMME IS THE LIVE ONE.

Reported: the board writes a UFC row on TODAY, and today's is not the
live card — Saturday's is. Sky marks a live broadcast by prefixing the
title with "Live:", and a_programme() strips that prefix before the row
is built, so the signal is thrown away and a REPEAT of last week's card
reads exactly like tonight's.

That is a guess until the titles are printed. So every fight programme
on every Sky fight channel is printed RAW, with its prefix intact and
its channel and clock beside it. If the live airings carry "Live:" and
the repeats do not, the rule writes itself.

TWO — TURKEY AND THE MIDDLE EAST, IN ARABIC.

Asked for outright: drop the Turkish-language sources, keep the news.
So the Arabic newsrooms that cover Turkey are asked whether they answer
and how fresh they are — TRT's own Arabic service first, since it is
the same broadcaster whose Turkish feed is being dropped.

It prints. It writes nothing.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

sys.path.insert(0, ".")

import requests

import sky_epg

UTC = timezone.utc
BROWSER = {"User-Agent": "Mozilla/5.0 (compatible; UnifiedMENAEPG/1.0)"}

# Arabic newsrooms that cover Turkey and the region. Every one is an
# outlet's own feed; whether each answers is the point of asking.
ARABIC_FOR_TURKEY = (
    ("TRT عربي", "https://www.trtarabi.com/rss"),
    ("TRT عربي (feed)", "https://www.trtarabi.com/feed/rss.xml"),
    ("الأناضول عربي", "https://www.aa.com.tr/ar/rss/default?cat=guncel"),
    ("الجزيرة", "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-"
                "9d80-a84db769f779/73d0e1b4-532f-45ef-b135-bfdff8b8cab9"),
    ("سكاي عربية", "https://www.skynewsarabia.com/rss.xml"),
    ("الشرق الأوسط", "https://aawsat.com/feed"),
    ("العربي الجديد", "https://www.alaraby.co.uk/rss"),
    ("عربي21", "https://arabi21.com/rss"),
)

TAGS = re.compile(r"<[^>]+>")


def plain(node) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", TAGS.sub(" ", "".join(node.itertext()))).strip()


def sky_titles(session) -> None:
    print("=" * 72)
    print("SKY'S FIGHT PROGRAMMES, RAW — is 'Live:' what marks the live one?")
    print("=" * 72)
    on_air = sky_epg.channels(session)
    if not on_air:
        print("  Sky's channel list is unreachable")
        return

    days = [(datetime.now(UTC) + timedelta(days=n)).strftime("%Y%m%d")
            for n in range(6)]
    rows = []
    for sid, channel in on_air:
        for day in days:
            try:
                page = json.loads(sky_epg.fetch(
                    session, sky_epg.SCHEDULE.format(day=day, sid=sid)).text)
            except Exception:                                 # noqa: BLE001
                continue
            for block in page.get("schedule") or []:
                for event in block.get("events") or []:
                    raw = (event.get("t") or "").strip()
                    if not sky_epg.A_FIGHT.search(raw):
                        continue
                    try:
                        when = datetime.fromtimestamp(int(event["st"]), UTC)
                    except (KeyError, TypeError, ValueError):
                        continue
                    rows.append((when, channel, raw,
                                 (event.get("sy") or "")[:70]))

    rows.sort()
    live = [r for r in rows if r[2].lower().startswith("live")]
    print(f"\n  {len(rows)} fight programme(s); {len(live)} begin with 'Live'")
    print(f"  {'when':<17}{'channel':<24}title")
    for when, channel, raw, _ in rows:
        mark = "LIVE" if raw.lower().startswith("live") else "    "
        print(f"  {mark} {when:%m-%d %H:%M}  {channel:<22}{raw[:58]}")

    print("\n  the ones that do NOT say Live, with Sky's own synopsis:")
    for when, channel, raw, why in rows:
        if not raw.lower().startswith("live"):
            print(f"     {when:%m-%d %H:%M} {channel:<20} {raw[:44]}")
            print(f"        {why}")


def arabic_sources(session) -> None:
    print("\n" + "=" * 72)
    print("ARABIC NEWSROOMS THAT COVER TURKEY AND THE REGION")
    print("=" * 72)
    now = datetime.now(UTC)
    for name, url in ARABIC_FOR_TURKEY:
        print(f"\n── {name}\n   {url}")
        try:
            page = session.get(url, timeout=25, headers=BROWSER)
        except Exception as exc:                              # noqa: BLE001
            print(f"   UNREACHABLE {str(exc)[:80]}")
            continue
        print(f"   {page.status_code}  {len(page.content) // 1024} KB")
        if page.status_code != 200:
            continue
        try:
            root = ET.fromstring(page.content)
        except ET.ParseError as exc:
            print(f"   NOT XML {str(exc)[:60]}")
            continue
        items = root.findall(".//item")
        dated = []
        for item in items:
            when = None
            for field in ("pubDate", "published", "updated"):
                text = plain(item.find(field))
                if not text:
                    continue
                try:
                    when = parsedate_to_datetime(text)
                except (TypeError, ValueError):
                    try:
                        when = datetime.fromisoformat(
                            text.replace("Z", "+00:00"))
                    except ValueError:
                        when = None
                if when:
                    break
            title = plain(item.find("title"))
            if title and when:
                dated.append(((when if when.tzinfo else
                               when.replace(tzinfo=UTC)).astimezone(UTC),
                              title, plain(item.find("description"))))
        print(f"   {len(items)} item(s), {len(dated)} with a real timestamp")
        if not dated:
            continue
        dated.sort(reverse=True)
        age = (now - dated[0][0]).total_seconds() / 60
        print(f"   NEWEST IS {age:.0f} MIN OLD "
              f"{'FRESH' if age <= 180 else 'SLOW' if age <= 720 else 'STALE'}")
        turkey = [row for row in dated
                  if re.search(r"ترك|أنقرة|إسطنبول|أردوغان", row[1])]
        print(f"   of them, naming Turkey: {len(turkey)}")
        for when, title, summary in dated[:3]:
            print(f"      {when:%m-%d %H:%M}  {title[:62]}")
            print(f"          {summary[:78]}")


def main() -> int:
    session = requests.Session()
    print(f"asked at {datetime.now(UTC):%Y-%m-%d %H:%M} UTC\n")
    sky_titles(session)
    arabic_sources(session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
