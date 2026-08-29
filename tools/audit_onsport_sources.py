#!/usr/bin/env python3
"""Why does livefootballtv's front page yield zero ON Sport rows?

The guide is 91% stand-in, above its ceiling. The parser reports 55 rows
dropped because the markup date and the displayed time disagree by more
than LFTV_META_TOLERANCE. Dropping every row is not a tolerance working,
it is a tolerance misfiring — so this prints the two values side by side
and the actual offset between them.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bs4 import BeautifulSoup  # noqa: E402
import update_onsport_epg as ON  # noqa: E402


def main() -> int:
    html = ON.fetch_text(ON.LIVEFOOTBALLTV_HOME)
    soup = BeautifulSoup(html, "html.parser")
    print(f"page: {len(html)} bytes, tolerance = {ON.LFTV_META_TOLERANCE}\n")

    deltas: Counter = Counter()
    shown = 0
    for row in soup.select("tr"):
        hora = row.select_one("td.hora")
        meta = row.select_one("meta[itemprop=startDate]")
        if not hora or not meta:
            continue
        text = hora.get_text(" ", strip=True)
        raw = meta.get("content") or ""
        m = re.search(r"(\d{2}):(\d{2})", text)
        if not m or not raw:
            continue
        try:
            when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        cell_minutes = int(m.group(1)) * 60 + int(m.group(2))
        meta_minutes = when.hour * 60 + when.minute
        diff = (cell_minutes - meta_minutes) % (24 * 60)
        deltas[diff] += 1
        if shown < 12:
            shown += 1
            print(f"  cell {m.group(0)}   meta {raw:28} "
                  f"offset {diff // 60:+d}h{diff % 60:02d}")

    print(f"\noffset between the displayed time and the markup, "
          f"across {sum(deltas.values())} rows:")
    for diff, n in deltas.most_common(8):
        print(f"   {diff // 60:+3d}h{diff % 60:02d}   {n:4} rows")
    print("\nA single offset shared by every row is a timezone, not bad data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
