#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Two questions the board cannot be changed without answering.

ONE — WRC. The reader asked for the World Rally Championship on channel
2. Nothing is written until a source is asked what it actually publishes:
does wheresthematch carry a rally page at all, do its rows carry a
machine-readable instant, and do they name a broadcaster? A calendar with
no channel is no use to this board, and counting the word "rally" in a
page is not finding a row.

TWO — the duplicate. The board printed today:

    16:00  Dana White's Contender Series: Season 10, Week 5   Paramount+
    16:00  MMA Berisha vs Pasley - Meta Apex                  UFC Fight Pass

One card, two rows. _the_same_card_family already exists for exactly this
pair — its own comment names it — so the question is not what rule to
write but why the rule there did not fire. This prints the two rows whole
and asks each fold about them directly.

Measurement only: nothing here writes to the guide.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

from epg_lib import new_session, fetch, norm                   # noqa: E402
import world_sport_on_tv as world                              # noqa: E402
import other_sports_epg as board                               # noqa: E402


def line(text=""):
    print(text, flush=True)


def rule(text):
    line()
    line("=" * 72)
    line(text)
    line("=" * 72)


# ── one: is there a rally page, and what is on it ───────────────────────
CANDIDATES = (
    "/live-rally-on-tv/",
    "/live-wrc-on-tv/",
    "/live-rallying-on-tv/",
    "/live-world-rally-championship-on-tv/",
    "/live-motorsport-on-tv/",
    "/live-motor-sport-on-tv/",
    "/live-racing-on-tv/",
)


def the_rally_pages(session):
    rule("ONE — where the World Rally Championship might come from")
    for path in CANDIDATES:
        url = world.SOURCE + path
        try:
            got = fetch(session, url)
        except Exception as exc:                               # noqa: BLE001
            line(f"{path:46} unreachable — {exc}")
            continue
        if (got.encoding or "").lower() in ("", "iso-8859-1", "latin-1"):
            got.encoding = "utf-8"
        page = got.text
        line(f"{path:46} {got.status_code}  {len(page):>8,} bytes")
        if got.status_code != 200:
            continue

        # read it with the board's own reader, refusing nothing, so the
        # count is what the page has rather than what a filter allowed
        rows = world.collect(page, "Rally", None, None)
        line(f"    -> {len(rows)} row(s) with an instant and a title")
        for row in rows[:12]:
            line(f"       {row['start']:%Y-%m-%d %H:%M} UTC  "
                 f"{row['title'][:52]:52}  {row['competition'][:24]:24}  "
                 f"{row['channels']}")
        if rows:
            named = sum(1 for r in rows if r["channels"])
            line(f"    -> {named} of {len(rows)} name a broadcaster")
            wrc = [r for r in rows
                   if "wrc" in (r['title'] + r['competition']).lower()
                   or "rally" in (r['title'] + r['competition']).lower()]
            line(f"    -> {len(wrc)} say rally or WRC in so many words")
        line()


def already_collected(session, floor, ceiling):
    """Is rally arriving already and being dropped for want of a sport?"""
    rule("ONE(b) — does anything the board already reads mention rally?")
    everything = world.events(session)
    line(f"world_sport_on_tv gave {len(everything)} event(s)")
    hits = [e for e in everything
            if "rally" in f"{e.get('title','')} {e.get('competition','')}".lower()
            or "wrc" in f"{e.get('title','')} {e.get('competition','')}".lower()]
    line(f"of which {len(hits)} mention rally or WRC:")
    for e in hits[:20]:
        line(f"   {e['start']:%m-%d %H:%M}  {e.get('sport'):10} "
             f"{e['title'][:50]:50} {e['channels']}")


# ── two: the duplicate, and why the fold did not take it ────────────────
def the_duplicate(session, floor, ceiling):
    rule("TWO — today's MMA rows, whole")
    events = board.collect(session, floor, ceiling)
    line(f"collect() gave {len(events)} event(s) in the window")

    fights = [e for e in events if e.get("sport") in ("MMA", "Boxing")]
    line(f"{len(fights)} of them are MMA or Boxing:")
    line()
    for e in sorted(fights, key=lambda x: x["start"]):
        line(f"  start      {e['start']:%Y-%m-%d %H:%M} UTC")
        line(f"  title      {e.get('title')!r}")
        line(f"  competition{e.get('competition')!r}")
        line(f"  sport      {e.get('sport')!r}   source {e.get('source')!r}")
        line(f"  channels   {e.get('channels')}")
        line()

    rule("TWO(b) — what each fold says about every MMA pair")
    mma = sorted([e for e in fights if e.get("sport") == "MMA"],
                 key=lambda x: x["start"])
    for i, a in enumerate(mma):
        for b in mma[i + 1:]:
            gap = abs((a["start"] - b["start"]).total_seconds()) / 60
            line(f"  {a['title'][:34]:34} | {b['title'][:34]:34}")
            line(f"    {gap:.0f} min apart   "
                 f"same minute: {a['start'] == b['start']}")
            line(f"    channels in common : "
                 f"{sorted(set(a['channels']) & set(b['channels']))}")
            line(f"    _the_same_card_family : "
                 f"{board._the_same_card_family(a, b)}")
            line(f"    _the_same_ufc_card    : "
                 f"{board._the_same_ufc_card(a, b)}")
            line(f"    _the_same_fight_card  : "
                 f"{board._the_same_fight_card(a, b)}")
            line(f"    family read from each : "
                 f"{board._the_card_family(a)!r} / "
                 f"{board._the_card_family(b)!r}")
            line()

    rule("TWO(c) — what survives the fold as it stands")
    kept = board.one_row_per_broadcast(list(events))
    for e in sorted([k for k in kept if k.get("sport") == "MMA"],
                    key=lambda x: x["start"]):
        line(f"  {e['start']:%m-%d %H:%M}  {e['title'][:56]:56} "
             f"{e['channels']}")


def main() -> int:
    session = new_session()
    now = datetime.now(timezone.utc)
    floor = now - timedelta(hours=12)
    ceiling = now + timedelta(days=3)
    line(f"now {now:%Y-%m-%d %H:%M} UTC   window {floor:%m-%d %H:%M} "
         f"-> {ceiling:%m-%d %H:%M}")

    the_rally_pages(session)
    already_collected(session, floor, ceiling)
    the_duplicate(session, floor, ceiling)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
