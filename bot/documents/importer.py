"""Tayyor DOCX yoki PDF ishdan (referat, mustaqil ish, kurs ishi) muharrir loyihasini tiklaydi.

Ikki holat:
- botning o'zi yozgan eski ishlar (loyihasi saqlanmagan) — tuzilma to'liq tiklanadi: titul, kirish,
  boblar va bo'limlar, bob rasmlari, xulosa, adabiyotlar;
- foydalanuvchining boshqa ishlari — sarlavhalar (uslub yoki qalin qisqa qatorlar) bo'yicha boblarga
  bo'linadi; sarlavha topilmasa, butun matn bitta bobga tushadi.

DOCX va PDF avval bir xil bloklar ro'yxatiga keltiriladi: (tur, matn) yoki ("img", bytes). Turlar:
h1/h2 — uslubli sarlavha (Heading 1/2), b1/b2 — qalinligidan taxmin qilingan sarlavha, p — xatboshi;
so'ng bitta umumiy tahlil (build_paper) ishlaydi. Natija server chegaralariga (routes/papers.js) moslanadi."""
import io
import re

from documents.builder import LABELS
from presentation.importer import ImportError_, clean, guess_lang, to_jpeg

# Server chegaralari (slayd-web/server/src/routes/papers.js → LIMITS) bilan bir xil
MAX_CHAPTERS, MAX_SECTIONS, MAX_PARAGRAPHS, MAX_BLOCK, MAX_REFERENCES = 6, 8, 60, 30, 40
PARAGRAPH_MAX, HEADING_MAX, TITLE_MAX, REFERENCE_MAX, FIELD_MAX = 4000, 200, 300, 500, 150
MAX_PAGES = 150
MAIN_PART = {"uz": "Asosiy qism", "ru": "Основная часть", "en": "Main part"}


def _labels(key, *extra):
    return {labels[key].lower().rstrip(".") for labels in LABELS.values()} | set(extra)


INTRO = _labels("intro", "kirish", "введение")
CONCLUSION = _labels("conclusion", "xulosa", "xulosa va takliflar", "xulosa va tavsiyalar", "заключение", "выводы")
CONTENTS = _labels("contents", "mundarija", "reja", "оглавление", "содержание", "contents")
REFERENCES_START = ("foydalanilgan adabiyot", "adabiyotlar", "список литератур", "список использованн",
                    "литература", "references", "bibliography")
COVER_FIELDS = {}  # «Bajardi:» → student va h.k. (barcha tillar)
for _labels_set in LABELS.values():
    for _key in ("subject", "student", "group", "teacher"):
        COVER_FIELDS[_labels_set[_key].lower()] = _key
KIND_LABELS = {labels[k].lower() for labels in LABELS.values() for k in ("referat", "mustaqil", "kurs")}
TOPIC_LABELS = {labels["topic"].lower() for labels in LABELS.values()}

CHAPTER_PREFIX = re.compile(
    r"^(?:(?:[IVX]+|\d+)\s*-?\s*(?:bob|глава|chapter)|(?:bob|глава|chapter)\s+(?:[IVX]+|\d+))\s*[.:]?\s*", re.I
)
NUMBER_PREFIX = re.compile(r"^\d{1,2}\s*[.)]\s+")
SECTION_PREFIX = re.compile(r"^\d{1,2}\.\d{1,2}\.?\s*")
FIGURE_CAPTION = re.compile(r"^(?:\d+\s*-\s*rasm|рис\.?\s*\d+|figure\s*\d+)\b", re.I)
PAGE_NUMBER = re.compile(r"^\d{1,3}$")
CITY_YEAR = re.compile(r"^(?:(.{2,60}?)\s*[—–-]\s*)?((?:19|20)\d{2})\s*(?:y\.?|г\.?|yil)?$")


def norm(text):
    return clean(text).lower().strip(" .:;")


