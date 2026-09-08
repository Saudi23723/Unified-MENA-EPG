#!/usr/bin/env python3
"""
Channel 6 — Live Flight Tracker generator.
Renders a 1280x720 aviation dashboard video (60s) and segments it into HLS,
matching the format of the other Unified-MENA-EPG channels.

Usage:
    python3 generate_flight_tracker.py --tz 3 --out flight_tracker      # Jordan time
    python3 generate_flight_tracker.py --tz 4 --out dubai_flight_tracker # Dubai time
"""
import argparse, json, math, os, subprocess, sys, datetime
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
FPS = 5
DURATION = None  # dynamic: total_pages * PAGE_SECONDS
PAGE_SECONDS = 18
PER_PAGE = 8
DATA_FILE = "/dev-server/public/stream/flights.json"
SEG_TIME = 20

# ---------------------------------------------------------------- fonts
NOTO_CANDIDATES = [
    os.environ.get("CH6_FONT", ""),
    "/nix/store/dg3hd9mqha517djbgpgnq8r4q1j1wn30-noto-fonts-2025.11.01/share/fonts/noto/NotoSans[wdth,wght].ttf",
    "/usr/share/fonts/truetype/noto/NotoSans[wdth,wght].ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
NOTO_BOLD = {
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf": "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
}


def _pick_font():
    for c in NOTO_CANDIDATES + ["/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"]:
        if c and os.path.exists(c):
            return c
    raise SystemExit("no usable font found")


NOTO = _pick_font()


def font(size, bold=False):
    path = NOTO
    if bold and path in NOTO_BOLD and os.path.exists(NOTO_BOLD[path]):
        path = NOTO_BOLD[path]
    f = ImageFont.truetype(path, size)
    try:
        f.set_variation_by_axes([100, 700 if bold else 400])
    except Exception:
        pass
    return f


F_TITLE = font(34, True)
F_SUB   = font(20)
F_STAT  = font(26, True)
F_STATL = font(15)
F_FLIGHT= font(20, True)
F_BODY  = font(17)
F_SMALL = font(14)
F_BADGE = font(16, True)
F_CLOCK = font(22, True)

# ---------------------------------------------------------------- theme
BG        = (10, 15, 26)
PANEL     = (18, 26, 43)
PANEL_2   = (24, 34, 55)
BORDER    = (43, 58, 89)
TEXT      = (226, 232, 240)
MUTED     = (148, 163, 184)
ACCENT    = (56, 189, 248)
GREEN     = (52, 211, 153)
AMBER     = (251, 191, 36)
RED       = (248, 113, 113)
BLUE      = (96, 165, 250)
GREY      = (100, 116, 139)

AIRLINES = {
    "EY": ("Etihad",          (200, 164, 105)),
    "EK": ("Emirates",        (215, 25, 32)),
    "RJ": ("Royal Jordanian", (159, 30, 60)),
    "FZ": ("FlyDubai",        (46, 134, 193)),
    "TK": ("Turkish",         (232, 25, 44)),
}

STATUS_COLOR = {
    "SCHEDULED": BLUE, "BOARDING": AMBER, "IN FLIGHT": GREEN,
    "LANDED": GREY, "DELAYED": RED, "CANCELLED": RED,
}

# ------------------------------------------------------- flight schedule
# (airline, flight, origin, dest, dep UTC, arr UTC, aircraft)
SCHEDULE = [
    ("EY", "EY101", "AUH", "JFK",  2*60+10,  8*60+25,  "A350-1000"),
    ("EK", "EK203", "DXB", "JFK",  4*60+30,  10*60+15, "A380-800"),
    ("RJ","RJ261", "AMM", "JFK",  7*60+45,  13*60+30, "B787-8"),
    ("TK", "TK1",   "IST", "JFK",  8*60+5,   12*60+30, "B777-300ER"),
    ("FZ", "FZ157", "DXB", "CAI",  6*60+20,  8*60+35,  "B737 MAX 8"),
    ("EY", "EY371", "AUH", "BKK",  5*60+40,  14*60+55, "B787-9"),
    ("EK", "EK847", "DXB", "RUH",  3*60+15,  4*60+55,  "B777-300ER"),
    ("RJ", "RJ131", "AMM", "LHR",  9*60+10,  12*60+40, "B787-8"),
    ("TK", "TK763", "IST", "DXB",  6*60+50,  12*60+5,  "A330-300"),
    ("FZ", "FZ981", "DXB", "MOW",  5*60+5,   9*60+45,  "B737 MAX 8"),
    ("EY", "EY151", "AUH", "LHR",  6*60+30,  11*60+20, "B787-10"),
    ("EK", "EK353", "DXB", "SIN",  4*60+45,  16*60+5,  "A380-800"),
    ("RJ", "RJ811", "AMM", "DXB",  10*60+25, 14*60+15, "A320neo"),
    ("TK", "TK815", "IST", "RUH",  7*60+15,  11*60+30, "B737 MAX 9"),
    ("FZ", "FZ451", "DXB", "KTM",  8*60+40,  14*60+20, "B737 MAX 8"),
    ("EY", "VY411", "AUH", "KUL",  7*60+55,  19*60+10, "B787-9"),
