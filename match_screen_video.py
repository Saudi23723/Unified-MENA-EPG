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
import math
import os
import re
import shutil
import subprocess
import sys
import time

from epg_lib import log, warn

BOARD_DIR = "boards"
OUT_DIR = "stream"

# One encoder, two screens. The second board draws the same way and is
# encoded the same way, so it takes the same routine with a different
# prefix rather than a copy of this file that would drift out of step.
#
# Each screen owns the segments whose names begin with its prefix, and
# NOTHING ELSE MAY TOUCH THEM. That is not tidiness: forget_old_segments
# deletes every .ts it does not recognise, so without the prefix each
# screen would sweep away the other's segments on every pass, and the
# gate would find a playlist naming files that no longer exist.
SCREENS = {
    "today_matches": ("today_matches_", "screen.m3u8", "board.sha256"),
    "other_sports": ("other_sports_", "sports.m3u8", "sports.sha256"),
}

# How far ahead the playlist reaches. It is a WINDOW, not a running time:
# the channel is live and the window rolls forward with each build.
#
# IT HAS TO OUTLAST THE GAP BETWEEN BUILDS. A player that reaches the end
# of the window and finds the file unchanged has nothing left to play,
# and that is a black screen — not buffering, not a stale board, nothing.
#
# This said thirty, on the reasoning that "the board rebuilds every ten
# minutes at worst, so thirty is three times the room it needs". THAT
# ASSUMPTION WAS WRONG AND THE CHANNEL DIED OF IT:
#
#     last build 15:32 · reported black at 16:23 · 56 minutes
#     the window covered 30 · so it ran dry at 16:02
#
# Nothing had failed. The guide had today, the boards were drawn for
# today, every segment the playlist named was present and probed clean —
# 1280x720, 12 fps, h264 and AAC. The build simply had not run, because
# GitHub drops sub-hourly schedules, which is a thing this repository
# already knows and works around everywhere else.
#
# So the window is no longer sized by what the build is SUPPOSED to do.
#
# AND ON ITS OWN IT FIXED NOTHING, which is worth writing down because
# it was shipped believing otherwise. A live player does not start at
# the front of the window — RFC 8216 §6.3.3 puts it three target
# durations back from the END — so the runway was sixty seconds whether
# this said thirty minutes or six hours. EXT-X-START, written into the
# playlist, is what turns this number into runway at all; without it
# the window is decoration. Neither is any use without the other.
#
# TWELVE HOURS, and the length is a real trade rather than a free lunch:
# the whole playlist is re-fetched once per target duration, so every
# hour of window is bandwidth spent on every poll, forever. Measured
# against a 700 KB segment every twenty seconds:
#
#        2 h    15 KB     2% of the video
#        6 h    45 KB     6%
#       12 h    91 KB    13%
#       24 h   181 KB    26%   <- enough overhead to cause the fault
#                               it is meant to prevent
#
# Twelve carries a whole night of Actions being down — far past the
# hour the watch needs to notice a dropped schedule — for an eighth of
# what the pictures already cost. Twenty-four buys one more night at
# double the price, on a box that is already the weak link.
WINDOW_MINUTES = 12 * 60

# HOW MANY BOARDS THE CHANNEL ACTUALLY PLAYS, out of however many the
# guide draws.
#
# The guide reaches fourteen days now, and at eight rows a board that is
# sixteen boards — a five-and-a-half-minute lap. Every one of them is
# worth having in the GUIDE, where a viewer scrolls to what they want.
# On a channel they cannot: whatever is on when they tune in is what
# they get, and five minutes of lap means most arrivals land on a day
# next week and have to wait out the rest to see tonight.
#
# Six is two minutes, which is short enough that today comes round while
# somebody is still looking at the screen, and long enough to carry
# today, tomorrow and the day after even when one of them needs two
# pages. The days past that are not lost — they are in the guide, in
# full, with their own boards drawn and pointed at.
ON_SCREEN = 6
HOLD = 20               # seconds a board stays up before the next one

# Every segment opens on a keyframe, which a segment must, and needs no
# other: it is the same picture for twenty seconds.


A_BOARD_NUMBER = re.compile(r"_(\d+)\.png$")


