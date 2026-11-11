"""Dissertatsiyani .docx ga yig'adi (python-docx). Tartib: titul → annotatsiya va kalit so'zlar → mundarija →
kirish → boblar (bob xulosalari bilan) → umumiy xulosa → foydalanilgan adabiyotlar → ilovalar.

Rasmiylashtirish metodik qo'llanmadan (method.rules) olinadi, yo'q bo'lsa — keng tarqalgan talablar
(A4, Times New Roman 14, 1.5 interval, chap 3 / o'ng 1.5 / yuqori-pastki 2 sm). Mundarija — Word maydoni (TOC),
rasm va jadvallar har bob ichida raqamlanadi, matnda ularga havola beriladi, [n] iqtiboslar ro'yxat bilan mos."""
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
from dissertation.storage import SAFE_NAME
from metadata import clean_properties

ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII")
CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
WORK = {
    "uz": {"master": "MAGISTRLIK DISSERTATSIYASI", "phd": "FALSAFA DOKTORI (PhD) DISSERTATSIYASI",
           "dsc": "FAN DOKTORI (DSc) DISSERTATSIYASI", "other": "ILMIY TADQIQOT ISHI"},
    "ru": {"master": "МАГИСТЕРСКАЯ ДИССЕРТАЦИЯ", "phd": "ДИССЕРТАЦИЯ ДОКТОРА ФИЛОСОФИИ (PhD)",
           "dsc": "ДИССЕРТАЦИЯ ДОКТОРА НАУК (DSc)", "other": "НАУЧНО-ИССЛЕДОВАТЕЛЬСКАЯ РАБОТА"},
    "en": {"master": "MASTER'S DISSERTATION", "phd": "DOCTOR OF PHILOSOPHY (PhD) DISSERTATION",
           "dsc": "DOCTOR OF SCIENCE (DSc) DISSERTATION", "other": "RESEARCH WORK"},
}
LABELS = {
    "uz": {"topic": "Mavzu", "student": "Tadqiqotchi", "specialty": "Ixtisoslik", "degree": "Ilmiy daraja",
           "supervisor": "Ilmiy rahbar", "consultant": "Ilmiy maslahatchi", "annotation": "ANNOTATSIYA",
           "keywords": "Kalit so'zlar", "contents": "MUNDARIJA", "intro": "KIRISH", "chapter": "{n} BOB.",
           "summary": "{n} bob bo'yicha xulosalar", "conclusion": "XULOSA", "references": "FOYDALANILGAN ADABIYOTLAR RO'YXATI",
           "appendix": "ILOVALAR", "appendix_n": "{n}-ilova", "figure": "{n}-rasm.", "table": "{n}-jadval.", "source": "Manba",
           "see_fig": "Bu {n}-rasmda ko'rsatilgan.", "see_table": "Batafsil {n}-jadvalda keltirilgan.",
           "data_appendix": "«{name}» ma'lumotlari (birinchi {k} qator)"},
    "ru": {"topic": "Тема", "student": "Соискатель", "specialty": "Специальность", "degree": "Учёная степень",
           "supervisor": "Научный руководитель", "consultant": "Научный консультант", "annotation": "АННОТАЦИЯ",
           "keywords": "Ключевые слова", "contents": "СОДЕРЖАНИЕ", "intro": "ВВЕДЕНИЕ", "chapter": "ГЛАВА {n}.",
           "summary": "Выводы по главе {n}", "conclusion": "ЗАКЛЮЧЕНИЕ", "references": "СПИСОК ИСПОЛЬЗОВАННОЙ ЛИТЕРАТУРЫ",
           "appendix": "ПРИЛОЖЕНИЯ", "appendix_n": "Приложение {n}", "figure": "Рис. {n}.", "table": "Таблица {n}.",
           "source": "Источник", "see_fig": "Это показано на рисунке {n}.", "see_table": "Подробнее — в таблице {n}.",
           "data_appendix": "Данные «{name}» (первые {k} строк)"},
    "en": {"topic": "Topic", "student": "Researcher", "specialty": "Specialty", "degree": "Degree", "supervisor": "Supervisor",
           "consultant": "Scientific consultant", "annotation": "ABSTRACT", "keywords": "Keywords", "contents": "CONTENTS",
           "intro": "INTRODUCTION", "chapter": "CHAPTER {n}.", "summary": "Conclusions to chapter {n}",
           "conclusion": "CONCLUSION", "references": "REFERENCES", "appendix": "APPENDICES", "appendix_n": "Appendix {n}",
           "figure": "Figure {n}.", "table": "Table {n}.", "source": "Source", "see_fig": "This is shown in Figure {n}.",
           "see_table": "See Table {n} for details.", "data_appendix": "Data «{name}» (first {k} rows)"},
}


