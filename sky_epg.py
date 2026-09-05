#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The card, split, from the broadcaster's own programme guide.

A UFC night is not one broadcast. It is early prelims, then prelims,
then the main card, each with its own start — and the reader asked for
all three, more than once. Every listings page this repository had gives
ONE row per card: wheresthematch's UFC page was printed row by row and
carries six rows, one per event, with no prelim among them.

Sky publishes its own electronic programme guide, openly, and it has
them as PROGRAMMES:

    TNTSports1 HD · 2026-09-05
       1788627600  Live: UFC Fight Night Prelims     19:00 UTC
       1788634800  Live: UFC Fight Night             21:00 UTC

That is the whole answer. A prelim arrives as a row with a start of its
own, on the channel actually carrying it, from the broadcaster rather
than from anybody's opinion — which is the rule this repository is held
to and the reason the alternatives were refused.

IT ALSO RECOVERS TNT. tntsports.co.uk answers 403 to every request from
a runner — its schedule, its boxing page and its MMA page alike — so the
channel that carries the UFC in Britain could not be read from its own
site at all. Sky's guide carries TNT's schedule, so it is read here.

THE SHAPE, printed before a line of this was written:

    services   {"services": [{"sid": "3625", "c": "410",
                              "t": "TNTSports1 HD", ...}, ...]}   383 of them
    schedule   {"schedule": [{"events": [{"st": 1788627600, "d": 3600,
                                          "t": "Live: UFC Fight Night Prelims",
                                          "sy": "...", ...}]}]}

`st` is a unix instant and `d` a duration in seconds, so there is no
printed clock to place in a timezone — the fault this project has paid
for most simply cannot happen here.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from epg_lib import fetch, log, norm, warn

SERVICES = "https://awk.epgsky.com/hawk/linear/services/4101/1"
SCHEDULE = "https://awk.epgsky.com/hawk/linear/schedule/{day}/{sid}"

# HOW SKY ACTUALLY WRITES ITS SPORT CHANNELS, printed from its own
# service list on a runner rather than assumed. It does not write "Sky
# Sports" at all — it writes "SkySp", and abbreviates what follows:
#
#     4002  SkySpMainEvHD     4022  SkySp ActionHD
#     1035  SkySpBoxOffHD     4090  SkySp Mix HD
#     3940  SkySp+ HD         4010  SkySp PL HD
#     3939  SkySp F'ball HD   3835  SkySp F1 HD
#
# The first filter written here named "Sky Sports Action" and matched
# NONE of them: six channels came back and every one was TNT, so the
# boxing was missing while the MMA arrived. There is also no Sky Sports
# Arena in the list any more — it was named here and does not exist.
#
# So this is written from what came back. The channels kept are the ones
# that carry a fight: Main Event, Action, Mix, Box Office (the pay-per-
# view) and Sky Sports+. Golf, cricket, F1, tennis, racing, the football
# channels and Sky Sports News are not fight channels and every day of
# each of them would be a request for nothing.
A_FIGHT_CHANNEL = re.compile(
    r"tnt\s*sports?\s*[1-5]|tnt\s*s?\s*box\s*off"
    r"|sky\s*sp(?:orts?)?\s*(?:main\s*ev|action|mix|box\s*off|\+)", re.I)

# Sky's shorthand, expanded — measured from the same list. A name is
# matched after its quality suffix is off and its spaces are squashed,
# so "SkySp ActionHD", "SkySpActionHD" and "Sky Sports Action" are one
# entry. Longest first: "boxoff2" must be tried before "boxoff".
SHORTHAND = (
    ("skyspmainev", "Sky Sports Main Event"),
    ("skyspboxoff", "Sky Sports Box Office"),
    ("skyspaction", "Sky Sports Action"),
    ("skyspmix", "Sky Sports Mix"),
    ("skysp+", "Sky Sports+"),
)

# What counts as a fight, in the title Sky prints. Deliberately about the
# EVENT and not about the word "prelim": a prelim is kept because it is a
# UFC programme, not because of what it is called, so the main card and
# the early prelims arrive by the same rule.
A_FIGHT = re.compile(
    r"\bUFC\b|\bMMA\b|ultimate fighting|contender series|ultimate fighter"
    r"|\bPFL\b|bellator|\boktagon\b"
    r"|\bboxing\b|fight night|title fight|undisputed"
    r"|\bzuffa\b|\braf\b", re.I)

