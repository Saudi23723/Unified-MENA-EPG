#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Guard the published guides and the links that serve them.

This never writes anything. It reads what is committed and reports what
is wrong with it, so a guide that quietly died, a channel that lost its
logo, or a merge that dropped a source shows up as a red run instead of
as a blank guide in TiviMate weeks later.

What counts as a failure:

  * a source file named in merge_epg.py that is missing or unparsable
  * a programme whose stop is not after its start, or two that overlap on
    one channel — either makes the file invalid XMLTV
  * a guide with less than half a day left in the future: it is still
    being published, but there is nothing left to watch in it. tabii's
    guide sat like that — 83 programmes, one of them still ahead — and
    nothing said so. Sources that publish a single day by design are
    listed in ONE_DAY_SOURCES and fail only when nothing at all is left
    ahead, since half a day is more than they ever carry after midday
  * a channel with no name, or an icon pointing at a logo file this
    repository does not actually have
  * the same channel id claimed by two different source files — the merge
    keeps whichever it reads first and silently drops the other
  * a channel that exists in a source file but is missing from the merged
    guide
  * a guide made up of more stand-in than guide_ceilings.json allows it.
    A stand-in is a title that fills time instead of describing a
    broadcast, and a guide that turns mostly into them has usually lost a
    source rather than run out of sport. ON Sport sat at 94 per cent for
    days after FilGoal shut off its feed, warning every run into a log
    nobody read, while every other check here passed

What is only reported:

  * a guide with less than two days ahead of now — thin, not broken
  * a channel with no programmes at all

Run it with no arguments. Exit code 1 means something needs attention.

