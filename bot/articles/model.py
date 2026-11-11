"""Maqola: turlari, hajmlari, tarjimalari va tarkib modeli.

Tarkib — bloklar ro'yxati (web muharrir, DOCX va PDF bir xil modeldan ishlaydi):
  {"t": "h", "level": 1-3, "align": ..., "runs": [...]}         — sarlavha
  {"t": "p", "align": ..., "runs": [...]}                        — xatboshi
  {"t": "ul" | "ol", "items": [[runs], ...]}                     — ro'yxat
  {"t": "table", "head": bool, "rows": [[[runs], ...], ...]}      — jadval (katakda runs)
  {"t": "img", "src": nom, "width": 30-100, "align": ..., "caption": str}
run — matn bo'lagi: {"text", "b", "i", "u", "color": "#rrggbb", "size": pt, "link": "https://..."}.
Server (routes/articles.js) saqlashda xuddi shu qoidalar bilan tekshiradi; normalize() bot tomonidagi himoya."""
import re

TYPES = ("general", "scientific", "analytical", "journalistic", "review")
LANGS = ("uz", "ru", "en")
SIZES = {"short": (500, 700), "medium": (1000, 1500), "long": (2000, 3000)}
STYLES = ("auto", "academic", "simple")
ALIGNS = ("left", "center", "right", "justify")
TOPIC_MIN, TOPIC_MAX = 3, 200
NOTES_MAX, PURPOSE_MAX = 600, 200

LIMITS = {"blocks": 400, "runs": 200, "text": 8000, "items": 60, "rows": 40, "cols": 8, "caption": 300,
          "title": 300}
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
LINK = re.compile(r"^(https?://|mailto:)[^\s<>\"']{1,500}$")
SAFE_NAME = re.compile(r"^[\w.-]{1,80}$")

# Turlarning nomi va tavsifi (bot va hujjat nomlari uchun; web ilova o'z lug'atidan oladi)
TYPE_NAMES = {
    "uz": {"general": "Oddiy maqola", "scientific": "Ilmiy maqola", "analytical": "Tahliliy maqola",
           "journalistic": "Publitsistik maqola", "review": "Sharh maqolasi"},
    "ru": {"general": "Обычная статья", "scientific": "Научная статья", "analytical": "Аналитическая статья",
           "journalistic": "Публицистическая статья", "review": "Обзорная статья"},
    "en": {"general": "General Article", "scientific": "Scientific Article", "analytical": "Analytical Article",
           "journalistic": "Journalistic Article", "review": "Review Article"},
}
TYPE_ICONS = {"general": "📝", "scientific": "🔬", "analytical": "📊", "journalistic": "📰", "review": "📚"}

# Hujjat ichidagi doimiy yozuvlar (AI emas, kod qo'yadi — til aralashmasin)
LABELS = {
    "uz": {"abstract": "Annotatsiya", "keywords": "Kalit so'zlar", "references": "Foydalanilgan adabiyotlar",
           "figure": "{n}-rasm.", "table": "{n}-jadval.", "photo": "Illyustrativ foto", "author": "Muallif",
           "page": "{n}"},
    "ru": {"abstract": "Аннотация", "keywords": "Ключевые слова", "references": "Список литературы",
           "figure": "Рис. {n}.", "table": "Таблица {n}.", "photo": "Иллюстративное фото", "author": "Автор",
           "page": "{n}"},
    "en": {"abstract": "Abstract", "keywords": "Keywords", "references": "References",
           "figure": "Figure {n}.", "table": "Table {n}.", "photo": "Illustrative photo", "author": "Author",
           "page": "{n}"},
}


def target_words(size, words=None):
    """Tanlangan hajmdan maqsad so'zlar soni (oraliqning o'rtasi) yoki foydalanuvchi kiritgani."""
    if size in SIZES:
        low, high = SIZES[size]
        return (low + high) // 2
    return int(words)


def plain(runs):
    return "".join(run.get("text", "") for run in runs or [])


REFERENCE_TITLES = {labels["references"] for labels in LABELS.values()}


def word_count(blocks):
    """Maqola matnining hajmi: sarlavhalar, xatboshilar va ro'yxatlar. Jadvallar va adabiyotlar ro'yxati
    hisobga olinmaydi (hajm — muallif matni)."""
    total, previous = 0, None
    for block in blocks:
        if block["t"] in ("h", "p"):
            total += len(plain(block["runs"]).split())
        elif block["t"] in ("ul", "ol"):
            is_references = previous and previous["t"] == "h" and plain(previous["runs"]) in REFERENCE_TITLES
            if not is_references:
                total += sum(len(plain(item).split()) for item in block["items"])
        previous = block
    return total


# ===== Tekshirish (bot tomonidagi himoya: buzuq yoki begona ma'lumot fayl yasashni buzmasin) =====
def _runs(raw):
    out = []
    for run in (raw if isinstance(raw, list) else [])[:LIMITS["runs"]]:
        if not isinstance(run, dict):
            continue
        text = str(run.get("text") or "")[:LIMITS["text"]]
        if not text:
            continue
        clean = {"text": text}
        for key in ("b", "i", "u"):
            if run.get(key):
                clean[key] = 1
        if isinstance(run.get("color"), str) and COLOR.match(run["color"]):
            clean["color"] = run["color"].lower()
        size = run.get("size")
        if isinstance(size, (int, float)) and 8 <= size <= 40:
            clean["size"] = int(size)
        if isinstance(run.get("link"), str) and LINK.match(run["link"]):
            clean["link"] = run["link"]
        out.append(clean)
    return out


def _align(value, default="left"):
    return value if value in ALIGNS else default


def normalize(blocks):
    out = []
    for block in (blocks if isinstance(blocks, list) else [])[:LIMITS["blocks"]]:
        if not isinstance(block, dict):
            continue
        kind = block.get("t")
        if kind == "h":
            runs = _runs(block.get("runs"))
            if runs:
                level = block.get("level") if block.get("level") in (1, 2, 3) else 2
                out.append({"t": "h", "level": level, "align": _align(block.get("align")), "runs": runs})
        elif kind == "p":
            runs = _runs(block.get("runs"))
            if runs:
                out.append({"t": "p", "align": _align(block.get("align"), "justify"), "runs": runs})
        elif kind in ("ul", "ol"):
            items = [r for r in (_runs(i) for i in (block.get("items") or [])[:LIMITS["items"]]) if r]
            if items:
                out.append({"t": kind, "items": items})
        elif kind == "table":
            rows = []
            for row in (block.get("rows") or [])[:LIMITS["rows"]]:
                if isinstance(row, list) and row:
                    rows.append([_runs(cell) for cell in row[:LIMITS["cols"]]])
            if rows:
                width = max(len(r) for r in rows)
                rows = [r + [[] for _ in range(width - len(r))] for r in rows]
                out.append({"t": "table", "head": bool(block.get("head")), "rows": rows})
        elif kind == "img":
            src = block.get("src")
            if isinstance(src, str) and SAFE_NAME.match(src):
                width = block.get("width")
                out.append({
                    "t": "img", "src": src,
                    "width": int(width) if isinstance(width, (int, float)) and 25 <= width <= 100 else 80,
                    "align": block.get("align") if block.get("align") in ("left", "center", "right") else "center",
                    "caption": str(block.get("caption") or "")[:LIMITS["caption"]],
                })
    return out
