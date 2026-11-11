"""Maqolani Word (DOCX, python-docx) va PDF (PyMuPDF — LibreOffice kerak emas) ga aylantiradi.
Ikkalasi ham bir xil bloklardan quriladi: sarlavhalar, formatlangan matn (qalin, kursiv, tagiga chizilgan, rang,
o'lcham, havola), ro'yxatlar, jadvallar va rasmlar (o'lchami, joylashuvi, izohi bilan).
A4, 2 sm hoshiya, Times New Roman 12 (PDF da — Noto Serif, o'zbek/kirill harflari to'liq), 1.5 interval."""
import html
import io

import pymupdf
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from PIL import Image

from metadata import clean_properties

FONT = "Times New Roman"
BODY_PT = 12
HEADING_PT = {1: 15, 2: 13, 3: 12}
TEXT_WIDTH_CM = 17  # A4 (21 sm) − 2 × 2 sm hoshiya
DOCX_ALIGN = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
              "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}


def safe_image(data):
    """Rasmni tekshiradi va JPEG/PNG holiga keltiradi (buzuq rasm butun hujjatni buzmasin)."""
    if not data:
        return None
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if image.format in ("JPEG", "PNG"):
                return data
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, "JPEG", quality=88)
            return buffer.getvalue()
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


# ===================================================================================================
# Word
def _font(style, size, bold=False, italic=False):
    style.font.name = FONT
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.italic = italic
    style.font.color.rgb = RGBColor(0, 0, 0)
    fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        fonts.attrib.pop(qn(attr), None)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(attr), FONT)


def _style_run(run, r):
    run.bold = bool(r.get("b")) or None
    run.italic = bool(r.get("i")) or None
    run.underline = bool(r.get("u")) or None
    if r.get("color"):
        run.font.color.rgb = RGBColor.from_string(r["color"][1:].upper())
    if r.get("size"):
        run.font.size = Pt(r["size"])


def _hyperlink(paragraph, r):
    """Bosiladigan havola (python-docx'da tayyor funksiya yo'q — XML orqali)."""
    rel = paragraph.part.relate_to(r["link"], RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), rel)
    run = OxmlElement("w:r")
    props = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), (r.get("color") or "#1d4ed8")[1:].upper())
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    props.extend([color, underline])
    for key, tag in (("b", "w:b"), ("i", "w:i")):
        if r.get(key):
            props.append(OxmlElement(tag))
    if r.get("size"):
        size = OxmlElement("w:sz")
        size.set(qn("w:val"), str(r["size"] * 2))
        props.append(size)
    run.append(props)
    text = OxmlElement("w:t")
    text.text = r["text"]
    text.set(qn("xml:space"), "preserve")
    run.append(text)
    link.append(run)
    paragraph._p.append(link)


def _fill(paragraph, runs):
    for r in runs:
        if r.get("link"):
            _hyperlink(paragraph, r)
        else:
            _style_run(paragraph.add_run(r["text"]), r)


def _spacing(p, line=1.5, before=0, after=6, indent=None):
    fmt = p.paragraph_format
    fmt.line_spacing = line
    fmt.space_before, fmt.space_after = Pt(before), Pt(after)
    if indent is not None:
        fmt.first_line_indent = indent


def _page_numbers(section):
    para = section.footer.paragraphs[0]
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    run, text = OxmlElement("w:r"), OxmlElement("w:t")
    text.text = "1"
    run.append(text)
    field.append(run)
    para._p.append(field)


def _shade(cell, color):
    props = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), color)
    props.append(shading)