def boards(prefix: str) -> list[str]:
    """This screen's boards, in the order of the days.

    SORTED BY THEIR NUMBER, and it has to be said out loud because the
    obvious way is wrong and was wrong here for a day.

    sorted() on the file names compares them as text, and as text "10"
    comes before "2". So a screen with more than ten boards played:

        0, 1, 10, 11, 12, 13, 14, 15, 2, 3, 4 …

    Board 0 and 1 are today. Then it jumps to board 10 — a week and a
    half ahead — and stays there for six boards before coming back to
    tomorrow. A reader watching it said the channel "starts from the
    6th", and that is precisely what it did: today went past in forty
    seconds and did not come round again for two minutes.

    It only appeared when the boards crossed ten, which is why it hid for
    so long: the second screen crossed it when its window went to
    fourteen days, and the first when eight rows a board turned three
    days into ten pages. Both crossed within an hour of each other.

    The number in the name is the order. Nothing else is.
    """
    if not os.path.isdir(BOARD_DIR):
        return []
    mine = [name for name in os.listdir(BOARD_DIR)
            if name.startswith(prefix) and name.endswith(".png")
            and A_BOARD_NUMBER.search(name)]
    mine.sort(key=lambda name: int(A_BOARD_NUMBER.search(name).group(1)))
    return [os.path.join(BOARD_DIR, name) for name in mine]


# Bumped whenever the SEGMENTS THEMSELVES would come out different for
# the same board — a codec setting, a duration, the timestamp offset that
# makes the reel one timeline. It goes into the fingerprint, so changing
# how a segment is made re-encodes every segment.
#
# Without it a change like that ships half-applied and is worse than not
# shipping at all: the playlist stops declaring a break between boards
# because the segments are supposed to be continuous, the fingerprint
# still matches so nothing is re-encoded, and the television is handed a
# continuous playlist over segments that all still start at zero. That is
# every stall back, with the tag that used to cover for it removed.
#
#   1  the original: every segment starts at zero
#   2  each board stamped with its place in the reel
#   3  audio at 32kHz, so a segment is exactly HOLD seconds and does not
#      overlap the one after it
#   4  twelve frames a second with a keyframe every two, instead of one
#      frame a second, no declared rate at all and one keyframe
ENCODER_REVISION = 5

# TWELVE FRAMES A SECOND, AND A KEYFRAME EVERY TWO.
#
# It was one frame a second, and the measurement is the argument:
#
#     fps   size/20s   rate the stream declares   keyframes in 20s
#      1     221 KB    NONE — 0/0                        1
#     12     455 KB    12/1                             10
#     25     470 KB    25/1                             10
#
# Two things were wrong and both are what a player complains about by
# buffering. The stream declared NO FRAME RATE, so a television had to
# infer every frame's timing from timestamps alone. And it carried ONE
# KEYFRAME in twenty seconds, so there was exactly one instant in each
# segment where a player could begin, or recover after any hiccup — miss
# it and there is nothing to do but wait for the next segment.
#
# A still picture costs almost nothing to run faster: every frame after
# the first is identical, so they code to nearly zero bytes. Twelve
# frames a second doubles a segment from 221 KB to 455 KB, which is
# about 180 kbit/s, and buys a rate the decoder is told outright and a
# keyframe every two seconds.
#
# Twelve rather than twenty-five because the extra fifteen frames buy
# nothing on a page of text that never moves, and 12 is a rate every
# decoder handles without thinking.
FPS = 12
KEYFRAME_SECONDS = 2


def digest(paths: list[str]) -> str:
    """One fingerprint for the whole reel, so any board changing re-encodes.

    The encoder's own revision is folded in, because a segment is made of
    two things — the picture, and how the picture is encoded — and only
    one of them used to be counted.
    """
    running = hashlib.sha256()
    running.update(f"encoder:{ENCODER_REVISION}\n".encode())
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


def still_wanted(prefix: str) -> set[str]:
    """The segments the PREVIOUS pass published, which are not rubbish yet."""
    path = os.path.join(OUT_DIR, f"{prefix}previous.txt")
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as handle:
        return {line.strip() for line in handle if line.strip()}


