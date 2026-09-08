#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Draw channel 8's mark — the WNBA and MLB badges, from scratch.

The four dashboard guides carry drawn emblems (make_today_matches_logo.py):
a ball, a trophy, a wave, a sun. This channel is not a subject, it is two
named leagues, and a viewer scrolling two hundred rows finds it by the
marks those leagues are known by rather than by a picture of a bat.

So both are drawn here rather than fetched: the silhouettes are polygons
in this file, at the leagues' own colours, and nothing is downloaded at
build time from a service that can stop answering.

    python make_ball_sports_logo.py

Writes logos/ball_sports.png — one 512x512 transparent PNG, rounded like
the tiles beside it.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

SCALE = 4                      # draw large, shrink at the end
S = 512 * SCALE
RADIUS = 118 * SCALE
WHITE = (255, 255, 255, 255)

# The leagues' own colours.
MLB_BLUE = (0, 45, 114, 255)
MLB_RED = (213, 0, 50, 255)
WNBA_ORANGE = (247, 105, 2, 255)
WNBA_BLUE = (11, 36, 100, 255)

TILE_TOP = (12, 22, 44, 255)
TILE_BOTTOM = (4, 7, 14, 255)

EN_FONT = "fonts/Tajawal-Medium.ttf"
OUT = "logos/ball_sports.png"


def tile() -> Image.Image:
    """The rounded app tile the other marks sit on, in this one's colours."""
    grad = Image.new("RGBA", (1, S))
    for y in range(S):
        t = y / (S - 1)
        grad.putpixel((0, y), tuple(
            int(a + (b - a) * t) for a, b in zip(TILE_TOP, TILE_BOTTOM)))
    grad = grad.resize((S, S))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1],
                                           radius=RADIUS, fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask)
    return out


