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
FPS = 2
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
F_TINY  = font(12)
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
    ("RJ", "RJ261", "AMM", "JFK",  7*60+45,  13*60+30, "B787-8"),
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
    ("EY", "EY411", "AUH", "KUL",  7*60+55,  19*60+10, "B787-9"),
    ("EK", "EK927", "DXB", "CAI",  9*60+50,  12*60+5,  "B777-300ER"),
    ("RJ", "RJ404", "AMM", "BEY",  11*60+5,  12*60+0,  "E195-E2"),
    ("TK", "TK55",  "IST", "SIN",  10*60+40, 2*60+15,  "A350-900"),
    ("FZ", "FZ585", "DXB", "CMB",  11*60+20, 17*60+5,  "B737 MAX 8"),
    ("EY", "EY7",   "AUH", "FRA",  8*60+15,  13*60+5,  "B787-10"),
    ("EK", "EK163", "DXB", "DUB",  7*60+5,   11*60+40, "B777-300ER"),
    ("RJ", "RJ615", "AMM", "CAI",  13*60+30, 14*60+10, "A320neo"),
    ("TK", "TK761", "IST", "AUH",  12*60+45, 18*60+0,  "A321neo"),
]

# UTC offsets (hours) per airport, for showing each flight in the airports' own local time
AIRPORT_TZ = {
 "AMM":3,"ADJ":3,"AQJ":3,"AUH":4,"DXB":4,"DWC":4,"SHJ":4,"AQI":3,"RUH":3,"JED":3,"DMM":3,"AHB":3,
 "MED":3,"TUU":3,"ULH":3,"HAS":3,"MJI":3,"BSZ":3,"DOH":3,"MCT":4,"KWI":3,"BAH":3,"BGW":3,"EBL":3,
 "BEY":3,"DAM":3,"ALP":3,"CAI":3,"SSH":2,"TLV":3,"KHI":5,"DEL":5.5,"BLR":5.5,"CMB":5.5,"KTM":5.75,
 "MLE":5,"IST":3,"AYT":3,"HTY":3,"KSY":3,"GYD":4,"TBS":4,"ALA":5,"NQZ":5,"DME":3,"VKO":3,"LED":3,
 "ATH":3,"LCA":3,"MLA":2,"FCO":2,"MXP":2,"BGY":2,"BLQ":2,"NAP":2,"VIE":2,"MUC":2,"FRA":2,"DUS":2,
 "HAM":2,"BER":2,"ZRH":2,"GVA":2,"BRU":2,"AMS":2,"CDG":2,"LYS":2,"NCE":2,"BCN":2,"MAD":2,"LIS":1,
 "CPH":2,"ARN":2,"OSL":2,"TLL":3,"WAW":2,"KRK":2,"OTP":3,"BEG":2,"PRG":2,"BUD":2,"LHR":1,"LGW":1,
 "STN":1,"MAN":1,"BHX":1,"NCL":1,"EDI":1,"DUB":1,"CMN":1,"TUN":1,"BEN":2,"DSS":0,"CKY":0,"ACC":0,
 "ASM":3,"NBO":3,"MBA":3,"EBB":3,"JNB":2,"CPT":2,"TNR":3,"MRU":4,"SEZ":4,"BKK":7,"DMK":7,"HKT":7,
 "KUL":8,"SIN":8,"CGK":7,"DPS":8,"HAN":7,"SGN":7,"HKG":8,"CAN":8,"SZX":8,"PVG":8,"PEK":8,"CGO":8,
 "ICN":9,"NRT":9,"TPE":8,"MNL":8,"SYD":10,"MEL":10,"BNE":10,"AKL":12,"JFK":-4,"EWR":-4,"BOS":-4,
 "IAD":-4,"ORD":-5,"ATL":-4,"CLT":-4,"MCO":-4,"DFW":-5,"IAH":-5,"DTW":-4,"SEA":-7,"SFO":-7,
 "LAX":-7,"YYZ":-4,"YUL":-4,"MEX":-6,"BOG":-5,"PTY":-5,"GRU":-3,"SCL":-4,"LIM":-5,
}

