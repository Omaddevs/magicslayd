"""Diplom ishi amallari — bot chati (handlers/diploma.py) va web ilova navbati (handlers/web.py → run_job) uchun umumiy.

Qism kalitlari: «intro», «chapter:0», «chapter:1», ..., «conclusion».
To'lov: reja tasdiqlanganda BIR MARTA (narx = betlar × DIPLOM_PAGE_PRICE). Avval bazada «to'landi» belgisi atomar
qo'yiladi (diplomas.paid = 0 bo'lsagina) — ikki marta bosilsa ham pul ikki marta yechilmaydi.
Har bir diplom uchun bir vaqtda bitta AI amali bajariladi (qulf). AI natijasi faqat o'z qismiga yoziladi."""
import asyncio
import logging
from datetime import date

from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from admins import has_perm
from config import DIPLOM_AI_OPS_DAILY, DIPLOM_PAGE_PRICE, DIPLOM_PLANS_DAILY, WEBAPP_URL, money
from converter import PDF_AVAILABLE, ConvertError, to_pdf
from database import add_document, change_balance, get_balance
from diploma import ai, storage
from diploma.designs import DOC_DESIGNS, get_design
from diploma.docx_builder import build_docx
from diploma.extract import ExtractError, extract
from diploma.figures import make_figures
from diploma.sources import find_sources
from presentation.ai import GenerationError

_locks = {}


class DiplomaError(Exception):
    """Foydalanuvchiga ko'rsatsa bo'ladigan xato. need — to'lov uchun yetmayotgan summa (bo'lsa)."""

    def __init__(self, message, need=0):
        super().__init__(message)
        self.need = need


def lock(diploma_id):
    return _locks.setdefault(diploma_id, asyncio.Lock())


def busy(diploma_id):
    return lock(diploma_id).locked()


def price_for(user_id, pages):
    return 0 if has_perm(user_id, "free") else int(pages) * DIPLOM_PAGE_PRICE


def get(diploma_id, user_id):
    loaded = storage.load(diploma_id, user_id)
    if not loaded:
        raise DiplomaError("Diplom ishi topilmadi.")
    return loaded


# ===== Qismlar =====
def parts(project):
    return ["intro"] + [f"chapter:{i}" for i in range(len(project["chapters"]))] + ["conclusion"]


def part_of(project, key):
    if key == "intro":
        return project["intro"]
    if key == "conclusion":
        return project["conclusion"]
    if key.startswith("chapter:") and key[8:].isdecimal() and int(key[8:]) < len(project["chapters"]):
        return project["chapters"][int(key[8:])]
    raise DiplomaError("Bunday qism yo'q.")


ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII")


def part_name(project, key):
    if key == "intro":
        return "Kirish"
    if key == "conclusion":
        return "Xulosa"
    i = int(key[8:])
    return f"{ROMAN[i] if i < len(ROMAN) else i + 1} bob: {project['chapters'][i]['title']}"


def current_part(project):
    """Birinchi tasdiqlanmagan qism (yozish tartibida) yoki None — hammasi tasdiqlangan."""
    return next((key for key in parts(project) if part_of(project, key).get("status") != "approved"), None)


def has_text(project, key):
    part = part_of(project, key)
    if key == "intro":
        return bool(part["items"])
    if key == "conclusion":
        return bool(part["paragraphs"])
    return any(s["paragraphs"] for s in part["sections"])


def word_count(project):
    texts = [p for item in project["intro"]["items"] for p in item["paragraphs"]]
    for chapter in project["chapters"]:
        texts += [p for s in chapter["sections"] for p in s["paragraphs"]] + list(chapter.get("summary") or [])
    texts += project["conclusion"]["paragraphs"]
    return sum(len(t.split()) for t in texts)


def count_op(diploma_id, kind="ops"):
    """Kunlik bepul amallar: «plans» — to'lovgacha reja tuzish, «ops» — qayta yozish va tahrirlash."""
    limit = DIPLOM_PLANS_DAILY if kind == "plans" else DIPLOM_AI_OPS_DAILY

    def change(project):
        ops = project["ops"]
        if ops.get("date") != date.today().isoformat():
            ops.update(date=date.today().isoformat(), count=0, plans=0)
        if ops.get(kind, 0) >= limit:
            raise DiplomaError(f"Bugungi bepul AI amallari tugadi ({limit} ta). Ertaga davom ettiring.")
        ops[kind] = ops.get(kind, 0) + 1

    storage.update(diploma_id, change)


