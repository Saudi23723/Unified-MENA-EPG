"""
Where a guide links a board picture — one table for every generator.

A board is drawn as a PNG and attached to its programmes as the XMLTV
<icon>, so the address is public: a player holding a guide asks for it.
Boards used to be committed to main on every redraw, and git keeps every
copy for ever — after the screen segments moved off main (see
tools/segment_branch.py) the boards were most of what still grew the
repository.

So a screen's boards move to hls-segments, the branch that is one commit
replaced on every publish, in two steps, one screen at a time:

  PUBLISHED  the boards are ALSO published to hls-segments, and the guides
             link them there. main still carries them exactly as before,
             so a player holding a guide from before the switch — players
             keep a guide for up to a day — still finds every picture.

  UNTRACKED  a day or more later: main stops carrying them. Only then does
             the repository stop growing with them. Always a subset of
             PUBLISHED.

A prefix in neither links to main, character for character as before.
"""

from __future__ import annotations

MAIN = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
        "main/boards/")
BRANCH = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
          "hls-segments/boards/")

PUBLISHED: set[str] = {
    "today_prayer_",
    "today_weather_", "dubai_weather_",
    "today_news_", "dubai_news_",
    "f1_", "dubai_f1_",
    "hoops_gridiron_", "dubai_hoops_gridiron_",
    "ball_sports_", "dubai_ball_sports_",
    "sporttv_", "dubai_sporttv_",
    "turkish_ppv_", "dubai_turkish_ppv_",
    "multi_sport_", "dubai_multi_sport_",
    "flight_tracker_", "dubai_flight_tracker_",
    "disasters_", "dubai_disasters_",
    "today_matches_", "dubai_matches_",
    "other_sports_", "dubai_sports_",
}

UNTRACKED: set[str] = {
    "ball_sports_",
    "disasters_",
    "dubai_ball_sports_",
    "dubai_disasters_",
    "dubai_f1_",
    "dubai_flight_tracker_",
    "dubai_hoops_gridiron_",
    "dubai_matches_",
    "dubai_multi_sport_",
    "dubai_news_",
    "dubai_sports_",
    "dubai_sporttv_",
    "dubai_turkish_ppv_",
    "dubai_weather_",
    "f1_",
    "flight_tracker_",
    "hoops_gridiron_",
    "multi_sport_",
    "other_sports_",
    "sporttv_",
    "today_matches_",
    "today_news_",
    "today_prayer_",
    "today_weather_",
    "turkish_ppv_",
}


def prefix_of(name: str, prefixes) -> str | None:
    """The longest prefix in `prefixes` a board file name starts with.

    Longest, because "turkish_ppv_" is a prefix of nothing else but
    "dubai_turkish_ppv_" must not be claimed by a shorter entry.
    """
    best = None
    for prefix in prefixes:
        if name.startswith(prefix) and (best is None or len(prefix) > len(best)):
            best = prefix
    return best


def link(name: str) -> str:
    """The public address of board `name`, e.g. "today_prayer_0.png".

    Works on a template too — link("today_prayer_{n}.png") keeps the {n}
    for the caller's .format().
    """
    return (BRANCH if prefix_of(name, PUBLISHED) else MAIN) + name
