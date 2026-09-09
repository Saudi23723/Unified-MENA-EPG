#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Channel 6, held still — the channel that had no test.

WHY THIS FILE EXISTS. Every other channel here goes through
publish_screens and answers to channel_gate_selftest. Channel 6 was the
exception: its own workflow, its own hand-rolled git plumbing, its own
generator, and nothing checking any of it. Three separate faults reached
the television through that gap, and each was found by a viewer rather
than by a test:

  1. "git reset --soft origin/main" left the index holding the tree the
     runner had checked out hours earlier, so the commit carried the
     WHOLE index. One refresh changed 184 files and deleted 31 —
     including every dubai_f1 board, segment and playlist. Channel 6 was
     deleting channel 11.

  2. "git add $PATHS" with an unquoted glob is expanded by BASH against
     the files that exist, so a segment the generator had just deleted
     could never match it and its deletion was never staged. Fifty stale
     segments accumulated with no playlist naming them.

  3. The reel ran twelve minutes and was rebuilt every eight, so no
     viewer could reach the end of one before it was replaced, and any
     one flight came round once every twelve minutes at best.

All three are the same shape: an invariant nobody had written down.
They are written down here. Run it with `python channel6_selftest.py`;
it needs no network and touches nothing outside a temporary directory.
"""

from __future__ import annotations

import glob
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORKFLOW = os.path.join(HERE, ".github/workflows/flight_tracker_daily.yml")
GENERATOR = os.path.join(HERE, "tools/generate_flight_tracker.py")
STREAM = os.environ.get("CH6_OUT") or os.path.join(HERE, "stream")
PLAYLISTS = ("flight_tracker", "dubai_flight_tracker")

class CannotRun(Exception):
    """The checks could not be run at all — as opposed to failing."""


failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{f' — {detail}' if detail else ''}")
        failures.append(name)


def git(*args, cwd, **kw):
    return subprocess.run(("git",) + args, cwd=cwd, capture_output=True,
                          text=True, **kw)


# ------------------------------------------------------- the commit step

def the_commit_step() -> int:
    """The git plumbing that publishes this channel, proved in a real repo.

    NOT A READING OF THE WORKFLOW — an actual repository, an actual
    stale checkout, the actual commands. The two faults this catches
    both looked correct on the page and were only wrong when run.
    """
    print("\nthe commit step")
    text = open(WORKFLOW, encoding="utf-8").read()

    # The dangerous forms, named so a future edit cannot reintroduce them
    # by accident. Both of these shipped and both broke something.
    check("it does not reset --soft onto the branch it is pushing to",
          "reset --soft" not in text,
          "--soft keeps the stale index and commits the whole of it")
    check("it does not hand an unquoted glob to git add",
          not re.search(r"git add\s+\$PATHS\b", text),
          "bash expands it against files that exist, so deletions vanish")
    check("it resets the index to the branch it is pushing to",
          "git reset --mixed origin/main" in text)
    check("it stages deletions as well as changes",
          re.search(r'git add -A -- "\$\{PATHS\[@\]\}"', text) is not None)
    check("it refuses a commit carrying paths that are not channel 6's",
          "refusing to push it" in text and "--cached --name-only" in text)

    # THE STEP ORDER, because getting it wrong took the channel off air
    # for twenty minutes. This selftest loads the generator and the
    # generator imports PIL, so a step that runs it before the
    # dependencies are installed does not guard the channel — it kills
    # it, in twenty seconds, every single run.
    try:
        import yaml
        steps = (yaml.safe_load(open(WORKFLOW, encoding="utf-8"))
                 ["jobs"]["build"]["steps"])
        names = [str(s.get("name") or s.get("uses") or "") for s in steps]
        installs = next(i for i, n in enumerate(names)
                        if "Install dependencies" in n)
        guards = next(i for i, n in enumerate(names)
                      if "invariants" in n.lower())
        check("the invariants are checked AFTER the dependencies "
              "they need", installs < guards,
              f"install at step {installs}, check at step {guards}")
        publishes = next(i for i, n in enumerate(names)
                         if "Refresh, render and publish" in n)
        check("and before anything is published", guards < publishes,
              f"check at {guards}, publish at {publishes}")
    except StopIteration:
        check("the publish workflow still has the steps this relies on",
              False, "a step was renamed")
    except ImportError:
        print("  skip  step order — pyyaml is not installed here")

    with tempfile.TemporaryDirectory() as room:
        git("init", "-q", ".", cwd=room)
        git("config", "user.email", "t@t", cwd=room)
        git("config", "user.name", "t", cwd=room)
        os.makedirs(f"{room}/stream")
        os.makedirs(f"{room}/boards")
        for name in ("flight_tracker_0.ts", "flight_tracker_1.ts",
                     "flight_tracker_2.ts"):
            open(f"{room}/stream/{name}", "w").write("old")
        open(f"{room}/stream/flights.json", "w").write("{}")
        open(f"{room}/boards/another_channel.png", "w").write("keep me")
        git("add", "-A", cwd=room)
        git("commit", "-qm", "the runner's checkout", cwd=room)
        git("branch", "-q", "-f", "origin-main", cwd=room)

        # MAIN MOVES ON while this runner is still looping: another
        # channel publishes a board. This is the situation that deleted
        # channel 11 — the runner's index is now behind.
        git("checkout", "-q", "-b", "elsewhere", cwd=room)
        open(f"{room}/boards/eleventh_channel.png", "w").write("new board")
        git("add", "-A", cwd=room)
        git("commit", "-qm", "channel 11 publishes", cwd=room)
        git("branch", "-q", "-f", "origin-main", "elsewhere", cwd=room)
        git("checkout", "-q", "-", cwd=room)

        # THE PASS: a shorter reel than last time — one segment rewritten,
        # one dropped entirely.
        open(f"{room}/stream/flight_tracker_0.ts", "w").write("fresh")
        os.remove(f"{room}/stream/flight_tracker_2.ts")

        git("reset", "--mixed", "origin-main", cwd=room)
        git("add", "-A", "--", "stream/flights.json", "stream/flight_tracker*",
            cwd=room)
        staged = [l.split("\t")[-1] for l in
                  git("diff", "--cached", "--name-status",
                      cwd=room).stdout.strip().splitlines()]
        marks = dict(l.split("\t")[0][:1] + "\t" + l.split("\t")[-1]
                     for l in [])  # readability only
        status = git("diff", "--cached", "--name-status", cwd=room).stdout

        check("a pass cannot delete another channel's board",
              "boards/eleventh_channel.png" not in status,
              status.replace("\n", " | "))
        check("a segment the reel no longer names IS staged as deleted",
              "D\tstream/flight_tracker_2.ts" in status,
              status.replace("\n", " | "))
        check("a rewritten segment is staged as modified",
              "M\tstream/flight_tracker_0.ts" in status)
        check("nothing outside channel 6 is staged at all",
              all(p.startswith("stream/flight") for p in staged),
              ", ".join(p for p in staged
                        if not p.startswith("stream/flight")))

        # AND THE GUARD, on an index that has been contaminated anyway.
        open(f"{room}/boards/sneaked_in.png", "w").write("x")
        git("add", "boards/sneaked_in.png", cwd=room)
        listed = git("diff", "--cached", "--name-only", cwd=room).stdout
        foreign = [p for p in listed.split()
                   if not re.match(r"^stream/(dubai_)?flight", p)]
        check("the guard sees a foreign path in the staged list",
              foreign == ["boards/sneaked_in.png"], str(foreign))
    return 0


# ------------------------------------------------------------- the reel

def the_shared_installer() -> int:
    """No workflow may let a third-party apt repo take the service down.

    On the 9th of September 2026 Google served a Packages.gz whose hash
    did not match its own Release file. apt-get update returned 100 and
    all three publishing workflows died inside thirty seconds — for a
    repository this service does not use, hosting a browser it does not
    install. Every workflow began "apt-get update && apt-get install",
    so every workflow was exposed to it.

    They all go through tools/apt_install.sh now, which drops the
    sources this repository never installs from, refreshes tolerantly,
    and lets the INSTALL decide whether the step failed. This checks
    that none of them has drifted back.
    """
    print("\nhow packages are installed")
    here = os.path.join(HERE, ".github/workflows")
    script = os.path.join(HERE, "tools/apt_install.sh")
    check("the shared installer exists", os.path.exists(script))
    if os.path.exists(script):
        check("and is executable", os.access(script, os.X_OK))
        body = open(script, encoding="utf-8").read()
        check("it refreshes tolerantly", "|| " in body
              or "if ! sudo apt-get update" in body)
        check("and installs strictly",
              re.search(r"sudo apt-get install -y[^\n]*\"\$@\"", body)
              is not None)

    offenders = []
    for name in sorted(os.listdir(here)):
        if not name.endswith((".yml", ".yaml")):
            continue
        text = open(os.path.join(here, name), encoding="utf-8").read()
        if "apt-get" in text:
            offenders.append(name)
    check("no workflow calls apt-get directly", not offenders,
          ", ".join(offenders))
    return 0


def the_reel() -> int:
    """What the reel may and may not do, whatever the traffic is."""
    print("\nthe reel")
    spec = importlib.util.spec_from_file_location("ch6", GENERATOR)
    g = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(g)
    except Exception as exc:                                  # noqa: BLE001
        # THE CHECK COULD NOT RUN. That is not evidence the channel is
        # broken, and a guard that takes the television off air when the
        # guard is what is broken is worse than no guard. Exit 2 says
        # "ask someone", exit 1 says "do not publish".
        print(f"  CANNOT RUN — the generator would not load: "
              f"{type(exc).__name__}: {exc}")
        raise CannotRun(str(exc)) from exc

    check("the reel is capped at half the refresh interval",
          g.MAX_REEL_SECONDS * 2 <= g.REFRESH_SECONDS,
          f"{g.MAX_REEL_SECONDS}s of {g.REFRESH_SECONDS}s")
    check("the cap is a whole number of pages",
          g.MAX_PAGES >= 1 and g.MAX_PAGES * g.PAGE_SECONDS
          <= g.MAX_REEL_SECONDS)

    def rows(airborne: int, landed: int) -> list[dict]:
        out = []
        for n in range(airborne):
            out.append({"code": "EK", "num": f"EK{n}", "o": "AAA", "d": "BBB",
                        "dep": n % 1400, "arr": (n % 1400) + 30,
                        "ac": "A388", "api_status": "ACTIVE", "delay": 0})
        for n in range(landed):
            out.append({"code": "TK", "num": f"TK{n}", "o": "CCC", "d": "DDD",
                        "dep": n % 1400, "arr": (n % 1400) + 30,
                        "ac": "B77W", "api_status": "LANDED", "delay": 0})
        return out

    def reel(airborne, landed):
        # THE GENERATOR'S OWN ARITHMETIC, not a copy of it here. A test
        # that recomputes the page count is a test that can agree with
        # itself while the channel is wrong.
        flights = g.build_flights(rows(airborne, landed), 900)
        shown, held = g.on_the_reel(flights)
        return shown, held, g.pages_for(shown)

    shown, held, pages = reel(79, 237)
    check("a normal day fits inside the cap",
          pages <= g.MAX_PAGES, f"{pages} pages")
    check("every flight in the air is on the reel",
          sum(1 for f in shown if f["status"] == "IN FLIGHT") == 79)
    check("the landed that did not fit are counted, not silently dropped",
          held == 316 - len(shown), f"held {held}, shown {len(shown)}")

    # THE ONE THING THE CAP MAY NEVER DO: cut a flight that is moving.
    shown, held, pages = reel(316, 0)
    check("a sky full of aircraft keeps every one of them",
          len(shown) == 316 and held == 0, f"{len(shown)} shown, {held} held")
    check("and the cap gives way to do it", pages > g.MAX_PAGES)

    # THE LANDED TAIL MUST BE THE NEWEST ARRIVALS, never the morning's.
    flights = g.build_flights(rows(0, 200), 900)
    shown, held = g.on_the_reel(flights)
    kept = [f["arr"] for f in shown]
    dropped = [f["arr"] for f in flights if f not in shown]
    check("the landed kept are the most recent arrivals",
          not dropped or min(kept) >= max(dropped),
          f"kept from {min(kept) if kept else '-'}, "
          f"dropped up to {max(dropped) if dropped else '-'}")

    # THE QUIET CASES, which are what a dead feed actually hands over.
    for name, (air, done) in (("an empty feed", (0, 0)),
                              ("three flights", (1, 2)),
                              ("a night with nothing airborne", (0, 40))):
        try:
            shown, held, pages = reel(air, done)
            check(f"{name} draws a sane reel",
                  pages >= 1 and len(shown) <= air + done,
                  f"{pages} pages, {len(shown)} rows")
        except Exception as exc:                              # noqa: BLE001
            check(f"{name} draws a sane reel", False,
                  f"{type(exc).__name__}: {exc}")

    check("the page count is computed in exactly one place",
          len(re.findall(r"math\.ceil\(len\([a-z_]+\) / PER_PAGE\)",
                         open(GENERATOR, encoding="utf-8").read())) == 1,
          "three copies of this sum is how the length and the paging "
          "came to disagree")
    check("the generator deletes segments its reel no longer names",
          "no longer names" in open(GENERATOR, encoding="utf-8").read())
    return 0


# --------------------------------------------------- what is on the disk

def the_published_reel() -> int:
    """The playlists and the segments in this repository must agree."""
    print("\nwhat is published")
    named: set[str] = set()
    for base in PLAYLISTS:
        path = os.path.join(STREAM, f"{base}.m3u8")
        if not os.path.exists(path):
            check(f"{base}.m3u8 exists", False)
            continue
        rows = [l.strip() for l in open(path)
                if l.strip().endswith(".ts")]
        named |= set(rows)
        check(f"{base} names at least one segment", bool(rows))
        missing = [s for s in rows
                   if not os.path.exists(os.path.join(STREAM, s))]
        check(f"every segment {base} names exists", not missing,
              ", ".join(missing[:4]))
        seconds = sum(float(x) for x in
                      re.findall(r"#EXTINF:([0-9.]+)", open(path).read()))
        check(f"{base} is shorter than the interval that replaces it",
              seconds <= 8 * 60, f"{seconds:.0f}s")
        numbers = [int(re.search(r"_(\d+)\.ts$", s).group(1)) for s in rows]
        check(f"{base} runs 0, 1, 2 … in order",
              numbers == list(range(len(numbers))), str(numbers[:6]))

    on_disk = {os.path.basename(p) for p in
               glob.glob(os.path.join(STREAM, "flight_tracker_*.ts"))
               + glob.glob(os.path.join(STREAM, "dubai_flight_tracker_*.ts"))}
    orphans = sorted(on_disk - named)
    check("no segment is published that no playlist names",
          not orphans, f"{len(orphans)} orphan(s): {', '.join(orphans[:4])}")
    return 0


def main() -> int:
    # --published tests only what is on the disk right now, which is what
    # the workflow runs after it renders and BEFORE it pushes: a reel
    # that does not hold together must never reach the television, and
    # by then the source checks have already run once at job start.
    only_published = "--published" in sys.argv
    print("channel 6 — the invariants that were only ever learned the "
          "hard way")
    try:
        if not only_published:
            the_commit_step()
            the_shared_installer()
            the_reel()
        the_published_reel()
    except CannotRun as why:
        print(f"\nthe checks could not be run: {why}")
        print("exit 2 — this says nothing about whether channel 6 is "
              "sound, only that nothing here could look")
        return 2
    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("channel 6 holds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
