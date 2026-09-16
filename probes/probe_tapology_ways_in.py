#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print, do not guess: every way into tapology, and what sporteventz is.

TWO THINGS, ASKED TOGETHER because they answer the same gap.

ONE — IS THERE A WAY BACK INTO TAPOLOGY AT ALL?

What is already established, measured rather than assumed: the direct
page answers a runner with Cloudflare's wall, which tapology.py has
always said; and r.jina.ai, the reader written to get past it, now
answers 403 from Cloudflare TOO — proven with a control on
r.jina.ai/https://example.com, a page with no wall of its own. The
reader is blocked, not the site. So tapology may be perfectly readable
behind a door we no longer have a key to.

This tries every door without buying one:

  * the bare page, with a full browser header set rather than the
    minimal one — Cloudflare's decision can turn on Accept-Encoding,
    sec-ch-ua and a referer as much as on the IP
  * tapology's own AJAX path, which serves the fightcenter as a
    fragment and is sometimes not behind the same rule as the page
  * three public text/CORS readers that are not jina
  * jina again, both with and without a scheme in the target, because
    the two spellings are routed differently

Whichever answers 200 with fight names in it is the way in. The names
are counted, not eyeballed: a wall page is 5KB and says "Just a
moment", a fightcenter is hundreds of KB and says UFC and Bellator and
BRAVE and PPV.

TWO — IS SPORTEVENTZ ANY USE?

Asked the same question as every other candidate, and it is the only
question that matters here: DOES IT NAME THE BROADCASTER? The gap that
is open is boxing with nowhere to watch it — "boxing promotions: 0
card(s) inside the window", "Sky: 0 fight programme(s) inside the
window". A calendar that lists cards without saying who carries them
cannot close that, however complete it is.

So sporteventz is fetched at its root and at the paths a fight listing
would live under, and each answer is measured for size, for clocks, for
the share of those clocks on the hour — the Sport TV /guia test, where a
page whose clocks are nearly all at :00 is an empty template — and for
whether broadcaster words appear beside the fixtures.

EVERY TIMEOUT HERE IS SHORT, and that is a lesson paid for an hour ago:
boxingly-api was given ninety seconds per call and spent ten and a half
minutes returning nothing seven times. A source that cannot answer in
fifteen seconds is not a source this board can poll every five minutes,
so fifteen seconds is all any of them gets.

