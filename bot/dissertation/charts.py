"""Ilmiy grafiklar (Pillow): ustunli, chiziqli va doiraviy. Qiymatlar faqat datasets.series() dan keladi.
Uslub — oq fon, ingichka o'qlar, qiymat yorliqlari: dissertatsiya sahifasida bosilganda ham aniq o'qiladi."""
import io
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/liberation"), Path("/usr/share/fonts/truetype/dejavu")]
FONT_FILES = ["times.ttf", "LiberationSerif-Regular.ttf", "DejaVuSerif.ttf", "DejaVuSans.ttf"]
PALETTE = [(58, 84, 160), (214, 122, 48), (74, 150, 104), (178, 64, 72), (120, 92, 170), (60, 150, 170),
           (190, 160, 60), (110, 110, 110), (150, 80, 130), (90, 130, 60), (200, 100, 120), (70, 70, 130)]
W, H = 1600, 900


def font(size):
    for directory in FONT_DIRS:
        for name in FONT_FILES:
            if (directory / name).exists():
                return ImageFont.truetype(str(directory / name), size)
    return ImageFont.load_default(size=size)


def fmt(value):
    if abs(value) >= 1000:
        return f"{value:,.0f}".replace(",", " ")
    return f"{value:.1f}".rstrip("0").rstrip(".") if value != int(value) else str(int(value))


def nice_max(value):
    if value <= 0:
        return 1
    exp = 10 ** math.floor(math.log10(value))
    for step in (1, 2, 2.5, 5, 10):
        if value <= step * exp:
            return step * exp
    return 10 * exp


def short(draw, text, fnt, width):
    text = str(text)
    while draw.textlength(text, font=fnt) > width and len(text) > 3:
        text = text[:-2].rstrip() + "…"
    return text


def axes_chart(labels, values, kind, y_label=""):
    image = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(image)
    small, normal = font(26), font(30)
    left, right, top, bottom = 150, W - 60, 60, H - 170
    top_value = nice_max(max(max(values), 0))
    # Setka va Y o'qi
    for i in range(6):
        y = bottom - (bottom - top) * i / 5
        draw.line([(left, y), (right, y)], fill=(225, 225, 230), width=2)
        draw.text((left - 14, y), fmt(top_value * i / 5), font=small, fill=(60, 60, 70), anchor="rm")
    draw.line([(left, top), (left, bottom), (right, bottom)], fill=(40, 40, 50), width=3)
    if y_label:
        draw.text((left, top - 34), short(draw, y_label, small, 900), font=small, fill=(60, 60, 70), anchor="ls")
    n = len(values)
    step = (right - left) / n
    points = []
    for i, (label, value) in enumerate(zip(labels, values)):
        cx = left + step * (i + 0.5)
        y = bottom - (bottom - top) * max(value, 0) / top_value
        if kind == "bar":
            width = min(step * 0.6, 140)
            draw.rectangle((cx - width / 2, y, cx + width / 2, bottom), fill=PALETTE[0])
        points.append((cx, y))
        draw.text((cx, y - 12), fmt(value), font=small, fill=(30, 30, 40), anchor="ms")
        text = short(draw, label, small, max(step - 10, 60))
        if step < 150:  # tor bo'lsa — yorliq qiya yoziladi
            layer = Image.new("RGBA", (260, 40), (255, 255, 255, 0))
            ImageDraw.Draw(layer).text((258, 20), short(draw, label, small, 250), font=small, fill=(40, 40, 50), anchor="rm")
            layer = layer.rotate(40, expand=True)
            image.paste(layer, (int(cx - layer.width + 14), bottom + 8), layer)
        else:
            draw.text((cx, bottom + 16), text, font=normal, fill=(40, 40, 50), anchor="mt")
    if kind == "line":
        draw.line(points, fill=PALETTE[0], width=6, joint="curve")
        for x, y in points:
            draw.ellipse((x - 10, y - 10, x + 10, y + 10), fill="white", outline=PALETTE[0], width=5)
    return image


def pie_chart(labels, values):
    image = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(image)
    small = font(28)
    total = sum(values) or 1
    box = (120, 90, 120 + 720, 90 + 720)
    start = -90.0
    for i, value in enumerate(values):
        extent = 360 * value / total
        draw.pieslice(box, start, start + extent, fill=PALETTE[i % len(PALETTE)], outline="white", width=4)
        mid = math.radians(start + extent / 2)
        if extent > 14:
            cx, cy, r = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2, 250
            draw.text((cx + r * math.cos(mid), cy + r * math.sin(mid)), f"{100 * value / total:.1f}%",
                      font=small, fill="white", anchor="mm")
        start += extent
    y = 120
    for i, (label, value) in enumerate(zip(labels, values)):
        draw.rectangle((900, y, 936, y + 36), fill=PALETTE[i % len(PALETTE)])
        text = short(draw, f"{label} — {fmt(value)} ({100 * value / total:.1f}%)", small, 640)
        draw.text((952, y + 18), text, font=small, fill=(30, 30, 40), anchor="lm")
        y += 56
    return image


def render(kind, labels, values, y_label=""):
    """kind: bar | line | pie → PNG bytes."""
    if not labels or len(labels) != len(values):
        raise ValueError("Grafik uchun ma'lumot yo'q")
    if kind == "pie" and any(v < 0 for v in values):
        kind = "bar"
    image = pie_chart(labels, values) if kind == "pie" else axes_chart(labels, values, kind, y_label)
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()
