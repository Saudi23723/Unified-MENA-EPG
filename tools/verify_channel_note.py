#!/usr/bin/env python3
"""Build Shahid for real and look for the sentence in the published file.

The last round passed every selftest and every runner check and the
feature still did nothing, because everything tested the code that was
written and nothing read what a viewer would see. So this reads the file.
"""
from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET

OUTPUT = "shahid_sports_epg.xml"


def main() -> int:
    run = subprocess.run([sys.executable, "-u", "update_shahid_sports_epg.py"],
                         capture_output=True, text=True, timeout=60 * 20)
    if run.returncode != 0:
        print((run.stderr or "")[-1500:])
        return 1

    notes, comps, fixtures = set(), set(), set()
    for programme in ET.parse(OUTPUT).getroot().iter("programme"):
        for line in (programme.findtext("desc") or "").splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            fixtures.add(line)
            if "يُبث أيضًا على:" in line:
                notes.add(line)
            if "—" in line:
                comps.add(line)

    print(f"-- {len(fixtures)} fixture lines in the descriptions")
    print(f"-- {len(comps)} name a competition")
    print(f"-- {len(notes)} name another channel")
    for line in sorted(notes)[:8]:
        print(f"     {line[:130]}")
    for line in sorted(comps)[:5]:
        print(f"   comp: {line[:130]}")

    if not fixtures:
        print("\nno fixture lines at all — cannot tell whether the note works")
        return 1
    print("\nread from the published file, not from the code")
    return 0


if __name__ == "__main__":
    sys.exit(main())
