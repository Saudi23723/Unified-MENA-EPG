#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print, do not guess: what Canal 11 is actually showing, and where it says so.

"كمان ضيف Canal 11 و مباريات المباشر تبعها القناة البرتغال" — Canal 11 is
the Portuguese Football Federation's own channel: the national teams, the
Liga 3 and Campeonato de Portugal, Liga Revelação, futsal, beach soccer
and the women's game. None of it is on SPORT TV's live pages and none of
it is on DAZN's rail, so the twelfth channel cannot be carrying it today
and nothing in the build would have noticed.

WHAT THIS HAS TO ESTABLISH, in order, before a line is written:

  1. WHICH PAGE HAS THE FIXTURES AT ALL. Six candidates, two shapes.
     A football-on-TV page lists matches and nothing else, which is
     already "بس المباشر" structurally. A full EPG page lists the
     debates and the magazines beside them and would have to be
     filtered — worse, and this repository has the scars to prove it.

  2. WHETHER THE TIME IS AN INSTANT OR A PRINTED CLOCK. live_soccer_tv
     records the trap: this site prints data-ko as its Eastern wall
     clock and dv as a true epoch, and the two disagree by four hours.
     Every row below is therefore asked for dv, not for what it prints.

  3. WHETHER THE ROWS NAME CANAL 11. A channel page that lists a fixture
     without saying the channel is a fixture this board may not publish.

THE POLICY THIS MAY BE CROSSING, and it is written into the module it
would reuse: "Used to NAME channels, never to add fixtures — the limit
every source of this kind carries here." /schedules/ is a global
aggregate and that limit is right for it. A CHANNEL page is a different
claim — it is that channel's own listing, which is what
update_shahid_sports_epg already reads it for. This prints enough to
decide which of the two Canal 11's page is, and the decision is the
reader's to make, not this file's.

Nothing here is wired to anything. It prints; a human reads.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

import requests                                          # noqa: E402
from bs4 import BeautifulSoup                            # noqa: E402

A_RUNNER = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
}

# The candidates, and what each one would mean if it is the one that answers.
CANDIDATES = (
    ("livesoccertv channel",
     "https://www.livesoccertv.com/channels/canal-11-portugal/",
     "fixtures only — the shape live_soccer_tv already parses"),
    ("futebolnatv",
     "https://www.futebolnatv.pt/canai/canal-11-portugal",
     "fixtures only, Portuguese"),
    ("canal11.pt",
     "https://www.canal11.pt/",
     "the broadcaster's own site"),
    ("fpf.pt",
     "https://www.fpf.pt/",
     "the federation that owns the channel"),
    ("programacaotv",
     "https://www.programacaotv.com/canal-11/",
     "a full EPG — carries the magazines too"),
    ("tvepg.eu",
     "https://tvepg.eu/pt/portugal/channel/canal_11",
     "a full EPG — carries the magazines too"),
)

A_CLOCK = re.compile(r"\b([0-2]?\d):([0-5]\d)\b")
SAYS_CANAL_11 = re.compile(r"canal\s*11", re.I)


def ask(label: str, url: str, why: str) -> tuple[str, int, str]:
    try:
        got = requests.get(url, headers=A_RUNNER, timeout=45)
    except Exception as exc:                              # noqa: BLE001
        print(f"  {label:22} FAILED  {type(exc).__name__}: {str(exc)[:80]}")
        return label, 0, ""
    body = got.text or ""
    clocks = A_CLOCK.findall(body)
    on_hour = sum(1 for _h, m in clocks if m == "00")
    share = (on_hour / len(clocks) * 100) if clocks else 0.0
    named = len(SAYS_CANAL_11.findall(body))
    print(f"  {label:22} {got.status_code}  {len(body):>8,}B  "
          f"{len(clocks):>4} clocks  {share:5.1f}% on :00  "
          f"{named:>4}x 'Canal 11'")
    print(f"  {'':22} {why}")
    return label, got.status_code, body


def read_the_rows(body: str) -> None:
    """The livesoccertv row shape, as live_soccer_tv.py records it."""
    soup = BeautifulSoup(body, "html.parser")
    rows = soup.select("tr.matchrow")
    print(f"\n  tr.matchrow found: {len(rows)}")
    if not rows:
        # It may be a different markup on a channel page than on
        # /schedules/. Say what IS there rather than declaring failure.
        for guess in ("tr[data-ko]", "table tr", "div.mchannels",
                      "span.ts", "td.matchcol"):
            print(f"    {guess:18} -> {len(soup.select(guess))}")
        return

    shown = 0
    no_instant = 0
    for row in rows:
        stamp = row.select_one("span.ts[dv]")
        if not stamp or not (stamp.get("dv") or "").strip().isdigit():
            no_instant += 1
            continue
        when = datetime.fromtimestamp(
            int(stamp["dv"]) / 1000, tz=timezone.utc)
        link = row.select_one("td.matchcol a[title]")
        title = (link.get("title") if link else "") or ""
        comp = row.get("data-tournament") or ""
        carried = [a.get_text(strip=True)
                   for a in row.select("div.mchannels a")]
        printed = (stamp.get_text(strip=True) or "")
        ko = row.get("data-ko") or ""
        if shown < 25:
            print(f"    {when:%d.%m %H:%M}Z  {title[:46]:46}  "
                  f"{' · '.join(carried[:3])[:44]}")
            if shown < 3:
                print(f"      {'':14} printed={printed!r} data-ko={ko!r} "
                      f"tournament={comp[:30]!r}")
        shown += 1
    print(f"\n  rows with a true instant: {shown}")
    print(f"  rows with none:           {no_instant}")
    ahead = 0
    now = datetime.now(timezone.utc)
    for row in rows:
        stamp = row.select_one("span.ts[dv]")
        if stamp and (stamp.get("dv") or "").strip().isdigit():
            if datetime.fromtimestamp(int(stamp["dv"]) / 1000,
                                      tz=timezone.utc) > now:
                ahead += 1
    print(f"  still ahead of now:       {ahead}")


def main() -> int:
    print("Canal 11 — the Portuguese federation's channel. Which page has")
    print("its fixtures, and does that page publish an INSTANT or a clock?\n")
    print(f"  {'page':22} {'code':>4}  {'size':>8}   {'clocks':>4}  "
          f"{'on :00':>12}  {'names it':>10}\n")

    bodies = {}
    for label, url, why in CANDIDATES:
        name, status, body = ask(label, url, why)
        if status == 200:
            bodies[name] = body
        print()

    if "livesoccertv channel" in bodies:
        print("\nTHE LIVESOCCERTV CHANNEL PAGE, ROW BY ROW")
        print("─" * 42)
        print("  dv is read and data-ko is not — live_soccer_tv.py records")
        print("  that the two disagree by four hours. The first three rows")
        print("  print both so the gap is visible rather than assumed.")
        read_the_rows(bodies["livesoccertv channel"])
    else:
        print("\nThe livesoccertv channel page did not answer 200, so the")
        print("row shape could not be read. Whatever else answered above is")
        print("what the next probe should be pointed at.")

    print("\nHOW TO READ THIS")
    print("─" * 16)
    print("  A page worth a reader: 200, rows carrying a dv epoch, the")
    print("  fixtures ahead of now, and Canal 11 named on them. A full EPG")
    print("  page that answers is NOT automatically better — it carries the")
    print("  debates and magazines this channel has been told to exclude.")
    print("  Nothing is decided here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