def build_docx(article, read_media, author=""):
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin = section.right_margin = section.top_margin = section.bottom_margin = Cm(2)
    _page_numbers(section)
    _font(doc.styles["Normal"], BODY_PT)
    for level, size in HEADING_PT.items():
        _font(doc.styles[f"Heading {level}"], size, bold=True, italic=level == 3)

    # Sarlavha — oddiy xatboshi (Word'ning «Title» uslubi ostiga ko'k chiziq chizadi)
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _spacing(title, line=1.2, after=6)
    title.paragraph_format.keep_with_next = True
    run = title.add_run(article["title"])
    run.bold = True
    run.font.size = Pt(16)
    if author:
        line = doc.add_paragraph()
        line.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _spacing(line, line=1.2, after=12)
        run = line.add_run(author)
        run.italic = True

    for block in article["blocks"]:
        kind = block["t"]
        if kind == "h":
            p = doc.add_paragraph(style=f"Heading {block['level']}")
            p.alignment = DOCX_ALIGN.get(block["align"], WD_ALIGN_PARAGRAPH.LEFT)
            _spacing(p, line=1.3, before=12, after=6)
            p.paragraph_format.keep_with_next = True
            _fill(p, block["runs"])
        elif kind == "p":
            p = doc.add_paragraph()
            p.alignment = DOCX_ALIGN.get(block["align"], WD_ALIGN_PARAGRAPH.JUSTIFY)
            _spacing(p, indent=Cm(1.25) if block["align"] in ("justify", "left") else None)
            _fill(p, block["runs"])
        elif kind in ("ul", "ol"):
            for n, item in enumerate(block["items"], 1):
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                _spacing(p, after=3)
                p.paragraph_format.left_indent = Cm(1.0)
                p.paragraph_format.first_line_indent = Cm(-0.6)
                p.add_run(f"{n}. " if kind == "ol" else "•  ")
                _fill(p, item)
        elif kind == "table":
            rows, cols = len(block["rows"]), max(len(r) for r in block["rows"])
            table = doc.add_table(rows=rows, cols=cols)
            table.style = "Table Grid"
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            for r, row in enumerate(block["rows"]):
                for c, cell_runs in enumerate(row):
                    cell = table.cell(r, c)
                    p = cell.paragraphs[0]
                    _spacing(p, line=1.15, after=0)
                    header = block["head"] and r == 0
                    _fill(p, [{**run, "b": 1} if header else run for run in cell_runs])
                    if header:
                        _shade(cell, "E8ECF4")
            doc.add_paragraph()
        elif kind == "img":
            data = safe_image(read_media(block["src"]))
            if not data:
                continue
            p = doc.add_paragraph()
            p.alignment = DOCX_ALIGN[block["align"]]
            _spacing(p, line=1.0, before=6, after=2)
            p.paragraph_format.keep_with_next = True
            p.add_run().add_picture(io.BytesIO(data), width=Cm(TEXT_WIDTH_CM * block["width"] / 100))
            if block["caption"]:
                caption = doc.add_paragraph()
                caption.alignment = DOCX_ALIGN[block["align"]]
                _spacing(caption, line=1.15, after=8)
                run = caption.add_run(block["caption"])
                run.italic = True
                run.font.size = Pt(10)

    clean_properties(doc.core_properties, article["title"])
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


# ===================================================================================================
# PDF (HTML → PyMuPDF Story)
CSS = """
body { font-family: serif; font-size: 12pt; line-height: 1.5; color: #111; }
h1.title { font-size: 17pt; text-align: center; margin: 0 0 4pt 0; line-height: 1.25; }
p.author { text-align: center; font-style: italic; margin: 0 0 14pt 0; }
h1 { font-size: 15pt; margin: 14pt 0 6pt 0; line-height: 1.3; }
h2 { font-size: 13pt; margin: 12pt 0 6pt 0; line-height: 1.3; }
h3 { font-size: 12pt; font-style: italic; margin: 10pt 0 4pt 0; }
p { margin: 0 0 6pt 0; }
p.indent { text-indent: 1.25cm; }
ul, ol { margin: 0 0 6pt 0; }
li { margin: 0 0 3pt 0; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 10pt 0; }
td, th { border: 1px solid #555; padding: 4pt 5pt; font-size: 11pt; line-height: 1.3; vertical-align: top; }
th { font-weight: bold; border-bottom: 2px solid #222; }
p.figure { margin: 6pt 0 2pt 0; text-indent: 0; }
p.caption { font-size: 10pt; font-style: italic; margin: 0 0 10pt 0; text-indent: 0; }
a { color: #1d4ed8; }
"""


