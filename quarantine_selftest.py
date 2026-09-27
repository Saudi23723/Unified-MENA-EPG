#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Does the quarantine hold back the right screen, and only that screen?

Written before the thing shipped, because the last time a guard went
into a publish workflow without one it was placed above the step that
installed what it imported, the job died in twenty seconds and channel
6 was dark for twenty-four minutes.

The two ways this can be wrong are opposite and both bad:

  TOO EAGER   a failure about the whole build gets blamed on a screen,
              one channel is held back, and a torn build publishes.
  TOO SHY     a failure that names a screen is not recognised, nothing
              publishes, and thirteen channels freeze for one — the
              fault this file exists to end.

So both are tested, on the REAL log of the run that caused this.
"""
import os
import sys

import quarantine_screens as q

FAILED = 0


def check(what, got, want):
    global FAILED
    ok = got == want
    FAILED += not ok
    print(f"  {'ok  ' if ok else 'BAD '} {what}"
          + ("" if ok else f"\n         got {got!r}, wanted {want!r}"))


# The gate's own output from run 34400636215, which froze every channel.
THE_REAL_LOG = """
7 gate(s) let something through:

  SCREEN: 'dubai_turkish_ppv_ the playlist names one segment per board' -> 6, expected 0
  SCREEN: "dubai_turkish_ppv_ every real programme points at one of the screen's own boards" -> [0], expected []
  SCREEN: 'dubai_turkish_ppv_ and every board it points at is published' -> [0], expected []
  SCREEN: 'dubai_turkish_ppv_ one manifest line per day the guide programmes' -> 0, expected 1
  SCREEN: "dubai_turkish_ppv_ each programme points at its day's first board" -> [0], expected []
  ROW: 'and there the competition changes nothing, because it is not drawn' -> False, expected True
  ALWAN: "and its Toulouse - Lille can now find the board's" -> [], expected ['تولوز - ليل']

A guide that publishes another channel's match is worse than one that publishes nothing.
"""

ONLY_ONE_SCREEN = """
5 gate(s) let something through:

  SCREEN: 'dubai_turkish_ppv_ the playlist names one segment per board' -> 6, expected 0
  SCREEN: "dubai_turkish_ppv_ every real programme points at one of the screen's own boards" -> [0], expected []
  SCREEN: 'dubai_turkish_ppv_ and every board it points at is published' -> [0], expected []
  SCREEN: 'dubai_turkish_ppv_ one manifest line per day the guide programmes' -> 0, expected 1
  SCREEN: "dubai_turkish_ppv_ each programme points at its day's first board" -> [0], expected []
"""

TWO_SCREENS = """
2 gate(s) let something through:

  SCREEN: 'f1_ the playlist names one segment per board' -> 3, expected 0
  SCREEN: 'ball_sports_ and every board it points at is published' -> [0], expected []
