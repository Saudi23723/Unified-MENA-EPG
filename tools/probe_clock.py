#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Temporary probe: what IS the time in a row on livefootballtv?

A guide built on this page is an hour ahead of the truth, checked against
a scores app for three Saudi league matches on the same day. The module
note says the printed clock runs exactly two hours ahead of the markup and
that the markup is therefore the UTC instant. One of those two statements
has stopped being true, and guessing which costs a day.

So: for a handful of rows, print the visible clock, the raw startDate
exactly as the markup carries it, and what each becomes. Delete once it
has answered.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from epg_lib import fetch, new_session

SOURCE = "https://www.livefootballtv.info/"
# Spanish class names all through the markup — local, visitante, canales.
MADRID = ZoneInfo("Europe/Madrid")


def main() -> int:
    soup = BeautifulSoup(fetch(new_session(), SOURCE).text, "html.parser")
    now = datetime.now(timezone.utc)
    print(f"now: {now:%Y-%m-%d %H:%M} UTC | "
          f"{now.astimezone(MADRID):%H:%M} Madrid "
          f"(offset {now.astimezone(MADRID).utcoffset()})")
    print()

    shown = 0
    for row in soup.find_all("tr"):
        local = row.find("td", class_="local")
        visit = row.find("td", class_="visitante")
        canales = row.find("td", class_="canales")
        hora = row.find("td", class_="hora")
        if not (local and visit and canales) or shown >= 12:
            continue
        meta = canales.find("meta", attrs={"itemprop": "startDate"})
        raw = (meta.get("content") if meta else "") or ""
        printed = re.sub(r"\s+", " ", hora.get_text(" ", strip=True)) if hora else "?"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            print(f"  unreadable startDate: {raw!r}")
            continue

        naive = parsed.tzinfo is None
        as_utc = (parsed.replace(tzinfo=timezone.utc) if naive
                  else parsed.astimezone(timezone.utc))
        name = f"{local.get_text(' ', strip=True)} - {visit.get_text(' ', strip=True)}"
        print(f"  printed {printed:>6} | raw {raw:<28} "
              f"| tz {'none' if naive else parsed.tzinfo} "
              f"| as UTC {as_utc:%H:%M} | Madrid {as_utc.astimezone(MADRID):%H:%M}"
              f" | {name[:34]}")
        shown += 1

    print("\nIf 'printed' equals 'Madrid', the markup is a true instant and the")
    print("guide's arithmetic is right. If 'printed' equals 'as UTC', the")
    print("markup is Madrid wall-clock wearing no timezone, and every time")
    print("this guide publishes is two hours late — or one, in winter.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
