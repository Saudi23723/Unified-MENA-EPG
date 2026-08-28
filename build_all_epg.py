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
generator in sequence, merges, and pushes. A whole pass measured 5m29s
the day it went in.

The second effect matters as much as the first. A dropped per-guide cron
used to strand that one guide until its own cron came round again — tabii
sat eleven hours behind while every other guide was current. Every pass
here rebuilds everything, so any single successful run heals the whole
lot at once, no matter how many were missed before it.

Why it does not just run once and exit
--------------------------------------

Cutting the volume was not enough on its own. With the fifteen crons gone
and this one left, GitHub still dropped the 14:27, 14:47 and 15:07
events — three in a row, on a workflow asking for three events an hour
against the four hundred a day it had been asking for. Whatever the
scheduler is doing, correctness cannot be made to depend on it.

So a scheduled run does not build once. It builds, publishes, waits for
the next twenty-minute mark, and builds again, for three passes inside
one run, then exits before the next hour's event is due. One landed
event therefore covers a whole hour rather than a single moment, and the
repository asks for one scheduled event an hour — twenty-four a day
against the four hundred that were being throttled, which is the lowest
pressure this can be run at while still refreshing every twenty minutes.

Each pass publishes on its own, immediately. A run that is cancelled or
killed in its third pass has already pushed the first two; nothing waits
for the end.

A run started by hand or by a code change builds once and stops — the
--once flag. There is nothing to bridge there.

What it does not do
-------------------

It does not stop on a failure. A generator that raises, times out or
writes nothing keeps its previously published file — write_xml_atomic in
epg_lib guarantees that — so one broken source costs one guide's
freshness and nothing else. The run stays green and publishes the rest;
the summary table says plainly which one failed and how far ahead each
guide still reaches.

The job goes red only if the merge failed on the last pass, because that
is the state the link is actually left in. A merge that failed at :07 and
succeeded at :27 is reported as a warning and not as a red run: the link
is fine, and a red one there would train the eye to ignore it.

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

# And a brake on the set, so a pass can never sit against the job's own
# timeout and be killed before it has merged and pushed anything at all.
# Whatever has not started by then is skipped and keeps its previous
# file; the merge and the push still happen.
TOTAL_BUDGET = timedelta(minutes=16)

# A scheduled run bridges its hour rather than building once — see the
# docstring. Three passes twenty minutes apart, the last starting at +40,
# so the run is finished well before the next hour's event is due and two
# runs can never overlap.
CYCLE = timedelta(minutes=20)
PASSES = 3


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


def publish() -> bool:
    """Commit and push whatever this pass rewrote.

    Every pass publishes on its own rather than at the end of the run, so
    a run killed in its third pass has already delivered the first two.
    The retry loop is here because several workflows used to race for the
    same branch; only this one pushes guides now, but a merge landing at
    the same moment would still reject the push.
    """
    subprocess.run(["git", "add", "--", "*.xml"], check=False)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"],
                            check=False).returncode
    if staged == 0:
        print("nothing changed, nothing to push")
        return True

    # Whatever branch the run is on, which on a scheduled run is main.
    # Naming it rather than hard-coding main is what lets this be
    # exercised end to end from a branch without touching the real guide.
    branch = os.environ.get("GITHUB_REF_NAME") or "main"

    subprocess.run(["git", "commit", "-m", "Update every EPG"], check=False)
    for attempt in range(1, 6):
        subprocess.run(["git", "pull", "--rebase", "origin", branch], check=False)
        if subprocess.run(["git", "push", "origin", f"HEAD:{branch}"],
                          check=False).returncode == 0:
            print(f"pushed on attempt {attempt}")
            return True
        print(f"push rejected, retrying ({attempt}/5)")
        time.sleep(2 + attempt * 2)
    print("::error::could not push after five attempts")
    return False


def build_once() -> bool:
    """One pass: every generator, then the merge, then a push."""
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
        print("::warning::the merge failed — the link the player reads was "
              "not rebuilt this pass")
        return False
    if ahead in ("missing", "unparsable", "nothing"):
        print(f"::warning::{MERGED} is {ahead} after a merge that reported "
              f"success")
        return False

    return publish()


def main() -> int:
    once = "--once" in sys.argv
    passes = 1 if once else PASSES
    started = time.monotonic()
    ok = False

    for index in range(passes):
        print(f"\n########  pass {index + 1} of {passes}  "
              f"########", flush=True)
        ok = build_once()

        if index + 1 >= passes:
            break

        # Sleep to the next twenty-minute mark measured from the start of
        # the run, not from the end of the pass, so the marks stay put
        # however long a pass took. A pass that overran its slot goes
        # straight into the next one rather than sliding the whole run.
        due = (index + 1) * CYCLE.total_seconds()
        wait = due - (time.monotonic() - started)
        if wait > 0:
            print(f"\nnext pass in {timedelta(seconds=round(wait))} — "
                  f"the guides just published stand until then", flush=True)
            time.sleep(wait)

    # The colour of the run reports the state the link was left in, so a
    # pass that failed and a later one that fixed it is a warning, not a
    # red run. An earlier failure is already annotated where it happened.
    if not ok:
        print("::error::the last pass did not publish — the link may be "
              "behind its sources")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
