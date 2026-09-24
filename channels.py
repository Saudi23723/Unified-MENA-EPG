#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WHICH CHANNELS THERE ARE — stated once, here, and nowhere else.

THE FAULT THIS EXISTS TO END, and it cost an hour of frozen boards on
2026-09-13 after costing smaller amounts before that.

Every channel used to be named twice inside the workflow file: once as
its own build step, once again in the ticker's list. A workflow's steps
are FROZEN when a run starts, but the code underneath them is not —
publish_screens does `git reset --hard origin/main` every pass, so a
channel added or deleted on main changes the files under a list that
cannot change. Run #916 was still calling a channel that had been
deleted half an hour earlier; the loop runs under `set -e`, so the
missing file killed the pass at its second command, before a single
channel was rebuilt, and went on doing that for an hour.

Patching that one loop to skip a missing file would have fixed the
symptom and left the disease: two lists that must agree and no way to
make them. So the workflow now names NO channel at all. It runs
one_pass.py, which reads this.

WHAT IS WRITTEN HERE IS THE MINIMUM. Only the build modules, in the
order they run — channel 1 first, because it is the one a reader opens.
Which SCREENS each one produces is not written down: a module already
declares its own board prefixes, and publish_screens already maps a
prefix to a screen, so the answer is derived from the two of them by
screens_of(). A list that is derived cannot fall out of step with what
it describes, which is the whole point of this file.

Adding a channel is one line here plus its entries in the two
registries it genuinely needs. Deleting one is the same line removed —
and a run already in flight picks that up on its next pass instead of
dying on it.
"""
from __future__ import annotations

import importlib

# In the order they are built. Channel 1 leads because a reader opening
# the list opens it first, so it should be the freshest thing there.
BUILDS: tuple[str, ...] = (
    "today_matches_epg",
    "other_sports_epg",
    # Straight after channel 2, whose collection it is handed.
    "multi_sport_epg",
    "ball_sports_epg",
    "hoops_gridiron_epg",
    "turkish_ppv_epg",
    "sporttv_epg",
    "f1_epg",
    "news_epg",
    "weather_epg",
    "prayer_epg",
)


def screens_of(module: str) -> list[str]:
    """The screens one build module produces, derived rather than listed.

    A module says where it writes (BOARD_PREFIX, and DUBAI_BOARD_PREFIX
    for the channels that have a second clock); publish_screens says
    which screen owns a prefix. Neither has to be told about the other.
    """
    import publish_screens

    owner = {row[0]: name for name, row in publish_screens.SCREENS.items()}
    loaded = importlib.import_module(module)
    found = []
    for attribute in ("BOARD_PREFIX", "DUBAI_BOARD_PREFIX"):
        prefix = getattr(loaded, attribute, None)
        screen = owner.get(prefix) if prefix else None
        if screen and screen not in found:
            found.append(screen)
    return found


def unclaimed() -> list[str]:
    """Registered screens that no build in BUILDS produces.

    Not fatal anywhere — a screen can be registered a moment before the
    build that fills it. It is worth SAYING, though: a screen nothing
    builds is a channel that will quietly serve yesterday forever.
    """
    import publish_screens

    made = {screen for module in BUILDS for screen in screens_of(module)}
    return [name for name in publish_screens.SCREENS if name not in made]


if __name__ == "__main__":
    for name in BUILDS:
        print(f"{name:24} -> {', '.join(screens_of(name)) or '(no screen)'}")
    left = unclaimed()
    print(f"\nregistered screens nothing builds: {left or 'none'}")
