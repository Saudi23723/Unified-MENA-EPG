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

import json
import os
import re
import sys
import urllib.request

from epg_lib import log, warn
from other_sports_epg import CHANNEL_AR as SPORTS_AR
from other_sports_epg import CHANNEL_ID as SPORTS_ID
from other_sports_epg import LOGO as SPORTS_LOGO
from news_epg import CHANNEL_AR as NEWS_AR
from news_epg import CHANNEL_ID as NEWS_ID
from news_epg import LOGO as NEWS_LOGO
from today_matches_epg import CHANNEL_AR, CHANNEL_ID, LOGO
from weather_epg import CHANNEL_AR as WEATHER_AR
from weather_epg import CHANNEL_ID as WEATHER_ID
from weather_epg import LOGO as WEATHER_LOGO
from ball_sports_epg import CHANNEL_AR as BALL_AR
from ball_sports_epg import CHANNEL_ID as BALL_ID
from ball_sports_epg import LOGO as BALL_LOGO
from hoops_gridiron_epg import CHANNEL_AR as HOOPS_AR
from hoops_gridiron_epg import CHANNEL_ID as HOOPS_ID
from hoops_gridiron_epg import LOGO as HOOPS_LOGO
from f1_epg import CHANNEL_AR as F1_AR
from f1_epg import CHANNEL_ID as F1_ID
from f1_epg import LOGO as F1_LOGO
from turkish_ppv_epg import CHANNEL_AR as TPPV_AR
from turkish_ppv_epg import CHANNEL_ID as TPPV_ID
from turkish_ppv_epg import LOGO as TPPV_LOGO
from prayer_epg import CHANNEL_AR as PRAYER_AR
from quran_epg import CHANNEL_ID as QURAN_ID
from quran_epg import LOGO as QURAN_LOGO
from prayer_epg import CHANNEL_ID as PRAYER_ID
from prayer_epg import LOGO as PRAYER_LOGO

OUTPUT = "ai_sports_dashboard.m3u"
GROUP = "AI Sports Dashboard"
RAW = "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main"

# The fourth channel — 🌤️ طقس اليوم. It is drawn and encoded here like
# the three boards beside it: the weather is read from Open-Meteo each
# pass, drawn as boards (weather_epg.py) and encoded into
# stream/weather.m3u8 by the same encoder, so the picture is this
# repository's own end to end and no outside server can switch it off.
# It began as a relay of the AccuWeather channel through the amagi CDN,
# which is somebody else's URL to rotate — and the day that CDN stopped
# answering, the row was in the playlist and the channel played nothing.
WEATHER_NAME = WEATHER_AR

# The fifth channel — Ain FM 98.3, and the only one of the five whose
# sound comes from somebody else. A radio station publishes audio and
# nothing else, so the row played and the screen stayed black; what is
# added beside the station's stream is a picture, encoded here from the
# station's own mark. ain_fm_screen.py builds the three files behind
# stream/ain_fm.m3u8 and says why they are three.
AIN_FM_ID = "AinFMJordan"
AIN_FM_NAME = "Ain FM 98.3"
AIN_FM_LOGO = f"{RAW}/logos/ain_fm.png"

# The sixth channel — ✈️ رحلات اليوم. Today's departures and arrivals for
# Etihad, Emirates, Royal Jordanian, flydubai and Turkish, pulled once a
# day from AviationStack (tools/fetch_flights.py) and re-drawn every
# twenty minutes so a plane's status and its place along the route are
# current rather than a picture of the morning. Encoded here into
# stream/flight_tracker.m3u8 the same way the boards beside it are, so
# nothing outside this repository can switch the channel off.
FLIGHT_ID = "FlightTracker"
FLIGHT_NAME = "رحلات اليوم"
FLIGHT_LOGO = f"{RAW}/logos/flight_tracker.png"

