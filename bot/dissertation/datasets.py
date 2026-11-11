"""Foydalanuvchi yuklagan jadval ma'lumotlari (CSV / XLSX): o'qish, statistik ko'rsatkichlar, grafik uchun qatorlar.

Barcha raqamlar FAQAT fayldan olinadi va shu yerda (Python'da) hisoblanadi — AI faqat qaysi ustunni qanday
ko'rsatishni tanlaydi. So'rovnoma javoblari (matnli ustun) — har bir javob necha marta uchragani sanaladi."""
import csv
import io
import re
import statistics
import zipfile
from collections import Counter
from xml.etree import ElementTree

MAX_ROWS = 5000
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


class DataError(Exception):
    """Foydalanuvchiga ko'rsatsa bo'ladigan xato."""


def _csv_rows(data):
    text = data.decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [row for row in csv.reader(io.StringIO(text), dialect)][:MAX_ROWS + 1]


def _col_index(ref):
    letters = re.match(r"[A-Z]+", ref or "A").group(0)
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def _xlsx_rows(data):
    archive = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if "xl/sharedStrings.xml" in archive.namelist():
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
        shared = ["".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")) for si in root.findall("m:si", NS)]
    sheets = sorted((n for n in archive.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)),
                    key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)))
    if not sheets:
        raise DataError("Excel faylda varaq topilmadi.")
    root = ElementTree.fromstring(archive.read(sheets[0]))
    rows = []
    for row in root.iter(f"{{{NS['m']}}}row"):
        cells = {}
        for cell in row.findall("m:c", NS):
            value, inline = cell.find("m:v", NS), cell.find("m:is", NS)
            if cell.get("t") == "s" and value is not None:
                text = shared[int(value.text)] if int(value.text) < len(shared) else ""
            elif inline is not None:
                text = "".join(t.text or "" for t in inline.iter(f"{{{NS['m']}}}t"))
            else:
                text = value.text if value is not None else ""
            cells[_col_index(cell.get("r"))] = text
        if cells:
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
        if len(rows) > MAX_ROWS:
            break
    return rows


def number(value):
    """«1 234,5» / «12%» / «3.5» → float yoki None."""
    text = str(value or "").strip().replace(" ", "").replace(" ", "").rstrip("%")
    if not text or not re.fullmatch(r"[-+]?\d+([.,]\d+)?", text):
        return None
    return float(text.replace(",", "."))


def load(data, kind):
    """(sarlavhalar, qatorlar). Birinchi to'ldirilgan qator — sarlavha."""
    rows = _csv_rows(data) if kind == "csv" else _xlsx_rows(data)
    rows = [[c.strip() for c in r] for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise DataError("Jadvalda kamida sarlavha va bitta qator bo'lsin.")
    width = max(len(r) for r in rows[:50])
    headers = [(rows[0][i] if i < len(rows[0]) and rows[0][i] else f"Ustun {i + 1}") for i in range(width)]
    body = [r + [""] * (width - len(r)) for r in rows[1:]]
    return headers, body


def summarize(headers, rows):
    """Har bir ustun: raqamli bo'lsa — soni, min, max, o'rtacha, yig'indi; matnli bo'lsa — eng ko'p uchragan qiymatlar."""
    columns = []
    for i, name in enumerate(headers):
        values = [r[i] for r in rows if r[i]]
        numbers = [n for n in (number(v) for v in values) if n is not None]
        if values and len(numbers) >= 0.8 * len(values):
            columns.append({"name": name, "numeric": True, "count": len(numbers),
                            "min": min(numbers), "max": max(numbers), "mean": round(statistics.fmean(numbers), 3),
                            "sum": round(sum(numbers), 3)})
        else:
            top = Counter(values).most_common(8)
            columns.append({"name": name, "numeric": False, "count": len(values), "unique": len(set(values)),
                            "top": [[v, c] for v, c in top]})
    return {"rows": len(rows), "columns": columns}


def series(headers, rows, label, value=None, limit=12):
    """Grafik uchun (yorliqlar, qiymatlar). value bo'lmasa — label ustunidagi har bir javob soni (so'rovnoma).
    value bo'lsa — label bo'yicha yig'indi (bir xil yorliqlar qo'shiladi). Yorliqlar ko'p bo'lsa — eng kattalari."""
    if label not in headers or (value is not None and value not in headers):
        raise DataError("Ustun topilmadi.")
    li = headers.index(label)
    if value is None:
        pairs = Counter(r[li] for r in rows if r[li]).most_common(limit)
        return [p[0] for p in pairs], [float(p[1]) for p in pairs]
    vi = headers.index(value)
    totals = {}
    for r in rows:
        n = number(r[vi])
        if r[li] and n is not None:
            totals[r[li]] = totals.get(r[li], 0.0) + n
    if not totals:
        raise DataError("Tanlangan ustunda raqamli ma'lumot yo'q.")
    items = list(totals.items())
    if len(items) > limit:  # tartib (masalan yillar) saqlanadi, faqat ko'p bo'lsa eng kattalari olinadi
        keep = {k for k, _ in sorted(items, key=lambda x: -x[1])[:limit]}
        items = [i for i in items if i[0] in keep]
    return [k for k, _ in items], [v for _, v in items]


def describe(name, summary):
    """AI uchun qisqa tavsif (raqamlar Python hisoblagan)."""
    lines = [f"Dataset «{name}»: {summary['rows']} rows."]
    for c in summary["columns"]:
        if c["numeric"]:
            lines.append(f"- {c['name']} (numeric): count {c['count']}, min {c['min']}, max {c['max']}, "
                         f"mean {c['mean']}, sum {c['sum']}")
        else:
            top = ", ".join(f"{v} ({n})" for v, n in c["top"][:6])
            lines.append(f"- {c['name']} (text, {c['unique']} distinct): {top}")
    return "\n".join(lines)
