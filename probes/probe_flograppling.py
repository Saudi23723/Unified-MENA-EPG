#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print, do not guess: where FloGrappling keeps its schedule, and its shape.

Round one found the one source tonight that passed the test every other
candidate failed:

    flograppling   200   473,678B   205 clocks  64.4% on :00   541x ADCC
                   carriers: FLOGRAPPLING×303, FLOSPORTS×33, YOUTUBE×3

A real schedule, not a template — 64% on the hour, so there are 19:30s
and 21:45s in it — and it names the carrier, which is the rule that
turned down sporteventz, bjjheroes and smoothcomp.

But /events answered 406, so the path was a guess and the guess was
wrong. THIS DOES NOT GUESS AGAIN. It asks the home page for its own
links and follows the ones that look like a schedule, which is how the
right path is found rather than invented.

THEN THE SHAPE. A page is only worth a reader if a repeating block
carries three things together: an instant, a title, and a carrier.
livesoccertv gave a dv epoch in milliseconds; Sport TV gave a duracao;
DAZN gave Start and End as ISO. Whatever this one gives, it is printed
as it is found — including any JSON the page ships inline, because a
FloSports site is a React app and its schedule usually arrives as a
__NEXT_DATA__ or apollo state blob rather than as table rows.

AND THE INSTANT IS ALWAYS SUSPECT. Every source tonight has had a clock
that disagreed with its own epoch somewhere: livesoccertv's data-ko was
four hours off dv. So any date-looking field found here is printed
RAW, beside its parsed value, so the two can be compared rather than
assumed equal.

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

HOME = "https://www.flograppling.com/"
LIKE_A_BROWSER = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/128.0.0.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "en-GB,en;q=0.9",
}
SECONDS = 15

A_SCHEDULE_LINK = re.compile(
    r"/(events?|schedule|calendar|live|upcoming|watch)\b", re.I)
SAYS_ADCC = re.compile(r"\bADCC\b", re.I)
AN_ISO = re.compile(
    r"\b(20\d\d-[01]\d-[0-3]\dT[0-2]\d:[0-5]\d(?::[0-5]\d)?"
    r"(?:Z|[+-][0-2]\d:?[0-5]\d)?)\b")
AN_EPOCH = re.compile(r"\b(1[7-9]\d{11})\b")


def get(label: str, url: str):
    try:
        got = requests.get(url, headers=LIKE_A_BROWSER, timeout=SECONDS)
    except Exception as exc:                              # noqa: BLE001
        print(f"  {label:34} FAILED {type(exc).__name__}")
        return None
    body = got.text or ""
    print(f"  {label:34} {got.status_code}  {len(body):>9,}B  "
          f"{len(SAYS_ADCC.findall(body)):>4}x ADCC  "
          f"{len(AN_ISO.findall(body)):>4} ISO  "
          f"{len(AN_EPOCH.findall(body)):>4} epoch")
    return got


def heading(text: str) -> None:
    print(f"\n{text}\n{'─' * len(text)}", flush=True)


def its_own_links(body: str) -> list[str]:
    """The schedule-looking paths the site links to itself."""
    soup = BeautifulSoup(body, "html.parser")
    seen: dict[str, int] = {}
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.startswith("/"):
            href = "https://www.flograppling.com" + href
        if not href.startswith("https://www.flograppling.com"):
            continue
        if A_SCHEDULE_LINK.search(href):
            seen[href.split("?")[0]] = seen.get(href.split("?")[0], 0) + 1
    return [url for url, _ in sorted(seen.items(), key=lambda kv: -kv[1])]


