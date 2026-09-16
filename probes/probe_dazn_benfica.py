#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WHY IS Benfica - Sporting CP ON THE PORTUGUESE CHANNEL FOR 14 HOURS?

The reader: "في اخطاء بالقنوات البرتغالية، مثلا Benfica vs Sporting هاي غلط،
يعني بكرا Benifica vs AC milan بس، اما الموجودة هاي يمكن recorded".

WHAT IS PUBLISHED, read off sporttv_epg.xml on main:

    16/09 23:30 -> 17/09 01:25   Benfica - Sporting CP   (🔴 then ✅)
    17/09 07:00 -> 17/09 14:00   Benfica - Sporting CP   (⏳ then 🔴 12:05)

Two separate blocks, the same title, and a live Lisbon derby at 12:05 on a
Thursday. Beside them the build also carries "Ac Milan X Sl Benfica",
which is the fixture the reader says is the real one.

THE SEPARATOR NAMES THE SOURCE. Every other row on that channel joins its
teams with x or X — sporttv_pt and canal11_pt both do. This one uses " - ",
and only one reader passes a name straight through: dazn_pt line 169,
EpisodeTitle verbatim. So DAZN is where it comes from.

AND DAZN IS SUPPOSED TO HAVE REFUSED IT. dazn_pt already screens exactly
this, in its own words:

    IsLive alone is insufficient: DAZN marks live studio/talk blocks too.
    ProgramType alone is insufficient: recorded games are Sports event.
    Both together mean a live sporting event.

If a replay reached the board, then on this row DAZN is reporting
IsLive=True on something that is not live, and the pair is not the
discriminator it was taken to be. That is the thing to establish before a
line of filtering is written.

SO THIS PRINTS, FOR EVERY DAZN 1-5 PROGRAMME:

  - Start, End and the span in minutes. A 14-hour "match" is a channel
    placeholder, not a contest, and the span alone may be enough to
    refuse it.
  - IsLive and ProgramType, the pair the current filter trusts.
  - Every other key the row carries. If DAZN distinguishes a replay from
    a live game ANYWHERE, it is in a key this build is not yet reading,
    and it will be visible here.

Benfica/Sporting rows print in full. The rest print one line each, so the
shape of a normal row is visible next to the suspect one.

Wired to nothing. It prints; a human reads.
"""

import json
import sys

sys.path.insert(0, ".")

import dazn_pt
from epg_lib import new_session

INTERESTING = ("enfica", "porting")


def main():
    session = new_session()

    try:
        response = dazn_pt.fetch(
            session,
            dazn_pt.BASE,
            params=dazn_pt.RAIL_PARAMS,
            headers=dazn_pt.RAIL_HEADERS,
        )
        payload = response.json()
    except Exception as exc:
        print(f"RAIL UNREADABLE: {type(exc).__name__}: {exc}")
        return 1

    tiles = payload.get("Tiles", []) if isinstance(payload, dict) else []
    print(f"tiles: {len(tiles)}   linear channels: {dazn_pt.LINEAR_CHANNELS}")

    for tile in tiles:
        if not isinstance(tile, dict):
            continue

        channel = dazn_pt.norm(str(tile.get("Title") or ""))

        if channel not in dazn_pt.LINEAR_CHANNELS:
            continue

        rows = dazn_pt._programmes(tile)
        print(f"\n{'=' * 68}\n{channel}: {len(rows)} programmes")

        for row in rows:
            title = str(row.get("Title") or "")
            episode = str(row.get("EpisodeTitle") or "")
            start = dazn_pt._parse(row.get("Start"))
            end = dazn_pt._parse(row.get("End"))

            span = ""

            if start and end:
                span = f"{(end - start).total_seconds() / 60:.0f}min"

            live = row.get("IsLive")
            kind = row.get("ProgramType")

            # Would the filter as it stands today let this through?
            passes = live is True and kind == "Sports event"

            hit = any(w in title + episode for w in INTERESTING)

            # A contest does not run for three hours. Anything longer is
            # a channel placeholder, and it is printed even when it is
            # not the suspect row -- if span alone can refuse these, that
            # is the cheapest fix available.
            long_run = bool(start and end
                            and (end - start).total_seconds() > 3 * 3600)

            if hit or long_run or passes:
                mark = "  <== " if hit else "      "
                print(f"{mark}{str(start)[:16]} {span:>7} "
                      f"live={str(live):<5} type={str(kind):<14} "
                      f"pass={'Y' if passes else 'n'} | "
                      f"{(episode or title)[:52]}")

            if not hit:
                continue

            # The suspect row in full -- every key, so a replay marker
            # this build is not reading cannot hide.
            print("        ---- every key on this row ----")

            for key in sorted(row):
                value = row[key]

                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)[:200]

                print(f"        {key}: {str(value)[:200]}")

            print("        --------------------------------")

    return 0


if __name__ == "__main__":
    sys.exit(main())
