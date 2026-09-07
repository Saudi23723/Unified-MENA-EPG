#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Publish Ain FM as a direct stream playlist.

Ain FM is an endless Icecast-style MP3 stream. It cannot be used as an HLS
media segment: HLS players wait for a segment to finish before advancing, but
this source never finishes. That makes the old wrapper buffer indefinitely.

The repository is static hosting, so it cannot transcode the live source into
fresh HLS segments. A standard M3U playlist lets the player open the source
immediately and keep its own live buffer instead.
"""
from __future__ import annotations

import os
import sys

from epg_lib import log, warn

MARK = os.path.join("logos", "ain_fm.png")
OUT_DIR = "stream"
MASTER = os.path.join(OUT_DIR, "ain_fm.m3u8")
AUDIO = os.path.join(OUT_DIR, "ain_fm_audio.m3u8")
LIVE = "https://radio.ainfm.site/ainfm"
LOGO = "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/logos/ain_fm_radio_dim.png"


def write(path: str, lines: list[str]) -> None:
  with open(path, "w", encoding="utf-8", newline="\n") as out:
      out.write("\n".join(lines) + "\n")


def playlist() -> list[str]:
  return [
      "#EXTM3U",
      (
          '#EXTINF:-1 tvg-id="ain-fm" tvg-name="Ain FM" '
          f'tvg-logo="{LOGO}" group-title="Radio",Ain FM'
      ),
      LIVE,
  ]


def build() -> int:
  if not os.path.exists(MARK):
      warn(f"{MARK} is not here — Ain FM has no station logo")
      return 1

  os.makedirs(OUT_DIR, exist_ok=True)
  lines = playlist()
  write(MASTER, lines)
  # Keep the legacy audio path usable for clients that already reference it.
  write(AUDIO, lines)
  log(f"{MASTER}: direct Ain FM stream (no fake HLS segment)")
  return 0


if __name__ == "__main__":
  sys.exit(build())
