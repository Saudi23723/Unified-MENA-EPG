#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ONE PUBLISHING PASS, whole: build, encode, verify, publish.

The workflow used to spell this out — twenty-six steps naming a channel
each, then the same names again inside the ticker's loop. channels.py
says why that could not be kept honest. This is the other half of the
answer: the sequence itself is written once, here, and the workflow
calls it twice — once for the first pass, once every five minutes for
the rest of the window. The two cannot drift, because they are the same
file.

A FAULT IN ONE CHANNEL DOES NOT FREEZE THE OTHERS. That principle is
already in the repository — quarantine_screens.py holds back the one
screen a gate names and lets the rest go out, written after five gates
about Turkish PPV froze all thirteen channels' boards twice in one
evening. It stopped at the gate, though: ABOVE the gate, the build and
encode loops ran under `set -e`, so one channel's source answering
badly killed the pass before anything was published, and every channel
kept yesterday's picture because one of them had a bad minute.

So a build that fails here costs its own channel and nothing else: that
channel keeps the boards it already has, the others are rebuilt, and
the pass goes on to publish. The same for an encode. What still stops
the pass is what should: EVERY build failing, which is not one bad
source but something systemic, and a gate failure that names no screen,
which is the one case quarantine_screens cannot narrow.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

GATE_LOG = "/tmp/gate.log"
MANUAL_TICKER_WINDOW = 165 * 60
MARK_CADENCE = 60
FULL_PASS_CADENCE = 5 * 60
TICKER_CHILD = "ONE_PASS_TICKER_CHILD"


def run(*command: str) -> int:
    """One command, its output straight through, its exit code back."""
    print(f"\n───── {' '.join(command)} ─────", flush=True)
    return subprocess.call([sys.executable, "-u", *command])


def catch_up() -> None:
    """Take whatever landed on main since this run checked out.

    THE ONE THING THAT WAS NOT AUTOMATIC, and it is the reason a fix
    merged at 09:46 was still not on the television at 09:57 with a run
    healthily in progress the whole time.

    A workflow's steps are frozen when a run starts, and so was its
    CODE: publish_screens only reset to main when a push was rejected,
    which is luck rather than design. If its pushes went through, a run
    kept the code it checked out for the whole 165-minute window — so
    every merge waited for that window to end, or for somebody to
    cancel the run and dispatch another by hand. Which is what I kept
    doing, and what "Everything to be automatic from now on" is about.

    So every pass starts by fast-forwarding to main. FAST-FORWARD ONLY,
    deliberately: if this run has a commit of its own that has not been
    pushed yet — a pass whose publish failed — the merge refuses and
    the pass carries on with what it has rather than throwing that work
    away. Nothing is ever discarded to take an update.
    """
    fetched = subprocess.call(["git", "fetch", "--quiet", "origin", "main"])
    if fetched != 0:
        print("::warning::could not reach origin — this pass uses the code "
              "it already has")
        return
    was = subprocess.run(["git", "rev-parse", "HEAD"], text=True,
                         capture_output=True).stdout.strip()
    moved = subprocess.call(["git", "merge", "--ff-only", "--quiet",
                             "origin/main"])
    now = subprocess.run(["git", "rev-parse", "HEAD"], text=True,
                         capture_output=True).stdout.strip()
    if moved != 0:
        print("::warning::this run has work of its own not yet pushed — "
              "keeping it and building on the code in hand")
    elif was != now:
        print(f"───── caught up to main: {was[:8]} -> {now[:8]} ─────",
              flush=True)


def manual_ticker_needed(environ=None) -> bool:
    """A manual Actions run must cover the same window as a scheduled one.

    GitHub keeps only one pending run in a concurrency group. A manual
    repair can replace the pending scheduled successor; if the manual run
    exits after its first pass, LIVE/NEXT/FINISHED then freeze until another
    cron event happens to arrive. A child full pass must not start another
    ticker recursively.
    """
    environ = os.environ if environ is None else environ
    return (
        environ.get("GITHUB_ACTIONS") == "true"
        and environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        and environ.get(TICKER_CHILD) != "1"
    )


def keep_manual_run_alive(
        *, window_seconds=MANUAL_TICKER_WINDOW,
        mark_cadence=MARK_CADENCE,
        pass_cadence=FULL_PASS_CADENCE,
        clock=time.monotonic, sleeper=time.sleep,
        caller=subprocess.call) -> None:
    """Keep a manual repair publishing until its queued successor can run.

    This mirrors the scheduled workflow's ticker without requiring workflow
    file permissions: marks are checked every minute and the full source,
    board, HLS and gate pass is rerun every five minutes. Full-pass children
    carry TICKER_CHILD so they return normally instead of recursing.

    The injected clock/sleeper/caller make the timing testable instantly.
    """
    if not manual_ticker_needed():
        return

    deadline = clock() + window_seconds
    last_pass = clock()
    pass_no = 1
    print("\n───── manual run owns the status ticker ─────", flush=True)

    while clock() < deadline:
        while (clock() - last_pass < pass_cadence
               and clock() < deadline):
            sleeper(min(mark_cadence, max(0, deadline - clock())))
            if clock() >= deadline:
                break
            code = caller([sys.executable, "-u", "flip_marks.py"])
            if code != 0:
                print("::warning::a flip did not finish — the next full "
                      "pass redraws it")

        if clock() >= deadline:
            break

        last_pass = clock()
        pass_no += 1
        print(f"───── manual ticker pass {pass_no} ─────", flush=True)
        child_env = os.environ.copy()
        child_env[TICKER_CHILD] = "1"
        code = caller(
            [sys.executable, "-u", "one_pass.py"], env=child_env)
        if code != 0:
            print(f"::warning::manual ticker pass {pass_no} did not finish "
                  "— whatever it published stands")

    print(f"───── manual ticker window ended after {pass_no} pass(es) ─────",
          flush=True)


