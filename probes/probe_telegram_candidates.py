#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WHICH OPEN TELEGRAM CHANNEL IS WORTH READING — asked, not guessed.

"لاقي قنوات تيليجرام فاتحه ممكن تفيدنا".

Telegram is already a first-class source here. Three public channels are
read today, each through the same door -- t.me/s/<slug>, the preview view
a channel gets only when it is PUBLIC:

    t.me/s/fajersport      update_fajer_sports_epg.py
    t.me/s/AlwanSports     update_alwan_epg.py
    t.me/s/matches_today2  update_thmanyah_epg.py

So the question is NOT whether Telegram can be read. It is whether a
FOURTH channel carries something those three do not, and whether its
posts clear the bar every source here is held to: an exact instant, and
a named broadcaster. A post that says "الليلة قمة نارية" has neither.

WHY THE CONTROLS ARE IN THE LIST. A candidate that shows "40 posts, 12
with a clock" means nothing on its own -- 12 could be excellent or
useless. The three channels ALREADY WIRED are measured in the same pass
with the same counters, so every candidate's numbers can be read against
a channel known to work. This is the control that separated jina's 403
from tapology's, one change ago.

WHAT IS COUNTED, per channel:

  posts        .tgme_widget_message, same selector update_alwan_epg uses
  clock        a HH:MM anywhere in the post text
  broadcaster  any name from BROADCASTERS below
  BOTH         the only number that matters -- a post that could
               actually become a programme
  freshness    newest and oldest post date in the page

THE FIGHT GAP IS WHY THE UFC CHANNELS ARE HERE. tapology answers 403
through the reader now, and what it uniquely carried was the promotions
that sell their own card. If an Arabic fight channel posts card times
with a broadcaster, it covers ground no football channel here does.

Wired to nothing. It prints; a human reads; a reader is written
afterwards against what was printed, if anything deserves one.
"""

import re
import sys
import time
import urllib.error
import urllib.request

from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# The three already wired, measured with the same counters so the
# candidates have something to be read against.
CONTROLS = [
    ("fajersport", "CONTROL - update_fajer_sports_epg.py"),
    ("AlwanSports", "CONTROL - update_alwan_epg.py"),
    ("matches_today2", "CONTROL - update_thmanyah_epg.py"),
]

CANDIDATES = [
    ("c77m1", "روابط مباريات - football, fast coverage"),
    ("MuhtrefSports", "المحترف سبورت - season matches"),
    ("matsh_today", "مباريات اليوم - a second one under this name"),
    ("Kora4Live", "كورة لايف - live streaming"),
    ("ufc_saudiarabia", "UFC Arabia - the fight gap tapology left"),
    ("UFC_fightclub", "UFC - fights"),
    ("UFClive_en", "UFC Live - fights, English"),
]

# Enough of the region's broadcasters to tell a post that names one from
# a post that does not. Not a vocabulary anything is built on -- it only
# has to be good enough to count with.
BROADCASTERS = [
    "بي ان", "بين سبورت", "bein", "ssc", "اس اس سي", "الكاس", "الكأس",
    "alkass", "شاهد", "shahid", "ثمانية", "thmanyah", "أبوظبي", "ابوظبي",
    "ad sports", "دبي", "dubai", "روتانا", "rotana", "on sport", "اون سبورت",
    "mbc", "dazn", "sport tv", "starzplay", "tod", "تود", "الشرق",
    "الرياضية", "ksa sports", "كاس", "espn", "tnt", "sky", "canal",
]

CLOCK = re.compile(r"\b([01]?\d|2[0-3])\s*[:٫:]\s*([0-5]\d)\b")

TEXT_SELECTORS = (
    ".tgme_widget_message_text",
    ".tgme_widget_message_caption",
)


def fetch(url, attempts=3):
    last = None

    for n in range(attempts):
        req = urllib.request.Request(url, headers={"User-Agent": UA})

        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read().decode("utf-8", "replace")

        except urllib.error.HTTPError as exc:
            # A 404 here is the answer, not a hiccup -- a private or
            # renamed channel has no /s/ page. Don't spend retries on it.
            return exc.code, ""

        except Exception as exc:
            last = exc
            time.sleep(2 * (n + 1))

    print(f"    unreachable after {attempts}: {last}")
    return 0, ""


def post_text(post):
    parts = []

    for sel in TEXT_SELECTORS:
        for tag in post.select(sel):
            parts.append(tag.get_text(" ", strip=True))

    return " ".join(p for p in parts if p)


def post_date(post):
    tag = post.select_one("time[datetime]")
    return (tag.get("datetime", "") or "")[:10] if tag else ""


def names_broadcaster(text):
    low = text.lower()
    return [b for b in BROADCASTERS if b in low]


def measure(slug, note):
    url = f"https://t.me/s/{slug}"
    print(f"\n{'=' * 68}\n{slug}  --  {note}\n{url}")

    status, html = fetch(url)
    print(f"    status {status}   size {len(html):,}B")

    if status != 200 or not html:
        print("    NOTHING TO READ")
        return

    soup = BeautifulSoup(html, "html.parser")
    posts = soup.select(".tgme_widget_message")

    if not posts:
        # A 200 with no posts is what a private channel's join page
        # looks like, and what a dead slug looks like. Say so.
        print("    200 but ZERO posts -- a join page or an empty slug")
        return

    clocked = named = both = 0
    dates = []
    samples = []

    for post in posts:
        text = post_text(post)

        if not text:
            continue

        day = post_date(post)

        if day:
            dates.append(day)

        has_clock = bool(CLOCK.search(text))
        hits = names_broadcaster(text)

        clocked += has_clock
        named += bool(hits)

        if has_clock and hits:
            both += 1

            if len(samples) < 2:
                samples.append((day, hits[:3], text[:260]))

    total = len(posts)
    print(f"    posts {total}")
    print(f"    with a clock        {clocked:>3}  ({clocked * 100 // max(total, 1)}%)")
    print(f"    naming a channel    {named:>3}  ({named * 100 // max(total, 1)}%)")
    print(f"    BOTH                {both:>3}  ({both * 100 // max(total, 1)}%)  <-- the bar")

    if dates:
        print(f"    dates {min(dates)} .. {max(dates)}")

    for day, hits, text in samples:
        print(f"\n    [{day}] names {hits}\n    {text}")

    if not samples:
        print("\n    no post carried both -- nothing to show")


def main():
    print("MEASURING OPEN TELEGRAM CHANNELS")
    print("controls first, so the candidates have a baseline to be read against")

    for slug, note in CONTROLS + CANDIDATES:
        try:
            measure(slug, note)
        except Exception as exc:
            print(f"    FAILED {slug}: {exc}")

    print(f"\n{'=' * 68}\nread the BOTH line. a candidate below the controls adds nothing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
