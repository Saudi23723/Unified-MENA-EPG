#!/usr/bin/env python3
"""Build Shahid and Shasha for real and check no match is printed twice.

The duplicate only appears when two sources disagree on script, so it
cannot be reproduced offline — it needs the live pages.
"""
from __future__ import annotations

import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import update_shahid_sports_epg as SH  # noqa: E402
from epg_lib import same_fixture  # noqa: E402

GUIDES = [("Shahid", "update_shahid_sports_epg.py", "shahid_sports_epg.xml"),
          ("Shasha", "update_shasha_epg.py", "shasha_epg.xml")]


def main() -> int:
    bad: list[str] = []
    for name, script, output in GUIDES:
        print(f"\n=== {name} " + "=" * 46)
        run = subprocess.run([sys.executable, "-u", script],
                             capture_output=True, text=True, timeout=60 * 20)
        if run.returncode != 0:
            print((run.stderr or "")[-1200:])
            bad.append(f"{name}: build failed")
            continue

        rows = sorted(ET.parse(output).getroot().iter("programme"),
                      key=lambda p: p.get("start"))
        titles = [(p.findtext("title") or "").strip() for p in rows]

        widest, worst = 0, ""
        for title in titles:
            body = re.sub(r"·.*$", "", re.sub(r"^⏰\s*", "", title)).strip()
            body = re.sub(r"‎?• Live.*", "", body).strip()
            parts = [p.strip() for p in body.split(" + ") if p.strip()]
            if len(parts) > widest:
                widest, worst = len(parts), body
            for i, a in enumerate(parts):
                for b in parts[i + 1:]:
                    if same_fixture(a, b):
                        bad.append(f"{name}: two scripts, one match -> "
                                   f"{a} / {b}")
                    if SH.title_signature(a) == SH.title_signature(b):
                        bad.append(f"{name}: two spellings, one match -> "
                                   f"{a} / {b}")
        print(f"-- {len(rows)} rows; widest slot carries {widest} matches")
        if worst:
            print(f"   {worst[:200]}")

    print("\n" + "=" * 60)
    if bad:
        print(f"{len(bad)} duplicate(s):")
        for line in dict.fromkeys(bad):
            print(f"  {line}")
        return 1
    print("no slot names the same match twice, in either script")
    return 0


if __name__ == "__main__":
    sys.exit(main())
