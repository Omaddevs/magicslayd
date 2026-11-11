"""Shablonlar: Deck (builder.py) ilgaklarini o'z uslubida qayta yozadigan maketlar.
Maketlar (bullets, cards, stats, timeline, quote) umumiy — shablon faqat fon, sarlavha, karta, rasm ramkasi,
bezaklar, muqova va xulosani o'zgartiradi. Shuning uchun matn har doim tahrirlanadigan PowerPoint matni bo'lib qoladi.

- corporate — och lavanda fon, yashil urg'u, katta qalin sarlavhalar, yumaloq burchakli fotolar;
- doodle    — katakli daftar, pushti/yalpiz lentali sarlavhalar, qora konturli kartalar, qo'lda chizilgan bezaklar;
- vintage   — to'q eski qog'oz foni, yirtiq qog'oz kartalar, sepiya fotolar, serif shrift;
- baroque   — qora fon, butun slaydli rasm ustida qorong'ilashtirish, oltin ingichka chiziqlar, nafis serif."""
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn

from presentation import art
from presentation.builder import H, MARGIN, W, Deck, on_accent, overlay, picture, rgb, shape


def rounded(pic, share=0.08):
    """Rasm burchaklarini yumaloq qiladi (PowerPoint'da ham rasm bo'lib qoladi — almashtirish mumkin)."""
    pic.auto_shape_type = MSO_SHAPE.ROUNDED_RECTANGLE
    geometry = pic._element.spPr.find(qn("a:prstGeom"))
    av = geometry.find(qn("a:avLst"))
    if av is None:
        av = geometry.makeelement(qn("a:avLst"), {})
        geometry.append(av)
    av.append(av.makeelement(qn("a:gd"), {"name": "adj", "fmla": f"val {int(share * 100000)}"}))
    return pic


def outline(pic, color, width):
    pic.line.color.rgb = rgb(color)
    pic.line.width = int(width * 12700)
    return pic


def split_title(title):
    """Sarlavhani ikki qatorga (muqovadagi ikki lenta uchun) taxminan teng bo'ladi."""
    words = title.split()
    if len(words) < 2:
        return [title]
    best = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return [" ".join(words[:best]), " ".join(words[best:])]


# ===================================================================================================
class CorporateDeck(Deck):
    IMG = (8.25, 0.75, 4.35, 6.0)  # kontent slaydidagi rasm qutisi

    def background(self, slide, angle):
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = rgb(self.theme["bg"])
        # Ichki ingichka ramka — shablonning «varaq» ko'rinishi
        shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, 0.22, 0.22, W - 0.44, H - 0.44, None, radius=0.03,
              line="D2CFEC", line_width=1)

    def text_width(self):
        return self.IMG[0] - 0.45 - MARGIN

    def side_media(self, slide, image, video):
        x, y, w, h = self.IMG
        shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x + 0.25, y + 0.25, w, h, self.theme["accent"], alpha=0.18, radius=0.08)
        if video:
            self.movie(slide, video, x, y, w, h)
        else:
            rounded(picture(slide, image, x, y, w, h))

    def corner_badge(self, slide):
        t = self.theme
        shape(slide, MSO_SHAPE.OVAL, W - 0.95, 0.42, 0.48, 0.48, None, line=t["accent"], line_width=1.25)
        self.text(slide, W - 0.95, 0.42, 0.48, 0.48, "↗", 16, t["accent"], font=self.fonts["heading"],
                  align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, auto=False)

    def decorations(self, slide):
        if not self.has_image:
            self.corner_badge(slide)
        self.footer(slide)

    def heading(self, slide, title, tag=None):
        t = self.theme
        y = 0.6
        if tag:
            tag = tag if len(tag) <= 60 else tag[:59] + "…"
            width = min(self.area_w, 0.45 + len(tag) * 0.075)
            shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, MARGIN, y, width, 0.36, None, radius=0.5,
                  line=t["accent"], line_width=1)
            self.text(slide, MARGIN + 0.18, y + 0.06, width - 0.3, 0.26, tag, 11, t["accent"],
                      font=self.fonts["heading"], bold=True, auto=False)
            y += 0.55
        width = self.area_w if self.has_image else self.area_w - 0.9
        self.text(slide, MARGIN, y, width, 1.05, title, 38, t["accent"], font=self.fonts["title"],
                  anchor=MSO_ANCHOR.MIDDLE, min_size=20)
        return y + 1.3

    def card(self, slide, x, y, w, h, i=0, radius=0.22, alpha=0.85):
        return shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, "FFFFFF", radius=min(radius, 0.12),
                     line=self.theme["accent"] if i % 2 == 0 else "C9E8D5", line_width=1.25)

    def card_stripe(self, slide, x, y, h, i):
        shape(slide, MSO_SHAPE.OVAL, x + 0.12, y + h / 2 - 0.07, 0.14, 0.14, self.theme["accent"])

    def title_slide(self):
        t = self.theme
        image = self.content.get("cover_image")
        slide = self.new_slide(decorate=False)
        title_w = 6.6 if image else 9.5
        if image:
            shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, 7.75, 1.0, 4.9, 5.85, t["accent"], radius=0.07)
            rounded(picture(slide, image, 7.45, 0.65, 4.9, 5.85), 0.07)
        else:
            for d, a in ((5.2, 0.10), (3.4, 0.16), (1.6, 0.9)):
                shape(slide, MSO_SHAPE.OVAL, 10.0 - d / 2, 3.75 - d / 2, d, d, t["accent"], alpha=a)
        self.corner_badge(slide)
        shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, MARGIN, 1.05, 1.9, 0.4, t["accent"], radius=0.5)
        self.text(slide, MARGIN, 1.05, 1.9, 0.4, self.labels["badge"], 11, "FFFFFF", font=self.fonts["heading"],
                  bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, spacing=200, auto=False)
        self.text(slide, MARGIN, 1.7, title_w, 3.0, self.content["title"], 58, t["accent"],
                  font=self.fonts["title"], anchor=MSO_ANCHOR.MIDDLE, min_size=28)
        if self.content.get("subtitle"):
            self.text(slide, MARGIN, 4.85, title_w - 0.4, 0.95, self.content["subtitle"], 18, t["muted"], min_size=12)
        shape(slide, MSO_SHAPE.RECTANGLE, MARGIN, 6.2, title_w, 0.015, "C8C4E6")
        self.text(slide, MARGIN, 6.35, title_w, 0.4, self.cover_footer(), 13, t["text"],
                  font=self.fonts["heading"], min_size=10)

    def conclusion_slide(self):
        t = self.theme
        slide = self.new_slide()
        y = self.heading(slide, self.labels["conclusion"])
        points = self.content["conclusion"][:5]
        band_h = 1.1
        row_h = min(0.78, (H - 0.95 - band_h - 0.3 - y) / max(1, len(points)))
        for i, point in enumerate(points):
            ry = y + i * row_h
            shape(slide, MSO_SHAPE.OVAL, MARGIN, ry + row_h / 2 - 0.17, 0.34, 0.34, t["accent"])
            self.text(slide, MARGIN, ry + row_h / 2 - 0.17, 0.34, 0.34, "✓", 13, "FFFFFF", font=self.fonts["heading"],
                      align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, auto=False)
            self.text(slide, MARGIN + 0.55, ry, self.area_w - 0.6, row_h - 0.05, point, 18, t["text"],
                      anchor=MSO_ANCHOR.MIDDLE, min_size=11)
        band_y = H - 0.95 - band_h
        shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, MARGIN, band_y, self.area_w, band_h, t["accent"], radius=0.25)
        self.text(slide, MARGIN, band_y, self.area_w, band_h, self.labels["thanks"], 30, "FFFFFF",
                  font=self.fonts["title"], align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, min_size=18)


