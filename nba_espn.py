#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Basketball for the NBA/NFL channel, from the league's own scoreboard.

Every game of the day, timed in UTC by the feed itself, with whatever
networks the feed names beside it. Asked for in those words: "another
channel for NFL/NBA separately all games" — so nothing is dropped for
being a local broadcast or for having no broadcaster at all. A game with
no network simply shows no broadcaster line.

The postseason arrives on the same endpoint with its own wording, so the
play-in, the conference finals and the NBA Finals need nothing written
down here: the feed labels them and the label is printed beside the game.
"""
from __future__ import annotations

from espn_league import collect_league

SCOREBOARD = ("https://site.web.api.espn.com/apis/site/v2/sports/"
              "basketball/nba/scoreboard")


def collect(session, floor, ceiling) -> list[dict]:
    return collect_league(session, floor, ceiling, SCOREBOARD, "NBA", "NBA")
