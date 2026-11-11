"""AI yozgan kontentdan chiroyli .pptx fayl yasaydi (python-pptx).

Deck — klassik dizayn (themes.py dagi rangli mavzular). Shablonlar (presentation/styles.py) Deck ning
ilgaklarini o'z uslubida qayta yozadi: fon, bezaklar, sarlavha, karta, rasm ramkasi, muqova va xulosa.
Maketlar (bullets, cards, ...) hamma uchun umumiy — ular faqat shu ilgaklar orqali chizadi."""
import io
import math
from datetime import datetime

from PIL import Image, ImageDraw, ImageFilter
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from config import FIXED_SLIDES
from metadata import clean_properties
from presentation.themes import BODY_FONT, DEFAULT_THEME, HEADING_FONT, QUOTE_FONT, THEMES, TITLE_FONT

W, H = 13.333, 7.5  # 16:9, dyuymda
MARGIN = 0.8
IMG_X = 8.0  # rasmli slaydlarda rasm shu nuqtadan o'ngga, butun balandlik bo'yicha joylashadi
COVER_IMG_X = 7.7

LABELS = {
    "uz": {"badge": "TAQDIMOT", "plan": "Reja", "contents": "Mundarija", "conclusion": "Xulosa",
           "thanks": "E'tiboringiz uchun rahmat!", "author": "Muallif"},
    "uz_cyrl": {"badge": "ТАҚДИМОТ", "plan": "Режа", "contents": "Мундарижа", "conclusion": "Хулоса",
                "thanks": "Эътиборингиз учун раҳмат!", "author": "Муаллиф"},
    "ru": {"badge": "ПРЕЗЕНТАЦИЯ", "plan": "План", "contents": "Содержание", "conclusion": "Заключение",
           "thanks": "Спасибо за внимание!", "author": "Автор"},
    "en": {"badge": "PRESENTATION", "plan": "Outline", "contents": "Contents", "conclusion": "Conclusion",
           "thanks": "Thank you for your attention!", "author": "Author"},
}
DEFAULT_FONTS = {"title": TITLE_FONT, "heading": HEADING_FONT, "body": BODY_FONT, "quote": QUOTE_FONT}


# ===== Kichik yordamchilar =====
def rgb(hex_color):
    return RGBColor.from_string(hex_color)


def set_alpha(shape, alpha):
    """Shakl to'ldirish rangiga shaffoflik beradi (0 — ko'rinmas, 1 — to'liq)."""
    color = shape._element.spPr.find(qn("a:solidFill")).find(qn("a:srgbClr"))
    node = color.makeelement(qn("a:alpha"), {"val": str(int(alpha * 100000))})
    color.append(node)


def shape(slide, kind, x, y, w, h, color, alpha=None, radius=None, line=None, line_width=None):
    """color=None — ichi bo'sh (faqat chiziq). line — chiziq rangi, line_width — punktda."""
    s = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    if color is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = rgb(color)
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(line_width or 1)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    if alpha is not None and color is not None:
        set_alpha(s, alpha)
    if radius is not None and kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    return s


def focus(profile, keep):
    """Smart crop: profile — rasm ustunlari (yoki qatorlari) bo'yicha detal miqdori, keep — saqlanadigan ulush.
    Detal eng ko'p bo'lgan oynani topadi (markazga biroz ustunlik bilan) va oyna boshini ulushda qaytaradi."""
    n = len(profile)
    size = max(1, round(n * keep))
    best, best_start = -1.0, (n - size) // 2
    for start in range(0, n - size + 1):
        center_shift = abs((start + size / 2) / n - 0.5)  # 0 — markazda, 0.5 — chetda
        score = sum(profile[start:start + size]) * (1 - 0.6 * center_shift)
        if score > best:
            best, best_start = score, start
    return best_start / n