# Sky marks a live broadcast in the title. A repeat of last week's card
# is not tonight's, and this is the only thing that tells them apart.
# SKY ABBREVIATES IN THE TITLE TOO, and this was measured, not guessed:
# a live run put "MVP Boxing: Mayer v Cameron Hlts" on the board three
# times over four days. "Hlts" is how Sky writes Highlights when the
# title is long, and a highlights show is last week's fight, not one to
# tell somebody about. The spelled-out words were already refused; the
# short forms were what got through.
A_REPEAT = re.compile(r"\brepeat\b|\bhighlights\b|\breplay\b|\bclassic\b"
                      r"|\bbest of\b|\breview\b|\bpreview\b|\breloaded\b"
                      r"|\bcountdown\b|\bembedded\b"
                      r"|\bhlts\b|\bhghlts\b|\bhi-?lites\b|\brpt\b", re.I)

# Which board row this is. Boxing and MMA are ranked separately there.
A_BOXING = re.compile(r"\bboxing\b|title fight|undisputed", re.I)

# "Live: " is Sky saying it is live, which the board says with its own
# mark; the channel's own name is not part of a programme's name.
A_PREFIX = re.compile(r"^(?:live:\s*|new:\s*)+", re.I)

# AND IT IS THE ONLY THING THAT SAYS SO. Reported: "ال UFC مكتوب اليوم
# بس هو السبت تبع ال Live". It was — and Sky said so plainly, in the
# titles this used to strip before looking:
#
#   09-05 17:00 TNT Sports 1  Live: UFC Fight Night Prelims
#   09-05 19:00 TNT Sports 1  Live: UFC Fight Night
#   09-03 20:00 TNT Sports 4  UFC Fight Night
#      "Action from UFC Fight Night at the SPD Bank Oriental Sports
#       Center" — Shanghai, and over
#   09-07 01:00 TNT Sports 2  UFC Fight Night
#      "...at Accor Arena in Paris" — the same card again, twice more
#
# The live airings carry the prefix and the replays do not. Stripping it
# first threw away the one signal that told them apart, so a card fought
# weeks ago in Shanghai was announced as tonight's.
#
# A_REPEAT catches what a repeat is CALLED — Reloaded, Hlts, Classic —
# and it caught "UFC Reloaded" three hours later on the same channel.
# It cannot catch a replay Sky simply titles "UFC Fight Night", because
# nothing in that name is wrong. Only the missing prefix is.
#
# So the prefix is now required. This is the rule own_guides already
# lives by for beIN, whose own titles mark a live airing and whose
# eighteen repeats of four fixtures are refused by exactly this test.
# The cost is a real broadcast Sky forgets to mark, and it is the right
# way round: a guide that invents a broadcast is worse than one that
# admits it does not know.
A_LIVE_AIRING = re.compile(r"^\s*live\b", re.I)


def a_channel(name: str) -> str:
    """Sky's name for a channel, written the way this board writes one.

    "TNTSports1 HD" is TNT Sports 1. The board's own shortener then makes
    that "TNT 1", and its channel order recognises it as British — both
    of which need the spaces Sky leaves out.
    """
    name = norm(name)
    # The quality suffix, whether Sky spaces it or glues it on:
    # "TNTSports1 HD" and "TNTSBoxOffHD" are the same habit.
    name = re.sub(r"(?i)\s*\b(?:HD|SD|UHD|\+1)\b\s*$", "", name)
    name = re.sub(r"(?i)(?<=[a-z0-9])(?:HD|SD|UHD)$", "", name)

    # Sky's own abbreviations, expanded from the measured list before any
    # spacing rule runs — "SkySpMainEv" has no boundary a regex could
    # find, and guessing at one is how "Sky Sports s Action" happened.
    squashed = re.sub(r"[^a-z0-9+]", "", name.lower())
    for short, full in SHORTHAND:
        if squashed == short:
            return full

    name = re.sub(
        r"(?i)^TNTS?\s*Box\s*Off(?:ice)?\s*(\d?)\s*$",
        lambda m: "TNT Sports Box Office"
                  + (f" {m.group(1)}" if m.group(1) else ""), name)
    name = re.sub(r"(?i)^TNT\s*Sports?\s*(\d)", r"TNT Sports \1", name)
    # A space only where Sky glued a name onto "Sports" — never before a
    # lowercase letter, or "Sky Sports Action" becomes "Sky Sports s
    # Action", which is what the first attempt at this did.
    # No (?i) here on purpose: with it, [A-Z0-9] matches a lowercase "s"
    # too, so "Sky Sports Action" backtracks to "Sky Sport" + "s" and
    # comes out as "Sky Sports s Action". Case matters in the lookahead.
    name = re.sub(r"^[Ss]ky\s*[Ss]ports?(?=[A-Z0-9])", "Sky Sports ", name)
    return norm(re.sub(r"\s{2,}", " ", name))


