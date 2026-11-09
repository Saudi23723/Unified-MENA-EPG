#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HYPE Fighting Championship's cards on channel 2 — asked for by name.

WHY THESE ARE WRITTEN DOWN AND NOT READ. Every other promotion on this
board is read off its own page (pfl_events.py, brave_cf.py,
uae_warriors.py). HYPE publishes no calendar anybody can read: its site
(hypefc.ru) carries its reality show and no fight dates, Sherdog lists no
upcoming HYPE event, and Tapology answers a runner with Cloudflare's wall
and its reader with a rate-limit refusal — all measured on 1 October
2026. So the cards HYPE has announced are kept here, each with where the
date, the hour and the carrier were published, and each drops off the
board by itself once it is over. A card that is announced later is one
line added below.

THE HOUR IS THE VENUE'S, in the venue's own zone, so the row lands on the
minute the promotion gave and the board prints it in each viewer's clock.
AND THE CARRIER IS THE ONE ANNOUNCED; with none announced the row says
PPV, like every promotion that sells its own card.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from epg_lib import log

# (the card, its local start, the venue's zone, carriers, where it was said)
CARDS = (
    # HYPE Quito: Chito Vera vs José Aldo (submission-only grappling) and
    # Mayton Perea vs Colby Covington; 15 bouts, nine bare-knuckle. Sunday
    # 4 October 2026, 16:00, Coliseo General Rumiñahui; streamed on Zapping
    # (El Universo and Metro Ecuador, 28-30 September 2026).
    ("HYPE FC Quito: Chito Vera vs. José Aldo", "2026-10-04 16:00",
     "America/Guayaquil", ["Zapping"], "eluniverso.com"),
)

# How long a card stays on the board after it starts.
RUNS = timedelta(hours=4)


def events(session=None, floor=None, ceiling=None) -> list[dict]:
    now = datetime.now(timezone.utc)
    out = []
    for title, local, zone, channels, said in CARDS:
        start = datetime.strptime(local, "%Y-%m-%d %H:%M").replace(
            tzinfo=ZoneInfo(zone)).astimezone(timezone.utc)
        if start + RUNS < now:
            continue
        if floor is not None and not (floor <= start < ceiling):
            continue
        out.append({"start": start, "title": title, "sport": "MMA",
                    "competition": "HYPE FC", "channels": list(channels),
                    "source": "hypefc"})
        log(f"  hype fc: {title}, {start:%d.%m %H:%M} UTC "
            f"({', '.join(channels) or 'PPV'}; announced on {said})")
    return out