def picture(slide, data, x, y, w, h):
    """Rasmni qutini to'liq to'ldiradigan qilib joylaydi. Ortiqcha qism o'rtadan emas, rasmning eng muhim
    (detali ko'p — odam, bino, predmet turgan) qismi ko'rinadigan qilib kesiladi."""
    with Image.open(io.BytesIO(data)) as img:
        img_ratio = img.width / img.height
        edges = img.convert("L").resize((164, max(5, round(164 / img_ratio)))).filter(ImageFilter.FIND_EDGES)
        edges = edges.crop((2, 2, edges.width - 2, edges.height - 2))  # filtr rasm chetida soxta «detal» beradi
    pic = slide.shapes.add_picture(io.BytesIO(data), Inches(x), Inches(y), Inches(w), Inches(h))
    box_ratio = w / h
    if img_ratio > box_ratio:  # rasm kengroq — yon tomonlardan kesiladi
        keep = box_ratio / img_ratio
        columns = list(edges.resize((edges.width, 1), Image.Resampling.BOX).getdata())
        left = focus(columns, keep)
        pic.crop_left, pic.crop_right = left, max(0.0, 1 - keep - left)
    else:  # rasm balandroq — tepa/pastdan kesiladi
        keep = img_ratio / box_ratio
        rows = list(edges.resize((1, edges.height), Image.Resampling.BOX).getdata())
        top = focus(rows, keep)
        pic.crop_top, pic.crop_bottom = top, max(0.0, 1 - keep - top)
    return pic


def overlay(slide, png, x, y, w, h):
    """Tayyor PNG (bezak, tekstura, gradient) ni joylaydi — kesilmaydi."""
    return slide.shapes.add_picture(io.BytesIO(png), Inches(x), Inches(y), Inches(w), Inches(h))


# Shriftdagi o'rtacha harf kengligi (shrift o'lchamiga nisbatan)
CHAR_WIDTH = {TITLE_FONT: 0.64, HEADING_FONT: 0.55, QUOTE_FONT: 0.5, "Georgia": 0.55, "Arial Black": 0.7,
              "Segoe UI Bold": 0.58}


def fit_size(text, w, h, max_size, min_size=12, font=BODY_FONT, line_height=1.45):
    # line_height: 1.1 qator oralig'i × Segoe UI shriftining ~1.33 balandligi (o'lchab tekshirilgan)
    """Matn qutiga sig'adigan shrift o'lchamini taxminan hisoblaydi.
    Eng uzun so'z ham bitta qatorga sig'ishi shart — aks holda so'z o'rtasidan bo'linadi."""
    factor = CHAR_WIDTH.get(font, 0.52)
    paragraphs = text.split("\n") or [""]
    longest = max((len(word) for word in text.split()), default=1)
    for size in range(max_size, min_size - 1, -1):
        chars_per_line = max(1, int(w * 72 / (size * factor)))
        lines = sum(max(1, math.ceil(len(p) / chars_per_line)) for p in paragraphs)
        if longest <= chars_per_line and lines * size * line_height / 72 <= h:
            return size
    return min_size


def text(slide, x, y, w, h, value, size, color, font=BODY_FONT, bold=False, italic=False,
         align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, spacing=None, auto=True, min_size=11):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = Emu(0)
    frame.vertical_anchor = anchor
    if auto:
        size = fit_size(value, w, h, size, min_size, font)
    for i, line in enumerate(value.split("\n")):
        para = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        para.alignment = align
        para.line_spacing = 1.1
        run = para.add_run()
        run.text = line
        run.font.size = Pt(size)
        run.font.name = font
        run.font.bold = bold
        run.font.italic = italic
        run.font.color.rgb = rgb(color)
        if spacing:
            run.font._element.set("spc", str(spacing))
    return box


def video_poster(theme):
    """Video muqovasi: dizayn ranglarida gradient va o'rtada ▶ belgisi (PNG bytes)."""
    w, h = 1280, 720
    start, end = Image.new("RGB", (w, h), f"#{theme['accent']}"), Image.new("RGB", (w, h), f"#{theme['accent2']}")
    mask = Image.linear_gradient("L").rotate(-90).resize((w, h))
    image = Image.composite(end, start, mask)
    draw = ImageDraw.Draw(image)
    draw.ellipse((w / 2 - 110, h / 2 - 110, w / 2 + 110, h / 2 + 110), fill=(255, 255, 255))
    draw.polygon([(w / 2 - 35, h / 2 - 55), (w / 2 - 35, h / 2 + 55), (w / 2 + 60, h / 2)], fill=f"#{theme['accent']}")
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def on_accent(theme):
    """Urg'u rangli shakl ustidagi matn rangi."""
    return theme.get("on_accent") or (theme["bg"] if theme["dark"] else "FFFFFF")


