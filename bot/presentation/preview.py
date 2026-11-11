"""Dizaynlarni tanlashdan oldin ko'rsatiladigan kollaj rasm (Pillow)."""
import io
import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from presentation import art
from presentation.themes import THEMES

TILE_W, TILE_H = 640, 360
GAP = 24
FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu")]
FONT_FILES = {
    "bold": ["seguibl.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"],
    "regular": ["segoeui.ttf", "DejaVuSans.ttf"],
    "black": ["ariblk.ttf", "DejaVuSans-Bold.ttf"],
    "serif": ["georgia.ttf", "DejaVuSerif.ttf"],
    "serif_bold": ["georgiab.ttf", "DejaVuSerif-Bold.ttf"],
}


def font(weight, size):
    for directory in FONT_DIRS:
        for name in FONT_FILES[weight]:
            if (directory / name).exists():
                return ImageFont.truetype(str(directory / name), size)
    return ImageFont.load_default(size=size)


def color(hex_color, alpha=255):
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def gradient(w, h, start, end):
    base = Image.new("RGBA", (w, h), color(start))
    top = Image.new("RGBA", (w, h), color(end))
    # diagonal gradient: gorizontal va vertikal niqoblarning o'rtachasi
    vertical = Image.linear_gradient("L").resize((w, h))
    horizontal = Image.linear_gradient("L").rotate(90).resize((w, h))
    base.paste(top, (0, 0), ImageChops.add(horizontal, vertical, scale=2))
    return base


def label(img, number, t, fill=None, ink=None):
    """O'ng yuqoridagi «7. Korporativ» belgisi."""
    draw = ImageDraw.Draw(img)
    text = f"{number}. {t['name'].split(' ', 1)[1]}"
    label_font = font("bold", 24)
    width = draw.textlength(text, font=label_font) + 36
    draw.rounded_rectangle((TILE_W - width - 20, 20, TILE_W - 20, 62), radius=21, fill=color(fill or t["accent"]))
    draw.text((TILE_W - width - 2, 25), text, font=label_font, fill=color(ink or (t["bg"] if t["dark"] else "FFFFFF")))
    return img


def sample_photo(top, bottom, size):
    """Kollajdagi «rasm» o'rni: ikki rangli gradient va oddiy siluet (tog'lar va quyosh)."""
    w, h = size
    img = gradient(w, h, top, bottom)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.ellipse((w * 0.62, h * 0.18, w * 0.8, h * 0.18 + w * 0.18), fill=(255, 255, 255, 170))
    draw.polygon([(0, h), (w * 0.35, h * 0.45), (w * 0.6, h)], fill=(0, 0, 0, 55))
    draw.polygon([(w * 0.35, h), (w * 0.72, h * 0.35), (w, h * 0.8), (w, h)], fill=(0, 0, 0, 85))
    return Image.alpha_composite(img, layer)


def paste_png(img, png, box):
    layer = Image.open(io.BytesIO(png)).convert("RGBA").resize((box[2] - box[0], box[3] - box[1]))
    img.alpha_composite(layer, (box[0], box[1]))


def tile_corporate(number, t):
    img = Image.new("RGBA", (TILE_W, TILE_H), color(t["bg"]))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((10, 10, TILE_W - 10, TILE_H - 10), radius=14, outline=color("D2CFEC"), width=2)
    draw.rounded_rectangle((372, 92, 612, 332), radius=22, fill=color(t["accent"]))
    photo = sample_photo("9CC9E8", "3E7A55", (240, 240))
    mask = Image.new("L", photo.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 239, 239), radius=22, fill=255)
    img.paste(photo, (356, 76), mask)
    draw.rounded_rectangle((36, 70, 150, 94), radius=12, fill=color(t["accent"]))
    draw.text((50, 72), "TAQDIMOT", font=font("bold", 14), fill=color("FFFFFF"))
    draw.text((36, 110), "Kompaniya", font=font("bold", 44), fill=color(t["accent"]))
    draw.text((36, 162), "taqdimoti", font=font("bold", 44), fill=color(t["accent"]))
    for i in range(2):
        y = 236 + i * 40
        draw.rounded_rectangle((36, y, 320, y + 30), radius=8, fill=color("FFFFFF"), outline=color(t["accent"]), width=2)
        draw.ellipse((46, y + 11, 54, y + 19), fill=color(t["accent"]))
        draw.rounded_rectangle((64, y + 11, 240 - i * 50, y + 19), radius=4, fill=color(t["muted"], 120))
    return label(img, number, t, fill=t["accent"], ink="FFFFFF")


