#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only audit: is every live broadcast beIN airs actually badged?

Two things came out of reading the raw API:

  * the endpoint caps at 100 rows unless `limit` is passed. beIN SPORTS 1
    answers count=156 and hands back 100, so three days go missing —
    a live match in them is not unbadged, it is absent.
  * every match row carries data.m_date / data.m_time, the real kick-off
    in UTC. A broadcast whose own window contains the kick-off IS the
    live airing; one that does not is a replay. That is an independent
    check on beIN's `live` flag rather than taking it on trust.

This runs that check on every channel and reports both directions: a
kick-off inside the window with live=false (a badge we would miss) and
live=true with the kick-off outside (a badge we would invent). Changes
nothing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

UTC = timezone.utc
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "Accept": "application/json", "Accept-Language": "ar,en;q=0.8"}
T = (5, 30)
API_CHANNELS = "https://www.beinsports.com/api/opta/tv-channel"
API_EVENTS = "https://www.beinsports.com/api/opta/tv-event"
DAYS_BACK, DAYS_FORWARD = 1, 6


def section(name):
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}", flush=True)


def when(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def kickoff(row):
    """The real kick-off, UTC. m_time carries the Z; m_date is the same
    instant without it."""
    data = row.get("data") or {}
    stamp = when(data.get("m_date"))
    return stamp.replace(tzinfo=UTC) if stamp else None


def is_live_flag(row):
    f = row.get("live")
    return f is True or (isinstance(f, str) and f.strip().lower() == "true")


def main():
    now = datetime.now(UTC)
    params = {
        "startBefore": (now + timedelta(days=DAYS_FORWARD)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "endAfter": (now - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "limit": 1000,
    }

    r = requests.get(API_CHANNELS, headers=H, params={"region": "ar-mena"}, timeout=T)
    channels = []
    for c in r.json().get("rows", []) or []:
        name = (c.get("title") or c.get("name") or "").strip()
        guid = c.get("site_id") or c.get("siteId") or c.get("id")
        if name and guid:
            channels.append((name, guid))
    channels.sort()
    section(f"{len(channels)} channels — auditing with limit=1000")

    print(f"{'channel':22} {'count':>6} {'got':>5} {'flag':>5} "
          f"{'kickoff-in-window':>18} {'MISSED':>7} {'EXTRA':>6}", flush=True)
    missed_all, extra_all = [], []
    totals = [0, 0, 0, 0, 0, 0]

    for name, guid in channels:
        try:
            body = requests.get(API_EVENTS, headers=H,
                                params={**params, "channelIds": guid},
                                timeout=T).json()
        except Exception as exc:
            print(f"  {name:22} FAILED: {exc}", flush=True)
            continue
        rows = body.get("rows", []) or []
        count = body.get("count")

        flagged = sum(1 for x in rows if is_live_flag(x))
        checkable = missed = extra = 0
        for x in rows:
            ko, start, stop = kickoff(x), when(x.get("startDate")), when(x.get("endDate"))
            if ko is None or start is None or stop is None:
                continue
            checkable += 1
            inside = start <= ko < stop
            if inside and not is_live_flag(x):
                missed += 1
                missed_all.append((name, x.get("startDate"), x.get("data", {}).get("m_date"),
                                   x.get("title")))
            if is_live_flag(x) and not inside:
                extra += 1
                extra_all.append((name, x.get("startDate"), x.get("data", {}).get("m_date"),
                                  x.get("title")))

        print(f"  {name:22} {str(count):>6} {len(rows):>5} {flagged:>5} "
              f"{checkable:>18} {missed:>7} {extra:>6}", flush=True)
        for i, v in enumerate((count or 0, len(rows), flagged, checkable, missed, extra)):
            totals[i] += v

    section("totals")
    print(f"  count={totals[0]}  rows={totals[1]}  live-flagged={totals[2]}  "
          f"match-rows={totals[3]}  MISSED={totals[4]}  EXTRA={totals[5]}", flush=True)

    section(f"MISSED — kick-off inside the broadcast but live=false ({len(missed_all)})")
    for n, s, k, t in missed_all[:60]:
        print(f"  {n:20} air {s}  kickoff {k}  {str(t)[:56]}", flush=True)

    section(f"EXTRA — live=true but kick-off outside the broadcast ({len(extra_all)})")
    for n, s, k, t in extra_all[:60]:
        print(f"  {n:20} air {s}  kickoff {k}  {str(t)[:56]}", flush=True)


if __name__ == "__main__":
    main()
