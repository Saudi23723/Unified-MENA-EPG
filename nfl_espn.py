#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""American football for the NBA/NFL channel, from the league's feed.

Every game on the week's card, timed in UTC by the feed, with the
networks it names. Wild Card weekend, the Divisional round, the
Conference Championships and the SUPER BOWL come through the same
endpoint, labelled in the feed's own words.
"""
from __future__ import annotations

from espn_league import collect_league

SCOREBOARD = ("https://site.web.api.espn.com/apis/site/v2/sports/"
              "football/nfl/scoreboard")


def collect(session, floor, ceiling) -> list[dict]:
    return collect_league(session, floor, ceiling, SCOREBOARD, "NFL", "NFL")
