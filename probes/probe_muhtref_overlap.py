#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DOES MuhtrefSports BRING ANYTHING THE BUILD DOES NOT ALREADY HAVE?

"شوف اذا بتجيب اشي مختلف".

ROUND ONE MEASURED THE WRONG THING AND SAID SO. It counted posts whose
TEXT carried a clock, and the three channels already wired scored 0%, 5%
and 0%. A test that fails fajersport, AlwanSports and matches_today2 --
all three in production, all three producing XML every pass -- is a
broken test, not three broken channels. The reason is in this repo's own
code: update_fajer_sports_epg.py runs pytesseract over the POSTERS. The
times are pixels, not text.

What round one did establish is which candidates are alive. Kora4Live's
newest post is 21 Aug, matsh_today's /s/ page is serving 2025, c77m1
names no broadcaster in twenty posts, and all three UFC channels post
promos rather than cards -- so the fight gap tapology left is still open
and none of these closes it. One candidate survived: MuhtrefSports, fresh
to today, naming a broadcaster in 30% of posts, no clocks in text. That
is the controls' fingerprint exactly.

SO THIS ROUND ASKS THE TWO QUESTIONS THAT DECIDE IT.

1. CAN ITS POSTERS BE READ, AND BY WHAT? fajer's parse_poster is tried
   first, because reusing it would cost nothing. It looks for cyan match
   strips -- Fajer's own design -- so it is EXPECTED to fail here, and
   the useful answer is what the raw OCR shows underneath. A poster whose
   OCR comes back as legible times and team names can have a reader
   written for it. One that comes back as noise cannot, at any price.

2. IS WHAT IT CARRIES ALREADY ON THE BOARD? This is the question that
   actually decides, and the expensive answer is the one nobody checks:
   a fourth OCR channel that duplicates the first three costs build
   minutes every pass and adds not one programme. The committed XMLs are
   the truth of what is already covered, so they are read straight off
   disk and printed beside the OCR.

fajersport is measured in the same pass again, as the control -- this
time on the mechanism that actually applies, so "parse_poster found 4
cards" has a number next to it that is known to be right.

Wired to nothing. It prints; a human reads.
"""

import io
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup
from PIL import Image

import update_fajer_sports_epg as fajer

PAGES = 2
MAX_POSTERS = 4

TARGET = ("MuhtrefSports", "the one survivor of round one")
CONTROL = ("fajersport", "CONTROL - known readable")

# What the build already publishes from Telegram. If MuhtrefSports is
# carrying these same fixtures, it is a fourth cost for a third result.
COVERED_XML = [
    "fajer_sports_epg.xml",
    "alwan_sports_epg.xml",
    "thmanyah_epg.xml",
    "today_matches_epg.xml",
]

CLOCK = re.compile(r"\b([01]?\d|2[0-3])\s*[:.]\s*([0-5]\d)\b")


def posts_of(slug, pages=PAGES):
    posts, before = [], None

    for _ in range(pages):
        url = f"https://t.me/s/{slug}"

        if before:
            url += f"?before={before}"

        try:
            html = fajer.fetch(url)
        except Exception as exc:
            print(f"    fetch failed: {exc}")
            break

        soup = BeautifulSoup(html, "html.parser")
        batch = soup.select(".tgme_widget_message")

        if not batch:
            break

        posts.extend(batch)

        first = batch[0].get("data-post", "")
        before = first.rsplit("/", 1)[-1] if "/" in first else None

        if not before:
            break

    return posts


def read_poster(url):
    raw = fajer.fetch(url, binary=True)
    return Image.open(io.BytesIO(raw)).convert("RGB")


def look_at(slug, note):
    print(f"\n{'=' * 70}\n{slug}  --  {note}")

    posts = posts_of(slug)
    print(f"    posts across {PAGES} pages: {len(posts)}")

    seen = 0

    for post in posts:
        if seen >= MAX_POSTERS:
            break

        try:
            urls = fajer.image_urls(post)
        except Exception as exc:
            print(f"    image_urls failed: {exc}")
            continue

        if not urls:
            continue

        url = urls[0]
        stamp = post.select_one("time[datetime]")
        posted = (stamp.get("datetime", "") if stamp else "")[:16]

        try:
            im = read_poster(url)
        except Exception as exc:
            print(f"    poster unreadable: {exc}")
            continue

        seen += 1
        print(f"\n    --- poster {seen}  posted {posted}  {im.width}x{im.height}")

        # 1. Would fajer's reader take it as-is?
        try:
            when = datetime.now(timezone.utc)
            events = fajer.parse_poster(im, when, url)
            print(f"    fajer parse_poster -> {len(events)} match cards")

            for ev in events[:3]:
                print(f"        ch={ev.get('channel_num')} "
                      f"start={ev.get('start')} {ev.get('title')}")

        except Exception as exc:
            print(f"    fajer parse_poster raised: {type(exc).__name__}: {exc}")

        # 2. What is actually printed on it, reader or no reader.
        try:
            text = fajer.ocr(fajer.prep(im))
            flat = " ".join(text.split())
            clocks = CLOCK.findall(flat)
            print(f"    raw OCR: {len(flat)} chars, {len(clocks)} clocks")
            print(f"        {flat[:420]}")

        except Exception as exc:
            print(f"    OCR raised: {type(exc).__name__}: {exc}")

    if not seen:
        print("    NO POSTERS FOUND -- this channel posts no images")


def already_covered():
    print(f"\n{'=' * 70}\nWHAT THE BUILD ALREADY PUBLISHES (next 3 days)")

    horizon = datetime.now(timezone.utc) + timedelta(days=3)

    for name in COVERED_XML:
        try:
            root = ET.parse(name).getroot()
        except Exception as exc:
            print(f"\n  {name}: unreadable ({exc})")
            continue

        rows = []

        for prog in root.findall("programme"):
            start = prog.get("start", "")

            try:
                when = datetime.strptime(start[:14], "%Y%m%d%H%M%S")
                when = when.replace(tzinfo=timezone.utc)
            except Exception:
                continue

            if when > horizon:
                continue

            title = (prog.findtext("title") or "").strip()
            rows.append((start[:12], prog.get("channel", ""), title))

        rows.sort()
        print(f"\n  {name}: {len(rows)} programmes in window")

        for start, chan, title in rows[:12]:
            print(f"      {start} {chan:<22} {title[:60]}")


def main():
    print("ROUND TWO -- is MuhtrefSports carrying anything new?")

    for slug, note in (CONTROL, TARGET):
        try:
            look_at(slug, note)
        except Exception as exc:
            print(f"    FAILED {slug}: {type(exc).__name__}: {exc}")

    already_covered()

    print(f"\n{'=' * 70}")
    print("compare the OCR above against the programmes below it.")
    print("same fixtures = a fourth cost for a third result.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
