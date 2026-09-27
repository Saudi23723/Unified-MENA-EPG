#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round five: resolve the blob's indices into real values.

Round four found the schedule and then found that none of its fields
hold a value. tipoEmissao is 2021, data is 2198, evento is 2027 — small
integers, every one of them, and 336 rows all saying exclusivo=2021.

They are POSITIONS. The blob is a flat reference table — one list, and
every field an index into it — which is how Nuxt serialises a store
without repeating a string that appears four hundred times. A value is
read by following the index, and a value that is itself a dict of
indices is followed again.

So this resolves them and prints what the fields actually say: the
broadcast type that decides live from recorded, the channel, the sport,
the date and the event name. Nothing is written against Sport TV until
these are read in their own words.

It commits nothing and publishes nothing.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter

import requests

TIMEOUT = 30
HEAD = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8"}
BASE = "https://www.sporttv.pt"


def biggest_json(text: str) -> str:
    best = ""
    for m in re.finditer(
            r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
            text, re.S):
        if len(m.group(1)) > len(best):
            best = m.group(1)
    return best


def main() -> int:
    session = requests.Session(); session.headers.update(HEAD)
    r = session.get(f"{BASE}/live/canal/727/SPORT.TV1", timeout=TIMEOUT)
    table = json.loads(biggest_json(r.text))
    print(f"  flat table of {len(table)} entries")

    def at(index, depth=0):
        """Follow an index into the table, and keep following."""
        if depth > 6 or not isinstance(index, int):
            return index
        if not (0 <= index < len(table)):
            return index
        value = table[index]
        if isinstance(value, dict):
            return {k: at(v, depth + 1) for k, v in value.items()}
        if isinstance(value, list):
            return [at(v, depth + 1) for v in value[:6]]
        return value

    rows = [n for n in table if isinstance(n, dict) and "tipoEmissao" in n]
    print(f"  {len(rows)} programme row(s)\n")

    print("=" * 74)
    print("TWO ROWS, RESOLVED")
    print("=" * 74)
    for row in rows[:2]:
        print(json.dumps({k: at(v) for k, v in row.items()},
                         ensure_ascii=False, indent=2)[:1200])
        print("  ---")

    print()
    print("=" * 74)
    print("WHAT THE DECIDING FIELDS ACTUALLY SAY")
    print("=" * 74)
    for field in ("tipoEmissao", "canal", "nomeModalidade", "modalidade",
                  "data", "evento", "descricao", "duracao", "grandeEvento"):
        seen = Counter()
        for row in rows:
            v = at(row.get(field))
            seen[json.dumps(v, ensure_ascii=False)[:70]
                 if isinstance(v, (dict, list)) else str(v)] += 1
        print(f"\n  {field}  ({len(seen)} distinct)")
        for value, n in seen.most_common(10):
            print(f"      {n:>4}x  {value[:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
