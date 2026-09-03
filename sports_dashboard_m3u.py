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
from other_sports_epg import CHANNEL_AR as SPORTS_AR
from other_sports_epg import CHANNEL_ID as SPORTS_ID
from other_sports_epg import LOGO as SPORTS_LOGO
from news_epg import CHANNEL_AR as NEWS_AR
from news_epg import CHANNEL_ID as NEWS_ID
from news_epg import LOGO as NEWS_LOGO
from today_matches_epg import CHANNEL_AR, CHANNEL_ID, LOGO

OUTPUT = "ai_sports_dashboard.m3u"
GROUP = "AI Sports Dashboard"
RAW = "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main"

# Two channels, ONE playlist, because that is the whole point of it: the
# reader pastes one link into a player and the second screen appears
# beside the first without touching anything.
#
# Each is its own encoded screen — its own boards, its own segments, its
# own live playlist — and they share only this file and the group they
# sit under.
#
# Each carries ITS OWN mark. They shared one for an afternoon and a reader
# saw the same picture on both channels — a logo is how a channel is
# found in a list, so two channels wearing one is two channels nobody can
# tell apart. Taken from each guide rather than written here, so the
# playlist and the guide can never disagree about a channel's picture.
SCREENS = (
    # (id, guide name, file that must exist, url, what the player shows,
    #  its mark)
    (CHANNEL_ID, CHANNEL_AR, "stream/screen.m3u8",
     f"{RAW}/stream/screen.m3u8", "📺 مباريات اليوم", LOGO),
    (SPORTS_ID, SPORTS_AR, "stream/sports.m3u8",
     f"{RAW}/stream/sports.m3u8", "🏁 رياضات اليوم", SPORTS_LOGO),
    (NEWS_ID, NEWS_AR, "stream/news.m3u8",
     f"{RAW}/stream/news.m3u8", "📰 أخبار اليوم", NEWS_LOGO),
)


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
    lines = ["#EXTM3U"]
    written = 0
    for channel_id, guide_name, path, url, shown, mark in SCREENS:
        if not os.path.exists(path):
            # A channel whose screen has not been encoded is left OUT
            # rather than written pointing at nothing: a row in a playlist
            # that plays nothing is worse than a row that is not there,
            # because the first looks like a fault in the television.
            warn(f"{path} has not been encoded — {guide_name} is left out "
                 f"of the playlist this pass")
            continue
        lines.append(
            f'#EXTINF:-1 tvg-id="{attribute(channel_id)}" '
            f'tvg-name="{attribute(guide_name)}" tvg-logo="{mark}" '
            f'group-title="{attribute(GROUP)}",{display(shown)}')
        lines.append(url)
        written += 1

    if not written:
        warn("no screen has been encoded — the playlist is left exactly "
             "as it was published")
        return 1

    # No BOM: a byte-order mark in front of #EXTM3U makes a player refuse
    # the file outright.
    with open(OUTPUT, "w", encoding="utf-8", newline="\n") as out:
        out.write("\n".join(lines) + "\n")

    log(f"{OUTPUT}: {written} channel(s) under “{GROUP}”")
    return 0


if __name__ == "__main__":
    sys.exit(build())
