#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print, do not guess: does anybody publish ADCC with a broadcaster?

"في مصادر ل adcc major؟" — and the build has a place for it already.
Channel two's IN_ORDER ends with 'Wrestling', and real_american_freestyle
files its freestyle cards as "sport": "MMA", which the gate records as
"filed with the fights, like Sky files RAF". So an ADCC row has a home
the moment something publishes one.

WHAT COVERED IT BEFORE, AND WHY IT STOPPED. The only mention of
grappling anywhere in this repository is one line:

    tapology.py:113    "Jiu Jitsu": "MMA"

Tapology carried it, and tapology is shut to a runner — seven doors
tried an hour ago, every one a Cloudflare wall, including three public
readers and jina both ways. So the question is whether anybody ELSE
publishes an ADCC card with a start and a broadcaster.

THE ONE QUESTION, unchanged from every other candidate tonight: DOES IT
NAME WHERE TO WATCH? ADCC is carried by FloGrappling and has been on UFC
Fight Pass, and a calendar that lists the brackets without saying which
of the two has it cannot reach this board — an event with no published
broadcaster is not a broadcast.

WHERE TO ASK. The official site, the broadcaster, the registration
platform most grappling events run their brackets on, and the two
listings sites that cover the sport. Each is measured for size, for
clocks, for the share of clocks on the hour — the Sport TV /guia test —
and for whether ADCC and a carrier's name appear in the same page.

FIFTEEN SECONDS EACH. boxingly-api was given ninety and spent ten and a
half minutes returning nothing seven times over.

Nothing is wired off this. It prints; a human reads.
"""
from __future__ import annotations

import re
import sys

sys.path.insert(0, ".")

import requests                                          # noqa: E402

LIKE_A_BROWSER = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/128.0.0.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "en-GB,en;q=0.9",
}

SECONDS = 15

A_CLOCK = re.compile(r"\b([0-2]?\d):([0-5]\d)\b")
A_WALL = re.compile(r"just a moment|cf-browser-verification|challenge-platform",
                    re.I)
SAYS_ADCC = re.compile(r"\bADCC\b", re.I)
# Who actually carries grappling. If none of these is on the page, the
# page cannot tell this board where to watch.
A_CARRIER = re.compile(
    r"\bFloGrappling\b|\bFlo\s*Sports\b|\bUFC Fight Pass\b|\bFight Pass\b"
    r"|\bDAZN\b|\bESPN\+?\b|\bYouTube\b|\bPPV\b|\bAbu Dhabi\b", re.I)


def ask(label: str, url: str) -> tuple[int, str]:
    try:
        got = requests.get(url, headers=LIKE_A_BROWSER, timeout=SECONDS)
    except Exception as exc:                              # noqa: BLE001
        print(f"  {label:26} FAILED  {type(exc).__name__}")
        return 0, ""
    body = got.text or ""
    clocks = A_CLOCK.findall(body)
    on_hour = sum(1 for _h, m in clocks if m == "00")
    share = (on_hour / len(clocks) * 100) if clocks else 0.0
    wall = "WALL" if A_WALL.search(body[:4000]) else "    "
    carriers = A_CARRIER.findall(body)
    seen: dict[str, int] = {}
    for name in carriers:
        seen[name.upper()] = seen.get(name.upper(), 0) + 1
    print(f"  {label:26} {got.status_code}  {len(body):>9,}B  {wall}  "
          f"{len(clocks):>4} clocks {share:5.1f}%:00  "
          f"{len(SAYS_ADCC.findall(body)):>4}x ADCC")
    if seen:
        listed = sorted(seen.items(), key=lambda kv: -kv[1])[:5]
        print(f"  {'':26} carriers: "
              f"{', '.join(f'{k}×{v}' for k, v in listed)}")
    elif got.status_code == 200 and len(body) > 20000:
        print(f"  {'':26} carriers: NONE — lists events, not where to watch")
    return got.status_code, body


def heading(text: str) -> None:
    print(f"\n{text}\n{'─' * len(text)}", flush=True)


def main() -> int:
    print("Does anybody publish an ADCC card with a start AND a carrier?")
    print("Channel two already accepts Wrestling, and RAF is filed as MMA,")
    print("so a row has a home. The source is what is missing.\n")
    print(f"  {'page':26} {'code':>4}  {'size':>9}  wall  clocks  ADCC")

    heading("1. ADCC ITSELF")
    ask("adcc.com", "https://adcc.com/")
    ask("adcombat.com", "https://adcombat.com/")
    ask("adcombat events", "https://adcombat.com/events/")
    ask("adcc-worlds", "https://www.adccombat.com/")

    heading("2. WHO CARRIES IT")
    ask("flograppling", "https://www.flograppling.com/")
    ask("flograppling events", "https://www.flograppling.com/events")
    ask("ufc fight pass", "https://ufcfightpass.com/")

    heading("3. WHERE GRAPPLING BRACKETS LIVE")
    ask("smoothcomp", "https://smoothcomp.com/en/events")
    ask("bjjheroes", "https://www.bjjheroes.com/")

    heading("4. AND THE ONE THAT USED TO CARRY IT")
    ask("tapology jiu-jitsu",
        "https://www.tapology.com/fightcenter?group=tv")

    heading("HOW TO READ THIS")
    print("  A source worth writing a reader against: 200, no wall, ADCC")
    print("  named, clocks that are NOT nearly all on the hour, and a")
    print("  carrier named on the same page. Carriers NONE decides it")
    print("  whatever else the page has. Nothing is decided here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
