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
the next twenty-minute mark, and builds again — nine passes, not quite
three hours, from a single landed event. Whatever the scheduler does
after that, the guides keep being rebuilt every twenty minutes.

Two events an hour are asked for, which is two chances an hour of
starting a fresh ticker after a long silence, and the workflow cancels a
run in progress when a new one lands so they can never pile up. Forty-
eight scheduled events a day against the four hundred that were being
throttled.

Each pass publishes on its own, immediately. A run that is cancelled or
killed in its fifth pass has already pushed the first four; nothing waits
for the end, and a cancellation almost always lands during a sleep.

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

import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import epg_lib
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

# A rebuild that comes back with less than this share of what is already
# published has not had a quiet day; it has lost a source. The published
# file is put back and the run says so.
#
# Seven of the thirteen generators already refuse this themselves, through
# write_xml_atomic's regression guard. Six write their own XML and have no
# such guard, and three of those six are not ours to change. Doing it here
# covers all thirteen without touching any of them.
#
# Half is deliberately far below ordinary variation. Across a week of runs
# no guide moved by more than a few per cent between consecutive builds,
# and the two real collapses on record — ON Sport losing FilGoal, and the
# Combined pipeline before it was retired — were far past it.
COLLAPSE_FLOOR = 0.5

# ON Sport did not collapse to nothing when FilGoal died. It collapsed to
# placeholder: ten real events and sixty-two rows saying it did not know,
# which is a full file by any count of rows. So the share of rows that say
# nothing is checked too, against the same ceilings health_check enforces.
# A rebuild that crosses its guide's ceiling, when what is published is
# still under it, is the same failure wearing a different shape.
CEILINGS_FILE = "guide_ceilings.json"
STANDIN_TITLE = re.compile(
    r"لا توجد مباراة|لا يوجد|مباراة لم تُعلن|لم يُعلن البث"
    r"|No listing published|PPV — حسب المباراة|Tanıtım|24/7",
    re.I)

# Rows that fill the space between broadcasts rather than announcing one:
# a countdown, or the single row that covers a long wait.
#
# Counting them as programmes made the collapse guard measure the wrong
# thing. A guide with 17 matches published 640 rows because the gaps were
# filled hour by hour; when the filling was made sane the row count halved
# and the guard would have called that a collapse and restored the old
# file — for ever, since the published file never moves. Worse, it was
# blind in the direction that matters: a guide whose source had died could
# keep 600 countdown rows pointed at one stale fixture and sail past a
# floor set on rows.
#
# So the floor counts what a guide is actually for: how many broadcasts it
# knows about.
FILLER_TITLE = re.compile(r"\u23f0|·\s*بعد\s|المباراة القادمة")

# A generator that has not finished in this long is not going to. The
# whole set normally runs in a few minutes; this is the brake, not the
# budget.
PER_SCRIPT_TIMEOUT = timedelta(minutes=6)

# And a brake on the set, so a pass can never sit against the job's own
# timeout and be killed before it has merged and pushed anything at all.
# Whatever has not started by then is skipped and keeps its previous
# file; the merge and the push still happen.
TOTAL_BUDGET = timedelta(minutes=16)

# A scheduled run bridges the gap to the next one rather than building
# once — see the docstring. Nine passes twenty minutes apart, so one
# landed event covers not quite three hours on its own.
#
# The length is set by how long the scheduler has actually gone quiet.
# Before the consolidation the observed gaps ran two to eleven hours; the
# afternoon it went in, three events an hour were dropped in a row and
# then a fourth. Three hours covers the common case outright and turns
# the worst one from eleven hours dark into eight.
#
# It costs nothing when the scheduler is behaving: the workflow cancels a
# run in progress when a new event lands, so a ticker that is no longer
# needed is replaced rather than left to finish. Almost every such
# cancellation lands during a sleep, and a pass that is cut off has
# already published everything the passes before it built.
CYCLE = timedelta(minutes=20)
PASSES = 9


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


