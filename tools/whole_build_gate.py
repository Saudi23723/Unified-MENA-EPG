#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The one kind of gate failure that must never reach main.

The publishing pass runs channel_gate_selftest.py and hands its failures
to quarantine_screens.py. A failure that names a screen holds back that
screen alone. A failure that names NO screen is about the whole build,
and then NOTHING is published: every channel on the dashboard stays on
its last picture until somebody notices.

That happened on 30 September. A reader added to the Roya link read a
source the source gate did not list, the gate failed about the whole
build, and every screen froze for five hours — the first channel played
pages drawn three days earlier. CI ran the very same gate on the pull
request, but as advice (continue-on-error), so it merged green.

This runs the gate the way the pass does and fails ONLY on that kind of
failure. A screen's own failures are left to the pass, which already
holds a broken screen back by itself — and which, in CI, see a checkout
rather than the published reel, so they are not a reason to block.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main() -> int:
    os.chdir(ROOT)
    done = subprocess.run([sys.executable, "-u", "channel_gate_selftest.py"],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True)
    log = done.stdout
    import quarantine_screens as q
    failures = q.failures_in(log)
    whole = [f for f in failures if q.screen_named_in(f) is None]
    screens = len(failures) - len(whole)
    if done.returncode != 0 and not failures:
        print(log[-4000:])
        print("::error::the gate did not finish — the pass would publish "
              "nothing")
        return 1
    if whole:
        for failure in whole:
            print(f"::error::about the whole build, so the pass would "
                  f"publish NOTHING: {failure}")
        return 1
    print(f"no gate fails about the whole build — every channel keeps "
          f"publishing ({screens} per-screen failure(s) left to the pass)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
