"""Fills the white seam FAA sectional GeoTIFFs carry where a chart's printed halves meet.

The seam is a band of very light pixels of nearly constant depth that follows a smooth curve (a
parallel, drawn in the chart's own projection) right across the map. It is found as that curve:
every column's very light vertical runs of seam-like depth are collected, a quadratic is fitted to
their centres with outliers thrown out, and the depth is their median. Where the band is white, its
paper (and only its paper: every line, contour and letter the chart prints across it is kept) is
painted with the ground tint carried across from the chart just above and below it, so it reads as
chart and not as a gap; elsewhere along the curve nothing is touched. A sheet with no such band is left untouched."""
import sys
import numpy as np
from PIL import Image, ImageDraw
Image.MAX_IMAGE_PIXELS = None

def runs_in_column(light_col, lo=14, hi=90, gap=3):
    """(start, end) of light runs of seam-like depth, short dark specks inside allowed."""
    out = []; n = len(light_col); y = 0
    while y < n:
        if not light_col[y]: y += 1; continue
        s = y; e = y; dark = 0
        while e < n and (light_col[e] or dark < gap):
            dark = 0 if light_col[e] else dark + 1
            e += 1
        e -= dark
        if lo <= e - s <= hi: out.append((s, e))
        y = e + 1
    return out

