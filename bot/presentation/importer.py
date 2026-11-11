"""Tayyor PPTX yoki PDF dan muharrir loyihasini tiklaydi (web ilovadagi «tahrirlash» uchun).

Ikki holat:
- botning o'zi yasagan eski taqdimotlar (loyihasi saqlanmagan) — tuzilma deyarli to'liq tiklanadi:
  muqova, reja, «1. Reja nomi» belgili slaydlar, xulosa;
- foydalanuvchi yuklagan istalgan taqdimot — har bir slayddan sarlavha, matn va eng katta rasm olinadi,
  dizayn esa botning mavzularidan biriga o'tadi.

PPTX va PDF avval bir xil ko'rinishga keltiriladi (Box — matn bloki: o'lcham, qalinlik, joylashuv),
so'ng bitta umumiy tahlil (build_project) ishlaydi."""
import io
import math
import re
from dataclasses import dataclass, field

from PIL import Image

from presentation.builder import LABELS
from presentation.themes import DEFAULT_THEME, THEMES

MAX_SLIDES = 60          # muharrir chegarasi (server bilan bir xil)
PER_PLAN = 20
ITEMS_MAX = 6
IMAGE_MIN_AREA = 0.04    # slayd maydonining shu ulushidan kichik rasmlar (logotip, belgi) olinmaydi
CONCLUSION_WORDS = ("xulosa", "заключение", "вывод", "итог", "conclusion", "summary", "yakun")
MAIN_PART = {"uz": "Asosiy qism", "ru": "Основная часть", "en": "Main part"}


class ImportError_(Exception):
    """Foydalanuvchiga ko'rsatsa bo'ladigan xato."""


@dataclass
class Para:
    text: str
    heading: str = ""    # «Sarlavha: matn» ko'rinishidagi qalin boshlanish
    dashed: bool = False  # «— Muallif» (iqtibos manbasi bo'lishi mumkin; clean tireni olib tashlaydi)


DASHED = re.compile(r"^\s*[—–-]\s")


@dataclass
class Box:
    paras: list
    size: float          # eng katta shrift (pt); noma'lum bo'lsa 0
    bold: bool
    top: float           # slayd balandligiga nisbatan 0..1
    left: float
    width: float
    title: bool = False  # PPTX sarlavha joyi (placeholder)

    @property
    def text(self):
        return "\n".join(p.text for p in self.paras)


@dataclass
class Page:
    boxes: list
    image: bytes = None  # eng katta rasm (JPEG)
    background: str = None  # birinchi slayd foni (dizaynni tanlash uchun)
    extra: dict = field(default_factory=dict)