def heading_kind(text):
    """Sarlavha turi: intro / conclusion / references / contents / None (oddiy bob nomi)."""
    key = norm(text)
    if key in INTRO:
        return "intro"
    if key in CONCLUSION:
        return "conclusion"
    if key in CONTENTS:
        return "contents"
    if key.startswith(REFERENCES_START):
        return "references"
    return None


def detect_type(data):
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:2] == b"PK" and b"word/" in data:
        return "docx"
    if data[:4] == b"\xd0\xcf\x11\xe0":
        raise ImportError_("Bu eski .doc formati. Word'da «Saqlash → .docx» qilib qayta yuklang.")
    raise ImportError_("Faqat DOCX yoki PDF ishni tahrirlash mumkin.")


def guess_level(text):
    """Uslubsiz (qalin) sarlavha darajasi: «1.2. ...» — bo'lim, qolgani — bob."""
    return 2 if SECTION_PREFIX.match(text) else 1


# ===== DOCX → bloklar =====
def read_docx(data):
    from docx import Document
    from docx.oxml.ns import qn

    doc = Document(io.BytesIO(data))
    blocks = []
    for p in doc.paragraphs:
        for blip in p._p.iter(qn("a:blip")):
            part = doc.part.related_parts.get(blip.get(qn("r:embed")))
            image = to_jpeg(part.blob) if part is not None else None
            if image:
                blocks.append(("img", image))
        text = clean(p.text)
        if not text:
            continue
        style = (p.style.name if p.style is not None else "").lower()
        if style.startswith(("toc", "оглавление")):
            continue  # avtomatik mundarija qatorlari
        level = re.search(r"(?:heading|заголовок|sarlavha)\s*(\d)", style)
        if style == "title" or (level and level.group(1) == "1"):
            blocks.append(("h1", text))
        elif level:
            blocks.append(("h2", text))
        elif _bold_line(p, text):
            blocks.append((f"b{guess_level(text)}", text))
        else:
            blocks.append(("p", text))
    return blocks


def _bold_line(p, text):
    """Uslubsiz sarlavha: qisqa, nuqtasiz va to'liq qalin qator."""
    if len(text) > 150 or text.endswith((".", ",", ";")) or ":" in text[:-1]:
        return False
    runs = [r for r in p.runs if r.text.strip()]
    style_bold = bool(p.style is not None and p.style.font.bold)
    return bool(runs) and all(r.bold or (r.bold is None and style_bold) for r in runs)


# ===== PDF → bloklar =====
def read_pdf(data):
    import pymupdf

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        raise ImportError_("PDF faylni ochib bo'lmadi.") from e
    if doc.needs_pass:
        raise ImportError_("PDF parol bilan himoyalangan.")
    blocks = []
    for page in doc.pages(0, min(doc.page_count, MAX_PAGES)):
        area = (page.rect.width * page.rect.height) or 1
        for block in page.get_text("dict", sort=True)["blocks"]:
            if block.get("type") == 1:  # rasm
                x0, y0, x1, y1 = block["bbox"]
                image = to_jpeg(block.get("image") or b"") if (x1 - x0) * (y1 - y0) / area > 0.05 else None
                if image:
                    blocks.append(("img", image))
                continue
            lines, bold = [], True
            for line in block.get("lines", []):
                spans = [s for s in line["spans"] if s["text"].strip()]
                if spans:
                    lines.append(" ".join(s["text"] for s in spans))
                    bold = bold and all(s["flags"] & 16 or "Bold" in s["font"] for s in spans)
            text = clean(" ".join(lines))
            if not text or PAGE_NUMBER.match(text):
                continue
            if bold and len(text) <= 150 and not text.endswith((".", ",", ";")):
                blocks.append((f"b{guess_level(text)}", text))
            else:
                blocks.append(("p", text))
    return blocks


