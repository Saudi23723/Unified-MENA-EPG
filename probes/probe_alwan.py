#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print Alwan's own posts and what this repository actually reads from them.

Reported: "الوان ما قرأ جميع مباريات اليوم". Its guide today carries six
fixtures across channels 2-5 and says "لا توجد مباراة مجدولة" on 1 and
6-10.

Whether that is right is a fact about what Alwan POSTED, and this
repository has a measured price for guessing at such things. There are
three different faults it could be, with three different fixes:

    NOT ENOUGH PAGES     TELEGRAM_PAGES is 3. Telegram's /s/ view pages
                         backwards from the newest post, so a fixture
                         announced four pages ago is simply never seen.

    THE BLOCK SPLITTER   one post can carry a whole day's card, and if
                         split_into_fixture_blocks cuts it wrongly the
                         later fixtures in the post are lost.

    THE FIXTURE PARSER   a line that names a match in a shape
                         fixture_from_line does not know is dropped
                         silently.

So this reads MORE pages than the builder does, prints how much each one
adds, and then — for every post that mentions today — prints the post
verbatim beside what the builder's own functions extract from it. The
two lists side by side say which of the three it is, or that it is none
of them and Alwan really did not post the rest.

It prints. It writes nothing and changes no guide.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

import update_alwan_epg as alwan

DEEPER = 10          # against the builder's 3


def main() -> int:
    now = datetime.now(timezone.utc)
    print(f"asked at {now:%Y-%m-%d %H:%M} UTC")
    print(f"the builder reads {alwan.TELEGRAM_PAGES} page(s); this reads "
          f"{DEEPER}\n")

    # HOW MUCH EACH PAGE ADDS. If page 4 and beyond carry fixtures the
    # builder never sees, the depth is the fault and nothing else needs
    # changing.
    print("=" * 70)
    print("WHAT EACH EXTRA PAGE ADDS")
    print("=" * 70)
    seen_at_depth = {}
    for depth in (alwan.TELEGRAM_PAGES, DEEPER):
        try:
            posts = alwan.fetch_posts(pages=depth)
        except Exception as exc:                              # noqa: BLE001
            print(f"  depth {depth}: UNREACHABLE {str(exc)[:90]}")
            continue
        events = []
        for post in posts:
            try:
                events.extend(alwan.parse_post(post) or [])
            except Exception:                                 # noqa: BLE001
                pass
        seen_at_depth[depth] = (posts, events)
        print(f"  {depth} page(s): {len(posts)} post(s), "
              f"{len(events)} fixture(s) parsed")

    if DEEPER in seen_at_depth and alwan.TELEGRAM_PAGES in seen_at_depth:
        shallow = {alwan.event_key(e) for e in seen_at_depth[alwan.TELEGRAM_PAGES][1]}
        deep = seen_at_depth[DEEPER][1]
        extra = [e for e in deep if alwan.event_key(e) not in shallow]
        print(f"\n  FIXTURES THE BUILDER'S DEPTH NEVER SEES: {len(extra)}")
        for one in sorted(extra, key=lambda e: e.get("start") or now)[:20]:
            when = one.get("start")
            print(f"     {when:%m-%d %H:%M}  {one.get('channel','?'):<10} "
                  f"{str(one.get('title') or one.get('home','')):.60}")

    posts, events = seen_at_depth.get(DEEPER, ([], []))

    # WHAT ALWAN POSTED ABOUT TODAY, verbatim, beside what was read.
    print("\n" + "=" * 70)
    print("EVERY POST MENTIONING TODAY, AND WHAT WAS READ FROM IT")
    print("=" * 70)
    stamp = now.strftime("%d/%m")
    other = now.strftime("%-d/%-m") if hasattr(now, "strftime") else stamp
    today_words = {stamp, other, now.strftime("%Y-%m-%d"), "اليوم"}

    shown = 0
    for post in posts:
        text = alwan.post_text(post) or ""
        if not any(word in text for word in today_words):
            continue
        shown += 1
        if shown > 4:
            break
        print(f"\n── post {shown} ─────────────────────────────────")
        for line in text.splitlines():
            if line.strip():
                print(f"   | {line.strip()[:110]}")
        try:
            got = alwan.parse_post(post) or []
        except Exception as exc:                              # noqa: BLE001
            print(f"   PARSE RAISED: {str(exc)[:90]}")
            continue
        print(f"   -> {len(got)} fixture(s) read from it:")
        for one in got:
            when = one.get("start")
            print(f"      {when:%m-%d %H:%M}  {one.get('channel','?'):<10} "
                  f"{str(one.get('title') or one.get('home','')):.60}")

    # AND THE WHOLE OF TODAY, PER CHANNEL, from the deeper read.
    print("\n" + "=" * 70)
    print("TODAY, PER ALWAN CHANNEL, READ AT DEPTH " + str(DEEPER))
    print("=" * 70)
    per: dict[str, list] = {}
    for one in events:
        when = one.get("start")
        if not when or when.date() != now.date():
            continue
        per.setdefault(str(one.get("channel", "?")), []).append(one)
    if not per:
        print("  nothing at all dated today")
    for channel in sorted(per, key=lambda c: (len(c), c)):
        for one in sorted(per[channel], key=lambda e: e["start"]):
            print(f"  {channel:<12} {one['start']:%H:%M}  "
                  f"{str(one.get('title') or one.get('home','')):.60}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
