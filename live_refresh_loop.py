"""Keep the red dot honest between the crons GitHub actually fires.

A kickoff is not an event anyone pushes; it is a clock reading. The
board that says 🔴 مباشر is only as true as the minute it was drawn in,
so the whole fix is to keep drawing it. That used to mean waiting for
the next cron — and the crons are the part GitHub drops first.

Measured, not supposed, on 6 September: the freshest board when a
reader's television said 08:26 had been built at 08:03. Angers - Rennes
kicked off at 08:15, eleven minutes live, and its row still carried no
mark, because every scheduled run after the 08:03 one was dropped —
zero runs across 27 minutes that morning, an hour and fifty-one minutes
gone the previous afternoon, cancelled runs between. Asking more often
does not help; surviving crons take five to eleven minutes for one
snapshot, and the snapshot is stale the moment it lands.

So this script does not ask the scheduler for anything. The job that
GitHub did start keeps working for itself: every few minutes it rebuilds
the two match guides, re-encodes the four sports screens, rewrites the
playlists, and publishes through publish_screens.py — the same gate,
the same screen-at-a-time publishing, the same everything as the pass
the workflow already ran. A kickoff lands 🔴 مباشر on both clocks'
guides within one cadence of the whistle rather than within one
surviving cron of it.

The cadence is not a promise the loop makes to itself: a pass that
takes three minutes sleeps for none of the two and a half it aimed at.
The loop only ever waits the *remainder* of the cadence, so slow
sources slow the cadence honestly instead of stacking passes on top of
one another.

It stops before the hour is out on purpose. The concurrency group
queues the next cron behind this job while it runs — one pending, the
newest one — so a job that yields at fifty-five minutes hands the pen
to a cron that was already waiting, and the next full pass (news,
weather, the merged guide, everything) starts immediately rather than
an hour from now. If every cron of some hour is dropped anyway, the
worst case is the belt the workflow already wears: the full build's
workflow_run trigger, which demonstrably fires.

Fault tolerance is per pass, not per hour. A source that does not
answer leaves its published guide untouched — that is the generators'
own rule — and a pass that crashes entirely is logged and yielded to;
the next pass starts from whatever the last one published, and the one
after that. Nothing below bypasses publish_screens.py, so nothing
reaches main that the gate has not agreed to, exactly as before.

LOOP_MINUTES and CADENCE_SECONDS exist as environment overrides so the
loop can be smoke-tested in seconds rather than an hour, and
SKIP_PUBLISH=1 runs every part of a pass except the push — for the
workspace copy, which has no git directory to push from.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

# The script writes everything the generators write — relative paths —
# so it must sit in the repository root no matter where it was invoked
# from.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Fifty-five minutes: long enough that the queued cron behind this job
# covers the handover, short enough that the job never runs two hours
# by accident if the queue is empty.
LOOP_MINUTES = float(os.environ.get("LOOP_MINUTES", "55"))
CADENCE_SECONDS = float(os.environ.get("CADENCE_SECONDS", "150"))
SKIP_PUBLISH = os.environ.get("SKIP_PUBLISH") == "1"

# The two guides whose marks go stale at a kickoff. Each one writes
# both clocks' XML and both clocks' boards in the same run, so one
# rebuild refreshes the Los Angeles link and the Dubai link together.
# The news and the weather are deliberately absent: neither carries a
# live mark that a kickoff can flip, and the full pass the workflow
# already ran — and the next queued cron's — rebuilds both of them.
GUIDES = ("today_matches_epg.py", "other_sports_epg.py")

# The four screens those two guides feed, both clocks again. The
# encoders are fingerprint-gated: a board that did not change costs a
# stamp check and nothing else, so running all four every pass is nearly
# free when nothing is happening and exactly right when something is.
SCREENS = ("today_matches", "other_sports",
           "dubai_matches", "dubai_sports")

# The playlists point players at the screens; rewritten only when their
# content really changed, and staging an identical file stages nothing.
PLAYLIST_WRITER = "sports_dashboard_m3u.py"

# Publishing stays in publish_screens.py: it stages by screen, runs the
# gate before any push, restores whole screens when a push is rejected,
# and refuses to publish at all without today_matches_epg.xml. The loop
# never publishes any other way, so the repository's one rule — nothing
# reaches main unless the gate agrees — holds every bit as much inside
# the loop as it did in the pass that ran before it.
PUBLISHER = "publish_screens.py"


def log(message: str) -> None:
    print(f"[loop] {message}", flush=True)


def run(step: str, command: list[str]) -> bool:
    """Run one piece of a pass, timed, and never let it kill the hour."""
    began = time.monotonic()
    finished = subprocess.run([sys.executable, "-u", *command],
                              check=False)
    took = time.monotonic() - began
    log(f"{step}: {took:.0f}s, exit {finished.returncode}")
    return finished.returncode == 0


def one_pass(number: int) -> tuple[int, int]:
    """One refresh: rebuild, encode, playlist, publish. Returns the
    count of steps that failed and of publishes attempted."""
    log(f"pass {number} begins")
    failed = 0

    for guide in GUIDES:
        if not run(f"rebuild {guide}", [guide]):
            # The generator's own rule already applies: a source that
            # did not answer leaves the published guide untouched, so
            # the pass continues with the guide it already had.
            failed += 1

    for screen in SCREENS:
        if not run(f"encode {screen}", ["match_screen_video.py", screen]):
            failed += 1

    if not run("rewrite the playlists", [PLAYLIST_WRITER]):
        failed += 1

    publishes = 0
    if SKIP_PUBLISH:
        log("publish skipped (SKIP_PUBLISH=1)")
    else:
        publishes += 1
        if not run("publish", [PUBLISHER]):
            # A refused publish left the repository exactly as the last
            # good pass had it; the next pass rebuilds from that.
            failed += 1

    log(f"pass {number} ends, {failed} step(s) unhappy")
    return failed, publishes


def main() -> int:
    began = time.monotonic()
    deadline = began + LOOP_MINUTES * 60
    log(f"refreshing for {LOOP_MINUTES:.0f} minutes, "
        f"aiming at one pass every {CADENCE_SECONDS:.0f}s")

    passes, publishes, unhappy = 0, 0, 0

    # A fixed schedule that corrects itself. The next pass is aimed at
    # one cadence after the last one BEGAN, so a pass that fits keeps
    # the cadence exactly and a pass that overruns it starts the next
    # one immediately — never stacking passes on top of one another,
    # and never letting a slow source quietly widen the cadence.
    #
    # The workflow's own steps are pass zero: the guides, boards,
    # screens, playlists and the first publish are minutes old at most
    # when this starts, so the first thing to do is wait, not redo.
    next_at = began + CADENCE_SECONDS

    while True:
        now = time.monotonic()
        if now >= deadline:
            break
        # Never sleep past the deadline: the queued cron is waiting.
        nap = min(next_at, deadline) - now
        if nap > 0:
            log(f"sleeping {nap:.0f}s")
            time.sleep(nap)
        if time.monotonic() >= deadline:
            break

        passes += 1
        pass_started = time.monotonic()
        try:
            failed, pushed = one_pass(passes)
        except Exception as exc:  # one bad pass must not end the hour
            log(f"pass {passes} crashed: {exc!r}")
            failed, pushed = 1, 0
        unhappy += failed
        publishes += pushed
        next_at = pass_started + CADENCE_SECONDS

    log(f"done: {passes} passes, {publishes} publish attempts, "
        f"{unhappy} unhappy step(s), "
        f"{(time.monotonic() - began) / 60:.1f} minutes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
