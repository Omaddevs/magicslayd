"""AI yordamchi natijasidan fayllar: taqdimot → .pptx, matnli ishlar → .docx va .pdf.
Word rasmiylashtiruvi: A4, Times New Roman 14, interval 1.5, hoshiyalar chap 3 / o'ng 1.5 / yuqori-past 2 sm,
titul varag'i (mavzu, fan, «Bajardi», «Tekshirdi»), reja, Heading uslubidagi sarlavhalar, sahifa raqamlari."""
import asyncio
import html
import io
import re
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.shared import Cm, Pt

from converter import PDF_AVAILABLE, ConvertError, to_pdf
from documents.builder import page_number, set_font
from metadata import clean_properties
from presentation.builder import build_outline_pptx

MIME = {
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}
PPTX_THEME = "business"  # o'qishga qulay, chop etishga mos yorug' dizayn

LABELS = {
    "uz": {"referat": "REFERAT", "mustaqil": "MUSTAQIL ISH", "kurs": "KURS ISHI", "topic": "Mavzu", "subject": "Fan",
           "student": "Bajardi", "teacher": "Tekshirdi", "plan": "REJA", "year": "{y}-yil"},
    "uz_cyrl": {"referat": "РЕФЕРАТ", "mustaqil": "МУСТАҚИЛ ИШ", "kurs": "КУРС ИШИ", "topic": "Мавзу", "subject": "Фан",
                "student": "Бажарди", "teacher": "Текширди", "plan": "РЕЖА", "year": "{y} йил"},
    "ru": {"referat": "РЕФЕРАТ", "mustaqil": "САМОСТОЯТЕЛЬНАЯ РАБОТА", "kurs": "КУРСОВАЯ РАБОТА", "topic": "Тема",
           "subject": "Предмет", "student": "Выполнил(а)", "teacher": "Проверил(а)", "plan": "ПЛАН", "year": "{y} г."},
}
BLANK = "____________________"
SUBSECTION = re.compile(r"^\d+\.\d+\.")  # «1.2. ...» — ikkinchi darajali sarlavha

# Kirill → lotin (fayl nomi uchun)
_TRANSLIT = dict(zip(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюяўқғҳ",
    ["a", "b", "v", "g", "d", "e", "yo", "j", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f",
     "x", "ts", "ch", "sh", "sh", "", "i", "", "e", "yu", "ya", "o", "q", "g", "h"],
))


def safe_filename(topic, ext):
    """«Turizmning rivojlanishi» → Turizmning_rivojlanishi.docx (faqat lotin harf, raqam, _ va -)."""
    def latin(ch):
        if ch.lower() not in _TRANSLIT:
            return ch
        value = _TRANSLIT[ch.lower()]
        return value.capitalize() if ch.isupper() else value  # «Ўзбекистон» → «Ozbekiston»

    text = "".join(latin(ch) for ch in topic)
    text = re.sub(r"[ʻʼ‘’'`]", "", text)
    text = re.sub(r"[^A-Za-z0-9\s-]", " ", text)
    text = re.sub(r"\s+", "_", text.strip())[:60].strip("_-")
    return f"{text or 'hujjat'}.{ext}"


# ===== Word =====
def _paragraph(doc, text="", *, size=14, bold=False, align=None, indent=True, before=0, after=0):
    para = doc.add_paragraph()
    fmt = para.paragraph_format
    fmt.space_before, fmt.space_after = Pt(before), Pt(after)
    if not indent:
        fmt.first_line_indent = Cm(0)
    if align is not None:
        para.alignment = align
    if text:
        run = para.add_run(text)
        run.font.size, run.font.bold = Pt(size), bold
    return para


