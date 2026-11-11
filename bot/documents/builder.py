"""AI yozgan matndan .docx hujjat yasaydi (python-docx).
Talablar: A4, Times New Roman 14, 1.5 interval, xatboshi 1.25 sm, chap 3 sm / o'ng 1.5 sm hoshiya."""
import io
from datetime import datetime

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from metadata import clean_properties

FONT = "Times New Roman"
ROMAN = ("I", "II", "III", "IV", "V", "VI")

LABELS = {
    "uz": {"referat": "REFERAT", "mustaqil": "MUSTAQIL ISH", "kurs": "KURS ISHI", "subject": "Fan", "topic": "Mavzu",
           "student": "Bajardi", "group": "Guruh", "teacher": "Qabul qildi", "contents": "MUNDARIJA", "intro": "KIRISH",
           "conclusion": "XULOSA", "references": "FOYDALANILGAN ADABIYOTLAR", "chapter": "{n} BOB.",
           "figure": "{n}-rasm."},
    "ru": {"referat": "РЕФЕРАТ", "mustaqil": "САМОСТОЯТЕЛЬНАЯ РАБОТА", "kurs": "КУРСОВАЯ РАБОТА", "subject": "Предмет",
           "topic": "Тема", "student": "Выполнил(а)", "group": "Группа", "teacher": "Проверил(а)",
           "contents": "СОДЕРЖАНИЕ", "intro": "ВВЕДЕНИЕ", "conclusion": "ЗАКЛЮЧЕНИЕ",
           "references": "СПИСОК ИСПОЛЬЗОВАННОЙ ЛИТЕРАТУРЫ", "chapter": "ГЛАВА {n}.", "figure": "Рис. {n}."},
    "en": {"referat": "REPORT", "mustaqil": "INDEPENDENT WORK", "kurs": "COURSE PAPER", "subject": "Subject",
           "topic": "Topic", "student": "Prepared by", "group": "Group", "teacher": "Checked by",
           "contents": "CONTENTS", "intro": "INTRODUCTION", "conclusion": "CONCLUSION", "references": "REFERENCES",
           "chapter": "CHAPTER {n}.", "figure": "Figure {n}."},
}


def set_font(style, size, bold=False):
    style.font.name = FONT
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.color.rgb = RGBColor(0, 0, 0)
    fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
    # Sarlavha uslublari mavzu shriftiga (Calibri Light) bog'langan — bog'lanishni olib tashlaymiz
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        fonts.attrib.pop(qn(attr), None)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(attr), FONT)


def page_number(section):
    """Pastki kolontitulga sahifa raqami (muqovada ko'rinmaydi)."""
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