def forget_old_segments(keep: list[str], prefix: str) -> int:
    """Delete this screen's segments that nothing points at ANY MORE.

    Content-addressed names mean a new board leaves its predecessor
    behind, and left alone they would pile up a few files a day forever.

    Only this screen's own segments are considered, and that is the whole
    point of the prefix: both screens publish into stream/, and a sweep
    that deleted everything it did not recognise would take the other
    screen's segments with it every pass.

    ONE GENERATION IS KEPT, and that is the buffering.

    A board changes every pass, because it prints a countdown. Its bytes
    change, so its name changes, so every ten minutes every segment is a
    new file and every old one was deleted the same minute. Meanwhile a
    television is holding the PREVIOUS playlist — raw.githubusercontent
    serves it with a five-minute cache, so it holds it for up to five
    minutes after we replaced it — and it is still working through the
    names on it. Every one of those files has just been deleted. It asks
    for the next, gets a 404, and shows a spinner.

    That is not a corner case: it happened on every pass, to every viewer
    who was watching, which is exactly what a reader kept photographing.
    A live server never deletes a segment the moment it leaves the
    playlist; it drops it from the window and keeps the file a while
    longer. This keeps the last generation — one pass, ten minutes, twice
    the cache it has to outlive — and deletes the one before that.
    """
    wanted = {os.path.basename(path) for path in keep}
    spared = still_wanted(prefix) - wanted
    gone = 0
    for name in sorted(os.listdir(OUT_DIR)):
        if (name.startswith(prefix) and name.endswith(".ts")
                and name not in wanted and name not in spared):
            os.remove(os.path.join(OUT_DIR, name))
            gone += 1

    # TWO RECORDS, because the sweep and the gate need different facts
    # and writing one for both is how this went wrong the first time.
    #
    #   previous.txt  what THIS pass published. The next pass reads it to
    #                 know what to spare.
    #   keeping.txt   what this pass SPARED. It is on disk and the
    #                 playlist does not name it, which is exactly what
    #                 the screen gate is built to catch — so the gate is
    #                 told, by name, which files are there on purpose.
    #
    # Writing the current set to both looked equivalent and is not: the
    # gate then reads "what is current" where it needed "what is kept",
    # sees a spared segment it was never told about, and stops the build.
    for name, names in ((f"{prefix}previous.txt", sorted(wanted)),
                        (f"{prefix}keeping.txt", sorted(spared))):
        with open(os.path.join(OUT_DIR, name), "w",
                  encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(names) + ("\n" if names else ""))
    if spared:
        log(f"  {len(spared)} segment(s) kept one more pass, so a "
            f"television on the old playlist does not hit a 404")
    return gone


# THE STEP BETWEEN BOARDS ON THE TIMELINE, and why it is not HOLD.
#
# A segment is not HOLD seconds long. Measured on the six actually on
# air, every one is 20.032 — and the shape of the excess is not a rule
# that could be worked out, it is a property of the encoder:
#
#     rate 16000   starts 0.064 early, runs 0.096 long
#     rate 32000   starts 0.032 early, runs 0.032 long
#     rate 48000   starts 0.021 early, runs 0.032 long
#
# So it is measured rather than calculated. Placing board k at k x HOLD
# when the media is longer than HOLD made every board OVERLAP the next
# by 32 milliseconds — six overlaps a lap, every lap, all day, and an
# overlap is a timeline that disagrees with its own media, which a
# player answers by re-syncing. Measured on the published reel:
#
#     other_sports_1   19.968 -> 40.000   -0.032 s  OVERLAP
#     other_sports_2   39.968 -> 60.000   -0.032 s  OVERLAP     ... all six
#
# Stepping by the measured length instead closes them exactly:
#
#     p1  40.0320 -> 60.0640   +0.0000 s  CLEAN
#     p2  60.0640 -> 80.0960   +0.0000 s  CLEAN
#
# AND THE FIRST BOARD STARTS A STEP IN, not at zero. The audio begins
# before the nominal start, so an offset of zero asks the muxer for a
# negative timestamp; it clamps instead, the segment lands 0.167 late,
# and that one boundary overlaps while every other is clean. One step of
# headroom costs nothing and removes the special case.
def step_of(segment: str) -> float:
    """The real length of an encoded segment, which is the timeline step."""
    return seconds_of(segment)


