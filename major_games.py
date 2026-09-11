#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Major multi-sport games — Asian, Commonwealth, Pan American, European, African.

The schedules are checked-in snapshots built from official session PDFs.
No broadcaster is named by the official documents, so rows are shown with
an empty channel line and the board's PPV fallback applies where the
repository's policy allows it.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from epg_lib import log, norm

DATA_PATH = Path(__file__).with_name("major_games_data.json")

# Map the edition name to the sport category used by the board.
EDITION_SPORT = {
    "Aichi-Nagoya 2026": "Asian Games",
    "Glasgow 2026": "Commonwealth Games",
}

# A session is shown for this long when deciding live indicators.
DEFAULT_DURATION = timedelta(hours=4)


def _load() -> dict:
    if not DATA_PATH.exists():
        log(f"major_games: {DATA_PATH.name} not found, no sessions loaded")
        return {"sessions": []}
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log(f"major_games: could not read {DATA_PATH.name} ({exc})")
        return {"sessions": []}


def _parse_start(raw: str) -> datetime:
    """ISO string with offset to timezone-aware datetime."""
    return datetime.fromisoformat(raw)


def events(floor: datetime, ceiling: datetime) -> list[dict]:
    """Return major-games sessions inside the window as board events."""
    data = _load()
    out = []
    for session in data.get("sessions", []):
        start = _parse_start(session["start"])
        if not (floor <= start < ceiling):
            continue
        edition = session["edition"]
        sport = EDITION_SPORT.get(edition, "Olympics")
        discipline = session["discipline"]
        # Aichi-Nagoya basketball is shown only when a beIN broadcast is
        # confirmed; unlabeled sessions (the board's "PPV" fallback) are
        # dropped for that discipline alone. Every other sport is untouched.
        if edition == "Aichi-Nagoya 2026" and "basketball" in discipline.lower():
            bein = [c for c in session.get("channels", []) if c.lower().startswith("bein")]
            if not bein:
                continue
            channels = bein
        else:
            channels = list(session.get("channels", []))
        title = norm(f"{edition} — {discipline}")
        out.append({
            "title": title,
            "sport": sport,
            "start": start,
            "channels": channels,
            "source": "majorgames",
            "duration": DEFAULT_DURATION,
            "discipline": discipline,
            "edition": edition,
        })
    if out:
        log(f"  major_games: {len(out)} session(s) inside the window")
    return out


if __name__ == "__main__":
    now = datetime.now(timezone.utc)
    floor = now
    ceiling = now + timedelta(days=14)
    for ev in events(floor, ceiling):
        print(ev["start"].isoformat(), ev["sport"], ev["title"])