def apoff(code, fallback):
    v = AIRPORT_TZ.get((code or "").upper())
    return float(v) if v is not None else float(fallback)

def hhmm(minutes):
    minutes %= 1440
    return f"{minutes//60:02d}:{minutes%60:02d}"

def load_flights():
    """Load the cached AviationStack feed; fall back to the built-in schedule."""
    try:
        with open(os.environ.get("FLIGHT_DATA", DATA_FILE)) as fh:
            data = json.load(fh)
        rows = data.get("flights") or []
        if rows:
            return rows, data.get("date", "")
    except Exception:
        pass
    return [dict(code=c, num=n, o=o, d=d, dep=dep, arr=arr, ac=ac,
                 api_status="", delay=0, lat=None, lon=None)
            for c, n, o, d, dep, arr, ac in SCHEDULE], ""


def build_flights(rows, now_min):
    flights = []
    for r in rows:
        dep, arr = r["dep"], r["arr"]
        if arr < dep:
            arr += 1440
        api = (r.get("api_status") or "").upper()
        delay = int(r.get("delay") or 0)
        prog = 0.0
        if api == "CANCELLED":
            status = "CANCELLED"
        elif api == "LANDED":
            status, prog = "LANDED", 1.0
        elif api == "ACTIVE" or (dep <= now_min < arr):
            status = "IN FLIGHT"
            prog = min(1.0, max(0.02, (now_min - dep) / max(1, arr - dep)))
        elif arr <= now_min:
            status, prog = "LANDED", 1.0
        elif delay > 0:
            status = "DELAYED"
        elif dep - now_min <= 45:
            status = "BOARDING"
        else:
            status = "SCHEDULED"
        f = dict(r)
        f.update(dep=dep, arr=arr, status=status, prog=prog, delay=delay)
        flights.append(f)

    order = {"IN FLIGHT": 0, "BOARDING": 1, "DELAYED": 2, "SCHEDULED": 3,
             "LANDED": 4, "CANCELLED": 5}
    flights.sort(key=lambda f: (order.get(f["status"], 9), f["dep"]))
    pages = max(1, math.ceil(len(flights) / PER_PAGE))
    return flights, pages


def draw_rounded(d, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)

def text(d, xy, s, f, fill=TEXT, anchor=None):
    d.text(xy, s, font=f, fill=fill, anchor=anchor)

ROWS = []