def encode_segment(board: str, out: str, place: int = 0,
                   step: float | None = None) -> bool:
    """One board as a transport stream segment, at its place in the reel.

    THE PLACE IS WHY THIS TAKES AN INDEX, and it is the difference between
    a channel that plays and one that stalls every twenty seconds.

    Each board used to be encoded on its own, so every segment's clock
    started at zero. Twenty seconds of stream whose timestamps run 0→20,
    then another twenty that also run 0→20: that is not one stream, it is
    fourteen recordings in a row, and a playlist has to say so with
    EXT-X-DISCONTINUITY before each of them. A discontinuity is not a
    formality — a player tears its decoder down and builds it again — and
    a reader photographed exactly that, a spinner between one board and
    the next, on both channels.

    So a board's segment is stamped with where it sits: board 0 starts at
    zero, board 1 at twenty, board 2 at forty. The reel becomes ONE
    continuous timeline, the playlist needs no discontinuity inside a
    cycle, and the player runs from board to board without stopping.

    The place is safe to derive and stays put: a board's own file name
    carries its index — other_sports_2.png is always the third board —
    so the same picture at the same place always encodes to the same
    bytes, and nothing is re-encoded for having been given an offset.
    """
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-framerate", str(FPS), "-i", board,
        # Silent audio: a live-television player with no audio track at all
        # will sometimes sit on a black screen rather than show the video.
        # 32000 and not 16000, measured rather than chosen: 20 x 16000
        # runs 96 ms long, 20 x 32000 runs 32 ms long.
        #
        # THE ARITHMETIC HERE USED TO SAY 32000 CAME OUT EXACT — 625
        # frames of 1024 samples is 20.000 — and the files say otherwise.
        # Every one of the six on air measures 20.032, which is 626
        # frames: the encoder emits one past the count, and neither
        # -shortest, -t, -frames:a nor an atrim filter removes it. Only
        # dropping the audio does, and a player with no audio track will
        # sometimes show black, so the audio stays.
        #
        # The excess is not worth fighting, and it is not a rule that
        # could be derived either — 16000 starts 0.064 early and runs
        # 0.096 long, 48000 starts 0.021 early and runs 0.032 long. So
        # it is MEASURED, and every board is placed by the measured
        # length rather than by HOLD, which is what closes the overlap.
        "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=32000",
        "-c:v", "libx264", "-preset", "veryslow", "-tune", "stillimage",
        "-vf", f"fps={FPS}", "-pix_fmt", "yuv420p",
        # -r as well as the filter, because it is -r that makes the
        # stream DECLARE its rate. Without it ffprobe reads 0/0 and so
        # does the television.
        "-r", str(FPS),
        "-g", str(FPS * KEYFRAME_SECONDS),
        "-keyint_min", str(FPS * KEYFRAME_SECONDS),
        "-sc_threshold", "0",
        "-crf", "32",
        "-c:a", "aac", "-b:a", "8k", "-ac", "1",
        "-shortest", "-t", str(HOLD), "-muxdelay", "0",
        "-muxpreload", "0",
        # Where this board sits in the reel, so the reel is one timeline.
        # Measured step, and a step of headroom so board zero is not
        # asked for a negative timestamp and silently clamped.
        "-output_ts_offset", f"{(place + 1) * (step or HOLD):.6f}",
        "-f", "mpegts", out,
    ]
    done = subprocess.run(command, check=False, capture_output=True, text=True)
    if done.returncode != 0:
        warn(f"ffmpeg refused to encode {out}: "
             f"{(done.stderr or '').strip()[:300]}")
        return False
    return True


