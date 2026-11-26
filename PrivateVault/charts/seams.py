"""Fills the white seam FAA sectional GeoTIFFs carry where a chart's printed halves meet.

The seam is a band of very light pixels of nearly constant depth that follows a smooth curve (a
parallel, drawn in the chart's own projection) right across the map. It is found as that curve:
every column's very light vertical runs of seam-like depth are collected, a quadratic is fitted to
their centres with outliers thrown out, and the depth is their median. The whole band is then
filled, column by column, from the chart just above and below it, so it is one smooth piece and
not a patchwork. A sheet with no such band is left untouched."""
import sys
import numpy as np
from PIL import Image
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

def fill_band(rgb, p, depth, x0, x1, pad=3, k=7):
    src = rgb.astype(np.float32)
    out = src.copy()
    h, w, _ = rgb.shape
    def edge(y, x):
        # The chart at the band's edge, as a median over a short stretch along it and three rows
        # out, so a thin line or a letter touching the edge does not run down the fill as a streak.
        a = src[max(0, y - 2):y + 1, max(0, x - k):x + k + 1].reshape(-1, 3)
        return np.median(a, axis=0)
    for x in range(max(0, int(x0) - 8), min(w, int(x1) + 9)):
        c = np.polyval(p, x)
        top = int(np.floor(c - depth / 2)) - pad
        bot = int(np.ceil(c + depth / 2)) + pad
        a, b = top - 1, bot + 1
        if a < 0 or b >= h: continue
        t = (np.arange(top, bot + 1) - a) / (b - a)
        ea = edge(a, x); eb = np.median(src[b:min(h, b + 3), max(0, x - k):x + k + 1].reshape(-1, 3), axis=0)
        out[top:bot + 1, x] = ea * (1 - t)[:, None] + eb * t[:, None]
    # Evened out along the band, so what is left of a line meeting its edge fades into the fill
    # instead of standing as a dark stroke across it.
    xs = np.arange(max(0, int(x0) - 8), min(w, int(x1) + 9))
    if len(xs) > 30:
        tops = np.floor(np.polyval(p, xs) - depth / 2).astype(int) - pad
        bots = np.ceil(np.polyval(p, xs) + depth / 2).astype(int) + pad
        r0, r1 = max(0, tops.min()), min(h, bots.max() + 1)
        strip = out[r0:r1, xs[0]:xs[-1] + 1].copy()
        ker = np.ones(25) / 25.0
        sm = np.stack([np.apply_along_axis(lambda v: np.convolve(np.pad(v, 12, mode='edge'), ker, 'valid'), 1, strip[:, :, c]) for c in range(3)], -1)
        for i, x in enumerate(xs):
            y0, y1 = max(r0, tops[i]), min(r1, bots[i] + 1)
            out[y0:y1, x] = sm[y0 - r0:y1 - r0, i]
    return out.astype(np.uint8)

def fix(rgb, max_bands=2):
    light = (rgb >= 225).all(-1)
    found = []
    for _ in range(max_bands):
        band = find_band(light)
        if band is None: break
        p, depth, x0, x1, n = band
        found.append((p, depth, x0, x1, n))
        rgb = fill_band(rgb, p, depth, x0, x1)
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
    rgb = np.ascontiguousarray(rgb[y0:y1, x0:x1])
    rgb, found = fix(rgb)
    for p, depth, a, b, n in found:
        print("  seam filled: %.0f px deep, columns %d-%d" % (depth, a, b), flush=True)
    Image.fromarray(rgb).save(out_tif, compression="tiff_deflate")
    A, D, B, E, C, F = [float(v) for v in open(tfw).read().split()[:6]]
    ulx = C - A / 2 + x0 * A; uly = F - E / 2 + y0 * E
    lrx = ulx + (x1 - x0) * A; lry = uly + (y1 - y0) * E
    print("  map frame: columns %d-%d, rows %d-%d" % (x0, x1, y0, y1), flush=True)
    return ulx, uly, lrx, lry
