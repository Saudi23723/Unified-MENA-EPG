#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Turkish PPV — the tenth channel: the Turkish grid's own listings, alone.

Asked for in those words: the full Spor Ekranı grid — every sport and
every competition it carries, with tabii, S Sport / S Sport Plus and
beIN CONNECT marked PPV beside their name — was to leave channel 2 and
stand on a channel of its own, "cloned coding so it's easier".

So nothing about the drawing, the guide or the reel is written twice.
The other-sports generator already turns a list of events into boards,
an XML guide and a second UAE-clock set; this module lends it this
channel's name, mark, files and board stem for the length of one build
and hands them back after, exactly the way the baseball and NBA/NFL
channels do. The two clocks, the row geometry and the live mark cannot
drift apart from the rest of the service.

The rows come from turkish_sport_grid.py alone: the sport is the icon's
own word, the clock is Istanbul's, the channel is the one printed in
the row. A row with no broadcaster reads PPV, and a carrier a viewer
buys the event on reads "tabii PPV", "S Sport Plus PPV", "beIN CONNECT
PPV" — the same wording asked for on channel 2 and kept here with it.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta

import dubai_time
import other_sports_epg as base
import turkish_sport_grid
from epg_lib import log, new_session, warn
from today_matches_epg import in_the_readers_order as channels_in_order
from today_matches_epg import shorter

CHANNEL_ID = "TurkishPPV"
CHANNEL_AR = "🇹🇷 Turkish PPV"
SUBTITLE = "كل رياضة وكل بطولة على الشاشات التركية"
OUTPUT = "turkish_ppv_epg.xml"
BOARD_PREFIX = "turkish_ppv_"
LOGO = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/logos/turkish_ppv.png")

DUBAI_OUTPUT = "dubai_turkish_ppv_epg.xml"
DUBAI_CHANNEL_ID = "TurkishPPVDubai"
DUBAI_BOARD_PREFIX = "dubai_turkish_ppv_"

# Every sport the grid can name, in the reader's order. A sport the
# grid's own icon map cannot produce never reaches the board, and one
# absent from here never reaches it either.
IN_ORDER = (
    "Olympics",
    # THE TWO THE TURKISH SCREENS LEAD WITH. Asked for by their carriers
    # — TRT Spor, S Sport and HT Spor — and those three carry football,
    # basketball and studio programmes and almost nothing else, so
    # without these two the channel had none of their matches at all.
    # A sport absent from this tuple never reaches the board however the
    # grid files it.
    "Football", "Basketball",
    "F1", "MotoGP", "WRC",
    "Boxing", "MMA",
    "Tennis", "Padel", "Snooker", "Darts", "Golf",
    "Volleyball", "Beach Volleyball", "Handball", "Futsal", "Rugby",
    "Cycling", "Athletics", "Swimming", "Triathlon",
)
RANK = {sport: place for place, sport in enumerate(IN_ORDER)}

# EIGHT ROWS A PAGE, AND 20 SECONDS A PAGE — the same as channels 1
# and 2, which is what was asked for: "حكينا ٨ صفوف و حكينا مثل ١ و ٢".
#
# It was FIVE for a reason that belonged to the other board. On the info
# screen eight rows are 56px each and every size falls to the drawing's
# smallest step, which is what "it's too small" meant off a television
# across a room, twice; five rows are 89px and the fixture reaches 34px.
#
# This channel wears the now-and-next table now, and there the
# comparison runs the other way, because the two boards disagree about
# WHICH HALF of a row matters. This channel's titles are "Yarış 2",
# "Çeyrek Finaller", "Ispanya GP" — race 2, the quarter-finals, the
# Spanish GP. None says anything alone; the competition beside it is the
# half a viewer reads. The info board printed the title at 30px and the
# competition UNDER it at 17px — the useful half in the small type. The
# table bolds the competition, so at eight rows that half is 26px: half
# again the size it was published at, not smaller.
#
# The 14-second page went back to 20 with it (see SCREENS in
# match_screen_video.py). The 14 was bought to pay for the pages five
# rows cost — 74 rows over fifteen boards. Eight rows is ten boards, and
# ten at 14s is 1.8s a row, less reading time per row than this channel
# has ever had. At 20s it is 2.5s a row and the day still comes round in
# 3:20, which is what fifteen pages of five took.
ON_A_PAGE = 8


