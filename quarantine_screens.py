#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One broken screen holds back one screen, not the whole publish.

THE FAULT THIS REPLACES
-----------------------
The publish workflow ran the screen gate and, on any failure at all,
stopped. That is the right instinct — a torn screen must not reach a
player — but it was applied to the wrong unit. On 2026-09-09 the
Turkish PPV channel's guide ran empty while its playlist still claimed
six segments, and five gates said so:

    SCREEN: 'dubai_turkish_ppv_ the playlist names one segment per board'
    SCREEN: 'dubai_turkish_ppv_ every real programme points at one of ...'
    ... three more, every one of them naming the same screen

The step exited 1, `Publish refreshed indicators` never ran, and all
THIRTEEN channels' boards froze on a fault that belonged to one of
them. Twice that evening. The reader's word for it was that the gates
"keep sending me emails and failures", and they were right: the gate
found a real break and then punished twelve innocent screens for it.

WHAT THIS DOES
--------------
A gate that names a screen is about that screen. So the failures are
read, each one is matched to the screen it names, and:

  * if EVERY failure names a screen, those screens are put back to what
    main already publishes — the reader keeps watching last hour's
    Turkish PPV rather than a torn one — and every other screen goes
    out on time. The publish proceeds.

  * if ANY failure names no screen, it is about the whole build and
    nothing is published, exactly as before. A rule that spans the
    screens is not something one channel can be blamed for.

Held back is not fixed. The screen stays broken and stays reported, and
the run is marked with a warning so the failure is still visible — it
simply stops taking the other channels down with it.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

from publish_screens import SCREENS, belongs_to_screen

# "  SCREEN: 'dubai_turkish_ppv_ the playlist names ...' -> 6, expected 0"
A_FAILURE = re.compile(r"^\s{2}([A-Z][A-Z0-9_]*): (.*)$")
# The gate's own closing line, which is not a failure.
A_TALLY = re.compile(r"^\d+ gate\(s\) let something through:")


def failures_in(log: str) -> list[str]:
    """Every failing gate line, from the tally onwards."""
    out, counting = [], False
    for line in log.splitlines():
        if A_TALLY.match(line.strip()):
            counting = True
            continue
        if not counting:
            continue
        found = A_FAILURE.match(line)
        if found:
            out.append(found.group(2))
    return out


def screen_named_in(failure: str) -> str | None:
    """Which screen this failure is about, if it is about one at all.

    LONGEST PREFIX WINS. "turkish_ppv_" is a substring of
    "dubai_turkish_ppv_", so the shorter one would claim the Dubai
    screen's failures and hold back the wrong channel.
    """
    best = None
    for name, screen in SCREENS.items():
        prefix = screen[0]
        if prefix in failure:
            if best is None or len(prefix) > len(SCREENS[best][0]):
                best = name
    return best


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(("git",) + args, capture_output=True, text=True)


def touched() -> list[tuple[str, str]]:
    """Every path this pass changed, as (status, path)."""
    out = []
    for line in git("status", "--porcelain").stdout.splitlines():
        if len(line) < 4:
            continue
        out.append((line[:2].strip(), line[3:].strip().strip('"')))
    return out


def hold_back(name: str) -> list[str]:
    """Put one screen's files back to what is already published."""
    screen = SCREENS[name]
    held = []
    for status, path in touched():
        if not belongs_to_screen(path, screen):
            continue
        if status == "??":
            # Built this pass and never published: it has no committed
            # version to go back to, so it goes away.
            try:
                os.remove(path)
            except OSError:
                continue
        else:
            if git("checkout", "HEAD", "--", path).returncode != 0:
                continue
        held.append(path)
    return held


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: quarantine_screens.py <gate log>", file=sys.stderr)
        return 2
    try:
        with open(sys.argv[1], encoding="utf-8") as handle:
            log = handle.read()
    except OSError as exc:
        print(f"::error::could not read the gate log ({exc})")
        return 1

    failures = failures_in(log)
    if not failures:
        print("::error::the gate failed but named no gate — "
              "not publishing on a report this file cannot read")
        return 1

    blamed: dict[str, list[str]] = {}
    unattributable = []
    for failure in failures:
        name = screen_named_in(failure)
        if name is None:
            unattributable.append(failure)
        else:
            blamed.setdefault(name, []).append(failure)

    if unattributable:
        print(f"::error::{len(unattributable)} gate(s) failed about the "
              f"whole build, not one screen — publishing nothing")
        for failure in unattributable:
            print(f"  {failure}")
        return 1

    for name, why in sorted(blamed.items()):
        held = hold_back(name)
        print(f"::warning::{name} is broken and is being held back — "
              f"it keeps the copy already published, and the other "
              f"screens publish as usual")
        for failure in why:
            print(f"    {failure}")
        print(f"    {len(held)} file(s) put back to the published copy")

    print(f"{len(blamed)} screen(s) held back, "
          f"{len(SCREENS) - len(blamed)} publishing normally")
    return 0


if __name__ == "__main__":
    sys.exit(main())
