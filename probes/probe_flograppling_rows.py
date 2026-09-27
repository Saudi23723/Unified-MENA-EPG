#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print, do not guess: are FloGrappling's dates fixtures or file dates?

Round two found the blob and the path, and raised the question that
decides everything:

    biggest inline script: 'flo-app-state', 228,179 chars
      it says ADCC 464 time(s)
      date-looking values: 82 ISO, 0 epoch-ms
        raw 2026-09-12T09:00:00+0000  -> 12.09 09:00Z
        raw 2026-09-13T23:59:59+0000  -> 13.09 23:59Z
        raw 2026-09-15T16:38:00+00:00 -> 15.09 16:38Z

EVERY ONE OF THOSE IS IN THE PAST. Today is the 16th. The page found was
/events/14687695-2026-adcc-world-championships/VIDEOS, and 09:00 to
23:59 on the 12th and 13th is exactly what a two-day championship that
has already been fought looks like. 23:59:59 in particular is nobody's
kickoff — it is an end-of-day boundary, the shape a catalogue window
has, not a broadcast.

So the blob may be a VIDEO CATALOGUE: when each replay was published,
not when anything is next on. A reader written against that would put
finished grappling on a board headed مباشر, which is the precise fault
this repository refuses in its own words — "a guide that publishes
another channel's match is worse than one that publishes nothing" — and
it is also the reader's own standing rule, "بس المباشر".

WHAT THIS ASKS, and it is the only thing left to know:

  1. IS ANY DATE IN THIS BLOB IN THE FUTURE? Counted, not sampled. If
     none is, the page is a catalogue and the answer to "is there a
     source for ADCC" is no, whatever else it has.

  2. WHAT KEY HOLDS IT? A date under "publishedAt" or "createdAt" is a
     file date. One under "startDateTime", "liveEventStart" or
     "scheduledStart" is a fixture. The key names are printed with
     their values so the difference is read rather than inferred.

  3. DOES A FUTURE DATE SIT BESIDE A TITLE AND A CARRIER? That is what
     a row is, and all three have to be in the same object.

The blob is parsed as JSON where it parses and walked as text where it
does not, because a React state dump is not always valid JSON on its
own. Both paths print what they find.

Fifteen seconds a call.

Nothing is wired off this. It prints; a human reads.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

import requests                                          # noqa: E402
from bs4 import BeautifulSoup                            # noqa: E402

PAGES = (
    ("home", "https://www.flograppling.com/"),
    ("adcc worlds",
     "https://www.flograppling.com/events/"
     "14687695-2026-adcc-world-championships/videos"),
    ("adcc worlds root",
     "https://www.flograppling.com/events/"
     "14687695-2026-adcc-world-championships"),
)

LIKE_A_BROWSER = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/128.0.0.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "en-GB,en;q=0.9",
}
SECONDS = 15

# "key": "2026-09-12T09:00:00+0000" — the key is what tells a fixture
# from a file date, so it is captured with the value.
# AND THE QUOTES MAY BE ESCAPED. Round three's first attempt found
# ZERO key/date pairs on a blob round two had already counted 82 ISO
# dates in — which was this pattern's fault, not the site's. A React
# state dump is often a JS STRING holding JSON, so every quote arrives
# as \" rather than ". The pattern now accepts either, and the failure
# is left recorded here because a probe that reports "nothing found"
# when its own regex is wrong is worse than no probe at all.
A_DATED_KEY = re.compile(
    r'\\?"([A-Za-z_][A-Za-z0-9_]{2,40})\\?"\s*:\s*'
    r'\\?"(20\d\d-[01]\d-[0-3]\dT[0-2]\d:[0-5]\d(?::[0-5]\d)?'
    r'(?:Z|[+-][0-2]\d:?[0-5]\d)?)\\?"')

# A plain sweep for any ISO date at all, as the control: if this finds
# dates and the pattern above finds none, the pattern is wrong again.
ANY_ISO = re.compile(
    r'(20\d\d-[01]\d-[0-3]\dT[0-2]\d:[0-5]\d(?::[0-5]\d)?'
    r'(?:Z|[+-][0-2]\d:?[0-5]\d)?)')

NOW = datetime.now(timezone.utc)