def main() -> int:
    catch_up()

    import channels
    import match_screen_video

    left = channels.unclaimed()
    if left:
        print(f"::warning::registered but nothing builds them: {left}")

    # ---- every channel, and one failure is one channel -----------------
    failed_builds = []
    for module in channels.BUILDS:
        if not os.path.exists(f"{module}.py"):
            # The file went while this run was in flight. That is a
            # channel that no longer exists, not an error.
            print(f"::warning::{module}.py is no longer on main — skipped")
            continue
        if run(f"{module}.py") != 0:
            failed_builds.append(module)
            print(f"::warning::{module} did not build — it keeps the boards "
                  f"it has; the other channels carry on")

    built = [m for m in channels.BUILDS if os.path.exists(f"{m}.py")]
    if built and len(failed_builds) == len(built):
        print("::error::every channel failed to build — that is not one bad "
              "source, and nothing is published on it")
        return 1

    # ---- every screen the encoder knows, read live, SIDE BY SIDE ------
    #
    # THE ENCODES ARE MOST OF THE WAIT, and the wait is what makes the
    # live mark late. A board is a picture inside an encoded reel, so it
    # cannot change on its own — مباشر appears on the television only
    # when a pass redraws that board and re-encodes it. Measured over
    # two hours of real publishes, passes landed every 9 to 17 minutes,
    # median 11, so the mark could be a quarter of an hour behind the
    # kickoff. "لما يجي الوقت تحول طوالي ل لايف".
    #
    # Measured inside one run: nine builds took 84 seconds, the gate 21,
    # the publish 179 — and NINETEEN ENCODES TOOK 394, one after another
    # on a four-core machine.
    #
    # They do not need to be. A screen owns its own boards, its own
    # segments, its own playlist and its own stamp, all under its own
    # prefix — that separation is what the whole quarantine design rests
    # on — so no two of them touch the same file. Run side by side they
    # finish in a fraction of the time, and the pass gets shorter by
    # most of six minutes.
    #
    # Each screen's output is held and printed whole when it finishes,
    # because interleaved ffmpeg logs from nineteen encodes are a log
    # nobody can read afterwards.
    workers = min(4, (os.cpu_count() or 2))
    screens = list(match_screen_video.SCREENS)

    def encode(screen):
        done = subprocess.run(
            [sys.executable, "-u", "match_screen_video.py", screen],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        return screen, done.returncode, done.stdout

    print(f"\n───── encoding {len(screens)} screen(s), {workers} at a time "
          f"─────", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for screen, code, output in pool.map(encode, screens):
            print(f"\n───── match_screen_video.py {screen} ─────", flush=True)
            sys.stdout.write(output)
            if code != 0:
                print(f"::warning::{screen} did not encode — the gate below "
                      f"decides whether it may still be published")

    # ---- the gate, and the quarantine it feeds -------------------------
    with open(GATE_LOG, "w", encoding="utf-8") as log:
        print("\n───── channel_gate_selftest.py ─────", flush=True)
        gate = subprocess.Popen(
            [sys.executable, "-u", "channel_gate_selftest.py"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in gate.stdout:
            sys.stdout.write(line)
            log.write(line)
        status = gate.wait()

    if status != 0:
        # A gate that names a screen holds back THAT screen and lets the
        # rest go out. A gate that names none is about the whole build,
        # and quarantine_screens says so by failing — which is the one
        # thing above that still stops this pass publishing.
        if run("quarantine_screens.py", GATE_LOG) != 0:
            print("::error::the gate failed and named no screen — "
                  "nothing is published on this pass")
            return 1

    # Source-level invariants are not enough for a transport stream. Decode
    # every generated screen through ffmpeg across a complete reel and its
    # wrap, and refuse publication on missing pages, malformed live-window
    # geometry, B-frame overlap, corrupt TS boundaries or non-monotonic DTS.
    if run("tools/audit_dashboard_hls.py") != 0:
        print("::error::dashboard HLS playback audit failed — nothing is "
              "published on this pass")
        return 1

    # ---- the playlists, then the push ---------------------------------
    # Written AFTER the gate so a quarantined screen is not listed
    # pointing at a stream that was put back. Tolerated if it fails and
    # both files are still on disk, exactly as the workflow tolerated it.
    if run("sports_dashboard_m3u.py") != 0:
        for name in ("ai_sports_dashboard.m3u", "ai_sports_dashboard_dubai.m3u"):
            if not (os.path.exists(name) and os.path.getsize(name)):
                print(f"::error::{name} is missing and could not be written")
                return 1

    return run("publish_screens.py")


if __name__ == "__main__":
    status = main()
    if status == 0:
        keep_manual_run_alive()
    sys.exit(status)