def a_programme(title: str) -> str:
    """The programme's name, without the words that are not part of it."""
    return norm(A_PREFIX.sub("", norm(title)))


def channels(session) -> list[tuple[str, str]]:
    """Every channel of Sky's that could be carrying a fight."""
    try:
        listing = json.loads(fetch(session, SERVICES).text)
    except Exception as exc:                                  # noqa: BLE001
        warn(f"Sky's channel list is unreachable ({exc}) — no card split "
             f"this pass")
        return []
    found = [(str(one.get("sid")), a_channel(one.get("t", "")))
             for one in listing.get("services", [])
             if A_FIGHT_CHANNEL.search(str(one.get("t", "")))]
    log(f"  Sky EPG: {len(listing.get('services', []))} channel(s), "
        f"{len(found)} that carry fights")
    return found


def a_day(session, sid: str, channel: str, day: str) -> list[dict]:
    """One channel, one day, as events the board understands."""
    try:
        page = json.loads(fetch(session, SCHEDULE.format(day=day, sid=sid)).text)
    except Exception as exc:                                  # noqa: BLE001
        warn(f"Sky EPG {channel} {day}: {str(exc)[:70]}")
        return []

    out: list[dict] = []
    for block in page.get("schedule") or []:
        for event in block.get("events") or []:
            raw = event.get("t", "") or ""
            # Read BEFORE the prefix is stripped — it is the whole signal.
            if not A_LIVE_AIRING.match(raw):
                continue
            title = a_programme(raw)
            if not title or not A_FIGHT.search(title):
                continue
            if A_REPEAT.search(title):
                continue
            try:
                start = datetime.fromtimestamp(int(event["st"]), timezone.utc)
            except (KeyError, TypeError, ValueError):
                # No instant, no row — never a time inferred from a day.
                continue
            out.append({
                "start": start,
                "title": title,
                "competition": norm(event.get("sy", ""))[:60] or title,
                "sport": "Boxing" if A_BOXING.search(title) else "MMA",
                "channels": [channel],
            })
    return out


def events(session, floor: datetime, ceiling: datetime) -> list[dict]:
    """Every fight Sky's guide has, on the channels that carry them."""
    on_air = channels(session)
    if not on_air:
        return []

    days = []
    walk = floor.astimezone(timezone.utc).date()
    last = ceiling.astimezone(timezone.utc).date()
    while walk <= last and len(days) < 10:
        days.append(walk.strftime("%Y%m%d"))
        walk += timedelta(days=1)

    out: list[dict] = []
    for sid, channel in on_air:
        for day in days:
            out.extend(a_day(session, sid, channel, day))

    # One programme, however many of Sky's channels carry it.
    seen, kept = set(), []
    for event in sorted(out, key=lambda one: one["start"]):
        if not (floor <= event["start"] < ceiling):
            continue
        key = (event["start"], event["title"])
        if key in seen:
            continue
        seen.add(key)
        kept.append(event)
    log(f"  Sky EPG: {len(out)} fight programme(s) over {len(on_air)} "
        f"channel(s) and {len(days)} day(s), {len(kept)} inside the window")
    return kept
