#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""مباريات اليوم — تجريبي: the first channel's matches, drawn the new way.

A TRIAL THAT STANDS BESIDE THE FIRST CHANNEL RATHER THAN REPLACING IT.
Asked for in those words — "مش تبدلها تضيفها اشوفها بعيني" — after three
photographs of V Sport's own info screen and "اشي moder و simple و
professional". So there are two links carrying the same matches: channel
one with the card board it has always had, and this one with the
broadcaster's now-and-next table, to be judged side by side on the
television.

NOTHING IS DUPLICATED TO MAKE IT. The whole of channel one's gathering —
five sources, the unifier, the competition filter, the channel
folding — is that module's, and this one borrows it whole for the length
of one build: it swaps the names that say WHERE a build writes, runs
channel one's own build, and puts them back. So the two channels cannot
drift apart in which matches they carry or how a name is spelled; the
only difference between them is the drawing, which is the one thing
being judged.

If the answer comes back yes, channel one sets BOARD_STYLE = "vsport"
and this file is deleted. If it comes back no, this file is deleted and
nothing else changes. Either way the first channel was never at risk.
"""
from __future__ import annotations

import sys

import dubai_time
import today_matches_epg as base

CHANNEL_ID = "TodayMatchesNew"
CHANNEL_AR = "مباريات اليوم — تجريبي"
OUTPUT = "today_matches_new_epg.xml"
# NOT "today_matches_new_", and that is the whole reason this channel
# failed to reach the screen the first time it was built. A screen owns
# its boards and its segments BY PREFIX — seven different places ask
# name.startswith(prefix) — so a prefix that begins with another
# screen's prefix makes that screen swallow this one's files.
# "today_matches_" is the first channel's, and it is a strict prefix of
# "today_matches_new_": channel one counted trial_matches boards as its
# own, and the screen gate then crashed reading a number out of a name
# its pattern could not match, which stopped the whole pass publishing.
# "trial_" begins no other screen's name, so nothing owns these files
# but this channel.
BOARD_PREFIX = "trial_matches_"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/today_matches_new.png")

# The second clock gets trial names of its own too, so that running this
# cannot write over the guide or the boards the REAL UAE channel is
# serving. They are not registered as a screen — one link is enough to
# look at a drawing — but they must not collide.
DUBAI_OUTPUT = "dubai_matches_new_epg.xml"
DUBAI_CHANNEL_ID = "TodayMatchesNewDubai"
# Same rule: "dubai_matches_" is the real UAE channel's prefix.
DUBAI_BOARD_PREFIX = "trial_dubai_matches_"


def build() -> int:
    """Channel one's build, writing to this channel's files in the new shape."""
    with dubai_time.the_other_clock(
            base.__dict__,
            CHANNEL_ID=CHANNEL_ID, CHANNEL_AR=CHANNEL_AR,
            OUTPUT=OUTPUT, BOARD_PREFIX=BOARD_PREFIX, LOGO=LOGO,
            BOARD_STYLE="vsport",
            DUBAI_OUTPUT=DUBAI_OUTPUT,
            DUBAI_CHANNEL_ID=DUBAI_CHANNEL_ID,
            DUBAI_BOARD_PREFIX=DUBAI_BOARD_PREFIX):
        return base.build()


if __name__ == "__main__":
    sys.exit(build())
