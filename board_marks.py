#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LIVE, التالي and انتهى change on the clock, not on a build.

"Fix it once and for all Live, التالي، انتهى for all the dashboard
channels!!!"

THE MARKS ARE DRAWN INTO A PICTURE, so they can only move when something
redraws that picture, re-encodes it and pushes it. Until now the only
thing that did was a FULL PASS — every channel fetched from its sources,
every guide rewritten, the whole gate selftest, then the push. Measured
on 13.09, board zero of channel one had to change six times:

    should change   changed    late by
    11:00           11:10      10 min
    12:00           12:10      10 min
    12:55 / 13:00   13:08      8-13 min
    13:55           14:04       9 min
    14:55           15:04       9 min

Nine to thirteen minutes, every time, and that is only the repository.
The television adds GitHub's own five-minute cache on the playlist
(cache-control: max-age=300, measured) and up to one lap of the reel.

THE PASS IS THE WRONG UNIT OF WORK FOR A MARK. Measured inside run #922:
a pass is 4 minutes 51 seconds, and almost none of it is the thing that
has to happen — the sources have not changed, the fixtures have not
changed, the guide has not changed. One row crossed its kickoff or its
final whistle, which changes ONE WORD on ONE PICTURE.

So this is that unit of work, and nothing else:

  - Every board a channel draws is REMEMBERED here as it was drawn:
    the rows, the clock it was drawn for, and the marks that came out.
  - A minute later, the marks are recomputed from the same rows at the
    new instant. If they are the same — which is almost always — there
    is nothing to do and this costs a few milliseconds.
  - If any of them moved, THAT board is redrawn from the remembered
    rows, and only its screen is re-encoded and published.

NOTHING IS DRAWN TWICE IN TWO PLACES, which is the trap this shape
usually falls into. The channel modules do not keep their own copy of
the drawing call: they hand the record here and this draws it, so the
board a flip produces is the board the build would have produced at that
instant, by construction rather than by care.
"""
from __future__ import annotations

import io
import json
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from PIL import Image

from epg_lib import on_air_for, status_of

# Untracked, beside the boards. A record is a note about work already
# published, not something a viewer or another machine ever reads, and
# committing one per board per pass would grow the repository for
# nothing. A fresh checkout simply has none until the first full pass
# writes them, and until then a flip pass has nothing to do — which is
# correct, because nothing has been drawn yet either.
SHELF = ".marks"


def _plain(value):
    """A board row as JSON, with the two types that are not."""
    if isinstance(value, datetime):
        return {"__when__": value.isoformat()}
    if isinstance(value, timedelta):
        return {"__long__": value.total_seconds()}
    if isinstance(value, date):
        return {"__day__": value.isoformat()}
    if isinstance(value, (list, tuple)):
        return [_plain(one) for one in value]
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _rich(value):
    """Back again."""
    if isinstance(value, dict):
        if "__when__" in value:
            return datetime.fromisoformat(value["__when__"])
        if "__long__" in value:
            return timedelta(seconds=value["__long__"])
        if "__day__" in value:
            return date.fromisoformat(value["__day__"])
        return {k: _rich(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_rich(one) for one in value]
    return value


def marks_of(rows: list[dict], now: datetime) -> list[str]:
    """Every row's mark at this instant — live, upcoming, over.

    This is the whole test. It is the same status_of the board itself
    draws with, so a board is redrawn exactly when the picture would
    differ and never merely because time passed.
    """
    return [status_of(row, now, on_air_for) for row in rows]


def remember(record: dict, rows: list[dict], now: datetime) -> None:
    """Keep a board's rows and the marks it was drawn with."""
    os.makedirs(SHELF, exist_ok=True)
    kept = dict(record)
    kept["rows"] = _plain(rows)
    kept["drawn_at"] = now.isoformat()
    kept["marks"] = marks_of(rows, now)
    where = os.path.join(SHELF, f"{record['name']}.json")
    with open(where, "w", encoding="utf-8") as handle:
        json.dump(kept, handle, ensure_ascii=False)


def _read(where: str) -> dict | None:
    try:
        with open(where, encoding="utf-8") as handle:
            kept = json.load(handle)
    except (OSError, ValueError):
        return None
    kept["rows"] = _rich(kept.get("rows") or [])
    return kept


def every_record() -> list[dict]:
    """Every board any channel has drawn since this checkout began."""
    if not os.path.isdir(SHELF):
        return []
    found = []
    for leaf in sorted(os.listdir(SHELF)):
        if not leaf.endswith(".json"):
            continue
        kept = _read(os.path.join(SHELF, leaf))
        if kept:
            found.append(kept)
    return found


def picture(kept: dict, now: datetime) -> bytes:
    """The board this record describes, drawn for this instant.

    The channel modules call this too, so there is exactly one drawing
    call in the service and a flip cannot produce a board the build
    would not have.
    """
    from match_board import draw_board, draw_board_info, draw_board_vsport

    draw = {"info": draw_board_info,
            "vsport": draw_board_vsport}.get(kept["style"], draw_board)
    board = draw(
        date.fromisoformat(kept["day"]), kept["rows"], now,
        ZoneInfo(kept["viewer"]), on_air_for,
        title=kept["title"], subtitle=kept["subtitle"],
        weekday=kept["weekday"], page=kept["page"], pages=kept["pages"],
        **({"accent": tuple(kept["accent"])} if kept.get("accent") else {}))
    drawn = io.BytesIO()
    board.convert("RGB").convert(
        "P", palette=Image.ADAPTIVE, colors=kept["colours"]).save(
            drawn, format="PNG", optimize=True)
    return drawn.getvalue()
