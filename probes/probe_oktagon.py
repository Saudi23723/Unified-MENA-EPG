"""OSN: every elcinema logo, measured and drawn round. Never fails."""
import base64
import io
import math
import re

import requests
from PIL import Image, ImageDraw

S = requests.Session()
S.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
IDS = [1393, 1394, 1257, 1395, 1232, 1231, 1392, 1205, 1285, 1390, 1211, 1213, 1391]
OUT, SS = 512, 4
BIG = OUT * SS


def trimmed(img):
    img = img.convert("RGBA")
    box = img.split()[3].point(lambda a: 255 if a > 24 else 0).getbbox()
    if box and box != (0, 0) + img.size:
        return img.crop(box)
    grey = img.convert("L")
    for mask in (grey.point(lambda v: 255 if v < 238 else 0), grey.point(lambda v: 255 if v > 18 else 0)):
        box = mask.getbbox()
        if box and (box[2] - box[0]) * (box[3] - box[1]) < 0.97 * img.size[0] * img.size[1]:
            return img.crop(box)
    return img


def round_logo(mark):
    px = [p for p in mark.getdata() if p[3] > 128]
    light = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b, _ in px) / max(1, len(px))
    dark = light > 165
    ground = (18, 20, 30, 255) if dark else (255, 255, 255, 255)
    rim = (70, 74, 92, 255) if dark else (222, 224, 230, 255)
    canvas = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    pen = ImageDraw.Draw(canvas)
    pen.ellipse([0, 0, BIG - 1, BIG - 1], fill=rim)
    e = int(BIG * 0.018)
    pen.ellipse([e, e, BIG - 1 - e, BIG - 1 - e], fill=ground)
    a = mark.width / mark.height
    h = BIG * 0.84 / math.sqrt(1 + a * a)
    s = mark.resize((max(1, int(h * a)), max(1, int(h))), Image.LANCZOS)
    canvas.alpha_composite(s, ((BIG - s.width) // 2, (BIG - s.height) // 2))
    mask = Image.new("L", (BIG, BIG), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, BIG - 1, BIG - 1], fill=255)
    canvas.putalpha(Image.composite(canvas.split()[3], mask, mask))
    return canvas.resize((OUT, OUT), Image.LANCZOS)


for cid in IDS:
    try:
        page = S.get(f"https://www.elcinema.com/tvguide/{cid}/", timeout=30).text
        title = re.search(r"<title>(.*?)</title>", page, re.S).group(1).strip()
        imgs = sorted(set(re.findall(r'(https://media\d+\.elcinema\.com/tvguide/%d_\d+\.(?:png|jpg))' % cid, page)))
        best = None
        for u in imgs:
            im = Image.open(io.BytesIO(S.get(u, timeout=30).content))
            if not best or im.size[0] * im.size[1] > best[1].size[0] * best[1].size[1]:
                best = (u, im)
        print(f"CH {cid} {title[:60]!r} imgs={[(u.rsplit('/',1)[1]) for u in imgs]} best={best and (best[0].rsplit('/',1)[1], best[1].size)}")
        if best:
            out = io.BytesIO()
            round_logo(trimmed(best[1])).save(out, format="PNG", optimize=True)
            print(f"LOGO e{cid} {base64.b64encode(out.getvalue()).decode()}")
    except Exception as exc:
        print("ERR", cid, type(exc).__name__, str(exc)[:100])