# ===================================================================================================
class DoodleDeck(Deck):
    IMG = (8.4, 1.15, 4.2, 5.2)
    INK = "141414"
    SPRITES = ("sparkle", "squiggle", "spiral", "swirl", "star", "arrow")

    def colors(self, i):
        t = self.theme
        return t["accent"] if i % 2 == 0 else t["accent2"]

    def background(self, slide, angle):
        overlay(slide, art.grid_paper(), 0, 0, W, H)

    def text_width(self):
        return self.IMG[0] - 0.5 - MARGIN

    def boxed(self, slide, x, y, w, h, color, shadow=None, offset=0.07, line=1.75, radius=None):
        """Qora konturli blok, ostida siljigan «soya» bloki — daftardagi stiker ko'rinishi."""
        kind = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
        shape(slide, kind, x + offset, y + offset, w, h, shadow or self.INK, radius=radius)
        return shape(slide, kind, x, y, w, h, color, radius=radius, line=self.INK, line_width=line)

    def sprite(self, slide, kind, x, y, size):
        overlay(slide, art.doodle(kind), x, y, size, size * {"squiggle": 0.29, "swirl": 0.52, "arrow": 0.61}.get(kind, 1))

    def side_media(self, slide, image, video):
        x, y, w, h = self.IMG
        shape(slide, MSO_SHAPE.RECTANGLE, x + 0.12, y + 0.12, w, h, self.colors(self.index))
        if video:
            self.movie(slide, video, x, y, w, h)
        else:
            outline(picture(slide, image, x, y, w, h), self.INK, 2.5)
        for i in range(7):  # daftar spirali
            shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x + 0.3 + i * (w - 0.6) / 6 - 0.05, y - 0.22, 0.1, 0.42,
                  self.INK, radius=0.5)

    def decorations(self, slide):
        kinds = self.SPRITES
        a, b = kinds[self.index % len(kinds)], kinds[(self.index + 2) % len(kinds)]
        if self.has_image:
            self.sprite(slide, a, 7.55, 6.35, 0.75)
        else:
            self.sprite(slide, a, W - 1.35, 0.35, 0.85)
            self.sprite(slide, b, W - 2.4, H - 1.05, 1.3)
        # Sahifa raqami — doiracha ichida
        shape(slide, MSO_SHAPE.OVAL, MARGIN - 0.1, H - 0.72, 0.5, 0.5, "FFFFFF", line=self.INK, line_width=1.5)
        self.text(slide, MARGIN - 0.1, H - 0.72, 0.5, 0.5, f"{self.index:02d}", 11, self.INK, font=self.fonts["title"],
                  align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, auto=False)

    def banner(self, slide, x, y, value, color, max_w, size=30, h=0.95):
        """Lenta-sarlavha: rangli to'rtburchak, qora kontur va soya."""
        w = min(max_w, 0.8 + len(value) * size * 0.0095)
        self.boxed(slide, x, y, w, h, color, offset=0.09, line=2.25)
        self.text(slide, x + 0.25, y + 0.06, w - 0.5, h - 0.12, value, size, self.INK, font=self.fonts["title"],
                  align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, min_size=14)
        return w

    def heading(self, slide, title, tag=None):
        y = 0.5
        if tag:
            tag = tag if len(tag) <= 55 else tag[:54] + "…"
            width = min(self.area_w, 0.5 + len(tag) * 0.085)
            self.boxed(slide, MARGIN, y, width, 0.38, self.theme["accent2"], offset=0.05, line=1.25, radius=0.5)
            self.text(slide, MARGIN + 0.2, y + 0.07, width - 0.35, 0.26, tag, 11, self.INK,
                      font=self.fonts["heading"], bold=True, auto=False)
            y += 0.62
        max_w = self.area_w if self.has_image else self.area_w - 1.3
        self.banner(slide, MARGIN, y, title, self.theme["accent"], max_w, 28)
        return y + 1.3

    def card(self, slide, x, y, w, h, i=0, radius=0.22, alpha=0.85):
        return self.boxed(slide, x, y, w, h, "FFFFFF", shadow=self.colors(i), offset=0.08)

    def card_stripe(self, slide, x, y, h, i):
        shape(slide, MSO_SHAPE.OVAL, x + 0.12, y + h / 2 - 0.08, 0.16, 0.16, self.colors(i), line=self.INK, line_width=1)

    def title_slide(self):
        t = self.theme
        image = self.content.get("cover_image")
        slide = self.new_slide(decorate=False)
        if image:
            self.side_media(slide, image, None)
            max_w, center = 7.0, MARGIN + 3.5
        else:
            max_w, center = 10.5, W / 2
        lines = split_title(self.content["title"])
        y = 3.0 - 0.55 * len(lines)
        badge_w = 2.3
        self.boxed(slide, center - badge_w / 2, y - 0.75, badge_w, 0.42, t["accent2"], offset=0.05, line=1.25, radius=0.5)
        self.text(slide, center - badge_w / 2, y - 0.75, badge_w, 0.42, self.labels["badge"], 12, self.INK,
                  font=self.fonts["heading"], bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
                  spacing=150, auto=False)
        for i, line in enumerate(lines):
            w = min(max_w, 0.9 + len(line) * 40 * 0.0095)
            self.banner(slide, center - w / 2 + (0.25 if i else -0.15), y, line, self.colors(i), max_w, 40, 1.2)
            y += 1.42
        if self.content.get("subtitle"):
            self.text(slide, center - max_w / 2, y + 0.05, max_w, 0.8, self.content["subtitle"], 17, t["muted"],
                      align=PP_ALIGN.CENTER, min_size=12)
        self.text(slide, center - max_w / 2, 6.55, max_w, 0.4, self.cover_footer(), 13, self.INK,
                  font=self.fonts["heading"], align=PP_ALIGN.CENTER, min_size=10)
        self.sprite(slide, "sparkle", 0.45, 0.4, 0.9)
        self.sprite(slide, "spiral", 0.5, 5.7, 1.0)
        self.sprite(slide, "star", (7.2 if image else W - 1.6), 0.55, 0.55)
        self.sprite(slide, "squiggle", (5.6 if image else W - 3.4), 6.75, 1.6)

    def conclusion_slide(self):
        t = self.theme
        slide = self.new_slide()
        y = self.heading(slide, self.labels["conclusion"])
        points = self.content["conclusion"][:5]
        band_h = 1.05
        gap = 0.16
        row_h = min(0.72, (H - 1.05 - band_h - 0.35 - y - gap * (len(points) - 1)) / max(1, len(points)))
        for i, point in enumerate(points):
            ry = y + i * (row_h + gap)
            self.card(slide, MARGIN, ry, self.area_w - 1.3, row_h, i)
            self.card_stripe(slide, MARGIN, ry, row_h, i)
            self.text(slide, MARGIN + 0.42, ry + 0.04, self.area_w - 1.9, row_h - 0.08, point, 16, self.INK,
                      anchor=MSO_ANCHOR.MIDDLE, min_size=10)
        self.banner(slide, MARGIN + 1.0, H - 1.05 - band_h, self.labels["thanks"], t["accent2"], self.area_w - 2.6, 26, band_h)