Nothing is wired off this. It prints; a human reads.
"""
from __future__ import annotations

import re
import sys
from urllib.parse import quote

sys.path.insert(0, ".")

import requests                                          # noqa: E402

# The page tapology.py wants, and the one this is all about.
WANTED = "https://www.tapology.com/fightcenter?group=tv"

# A whole browser, not the two headers a script usually sends.
LIKE_A_BROWSER = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/128.0.0.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://www.tapology.com/",
}

PLAIN = {"User-Agent": LIKE_A_BROWSER["User-Agent"],
         "Accept": "*/*"}

# An XHR asking for a fragment looks different to a browser asking for
# a page, and is sometimes governed by a different rule.
LIKE_AN_XHR = dict(PLAIN, **{
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "text/html, */*; q=0.01",
    "Referer": "https://www.tapology.com/fightcenter",
})

# What a real fightcenter says and a wall page does not.
A_WALL = re.compile(r"just a moment|cf-browser-verification|challenge-platform",
                    re.I)
A_FIGHT = re.compile(
    r"\bUFC\b|\bBellator\b|\bBRAVE\b|\bOKTAGON\b|\bPancrase\b|\bBKFC\b"
    r"|\bPFL\b|\bboxing\b|\bPPV\b|\bDAZN\b|Fight Pass", re.I)
A_CLOCK = re.compile(r"\b([0-2]?\d):([0-5]\d)\b")

SECONDS = 15


def ask(label: str, url: str, headers=None) -> tuple[int, str]:
    try:
        got = requests.get(url, headers=headers or PLAIN, timeout=SECONDS)
    except Exception as exc:                              # noqa: BLE001
        print(f"  {label:30} FAILED  {type(exc).__name__}")
        return 0, ""
    body = got.text or ""
    wall = "WALL" if A_WALL.search(body[:4000]) else "    "
    fights = len(A_FIGHT.findall(body))
    print(f"  {label:30} {got.status_code}  {len(body):>9,}B  {wall}  "
          f"{fights:>4} fight word(s)")
    return got.status_code, body


def heading(text: str) -> None:
    print(f"\n{text}\n{'─' * len(text)}", flush=True)


def ways_into_tapology() -> None:
    print("  A wall page is ~5KB and says 'Just a moment'. A fightcenter")
    print("  is hundreds of KB and says UFC, Bellator, BRAVE, PPV.\n")

    ask("bare, minimal headers", WANTED)
    ask("bare, a whole browser", WANTED, LIKE_A_BROWSER)
    ask("its own ajax path", WANTED + "&schedule=upcoming&page=1",
        LIKE_AN_XHR)
    ask("the plain fightcenter", "https://www.tapology.com/fightcenter",
        LIKE_A_BROWSER)

    print()
    for label, url in (
        ("jina, with scheme", f"https://r.jina.ai/{WANTED}"),
        ("jina, without scheme",
         "https://r.jina.ai/www.tapology.com/fightcenter?group=tv"),
        ("allorigins",
         f"https://api.allorigins.win/raw?url={quote(WANTED, safe='')}"),
        ("codetabs",
         f"https://api.codetabs.com/v1/proxy?quest={quote(WANTED, safe='')}"),
        ("isomorphic-git cors",
         f"https://cors.isomorphic-git.org/{WANTED}"),
    ):
        ask(label, url)


def sporteventz() -> None:
    print("  The only question that matters: does it name the")
    print("  broadcaster? The open gap is boxing with nowhere to watch.\n")
    print(f"  {'page':30} {'code':>4}  {'size':>9}  wall  fight words")
    bodies = {}
    for label, url in (
        ("root", "https://sporteventz.com/en/"),
        ("boxing", "https://sporteventz.com/en/boxing/"),
        ("mma", "https://sporteventz.com/en/mma/"),
        ("ufc", "https://sporteventz.com/en/ufc/"),
        ("today", "https://sporteventz.com/en/today/"),
        ("tv", "https://sporteventz.com/en/tv/"),
    ):
        code, body = ask(label, url, LIKE_A_BROWSER)
        if code == 200 and len(body) > 20000:
            bodies[label] = body

    if not bodies:
        print("\n  nothing substantial answered — there is no page to read")
        return

    label, body = max(bodies.items(), key=lambda pair: len(pair[1]))
    print(f"\n  the biggest answer was {label!r}; measuring it:\n")
    clocks = A_CLOCK.findall(body)
    on_hour = sum(1 for _h, m in clocks if m == "00")
    share = (on_hour / len(clocks) * 100) if clocks else 0.0
    print(f"    clocks in the HTML       {len(clocks)}")
    print(f"    on the hour              {share:.1f}%   "
          f"(near 100% is a template, not a schedule)")

    # And the decisive one: broadcaster words anywhere near the fixtures.
    carriers = re.findall(
        r"\bDAZN\b|\bESPN\+?\b|\bSky Sports?\b|\bTNT Sports?\b|\bbeIN\b"
        r"|\bPPV\b|\bParamount\+?\b|\bUFC Fight Pass\b|\bPrime Video\b"
        r"|\bTNT\b|\bCanal\+?\b|\bMovistar\b|\bViaplay\b", body, re.I)
    seen: dict[str, int] = {}
    for name in carriers:
        seen[name.upper()] = seen.get(name.upper(), 0) + 1
    print(f"    broadcaster names        {len(carriers)} mention(s)")
    if seen:
        listed = sorted(seen.items(), key=lambda kv: -kv[1])[:10]
        print(f"      {', '.join(f'{k}×{v}' for k, v in listed)}")
    else:
        print("      NONE — it lists events and not where to watch them,")
        print("      which is the one thing this board cannot do without")

    # Is any of it in the HTML, or is the page a shell?
    for guess in ("table tr", "[class*=event]", "[class*=match]",
                  "time", "[datetime]", "li"):
        try:
            from bs4 import BeautifulSoup
            found = BeautifulSoup(body, "html.parser").select(guess)
            print(f"    {guess:24} -> {len(found)}")
        except Exception:                                 # noqa: BLE001
            break


def main() -> int:
    print("Every door into tapology, and what sporteventz actually is.")
    print(f"Every call gets {SECONDS}s and no more — boxingly-api was given")
    print("ninety and spent ten and a half minutes returning nothing.")

    heading("1. TAPOLOGY — IS THERE A WAY IN?")
    ways_into_tapology()

    heading("2. SPORTEVENTZ")
    sporteventz()

    heading("HOW TO READ THIS")
    print("  Tapology: any row with a 200, no WALL, and fight words in the")
    print("  hundreds is the way back in. All walls means the site is shut")
    print("  to a runner and a promotion-by-promotion reader is the answer.")
    print("  Sporteventz: broadcaster names NONE decides it, whatever else")
    print("  the page has. Nothing is decided here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
