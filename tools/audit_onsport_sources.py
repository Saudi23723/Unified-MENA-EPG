#!/usr/bin/env python3
"""Print exactly what parse_lftv_home computes for the rows it throws away.

55 ON Sport rows are dropped every run because the markup time and the
displayed time "disagree by more than six hours", leaving the guide 91%
stand-in. Across the page as a whole the two differ by a flat +2h, which
is a timezone and not a disagreement — so the rows being dropped must
differ some other way. This prints the three numbers the check compares
instead of reasoning about them.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bs4 import BeautifulSoup  # noqa: E402
from datetime import datetime  # noqa: E402
import update_onsport_epg as ON  # noqa: E402


def main() -> int:
    print(f"SOURCE_TZ = {ON.SOURCE_TZ}   tolerance = {ON.LFTV_META_TOLERANCE}\n")
    soup = BeautifulSoup(ON.fetch_text(ON.LIVEFOOTBALLTV_HOME), "html.parser")

    shown = 0
    for row in soup.select("tr"):
        canales = row.select_one("td.canales")
        hora = row.select_one("td.hora")
        if not canales or not hora:
            continue
        labels = [li.get("title") or li.get_text(" ", strip=True)
                  for li in canales.select("ul.listaCanales li")]
        mine = [x for x in labels if ON.onsport_channel_from_label(x or "")]
        if not mine:
            continue
        m = re.search(r"(\d{1,2}):(\d{2})", hora.get_text(" ", strip=True))
        meta = canales.find("meta", attrs={"itemprop": "startDate"})
        if not m or not meta or not meta.get("content"):
            continue

        marked = datetime.fromisoformat(meta["content"])
        if marked.tzinfo is None:
            marked = marked.replace(tzinfo=ON.UTC)
        day = marked.astimezone(ON.SOURCE_TZ).date()
        start_local = datetime(day.year, day.month, day.day,
                               int(m.group(1)), int(m.group(2)),
                               tzinfo=ON.SOURCE_TZ)
        start_utc = start_local.astimezone(ON.UTC)
        delta = start_utc - marked.astimezone(ON.UTC)
        verdict = "DROPPED" if abs(delta) > ON.LFTV_META_TOLERANCE else "kept"

        shown += 1
        print(f"  cell {m.group(0)}  meta {meta['content']:22} "
              f"-> derived {start_utc:%Y-%m-%d %H:%M}Z  "
              f"delta {delta}  {verdict}   {mine[0][:22]}")
        if shown >= 20:
            break

    if not shown:
        print("  no ON Sport row found on the page at all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