# ===================================================================================================
class VintageDeck(Deck):
    IMG = (8.15, 0.85, 4.45, 5.6)

    def background(self, slide, angle):
        t = self.theme
        overlay(slide, art.dark_texture(t["bg"], t["bg2"]), 0, 0, W, H)

    def text_width(self):
        return self.IMG[0] - 0.45 - MARGIN

    def frame(self, slide):
        t = self.theme
        shape(slide, MSO_SHAPE.RECTANGLE, 0.25, 0.25, W - 0.5, H - 0.5, None, line=t["accent"], line_width=0.75)
        shape(slide, MSO_SHAPE.RECTANGLE, 0.33, 0.33, W - 0.66, H - 0.66, None, line=t["accent2"], line_width=0.5)

    def photo(self, slide, image, x, y, w, h, angle):
        pic = overlay(slide, art.vintage_photo(image, w, h), x, y, w, h)
        pic.rotation = angle
        return pic

    def side_media(self, slide, image, video):
        x, y, w, h = self.IMG
        if video:
            self.movie(slide, video, x, y, w, h)
        else:
            self.photo(slide, image, x, y, w, h, 2.0 if self.index % 2 else -2.0)

    def decorations(self, slide):
        self.frame(slide)
        self.footer(slide)

    def ornament(self, slide, x, y, width):
        """Ingichka chiziq va o'rtasida romb — eski kitoblardagi bezak."""
        t = self.theme
        shape(slide, MSO_SHAPE.RECTANGLE, x, y, width, 0.02, t["accent"])
        shape(slide, MSO_SHAPE.DIAMOND, x + width / 2 - 0.09, y - 0.08, 0.18, 0.18, t["accent"])

    def heading(self, slide, title, tag=None):
        t = self.theme
        y = 0.55
        if tag:
            tag = tag if len(tag) <= 60 else tag[:59] + "…"
            self.text(slide, MARGIN, y, self.area_w, 0.3, tag.upper(), 11, t["accent"], font=self.fonts["heading"],
                      bold=True, spacing=200, auto=False)
            y += 0.42
        width = self.area_w if self.has_image else self.area_w - 0.6
        self.text(slide, MARGIN, y, width, 1.0, title.upper(), 34, t["text"], font=self.fonts["title"], bold=True,
                  anchor=MSO_ANCHOR.MIDDLE, min_size=18, spacing=50)
        self.ornament(slide, MARGIN, y + 1.12, 1.6)
        return y + 1.4

    def card(self, slide, x, y, w, h, i=0, radius=0.22, alpha=0.85):
        paper = art.torn_paper(round(w * 20) / 20, round(h * 20) / 20, self.theme["card"], i % 3)
        return overlay(slide, paper, x - 0.06, y - 0.06, w + 0.12, h + 0.12)

    def card_stripe(self, slide, x, y, h, i):
        shape(slide, MSO_SHAPE.DIAMOND, x + 0.11, y + h / 2 - 0.08, 0.16, 0.16, self.theme["accent2"])

    def title_slide(self):
        t = self.theme
        image = self.content.get("cover_image")
        slide = self.new_slide(decorate=False)
        self.frame(slide)
        paper_w = 7.3 if image else 10.0
        px = 0.75 if image else (W - paper_w) / 2
        overlay(slide, art.torn_paper(paper_w, 5.2, t["card"], 5), px, 1.15, paper_w, 5.2)
        if image:
            self.photo(slide, image, 8.0, 0.75, 4.7, 5.9, 3.0)
        inner_x, inner_w = px + 0.55, paper_w - 1.1
        self.text(slide, inner_x, 1.6, inner_w, 0.35, self.labels["badge"], 12, t["item_heading"],
                  font=self.fonts["heading"], bold=True, align=PP_ALIGN.CENTER, spacing=500, auto=False)
        self.text(slide, inner_x, 2.0, inner_w, 2.3, self.content["title"].upper(), 46, self.ink,
                  font=self.fonts["title"], bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, min_size=22)
        shape(slide, MSO_SHAPE.RECTANGLE, inner_x + inner_w / 2 - 1.2, 4.45, 2.4, 0.02, t["accent2"])
        shape(slide, MSO_SHAPE.DIAMOND, inner_x + inner_w / 2 - 0.09, 4.37, 0.18, 0.18, t["accent2"])
        if self.content.get("subtitle"):
            self.text(slide, inner_x, 4.65, inner_w, 0.75, self.content["subtitle"], 16, self.ink_muted,
                      font=self.fonts["body"], italic=True, align=PP_ALIGN.CENTER, min_size=11)
        self.text(slide, px, 6.55, paper_w, 0.4, self.cover_footer(), 13, t["text"], font=self.fonts["heading"],
                  align=PP_ALIGN.CENTER, min_size=10)

    def conclusion_slide(self):
        t = self.theme
        slide = self.new_slide()
        y = self.heading(slide, self.labels["conclusion"])
        points = self.content["conclusion"][:5]
        band_h = 1.1
        row_h = min(0.78, (H - 1.0 - band_h - 0.3 - y) / max(1, len(points)))
        for i, point in enumerate(points):
            ry = y + i * row_h
            shape(slide, MSO_SHAPE.DIAMOND, MARGIN, ry + row_h / 2 - 0.1, 0.2, 0.2, t["accent"])
            self.text(slide, MARGIN + 0.45, ry, self.area_w - 0.5, row_h - 0.05, point, 18, t["text"],
                      anchor=MSO_ANCHOR.MIDDLE, min_size=11)
        band_y = H - 1.0 - band_h
        band_w = min(self.area_w, 7.5)
        bx = MARGIN + (self.area_w - band_w) / 2
        overlay(slide, art.torn_paper(band_w, band_h, t["card"], 9), bx, band_y, band_w, band_h)
        self.text(slide, bx + 0.3, band_y, band_w - 0.6, band_h, self.labels["thanks"].upper(), 26, self.ink,
                  font=self.fonts["title"], bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, min_size=15)


