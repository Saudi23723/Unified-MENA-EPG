#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Publish the screens, each one whole, or publish nothing.

THE FAULT THIS REPLACES
-----------------------
The publish step used to restore a rejected push path by path: it took
the list of files this pass had changed, reset the branch to the main
that had won the race, and checked out our version of each path on that
list. On paper that publishes exactly what this pass built. In practice
the list was the problem. A pass whose encoder had failed part way — a
step this workflow tolerates on purpose — carried an XML and fresh
boards in its diff but no segments, so the restore put our XML and our
boards on top of the other run's segments and stamped it one commit.
The screen gate calls that a torn screen, and it was: a playlist naming
segments no board here had produced, boards the playlist never showed,
a day count that matched neither side. What reached main was two runs
wearing one commit, and tomorrow's first board not showing was the
visible symptom.

THE FIX
-------
A screen is not a list of files. It is one thing in many files: its
XML, the boards drawn from that XML, the manifest that counts those
boards, the segments encoded from those boards, the playlist that names
those segments, the stamp that remembers their fingerprints, and the
two ledgers that keep retired segments answerable to a player still
holding a five-minute-cached playlist. So the restore here works per
SCREEN, not per path: if this pass touched a screen at all, the whole
screen comes back from our commit as one unit — boards, manifest,
segments, playlist, stamp, ledgers and XML together. If this pass did
not touch a screen, the branch keeps the winning run's copy of it
whole. No screen can end up half ours and half theirs, because no file
of a screen is ever restored without the rest of it.

Boards the winning run drew and ours did not are removed when their
screen is restored. A board PNG is not served to a player, so no cache
can be holding one, and a board the manifest does not count would sit
on the wrong side of the boards-versus-manifest count forever.
Segments the winning run encoded and ours did not are deliberately
KEPT: a player may still be holding the playlist that names them for
up to five minutes, so they are left to the encoder's sweep, which
stamps them into the ledger and retires them once the grace the ledger
already gives has run out.

Then all eight encoders run, not four. The old loop re-ran the first
clock's encoders only, so the UAE clock's screens were never reconciled
inside a retry: an orphaned dubai_ segment survived every attempt and
turned the gate red on the NEXT pass, before that pass had committed
anything.

And the gate runs inside the loop, before every push. Its verdict is
the publish decision: a pass whose gate fails on anything but the one
known Alwan row publishes NOTHING and the step goes red, rather than
pushing a screen that disagrees with its boards. The next pass is five
minutes away and builds from scratch. Nothing torn can reach main
through here, because nothing reaches main at all unless the gate says
the whole tree agrees with itself.
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
import time
from glob import glob

# The eight screens this workflow publishes. Each entry is the screen's
# board prefix, its XML, and the playlist and stamp files its encoder
# owns inside stream/. Kept here rather than read out of
# match_screen_video.SCREENS so that publishing never depends on the
# encoder module being importable; the two tables describe the same
# eight screens, and a ninth screen has to be added to both.
SCREENS: dict[str, tuple[str, str, str, str]] = {
    "today_matches": ("today_matches_", "today_matches_epg.xml",
                      "screen.m3u8", "board.sha256"),
    "other_sports": ("other_sports_", "other_sports_epg.xml",
                     "sports.m3u8", "sports.sha256"),
    "today_news": ("today_news_", "news_epg.xml",
                   "news.m3u8", "news.sha256"),
    "today_weather": ("today_weather_", "weather_epg.xml",
                      "weather.m3u8", "weather.sha256"),
    "dubai_matches": ("dubai_matches_", "dubai_matches_epg.xml",
                      "dubai_screen.m3u8", "dubai_board.sha256"),
    "dubai_sports": ("dubai_sports_", "dubai_sports_epg.xml",
                     "dubai_sports.m3u8", "dubai_sports.sha256"),
    "dubai_news": ("dubai_news_", "dubai_news_epg.xml",
                   "dubai_news.m3u8", "dubai_news.sha256"),
    "dubai_weather": ("dubai_weather_", "dubai_weather_epg.xml",
                      "dubai_weather.m3u8", "dubai_weather.sha256"),
}

