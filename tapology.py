#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tapology's fightcenter, as the fights board's calendar of last resort.

Asked for by name — "this website have all the missing parts or as a
backup for others if applicable" — and what it has that no listings page
here does is the part of fight sport nobody televises: the promotions
that sell their own card. BRAVE CF, Pancrase, OKTAGON, BKFC — every one
of them prints a start and a broadcaster on tapology.com/fightcenter,
and none of them is on wheresthematch or Sky's guide, because those
pages carry what a channel carries and these cards are their own channel.

THE BROADCAST IS READ, NOT GUESSED AT. Every event on the page names
where it is being sold — "Internet PPV", "UFC Fight Pass", "DAZN",
"YouTube", "ESPN Deportes" — and the reader asked for exactly the
honest version of that: "for channel broadcast write PPV channel
unless another source can confirm channels". So the word PPV is what
a card with no televising broadcaster gets, and the channel-confirmer
in other_sports_epg (which reads this repository's own beIN and
STARZPLAY guides) can still add a real channel beside it before the
board folds. A card confirmed on DAZN by Tapology itself keeps DAZN.

THE TIME IS EASTERN, AND ONLY EASTERN. Every event on the TV-filtered
page prints its clock with "ET" beside it — all 25 of them, measured —
so the guard is the same one real_american_freestyle uses: a time
whose zone word is not est/edt/et is not a time this page can place,
and the card is left rather than put an hour wrong.

THE PAGE IS READ THROUGH A READER, because tapology.com answers a
runner with Cloudflare's wall and nothing else. r.jina.ai renders it
to markdown and the rows keep their shape: the event's name as a
link, twice, then its clock, then the broadcaster as the first bullet
under it. The reader can refuse — it rate-limits — and on a refusal
this collector returns nothing and the board keeps what its other
sources gave it, which is the whole point of a backup.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from epg_lib import fetch, log, norm, warn

# The page through the reader. ?group=tv is the filter that matters: the
# unfiltered fightcenter carries every card anybody entered, and a card
# with no broadcaster at all is not a broadcast. The grouped page is the
# one whose events all name where they are being sold.
SOURCE = "https://r.jina.ai/https://www.tapology.com/fightcenter?group=tv"

# New York, not a fixed offset — the same guard RAF uses, for the same
# reason: a page that prints "et" all summer means EDT all summer.
EASTERN = "America/New_York"

# Only an Eastern word is a time this page can place.
AN_EASTERN_WORD = re.compile(r"^(?:est|edt|et)$", re.I)

# One event: its name as a link, twice (the page links the same event
# from its title and its card), then a bullet carrying the clock and
# its zone word — "•Saturday, September 5, 2:00 PM ET Sat Sep 5, 2pm ET".
A_HEAD = re.compile(
    r"\[([^\]]+)\]\(https://www\.tapology\.com/fightcenter/events/[^)]+\)"
    r"\[[^\]]*\]\(https://www\.tapology\.com/fightcenter/events/[^)]+\)"
    r"•([^\n]+)")

# The clock itself, out of the bullet's first half: the word after the
# time is the zone word, and only an Eastern one is accepted.
A_CLOCK = re.compile(
    r"^(?:[A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+)?"
    r"(\d{1,2}:\d{2}\s+[AP]M)\s+([A-Za-z]+)", re.I)
A_DAY = "%A, %B %d, %I:%M %p"

# The broadcast: the first bullet line after the head, before the flag
# line starts ("MMA •Pula, Istria County"). A card may have no bullet
# at all, and then there is no broadcaster to print.
A_BULLET = re.compile(r"^•(.+)$")

# The sport, off the flag line under the broadcast — "MMA •Pula" or
# "Boxing •Mexico City". Only the fights this board has a place for
# are kept; a Muay Thai or "Combat" card has no row on it.
A_FLAG = re.compile(
    r"!\[[^\]]*\]\([^)]*flags/[^)]*\)\s*([^•\n]+?)\s*•")

# How the page's broadcaster names are spelled the way a board spells
# them. The ones left unmapped keep their own casing — DAZN, YouTube
# and ESPN Deportes need no help — and "Internet PPV" and friends are
# already the honest word for what they are.
AS_PRINTED = {
    "internet ppv": "PPV",
    "ppv": "PPV",
    "internet stream": "PPV",
    "ufc fight pass": "UFC Fight Pass",
    "trillertv": "TrillerTV",
    "paramount+": "Paramount+",
    "vice tv": "Vice TV",
    "combat sports now": "Combat Sports Now",
}