def tile_doodle(number, t):
    img = Image.open(io.BytesIO(art.grid_paper())).convert("RGBA").resize((TILE_W, TILE_H))
    draw = ImageDraw.Draw(img)
    ink = color("141414")
    for (x, y, w, fill, text) in ((60, 110, 300, t["accent"], "Loyiha"), (100, 186, 330, t["accent2"], "taqdimoti")):
        draw.rectangle((x + 7, y + 7, x + w + 7, y + 62), fill=ink)
        draw.rectangle((x, y, x + w, y + 55), fill=color(fill), outline=ink, width=3)
        f = font("black", 34)
        draw.text((x + (w - draw.textlength(text, font=f)) / 2, y + 6), text, font=f, fill=ink)
    draw.rounded_rectangle((120, 66, 270, 92), radius=13, fill=color(t["accent2"]), outline=ink, width=2)
    draw.text((140, 69), "TAQDIMOT", font=font("bold", 14), fill=ink)
    draw.rectangle((470, 140, 600, 300), fill=color(t["accent"]))
    photo = sample_photo("FFD6EC", "9EE8CF", (130, 160))
    img.paste(photo, (460, 130))
    draw.rectangle((460, 130, 590, 290), outline=ink, width=3)
    for i in range(5):
        draw.rounded_rectangle((470 + i * 27, 118, 476 + i * 27, 142), radius=3, fill=ink)
    paste_png(img, art.doodle("sparkle"), (24, 20, 74, 70))
    paste_png(img, art.doodle("spiral"), (24, 270, 84, 330))
    paste_png(img, art.doodle("squiggle"), (250, 300, 380, 338))
    paste_png(img, art.doodle("star"), (410, 70, 440, 100))
    return label(img, number, t, fill=t["accent2"], ink="141414")


def tile_vintage(number, t):
    img = Image.open(io.BytesIO(art.dark_texture(t["bg"], t["bg2"]))).convert("RGBA").resize((TILE_W, TILE_H))
    draw = ImageDraw.Draw(img)
    draw.rectangle((12, 12, TILE_W - 12, TILE_H - 12), outline=color(t["accent"]), width=2)
    paste_png(img, art.torn_paper(3.3, 2.3, t["card"], 5), (30, 70, 380, 316))
    title = font("serif_bold", 34)
    for i, text in enumerate(("TARIX", "SAHIFALARI")):
        draw.text((205 - draw.textlength(text, font=title) / 2, 120 + i * 44), text, font=title, fill=color(t["card_text"]))
    draw.line((150, 222, 260, 222), fill=color(t["accent2"]), width=2)
    draw.text((140, 236), "XIV–XV asrlar", font=font("serif", 18), fill=color(t["card_muted"]))
    photo = art.sepia(sample_photo("D8C8A8", "6B4A2B", (200, 230)).convert("RGB")).convert("RGBA")
    frame = Image.new("RGBA", (220, 250), color("F0E4CC"))
    frame.paste(photo, (10, 10))
    frame = frame.rotate(-4, expand=True, resample=Image.Resampling.BICUBIC)
    img.alpha_composite(frame, (400, 70))
    return label(img, number, t, fill=t["accent"], ink=t["bg"])