# ===== Yordamchilar =====
def clean(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    return re.sub(r"^[•▪●◦■□►▶✓✔\-–—*·]+\s*", "", text)


def cut(text, limit):
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def to_jpeg(data):
    """Har qanday rasmni JPEG ga (PowerPoint va muharrir uchun). O'qib bo'lmasa — None."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if image.width * image.height < 120 * 120:
                return None
            image = image.convert("RGB")
            image.thumbnail((1920, 1920))
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=86)
            return buffer.getvalue()
    except Exception:  # noqa: BLE001 — EMF/WMF va buzuq rasmlar shunchaki o'tkazib yuboriladi
        return None


def detect_type(data):
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:2] == b"PK" and b"ppt/" in data:
        return "pptx"
    if data[:4] == b"\xd0\xcf\x11\xe0":
        raise ImportError_("Bu eski .ppt formati. PowerPoint'da «Saqlash → .pptx» qilib qayta yuklang.")
    raise ImportError_("Faqat PPTX yoki PDF faylni tahrirlash mumkin.")


# ===== PPTX → Page =====
def _iter_shapes(shapes):
    for shape in shapes:
        if shape.shape_type == 6:  # GROUP
            yield from _iter_shapes(shape.shapes)
        else:
            yield shape


def read_pptx(data):
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER

    prs = Presentation(io.BytesIO(data))
    width, height = prs.slide_width or 12192000, prs.slide_height or 6858000
    pages = []
    for slide in prs.slides:
        boxes, best, best_area = [], None, IMAGE_MIN_AREA
        for shape in _iter_shapes(slide.shapes):
            top = (shape.top or 0) / height
            left = (shape.left or 0) / width
            w = (shape.width or 0) / width
            area = w * (shape.height or 0) / height
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE and area > best_area:
                try:
                    best, best_area = shape.image.blob, area
                except (AttributeError, KeyError, ValueError):
                    pass
                continue
            if getattr(shape, "has_table", False) and shape.has_table:
                rows = [" — ".join(clean(c.text) for c in row.cells if clean(c.text)) for row in shape.table.rows]
                paras = [Para(r) for r in rows if r]
                if paras:
                    boxes.append(Box(paras, 14, False, top, left, w))
                continue
            if not getattr(shape, "has_text_frame", False) or not shape.text_frame.text.strip():
                continue
            is_title = shape.is_placeholder and shape.placeholder_format.type in (
                PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE)
            paras, sizes, bold = [], [], False
            for p in shape.text_frame.paragraphs:
                runs = [r for r in p.runs if r.text]
                raw = "".join(r.text for r in runs)
                text = clean(raw)
                if not text:
                    continue
                sizes += [r.font.size.pt for r in runs if r.font.size]
                first_bold = bool(runs and runs[0].font.bold)
                bold = bold or first_bold
                heading = ""
                # «Sarlavha: matn» — botning ro'yxat bandlari shunday yoziladi (sarlavha qalin)
                if first_bold and len(runs) > 1 and runs[0].text.rstrip().endswith(":"):
                    heading = clean(runs[0].text.rstrip()[:-1])
                    text = clean("".join(r.text for r in runs[1:]))
                paras.append(Para(text, heading, bool(DASHED.match(raw))))
            if paras:
                size = max(sizes) if sizes else (40 if is_title else 18)
                boxes.append(Box(paras, size, bold, top, left, w, is_title))
        background = None
        try:
            fill = slide.background.fill
            color = fill.gradient_stops[0].color if fill.type == 3 else fill.fore_color
            background = str(color.rgb)
        except Exception:  # noqa: BLE001 — fon rangi bo'lmasligi mumkin
            pass
        pages.append(Page(boxes, to_jpeg(best) if best else None, background))
    return pages


# ===== PDF → Page =====
def read_pdf(data):
    import pymupdf

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        raise ImportError_("PDF faylni ochib bo'lmadi.") from e
    if doc.needs_pass:
        raise ImportError_("PDF parol bilan himoyalangan.")
    pages = []
    for page in doc.pages(0, min(doc.page_count, MAX_SLIDES + 5)):
        width, height = page.rect.width or 1, page.rect.height or 1
        boxes = []
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            paras, sizes, bold = [], [], False
            for line in block["lines"]:
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                sizes += [s["size"] for s in spans]
                first_bold = bool(spans[0]["flags"] & 16) or "Bold" in spans[0]["font"] or "Black" in spans[0]["font"]
                bold = bold or first_bold
                raw = " ".join(s["text"] for s in spans)
                text = clean(raw)
                heading = ""
                if first_bold and len(spans) > 1 and spans[0]["text"].rstrip().endswith(":"):
                    heading = clean(spans[0]["text"].rstrip()[:-1])
                    text = clean(" ".join(s["text"] for s in spans[1:]))
                paras.append(Para(text, heading, bool(DASHED.match(raw))))
            if not paras:
                continue
            # PDF da bitta xatboshi bir nechta qatorga bo'linadi — oddiy qatorlarni birlashtiramiz
            merged = [paras[0]]
            for p in paras[1:]:
                if not p.heading and not p.dashed and not merged[-1].text.endswith((".", ":", "!", "?")):
                    merged[-1] = Para(f"{merged[-1].text} {p.text}", merged[-1].heading, merged[-1].dashed)
                else:
                    merged.append(p)
            x0, y0, x1, _ = block["bbox"]
            boxes.append(Box(merged, max(sizes), bold, y0 / height, x0 / width, (x1 - x0) / width))

        # Eng katta rasm; matnsiz sahifa (skan) bo'lsa — sahifaning o'zi rasm bo'ladi
        image, best_area = None, IMAGE_MIN_AREA
        for info in page.get_images(full=True):
            for rect in page.get_image_rects(info[0]):
                area = rect.width * rect.height / (width * height)
                if area > best_area:
                    try:
                        jpeg = to_jpeg(pymupdf.Pixmap(doc, info[0]).tobytes("png"))
                    except Exception:  # noqa: BLE001
                        jpeg = None
                    if jpeg:
                        image, best_area = jpeg, area
        if not boxes and image is None:
            image = to_jpeg(page.get_pixmap(dpi=110).tobytes("png"))
        pages.append(Page(boxes, image))
    return pages


# ===== Umumiy tahlil =====
PAGE_NUMBER = re.compile(r"^\d{1,3}\s*(/\s*\d{1,3})?$")
TAG = re.compile(r"^(\d{1,2})\.\s+(.+)$")
NUMBER_ONLY = re.compile(r"^0?\d{1,2}$")
FIGURE = re.compile(r"^[~≈+\-–]?\s?[\d][\d\s.,]*\s?(%|\+|[a-zA-Zа-яА-ЯёЁ.$€₽]{0,6})$")
ALL_LABELS = {key: {labels[key].lower() for labels in LABELS.values()} for key in ("contents", "plan", "conclusion")}


def strip_noise(page):
    """Sahifa raqami, pastki kolontitul va bezak belgilarini olib tashlaydi."""
    kept = []
    for box in page.boxes:
        text = box.text.strip()
        if box.top > 0.86 and (box.size <= 13 or PAGE_NUMBER.match(text)):
            continue
        if PAGE_NUMBER.match(text) and box.size <= 14:
            continue
        if text in ("“", "”", '"', "«", "»"):
            page.extra["quote_mark"] = True
            continue
        kept.append(box)
    return kept


def reading_order(box):
    return round(box.top * 30), box.left


def pick_title(boxes):
    marked = [b for b in boxes if b.title]
    if marked:
        return marked[0]
    # Sarlavha odatda tepada: avval yuqori 30% dan qidiriladi — aks holda «1991» kabi katta raqamlar
    # (raqamlar maketi) sarlavha bo'lib qolardi
    short = [b for b in boxes if len(b.text) <= 160]
    upper = [b for b in short if b.top < 0.3] or [b for b in short if b.top < 0.5] or boxes
    return max(upper, key=lambda b: (round(b.size), -b.top)) if upper else None


def body_items(boxes, quote=False):
    """Qolgan matn bloklaridan slayd tarkibi: (kirish, iqtibos manbasi, bandlar, maket turi).
    quote — slaydda «“» belgisi bor (iqtibos maketi)."""
    source, rest = "", []
    for box in sorted(boxes, key=reading_order):
        text = box.text.strip()
        if NUMBER_ONLY.match(text):  # kartalar/bosqichlardagi «01», «2» doiralari
            continue
        if quote and len(box.paras) == 1 and box.paras[0].dashed and len(text) <= 90:
            source = text
            continue
        rest.append(box)
    smallest = min((b.size for b in rest), default=0)

    def heading_like(b):
        # «Sarlavha: matn» bandlari allaqachon ajratilgan — ular alohida sarlavha emas.
        # Kattaroq shrift (raqamlar maketidagi «1991») yoki qalin qisqa matn — sarlavha
        return (len(b.paras) == 1 and len(b.text) <= 60 and not b.paras[0].heading
                and (b.bold or b.size >= smallest + 2))

    # Sarlavha → uning ostidagi (o'sha ustundagi) eng yaqin matn. Kartalar yonma-yon turgani uchun
    # oddiy o'qish tartibida juftlab bo'lmaydi
    pairs, used = [], set()
    for head in (b for b in rest if heading_like(b)):
        below = [b for b in rest if id(b) not in used and b is not head and not heading_like(b)
                 and b.top > head.top - 0.005 and abs(b.left - head.left) < 0.06]
        if below:
            body = min(below, key=lambda b: b.top)
            used.update((id(head), id(body)))
            pairs.append((head, body))

    intro, items = "", []
    others = [b for b in rest if id(b) not in used]
    # Kirish jumlasi: bandlardan oldingi keng, bitta jumlali blok — faqat undan keyingi bandlar
    # boshqacha bo'lsa (juftliklar, «Sarlavha: matn» yoki boshqa shrift); aks holda u oddiy birinchi band
    first_pair_top = min((h.top for h, _ in pairs), default=1)
    if others:
        first, after = others[0], others[1:]
        distinct = pairs or any(p.heading for b in after for p in b.paras) or (
            after and abs(first.size - after[0].size) >= 1.5)
        if (len(first.paras) == 1 and not first.paras[0].heading and first.width > 0.45
                and first.top < first_pair_top and distinct):
            intro = clean(others.pop(0).text)

    if pairs:
        tops = [h.top for h, _ in pairs]
        horizontal = len(pairs) >= 2 and max(tops) - min(tops) < 0.05
        for head, body in sorted(pairs, key=lambda p: (p[0].left, p[0].top) if horizontal else reading_order(p[0])):
            items.append({"heading": clean(head.text), "text": clean(" ".join(p.text for p in body.paras))})
    else:
        horizontal = False
    for box in others:
        for p in box.paras:
            if p.text or p.heading:
                items.append({"heading": p.heading, "text": p.text or p.heading})

    kind = "bullets"
    if horizontal:
        figures = sum(1 for item in items if FIGURE.match(item["heading"]) and len(item["heading"]) <= 10)
        kind = "stats" if figures >= len(items) / 2 else "cards"
    return intro, source, items, kind


def guess_lang(text):
    letters = re.findall(r"[A-Za-zА-Яа-яЁёЎўҚқҒғҲҳ]", text)
    if not letters:
        return "uz"
    cyrillic = sum(1 for ch in letters if "А" <= ch <= "я" or ch in "ЁёЎўҚқҒғҲҳ")
    if cyrillic / len(letters) > 0.3:
        return "ru"
    words = re.findall(r"[a-zʻʼ'’]+", text.lower())
    english = sum(w in ("the", "and", "of", "to", "is", "in", "for", "with") for w in words)
    uzbek = sum(w in ("va", "uchun", "bilan", "bu", "ham", "yoki", "deb", "edi") for w in words)
    return "en" if english > uzbek else "uz"


def guess_theme(color):
    if not color or not re.fullmatch(r"[0-9A-Fa-f]{6}", color):
        return DEFAULT_THEME
    rgb = [int(color[i:i + 2], 16) for i in (0, 2, 4)]

    def distance(key):
        bg = THEMES[key]["bg"]
        return math.dist(rgb, [int(bg[i:i + 2], 16) for i in (0, 2, 4)])

    best = min(THEMES, key=distance)
    if distance(best) < 60:
        return best
    return "cosmos" if sum(rgb) < 380 else "business"


def make_slide(title, intro, items, kind, source=""):
    """Muharrir slaydi (server cleanSlide qoidalariga mos). Ko'p bandli slayd bir nechtaga bo'linadi."""
    items = [{"heading": cut(i["heading"], 80), "text": cut(i["text"], 400)} for i in items if i["text"] or i["heading"]]
    if kind == "quote":
        return [{"title": title, "kind": "quote", "text": cut(intro, 600), "image": None, "video": None,
                 "items": [{"heading": source, "text": source}] if source else []}]
    if not items:
        items = [{"heading": "", "text": cut(intro or title, 400)}]
        intro = ""
    limit = 4 if kind in ("cards", "stats") else ITEMS_MAX
    chunks = [items[i:i + limit] for i in range(0, len(items), limit)]
    slides = []
    for n, chunk in enumerate(chunks):
        slide_kind = kind if len(chunk) >= 2 else "bullets"
        slides.append({
            "title": title if n == 0 else cut(f"{title} (davomi)", 150), "kind": slide_kind,
            "text": cut(intro, 600) if n == 0 else "", "items": chunk, "image": None, "video": None,
        })
    return slides


def build_project(pages):
    """Sahifalardan muharrir loyihasi: (project, media{nom: bytes})."""
    if not pages:
        raise ImportError_("Faylda slayd topilmadi.")
    media, everything = {}, []
    for page in pages:
        page.boxes = strip_noise(page)
        everything.append(" ".join(b.text for b in page.boxes))
    lang = guess_lang(" ".join(everything))
    labels = LABELS[lang]

    def store(image, name):
        if image:
            media[name] = image
            return name
        return None

    # ----- Muqova -----
    cover = pages[0]
    title_box = pick_title(cover.boxes)
    title = cut(clean(title_box.text.replace("\n", " ")), 200) if title_box else ""
    author, subtitle = "", ""
    badges = {l["badge"].lower() for l in LABELS.values()}
    author_words = tuple(l["author"].lower() for l in LABELS.values())
    for box in cover.boxes:
        if box is title_box:
            continue
        text = clean(box.text.replace("\n", " "))
        low = text.lower()
        if low in badges or re.fullmatch(r"\d{4}", text):
            continue
        if low.startswith(author_words):
            author = cut(re.split(r"\s+[•|]\s+", text.split(":", 1)[-1])[0].strip(), 70)
            continue
        if len(text) > len(subtitle):
            subtitle = text
    content_pages = pages[1:]

    # ----- Botning maxsus slaydlari: mundarija (tashlanadi), reja, xulosa -----
    plan_titles, conclusion, slides = {}, [], []
    for index, page in enumerate(content_pages):
        box = pick_title(page.boxes)
        heading = clean(box.text.replace("\n", " ")) if box else ""
        low = heading.lower()
        rest = [b for b in page.boxes if b is not box]
        if low in ALL_LABELS["contents"]:
            continue
        if low in ALL_LABELS["plan"]:
            # Ustunma-ustun o'qiladi: ko'p bandli rejada 2 ustun bo'ladi (1–5 chapda, 6–10 o'ngda)
            names = [clean(b.text) for b in sorted(rest, key=lambda b: (round(b.left * 4), b.top))
                     if not NUMBER_ONLY.match(b.text.strip())]
            plan_titles.update({i + 1: n for i, n in enumerate(names) if n})
            continue
        is_last = index == len(content_pages) - 1
        if low in ALL_LABELS["conclusion"] or (is_last and low.startswith(CONCLUSION_WORDS)):
            thanks = {l["thanks"].lower() for l in LABELS.values()}
            for b in sorted(rest, key=lambda b: b.top):
                for p in b.paras:
                    text = clean(p.text.replace("✨", ""))
                    if text and text.lower() not in thanks:
                        conclusion.append(cut(text, 300))
            continue

        tag = next((m for b in rest if b.top < (box.top if box else 1) and b.size <= 14
                    for m in [TAG.match(clean(b.text))] if m), None)
        if tag:
            rest = [b for b in rest if clean(b.text) != tag.group(0)]
        intro, source, items, kind = body_items(rest, quote=page.extra.get("quote_mark", False))
        if page.extra.get("quote_mark") and len(items) <= 1:
            kind, intro = "quote", intro or (items[0]["text"] if items else "")
        if not heading:
            if not items and not intro and not page.image:
                continue
            heading = f"{len(slides) + 1}-slayd"
        made = make_slide(cut(heading, 150), intro, items, kind, source)
        made[0]["image"] = store(page.image, f"imp-{len(media) + 1}.jpg")
        plan_no = int(tag.group(1)) if tag else None
        if tag:
            plan_titles.setdefault(plan_no, clean(tag.group(2)))
        slides += [(plan_no, s) for s in made]

    slides = slides[:MAX_SLIDES]
    if not slides:  # bitta slaydli fayl — muqova matnidan bitta slayd
        slides = [(None, make_slide(title or "Slayd", subtitle, [], "bullets")[0])]

    # ----- Rejalar -----
    plans = []
    if all(no for no, _ in slides) and len({no for no, _ in slides}) <= 10:
        for no, slide in slides:
            if not plans or plans[-1]["no"] != no:
                plans.append({"no": no, "title": cut(plan_titles.get(no) or f"{no}-reja", 120), "slides": []})
            if len(plans[-1]["slides"]) < PER_PLAN:
                plans[-1]["slides"].append(slide)
        plans = [{"title": p["title"], "slides": p["slides"]} for p in plans][:10]
    else:
        groups = math.ceil(len(slides) / PER_PLAN)
        size = math.ceil(len(slides) / groups)
        for g in range(groups):
            chunk = [s for _, s in slides[g * size:(g + 1) * size]]
            name = MAIN_PART[lang] if groups == 1 else chunk[0]["title"]
            plans.append({"title": cut(name, 120), "slides": chunk})

    project = {
        "version": 1,
        "theme": guess_theme(cover.background),
        "lang": lang,
        "author": author,
        "imported": True,
        "content": {
            "title": title or (plans[0]["slides"][0]["title"] if plans else "Taqdimot"),
            "subtitle": cut(subtitle, 300),
            "cover_image": store(cover.image, "imp-cover.jpg"),
            "plans": plans,
            "conclusion": conclusion[:5] or [labels["thanks"]],
        },
    }
    return project, media


def import_file(data):
    """PPTX yoki PDF bytes → (project, media). Xato bo'lsa ImportError_."""
    kind = detect_type(data)
    try:
        pages = read_pptx(data) if kind == "pptx" else read_pdf(data)
    except ImportError_:
        raise
    except Exception as e:  # noqa: BLE001 — buzuq fayl
        raise ImportError_("Faylni o'qib bo'lmadi. U buzilgan bo'lishi mumkin.") from e
    return build_project(pages)
