"""Dissertatsiya amallari — bot chati (handlers/dissertation.py) va web navbati (handlers/web.py → run_job) uchun umumiy.

Qism kalitlari: «intro», «chapter:0», ..., «conclusion», «annotation».
To'lov: reja tasdiqlanganda BIR MARTA (betlar × DISS_PAGE_PRICE). Avval bazada «to'landi» belgisi atomar qo'yiladi
(paid = 0 bo'lsagina) — ikki marta bosilsa ham pul ikki marta yechilmaydi. Xato bo'lsa — belgi qaytariladi.
Har bir ish uchun bir vaqtda bitta AI amali (qulf). AI qismni o'zgartirishidan oldin eski versiya tarixga yoziladi."""
import asyncio
import io
import logging
import uuid
from datetime import date, datetime

from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from admins import has_perm
from config import DISS_AI_OPS_DAILY, DISS_PAGE_PRICE, DISS_PLANS_DAILY, DISS_TYPES, WEBAPP_URL, money
from converter import PDF_AVAILABLE, ConvertError, to_pdf
from database import add_document, change_balance, get_balance
from diploma.designs import DOC_DESIGNS, get_design
from diploma.extract import ExtractError, extract
from diploma.sources import find_sources
from dissertation import ai, datasets, quality, storage
from dissertation.docx_builder import build_docx
from dissertation.figures import make_figures
from presentation.ai import GenerationError

ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII")
_locks = {}


class DissError(Exception):
    """Foydalanuvchiga ko'rsatsa bo'ladigan xato. need — to'lov uchun yetmayotgan summa."""

    def __init__(self, message, need=0):
        super().__init__(message)
        self.need = need


def lock(item_id):
    return _locks.setdefault(item_id, asyncio.Lock())


def busy(item_id):
    return lock(item_id).locked()


def price_for(user_id, pages):
    return 0 if has_perm(user_id, "free") else int(pages) * DISS_PAGE_PRICE


def get(item_id, user_id):
    loaded = storage.load(item_id, user_id)
    if not loaded:
        raise DissError("Dissertatsiya topilmadi.")
    return loaded


# ===== Qismlar =====
def parts(project):
    return ["intro"] + [f"chapter:{i}" for i in range(len(project["chapters"]))] + ["conclusion", "annotation"]


def part_of(project, key):
    if key in ("intro", "conclusion", "annotation"):
        return project[key]
    if key.startswith("chapter:") and key[8:].isdecimal() and int(key[8:]) < len(project["chapters"]):
        return project["chapters"][int(key[8:])]
    raise DissError("Bunday qism yo'q.")


def part_name(project, key):
    names = {"intro": "Kirish", "conclusion": "Umumiy xulosa", "annotation": "Annotatsiya"}
    if key in names:
        return names[key]
    i = int(key[8:])
    return f"{ROMAN[i] if i < len(ROMAN) else i + 1} bob: {project['chapters'][i]['title']}"


def has_text(project, key):
    part = part_of(project, key)
    if key == "intro":
        return bool(part["items"])
    if key in ("conclusion", "annotation"):
        return bool(part["paragraphs"])
    return any(s["paragraphs"] for s in part["sections"])


def current_part(project):
    return next((key for key in parts(project) if part_of(project, key).get("status") != "approved"), None)


def word_count(project):
    from dissertation.docx_builder import all_texts
    return sum(len(t.split()) for t in all_texts(project))


def count_op(item_id, kind="count"):
    limit = DISS_PLANS_DAILY if kind == "plans" else DISS_AI_OPS_DAILY

    def change(project):
        ops = project["ops"]
        if ops.get("date") != date.today().isoformat():
            ops.update(date=date.today().isoformat(), count=0, plans=0)
        if ops.get(kind, 0) >= limit:
            raise DissError(f"Bugungi bepul AI amallari tugadi ({limit} ta). Ertaga davom ettiring.")
        ops[kind] = ops.get(kind, 0) + 1
    storage.update(item_id, change)


# ===== Ma'lumotlar va fayllar =====
def create(user_id, kind):
    if kind not in DISS_TYPES:
        raise DissError("Dissertatsiya turini tanlang.")
    return storage.create(user_id, kind, {"pages": DISS_TYPES[kind]["pages"]})