# ===================================================================================================
class BaroqueDeck(Deck):
    def text_width(self):
        return 6.5

    def frame(self, slide):
        shape(slide, MSO_SHAPE.RECTANGLE, 0.3, 0.3, W - 0.6, H - 0.6, None, line=self.theme["accent"], line_width=0.5)

    def full_image(self, slide, image, fade=0.62):
        """Butun slaydli rasm va ustidan chapdan qorong'ilashtirish."""
        picture(slide, image, 0, 0, W, H)
        overlay(slide, art.side_fade(self.theme["bg"], fade), 0, 0, W, H)

    def side_media(self, slide, image, video):
        if video:
            self.movie(slide, video, 7.6, 0.75, 5.0, 6.0)
        else:
            self.full_image(slide, image)

    def decorations(self, slide):
        self.frame(slide)
        self.footer(slide)

    def gold_rule(self, slide, x, y, width):
        t = self.theme
        shape(slide, MSO_SHAPE.RECTANGLE, x, y, width, 0.015, t["accent"])
        shape(slide, MSO_SHAPE.DIAMOND, x + width + 0.06, y - 0.06, 0.13, 0.13, t["accent"])

    def heading(self, slide, title, tag=None):
        t = self.theme
        y = 0.65
        if tag:
            tag = tag if len(tag) <= 60 else tag[:59] + "…"
            self.text(slide, MARGIN, y, self.area_w, 0.3, tag.upper(), 10, t["accent"], font=self.fonts["heading"],
                      spacing=300, auto=False)
            y += 0.42
        width = self.area_w if self.has_image else self.area_w - 0.6
        self.text(slide, MARGIN, y, width, 1.0, title, 36, t["text"], font=self.fonts["title"],
                  anchor=MSO_ANCHOR.MIDDLE, min_size=20)
        self.gold_rule(slide, MARGIN, y + 1.1, 1.3)
        return y + 1.4

    def card(self, slide, x, y, w, h, i=0, radius=0.22, alpha=0.85):
        return shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, self.theme["card"], alpha=0.62,
                     radius=min(radius, 0.05), line=self.theme["accent"] if i % 2 == 0 else self.theme["accent2"],
                     line_width=0.75)

    def card_stripe(self, slide, x, y, h, i):
        shape(slide, MSO_SHAPE.DIAMOND, x + 0.11, y + h / 2 - 0.065, 0.13, 0.13, self.theme["accent"])

    def title_slide(self):
        t = self.theme
        image = self.content.get("cover_image")
        slide = self.new_slide(decorate=False)
        if image:
            self.full_image(slide, image, 0.7)
        else:
            for d in (6.2, 4.6, 3.0):
                shape(slide, MSO_SHAPE.OVAL, 9.6 - d / 2, 3.75 - d / 2, d, d, None, line=t["accent"], line_width=0.75)
        self.frame(slide)
        self.text(slide, MARGIN + 0.2, 1.35, 6.5, 0.35, self.labels["badge"], 12, t["accent"],
                  font=self.fonts["heading"], spacing=500, auto=False)
        self.text(slide, MARGIN + 0.2, 1.8, 7.0, 2.7, self.content["title"], 52, t["text"], font=self.fonts["title"],
                  anchor=MSO_ANCHOR.BOTTOM, min_size=26)
        self.gold_rule(slide, MARGIN + 0.2, 4.7, 2.2)
        if self.content.get("subtitle"):
            self.text(slide, MARGIN + 0.2, 4.95, 6.5, 0.95, self.content["subtitle"], 18, t["muted"],
                      font=self.fonts["quote"], italic=True, min_size=12)
        self.text(slide, MARGIN + 0.2, 6.35, 6.5, 0.4, self.cover_footer(), 13, t["accent"],
                  font=self.fonts["heading"], min_size=10)

    def conclusion_slide(self):
        t = self.theme
        image = self.content.get("cover_image")
        slide = self.new_slide(image=image)
        y = self.heading(slide, self.labels["conclusion"])
        points = self.content["conclusion"][:5]
        thanks_h = 1.0
        row_h = min(0.8, (H - 1.0 - thanks_h - 0.3 - y) / max(1, len(points)))
        numerals = ("I", "II", "III", "IV", "V")
        for i, point in enumerate(points):
            ry = y + i * row_h
            self.text(slide, MARGIN, ry, 0.6, row_h - 0.05, numerals[i], 18, t["accent"], font=self.fonts["title"],
                      anchor=MSO_ANCHOR.MIDDLE, auto=False)
            self.text(slide, MARGIN + 0.65, ry, self.area_w - 0.7, row_h - 0.05, point, 17, t["text"],
                      anchor=MSO_ANCHOR.MIDDLE, min_size=11)
        self.text(slide, MARGIN, H - 1.0 - thanks_h, self.area_w, thanks_h, self.labels["thanks"], 34, t["accent"],
                  font=self.fonts["quote"], italic=True, anchor=MSO_ANCHOR.MIDDLE, min_size=18)


