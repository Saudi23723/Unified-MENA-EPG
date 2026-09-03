#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Turn today's boards into a channel you can actually tune to.

Everything before this put the day somewhere a player might show it and
hoped: a description panel shows text and nothing else, and the programme
<icon> was ignored outright. A video has no such argument with the player.
Tune to the channel and the board is on the screen, full size, because it
IS the picture being played.

It is a slideshow: today, then tomorrow, then the day after, twenty
seconds each, round and round. A single board held on screen showed the
day and hid the two behind it; a viewer who waits a quarter of a minute
now sees all of them.

WHY THIS IS HLS AND NOT ONE LONG FILE
=====================================
A file has an end and a channel does not, and "it stops after a quarter of
an hour" is a fair thing to refuse. Half a day as one MP4 would be some
seventy megabytes committed every time a fixture moves, which is not a
price worth paying either.

An HLS playlist settles it, because a playlist may name the same segment
as many times as it likes. Three segments are encoded — one per day — and
the playlist lists them round and round for twelve hours. The bytes on
disk are three short clips; the length is a text file. Twelve hours of
picture costs about half a megabyte in total.

Each repeat is preceded by EXT-X-DISCONTINUITY, which is the tag that
exists for precisely this: it tells the player the timestamps are about to
start over, which they are, because it is the same clip again.

WHAT IT COSTS
=============
Almost nothing, because H.264 spends bits on change and a still picture
has none. The whole cost is the cuts between boards, which is why they are
twenty seconds apart and not two. A silent mono track rides along, since
players built for live television are happier with one than without.

The encode only runs when a board actually changed. The boards carry clock
times and no countdown precisely so that they change when the day's
fixtures change and not every ten minutes, and the screen inherits that:
a handful of files a day rather than a hundred and forty.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time

from epg_lib import log, warn

BOARD_DIR = "boards"
OUT_DIR = "stream"
OUT = os.path.join(OUT_DIR, "screen.m3u8")
STAMP = os.path.join(OUT_DIR, "board.sha256")

# How far ahead the playlist reaches. It is a WINDOW, not a running time:
# the channel is live and the window rolls forward with each build.
#
# It has to outlast the gap between builds or a player reaches the end and
# waits on a blank screen. The board rebuilds every ten minutes at worst,
# so thirty is three times the room it needs and still a five-kilobyte
# file instead of a hundred-and-thirty.
WINDOW_MINUTES = 30
HOLD = 20               # seconds a board stays up before the next one

# Every segment opens on a keyframe, which a segment must, and needs no
# other: it is the same picture for twenty seconds.
KEYFRAME_EVERY = HOLD


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


def segment_of(board: str) -> str:
    """The .ts file a given board is encoded into, named after its content.

    The name carries eight characters of the board's own hash, so a board
    that changes produces a segment nobody has seen before. Without that
    the file name stayed put while the picture underneath it moved, and
    every cache between here and the television went on serving what it
    already had — a viewer watched yesterday's fixtures on today's channel
    and there was no way to tell them apart from the outside.
    """
    stem = os.path.splitext(os.path.basename(board))[0]
    return os.path.join(OUT_DIR, f"{stem}.{digest([board])[:8]}.ts")


def forget_old_segments(keep: list[str]) -> int:
    """Delete segments no playlist points at any more.

    Content-addressed names mean a new board leaves its predecessor behind,
    and left alone they would pile up a few files a day forever.
    """
    wanted = {os.path.basename(path) for path in keep}
    gone = 0
    for name in sorted(os.listdir(OUT_DIR)):
        if name.endswith(".ts") and name not in wanted:
            os.remove(os.path.join(OUT_DIR, name))
            gone += 1
    return gone


def encode_segment(board: str, out: str) -> bool:
    """One board, fifteen seconds of it, as a transport stream segment."""
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-framerate", "1", "-i", board,
        # Silent audio: a live-television player with no audio track at all
        # will sometimes sit on a black screen rather than show the video.
        "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=16000",
        "-c:v", "libx264", "-preset", "veryslow", "-tune", "stillimage",
        "-vf", "fps=1", "-pix_fmt", "yuv420p",
        "-g", str(KEYFRAME_EVERY), "-crf", "32",
        "-c:a", "aac", "-b:a", "8k", "-ac", "1",
        "-shortest", "-t", str(HOLD), "-muxdelay", "0",
        "-f", "mpegts", out,
    ]
    done = subprocess.run(command, check=False, capture_output=True, text=True)
    if done.returncode != 0:
        warn(f"ffmpeg refused to encode {out}: "
             f"{(done.stderr or '').strip()[:300]}")
        return False
    return True


