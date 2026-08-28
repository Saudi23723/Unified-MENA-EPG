#!/usr/bin/env python3
"""Build Shahid and Shasha for real and report what the guide now looks like.

Two things are being checked, and neither can be checked offline: that no
channel name reaches a team's place, and that a long wait is one row
instead of a ticker. So this builds both guides against the live sources
on a runner, then reads the published XML back.
"""
from __future__ import annotations

import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import update_shahid_sports_epg as SH  # noqa: E402
from epg_lib import COUNTDOWN_HORIZON, is_channel_name  # noqa: E402

GUIDES = [
    ("Shahid", "update_shahid_sports_epg.py", "shahid_sports_epg.xml"),
    ("Shasha", "update_shasha_epg.py", "shasha_epg.xml"),
]

WAIT = re.compile(r"المباراة القادمة")
COUNTS = re.compile(r"·\s*بعد\s")


def when(raw: str) -> datetime:
    return datetime.strptime(raw[:14], "%Y%m%d%H%M%S")


def main() -> int:
    bad: list[str] = []
    for name, script, output in GUIDES:
        print(f"\n=== {name} " + "=" * 50)
        run = subprocess.run([sys.executable, "-u", script],
                             capture_output=True, text=True, timeout=60 * 20)
        if run.returncode != 0:
            print(f"!! {script} exited {run.returncode}")
            print((run.stderr or "")[-1500:])
            bad.append(f"{name}: build failed")
            continue

        rows = sorted(ET.parse(output).getroot().iter("programme"),
                      key=lambda p: p.get("start"))
        titles = [(p.findtext("title") or "").strip() for p in rows]
        waits = [t for t in titles if WAIT.search(t)]
        counts = [t for t in titles if COUNTS.search(t) and not WAIT.search(t)]
        real = [t for t in titles
                if not WAIT.search(t) and not COUNTS.search(t)]
        print(f"-- {len(rows)} rows: {len(real)} broadcasts, "
              f"{len(waits)} wait rows, {len(counts)} countdown rows")

        # No channel name may sit where a team belongs.
        for title in real:
            for side in re.split(r"\s\+\s|\s-\s", re.sub(r"‎?• Live.*", "", title)):
                side = side.strip()
                if side and is_channel_name(side):
                    bad.append(f"{name}: channel as a team -> {title}")

        # No slot may carry the same match twice under two spellings.
        for title in titles:
            body = re.sub(r"^⏰\s*", "", title)
            body = re.sub(r"·.*$", "", body).strip()
            parts = [p.strip() for p in body.split(" + ") if p.strip()]
            if len(parts) < 2:
                continue
            seen = {}
            for part in parts:
                key = SH.title_signature(part)
                if key in seen:
                    bad.append(f"{name}: one match twice -> "
                               f"{seen[key]} / {part}")
                seen[key] = part

        # No countdown row may sit further out than the horizon.
        kickoffs = sorted({when(p.get("start")) for p, t in zip(rows, titles)
                           if not WAIT.search(t) and not COUNTS.search(t)})
        for p, t in zip(rows, titles):
            if not COUNTS.search(t) or WAIT.search(t):
                continue
            start = when(p.get("start"))
            nxt = next((k for k in kickoffs if k >= start), None)
            if nxt and nxt - start > COUNTDOWN_HORIZON + timedelta(minutes=1):
                bad.append(f"{name}: countdown {nxt - start} out -> {t[:60]}")

        print("   first 18 rows as a viewer scrolls them:")
        for p, t in list(zip(rows, titles))[:18]:
            a, b = when(p.get("start")), when(p.get("stop"))
            print(f"     {a:%m-%d %H:%M}-{b:%H:%M} {t[:78]}")

    print("\n" + "=" * 60)
    if bad:
        print(f"{len(bad)} problem(s):")
        for line in bad[:15]:
            print(f"  {line}")
        return 1
    print("no channel sits where a team belongs, and no countdown runs long")
    return 0


if __name__ == "__main__":
    sys.exit(main())
