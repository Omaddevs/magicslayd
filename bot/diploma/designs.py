"""Diplom ishi va dissertatsiya uchun rasmiylashtirish dizaynlari («🎨 Boshqa dizaynda olish»).

Dizayn faqat ko'rinishni o'zgartiradi: sarlavha rangi, bob sarlavhasi ostidagi chiziq, sahifa ramkasi va shrift.
Metodik qo'llanmadagi talablar (shrift o'lchami, interval, chekkalar va qo'llanmada ko'rsatilgan shrift) doim ustun —
dizayn ularni buzmaydi. Tanlangan dizayn loyihada saqlanadi: project["design"]."""
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import RGBColor

DEFAULT_DESIGN = "classic"

# font — qo'llanmada shrift ko'rsatilmagan bo'lsa ishlatiladi; color — sarlavhalar rangi (None — qora);
# rule — 1-darajali sarlavha ostidagi chiziq rangi; border — sahifa ramkasi (Word chegara turi)
DOC_DESIGNS = {
    "classic": {
        "name": "📘 Klassik",
        "about": "Times New Roman, qora sarlavhalar — ko'pchilik OTM talabi",
        "font": "Times New Roman", "color": None, "rule": None, "border": None,
    },
    "frame": {
        "name": "🖼 Ramkali",
        "about": "Har bir sahifa chiziqli ramka ichida — texnik OTMlarda keng tarqalgan",
        "font": "Times New Roman", "color": None, "rule": None, "border": "single",
    },
    "modern": {
        "name": "🔷 Zamonaviy",
        "about": "To'q ko'k sarlavhalar, bob nomi ostida ingichka chiziq",
        "font": "Times New Roman", "color": "1F3864", "rule": "2E5597", "border": None,
    },
    "elegant": {
        "name": "✒️ Nafis",
        "about": "Cambria shrift, to'q bordo sarlavhalar va qo'sh ramka",
        "font": "Cambria", "color": "6B1E2B", "rule": "6B1E2B", "border": "double",
    },
}


def design_key(project):
    key = (project or {}).get("design")
    return key if key in DOC_DESIGNS else DEFAULT_DESIGN


def get_design(project):
    return DOC_DESIGNS[design_key(project)]


def body_font(project, rules):
    """Qo'llanmada shrift ko'rsatilgan bo'lsa — o'sha, aks holda dizayn shrifti."""
    return (rules or {}).get("font_name") or get_design(project)["font"]


def apply_document(doc, section, design):
    """Sarlavha uslublarining rangi va sahifa ramkasi (builder uslublarni sozlagandan keyin chaqiriladi)."""
    if design["color"]:
        for name in ("Heading 1", "Heading 2"):
            doc.styles[name].font.color.rgb = RGBColor.from_string(design["color"])
    if design["border"]:
        page_border(section, design["border"], design["color"] or "000000")


def page_border(section, kind, color):
    sect = section._sectPr
    old = sect.find(qn("w:pgBorders"))
    if old is not None:
        sect.remove(old)
    borders = OxmlElement("w:pgBorders")
    borders.set(qn("w:offsetFrom"), "text")
    for side in ("top", "left", "bottom", "right"):
        edge = OxmlElement(f"w:{side}")
        edge.set(qn("w:val"), kind)
        edge.set(qn("w:sz"), "6" if kind == "double" else "8")
        edge.set(qn("w:space"), "10" if side in ("left", "right") else "12")
        edge.set(qn("w:color"), color)
        borders.append(edge)
    # sectPr ichidagi tartib: ... pgSz, pgMar, paperSrc, pgBorders ...
    anchor = sect.find(qn("w:paperSrc"))
    if anchor is None:
        anchor = sect.find(qn("w:pgMar"))
    if anchor is not None:
        anchor.addnext(borders)
    else:
        sect.append(borders)


def decorate_heading(paragraph, design, level):
    """1-darajali sarlavha ostiga rangli chiziq (dizaynda bo'lsa)."""
    if level != 1 or not design["rule"]:
        return
    ppr = paragraph._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:space"), "6")
    bottom.set(qn("w:color"), design["rule"])
    bdr.append(bottom)
    # pPr ichida pBdr — keepNext/pageBreakBefore dan keyin, spacing/ind/jc dan oldin turishi kerak
    anchor = None
    for tag in ("w:spacing", "w:ind", "w:jc"):
        anchor = ppr.find(qn(tag))
        if anchor is not None:
            break
    if anchor is not None:
        anchor.addprevious(bdr)
    else:
        ppr.append(bdr)


def public_designs():
    """Web ilova uchun (handlers/web.py → web_config)."""
    return [{"key": k, "name": d["name"], "about": d["about"]} for k, d in DOC_DESIGNS.items()]