def seconds_of(segment: str) -> float:
    """How long the segment REALLY is, asked of the file.

    The playlist used to declare HOLD for every entry because that is
    what the encoder was told to make. Measured, they are 20.032 —
    ffmpeg's AAC encoder emits one frame more than the arithmetic says,
    and 626 frames of 1024 samples at 32000 is 20.032 seconds.

    Thirty-two milliseconds sounds like nothing. It is an OVERLAP: the
    playlist tells the player each board ends at a moment the media says
    it is still going, and a player answers a timeline that disagrees
    with its own media by re-syncing. Six boards a lap, every lap, all
    day.

    So the file is asked rather than assumed. A segment that cannot be
    measured — the gate writes playlists for names that were never
    encoded — falls back to HOLD, which is what it was before.
    """
    try:
        done = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", segment],
            check=False, capture_output=True, text=True)
        found = float(done.stdout.strip())
        return found if 0 < found < HOLD * 3 else float(HOLD)
    except (ValueError, OSError):
        return float(HOLD)


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
    reel = max(1, len(segments))
    long_enough = max(reel, (WINDOW_MINUTES * 60) // HOLD)

    # A WINDOW THAT ACTUALLY SLIDES.
    #
    # This is the second half of the frozen-screen fix, and getting the
    # first half alone was worse than getting neither. MEDIA-SEQUENCE
    # numbers the FIRST segment in the window, and a player uses it to
    # work out what happened while it was away: the sequence went up by
    # thirty, so thirty segments have left the front, so what I was
    # playing is now thirty places further back.
    #
    # The first fix moved the number every pass and left the list
    # identical. A player was therefore told thirty segments had been
    # dropped from a list that had not changed at all — so it could not
    # find where it was, gave up, and re-synced. Every ten minutes, on
    # both channels. That is the buffering.
    #
    # So the list moves with the number. The reel repeats forever, the
    # window is half an hour of it, and where the window sits is decided
    # by the clock: at whole-HOLD tick T the window opens at reel
    # position T mod (length of reel). A pass ten minutes later opens
    # thirty positions further along — which is exactly what the sequence
    # number says, and now it is true. A player away for less than the
    # window's own length finds its place still in it and plays straight
    # on.
    opens_at = int(now // HOLD)

    # HOW MANY BREAKS HAVE ALREADY SCROLLED PAST, which RFC 8216 §6.2.2
    # requires of any sliding window that drops a segment carrying an
    # EXT-X-DISCONTINUITY: without it a player cannot line up the breaks
    # it has seen with the ones the new window is describing, and some
    # re-sync rather than guess. The reel wraps once every `reel`
    # segments and the window opens at `opens_at`, so exactly this many
    # wraps are behind it.
    breaks_gone = opens_at // reel

    # Measured once per board, not once per entry: the same six files
    # are named hundreds of times in one window.
    real = [seconds_of(one) for one in segments]

    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        # At least the longest segment, rounded up, which the spec
        # requires and which 20.032 breaks if this stays at 20.
        f"#EXT-X-TARGETDURATION:{max(HOLD, math.ceil(max(real)))}",
        f"#EXT-X-MEDIA-SEQUENCE:{opens_at}",
        f"#EXT-X-DISCONTINUITY-SEQUENCE:{breaks_gone}",
        # Every segment opens on a keyframe, which is what lets a player
        # read ahead instead of fetching one segment at a time.
        "#EXT-X-INDEPENDENT-SEGMENTS",
        # WHERE THE PLAYER STARTS, AND THE REASON THE WINDOW MEANS
        # ANYTHING AT ALL.
        #
        # RFC 8216 §6.3.3: on a live playlist a client SHOULD begin at
        # least three target durations back from the END. Not from the
        # start — from the end. So a viewer opening this channel joined
        # SIXTY SECONDS from the end of it, and sixty seconds is all the
        # runway they had, whether the window behind them held half an
        # hour or half a day.
        #
        # That is why lengthening the window on its own fixed nothing:
        # six hours of playlist and a minute of runway. Once that minute
        # ran out the player had to wait for a rebuild to append more,
        # and every rebuild that came late was a stall — which is the
        # buffering, reported over and over.
        #
        # This says: start at the beginning. The reel is the same two
        # minutes of boards wherever it is entered, so nothing is lost
        # by joining at the front — and the whole window becomes real
        # runway instead of decoration.
        "#EXT-X-START:TIME-OFFSET:0,PRECISE=YES",
    ]
    # A break only where the reel really starts over, which is the one
    # place the timeline goes backwards — the segments carry their place
    # in the reel, so everything between two wraps is continuous.
    for step in range(long_enough):
        place = (opens_at + step) % reel
        if place == 0:
            lines.append("#EXT-X-DISCONTINUITY")
        lines += [f"#EXTINF:{real[place]:.3f},",
                  os.path.basename(segments[place])]
    cycles = long_enough / reel
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    return cycles


def main(argv: list[str] | None = None) -> int:
    which = (argv or sys.argv[1:] or ["today_matches"])[0]
    if which not in SCREENS:
        warn(f"no screen called {which!r} — known: {', '.join(SCREENS)}")
        return 1
    prefix, playlist, stamp_name = SCREENS[which]
    out = os.path.join(OUT_DIR, playlist)
    stamp = os.path.join(OUT_DIR, stamp_name)

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
    reel = boards(prefix)[:ON_SCREEN]
    if not reel:
        warn(f"no board has been drawn for {which} — nothing to encode")
        return 0

    fingerprint = digest(reel)
    was = ""
    if os.path.exists(stamp):
        with open(stamp, encoding="utf-8") as handle:
            was = handle.read().strip()
    if was == fingerprint and os.path.exists(out):
        # Sweep even when nothing is re-encoded. The sweep used to run only
        # after an encode, so a segment orphaned any other way stayed
        # forever: two scheduled passes failed to push, left main holding
        # segments for boards that had moved on, and every pass after them
        # matched the fingerprint, returned here, and never looked. The
        # screen gate found them days later.
        segments = [segment_of(board) for board in reel]
        dropped = forget_old_segments(segments, prefix)
        if dropped:
            log(f"  {dropped} segment(s) nothing points at any more, removed")

        # AND REWRITE THE PLAYLIST ANYWAY, which is the whole difference
        # between a channel that keeps playing and one that stops with a
        # spinner on the last board.
        #
        # A live playlist is a WINDOW, and a player only keeps playing
        # while the window keeps moving. This one holds thirty minutes of
        # content; MEDIA-SEQUENCE is what says where that window sits.
        # Written only on a re-encode, it froze the moment the boards
        # stopped changing — so a viewer played through the thirty
        # minutes, asked for the next segment, and was handed a playlist
        # that said the window had not moved since. There is nothing more
        # to play in it, so the player waits. That wait is the loading
        # circle on the last page, and it never resolves on its own.
        #
        # Rewriting it every pass costs nothing — the segments are
        # identical and none is re-encoded — and moves the window forward
        # by the ten minutes that passed, which is exactly what the
        # player is asking to be told.
        cycles = write_playlist(segments, out)
        log(f"{which}: the screen already shows these boards — not "
            f"re-encoded, and the playlist window moved on ({cycles} "
            f"cycles, {WINDOW_MINUTES} minutes)")
        return 0

    os.makedirs(OUT_DIR, exist_ok=True)

    # THE STEP IS MEASURED BEFORE ANYTHING IS PLACED. The first board is
    # encoded on its own, its real length read off the file, and every
    # board after it is placed by that. Guessing the step is what put a
    # 32 ms overlap on every boundary; the encoder is the only thing that
    # knows, so it is asked.
    first = segment_of(reel[0])
    if not encode_segment(reel[0], first, 0, HOLD):
        return 1
    step = step_of(first)
    if abs(step - HOLD) > 0.001:
        log(f"  a board measures {step:.3f}s, not {HOLD}s — placing every "
            f"board by the measured length so no boundary overlaps")
    # Re-placed with the step now known, so board zero sits on the same
    # timeline as the rest.
    if not encode_segment(reel[0], first, 0, step):
        return 1

    segments = []
    for place, board in enumerate(reel):
        segment = segment_of(board)
        if place == 0:
            segments.append(segment)
            continue
        if not encode_segment(board, segment, place, step):
            # Same reasoning: what is published stays, and this pass says
            # it failed so nothing is committed on top of it.
            return 1
        segments.append(segment)

    cycles = write_playlist(segments, out)
    dropped = forget_old_segments(segments, prefix)
    if dropped:
        log(f"  {dropped} segment(s) nothing points at any more, removed")

    with open(stamp, "w", encoding="utf-8") as handle:
        handle.write(fingerprint + "\n")
    bytes_on_disk = os.path.getsize(out) + sum(os.path.getsize(s)
                                               for s in segments)
    log(f"{which} re-encoded: {len(segments)} segment(s) at {HOLD}s, "
        f"played {cycles} times over = a {WINDOW_MINUTES}-minute "
        f"live window, "
        f"{bytes_on_disk // 1024} KB on disk in total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