# Five channels, ONE playlist, because that is the whole point of it: the
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
    (WEATHER_ID, WEATHER_NAME, "stream/weather.m3u8",
     f"{RAW}/stream/weather.m3u8", "🌤️ طقس اليوم", WEATHER_LOGO),
    (AIN_FM_ID, AIN_FM_NAME, "stream/ain_fm.m3u8",
     f"{RAW}/stream/ain_fm.m3u8", "🎙️ Ain FM 98.3", AIN_FM_LOGO),
    (FLIGHT_ID, FLIGHT_NAME, "stream/flight_tracker.m3u8",
     f"{RAW}/stream/flight_tracker.m3u8", "✈️ رحلات اليوم", FLIGHT_LOGO),
    # The seventh channel — 🕌 مواقيت الصلاة: عمّان, أبو ظبي, هندرسون in
    # Nevada and إسطنبول, each calculated the way its own authority
    # calculates it and printed in its own city's clock.
    (PRAYER_ID, PRAYER_AR, "stream/prayer.m3u8",
     f"{RAW}/stream/prayer.m3u8", "🕌 مواقيت الصلاة", PRAYER_LOGO),
    # The eighth channel — ⚾ بيسبول وسلة السيدات: MLB and the WNBA, off
    # channel 2 and on a screen of their own, as asked.
    (BALL_ID, BALL_AR, "stream/ball_sports.m3u8",
     f"{RAW}/stream/ball_sports.m3u8", "⚾ بيسبول وسلة السيدات", BALL_LOGO),
    # The ninth channel — 🏀 السلة والقدم الأمريكية: the NBA and the NFL,
    # off channel 2 and on a screen of their own, every game of both.
    (HOOPS_ID, HOOPS_AR, "stream/hoops_gridiron.m3u8",
     f"{RAW}/stream/hoops_gridiron.m3u8", "🏀 السلة والقدم الأمريكية",
     HOOPS_LOGO),
    # The tenth channel — القنوات التركية · PPV: the Turkish grid's whole
    # listing, every sport and every competition, off channel 2 and on a
    # screen of its own.
    (TPPV_ID, TPPV_AR, "stream/turkish_ppv.m3u8",
     f"{RAW}/stream/turkish_ppv.m3u8", "🇹🇷 Turkish PPV",
     TPPV_LOGO),
    # The eleventh channel — الفورمولا ١. One clock only: a Grand Prix
    # starts at one instant everywhere and the board already prints its
    # sessions in the viewer's own zone, so there is nothing for a
    # second row to say differently.
    (F1_ID, F1_AR, "stream/f1.m3u8",
     f"{RAW}/stream/f1.m3u8", "🏁 Formula 1",
     F1_LOGO),
    # The twelfth channel — وِرْدُ اليوم. One clock only, like مواقيت
    # الصلاة above it: the board carries a day's reading, and a day is
    # a day in either zone.
    (QURAN_ID, "وِرْدُ اليوم", "stream/quran.m3u8",
     f"{RAW}/stream/quran.m3u8", "☾ وِرْدُ اليوم",
     QURAN_LOGO),

)


# THE SECOND CLOCK — the same five channels with every time printed in
# the Gulf's (Asia/Dubai), asked for outright as a second set of links.
# A playlist of its own rather than rows appended to the first, because
# a reader pastes one link and gets one set: mixing the two clocks in
# one list is five channels each shown twice, and nobody can tell which
# row is which clock without reading a time on each.
#
# Same marks as the first set on purpose — a channel wearing another
# time is still that channel, and the mark is how it is found in a
# list. The ids differ, because two channels of the same name and id
# are one channel to a player and one of the two would never be tuned
# to. DUBAI_GROUP is its own group so the two sets never fold together
# in a player that groups by title.
DUBAI_OUTPUT = "ai_sports_dashboard_dubai.m3u"
DUBAI_GROUP = "AI Sports Dashboard · بتوقيت الإمارات"

DUBAI_SCREENS = (
    ("TodayMatchesDubai", CHANNEL_AR, "stream/dubai_screen.m3u8",
     f"{RAW}/stream/dubai_screen.m3u8", "📺 مباريات اليوم · بتوقيت الإمارات",
     LOGO),
    ("TodaySportsDubai", SPORTS_AR, "stream/dubai_sports.m3u8",
     f"{RAW}/stream/dubai_sports.m3u8", "🏁 رياضات اليوم · بتوقيت الإمارات",
     SPORTS_LOGO),
    ("TodayNewsDubai", NEWS_AR, "stream/dubai_news.m3u8",
     f"{RAW}/stream/dubai_news.m3u8", "📰 أخبار اليوم · بتوقيت الإمارات",
     NEWS_LOGO),
    ("TodayWeatherDubai", WEATHER_NAME, "stream/dubai_weather.m3u8",
     f"{RAW}/stream/dubai_weather.m3u8", "🌤️ طقس اليوم · بتوقيت الإمارات",
     WEATHER_LOGO),
    # Ain FM keeps its own clock — Amman's, since that is where it is
    # broadcast from — so this is the same channel under the second
    # list's heading, and only its id differs, because a player takes
    # two rows of one id for one channel and tunes to neither.
    ("AinFMJordanDubai", AIN_FM_NAME, "stream/ain_fm.m3u8",
     f"{RAW}/stream/ain_fm.m3u8", "🎙️ Ain FM 98.3", AIN_FM_LOGO),
    # Every time on this one is printed in the Gulf's, so it is its own
    # encode rather than the first clock's file under a second id.
    ("FlightTrackerDubai", FLIGHT_NAME, "stream/dubai_flight_tracker.m3u8",
     f"{RAW}/stream/dubai_flight_tracker.m3u8",
     "✈️ رحلات اليوم · بتوقيت الإمارات", FLIGHT_LOGO),
    # مواقيت الصلاة keeps every city's own clock — a prayer time in
    # another zone is another city's prayer — so this is the same reel
    # under the second list's heading, like Ain FM above, and only its
    # id differs, because a player takes two rows of one id for one
    # channel and tunes to neither.
    ("TodayPrayerDubai", PRAYER_AR, "stream/prayer.m3u8",
     f"{RAW}/stream/prayer.m3u8", "🕌 مواقيت الصلاة", PRAYER_LOGO),
    ("BallSportsDubai", BALL_AR, "stream/dubai_ball_sports.m3u8",
     f"{RAW}/stream/dubai_ball_sports.m3u8",
     "⚾ بيسبول وسلة السيدات · بتوقيت الإمارات", BALL_LOGO),
    ("HoopsGridironDubai", HOOPS_AR, "stream/dubai_hoops_gridiron.m3u8",
     f"{RAW}/stream/dubai_hoops_gridiron.m3u8",
     "🏀 السلة والقدم الأمريكية · بتوقيت الإمارات", HOOPS_LOGO),
    ("TurkishPPVDubai", TPPV_AR, "stream/dubai_turkish_ppv.m3u8",
     f"{RAW}/stream/dubai_turkish_ppv.m3u8",
     "🇹🇷 Turkish PPV · بتوقيت الإمارات", TPPV_LOGO),
    ("Formula1Dubai", F1_AR, "stream/dubai_f1.m3u8",
     f"{RAW}/stream/dubai_f1.m3u8",
     "🏁 Formula 1 · بتوقيت الإمارات", F1_LOGO),

)