def materials_text(diploma_id, project, limit=12000):
    chunks = []
    for item in project.get("materials") or []:
        path = storage.file_path(diploma_id, item.get("file"))
        if not path:
            continue
        try:
            text, _ = extract(path.read_bytes(), item.get("name") or "")
        except ExtractError:
            continue
        chunks.append(f"=== {item.get('name') or item['file']} ===\n{text}")
    return "\n\n".join(chunks)[:limit]


# ===== Ma'lumotlar va fayllar =====
def save_info(diploma_id, values):
    def change(project):
        for key, value in values.items():
            if key in storage.INFO_FIELDS:
                project["info"][key] = value
    storage.update(diploma_id, change)


def save_file(diploma_id, data, name, purpose):
    """Bot chatida yuklangan fayl: purpose «method» (metodik qo'llanma) yoki «material» (amaliy qism uchun).
    Fayl tekshiriladi (o'qiladimi) — keyin saqlanadi."""
    import uuid

    try:
        text, kind = extract(data, name)
    except ExtractError as e:
        raise DiplomaError(str(e)) from e
    if purpose == "method" and kind not in ("pdf", "docx", "txt"):
        raise DiplomaError("Metodik qo'llanma PDF yoki DOCX bo'lsin.")
    folder = storage.folder(diploma_id)
    folder.mkdir(parents=True, exist_ok=True)
    file = f"{purpose}-{uuid.uuid4().hex[:10]}.{kind}"
    (folder / file).write_bytes(data)

    def change(project):
        if purpose == "method":
            project["method"] = {"file": file, "name": name[:120], "status": "uploaded", "rules": {}, "found": [], "notes": ""}
        else:
            project["materials"] = (project.get("materials") or [])[-9:] + [{"file": file, "name": name[:120], "chars": len(text)}]
    storage.update(diploma_id, change)
    return file


# ===== AI amallari =====
async def analyze_method(diploma_id, user_id):
    _, project = get(diploma_id, user_id)
    path = storage.file_path(diploma_id, project["method"].get("file"))
    if not path:
        def sample(p):
            p["method"].update(status="sample", rules={}, found=[])
        storage.update(diploma_id, sample)
        return
    try:
        text, _ = extract(path.read_bytes(), project["method"].get("name") or "")
    except ExtractError as e:
        raise DiplomaError(str(e)) from e
    result = await ai.analyze_method(text)

    def change(p):
        if p["method"].get("file") == project["method"]["file"]:  # bu orada boshqa fayl yuklanmagan bo'lsa
            p["method"].update(status="analyzed" if result["found"] else "sample", rules=result["rules"],
                               found=result["found"],
                               notes="" if result["found"] else "Qo'llanmadan aniq talablar topilmadi — namunaviy talablar ishlatiladi.")
    storage.update(diploma_id, change)


async def make_plan(diploma_id, user_id):
    row, project = get(diploma_id, user_id)
    if not project["info"].get("topic"):
        raise DiplomaError("Avval diplom ishi mavzusini yozing.")
    if project["plan"].get("approved"):
        raise DiplomaError("Reja allaqachon tasdiqlangan.")
    if not row["paid"]:
        count_op(diploma_id, "plans")
    if project["method"]["status"] == "uploaded":
        await analyze_method(diploma_id, user_id)
        _, project = get(diploma_id, user_id)
    plan = await ai.make_plan(project, materials_text(diploma_id, project, 4000))

    def change(p):
        p["plan"] = {"field": plan["field"], "chapters": plan["chapters"], "queries": plan["queries"],
                     "approved": False, "sample": p["method"]["status"] != "analyzed"}
        if p["method"]["status"] == "none":
            p["method"]["status"] = "sample"
        p["stage"] = "plan"
    storage.update(diploma_id, change)


def edit_plan(diploma_id, chapters):
    """Foydalanuvchi o'zgartirgan reja (bot: qayta tuzish; web: to'g'ridan-to'g'ri). Tasdiqlangandan keyin — yo'q."""
    def change(p):
        if p["plan"].get("approved"):
            raise DiplomaError("Reja tasdiqlangan — endi o'zgartirib bo'lmaydi.")
        p["plan"]["chapters"] = chapters
    storage.update(diploma_id, change)