# ===== Slayd quruvchi =====
class Deck:
    def __init__(self, content, theme_key, lang, author):
        self.content = content
        self.theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
        self.fonts = {**DEFAULT_FONTS, **self.theme.get("fonts", {})}
        # Karta ichidagi matn ranglari (fon to'q, karta och bo'lgan shablonlarda farq qiladi)
        self.ink = self.theme.get("card_text", self.theme["text"])
        self.ink_muted = self.theme.get("card_muted", self.theme["muted"])
        self.labels = LABELS.get(lang, LABELS["uz"])
        self.author = author
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(W), Inches(H)
        self.total = FIXED_SLIDES + sum(len(plan["slides"]) for plan in content["plans"])
        self.index = 0
        self.area_w = W - 2 * MARGIN  # kontent kengligi (rasmli slaydda torayadi)
        self.has_image = False

    def text(self, slide, *args, font=None, **kwargs):
        """Matn — shablon shrifti bilan (font berilmasa — asosiy matn shrifti)."""
        return text(slide, *args, font=font or self.fonts["body"], **kwargs)

    # ----- Ilgaklar (shablonlar qayta yozadi) -----
    def background(self, slide, angle):
        t = self.theme
        fill = slide.background.fill
        fill.gradient()
        fill.gradient_angle = angle
        fill.gradient_stops[0].color.rgb = rgb(t["bg"])
        fill.gradient_stops[1].color.rgb = rgb(t["bg2"])

    def side_media(self, slide, image, video):
        """Kontent slaydining o'ng tomonidagi rasm yoki video."""
        if video:
            self.movie(slide, video)
        else:
            picture(slide, image, IMG_X, 0, W - IMG_X, H)
        shape(slide, MSO_SHAPE.RECTANGLE, IMG_X, 0, 0.08, H, self.theme["accent"])

    def text_width(self):
        """Rasmli slaydda matn uchun qolgan kenglik."""
        return IMG_X - 0.5 - MARGIN

    def card(self, slide, x, y, w, h, i=0, radius=0.22, alpha=0.85):
        """Matn kartasi foni. i — tartib raqami (rangni almashtirish uchun)."""
        return shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, self.theme["card"], alpha=alpha, radius=radius)

    def card_stripe(self, slide, x, y, h, i):
        """Kartaning chap chetidagi rangli chiziq."""
        t = self.theme
        shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, 0.1, h, t["accent"] if i % 2 == 0 else t["accent2"], radius=0.5)

    def new_slide(self, angle=135, decorate=True, image=None, video=None):
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])  # bo'sh maket
        self.index += 1
        self.background(slide, angle)
        self.has_image = image is not None or video is not None
        self.area_w = self.text_width() if self.has_image else (W - 2 * MARGIN)
        if self.has_image:
            self.side_media(slide, image, video)
        if decorate:
            self.decorations(slide)
        return slide

    def movie(self, slide, video, x=IMG_X, y=0, w=None, h=H):
        """Video (web muharrirda qo'shilgan) — panelda 16:9, dizayn rangidagi muqova bilan."""
        t = self.theme
        w = w or W - x
        shape(slide, MSO_SHAPE.RECTANGLE, x, y, w, h, t["card"])
        vw = w - 0.5
        vh = vw * 9 / 16
        slide.shapes.add_movie(
            video["path"], Inches(x + 0.25), Inches(y + (h - vh) / 2), Inches(vw), Inches(vh),
            poster_frame_image=io.BytesIO(video_poster(t)), mime_type=video["mime"],
        )

    def decorations(self, slide):
        """Burchakdagi shaffof doiralar, raqam va pastdagi progress chizig'i."""
        t = self.theme
        flip = self.index % 2 == 0
        if self.has_image:  # o'ng tomon rasm bilan band — faqat chapdagi bezak
            shape(slide, MSO_SHAPE.OVAL, -1.2, H - 1.6, 2.6, 2.6, t["accent2"], alpha=0.08)
        else:
            cx = -1.6 if flip else W - 2.6
            shape(slide, MSO_SHAPE.OVAL, cx, -1.8, 4.2, 4.2, t["accent"], alpha=0.10)
            shape(slide, MSO_SHAPE.OVAL, cx + (1.9 if flip else -0.9), -0.6, 1.6, 1.6, t["accent2"], alpha=0.14)
            shape(slide, MSO_SHAPE.OVAL, (W - 1.4) if flip else -0.6, H - 1.2, 2.0, 2.0, t["accent2"], alpha=0.08)
        # progress chizig'i
        shape(slide, MSO_SHAPE.RECTANGLE, 0, H - 0.08, W, 0.08, t["muted"], alpha=0.18)
        shape(slide, MSO_SHAPE.RECTANGLE, 0, H - 0.08, W * self.index / self.total, 0.08, t["accent"])
        self.footer(slide)

    def footer(self, slide, color=None):
        """Pastdagi mavzu nomi va slayd raqami."""
        color = color or self.theme["muted"]
        right = (MARGIN + self.area_w + 0.1) if self.has_image else (W - MARGIN)
        self.text(slide, right - 1.6, H - 0.55, 1.6, 0.3, f"{self.index:02d} / {self.total:02d}",
                  11, color, font=self.fonts["heading"], align=PP_ALIGN.RIGHT, auto=False)
        topic = " ".join(self.content["title"].split())
        self.text(slide, MARGIN, H - 0.55, right - MARGIN - 2.0, 0.3, topic[:80], 11, color, auto=False)

    def heading(self, slide, title, tag=None):
        t = self.theme
        y = 0.55
        if tag:
            tag = tag if len(tag) <= 60 else tag[:59] + "…"
            width = min(self.area_w, 0.5 + len(tag) * 0.08)
            shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, MARGIN, y, width, 0.38, t["accent"], alpha=0.16, radius=0.5)
            self.text(slide, MARGIN + 0.2, y + 0.07, width - 0.3, 0.26, tag, 11, t["accent"],
                      font=self.fonts["heading"], bold=True, auto=False)
            y += 0.6
        width = self.area_w if self.has_image else self.area_w - 1.2
        self.text(slide, MARGIN, y, width, 0.95, title, 34, t["text"], font=self.fonts["title"],
                  anchor=MSO_ANCHOR.MIDDLE, min_size=20)
        shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, MARGIN, y + 1.02, 1.1, 0.08, t["accent"], radius=0.5)
        shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, MARGIN + 1.2, y + 1.02, 0.35, 0.08, t["accent2"], radius=0.5)
        return y + 1.35  # kontent boshlanadigan y

    def intro(self, slide, value, y):
        if not value:
            return y
        self.text(slide, MARGIN, y, self.area_w, 0.7, value, 17, self.theme["muted"], min_size=12)
        return y + 0.85

    # ----- Muqova -----
    def title_slide(self):
        t = self.theme
        image = self.content.get("cover_image")
        slide = self.new_slide(angle=120, decorate=False)
        if image:
            picture(slide, image, COVER_IMG_X, 0, W - COVER_IMG_X, H)
            shape(slide, MSO_SHAPE.RECTANGLE, COVER_IMG_X, 0, 0.1, H, t["accent"])
            shape(slide, MSO_SHAPE.OVAL, COVER_IMG_X - 0.35, 5.5, 0.7, 0.7, t["accent2"])
            title_w = COVER_IMG_X - MARGIN - 0.6
        else:  # rasm topilmasa — o'ng tomondagi bezak kompozitsiya
            shape(slide, MSO_SHAPE.OVAL, 8.4, 0.9, 5.6, 5.6, t["accent"], alpha=0.12)
            shape(slide, MSO_SHAPE.OVAL, 9.4, 1.9, 3.6, 3.6, t["accent2"], alpha=0.22)
            shape(slide, MSO_SHAPE.OVAL, 10.35, 2.85, 1.7, 1.7, t["accent"], alpha=0.85)
            shape(slide, MSO_SHAPE.OVAL, 8.2, 5.6, 0.5, 0.5, t["accent2"], alpha=0.9)
            shape(slide, MSO_SHAPE.OVAL, 12.4, 0.7, 0.32, 0.32, t["accent"], alpha=0.9)
            title_w = 7.6
        shape(slide, MSO_SHAPE.OVAL, -1.2, 5.4, 3.0, 3.0, t["accent2"], alpha=0.08)

        self.text(slide, MARGIN, 1.25, 6, 0.4, self.labels["badge"], 14, t["accent"],
                  font=self.fonts["heading"], bold=True, spacing=600, auto=False)
        self.text(slide, MARGIN, 1.8, title_w, 2.6, self.content["title"], 54, t["text"],
                  font=self.fonts["title"], anchor=MSO_ANCHOR.BOTTOM, min_size=26)
        shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, MARGIN, 4.6, 1.6, 0.1, t["accent"], radius=0.5)
        shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, MARGIN + 1.75, 4.6, 0.5, 0.1, t["accent2"], radius=0.5)
        if self.content.get("subtitle"):
            self.text(slide, MARGIN, 4.9, title_w - 0.4, 1.0, self.content["subtitle"], 20, t["muted"], min_size=13)
        self.text(slide, MARGIN, 6.45, title_w, 0.4, self.cover_footer(), 14, t["text"],
                  font=self.fonts["heading"], min_size=10)

    def cover_footer(self):
        footer = str(datetime.now().year)
        if self.author:
            footer = f"{self.labels['author']}: {self.author}   •   {footer}"
        return footer

    # ----- Mundarija: bo'limlar va ular qaysi slaydlarda -----
    def contents_rows(self):
        rows, start = [(self.labels["plan"], "03")], 4
        for i, plan in enumerate(self.content["plans"], 1):
            end = start + len(plan["slides"]) - 1
            pages = f"{start:02d}" if start == end else f"{start:02d}–{end:02d}"
            rows.append((f"{i}. {plan['title']}", pages))
            start = end + 1
        rows.append((self.labels["conclusion"], f"{self.total:02d}"))
        return rows

    def contents_slide(self):
        t = self.theme
        slide = self.new_slide()
        y = self.heading(slide, self.labels["contents"])
        rows = self.contents_rows()
        columns = 1 if len(rows) <= 6 else 2
        per_col = math.ceil(len(rows) / columns)
        gap, col_gap = 0.14, 0.4
        col_w = (self.area_w - (columns - 1) * col_gap) / columns
        row_h = min(0.78, (H - 0.9 - y - (per_col - 1) * gap) / per_col)
        for i, (title, pages) in enumerate(rows):
            col, row = divmod(i, per_col)
            x, ry = MARGIN + col * (col_w + col_gap), y + row * (row_h + gap)
            color = t["accent"] if i % 2 == 0 else t["accent2"]
            self.card(slide, x, ry, col_w, row_h, i, radius=0.3)
            self.card_stripe(slide, x, ry, row_h, i)
            pill_w = 1.25
            self.text(slide, x + 0.35, ry + 0.06, col_w - pill_w - 0.6, row_h - 0.12, title, 18, self.ink,
                      font=self.fonts["heading"], anchor=MSO_ANCHOR.MIDDLE, min_size=11)
            shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x + col_w - pill_w - 0.15, ry + (row_h - 0.42) / 2,
                  pill_w, 0.42, color, radius=0.5)
            self.text(slide, x + col_w - pill_w - 0.15, ry + (row_h - 0.42) / 2, pill_w, 0.42, pages, 14, on_accent(t),
                      font=self.fonts["heading"], bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, auto=False)

    # ----- Reja -----
    def plan_slide(self):
        t = self.theme
        slide = self.new_slide()
        y = self.heading(slide, self.labels["plan"])
        plans = [p["title"] for p in self.content["plans"]]
        columns = 1 if len(plans) <= 5 else 2
        per_col = math.ceil(len(plans) / columns)
        gap = 0.18
        col_w = (self.area_w - (columns - 1) * 0.4) / columns
        row_h = min(0.95, (H - 0.9 - y - (per_col - 1) * gap) / per_col)
        for i, title in enumerate(plans):
            col, row = divmod(i, per_col)
            x = MARGIN + col * (col_w + 0.4)
            ry = y + row * (row_h + gap)
            self.card(slide, x, ry, col_w, row_h, i, radius=0.3)
            d = row_h - 0.24
            shape(slide, MSO_SHAPE.OVAL, x + 0.14, ry + 0.12, d, d, t["accent"] if i % 2 == 0 else t["accent2"])
            self.text(slide, x + 0.14, ry + 0.12, d, d, str(i + 1), int(d * 30), on_accent(t),
                      font=self.fonts["title"], align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, auto=False)
            self.text(slide, x + d + 0.4, ry + 0.08, col_w - d - 0.6, row_h - 0.16, title, 20, self.ink,
                      font=self.fonts["heading"], anchor=MSO_ANCHOR.MIDDLE, min_size=12)

    # ----- Kontent slaydlari -----
    def content_slide(self, plan_no, plan_title, data):
        image, video = data.get("image"), data.get("video")
        slide = self.new_slide(angle=135 if self.index % 2 else 45, image=image, video=video)
        y = self.heading(slide, data["title"], f"{plan_no}. {plan_title}")
        kind = data["kind"]
        # Tor joyga ko'p ustunli maketlar sig'maydi — rasmli slaydda ular ro'yxat ko'rinishida chiqadi
        if self.has_image and (kind in ("cards", "timeline") or (kind == "stats" and len(data["items"]) > 3)):
            kind = "bullets"
        getattr(self, f"layout_{kind}", self.layout_bullets)(slide, data, y)

    def layout_bullets(self, slide, data, y):
        t = self.theme
        y = self.intro(slide, data.get("text"), y)
        items = data["items"]
        columns = 2 if len(items) > 4 and not self.has_image else 1
        per_col = math.ceil(len(items) / columns)
        gap = 0.16
        col_w = (self.area_w - (columns - 1) * 0.35) / columns
        row_h = min(1.15, (H - 0.85 - y - (per_col - 1) * gap) / per_col)
        bodies = [f"{item['heading']}: {item['text']}" if item.get("heading") else item["text"] for item in items]
        # Barcha bandlar bir xil o'lchamda — eng uzun bandga sig'adigan shrift
        size = min(fit_size(body, col_w - 0.55, row_h - 0.2, 18, 10, self.fonts["body"]) for body in bodies)
        for i, (item, body) in enumerate(zip(items, bodies)):
            col, row = divmod(i, per_col)
            x = MARGIN + col * (col_w + 0.35)
            ry = y + row * (row_h + gap)
            self.card(slide, x, ry, col_w, row_h, i, alpha=0.8)
            self.card_stripe(slide, x, ry, row_h, i)
            box = self.text(slide, x + 0.35, ry + 0.1, col_w - 0.55, row_h - 0.2, body, size, self.ink,
                            anchor=MSO_ANCHOR.MIDDLE, auto=False)
            if item.get("heading"):  # sarlavha qismini qalin va rangli qilamiz
                run = box.text_frame.paragraphs[0].runs[0]
                run.text = item["heading"] + ": "
                run.font.bold = True
                run.font.color.rgb = rgb(t.get("item_heading") or (t["accent"] if t["dark"] else self.ink))
                tail = box.text_frame.paragraphs[0].add_run()
                tail.text = item["text"]
                tail.font.size, tail.font.name = run.font.size, self.fonts["body"]
                tail.font.color.rgb = rgb(self.ink)

    def layout_cards(self, slide, data, y):
        t = self.theme
        y = self.intro(slide, data.get("text"), y)
        items = data["items"]
        gap = 0.3
        n = len(items)
        card_w = (self.area_w - (n - 1) * gap) / n
        card_h = H - 0.85 - y
        for i, item in enumerate(items):
            x = MARGIN + i * (card_w + gap)
            color = t["accent"] if i % 2 == 0 else t["accent2"]
            self.card(slide, x, y, card_w, card_h, i, radius=0.08)
            shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x + 0.3, y, card_w - 0.6, 0.09, color, radius=0.5)
            shape(slide, MSO_SHAPE.OVAL, x + 0.3, y + 0.35, 0.7, 0.7, color)
            self.text(slide, x + 0.3, y + 0.35, 0.7, 0.7, f"{i + 1:02d}", 16, on_accent(t), font=self.fonts["title"],
                      align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, auto=False)
            self.text(slide, x + 0.3, y + 1.25, card_w - 0.6, 0.8, item.get("heading") or "", 20, self.ink,
                      font=self.fonts["heading"], bold=True, min_size=13)
            self.text(slide, x + 0.3, y + 2.1, card_w - 0.6, card_h - 2.3, item["text"], 16, self.ink_muted, min_size=10)

    def layout_stats(self, slide, data, y):
        t = self.theme
        y = self.intro(slide, data.get("text"), y)
        items = data["items"]
        gap = 0.35
        n = len(items)
        card_w = (self.area_w - (n - 1) * gap) / n
        card_h = min(3.6, H - 0.85 - y)
        y += (H - 0.85 - y - card_h) / 2
        for i, item in enumerate(items):
            x = MARGIN + i * (card_w + gap)
            color = t["accent"] if i % 2 == 0 else t["accent2"]
            self.card(slide, x, y, card_w, card_h, i, radius=0.1)
            shape(slide, MSO_SHAPE.OVAL, x + card_w - 0.75, y + 0.2, 0.45, 0.45, color, alpha=0.3)
            self.text(slide, x + 0.3, y + 0.4, card_w - 0.6, 1.4, item.get("heading") or "—", 54,
                      t.get("stat_color") or color, font=self.fonts["title"], anchor=MSO_ANCHOR.MIDDLE, min_size=20)
            shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x + 0.3, y + 1.95, 0.8, 0.07, color, radius=0.5)
            self.text(slide, x + 0.3, y + 2.2, card_w - 0.6, card_h - 2.4, item["text"], 16, self.ink, min_size=10)

    def layout_timeline(self, slide, data, y):
        t = self.theme
        y = self.intro(slide, data.get("text"), y)
        items = data["items"]
        n = len(items)
        line_y = y + 0.55
        step = self.area_w / n
        shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, MARGIN + step / 2, line_y - 0.03, step * (n - 1), 0.06,
              t["muted"], alpha=0.5, radius=0.5)
        for i, item in enumerate(items):
            cx = MARGIN + step * i + step / 2
            color = t["accent"] if i % 2 == 0 else t["accent2"]
            shape(slide, MSO_SHAPE.OVAL, cx - 0.45, line_y - 0.45, 0.9, 0.9, color, alpha=0.25)
            shape(slide, MSO_SHAPE.OVAL, cx - 0.32, line_y - 0.32, 0.64, 0.64, color)
            self.text(slide, cx - 0.32, line_y - 0.32, 0.64, 0.64, str(i + 1), 18, on_accent(t), font=self.fonts["title"],
                      align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, auto=False)
            box_w = step - 0.25
            top = line_y + 0.75
            self.card(slide, cx - box_w / 2, top, box_w, H - 0.85 - top, i, radius=0.1, alpha=0.8)
            self.text(slide, cx - box_w / 2 + 0.2, top + 0.2, box_w - 0.4, 0.75, item.get("heading") or "", 17,
                      self.ink, font=self.fonts["heading"], bold=True, align=PP_ALIGN.CENTER, min_size=11)
            self.text(slide, cx - box_w / 2 + 0.2, top + 1.0, box_w - 0.4, H - 0.85 - top - 1.2, item["text"], 14,
                      self.ink_muted, align=PP_ALIGN.CENTER, min_size=9)

    def layout_quote(self, slide, data, y):
        t = self.theme
        panel_h = H - 0.85 - y
        self.card(slide, MARGIN, y, self.area_w, panel_h, 0, radius=0.08, alpha=0.7)
        shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, MARGIN, y, 0.14, panel_h, t["accent"], radius=0.5)
        self.text(slide, MARGIN + 0.5, y - 0.35, 2, 1.8, "“", 150, t["accent2"], font=self.fonts["quote"], auto=False)
        self.text(slide, MARGIN + 1.3, y + 0.5, self.area_w - 2.4, panel_h - 1.5, data.get("text") or "", 30,
                  self.ink, font=self.fonts["quote"], italic=True, anchor=MSO_ANCHOR.MIDDLE, min_size=16)
        source = next((item.get("heading") or item["text"] for item in data["items"]), "")
        if source:
            self.text(slide, MARGIN + 1.3, y + panel_h - 0.85, self.area_w - 2.4, 0.5, f"— {source}", 16,
                      t.get("item_heading") or t["accent"], font=self.fonts["heading"], align=PP_ALIGN.RIGHT, auto=False)

    # ----- Xulosa -----
    def conclusion_slide(self):
        t = self.theme
        slide = self.new_slide(angle=60)
        y = self.heading(slide, self.labels["conclusion"])
        points = self.content["conclusion"][:5]
        band_h = 1.15
        area = H - 0.85 - band_h - 0.3 - y
        row_h = min(0.8, area / max(1, len(points)))
        for i, point in enumerate(points):
            ry = y + i * row_h
            shape(slide, MSO_SHAPE.OVAL, MARGIN, ry + row_h / 2 - 0.13, 0.26, 0.26,
                  t["accent"] if i % 2 == 0 else t["accent2"])
            self.text(slide, MARGIN + 0.5, ry, self.area_w - 0.5, row_h - 0.05, point, 18, t["text"],
                      anchor=MSO_ANCHOR.MIDDLE, min_size=11)
        band_y = H - 0.85 - band_h
        band = shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, MARGIN, band_y, self.area_w, band_h, t["accent"],
                     radius=0.3)
        band.fill.gradient()
        band.fill.gradient_angle = 0
        band.fill.gradient_stops[0].color.rgb = rgb(t["accent"])
        band.fill.gradient_stops[1].color.rgb = rgb(t["accent2"])
        self.text(slide, MARGIN, band_y, self.area_w, band_h, f"✨ {self.labels['thanks']}", 30, on_accent(t),
                  font=self.fonts["title"], align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, min_size=18)

    def build(self):
        self.title_slide()
        self.contents_slide()
        self.plan_slide()
        for no, plan in enumerate(self.content["plans"], 1):
            for data in plan["slides"]:
                self.content_slide(no, plan["title"], data)
        self.conclusion_slide()
        clean_properties(self.prs.core_properties, self.content["title"])
        buffer = io.BytesIO()
        self.prs.save(buffer)
        return buffer.getvalue()


