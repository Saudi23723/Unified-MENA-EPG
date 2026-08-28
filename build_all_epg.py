#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build every guide in one run, merge them, and report what happened.

Why this exists — the scheduling problem it fixes
-------------------------------------------------

Every guide used to carry its own hourly cron, and the merge followed all
fourteen of them through workflow_run. That came to roughly 750 workflow
runs a day in one repository, and GitHub answered the way it does: it
started delaying and dropping this repository's scheduled events. The
symptom was measured on 28 August, not guessed at —

  tabii Spor, cron "37 * * * *", the runs it actually got:
    26 Aug 13:37, 16:03, 18:21, 21:08 | 27 Aug 01:01, 11:58, 22:32
    28 Aug 06:16, then nothing for seven and a half hours

  Alkass, cron "15 * * * *":
    27 Aug 09:42, 20:28 | 28 Aug 05:21, then nothing for eight

Two things are visible there. The gaps: eight to eleven hours on an
hourly schedule. And the minutes: of nine tabii runs, exactly one landed
on :37 — the rest were the same events delivered up to three quarters of
an hour late. That is throttling, and the lever on it is the number of
scheduled events the repository asks for.

So there is now one scheduled build instead of fifteen. It runs every
generator in sequence, merges, and pushes once. Roughly fifty runs a day
where there were seven hundred and fifty.

The second effect matters as much as the first. A dropped per-guide cron
used to strand that one guide until its own cron came round again — tabii
sat eleven hours behind while every other guide was current. Every tick
here rebuilds everything, so any single successful run heals the whole
lot at once, no matter how many were missed before it.

What it does not do
-------------------

It does not stop on a failure. A generator that raises, times out or
writes nothing keeps its previously published file — write_xml_atomic in
epg_lib guarantees that — so one broken source costs one guide's
freshness and nothing else. The run stays green and publishes the rest;
the summary table says plainly which one failed and how far ahead each
guide still reaches. The job goes red only if the merge itself fails,
because that is the link the player actually reads.

Whether a guide has quietly aged out is health_check.py's question, on
its own schedule. This one's job is to keep the link fed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

UTC = timezone.utc

# (label, script, published file)
#
# Order is the order they run in. It is not significant to the result —
# every generator writes its own file and reads no other — so it is kept
# in the order the guides were added, which makes a diff against the old
# per-guide workflows easy to read.
GENERATORS: list[tuple[str, str, str]] = [
    ("beIN SPORTS Qatar",   "bein_sports_qatar_epg.py",        "bein_sports_qatar_epg.xml"),
    ("beIN SPORTS Türkiye", "bein_sports_turkey_epg.py",       "bein_sports_turkey_epg.xml"),
    ("Jordan (Roya)",       "roya_jordan_epg.py",              "roya_jordan_epg.xml"),
    ("Jordan Sports",       "JORDAN_SPORTS_FINAL_VERIFIED.py", "jordan_sports_epg.xml"),
    ("ON Sport",            "update_onsport_epg.py",           "onsport_epg.xml"),
    ("Alwan Sports",        "update_alwan_epg.py",             "alwan_sports_epg.xml"),
    ("Alkass",              "alkass_epg.py",                   "alkass_epg.xml"),
    ("STARZPLAY",           "starzplay_epg.py",                "starzplay_epg.xml"),
    ("Fajer Sports",        "update_fajer_sports_epg.py",      "fajer_sports_epg.xml"),
    ("Shahid Sports",       "update_shahid_sports_epg.py",     "shahid_sports_epg.xml"),
    ("Shasha",              "update_shasha_epg.py",            "shasha_epg.xml"),
    ("tabii Spor",          "update_tabii_epg.py",             "tabii_spor_1_10_epg.xml"),
    ("Thmanyah",            "update_thmanyah_epg.py",          "thmanyah_epg.xml"),
]

MERGE_SCRIPT = "merge_epg.py"
MERGED = "unified_mena_epg.xml"

# A generator that has not finished in this long is not going to. The
# whole set normally runs in a few minutes; this is the brake, not the
# budget.
PER_SCRIPT_TIMEOUT = timedelta(minutes=6)

# And a brake on the set, so a run can never sit against the job's own
# timeout and be killed before it has merged and pushed anything at all.
# Whatever has not started by then is skipped and keeps its previous
# file; the merge and the push still happen.
TOTAL_BUDGET = timedelta(minutes=32)


