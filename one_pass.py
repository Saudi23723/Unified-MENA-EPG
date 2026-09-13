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

GATE_LOG = "/tmp/gate.log"


def run(*command: str) -> int:
    """One command, its output straight through, its exit code back."""
    print(f"\n───── {' '.join(command)} ─────", flush=True)
    return subprocess.call([sys.executable, "-u", *command])


def main() -> int:
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

    # ---- every screen the encoder knows, read live --------------------
    for screen in list(match_screen_video.SCREENS):
        if run("match_screen_video.py", screen) != 0:
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
    sys.exit(main())
