#!/usr/bin/env python3
"""Keep the Ain FM dashboard on YouTube Live when available, otherwise radio."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

RADIO_URL = "https://radio.ainfm.site/ainfm"
YOUTUBE_LIVE_URL = os.environ.get(
    "AIN_FM_YOUTUBE_LIVE_URL",
    "https://www.youtube.com/@AinFM_Jo/live",
)
DASHBOARDS = {
    "ai_sports_dashboard.m3u": "AinFMJordan",
    "ai_sports_dashboard_dubai.m3u": "AinFMJordanDubai",
}


def resolve_live_video() -> str | None:
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--quiet",
        "--no-warnings",
        "--no-playlist",
        "--skip-download",
        "--match-filter",
        "is_live",
        "--format",
        "best[acodec!=none][vcodec!=none]/best",
        "--get-url",
        YOUTUBE_LIVE_URL,
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"YouTube resolver unavailable: {exc}")
        return None

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        print("No current Ain FM YouTube live broadcast found.")
        if detail:
            print(detail[-1])
        return None

    for line in result.stdout.splitlines():
        url = line.strip()
        if url.startswith("http://") or url.startswith("https://"):
            return url
    print("YouTube resolver returned no playable URL.")
    return None


def update_dashboard(path: str, channel_id: str, source_url: str) -> bool:
    file_path = Path(path)
    lines = file_path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines[:-1]):
        if f'tvg-id="{channel_id}"' in line:
            if lines[index + 1] == source_url:
                return False
            lines[index + 1] = source_url
            file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True
    raise RuntimeError(f"Could not find {channel_id} in {path}")


def main() -> int:
    video_url = resolve_live_video()
    source_url = video_url or RADIO_URL
    mode = "YouTube Live" if video_url else "radio fallback"
    changed = []
    for path, channel_id in DASHBOARDS.items():
        if update_dashboard(path, channel_id, source_url):
            changed.append(path)
    print(f"Ain FM source: {mode}")
    print(f"Updated dashboards: {', '.join(changed) if changed else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
