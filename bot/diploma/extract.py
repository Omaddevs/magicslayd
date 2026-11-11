"""Yuklangan fayldan matn: metodik qo'llanma (PDF/DOCX) va amaliy qism materiallari (PDF/DOCX/TXT/CSV/XLSX).
Excel uchun qo'shimcha kutubxona kerak emas — .xlsx ichidagi XML to'g'ridan-to'g'ri o'qiladi."""
import csv
import io
import re
import zipfile
from xml.etree import ElementTree

MAX_CHARS = 60_000  # AI'ga beriladigan matn chegarasi (qo'llanma odatda 10–40 ming belgi)
EXTENSIONS = ("pdf", "docx", "txt", "csv", "xlsx")


class ExtractError(Exception):
    """Foydalanuvchiga ko'rsatsa bo'ladigan xato."""


def detect(data, name=""):
    """Fayl turi (kengaytma) — ichidan aniqlanadi, nomga ishonilmaydi (nomi faqat matnli fayllar uchun)."""
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:2] == b"PK":
        try:
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        except zipfile.BadZipFile as e:
            raise ExtractError("Fayl buzilgan.") from e
        if any(n.startswith("word/") for n in names):
            return "docx"
        if any(n.startswith("xl/") for n in names):
            return "xlsx"
        raise ExtractError("Bu fayl turi qo'llab-quvvatlanmaydi.")
    if data[:4] == b"\xd0\xcf\x11\xe0":
        raise ExtractError("Eski .doc / .xls formati. Word yoki Excel'da .docx / .xlsx qilib saqlab, qayta yuklang.")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext in ("csv", "txt"):
        return ext
    try:
        data[:2000].decode("utf-8")
        return "txt"
    except UnicodeDecodeError as e:
        raise ExtractError("Faqat PDF, DOCX, XLSX, CSV yoki TXT fayl yuklash mumkin.") from e


def _pdf(data):
    import pymupdf

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        raise ExtractError("PDF faylni ochib bo'lmadi.") from e
    if doc.needs_pass:
        raise ExtractError("PDF parol bilan himoyalangan.")
    parts = []
    for page in doc:
        parts.append(page.get_text("text"))
        if sum(map(len, parts)) > MAX_CHARS:
            break
    text = "\n".join(parts)
    if len(text.strip()) < 50:
        raise ExtractError("PDF dan matn topilmadi — u skanerlangan (rasm) bo'lishi mumkin. DOCX ko'rinishida yuklang.")
    return text


def _docx(data):
    from docx import Document

    doc = Document(io.BytesIO(data))
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:  # qo'llanmalarda talablar ko'pincha jadvalda bo'ladi
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def _xlsx(data, max_rows=200):
    """Birinchi varaqning qatorlari: «A | B | C» ko'rinishida."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    archive = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if "xl/sharedStrings.xml" in archive.namelist():
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
        shared = ["".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")) for si in root.findall("m:si", ns)]
    sheets = sorted(n for n in archive.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
    if not sheets:
        raise ExtractError("Excel faylda varaq topilmadi.")
    root = ElementTree.fromstring(archive.read(sheets[0]))
    lines = []
    for row in root.iter(f"{{{ns['m']}}}row"):
        cells = []
        for cell in row.findall("m:c", ns):
            value = cell.find("m:v", ns)
            inline = cell.find("m:is", ns)
            if cell.get("t") == "s" and value is not None:
                cells.append(shared[int(value.text)] if int(value.text) < len(shared) else "")
            elif inline is not None:
                cells.append("".join(t.text or "" for t in inline.iter(f"{{{ns['m']}}}t")))
            else:
                cells.append(value.text if value is not None else "")
        if any(c.strip() for c in cells):
            lines.append(" | ".join(cells))
        if len(lines) >= max_rows:
            lines.append("… (qolgan qatorlar qisqartirildi)")
            break
    return "\n".join(lines)


def _csv(data, max_rows=200):
    text = data.decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    lines = []
    for i, row in enumerate(csv.reader(io.StringIO(text), dialect)):
        if i >= max_rows:
            lines.append("… (qolgan qatorlar qisqartirildi)")
            break
        lines.append(" | ".join(row))
    return "\n".join(lines)


def extract(data, name=""):
    """(matn, tur). Matn MAX_CHARS bilan cheklanadi. Xato bo'lsa — ExtractError."""
    kind = detect(data, name)
    try:
        if kind == "pdf":
            text = _pdf(data)
        elif kind == "docx":
            text = _docx(data)
        elif kind == "xlsx":
            text = _xlsx(data)
        elif kind == "csv":
            text = _csv(data)
        else:
            text = data.decode("utf-8", errors="replace")
    except ExtractError:
        raise
    except Exception as e:  # noqa: BLE001 — buzuq fayl
        raise ExtractError("Faylni o'qib bo'lmadi. U buzilgan bo'lishi mumkin.") from e
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise ExtractError("Faylda matn topilmadi.")
    return text[:MAX_CHARS], kind
