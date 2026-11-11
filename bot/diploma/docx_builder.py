"""Diplom ishini .docx ga yig'adi (python-docx). Talablar metodik qo'llanmadan (method.rules) olinadi,
yo'q bo'lsa — keng tarqalgan talablar: A4, Times New Roman 14, 1.5 interval, chap 3 / o'ng 1.5 / yuqori-pastki 2 sm.

- Mundarija — Word'ning avtomatik maydoni (TOC): fayl ochilganda yangilanadi, sahifa raqamlari bilan.
- Bob → «I BOB.», paragraf → «1.1.», rasm → «1.1-rasm», jadval → «1.1-jadval» (har bob ichida alohida raqam).
- Matndagi [n] iqtiboslar adabiyotlar ro'yxatidagi raqamlarga moslanadi (birinchi tilga olinish tartibida).
- Matn, jadval va rasmlar Word'da alohida tahrirlanadi."""
import io
import re
from datetime import datetime

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from diploma.designs import apply_document, body_font, decorate_heading, get_design
from diploma.sources import format_source
from metadata import clean_properties

ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII")
CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")

LABELS = {
    "uz": {"work": "BITIRUV MALAKAVIY ISHI", "topic": "Mavzu", "student": "Bajardi", "group": "Kurs va guruh",
           "specialty": "Mutaxassislik", "direction": "Ta'lim yo'nalishi", "supervisor": "Ilmiy rahbar",
           "contents": "MUNDARIJA", "intro": "KIRISH", "chapter": "{n} BOB.", "summary": "{n} bob bo'yicha xulosa",
           "conclusion": "XULOSA", "references": "FOYDALANILGAN ADABIYOTLAR", "figure": "{n}-rasm.", "table": "{n}-jadval.",
           "source": "Manba", "see_fig": "Bu {n}-rasmda ko'rsatilgan.", "see_table": "Batafsil {n}-jadvalda keltirilgan.",
           "toc_hint": "Mundarija Word'da avtomatik yangilanadi (sichqonchaning o'ng tugmasi → «Maydonni yangilash»)."},
    "ru": {"work": "ВЫПУСКНАЯ КВАЛИФИКАЦИОННАЯ РАБОТА", "topic": "Тема", "student": "Выполнил(а)", "group": "Курс и группа",
           "specialty": "Специальность", "direction": "Направление", "supervisor": "Научный руководитель",
           "contents": "СОДЕРЖАНИЕ", "intro": "ВВЕДЕНИЕ", "chapter": "ГЛАВА {n}.", "summary": "Выводы по главе {n}",
           "conclusion": "ЗАКЛЮЧЕНИЕ", "references": "СПИСОК ИСПОЛЬЗОВАННОЙ ЛИТЕРАТУРЫ", "figure": "Рис. {n}.",
           "table": "Таблица {n}.", "source": "Источник", "see_fig": "Это показано на рисунке {n}.",
           "see_table": "Подробнее — в таблице {n}.",
           "toc_hint": "Оглавление обновляется в Word автоматически (правая кнопка мыши → «Обновить поле»)."},
    "en": {"work": "GRADUATION THESIS", "topic": "Topic", "student": "Prepared by", "group": "Year and group",
           "specialty": "Specialty", "direction": "Field of study", "supervisor": "Supervisor", "contents": "CONTENTS",
           "intro": "INTRODUCTION", "chapter": "CHAPTER {n}.", "summary": "Conclusions to chapter {n}",
           "conclusion": "CONCLUSION", "references": "REFERENCES", "figure": "Figure {n}.", "table": "Table {n}.",
           "source": "Source", "see_fig": "This is shown in Figure {n}.", "see_table": "See Table {n} for details.",
           "toc_hint": "The table of contents updates in Word automatically (right click → «Update field»)."},
}


def citation_order(project):
    """Manba id → ro'yxatdagi raqam: avval matnda birinchi tilga olinish tartibida, keyin qolganlari."""
    texts = [p for item in project["intro"]["items"] for p in item["paragraphs"]]
    for chapter in project["chapters"]:
        texts += [p for s in chapter["sections"] for p in s["paragraphs"]] + list(chapter.get("summary") or [])
    texts += project["conclusion"]["paragraphs"]
    known = {s["n"] for s in project["sources"]}
    order = []
    for text in texts:
        for group in CITE.findall(text):
            for n in (int(x) for x in group.split(",")):
                if n in known and n not in order:
                    order.append(n)
    order += [s["n"] for s in project["sources"] if s["n"] not in order]
    return {n: i for i, n in enumerate(order, 1)}


