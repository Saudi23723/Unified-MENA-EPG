#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round four: the Sport TV EPG itself, field by field.

Round three found it. A channel's own live page carries a 164KB
<script type="application/json"> whose commonest keys are a broadcast
schedule written in Portuguese, 85 of each — one per programme:

    data 87 · descricao 85 · modalidade 85 · duracao 85 · canal 85
    tipoEmissao 85 · evento 85 · id_epg 85 · nomeModalidade 85 · epg 8

data is the date, descricao the description, modalidade and
nomeModalidade the sport, duracao the length, canal the channel,
evento the event — and tipoEmissao is the BROADCAST TYPE, which is the
one field "make sure only live event/match not programs or recorded"
turns on. epg appearing 8 times is the eight channels.

So the shape is known and the values are not. This prints whole
programme objects and every distinct value of the fields that decide
what is kept: tipoEmissao, canal, modalidade. Nothing is written
against this until those are read.

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
CHANNELS = [("727", "SPORT.TV1"), ("728", "SPORT.TV2"), ("5406", "SPORT.TV4"),
            ("7133", "SPORT.TV+")]


def biggest_json(text: str) -> str:
    best = ""
    for m in re.finditer(
            r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
            text, re.S):
        if len(m.group(1)) > len(best):
            best = m.group(1)
    return best


def programmes(data):
    """Every dict in the blob that looks like one EPG row."""
    out = []
    def walk(node, depth=0):
        if depth > 14:
            return
        if isinstance(node, dict):
            if "tipoEmissao" in node or "id_epg" in node:
                out.append(node)
            for v in node.values():
                walk(v, depth + 1)
        elif isinstance(node, list):
            for v in node:
                walk(v, depth + 1)
    walk(data)
    return out


def main() -> int:
    session = requests.Session(); session.headers.update(HEAD)
    every = []
    for cid, name in CHANNELS:
        url = f"{BASE}/live/canal/{cid}/{name}"
        try:
            r = session.get(url, timeout=TIMEOUT)
        except Exception as exc:                               # noqa: BLE001
            print(f"  {name}: {type(exc).__name__}")
            continue
        raw = biggest_json(r.text)
        try:
            data = json.loads(raw)
        except Exception:                                      # noqa: BLE001
            print(f"  {name}: blob is not JSON ({len(raw)} bytes)")
            continue
        rows = programmes(data)
        print(f"  {name:<12} blob {len(raw):>7}  programme rows {len(rows)}")
        every += rows

    print()
    print("=" * 74)
    print(f"{len(every)} programme row(s) in all — three printed whole")
    print("=" * 74)
    for row in every[:3]:
        print(json.dumps(row, ensure_ascii=False, indent=2)[:1400])
        print("   ---")

    print()
    print("=" * 74)
    print("THE FIELDS THAT DECIDE WHAT IS KEPT")
    print("=" * 74)
    for field in ("tipoEmissao", "canal", "modalidade", "nomeModalidade",
                  "data", "duracao", "evento", "grandeEvento", "exclusivo"):
        seen = Counter()
        for row in every:
            v = row.get(field)
            seen[json.dumps(v, ensure_ascii=False)[:60]
                 if isinstance(v, (dict, list)) else str(v)] += 1
        print(f"\n  {field}  ({len(seen)} distinct)")
        for value, n in seen.most_common(12):
            print(f"      {n:>4}x  {value[:88]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