def save_info(item_id, values):
    def change(project):
        for key, value in values.items():
            if key in storage.INFO_FIELDS:
                project["info"][key] = value
    storage.update(item_id, change)


def set_kind(item_id, kind):
    if kind not in DISS_TYPES:
        raise DissError("Dissertatsiya turini tanlang.")

    def change(project):
        if project["plan"]["approved"]:
            raise DissError("Reja tasdiqlangan — turini endi o'zgartirib bo'lmaydi.")
        if project.get("kind") != kind:
            project["info"]["pages"] = DISS_TYPES[kind]["pages"]
        project["kind"] = kind
    storage.update(item_id, change)


def save_file(item_id, data, name, purpose):
    """Bot chatida yuklangan fayl: purpose «method» (qo'llanma) yoki «material» (ma'lumotlar, hujjatlar)."""
    try:
        text, kind = extract(data, name)
    except ExtractError as e:
        raise DissError(str(e)) from e
    if purpose == "method" and kind not in ("pdf", "docx", "txt"):
        raise DissError("Metodik qo'llanma PDF yoki DOCX bo'lsin.")
    if kind in ("csv", "xlsx"):
        try:
            datasets.load(data, kind)
        except datasets.DataError as e:
            raise DissError(str(e)) from e
    folder = storage.folder(item_id)
    folder.mkdir(parents=True, exist_ok=True)
    file = f"{purpose}-{uuid.uuid4().hex[:10]}.{kind}"
    (folder / file).write_bytes(data)

    def change(project):
        if purpose == "method":
            if project["plan"]["approved"]:
                raise DissError("Reja tasdiqlangan — qo'llanmani endi almashtirib bo'lmaydi.")
            project["method"] = {"file": file, "name": name[:120], "status": "uploaded", "rules": {}, "found": [], "notes": ""}
        else:
            project["materials"] = project["materials"][-14:] + [{"file": file, "name": name[:120], "kind": kind}]
    storage.update(item_id, change)
    return file


def tables(item_id, project):
    """Yuklangan jadvallar (CSV/XLSX): [(nomi, sarlavhalar, qatorlar)] — buzuqlari tashlanadi."""
    result = []
    for item in project["materials"]:
        path = storage.file_path(item_id, item["file"])
        if path and item.get("kind") in ("csv", "xlsx"):
            try:
                result.append((item["name"], *datasets.load(path.read_bytes(), item["kind"])))
            except datasets.DataError:
                continue
    return result


def materials_text(item_id, project, limit=14000):
    """AI uchun: hujjatlar matni + jadvallarning Python hisoblagan ko'rsatkichlari."""
    chunks = []
    for item in project["materials"]:
        path = storage.file_path(item_id, item["file"])
        if not path or item.get("kind") in ("csv", "xlsx", "png", "jpg"):
            continue
        try:
            text, _ = extract(path.read_bytes(), item["name"])
            chunks.append(f"=== {item['name']} ===\n{text}")
        except ExtractError:
            continue
    for name, headers, rows in tables(item_id, project):
        chunks.append(datasets.describe(name, datasets.summarize(headers, rows)))
    return "\n\n".join(chunks)[:limit]


def datasets_text(item_id, project):
    return "\n".join(f"{i}: {datasets.describe(name, datasets.summarize(h, r))}"
                     for i, (name, h, r) in enumerate(tables(item_id, project)))


# ===== AI amallari =====
async def suggest_topics(item_id, user_id):
    row, project = get(item_id, user_id)
    if not project["info"].get("direction"):
        raise DissError("Avval tadqiqot yo'nalishini yozing — mavzular shunga qarab taklif qilinadi.")
    if not row["paid"]:
        count_op(item_id, "plans")
    topics = await ai.suggest_topics(project)
    storage.update(item_id, lambda p: p.update(suggestions=topics))
    return topics