# SIX COMPETITIONS OFF THIS CHANNEL, asked for by name: "Remove ... UCL
# championship from Turkish PPV channel / Amanya bundesliga 2 and 3 /
# CEV erkekler / Azebaycan League / Gloria Cup Basketball / Fransa
# handball ligi / Remove all from the channel".
#
# THE NAMES ARE READ AGAINST THE BOARD, not letter by letter. "Amanya"
# is Almanya and "Azebaycan" is Azerbaycan, which cost nothing; "ucl" is
# USL, which cost ten rows, because a rule for UCL matches nothing here
# and the channel went on carrying every one of them.
#
# MATCHED ON THE GRID'S LEAGUE LINE AND NOTHING ELSE, which is what
# "competition" carries here: the page prints a competition and then its
# sport in Turkish — "CEV Erkekler Avrupa Şampiyonasi Voleybol", "Daikin
# StarLigue Hentbol", "Sultanlar Ligi Voleybol". The grid always fills
# it, and falls back to it for a title it has none of, so the league
# line alone is enough.
#
# THE FIXTURE IS NOT SEARCHED, and that is the whole of it. Searching it
# too cost the men's handball World Championship on the first try: "IHF
# Erkekler Dünya Şampiyonasi Hentbol · Danimarka - Fransa" was refused
# as the French league, because the OPPONENT is France. "Letonya -
# Fransa" and "ABD - Fransa" sit on this channel as well, and an
# Azerbaijan national side would have walked into the Azerbaycan rule
# the same way. A country that is playing is not a country whose league
# this is.
#
# WHAT EACH ONE IS NOT ALLOWED TO TAKE WITH IT, because the ask names
# one half of a pair every time:
#   - Bundesliga 2 and 3 go; the Bundesliga does not. The rule needs a
#     2 or a 3 against it, in either the Turkish order ("Bundesliga 2")
#     or the German one ("2. Bundesliga").
#   - CEV Erkekler goes; CEV Kadınlar — the women's European
#     Championship, asked for by name when this channel was built — does
#     not. The rule needs the word erkekler.
#   - The French handball league goes; the men's handball World
#     Championship, also asked for by name, does not. So the rule names
#     the league — StarLigue, ProLigue, the Championnat de France — and
#     the Fransa/Hentbol pair, and nothing that says Şampiyonasi.
OFF_THIS_CHANNEL = (
    # "And ucl championship" — and it is USL, the American second
    # division, with the letters turned round. Read literally it bought a
    # rule for a competition that is not on this channel at all: nothing
    # here says UCL, while USL Championship was TEN of the board's 76
    # rows, every one of them on "USL Championship Youtube", stacked at
    # 16:00 and 19:00. Ten rows is why it was named first.
    ("USL Championship", re.compile(r"\busl\b", re.I)),
    ("Bundesliga 2 and 3", re.compile(
        r"bundesliga\s*[23]\b|\b[23]\s*\.?\s*bundesliga", re.I)),
    ("CEV Erkekler", re.compile(r"\bcev\b.*erkekler|erkekler.*\bcev\b",
                               re.I)),
    ("Azerbaycan", re.compile(r"azer?bay?can|azerbaijan", re.I)),
    ("Gloria Cup", re.compile(r"gloria\s*(?:cup|kupa)", re.I)),
    ("the French handball league", re.compile(
        r"starligue|proligue"
        r"|championnat\s+de\s+france.*hand"
        r"|fransa[^|]*hentbol|hentbol[^|]*fransa", re.I)),
)


def off_this_channel(event: dict) -> str:
    """The name of the rule refusing this row, or "" if none does."""
    said = event.get("competition") or ""
    for name, pattern in OFF_THIS_CHANNEL:
        if pattern.search(said):
            return name
    return ""


