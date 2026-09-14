#!/usr/bin/env python3
"""Regression checks for the dashboard's display-only match rows."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import match_board


FORBIDDEN = ("LIVE", "مباشر", "التالي", "انتهى")


def event(start: datetime) -> dict:
    return {
        "start": start,
        "title": "Home FC - Away FC",
        "competition": "Premier League",
        "channels": ["Sport TV 1"],
    }


def captured_text(drawer, *, day: date, now: datetime) -> list[str]:
    seen: list[str] = []
    def capture(pen, xy, text, size, fill, **kwargs):
        seen.append(str(text))
        return None

    original = match_board.draw_text
    match_board.draw_text = capture
    try:
        drawer(
            day,
            [event(now + timedelta(hours=1))],
            now,
            timezone.utc,
            timedelta(minutes=120),
            title="Sports Dashboard",
            subtitle="",
            weekday="الاثنين",
        )
    finally:
        match_board.draw_text = original
    return seen


def main() -> None:
    now = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
    drawers = (
        match_board.draw_board,
        match_board.draw_board_vsport,
        match_board.draw_board_info,
    )
    for drawer in drawers:
        for offset, expected_day in enumerate(("اليوم", "غداً", "بعد غد")):
            texts = captured_text(
                drawer, day=now.date() + timedelta(days=offset), now=now
            )
            joined = "\n".join(texts)
            assert expected_day in joined, (drawer.__name__, expected_day)
            assert not any(word in joined for word in FORBIDDEN), (
                drawer.__name__,
                [word for word in FORBIDDEN if word in joined],
            )
    print("dashboard display self-test: ok")


if __name__ == "__main__":
    main()