# Files this pass owns that are not any one screen's: the weather
# channel's data, and the two playlists that point a player at all
# eight screens at once.
SHARED_FILES = ("weather.json",
                "ai_sports_dashboard.m3u",
                "ai_sports_dashboard_dubai.m3u")

COMMIT_MESSAGE = "Update today's matches"
BRANCH = "main"
ATTEMPTS = 5

# The one failure the gate may carry and this still publishes: the Alwan
# transliteration gap that predates every change here. If the gate ever
# fails on anything else — or Alwan starts failing on some other row —
# this is the string to update, after finding out why it changed.
KNOWN_GATE_FAILURES = (
    'ALWAN: "and its Toulouse - Lille can now find the board\'s" '
    "-> [], expected ['تولوز - ليل']",
)


def log(message: str) -> None:
    print(message, flush=True)


def error(message: str) -> None:
    print(f"::error::{message}", flush=True)


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True,
                          text=True, check=False)


def belongs_to_screen(path: str, screen: tuple[str, str, str, str]) -> bool:
    """Is this path part of this screen, by its name alone?

    The prefix covers the boards, the manifest, the segments and the two
    ledgers; the playlist and the stamp are named outright because the
    first clock's carry names a screen never gave them (screen.m3u8,
    board.sha256).
    """
    prefix, xml, playlist, stamp = screen
    if path == xml:
        return True
    if "/" not in path:
        return False
    where, name = path.split("/", 1)
    if where == "boards":
        return name.startswith(prefix)
    if where == "stream":
        return name.startswith(prefix) or name in (playlist, stamp)
    return False


def ours_owns(ours: str, screen: tuple[str, str, str, str]) -> list[str]:
    """Every path of this screen that exists in our commit."""
    prefix, xml, _playlist, _stamp = screen
    listed = git("ls-tree", "-r", "--name-only", ours, "--",
                 "boards", "stream")
    owned = [path for path in listed.stdout.splitlines()
             if path and belongs_to_screen(path, screen)]
    if git("cat-file", "-e", f"{ours}:{xml}").returncode == 0:
        owned.append(xml)
    return owned


def restore(ours: str, changed: list[str]) -> None:
    """Put this pass back on top of the branch, one whole screen at a time.

    `changed` is what our commit touched, taken from its own diff — the
    same list the old loop restored path by path, and the reason a torn
    commit was possible. Here it is only ever used to DECIDE, per
    screen, whether the screen comes back at all; what comes back is
    everything the screen has in our commit, not the paths on the list.
    """
    for name, screen in SCREENS.items():
        if not any(belongs_to_screen(path, screen) for path in changed):
            # This pass did not touch the screen, so the branch keeps
            # whatever the winning run published for it — whole, because
            # the winning run's own publish restored or built it whole.
            continue
        prefix = screen[0]
        owned = ours_owns(ours, screen)
        owned_set = set(owned)
        for path in owned:
            git("checkout", ours, "--", path)

        # Boards ours does not have, left on disk by the winning run:
        # gone. Nothing serves a board PNG to a player, so nothing can
        # be holding a cached one, and a board the manifest does not
        # count would fail the boards-versus-manifest count forever.
        # git rm takes the tracked ones; a stray from a killed run was
        # never tracked, so the filesystem takes that one.
        for path in glob(f"boards/{prefix}*"):
            posix = path.replace(os.sep, "/")
            if posix in owned_set:
                continue
            git("rm", "-f", "--quiet", "--ignore-unmatch", "--", posix)
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

        # Paths of this screen our pass REMOVED — in the diff, absent
        # from ours — leave the branch again, the same way they left
        # the first time.
        for path in changed:
            if belongs_to_screen(path, screen) and path not in owned_set:
                git("rm", "-f", "--quiet", "--ignore-unmatch", "--", path)

        # Segments ours does not have, left on disk by the winning run,
        # are deliberately kept. A player may hold the winning run's
        # playlist for up to five minutes, so the encoder's sweep —
        # which stamps them into the ledger and retires them once their
        # grace runs out — is the only thing allowed to take them.

    # Anything else this pass touched still goes back one path at a
    # time, which is safe for it: none of it is half of a pair.
    for path in changed:
        if any(belongs_to_screen(path, screen) for screen in SCREENS.values()):
            continue
        if git("cat-file", "-e", f"{ours}:{path}").returncode == 0:
            git("checkout", ours, "--", path)
        else:
            git("rm", "-f", "--quiet", "--ignore-unmatch", "--", path)


