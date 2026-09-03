#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The SHAPE of the two pages worth reading, before a reader is written.

The first probe answered whether they are worth reading. They are:

    sportsmediawatch NFL   200 · 600 KB · 75 instants, every one 2026
                           "1:00 pm Atlanta Falcons vs Pittsburgh
                            Steelers   FOX, FOX One"
    boxingscene            200 · 502 KB · 91 instants, every one 2026
                           DAZN · ESPN · Sky · Amazon · TNT named

and one is not:

    mmatown                200 · NO machine-readable instant · NO channel

WHY THE NFL ONE MATTERS, measured on the board as it stands: seven NFL
games are on it and NOT ONE NAMES A CHANNEL. The league's own site is
read for them and gives a real UTC instant, which is why the games are
there at all — but the network that used to sit in its screen-reader text
is not reaching the row any more.

So this asks the ONE question a reader has to answer before it is
written: IS THE INSTANT ATTACHED TO THE ROW, or is it furniture
elsewhere on the page? Counting 75 instants proves nothing about which
game each belongs to — that is the mistake this repository has paid for
by name, and the reason "counting a word in a page is not finding a row"
is written on three other readers.

    sportsmediawatch is printed row by row: the date heading above it,
    the instants inside it, the clock it prints, and the networks.
    boxingscene renders in a browser, so its schedule is in the JSON its
    page ships rather than in any <tr>. The JSON is dumped by key so the
    path to a card can be read rather than guessed.
"""
from __future__ import annotations

import json
import re
import sys

sys.path.insert(0, ".")

import requests

BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                  " (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}

NFL = "https://www.sportsmediawatch.com/tv-schedules/nfl-tv-schedule/"
BOXING = "https://www.boxingscene.com/schedule"

TAGS = re.compile(r"<[^>]+>")
A_DATETIME = re.compile(r'datetime="([^"]+)"')
AN_ISO = re.compile(r"\b20\d\d-\d\d-\d\d(?:[T ]\d\d:\d\d)?")


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", TAGS.sub(" ", html)).strip()


def nfl(session) -> None:
    print(f"\n══ sportsmediawatch NFL\n   {NFL}")
    page = session.get(NFL, timeout=30, headers=BROWSER)
    print(f"   {page.status_code}  {len(page.content) // 1024} KB")
    if page.status_code != 200:
        return
    html = page.text

    # IS THE INSTANT INSIDE THE ROW? Printed per row, not counted.
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
    print(f"   {len(rows)} table row(s)")
    with_time = sum(1 for r in rows if A_DATETIME.search(r) or AN_ISO.search(r))
    print(f"   rows carrying an instant INSIDE them: {with_time}")

    # And what sits ABOVE each table, which is where a date heading would
    # be if the rows carry only a clock.
    print("\n   -- headings and the first rows under each --")
    for block in re.split(r"(?=<h[1-4][^>]*>)", html)[:14]:
        head = re.search(r"<h[1-4][^>]*>(.*?)</h[1-4]>", block, re.S)
        if not head:
            continue
        title = text_of(head.group(1))[:70]
        if not title:
            continue
        under = re.findall(r"<tr[^>]*>(.*?)</tr>", block, re.S)[:3]
        print(f"   [{title}]")
        for row in under:
            cells = [text_of(c) for c in
                     re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
            stamps = A_DATETIME.findall(row) + AN_ISO.findall(row)
            print(f"       cells={cells}")
            print(f"       instants in row={stamps}")

    print("\n   -- every distinct instant, in order --")
    seen = A_DATETIME.findall(html) + AN_ISO.findall(html)
    order, been = [], set()
    for one in seen:
        if one not in been:
            been.add(one)
            order.append(one)
    print(f"   {order[:24]}")


def dig(node, path="", out=None, depth=0):
    """Every list of dicts in the JSON, with the path that reaches it."""
    out = out if out is not None else []
    if depth > 8:
        return out
    if isinstance(node, dict):
        for key, value in node.items():
            dig(value, f"{path}.{key}", out, depth + 1)
    elif isinstance(node, list):
        if node and isinstance(node[0], dict):
            out.append((path, len(node), sorted(node[0])[:14]))
        for one in node[:2]:
            dig(one, f"{path}[]", out, depth + 1)
    return out


def boxing(session) -> None:
    print(f"\n══ boxingscene\n   {BOXING}")
    page = session.get(BOXING, timeout=30, headers=BROWSER)
    print(f"   {page.status_code}  {len(page.content) // 1024} KB")
    if page.status_code != 200:
        return
    html = page.text

    blobs = re.findall(
        r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    blobs += re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.S)
    print(f"   {len(blobs)} script payload(s)")

    parsed = 0
    for blob in blobs:
        text = blob.encode().decode("unicode_escape", "ignore")
        for found in re.finditer(r'(\{"[^\n]{200,})', text):
            chunk = found.group(1)
            for cut in range(len(chunk), 200, -1):
                try:
                    body = json.loads(chunk[:cut])
                except ValueError:
                    continue
                parsed += 1
                for path, count, keys in dig(body):
                    if count >= 3:
                        print(f"     {count:4} x {path}  keys={keys}")
                break
            if parsed >= 4:
                break
        if parsed >= 4:
            break
    if not parsed:
        print("   no JSON payload could be parsed — the schedule is not "
              "in what this fetch received")

    # And the plain text, so the shape of a card can be read even if the
    # JSON path is not obvious.
    flat = text_of(html)
    for word in ("DAZN", "ESPN", "Sky Sports", "Prime Video", "TNT"):
        at = flat.find(word)
        if at > 0:
            print(f"\n   around '{word}':\n     …{flat[max(0, at - 180):at + 90]}…")


def main() -> int:
    session = requests.Session()
    nfl(session)
    boxing(session)
    print("\nNothing is wired. This prints the SHAPE so a reader is "
          "written against what the page is, not what it looked like.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
