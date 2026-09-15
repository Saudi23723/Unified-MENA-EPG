#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print, do not guess: why tapology stopped, and what could stand in.

THE CHANNEL LOST ITS BACKUP AND NOBODY MEASURED WHY. Every pass now
prints the same two lines:

    WARN permanent 403 — not retrying https://r.jina.ai/https://www.tapology.com/fightcenter?group=tv
    WARN permanent 403 — not retrying https://www.tapology.com/fightcenter?group=tv
    WARN tapology is unreachable both ways — the board keeps what the other sources gave it

Two 403s are not one fact. The direct one is expected — tapology.py says
so itself: "tapology.com answers a runner with Cloudflare's wall and
nothing else", which is why the reader goes through r.jina.ai at all.
The one through the READER is the new thing, and it has three possible
causes that call for three different fixes:

  * jina is rate limiting this runner's IP. Its free tier is about
    twenty requests a minute counted per IP, and GitHub's runners are
    shared. Fix: a key, or a different reader.
  * jina now refuses Cloudflare-protected targets generally. Fix: a
    different reader, or a different source.
  * tapology itself is gone for good. Fix: a different source.

A CONTROL SEPARATES THEM, and that is the first thing below: the same
reader asked for a page that has no wall at all. If the control answers
and tapology does not, the wall is tapology's; if neither answers, the
reader is the problem and tapology may be fine behind it.

THEN THE STAND-INS. What tapology uniquely carried, in its own words,
is "the part of fight sport nobody televises: the promotions that sell
their own card. BRAVE CF, Pancrase, OKTAGON, BKFC". BKFC already has a
reader of its own here and it works — eight cards last pass — so the
real gap is the other three, plus Sherdog as the one aggregator that
has historically served plain HTML.

THE QUESTION THAT DECIDES A SOURCE is not whether the page answers. It
is whether the schedule is IN the HTML or drawn in the browser
afterwards, and whether each card names a start and a broadcaster. So
every page below is asked the same four things and the answers are
printed as numbers:

    status      what the server said
    bytes       how much came back — a JavaScript shell is small
    clocks      how many HH:MM look like times in the raw HTML
    on the hour what fraction of them fall exactly on :00

That last one is the test this repository learned the hard way on Sport
TV's /guia: a page whose clocks are nearly all on the hour is a
template, not a schedule. A real fight card starts at 21:00 and 23:30
and 02:45, and a grid drawn by a browser leaves behind only the row
labels of an empty table.

