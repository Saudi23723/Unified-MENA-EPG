#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ain FM as a channel with a picture, not a black rectangle.

THE FAULT THIS REPLACES
-----------------------
Ain FM is a radio station, and what it publishes is one endless MP3 at
radio.ainfm.site. A player handed audio and no video draws nothing, so
the row tuned, the sound came out of the television, and the screen
stayed black for as long as anybody left it there. A tvg-logo does not
help: that picture is how a channel is found in a list, and it is put
away the moment the channel is playing.

WHAT A BLACK SCREEN ACTUALLY NEEDS
----------------------------------
A video track. There is no way to make a player draw a still of its
own, so the still has to arrive as video, from here, beside the sound.

The obvious way to do that is to mux the two together with ffmpeg as
they play — one process, image in, live audio in, HLS out. That process
has to be running every second the channel is watchable, and there is
nowhere here for it to run: this repository is served by
raw.githubusercontent, which hands out files and nothing else.

So the two tracks are published SEPARATELY and joined by the player, in
the one arrangement a file server can serve:

    stream/ain_fm.m3u8        a master playlist naming the two below
    stream/ain_fm_video.m3u8  the still, encoded once, listed round and
                              round for a day
    stream/ain_fm_audio.m3u8  the station's own live MP3, named as the
                              one segment it is

The still is ONE file of about twenty kilobytes and it is named by the
video playlist four thousand times, because the picture never changes:
encoding a day of identical frames into a day of distinct segments
would put a hundred megabytes a day into a git repository to say the
same thing. Repeating one segment repeats its timestamps too, so every
repeat is preceded by EXT-X-DISCONTINUITY, which is how a player is
told to expect the clock to start over.