# WHAT EACH ROW IS CALLED IN A PLAYER, asked for by name.
#
# Kept here and not in the guides: a guide's CHANNEL_AR is the name its
# XMLTV file carries and the title its board draws across the top, and
# renaming a row in somebody's player is not a reason to redraw a board
# or to rewrite a guide every player already links by tvg-id.
#
# Two strings each, because a player may show either: the plain one goes
# in tvg-name, the marked one is what is shown after the comma. The ids
# are untouched, so every guide still finds its channel.
PLAYLIST_NAMES = {
    "TodayMatches":   ("Football Guide",  "⚽ Football Guide"),
    "TodaySports":    ("Sports Guide",    "📺 Sports Guide"),
    "TodayNews":      ("Breaking News",   "📰 Breaking News"),
    "TodayWeather":   ("Today's Weather", "🌤️ Today's Weather"),
    "FlightTracker":  ("Flight Tracker",  "✈️ Flight Tracker"),
    "TodayPrayer":    ("Prayers Time",    "🕌 Prayers Time"),
    "BallSports":     ("WNBA : MLB",      "🏀 WNBA : ⚾ MLB"),
    "HoopsGridiron":  ("NFL : NBA",       "🏈 NFL : 🏀 NBA"),
    "Formula1":       ("Formula 1",       "🏁 Formula 1"),
    "TodayQuran":     ("Daily Reading",   "☾ وِرْدُ اليوم"),
}

# The second clock's rows are the same channels under Gulf times, so they
# take the same names with the suffix they already carried. Ain FM and
# مواقيت الصلاة keep their own clock and so carry no suffix there; a row
# that is not renamed above keeps exactly the name it had.
DUBAI_SUFFIX = " · بتوقيت الإمارات"


def named(channel_id, guide_name, shown):
    """The two names this row shows, renamed if the reader named it."""
    base = channel_id[:-5] if channel_id.endswith("Dubai") else channel_id
    if base not in PLAYLIST_NAMES:
        return guide_name, shown
    plain, marked = PLAYLIST_NAMES[base]
    if channel_id.endswith("Dubai") and shown.endswith(DUBAI_SUFFIX):
        return plain + DUBAI_SUFFIX, marked + DUBAI_SUFFIX
    return plain, marked


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


def write_the_playlist(screens, output: str, group: str) -> int:
    """Write one playlist from one set of screens, or leave it alone.

    The same routine for both clocks, because a playlist is a playlist:
    what differs is the screens, the file and the group they sit under,
    and two copies of this body would drift apart exactly the way the
    two boards' channel manners did before they were shared.
    """
    lines = ["#EXTM3U"]
    written = 0
    for channel_id, guide_name, path, url, shown, mark in screens:
        guide_name, shown = named(channel_id, guide_name, shown)
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
            f'group-title="{attribute(group)}",{display(shown)}')
        lines.append(url)
        written += 1

    if not written:
        warn(f"no screen has been encoded — {output} is left exactly "
             f"as it was published")
        return 1

    # No BOM: a byte-order mark in front of #EXTM3U makes a player refuse
    # the file outright.
    with open(output, "w", encoding="utf-8", newline="\n") as out:
        out.write("\n".join(lines) + "\n")

    log(f"{output}: {written} channel(s) under “{group}”")
    return 0




def build() -> int:
    # The first clock, exactly as before.
    ok = write_the_playlist(SCREENS, OUTPUT, GROUP)

    # And the second, into a file of its own. A screen that has not been
    # encoded yet leaves its playlist unwritten rather than broken, and
    # the first clock's file is already safe on disk by then.
    ok = write_the_playlist(DUBAI_SCREENS, DUBAI_OUTPUT, DUBAI_GROUP) and ok

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(build())