Nothing here is wired to anything. It prints; a human reads; a reader
is written afterwards against what was printed.
"""
from __future__ import annotations

import re
import sys
from collections import Counter

sys.path.insert(0, ".")

import requests                                          # noqa: E402

A_RUNNER = {
    # The same User-Agent epg_lib sends, so this measures what the
    # builder would meet rather than what a bare urllib meets.
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

A_CLOCK = re.compile(r"\b([0-2]?\d):([0-5]\d)\b")

# The date words a real calendar prints beside its cards. A page that
# answers with none of these is not carrying a schedule whatever its
# size says.
A_MONTH = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", re.I)


def ask(label: str, url: str, timeout: int = 45) -> dict:
    """Fetch one page and print what it actually is."""
    out = {"label": label, "url": url}
    try:
        got = requests.get(url, headers=A_RUNNER, timeout=timeout)
    except Exception as exc:                              # noqa: BLE001
        print(f"  {label:26} FAILED  {type(exc).__name__}: {str(exc)[:90]}")
        out["status"] = None
        return out

    body = got.text or ""
    clocks = A_CLOCK.findall(body)
    on_hour = sum(1 for _h, m in clocks if m == "00")
    share = (on_hour / len(clocks) * 100) if clocks else 0.0
    months = len(A_MONTH.findall(body))

    out.update(status=got.status_code, bytes=len(body),
               clocks=len(clocks), on_hour=share, months=months)
    print(f"  {label:26} {got.status_code}  {len(body):>9,} bytes  "
          f"{len(clocks):>5} clocks  {share:5.1f}% on the hour  "
          f"{months:>5} month words")
    # A refusal usually explains itself in a header or the first line.
    if got.status_code >= 400:
        server = got.headers.get("server", "")
        why = got.headers.get("x-ratelimit-remaining", "")
        first = " ".join(body.split())[:140]
        print(f"  {'':26} server={server!r} ratelimit-remaining={why!r}")
        if first:
            print(f"  {'':26} said: {first}")
    return out


def heading(text: str) -> None:
    print(f"\n{text}\n{'─' * len(text)}", flush=True)


def main() -> int:
    print("What answers a GitHub runner, and what is actually in the HTML.")
    print("A schedule drawn in the browser leaves a small page whose few")
    print("clocks sit on the hour. A real card list does not.\n")
    print(f"  {'page':26} {'code':>4}  {'size':>9}         "
          f"{'clocks':>5}  {'on :00':>13}  {'month words':>11}")

    heading("1. IS IT THE READER, OR IS IT TAPOLOGY?")
    print("  A control with no wall, then the same reader on tapology,")
    print("  then tapology bare. Three answers, three different fixes.\n")
    control = ask("jina / example.com", "https://r.jina.ai/https://example.com")
    jina_tap = ask("jina / tapology",
                   "https://r.jina.ai/https://www.tapology.com/fightcenter?group=tv")
    bare_tap = ask("tapology direct",
                   "https://www.tapology.com/fightcenter?group=tv")

    print()
    reader_ok = (control.get("status") == 200)
    if reader_ok and jina_tap.get("status") == 200:
        print("  VERDICT: both answer — the 403s were this runner's IP being")
        print("           rate limited at the time, not a permanent wall.")
    elif reader_ok and jina_tap.get("status") != 200:
        print("  VERDICT: the reader works and refuses THIS target — jina will")
        print("           not fetch tapology any more. A key would not help;")
        print("           a different reader or a different source would.")
    elif not reader_ok:
        print("  VERDICT: the reader itself does not answer this runner at all.")
        print("           tapology may be perfectly fine behind it. Try a key")
        print("           or another reader before replacing the source.")
    if bare_tap.get("status") == 200:
        print("  AND: tapology answered DIRECTLY — the reader is not needed.")

    heading("2. SHERDOG — the one aggregator that has served plain HTML")
    print("  Tapology's value is the small promotions. Sherdog lists the")
    print("  same ones. The question is whether its calendar is in the HTML.\n")
    ask("sherdog /events", "https://www.sherdog.com/events")
    ask("sherdog /events/1", "https://www.sherdog.com/events/1")

    heading("3. THE THREE PROMOTIONS TAPOLOGY WAS CARRYING")
    print("  BKFC already has a reader here and it works, so it is not asked")
    print("  about. These are the ones nothing else in the build covers.\n")
    for label, url in (
            ("BRAVE CF", "https://bravecf.com/events/"),
            ("BRAVE CF (alt)", "https://www.bravecf.com/"),
            ("OKTAGON", "https://oktagonmma.com/en/events"),
            ("OKTAGON (alt)", "https://oktagonmma.com/"),
            ("Pancrase", "https://www.pancrase.co.jp/"),
            ("ONE Championship", "https://www.onefc.com/events/"),
            ("Cage Warriors", "https://www.cagewarriors.com/events/"),
    ):
        ask(label, url)

    heading("4. AND WHAT THE BUILD ALREADY HAS, as a baseline")
    print("  If these answer and the ones above do not, the difference is")
    print("  the page, not the runner.\n")
    ask("bkfc (already read)", "https://www.bkfc.com/events")
    ask("espn mma schedule", "https://global.espn.com/mma/schedule")

    heading("HOW TO READ THIS")
    print("  A page worth writing a reader against has: a 200, a body in the")
    print("  hundreds of KB, dozens of clocks, and NOT most of them on the")
    print("  hour. A 200 with 40KB and four clocks all at :00 is a shell.")
    print("  Nothing is decided here. This printed; a human reads.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