# ===================================================================================================
class NatureDeck(Deck):
    """Ko'rinishi sozlanadigan shablonlar oilasi (tabiat — style "nature", tarix — style "heritage").
    Ko'rinish theme["look"] dan olinadi (themes.py):
    media — rasm qanday turadi: panel (yumaloq burchakli katta panel), circle (doira, ortida quyosh),
            full (butun slayd, chapdan qorong'ilashadi), framed (to'g'ri burchak, ortida rangli blok),
            rounded (urg'u rangli hoshiyali), arch (tepasi arka), gold (ingichka oltin ramka ichida),
            fade (o'ng yarmida, chetidan fonga singib ketadi), plain (oddiy to'g'ri burchak);
    decor — bezak: leaf, sun, gold, peak, leaves (tabiat); ornament (bezakli ingichka chiziqlar va romb),
            stars (to'rt qirrali yulduzchalar), frame (saroy ramkasi — ikki qavat chiziq, burchaklarda romb);
    card — solid | outline | glass | frame (faqat ingichka chiziq); tone — sepia | mono (foto toni);
    texture — parchment | marble (fon); tag — pill (bo'lim nomi rangli tugmachada); italic — kursiv sarlavhalar;
    cover — full (butun slaydli foto) | side (foto o'ngda, media shaklida); band — solid | outline (xulosadagi
    «rahmat» bloki); upper — katta harflar.
    Muqova: foto ustida yirik sarlavha (rasm bo'lmasa — bezak kompozitsiya)."""
    BOXES = {
        "panel": (7.95, 0.45, 4.93, 6.6),
        "circle": (8.05, 1.3, 4.7, 4.7),
        "framed": (8.05, 0.8, 4.5, 5.9),
        "rounded": (8.1, 0.8, 4.45, 5.9),
        "arch": (8.2, 0.75, 4.3, 6.0),
        "gold": (8.05, 0.85, 4.5, 5.8),
        "plain": (7.9, 0.6, 4.9, 6.3),
        "slant": (7.8, 0.6, 5.0, 6.3),
        "snip": (8.05, 0.8, 4.6, 5.9),
    }
    SLANT = 0.15  # qiya foto: yuqori chap va pastki o'ng tomoni kenglikning shu ulushiga siljigan
    SPORT = ("slash", "corner", "cross", "arc", "shard", "glow", "line")  # sport bezaklari — sarlavha ostida to'g'ri burchakli qalin chiziq
    FADE_X = 6.4  # media "fade": rasm shu nuqtadan o'ngda

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.look = self.theme.get("look", {})

    def toned(self, image):
        return art.toned(image, self.look.get("tone")) if image else image

    def italic(self):
        return bool(self.look.get("italic"))

    @property
    def media_kind(self):
        return self.look.get("media", "panel")

    def up(self, value):
        return value.upper() if self.look.get("upper") else value

    def title_color(self):
        return self.theme["accent"] if self.look.get("title_color") == "accent" else self.theme["text"]

    # ----- Fon va rasm -----
    def background(self, slide, angle):
        t = self.theme
        if self.look.get("texture"):
            overlay(slide, art.texture(self.look["texture"], t["bg"], t["bg2"]), 0, 0, W, H)
            return
        fill = slide.background.fill
        if t["bg"] == t["bg2"]:
            fill.solid()
            fill.fore_color.rgb = rgb(t["bg"])
            return
        fill.gradient()
        fill.gradient_angle = angle
        fill.gradient_stops[0].color.rgb = rgb(t["bg"])
        fill.gradient_stops[1].color.rgb = rgb(t["bg2"])

    def text_width(self):
        if self.media_kind == "full":
            return 6.4
        if self.media_kind == "fade":
            return self.FADE_X - 0.4 - MARGIN
        return self.BOXES[self.media_kind][0] - 0.5 - MARGIN

    def side_media(self, slide, image, video):
        t, kind = self.theme, self.media_kind
        image = self.toned(image)
        if kind in ("full", "fade"):
            if video:
                self.movie(slide, video, 7.6, 0.75, 5.0, 6.0)
                return
            if kind == "full":
                picture(slide, image, 0, 0, W, H)
                overlay(slide, art.side_fade(t["bg"], 0.62), 0, 0, W, H)
            else:  # o'ng yarmida, chap cheti fonga silliq singib ketadi
                picture(slide, image, self.FADE_X, 0, W - self.FADE_X, H)
                overlay(slide, art.edge_fade(t["bg"]), self.FADE_X - 0.02, 0, 3.0, H)
            return
        x, y, w, h = self.BOXES[kind]
        if kind == "gold":
            shape(slide, MSO_SHAPE.RECTANGLE, x - 0.15, y - 0.15, w + 0.3, h + 0.3, None, line=t["accent"], line_width=0.75)
        if kind == "circle":
            if self.look.get("no_sun"):  # texno uslub: faqat ikki qavat halqa
                shape(slide, MSO_SHAPE.OVAL, x - 0.18, y - 0.18, w + 0.36, h + 0.36, None, line=t["accent"], line_width=2.5)
            else:
                star = shape(slide, MSO_SHAPE.STAR_24_POINT, x - 0.55, y - 0.65, 2.3, 2.3, t["accent"])
                star.rotation = 8
                shape(slide, MSO_SHAPE.OVAL, x + 0.22, y + 0.22, w, h, None, line=t["accent"], line_width=2)
        elif kind == "framed":
            shape(slide, MSO_SHAPE.RECTANGLE, x - 0.25, y + 0.25, w, h, t["accent"], alpha=0.85)
        if video:
            self.movie(slide, video, x, y, w, h)
            return
        pic = picture(slide, image, x, y, w, h)
        if kind == "circle":
            pic.auto_shape_type = MSO_SHAPE.OVAL
        elif kind == "panel":
            rounded(pic, 0.06)
        elif kind == "rounded":
            outline(rounded(pic, 0.07), t["accent"], 3)
        elif kind == "arch":
            arch(pic)
            outline(pic, t["accent"], 1)
        elif kind == "gold":
            outline(pic, t["accent"], 1.5)
        elif kind == "slant":  # parallelogramm — harakat, tezlik
            geometry(pic, MSO_SHAPE.PARALLELOGRAM, adj=int(self.SLANT * w / min(w, h) * 100000))
        elif kind == "snip":  # sakkiz burchak — kibersport, «ekran» ko'rinishi
            geometry(pic, MSO_SHAPE.OCTAGON, adj=16000)
            outline(pic, t["accent"], 1.5)

    # ----- Bezaklar -----
    def ornament_line(self, slide, x, y, width):
        """Ingichka chiziq va o'rtasida kichik romb — eski kitob bezagi."""
        t = self.theme
        shape(slide, MSO_SHAPE.RECTANGLE, x, y, width, 0.015, t["accent"])
        shape(slide, MSO_SHAPE.DIAMOND, x + width / 2 - 0.07, y - 0.065, 0.14, 0.14, t["accent"])

    def stars(self, slide, x, y, n=3, size=0.16):
        for i in range(n):
            shape(slide, MSO_SHAPE.STAR_4_POINT, x + i * (size + 0.1), y, size, size, self.theme["accent"])

    def palace_frame(self, slide):
        t = self.theme
        shape(slide, MSO_SHAPE.RECTANGLE, 0.22, 0.22, W - 0.44, H - 0.44, None, line=t["accent"], line_width=1.25)
        shape(slide, MSO_SHAPE.RECTANGLE, 0.32, 0.32, W - 0.64, H - 0.64, None, line=t["accent2"], line_width=0.5)
        for cx, cy in ((0.22, 0.22), (W - 0.22, 0.22), (0.22, H - 0.22), (W - 0.22, H - 0.22)):
            shape(slide, MSO_SHAPE.DIAMOND, cx - 0.1, cy - 0.1, 0.2, 0.2, t["accent"])
    def leaf_mark(self, slide, x, y, size, color=None, angle=-35):
        overlay(slide, art.leaf(color or self.theme["accent"], 1.0, angle), x, y, size, size)

    def decorations(self, slide):
        t, decor = self.theme, self.look.get("decor")
        free = not self.has_image
        if decor == "leaf":
            self.leaf_mark(slide, W - 0.95 if free else MARGIN + self.area_w - 0.3, 0.3, 0.5)
            shape(slide, MSO_SHAPE.RECTANGLE, 0, 0, W, 0.09, t["accent"])
        elif decor == "sun" and free:  # o'ng yuqori burchakda, yarmi slayddan tashqarida — matnga tegmaydi
            star = shape(slide, MSO_SHAPE.STAR_24_POINT, W - 1.25, -1.05, 2.3, 2.3, t["accent"])
            star.rotation = 12
        elif decor == "gold":
            shape(slide, MSO_SHAPE.RECTANGLE, MARGIN, 0.38, 0.9, 0.025, t["accent"])
        elif decor == "peak" and free:
            for x, w, h, a in ((W - 6.2, 5.0, 2.4, 0.07), (W - 4.0, 4.6, 3.1, 0.1), (W - 2.2, 3.4, 1.9, 0.08)):
                shape(slide, MSO_SHAPE.ISOSCELES_TRIANGLE, x, H - h, w, h, t["accent"], alpha=a)
        elif decor == "leaves":
            if free:
                overlay(slide, art.leaf(t["accent2"], 0.22, 35), W - 2.6, -0.9, 3.4, 3.4)
                overlay(slide, art.leaf(t["accent"], 0.16, -140), -1.2, H - 2.0, 3.0, 3.0)
            else:
                overlay(slide, art.leaf(t["accent2"], 0.18, -140), -1.0, H - 1.7, 2.6, 2.6)
        elif decor == "ornament":
            self.ornament_line(slide, MARGIN, 0.36, self.area_w)
            shape(slide, MSO_SHAPE.RECTANGLE, MARGIN, H - 0.72, self.area_w, 0.012, t["accent"])
        elif decor == "stars":
            self.stars(slide, MARGIN, 0.3)
            if free:  # o'ng yuqori burchakda — kartalar va raqamlarga tegmaydi
                self.stars(slide, W - MARGIN - 0.62, 0.3)
        elif decor == "frame":
            self.palace_frame(slide)
        elif decor == "slash":
            self.slashes(slide, (W - 1.75) if free else (MARGIN + self.area_w - 0.95), 0.42)
            if self.look.get("glow"):
                overlay(slide, art.glow(t["accent"]), W - 4.2 if free else -2.4, -2.6, 5.2, 5.2)
        elif decor == "corner":  # pastki chap uchburchak pastdagi yozuvga tegmaydigan kattalikda (1.15")
            shape(slide, MSO_SHAPE.RIGHT_TRIANGLE, 0, H - 1.15, 1.15, 1.15, t["accent"])
            if free:
                tri = shape(slide, MSO_SHAPE.RIGHT_TRIANGLE, W - 1.6, 0, 1.6, 1.6, t["accent"])
                tri.rotation = 180
        elif decor == "cross":
            if free:
                shape(slide, MSO_SHAPE.MATH_PLUS, W - 1.3, 0.5, 0.32, 0.32, t["accent"])
                shape(slide, MSO_SHAPE.MATH_PLUS, W - 0.75, 1.1, 0.2, 0.2, t["accent"])
            shape(slide, MSO_SHAPE.RECTANGLE, 0, 0, 0.09, H, t["accent"])
        elif decor == "shard" and free:
            self.shards(slide, 0.75)
        elif decor == "glow":
            overlay(slide, art.glow(t["accent"], 0.5), W - 4.0 if free else -2.6, -2.6, 5.2, 5.2)
        elif decor == "arc":
            shape(slide, MSO_SHAPE.DONUT, W - 1.3, -1.3, 2.6, 2.6, t["accent"]).adjustments[0] = 0.13
            if free:  # burchakda kichik halqa
                shape(slide, MSO_SHAPE.DONUT, -0.9, H - 0.9, 1.8, 1.8, t["accent"]).adjustments[0] = 0.15
        self.footer(slide, color=t["muted"])

    def footer(self, slide, color=None):
        """Pastki chap burchakda bezak (uchburchak, halqa) bo'lsa — taqdimot nomi undan o'ngroqdan boshlanadi."""
        if self.look.get("decor") not in ("corner", "arc"):
            return super().footer(slide, color)
        color = color or self.theme["muted"]
        right = (MARGIN + self.area_w + 0.1) if self.has_image else (W - MARGIN)
        self.text(slide, right - 1.6, H - 0.55, 1.6, 0.3, f"{self.index:02d} / {self.total:02d}",
                  11, color, font=self.fonts["heading"], align=PP_ALIGN.RIGHT, auto=False)
        left = 1.35
        topic = " ".join(self.content["title"].split())
        self.text(slide, left, H - 0.55, right - left - 2.0, 0.3, topic[:80], 11, color, auto=False)

    def shards(self, slide, scale=1.0):
        """Biznes bezagi: o'ng yuqori burchakda bir-birini qoplagan diagonal bloklar (ikki rang)."""
        t = self.theme
        for dx, w, color, alpha in ((0.0, 2.2, t["accent2"], 0.9), (0.95, 1.6, t["accent"], 1.0), (1.85, 1.1, t["accent2"], 0.55)):
            block = shape(slide, MSO_SHAPE.PARALLELOGRAM, W - 3.3 * scale + dx * scale, -0.2, w * scale, 1.5 * scale,
                          color, alpha=alpha)
            block.adjustments[0] = 0.5

    def slashes(self, slide, x, y, n=3):
        """/// — sportdagi tezlik belgisi: qiya qalin chiziqlar."""
        for i in range(n):
            bar = shape(slide, MSO_SHAPE.PARALLELOGRAM, x + i * 0.26, y, 0.32, 0.36, self.theme["accent"])
            bar.adjustments[0] = 0.55

    # ----- Sarlavha va kartalar -----
    def heading(self, slide, title, tag=None):
        t = self.theme
        y = 0.6
        if tag:
            tag = tag if len(tag) <= 60 else tag[:59] + "…"
            if self.look.get("tag") == "block":  # to'g'ri burchakli urg'u rangli yorliq (sport)
                per_char = 0.105 if self.fonts["heading"] == "Georgia" else 0.085  # serif katta harflar kengroq
                width = min(self.area_w, 0.5 + len(tag) * per_char)
                shape(slide, MSO_SHAPE.RECTANGLE, MARGIN, y, width, 0.36, t["accent"])
                self.text(slide, MARGIN + 0.18, y + 0.06, width - 0.3, 0.26, tag.upper(), 10.5, on_accent(t),
                          font=self.fonts["heading"], bold=True, auto=False)
            elif self.look.get("decor") == "leaves" or self.look.get("tag") == "pill":
                width = min(self.area_w, 0.5 + len(tag) * 0.08)
                shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, MARGIN, y, width, 0.38, t["accent"], radius=0.5)
                self.text(slide, MARGIN + 0.2, y + 0.07, width - 0.3, 0.26, tag, 11, on_accent(t),
                          font=self.fonts["heading"], bold=True, auto=False)
            else:
                shape(slide, MSO_SHAPE.RECTANGLE, MARGIN, y + 0.14, 0.35, 0.03, t["accent"])
                self.text(slide, MARGIN + 0.5, y, self.area_w - 0.5, 0.3, tag.upper(), 10.5, t["accent"],
                          font=self.fonts["heading"], bold=True, spacing=150, auto=False)
            y += 0.5
        width = self.area_w if self.has_image else self.area_w - 0.9
        # Katta harflar kengroq — shrift o'lchami hisobidan kichikroq boshlanadi (aks holda qutidan chiqib ketadi)
        size = 31 if self.look.get("upper") else 36
        self.text(slide, MARGIN, y, width, 1.0, self.up(title), size, self.title_color(), font=self.fonts["title"],
                  bold=self.look.get("bold_title", False), italic=self.italic(), anchor=MSO_ANCHOR.MIDDLE, min_size=20)
        if self.look.get("decor") in ("ornament", "stars", "frame"):
            self.ornament_line(slide, MARGIN, y + 1.1, 1.4)
        elif self.look.get("decor") in self.SPORT:
            shape(slide, MSO_SHAPE.RECTANGLE, MARGIN, y + 1.07, 1.0, 0.1, t["accent"])
        else:
            shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, MARGIN, y + 1.08, 0.9, 0.07, t["accent"], radius=0.5)
        return y + 1.38

    def card(self, slide, x, y, w, h, i=0, radius=0.22, alpha=0.85):
        t, style = self.theme, self.look.get("card", "solid")
        radius = min(radius, 0.1)
        if style == "outline":
            return shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, t["card"], radius=radius,
                         line=t["accent"] if i % 2 == 0 else t["accent2"], line_width=1.25)
        if style == "glass":
            return shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, t["card"], alpha=0.72, radius=radius,
                         line=t["accent2"], line_width=0.75)
        if style == "frame":  # faqat ingichka chiziq, ichi shaffofroq — nafis ko'rinish
            return shape(slide, MSO_SHAPE.RECTANGLE, x, y, w, h, t["card"], alpha=0.45, line=t["accent"], line_width=0.75)
        return shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, t["card"], radius=radius)

    def card_stripe(self, slide, x, y, h, i):
        t = self.theme
        color = t["accent"] if i % 2 == 0 else t["accent2"]
        if self.look.get("decor") in ("ornament", "frame"):
            shape(slide, MSO_SHAPE.DIAMOND, x + 0.11, y + h / 2 - 0.07, 0.14, 0.14, t["accent"])
        elif self.look.get("decor") == "stars":
            shape(slide, MSO_SHAPE.STAR_4_POINT, x + 0.09, y + h / 2 - 0.09, 0.18, 0.18, t["accent"])
        elif self.look.get("decor") in ("leaf", "leaves"):
            overlay(slide, art.leaf(color, 1.0, -35, False), x + 0.06, y + h / 2 - 0.13, 0.26, 0.26)
        elif self.look.get("decor") == "sun":
            shape(slide, MSO_SHAPE.STAR_12_POINT, x + 0.1, y + h / 2 - 0.1, 0.2, 0.2, color)
        else:
            shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y + 0.12, 0.08, h - 0.24, color, radius=0.5)

    # ----- Muqova -----
    def title_slide(self):
        t, decor = self.theme, self.look.get("decor")
        image = self.content.get("cover_image")
        slide = self.new_slide(angle=120, decorate=False)
        ink = t["text"]
        side = bool(image) and self.look.get("cover") == "side"
        if decor == "frame":
            self.palace_frame(slide)
        if side:  # foto o'ngda, kontent slaydlaridagi shaklda (arka, oltin ramka, so'nuvchi...)
            self.side_media(slide, image, None)
            image = None  # quyida matn — oddiy fon ustida
        elif image:  # butun slaydli foto
            picture(slide, self.toned(image), 0, 0, W, H)
            fade = self.look.get("cover_fade", t["bg"])
            overlay(slide, art.side_fade(fade, 0.75), 0, 0, W, H)
            ink = self.look.get("cover_text", t["text"])
        elif decor in ("ornament", "stars", "frame"):
            self.ornament_line(slide, 8.4, 3.75, 3.6)
            self.stars(slide, 9.85, 2.9, 3, 0.22)
        elif decor in ("leaf", "leaves"):
            overlay(slide, art.leaf(t["accent"], 0.9, 25), 8.2, 0.6, 5.6, 5.6)
            overlay(slide, art.leaf(t["accent2"], 0.75, -20), 7.0, 2.6, 4.0, 4.0)
        elif decor == "sun":
            star = shape(slide, MSO_SHAPE.STAR_24_POINT, 8.3, 1.3, 4.8, 4.8, t["accent"])
            star.rotation = 10
        elif decor == "peak":
            for x, w, h, a in ((5.2, 6.4, 4.4, 0.35), (7.6, 5.8, 5.6, 0.6), (10.0, 4.0, 3.6, 0.9)):
                shape(slide, MSO_SHAPE.ISOSCELES_TRIANGLE, x, H - h, w, h, t["accent"], alpha=a)
        else:
            for d, a in ((5.6, 0.12), (3.8, 0.2), (2.0, 0.9)):
                shape(slide, MSO_SHAPE.OVAL, 10.0 - d / 2, 3.75 - d / 2, d, d, t["accent"], alpha=a)
        # Sport bezaklari muqovada ham (foto ustida)
        if decor == "slash":
            self.slashes(slide, W - 1.75, 0.5)
            if self.look.get("glow"):
                overlay(slide, art.glow(t["accent"], 0.45), -2.6, H - 2.6, 5.2, 5.2)
        elif decor == "corner":
            shape(slide, MSO_SHAPE.RIGHT_TRIANGLE, 0, H - 1.15, 1.15, 1.15, t["accent"])
        elif decor == "shard":
            self.shards(slide, 1.0)
        elif decor == "glow":
            overlay(slide, art.glow(t["accent"], 0.5), -2.6, H - 2.6, 5.2, 5.2)
        elif decor == "arc":
            shape(slide, MSO_SHAPE.DONUT, W - 1.6, -1.6, 3.2, 3.2, t["accent"]).adjustments[0] = 0.13
        elif decor == "cross":
            shape(slide, MSO_SHAPE.RECTANGLE, 0, 0, 0.09, H, t["accent"])
            shape(slide, MSO_SHAPE.MATH_PLUS, W - 1.2, 0.5, 0.36, 0.36, t["accent"])
        title_w = self.FADE_X - MARGIN - 0.2 if side and self.media_kind == "fade" else 7.1 if side else 7.4
        # Fotoli muqovada och temaning to'q urg'usi ko'rinmaydi — ochroq ikkinchi urg'u rangi
        mark = self.look.get("cover_mark") or (t["accent2"] if image and not t["dark"] else t["accent"])
        shape(slide, MSO_SHAPE.RECTANGLE, MARGIN, 1.42, 0.5, 0.04, mark)
        self.text(slide, MARGIN + 0.65, 1.28, 6, 0.35, self.labels["badge"], 13, mark,
                  font=self.fonts["heading"], bold=True, spacing=400, auto=False)
        upper = self.look.get("upper")
        self.text(slide, MARGIN, 1.85, title_w, 2.85, self.up(self.content["title"]), 44 if upper else 58, ink,
                  font=self.fonts["title"], bold=self.look.get("bold_title", False), italic=self.italic(),
                  anchor=MSO_ANCHOR.BOTTOM, min_size=22 if upper else 28)
        if decor in ("ornament", "stars", "frame"):
            self.ornament_line(slide, MARGIN, 4.95, 2.2)
        elif decor in self.SPORT:
            shape(slide, MSO_SHAPE.RECTANGLE, MARGIN, 4.88, 1.6, 0.12, mark)
        else:
            shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, MARGIN, 4.9, 1.5, 0.09, mark, radius=0.5)
        if self.content.get("subtitle"):
            self.text(slide, MARGIN, 5.15, title_w - 0.4, 0.9, self.content["subtitle"], 19,
                      ink if image else t["muted"], min_size=12)
        self.text(slide, MARGIN, 6.5, title_w, 0.4, self.cover_footer(), 13, ink, font=self.fonts["heading"], min_size=10)

    # ----- Xulosa -----
    def conclusion_slide(self):
        t = self.theme
        slide = self.new_slide(angle=60)
        y = self.heading(slide, self.labels["conclusion"])
        points = self.content["conclusion"][:5]
        band_h = 1.1
        row_h = min(0.8, (H - 0.95 - band_h - 0.3 - y) / max(1, len(points)))
        for i, point in enumerate(points):
            ry = y + i * row_h
            self.card_stripe(slide, MARGIN - 0.06, ry + row_h / 2 - 0.25, 0.5, i)
            self.text(slide, MARGIN + 0.45, ry, self.area_w - 0.5, row_h - 0.05, point, 18, t["text"],
                      anchor=MSO_ANCHOR.MIDDLE, min_size=11)
        band_y = H - 0.95 - band_h
        if self.look.get("band") == "outline":  # nafis: ingichka ramka, ichida urg'u rangli (kursiv) yozuv
            shape(slide, MSO_SHAPE.RECTANGLE, MARGIN, band_y, self.area_w, band_h, None, line=t["accent"], line_width=1)
            shape(slide, MSO_SHAPE.RECTANGLE, MARGIN + 0.08, band_y + 0.08, self.area_w - 0.16, band_h - 0.16, None,
                  line=t["accent2"], line_width=0.5)
            color = t["accent"]
        else:
            shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, MARGIN, band_y, self.area_w, band_h, t["accent"], radius=0.12)
            color = on_accent(t)
        self.text(slide, MARGIN, band_y, self.area_w, band_h, self.up(self.labels["thanks"]), 28, color,
                  font=self.fonts["title"], bold=self.look.get("bold_title", False), italic=self.italic(),
                  align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, min_size=16)