def tile_baroque(number, t):
    img = gradient(TILE_W, TILE_H, "3A2A14", "0C0A07")
    draw = ImageDraw.Draw(img)
    draw.ellipse((360, 40, 600, 330), fill=color("6E5232", 200))
    draw.ellipse((420, 70, 540, 190), fill=color("C9A37A", 210))
    img = img.filter(ImageFilter.GaussianBlur(6))
    fade = Image.open(io.BytesIO(art.side_fade(t["bg"], 0.62))).convert("RGBA").resize((TILE_W, TILE_H))
    img.alpha_composite(fade)
    draw = ImageDraw.Draw(img)
    draw.rectangle((14, 14, TILE_W - 14, TILE_H - 14), outline=color(t["accent"]), width=1)
    draw.text((40, 70), "T A Q D I M O T", font=font("regular", 14), fill=color(t["accent"]))
    title = font("serif", 44)
    draw.text((40, 100), "Barokko", font=title, fill=color(t["text"]))
    draw.text((40, 152), "san'ati", font=title, fill=color(t["text"]))
    draw.line((40, 222, 170, 222), fill=color(t["accent"]), width=2)
    draw.polygon([(178, 222), (185, 215), (192, 222), (185, 229)], fill=color(t["accent"]))
    draw.text((40, 240), "Drama, dabdaba va nafosat", font=font("serif", 18), fill=color(t["muted"]))
    return label(img, number, t, fill=t["accent"], ink=t["bg"])


def tile_nature(number, t):
    """Tabiat shablonlari: muqovadagi kabi butun plitkali «foto» ustida yirik sarlavha + shablon bezagi."""
    look = t.get("look", {})
    history = t.get("category") == "tarix"
    photo = sample_photo(*(("C9B79A", "4A3A28") if history else ("8FC7A0", "1F4D2B")), (TILE_W, TILE_H))
    fade = Image.open(io.BytesIO(art.side_fade(look.get("cover_fade", t["bg"]), 0.75))).convert("RGBA")
    img = Image.alpha_composite(photo, fade.resize((TILE_W, TILE_H)))
    draw = ImageDraw.Draw(img)
    decor = look.get("decor")
    if decor == "sun":
        cx, cy, r = 560, 290, 90
        points = [(cx + (r if i % 2 == 0 else r * 0.72) * math.cos(math.pi * i / 12),
                   cy + (r if i % 2 == 0 else r * 0.72) * math.sin(math.pi * i / 12)) for i in range(24)]
        draw.polygon(points, fill=color(t["accent"]))
    elif decor in ("leaf", "leaves"):
        paste_png(img, art.leaf(t["accent"], 0.95, 25), (470, 150, 650, 330))
    elif decor == "peak":
        draw.polygon([(380, TILE_H), (520, 170), (660, TILE_H)], fill=color(t["accent"], 200))
    elif decor == "gold":
        draw.line((40, 300, 180, 300), fill=color(t["accent"]), width=2)
    elif decor == "frame":
        draw.rectangle((12, 12, TILE_W - 12, TILE_H - 12), outline=color(t["accent"]), width=2)
    elif decor in ("ornament", "stars"):
        draw.line((40, 300, 260, 300), fill=color(t["accent"]), width=1)
        draw.polygon([(150, 293), (157, 300), (150, 307), (143, 300)], fill=color(t["accent"]))
    ink = color(look.get("cover_text", t["text"]))
    draw.line((40, 92, 64, 92), fill=color(t["accent"]), width=3)
    draw.text((74, 82), "TAQDIMOT", font=font("bold", 16), fill=color(t["accent"]))
    serif = "Georgia" in t.get("fonts", {}).get("title", "")
    title_font = font("serif" if serif else "black", 50)
    sport = t.get("category") == "sport"
    office = t.get("category") == "ofis"
    lines = (("Tarix", "sahifalari") if history else ("Sport", "kuchi") if sport else ("Biznes", "reja") if office
             else ("Ta'lim", "kelajagi") if t.get("category") == "talim"
             else ("San'at", "olami") if t.get("category") == "sanat"
             else ("Sog'lom", "kelajak") if t.get("category") == "tibbiyot"
             else ("Qonun va", "adolat") if t.get("category") == "huquq"
             else ("Raqamli", "kelajak") if t.get("category") == "fan" else ("Tabiat", "va inson"))
    lines = tuple(line.upper() for line in lines) if look.get("upper") else lines
    for i, line in enumerate(lines):
        draw.text((40, 118 + i * 58), line, font=title_font, fill=ink)
    draw.rounded_rectangle((40, 248, 120, 255), radius=3, fill=color(t["accent"]))
    return label(img, number, t, fill=t["accent"], ink=t.get("on_accent") or ("FFFFFF" if not t["dark"] else t["bg"]))


