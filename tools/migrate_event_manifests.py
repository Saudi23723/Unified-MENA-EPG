#!/usr/bin/env python3
"""Convert generated dashboard manifests from frozen VOD to refreshable EVENT."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = {
    "screen.m3u8", "sports.m3u8", "sporttv.m3u8", "dubai_sporttv.m3u8",
    "news.m3u8", "weather.m3u8", "dubai_screen.m3u8", "dubai_sports.m3u8",
    "dubai_news.m3u8", "dubai_weather.m3u8", "prayer.m3u8",
    "ball_sports.m3u8", "dubai_ball_sports.m3u8", "hoops_gridiron.m3u8",
    "dubai_hoops_gridiron.m3u8", "f1.m3u8", "dubai_f1.m3u8",
    "turkish_ppv.m3u8", "dubai_turkish_ppv.m3u8",
}

for name in sorted(NAMES):
    path = ROOT / "stream" / name
    lines = path.read_text(encoding="utf-8").splitlines()
    converted = []
    for line in lines:
        if line == "#EXT-X-PLAYLIST-TYPE:VOD":
            converted.append("#EXT-X-PLAYLIST-TYPE:EVENT")
        elif line != "#EXT-X-ENDLIST":
            converted.append(line)
    path.write_text("\n".join(converted) + "\n", encoding="utf-8")
    print(path)

print(f"converted {len(NAMES)} generated dashboard manifests")
