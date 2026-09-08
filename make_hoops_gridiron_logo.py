#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fit channel 9's mark — the NFL/NBA shield — to the size the others are.

The artwork was supplied rather than drawn (the WNBA/MLB plaques beside
it are polygons in make_ball_sports_logo.py). It is kept in logos/src so
this is reproducible: the shield that ships is not a file somebody once
dropped in and nobody can rebuild, it is this source trimmed and centred
by the script below.

The source already carries a clean alpha channel — a cut-out edge with
its own anti-aliasing — so nothing here removes a background. Doing that
by colour would have taken the football's laces and stripes with it,
which are the same white as the paper behind the shield.

    python make_hoops_gridiron_logo.py

Writes logos/hoops_gridiron.png — one 512x512 transparent PNG.
"""
from __future__ import annotations

from PIL import Image

SRC = "logos/src/hoops_gridiron_shield.png"
OUT = "logos/hoops_gridiron.png"
SIZE = 512
MARGIN = 16          # the shield is its own silhouette, so it needs little


def build() -> int:
    art = Image.open(SRC).convert("RGBA")
    box = art.getbbox()
    if not box:
        raise SystemExit(f"{SRC} is empty — nothing opaque to fit")
    art = art.crop(box)

    room = SIZE - MARGIN * 2
    scale = min(room / art.width, room / art.height)
    art = art.resize((max(1, round(art.width * scale)),
                      max(1, round(art.height * scale))), Image.LANCZOS)

    out = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    out.alpha_composite(art, ((SIZE - art.width) // 2,
                              (SIZE - art.height) // 2))
    out.save(OUT)
    print(f"wrote {OUT} — shield {art.width}x{art.height} on {SIZE}x{SIZE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