def geometry(pic, kind, adj=None):
    """Rasm shaklini o'zgartiradi (parallelogramm, sakkiz burchak...) — PowerPoint'da rasm bo'lib qoladi."""
    pic.auto_shape_type = kind
    if adj is not None:
        geom = pic._element.spPr.find(qn("a:prstGeom"))
        av = geom.find(qn("a:avLst"))
        if av is None:
            av = geom.makeelement(qn("a:avLst"), {})
            geom.append(av)
        av.append(av.makeelement(qn("a:gd"), {"name": "adj", "fmla": f"val {adj}"}))
    return pic


def arch(pic):
    """Rasm shakli — arka (tepa burchaklari to'liq yumaloq). PowerPoint'da rasm bo'lib qoladi."""
    pic.auto_shape_type = MSO_SHAPE.ROUND_2_SAME_RECTANGLE
    geometry = pic._element.spPr.find(qn("a:prstGeom"))
    av = geometry.find(qn("a:avLst"))
    if av is None:
        av = geometry.makeelement(qn("a:avLst"), {})
        geometry.append(av)
    for name, value in (("adj1", 50000), ("adj2", 0)):
        av.append(av.makeelement(qn("a:gd"), {"name": name, "fmla": f"val {value}"}))
    return pic


STYLES = {"corporate": CorporateDeck, "doodle": DoodleDeck, "vintage": VintageDeck, "baroque": BaroqueDeck,
          "nature": NatureDeck, "heritage": NatureDeck, "sport": NatureDeck, "office": NatureDeck,
          "edu": NatureDeck, "tech": NatureDeck, "art": NatureDeck,
          "med": NatureDeck, "law": NatureDeck}