The audio playlist is the arrangement the channel already played with
before it had a picture, and it is left exactly as it was: an endless
stream named as a segment, which a player reads progressively for as
long as it is tuned to. Nothing about the sound changes here. What is
new is that there is now something to look at while it plays.
"""
from __future__ import annotations

import os
import subprocess
import sys

from PIL import Image, ImageEnhance

from epg_lib import log, warn

# The station's own mark, taken from ainfm.com, and the only picture
# this channel ever shows. It is the playlist's tvg-logo as well, so the
# row in the list and the screen it tunes to cannot show two different
# stations.
MARK = os.path.join("logos", "ain_fm.png")

OUT_DIR = "stream"
STILL = os.path.join(OUT_DIR, "ain_fm_still.ts")
VIDEO = os.path.join(OUT_DIR, "ain_fm_video.m3u8")
AUDIO = os.path.join(OUT_DIR, "ain_fm_audio.m3u8")
MASTER = os.path.join(OUT_DIR, "ain_fm.m3u8")

# The station's live stream, read from the station and from nowhere
# else. 128 kbit MPEG audio, and it does not stop.
LIVE = "https://radio.ainfm.site/ainfm"

WIDTH, HEIGHT = 1280, 720

# The mark's own two colours, read off ainfm.com: the navy it is drawn
# in, and the white it is drawn on. The board turns them round — white
# mark on navy — because a television showing a full screen of white in
# a dark room is a lamp, not a channel.
NAVY = (34, 44, 57)
WHITE = (255, 255, 255)

# How wide the mark sits on the board. Short of the edges on purpose:
# a television that overscans eats the outermost few per cent of every
# side, and a logo laid edge to edge loses its ends to it.
MARK_WIDTH = 0.72

# One frame a second, and one keyframe per segment. The picture never
# moves, so a frame rate is only what the segment has to declare; the
# keyframe is what lets a player start on any segment it likes. Twenty
# seconds is long enough that a day of them is a small playlist and
# short enough that tuning in does not wait on a long fetch.
FPS = 1
SEGMENT = 20

# A day of them. The list has to end somewhere — a file server cannot
# extend a live playlist — so it ends a day out, and a television left
# on the channel past that reloads the master and starts the day again.
SEGMENTS = 24 * 60 * 60 // SEGMENT


def board(path: str) -> None:
    """Draw the still: the station's mark, white, centred on navy.

    The mark is recoloured rather than fetched a second time in another
    colour, because the station publishes it in one colour only and a
    second file is a second thing to keep in step with the first.
    Recolouring is safe here because the drawing is flat: every pixel is
    the navy, the white it sits on, or one of the two circles, and only
    the first two are touched.
    """
    mark = Image.open(MARK).convert("RGB")
    pixels = mark.load()
    for y in range(mark.height):
        for x in range(mark.width):
            red, green, blue = pixels[x, y]
            if red > 200 and green > 200 and blue > 200:
                pixels[x, y] = NAVY
            elif red < 90 and green < 90 and blue < 110:
                pixels[x, y] = WHITE

    width = int(WIDTH * MARK_WIDTH)
    height = round(mark.height * width / mark.width)
    mark = mark.resize((width, height), Image.LANCZOS)

    canvas = Image.new("RGB", (WIDTH, HEIGHT), NAVY)
    canvas.paste(mark, ((WIDTH - width) // 2, (HEIGHT - height) // 2))
    canvas = ImageEnhance.Brightness(canvas).enhance(0.45)
    canvas.save(path)


def encode(image: str, out: str) -> bool:
    """Encode the still as one segment of silent, single-keyframe video.

    Silent on purpose: the sound arrives on the other playlist, and a
    video track carrying its own audio as well would give the player two
    of them to choose between.
    """
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-framerate", str(FPS), "-i", image,
        "-c:v", "libx264", "-preset", "veryslow", "-tune", "stillimage",
        "-vf", f"fps={FPS}", "-pix_fmt", "yuv420p",
        "-profile:v", "main", "-level", "3.1",
        "-r", str(FPS),
        "-g", str(SEGMENT), "-keyint_min", str(SEGMENT),
        "-sc_threshold", "0",
        "-crf", "34",
        "-an",
        "-t", str(SEGMENT),
        "-muxdelay", "0", "-muxpreload", "0",
        "-f", "mpegts", out,
    ]
    done = subprocess.run(command, capture_output=True, text=True)
    if done.returncode:
        warn(f"ffmpeg would not encode the Ain FM still: "
             f"{done.stderr.strip().splitlines()[-1:] or done.returncode}")
        return False
    return True


def write(path: str, lines: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as out:
        out.write("\n".join(lines) + "\n")


def playlists() -> None:
    """The three files a player is handed, smallest first."""
    still = os.path.basename(STILL)
    video = ["#EXTM3U",
             "#EXT-X-VERSION:3",
             "#EXT-X-PLAYLIST-TYPE:VOD",
             f"#EXT-X-TARGETDURATION:{SEGMENT}",
             "#EXT-X-MEDIA-SEQUENCE:0"]
    for number in range(SEGMENTS):
        if number:
            # One file named twice is one set of timestamps twice, and a
            # player told nothing would read the second as the clock
            # running backwards and stop.
            video.append("#EXT-X-DISCONTINUITY")
        video.append(f"#EXTINF:{SEGMENT}.000,")
        video.append(still)
    video.append("#EXT-X-ENDLIST")
    write(VIDEO, video)

    write(AUDIO, ["#EXTM3U",
                  "#EXT-X-VERSION:3",
                  "#EXT-X-TARGETDURATION:86400",
                  "#EXT-X-MEDIA-SEQUENCE:0",
                  "#EXTINF:86400.0,",
                  LIVE + "?stream.mp3"])

    write(MASTER, [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="ainfm",NAME="Ain FM",'
        'DEFAULT=YES,AUTOSELECT=YES,URI="ain_fm_audio.m3u8"',
        '#EXT-X-STREAM-INF:BANDWIDTH=160000,CODECS="avc1.4d401f,mp4a.40.2",'
        f'RESOLUTION={WIDTH}x{HEIGHT},AUDIO="ainfm"',
        os.path.basename(VIDEO),
    ])


def build() -> int:
    if not os.path.exists(MARK):
        warn(f"{MARK} is not here — Ain FM has no picture to show")
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    image = os.path.join(OUT_DIR, "ain_fm_board.png")
    board(image)
    made = encode(image, STILL)
    os.remove(image)
    if not made:
        return 1

    playlists()
    log(f"{MASTER}: {SEGMENTS} × {SEGMENT}s of {os.path.basename(STILL)} "
        f"beside the station's live sound")
    return 0


if __name__ == "__main__":
    sys.exit(build())