async def approve_plan(diploma_id, user_id):
    """Rejani tasdiqlaydi: pul (bir marta) yechiladi, boblar tuzilmasi yaratiladi, haqiqiy manbalar qidiriladi."""
    row, project = get(diploma_id, user_id)
    if not project["plan"]["chapters"]:
        raise DiplomaError("Avval reja tuzing.")
    price = price_for(user_id, project["info"]["pages"])
    if not row["paid"]:
        if price > get_balance(user_id):
            raise DiplomaError(f"Balans yetarli emas — yana {money(price - get_balance(user_id))} kerak.",
                               need=price - get_balance(user_id))
        if storage.mark_paid(diploma_id, price):  # faqat birinchi chaqiruv pul yechadi
            if price and not change_balance(user_id, -price, "charge", f"Diplom ishi: {project['info']['topic'][:40]}"):
                storage.unmark_paid(diploma_id)
                raise DiplomaError("Balans yetarli emas. Avval hisobni to'ldiring.", need=price)

    def change(p):
        if not p["plan"]["approved"]:
            p["plan"]["approved"] = True
            p["price"] = price
            p["chapters"] = [{"title": c["title"], "sections": [{"title": s["title"], "paragraphs": []} for s in c["sections"]],
                              "summary": [], "figures": [], "status": "empty"} for c in p["plan"]["chapters"]]
            p["intro"] = {"items": [], "status": "empty"}
            p["conclusion"] = {"paragraphs": [], "status": "empty"}
            p["stage"] = "writing"
    storage.update(diploma_id, change)
    await refresh_sources(diploma_id, user_id)