def _html_runs(runs):
    out = []
    for r in runs:
        text = html.escape(r["text"]).replace("\n", "<br/>")
        styles = []
        if r.get("color"):
            styles.append(f"color:{r['color']}")
        if r.get("size"):
            styles.append(f"font-size:{r['size']}pt")
        if styles:
            text = f'<span style="{";".join(styles)}">{text}</span>'
        if r.get("b"):
            text = f"<b>{text}</b>"
        if r.get("i"):
            text = f"<i>{text}</i>"
        if r.get("u"):
            text = f"<u>{text}</u>"
        if r.get("link"):
            text = f'<a href="{html.escape(r["link"], quote=True)}">{text}</a>'
        out.append(text)
    return "".join(out)


def article_html(article, images, author=""):
    parts = [f'<h1 class="title">{html.escape(article["title"])}</h1>']
    if author:
        parts.append(f'<p class="author">{html.escape(author)}</p>')
    for block in article["blocks"]:
        kind = block["t"]
        if kind == "h":
            tag = f"h{block['level']}"
            parts.append(f'<{tag} style="text-align:{block["align"]}">{_html_runs(block["runs"])}</{tag}>')
        elif kind == "p":
            indent = ' class="indent"' if block["align"] in ("justify", "left") else ""
            parts.append(f'<p{indent} style="text-align:{block["align"]}">{_html_runs(block["runs"])}</p>')
        elif kind in ("ul", "ol"):
            items = "".join(f"<li>{_html_runs(item)}</li>" for item in block["items"])
            parts.append(f"<{kind}>{items}</{kind}>")
        elif kind == "table":
            rows = []
            for r, row in enumerate(block["rows"]):
                tag = "th" if block["head"] and r == 0 else "td"
                rows.append("<tr>" + "".join(f"<{tag}>{_html_runs(cell)}</{tag}>" for cell in row) + "</tr>")
            parts.append(f"<table>{''.join(rows)}</table>")
        elif kind == "img" and block["src"] in images:
            width = round(TEXT_WIDTH_CM * block["width"] / 100, 2)
            parts.append(f'<p class="figure" style="text-align:{block["align"]}">'
                         f'<img src="{block["src"]}" style="width:{width}cm"/></p>')
            if block["caption"]:
                parts.append(f'<p class="caption" style="text-align:{block["align"]}">'
                             f'{html.escape(block["caption"])}</p>')
    return f"<html><body>{''.join(parts)}</body></html>"


def build_pdf(article, read_media, author=""):
    images = {}
    for block in article["blocks"]:
        if block["t"] == "img" and block["src"] not in images:
            data = safe_image(read_media(block["src"]))
            if data:
                images[block["src"]] = data
    archive = pymupdf.Archive()
    for name, data in images.items():
        archive.add(data, name)
    story = pymupdf.Story(html=article_html(article, images, author), user_css=CSS, archive=archive)
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    page = pymupdf.paper_rect("a4")
    margin = 2 / 2.54 * 72  # 2 sm
    where = page + (margin, margin, -margin, -margin)
    more = True
    while more:
        device = writer.begin_page(page)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
    writer.close()

    # Sahifa raqamlari va hujjat xossalari
    doc = pymupdf.open("pdf", buffer.getvalue())
    for number, pdf_page in enumerate(doc, 1):
        width = pdf_page.rect.width
        pdf_page.insert_text((width / 2 - 4, pdf_page.rect.height - margin / 2), str(number), fontsize=10,
                             fontname="tiro", color=(0.3, 0.3, 0.3))
    doc.set_metadata({"title": article["title"], "author": "", "creator": "", "producer": ""})
    return doc.tobytes(deflate=True, garbage=3)


def build(article, read_media, fmt, author=""):
    return (build_pdf if fmt == "pdf" else build_docx)(article, read_media, author)