def make_deck(content, theme_key, lang, author):
    """Mavzuga mos quruvchi: shablon (style) bo'lsa — o'z klassi, aks holda klassik Deck."""
    from presentation.styles import STYLES  # styles builder'dan meros oladi — aylanma import bo'lmasin

    style = THEMES.get(theme_key, {}).get("style")
    return STYLES.get(style, Deck)(content, theme_key, lang, author)


def build_outline_pptx(title, subtitle, slides, theme_key="business", lang="uz"):
    """AI yordamchi uchun ixcham taqdimot: muqova + ro'yxatli slaydlar (mundarija va reja slaydlarisiz).
    slides — [{"title": ..., "bullets": [...]}]; jami slaydlar = 1 + len(slides)."""
    deck = make_deck({"title": title, "subtitle": subtitle, "plans": [], "conclusion": []}, theme_key, lang, None)
    deck.total = 1 + len(slides)
    deck.title_slide()
    for data in slides:
        slide = deck.new_slide(angle=135 if deck.index % 2 else 45)
        y = deck.heading(slide, data["title"])
        items = [{"heading": "", "text": bullet} for bullet in data["bullets"]]
        deck.layout_bullets(slide, {"text": "", "items": items}, y)
    clean_properties(deck.prs.core_properties, title)
    buffer = io.BytesIO()
    deck.prs.save(buffer)
    return buffer.getvalue()


def build_pptx(content, theme_key, lang="uz", author=None):
    """Tayyor .pptx faylni bytes ko'rinishida qaytaradi.
    Rasmlar: content["cover_image"] va har bir slaydning "image" kaliti (JPEG/PNG bytes, ixtiyoriy).
    Video: slaydning "video" kaliti — {"path": fayl yo'li, "mime": "video/mp4"} (ixtiyoriy, web muharrirdan)."""
    return make_deck(content, theme_key, lang, author).build()