class Paper:
    def __init__(self, content, kind, lang, title):
        self.content = content
        self.kind = kind
        self.labels = LABELS.get(lang, LABELS["uz"])
        self.title = title or {}
        self.doc = Document()
        section = self.doc.sections[0]
        section.page_width, section.page_height = Cm(21), Cm(29.7)
        section.left_margin, section.right_margin = Cm(3), Cm(1.5)
        section.top_margin = section.bottom_margin = Cm(2)
        page_number(section)
        set_font(self.doc.styles["Normal"], 14)
        for name in ("Heading 1", "Heading 2"):
            set_font(self.doc.styles[name], 14, bold=True)

    def para(self, value="", align=WD_ALIGN_PARAGRAPH.JUSTIFY, indent=True, bold=False, size=None, before=0, after=0):
        p = self.doc.add_paragraph()
        fmt = p.paragraph_format
        fmt.alignment = align
        fmt.line_spacing = 1.5
        fmt.space_before, fmt.space_after = Pt(before), Pt(after)
        if indent:
            fmt.first_line_indent = Cm(1.25)
        if value:
            run = p.add_run(value)
            run.bold = bold
            if size:
                run.font.size = Pt(size)
        return p

    def heading(self, value, level=1, new_page=False):
        p = self.doc.add_paragraph(value, style=f"Heading {level}")
        fmt = p.paragraph_format
        fmt.alignment = WD_ALIGN_PARAGRAPH.CENTER if level == 1 else WD_ALIGN_PARAGRAPH.LEFT
        fmt.first_line_indent = None if level == 1 else Cm(1.25)
        fmt.line_spacing = 1.5
        fmt.space_before, fmt.space_after = Pt(0 if new_page else 12), Pt(6)
        fmt.page_break_before = new_page
        fmt.keep_with_next = True
        return p

    def figure(self, image, caption):
        """Markazdagi rasm va uning ostidagi imzo («1-rasm. ...»)."""
        p = self.para(align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, before=6)
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.line_spacing = 1.0  # 1.5 interval rasm balandligiga ham qo'llanib, bo'sh joy qoldiradi
        p.add_run().add_picture(io.BytesIO(image), width=Cm(14))
        caption_p = self.para(caption, WD_ALIGN_PARAGRAPH.CENTER, indent=False, size=12, after=6)
        caption_p.runs[0].italic = True

    def chapter_title(self, number, title):
        if self.kind == "kurs":
            return f"{self.labels['chapter'].format(n=ROMAN[number - 1])} {title.upper()}"
        return f"{number}. {title}"

    # ----- Muqova -----
    def cover(self):
        t, center = self.title, WD_ALIGN_PARAGRAPH.CENTER
        if t.get("university"):
            self.para(t["university"].upper(), center, indent=False, bold=True)
        if t.get("faculty"):
            self.para(t["faculty"], center, indent=False)
        self.para(self.labels[self.kind], center, indent=False, bold=True, size=28, before=150, after=12)
        if t.get("subject"):
            self.para(f"{self.labels['subject']}: {t['subject']}", center, indent=False)
        topic = self.para(align=center, indent=False)
        topic.add_run(f"{self.labels['topic']}: ").bold = True
        topic.add_run(f"«{self.content['title']}»")

        people = [(self.labels["student"], t.get("student")), (self.labels["group"], t.get("group")),
                  (self.labels["teacher"], t.get("teacher"))]
        first = True
        for label, value in people:
            if not value:
                continue
            p = self.para(align=WD_ALIGN_PARAGRAPH.LEFT, indent=False, before=90 if first else 0)
            p.paragraph_format.left_indent = Cm(7.5)  # o'ng tomondagi blok; uzun F.I.Sh. ham bir qatorga sig'sin
            p.add_run(f"{label}: ").bold = True
            p.add_run(value)
            first = False
        year = str(datetime.now().year)
        footer = f"{t['city']} — {year}" if t.get("city") else year
        # Shahar va yil — sahifa pastiga yaqin (uzun mavzu 3 qatorga cho'zilsa ham muqova 1 betga sig'adi)
        self.para(footer, center, indent=False, before=160 if first else 100)

    # ----- Mundarija -----
    def contents(self):
        self.heading(self.labels["contents"], new_page=True)
        lines = [self.labels["intro"]]
        for i, chapter in enumerate(self.content["chapters"], 1):
            lines.append(self.chapter_title(i, chapter["title"]))
            lines += [f"    {i}.{j}. {sec['title']}" for j, sec in enumerate(chapter["sections"], 1)]
        lines += [self.labels["conclusion"]]
        if self.content["references"]:
            lines.append(self.labels["references"])
        for line in lines:
            self.para(line, WD_ALIGN_PARAGRAPH.LEFT, indent=False)

    def body(self):
        self.heading(self.labels["intro"], new_page=True)
        for text in self.content["intro"]:
            self.para(text)
        figure = 0
        for i, chapter in enumerate(self.content["chapters"], 1):
            # Kurs ishida har bir bob yangi sahifadan boshlanadi
            self.heading(self.chapter_title(i, chapter["title"]), new_page=self.kind == "kurs")
            for j, sec in enumerate(chapter["sections"], 1):
                self.heading(f"{i}.{j}. {sec['title']}", level=2)
                for k, text in enumerate(sec["paragraphs"]):
                    self.para(text)
                    if j == 1 and k == 0 and chapter.get("image"):  # bob rasmi — birinchi xatboshidan keyin
                        figure += 1
                        self.figure(chapter["image"], f"{self.labels['figure'].format(n=figure)} {chapter['title']}")
                    elif k == 0 and sec.get("image"):  # bo'lim rasmi — shu bo'limning birinchi xatboshisidan keyin
                        figure += 1
                        self.figure(sec["image"], f"{self.labels['figure'].format(n=figure)} {sec['title']}")
        self.heading(self.labels["conclusion"], new_page=True)
        for text in self.content["conclusion"]:
            self.para(text)
        if self.content["references"]:
            self.heading(self.labels["references"], new_page=True)
            for i, ref in enumerate(self.content["references"], 1):
                self.para(f"{i}. {ref}")

    def build(self):
        self.cover()
        self.contents()
        self.body()
        clean_properties(self.doc.core_properties, self.content["title"])
        buffer = io.BytesIO()
        self.doc.save(buffer)
        return buffer.getvalue()


def build_docx(content, kind, lang="uz", title=None):
    """Tayyor .docx faylni bytes ko'rinishida qaytaradi. title — foydalanuvchining titul ma'lumotlari."""
    return Paper(content, kind, lang, title).build()
