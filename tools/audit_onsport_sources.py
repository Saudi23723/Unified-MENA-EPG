#!/usr/bin/env python3
"""Rebuild the two guides that were showing blank rows, then check them.

Also settles what the ON Sport ceiling failure actually is: the tolerance
check in parse_lftv_home runs BEFORE the ON Sport channel filter, so its
"55 rows dropped" counts rows for every channel on the page, not ON Sport
rows. An independent pass that applies no tolerance at all finds how many
ON Sport rows the page carries, which is the number that matters.
"""
from __future__ import annotations

import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bs4 import BeautifulSoup  # noqa: E402
import update_onsport_epg as ON  # noqa: E402

NOW = datetime.now(timezone.utc)


def stamp(raw):
    raw = (raw or "").strip()
    try:
        return datetime.strptime(raw, "%Y%m%d%H%M%S %z")
    except ValueError:
        try:
            return datetime.strptime(raw[:14], "%Y%m%d%H%M%S").replace(
                tzinfo=timezone.utc)
        except ValueError:
            return None


def blank_channels(path):
    root = ET.parse(path).getroot()
    spans = {}
    for p in root.findall("programme"):
        a, b = stamp(p.get("start")), stamp(p.get("stop"))
        if a and b:
            spans.setdefault(p.get("channel"), []).append((a, b))
    return [c.get("id") for c in root.findall("channel")
            if not any(a <= NOW < b for a, b in spans.get(c.get("id"), []))]


def main() -> int:
    print("=" * 66)
    print("ON SPORT — how many rows does the page carry for it, tolerance aside")
    soup = BeautifulSoup(ON.fetch_text(ON.LIVEFOOTBALLTV_HOME), "html.parser")
    rows = found = 0
    for row in soup.find_all("tr"):
        canales = row.find("td", class_="canales")
        hora = row.find("td", class_="hora")
        if not (canales and hora):
            continue
        rows += 1
        for li in canales.select("ul.listaCanales li"):
            label = (li.get("title") or li.get_text(" ", strip=True) or "")
            if ON.onsport_channel_from_label(label.strip()):
                found += 1
                break
    print(f"  {rows} fixture rows on the page, {found} of them name ON Sport")
    print("  (the tolerance check runs before the ON Sport filter, so its")
    print("   'dropped' count is about every channel, not this guide)")

    for script, path in (("update_bein_sports_turkey_epg.py",
                          "bein_sports_turkey_epg.xml"),
                         ("update_roya_jordan_epg.py",
                          "roya_jordan_epg.xml")):
        print("\n" + "=" * 66)
        print(f"{path}")
        before = blank_channels(path) if Path(path).exists() else []
        print(f"  blank right now, before rebuilding: {before}")
        run = subprocess.run([sys.executable, "-u", script],
                             capture_output=True, text=True, timeout=60 * 20)
        if run.returncode != 0:
            print(f"  !! {script} exited {run.returncode}")
            print((run.stderr or "")[-1200:])
            continue
        after = blank_channels(path)
        print(f"  blank right now, after  rebuilding: {after}")
        if after:
            print("  STILL BLANK — the fix did not take")
            return 1
    print("\nno channel shows a blank row")
    return 0


if __name__ == "__main__":
    sys.exit(main())