def find_band(light, step=4, min_frac=0.15):
    h, w = light.shape
    xs, cs, ds = [], [], []
    for x in range(0, w, step):
        for s, e in runs_in_column(light[:, x]):
            xs.append(x); cs.append((s + e) / 2); ds.append(e - s)
    if len(xs) < (w // step) * min_frac: return None
    xs = np.array(xs, float); cs = np.array(cs); ds = np.array(ds)
    # the band: the largest group of centres lying on one smooth curve
    best = None
    rng = np.random.default_rng(1)
    for _ in range(5000):
        i = rng.choice(len(xs), 3, replace=False)
        if len(set(xs[i])) < 3: continue
        p = np.polyfit(xs[i], cs[i], 2)
        inl = np.abs(np.polyval(p, xs) - cs) < 6
        if best is None or inl.sum() > best.sum(): best = inl
    if best is None or best.sum() < (w // step) * min_frac: return None
    p = np.polyfit(xs[best], cs[best], 2)
    for _ in range(3):
        inl = np.abs(np.polyval(p, xs) - cs) < 6
        p = np.polyfit(xs[inl], cs[inl], 2)
    depth = float(np.median(ds[inl]))
    # A real seam is white right through: over the columns where it was found, nearly every pixel
    # inside the fitted band is very light. A chance alignment of light patches is not.
    xi = xs[inl].astype(int)
    ys = np.round(np.polyval(p, xi)).astype(int)
    frac = np.mean([light[max(0, y - int(depth / 3)):y + int(depth / 3) + 1, x].mean() for x, y in zip(xi, ys)])
    if frac < 0.8 or not (20 <= depth <= 70): return None
    return p, depth, xs[inl].min(), xs[inl].max(), int(inl.sum())


def lum(c): return c[..., 0] * 0.3 + c[..., 1] * 0.59 + c[..., 2] * 0.11

def _unused_trace(src, x, y, step, n, w):
    """Follows a thin dark line from (x, y) outward n rows; returns its x at each row."""
    xs = [x]
    for k in range(1, n + 1):
        yy = y + step * k
        if yy < 0 or yy >= src.shape[0]: break
        c = int(round(xs[-1]))
        lo, hi = max(0, c - 3), min(w, c + 4)
        L = lum(src[yy, lo:hi])
        xs.append(lo + int(np.argmin(L)))
    return xs

def fill_band(rgb, centre, depth, x0, x1, pad=7, win=40, light_lo=222):
    """Paints the band's paper with the ground tint carried across from the chart just above and
    below it. Paper is the white, and anything paler than the chart at the band's edges in that
    column (a translucent airway or airspace tint over the white); every line, contour and letter
    printed across the band is kept as it is. Only where the band really is pure white over a stretch
    of 31 columns; elsewhere along it nothing is touched."""
    src = rgb.astype(np.float32)
    out = src.copy()
    h, w, _ = rgb.shape
    xs = np.arange(max(0, int(x0) - 8), min(w, int(x1) + 9))
    c = centre(xs)
    top = np.floor(c - depth / 2).astype(int) - pad
    bot = np.ceil(c + depth / 2).astype(int) + pad
    def tint(y0s, y1s):
        t = np.zeros((len(xs), 3), np.float32)
        for i, x in enumerate(xs):
            a = src[max(0, y0s[i]):min(h, max(0, y1s[i])), x]
            if not len(a): continue
            L = lum(a); keep = a[L >= np.percentile(L, 50)]
            t[i] = np.median(keep, axis=0)
        k = np.ones(win) / win
        return np.stack([np.convolve(np.pad(t[:, ch], win // 2, mode='edge'), k, 'valid')[:len(t)] for ch in range(3)], -1)
    tu, td = tint(top - 14, top), tint(bot + 1, bot + 15)
    paper = []
    frac = np.zeros(len(xs))
    for i, x in enumerate(xs):
        y0, y1 = top[i], bot[i]
        if y0 < 4 or y1 >= h - 4: paper.append(None); continue
        seg = src[y0:y1 + 1, x]
        el = min(lum(src[y0 - 3:y0, x]).mean(), lum(src[y1 + 1:y1 + 4, x]).mean(), lum(tu[i] * 0.5 + td[i] * 0.5))
        pp = ((seg >= light_lo).all(-1)) | (lum(seg) > el + 6)
        paper.append(pp)
        # Whether the band is really here is judged on pure white only: a pale stretch of chart is
        # never taken for the seam.
        core = seg[pad:len(seg) - pad]
        frac[i] = (core >= light_lo).all(-1).mean() if len(core) else 0
    sm = np.convolve(np.pad(frac, 15, mode='edge'), np.ones(31) / 31, 'valid')[:len(frac)]
    n = 0
    for i, x in enumerate(xs):
        pp = paper[i]
        if pp is None or sm[i] < 0.45: continue
        y0, y1 = top[i], bot[i]
        t = (np.arange(y0, y1 + 1) - (y0 - 1)) / (y1 - y0 + 2)
        fillc = tu[i] * (1 - t)[:, None] + td[i] * t[:, None]
        out[y0:y1 + 1, x] = np.where(pp[:, None], fillc, src[y0:y1 + 1, x]); n += int(pp.sum())
    return np.clip(out, 0, 255).astype(np.uint8), n


def _gdt(tif, pts, inverse=False):
    """Pixel/line of the sheet to longitude/latitude (or back) with gdaltransform."""
    import subprocess
    args = ["gdaltransform"] + (["-i"] if inverse else []) + ["-t_srs", "EPSG:4326", tif]
    out = subprocess.run(args, input="".join("%r %r\n" % (float(a), float(b)) for a, b in pts), capture_output=True, text=True, check=True).stdout
    return [tuple(float(v) for v in l.split()[:2]) for l in out.strip().splitlines()]


def snap(light, rows, depth, a, b, reach=30, win=61):
    """Moves the predicted centre of the band onto the white run actually found in each column (within
    reach), smoothed along the band; where no run is found the prediction stands."""
    h = light.shape[0]
    off = np.full(len(rows), np.nan)
    for x in range(max(0, a), min(len(rows), b + 1)):
        c = int(round(rows[x]))
        lo, hi = max(0, c - reach - int(depth)), min(h, c + reach + int(depth))
        best = None
        for s0, e0 in runs_in_column(light[lo:hi, x], lo=max(10, int(depth * 0.6)), hi=int(depth * 1.6)):
            m = lo + (s0 + e0) / 2
            if abs(m - c) <= reach and (best is None or abs(m - c) < abs(best - c)): best = m
        if best is not None: off[x] = best - rows[x]
    ok = ~np.isnan(off)
    if ok.sum() < 10: return rows
    xs = np.arange(len(rows))
    o = np.interp(xs, xs[ok], off[ok])
    k = np.ones(win) / win
    o = np.convolve(np.pad(o, win // 2, mode='edge'), k, 'valid')[:len(o)]
    return rows + o


def find_bands_geo(light, tif, ox, oy, step=8, max_bands=3):
    """The seams are parallels: found as latitudes, then followed exactly along them in the sheet's
    own projection, so the band is tracked all the way across."""
    h, w = light.shape
    xs, cs, ds = [], [], []
    for x in range(0, w, step):
        for s, e in runs_in_column(light[:, x]):
            xs.append(x); cs.append((s + e) / 2); ds.append(e - s)
    if not xs: return []
    ll = _gdt(tif, [(x + ox, c + oy) for x, c in zip(xs, cs)])
    lats = np.array([b for a, b in ll]); ds = np.array(ds, float); xs = np.array(xs)
    bands = []
    used = np.zeros(len(lats), bool)
    for _ in range(max_bands):
        free = ~used
        if free.sum() < (w // step) * 0.1: break
        # The most crowded place, counted over a window rather than in fixed bins, so a seam whose
        # samples straddle a bin edge is not split in two and missed.
        cand = np.unique(np.round(lats[free] / 0.002)) * 0.002
        cnt = np.array([(free & (np.abs(lats - c) < 0.006)).sum() for c in cand])
        k = float(cand[np.argmax(cnt)])
        near = free & (np.abs(lats - k) < 0.006)
        if near.sum() < (w // step) * 0.1: break
        lat = float(np.median(lats[near])); depth = float(np.median(ds[near]))
        used |= np.abs(lats - lat) < 0.01
        xa, xb = xs[near].min(), xs[near].max()
        lon_a = _gdt(tif, [(xa + ox, oy + h / 2)])[0][0]; lon_b = _gdt(tif, [(xb + ox, oy + h / 2)])[0][0]
        lons = np.linspace(lon_a - 0.3, lon_b + 0.3, 400)
        px = _gdt(tif, [(lo, lat) for lo in lons], inverse=True)
        pxx = np.array([a - ox for a, b in px]); pyy = np.array([b - oy for a, b in px])
        rows = np.interp(np.arange(w), pxx, pyy)
        bands.append((rows, depth, xa, xb, int(near.sum()), lat))
    return bands


def find_meridians_geo(light, tif, ox, oy, step=8, max_bands=3):
    """Seams that run down the sheet along a meridian: found as longitudes and followed exactly along
    them in the sheet's projection. Returns, for each, the band's centre column for every row."""
    h, w = light.shape
    ys, cs, ds = [], [], []
    for y in range(0, h, step):
        for s0, e0 in runs_in_column(light[y, :]):
            ys.append(y); cs.append((s0 + e0) / 2); ds.append(e0 - s0)
    if not ys: return []
    ll = _gdt(tif, [(c + ox, y + oy) for y, c in zip(ys, cs)])
    lons = np.array([a for a, b in ll]); ds = np.array(ds, float); ys = np.array(ys)
    out = []; used = np.zeros(len(lons), bool)
    for _ in range(max_bands):
        free = ~used
        if free.sum() < (h // step) * 0.1: break
        # The most crowded place, counted over a window rather than in fixed bins, so a seam whose
        # samples straddle a bin edge is not split in two and missed.
        cand = np.unique(np.round(lons[free] / 0.002)) * 0.002
        cnt = np.array([(free & (np.abs(lons - c) < 0.006)).sum() for c in cand])
        k = float(cand[np.argmax(cnt)])
        near = free & (np.abs(lons - k) < 0.006)
        if near.sum() < (h // step) * 0.1: break
        lon = float(np.median(lons[near])); depth = float(np.median(ds[near]))
        used |= np.abs(lons - lon) < 0.01
        ya, yb = ys[near].min(), ys[near].max()
        lat_a = _gdt(tif, [(ox + w / 2, ya + oy)])[0][1]; lat_b = _gdt(tif, [(ox + w / 2, yb + oy)])[0][1]
        lats = np.linspace(min(lat_a, lat_b) - 0.3, max(lat_a, lat_b) + 0.3, 400)
        px = _gdt(tif, [(lon, la) for la in lats], inverse=True)
        pxx = np.array([a - ox for a, b in px]); pyy = np.array([b - oy for a, b in px])
        order = np.argsort(pyy)
        cols = np.interp(np.arange(h), pyy[order], pxx[order])
        out.append((cols, depth, ya, yb, int(near.sum()), lon))
    return out


def fix(rgb, max_bands=2):
    light = (rgb >= 225).all(-1)
    found = []
    for _ in range(max_bands):
        band = find_band(light)
        if band is None: break
        p, depth, x0, x1, n = band
        found.append((p, depth, x0, x1, n))
        rgb, _ = fill_band(rgb, lambda xx, p=p: np.polyval(p, xx), depth, x0, x1)
        light = (rgb >= 225).all(-1)
    return rgb, found

if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    rgb = np.array(Image.open(src).convert("RGB"))
    rgb, found = fix(rgb)
    for p, depth, x0, x1, n in found:
        print("band: depth %.0f px, columns %d-%d, %d samples, centre at middle row %.0f" % (depth, x0, x1, n, np.polyval(p, (x0 + x1) / 2)))
    Image.fromarray(rgb).save(dst)


# ---- the map frame, and a whole sheet made ready for the tiles ----

def map_frame(rgb, white_lo=240, thresh=0.5, run=200):
    """The rectangle of the sheet that is map, inside the white collar with its legends and tables:
    the first and last rows and columns, from each side, past which the picture stays mostly not white."""
    W = (rgb >= white_lo).all(-1)
    h, w = W.shape
    colf = W[h // 4: 3 * h // 4].mean(0)
    rowf = W[:, w // 4: 3 * w // 4].mean(1)
    def first(f, n):
        for i in range(n - run):
            if (f[i:i + run] < thresh).all(): return i
        return 0
    def last(f, n):
        for i in range(n - 1, run, -1):
            if (f[i - run:i] < thresh).all(): return i
        return n
    return first(colf, w), first(rowf, h), last(colf, w), last(rowf, h)   # x0, y0, x1, y1


def prepare(tif, tfw, out_tif):
    """Reads an FAA sectional GeoTIFF, keeps only its map, fills its seams, and writes it with a
    world file. Returns (ulx, uly, lrx, lry) of what was written, in the sheet's own projection."""
    im = Image.open(tif)
    if im.mode == "P":
        pal = np.array(im.getpalette()[:768], np.uint8).reshape(-1, 3)
        rgb = pal[np.array(im)]
    else:
        rgb = np.array(im.convert("RGB"))
    x0, y0, x1, y1 = map_frame(rgb)
    # Inside the frame each edge can still carry a thin white rule (the neatline's margin). Cut the
    # frame in past any row or column near an edge that is mostly white, so no white line is left
    # where one sheet stops over its neighbour.
    W = (rgb[y0:y1, x0:x1] >= 240).all(-1)
    rowf = W.mean(1); colf = W.mean(0)
    edge = 400
    bad = np.where(rowf[-edge:] > 0.6)[0]
    if len(bad): y1 = y0 + (len(rowf) - edge) + bad.min() - 2
    bad = np.where(rowf[:edge] > 0.6)[0]
    if len(bad): y0 = y0 + bad.max() + 3
    bad = np.where(colf[-edge:] > 0.6)[0]
    if len(bad): x1 = x0 + (len(colf) - edge) + bad.min() - 2
    bad = np.where(colf[:edge] > 0.6)[0]
    if len(bad): x0 = x0 + bad.max() + 3
    rgb = np.ascontiguousarray(rgb[y0:y1, x0:x1])
    light = (rgb >= 225).all(-1)
    for rows, depth, a, b, n, lat in find_bands_geo(light, tif, x0, y0):
        # A real seam is white right through over most of where it was found.
        rows = snap(light, rows, depth, int(a), int(b))
        cols = np.arange(int(a), int(b) + 1, 8)
        r = np.round(rows[cols]).astype(int)
        hh = light.shape[0]
        vals = [light[y - 12:y + 13, x].mean() for x, y in zip(cols, r) if 12 <= y < hh - 12]
        frac = float(np.mean(np.array(vals) > 0.8)) if vals else 0.0
        if frac < 0.15 or not (20 <= depth <= 70):
            print("  band at %.4f N not a seam (white %.0f%%, %.0f px)" % (lat, frac * 100, depth), flush=True)
            continue
        rgb, _ = fill_band(rgb, lambda xx, rows=rows: rows[np.clip(xx, 0, len(rows) - 1)], depth, a, b)
        light = (rgb >= 225).all(-1)
        print("  seam filled at %.4f N: %.0f px deep, columns %d-%d, white %.0f%%" % (lat, depth, a, b, frac * 100), flush=True)
    # Seams that run down the sheet along a meridian: found by longitude, filled on the sheet turned
    # on its side so the same fill works across them.
    rt = np.ascontiguousarray(rgb.transpose(1, 0, 2))
    lt = (rt >= 225).all(-1)
    for cols, depth, a, b, n, lon in find_meridians_geo(light, tif, x0, y0):
        cols = snap(lt, cols, depth, int(a), int(b))
        yy = np.arange(int(a), int(b) + 1, 8); cc = np.round(cols[yy]).astype(int)
        vals = [lt[c - 12:c + 13, y].mean() for y, c in zip(yy, cc) if 12 <= c < lt.shape[0] - 12]
        frac = float(np.mean(np.array(vals) > 0.8)) if vals else 0.0
        if frac < 0.15 or not (20 <= depth <= 70):
            print("  band at %.4f E not a seam (white %.0f%%, %.0f px)" % (lon, frac * 100, depth), flush=True); continue
        rt, _ = fill_band(rt, lambda xx, cols=cols: cols[np.clip(xx, 0, len(cols) - 1)], depth, a, b)
        lt = (rt >= 225).all(-1)
        print("  seam filled at %.4f E: %.0f px deep, rows %d-%d, white %.0f%%" % (lon, depth, a, b, frac * 100), flush=True)
    rgb = np.ascontiguousarray(rt.transpose(1, 0, 2))
    # Along the frame's edges, the white left between the map and the border rule is made clear, so
    # where this sheet lies over its neighbour no white line is drawn on the neighbour's chart.
    h, w, _ = rgb.shape
    alpha = np.full((h, w), 255, np.uint8)
    wh = (rgb >= 235).all(-1)
    reach = 120
    for x in range(w):
        col = wh[:, x]
        k = 0
        k = 6
        while k < reach and k < h and col[h - 1 - k]: k += 1
        alpha[h - k:, x] = 0
        k = 0
        k = 6
        while k < reach and k < h and col[k]: k += 1
        alpha[:k, x] = 0
    for y in range(h):
        row = wh[y]
        k = 0
        k = 6
        while k < reach and k < w and row[w - 1 - k]: k += 1
        alpha[y, w - k:] = 0
        k = 0
        k = 6
        while k < reach and k < w and row[k]: k += 1
        alpha[y, :k] = 0
    rgb = np.dstack([rgb, alpha])
    Image.fromarray(rgb, "RGBA").save(out_tif, compression="tiff_deflate")
    A, D, B, E, C, F = [float(v) for v in open(tfw).read().split()[:6]]
    ulx = C - A / 2 + x0 * A; uly = F - E / 2 + y0 * E
    lrx = ulx + (x1 - x0) * A; lry = uly + (y1 - y0) * E
    print("  map frame: columns %d-%d, rows %d-%d" % (x0, x1, y0, y1), flush=True)
    return ulx, uly, lrx, lry
