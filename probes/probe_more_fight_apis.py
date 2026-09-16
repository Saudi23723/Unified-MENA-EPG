#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print, do not guess: are these four any use to this board?

The reader sent four links and asked outright. Three are candidate data
sources and one is documentation, and the honest answer for every one of
them is the same question this repository asks of every source:

    DOES IT NAME THE BROADCASTER?

Not "does it have the event". The board's rule, everywhere, is that a
fixture with no published broadcaster is not a broadcast and does not go
out. A calendar that lists a fight card perfectly and says nothing about
where to watch it cannot fill the gap that is open here, and two of this
repository's sources were already rejected on exactly that ground.

WHAT IS ACTUALLY OPEN, measured on the last full build:

    boxing promotions:  0 card(s) inside the window
    Sky EPG:            383 channels, 11 carry fights,
                        0 fight programme(s) inside the window
    tapology:           403 both ways — the reader is blocked, not the
                        site; a control on r.jina.ai/example.com came
                        back 403 from Cloudflare too
    espn:               UFC gave five cards; PFL and Bellator each
                        printed "no future card on the page this pass"

So there are two distinct gaps and they want different answers. One is
BOXING, where nothing inside the window has a broadcaster. The other is
whether ESPN's PFL and BELLATOR scoreboards are empty because those
promotions have nothing on, or because the endpoint has moved.

THE FOUR, AND WHAT EACH IS ASKED

1. ESPN, the same scoreboard espn_fights.py already reads. This is not a
   new source at all — the question is why two of its three leagues come
   back empty. Each league is asked with an explicit sixteen-day window,
   and the answer is printed as a count of events and a count of those
   naming a broadcast, per league. If PFL answers with events here, the
   reader has a bug. If it answers with none, PFL has nothing on.

2. thesportsdb.com. Free tier, test key "3" and "123" both tried since
   the free key has changed before. Asked for its boxing and MMA leagues
   and their next events, and every event inspected for a broadcaster
   field — strTvStation or anything like it.

3. boxingly-api.onrender.com. A free Render dyno sleeps when idle and
   wakes slowly, so it is asked twice with the gap timed: a source this
   board polls every five minutes cannot take a minute to answer. Its
   shape is printed whatever it is.

4. api-evangelist/sportsdb. This is a GitHub repository of API
   DOCUMENTATION, not a feed. It is asked only what it points at, so the
   answer is a list of names rather than rows.

Nothing here is wired to anything. It prints; a human reads.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

import requests                                          # noqa: E402

A_RUNNER = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
}

# The words a feed uses when it names where something is shown. If none
# of these carries a value, the feed does not name a broadcaster.
A_BROADCASTER = ("strTvStation", "strChannel", "tv", "tvStation",
                 "broadcast", "broadcasts", "network", "channel",
                 "streaming", "watch", "provider")


def heading(text: str) -> None:
    print(f"\n{text}\n{'─' * len(text)}", flush=True)


def get(url: str, timeout: int = 60):
    began = time.monotonic()
    try:
        got = requests.get(url, headers=A_RUNNER, timeout=timeout)
    except Exception as exc:                              # noqa: BLE001
        print(f"    FAILED after {time.monotonic() - began:.1f}s  "
              f"{type(exc).__name__}: {str(exc)[:90]}")
        return None, time.monotonic() - began
    return got, time.monotonic() - began


def names_a_broadcaster(blob) -> list[str]:
    """Every key anywhere in this object that carries a broadcaster."""
    found = []

    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                here = f"{path}.{key}" if path else key
                if (any(word.lower() in key.lower()
                        for word in A_BROADCASTER)
                        and value not in (None, "", [], {})):
                    found.append(f"{here}={json.dumps(value, ensure_ascii=False)[:60]}")
                walk(value, here)
        elif isinstance(node, list):
            for item in node[:4]:
                walk(item, f"{path}[]")

    walk(blob)
    return found


def espn_leagues() -> None:
    host = "https://site.web.api.espn.com/apis/site/v2/sports/mma"
    now = datetime.now(timezone.utc)
    window = (f"{(now - timedelta(days=16)):%Y%m%d}-"
              f"{(now + timedelta(days=16)):%Y%m%d}")
    print(f"  the same endpoint espn_fights.py reads, window {window}\n")
    for league in ("ufc", "pfl", "bellator"):
        url = f"{host}/{league}/scoreboard?dates={window}"
        got, took = get(url)
        if got is None:
            continue
        try:
            payload = got.json()
        except ValueError:
            print(f"    {league:9} {got.status_code}  not JSON "
                  f"({len(got.text):,}B)")
            continue
        events = payload.get("events") or []
        named = 0
        titles = []
        for event in events:
            if names_a_broadcaster(event):
                named += 1
            name = event.get("name") or event.get("shortName") or ""
            when = event.get("date") or ""
            if len(titles) < 4:
                titles.append(f"{when[:16]} {name[:46]}")
        print(f"    {league:9} {got.status_code}  {took:4.1f}s  "
              f"{len(events):>3} event(s), {named} naming a broadcast")
        for line in titles:
            print(f"      {line}")
        if not events:
            # Say WHY there are none, if the payload says anything.
            leagues = payload.get("leagues") or []
            if leagues:
                season = (leagues[0].get("season") or {}).get("year")
                print(f"      the endpoint answered; season={season}, "
                      f"events=[] — the league has nothing in the window")


