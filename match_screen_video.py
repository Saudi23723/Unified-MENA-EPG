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
#
# THE LAST NUMBER IS HOW LONG A PAGE STAYS UP, and it is per screen
# because a page of fixtures and a page of news are not read at the same
# speed. "الصفحة زيد وقتها فقط ل قناة الأخبار": a fixtures row is a
# clock, two club names and a channel, taken in at a glance; a news row
# is a headline and a sentence explaining it, and six of those cannot be
# read in twenty seconds.
SCREENS = {
    "today_matches": ("today_matches_", "screen.m3u8", "board.sha256", 20),
    "other_sports": ("other_sports_", "sports.m3u8", "sports.sha256", 20),
    "today_news": ("today_news_", "news.m3u8", "news.sha256", 35),
    # The fourth channel — طقس اليوم. It was a relay of somebody else's
    # CDN until that CDN stopped answering, and it is a board now for
    # the same reason the other three are: a picture this repository
    # drew is a picture nobody outside can switch off.
    #
    # TWENTY SECONDS, because a weather row is read the way a fixtures
    # row is — a city, a number, a sky — and not the way a headline is.
    # Five cities a page is a glance, and a glance does not need the
    # half a minute the bulletin's six headlines do.
    "today_weather": ("today_weather_", "weather.m3u8", "weather.sha256", 20),
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
WINDOW_MINUTES = 2 * 60

# The window only has to outlast the gap between builds now — see
# write_playlist for why EXT-X-START is not written and what that costs.
# Two hours against a ten-minute build is margin; twelve hours was 91 KB
# re-fetched on every poll, 13% of the video's own bandwidth, buying
# runway no player was reaching.

# HOW MUCH OF THE GUIDE THE CHANNEL ACTUALLY PLAYS: ALL OF IT.
#
# THIS USED TO BE "THE FIRST SIX BOARDS" AND THAT WAS THE FAULT:
#
#     "ما عم بكمل جدول السبت و لا عم يجيب الخميس و بقطع اشياء لحاله"
#
# Six boards is not six days. Thursday took two, Friday took two, and
# Saturday took SIX of its own — so the channel played Thursday, Friday,
# and the first third of Saturday, then went back to the top.
#
# The first answer was a ceiling on the LAP: whole days, but only as
# many as fit four minutes. It cut less and IT STILL CUT, measured on
# what was actually on air:
#
#     other_sports   18 boards written · 12 in the reel
#                    three days drawn, published, and never once shown
#
# reported back as "لسى عم يشطب صفحات", and rightly.
#
# SO THE CEILING IS GONE. What made it seem necessary was that a viewer
# landed at whatever board the clock happened to be on, so a long lap
# meant a long wait for today; the answer was to shorten the lap, and
# the price was days nobody ever saw.
#
# write_playlist now opens the window on the FIRST board of the lap, so
# a viewer tuning in starts at today and walks forward through the days
# in order. Nobody is dropped into the middle any more, which is what
# the ceiling was paying for — so there is nothing left to buy, and
# every day that has a board gets played.
HOLD = 20               # seconds a board stays up before the next one

# HOW FAR BACK FROM THE END OF A LIVE PLAYLIST A PLAYER BEGINS. RFC 8216
# §6.3.3: "the client SHOULD NOT choose a segment that starts less than
# three target durations from the end". Three entries, then — and it is
# a constant here because write_playlist sizes the window around it.
JOIN_BACK = 3

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
#   5  each board placed by the MEASURED length of a segment, closing a
#      32 ms overlap on every boundary
#   6  how long a board stays up is per screen, and is folded into the
#      fingerprint below — the news pages hold for 35 seconds and the
#      fixtures pages for 20, so the same picture on two screens is not
#      the same segment
#   7  THE THEME. Every segment now carries its slice of audio/theme.m4a
#      instead of silence — see THEME_LAP below for how the slice is
#      chosen so the music runs continuously through a reel.
#
# THE THEME IS NOT IN THE FINGERPRINT, because the fingerprint's recipe
# is held byte for byte by the gate and a theme swap must not quietly
# leave stale segments playing the old music either: REPLACING
# audio/theme.m4a WITH DIFFERENT AUDIO REQUIRES BUMPING THIS NUMBER, or
# every segment keeps its old name and goes on playing the music it was
# encoded with. The number is the whole mechanism.
ENCODER_REVISION = 8

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

# THE MUSIC EVERY CHANNEL PLAYS UNDER ITS BOARDS.
#
# The reader handed over one mp3 and asked for it on all four channels,
# "cropped" and working "always without messing up the contents". The
# file is audio/theme.m4a, 140.000 seconds exactly, built from it once:
# the source's quiet lead-in and its silent tail are cropped away, the
# music is normalised to −20 LUFS so it sits under an information board
# rather than shouting over it, and the END AND THE BEGINNING ARE THE
# SAME INSTANT OF THE SOURCE — the loop-back is an acrossfade inside the
# file, so playing it round and round is one continuous piece.
#
# 140 IS THE LEAST COMMON MULTIPLE OF THE TWO PAGE HOLDS, 20 and 35, so
# the slice a board carries is place x HOLD mod 140 and every slice
# abuts the one before it: a reel plays the theme end to end, and where
# the reel is longer than a lap the music wraps at the seam the file was
# built to hide.
#
# EACH SLICE IS FADED A QUARTER OF A SECOND AT BOTH EDGES. That is not
# decoration: an independently encoded AAC segment carries about 64 ms
# of decoder priming at its head, and a slice that starts loud butt-ended
# against the one before it drops those samples out — a click on every
# page turn, measured on segments encoded in this very repository. A
# 400 ms breath at each edge is wider than the priming by an order of
# magnitude and reads as the page turning, which is what the ear is
# being told anyway. The fades are symmetric and deterministic, so the
# same slice still encodes to the same bytes.
#
# THE FALLBACK IS SILENCE, because a channel whose music track is
# missing is a channel, and a channel with no audio track at all can be
# a black screen on some players. If audio/theme.m4a is not where this
# expects it, the segment is encoded exactly as revision 6 encoded it,
# and the picture is untouched either way.
THEME = "audio/theme.m4a"      # kept as the shared fallback
THEMES = {
    "today_matches": "audio/theme_matches.m4a",
    "other_sports": "audio/theme_sports.m4a",
    "today_news": "audio/theme_news.m4a",
    "today_weather": "audio/theme_weather.m4a",
}
THEME_LAP = 140.0
THEME_FADE = 0.4


def days_of(prefix: str) -> list[int]:
    """How many boards each day took, as the builder wrote it down.

    Empty when there is no manifest — an older build, or the second
    screen, which has never had one. The caller falls back to a count of
    boards, which is what this replaced.
    """
    path = os.path.join(BOARD_DIR, f"{prefix}days.txt")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            return [int(line) for line in handle if line.strip()]
    except (OSError, ValueError) as exc:
        warn(f"{prefix}days.txt could not be read ({exc}) — falling back "
             f"to a plain board count")
        return []


def whole_days(prefix: str, every: list[str]) -> list[str]:
    """Every board the builder drew, in the order of the days.

    IT DROPS NOTHING. The manifest is still read, because it is the only
    thing that knows where one day ends and the next begins, but it is
    read to CHECK the reel rather than to cut it: a day counted in the
    manifest and missing from the folder is worth saying out loud, and a
    board in the folder that no day claims is still a board somebody
    drew and is still played.
    """
    counts = days_of(prefix)
    if not counts:
        log(f"  no day manifest — playing all {len(every)} board(s) in "
            f"the order they were drawn, {len(every) * HOLD}s a lap")
        return every

    covered = sum(counts)
    if covered != len(every):
        # The two disagree: a build wrote one and not the other, or a day
        # left the window between them. THE FOLDER WINS, because it is
        # what exists — dropping a drawn board on the strength of a stale
        # count is the fault this whole function was rewritten to end.
        warn(f"{prefix}days.txt accounts for {covered} board(s) and the "
             f"folder holds {len(every)} — playing every board there is")

    log(f"  the reel is {len(every)} board(s) over {len(counts)} day(s) — "
        f"{len(every) * HOLD}s a lap, nothing left out")
    return every


def digest(paths: list[str]) -> str:
    """One fingerprint for the whole reel, so any board changing re-encodes.

    The encoder's own revision is folded in, because a segment is made of
    two things — the picture, and how the picture is encoded — and only
    one of them used to be counted.
    """
    running = hashlib.sha256()
    running.update(f"encoder:{ENCODER_REVISION} hold:{HOLD}\n".encode())
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


# HOW LONG A SEGMENT LIVES AFTER IT LEAVES THE PLAYLIST.
#
# THIS USED TO BE "ONE PASS" AND ONE PASS IS NOT A LENGTH OF TIME. It was
# reasoned as "one pass, ten minutes, twice the cache it has to outlive",
# and the arithmetic only holds while builds are ten minutes apart. They
# are not: the ten-minute schedule and the full hourly build both push,
# and a manual dispatch pushes too, so three landed inside seven minutes:
#
#     20:04  news renamed        20:10  news renamed
#     20:07  news renamed        20:13  news renamed
#
# raw.githubusercontent serves the playlist with a FIVE-MINUTE cache, so
# a television was reading a playlist from 20:07 whose segments 20:10 had
# already deleted:
#
#     An error occurred: code 404     photographed at 13:09 PT = 20:09 UTC
#
# So the grace is a CLOCK now, not a counter. Half an hour outlives the
# cache six times over and does not care how fast builds land.
#
# It is stamped in a file rather than read off the filesystem, because
# every build starts from a fresh clone and every file in it has the same
# mtime — the checkout's.
GRACE_SECONDS = 30 * 60

# And a ceiling, so a day of churn cannot fill the repository: at most
# this many laps of segments are ever kept behind the playlist. The
# oldest go first.
GRACE_LAPS = 3


def still_wanted(prefix: str) -> dict[str, float]:
    """Segments kept behind the playlist, and when each left it.

    Read from the ledger the last pass wrote. A missing or unreadable
    ledger is not a failure — it means the next pass stamps everything it
    finds with now, which costs one extra grace period and nothing else.
    """
    out: dict[str, float] = {}
    for name in (f"{prefix}keeping.txt", f"{prefix}previous.txt"):
        path = os.path.join(OUT_DIR, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                parts = line.split()
                if not parts:
                    continue
                try:
                    when = float(parts[1])
                except (IndexError, ValueError):
                    continue
                out.setdefault(parts[0], when)
    return out


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
    longer. HOW LONG IS A CLOCK AND NOT A COUNT OF PASSES — see
    GRACE_SECONDS for the 404 that taught it.
    """
    now = time.time()
    wanted = {os.path.basename(path) for path in keep}
    left_at = still_wanted(prefix)

    spared: dict[str, float] = {}
    stale: list[tuple[float, str]] = []
    for name in sorted(os.listdir(OUT_DIR)):
        if not (name.startswith(prefix) and name.endswith(".ts")):
            continue
        if name in wanted:
            continue
        # First seen leaving the playlist now, unless a pass before this
        # one already stamped it.
        when = left_at.get(name, now)
        if now - when <= GRACE_SECONDS:
            spared[name] = when
        else:
            stale.append((when, name))

    # THE CEILING, oldest first, so a day of churn cannot fill the
    # repository however fast the boards change.
    room = max(len(wanted), 1) * GRACE_LAPS
    if len(spared) > room:
        for when, name in sorted((w, n) for n, w in spared.items())[:-room]:
            stale.append((when, name))
            del spared[name]

    for _, name in stale:
        os.remove(os.path.join(OUT_DIR, name))

    # TWO RECORDS, because the sweep and the gate need different facts
    # and writing one for both is how this went wrong the first time.
    #
    #   previous.txt  what THIS pass published, each stamped with now.
    #                 The next pass reads it to learn when a segment it
    #                 no longer names was last on the air.
    #   keeping.txt   what this pass SPARED, each with the moment it LEFT
    #                 the playlist — carried forward, not restamped, or
    #                 the grace would never expire. It is on disk and the
    #                 playlist does not name it, which is exactly what
    #                 the screen gate is built to catch, so the gate is
    #                 told by name which files are there on purpose.
    #
    # Writing the current set to both looked equivalent and is not: the
    # gate then reads "what is current" where it needed "what is kept",
    # sees a spared segment it was never told about, and stops the build.
    records = (
        (f"{prefix}previous.txt", [(name, now) for name in sorted(wanted)]),
        (f"{prefix}keeping.txt", sorted(spared.items())),
    )
    for name, rows in records:
        with open(os.path.join(OUT_DIR, name), "w",
                  encoding="utf-8", newline="\n") as handle:
            handle.write("".join(f"{one} {when:.0f}\n" for one, when in rows))
    if spared:
        oldest = min(spared.values())
        log(f"  {len(spared)} segment(s) kept behind the playlist, the "
            f"oldest for {int(now - oldest) // 60} min, so a television "
            f"on a cached playlist does not hit a 404")
    return len(stale)


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

    AND THE SAME PLACE CHOOSES THE MUSIC. Board k carries the slice of
    the theme that begins k x HOLD into it (wrapped at the lap), so the
    reel's audio is the theme played through, one slice after another,
    with a breath at each page turn. See THEME_LAP for why that is
    continuous and THEME_FADE for why each edge is faded. When the theme
    is missing the segment is encoded silent, exactly as revision 6
    encoded it, and the channel stays up.
    """
    hold = step if step is not None else HOLD
    where = (place * hold) % THEME_LAP
    end = where + hold

    fade_in = f"afade=t=in:st=0:d={THEME_FADE}"
    fade_out = (f"afade=t=out:st={max(0.0, hold - THEME_FADE):.6f}"
                f":d={THEME_FADE}")

    # THE MUSIC IS THE SLICE OF THE THEME THIS BOARD'S PLACE LANDS ON,
    # or silence when the theme is not there. Three shapes:
    #
    #   whole      [where, where+hold] fits inside the lap
    #   wrapping   the slice crosses the lap's end: the tail of this lap
    #              and the head of the next, concatenated — the seam is
    #              the one the theme file was built to hide
    #   silent     audio/theme.m4a is missing and the picture is the thing
    if os.path.exists(THEME):
        if end <= THEME_LAP + 0.000001:
            inputs = ["-i", THEME]
            filters = [
                "-filter_complex",
                f"[1:a]atrim=start={where:.6f}:end={end:.6f},"
                f"asetpts=PTS-STARTPTS,{fade_in},{fade_out}[a]",
            ]
            maps = ["-map", "0:v", "-map", "[a]"]
        else:
            inputs = ["-i", THEME]
            filters = [
                "-filter_complex",
                f"[1:a]asplit=2[u][v];"
                f"[u]atrim=start={where:.6f}:end={THEME_LAP:.6f},"
                f"asetpts=PTS-STARTPTS,{fade_out}[p];"
                f"[v]atrim=start=0:end={end - THEME_LAP:.6f},"
                f"asetpts=PTS-STARTPTS,{fade_in}[q];"
                f"[p][q]concat=n=2:v=0:a=1[a]",
            ]
            maps = ["-map", "0:v", "-map", "[a]"]
        codec = ["-c:a", "aac", "-b:a", "96k", "-ac", "2", "-ar", "32000"]
    else:
        inputs = [
            # Silent audio: a live-television player with no audio track
            # at all will sometimes sit on a black screen rather than
            # show the video. 32000 and not 16000, measured rather than
            # chosen: 20 x 16000 runs 96 ms long, 20 x 32000 runs 32 ms
            # long.
            #
            # THE ARITHMETIC HERE USED TO SAY 32000 CAME OUT EXACT — 625
            # frames of 1024 samples is 20.000 — and the files say
            # otherwise. Every one of the six on air measures 20.032,
            # which is 626 frames: the encoder emits one past the count,
            # and neither -shortest, -t, -frames:a nor an atrim filter
            # removes it. Only dropping the audio does, and a player with
            # no audio track will sometimes show black, so the audio
            # stays.
            #
            # The excess is not worth fighting, and it is not a rule that
            # could be derived either — 16000 starts 0.064 early and runs
            # 0.096 long, 48000 starts 0.021 early and runs 0.032 long.
            # So it is MEASURED, and every board is placed by the
            # measured length rather than by HOLD, which is what closes
            # the overlap. The theme slice, when the theme is there,
            # lands on the same 20.032 for the same reason: 1024 samples
            # to an AAC frame, one frame more than the arithmetic says.
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=mono:sample_rate=32000",
        ]
        filters, maps = [], []
        codec = ["-c:a", "aac", "-b:a", "8k", "-ac", "1"]

    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-framerate", str(FPS), "-i", board,
        *inputs,
        *filters,
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
        *codec,
        *maps,
        "-shortest", "-t", f"{hold:.6f}", "-muxdelay", "0",
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
    """A VOD playlist, so the channel ALWAYS opens on board zero.

    This was live for a while — a sliding window with a moving
    MEDIA-SEQUENCE and no ENDLIST — so the television could show the next
    day without the viewer reopening the channel. The cost was the one
    fault asked about more than any other:

        "خليهم دائما لما افتح اي قناة يبدا من الاول عشان ما بخربط"

    A live client is free to join a window near its END (RFC 8216 §6.3.3
    starts it about three target durations back), and EXT-X-START — the
    one tag that pins the open point — took all three channels off the
    air twice and cannot be used. So "always from the first page" and a
    live window are not both achievable on the television in question,
    and the first is what was actually asked for.

    A VOD playlist settles it with no tag a player may refuse:

      PLAYLIST-TYPE:VOD and EXT-X-ENDLIST say the reel is complete, so
      every player opens it at the FIRST segment and plays to the end —
      board zero, every time, on every device.
      MEDIA-SEQUENCE:0, fixed, because the list is the whole reel and
      never slides.
      ONE EXT-X-DISCONTINUITY at the top only. The segments are stamped
      as one continuous timeline (encode_segment places each at its
      offset), and a VOD reel does not wrap, so there is no interior
      point where the timeline goes backwards.

    THE TRADE, written down rather than glossed: a viewer already
    watching does NOT see the next day roll in on its own — the daily
    rebuild changes these files, and the player picks the new reel up
    the next time the channel is opened. For a board that changes once a
    day that is the right side of the trade; a channel that reliably
    opens on page one beats one that updates in place but opens wherever
    it likes.

    raw.githubusercontent still serves with a five-minute cache, which
    only delays when a reopened channel sees the new reel — it does not
    affect the open point.
    """
    now = now or time.time()
    reel = max(1, len(segments))

    # Measured once per board, not once per entry.
    real = [seconds_of(one) for one in segments]

    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{max(HOLD, math.ceil(max(real)))}",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-PLAYLIST-TYPE:VOD",
        "#EXT-X-INDEPENDENT-SEGMENTS",
        # One break at the head of the reel, where the timeline begins.
        "#EXT-X-DISCONTINUITY",
    ]
    for place in range(reel):
        lines += [f"#EXTINF:{real[place]:.3f},",
                  os.path.basename(segments[place])]
    lines.append("#EXT-X-ENDLIST")
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    # One pass over the reel — a VOD playlist is exactly one cycle.
    return 1.0


def main(argv: list[str] | None = None) -> int:
    which = (argv or sys.argv[1:] or ["today_matches"])[0]
    if which not in SCREENS:
        warn(f"no screen called {which!r} — known: {', '.join(SCREENS)}")
        return 1
    prefix, playlist, stamp_name, seconds = SCREENS[which]

    # HOW LONG A PAGE STAYS UP, set once for this screen before anything
    # is measured, encoded or written. Everything below reads HOLD — the
    # encoder's -t, the playlist's window and target duration, the
    # timeline step — so there is one place it can be wrong, and it is
    # folded into the fingerprint so a change to it re-encodes rather
    # than leaving a playlist declaring a length its segments do not
    # have.
    global HOLD, THEME                                     # noqa: PLW0603
    HOLD = seconds
    THEME = THEMES.get(which, THEME)
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
    reel = whole_days(prefix, boards(prefix))
    if not reel:
        warn(f"no board has been drawn for {which} — nothing to encode")
        return 0

    fingerprint = digest(reel)
    was = ""
    if os.path.exists(stamp):
        with open(stamp, encoding="utf-8") as handle:
            was = handle.read().strip()
    # EVERY SEGMENT THE REEL NEEDS, AND WHETHER IT IS ACTUALLY THERE.
    #
    # segment_of() computes a NAME from a board's bytes. It does not
    # promise the file exists, and the fast path below used to take the
    # names on trust: matching fingerprint, so nothing was re-encoded,
    # so the playlist was written from names alone. A name whose file had
    # gone was published exactly like one whose file was there.
    #
    # THAT IS THE SKIPPED PAGE. A missing segment is a 404 to the
    # television, and a player that cannot fetch one segment of a VOD
    # reel does not stop — it moves to the next one. The viewer sees the
    # day open on page 2, with page 1 never drawn:
    #
    #     "it skipped one page on Sunday it went directly to 2"
    #
    # Sunday was three boards; the first of them was named in the
    # playlist and was not in the repository, so the page a viewer was
    # meant to open on was the one page they never saw. Nothing about
    # the board was wrong — it was drawn, it was numbered, it was
    # committed. Only the segment was gone.
    #
    # A segment can go missing without the fingerprint noticing: the
    # stamp tracks THE BOARDS, not the files encoded from them, so any
    # pass that lost a .ts while leaving boards/ and the stamp intact
    # left this function certain there was nothing to do. The retry loop
    # in the workflow resets to main and restores only the paths its own
    # commit touched, which is exactly such a pass.
    #
    # So existence is CHECKED rather than assumed, and a missing segment
    # is re-encoded rather than published as a name. The check is one
    # stat per board — nothing measurable against an encode — and it runs
    # on every pass, which is what makes the skip impossible rather than
    # unlikely.
    wanted_segments = [segment_of(board) for board in reel]
    absent = [seg for seg in wanted_segments if not os.path.exists(seg)]
    if absent and was == fingerprint:
        warn(f"{which}: {len(absent)} segment(s) the reel needs are not on "
             f"disk though the boards have not changed — re-encoding rather "
             f"than publishing a playlist that names them: "
             f"{', '.join(os.path.basename(one) for one in absent[:4])}")

    if was == fingerprint and os.path.exists(out) and not absent:
        # Sweep even when nothing is re-encoded. The sweep used to run only
        # after an encode, so a segment orphaned any other way stayed
        # forever: two scheduled passes failed to push, left main holding
        # segments for boards that had moved on, and every pass after them
        # matched the fingerprint, returned here, and never looked. The
        # screen gate found them days later.
        segments = wanted_segments
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
        write_playlist(segments, out)
        log(f"{which}: the screen already shows these boards — not "
            f"re-encoded, VOD playlist rewritten so the channel opens "
            f"on board zero ({len(segments)} segment(s))")
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

    write_playlist(segments, out)
    dropped = forget_old_segments(segments, prefix)
    if dropped:
        log(f"  {dropped} segment(s) nothing points at any more, removed")

    with open(stamp, "w", encoding="utf-8") as handle:
        handle.write(fingerprint + "\n")
    bytes_on_disk = os.path.getsize(out) + sum(os.path.getsize(s)
                                               for s in segments)
    log(f"{which} re-encoded: {len(segments)} segment(s) at {HOLD}s, "
        f"VOD reel that opens on board zero, "
        f"{bytes_on_disk // 1024} KB on disk in total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