async def analyze_method(item_id, user_id):
    _, project = get(item_id, user_id)
    path = storage.file_path(item_id, project["method"].get("file"))
    if not path:
        storage.update(item_id, lambda p: p["method"].update(status="sample", rules={}, found=[]))
        return
    try:
        text, _ = extract(path.read_bytes(), project["method"].get("name") or "")
    except ExtractError as e:
        raise DissError(str(e)) from e
    result = await ai.analyze_method(text)

    def change(p):
        if p["method"].get("file") == project["method"]["file"]:
            p["method"].update(status="analyzed" if result["found"] else "sample", rules=result["rules"],
                               found=result["found"],
                               notes="" if result["found"] else "Qo'llanmadan aniq talablar topilmadi — namunaviy talablar ishlatiladi.")
    storage.update(item_id, change)


async def make_plan(item_id, user_id):
    row, project = get(item_id, user_id)
    if len(project["info"].get("topic") or "") < 5:
        raise DissError("Avval dissertatsiya mavzusini yozing.")
    if project["plan"]["approved"]:
        raise DissError("Reja allaqachon tasdiqlangan.")
    if not row["paid"]:
        count_op(item_id, "plans")
    if project["method"]["status"] == "uploaded":
        await analyze_method(item_id, user_id)
        _, project = get(item_id, user_id)
    plan = await ai.make_plan(project, materials_text(item_id, project, 5000))

    def change(p):
        p["plan"] = {"field": plan["field"], "chapters": plan["chapters"], "queries": plan["queries"],
                     "approved": False, "sample": p["method"]["status"] != "analyzed"}
        if p["method"]["status"] == "none":
            p["method"]["status"] = "sample"
        p["stage"] = "plan"
    storage.update(item_id, change)


async def approve_plan(item_id, user_id):
    row, project = get(item_id, user_id)
    if not project["plan"]["chapters"]:
        raise DissError("Avval reja tuzing.")
    price = price_for(user_id, project["info"]["pages"])
    if not row["paid"]:
        balance = get_balance(user_id)
        if price > balance:
            raise DissError(f"Balans yetarli emas — yana {money(price - balance)} kerak.", need=price - balance)
        if storage.mark_paid(item_id, price):
            if price and not change_balance(user_id, -price, "charge", f"Dissertatsiya: {project['info']['topic'][:40]}"):
                storage.unmark_paid(item_id)
                raise DissError("Balans yetarli emas. Avval hisobni to'ldiring.", need=price)

    def change(p):
        if not p["plan"]["approved"]:
            p["plan"]["approved"], p["price"], p["stage"] = True, price, "writing"
            p["chapters"] = [{"title": c["title"], "sections": [{"title": s["title"], "paragraphs": []} for s in c["sections"]],
                              "summary": [], "figures": [], "status": "empty"} for c in p["plan"]["chapters"]]
            p["intro"] = {"items": [], "status": "empty"}
            p["conclusion"] = {"paragraphs": [], "status": "empty"}
            p["annotation"] = {"paragraphs": [], "keywords": [], "status": "empty"}
    storage.update(item_id, change)
    await refresh_sources(item_id, user_id)


