#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Why does the Alkass guide repeat channels, and is there a better source?

The published guide shows Alkass 1 and 4 with byte-identical schedules,
3 and 6 at 91 per cent, 2 and 7 at 87. That is exactly the pattern
alkass_epg.py's own docstring names as the broken one it avoids — "the
collapsible cg1..cg8 list repeats whole channels (1=4=8, 2=5=7, 3=6)".
So either the page changed under the parser, or the grid it reads has
gone the same way.

Only the page settles it, and the page answers from Doha and nowhere
else. This dumps what the parser sees: how many logos, how many tables,
the order they pair in, and the opening rows of each table so identical
ones are visible as identical.

It also asks whether tomorrow exists — the guide publishes one day, and
the generator does request ?day=next — and what other sources carry
Alkass at all, since a second opinion is worth having either way.

Reads only; writes nothing.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import alkass_epg as g  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/127.0 Safari/537.36")

OTHERS = [
    ("epgshare AR1", "https://epgshare01.online/epgshare01/epg_ripper_AR1.xml.gz"),
    ("epgshare AE1", "https://epgshare01.online/epgshare01/epg_ripper_AE1.xml.gz"),
    ("open-epg qatar1", "https://www.open-epg.com/files/qatar1.xml"),
]


def dump_page(session, label: str, url: str) -> str:
    print(f"\n--- {label}: {url} ---")
    try:
        page = session.get(url, timeout=45, headers={"User-Agent": UA}).text
    except Exception as exc:
        print(f"    ERROR {type(exc).__name__}: {exc}")
        return ""
    print(f"    {len(page)} chars, sha1 {hashlib.sha1(page.encode()).hexdigest()[:12]}")

    cut = page.find(g.GRID_START)
    print(f"    '{g.GRID_START}' found at {cut}")
    if cut < 0:
        return page
    grid = page[cut:]
    column = g.COLUMN_RE.findall(grid)
    tables = g.CHANNEL_TABLE_RE.findall(grid)
    print(f"    logos in column : {column}")
    print(f"    schedule tables : {len(tables)}")
    if len(column) != len(tables):
        print("    *** MISMATCH — the parser refuses to read this ***")

    for name, body in zip(column, tables):
        rows = [(m.group("start"), m.group("stop"), g.clean(m.group("title")))
                for m in g.PROGRAMME_RE.finditer(body)]
        head = " | ".join(f"{s} {t[:22]}" for s, _e, t in rows[:3])
        print(f"      logo={name:<7} rows={len(rows):>3}  {head}")

    # Identical tables are the whole question, so say it outright.
    seen: dict[str, list[str]] = defaultdict(list)
    for name, body in zip(column, tables):
        rows = tuple((m.group("start"), g.clean(m.group("title")))
                     for m in g.PROGRAMME_RE.finditer(body))
        seen[hashlib.sha1(str(rows).encode()).hexdigest()].append(name)
    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    if dupes:
        print("    IDENTICAL TABLES ON THE PAGE ITSELF:")
        for names in dupes.values():
            print(f"      {names}")
    else:
        print("    every table on the page is distinct")
    return page


def main() -> int:
    session = requests.Session()
    print("=" * 72)
    print("1. What alkass.net actually serves")
    print("=" * 72)
    today = dump_page(session, "today", g.BASE)
    tomorrow = dump_page(session, "?day=next", g.BASE + "?day=next")
    if today and tomorrow:
        same = hashlib.sha1(today.encode()).digest() == \
            hashlib.sha1(tomorrow.encode()).digest()
        print(f"\n  today and ?day=next are the same page: {same}")

    print("\n" + "=" * 72)
    print("2. Who else carries Alkass")
    print("=" * 72)
    for label, url in OTHERS:
        print(f"\n[{label}]")
        try:
            resp = session.get(url, timeout=60, headers={"User-Agent": UA})
        except Exception as exc:
            print(f"    ERROR {type(exc).__name__}")
            continue
        print(f"    http={resp.status_code} bytes={len(resp.content)}")
        if resp.status_code != 200 or not resp.content:
            continue
        raw = resp.content
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        try:
            root = ET.parse(io.BytesIO(raw)).getroot()
        except Exception:
            print("    not XMLTV")
            continue
        names = {c.get("id"): " / ".join(d.text or ""
                                        for d in c.findall("display-name"))
                 for c in root.findall("channel")}
        counts: dict[str, int] = defaultdict(int)
        days: dict[str, set] = defaultdict(set)
        for p in root.findall("programme"):
            counts[p.get("channel")] += 1
            days[p.get("channel")].add(p.get("start")[:8])
        hits = [c for c in names
                if re.search(r"alkass|kass|الكأس", c + names[c], re.I)]
        if not hits:
            print("    no Alkass channel")
            continue
        for c in sorted(hits):
            print(f"      {c:<30} {counts[c]:>4} progs over "
                  f"{len(days[c])} day(s)  | {names[c][:30]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