def the_inline_json(body: str) -> None:
    """A React site ships its data as a blob; find it and describe it."""
    soup = BeautifulSoup(body, "html.parser")
    best, where = "", ""
    for tag in soup.find_all("script"):
        text = tag.string or tag.get_text() or ""
        if len(text) > len(best) and ("{" in text):
            best, where = text, (tag.get("id") or tag.get("type") or "inline")
    print(f"    biggest inline script: {where!r}, {len(best):,} chars")
    if len(best) < 200:
        print("    nothing substantial inline — the schedule is fetched")
        print("    by the browser afterwards, so an API call is the way in")
        return
    print(f"    it says ADCC {len(SAYS_ADCC.findall(best))} time(s)")
    isos = AN_ISO.findall(best)
    epochs = AN_EPOCH.findall(best)
    print(f"    date-looking values: {len(isos)} ISO, {len(epochs)} epoch-ms")
    for raw in isos[:5]:
        try:
            when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            when = when.astimezone(timezone.utc)
            print(f"      raw {raw:28} -> {when:%d.%m %H:%M}Z")
        except ValueError:
            print(f"      raw {raw:28} -> unparseable")
    for raw in epochs[:3]:
        when = datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc)
        print(f"      raw {raw:28} -> {when:%d.%m %H:%M}Z")
    # And whether a title sits near a date, which is what a row is.
    for found in re.finditer(r'"(?:title|name|eventName)"\s*:\s*"([^"]{6,70})"',
                             best):
        near = best[max(0, found.start() - 400): found.end() + 400]
        if AN_ISO.search(near) or AN_EPOCH.search(near):
            print(f"      a title beside a date: {found.group(1)[:60]!r}")
            break


def flosports_api() -> None:
    """FloSports sites share one API host; ask it the obvious things."""
    for label, url in (
        ("api/events upcoming",
         "https://api.flosports.tv/api/experiences/tv/events"
         "?site_id=25&limit=20&upcoming=true"),
        ("api/nodes live",
         "https://api.flosports.tv/api/nodes?site_id=25&limit=20"),
        ("live-events",
         "https://api.flosports.tv/api/live-events?site_id=25&limit=20"),
    ):
        got = get(label, url)
        if got is None or got.status_code != 200:
            continue
        try:
            blob = got.json()
        except ValueError:
            continue
        if isinstance(blob, dict):
            print(f"      keys: {list(blob)[:12]}")
        elif isinstance(blob, list) and blob:
            print(f"      {len(blob)} item(s); first keys: "
                  f"{list(blob[0])[:12] if isinstance(blob[0], dict) else '—'}")


def main() -> int:
    print("FloGrappling passed round one. Where is its schedule, and what")
    print("shape is a row? The path is asked for, not guessed — /events")
    print("was a guess and answered 406.\n")
    print(f"  {'page':34} {'code':>4}  {'size':>9}  ADCC   ISO  epoch")

    heading("1. THE HOME PAGE, AND THE LINKS IT OFFERS")
    home = get("home", HOME)
    if home is None or home.status_code != 200:
        print("\n  the home page did not answer — nothing more to ask")
        return 0

    links = its_own_links(home.text)
    print(f"\n    schedule-looking links it offers: {len(links)}")
    for url in links[:12]:
        print(f"      {url}")

    heading("2. FOLLOWING THEM")
    best_body, best_url = "", ""
    for url in links[:6]:
        got = get(url.replace("https://www.flograppling.com", "")[:34] or "/",
                  url)
        if got is not None and got.status_code == 200 and len(got.text) > len(best_body):
            best_body, best_url = got.text, url

    heading("3. WHAT THE HOME PAGE ITSELF CARRIES")
    print("  It said ADCC 541 times in round one, so the data may already")
    print("  be on it rather than behind a link.\n")
    the_inline_json(home.text)

    if best_body and best_url:
        heading(f"4. AND THE BIGGEST PAGE IT LINKED TO")
        print(f"  {best_url}\n")
        the_inline_json(best_body)

    heading("5. THE FLOSPORTS API, WHICH ALL THEIR SITES SHARE")
    flosports_api()

    heading("HOW TO READ THIS")
    print("  A row needs three things together: an instant, a title, and a")
    print("  carrier. 'a title beside a date' above is the one line that")
    print("  says a reader is possible. Raw values are printed next to")
    print("  parsed ones because every source tonight had a clock that")
    print("  disagreed with its own epoch. Nothing is decided here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