async def refresh_sources(item_id, user_id):
    _, project = get(item_id, user_id)
    pages = int(project["info"].get("pages") or 80)
    minimum = int((project["method"].get("rules") or {}).get("min_sources") or 0)
    limit = max(minimum, min(80, max(30, pages // 3)))
    found = await find_sources(project["plan"].get("queries") or [project["info"]["topic"]], limit)

    def change(p):
        existing = p["sources"]
        keys = {(s.get("doi") or s["title"]).lower() for s in existing}
        n = max((s["n"] for s in existing), default=0)
        for item in found:
            key = (item.get("doi") or item["title"]).lower()
            if key not in keys and len(existing) < limit + 15:
                n += 1
                keys.add(key)
                existing.append({**item, "n": n})
    storage.update(item_id, change)


async def generate(item_id, user_id, key, count_as_op=None):
    row, project = get(item_id, user_id)
    if not row["paid"] or not project["plan"]["approved"]:
        raise DissError("Avval rejani tasdiqlang.")
    if key.startswith("chapter:") and int(key[8:]) > 0 and not project["chapters"][int(key[8:]) - 1].get("summary"):
        raise DissError("Avval oldingi bobni yozing — boblar bir-biriga bog'liq.")
    if key == "conclusion" and any(not c.get("summary") for c in project["chapters"]):
        raise DissError("Avval barcha boblarni yozing.")
    if key == "annotation" and not project["conclusion"]["paragraphs"]:
        raise DissError("Annotatsiya umumiy xulosadan keyin yoziladi.")
    if count_as_op if count_as_op is not None else has_text(project, key):
        count_op(item_id)

    if key == "intro":
        new = {"items": await ai.write_intro(project), "status": "draft"}
    elif key == "conclusion":
        new = {"paragraphs": await ai.write_conclusion(project), "status": "draft"}
    elif key == "annotation":
        paragraphs, keywords = await ai.write_annotation(project)
        new = {"paragraphs": paragraphs, "keywords": keywords, "status": "draft"}
    else:
        ci = int(key[8:])
        found_tables = tables(item_id, project)
        # Grafik va statistika — faqat tahliliy boblarda (1-bob nazariy); boshqa bobdagi grafik takrorlanmaydi
        used = {chart_key(f) for i, c in enumerate(project["chapters"]) if i != ci for f in c.get("figures") or []}
        sections, summary, visuals = await ai.write_chapter(project, ci, materials_text(item_id, project),
                                                            datasets_text(item_id, project) if ci > 0 else "")
        kept = []
        for v in visuals:
            if v["kind"] in ("chart", "stats"):
                signature = chart_key(v, found_tables)
                if ci == 0 or signature in used:
                    continue
                used.add(signature)  # bitta bob ichida ham takrorlanmasin
            kept.append(v)
        visuals = kept
        figures = await make_figures(storage.folder(item_id), visuals, project["info"]["topic"], ai.lang_of(project), found_tables)
        new = None

    def change(p):
        storage.remember(p, key, part_of(p, key), "AI qayta yozishidan oldin")
        if new is not None:
            p[key] = new
        else:
            chapter = p["chapters"][ci]
            for section, paragraphs in zip(chapter["sections"], sections):
                section["paragraphs"] = paragraphs
            chapter.update(summary=summary, figures=figures, status="draft")
    storage.update(item_id, change)


def set_progress(item_id, value):
    """Hammasini yozish jarayoni: {"part", "name", "done", "total"} yoki None — ilova va bot shuni ko'rsatadi."""
    def change(p):
        p["progress"] = value
    storage.update(item_id, change)


async def generate_all(item_id, user_id, on_part=None):
    """Bir bosishda butun dissertatsiya: yozilmagan qismlar (kirish → boblar → umumiy xulosa → annotatsiya)
    ketma-ket yoziladi, hammasi tasdiqlanadi va sifat nazorati o'tkaziladi. Yozilganlari qayta yozilmaydi —
    xato bo'lsa, qayta bosilganda qolgan joyidan davom etadi. on_part(nomi, n, jami) — bot progressi uchun."""
    row, project = get(item_id, user_id)
    if not row["paid"] or not project["plan"]["approved"]:
        raise DissError("Avval rejani tasdiqlang.")
    keys = parts(project)
    try:
        for n, key in enumerate(keys, 1):
            _, project = get(item_id, user_id)
            if has_text(project, key):
                continue
            name = part_name(project, key)
            set_progress(item_id, {"part": key, "name": name, "done": n - 1, "total": len(keys)})
            if on_part:
                await on_part(name, n, len(keys))
            await generate(item_id, user_id, key, count_as_op=False)
        set_progress(item_id, {"part": "quality", "name": "Sifat nazorati", "done": len(keys), "total": len(keys)})
        if on_part:
            await on_part("Sifat nazorati", len(keys), len(keys))
        try:
            await check_quality(item_id, user_id)
        except (DissError, GenerationError):
            logging.warning("Dissertatsiya #%s: sifat nazoratini o'tkazib bo'lmadi", item_id)
    finally:
        set_progress(item_id, None)

    def change(p):
        for key in parts(p):
            if has_text(p, key):
                part_of(p, key)["status"] = "approved"
        if current_part(p) is None:
            p["stage"] = "done"
    storage.update(item_id, change)


def chart_key(item, found_tables=None):
    """Grafik / statistik jadvalning «imzosi» (qaysi ma'lumot, qaysi ustunlar) — takrorni aniqlash uchun.
    Tayyor figuradan (dataset — fayl nomi) yoki AI rejasidan (dataset — tartib raqami) olinadi."""
    if item.get("kind") not in ("chart", "stats") and not item.get("dataset"):
        return None
    dataset = item.get("dataset")
    if isinstance(dataset, int) and found_tables is not None:
        dataset = found_tables[dataset][0] if 0 <= dataset < len(found_tables) else None
    columns = tuple(item.get("stat_columns") or (item.get("columns") if item.get("kind") == "stats" else ()) or ())
    return dataset, item.get("label_column") or "", item.get("value_column") or "", columns


def locate(part, address):
    k = int(address.get("paragraph", -1))
    if "item" in address:
        paragraphs = part["items"][int(address["item"])]["paragraphs"]
    elif address.get("summary"):
        paragraphs = part["summary"]
    elif "section" in address:
        paragraphs = part["sections"][int(address["section"])]["paragraphs"]
    else:
        paragraphs = part["paragraphs"]
    if not 0 <= k < len(paragraphs):
        raise DissError("Xatboshi topilmadi.")
    return paragraphs, k


async def rewrite(item_id, user_id, key, address, op):
    if op not in ai.OPS:
        raise DissError("Noma'lum amal.")
    row, project = get(item_id, user_id)
    if not row["paid"]:
        raise DissError("Avval rejani tasdiqlang.")
    paragraphs, k = locate(part_of(project, key), address)
    original = paragraphs[k]
    count_op(item_id)
    result = await ai.rewrite(project, original, op, part_name(project, key))

    def change(p):
        target, index = locate(part_of(p, key), address)
        if target[index] != original:
            raise DissError("Bu xatboshi shu orada o'zgartirilgan — AI natijasi saqlanmadi. Qayta urinib ko'ring.")
        storage.remember(p, key, part_of(p, key), f"«{ai.OPS[op][:30]}…» dan oldin")
        target[index] = result
        if part_of(p, key).get("status") == "approved":
            part_of(p, key)["status"] = "draft"
    storage.update(item_id, change)
    return result


def approve_part(item_id, key):
    def change(p):
        if not has_text(p, key):
            raise DissError("Bu qism hali yozilmagan.")
        part_of(p, key)["status"] = "approved"
        if current_part(p) is None:
            p["stage"] = "done"
    storage.update(item_id, change)


async def check_quality(item_id, user_id):
    """Avtomatik tekshiruvlar + AI mazmuniy muvofiqlik tekshiruvi (xulosa yozilgan bo'lsa)."""
    row, project = get(item_id, user_id)
    if not row["paid"]:
        raise DissError("Avval rejani tasdiqlang.")
    checks = quality.run_checks(project, storage.folder(item_id))
    review = await ai.review(project) if project["conclusion"]["paragraphs"] else []
    storage.update(item_id, lambda p: p.update(quality={"at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                                        "checks": checks, "review": review}))
    return checks, review


# ===== Eksport =====
def edit_markup(item_id):
    """Tayyor fayl ostidagi tugmalar — taqdimotdagidek: tahrirlash (ilovada), boshqa dizayn, yangi ish."""
    rows = []
    if WEBAPP_URL:
        url = f"{WEBAPP_URL}{'&' if '?' in WEBAPP_URL else '?'}diss={item_id}"
        rows.append([InlineKeyboardButton(text="✏️ Tahrirlash", web_app=WebAppInfo(url=url))])
    rows.append([InlineKeyboardButton(text="🎨 Boshqa dizaynda olish", callback_data=f"dis:design:{item_id}")])
    rows.append([InlineKeyboardButton(text="🔬 Yangi dissertatsiya", callback_data="dis:new:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def set_design(item_id, key):
    if key not in DOC_DESIGNS:
        raise DissError("Bunday dizayn yo'q.")

    def change(p):
        p["design"] = key
    storage.update(item_id, change)


def verify_docx(data):
    from docx import Document
    try:
        Document(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        raise DissError("DOCX fayl tekshiruvdan o'tmadi. Qayta urinib ko'ring.") from e


def verify_pdf(data):
    import pymupdf
    try:
        if pymupdf.open(stream=data, filetype="pdf").page_count < 1:
            raise ValueError("bo'sh")
    except Exception as e:  # noqa: BLE001
        raise DissError("PDF fayl tekshiruvdan o'tmadi. DOCX ni yuklab oling.") from e


async def export(bot: Bot, item_id, user_id, fmt="docx"):
    from handlers.presentation import file_name

    row, project = get(item_id, user_id)
    if not row["paid"] or not has_text(project, "intro"):
        raise DissError("Hali yuklab olinadigan matn yo'q.")
    data = await asyncio.to_thread(build_docx, project, storage.folder(item_id), tables(item_id, project))
    await asyncio.to_thread(verify_docx, data)
    if fmt == "pdf":
        if not PDF_AVAILABLE:
            raise DissError("PDF yaratish hozircha mavjud emas — DOCX yuklab oling.")
        try:
            data = await to_pdf(data, "docx")
        except ConvertError as e:
            raise DissError(str(e)) from e
        await asyncio.to_thread(verify_pdf, data)
    done = current_part(project) is None
    title = project["info"]["topic"]
    caption = (
        f"🔬 <b>{DISS_TYPES.get(project['kind'], DISS_TYPES['other'])['name']}{'' if done else ' (qoralama)'}</b>\n\n"
        f"📝 {title[:200]}\n📄 ~{round(word_count(project) / ai.WORDS_PER_PAGE) + 7} bet  ·  "
        f"📚 Manbalar: {len(project['sources'])} ta\n🎨 Dizayn: {get_design(project)['name']}\n\n"
        "💡 Word'da ochganda «Maydonlarni yangilash» so'ralsa — «Ha» ni bosing: mundarija sahifa raqamlari bilan yangilanadi."
        + ("" if done else "\n⏳ Ba'zi qismlar hali tasdiqlanmagan.")
    )
    sent = await bot.send_document(user_id, BufferedInputFile(data, filename=file_name(title, fmt)), caption=caption,
                                   reply_markup=edit_markup(item_id))
    if row["document_id"]:
        storage.replace_document_file(row["document_id"], sent.document.file_id, title)
        return row["document_id"]
    document_id = add_document(user_id, "diss", title, sent.document.file_id)
    storage.set_document(item_id, document_id)
    return document_id


# ===== Web ilova navbati =====
ACTIONS = ("topics", "analyze", "plan", "approve_plan", "generate", "write_all", "rewrite", "sources", "quality", "export",
           "design")


async def run_job(bot: Bot, user_id, params):
    item_id, action = int(params.get("diss_id") or 0), params.get("action")
    if action not in ACTIONS:
        raise DissError("Noma'lum amal.")
    async with lock(item_id):
        try:
            if action == "topics":
                await suggest_topics(item_id, user_id)
            elif action == "analyze":
                await analyze_method(item_id, user_id)
            elif action == "plan":
                await make_plan(item_id, user_id)
            elif action == "approve_plan":
                await approve_plan(item_id, user_id)
            elif action == "generate":
                await generate(item_id, user_id, str(params.get("part")))
            elif action == "write_all":
                await generate_all(item_id, user_id)
                return await export(bot, item_id, user_id)
            elif action == "rewrite":
                await rewrite(item_id, user_id, str(params.get("part")), params.get("address") or {}, params.get("op"))
            elif action == "sources":
                await refresh_sources(item_id, user_id)
            elif action == "quality":
                await check_quality(item_id, user_id)
            elif action == "export":
                return await export(bot, item_id, user_id, "pdf" if params.get("fmt") == "pdf" else "docx")
            elif action == "design":  # ilovadan: dizaynni almashtirib, yangi faylni chatga yuborish
                get(item_id, user_id)
                set_design(item_id, str(params.get("design")))
                return await export(bot, item_id, user_id, "pdf" if params.get("fmt") == "pdf" else "docx")
        except GenerationError as e:
            raise DissError(str(e)) from e
        except KeyError as e:
            logging.warning("Dissertatsiya vazifasida ma'lumot topilmadi: %s", e)
            raise DissError("Dissertatsiya ma'lumoti topilmadi yoki o'zgartirilgan.") from e
    return None