def reconcile_stream_with_the_encoder() -> None:
    """Run every screen's encoder, then stage what the sweeps changed.

    With the screens restored whole, the encoders are near no-ops — a
    fingerprint that has not changed re-encodes nothing — but each one
    still sweeps its own prefix: it stamps the winning run's leftover
    segments into the ledger, retires the ones whose grace has run out,
    and rewrites a playlist only if its boards really changed. All
    eight run, because the old loop's four left the UAE clock's screens
    unreconciled inside every retry.
    """
    for name in SCREENS:
        subprocess.run([sys.executable, "-u", "match_screen_video.py", name],
                       check=False)
    for directory in ("boards", "stream"):
        if os.path.isdir(directory):
            git("add", "-A", "--", directory)


def the_gate_allows_publishing() -> tuple[bool, list[str]]:
    """Run the screen gate and read its verdict from its own list.

    Imported rather than parsed: the gate's failures land in
    channel_gate_selftest.FAILURES as exact strings, and reading that
    list cannot mis-read a line of console output. The list is cleared
    first because the module keeps it across runs in one process.
    """
    import channel_gate_selftest as the_gate
    the_gate.FAILURES.clear()
    the_gate.main()
    unexpected = [failure for failure in the_gate.FAILURES
                  if failure not in KNOWN_GATE_FAILURES]
    return not unexpected, list(the_gate.FAILURES)


def stage() -> int:
    """Stage everything this pass built, exactly as the shell step did.

    Never a path that may not exist yet: git add fails the whole
    command on a pathspec that matches nothing, and on the first pass
    half of these are not there. today_matches_epg.xml is the one file
    this workflow cannot publish without, so a missing one is refused
    loudly rather than skipped quietly.
    """
    if not os.path.exists("today_matches_epg.xml"):
        error("today_matches_epg.xml is missing — refusing to publish "
              "anything")
        return 1
    git("add", "--", "today_matches_epg.xml")
    for path in ("other_sports_epg.xml", "news_epg.xml", "weather_epg.xml",
                 "dubai_matches_epg.xml", "dubai_sports_epg.xml",
                 "dubai_news_epg.xml", "dubai_weather_epg.xml",
                 *SHARED_FILES):
        if os.path.exists(path):
            git("add", "--", path)
    for directory in ("boards", "stream"):
        if os.path.isdir(directory):
            git("add", "--", directory)
    return 0


def nothing_is_staged() -> bool:
    return git("diff", "--cached", "--quiet").returncode == 0


def publish() -> int:
    if stage() != 0:
        return 1
    if nothing_is_staged():
        log("Nothing changed.")
        return 0
    git("commit", "-m", COMMIT_MESSAGE)

    for attempt in range(1, ATTEMPTS + 1):
        allowed, failures = the_gate_allows_publishing()
        if not allowed:
            error("the screen gate refused this pass — nothing is published")
            for failure in failures:
                log(f"  {failure}")
            return 1

        pushed = git("push", "origin", f"HEAD:{BRANCH}")
        if pushed.returncode == 0:
            log(f"Pushed on attempt {attempt}")
            return 0
        rejected = (pushed.stderr or pushed.stdout).strip().splitlines()
        if rejected:
            log(f"push rejected: {rejected[-1]}")
        if attempt == ATTEMPTS:
            break
        log(f"Push rejected, rebuilding on top of {BRANCH} "
            f"({attempt}/{ATTEMPTS - 1})")

        ours = git("rev-parse", "HEAD").stdout.strip()
        changed = [line.strip() for line in
                   git("diff", "--name-only", f"{ours}^", ours)
                   .stdout.splitlines() if line.strip()]
        git("fetch", "origin", BRANCH)
        git("reset", "--hard", f"origin/{BRANCH}")

        restore(ours, changed)
        reconcile_stream_with_the_encoder()

        if nothing_is_staged():
            log(f"{BRANCH} already carries this pass.")
            return 0
        git("commit", "-m", COMMIT_MESSAGE)
        time.sleep(random.randint(2, 6))

    error(f"could not push after {ATTEMPTS} attempts")
    return 1


if __name__ == "__main__":
    sys.exit(publish())
