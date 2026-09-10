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

CANDIDATES = (
    # azkar.ml, as the reader's screenshot documents it. The categories
    # are m=صباح e=مساء as=بعد الصلاة t=تسابيح bs=قبل النوم
    # wu=الاستيقاظ qd=أدعية قرآنية pd=أدعية الأنبياء
    ("azkar.ml · أذكار الصباح", "https://azkar.ml/zekr?m=true&json=true"),
    ("azkar.ml · أذكار المساء", "https://azkar.ml/zekr?e=true&json=true"),
    ("azkar.ml · أدعية الأنبياء", "https://azkar.ml/zekr?pd=true&json=true"),
    # Islamic-Api, whose data is served as files out of the repository.
    ("Islamic-Api · repo root",
     "https://api.github.com/repos/itsSamBz/Islamic-Api/contents"),
    ("Islamic-Api · raw azkar (guess a)",
     "https://raw.githubusercontent.com/itsSamBz/Islamic-Api/main/azkar.json"),
    ("Islamic-Api · raw azkar (guess b)",
     "https://raw.githubusercontent.com/itsSamBz/Islamic-Api/master/azkar.json"),
    # A third, widely mirrored, for comparison only.
    ("hisnmuslim · index",
     "https://www.hisnmuslim.com/api/ar/husn_ar.json"),
)

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
        payload = got.json()
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
    if isinstance(row, dict):
        carries = [k for k in row if k.lower() in ATTRIBUTION
                   or k in ATTRIBUTION]
        log(f"      a row's keys: {sorted(row)}")
        log(f"      attribution present: {carries or 'NONE'}")


def main() -> int:
    session = new_session()
    log("Does an adhkar row carry a COUNT and a SOURCE, or only text?")
    for name, url in CANDIDATES:
        ask(session, name, url)
    log("")
    log("A row with no count and no takhrij cannot feed this board.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
