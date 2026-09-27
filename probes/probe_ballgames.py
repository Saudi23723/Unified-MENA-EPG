"""Where today's live MLB and NFL games go, between ESPN and the board.

MEASUREMENT ONLY — writes nothing, changes nothing.

Reported off the screen: "رجع الي NFL المباشر اليوم و ال MLB المباشر
اليوم". Both channels drew today as

    لا يوجد حدث من الرياضات المتابَعة في هذا اليوم

while tomorrow carried fifteen baseball games. So the question is where
today's games are lost, and there are only three places they can be:

  * ESPN does not return them for today's date at all
  * they come back but carry no broadcaster, and ball_sports drops any
    game that names no channel
  * they come back, name a channel, and something after that drops them

This walks the same window the build walks, with the build's own
collectors, and counts each of those separately. Prints counts and
statuses, never a whole payload.
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

import mlb_espn  # noqa: E402
import nfl_espn  # noqa: E402
import other_sports_epg as base  # noqa: E402
import wnba_espn  # noqa: E402
from epg_lib import log, new_session  # noqa: E402


def walk(session, name, module, floor, ceiling, viewer):
    log(f"\n=== {name}")
    try:
        events = module.collect(session, floor, ceiling)
    except Exception as exc:
        log(f"  collect() raised {type(exc).__name__}: {str(exc)[:100]}")
        return

    log(f"  {len(events)} event(s) returned for the whole window")
    if not events:
        return

    by_day = Counter(e["start"].astimezone(viewer).date() for e in events)
    log(f"  {'day (viewer)':14} {'events':>7} {'with a channel':>15} "
        f"{'live-titled':>12}")
    for day in sorted(by_day):
        same = [e for e in events
                if e["start"].astimezone(viewer).date() == day]
        with_ch = sum(1 for e in same if e.get("channels"))
        live = sum(1 for e in same if base.a_live_event(e.get("title", "")))
        log(f"  {str(day):14} {len(same):7} {with_ch:15} {live:12}")

    today = datetime.now(timezone.utc).astimezone(viewer).date()
    mine = [e for e in events
            if e["start"].astimezone(viewer).date() == today]
    log(f"\n  TODAY ({today}) in detail — {len(mine)} event(s)")
    for event in sorted(mine, key=lambda e: e["start"])[:14]:
        channels = ", ".join(event.get("channels") or []) or "NO CHANNEL"
        log(f"    {event['start'].astimezone(viewer):%H:%M}  "
            f"{(event.get('title') or '')[:44]:46} {channels[:34]}")


def main() -> int:
    session = new_session()
    now = datetime.now(base.UTC)
    days = base.days_of(now)
    floor = base.start_of_day(days[0])
    ceiling = base.start_of_day(days[-1] + timedelta(days=1))
    log(f"the window the build walks: {floor} .. {ceiling}")
    log(f"viewer clock: {base.VIEWER}, and it is "
        f"{now.astimezone(base.VIEWER):%a %d %b %H:%M} there")

    for name, module in (("MLB", mlb_espn), ("WNBA", wnba_espn),
                         ("NFL", nfl_espn)):
        walk(session, name, module, floor, ceiling, base.VIEWER)

    log("\nWhat matters: whether today's row is missing from ESPN, or "
        "present with NO CHANNEL against it. ball_sports keeps only "
        "games that name a channel, so the second would explain an "
        "empty board with games being played.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
