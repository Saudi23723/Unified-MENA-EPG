#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Logos for the Alwan channels the guide had nothing for.

Asked for outright, from photos of the player: every Alwan channel that
is not already in this repository's guides gets a logo, in Alwan's own
style — the cluster of circles in the channel's colour and its name in
white beside it, on the black rounded tile logos/alwan.png wears.

The circles are Alwan's own, lifted from logos/alwan.png and recoloured
by brightness, so each logo keeps the shading the mark was drawn with.

    python make_alwan_channel_logos.py

Writes logos/alwan_<key>.png for every channel in alwan_channels_epg.
"""

from __future__ import annotations

import colorsys
import os

from PIL import Image, ImageDraw, ImageFont

from alwan_channels_epg import CHANNELS

SRC = "logos/alwan.png"
FONT = "fonts/Tajawal-ExtraBold.ttf"
FONT_TAG = "fonts/Tajawal-Bold.ttf"
LATIN = "fonts/Outfit-Bold.ttf"
SIZE = 512

# Where the circles sit on logos/alwan.png — everything green left of
# the lettering. Measured on the file: x 38-215, y 159-313.
CLUSTER = (30, 150, 205, 330)

RAINBOW = [(235, 64, 52), (245, 160, 30), (250, 215, 40), (90, 200, 80),
           (40, 150, 235), (150, 90, 220)]


def cluster() -> Image.Image:
    """Alwan's circles alone, as white with their own shading in alpha."""
    base = Image.open(SRC).convert("RGBA").crop(CLUSTER)
    out = Image.new("RGBA", base.size, (0, 0, 0, 0))
    src, dst = base.load(), out.load()
    for y in range(base.height):
        for x in range(base.width):
            r, g, b, a = src[x, y]
            # Every lit pixel: the palest circles are nearly white, and a
            # green-only test cut them off.
            # White lettering is grey; a circle, however pale, leans green.
            lit = max(r, g, b)
            if a and lit > 24 and g >= r + 6 and g >= b + 6:
                dst[x, y] = (r, g, b, min(255, lit * 2))
    return out


def recolour(dots: Image.Image, colour, *, rainbow=False) -> Image.Image:
    """The circles in another colour, each keeping its own lightness."""
    out = dots.copy()
    px = out.load()
    target_h, target_l, target_s = colorsys.rgb_to_hls(*[c / 255 for c in colour])
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if not a:
                continue
            _h, light, _s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
            hue = target_h
            if rainbow:
                pick = RAINBOW[(x * len(RAINBOW)) // out.width]
                hue = colorsys.rgb_to_hls(*[c / 255 for c in pick])[0]
            # Alwan's greens run from dark to pale; keep that spread
            # around the target's own lightness.
            lit = max(0.18, min(0.85, target_l + (light - 0.55) * 0.9))
            nr, ng, nb = colorsys.hls_to_rgb(hue, lit, max(target_s, 0.65))
            px[x, y] = (int(nr * 255), int(ng * 255), int(nb * 255), a)
    return out


def tile() -> Image.Image:
    """The black rounded tile logos/alwan.png stands on."""
    board = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(board).rounded_rectangle(
        [0, 0, SIZE - 1, SIZE - 1], radius=118, fill=(0, 0, 0, 255))
    return board


def fit(font_path: str, text: str, size: int, room: int, *, rtl=True):
    while size > 20:
        font = ImageFont.truetype(font_path, size)
        box = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox(
            (0, 0), text, font=font,
            direction="rtl" if rtl else None,
            language="ar" if rtl else None)
        if box[2] - box[0] <= room:
            return font
        size -= 2
    return ImageFont.truetype(font_path, size)


def draw(key: str, name_ar: str, colour, tag: str) -> Image.Image:
    board = tile()
    pen = ImageDraw.Draw(board)
    dots = recolour(cluster(), colour, rainbow=(key == "atfal"))
    board.alpha_composite(dots, (40, (SIZE - dots.height) // 2 + 10))

    # The name, right-aligned where Alwan's own lettering sits.
    right = SIZE - 44
    name_font = fit(FONT, name_ar, 118, right - 240)
    pen.text((right, SIZE // 2 + 58), name_ar, font=name_font,
             fill=(255, 255, 255, 255), anchor="rs",
             direction="rtl", language="ar")

    # The small tag above it, in the channel's colour: الوان, or the
    # sport the channel is named for.
    latin = tag.isascii()
    tag_font = (ImageFont.truetype(LATIN, 40) if latin
                else ImageFont.truetype(FONT_TAG, 42))
    box = pen.textbbox((0, 0), tag, font=tag_font,
                       direction=None if latin else "rtl",
                       language=None if latin else "ar")
    wide, high = box[2] - box[0] + 26, 50
    top = SIZE // 2 - 110
    pen.rounded_rectangle([right - wide, top, right, top + high],
                          radius=12, fill=tuple(colour) + (255,))
    pen.text((right - wide // 2, top + high // 2 + 2), tag, font=tag_font,
             fill=(255, 255, 255, 255), anchor="mm",
             direction=None if latin else "rtl",
             language=None if latin else "ar")
    return board


def main() -> None:
    os.makedirs("logos", exist_ok=True)
    for key, _names, name_ar, colour, tag in CHANNELS:
        path = f"logos/alwan_{key}.png"
        draw(key, name_ar, colour, tag).save(path, optimize=True)
        print(path)


if __name__ == "__main__":
    main()
