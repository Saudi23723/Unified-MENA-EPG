#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Turn today's board into a channel you can actually tune to.

Everything before this put the day somewhere a player might show it and
hoped: a description panel shows text and nothing else, and the programme
<icon> was ignored outright. A video has no such argument with the player.
Tune to the channel and the board is on the screen, full size, because it
IS the picture being played.

It is a slideshow: today, then tomorrow, then the day after, fifteen
seconds each, round and round for twenty minutes. One still board held for
half an hour showed the day and hid the two behind it; a viewer who tunes
in and waits a quarter of a minute now sees all of them.

It costs almost nothing, because H.264 spends bits on change and a still
picture has none — the whole cost here is the cuts between boards, which
is why they are fifteen seconds apart and not two. A silent mono track
rides along, since players built for live television are happier with one
than without.

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
import tempfile

from epg_lib import log, warn

BOARD_DIR = "boards"
OUT_DIR = "stream"
OUT = os.path.join(OUT_DIR, "today_matches.mp4")
STAMP = os.path.join(OUT_DIR, "board.sha256")

MINUTES = 15
HOLD = 15               # seconds a board stays up before the next one

# A keyframe every second is what turned ten minutes of nothing into 1379
# KB the first time this was measured; at one every five minutes the same
# ten minutes is 75 KB. The cuts between boards force their own keyframes
# regardless, which is the whole real cost of a slideshow.
KEYFRAME_EVERY = 300


def boards() -> list[str]:
    """Every day's board that has been drawn, in the order of the days."""
    if not os.path.isdir(BOARD_DIR):
        return []
    return [os.path.join(BOARD_DIR, name)
            for name in sorted(os.listdir(BOARD_DIR))
            if name.startswith("today_matches_") and name.endswith(".png")]


def digest(paths: list[str]) -> str:
    """One fingerprint for the whole reel, so any board changing re-encodes."""
    running = hashlib.sha256()
    for path in paths:
        running.update(path.encode())
        with open(path, "rb") as handle:
            running.update(handle.read())
    return running.hexdigest()


def reel_text(paths: list[str]) -> str:
    """The concat list ffmpeg reads: each board, and how long it stays up.

    The last file is named twice because the concat demuxer reads a
    duration as the gap before the NEXT entry, so without a repeat the
    final board flashes past in a single frame.
    """
    lines = []
    for path in paths:
        lines.append(f"file '{os.path.abspath(path)}'")
        lines.append(f"duration {HOLD}")
    lines.append(f"file '{os.path.abspath(paths[-1])}'")
    return "\n".join(lines) + "\n"


def encode(paths: list[str], out: str) -> bool:
    # The reel is scaffolding, not output: it holds absolute paths from
    # whichever machine ran the encode and has no business in the
    # repository beside the video it built.
    handle, reel = tempfile.mkstemp(suffix=".txt", text=True)
    with os.fdopen(handle, "w", encoding="utf-8") as out_handle:
        out_handle.write(reel_text(paths))

    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        # Round and round until the running time is up.
        "-stream_loop", "-1", "-f", "concat", "-safe", "0", "-i", reel,
        # Silent audio: a live-television player with no audio track at all
        # will sometimes sit on a black screen rather than show the video.
        "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=16000",
        "-c:v", "libx264", "-preset", "veryslow", "-tune", "stillimage",
        "-vf", "fps=1", "-pix_fmt", "yuv420p",
        "-g", str(KEYFRAME_EVERY), "-crf", "32",
        "-c:a", "aac", "-b:a", "8k", "-ac", "1",
        "-shortest", "-t", str(MINUTES * 60),
        # The header goes first, so a player can start without fetching
        # the whole file.
        "-movflags", "+faststart",
        out,
    ]
    try:
        done = subprocess.run(command, check=False, capture_output=True,
                              text=True)
    finally:
        os.unlink(reel)
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
    reel = boards()
    if not reel:
        warn(f"no board has been drawn in {BOARD_DIR}/ — nothing to encode")
        return 0

    fingerprint = digest(reel)
    was = ""
    if os.path.exists(STAMP):
        with open(STAMP, encoding="utf-8") as handle:
            was = handle.read().strip()
    if was == fingerprint and os.path.exists(OUT):
        log("the screen already shows these boards — not re-encoded")
        return 0

    os.makedirs(OUT_DIR, exist_ok=True)
    if not encode(reel, OUT):
        return 0            # keep whatever is already published

    with open(STAMP, "w", encoding="utf-8") as handle:
        handle.write(fingerprint + "\n")
    log(f"screen channel re-encoded: {OUT} "
        f"({os.path.getsize(OUT) // 1024} KB, {MINUTES} minutes, "
        f"{len(reel)} board(s) at {HOLD}s each)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
