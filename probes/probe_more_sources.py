#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ask four pages named by the reader what they actually publish.

    "مفروض ال premier League الانجليزي تضيف عليه كمان sky sports صح ؟
     و عندك fox soccer ممكن بتنقل و Stan الاسترالية و Paramount+
     يعني إضافة بحكي على beIN qatar مش اشي اخر يبينوا جنبها او معها"

    https://www.sportsmediawatch.com/tv-schedules/nfl-tv-schedule/
    https://www.boxingscene.com/schedule
    https://mmatown.com/events?page=1

NOTHING IS WIRED UNTIL A PAGE HAS BEEN ASKED. That rule is not caution
for its own sake — it is the only reason this repository ever found out
that live-footballontv names no Egyptian channel in 152 fixtures, that
pflmma's 77 timestamps are all from 2018, and that ESPN's own API answers
403 to everything its own pages call. Each of those looked certain from
the outside.

WHAT IS PRINTED, and why each line is the one that decides:

    the STATUS and SIZE      a 22 KB shell is a page that renders in the
                             browser and carries nothing here
    a MACHINE-READABLE INSTANT, decoded and DATED. Counting timestamps
                             is what made an archive look like a
                             schedule; the years are printed
    a BROADCASTER            the board's standing rule is that an event
                             nobody can name a channel for does not go on
                             it, so a page with dates and no channel
                             cannot become a row however good it is
    the FIRST ROWS           so the shape is read rather than guessed

And the first question is asked of the source this repository ALREADY
has: livesoccertv is wired for the American broadcasters, so before any
new page is added, what does it name today?
"""
from __future__ import annotations

import collections
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

import requests

BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                  " (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}

PAGES = (
    ("NFL · sportsmediawatch",
     "https://www.sportsmediawatch.com/tv-schedules/nfl-tv-schedule/"),
    ("Boxing · boxingscene",
     "https://www.boxingscene.com/schedule"),
    ("MMA · mmatown", "https://mmatown.com/events?page=1"),
)

# The broadcasters the reader named, plus the ones a page like these
# would have to name to be worth reading at all.
ASKED_FOR = ("sky", "fox", "stan", "paramount", "cbs", "nbc", "peacock",
             "usa network", "espn", "abc", "amazon", "prime video",
             "netflix", "dazn", "tnt", "hbo", "bein", "optus", "kayo")

A_UNIX = re.compile(r"\b1[7-9]\d{8}\b")
AN_ISO = re.compile(r"\b20\d\d-\d\d-\d\dT?\s?\d\d:\d\d")
A_DATETIME_ATTR = re.compile(r'datetime="([^"]+)"')
TAGS = re.compile(r"<[^>]+>")


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", TAGS.sub(" ", html))


def years_in(html: str) -> collections.Counter:
    """Every instant the page carries, counted BY YEAR.

    Counting them is what made pflmma's archive look like a schedule.
    """
    years: collections.Counter = collections.Counter()
    for stamp in A_UNIX.findall(html):
        try:
            years[datetime.fromtimestamp(int(stamp), timezone.utc).year] += 1
        except (ValueError, OSError):
            pass
    for stamp in AN_ISO.findall(html) + A_DATETIME_ATTR.findall(html):
        found = re.match(r"(20\d\d)", stamp)
        if found:
            years[int(found.group(1))] += 1
    return years


def ask(session, name: str, url: str) -> None:
    print(f"\n── {name}\n   {url}")
    try:
        page = session.get(url, timeout=30, headers=BROWSER)
    except Exception as exc:                                  # noqa: BLE001
        print(f"   UNREACHABLE {str(exc)[:100]}")
        return
    html = page.text
    print(f"   {page.status_code}   {len(page.content) // 1024} KB")
    if page.status_code != 200:
        print("   REFUSED — nothing can be read from it")
        return

    years = years_in(html)
    print(f"   instants by year: "
          f"{dict(sorted(years.items())) if years else 'NONE'}")
    if not years:
        print("   NO MACHINE-READABLE INSTANT — the board refuses a row "
              "whose time had to be guessed")

    flat = text_of(html).casefold()
    named = [word for word in ASKED_FOR if word in flat]
    print(f"   broadcasters named: {named if named else 'NONE'}")

    # The first rows, so the shape is read and not imagined.
    rows = [one for one in
            re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)[:6]]
    if rows:
        print("   first rows:")
        for row in rows:
            line = text_of(row).strip()[:150]
            if line:
                print(f"     {line}")
    else:
        blocks = re.findall(r"<li[^>]*>(.*?)</li>", html, re.S)
        shown = 0
        for block in blocks:
            line = text_of(block).strip()
            if len(line) > 40 and any(c.isdigit() for c in line):
                print(f"     {line[:150]}")
                shown += 1
            if shown >= 6:
                break
        if not shown:
            print("   no table and no list rows — the schedule is not in "
                  "the HTML this fetch received")


def what_livesoccertv_names_today(session) -> None:
    """The source already wired for the American broadcasters."""
    print("\n══ The source already here: livesoccertv")
    try:
        import live_soccer_tv
        rows = live_soccer_tv.broadcasts(session)
    except Exception as exc:                                  # noqa: BLE001
        print(f"   the reader raised {type(exc).__name__}: {str(exc)[:90]}")
        return
    print(f"   {len(rows)} broadcast(s) read")
    names = collections.Counter(row["channel"] for row in rows)
    for channel, count in names.most_common(40):
        print(f"     {count:3}  {channel}")
    for word in ("sky", "fox", "stan", "paramount", "peacock", "usa"):
        hit = [n for n in names if word in n.casefold()]
        print(f"   '{word}': {hit if hit else 'NOT NAMED'}")


def main() -> int:
    session = requests.Session()
    what_livesoccertv_names_today(session)
    for name, url in PAGES:
        ask(session, name, url)
    print("\nNothing here is wired. This prints what each page answers so "
          "the decision is made on the answer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