def all_texts(project):
    texts = [p for item in project["intro"]["items"] for p in item["paragraphs"]]
    for chapter in project["chapters"]:
        texts += [p for s in chapter["sections"] for p in s["paragraphs"]] + list(chapter.get("summary") or [])
    return texts + project["conclusion"]["paragraphs"]


def citation_order(project):
    known, order = {s["n"] for s in project["sources"]}, []
    for text in all_texts(project):
        for group in CITE.findall(text):
            for n in (int(x) for x in group.split(",")):
                if n in known and n not in order:
                    order.append(n)
    order += [s["n"] for s in project["sources"] if s["n"] not in order]
    return {n: i for i, n in enumerate(order, 1)}


class Dissertation:
    def __init__(self, project, folder, tables=()):
        self.p, self.folder, self.tables = project, folder, list(tables)
        self.lang = project["info"].get("lang") if project["info"].get("lang") in LABELS else "uz"
        self.l = LABELS[self.lang]
        rules = project["method"].get("rules") or {}
        self.design = get_design(project)
        self.font = body_font(project, rules)
        self.size = float(rules.get("font_size") or 14)
        self.spacing = float(rules.get("line_spacing") or 1.5)
        margins = {k: float(rules.get(f"margin_{k}") or d) for k, d in (("left", 3), ("right", 1.5), ("top", 2), ("bottom", 2))}
        self.numbers = citation_order(project)
        self.doc = Document()
        section = self.doc.sections[0]
        section.page_width, section.page_height = Cm(21), Cm(29.7)
        section.left_margin, section.right_margin = Cm(margins["left"]), Cm(margins["right"])
        section.top_margin, section.bottom_margin = Cm(margins["top"]), Cm(margins["bottom"])
        self.page_numbers(section)
        self.style(self.doc.styles["Normal"], self.size)
        for name in ("Heading 1", "Heading 2"):
            self.style(self.doc.styles[name], self.size, bold=True)
        apply_document(self.doc, section, self.design)
        update = OxmlElement("w:updateFields")
        update.set(qn("w:val"), "true")
        self.doc.settings.element.append(update)

    def style(self, style, size, bold=False):
        style.font.name, style.font.size, style.font.bold, style.font.italic = self.font, Pt(size), bold, False
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
             before=0, after=0, keep=False, page_break=False):
        p = self.doc.add_paragraph()
        fmt = p.paragraph_format
        fmt.alignment, fmt.line_spacing = align, self.spacing
        fmt.space_before, fmt.space_after, fmt.keep_with_next = Pt(before), Pt(after), keep
        fmt.page_break_before = page_break
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
        fmt.page_break_before, fmt.keep_with_next = new_page, True
        decorate_heading(p, self.design, level)
        return p

    # ----- titul, annotatsiya, mundarija -----
    def title_page(self):
        info, l, center = self.p["info"], self.l, WD_ALIGN_PARAGRAPH.CENTER
        if info.get("university"):
            self.para(info["university"].upper(), center, indent=False, bold=True)
        if info.get("faculty"):
            self.para(info["faculty"], center, indent=False)
        if info.get("student"):
            self.para(info["student"], center, indent=False, bold=True, before=70)
        self.para(WORK[self.lang].get(self.p.get("kind") or "other", WORK[self.lang]["other"]), center, indent=False,
                  bold=True, size=self.size + 6, before=40 if info.get("student") else 110, after=12)
        topic = self.para(align=center, indent=False)
        topic.add_run(f"{l['topic']}: ").bold = True
        topic.add_run(f"«{info['topic']}»")
        specialty = " ".join(x for x in (info.get("specialty_code"), info.get("specialty")) if x)
        rows = [("specialty", specialty), ("degree", info.get("degree")),
                ("consultant" if self.p.get("kind") == "dsc" else "supervisor", info.get("supervisor"))]
        first = True
        for key, value in rows:
            if not value:
                continue
            p = self.para(align=WD_ALIGN_PARAGRAPH.LEFT, indent=False, before=60 if first else 0)
            p.paragraph_format.left_indent = Cm(7.5)
            p.add_run(f"{l[key]}: ").bold = True
            p.add_run(value)
            first = False
        self.para(str(datetime.now().year), center, indent=False, before=110 if first else 70)

    def annotation(self):
        annotation = self.p["annotation"]
        if not annotation["paragraphs"]:
            return
        self.para(self.l["annotation"], WD_ALIGN_PARAGRAPH.CENTER, indent=False, bold=True, after=12, page_break=True)
        for text in annotation["paragraphs"]:
            self.para(self.cite(text))
        if annotation["keywords"]:
            p = self.para(before=6)
            p.add_run(f"{self.l['keywords']}: ").bold = True
            p.add_run(", ".join(annotation["keywords"]) + ".")

    def contents(self):
        self.para(self.l["contents"], WD_ALIGN_PARAGRAPH.CENTER, indent=False, bold=True, after=12, page_break=True)
        p = self.doc.add_paragraph()
        nodes = [("begin", None), (None, 'TOC \\o "1-2" \\h \\z \\u'), ("separate", None)]
        for kind, instr in nodes:
            run = OxmlElement("w:r")
            if kind:
                node = OxmlElement("w:fldChar")
                node.set(qn("w:fldCharType"), kind)
            else:
                node = OxmlElement("w:instrText")
                node.set(qn("xml:space"), "preserve")
                node.text = instr
            run.append(node)
            p._p.append(run)
        lines = [self.l["intro"]]
        for i, chapter in enumerate(self.p["chapters"]):
            lines.append(self.chapter_title(i, chapter["title"]))
            lines += [f"    {i + 1}.{j}. {s['title']}" for j, s in enumerate(chapter["sections"], 1)]
        lines += [self.l["conclusion"], self.l["references"]]
        for k, line in enumerate(lines):
            run = p.add_run(line)
            if k < len(lines) - 1:
                run.add_break(WD_BREAK.LINE)
        run, end = OxmlElement("w:r"), OxmlElement("w:fldChar")
        end.set(qn("w:fldCharType"), "end")
        run.append(end)
        p._p.append(run)

    def chapter_title(self, index, title):
        return f"{self.l['chapter'].format(n=ROMAN[index])} {title.upper()}"

    # ----- matn -----
    def intro(self):
        self.heading(self.l["intro"], new_page=True)
        for item in self.p["intro"]["items"]:
            for k, text in enumerate(item["paragraphs"]):
                p = self.para()
                if k == 0:
                    p.add_run(f"{item['label']}. ").bold = True
                p.add_run(self.cite(text))

    def image_path(self, item):
        if not item.get("file") or not SAFE_NAME.match(item["file"]):
            return None
        path = self.folder / item["file"]
        return path if path.is_file() else None

    def figure(self, number, item):
        p = self.para(align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, before=6, keep=True)
        p.paragraph_format.line_spacing = 1.0
        p.add_run().add_picture(str(self.image_path(item)), width=Cm(15))
        self.para(f"{self.l['figure'].format(n=number)} {item['caption']}", WD_ALIGN_PARAGRAPH.CENTER, indent=False,
                  size=self.size - 2, italic=True, keep=bool(item.get("source")))
        if item.get("source"):
            self.para(f"{self.l['source']}: {item['source']}", WD_ALIGN_PARAGRAPH.CENTER, indent=False, size=self.size - 3, after=6)

    def table(self, number, columns, rows, caption=None, source=None):
        if caption:
            p = self.para(f"{self.l['table'].format(n=number)} {caption}", WD_ALIGN_PARAGRAPH.RIGHT, indent=False,
                          size=self.size - 2, before=6, keep=True)
            p.runs[0].italic = True
        table = self.doc.add_table(rows=1 + len(rows), cols=len(columns))
        table.style, table.alignment = "Table Grid", WD_TABLE_ALIGNMENT.CENTER
        for r, values in enumerate([columns] + rows):
            for c, value in enumerate(values[:len(columns)]):
                cell = table.cell(r, c)
                cell.text = ""
                run = cell.paragraphs[0].add_run(str(value))
                run.font.size, run.bold = Pt(self.size - 3), r == 0
                cell.paragraphs[0].paragraph_format.line_spacing = 1.0
        if source:
            self.para(f"{self.l['source']}: {source}", WD_ALIGN_PARAGRAPH.LEFT, indent=False, size=self.size - 3, before=3, after=6)

    def chapters(self):
        for ci, chapter in enumerate(self.p["chapters"]):
            self.heading(self.chapter_title(ci, chapter["title"]), new_page=True)
            figures = [f for f in chapter.get("figures") or [] if f["kind"] != "table" and self.image_path(f)]
            tables = [f for f in chapter.get("figures") or [] if f["kind"] == "table"]
            fig_no = table_no = 0
            for si, section in enumerate(chapter["sections"]):
                self.heading(f"{ci + 1}.{si + 1}. {section['title']}", level=2)
                last = len(section["paragraphs"]) - 1
                for pi, text in enumerate(section["paragraphs"]):
                    here = [f for f in figures if f["section"] == si and min(f["paragraph"], last) == pi]
                    here_t = [t for t in tables if t["section"] == si and min(t["paragraph"], last) == pi]
                    numbers_f = [f"{ci + 1}.{fig_no + k + 1}" for k in range(len(here))]
                    numbers_t = [f"{ci + 1}.{table_no + k + 1}" for k in range(len(here_t))]
                    refs = [self.l["see_fig"].format(n=n) for n in numbers_f] + [self.l["see_table"].format(n=n) for n in numbers_t]
                    self.para(" ".join([self.cite(text)] + refs))
                    for item, number in zip(here, numbers_f):
                        self.figure(number, item)
                    for item, number in zip(here_t, numbers_t):
                        self.table(number, item["columns"], item["rows"], item["caption"], item.get("source"))
                    fig_no, table_no = fig_no + len(here), table_no + len(here_t)
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
        if self.tables:
            self.heading(self.l["appendix"], new_page=True)
            for i, (name, headers, rows) in enumerate(self.tables, 1):
                k = min(15, len(rows))
                self.para(self.l["appendix_n"].format(n=i), WD_ALIGN_PARAGRAPH.RIGHT, indent=False, bold=True, before=12)
                self.para(self.l["data_appendix"].format(name=name, k=k), WD_ALIGN_PARAGRAPH.CENTER, indent=False, after=6)
                self.table(None, headers[:8], [r[:8] for r in rows[:k]])

    def build(self):
        self.title_page()
        self.annotation()
        self.contents()
        self.intro()
        self.chapters()
        self.ending()
        clean_properties(self.doc.core_properties, self.p["info"]["topic"])
        buffer = io.BytesIO()
        self.doc.save(buffer)
        return buffer.getvalue()


def build_docx(project, folder, tables=()):
    """Tayyor .docx (bytes). tables — ilovaga qo'yiladigan foydalanuvchi ma'lumotlari [(nomi, sarlavhalar, qatorlar)]."""
    return Dissertation(project, folder, tables).build()