STYLE_TILES = {"corporate": tile_corporate, "doodle": tile_doodle, "vintage": tile_vintage, "baroque": tile_baroque,
               "nature": tile_nature, "heritage": tile_nature, "sport": tile_nature,
               "office": tile_nature, "edu": tile_nature, "tech": tile_nature,
               "art": tile_nature, "med": tile_nature, "law": tile_nature}


def tile(number, theme):
    t = theme
    if t.get("style") in STYLE_TILES:
        return STYLE_TILES[t["style"]](number, t)
    img = gradient(TILE_W, TILE_H, t["bg"], t["bg2"])
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.ellipse((400, 40, 700, 340), fill=color(t["accent"], 35))
    draw.ellipse((455, 95, 645, 285), fill=color(t["accent2"], 70))
    draw.ellipse((510, 150, 590, 230), fill=color(t["accent"], 230))
    draw.ellipse((-60, 280, 90, 430), fill=color(t["accent2"], 30))
    img = Image.alpha_composite(img, layer)

    draw = ImageDraw.Draw(img)
    draw.text((40, 48), "TAQDIMOT", font=font("bold", 18), fill=color(t["accent"]))
    draw.text((40, 82), "Sarlavha", font=font("bold", 54), fill=color(t["text"]))
    draw.rounded_rectangle((40, 162, 120, 168), radius=3, fill=color(t["accent"]))
    draw.rounded_rectangle((128, 162, 152, 168), radius=3, fill=color(t["accent2"]))
    for i in range(3):  # kichik kartalar
        y = 196 + i * 40
        draw.rounded_rectangle((40, y, 360, y + 30), radius=8, fill=color(t["card"], 230))
        draw.rounded_rectangle((40, y, 45, y + 30), radius=3, fill=color(t["accent"] if i % 2 == 0 else t["accent2"]))
        draw.rounded_rectangle((58, y + 11, 58 + 220 - i * 40, y + 19), radius=4, fill=color(t["muted"], 160))
    draw.rounded_rectangle((0, TILE_H - 6, TILE_W * 0.6, TILE_H), fill=color(t["accent"]))

    label = f"{number}. {t['name'].split(' ', 1)[1]}"
    label_font = font("bold", 24)
    width = draw.textlength(label, font=label_font) + 36
    draw.rounded_rectangle((TILE_W - width - 20, 20, TILE_W - 20, 62), radius=21, fill=color(t["accent"]))
    draw.text((TILE_W - width - 2, 25), label, font=label_font, fill=color(t["bg"] if t["dark"] else "FFFFFF"))
    return img


@lru_cache(maxsize=1)
def themes_collage():
    """Barcha dizaynlar bitta rasmda (PNG bytes). Bir marta yasaladi va eslab qolinadi."""
    themes = list(THEMES.values())
    cols = 2
    rows = (len(themes) + cols - 1) // cols
    canvas = Image.new("RGBA", (cols * TILE_W + (cols + 1) * GAP, rows * TILE_H + (rows + 1) * GAP), (18, 18, 24, 255))
    for i, theme in enumerate(themes):
        col, row = i % cols, i // cols
        canvas.paste(tile(i + 1, theme), (GAP + col * (TILE_W + GAP), GAP + row * (TILE_H + GAP)))
    buffer = io.BytesIO()
    canvas.convert("RGB").save(buffer, "PNG", optimize=True)
    return buffer.getvalue()
