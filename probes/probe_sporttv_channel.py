#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round three: a Sport TV channel's own page, and the 762KB blob.

Round two gave two things worth following.

THE SITE NAMES ITS OWN CHANNELS, in live-sitemap.xml, and there are
EIGHT of them rather than the six asked for:

    727/SPORT.TV1   728/SPORT.TV2   729/SPORT.TV3   5406/SPORT.TV4
    5422/SPORT.TV5  7133/SPORT.TV+  7577/SPORT.TV6  7600/SPORT.TV7

So the ids are published rather than guessed, and 6 and 7 exist to be
asked about rather than assumed.

AND A COMPETITION PAGE CARRIES A 762KB <script type="application/json">
holding 6719 entries — a serialised store, which is a far better thing
to read than Vue markup that has already been flattened to pipes. This
walks that blob properly: what shape it is, whether it is a flat
devalue table, and which of its strings look like clocks, ISO instants,
competition names and channel ids.

/jogos itself answers 200 with ZERO clocks and ZERO events — an empty
shell — so the listing has to come from somewhere else, and the
per-channel live pages are the first candidate.

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

CHANNELS = [("727", "SPORT.TV1"), ("728", "SPORT.TV2"), ("729", "SPORT.TV3"),
            ("5406", "SPORT.TV4"), ("5422", "SPORT.TV5"), ("7133", "SPORT.TV+"),
            ("7577", "SPORT.TV6"), ("7600", "SPORT.TV7")]


def get(session, url):
    try:
        return session.get(url, timeout=TIMEOUT, allow_redirects=True)
    except Exception as exc:                                   # noqa: BLE001
        print(f"      {url[:88]} -> {type(exc).__name__}")
        return None


def biggest_json(text: str):
    """The largest <script type="application/json"> body on the page."""
    best = ""
    for m in re.finditer(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
                         text, re.S):
        if len(m.group(1)) > len(best):
            best = m.group(1)
    return best


def walk_blob(raw: str) -> None:
    print(f"      blob {len(raw)} bytes")
    try:
        data = json.loads(raw)
    except Exception as exc:                                   # noqa: BLE001
        print(f"      not JSON: {exc}")
        return
    print(f"      top-level {type(data).__name__} "
          f"len={len(data) if hasattr(data,'__len__') else '?'}")

    # Collect every string in the structure and classify it.
    strings: list[str] = []
    def collect(node, depth=0):
        if depth > 12:
            return
        if isinstance(node, str):
            strings.append(node)
        elif isinstance(node, list):
            for v in node:
                collect(v, depth + 1)
        elif isinstance(node, dict):
            for k, v in node.items():
                strings.append(str(k))
                collect(v, depth + 1)
    collect(data)
    print(f"      {len(strings)} string(s) inside")

    pats = {
        "ISO instants  ": r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}",
        "hh:mm clocks  ": r"^(?:[01]?\d|2[0-3]):[0-5]\d$",
        "mg: ids       ": r"^mg:[a-z]+:",
        "channel ids   ": r"^(?:727|728|729|5406|5422|7133|7577|7600)$",
        "sporttv logos ": r"sporttv-.*\.svg",
    }
    for label, pat in pats.items():
        hits = [s for s in strings if re.search(pat, s)]
        print(f"      {label} {len(hits):<6} e.g. {hits[:4]}")

    # the most common KEYS, which is what names the fields
    keys = Counter()
    def keyscan(node, depth=0):
        if depth > 12: return
        if isinstance(node, dict):
            keys.update(node.keys())
            for v in node.values(): keyscan(v, depth + 1)
        elif isinstance(node, list):
            for v in node: keyscan(v, depth + 1)
    keyscan(data)
    if keys:
        print(f"      commonest keys: {keys.most_common(30)}")


def main() -> int:
    session = requests.Session(); session.headers.update(HEAD)

    print("=" * 74)
    print("EACH CHANNEL'S OWN LIVE PAGE")
    print("=" * 74)
    for cid, name in CHANNELS:
        url = f"{BASE}/live/canal/{cid}/{name}"
        r = get(session, url)
        if r is None:
            continue
        ok = r.status_code == 200 and "html" in r.headers.get("content-type", "")
        clocks = len(re.findall(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b", r.text)) if ok else 0
        evts = len(set(re.findall(r"mg:sportevent:[A-Za-z0-9]+", r.text))) if ok else 0
        blob = biggest_json(r.text) if ok else ""
        print(f"  {name:<12} {r.status_code}  {len(r.text):>8} bytes  "
              f"clocks {clocks:<5} events {evts:<5} blob {len(blob)}")

    print()
    print("=" * 74)
    print("THE BLOB ON SPORT.TV1's PAGE, WALKED")
    print("=" * 74)
    r = get(session, f"{BASE}/live/canal/727/SPORT.TV1")
    if r is not None and r.status_code == 200:
        walk_blob(biggest_json(r.text))

    print()
    print("=" * 74)
    print("AND THE BLOB ON THE COMPETITION PAGE, WALKED")
    print("=" * 74)
    r = get(session, f"{BASE}/jogos/competicao/mg:competition:14y9s73xvl9b"
                     f"/liga-portugal-betclic")
    if r is not None and r.status_code == 200:
        walk_blob(biggest_json(r.text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