def when_of(raw: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        # "+0000" without the colon is not ISO to Python before 3.11 in
        # every shape; normalise it rather than dropping the value.
        fixed = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", raw)
        try:
            parsed = datetime.fromisoformat(fixed.replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else \
        parsed.replace(tzinfo=timezone.utc)


def the_blob(body: str) -> str:
    soup = BeautifulSoup(body, "html.parser")
    best = ""
    for tag in soup.find_all("script"):
        text = tag.string or tag.get_text() or ""
        if len(text) > len(best) and "{" in text:
            best = text
    return best


def heading(text: str) -> None:
    print(f"\n{text}\n{'─' * len(text)}", flush=True)


def read_one(label: str, url: str) -> None:
    try:
        got = requests.get(url, headers=LIKE_A_BROWSER, timeout=SECONDS)
    except Exception as exc:                              # noqa: BLE001
        print(f"  {label}: FAILED {type(exc).__name__}")
        return
    if got.status_code != 200:
        print(f"  {label}: {got.status_code}")
        return
    blob = the_blob(got.text)
    print(f"  {label}: {got.status_code}, blob {len(blob):,} chars")

    pairs = A_DATED_KEY.findall(blob)
    loose = ANY_ISO.findall(blob)
    print(f"    control: {len(loose)} ISO date(s) anywhere in the blob")
    if not pairs:
        print(f"    but 0 under a readable key.")
        if loose:
            print("    THE PATTERN IS STILL WRONG, not the page — the dates")
            print("    are there. Printing them bare so the answer is not lost:")
            whens = [w for w in (when_of(r) for r in loose) if w]
            ahead = [w for w in whens if w > NOW]
            print(f"      {len(whens)} parseable, {len(ahead)} AHEAD of now")
            for w in sorted(set(whens))[-6:]:
                mark = "AHEAD" if w > NOW else "past "
                print(f"        {mark}  {w:%d.%m.%Y %H:%M}Z")
        return

    future, past, unparsed = [], [], 0
    by_key: dict[str, list] = {}
    for key, raw in pairs:
        when = when_of(raw)
        if when is None:
            unparsed += 1
            continue
        (future if when > NOW else past).append((key, raw, when))
        by_key.setdefault(key, []).append(when)

    print(f"    {len(pairs)} dated key(s): {len(future)} IN THE FUTURE, "
          f"{len(past)} past, {unparsed} unparseable")

    print("\n    which keys carry dates, and what they span:")
    for key, whens in sorted(by_key.items(),
                             key=lambda kv: -len(kv[1]))[:12]:
        ahead = sum(1 for w in whens if w > NOW)
        print(f"      {key:26} {len(whens):>3}x  "
              f"{min(whens):%d.%m %H:%M} .. {max(whens):%d.%m %H:%M}  "
              f"{ahead} ahead")

    if not future:
        print("\n    NOT ONE DATE IS AHEAD OF NOW. On this page these are")
        print("    file dates, not fixtures — a catalogue of what has been")
        print("    fought, which cannot feed a live board.")
        return

    print(f"\n    the {min(6, len(future))} nearest future date(s):")
    for key, raw, when in sorted(future, key=lambda t: t[2])[:6]:
        print(f"      {when:%d.%m %H:%M}Z  under {key!r}  raw {raw!r}")
        # And is there a title and a carrier in the same object?
        where = blob.find(raw)
        near = blob[max(0, where - 700): where + 700]
        title = re.search(
            r'"(?:title|name|eventName|label)"\s*:\s*"([^"]{5,70})"', near)
        carrier = re.search(
            r"FloGrappling|FloSports|UFC Fight Pass|YouTube|DAZN", near, re.I)
        print(f"        title beside it:   "
              f"{title.group(1)[:56] if title else 'NONE'}")
        print(f"        carrier beside it: "
              f"{carrier.group(0) if carrier else 'NONE'}")


def main() -> int:
    print("Are FloGrappling's dates fixtures, or when a video was filed?")
    print(f"Now is {NOW:%d.%m.%Y %H:%M}Z. Round two's samples — 12.09, 13.09,")
    print("15.09 — are ALL in the past, and 23:59:59 is nobody's kickoff.")
    print("If not one date is ahead, the page is a catalogue and the")
    print("answer is no, whatever else it carries.")

    for label, url in PAGES:
        heading(label.upper())
        read_one(label, url)

    heading("HOW TO READ THIS")
    print("  A fixture sits under a key like startDateTime or")
    print("  scheduledStart and is AHEAD of now, with a title and a")
    print("  carrier in the same object. A date under publishedAt or")
    print("  createdAt is a file date. Publishing the second as the first")
    print("  would put finished grappling under مباشر, which is the one")
    print("  thing this board refuses. Nothing is decided here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