def poly(pen, points, box, fill=WHITE):
    """Draw a shape given in 0..1 coordinates inside `box`."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    pen.polygon([(x0 + px * w, y0 + py * h) for px, py in points], fill=fill)


def oval(pen, cx, cy, rx, ry, box, fill=WHITE):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    pen.ellipse([x0 + (cx - rx) * w, y0 + (cy - ry) * h,
                 x0 + (cx + rx) * w, y0 + (cy + ry) * h], fill=fill)


def bar(pen, a, b, thick, box, fill=WHITE):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    pen.line([(x0 + a[0] * w, y0 + a[1] * h), (x0 + b[0] * w, y0 + b[1] * h)],
             fill=fill, width=int(thick * w), joint="curve")


def limb(pen, joints, thick, box, fill=WHITE):
    """A chain of segments with a round cap at every joint.

    Drawn this way rather than as one polygon per limb because a polygon
    has to guess where an elbow's outside edge falls and gets it wrong at
    every angle; a thick line with a disc at each joint bends correctly
    wherever the joint is put, and the figure stops looking like a set of
    separate planks laid end to end.
    """
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    pts = [(x0 + px * w, y0 + py * h) for px, py in joints]
    r = thick * w / 2
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        pen.line([(ax, ay), (bx, by)], fill=fill, width=int(thick * w))
    for cx, cy in pts:
        pen.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)


# ── the batter ──────────────────────────────────────────────────────────
# A right-handed hitter loaded at the top of the swing, seen from the
# side: hands together back by the shoulder, the bat up and away over it,
# both knees bent over a wide stance. Built from joints rather than from
# outlines, so the elbows and knees bend where they are put.

def batter(pen, box) -> None:
    HAND = (0.585, 0.300)
    bar(pen, HAND, (0.930, 0.130), 0.082, box)             # the bat
    limb(pen, [(0.430, 0.545), (0.560, 0.700), (0.628, 0.858)], 0.105, box)
    limb(pen, [(0.430, 0.545), (0.300, 0.705), (0.232, 0.858)], 0.105, box)
    poly(pen, [(0.600, 0.845), (0.706, 0.842), (0.712, 0.905),
               (0.598, 0.908)], box)                        # front foot
    poly(pen, [(0.154, 0.842), (0.262, 0.845), (0.264, 0.908),
               (0.148, 0.905)], box)                        # back foot
    poly(pen, [(0.368, 0.298), (0.512, 0.288), (0.545, 0.410),
               (0.512, 0.565), (0.372, 0.570), (0.330, 0.418)], box)  # torso
    limb(pen, [(0.470, 0.335), (0.548, 0.395), HAND], 0.078, box)   # near arm
    limb(pen, [(0.430, 0.320), (0.520, 0.352), HAND], 0.070, box)   # far arm
    oval(pen, 0.462, 0.212, 0.081, 0.088, box)             # helmet
    poly(pen, [(0.386, 0.176), (0.462, 0.166), (0.462, 0.222),
               (0.374, 0.232)], box)                        # the brim


# ── the shooter ─────────────────────────────────────────────────────────
# A player at the top of a jump shot: the ball just off the fingers above
# the head, the shooting arm still extended under it, the guide hand
# falling away, both legs tucked. Same weight of limb as the batter, so
# the two plaques read as a pair rather than two different drawings.

def shooter(pen, box) -> None:
    # tucked, not striding: a jump shot leaves the floor with the knees
    # drawn up and the feet close together under the hips
    limb(pen, [(0.398, 0.582), (0.488, 0.726), (0.432, 0.872)], 0.100, box)
    limb(pen, [(0.398, 0.582), (0.300, 0.720), (0.320, 0.866)], 0.100, box)
    poly(pen, [(0.392, 0.856), (0.482, 0.858), (0.486, 0.912),
               (0.388, 0.910)], box)                        # near foot
    poly(pen, [(0.256, 0.850), (0.348, 0.852), (0.352, 0.906),
               (0.252, 0.904)], box)                        # far foot
    poly(pen, [(0.334, 0.330), (0.478, 0.320), (0.512, 0.448),
               (0.478, 0.600), (0.338, 0.605), (0.296, 0.455)], box)  # torso
    limb(pen, [(0.452, 0.352), (0.552, 0.268), (0.596, 0.176)], 0.076, box)
    limb(pen, [(0.336, 0.360), (0.372, 0.258), (0.470, 0.198)], 0.070, box)
    oval(pen, 0.398, 0.252, 0.079, 0.086, box)             # head
    poly(pen, [(0.318, 0.278), (0.330, 0.232), (0.392, 0.226),
               (0.392, 0.296)], box)                        # tied-back hair
    oval(pen, 0.628, 0.104, 0.084, 0.084, box)             # the ball


def badge(size, left, right, figure) -> Image.Image:
    """One league plaque: a two-colour rounded field, a white figure."""
    w, h = size
    big = (w * 2, h * 2)
    card = Image.new("RGBA", big, (0, 0, 0, 0))
    pen = ImageDraw.Draw(card)
    pen.rectangle([0, 0, big[0] // 2, big[1]], fill=left)
    pen.rectangle([big[0] // 2, 0, big[0], big[1]], fill=right)
    figure(pen, (0, 0, big[0], big[1]))

    mask = Image.new("L", big, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, big[0] - 1, big[1] - 1], radius=int(big[0] * 0.10), fill=255)
    plate = Image.new("RGBA", big, (0, 0, 0, 0))
    plate.paste(card, (0, 0), mask)

    # the white keyline the real plaques carry
    ImageDraw.Draw(plate).rounded_rectangle(
        [0, 0, big[0] - 1, big[1] - 1], radius=int(big[0] * 0.10),
        outline=WHITE, width=int(big[0] * 0.035))
    return plate.resize(size, Image.LANCZOS)


def build() -> int:
    out = tile()
    bw, bh = int(S * 0.335), int(S * 0.435)
    gap = int(S * 0.045)
    top = int(S * 0.175)
    left_x = (S - (bw * 2 + gap)) // 2

    out.alpha_composite(badge((bw, bh), WNBA_ORANGE, WNBA_BLUE, shooter),
                        (left_x, top))
    out.alpha_composite(badge((bw, bh), MLB_BLUE, MLB_RED, batter),
                        (left_x + bw + gap, top))

    pen = ImageDraw.Draw(out)
    font = ImageFont.truetype(EN_FONT, int(S * 0.083))
    label = "WNBA  ·  MLB"
    box = pen.textbbox((0, 0), label, font=font)
    pen.text(((S - (box[2] - box[0])) // 2, int(S * 0.735)), label,
             font=font, fill=WHITE)

    out.resize((512, 512), Image.LANCZOS).save(OUT)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