"""

print("Reading the failures out of a gate log")
check("every failing gate is found, and the prose after them is not",
      len(q.failures_in(THE_REAL_LOG)), 7)
check("a log with no tally yields nothing to act on",
      q.failures_in("all gates hold\n"), [])

print("\nBlaming the right screen")
check("the Dubai screen is blamed, not the first-clock one whose "
      "prefix is inside its name",
      q.screen_named_in(
          "SCREEN: 'dubai_turkish_ppv_ the playlist names one segment "
          "per board' -> 6, expected 0"),
      "dubai_turkish_ppv")
check("and the first-clock screen is still blamed for its own",
      q.screen_named_in("SCREEN: 'turkish_ppv_ one manifest line' -> 0"),
      "turkish_ppv")
check("a gate that names no screen is blamed on no screen",
      q.screen_named_in(
          "ROW: 'and there the competition changes nothing' -> False"),
      None)
check("nor is the Alwan one, which is about a guide and not a screen",
      q.screen_named_in(
          "ALWAN: \"and its Toulouse - Lille can now find the board's\""),
      None)

print("\nDeciding what to do with a whole log")

# THE DECISION IS ASKED OF main(), NOT REBUILT HERE. This file first
# reimplemented the blame loop locally and checked its own copy, so
# deleting the whole-build guard out of main() changed nothing any
# check could see: the injection ran and the suite still said every
# guard held. A test that rebuilds the thing it is testing tests the
# rebuild. So main() is run, on a real log file, in a scratch
# repository of its own — it moves files, and it is not going to move
# this one's.


def verdict(log):
    """What main() does with this log: (screens held back, published)."""
    import os
    import subprocess
    import tempfile

    was = os.getcwd()
    with tempfile.TemporaryDirectory() as room:
        os.chdir(room)
        try:
            subprocess.run(("git", "init", "-q", "."), check=True)
            for name, value in (("user.email", "t@t"), ("user.name", "t")):
                subprocess.run(("git", "config", name, value), check=True)
            os.makedirs("boards")
            os.makedirs("stream")
            # One published file per screen, so a held-back screen has
            # something to be put back to and the count is real.
            for prefix, xml, playlist, _stamp in q.SCREENS.values():
                for path in (f"boards/{prefix}0.png",
                             f"stream/{playlist}", xml):
                    with open(path, "w") as handle:
                        handle.write("published\n")
            subprocess.run(("git", "add", "-A"), check=True)
            subprocess.run(("git", "commit", "-qm", "published"),
                           check=True)
            # This pass rebuilt every one of them, and drew a SECOND
            # board for each that was never published. A held-back
            # screen's new board has no committed version to return to,
            # so it has to be removed rather than left: a board the
            # manifest does not count sits on the wrong side of the
            # boards-versus-manifest gate for ever. Without one of these
            # in the room, deleting that branch out of hold_back changed
            # nothing any check could see.
            for prefix, xml, playlist, _stamp in q.SCREENS.values():
                for path in (f"boards/{prefix}0.png",
                             f"stream/{playlist}", xml):
                    with open(path, "w") as handle:
                        handle.write("fresh\n")
                with open(f"boards/{prefix}1.png", "w") as handle:
                    handle.write("never published\n")
            with open("gate.log", "w") as handle:
                handle.write(log)

            sys.argv = ["quarantine_screens.py", "gate.log"]
            code = q.main()

            held = sorted(
                name for name, screen in q.SCREENS.items()
                if open(screen[1]).read().strip() == "published")
            # A screen that was held back must have lost its unpublished
            # board; one that published must have kept it.
            strays = sorted(
                name for name, screen in q.SCREENS.items()
                if os.path.exists(f"boards/{screen[0]}1.png"))
            return held, code == 0, strays
        finally:
            os.chdir(was)


check("the real log publishes NOTHING: two of its seven gates are "
      "about the whole build",
      verdict(THE_REAL_LOG)[1], False)
check("and it holds back no screen when it is publishing nothing",
      verdict(THE_REAL_LOG)[0], [])
one = verdict(ONLY_ONE_SCREEN)
check("with those two gates now fixed, the same run holds back "
      "Turkish PPV alone and publishes",
      one[:2], (["dubai_turkish_ppv"], True))
check("the held-back screen's unpublished board goes with it, and "
      "every other screen keeps its own",
      "dubai_turkish_ppv" not in one[2] and len(one[2]) == len(q.SCREENS) - 1,
      True)
check("two broken screens hold back two, and the other fifteen go out",
      verdict(TWO_SCREENS)[:2], (["ball_sports", "f1"], True))

print("\nEvery screen the publisher knows can be blamed for its own gate")
missed = [name for name, screen in q.SCREENS.items()
          if q.screen_named_in(f"SCREEN: '{screen[0]} something' -> x")
          != name]
check("no screen's prefix is swallowed by another's", missed, [])

print("\nall quarantine guards hold" if not FAILED
      else f"\n{FAILED} guard(s) did not hold")
sys.exit(1 if FAILED else 0)