def count(root) -> tuple[int, int, int]:
    """(programmes, rows that say the guide does not know, real broadcasts).

    One function, so a rebuild and the file it is compared against are
    always counted the same way.
    """
    per: dict[str, list] = {}
    for programme in root.findall("programme"):
        title = (programme.findtext("title") or "").strip()
        slot = per.setdefault(programme.get("channel"), [0, 0, set(), 0])
        slot[0] += 1
        if not STANDIN_TITLE.search(title):
            slot[2].add(title)
        if STANDIN_TITLE.search(title):
            slot[1] += 1
        elif not FILLER_TITLE.search(title):
            slot[3] += 1
    for slot in per.values():
        # A channel saying one single thing all day is saying nothing,
        # whatever that thing is.
        if slot[0] >= 4 and len(slot[2]) <= 1:
            slot[1] = slot[0]
            slot[3] = 0
    return (sum(v[0] for v in per.values()),
            sum(v[1] for v in per.values()),
            sum(v[3] for v in per.values()))


def measure(path: str) -> tuple[int, int, int]:
    """Count a file on disk."""
    if not os.path.exists(path):
        return 0, 0, 0
    try:
        return count(ET.parse(path).getroot())
    except Exception:
        return 0, 0, 0


def committed(path: str) -> tuple[int, int, int]:
    """The same measurement, taken on what is already published."""
    done = subprocess.run(["git", "show", f"HEAD:{path}"],
                          capture_output=True, check=False)
    if done.returncode != 0 or not done.stdout:
        return 0, 0, 0
    try:
        return count(ET.fromstring(done.stdout))
    except Exception:
        return 0, 0, 0


def close_gaps_in(label: str, path: str) -> str | None:
    """Give every channel in a freshly built file something to show.

    Seven of the thirteen generators write their own file instead of going
    through write_xml_atomic, so the gap-closing that lives there reaches
    barely half the guides. Rewriting those seven to use the shared writer
    would touch guides that are working, and the ones that work are the
    ones not to touch.

    So the guarantee is applied here instead, to the finished file, where
    it does not care which code wrote it. Every guide gets it, including
    any added later by someone who never opens epg_lib — and no working
    generator is altered to get it.

    Returns a note when it changed something, so the pass can say so.
    """
    if not os.path.exists(path):
        return None
    try:
        tree = ET.parse(path)
    except Exception as exc:
        print(f"::warning::{label}: {path} could not be re-read to close its "
              f"gaps ({exc}) — published as its generator wrote it")
        return None

    root = tree.getroot()
    try:
        filled = epg_lib.close_every_gap(root)
    except Exception as exc:
        print(f"::warning::{label}: could not close gaps ({exc}) — published "
              f"as its generator wrote it")
        return None
    if not filled:
        return None

    try:
        epg_lib.order_for_xmltv(root)
        tmp = f"{path}.gaps"
        ET.ElementTree(root).write(tmp, encoding="utf-8",
                                   xml_declaration=True)
        # Parse it back before it replaces anything: a guide that is merely
        # missing filler is far better than one that is malformed.
        ET.parse(tmp)
        os.replace(tmp, path)
    except Exception as exc:
        print(f"::warning::{label}: gap-filled file was not valid ({exc}) — "
              f"kept the generator's own file")
        return None
    return f"closed {filled} gap(s)"


