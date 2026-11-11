"""Shablonlar uchun grafik elementlar (Pillow): teksturalar, qo'lda chizilgan bezaklar, yirtiq qog'oz, foto ramkalari.
Hammasi PNG bytes qaytaradi va keshlanadi — bir xil element har bir slaydda qayta chizilmaydi."""
import io
import math
import random
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageOps

PX = 120  # generatsiya qilinadigan elementlarning zichligi: dyuymiga piksel


def to_png(image):
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def to_jpeg(image, quality=86):
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def hex_rgb(value):
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def noise(size, sigma=40):
    """Kulrang shovqin (qog'oz va eski foto donadorligi uchun)."""
    return Image.effect_noise(size, sigma).convert("L")


# ===== Fonlar =====
@lru_cache(maxsize=2)
def grid_paper():
    """Katakli daftar varag'i (16:9)."""
    w, h, step = 1600, 900, 40
    image = Image.new("RGB", (w, h), (252, 252, 253))
    draw = ImageDraw.Draw(image)
    for x in range(step // 2, w, step):
        draw.line([(x, 0), (x, h)], fill=(229, 229, 239), width=2)
    for y in range(step // 2, h, step):
        draw.line([(0, y), (w, y)], fill=(229, 229, 239), width=2)
    return to_jpeg(image, 90)


@lru_cache(maxsize=4)
def dark_texture(bg, bg2):
    """To'q eski qog'oz/teri teksturasi: gradient + donadorlik + chetlari qoraygan (vinyetka)."""
    w, h = 1600, 900
    start, end = Image.new("RGB", (w, h), hex_rgb(bg)), Image.new("RGB", (w, h), hex_rgb(bg2))
    image = Image.composite(end, start, Image.linear_gradient("L").rotate(-45, expand=False).resize((w, h)))
    grain = noise((w // 2, h // 2), 60).resize((w, h)).filter(ImageFilter.GaussianBlur(1.2))
    image = Image.blend(image, Image.merge("RGB", (grain, grain, grain)), 0.07)
    blotches = noise((32, 18), 90).resize((w, h), Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(30))
    image = Image.composite(image, Image.blend(image, Image.new("RGB", (w, h), (0, 0, 0)), 0.25), blotches)
    vignette = Image.radial_gradient("L").resize((w, h))  # markazda qora (0), chetlarda oq
    return to_jpeg(Image.composite(Image.new("RGB", (w, h), (8, 5, 3)), image, vignette.point(lambda v: int(v * 0.75))), 88)


@lru_cache(maxsize=4)
def side_fade(color, width_share=0.62):
    """Butun slaydli rasm ustidan chapdan o'ngga qorong'ilashtirish: chap qismda matn o'qilsin."""
    w, h = 800, 450
    alpha = Image.new("L", (w, h))
    solid, end = int(w * width_share * 0.55), int(w * width_share * 1.25)
    for x in range(w):
        value = 238 if x < solid else max(0, int(238 * (1 - (x - solid) / max(1, end - solid)) ** 1.6)) if x < end else 0
        alpha.paste(value, (x, 0, x + 1, h))
    layer = Image.new("RGBA", (w, h), hex_rgb(color) + (0,))
    layer.putalpha(alpha)
    return to_png(layer)


@lru_cache(maxsize=8)
def glow(color, strength=0.55):
    """Burchakdagi rangli nur (sport shablonlari): markazda yorqin, chetga qarab shaffof — kvadrat PNG."""
    size = 600
    alpha = Image.radial_gradient("L").resize((size, size)).point(lambda v: int(255 * strength * max(0, 1 - v / 255) ** 1.6))
    layer = Image.new("RGBA", (size, size), hex_rgb(color) + (0,))
    layer.putalpha(alpha)
    return to_png(layer)


@lru_cache(maxsize=8)
def edge_fade(color):
    """Rasmning chap cheti fonga silliq singib ketishi uchun: chapda to'liq fon rangi, o'ngga qarab shaffof."""
    w, h = 400, 450
    alpha = Image.new("L", (w, h))
    for x in range(w):
        alpha.paste(int(255 * (1 - x / (w - 1)) ** 1.8), (x, 0, x + 1, h))
    layer = Image.new("RGBA", (w, h), hex_rgb(color) + (0,))
    layer.putalpha(alpha)
    return to_png(layer)


@lru_cache(maxsize=4)
def bottom_fade(color):
    """Pastdan yuqoriga qorong'ilashtirish (muqovadagi butun rasm ustida)."""
    w, h = 400, 450
    alpha = Image.linear_gradient("L").resize((w, h)).point(lambda v: int(min(255, v * 1.15)))
    layer = Image.new("RGBA", (w, h), hex_rgb(color) + (0,))
    layer.putalpha(alpha)
    return to_png(layer)


# ===== Qo'lda chizilgan bezaklar (Daftar shabloni) =====
def _hand(points, seed, amount=2.5):
    """Chiziqqa qo'l titrashi: har bir nuqta biroz siljiydi."""
    rnd = random.Random(seed)
    return [(x + rnd.uniform(-amount, amount), y + rnd.uniform(-amount, amount)) for x, y in points]


def _canvas(w, h):
    return Image.new("RGBA", (w * 2, h * 2), (0, 0, 0, 0))


def _finish(image):
    return to_png(image.resize((image.width // 2, image.height // 2), Image.Resampling.LANCZOS))


@lru_cache(maxsize=16)
def doodle(kind, color="141414"):
    """kind: sparkle | star | squiggle | spiral | swirl | arrow — shaffof PNG."""
    ink = hex_rgb(color) + (255,)
    width = 14
    if kind == "sparkle":
        image = _canvas(300, 300)
        draw = ImageDraw.Draw(image)
        c, outer, inner = 300, 250, 55
        points = []
        for i in range(8):
            r = outer if i % 2 == 0 else inner
            a = math.pi / 4 * i - math.pi / 2
            points.append((c + r * math.cos(a), c + r * math.sin(a)))
        draw.line(_hand(points + points[:1], 3) + [points[0]], fill=ink, width=width, joint="curve")
        return _finish(image)
    if kind == "star":
        image = _canvas(260, 260)
        draw = ImageDraw.Draw(image)
        c = 260
        points = [(c + (220 if i % 2 == 0 else 95) * math.cos(math.pi / 5 * i - math.pi / 2),
                   c + (220 if i % 2 == 0 else 95) * math.sin(math.pi / 5 * i - math.pi / 2)) for i in range(10)]
        draw.polygon(points, fill=ink)
        return _finish(image)
    if kind == "squiggle":
        image = _canvas(420, 120)
        draw = ImageDraw.Draw(image)
        points = [(30 + x, 120 + 60 * math.sin(x / 55)) for x in range(0, 780, 6)]
        draw.line(_hand(points, 5, 1.5), fill=ink, width=width, joint="curve")
        return _finish(image)
    if kind == "spiral":
        image = _canvas(300, 300)
        draw = ImageDraw.Draw(image)
        points = [(300 + 9 * t * math.cos(t), 300 + 9 * t * math.sin(t)) for t in (i / 10 for i in range(5, 300))]
        draw.line(_hand(points, 7, 1.5), fill=ink, width=width, joint="curve")
        return _finish(image)
    if kind == "swirl":
        image = _canvas(420, 220)
        draw = ImageDraw.Draw(image)
        points = []
        for i in range(0, 361, 4):
            t = math.radians(i)
            points.append((60 + i * 1.9 + 70 * math.cos(t * 2 + math.pi), 220 + 120 * math.sin(t * 2)))
        draw.line(_hand(points, 9, 1.5), fill=ink, width=width, joint="curve")
        return _finish(image)
    # arrow — egilgan strelka
    image = _canvas(360, 220)
    draw = ImageDraw.Draw(image)
    points = [(40 + x, 360 - 0.0016 * (x - 330) ** 2 - 40) for x in range(0, 620, 8)]
    draw.line(_hand(points, 11, 1.5), fill=ink, width=width, joint="curve")
    tip = points[-1]
    draw.line([(tip[0] - 70, tip[1] - 10), tip, (tip[0] - 40, tip[1] + 60)], fill=ink, width=width, joint="curve")
    return _finish(image)


# ===== Tarixiy shablonlar: pergament va marmar fon, foto tonlari =====
@lru_cache(maxsize=8)
def texture(kind, bg, bg2):
    """kind: parchment — eski qog'oz (dog'lar, chetlari to'qroq); marble — och marmar (yumshoq tomirlar). JPEG 16:9."""
    w, h = 1600, 900
    start, end = Image.new("RGB", (w, h), hex_rgb(bg)), Image.new("RGB", (w, h), hex_rgb(bg2))
    image = Image.composite(end, start, Image.linear_gradient("L").rotate(-35).resize((w, h)))
    if kind == "parchment":
        blotches = noise((40, 24), 90).resize((w, h), Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(25))
        image = Image.composite(image, Image.blend(image, Image.new("RGB", (w, h), (120, 80, 35)), 0.22), blotches)
        grain = noise((w // 2, h // 2), 50).resize((w, h)).filter(ImageFilter.GaussianBlur(0.8))
        image = Image.blend(image, Image.merge("RGB", (grain, grain, grain)), 0.05)
        edge = Image.radial_gradient("L").resize((w, h)).point(lambda v: int(max(0, v - 90) * 1.2))
        image = Image.composite(Image.new("RGB", (w, h), (95, 60, 25)), image, edge.point(lambda v: int(v * 0.55)))
    elif kind == "marble":
        # Kam va yumshoq tomirlar (yirik shovqinning faqat ingichka chegarasi) — fon matnga xalaqit bermasin
        veins = noise((18, 10), 120).resize((w, h), Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(6))
        veins = veins.point(lambda v: 255 if 126 < v < 129 else 0).filter(ImageFilter.GaussianBlur(2.5))
        image = Image.composite(Image.blend(image, Image.new("RGB", (w, h), (130, 130, 128)), 0.18), image, veins)
        grain = noise((w // 2, h // 2), 30).resize((w, h))
        image = Image.blend(image, Image.merge("RGB", (grain, grain, grain)), 0.03)
    return to_jpeg(image, 88)


def toned(data, tone):
    """Foto toni: sepia — eski foto, mono — oq-qora arxiv. Boshqa holatda rasm o'zgarmaydi."""
    if tone not in ("sepia", "mono"):
        return data
    image = Image.open(io.BytesIO(data)).convert("RGB")
    if tone == "sepia":
        image = sepia(image)
    else:
        image = ImageOps.autocontrast(ImageOps.grayscale(image), cutoff=1).convert("RGB")
    return to_jpeg(image, 86)


# ===== Tabiat shablonlari: barg bezagi =====
@lru_cache(maxsize=32)
def leaf(color, alpha=1.0, angle=0, veins=True):
    """Barg siluet (tomirlari bilan) — shaffof kvadrat PNG. angle — gradusda (soat strelkasiga qarshi)."""
    size = 800
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    rgb = hex_rgb(color)
    fill = rgb + (int(255 * alpha),)
    cx, top, bottom, half = size / 2, 90, 690, 210
    # Ikki yoy — barg qirralari (pastdan tepaga uchli), oxirida kichik band
    left = [(cx - half * math.sin(math.pi * i / 40) * (1 - 0.25 * i / 40), bottom - (bottom - top) * i / 40) for i in range(41)]
    right = [(2 * cx - x, y) for x, y in reversed(left)]
    draw.polygon(left + right, fill=fill)
    draw.line([(cx, bottom), (cx, bottom + 70)], fill=fill, width=14)
    if veins:
        vein = (255, 255, 255, int(70 * alpha)) if sum(rgb) < 600 else (0, 0, 0, int(45 * alpha))
        draw.line([(cx, bottom), (cx, top + 40)], fill=vein, width=8)
        for i in range(1, 7):
            y = bottom - (bottom - top) * i / 7.5
            reach = half * math.sin(math.pi * i / 7.5) * 0.75
            draw.line([(cx, y), (cx - reach, y - 70)], fill=vein, width=5)
            draw.line([(cx, y), (cx + reach, y - 70)], fill=vein, width=5)
    image = image.rotate(angle, resample=Image.Resampling.BICUBIC)
    return to_png(image.resize((size // 2, size // 2), Image.Resampling.LANCZOS))


# ===== Rasm tayyorlash =====
def crop_to(data, ratio):
    """Rasmni kerakli nisbatga kesadi — eng muhim (detali ko'p) qismi saqlanadi (builder.picture bilan bir xil)."""
    from presentation.builder import focus

    image = Image.open(io.BytesIO(data))
    image.load()
    image = image.convert("RGB")
    edges = image.convert("L").resize((164, max(5, round(164 * image.height / image.width)))).filter(ImageFilter.FIND_EDGES)
    edges = edges.crop((2, 2, edges.width - 2, edges.height - 2))
    if image.width / image.height > ratio:
        keep = ratio / (image.width / image.height)
        left = focus(list(edges.resize((edges.width, 1), Image.Resampling.BOX).getdata()), keep)
        x0 = int(left * image.width)
        return image.crop((x0, 0, x0 + int(image.width * keep), image.height))
    keep = (image.width / image.height) / ratio
    top = focus(list(edges.resize((1, edges.height), Image.Resampling.BOX).getdata()), keep)
    y0 = int(top * image.height)
    return image.crop((0, y0, image.width, y0 + int(image.height * keep)))


def sepia(image):
    gray = ImageOps.autocontrast(ImageOps.grayscale(image), cutoff=1)
    toned = ImageOps.colorize(gray, black=(38, 24, 14), white=(246, 232, 205), mid=(156, 116, 76))
    grain = noise(toned.size, 35)
    return Image.blend(toned, Image.merge("RGB", (grain, grain, grain)), 0.06)


def vintage_photo(data, w_in, h_in):
    """Eski foto: sepiya, krem rangli hoshiya va soya (PNG, w_in × h_in dyuymga mo'ljallangan)."""
    w, h = int(w_in * PX), int(h_in * PX)
    pad, border = int(0.12 * PX), int(0.16 * PX)
    inner_w, inner_h = w - 2 * pad - 2 * border, h - 2 * pad - 2 * border
    photo = sepia(crop_to(data, inner_w / inner_h)).resize((inner_w, inner_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(shadow).rectangle((pad + 6, pad + 10, w - pad + 6, h - pad + 10), fill=150)
    canvas.paste((0, 0, 0, 255), (0, 0), shadow.filter(ImageFilter.GaussianBlur(9)))
    frame = Image.new("RGB", (w - 2 * pad, h - 2 * pad), (240, 228, 204))
    frame.paste(photo, (border, border))
    canvas.paste(frame, (pad, pad))
    return to_png(canvas)


@lru_cache(maxsize=64)
def torn_paper(w_in, h_in, color, seed=0):
    """Yirtiq qirrali eski qog'oz varag'i (soya bilan). O'lcham — dyuymda, 0.05 ga yaxlitlangan holda chaqiring."""
    w, h = max(40, int(w_in * PX)), max(40, int(h_in * PX))
    pad = int(0.09 * PX)
    rnd = random.Random(seed * 7919 + w * 31 + h)

    def edge(x0, y0, x1, y1, amount):
        length = math.hypot(x1 - x0, y1 - y0)
        steps = max(2, int(length / 9))
        nx, ny = -(y1 - y0) / length, (x1 - x0) / length
        return [(x0 + (x1 - x0) * i / steps + nx * rnd.uniform(-amount, amount),
                 y0 + (y1 - y0) * i / steps + ny * rnd.uniform(-amount, amount)) for i in range(steps)]

    left, top, right, bottom = pad, pad, w - pad, h - pad
    outline = (edge(left, top, right, top, 4.5) + edge(right, top, right, bottom, 2.5)
               + edge(right, bottom, left, bottom, 4.5) + edge(left, bottom, left, top, 2.5))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon(outline, fill=255)

    base = hex_rgb(color)
    paper = Image.new("RGB", (w, h), base)
    grain = noise((w, h), 55).filter(ImageFilter.GaussianBlur(0.6))
    paper = Image.blend(paper, Image.merge("RGB", (grain, grain, grain)), 0.08)
    stains = noise((max(2, w // 60), max(2, h // 60)), 80).resize((w, h), Image.Resampling.BICUBIC)
    paper = Image.composite(paper, Image.blend(paper, Image.new("RGB", (w, h), (120, 82, 45)), 0.18), stains.point(lambda v: 255 if v > 90 else 255 - (90 - v) * 2))
    # Qirralari biroz qoraygan (kuygan qog'oz)
    burn = mask.filter(ImageFilter.GaussianBlur(10)).point(lambda v: 255 - v)
    paper = Image.composite(Image.new("RGB", (w, h), (110, 72, 38)), paper, burn.point(lambda v: int(v * 0.55)))

    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow = Image.new("L", (w, h), 0)
    shadow.paste(mask.point(lambda v: int(v * 0.55)), (4, 7))
    canvas.paste((0, 0, 0, 255), (0, 0), shadow.filter(ImageFilter.GaussianBlur(6)))
    canvas.paste(paper, (0, 0), mask)
    return to_png(canvas)