# How the page's own sport words map to the two this board carries. The
# page prints them in the casing the promotion uses — "MMA" and "Boxing"
# — and that is kept exactly, because a numbered card is a name and not
# a sentence to be re-cased. A flag line can carry two of them — "MMA &
# Kickboxing", "MMA & Muay Thai" — and the first one the board has a
# place for wins; "Combat Sports" is Tapology's umbrella word and the
# cards that carry it are MMA-shaped, so it is read as MMA. A card whose
# flag line carries no sport word at all — BKFC, whose page says only
# where it is held — is judged by its name: BKFC is bare-knuckle boxing.
AS_A_SPORT = {
    "MMA": "MMA",
    "Boxing": "Boxing",
    "Combat Sports": "MMA",
    "Kickboxing": "MMA",
    "Wrestling": "MMA",
    "Jiu Jitsu": "MMA",
    "Muay Thai": None,  # no row on this board for it
}
AS_BY_NAME = {
    "BKFC": "Boxing",
}


def a_bare(name: str) -> str:
    """The event's name, as the board's other rows spell a fight card.

    Tapology writes "BRAVE CF 108" and "Contender Series 2026: Week 5"
    in the casing the promotion itself uses, and that is the casing the
    board wants too — no coming down from capitals, because a numbered
    card is a name and not a sentence.
    """
    return norm(name)


def collect(page: str) -> list[dict]:
    """Every event on the page that names a clock, a zone and a seller."""
    out: list[dict] = []
    for head in A_HEAD.finditer(page):
        name, bullet = norm(head.group(1)), head.group(2)
        clock = A_CLOCK.search(norm(bullet))
        if not clock:
            continue
        if not AN_EASTERN_WORD.search(norm(clock.group(2))):
            warn(f"tapology printed '{clock.group(2)}' beside a clock, "
                 "which is not an Eastern word — the card is left rather "
                 "than placed in a guessed zone")
            continue

        # The card's day is inside the bullet's first half — "Saturday,
        # September 5, 2:00 PM ET". Without it there is no date to build.
        a_day = re.match(r"^([A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+)"
                         r"(\d{1,2}:\d{2}\s+[AP]M)", norm(bullet))
        if not a_day:
            continue
        try:
            when = datetime.strptime(
                f"{a_day.group(1)}{a_day.group(2)}", A_DAY)
        except ValueError:
            warn(f"tapology printed a clock this reader cannot read "
                 f"('{bullet.strip()}') — the card is left alone")
            continue

        # The broadcaster and the sport: the first bullet after the head
        # is where the card is sold, and the flag line below it carries
        # the sport — "![Image 31](...flags/HR-...) MMA •Pula, Istria".
        # Both are read, because one names the seller and the other
        # names the row the card sits on.
        after = page[head.end():head.end() + 700]
        broadcast = None
        sport = None
        for line in after.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("![Image"):
                flag = A_FLAG.search(line)
                if flag:
                    sport = flag.group(1)
                break
            if broadcast is None:
                said = A_BULLET.match(line)
                if said:
                    broadcast = norm(said.group(1))
        if broadcast is None:
            continue

        # The sport the row will sit under. Tapology's flag line carries
        # the card's sport words — one, two or the umbrella — and the
        # first one this board has a place for wins. A flag line with no
        # sport word at all is not the end of the card: its name can
        # name the sport, as BKFC's does.
        sport_as_read = None
        if sport is not None:
            phrases = [sport] + [p.strip() for p in re.split(r"\s*[&/]\s*", sport)]
            for a_word in phrases:
                if a_word in AS_A_SPORT:
                    sport_as_read = AS_A_SPORT[a_word]
                    if sport_as_read is not None:
                        break
        if sport_as_read is None:
            for a_word, a_sport in AS_BY_NAME.items():
                if a_word in name.upper():
                    sport_as_read = a_sport
                    break
        if sport_as_read is None:
            continue

        from zoneinfo import ZoneInfo
        start = when.replace(tzinfo=ZoneInfo(EASTERN)).astimezone(timezone.utc)
        channel = AS_PRINTED.get(broadcast.casefold(), broadcast)
        out.append({
            "start": start,
            "title": a_bare(name),
            "sport": sport_as_read,
            "channels": [channel],
        })
        log(f"  tapology: {a_bare(name)} on {channel}, {start:%d.%m %H:%M} UTC")
    if not out:
        log("  tapology: no card on the page this pass")
    return out


def events(session, floor=None, ceiling=None) -> list[dict]:
    """Tapology's cards, or none if its reader is having a bad day."""
    try:
        page = fetch(session, SOURCE, headers={"x-no-cache": "true"},
                     retries=1).text
    except Exception as exc:                                  # noqa: BLE001
        warn(f"tapology is unreachable through its reader ({exc}) — the "
             f"board keeps what the other sources gave it")
        return []
    found = collect(page)
    for event in found:
        event["source"] = "tapology"
    if floor is not None:
        found = [event for event in found
                 if floor <= event["start"] < ceiling]
    return found
