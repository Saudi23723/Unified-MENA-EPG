#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fonts, colours and layout metrics for the info-channel renderer.

Everything here is resolution independent: metrics are expressed for a
1280x720 canvas and scaled by `Theme.s` so the same layout renders cleanly
at 720p, 1080p or on a small box that can only afford 854x480.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache

from PIL import ImageFont, features

# --- Arabic shaping ---------------------------------------------------------
# Two different worlds, and getting this wrong is what makes Arabic come out
# either disconnected or mirrored:
#
#   * Pillow built with Raqm (HarfBuzz + FriBidi) already shapes and
#     bidi-reorders text itself. Pre-shaping here would reorder it a second
#     time and render every Arabic line backwards, so shape() must be a no-op.
#   * Pillow without Raqm draws code points verbatim. Then we have to reshape
#     and reorder ourselves, using the BASIC layout engine.
HAS_RAQM = bool(features.check("raqm"))

if not HAS_RAQM:
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        _SHAPING = True
    except Exception:  # noqa: BLE001 - optional dependency
        _SHAPING = False
else:
    _SHAPING = False

ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")


def has_arabic(text: str) -> bool:
    return bool(ARABIC_RE.search(text or ""))


def direction_for(text: str) -> str | None:
    """Base paragraph direction to hand Pillow. Only meaningful with Raqm."""
    if HAS_RAQM and has_arabic(text):
        return "rtl"
    return None


def shape(text: str) -> str:
    """Make a string safe to draw. A no-op when Raqm does the work for us."""
    if not text or not _SHAPING or not has_arabic(text):
        return text
    try:
        return get_display(arabic_reshaper.reshape(text))
    except Exception:  # noqa: BLE001 - never let text break a frame
        return text


# --- Font discovery ---------------------------------------------------------
# Two families: one that covers Arabic, one for Latin/digits. Both lists are
# ordered by preference and the first file that exists wins.
ARABIC_FONTS = {
    "bold": [
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoKufiArabic-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ],
    "regular": [
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ],
}

LATIN_FONTS = {
    "bold": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ],
    "regular": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ],
}


def _first_existing(paths: list[str]) -> str | None:
    for p in paths:
        if os.path.exists(p):
            return p
    return None


@lru_cache(maxsize=256)
def font(size: int, *, bold: bool = False, arabic: bool = False) -> ImageFont.FreeTypeFont:
    """Load (and cache) a font face at `size`, picking an Arabic-capable file
    when the text needs one."""
    weight = "bold" if bold else "regular"
    table = ARABIC_FONTS if arabic else LATIN_FONTS
    path = _first_existing(table[weight]) or _first_existing(
        (LATIN_FONTS if arabic else ARABIC_FONTS)[weight]
    )
    if path is None:
        return ImageFont.load_default()
    engine = ImageFont.Layout.RAQM if HAS_RAQM else ImageFont.Layout.BASIC
    return ImageFont.truetype(path, size, layout_engine=engine)


def font_for(text: str, size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Pick the right face for a specific string."""
    return font(size, bold=bold, arabic=has_arabic(text))


# --- Palette ----------------------------------------------------------------
# Tuned for a TV screen viewed from a distance: deep navy ground, high
# contrast text, one warm accent for LIVE and one cool accent for UPCOMING.
class Palette:
    bg_top = (9, 13, 26)
    bg_bottom = (19, 26, 48)
    glow = (46, 88, 170)

    card = (255, 255, 255, 12)
    card_alt = (255, 255, 255, 20)
    card_live = (255, 59, 71, 26)
    card_border = (255, 255, 255, 26)

    text = (255, 255, 255)
    text_dim = (150, 163, 196)
    text_faint = (98, 111, 143)

    live = (255, 71, 82)
    live_soft = (255, 138, 145)
    next_ = (60, 214, 244)
    next_soft = (150, 233, 250)
    accent = (139, 122, 255)
    ok = (74, 222, 128)

    track = (255, 255, 255, 30)


# Channel-chip colours. Known broadcasters get their own hue; anything else
# is assigned deterministically from the palette so a channel always keeps
# the same colour between frames and restarts.
BRAND_COLOURS = [
    (139, 122, 255),
    (60, 214, 244),
    (255, 138, 76),
    (74, 222, 128),
    (244, 114, 182),
    (250, 204, 21),
    (94, 165, 255),
    (45, 212, 191),
]

BRAND_OVERRIDES = {
    "bein": (125, 60, 240),
    "ssport": (232, 60, 120),
    "tabii": (0, 179, 152),
    "thmanyah": (0, 168, 132),
    "shahid": (0, 200, 120),
    "alwan": (46, 124, 246),
    "onsport": (232, 78, 40),
    "jordan": (16, 185, 129),
    "roya": (236, 72, 60),
    "shasha": (255, 160, 0),
    "fajer": (255, 120, 40),
}


def channel_colour(channel_id: str, display: str = "") -> tuple[int, int, int]:
    key = re.sub(r"[^a-z0-9]", "", f"{channel_id}{display}".lower())
    for name, colour in BRAND_OVERRIDES.items():
        if name in key:
            return colour
    return BRAND_COLOURS[sum(key.encode()) % len(BRAND_COLOURS)]


class Theme:
    """Layout metrics, scaled from the 1280x720 reference design."""

    def __init__(self, width: int, height: int) -> None:
        self.w = width
        self.h = height
        self.s = width / 1280.0

    def px(self, v: float) -> int:
        return max(1, int(round(v * self.s)))

    # -- structure
    @property
    def pad(self) -> int:
        return self.px(28)

    @property
    def header_h(self) -> int:
        return self.px(92)

    @property
    def footer_h(self) -> int:
        return self.px(52)

    @property
    def gutter(self) -> int:
        return self.px(22)

    @property
    def radius(self) -> int:
        return self.px(12)

    # -- type scale
    @property
    def fs_clock(self) -> int:
        return self.px(46)

    @property
    def fs_brand(self) -> int:
        return self.px(30)

    @property
    def fs_section(self) -> int:
        return self.px(23)

    @property
    def fs_row(self) -> int:
        return self.px(19)

    @property
    def fs_meta(self) -> int:
        return self.px(15)

    @property
    def fs_small(self) -> int:
        return self.px(13)

    @property
    def fs_time(self) -> int:
        return self.px(24)
