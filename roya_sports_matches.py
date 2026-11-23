#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Jordan's matches on the Roya channel that carries them — from Roya Sports.

Roya's own schedule (backend.roya.tv) is a template: Roya Sport repeats
the same youth-cup block every day, and Roya TV had نشرة الأخبار at 20:00
on 6 October 2026 — the evening Jordan play Venezuela on Roya TV. The
match is not in Roya's schedule until somebody types it in.

Roya Sports (roya-sports.com, Roya's own sports site) knows. Its match
page names the channels that carry each match — for Jordan v Venezuela:
"تطبيق رؤيا الرياضي" and "رؤيا TV" — and its backend answers the same
data as JSON:

    v1/home/fixtures?date=YYYY-MM-DD&locale=ar   every match of a day
    v2/matches/<id>?locale=ar                    one match, with channels

The day list carries no channel, so only Jordan's matches — a team named
الأردن, or a Jordanian competition — are opened one by one. A match is
placed only on a Roya TV channel the page names; the app is not a channel
and anything else is not this guide's. The kickoff is the page's own
starting_at, with its own offset.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from epg_lib import fetch, log, warn

API = "https://backend.roya-sports.com/api"
DAYS = 4                            # today and the three after it
# A day of Jordanian football is twenty-odd youth and league matches, and
# the day list does not say which Roya carries, so each is opened. Kept to
# what one person browsing the site asks for: the national team first.
MOST = 60
MATCH = timedelta(hours=2)          # kickoff to final whistle, with the break
JORDAN = "الأردن"

# The channel names Roya Sports writes -> this guide's ids. Only Roya's own
# television channels; the app ("تطبيق رؤيا الرياضي") is not one.
CHANNELS = (
    (("رؤيا tv", "roya tv", "رؤيا تي في", "قناة رؤيا"), "Roya_RoyaTV"),
    (("رؤيا الرياضية", "roya sport", "رؤيا سبورت"), "Roya_RoyaSport"),
)


def channel_id(name: str) -> str | None:
    text = " ".join((name or "").lower().split())
    if not text or "تطبيق" in text or "app" in text:
        return None
    for names, cid in CHANNELS:
        # "رؤيا سبورت ١" is one of the app's five live channels, not the
        # television channel — a number after the name says so.
        if any(text == n for n in names):
            return cid
    return None


def jordanian(match: dict, section: dict) -> bool:
    teams = [(match.get(side) or {}).get("name") or "" for side in ("home_team", "away_team")]
    return any(JORDAN in t for t in teams) or JORDAN in (section.get("country_name") or "")


def day_matches(session, day: str) -> list[dict]:
    found, page = [], 1
    while page <= 10:
        data = fetch(session, f"{API}/v1/home/fixtures",
                     params={"date": day, "locale": "ar", "page": page},
                     headers={"Accept": "application/json"}).json().get("data") or {}
        for section in data.get("sections") or []:
            for match in section.get("matches") or []:
                if jordanian(match, section):
                    found.append(match)
        pages = data.get("pagination") or {}
        if not pages or (pages.get("current_page") or page) >= (pages.get("last_page") or page):
            break
        page += 1
    return found


def collect(session, now: datetime | None = None) -> list[dict]:
    """[{channel, start, stop, title, desc}] for every Jordan match on a
    Roya television channel from yesterday to three days ahead."""
    now = now or datetime.now(timezone.utc)
    seen, rows, todo = set(), [], []
    for offset in range(-1, DAYS):
        day = (now + timedelta(days=offset)).astimezone(timezone(timedelta(hours=3))).date()
        try:
            matches = day_matches(session, day.isoformat())
        except Exception as exc:  # noqa: BLE001 - one day lost, the rest go on
            warn(f"Roya Sports {day}: {exc}")
            continue
        for match in matches:
            mid = match.get("id")
            if mid and mid not in seen:
                seen.add(mid)
                todo.append(match)
    national = lambda m: any(((m.get(side) or {}).get("name") or "").strip() == JORDAN
                             for side in ("home_team", "away_team"))
    todo.sort(key=lambda m: (not national(m), m.get("starting_at") or ""))
    for match in todo[:MOST]:
        mid = match.get("id")
        try:
            detail = fetch(session, f"{API}/v2/matches/{mid}", params={"locale": "ar"},
                           headers={"Accept": "application/json"}).json().get("data") or {}
            start = datetime.fromisoformat(detail["starting_at"]).astimezone(timezone.utc)
        except Exception as exc:  # noqa: BLE001
            warn(f"Roya Sports match {mid}: {exc}")
            continue
        home = (detail.get("home_team") or {}).get("name") or ""
        away = (detail.get("away_team") or {}).get("name") or ""
        league = detail.get("league_name") or ""
        venue = (detail.get("match_info") or {}).get("stadium") or ""
        names = [channel.get("name") or "" for channel in detail.get("channels") or []]
        targets = [cid for cid in map(channel_id, names) if cid]
        # The national team on Roya is on Roya Sport too — the owner's word
        # (5 October 2026), for Jordan v Venezuela, which Roya Sports lists
        # on Roya TV and the app only.
        if national(detail) and any("رؤيا" in n or "roya" in n.lower() for n in names):
            targets.append("Roya_RoyaSport")
        for cid in dict.fromkeys(targets):
            if not home or not away:
                continue
            rows.append({"channel": cid, "start": start, "stop": start + MATCH,
                         "title": f"⚽ {home} × {away}",
                         "desc": " — ".join(x for x in (league, venue, "مباشر") if x)})
    log(f"Roya Sports: {len(seen)} Jordan match(es) in {DAYS + 1} days, "
        f"{min(len(todo), MOST)} opened, {len(rows)} on a Roya channel")
    return rows


def make_room(rows: list[dict], start: datetime, stop: datetime) -> list[dict]:
    """The channel's rows with start..stop cleared for the match: a row inside
    it goes, one across an edge is cut there."""
    out = []
    for r in rows:
        if r["stop"] <= start or r["start"] >= stop:
            out.append(r)
            continue
        if r["start"] < start:
            out.append({**r, "stop": start})
        if r["stop"] > stop:
            out.append({**r, "start": stop})
    return [r for r in out if r["stop"] - r["start"] >= timedelta(minutes=5)]