def _page_break(doc):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def build_docx(result, params):
    kind, lang = params["type"], params["language"]
    labels = LABELS[lang]
    doc = Document()

    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin, section.right_margin = Cm(3), Cm(1.5)
    section.top_margin = section.bottom_margin = Cm(2)
    page_number(section)  # titulda raqam ko'rinmaydi

    normal = doc.styles["Normal"]
    set_font(normal, 14)
    fmt = normal.paragraph_format
    fmt.line_spacing = 1.5
    fmt.space_before = fmt.space_after = Pt(0)
    fmt.first_line_indent = Cm(1.25)
    fmt.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for name, align in (("Heading 1", WD_ALIGN_PARAGRAPH.CENTER), ("Heading 2", WD_ALIGN_PARAGRAPH.LEFT)):
        style = doc.styles[name]
        set_font(style, 14, bold=True)
        style.font.italic = False
        hf = style.paragraph_format
        hf.alignment, hf.line_spacing, hf.first_line_indent = align, 1.5, Cm(0)
        hf.space_before, hf.space_after, hf.keep_with_next = Pt(6), Pt(12), True

    # ----- Titul varag'i -----
    _paragraph(doc, labels[kind], size=18, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, before=200)
    _paragraph(doc, f"{labels['topic']}: «{result['title']}»", size=16, bold=True,
               align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, before=24)
    _paragraph(doc, f"{labels['subject']}: {params['subject'] or BLANK}", align=WD_ALIGN_PARAGRAPH.CENTER,
               indent=False, before=12)
    _paragraph(doc, f"{labels['student']}: {BLANK}", align=WD_ALIGN_PARAGRAPH.RIGHT, indent=False, before=150)
    _paragraph(doc, f"{labels['teacher']}: {BLANK}", align=WD_ALIGN_PARAGRAPH.RIGHT, indent=False, before=12)
    _paragraph(doc, labels["year"].format(y=datetime.now().year), align=WD_ALIGN_PARAGRAPH.CENTER, indent=False,
               before=110)
    _page_break(doc)

    # ----- Reja -----
    # Bandlar sarlavhalardagidek (raqamlar sarlavhaning o'zida: «1. …», «1-bob. …», «1.1. …»)
    doc.add_heading(labels["plan"], level=1)
    for item in result["plan"]:
        para = _paragraph(doc, item, indent=False)
        para.paragraph_format.left_indent = Cm(1.25 if SUBSECTION.match(item) else 0)

    # ----- Matn: har bir birinchi darajali qism yangi sahifadan -----
    for part in result["sections"]:
        level = 2 if SUBSECTION.match(part["heading"]) else 1
        heading = doc.add_heading(part["heading"], level=level)
        heading.paragraph_format.page_break_before = level == 1
        for text in filter(None, (p.strip() for p in part["content"].split("\n\n"))):
            _paragraph(doc, text)

    # ----- Adabiyotlar -----
    heading = doc.add_heading(result["plan"][-1], level=1)
    heading.paragraph_format.page_break_before = True
    for number, item in enumerate(result["references"], 1):
        para = _paragraph(doc, f"{number}. {item}", indent=False)
        para.paragraph_format.left_indent, para.paragraph_format.first_line_indent = Cm(0.75), Cm(-0.75)

    clean_properties(doc.core_properties, result["title"])
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


# ===== PDF (LibreOffice bo'lmasa — PyMuPDF bilan, bir xil rasmiylashtiruv) =====
_FONT_CANDIDATES = (
    (r"C:\Windows\Fonts\times.ttf", r"C:\Windows\Fonts\timesbd.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
     "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"),
)
CM = 72 / 2.54


def _fonts():
    return next(((Path(r), Path(b)) for r, b in _FONT_CANDIDATES if Path(r).exists() and Path(b).exists()), None)


def _html_document(result, params):
    labels, e = LABELS[params["language"]], html.escape
    title_page = (
        f"<p class='c b' style='font-size:18pt;margin-top:150pt'>{e(labels[params['type']])}</p>"
        f"<p class='c b' style='font-size:16pt;margin-top:24pt'>{e(labels['topic'])}: «{e(result['title'])}»</p>"
        f"<p class='c' style='margin-top:12pt'>{e(labels['subject'])}: {e(params['subject'] or BLANK)}</p>"
        f"<p class='r' style='margin-top:130pt'>{e(labels['student'])}: {BLANK}</p>"
        f"<p class='r' style='margin-top:12pt'>{e(labels['teacher'])}: {BLANK}</p>"
        f"<p class='c' style='margin-top:90pt'>{e(labels['year'].format(y=datetime.now().year))}</p>"
    )
    plan = f"<h1>{e(labels['plan'])}</h1>" + "".join(
        f"<p class='n' style='margin-left:{35 if SUBSECTION.match(item) else 0}pt'>{e(item)}</p>"
        for item in result["plan"]
    )
    pages = [title_page, plan]
    for part in result["sections"]:
        tag = "h2" if SUBSECTION.match(part["heading"]) else "h1"
        block = f"<{tag}>{e(part['heading'])}</{tag}>" + "".join(
            f"<p>{e(p.strip())}</p>" for p in part["content"].split("\n\n") if p.strip()
        )
        if tag == "h1":
            pages.append(block)
        else:
            pages[-1] += block
    pages.append(f"<h1>{e(result['plan'][-1])}</h1>" + "".join(
        f"<p class='n'>{n}. {e(item)}</p>" for n, item in enumerate(result["references"], 1)
    ))
    return pages


