#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print the two sources that admitted to having the card, and their shape.

Counting words settled which sources HAVE the prelims. It cannot settle
how to read them, and guessing at that is what this repository has paid
for most. So this prints content:

    ufc.com/events        early prelim 7 · prelim 84 · main card 78
    awk.epgsky.com        200, a channel list and a day's schedule as JSON

The first was written off earlier in this session as "not in the HTML"
because it carries no <time datetime> and no ld+json. That was a wrong
conclusion from a missing field — the words are plainly there, so the
markup around them is printed here rather than reasoned about again.

The second is Sky's own electronic programme guide. If Sky Sports Action
writes "UFC Prelims" as a PROGRAMME with a start of its own, the whole
question answers itself: a prelim becomes a row like any other, from a
broadcaster's own schedule, with nothing inferred.

Nothing is wired off this. It prints.
"""
from __future__ import annotations

import json
import re
import sys

sys.path.insert(0, ".")
from epg_lib import fetch, new_session, norm            # noqa: E402

A_TAG = re.compile(r"<[^>]+>")


def ufc(session) -> None:
    print("\n=== ufc.com/events — the markup around every 'prelim' " + "=" * 8)
    try:
        html = fetch(session, "https://www.ufc.com/events").text
    except Exception as exc:                                  # noqa: BLE001
        print(f"  SHUT: {exc}")
        return
    print(f"  {len(html) // 1024} KB")

    # Where the words sit, and what is around them.
    for word in ("early prelim", "prelims", "main card"):
        spots = [m.start() for m in re.finditer(word, html, re.I)]
        print(f"\n  -- {word}: {len(spots)} times, first three in context --")
        for at in spots[:3]:
            chunk = html[max(0, at - 260):at + 260]
            print(f"     …{norm(chunk)[:420]}…")

    # A schedule has to carry a TIME. These are the ways a page that has
    # no <time datetime> can still be carrying one.
    print("\n  -- how this page carries a time --")
    for what, pattern in (
            ("data-* with a unix timestamp", r'data-[a-z-]*(?:time|date|stamp)[a-z-]*="(\d{10,13})"'),
            ("any ten-digit unix stamp", r"\b(1[6-9]\d{8})\b"),
            ("an ISO instant", r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})"),
            ("a data-main-card attribute", r'(data-[a-z-]*card[a-z-]*="[^"]{0,40}")'),
            ("a timezone-aware element", r'(class="[^"]*timezone[^"]*")'),
    ):
        found = re.findall(pattern, html, re.I)
        print(f"     {what:<32} {len(found):>5}   {found[:4]}")


def sky(session) -> None:
    print("\n\n=== Sky's own EPG — the channels, then a day of one " + "=" * 8)
    try:
        raw = fetch(session,
                    "https://awk.epgsky.com/hawk/linear/services/4101/1").text
    except Exception as exc:                                  # noqa: BLE001
        print(f"  SHUT: {exc}")
        return
    try:
        listing = json.loads(raw)
    except ValueError:
        print(f"  not JSON. first 300 characters:\n     {raw[:300]}")
        return

    print(f"  top-level keys: {list(listing)[:8]}")
    services = listing.get("services") or []
    print(f"  {len(services)} services; one of them looks like:")
    if services:
        print(f"     {json.dumps(services[0], ensure_ascii=False)[:220]}")

    wanted = [s for s in services
              if re.search(r"sky spo?rts?|tnt", str(s.get("t", "")), re.I)]
    print(f"\n  {len(wanted)} that carry sport:")
    for s in wanted[:16]:
        print(f"     sid={s.get('sid'):<8} {s.get('t')}")

    # A day of the ones that would carry a fight.
    for s in wanted:
        if not re.search(r"action|arena|main event|mix|tnt", str(s.get("t")), re.I):
            continue
        sid = s.get("sid")
        for day in ("20260905", "20260906"):
            url = f"https://awk.epgsky.com/hawk/linear/schedule/{day}/{sid}"
            try:
                page = json.loads(fetch(session, url).text)
            except Exception as exc:                          # noqa: BLE001
                print(f"     {s.get('t')} {day}: SHUT {str(exc)[:70]}")
                continue
            blocks = page.get("schedule") or []
            events = blocks[0].get("events", []) if blocks else []
            print(f"\n  -- {s.get('t')} · {day} · {len(events)} programme(s) --")
            if events:
                print(f"     one event whole: "
                      f"{json.dumps(events[0], ensure_ascii=False)[:260]}")
            for event in events:
                title = str(event.get("t", ""))
                if re.search(r"ufc|prelim|fight|boxing|main card|mma", title, re.I):
                    print(f"     {event.get('st')}  {title[:70]}")
        break                                   # one channel is the shape


def main() -> int:
    session = new_session()
    ufc(session)
    sky(session)
    return 0


if __name__ == "__main__":
    sys.exit(main())
