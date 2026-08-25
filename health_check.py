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
    nothing said so
  * a channel with no name, or an icon pointing at a logo file this
    repository does not actually have
  * the same channel id claimed by two different source files — the merge
    keeps whichever it reads first and silently drops the other
  * a channel that exists in a source file but is missing from the merged
    guide

What is only reported:

  * a guide with less than two days ahead of now — thin, not broken
  * a channel with no programmes at all

Run it with no arguments. Exit code 1 means something needs attention.
"""

from __future__ import annotations

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

errors: list[str] = []
notes: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def note(msg: str) -> None:
    notes.append(msg)


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
    now = datetime.now(UTC)
    print(f"Health check | {now:%Y-%m-%d %H:%M} UTC\n", flush=True)

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
        if info["programmes"] and days < DEAD_DAYS:
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