# ===== Umumiy tahlil =====
def cut(text, limit):
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def parse_cover(paras, fallback_title):
    """Titul sahifasidan mavzu va titul maydonlarini oladi (bot yozgan muqova tartibi bo'yicha)."""
    title, page, before_kind = None, {}, []
    seen_kind = False
    for text in paras:
        key, _, value = text.partition(":")
        key, value = key.strip().lower(), clean(value).strip("«»\"' ")
        if key in TOPIC_LABELS and value:
            title = value
        elif key in COVER_FIELDS and value:
            page[COVER_FIELDS[key]] = cut(value, FIELD_MAX)
        elif norm(text) in KIND_LABELS:
            seen_kind = True
        elif (match := CITY_YEAR.match(text)) and match.group(1):
            page["city"] = cut(match.group(1), FIELD_MAX)
        elif not seen_kind and not CITY_YEAR.match(text):
            before_kind.append(text)
    if seen_kind:  # kind belgisidan oldingilar — o'quv muassasasi va fakultet
        for key, text in zip(("university", "faculty"), before_kind):
            page[key] = cut(text, FIELD_MAX)
    return cut(title or fallback_title, TITLE_MAX), page


def build_paper(blocks, fallback_title):
    cover, intro, conclusion, references, chapters = [], [], [], [], []
    state = "cover"

    def chapter(title):
        chapters.append({"title": cut(clean(CHAPTER_PREFIX.sub("", NUMBER_PREFIX.sub("", title))) or title, HEADING_MAX),
                         "image": None, "sections": []})

    def section(title):
        if not chapters:
            chapter(title)
        chapters[-1]["sections"].append(
            {"title": cut(clean(SECTION_PREFIX.sub("", title)) or title, HEADING_MAX), "paragraphs": []}
        )

    for kind, value in blocks:
        if kind == "img":
            if state == "chapter" and chapters and not chapters[-1]["image"]:
                chapters[-1]["image"] = value
            continue
        text = value
        heading = kind != "p"
        # Mundarija qatorlari (KIRISH, XULOSA ...) oddiy xatboshi — ular bo'limni almashtirmaydi.
        # Uslubsiz hujjatda «KIRISH» oddiy katta harfli qator bo'lishi mumkin
        special = heading_kind(text) if heading or (state != "contents" and text.isupper() and len(text) < 60) else None
        if special == "contents":
            state = "contents"
            continue
        if special in ("intro", "conclusion", "references"):
            state = special
            continue
        # Qalin qator muqova / kirish / xulosada sarlavha emas («REFERAT», qalin jumla) —
        # faqat raqamlangan bo'lsa («1. ...», «1.2. ...», «I BOB. ...») bob yoki bo'lim boshlaydi
        numbered = bool(CHAPTER_PREFIX.match(text) or NUMBER_PREFIX.match(text) or SECTION_PREFIX.match(text))
        strong = kind in ("h1", "h2") or numbered or state in ("chapter", "contents")
        if heading and strong:
            if kind.endswith("1"):
                chapter(text)
            else:
                section(text)
            state = "chapter"
            continue
        # Oddiy xatboshi
        if state == "cover":
            cover.append(text)
        elif state == "contents":
            continue
        elif state == "intro":
            intro.append(text)
        elif state == "conclusion":
            conclusion.append(text)
        elif state == "references":
            references.append(cut(NUMBER_PREFIX.sub("", text), REFERENCE_MAX))
        elif FIGURE_CAPTION.match(text):
            continue  # «1-rasm. ...» imzosi — fayl yig'ilganda qayta qo'yiladi
        else:
            if not chapters[-1]["sections"]:
                chapters[-1]["sections"].append({"title": chapters[-1]["title"], "paragraphs": []})
            chapters[-1]["sections"][-1]["paragraphs"].append(text)

    title, title_page = parse_cover(cover, fallback_title)
    text_all = " ".join(intro + conclusion + [p for c in chapters for s in c["sections"] for p in s["paragraphs"]])

    # Hech qanday tuzilma topilmadi (oddiy matnli fayl) — titulni ham matn deb olamiz
    if not chapters and not intro and not conclusion:
        loose = cover
        title_page = {}
        text_all = " ".join(loose)
        if not loose:
            raise ImportError_("Fayldan matn topilmadi. U skanerlangan (rasm) bo'lishi mumkin.")
        chapters = [{"title": fallback_title, "image": None, "sections": [{"title": fallback_title, "paragraphs": loose}]}]
    lang = guess_lang(text_all or " ".join(cover))
    return {
        "title": title,
        "intro": fit_block(intro),
        "chapters": fit_chapters(chapters, MAIN_PART.get(lang, MAIN_PART["uz"])),
        "conclusion": fit_block(conclusion),
        "references": [r for r in references if r][:MAX_REFERENCES],
    }, title_page, lang


