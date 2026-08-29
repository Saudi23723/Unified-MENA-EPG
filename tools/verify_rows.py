#!/usr/bin/env python3
"""Build the guides and count what a viewer actually scrolls past."""
from __future__ import annotations

import re
import subprocess
import sys
import xml.etree.ElementTree as ET

GUIDES = [("Shahid", "update_shahid_sports_epg.py", "shahid_sports_epg.xml", 261),
          ("Shasha", "update_shasha_epg.py", "shasha_epg.xml", 550)]


def main() -> int:
    for name, script, output, before in GUIDES:
        run = subprocess.run([sys.executable, "-u", script],
                             capture_output=True, text=True, timeout=60 * 20)
        if run.returncode != 0:
            print(f"!! {script} exited {run.returncode}")
            print((run.stderr or "")[-1200:])
            return 1
        rows = sorted(ET.parse(output).getroot().iter("programme"),
                      key=lambda p: p.get("start"))
        titles = [(p.findtext("title") or "").strip() for p in rows]
        wait = [t for t in titles if "المباراة القادمة" in t]
        cnt = [t for t in titles if "بعد" in t and "المباراة القادمة" not in t]
        real = len(titles) - len(wait) - len(cnt)
        filler = round(100 * (len(titles) - real) / max(len(titles), 1))
        print(f"\n{name}: {before} rows -> {len(titles)}   "
              f"{real} matches + {len(wait)} wait + {len(cnt)} countdown "
              f"({filler}% filler)")
        for p, t in list(zip(rows, titles))[:6]:
            a = p.get("start")[:12]
            print(f"   {a}  {t[:96]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