def build_pdf_story(result, params):
    import pymupdf

    fonts = _fonts()
    archive = pymupdf.Archive()
    face = ""
    if fonts:
        for font in fonts:
            archive.add(str(font.parent))
        face = (f"@font-face {{font-family: Doc; src: url({fonts[0].name});}}"
                f"@font-face {{font-family: Doc; src: url({fonts[1].name}); font-weight: bold;}}")
    css = face + (
        "body {font-family: Doc, serif; font-size: 14pt; line-height: 1.5; text-align: justify;}"
        "p {margin: 0; text-indent: 35pt;} p.c, p.r, p.n {text-indent: 0;} .c {text-align: center;}"
        ".r {text-align: right;} .b {font-weight: bold;}"
        "h1 {font-size: 14pt; text-align: center; margin: 0 0 12pt 0;}"
        "h2 {font-size: 14pt; text-align: left; margin: 6pt 0 12pt 0;}"
    )
    page_box = pymupdf.paper_rect("a4")
    area = page_box + (3 * CM, 2 * CM, -1.5 * CM, -2 * CM)
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    for body in _html_document(result, params):  # titul, reja va har bir bob — yangi sahifadan
        story = pymupdf.Story(html=f"<body>{body}</body>", user_css=css, archive=archive)
        more = True
        while more:
            device = writer.begin_page(page_box)
            more, _ = story.place(area)
            story.draw(device)
            writer.end_page()
    writer.close()

    # Sahifa raqamlari (titulda yo'q)
    pdf = pymupdf.open(stream=buffer.getvalue(), filetype="pdf")
    for index, page in enumerate(pdf):
        if index:
            text = str(index + 1)
            width = pymupdf.get_text_length(text, fontname="Times-Roman", fontsize=12)
            page.insert_text(((page.rect.width - width) / 2, page.rect.height - 1.2 * CM), text,
                             fontname="Times-Roman", fontsize=12)
    pdf.set_metadata({"title": result["title"]})
    pdf.subset_fonts()  # shriftdan faqat ishlatilgan harflar — fayl ~1.3 MB dan bir necha o'n KB ga tushadi
    return pdf.tobytes(garbage=3, deflate=True)


async def build_pdf(result, params, docx):
    if PDF_AVAILABLE:
        try:
            return await to_pdf(docx, "docx")  # Word faylining aniq nusxasi
        except ConvertError:
            pass
    return await asyncio.to_thread(build_pdf_story, result, params)


# ===== Hammasi =====
async def build_files(result, params):
    """[{name, ext, mime, data}] — taqdimot uchun .pptx, matnli ishlar uchun .docx va .pdf."""
    if params["type"] == "pres":
        data = await asyncio.to_thread(
            build_outline_pptx, result["title"], params["subject"], result["slides"], PPTX_THEME, params["language"],
        )
        return [{"name": safe_filename(params["topic"], "pptx"), "ext": "pptx", "mime": MIME["pptx"], "data": data}]
    docx = await asyncio.to_thread(build_docx, result, params)
    pdf = await build_pdf(result, params, docx)
    return [
        {"name": safe_filename(params["topic"], "docx"), "ext": "docx", "mime": MIME["docx"], "data": docx},
        {"name": safe_filename(params["topic"], "pdf"), "ext": "pdf", "mime": MIME["pdf"], "data": pdf},
    ]