def write_playlist(segments: list[str], out: str, now=None) -> int:
    """A LIVE playlist, which is the whole reason the television updates.

    It used to be VOD: PLAYLIST-TYPE:VOD, MEDIA-SEQUENCE fixed at 0, and
    EXT-X-ENDLIST under twelve hours of segments. That is a complete,
    finished recording, and RFC 8216 is explicit about what a player does
    with one — it loads the playlist ONCE and never asks again. So a
    viewer opened the channel, got whatever the board said at that moment,
    and watched it for twelve hours while the guide rebuilt every ten
    minutes behind them. The build was never the problem: the picture was
    reaching the repository and the television was never told to look.

    Three things make it live, and all three are needed:

      NO ENDLIST. That tag alone says the recording is complete, and a
      player that sees it stops reloading.
      NO PLAYLIST-TYPE:VOD, for the same reason at the top of the file.
      A MEDIA-SEQUENCE THAT MOVES. It numbers the first segment in the
      window, and a player uses it to tell an unchanged playlist from a
      new one. Left at 0 forever, a fresh window looks like the old one.

    Counted in whole HOLDs since the epoch, so it advances on its own with
    the clock and cannot go backwards between builds.

    EXT-X-DISCONTINUITY still goes before every entry: the timestamps do
    start over each time, because it is the same clip again.

    One thing outside our hands, written down rather than discovered
    twice: raw.githubusercontent serves with a five-minute cache, so a
    player polling every twenty seconds may sit on a stale copy for up to
    that long. Ten-minute builds live with it comfortably.
    """
    now = now or time.time()
    per_cycle = max(1, len(segments))
    cycles = max(1, (WINDOW_MINUTES * 60) // (HOLD * per_cycle))
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{HOLD}",
        f"#EXT-X-MEDIA-SEQUENCE:{int(now // HOLD)}",
    ]
    for _ in range(cycles):
        for segment in segments:
            lines += ["#EXT-X-DISCONTINUITY",
                      f"#EXTINF:{HOLD}.0,",
                      os.path.basename(segment)]
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    return cycles


def main() -> int:
    if not shutil.which("ffmpeg"):
        # Not a shrug. This shrugged once, and the cost was a television
        # showing a hand-encoded picture for hours: ubuntu-latest carries
        # no ffmpeg, so every ten-minute pass drew fresh boards, skipped
        # the encode, and published the pair out of step. Carrying on
        # without an encoder is precisely the failure, so it is one.
        warn("ffmpeg is not installed — the screen cannot be re-encoded, "
             "and publishing boards it does not show is the fault this "
             "refuses to repeat")
        return 1
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
        # Sweep even when nothing is re-encoded. The sweep used to run only
        # after an encode, so a segment orphaned any other way stayed
        # forever: two scheduled passes failed to push, left main holding
        # segments for boards that had moved on, and every pass after them
        # matched the fingerprint, returned here, and never looked. The
        # screen gate found them days later.
        dropped = forget_old_segments([segment_of(b) for b in reel])
        if dropped:
            log(f"  {dropped} segment(s) nothing points at any more, removed")
        log("the screen already shows these boards — not re-encoded")
        return 0

    os.makedirs(OUT_DIR, exist_ok=True)
    segments = []
    for board in reel:
        segment = segment_of(board)
        if not encode_segment(board, segment):
            # Same reasoning: what is published stays, and this pass says
            # it failed so nothing is committed on top of it.
            return 1
        segments.append(segment)

    cycles = write_playlist(segments, OUT)
    dropped = forget_old_segments(segments)
    if dropped:
        log(f"  {dropped} segment(s) nothing points at any more, removed")

    with open(STAMP, "w", encoding="utf-8") as handle:
        handle.write(fingerprint + "\n")
    bytes_on_disk = os.path.getsize(OUT) + sum(os.path.getsize(s)
                                               for s in segments)
    log(f"screen channel re-encoded: {len(segments)} segment(s) at {HOLD}s, "
        f"played {cycles} times over = a {WINDOW_MINUTES}-minute "
        f"live window, "
        f"{bytes_on_disk // 1024} KB on disk in total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