def run(script: str, budget_left: timedelta) -> tuple[str, float]:
    """Run one generator. Returns (outcome, seconds)."""
    limit = min(PER_SCRIPT_TIMEOUT, budget_left)
    started = time.monotonic()
    print(f"\n{'=' * 72}\n== {script}\n{'=' * 72}", flush=True)
    try:
        done = subprocess.run(
            [sys.executable, "-u", script],
            timeout=limit.total_seconds(),
        )
    except subprocess.TimeoutExpired:
        print(f"::warning::{script} passed {limit} and was stopped; its "
              f"previously published file is kept")
        return "timed out", time.monotonic() - started
    except Exception as exc:                       # pragma: no cover
        print(f"::warning::{script} could not be started: {exc}")
        return "not started", time.monotonic() - started
    seconds = time.monotonic() - started
    if done.returncode != 0:
        print(f"::warning::{script} exited {done.returncode}; its "
              f"previously published file is kept")
        return f"exit {done.returncode}", seconds
    return "ok", seconds


def describe(path: str, now: datetime) -> tuple[str, str, str]:
    """(channels, programmes, how far ahead) for a published file."""
    if not os.path.exists(path):
        return "—", "—", "missing"
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return "—", "—", "unparsable"

    channels = len(root.findall("channel"))
    newest = None
    programmes = 0
    for programme in root.findall("programme"):
        programmes += 1
        raw = (programme.get("stop") or "")[:14]
        offset = (programme.get("stop") or "")[-5:]
        if len(raw) != 14:
            continue
        try:
            stop = datetime.strptime(raw, "%Y%m%d%H%M%S")
        except ValueError:
            continue
        if len(offset) == 5 and offset[0] in "+-":
            sign = 1 if offset[0] == "+" else -1
            stop = stop.replace(tzinfo=timezone(sign * timedelta(
                hours=int(offset[1:3]), minutes=int(offset[3:5]))))
        else:
            stop = stop.replace(tzinfo=UTC)
        stop = stop.astimezone(UTC)
        if newest is None or stop > newest:
            newest = stop

    if newest is None:
        ahead = "nothing"
    else:
        hours = (newest - now).total_seconds() / 3600
        ahead = f"{hours:+.1f} h" if abs(hours) < 48 else f"{hours / 24:+.1f} d"
    return str(channels), str(programmes), ahead


def summarise(rows: list[tuple[str, str, float, str, str, str]],
              merge_outcome: str) -> None:
    """Print the table, and put it on the run's summary page as well."""
    header = ("| Guide | Result | Time | Channels | Programmes | Reaches ahead |\n"
              "|---|---|---:|---:|---:|---:|\n")
    body = "".join(
        f"| {label} | {'✅' if outcome == 'ok' else '⚠️ ' + outcome} | "
        f"{seconds:.0f}s | {channels} | {programmes} | {ahead} |\n"
        for label, outcome, seconds, channels, programmes, ahead in rows)
    table = header + body

    print("\n" + table)
    print(f"merge: {merge_outcome}")

    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("## Guides built this run\n\n")
        fh.write(table)
        fh.write(f"\n**Merged link:** {merge_outcome}\n")
        failed = [r[0] for r in rows if r[1] != "ok"]
        if failed:
            fh.write(f"\nKept the previous file for: {', '.join(failed)}\n")


def main() -> int:
    started = time.monotonic()
    print(f"Building every guide — {datetime.now(UTC):%Y-%m-%d %H:%M} UTC, "
          f"{len(GENERATORS)} generators")

    rows: list[tuple[str, str, float, str, str, str]] = []
    for label, script, output in GENERATORS:
        spent = timedelta(seconds=time.monotonic() - started)
        left = TOTAL_BUDGET - spent
        if left <= timedelta(seconds=30):
            print(f"::warning::out of time before {script}; it keeps its "
                  f"previously published file and the merge goes ahead")
            outcome, seconds = "skipped, out of time", 0.0
        else:
            outcome, seconds = run(script, left)
        rows.append((label, outcome, seconds, "", "", ""))

    # Every file is measured after the whole set has run, so the table
    # reads as one consistent snapshot rather than as thirteen taken
    # minutes apart.
    now = datetime.now(UTC)
    rows = [(label, outcome, seconds, *describe(output, now))
            for (label, outcome, seconds, *_), (_l, _s, output)
            in zip(rows, GENERATORS)]

    print(f"\n{'=' * 72}\n== {MERGE_SCRIPT}\n{'=' * 72}", flush=True)
    merged_ok = subprocess.run([sys.executable, "-u", MERGE_SCRIPT]).returncode == 0

    channels, programmes, ahead = describe(MERGED, datetime.now(UTC))
    merge_outcome = (f"{'✅' if merged_ok else '❌ FAILED'} — {channels} channels, "
                     f"{programmes} programmes, reaches {ahead}")
    summarise(rows, merge_outcome)

    took = timedelta(seconds=round(time.monotonic() - started))
    print(f"\nWhole build took {took}")

    if not merged_ok:
        print("::error::the merge failed — the link the player reads was not "
              "rebuilt this run")
        return 1
    if ahead in ("missing", "unparsable", "nothing"):
        print(f"::error::{MERGED} is {ahead} after a merge that reported "
              f"success")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
