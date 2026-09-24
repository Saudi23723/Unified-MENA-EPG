"""Draw the MBC round logos at their largest readable size. Never fails."""
import base64
import io
import math

import requests
from PIL import Image, ImageDraw

S = requests.Session()
S.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
LOGOS = {
    "aljazeera_a": "https://i.imgur.com/7bRVpnu.png",
    "aljazeera_b": "https://jiotvimages.cdn.jio.com/dare_images/images/AL_Jazeera.png",
    "aljazeera_c": "https://dtil.tmsimg.com/assets/s159135_ld_h15_aa.png?lock=720x540",
}
DARK = set()
OUT, SS = 512, 4            # final size, supersampling for smooth edges
BIG = OUT * SS
FILL = 0.84                 # share of the circle the mark's bounding box may reach


def trimmed(img):
    """Crop to what is actually drawn (alpha, or non-white on an opaque logo)."""
    img = img.convert("RGBA")
    alpha = img.split()[3].point(lambda a: 255 if a > 24 else 0)
    box = alpha.getbbox()
    if box and box != (0, 0) + img.size:
        return img.crop(box)
    # Opaque image: crop away a near-white or near-black frame.
    grey = img.convert("L")
    for mask in (grey.point(lambda v: 255 if v < 238 else 0), grey.point(lambda v: 255 if v > 18 else 0)):
        box = mask.getbbox()
        if box and (box[2] - box[0]) * (box[3] - box[1]) < 0.97 * img.size[0] * img.size[1]:
            return img.crop(box)
    return img


for key, url in LOGOS.items():
    try:
        mark = trimmed(Image.open(io.BytesIO(S.get(url, timeout=30).content)))
        px = [p for p in mark.getdata() if p[3] > 128]
        light = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b, _ in px) / max(1, len(px))
        dark = light > 165 or key in DARK
        ground = (18, 20, 30, 255) if dark else (255, 255, 255, 255)
        rim = (70, 74, 92, 255) if dark else (222, 224, 230, 255)

        canvas = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
        pen = ImageDraw.Draw(canvas)
        pen.ellipse([0, 0, BIG - 1, BIG - 1], fill=rim)
        edge = int(BIG * 0.018)
        pen.ellipse([edge, edge, BIG - 1 - edge, BIG - 1 - edge], fill=ground)

        # The largest box of this mark's shape that fits inside the circle.
        aspect = mark.width / mark.height
        diameter = BIG * FILL
        h = diameter / math.sqrt(1 + aspect * aspect)
        w = h * aspect
        scaled = mark.resize((max(1, int(w)), max(1, int(h))), Image.LANCZOS)
        canvas.alpha_composite(scaled, ((BIG - scaled.width) // 2, (BIG - scaled.height) // 2))

        # Keep only the disc.
        mask = Image.new("L", (BIG, BIG), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, BIG - 1, BIG - 1], fill=255)
        canvas.putalpha(Image.composite(canvas.split()[3], mask, mask))
        final = canvas.resize((OUT, OUT), Image.LANCZOS)
        out = io.BytesIO()
        final.save(out, format="PNG", optimize=True)
        print(f"LOGO {key} {base64.b64encode(out.getvalue()).decode()}")
    except Exception as exc:
        print("LOGO-ERR", key, type(exc).__name__, str(exc)[:100])