`--structure-only` skips the freshness checks — whether a guide has run
out, how many days it reaches. Those are about the data ageing, not about
the code, so a pull request must not go red for them; the scheduled run
is what watches freshness.
"""

from __future__ import annotations

import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
REPO_LOGO_RE = re.compile(
    r"raw\.githubusercontent\.com/[^/]+/[^/]+/[^/]+/logos/([^/?#]+)$", re.I)

MERGED = "unified_mena_epg.xml"
# Under half a day left means the guide has stopped being a guide.
DEAD_DAYS = 0.5
THIN_DAYS = 2

# Sources that publish exactly one day, by their own design rather than
# because something broke. Judging these on days-ahead raises a failure
# every evening for a guide that is working perfectly: Alkass serves one
# day and nothing else -- ?day=next, ?day=prev and an invented ?day=next2
# all return byte-identical schedules -- so by late evening in Doha it
# always has under half a day left. They are held to a different rule
# below: they must still cover now, and they must have been refreshed.
ONE_DAY_SOURCES = {
    "alkass_epg.xml": "alkass.net/tvguide publishes the current day only",
}

# How long a one-day guide may sit with nothing ahead before it counts as
# dead rather than as waiting. Such a guide runs out every night by design:
# its last programme ends at midnight in the broadcaster's own timezone and
# the source publishes the next day some time after that. Failing the
# moment nothing is ahead turned that nightly window into a nightly alarm —
# Alkass went red at 23:50 in Doha for having reached the end of its own
# day. What actually distinguishes dead from waiting is how long ago the
# guide's newest programme ended: hours means the day is over, a day or
# more means the source has stopped refreshing.
ONE_DAY_STALE_HOURS = 8

errors: list[str] = []
notes: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def note(msg: str) -> None:
    notes.append(msg)


def stale_hours(path: str, now: datetime) -> float | None:
    """Hours since this guide's newest programme ended, or None if unreadable.

    Negative would mean it still reaches into the future; callers only ask
    once they know it does not.
    """
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return None
    stops = [parse_stamp(p.get("stop")) for p in root.findall("programme")]
    stops = [s for s in stops if s]
    if not stops:
        return None
    return (now - max(stops)).total_seconds() / 3600.0


# A title that stands in for a schedule instead of being one. Each entry
# is a real string some guide publishes, not a guess:
#
#   لا توجد مباراة مجدولة       ON Sport, Alwan, Fajer, Thmanyah — no match known
#   مباراة لم تُعلن قناتها بعد   Thmanyah — match known, channel not
#   PPV — حسب المباراة          tabii Spor 1-10, the standing notice
#   ⏰ التالي:                   the countdown filler between fixtures
#   Tanıtım                     Tivibu Spor, the channel trailing itself
#
# A channel whose every row carries one single title is counted the same
# way whatever that title is, because that is what beIN's XTRA blurb and
# an operator's channel-name filler both look like from here.
STANDIN_TITLE = re.compile(
    r"لا توجد مباراة|لا يوجد|مباراة لم تُعلن|PPV — حسب المباراة|"
    r"⏰ التالي|Tanıtım|24/7",
    re.I)

CEILINGS_FILE = "guide_ceilings.json"


def standin_share(path: str) -> tuple[int, int]:
    """(stand-in rows, total rows) for one published guide."""
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return 0, 0
    per: dict[str, list] = {}
    for programme in root.findall("programme"):
        title = (programme.findtext("title") or "").strip()
        cid = programme.get("channel")
        slot = per.setdefault(cid, [0, 0, set()])
        slot[0] += 1
        slot[2].add(title)
        if STANDIN_TITLE.search(title):
            slot[1] += 1
    for slot in per.values():
        # One title for a whole channel is filler whatever it says.
        if slot[0] >= 4 and len(slot[2]) == 1:
            slot[1] = slot[0]
    return (sum(v[1] for v in per.values()),
            sum(v[0] for v in per.values()))


def check_ceilings(now: datetime) -> None:
    """Fail a guide that has turned mostly into stand-in.

    This is the check that would have caught FilGoal on the first run
    after it was shut off, instead of days later and on a television.
    """
    if not os.path.exists(CEILINGS_FILE):
        note(f"{CEILINGS_FILE} is missing — no guide is held to a "
             f"stand-in ceiling this run")
        return
    try:
        ceilings = json.load(open(CEILINGS_FILE, encoding="utf-8"))
    except Exception as exc:
        fail(f"{CEILINGS_FILE} is unreadable: {exc}")
        return

    print(f"\n{'file':34} {'stand-in':>9} {'ceiling':>8}")
    for path, ceiling in sorted(ceilings.items()):
        if not path.endswith(".xml") or not isinstance(ceiling, (int, float)):
            continue
        if not os.path.exists(path):
            continue
        standin, total = standin_share(path)
        if not total:
            continue
        share = round(100 * standin / total)
        mark = "  OVER" if share > ceiling else ""
        print(f"{path:34} {share:>8}% {ceiling:>7}%{mark}")
        if share > ceiling:
            fail(f"{path}: {share}% of its rows are stand-in, above the "
                 f"{ceiling}% this guide is held to. A guide does not "
                 f"usually fill up with stand-in because there is no sport "
                 f"— check whether one of its sources has stopped "
                 f"answering, the way FilGoal's feed did")


def source_files() -> list[str]:
    """The list merge_epg.py itself publishes, read from the file so the
    two can never drift apart."""
    text = open("merge_epg.py", encoding="utf-8").read()
    block = re.search(r"SOURCE_FILES\s*=\s*\[(.*?)\]", text, re.S)
    if not block:
        fail("merge_epg.py: SOURCE_FILES not found — cannot tell what is published")
        return []
    return re.findall(r'"([^"]+\.xml)"', block.group(1))


def parse_stamp(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y%m%d%H%M%S %z")
    except (TypeError, ValueError):
        return None


def check_file(path: str, now: datetime, *, check_overlaps: bool = True) -> dict:
    """Everything worth knowing about one guide."""
    out = {"channels": {}, "programmes": 0, "ahead": 0, "ids": set()}
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        fail(f"{path}: unreadable ({exc})")
        return out

    if root.tag != "tv":
        fail(f"{path}: root element is <{root.tag}>, not <tv>")

    for ch in root.findall("channel"):
        cid = ch.get("id")
        if not cid:
            fail(f"{path}: a <channel> has no id")
            continue
        out["ids"].add(cid)
        names = [d.text for d in ch.findall("display-name") if (d.text or "").strip()]
        if not names:
            fail(f"{path}: channel {cid} has no display-name")
        icon = ch.find("icon")
        src = icon.get("src") if icon is not None else ""
        if not src:
            note(f"{path}: channel {cid} has no icon")
        else:
            local = REPO_LOGO_RE.search(src)
            if local and not os.path.exists(os.path.join("logos", local.group(1))):
                fail(f"{path}: channel {cid} points at logos/{local.group(1)}, "
                     f"which is not in this repository")
        out["channels"][cid] = 0

    # XMLTV does not require programmes to be stored in time order, and
    # several guides here do not store them that way — a player sorts by
    # start itself. So overlap has to be judged after sorting per channel;
    # judging it in document order reports every unsorted channel as
    # broken when nothing is wrong with it.
    spans: dict[str, list[tuple[datetime, datetime]]] = defaultdict(list)
    for pr in root.findall("programme"):
        cid = pr.get("channel")
        start, stop = parse_stamp(pr.get("start")), parse_stamp(pr.get("stop"))
        if start is None or stop is None:
            fail(f"{path}: programme on {cid} has an unreadable time "
                 f"({pr.get('start')} -> {pr.get('stop')})")
            continue
        if stop <= start:
            fail(f"{path}: programme on {cid} ends before it starts "
                 f"({pr.get('start')} -> {pr.get('stop')})")
        else:
            spans[cid].append((start, stop))

        out["programmes"] += 1
        if cid in out["channels"]:
            out["channels"][cid] += 1
        if start > now:
            out["ahead"] += 1

    if check_overlaps:
        for cid, rows in spans.items():
            cursor = None
            for start, stop in sorted(rows):
                if cursor is not None and start < cursor:
                    fail(f"{path}: overlapping programmes on {cid} at "
                         f"{start:%Y-%m-%d %H:%M %z}")
                cursor = stop if cursor is None else max(cursor, stop)


    empty = [c for c, n in out["channels"].items() if n == 0]
    if empty:
        note(f"{path}: {len(empty)} channel(s) carry no programmes: "
             f"{', '.join(sorted(empty)[:6])}")
    return out


def main() -> int:
    structure_only = "--structure-only" in sys.argv[1:]
    now = datetime.now(UTC)
    print(f"Health check{' (structure only)' if structure_only else ''} | "
          f"{now:%Y-%m-%d %H:%M} UTC\n", flush=True)

    files = source_files()
    if not files:
        return 1

    seen_owner: dict[str, str] = {}
    all_source_ids: set[str] = set()

    print(f"{'file':34} {'ch':>4} {'prog':>6} {'ahead':>6} {'days':>5}")
    for path in files:
        if not os.path.exists(path):
            fail(f"{path}: named in merge_epg.py but missing from the repository")
            print(f"{path:34}   MISSING")
            continue
        info = check_file(path, now)
        days = 0
        try:
            root = ET.parse(path).getroot()
            stamps = [parse_stamp(p.get("start")) for p in root.findall("programme")]
            future = [s for s in stamps if s and s > now]
            days = round((max(future) - now) / timedelta(days=1), 1) if future else 0
        except Exception:
            pass
        print(f"{path:34} {len(info['ids']):4} {info['programmes']:6} "
              f"{info['ahead']:6} {days:5}")
        if structure_only:
            pass
        elif path in ONE_DAY_SOURCES:
            # A one-day guide is judged on whether it is still being
            # refreshed, not on how far ahead it reaches — it never reaches
            # far, and every night it reaches nowhere at all.
            if info["ahead"]:
                note(f"{path}: {days} day(s) ahead — one-day source "
                     f"({ONE_DAY_SOURCES[path]})")
            elif info["programmes"]:
                behind = stale_hours(path, now)
                if behind is None:
                    fail(f"{path}: {info['programmes']} programmes and no "
                         f"readable times — cannot tell whether it is fresh")
                elif behind > ONE_DAY_STALE_HOURS:
                    fail(f"{path}: nothing ahead and its newest programme ended "
                         f"{behind:.0f}h ago — the source has stopped refreshing "
                         f"({ONE_DAY_SOURCES[path]})")
                elif behind < 0:
                    note(f"{path}: on its last programme of the day — nothing "
                         f"starts after it, and it is still running "
                         f"({ONE_DAY_SOURCES[path]})")
                else:
                    note(f"{path}: today has ended and tomorrow is not published "
                         f"yet — newest programme ended {behind:.0f}h ago, within "
                         f"the {ONE_DAY_STALE_HOURS}h this source is given "
                         f"({ONE_DAY_SOURCES[path]})")
        elif info["programmes"] and days < DEAD_DAYS:
            fail(f"{path}: {info['programmes']} programmes but only {days} day(s) "
                 f"still ahead — this guide has run out")
        elif days < THIN_DAYS:
            note(f"{path}: only {days} day(s) ahead")

        for cid in info["ids"]:
            if cid in seen_owner and seen_owner[cid] != path:
                fail(f"channel id {cid} is claimed by both {seen_owner[cid]} and "
                     f"{path} — the merge keeps one and drops the other")
            seen_owner[cid] = path
        all_source_ids |= info["ids"]

    print()
    if not os.path.exists(MERGED):
        fail(f"{MERGED}: the merged link is missing")
    else:
        # Sources are merged as-is, so a cross-file overlap check here would
        # only re-report what each file was already checked for.
        merged = check_file(MERGED, now, check_overlaps=False)
        print(f"{MERGED:34} {len(merged['ids']):4} {merged['programmes']:6} "
              f"{merged['ahead']:6}")
        missing = sorted(all_source_ids - merged["ids"])
        if missing:
            fail(f"{MERGED}: {len(missing)} channel(s) present in a source file "
                 f"but absent from the merged link: {', '.join(missing[:8])}")

    print()
    if not structure_only:
        check_ceilings(now)

    for n in notes:
        print(f"NOTE  {n}", flush=True)
    for e in errors:
        print(f"FAIL  {e}", flush=True)

    if errors:
        print(f"\n{len(errors)} problem(s) found.", flush=True)
        return 1
    print(f"\nAll good — {len(files)} source files and the merged link are healthy"
          f"{f', {len(notes)} note(s)' if notes else ''}.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