def wear_this_channel(**also):
    """Put the shared generator in this channel's clothes for a block."""
    return dubai_time.the_other_clock(
        base.__dict__,
        CHANNEL_ID=CHANNEL_ID, CHANNEL_AR=CHANNEL_AR, SUBTITLE=SUBTITLE,
        OUTPUT=OUTPUT, BOARD_PREFIX=BOARD_PREFIX, LOGO=LOGO,
        IN_ORDER=IN_ORDER, RANK=RANK, BOARD_STYLE="vsport",
        MAX_ON_BOARD=ON_A_PAGE, **also)


def collect(session, floor: datetime, ceiling: datetime) -> list[dict]:
    """Every live row of the Turkish grid inside the window, folded once."""
    events = turkish_sport_grid.events(session)
    inside = [event for event in events
              if floor <= event["start"] < ceiling
              and event.get("sport") in RANK]

    # One row per broadcast — the same fold channel 2 does, so a fixture
    # the grid prints twice keeps every channel it was printed with.
    inside = base.one_row_per_broadcast(inside)
    kept = []
    refused: dict[str, set] = {}
    for event in inside:
        if not base.a_live_event(event.get("title", "")):
            continue
        why = off_this_channel(event)
        if why:
            # THE LEAGUE LINE AS THE GRID PRINTED IT, written down. The
            # six rules above are matched against a page this machine
            # cannot reach, so the only way to know a rule is catching
            # what it was meant to — and nothing beside it — is to read
            # back what it caught.
            refused.setdefault(why, set()).add(
                (event.get("competition") or "").strip())
            continue
        kept.append(event)
    log(f"  {len(events)} row(s) offered, {len(kept)} live and inside the "
        f"window")
    for why in sorted(refused):
        names = ", ".join(sorted(n for n in refused[why] if n)) or "(no league)"
        log(f"  refused as {why}: {names}")
    # AND WHAT THE CHANNEL IS ACTUALLY CARRYING, by competition. Asked
    # outright — "و بدي اعرف شو القناة رح تعطيني" — and there is nowhere
    # else to read it: the guide carries a fixture and its channels, and
    # the competition is drawn on the board and nowhere in the XML. So
    # the build says it, once a pass, and the answer stops being a guess
    # made from team names.
    carrying: dict[str, int] = {}
    for event in kept:
        carrying[(event.get("competition") or "").strip() or "(no league)"] = (
            carrying.get((event.get("competition") or "").strip()
                         or "(no league)", 0) + 1)
    log(f"  carrying {len(carrying)} competition(s):")
    for name, count in sorted(carrying.items(), key=lambda kv: (-kv[1], kv[0])):
        log(f"    {count:3d}  {name}")
    return sorted(kept, key=lambda e: (e["start"], RANK[e["sport"]]))


def build() -> int:
    now = datetime.now(base.UTC)
    with wear_this_channel():
        days = base.days_of(now)
        floor = base.start_of_day(days[0])
        ceiling = base.start_of_day(days[-1] + timedelta(days=1))

        session = new_session()
        events = collect(session, floor, ceiling)
        for event in events:
            event["channels"] = [base.ppv_beside(shorter(name)) for name
                                 in channels_in_order(event["channels"])]
            if not event["channels"]:
                event["channels"] = ["PPV"]

        ok = base.publish_all(events, now) == 0

        # THE SECOND CLOCK — the same rows with every time printed in the
        # Gulf's, on its own link, exactly as the other channels do.
        with dubai_time.the_other_clock(
                base.__dict__,
                VIEWER=dubai_time.DUBAI, VIEWER_NAME=dubai_time.DUBAI_NAME,
                OUTPUT=DUBAI_OUTPUT, CHANNEL_ID=DUBAI_CHANNEL_ID,
                BOARD_PREFIX=DUBAI_BOARD_PREFIX):
            try:
                base.publish_all(events, now,
                                 days=dubai_time.days_the_events_span(
                                     now, events, dubai_time.DUBAI))
            except Exception as exc:                          # noqa: BLE001
                warn(f"the UAE-clock Turkish PPV guide could not be written "
                     f"({exc}) — the published one is unchanged")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
