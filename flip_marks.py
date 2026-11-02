#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One minute's work: move the marks that have changed, and nothing else.

"Fix it once and for all Live, التالي، انتهى for all the dashboard
channels!!!"

A FULL PASS IS THE WRONG UNIT OF WORK FOR A MARK, and that is the whole
of why it was late. Measured inside run #922 a pass takes 4 minutes 51
seconds, and when a row crosses its kickoff or its final whistle almost
none of that work is the work: the sources have not changed, the
fixtures have not changed, the guide has not changed. One word on one
picture has.

So this runs between passes and does only that word:

  1. Every board a channel has drawn left a record of its rows and the
     marks it was drawn with — board_marks. Recompute those marks now.
  2. Almost always they are identical, and this exits having done
     nothing, in the time it takes to read a few small files.
  3. When one has moved, redraw THAT board from its own record, through
     the same drawing call the build uses, and re-encode only the screen
     it belongs to. A board that did not change is not re-encoded — so
     the encode is one segment, not a reel.
  4. Publish.

WHAT IT DELIBERATELY DOES NOT DO: fetch a source, rebuild a guide, write
an XML, or run the gate selftest. It publishes nothing that was not
already gated: the rows are the rows the last full pass collected and
the gate passed, and the only thing that differs is which of them says
مباشر. A row cannot appear, vanish or change its time here.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone

import board_marks
from board_marks import marks_of

UTC = timezone.utc


def screen_of(name: str) -> str | None:
    """Which registered screen owns this board, by prefix.

    A screen owns its boards, its segments, its playlist and its stamp by
    prefix — the same rule seven other places in this service use.
    THE LONGEST MATCHING PREFIX WINS, because prefixes nest: a board of
    dubai_matches_ also starts with nothing else, but the pair
    today_matches_ / trial_matches_ was once a strict prefix of another
    and cost a whole pass when the shorter one swallowed the longer.
    """
    import publish_screens

    best, owner = "", None
    for screen, row in publish_screens.SCREENS.items():
        prefix = row[0]
        if name.startswith(prefix) and len(prefix) > len(best):
            best, owner = prefix, screen
    return owner


def main() -> int:
    now = datetime.now(UTC)
    records = board_marks.every_record()
    if not records:
        # A fresh checkout has drawn nothing yet, so there is nothing
        # whose marks could have moved. The first full pass writes them.
        print("no board has been drawn in this checkout yet — nothing to flip")
        return 0

    moved, touched = [], {}
    for kept in records:
        was = kept.get("marks") or []
        rows = kept.get("rows") or []
        if not rows:
            continue
        is_now = marks_of(rows, now)
        if is_now == was:
            continue
        screen = screen_of(kept["name"])
        if screen is None:
            print(f"::warning::{kept['name']} belongs to no registered "
                  f"screen — left alone")
            continue
        moved.append((kept, was, is_now, screen))
        touched.setdefault(screen, []).append(kept["name"])

    if not moved:
        print(f"every mark still true at {now:%H:%M:%S} — nothing redrawn")
        return 0

    redrawn = 0
    for kept, was, is_now, screen in moved:
        changed = [f"{index}: {before} -> {after}"
                   for index, (before, after) in enumerate(zip(was, is_now))
                   if before != after]
        print(f"{kept['name']}  ({', '.join(changed)})")
        try:
            fresh = board_marks.picture(kept, now)
        except Exception as exc:                              # noqa: BLE001
            print(f"::warning::{kept['name']} could not be redrawn ({exc}) "
                  f"— it keeps the picture it has")
            continue
        path = os.path.join(kept["board_dir"], kept["name"])
        if os.path.exists(path) and open(path, "rb").read() == fresh:
            # The marks moved but the picture did not — a row that went
            # from upcoming to live while التالي stayed on the same row,
            # for instance. Nothing to publish, but the record is
            # refreshed so this is not recomputed every minute.
            board_marks.remember(kept, kept["rows"], now)
            touched[screen].remove(kept["name"])
            if not touched[screen]:
                del touched[screen]
            continue
        with open(path, "wb") as out:
            out.write(fresh)
        board_marks.remember(kept, kept["rows"], now)
        redrawn += 1

    if not touched:
        print("the marks moved but no picture did — nothing to publish")
        return 0

    print(f"\n{redrawn} board(s) redrawn on "
          f"{len(touched)} screen(s): {', '.join(sorted(touched))}")

    # ---- only the screens whose pictures moved ------------------------
    for screen in sorted(touched):
        done = subprocess.run(
            [sys.executable, "-u", "match_screen_video.py", screen],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        print(done.stdout, end="")
        if done.returncode != 0:
            print(f"::warning::{screen} did not encode — its board is "
                  f"redrawn and the next full pass will encode it")

    return subprocess.call([sys.executable, "-u", "publish_screens.py"])


if __name__ == "__main__":
    sys.exit(main())
