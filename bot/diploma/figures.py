"""Diplom ishi uchun vizual materiallar.

- scheme — jarayon / tuzilma sxemasi: bob matnidan olingan 3–6 bosqich bloklar va strelkalar bilan chiziladi (Pillow).
  Ichida faqat matn bor, hech qanday o'ylab topilgan raqam yo'q.
- illustration — mavzuga mos ilmiy illyustratsiya: AI bilan chiziladi (presentation/genimage.py — Cloudflare/Gemini).
  Chizib bo'lmasa — shu mavzudagi haqiqiy foto (Pixabay / Pexels / Wikimedia) qo'yiladi, manbasi yoziladi.
Har bir rasm manbasi saqlanadi: «Muallif tomonidan tuzilgan» yoki «AI yordamida yaratilgan»."""
import io
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/truetype/liberation")]
FONT_FILES = ["times.ttf", "LiberationSerif-Regular.ttf", "DejaVuSerif.ttf", "DejaVuSans.ttf"]
ILLUSTRATION_STYLE = ("photorealistic documentary photograph, DSLR, 35mm lens, natural colors, sharp focus, "
                      "soft natural lighting, clean uncluttered composition, academic publication quality")


def figure_prompt(scene, caption, topic, style=ILLUSTRATION_STYLE):
    """Ilmiy ish (diplom / dissertatsiya) rasmi uchun so'rov — taqdimot slaydi uchun emas."""
    return (
        f"Create a figure for an academic thesis. Subject to depict: {scene}\n"
        f"Figure caption: «{caption}». Thesis topic: «{topic}».\n"
        f"Style: {style}.\n"
        "Requirements: show exactly the described subject — the real objects, equipment, technology, places, "
        "processes or people that this part of the thesis discusses, so a reader immediately sees how the picture "
        "relates to the topic. If the topic concerns Uzbekistan or Central Asia, use a recognisably local setting "
        "(landscape, architecture, people, vehicles) — never substitute another country. Modern, accurate, "
        "plausible details; no fantasy, no cartoon or drawing style, no abstract shapes, no infographics, charts "
        "or diagrams. Wide 16:9 landscape composition, the main subject centred and well lit. Keep signboards, "
        "menus, posters and screens out of view or blank. "
        "Absolutely no text, letters, numbers, labels, captions, logos or watermarks."
    )
SOURCE_SCHEME = {"uz": "Muallif tomonidan tuzilgan", "ru": "Составлено автором", "en": "Compiled by the author"}
SOURCE_AI = {"uz": "AI yordamida yaratilgan illyustratsiya", "ru": "Иллюстрация создана с помощью ИИ",
             "en": "Illustration generated with AI"}
SOURCE_PHOTO = {"uz": "Ochiq foto bazasidan (Pexels / Pixabay / Wikimedia Commons)",
                "ru": "Открытый фотобанк (Pexels / Pixabay / Wikimedia Commons)",
                "en": "Open photo library (Pexels / Pixabay / Wikimedia Commons)"}


async def illustrate(illustrations, topic, style=ILLUSTRATION_STYLE):
    """Illyustratsiyalar uchun rasm: avval AI chizadi (Cloudflare / Gemini), chiza olmaganlari — mavzuga mos foto
    (Pexels / Pixabay / Wikimedia, item["image_query"], topilmasa — bob mavzusi bo'yicha). Har bir rasm — AI chizgani
    ham, foto ham — AI tekshiruvidan o'tadi (presentation/ai.py → best_pictures); mos kelmasa — qayta chiziladi.
    Umuman topilmasa — tashlanadi. Qaytaradi: {id(item): (bytes, "ai" | "photo")}."""
    if not illustrations:
        return {}
    from presentation.ai import best_pictures  # kech import: presentation.ai og'ir modul, sxemalar uchun kerak emas

    targets = [{"title": v["caption"], "text": "", "items": [],
                "image_query": v.get("image_query") or v.get("fallback_query") or v["caption"],
                "image_prompt": v["image_prompt"]} for v in illustrations]
    fallback = next((v.get("fallback_query") for v in illustrations if v.get("fallback_query")), None)
    found = await best_pictures(
        targets, topic, prefer_ai=True, fallback=fallback,
        draw_prompt=lambda t: figure_prompt(t["image_prompt"], t["title"], topic, style),
    )
    return {id(v): (image, origin) for v, (image, origin) in zip(illustrations, found) if image}


def font(size):
    for directory in FONT_DIRS:
        for name in FONT_FILES:
            if (directory / name).exists():
                return ImageFont.truetype(str(directory / name), size)
    return ImageFont.load_default(size=size)


def wrap(draw, text, fnt, width):
    lines, line = [], ""
    for word in text.split():
        test = f"{line} {word}".strip()
        if draw.textlength(test, font=fnt) <= width or not line:
            line = test
        else:
            lines.append(line)
            line = word
    return lines + ([line] if line else [])