async def refresh_sources(diploma_id, user_id):
    """OpenAlex/Crossref dan haqiqiy manbalar. Qo'lda qo'shilganlari saqlanadi. Tartib raqami (n) o'zgarmaydi."""
    _, project = get(diploma_id, user_id)
    pages = int(project["info"].get("pages") or 60)
    rules = project["method"].get("rules") or {}
    limit = int(max(rules.get("min_sources") or 0, min(45, max(15, pages // 3))))
    queries = project["plan"].get("queries") or [project["info"]["topic"]]
    found = await find_sources(queries, limit)

    def change(p):
        existing = p.get("sources") or []
        keys = {(s.get("doi") or s["title"]).lower() for s in existing}
        n = max((s["n"] for s in existing), default=0)
        for item in found:
            key = (item.get("doi") or item["title"]).lower()
            if key in keys or len(existing) >= limit + 10:
                continue
            n += 1
            keys.add(key)
            existing.append({**item, "n": n})
        p["sources"] = existing
    storage.update(diploma_id, change)


async def generate(diploma_id, user_id, key, count_as_op=None):
    """Qismni (qayta) yozadi. Matni bor qismni qayta yozish — kunlik bepul amallar hisobiga."""
    row, project = get(diploma_id, user_id)
    if not row["paid"] or not project["plan"]["approved"]:
        raise DiplomaError("Avval rejani tasdiqlang.")
    if key.startswith("chapter:") and int(key[8:]) > 0:
        previous = project["chapters"][int(key[8:]) - 1]
        if not previous.get("summary") and previous.get("status") != "approved":
            raise DiplomaError("Avval oldingi bobni yozing — boblar bir-biriga bog'liq.")
    if key == "conclusion" and any(not c.get("summary") for c in project["chapters"]):
        raise DiplomaError("Avval barcha boblarni yozing.")
    if count_as_op if count_as_op is not None else has_text(project, key):
        count_op(diploma_id)

    if key == "intro":
        items = await ai.write_intro(project)

        def change(p):
            p["intro"] = {"items": items, "status": "draft"}
    elif key == "conclusion":
        paragraphs = await ai.write_conclusion(project)

        def change(p):
            p["conclusion"] = {"paragraphs": paragraphs, "status": "draft"}
    else:
        ci = int(key[8:])
        sections, summary, visuals = await ai.write_chapter(project, ci, materials_text(diploma_id, project))
        figures = await make_figures(storage.folder(diploma_id), visuals, project["info"]["topic"], ai.lang_of(project))

        def change(p):
            chapter = p["chapters"][ci]
            for section, paragraphs in zip(chapter["sections"], sections):
                section["paragraphs"] = paragraphs
            chapter.update(summary=summary, figures=figures, status="draft")
    storage.update(diploma_id, change)


def set_progress(diploma_id, value):
    """Hammasini yozish jarayoni: {"part", "name", "done", "total"} yoki None — ilova va bot shuni ko'rsatadi."""
    def change(p):
        p["progress"] = value
    storage.update(diploma_id, change)


async def generate_all(diploma_id, user_id, on_part=None):
    """Bir bosishda butun ish: yozilmagan qismlar (kirish → boblar → xulosa) ketma-ket yoziladi, keyin hammasi
    tasdiqlanadi. Yozilganlari qayta yozilmaydi — xato bo'lsa, qayta bosilganda qolgan joyidan davom etadi.
    Keyin ham istalgan qismni tahrirlash yoki qayta yozdirish mumkin. on_part(nomi, n, jami) — bot progressi uchun."""
    row, project = get(diploma_id, user_id)
    if not row["paid"] or not project["plan"]["approved"]:
        raise DiplomaError("Avval rejani tasdiqlang.")
    keys = parts(project)
    try:
        for n, key in enumerate(keys, 1):
            _, project = get(diploma_id, user_id)
            if has_text(project, key):
                continue
            name = part_name(project, key)
            set_progress(diploma_id, {"part": key, "name": name, "done": n - 1, "total": len(keys)})
            if on_part:
                await on_part(name, n, len(keys))
            await generate(diploma_id, user_id, key, count_as_op=False)
    finally:
        set_progress(diploma_id, None)

    def change(p):
        for key in parts(p):
            if has_text(p, key):
                part_of(p, key)["status"] = "approved"
        if current_part(p) is None:
            p["stage"] = "done"
    storage.update(diploma_id, change)


def locate(part, address):
    """address: {"item": i, "paragraph": k} (kirish) | {"section": s, "paragraph": k} (bob) |
    {"summary": True, "paragraph": k} | {"paragraph": k} (xulosa) → (ro'yxat, indeks)."""
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
        raise DiplomaError("Xatboshi topilmadi.")
    return paragraphs, k


async def rewrite(diploma_id, user_id, key, address, op):
    if op not in ai.OPS:
        raise DiplomaError("Noma'lum amal.")
    row, project = get(diploma_id, user_id)
    if not row["paid"]:
        raise DiplomaError("Avval rejani tasdiqlang.")
    paragraphs, k = locate(part_of(project, key), address)
    original = paragraphs[k]
    count_op(diploma_id)
    result = await ai.rewrite(project, original, op, part_name(project, key))

    def change(p):
        target, index = locate(part_of(p, key), address)
        if target[index] != original:
            raise DiplomaError("Bu xatboshi shu orada o'zgartirilgan — AI natijasi saqlanmadi. Qayta urinib ko'ring.")
        target[index] = result
        part = part_of(p, key)
        if part.get("status") == "approved":  # foydalanuvchi o'zi so'radi — qism qayta ko'rib chiqiladi
            part["status"] = "draft"
    storage.update(diploma_id, change)
    return result


def approve_part(diploma_id, key):
    def change(p):
        part = part_of(p, key)
        if not has_text(p, key):
            raise DiplomaError("Bu qism hali yozilmagan.")
        part["status"] = "approved"
        if current_part(p) is None:
            p["stage"] = "done"
    storage.update(diploma_id, change)


# ===== Eksport =====
def edit_markup(diploma_id):
    """Tayyor fayl ostidagi tugmalar — taqdimotdagidek: tahrirlash (ilovada), boshqa dizayn, yangi ish."""
    rows = []
    if WEBAPP_URL:
        url = f"{WEBAPP_URL}{'&' if '?' in WEBAPP_URL else '?'}diplom={diploma_id}"
        rows.append([InlineKeyboardButton(text="✏️ Tahrirlash", web_app=WebAppInfo(url=url))])
    rows.append([InlineKeyboardButton(text="🎨 Boshqa dizaynda olish", callback_data=f"dip:design:{diploma_id}")])
    rows.append([InlineKeyboardButton(text="🎓 Yangi diplom ishi", callback_data="dip:new:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def set_design(diploma_id, key):
    if key not in DOC_DESIGNS:
        raise DiplomaError("Bunday dizayn yo'q.")

    def change(p):
        p["design"] = key
    storage.update(diploma_id, change)


async def export(bot: Bot, diploma_id, user_id, fmt="docx"):
    """DOCX (yoki PDF) ni yasab, foydalanuvchining Telegram chatiga yuboradi. «Hujjatlarim» dagi yozuv ID'si qaytadi."""
    from handlers.presentation import file_name

    row, project = get(diploma_id, user_id)
    if not row["paid"] or not has_text(project, "intro"):
        raise DiplomaError("Hali yuklab olinadigan matn yo'q.")
    data = await asyncio.to_thread(build_docx, project, storage.folder(diploma_id))
    if fmt == "pdf":
        if not PDF_AVAILABLE:
            raise DiplomaError("PDF yaratish hozircha mavjud emas — DOCX yuklab oling.")
        try:
            data = await to_pdf(data, "docx")
        except ConvertError as e:
            raise DiplomaError(str(e)) from e
    done = current_part(project) is None
    title = project["info"]["topic"]
    caption = (
        f"🎓 <b>Diplom ishi{'' if done else ' (qoralama)'}</b>\n\n📝 {title[:200]}\n"
        f"📄 ~{max(1, round(word_count(project) / ai.WORDS_PER_PAGE)) + ai.SERVICE_PAGES} bet  ·  "
        f"📚 Manbalar: {len(project['sources'])} ta\n🎨 Dizayn: {get_design(project)['name']}\n\n"
        "💡 Word'da ochganda «Maydonlarni yangilash» so'ralsa — «Ha» ni bosing: mundarija sahifa raqamlari bilan yangilanadi."
        + ("" if done else "\n⏳ Ba'zi qismlar hali tasdiqlanmagan.")
    )
    sent = await bot.send_document(user_id, BufferedInputFile(data, filename=file_name(title, fmt)), caption=caption,
                                   reply_markup=edit_markup(diploma_id))
    if row["document_id"]:
        storage.replace_document_file(row["document_id"], sent.document.file_id, title)
        document_id = row["document_id"]
    else:
        document_id = add_document(user_id, "diplom", title, sent.document.file_id)
        storage.set_document(diploma_id, document_id)
    return document_id


# ===== Web ilova navbati (handlers/web.py) =====
ACTIONS = ("analyze", "plan", "approve_plan", "generate", "write_all", "rewrite", "sources", "export", "design")


async def run_job(bot: Bot, user_id, params):
    """web_orders (kind = 'diplom') vazifasi. Qaytaradi: hujjat ID'si (eksportda) yoki None. Xato — DiplomaError."""
    diploma_id, action = int(params.get("diploma_id") or 0), params.get("action")
    if action not in ACTIONS:
        raise DiplomaError("Noma'lum amal.")
    async with lock(diploma_id):
        try:
            if action == "analyze":
                await analyze_method(diploma_id, user_id)
            elif action == "plan":
                await make_plan(diploma_id, user_id)
            elif action == "approve_plan":
                await approve_plan(diploma_id, user_id)
            elif action == "generate":
                await generate(diploma_id, user_id, str(params.get("part")))
            elif action == "write_all":
                await generate_all(diploma_id, user_id)
                return await export(bot, diploma_id, user_id)
            elif action == "rewrite":
                await rewrite(diploma_id, user_id, str(params.get("part")), params.get("address") or {}, params.get("op"))
            elif action == "sources":
                await refresh_sources(diploma_id, user_id)
            elif action == "export":
                return await export(bot, diploma_id, user_id, "pdf" if params.get("fmt") == "pdf" else "docx")
            elif action == "design":  # ilovadan: dizaynni almashtirib, yangi faylni chatga yuborish
                get(diploma_id, user_id)
                set_design(diploma_id, str(params.get("design")))
                return await export(bot, diploma_id, user_id, "pdf" if params.get("fmt") == "pdf" else "docx")
        except GenerationError as e:
            raise DiplomaError(str(e)) from e
        except KeyError as e:
            logging.warning("Diplom vazifasida ma'lumot topilmadi: %s", e)
            raise DiplomaError("Diplom ishi ma'lumoti topilmadi yoki o'zgartirilgan.") from e
    return None