class Thesis:
    def __init__(self, project):
        self.p = project
        self.lang = project["info"].get("lang") if project["info"].get("lang") in LABELS else "uz"
        self.l = LABELS[self.lang]
        rules = (project.get("method") or {}).get("rules") or {}
        self.design = get_design(project)
        self.font = body_font(project, rules)
        self.size = float(rules.get("font_size") or 14)
        self.spacing = float(rules.get("line_spacing") or 1.5)
        self.margins = {k: float(rules.get(f"margin_{k}") or d) for k, d in
                        (("left", 3), ("right", 1.5), ("top", 2), ("bottom", 2))}
        self.numbers = citation_order(project)
        self.doc = Document()
        section = self.doc.sections[0]
        section.page_width, section.page_height = Cm(21), Cm(29.7)
        section.left_margin, section.right_margin = Cm(self.margins["left"]), Cm(self.margins["right"])
        section.top_margin, section.bottom_margin = Cm(self.margins["top"]), Cm(self.margins["bottom"])
        self.page_numbers(section)
        self.style(self.doc.styles["Normal"], self.size)
        for name in ("Heading 1", "Heading 2"):
            self.style(self.doc.styles[name], self.size, bold=True)
        apply_document(self.doc, section, self.design)
        # Word fayl ochilganda maydonlarni (mundarija) yangilasin
        update = OxmlElement("w:updateFields")
        update.set(qn("w:val"), "true")
        self.doc.settings.element.append(update)

    # ----- yordamchilar -----
    def style(self, style, size, bold=False):
        style.font.name = self.font
        style.font.size = Pt(size)
        style.font.bold = bold
        style.font.italic = False
        style.font.color.rgb = RGBColor(0, 0, 0)
        fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
        for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
            fonts.attrib.pop(qn(attr), None)
        for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
            fonts.set(qn(attr), self.font)

    @staticmethod
    def page_numbers(section):
        section.different_first_page_header_footer = True
        para = section.footer.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        field = OxmlElement("w:fldSimple")
        field.set(qn("w:instr"), "PAGE")
        run, text = OxmlElement("w:r"), OxmlElement("w:t")
        text.text = "1"
        run.append(text)
        field.append(run)
        para._p.append(field)

    def cite(self, text):
        def repl(match):
            numbers = sorted({self.numbers[n] for n in (int(x) for x in match.group(1).split(",")) if n in self.numbers})
            return f"[{', '.join(map(str, numbers))}]" if numbers else ""
        return re.sub(r"\s+([.,;:])", r"\1", CITE.sub(repl, text)).strip()

    def para(self, value="", align=WD_ALIGN_PARAGRAPH.JUSTIFY, indent=True, bold=False, size=None, italic=False,
             before=0, after=0, keep=False):
        p = self.doc.add_paragraph()
        fmt = p.paragraph_format
        fmt.alignment = align
        fmt.line_spacing = self.spacing
        fmt.space_before, fmt.space_after = Pt(before), Pt(after)
        fmt.keep_with_next = keep
        if indent:
            fmt.first_line_indent = Cm(1.25)
        if value:
            run = p.add_run(value)
            run.bold, run.italic = bold, italic
            if size:
                run.font.size = Pt(size)
        return p

    def heading(self, value, level=1, new_page=False):
        p = self.doc.add_paragraph(value, style=f"Heading {level}")
        fmt = p.paragraph_format
        fmt.alignment = WD_ALIGN_PARAGRAPH.CENTER if level == 1 else WD_ALIGN_PARAGRAPH.LEFT
        fmt.first_line_indent = None if level == 1 else Cm(1.25)
        fmt.line_spacing = self.spacing
        fmt.space_before, fmt.space_after = Pt(0 if new_page else 12), Pt(12 if level == 1 else 6)
        fmt.page_break_before = new_page
        fmt.keep_with_next = True
        decorate_heading(p, self.design, level)
        return p

    def chapter_title(self, index, title):
        return f"{self.l['chapter'].format(n=ROMAN[index])} {title.upper()}"

    # ----- titul -----
    def title_page(self):
        info, l, center = self.p["info"], self.l, WD_ALIGN_PARAGRAPH.CENTER
        if info.get("university"):
            self.para(info["university"].upper(), center, indent=False, bold=True)
        if info.get("faculty"):
            self.para(info["faculty"], center, indent=False)
        if info.get("direction"):
            self.para(f"{l['direction']}: {info['direction']}", center, indent=False)
        self.para(l["work"], center, indent=False, bold=True, size=self.size + 8, before=110, after=12)
        topic = self.para(align=center, indent=False)
        topic.add_run(f"{l['topic']}: ").bold = True
        topic.add_run(f"«{info['topic']}»")
        first = True
        for label, key in (("student", "student"), ("group", "course_group"), ("specialty", "specialty"),
                           ("supervisor", "supervisor")):
            if not info.get(key):
                continue
            p = self.para(align=WD_ALIGN_PARAGRAPH.LEFT, indent=False, before=70 if first else 0)
            p.paragraph_format.left_indent = Cm(8)
            p.add_run(f"{l[label]}: ").bold = True
            p.add_run(info[key])
            first = False
        self.para(str(datetime.now().year), center, indent=False, before=120 if first else 80)

    # ----- mundarija (Word maydoni) -----
    def contents(self):
        # Sarlavha uslubisiz — aks holda «MUNDARIJA» ning o'zi ham mundarijaga tushadi
        title = self.para(self.l["contents"], WD_ALIGN_PARAGRAPH.CENTER, indent=False, bold=True, after=12)
        title.paragraph_format.page_break_before = True
        p = self.doc.add_paragraph()
        begin, instr, separate, end = (OxmlElement("w:fldChar"), OxmlElement("w:instrText"),
                                       OxmlElement("w:fldChar"), OxmlElement("w:fldChar"))
        begin.set(qn("w:fldCharType"), "begin")
        instr.set(qn("xml:space"), "preserve")
        instr.text = 'TOC \\o "1-2" \\h \\z \\u'
        separate.set(qn("w:fldCharType"), "separate")
        end.set(qn("w:fldCharType"), "end")
        for node in (begin, instr, separate):
            run = OxmlElement("w:r")
            run.append(node)
            p._p.append(run)
        # Maydon yangilanmaguncha ko'rinadigan matn — sarlavhalar ro'yxati (bo'sh qolmasin)
        lines = [self.l["intro"]]
        for i, chapter in enumerate(self.p["chapters"]):
            lines.append(self.chapter_title(i, chapter["title"]))
            lines += [f"    {i + 1}.{j}. {s['title']}" for j, s in enumerate(chapter["sections"], 1)]
        lines += [self.l["conclusion"], self.l["references"]]
        for k, line in enumerate(lines):
            run = p.add_run(line)
            if k < len(lines) - 1:
                run.add_break(WD_BREAK.LINE)
        run = OxmlElement("w:r")
        run.append(end)
        p._p.append(run)

    # ----- matn -----
    def intro(self):
        self.heading(self.l["intro"], new_page=True)
        for item in self.p["intro"]["items"]:
            for k, text in enumerate(item["paragraphs"]):
                p = self.para()
                if k == 0:
                    p.add_run(f"{item['label']}. ").bold = True
                p.add_run(self.cite(text))

    @staticmethod
    def figure_path(item, folder):
        from diploma.storage import SAFE_NAME

        path = folder / item["file"] if item.get("file") and SAFE_NAME.match(item["file"]) else None
        return path if path and path.is_file() else None

    def figure(self, number, item, folder):
        path = self.figure_path(item, folder)
        p = self.para(align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, before=6, keep=True)
        p.paragraph_format.line_spacing = 1.0
        p.add_run().add_picture(str(path), width=Cm(15 if item["kind"] == "scheme" else 14))
        self.para(f"{self.l['figure'].format(n=number)} {item['caption']}", WD_ALIGN_PARAGRAPH.CENTER, indent=False,
                  size=self.size - 2, italic=True, keep=bool(item.get("source")))
        if item.get("source"):
            self.para(f"{self.l['source']}: {item['source']}", WD_ALIGN_PARAGRAPH.CENTER, indent=False,
                      size=self.size - 3, after=6)

    def table(self, number, item):
        caption = self.para(f"{self.l['table'].format(n=number)} {item['caption']}", WD_ALIGN_PARAGRAPH.RIGHT,
                            indent=False, size=self.size - 2, before=6, keep=True)
        caption.runs[0].italic = True
        table = self.doc.add_table(rows=1 + len(item["rows"]), cols=len(item["columns"]))
        table.style = "Table Grid"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        for row_i, values in enumerate([item["columns"]] + item["rows"]):
            for col_i, value in enumerate(values):
                cell = table.cell(row_i, col_i)
                cell.text = ""
                run = cell.paragraphs[0].add_run(value)
                run.font.size = Pt(self.size - 2)
                run.bold = row_i == 0
                cell.paragraphs[0].paragraph_format.line_spacing = 1.0
        if item.get("source"):
            self.para(f"{self.l['source']}: {item['source']}", WD_ALIGN_PARAGRAPH.LEFT, indent=False,
                      size=self.size - 3, before=3, after=6)

    def chapters(self, folder):
        for ci, chapter in enumerate(self.p["chapters"]):
            self.heading(self.chapter_title(ci, chapter["title"]), new_page=True)
            # Fayli yo'q rasm hisobga olinmaydi — matndagi havola va raqamlar doim mos bo'lsin
            figures = [f for f in chapter.get("figures") or [] if f["kind"] != "table" and self.figure_path(f, folder)]
            tables = [f for f in chapter.get("figures") or [] if f["kind"] == "table"]
            fig_no = table_no = 0
            for si, section in enumerate(chapter["sections"]):
                self.heading(f"{ci + 1}.{si + 1}. {section['title']}", level=2)
                for pi, text in enumerate(section["paragraphs"]):
                    here = [f for f in figures if f["section"] == si and min(f["paragraph"], len(section["paragraphs"]) - 1) == pi]
                    here_t = [t for t in tables if t["section"] == si and min(t["paragraph"], len(section["paragraphs"]) - 1) == pi]
                    refs = []
                    numbers_f = [f"{ci + 1}.{fig_no + k + 1}" for k in range(len(here))]
                    numbers_t = [f"{ci + 1}.{table_no + k + 1}" for k in range(len(here_t))]
                    refs += [self.l["see_fig"].format(n=n) for n in numbers_f]
                    refs += [self.l["see_table"].format(n=n) for n in numbers_t]
                    # Rasm/jadvalga havola — o'sha xatboshining oxirida (raqam har doim to'g'ri)
                    self.para(" ".join([self.cite(text)] + refs))
                    for item, number in zip(here, numbers_f):
                        self.figure(number, item, folder)
                        fig_no += 1
                    for item, number in zip(here_t, numbers_t):
                        self.table(number, item)
                        table_no += 1
            if chapter.get("summary"):
                self.heading(self.l["summary"].format(n=ROMAN[ci]), level=2)
                for text in chapter["summary"]:
                    self.para(self.cite(text))

    def ending(self):
        self.heading(self.l["conclusion"], new_page=True)
        for text in self.p["conclusion"]["paragraphs"]:
            self.para(self.cite(text))
        if self.p["sources"]:
            self.heading(self.l["references"], new_page=True)
            ordered = sorted(self.p["sources"], key=lambda s: self.numbers.get(s["n"], 10_000))
            for i, source in enumerate(ordered, 1):
                self.para(f"{i}. {format_source(source, self.lang)}", WD_ALIGN_PARAGRAPH.LEFT, indent=False)

    def build(self, folder):
        self.title_page()
        self.contents()
        self.intro()
        self.chapters(folder)
        self.ending()
        clean_properties(self.doc.core_properties, self.p["info"]["topic"])
        buffer = io.BytesIO()
        self.doc.save(buffer)
        return buffer.getvalue()


def build_docx(project, folder):
    """Tayyor .docx (bytes). folder — loyiha papkasi (rasmlar shu yerda)."""
    return Thesis(project).build(folder)
