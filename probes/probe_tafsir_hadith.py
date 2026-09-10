#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Which tafsir and hadith sources exist, and do they carry attribution?

MEASUREMENT ONLY. Nothing here is wired to a channel and nothing here
decides anything: it asks each candidate, prints what came back, and
answers the one question that settles whether a source is usable at
all —

    does every row carry its own reference, and for a hadith its
    takhrij and its grading, as the SOURCE states them?

A source that hands back text with no reference cannot feed this
channel, however good the text is, because the board's rule is that
nothing is drawn unattributed. So the report below is deliberately
about SHAPE and KEYS, not about words: it prints how many rows, which
fields each row has, and one field-name listing per source. It does not
print the text itself — the question is whether attribution exists, and
a probe that dumps scripture answers a question nobody asked.
"""
from __future__ import annotations

import json
import sys

# The convention the other probes here already use: a probe lives in
# probes/ and the library it reads lives at the root, so the root goes
# on the path before it is imported.
sys.path.insert(0, ".")
from epg_lib import log, new_session, warn                     # noqa: E402

# Every candidate is a complete, keyless, single-file edition where one
# exists — the same preference the Quran fetch already makes, because a
# file downloaded once cannot rate-limit a build and cannot go dark
# between two passes of it.
TAFSIR = (
    ("quran-api · ara-tafsir-ibn-kathir",
     "https://cdn.jsdelivr.net/gh/fawazahmed0/quran-api@1"
     "/editions/ara-tafsiribnkatheer.json"),
    ("quran-api · ara-tafsir-muyassar",
     "https://cdn.jsdelivr.net/gh/fawazahmed0/quran-api@1"
     "/editions/ara-tafsirmuyassar.json"),
    ("quran-api · ara-tafsir-jalalayn",
     "https://cdn.jsdelivr.net/gh/fawazahmed0/quran-api@1"
     "/editions/ara-tafsiraljalalayn.json"),
    ("quran-api · the edition index",
     "https://cdn.jsdelivr.net/gh/fawazahmed0/quran-api@1"
     "/editions.json"),
    ("spa5k tafsir_api · the tafsir index",
     "https://cdn.jsdelivr.net/gh/spa5k/tafsir_api@main"
     "/tafsir/editions.json"),
    ("quran-tafseer · the tafsir list",
     "http://api.quran-tafseer.com/tafseer/"),
)

HADITH = (
    ("hadith-api · the edition index",
     "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1"
     "/editions.json"),
    ("hadith-api · bukhari (arabic)",
     "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1"
     "/editions/ara-bukhari.json"),
    ("hadith-api · muslim (arabic)",
     "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1"
     "/editions/ara-muslim.json"),
    ("hadith-api · nawawi's forty (arabic)",
     "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1"
     "/editions/ara-nawawi.json"),
    ("gading.dev · the book list",
     "https://api.hadith.gading.dev/books"),
)

# The words a source uses when it states a hadith's grading or its
# takhrij. Their PRESENCE is what is being measured — never their value
# printed back, which would be quoting the source at length for no gain.
ATTRIBUTION = ("grade", "grades", "daraja", "درجة", "hukm", "حكم",
               "takhrij", "تخريج", "reference", "book", "chapter",
               "number", "hadithnumber", "arabicnumber", "sura",
               "chapter", "verse", "ayah")


def shape_of(value, depth=0):
    """The keys, not the contents."""
    if isinstance(value, dict):
        return {key: shape_of(val, depth + 1) if depth < 2 else type(val).__name__
                for key, val in list(value.items())[:12]}
    if isinstance(value, list):
        return [shape_of(value[0], depth + 1)] if value else []
    return type(value).__name__


def first_row(payload):
    """One row out of whatever container this source uses."""
    if isinstance(payload, list) and payload:
        return payload[0]
    if isinstance(payload, dict):
        for key in ("hadiths", "quran", "tafsir", "data", "ayahs",
                    "editions"):
            inner = payload.get(key)
            if isinstance(inner, list) and inner:
                return inner[0]
            if isinstance(inner, dict) and inner:
                return next(iter(inner.values()))
        return payload
    return None


def ask(session, name, url) -> None:
    try:
        got = session.get(url, timeout=45)
    except Exception as exc:                                   # noqa: BLE001
        warn(f"{name}: unreachable ({exc})")
        return
    if got.status_code != 200:
        warn(f"{name}: HTTP {got.status_code}")
        return
    size = len(got.content)
    try:
        payload = got.json()
    except (ValueError, json.JSONDecodeError):
        log(f"  {name}: {size:,} bytes, NOT json")
        return

    rows = None
    if isinstance(payload, dict):
        for key in ("hadiths", "quran", "tafsir", "ayahs", "editions"):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
    if rows is None and isinstance(payload, list):
        rows = payload

    row = first_row(payload)
    keys = sorted(row) if isinstance(row, dict) else "(not a mapping)"
    carries = ([k for k in row if k.lower() in ATTRIBUTION]
               if isinstance(row, dict) else [])

    log(f"  {name}")
    log(f"      {size:,} bytes"
        + (f", {len(rows):,} row(s)" if rows is not None else ""))
    log(f"      a row's keys: {keys}")
    log(f"      attribution fields present: {carries or 'NONE'}")
    if isinstance(payload, dict) and rows is None:
        log(f"      top-level shape: {shape_of(payload)}")


def main() -> int:
    session = new_session()
    log("TAFSIR — is there a named work, quoted per ayah, with the ayah "
        "named on the row?")
    for name, url in TAFSIR:
        ask(session, name, url)
    log("")
    log("HADITH — is there a number, a book, and a GRADING the source "
        "states itself?")
    for name, url in HADITH:
        ask(session, name, url)
    log("")
    log("A source with no attribution field cannot feed this channel, "
        "however good its text is.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
