#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Turn today's board into a channel you can actually tune to.

Everything before this put the day somewhere a player might show it and
hoped: a description panel shows text and nothing else, and the programme
<icon> was ignored outright. A video has no such argument with the player.
Tune to the channel and the board is on the screen, full size, because it
IS the picture being played.

It is a still image encoded as video, which costs almost nothing: half an
hour of it is under five hundred kilobytes, because H.264 spends bits on
change and there is none. A silent mono track rides along, since players
built for live television are happier with one than without.

The encode only runs when the board itself changed. The board carries
clock times and no countdown precisely so that it changes when the day's
fixtures change and not every ten minutes, and the video inherits that:
a handful of files a day rather than a hundred and forty.

When the half hour runs out the picture stops, because a file has an end
and a real channel does not. Making it endless needs a machine holding a
stream open, which is a server, which is not free — so the honest shape
here is a long file that is redrawn whenever the day moves on.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys

from epg_lib import log, warn

BOARD = os.path.join("boards", "today_matches_0.png")
OUT_DIR = "stream"
OUT = os.path.join(OUT_DIR, "today_matches.mp4")
STAMP = os.path.join(OUT_DIR, "board.sha256")

MINUTES = 30

# One keyframe for the whole file. There is nothing to seek to in a still
# picture, and a keyframe every second is what turned eight megabytes of
# nothing into a repository problem the first time this was measured.
KEYFRAME_EVERY = MINUTES * 60


def digest(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def encode(board: str, out: str) -> bool:
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-framerate", "1", "-i", board,
        # Silent audio: a live-television player with no audio track at all
        # will sometimes sit on a black screen rather than show the video.
        "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=16000",
        "-c:v", "libx264", "-preset", "veryslow", "-tune", "stillimage",
        "-pix_fmt", "yuv420p", "-g", str(KEYFRAME_EVERY), "-crf", "30",
        "-c:a", "aac", "-b:a", "8k", "-ac", "1",
        "-shortest", "-t", str(MINUTES * 60),
        # The header goes first, so a player can start without fetching
        # the whole file.
        "-movflags", "+faststart",
        out,
    ]
    done = subprocess.run(command, check=False, capture_output=True, text=True)
    if done.returncode != 0:
        warn(f"ffmpeg refused to encode the screen: "
             f"{(done.stderr or '').strip()[:300]}")
        return False
    return True


def main() -> int:
    if not shutil.which("ffmpeg"):
        warn("ffmpeg is not installed — the screen channel is not rebuilt "
             "this pass and the published one stays as it is")
        return 0
    if not os.path.exists(BOARD):
        warn(f"{BOARD} has not been drawn — nothing to encode")
        return 0

    fingerprint = digest(BOARD)
    was = ""
    if os.path.exists(STAMP):
        with open(STAMP, encoding="utf-8") as handle:
            was = handle.read().strip()
    if was == fingerprint and os.path.exists(OUT):
        log("the screen already shows this board — not re-encoded")
        return 0

    os.makedirs(OUT_DIR, exist_ok=True)
    if not encode(BOARD, OUT):
        return 0            # keep whatever is already published

    with open(STAMP, "w", encoding="utf-8") as handle:
        handle.write(fingerprint + "\n")
    log(f"screen channel re-encoded: {OUT} "
        f"({os.path.getsize(OUT) // 1024} KB, {MINUTES} minutes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
