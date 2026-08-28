#!/usr/bin/env python3
"""Build the three guides that print a countdown and read the lines back.

The complaint was not that a number was wrong — it was that the line could
not be read: "بعد19 س و30 د" is nineteen minutes, or thirty minutes, or
thirty hours and nineteen minutes, depending on where the eye puts the
letters. So this checks the rendered guides, not the formatter: it builds
Shahid, Shasha and Thmanyah on a runner with the real sources, pulls every
countdown title out of the XML they publish, and fails if any of them still
carries a lone س / د / ي.
"""
from __future__ import annotations

import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

GUIDES = [
    ("Shahid", "update_shahid_sports_epg.py", "shahid_sports_epg.xml"),
    ("Shasha", "update_shasha_epg.py", "shasha_epg.xml"),
    ("Thmanyah", "update_thmanyah_epg.py", "thmanyah_epg.xml"),
]

# A unit that is one letter standing on its own — the shape that drifts.
ABBREVIATED = re.compile(r"(?:^|\s)[سدي](?:\s|$)")
COUNTDOWN = re.compile(r"·\s*بعد|بعد\s*\d")


def main() -> int:
    bad: list[str] = []
    for name, script, output in GUIDES:
        print(f"\n=== {name} ({script}) " + "=" * 40)
        run = subprocess.run([sys.executable, "-u", script],
                             capture_output=True, text=True, timeout=60 * 25)
        tail = (run.stdout or "").strip().splitlines()[-12:]
        print("\n".join(tail))
        if run.returncode != 0:
            print(f"!! {script} exited {run.returncode}")
            print((run.stderr or "")[-2000:])

        path = Path(output)
        if not path.exists():
            print(f"!! {output} was not written — cannot read the lines back")
            continue

        titles = [t.text or "" for t in ET.parse(path).getroot()
                  .iter("title")]
        counts = [t for t in titles if COUNTDOWN.search(t)]
        print(f"-- {len(counts)} countdown titles of {len(titles)}")
        for line in counts[:15]:
            print(f"   {line}")
        for line in counts:
            if ABBREVIATED.search(line):
                bad.append(f"{name}: {line}")

    print("\n" + "=" * 60)
    if bad:
        print(f"{len(bad)} countdown line(s) still abbreviate the unit:")
        for line in bad[:20]:
            print(f"  {line}")
        return 1
    print("every published countdown spells its unit out")
    return 0


if __name__ == "__main__":
    sys.exit(main())
