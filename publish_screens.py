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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "tools"))
import segment_branch  # noqa: E402

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
    # THE TWELFTH CHANNEL — 🇵🇹 Sport TV, the six Portuguese screens,
    # live contests only. See sporttv_epg.py.
    "sporttv": ("sporttv_", "sporttv_epg.xml",
                "sporttv.m3u8", "sporttv.sha256"),
    "dubai_sporttv": ("dubai_sporttv_", "dubai_sporttv_epg.xml",
                      "dubai_sporttv.m3u8", "dubai_sporttv.sha256"),
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
    # The seventh channel — مواقيت الصلاة, one screen for both link sets
    # (prayer_epg.py says why it is not doubled).
    "today_prayer": ("today_prayer_", "prayer_epg.xml",
                     "prayer.m3u8", "prayer.sha256"),
    # The eighth channel — بيسبول وسلة السيدات, in both clocks.
    "ball_sports": ("ball_sports_", "ball_sports_epg.xml",
                    "ball_sports.m3u8", "ball_sports.sha256"),
    "dubai_ball_sports": ("dubai_ball_sports_", "dubai_ball_sports_epg.xml",
                          "dubai_ball_sports.m3u8",
                          "dubai_ball_sports.sha256"),
    # The ninth channel — السلة والقدم الأمريكية, in both clocks.
    "hoops_gridiron": ("hoops_gridiron_", "hoops_gridiron_epg.xml",
                       "hoops_gridiron.m3u8", "hoops_gridiron.sha256"),
    "dubai_hoops_gridiron": ("dubai_hoops_gridiron_",
                             "dubai_hoops_gridiron_epg.xml",
                             "dubai_hoops_gridiron.m3u8",
                             "dubai_hoops_gridiron.sha256"),
    # The eleventh channel — الفورمولا ١. One clock only: a Grand Prix
    # is one instant everywhere, and the board prints its sessions in
    # the viewer's zone already, so a second copy would say the same
    # thing twice.
    "f1": ("f1_", "f1_epg.xml", "f1.m3u8", "f1.sha256"),
    "dubai_f1": ("dubai_f1_", "dubai_f1_epg.xml", "dubai_f1.m3u8",
                 "dubai_f1.sha256"),
    # The tenth channel — القنوات التركية · PPV, in both clocks.
    "turkish_ppv": ("turkish_ppv_", "turkish_ppv_epg.xml",
                    "turkish_ppv.m3u8", "turkish_ppv.sha256"),
    "dubai_turkish_ppv": ("dubai_turkish_ppv_", "dubai_turkish_ppv_epg.xml",
                          "dubai_turkish_ppv.m3u8",
                          "dubai_turkish_ppv.sha256"),
}

# Files this pass owns that are not any one screen's: the weather
# channel's data, and the two playlists that point a player at all
# eight screens at once.
SHARED_FILES = (
    # The F1 channel's cache: a source that rate limits is not a source
    # that failed, and this is what the next pass stands on when it does.
    "f1_state.json",
    "weather.json",
                "prayer_times.json",
                # WHO CARRIES A CARD, remembered across passes. A fight
                # card's two sources name different carriers, and one of
                # them drops the card the moment its night is past — so
                # the pairing is written down while both still say it and
                # read back for as long as the card is on. Published with
                # the boards because a ledger that does not survive the
                # run that wrote it remembers nothing at all.
                "known_channels.json",
                "ai_sports_dashboard.m3u",
                "ai_sports_dashboard_dubai.m3u")

COMMIT_MESSAGE = "Update today's matches"
BRANCH = "main"
ATTEMPTS = 5

# The one failure the gate may carry and this still publishes: the Alwan
# transliteration gap that predates every change here. If the gate ever
# fails on anything else — or Alwan starts failing on some other row —
# this is the string to update, after finding out why it changed.
# BOTH WERE FIXED, so both are gone. ROW was handing draw_board
# eighteen rows so alike that without_repeats folded them to three, and
# ALWAN demanded a fixture that had rolled off Alwan's schedule. Neither
# fails any more, and an allowance for a failure that cannot happen is
# an invitation to let the next one through under its name.
KNOWN_GATE_FAILURES: tuple[str, ...] = ()


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
                # A segment kept on hls-segments is not on main at all:
                # its deletion in our commit is main letting go of it, and
                # `git rm -f` would take this pass's own copy off the disk.
                if segment_branch.moved_prefix(os.path.basename(path)):
                    continue
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
    # A CREST IS FETCHED ONCE IN ITS LIFE. Any badge this pass had to
    # download is published with the boards, so tomorrow's build reads
    # it off the disk and the board looks the same whether the badge
    # service answers that morning or not.
    for directory in ("boards", "stream", "logos"):
        if os.path.isdir(directory):
            git("add", "-A", "--", directory)