def thesportsdb() -> None:
    for key in ("3", "123"):
        base = f"https://www.thesportsdb.com/api/v1/json/{key}"
        got, took = get(f"{base}/all_leagues.php", timeout=45)
        if got is None or got.status_code != 200:
            code = got.status_code if got else "—"
            print(f"    key {key!r}: {code}")
            continue
        try:
            leagues = (got.json() or {}).get("leagues") or []
        except ValueError:
            print(f"    key {key!r}: 200 but not JSON")
            continue
        fighting = [one for one in leagues
                    if (one.get("strSport") or "").lower()
                    in ("fighting", "boxing", "mma")]
        print(f"    key {key!r}: {got.status_code} {took:4.1f}s  "
              f"{len(leagues)} league(s), {len(fighting)} in fighting sports")
        for one in fighting[:10]:
            print(f"      {one.get('idLeague'):>5}  "
                  f"{(one.get('strLeague') or '')[:40]:40} "
                  f"{one.get('strSport')}")
        # And the decisive question, asked of a real event list.
        for one in fighting[:3]:
            lid = one.get("idLeague")
            nxt, _ = get(f"{base}/eventsnextleague.php?id={lid}", timeout=45)
            if nxt is None or nxt.status_code != 200:
                continue
            try:
                events = (nxt.json() or {}).get("events") or []
            except ValueError:
                continue
            print(f"\n      next events for {one.get('strLeague')}: "
                  f"{len(events)}")
            for event in events[:3]:
                said = names_a_broadcaster(event)
                print(f"        {event.get('dateEvent')} "
                      f"{event.get('strTime')}  "
                      f"{(event.get('strEvent') or '')[:42]}")
                print(f"          broadcaster field(s): "
                      f"{said if said else 'NONE'}")
        break


def boxingly() -> None:
    base = "https://boxingly-api.onrender.com"
    print("    a free Render dyno sleeps when idle — the first call is")
    print("    timed, then a second, so the wake cost is visible.\n")
    for attempt, path in enumerate(("/", "/", "/api", "/events",
                                    "/api/events", "/fights", "/docs"), 1):
        got, took = get(base + path, timeout=90)
        if got is None:
            continue
        body = got.text or ""
        shape = "JSON" if body[:1] in "[{" else "not JSON"
        print(f"    {path:14} {got.status_code}  {took:5.1f}s  "
              f"{len(body):>8,}B  {shape}")
        if shape == "JSON" and got.status_code == 200:
            try:
                blob = got.json()
            except ValueError:
                continue
            said = names_a_broadcaster(blob)
            if isinstance(blob, list):
                print(f"      {len(blob)} item(s); first: "
                      f"{json.dumps(blob[0], ensure_ascii=False)[:180]}"
                      if blob else "      empty list")
            else:
                print(f"      keys: {list(blob)[:12]}")
            print(f"      broadcaster field(s): {said[:3] if said else 'NONE'}")


def api_evangelist() -> None:
    print("    a repository of API DOCUMENTATION, not a feed. Asked only")
    print("    what it points at.\n")
    for url in ("https://api.github.com/repos/api-evangelist/sportsdb",
                "https://api.github.com/repos/api-evangelist/sportsdb/"
                "contents/"):
        got, _ = get(url, timeout=45)
        if got is None or got.status_code != 200:
            print(f"    {got.status_code if got else '—'}  {url[-40:]}")
            continue
        try:
            blob = got.json()
        except ValueError:
            continue
        if isinstance(blob, dict):
            print(f"    {blob.get('full_name')}: "
                  f"{(blob.get('description') or '')[:90]}")
            print(f"      updated {blob.get('pushed_at')}, "
                  f"{blob.get('size')}KB")
        else:
            print(f"      {len(blob)} entries at the root: "
                  f"{[item.get('name') for item in blob][:14]}")


def main() -> int:
    print("Four links, one question each: does it name the broadcaster?")
    print("A fixture with no published broadcaster is not a broadcast and")
    print("does not reach this board. That rule decides all four.")

    heading("1. ESPN — ALREADY READ. WHY ARE TWO LEAGUES EMPTY?")
    espn_leagues()

    heading("2. THESPORTSDB — the boxing gap is the real one")
    thesportsdb()

    heading("3. BOXINGLY on Render — and what it costs to wake")
    boxingly()

    heading("4. API-EVANGELIST/SPORTSDB — documentation, not a feed")
    api_evangelist()

    heading("HOW TO READ THIS")
    print("  A source worth writing a reader against answers quickly,")
    print("  carries events inside a four-day window, and NAMES WHERE")
    print("  EACH ONE IS SHOWN. A perfect calendar with no broadcaster")
    print("  cannot fill the gap that is open. Nothing is decided here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
