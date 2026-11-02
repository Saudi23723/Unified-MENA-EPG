#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The second clock: the same four channels, told in UAE time.

"copy full links for 4 channels + second link set with all times in UAE
time (Asia/Dubai)" — asked for as links, and links are what the four
generators already publish: boards, a guide and an encoded screen each.
So the second set is drawn by the same generators, from the same
collected events, in the same pass — not converted from the first set
afterwards.

WHY DRAWN RATHER THAN CONVERTED. The first channel's guide carries its
clock inside sentences — "10:00 بعد ساعتين", "مباريات السبت — بتوقيتك",
a board whose every row is a kickoff in the viewer's zone — and a
sentence with the clock baked into it cannot be re-zoned without
re-parsing it. The generator that wrote it can simply write it again
with a different zone on its wrist, which is what the swap below does:
the module's VIEWER is the one thing every clock in the file reads, so
changing it changes the file.

THE ZONE IS SWAPPED, NOT THE DATA. The events were collected once, from
the same sources, in one network pass; the second render groups them by
the Gulf's dates and prints the Gulf's hours. No page is fetched twice,
and nothing about the first set's build is on the path of the second:
the swap is undone in a finally, and a failure in the second render
warns and leaves the first set exactly as it was written.

THE DAYS COME FROM THE EVENTS. The collecting window is the first
viewer's — their today through their last day — which in the Gulf's
clock runs from mid-morning to mid-morning. So the Gulf's days are
taken from where the collected events actually fall, today first, so
that a match at the far edge of the window is never dropped for having
landed on a date the window never named.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# The zone the second set is asked for in, by name: UAE time.
DUBAI = ZoneInfo("Asia/Dubai")

# What every clock-bearing sentence says, where the first set says
# "بتوقيتك". Stated as a place rather than a zone word, because that is
# how the reader asked for it and how a board reads from across a room.
DUBAI_NAME = "بتوقيت الإمارات"


@contextmanager
def the_other_clock(module_globals: dict, **wear):
    """Put the module in the Gulf's clock for the block, whatever else
    it was wearing.

    Takes the module's own globals() — the one dict every function in
    that module reads its VIEWER from — so the swap is seen by every
    helper without any of them being told. Whatever names are handed
    over are restored exactly, in a finally, so an exception in the
    second render cannot leave the first set's generator in the wrong
    zone for whoever calls it next.
    """
    saved = {name: module_globals[name] for name in wear}
    module_globals.update(wear)
    try:
        yield
    finally:
        module_globals.update(saved)


def days_the_events_span(now: datetime, events: list[dict],
                         viewer) -> list[date]:
    """The days to draw for the other clock: today, out to whatever the
    collected events reach.

    The window the events came out of is the FIRST viewer's — their
    midnight to their midnight — which straddles two of the Gulf's dates
    at each end: the reader's day begins eleven hours before the Gulf's
    ends, so the reader's "three days" arrive as the Gulf's today from
    mid-morning and run to the Gulf's fourth day at mid-morning. Drawing
    the Gulf's "today plus the same number of days" would drop
    everything on that far straddle — a match the first channel shows
    would be missing from the second for no reason but the clock it is
    printed in. So the last day is wherever the last collected event
    falls, and no match is dropped.
    """
    first = now.astimezone(viewer).date()
    last = max((event["start"].astimezone(viewer).date()
                for event in events), default=first)
    return [first + timedelta(days=step)
            for step in range((last - first).days + 1)]