def render_frame(t, tz, date_label, out):
    """t: seconds since start of video."""
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=tz, seconds=t)
    now_min = now.hour * 60 + now.minute
    clock = now.strftime("%H:%M:%S")

    flights, pages = build_flights(ROWS, now_min)
    page = int(t // PAGE_SECONDS) % pages
    page_flights = flights[page*PER_PAGE:(page+1)*PER_PAGE]

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # header
    d.rectangle([0, 0, W, 86], fill=PANEL)
    d.line([0, 86, W, 86], fill=BORDER, width=2)
    d.ellipse([36, 26, 68, 58], outline=ACCENT, width=3)
    d.polygon([(44, 42), (60, 42), (52, 34)], fill=ACCENT)
    d.line([40, 50, 64, 50], fill=ACCENT, width=2)
    text(d, (84, 24), "LIVE FLIGHT TRACKER", F_TITLE)
    text(d, (86, 60), "Etihad  •  Emirates  •  Royal Jordanian  •  FlyDubai  •  Turkish Airlines", F_SMALL, MUTED)

    # live indicator (blinks)
    if int(t * 2) % 2 == 0:
        d.ellipse([W-300, 34, W-288, 46], fill=RED)
    text(d, (W-280, 30), "LIVE", F_CLOCK, RED)
    text(d, (W-230, 30), clock, F_CLOCK, TEXT)
    tzname = "Jordan Time (UTC+3)" if tz == 3 else "Dubai Time (UTC+4)"
    tzcity = "AMM" if tz == 3 else "DXB"
    text(d, (W-40, 58), f"{date_label}  •  {tzname}", F_SMALL, MUTED, anchor="ra")

    # stats bar
    counts = {"SCHEDULED":0,"BOARDING":0,"IN FLIGHT":0,"LANDED":0,"DELAYED":0,"CANCELLED":0}
    for f in flights:
        counts[f["status"]] = counts.get(f["status"], 0) + 1
    stats = [("TOTAL FLIGHTS", len(flights), TEXT),
             ("SCHEDULED", counts["SCHEDULED"], BLUE),
             ("BOARDING", counts["BOARDING"], AMBER),
             ("IN FLIGHT", counts["IN FLIGHT"], GREEN),
             ("LANDED", counts["LANDED"], GREY),
             ("DELAYED", counts["DELAYED"], RED)]
    y0, hh = 102, 74
    bw, gap = 196, 12
    x = 24
    for label, val, col in stats:
        draw_rounded(d, [x, y0, x+bw, y0+hh], 10, PANEL, BORDER)
        text(d, (x+bw//2, y0+12), str(val), F_STAT, col, anchor="ma")
        text(d, (x+bw//2, y0+46), label, F_STATL, MUTED, anchor="ma")
        x += bw + gap

    # flight cards: 2 columns x 4 rows
    card_w, card_h = 600, 96
    gx, gy = 24, 192
    for i, f in enumerate(page_flights):
        col_i, row_i = i % 2, i // 2
        cx = gx + col_i * (card_w + 32)
        cy = gy + row_i * (card_h + 14)
        acode = f["code"]
        aname, acol = AIRLINES[acode]
        scol = STATUS_COLOR.get(f["status"], MUTED)

        draw_rounded(d, [cx, cy, cx+card_w, cy+card_h], 10, PANEL_2, BORDER)
        # airline badge
        draw_rounded(d, [cx+12, cy+12, cx+64, cy+44], 8, acol)
        text(d, (cx+38, cy+27), acode, F_BADGE, (255, 255, 255), anchor="mm")
        text(d, (cx+76, cy+12), f["num"], F_FLIGHT)
        text(d, (cx+76, cy+38), f"{aname}  •  {f['ac']}", F_SMALL, MUTED)

        # route with progress line
        ry = cy + 72
        text(d, (cx+76, ry-8), f["o"], F_BODY, TEXT)
        text(d, (cx+200, ry-8), f["d"], F_BODY, TEXT, anchor="ra")
        line_y = ry + 14
        d.line([cx+100, line_y, cx+176, line_y], fill=BORDER, width=3)
        if f["prog"] > 0:
            px = cx + 100 + int(76 * f["prog"])
            d.line([cx+100, line_y, px, line_y], fill=GREEN, width=3)
            # plane marker
            d.polygon([(px, line_y-6), (px-8, line_y+6), (px+8, line_y+6)], fill=GREEN)
        dep_act=bool(f.get("dep_actual")); arr_act=bool(f.get("arr_actual"))
        dlab="DEP" if dep_act else "SCH"
        alab="ARR" if arr_act else ("ETA" if f["status"]=="IN FLIGHT" else "SCH")
        o_off = apoff(f["o"], tz); d_off = apoff(f["d"], tz)
        dep_o = int(round(f['dep'] + o_off*60 - 3*60))
        arr_d = int(round(f['arr'] + d_off*60 - 3*60))
        dep_l = f['dep'] + tz*60 - 3*60
        arr_l = f['arr'] + tz*60 - 3*60
        text(d, (cx+230, cy+14), f"{dlab} {hhmm(dep_o)}", F_SMALL, GREEN if dep_act else ACCENT)
        text(d, (cx+360, cy+14), f"{alab} {hhmm(arr_d)}", F_SMALL, GREEN if arr_act else ACCENT)
        text(d, (cx+230, cy+34), f"{hhmm(dep_l)} {tzcity}", F_TINY, GREY)
        text(d, (cx+360, cy+34), f"{hhmm(arr_l)} {tzcity}", F_TINY, GREY)
        dur = int(round(f["arr"] - f["dep"]))
        if dur < 0: dur += 1440
        text(d, (cx+230, cy+54), f"{dur//60}h {dur%60:02d}m", F_SMALL, MUTED)

        # status badge
        bw2 = 118
        draw_rounded(d, [cx+card_w-bw2-12, cy+12, cx+card_w-12, cy+40], 8, None, scol, 2)
        text(d, (cx+card_w-bw2//2-12, cy+25), f["status"], F_SMALL, scol, anchor="mm")
        if f["delay"]:
            text(d, (cx+card_w-16, cy+52), f"+{f['delay']} min", F_SMALL, RED, anchor="ra")
        elif f["status"] == "IN FLIGHT":
            bits=[]
            if f.get("alt"): bits.append("FL%03d"%(int(f["alt"])//100))
            if f.get("spd"): bits.append("%d kt"%int(f["spd"]))
            ph=(f.get("phase") or "").upper(); vs=f.get("vs") or 0
            if ph=="CLIMB" or vs>300: bits.append("climbing")
            elif ph=="DESCENT" or vs<-300: bits.append("descending")
            elif ph=="GROUND": bits.append("on ground")
            elif ph=="CRUISE": bits.append("cruising")
            if f.get("trk") is not None: bits.append("%03d°"%int(f["trk"]))
            if not bits: bits=[f"{int(f['prog']*100)}% en route"]
            text(d, (cx+card_w-16, cy+52), "  ".join(bits), F_SMALL, GREEN, anchor="ra")
            if f.get("callsign"): text(d, (cx+card_w-16, cy+72), str(f["callsign"]), F_SMALL, MUTED, anchor="ra")

    # footer
    d.rectangle([0, H-34, W, H], fill=PANEL)
    text(d, (24, H-26), f"Blue = airport local time  •  grey = {tzcity} time  •  green = actual recorded  •  Page {page+1} of {pages}", F_SMALL, MUTED)
    text(d, (W-24, H-26), "Live data • refreshed every 8 min  •  Unified MENA EPG — Channel 6", F_SMALL, MUTED, anchor="ra")

    img.save(out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tz", type=int, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    global ROWS
    ROWS, _ = load_flights()
    print(f"loaded {len(ROWS)} flights", flush=True)

    WORK = os.environ.get("CH6_WORK", "/tmp/browser/ch6")
    work = f"{WORK}/frames_{args.out}"
    os.makedirs(work, exist_ok=True)
    today = (datetime.datetime.utcnow() + datetime.timedelta(hours=args.tz)).strftime("%A, %d %B %Y")

    # video length = enough pages to show EVERY loaded flight
    total_pages = max(1, math.ceil(len(ROWS) / PER_PAGE))
    n = FPS * total_pages * PAGE_SECONDS
    for i in range(n):
        render_frame(i / FPS, args.tz, today, f"{work}/f{i:04d}.png")
        if i % 50 == 0:
            print(f"frame {i}/{n}", flush=True)

    outdir = os.environ.get("CH6_OUT", f"{WORK}/out_{args.out}")
    os.makedirs(outdir, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-framerate", str(FPS), "-i", f"{work}/f%04d.png",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-g", str(FPS*SEG_TIME),
        "-sc_threshold", "0",
        "-f", "hls", "-hls_time", str(SEG_TIME),
        "-hls_playlist_type", "vod",
        "-hls_segment_type", "mpegts",
        "-hls_segment_filename", f"{outdir}/{args.out}_%d.ts",
        f"{outdir}/{args.out}.m3u8",
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    # rewrite playlist to match house style
    with open(f"{outdir}/{args.out}.m3u8") as fh:
        print(fh.read())

if __name__ == "__main__":
    main()