def scheme(steps):
    """Bosqichlar sxemasi (PNG bytes): 3–4 bosqich — bir qatorda, 5–6 — ikki qatorda (ilon izi bo'ylab)."""
    steps = steps[:6]
    per_row = len(steps) if len(steps) <= 4 else 3
    rows = (len(steps) + per_row - 1) // per_row
    box_w, box_h, gap_x, gap_y, pad = 330, 150, 90, 90, 40
    width = pad * 2 + per_row * box_w + (per_row - 1) * gap_x
    height = pad * 2 + rows * box_h + (rows - 1) * gap_y
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    fnt, num_font = font(30), font(26)
    ink = (40, 60, 110)
    # Bosqichlar ranglari — bir oiladan, bosqichma-bosqich to'qlashadi (oq-qora chop etilganda ham farqlanadi)
    fills = [(234, 241, 252), (226, 236, 251), (218, 231, 250), (210, 226, 248), (202, 220, 246), (194, 214, 244)]
    centers = []
    for i, step in enumerate(steps):
        row, col = divmod(i, per_row)
        if row % 2:  # ilon izi: ikkinchi qator o'ngdan chapga
            col = per_row - 1 - col
        x, y = pad + col * (box_w + gap_x), pad + row * (box_h + gap_y)
        draw.rounded_rectangle((x + 6, y + 8, x + box_w + 6, y + box_h + 8), radius=20, fill=(225, 229, 238))  # soya
        draw.rounded_rectangle((x, y, x + box_w, y + box_h), radius=20, fill=fills[i], outline=ink, width=4)
        # Bosqich raqami — chap yuqori burchakda
        cx, cy, r = x + 30, y + 30, 20
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ink)
        draw.text((cx, cy), str(i + 1), font=num_font, fill="white", anchor="mm")
        lines = wrap(draw, step, fnt, box_w - 70)[:4]
        line_h = 36
        top = y + 8 + (box_h - line_h * len(lines)) / 2
        for j, line in enumerate(lines):
            draw.text((x + box_w / 2 + 14, top + j * line_h + line_h / 2), line, font=fnt, fill=(20, 25, 40), anchor="mm")
        centers.append((x, y))
    for (x1, y1), (x2, y2) in zip(centers, centers[1:]):
        if y1 == y2:  # bir qatorda — gorizontal strelka
            left_to_right = x2 > x1
            start = (x1 + box_w if left_to_right else x1, y1 + box_h / 2)
            end = (x2 if left_to_right else x2 + box_w, y2 + box_h / 2)
        else:  # keyingi qatorga — pastga
            start, end = (x1 + box_w / 2, y1 + box_h), (x2 + box_w / 2, y2)
        draw.line([start, end], fill=(40, 60, 110), width=5)
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = max(1.0, (dx * dx + dy * dy) ** 0.5)
        ux, uy = dx / length, dy / length
        tip = end
        draw.polygon([tip, (tip[0] - 22 * ux + 12 * uy, tip[1] - 22 * uy - 12 * ux),
                      (tip[0] - 22 * ux - 12 * uy, tip[1] - 22 * uy + 12 * ux)], fill=(40, 60, 110))
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


async def make_figures(diploma_folder, visuals, topic, lang):
    """visuals (ai.chapter_extras) → rasm fayllari bilan figure yozuvlari. Jadval — o'zgarmaydi (matn).
    Chizib bo'lmagan illyustratsiya tashlab yuboriladi."""
    diploma_folder.mkdir(parents=True, exist_ok=True)
    images = await illustrate([v for v in visuals if v["kind"] == "illustration"], topic)
    result = []
    for visual in visuals:
        item = {k: visual[k] for k in ("kind", "caption", "section", "paragraph")}
        item["id"] = uuid.uuid4().hex[:10]
        if visual["kind"] == "table":
            item.update(columns=visual["columns"], rows=visual["rows"], source=SOURCE_SCHEME.get(lang, SOURCE_SCHEME["uz"]))
        else:
            data, origin = (scheme(visual["steps"]), "scheme") if visual["kind"] == "scheme" else images.get(id(visual), (None, None))
            if not data:
                continue
            ext = "png" if visual["kind"] == "scheme" else "jpg"
            name = f"fig-{item['id']}.{ext}"
            (diploma_folder / name).write_bytes(data)
            item["file"] = name
            source = {"scheme": SOURCE_SCHEME, "ai": SOURCE_AI, "photo": SOURCE_PHOTO}[origin]
            item["source"] = source.get(lang, source["uz"])
            if visual["kind"] == "scheme":
                item["steps"] = visual["steps"]
        result.append(item)
    return result


def image_size(data):
    with Image.open(io.BytesIO(data)) as image:
        return image.width, image.height
