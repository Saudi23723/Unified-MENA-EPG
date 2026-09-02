#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI Sports Dashboard — one group, one channel.

This file has been three things, and the television decided each time.

First it was one entry per match: a playlist group renders as a full
screen list of rows, which was the shape asked for and an EPG could never
give. Then the day moved out of the row names and into group titles,
because an Arabic word at the head of a line of Latin club names turned
the whole row round and put the clock at its far end.

And then the group titles were the problem: four headings — the dashboard,
today, tomorrow, the day after — for one list, which is three more than
anybody wants to scroll past. What settled it is that the rows were never
playable. Their URLs are placeholders, because a real one carries a
username and password and this repository is public. A list of channels
that do not play, sitting under four headings, is clutter wearing the
costume of a feature.

So: one group, one channel, and that channel is the screen — the day's
boards encoded as video and listed round and round for half a day. It
plays, it needs no URL of anyone's, and it says everything the rows said,
in a form built to be looked at from across a room.

The matches themselves still publish, in the guide, as text: مباريات اليوم
in today_matches_epg.xml. Nothing was lost by taking the rows out.
"""
from __future__ import annotations

import os
import re
import sys

from epg_lib import log, warn
from today_matches_epg import CHANNEL_AR, CHANNEL_ID, LOGO

OUTPUT = "ai_sports_dashboard.m3u"
GROUP = "AI Sports Dashboard"

# The screen channel: the days' boards as video, listed round and round.
SCREEN_FILE = "stream/screen.m3u8"
SCREEN_URL = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
              "main/stream/screen.m3u8")
SCREEN_NAME = "📺 مباريات اليوم"


def clean(value: str) -> str:
    """Flatten anything that would break the line this sits on."""
    return re.sub(r"\s+", " ", (value or "").replace('"', "")).strip()


def attribute(value: str) -> str:
    """A value safe to put inside double quotes in an #EXTINF line.

    The quote goes because a stray one ends the attribute and swallows the
    rest of the line; the comma goes because the display name begins at
    the first comma, and one here would start it early.
    """
    return clean(value).replace(",", " ")


def display(value: str) -> str:
    """The name after the comma, which may not contain a comma itself."""
    return clean(value).replace(",", " ·")


def build() -> int:
    if not os.path.exists(SCREEN_FILE):
        warn(f"{SCREEN_FILE} has not been encoded — the playlist is left "
             f"exactly as it was published")
        return 1

    lines = [
        "#EXTM3U",
        f'#EXTINF:-1 tvg-id="{attribute(CHANNEL_ID)}" '
        f'tvg-name="{attribute(CHANNEL_AR)}" tvg-logo="{LOGO}" '
        f'group-title="{attribute(GROUP)}",{display(SCREEN_NAME)}',
        SCREEN_URL,
    ]

    # No BOM: a byte-order mark in front of #EXTM3U makes a player refuse
    # the file outright.
    with open(OUTPUT, "w", encoding="utf-8", newline="\n") as out:
        out.write("\n".join(lines) + "\n")

    log(f"{OUTPUT}: one channel under “{GROUP}”, pointing at the screen")
    return 0


if __name__ == "__main__":
    sys.exit(build())
