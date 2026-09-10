#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What do the azkar sources actually return, and is anything sourced?

MEASUREMENT ONLY. The reader named two: azkar.ml's API and the
Islamic-Api repository on GitHub. The board's rule has not changed —
nothing is drawn that did not arrive from a source — so the question
here is the same one that caught the hadith out: does a row carry its
own attribution, or only its text?

For adhkar the attribution that matters is the takhrij: which
collection the dhikr comes from, and how many times it is said. A
count and a source are what turn a line of text into something a
board may show.

Prints SHAPE AND KEYS, never the text itself.
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, ".")
from epg_lib import log, new_session, warn                     # noqa: E402

# WHAT THE FIRST PASS SETTLED, so it is not asked again:
#   azkar.ml            DOES NOT RESOLVE. A free .ml domain that has
#                       been reclaimed; the API in the screenshot is
#                       gone, whatever the documentation still says.
#   Islamic-Api         the repository answers, but the file names
#                       guessed for it did not. So the listing is read
#                       and the files are found in it — the same
#                       lesson the tafsir slugs taught.
#   hisnmuslim          answers, and is JSON behind a BOM. The parse
#                       failed on the byte order mark, not the content.
CANDIDATES = (
    # FOUND BY READING THE LISTING, not by guessing at it.
    ("Islamic-Api · various_adkar",
     "https://raw.githubusercontent.com/itsSamBz/Islamic-Api/main"
     "/various_adkar.json"),
    ("Islamic-Api · sunnah_data",
     "https://raw.githubusercontent.com/itsSamBz/Islamic-Api/main"
     "/sunnah_data.json"),
    # hisnmuslim's index gave ID/TITLE/TEXT/AUDIO_URL — TEXT there looks
    # like a link into the category rather than the dhikr itself, so one
    # category is followed to see what a real row carries.
    ("hisnmuslim · الفهرس",
     "https://www.hisnmuslim.com/api/ar/husn_ar.json"),
    ("hisnmuslim · باب واحد",
     "https://www.hisnmuslim.com/api/ar/27.json"),
    # zakroon, as the reader sent it. A GitHub Pages site is a
    # repository underneath, so the data is looked for there.
    ("zakroon · the page itself", "https://osamayy.github.io/zakroon/"),
)

ZAKROON = "https://api.github.com/repos/osamayy/zakroon/contents{path}"

# The repository whose file names have to be read rather than guessed.
LISTING = "https://api.github.com/repos/itsSamBz/Islamic-Api/contents{path}"

# What turns a line of text into something this board may draw.
ATTRIBUTION = ("count", "repeat", "times", "التكرار", "تكرار", "العدد",
               "reference", "source", "المصدر", "التخريج", "takhrij",
               "narrator", "الراوي", "hadith", "الفضل", "benefit",
               "description", "category", "title", "id", "zekr", "content")


def walk(value, depth=0):
    if isinstance(value, dict):
        return {k: walk(v, depth + 1) if depth < 2 else type(v).__name__
                for k, v in list(value.items())[:10]}
    if isinstance(value, list):
        return [walk(value[0], depth + 1)] if value else []
    return type(value).__name__


def ask(session, name, url) -> None:
    try:
        got = session.get(url, timeout=30,
                          headers={"User-Agent": "Mozilla/5.0"})
    except Exception as exc:                                   # noqa: BLE001
        warn(f"{name}: unreachable ({exc})")
        return
    size = len(got.content)
    if got.status_code != 200:
        warn(f"{name}: HTTP {got.status_code} ({size:,} bytes)")
        return
    try:
        # A BOM IS NOT A PARSE ERROR. hisnmuslim serves valid JSON
        # behind a byte order mark and .json() choked on it, which
        # read as "not json" when the content was fine all along.
        payload = json.loads(got.content.decode("utf-8-sig"))
    except (ValueError, json.JSONDecodeError):
        log(f"  {name}: {size:,} bytes, NOT json "
            f"(starts {got.text[:40]!r})")
        return

    log(f"  {name}")
    log(f"      {size:,} bytes, top-level {type(payload).__name__}")
    if isinstance(payload, dict):
        log(f"      top-level keys: {sorted(payload)[:12]}")
    log(f"      shape: {walk(payload)}")

    # find the first row-looking mapping anywhere shallow
    row = None
    if isinstance(payload, list) and payload:
        row = payload[0]
    elif isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                row = value[0]
                break
        if row is None:
            row = payload
    if isinstance(row, dict) and not any(
            isinstance(v, (list, dict)) for v in row.values()):
        pass
    elif isinstance(row, dict):
        for value in row.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                row = value[0]
                break
    if isinstance(row, dict):
        carries = [k for k in row if k.lower() in ATTRIBUTION
                   or k in ATTRIBUTION]
        log(f"      a row's keys: {sorted(row)}")
        log(f"      attribution present: {carries or 'NONE'}")


def walk_the_repo(session, path="", depth=0, listing=None) -> None:
    """Read the file names out of the listing instead of inventing them."""
    if depth > 2:
        return
    try:
        got = session.get((listing or LISTING).format(path=path),
                          timeout=30)
        rows = got.json() if got.status_code == 200 else []
    except Exception as exc:                                   # noqa: BLE001
        warn(f"listing {path or '/'}: {exc}")
        return
    if not isinstance(rows, list):
        return
    for row in rows:
        kind, name = row.get("type"), row.get("name", "")
        if kind == "dir":
            log(f"  {'  ' * depth}[{name}]")
            walk_the_repo(session, f"{path}/{name}", depth + 1,
                          listing)
        elif name.lower().endswith((".json", ".js")):
            log(f"  {'  ' * depth}{name}  ({row.get('size', 0):,} bytes)")
            log(f"  {'  ' * depth}   {row.get('download_url')}")


def main() -> int:
    session = new_session()
    log("WHAT IS IN zakroon — names read, not guessed")
    walk_the_repo(session, listing=ZAKROON)
    log("")
    log("Does an adhkar row carry a COUNT and a SOURCE, or only text?")
    for name, url in CANDIDATES:
        ask(session, name, url)
    log("")
    log("A row with no count and no takhrij cannot feed this board.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
