#!/usr/bin/env python3
"""Fail if any generated dashboard stream can skip, stall, or corrupt a page."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import match_screen_video as video  # noqa: E402

BAD_DECODE = (
    "corrupt input packet",
    "packet corrupt",
    "non monotonically increasing",
)


def fail(message: str) -> None:
    print(f"FAIL {message}")
    raise SystemExit(1)


def probe(path: str) -> tuple[float, float, int]:
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=start_time,duration,has_b_frames",
         "-of", "json", path],
        check=False, capture_output=True, text=True,
    )
    if done.returncode != 0:
        fail(f"{path}: ffprobe failed: {done.stderr.strip()[:240]}")
    try:
        stream = json.loads(done.stdout)["streams"][0]
        return (float(stream["start_time"]), float(stream["duration"]),
                int(stream["has_b_frames"]))
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        fail(f"{path}: incomplete ffprobe result")


def audit(name: str) -> None:
    prefix, playlist_name, _stamp, hold = video.SCREENS[name]
    video.HOLD = hold
    manifest = os.path.join(video.OUT_DIR, playlist_name)
    if not os.path.exists(manifest):
        fail(f"{name}: missing {manifest}")
    text = open(manifest, encoding="utf-8").read()
    if "#EXT-X-ENDLIST" in text or "#EXT-X-PLAYLIST-TYPE:" in text:
        fail(f"{name}: playlist is finite and can run dry")
    if "#EXT-X-START:TIME-OFFSET=0.0,PRECISE=YES" not in text:
        fail(f"{name}: valid page-zero start directive is missing")
    if "#EXT-X-START:TIME-OFFSET:" in text:
        fail(f"{name}: malformed start directive is present")

    boards = video.whole_days(prefix, video.boards(prefix))
    expected = [os.path.basename(video.segment_of(board)) for board in boards]
    if not expected:
        fail(f"{name}: no pages were generated")
    refs = re.findall(r"(?m)^([^#\s]+\.ts)$", text)
    reel = len(expected)
    if refs[:reel] != expected:
        fail(f"{name}: first reel is not page 0..{reel - 1} in order")
    if len(refs) <= reel:
        fail(f"{name}: playlist contains only one reel and will buffer at its end")
    if refs[-video.JOIN_BACK] != expected[0]:
        fail(f"{name}: normal live join point is not page zero")

    found = re.search(r"(?m)^#EXT-X-MEDIA-SEQUENCE:(\d+)$", text)
    if not found or int(found.group(1)) % reel:
        fail(f"{name}: media sequence is not aligned to page zero")
    durations = [float(value) for value in re.findall(r"#EXTINF:([\d.]+)", text)]
    if sum(durations) < video.WINDOW_MINUTES * 60 - max(durations):
        fail(f"{name}: live runway is shorter than the configured window")

    missing = [ref for ref in set(refs)
               if not os.path.exists(os.path.join(video.OUT_DIR, ref))]
    if missing:
        fail(f"{name}: playlist names missing segments: {missing[:4]}")

    timing = [probe(os.path.join(video.OUT_DIR, segment))
              for segment in expected]
    for page, (start, duration, bframes) in enumerate(timing):
        if bframes:
            fail(f"{name}: page {page} still contains B-frames")
        if page:
            boundary = timing[page - 1][0] + timing[page - 1][1]
            gap = start - boundary
            # AAC packets make the measured reel step 32–56 ms longer than
            # the video itself. That tiny positive padding is intentional;
            # overlap or a human-visible gap is not.
            if gap < -0.002 or gap > 0.100:
                fail(f"{name}: timestamp gap/overlap before page {page}: "
                     f"{gap:.3f}s")

    # Decode one complete reel plus one page. The wrap is a declared
    # discontinuity; ordinary page boundaries must produce no corrupt packet
    # and no non-monotonic DTS warning.
    frames = max(1, math.ceil((sum(durations[:reel]) + hold / 2) * video.FPS))
    done = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "warning", "-live_start_index", "0",
         "-i", manifest, "-map", "0:v:0", "-frames:v", str(frames),
         "-f", "null", "-"],
        check=False, capture_output=True, text=True, timeout=90,
    )
    lowered = done.stderr.lower()
    bad = [needle for needle in BAD_DECODE if needle in lowered]
    if done.returncode != 0 or bad:
        fail(f"{name}: HLS decode failed ({done.returncode}, {bad}): "
             f"{done.stderr.strip()[:300]}")
    print(f"ok {name}: {reel} page(s), {len(refs)} live entries, no skip/corruption")


def main() -> int:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        fail("ffmpeg and ffprobe are required")
    for name in video.SCREENS:
        audit(name)
    print(f"all {len(video.SCREENS)} dashboard streams passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
