"""Al Jazeera round logo — several finished designs. Never fails."""
import base64
import io
import math

import requests
from PIL import Image, ImageDraw, ImageFilter

S = requests.Session()
S.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
OUT, SS = 512, 4
BIG = OUT * SS


def mark():
    img = Image.open(io.BytesIO(S.get("https://i.imgur.com/7bRVpnu.png", timeout=30).content)).convert("RGBA")
    return img.crop(img.split()[3].point(lambda a: 255 if a > 24 else 0).getbbox())


def tint(img, rgb):
    solid = Image.new("RGBA", img.size, rgb + (255,))
    solid.putalpha(img.split()[3])
    return solid


def gradient(size, top, bottom):
    g = Image.new("RGBA", (1, size))
    for y in range(size):
        t = y / (size - 1)
        g.putpixel((0, y), tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3)) + (255,))
    return g.resize((size, size))


def disc(ground, logo, fill, rim=None, rim_w=0.02, glow=False):
    canvas = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    mask = Image.new("L", (BIG, BIG), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, BIG - 1, BIG - 1], fill=255)
    canvas.paste(ground, (0, 0), mask)
    aspect = logo.width / logo.height
    h = BIG * fill / math.sqrt(1 + aspect * aspect)
    scaled = logo.resize((int(h * aspect), int(h)), Image.LANCZOS)
    pos = ((BIG - scaled.width) // 2, (BIG - scaled.height) // 2)
    if glow:
        halo = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
        halo.alpha_composite(tint(scaled, (255, 214, 120)), pos)
        halo = halo.filter(ImageFilter.GaussianBlur(BIG * 0.03))
        a = halo.split()[3].point(lambda v: int(v * 0.45))
        halo.putalpha(a)
        canvas.alpha_composite(halo)
    canvas.alpha_composite(scaled, pos)
    if rim:
        w = int(BIG * rim_w)
        ImageDraw.Draw(canvas).ellipse([w // 2, w // 2, BIG - 1 - w // 2, BIG - 1 - w // 2], outline=rim, width=w)
    canvas.putalpha(Image.composite(canvas.split()[3], mask, mask))
    return canvas.resize((OUT, OUT), Image.LANCZOS)


m = mark()
designs = {
    # 1. gold on deep navy, gold rim, soft glow — the premium broadcast look
    "aj_navy_gold": disc(gradient(BIG, (16, 34, 62), (6, 14, 30)), m, 0.80, (201, 160, 72, 255), 0.022, True),
    # 2. gold on black, thin gold rim
    "aj_black_gold": disc(gradient(BIG, (28, 28, 30), (4, 4, 6)), m, 0.80, (190, 150, 64, 255), 0.018, True),
    # 3. white calligraphy on Al Jazeera gold
    "aj_gold_white": disc(gradient(BIG, (236, 178, 58), (196, 130, 20)), tint(m, (255, 255, 255)), 0.78, (255, 255, 255, 230), 0.02),
    # 4. gold on white with a gold rim
    "aj_white_gold": disc(gradient(BIG, (255, 255, 255), (242, 238, 230)), m, 0.80, (201, 160, 72, 255), 0.022),
}
for key, img in designs.items():
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    print(f"LOGO {key} {base64.b64encode(out.getvalue()).decode()}")