def fit_block(paragraphs, limit=MAX_BLOCK):
    """Kirish / xulosa: chegaradan oshganlari oxirgi xatboshiga qo'shiladi; bo'sh bo'lsa — «—»."""
    paragraphs = [cut(p, PARAGRAPH_MAX) for p in paragraphs if p] or ["—"]
    if len(paragraphs) > limit:
        paragraphs = paragraphs[: limit - 1] + [cut(" ".join(paragraphs[limit - 1:]), PARAGRAPH_MAX)]
    return paragraphs


def fit_chapters(chapters, main_part):
    """Boblarni server chegaralariga moslaydi: ortiqcha boblar oxirgisiga bo'lim bo'lib qo'shiladi,
    juda uzun bo'limlar bo'linadi, bo'sh bob/bo'limga «—» qo'yiladi."""
    for chapter in chapters:
        sections = []
        for sec in chapter["sections"] or [{"title": chapter["title"], "paragraphs": []}]:
            paragraphs = [cut(p, PARAGRAPH_MAX) for p in sec["paragraphs"]] or ["—"]
            for start in range(0, len(paragraphs), MAX_PARAGRAPHS):
                sections.append({"title": sec["title"] or main_part, "paragraphs": paragraphs[start:start + MAX_PARAGRAPHS]})
        chapter["sections"] = sections
        chapter["title"] = chapter["title"] or main_part

    if len(chapters) > MAX_CHAPTERS:
        last = chapters[MAX_CHAPTERS - 1]
        for extra in chapters[MAX_CHAPTERS:]:
            last["sections"] += [{"title": cut(f"{extra['title']}. {s['title']}" if s["title"] != extra["title"] else s["title"],
                                               HEADING_MAX), "paragraphs": s["paragraphs"]} for s in extra["sections"]]
        chapters = chapters[:MAX_CHAPTERS]
    for chapter in chapters:
        sections = chapter["sections"]
        if len(sections) > MAX_SECTIONS:  # ortiqcha bo'limlar oxirgisiga qo'shiladi
            tail = [p for s in sections[MAX_SECTIONS - 1:] for p in s["paragraphs"]]
            sections[MAX_SECTIONS - 1:] = [{"title": sections[MAX_SECTIONS - 1]["title"], "paragraphs": tail[:MAX_PARAGRAPHS - 1]
                                            + ([cut(" ".join(tail[MAX_PARAGRAPHS - 1:]), PARAGRAPH_MAX)]
                                               if len(tail) >= MAX_PARAGRAPHS else [])}]
    return chapters


def import_paper(data, fallback_title):
    """DOCX yoki PDF bytes → (content, title_page, lang, fmt). content dagi bob rasmlari — bytes.
    Xato bo'lsa ImportError_."""
    fmt = detect_type(data)
    try:
        blocks = read_docx(data) if fmt == "docx" else read_pdf(data)
    except ImportError_:
        raise
    except Exception as e:  # noqa: BLE001 — buzuq fayl
        raise ImportError_("Faylni o'qib bo'lmadi. U buzilgan bo'lishi mumkin.") from e
    content, title_page, lang = build_paper(blocks, cut(clean(fallback_title) or "—", TITLE_MAX))
    return content, title_page, lang, fmt