def keep_published_if_collapsed(label: str, path: str,
                                ceilings: dict) -> str | None:
    """Put the published file back if this rebuild is a collapse.

    Returns a note when it intervened, so the caller can say so in the
    table rather than leaving it to a log line.
    """
    was_rows, was_blank, was_real = committed(path)
    now_rows, now_blank, now_real = measure(path)
    if not was_rows or not now_rows:
        return None

    reason = None
    # Broadcasts, not rows — see FILLER_TITLE. Rows are the fallback for a
    # guide that has never had a real one to count.
    if was_real:
        if now_real < was_real * COLLAPSE_FLOOR:
            reason = (f"{now_real} matches against {was_real} already "
                      f"published — under half")
    elif now_rows < was_rows * COLLAPSE_FLOOR:
        reason = (f"{now_rows} programmes against {was_rows} already "
                  f"published — under half")
    else:
        ceiling = ceilings.get(path)
        if isinstance(ceiling, (int, float)):
            was_share = 100 * was_blank / was_rows
            now_share = 100 * now_blank / now_rows
            if now_share > ceiling >= was_share:
                reason = (f"{now_share:.0f}% of it says it does not know what "
                          f"is on, against {was_share:.0f}% published and a "
                          f"ceiling of {ceiling}%")

    if reason is None:
        return None

    restored = subprocess.run(["git", "checkout", "--", path],
                              check=False).returncode == 0
    print(f"::warning::{label}: {reason}. "
          f"{'Kept the published file' if restored else 'COULD NOT restore ' + path}"
          f" — a source has almost certainly stopped answering.")
    return "collapsed, kept published" if restored else "collapsed, NOT restored"


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

    # Rebasing generated files against a moving branch is the wrong shape
    # and it cost a whole night: a rebase stopped on a conflict in a guide,
    # left .git/rebase-merge behind, and every later attempt died on
    # "there is already a rebase-merge directory". The build kept producing
    # correct files and never published one of them.
    #
    # Nothing here needs merging. These XML files are written whole by the
    # pass that just ran, so on a rejection the answer is simply: take the
    # branch as it now stands, put our files back on top, commit that.
    built = {path: open(path, "rb").read()
             for _, _, path in GENERATORS + [("", "", MERGED)]
             if os.path.exists(path)}

    for attempt in range(1, 6):
        if subprocess.run(["git", "push", "origin", f"HEAD:{branch}"],
                          check=False).returncode == 0:
            print(f"pushed on attempt {attempt}")
            return True
        print(f"push rejected, rebuilding on top of {branch} "
              f"({attempt}/5)")

        # Leave no half-finished rebase behind, whoever started it.
        subprocess.run(["git", "rebase", "--abort"], check=False,
                       capture_output=True)
        subprocess.run(["git", "merge", "--abort"], check=False,
                       capture_output=True)
        subprocess.run(["git", "fetch", "origin", branch], check=False)
        subprocess.run(["git", "reset", "--hard", "FETCH_HEAD"], check=False)

        # Their code and everything else; our guides.
        for path, blob in built.items():
            with open(path, "wb") as handle:
                handle.write(blob)
        subprocess.run(["git", "add", "--", "*.xml"], check=False)
        if subprocess.run(["git", "diff", "--cached", "--quiet"],
                          check=False).returncode == 0:
            print("the branch already carries these guides")
            return True
        subprocess.run(["git", "commit", "-m", "Update every EPG"],
                       check=False)
        time.sleep(2 + attempt * 2)
    print("::error::could not push after five attempts")
    return False


def build_once() -> bool:
    """One pass: every generator, then the merge, then a push."""
    started = time.monotonic()
    print(f"Building every guide — {datetime.now(UTC):%Y-%m-%d %H:%M} UTC, "
          f"{len(GENERATORS)} generators")

    ceilings: dict = {}
    if os.path.exists(CEILINGS_FILE):
        try:
            ceilings = json.load(open(CEILINGS_FILE, encoding="utf-8"))
        except Exception as exc:
            print(f"::warning::{CEILINGS_FILE} unreadable ({exc}) — this pass "
                  f"can only catch a collapse by row count, not by content")

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
            if outcome == "ok":
                collapsed = keep_published_if_collapsed(label, output, ceilings)
                if collapsed:
                    outcome = collapsed
                else:
                    # Only on a file this pass is actually publishing: a
                    # restored file is already whole and must not be touched.
                    note = close_gaps_in(label, output)
                    if note:
                        outcome = f"ok, {note}"
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
