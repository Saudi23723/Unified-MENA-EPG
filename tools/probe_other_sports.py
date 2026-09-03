#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""How livesportsontv lays a game out, printed rather than guessed at.

Canada's own broadcasters are shut to us and it is worth writing down:
tsn.ca answers 200 with 144 KB and names only the word "TSN"; sportsnet.ca
answers with an 18 KB shell; cbc.ca/sports/live is a 404. All three build
their schedule in the browser, so there is nothing to read from a runner.

livesportsontv is not shut. Its visible text on /league/nfl names ABC,
ESPN, NBC, Peacock, Prime Video and Amazon — the American channels asked
for are there. What failed was my row detector, which wanted ONE
container holding both a clock and a channel, and this page evidently
does not put them together.

So this stops guessing at the shape and prints it: the containers that
hold a channel, what sits beside them, and the whole of one game as the
page writes it.
"""
from __future__ import annotations

import re
import sys

sys.path.insert(0, ".")

from bs4 import BeautifulSoup                                  # noqa: E402
from epg_lib import new_session, norm                          # noqa: E402

PAGES = [
    ("NFL", "https://www.livesportsontv.com/league/nfl"),
    ("NBA", "https://www.livesportsontv.com/league/nba"),
]

CHANNELS = re.compile(
    r"\bABC\b|\bESPN\d?\b|\bNBC\b|Peacock|\bFOX\b|FS1|\bCBS\b|Paramount"
    r"|\bTSN\d?\b|Sportsnet|Prime Video|Amazon|\bNFL Network\b|NBA TV"
    r"|\bTNT\b|\bDAZN\b|\bCBC\b|\bRDS\b", re.I)
A_CLOCK = re.compile(r"\b\d{1,2}:\d{2}\s?(?:[AP]M)?\b", re.I)


def look(name: str, url: str, session) -> None:
    print(f"\n=== {name} — {url}")
    reply = session.get(url, timeout=30)
    print(f"  {reply.status_code} — {len(reply.text)} bytes")
    if reply.status_code != 200:
        return

    soup = BeautifulSoup(reply.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # Find the smallest node that NAMES A CHANNEL, then climb until the
    # ancestor also holds a clock. That ancestor is the game's own block,
    # and it is found rather than assumed — the same climb, and the same
    # stopping rule, that reading jfa.jo eventually needed.
    printed = 0
    for node in soup.find_all(string=CHANNELS):
        holder = node.parent
        climbed = 0
        while holder is not None and climbed < 8:
            text = norm(holder.get_text(" | ", strip=True))
            if A_CLOCK.search(text) and len(text) < 400:
                print(f"\n  --- a game, {climbed} step(s) up from the "
                      f"channel: <{holder.name} class="
                      f"{' '.join(holder.get('class') or []) or '-'}> ---")
                print(f"    {text[:340]}")
                for kid in holder.find_all(recursive=False):
                    label = " ".join(kid.get("class") or []) or kid.name
                    print(f"      [{label[:32]:32}] "
                          f"{norm(kid.get_text(' ', strip=True))[:90]}")
                for stamp in holder.find_all("time"):
                    print(f"      <time datetime="
                          f"{stamp.get('datetime')!r}>")
                printed += 1
                break
            holder = holder.parent
            climbed += 1
        if printed >= 3:
            break
    if not printed:
        print("  nothing that holds a channel sits under anything with a "
              "clock — the page does not pair them in the markup")


def main() -> int:
    session = new_session()
    for name, url in PAGES:
        try:
            look(name, url, session)
        except Exception as exc:
            print(f"  {name} failed: {type(exc).__name__}: {str(exc)[:140]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