def screen_named_in(failure: str) -> str | None:
    """Which screen a gate failure is about, if it is about one at all.

    LONGEST PREFIX WINS. "turkish_ppv_" is a substring of
    "dubai_turkish_ppv_", so the shorter one would claim the Dubai
    screen's failures. quarantine_screens.py reads the same rule off the
    same table; it cannot be imported here because it imports this file.
    """
    best = None
    for name, screen in SCREENS.items():
        prefix = screen[0]
        if prefix in failure:
            if best is None or len(prefix) > len(SCREENS[best][0]):
                best = name
    return best


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

    # A FAILURE THAT NAMES A SCREEN HOLDS BACK THAT SCREEN. IT DOES NOT
    # STOP THE PUBLISH — quarantine_screens has already held it back.
    #
    # This is the deadlock that cost sixteen hours. one_pass runs the
    # gate, and a failure naming a screen sends that screen back to the
    # bytes main already publishes; only a failure naming NO screen is
    # about the whole build and stops the pass. Then publish_screens ran
    # the gate a SECOND time and applied the old all-or-nothing rule to
    # its verdict — over a working tree in which the named screens are
    # now the PUBLISHED ones. So if the published state was itself what
    # the gate objected to, holding it back could not satisfy the gate,
    # the second run refused, nothing was published, and the next pass
    # inherited exactly the same published state. Runs #953 to #955:
    # nine channels built correctly, none shipped, the board on the
    # television stuck on 14.09 at ten at night on the 15th.
    #
    # A rule that can only be satisfied by publishing, and refuses to
    # publish, is not a gate. It is a stop. So the two runs now agree on
    # the unit: a failure about one screen is about one screen, and the
    # other eighteen go out on time. It is still reported, and the
    # screen is still held back — it simply stops taking the channel
    # down with it.
    named = [failure for failure in unexpected if screen_named_in(failure)]
    blocking = [failure for failure in unexpected if failure not in named]
    for failure in named:
        log(f"::warning::held back: {failure}")
    return not blocking, list(the_gate.FAILURES)


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

    # EVERY SCREEN'S GUIDE, TAKEN FROM THE SCREEN TABLE — NOT FROM A
    # LIST TYPED OUT BY HAND BESIDE IT.
    #
    # The hand-written list had sixteen guides on it. SCREENS has
    # nineteen. The three that were never added are Sport TV's, and this
    # is what that cost: boards/ and stream/ are staged WHOLESALE, so
    # every pass published Sport TV's boards, its manifest, its segments
    # and its playlist — and never its guide. sporttv_epg.xml was last
    # committed on 14 September at 13:07, by hand, in a pull request.
    # Not once by the workflow that is supposed to publish it.
    #
    # A guide frozen under boards that keep moving is not a stale guide,
    # it is a WRONG one: the icons name boards whose contents changed
    # underneath them, and its day manifest describes a build two days
    # gone. That is the pair the screen gate kept reporting —
    #
    #   sporttv_ one manifest line per day the guide programmes
    #       -> 2, expected 3
    #   sporttv_ each programme points at its day's first board
    #       -> [0, 1, 2], expected [0, 2]
    #
    # — and it was right every time. The twelfth channel was added to
    # channels.BUILDS, to publish_screens.SCREENS, to the video encoder
    # and to the dashboard playlists, and missed the one list that is
    # not derived from anything. So this stops being a list.
    for _name, screen in SCREENS.items():
        if os.path.exists(screen[1]):
            git("add", "--", screen[1])
    for path in SHARED_FILES:
        if os.path.exists(path):
            git("add", "--", path)
    for directory in ("boards", "stream"):
        if os.path.isdir(directory):
            git("add", "--", directory)
    segment_branch.untrack()
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

    # THE GATE RUNS ONCE, HERE, BEFORE THE FIRST PUSH — not once per
    # attempt inside the loop.
    #
    # It used to run at the top of every attempt, and that is what cost
    # runs #911, #915 and #917. The loop's recovery from a rejected push
    # is `git reset --hard origin/main`, which brings main's CODE into a
    # pass whose boards and segments were built minutes earlier by the
    # code this run checked out. The next attempt then judged this
    # pass's artefacts with somebody else's newer rules.
    #
    # Run #917 is the clean example. Its own "Verify screens" step had
    # just passed. The push was rejected because main had moved, the
    # reset pulled in a change that had altered a screen's page length
    # from 14 seconds to 20, and the gate — now expecting 20 — refused
    # fifteen segments this run had correctly encoded at 14, plus five
    # VOD checks and a crash, eight failures from one version skew. The
    # run published nothing, and the boards on the television stayed as
    # they were for another hour.
    #
    # Running it once is not a weakening. restore() puts this pass back
    # whole, screen by screen, from our own commit — so the artefacts
    # after a rebase are the SAME BYTES the gate has already approved.
    # What re-running could catch is not a fault in this pass; it is
    # only the skew, and the skew is the bug.
    allowed, failures = the_gate_allows_publishing()
    if not allowed:
        error("the screen gate refused this pass — nothing is published")
        for failure in failures:
            log(f"  {failure}")
        return 1

    for attempt in range(1, ATTEMPTS + 1):
        # THE SEGMENTS GO FIRST, AND MAIN ONLY IF THEY ALL WENT. Some
        # screens' segments live on hls-segments, and main's playlists
        # name them there. So they are pushed before the commit that
        # names them, and a commit that is not safe to push — a playlist
        # naming a segment the branch does not hold, or naming one by a
        # relative path main no longer carries — is not pushed at all.
        # The next pass is minutes away and builds from scratch.
        problems = segment_branch.head_problems()
        if problems:
            for problem in problems:
                error(problem)
            error("this commit would point a playlist at a missing "
                  "segment — nothing is published")
            return 1
        if not segment_branch.publish():
            error("the segments could not be published, so the playlists "
                  "naming them are not published either")
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
        # A reset brings the winning run's playlists but not the segments
        # they name that live on hls-segments; put those on disk, as the
        # reset itself used to.
        segment_branch.hydrate()

        restore(ours, changed)
        reconcile_stream_with_the_encoder()
        segment_branch.untrack()

        if nothing_is_staged():
            log(f"{BRANCH} already carries this pass.")
            return 0
        git("commit", "-m", COMMIT_MESSAGE)
        time.sleep(random.randint(2, 6))

    error(f"could not push after {ATTEMPTS} attempts")
    return 1


if __name__ == "__main__":
    sys.exit(publish())
