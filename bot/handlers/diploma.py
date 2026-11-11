"""🎓 Diplom ishi — bot chatidagi bosqichma-bosqich jarayon.

Ma'lumotlar (12 ta savol, har biri darhol saqlanadi) → reja (bepul, tahrirlash va qayta tuzish) → tasdiqlash (to'lov)
→ kirish, boblar, xulosa (har biri alohida ko'rib chiqiladi va tasdiqlanadi) → DOCX / PDF.
Batafsil tahrirlash (xatboshilar, rasmlar, manbalar) — web ilovada: «✏️ Ilovada ochish». Ikkalasi bitta loyihada ishlaydi."""
import asyncio
import html
import logging
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from config import DIPLOM_PAGE_OPTIONS, DIPLOM_PAGE_PRICE, DIPLOM_PAGES_MAX, DIPLOM_PAGES_MIN, WEBAPP_URL, money
from converter import PDF_AVAILABLE
from database import get_balance, save_user
from diploma import service, storage
from diploma.service import DiplomaError
from handlers import doc_design
from handlers.presentation import animate, plain_text
from presentation.ai import LANGUAGES, GenerationError

router = Router()
Button = InlineKeyboardButton


class Diplom(StatesGroup):
    field = State()   # matnli maydon kutilmoqda (dip_field)
    upload = State()  # metodik qo'llanma / material fayli kutilmoqda


# (kalit, sarlavha, misol, majburiy) — tartib shu bo'yicha so'raladi
FIELDS = [
    ("topic", "📝 Diplom ishi mavzusi", "Masalan: Kichik biznesda raqamli marketing strategiyalari", True),
    ("student", "🎓 Talabaning F.I.Sh.", "Masalan: Aliyev Vali Karimovich", False),
    ("university", "🏫 Universitet yoki institut", "Masalan: Toshkent davlat iqtisodiyot universiteti", False),
    ("faculty", "🏛 Fakultet", "Masalan: Marketing fakulteti", False),
    ("direction", "🧭 Ta'lim yo'nalishi", "Masalan: Marketing", False),
    ("specialty", "🔖 Mutaxassislik nomi va kodi", "Masalan: Marketing (60410500)", False),
    ("course_group", "👥 Kursi va guruhi", "Masalan: 4-kurs, MR-21", False),
    ("supervisor", "👨‍🏫 Ilmiy rahbar F.I.Sh.", "Masalan: i.f.n., dots. Karimov A.B.", False),
    ("lang", "🌐 Diplom ishi tili", "", True),
    ("pages", "📄 Ish hajmi (betlar soni)", "", True),
    ("method", "📘 Universitet metodik qo'llanmasi", "", False),
    ("extra", "🗒 Qo'shimcha talablar", "Masalan: amaliy qism «Artel» korxonasi misolida bo'lsin", False),
]
KEYS = [f[0] for f in FIELDS]
LABEL = {f[0]: f[1] for f in FIELDS}
MAX_LEN = {"topic": 300, "extra": 1000}
PROGRESS = ("🧠 Mavzu tahlil qilinmoqda", "📘 Metodik talablar o'rganilmoqda", "📋 Reja tuzilmoqda",
            "🔎 Ilmiy manbalar qidirilmoqda", "✍️ Matn yozilmoqda", "🧩 Boblar bog'lanmoqda",
            "🖼 Sxema va jadvallar tayyorlanmoqda", "🔍 Matn tekshirilmoqda")


def cb(action, diploma_id, arg=""):
    return f"dip:{action}:{diploma_id}" + (f":{arg}" if arg != "" else "")


def inline(*rows):
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows if r])


def app_button(diploma_id, text="✏️ Ilovada ochish"):
    if not WEBAPP_URL:
        return None
    url = f"{WEBAPP_URL}{'&' if '?' in WEBAPP_URL else '?'}diplom={diploma_id}"
    return Button(text=text, web_app=WebAppInfo(url=url))


def esc(value, limit=300):
    value = str(value or "")
    return html.escape(value if len(value) <= limit else value[:limit - 1] + "…")


async def send(target, text, markup=None, edit=None):
    """edit — tahrirlanadigan xabar (bo'lmasa yangisi yuboriladi)."""
    if edit is not None and edit.text:
        with suppress(TelegramBadRequest):
            await edit.edit_text(text, reply_markup=markup)
            return edit
    return await target.answer(text, reply_markup=markup)


# ===== Kirish nuqtasi =====
async def diploma_start(message: Message, state: FSMContext):
    """Pastdagi «🎓 Diplom ishi» tugmasi va /diplom buyrug'i."""
    save_user(message.from_user)
    await state.set_state(None)
    drafts = storage.user_diplomas(message.from_user.id)
    if not drafts:
        await ask_new(message, state)
        return
    rows = [[Button(text=f"▶️ {d['title'][:45] or 'Mavzusiz'}", callback_data=cb("open", d["id"]))] for d in drafts]
    rows.append([Button(text="➕ Yangi diplom ishi", callback_data="dip:new:0")])
    await message.answer(
        "🎓 <b>Diplom ishi</b>\n\nBoshlangan ishlaringiz saqlangan — davom ettirishingiz yoki yangisini boshlashingiz mumkin 👇",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


INTRO = (
    "🎓 <b>Diplom ishi</b>\n\n"
    "Mavzudan boshlab tayyor DOCX/PDF gacha bosqichma-bosqich birga ishlaymiz:\n"
    "1️⃣ Ma'lumotlar (12 ta savol, keyinroq to'ldirsa ham bo'ladi)\n"
    "2️⃣ Metodik qo'llanma tahlili (yuklasangiz)\n"
    "3️⃣ Reja — <b>bepul</b>, o'zgartirish va qayta tuzish mumkin\n"
    "4️⃣ Kirish, har bir bob va xulosa — har birini ko'rib, tasdiqlaysiz\n"
    "5️⃣ Haqiqiy ilmiy manbalar (OpenAlex/Crossref), sxema va jadvallar\n\n"
    f"💰 Narxi: har bir bet <b>{money(DIPLOM_PAGE_PRICE)}</b> — pul faqat reja tasdiqlanganda bir marta yechiladi.\n\n"
)


async def ask_new(message: Message, state: FSMContext):
    await state.set_state(Diplom.field)
    await state.update_data(dip_id=None, dip_field="topic", dip_mode="wizard")
    await message.answer(INTRO + f"✍️ {LABEL['topic']}ni yozing:\n\n<i>{FIELDS[0][2]}</i>",
                         reply_markup=inline([Button(text="❌ Bekor qilish", callback_data="dip:cancel:0")]))


@router.message(Command("diplom"))
async def diploma_command(message: Message, state: FSMContext):
    await diploma_start(message, state)


@router.callback_query(F.data == "dip:new:0")
async def new_diploma(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await ask_new(callback.message, state)


@router.callback_query(F.data.startswith("dip:cancel:"))
async def cancel(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await callback.answer("Bekor qilindi")
    with suppress(TelegramBadRequest):
        await callback.message.edit_text("❌ Bekor qilindi. Saqlangan ma'lumotlar yo'qolmaydi — «🎓 Diplom ishi» orqali davom ettirasiz.")


def owned(callback: CallbackQuery):
    """Tugmadagi diplom ID'si va loyiha (faqat egasiniki). Topilmasa — None."""
    parts = callback.data.split(":")
    if len(parts) < 3 or not parts[2].isdecimal():
        return None
    loaded = storage.load(int(parts[2]), callback.from_user.id)
    # Qism kaliti o'zi ham «:» li bo'lishi mumkin («chapter:0») — qolgan hammasi bitta argument
    return (int(parts[2]), ":".join(parts[3:]), *loaded) if loaded else None


# ===== 1. Ma'lumotlar =====
def field_prompt(diploma_id, key, project, mode):
    index = KEYS.index(key)
    head = f"🎓 <b>Diplom ishi</b> · ma'lumotlar <code>{index + 1}/{len(KEYS)}</code>\n\n"
    back = cb("field", diploma_id, KEYS[index - 1]) if index and mode == "wizard" else cb("summary", diploma_id)
    nav = [Button(text="⬅️ Orqaga", callback_data=back)]
    if not FIELDS[index][3]:
        nav.append(Button(text="⏭ Keyinroq", callback_data=cb("skip", diploma_id, key)))
    cancel = [Button(text="❌ Bekor qilish", callback_data=cb("cancel", diploma_id))]
    current = project["info"].get(key) if key != "method" else project["method"].get("name")
    now = f"\n\nHozirgi qiymat: <b>{esc(current)}</b>" if current and key not in ("lang", "pages") else ""
    if key == "lang":
        langs = [Button(text=name, callback_data=cb("set", diploma_id, f"lang={k}")) for k, name in LANGUAGES.items()]
        return head + f"{LABEL[key]}ni tanlang:", inline(langs, nav, cancel)
    if key == "pages":
        options = [Button(text=f"{'✅ ' if project['info'].get('pages') == n else ''}{n} bet · {money(n * DIPLOM_PAGE_PRICE)}",
                          callback_data=cb("set", diploma_id, f"pages={n}")) for n in DIPLOM_PAGE_OPTIONS]
        rows = [options[i:i + 2] for i in range(0, len(options), 2)]
        return head + (
            f"{LABEL[key]}ni tanlang yoki o'zingiz <b>{DIPLOM_PAGES_MIN}–{DIPLOM_PAGES_MAX}</b> oralig'ida son yozing.\n"
            f"💰 Har bir bet — {money(DIPLOM_PAGE_PRICE)}"
        ), InlineKeyboardMarkup(inline_keyboard=rows + [nav, cancel])
    if key == "method":
        return head + (
            f"{LABEL[key]}ni <b>PDF yoki DOCX</b> fayl qilib yuboring.\n\n"
            "AI undan tarkib, hajm, shrift, chetlar, iqtibos va adabiyotlar talablarini oladi. Yuklamasangiz — "
            "namunaviy tuzilma taklif qilinadi (bu haqda alohida aytiladi)." + now
        ), inline(nav, cancel)
    return head + f"✍️ {LABEL[key]}ni yozing:\n\n<i>{FIELDS[index][2]}</i>" + now, inline(nav, cancel)


async def show_field(message: Message, state: FSMContext, diploma_id, key, mode="wizard", edit=None):
    _, project = storage.load(diploma_id)
    await state.set_state(Diplom.upload if key == "method" else Diplom.field)
    await state.update_data(dip_id=diploma_id, dip_field=key, dip_mode=mode)
    text, markup = field_prompt(diploma_id, key, project, mode)
    await send(message, text, markup, edit)


async def after_field(message: Message, state: FSMContext, diploma_id, key, edit=None):
    """Maydon saqlangach: wizard'da — keyingi savol, tahrirlashda — umumiy ko'rinish."""
    data = await state.get_data()
    index = KEYS.index(key)
    if data.get("dip_mode") == "wizard" and index + 1 < len(KEYS):
        await show_field(message, state, diploma_id, KEYS[index + 1], "wizard", edit)
    else:
        await state.set_state(None)
        await show_summary(message, diploma_id, edit)


@router.message(Diplom.field, plain_text)
async def field_text(message: Message, state: FSMContext):
    data = await state.get_data()
    key, diploma_id = data.get("dip_field"), data.get("dip_id")
    value = " ".join(message.text.split())
    if key == "pages":
        if not value.isdecimal() or not DIPLOM_PAGES_MIN <= int(value) <= DIPLOM_PAGES_MAX:
            await message.answer(f"⚠️ {DIPLOM_PAGES_MIN} dan {DIPLOM_PAGES_MAX} gacha son yozing yoki tugmani bosing.")
            return
        value = int(value)
    elif key == "lang":
        await message.answer("Tilni tugma orqali tanlang 👆")
        return
    elif key == "topic" and len(value) < 5:
        await message.answer("⚠️ Mavzu kamida 5 belgi bo'lsin. Qayta yozing:")
        return
    elif len(str(value)) > MAX_LEN.get(key, 200):
        await message.answer(f"⚠️ {MAX_LEN.get(key, 200)} belgidan oshmasin. Qayta yozing:")
        return
    if diploma_id is None:  # yangi diplom — mavzu kiritilganda yaratiladi
        diploma_id = storage.create(message.from_user.id, {"topic": value})
        await state.update_data(dip_id=diploma_id)
    else:
        service.save_info(diploma_id, {key: value})
    await after_field(message, state, diploma_id, key)


@router.message(Diplom.upload, F.document)
async def method_file(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    diploma_id = data.get("dip_id")
    document = message.document
    if document.file_size and document.file_size > 20 * 1024 * 1024:
        await message.answer("⚠️ Fayl 20 MB dan katta. Kichikroq faylni yoki ilova orqali yuklang.")
        return
    try:
        content = (await bot.download(document.file_id)).getvalue()
        service.save_file(diploma_id, content, document.file_name or "metodika", "method")
    except DiplomaError as e:
        await message.answer(f"⚠️ {html.escape(str(e))}")
        return
    except TelegramAPIError:
        await message.answer("⚠️ Faylni olib bo'lmadi. Qayta yuboring.")
        return
    await message.answer("✅ Metodik qo'llanma saqlandi — reja tuzishda AI uni tahlil qiladi.")
    await after_field(message, state, diploma_id, "method")


@router.message(Diplom.upload)
async def method_wrong(message: Message):
    await message.answer("📎 Faylni <b>hujjat</b> sifatida yuboring (PDF yoki DOCX) yoki «⏭ Keyinroq» ni bosing.")


@router.message(Diplom.field)
async def field_wrong(message: Message):
    await message.answer("Matn ko'rinishida yozing ✍️ yoki tugmalardan birini bosing.")


@router.callback_query(F.data.startswith("dip:field:"))
async def field_button(callback: CallbackQuery, state: FSMContext):
    found = owned(callback)
    if not found or found[1] not in KEYS:
        await callback.answer("Topilmadi", show_alert=True)
        return
    data = await state.get_data()
    await show_field(callback.message, state, found[0], found[1], data.get("dip_mode") or "edit", callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("dip:edit:"))
async def edit_field(callback: CallbackQuery, state: FSMContext):
    found = owned(callback)
    if not found or found[1] not in KEYS:
        await callback.answer("Topilmadi", show_alert=True)
        return
    if found[3]["plan"].get("approved") and found[1] in ("pages", "lang"):
        await callback.answer("Reja tasdiqlangan — til va hajmni endi o'zgartirib bo'lmaydi.", show_alert=True)
        return
    await show_field(callback.message, state, found[0], found[1], "edit", callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("dip:skip:"))
async def skip_field(callback: CallbackQuery, state: FSMContext):
    found = owned(callback)
    if not found:
        await callback.answer()
        return
    await callback.answer()
    await after_field(callback.message, state, found[0], found[1], callback.message)


@router.callback_query(F.data.startswith("dip:set:"))
async def set_choice(callback: CallbackQuery, state: FSMContext):
    found = owned(callback)
    if not found or "=" not in found[1]:
        await callback.answer()
        return
    key, value = found[1].split("=", 1)
    if key == "lang" and value in LANGUAGES:
        service.save_info(found[0], {"lang": value})
    elif key == "pages" and value.isdecimal() and DIPLOM_PAGES_MIN <= int(value) <= DIPLOM_PAGES_MAX:
        service.save_info(found[0], {"pages": int(value)})
    else:
        await callback.answer()
        return
    await callback.answer("Saqlandi ✅")
    await after_field(callback.message, state, found[0], key, callback.message)


# ===== Umumiy ko'rinish =====
def method_line(project):
    method = project["method"]
    if method["status"] == "analyzed":
        return f"📘 Metodika: <b>tahlil qilingan</b> ({len(method['found'])} ta talab)"
    if method["status"] == "uploaded":
        return f"📘 Metodika: <b>{esc(method['name'], 60)}</b> (reja tuzishda tahlil qilinadi)"
    return "📘 Metodika: yuklanmagan — namunaviy talablar"


def warnings(project):
    rules = project["method"].get("rules") or {}
    pages = project["info"].get("pages") or 0
    lines = []
    if rules.get("pages_min") and pages < rules["pages_min"]:
        lines.append(f"⚠️ Qo'llanmaga ko'ra hajm kamida {int(rules['pages_min'])} bet — siz {pages} bet tanlagansiz.")
    if rules.get("pages_max") and pages > rules["pages_max"]:
        lines.append(f"⚠️ Qo'llanmaga ko'ra hajm ko'pi bilan {int(rules['pages_max'])} bet — siz {pages} bet tanlagansiz.")
    return "\n".join(lines)


async def show_summary(message: Message, diploma_id, edit=None):
    row, project = storage.load(diploma_id)
    info = project["info"]
    lines = [f"{LABEL[k]}: <b>{esc(info.get(k)) or '—'}</b>" for k in KEYS if k not in ("lang", "pages", "method")]
    lines.insert(8, f"{LABEL['lang']}: <b>{LANGUAGES.get(info['lang'], info['lang'])}</b>")
    lines.insert(9, f"{LABEL['pages']}: <b>{info['pages']} bet</b>")
    price = service.price_for(message.chat.id, info["pages"])
    text = (
        "🎓 <b>Diplom ishi — ma'lumotlar</b>\n\n" + "\n".join(lines) + f"\n{method_line(project)}\n\n"
        f"💰 Narxi: <b>{money(price) if price else 'bepul (admin)'}</b> — reja tasdiqlanganda yechiladi.\n"
        + (f"\n{warnings(project)}\n" if warnings(project) else "")
        + "\nKeyingi qadam — reja (bepul). Ma'lumotlarni keyin ham o'zgartirasiz."
    )
    rows = [
        [Button(text="📋 Reja tuzish (bepul)" if not project["plan"]["chapters"] else "📋 Rejaga o'tish",
                callback_data=cb("plan" if not project["plan"]["chapters"] else "showplan", diploma_id))],
        [Button(text="✏️ Ma'lumotlarni tahrirlash", callback_data=cb("fields", diploma_id))],
        [app_button(diploma_id)] if app_button(diploma_id) else None,
        [Button(text="❌ Yopish", callback_data=cb("cancel", diploma_id))],
    ]
    await send(message, text, InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r]), edit)


@router.callback_query(F.data.startswith("dip:summary:"))
async def summary_button(callback: CallbackQuery, state: FSMContext):
    found = owned(callback)
    if not found:
        await callback.answer("Topilmadi", show_alert=True)
        return
    await state.set_state(None)
    await show_summary(callback.message, found[0], callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("dip:fields:"))
async def fields_menu(callback: CallbackQuery):
    found = owned(callback)
    if not found:
        await callback.answer()
        return
    buttons = [Button(text=LABEL[k], callback_data=cb("edit", found[0], k)) for k in KEYS]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([Button(text="⬅️ Orqaga", callback_data=cb("summary", found[0]))])
    await send(callback.message, "✏️ Qaysi ma'lumotni o'zgartirasiz?", InlineKeyboardMarkup(inline_keyboard=rows),
               callback.message)
    await callback.answer()


# ===== Ishni ochish (davom ettirish) =====
@router.callback_query(F.data.startswith("dip:open:"))
async def open_diploma(callback: CallbackQuery, state: FSMContext):
    found = owned(callback)
    if not found:
        await callback.answer("Topilmadi", show_alert=True)
        return
    await callback.answer()
    await state.set_state(None)
    await show_stage(callback.message, found[0], callback.message)


async def show_stage(message: Message, diploma_id, edit=None):
    row, project = storage.load(diploma_id)
    if not project["plan"]["chapters"]:
        await show_summary(message, diploma_id, edit)
    elif not project["plan"]["approved"]:
        await show_plan(message, diploma_id, edit)
    elif not all(service.has_text(project, k) for k in service.parts(project)):
        await show_write_all(message, diploma_id, edit)
    else:
        key = service.current_part(project)
        if key is None:
            await show_done(message, diploma_id, edit)
        else:
            await show_part(message, diploma_id, key, edit)


# ===== 2. Reja =====
async def animate_live(message: Message, title, hint):
    """title() — har safar yangi sarlavha (masalan «2/5 · I bob yozilmoqda»)."""
    step = 0
    while True:
        bar = "▰" * (step % 10 + 1) + "▱" * (9 - step % 10)
        with suppress(TelegramBadRequest):
            await message.edit_text(f"⏳ <b>{html.escape(title())}</b>\n\n<code>{bar}</code>\n\n<i>{hint}</i>")
        step += 1
        await asyncio.sleep(5)


async def run_with_progress(message: Message, title, coroutine, hint="Odatda 15–40 soniya."):
    """title — matn yoki funksiya (jarayon davomida o'zgaradigan sarlavha)."""
    progress = await message.answer(f"⏳ <b>{html.escape(title()) if callable(title) else title}</b>")
    animation = asyncio.create_task(animate_live(progress, title, hint) if callable(title)
                                    else animate(progress, title, PROGRESS, hint))
    try:
        return await coroutine
    finally:
        animation.cancel()
        with suppress(TelegramBadRequest):
            await progress.delete()


async def guarded(callback: CallbackQuery, diploma_id, title, coroutine_factory, hint="Odatda 15–40 soniya."):
    """Bir diplomda bir vaqtda bitta AI amali. Xato — foydalanuvchiga tushunarli matn bilan. True — muvaffaqiyat."""
    if service.busy(diploma_id):
        with suppress(TelegramBadRequest):
            await callback.answer("⏳ Hozir tayyorlanmoqda, biroz kuting.", show_alert=True)
        return False
    # Bitta tugma bosilishidan keyin bir nechta qadam ketma-ket bo'lishi mumkin (tasdiqlash → kirishni yozish):
    # Telegram tugmaga faqat bir marta javob qabul qiladi
    with suppress(TelegramBadRequest):
        await callback.answer("🚀 Boshladik!")
    async with service.lock(diploma_id):
        try:
            await run_with_progress(callback.message, title, coroutine_factory(), hint)
            return True
        except DiplomaError as e:
            markup = None
            if e.need:
                markup = inline([Button(text="➕ Hisobni to'ldirish", callback_data="wallet_topup")],
                                [Button(text="🔄 Qayta urinish", callback_data=cb("approve", diploma_id))])
            await callback.message.answer(f"⚠️ {html.escape(str(e))}", reply_markup=markup)
        except GenerationError as e:
            await callback.message.answer(f"😕 {html.escape(str(e))}")
        except Exception:
            logging.exception("Diplom ishida kutilmagan xato")
            await callback.message.answer("😕 Kutilmagan xato yuz berdi. Ishingiz saqlangan — qayta urinib ko'ring.")
    return False


def plan_lines(project):
    lines = []
    for i, chapter in enumerate(project["plan"]["chapters"]):
        lines.append(f"<b>{service.ROMAN[i]} BOB. {esc(chapter['title'], 150)}</b>")
        lines += [f"   {i + 1}.{j}. {esc(s['title'], 150)}" for j, s in enumerate(chapter["sections"], 1)]
    return "\n".join(lines)


async def show_plan(message: Message, diploma_id, edit=None):
    row, project = storage.load(diploma_id)
    price = service.price_for(message.chat.id, project["info"]["pages"])
    note = ("✅ Metodik qo'llanma talablari asosida tuzildi." if project["method"]["status"] == "analyzed" else
            "ℹ️ Metodik qo'llanma yuklanmagan — bu <b>namunaviy</b> tuzilma. Universitetingiz talablari boshqacha "
            "bo'lsa, qo'llanmani yuklab, rejani qayta tuzing.")
    approved = project["plan"]["approved"]
    text = (
        f"📋 <b>Diplom ishi rejasi</b>\n📝 {esc(project['info']['topic'])}\n\n"
        f"KIRISH\n{plan_lines(project)}\nXULOSA\nFOYDALANILGAN ADABIYOTLAR\n\n{note}\n"
        + (f"\n{warnings(project)}\n" if warnings(project) else "")
        + ("" if approved else
           f"\n💰 Tasdiqlansangiz <b>{money(price) if price else 'bepul (admin)'}</b> yechiladi va yozish boshlanadi.\n"
           f"👛 Balansingiz: <b>{money(get_balance(message.chat.id))}</b>")
    )
    if approved:
        rows = [[Button(text="▶️ Davom ettirish", callback_data=cb("open", diploma_id))]]
    else:
        rows = [
            [Button(text=f"✅ Tasdiqlash — {money(price)}" if price else "✅ Tasdiqlash", callback_data=cb("approve", diploma_id))],
            [Button(text="🔄 Qayta tuzish", callback_data=cb("plan", diploma_id)),
             Button(text="⬅️ Ma'lumotlar", callback_data=cb("summary", diploma_id))],
        ]
        if app_button(diploma_id):
            rows.insert(1, [app_button(diploma_id, "✏️ Rejani ilovada tahrirlash")])
    await send(message, text[:4000], InlineKeyboardMarkup(inline_keyboard=rows), edit)


@router.callback_query(F.data.startswith("dip:showplan:"))
async def showplan_button(callback: CallbackQuery):
    found = owned(callback)
    if not found:
        await callback.answer("Topilmadi", show_alert=True)
        return
    await callback.answer()
    await show_plan(callback.message, found[0], callback.message)


@router.callback_query(F.data.startswith("dip:plan:"))
async def plan_button(callback: CallbackQuery):
    found = owned(callback)
    if not found:
        await callback.answer("Topilmadi", show_alert=True)
        return
    diploma_id, user_id = found[0], callback.from_user.id
    if await guarded(callback, diploma_id, "Reja tuzilmoqda...", lambda: service.make_plan(diploma_id, user_id)):
        await show_plan(callback.message, diploma_id)


@router.callback_query(F.data.startswith("dip:approve:"))
async def approve_button(callback: CallbackQuery):
    found = owned(callback)
    if not found:
        await callback.answer("Topilmadi", show_alert=True)
        return
    diploma_id, user_id = found[0], callback.from_user.id
    if found[3]["plan"]["approved"]:
        await callback.answer()
        await show_stage(callback.message, diploma_id)
        return
    ok = await guarded(callback, diploma_id, "Reja tasdiqlanmoqda, ilmiy manbalar qidirilmoqda...",
                       lambda: service.approve_plan(diploma_id, user_id))
    if ok:
        with suppress(TelegramBadRequest):
            await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("✅ Reja tasdiqlandi. Endi butun ishni yozamiz: kirish, boblar va xulosa.")
        await write_all(callback, diploma_id)


# ===== 3. Qismlar: kirish, boblar, xulosa =====
def part_preview(project, key, limit=2600):
    part = service.part_of(project, key)
    lines = []
    if key == "intro":
        for item in part["items"]:
            lines.append(f"<b>{esc(item['label'])}.</b> {esc(item['paragraphs'][0], 260)}")
    elif key == "conclusion":
        lines = [esc(p, 400) for p in part["paragraphs"][:4]]
    else:
        ci = int(key[8:])
        for si, section in enumerate(part["sections"], 1):
            first = section["paragraphs"][0] if section["paragraphs"] else ""
            lines.append(f"<b>{ci + 1}.{si}. {esc(section['title'], 120)}</b> ({len(section['paragraphs'])} xatboshi)\n{esc(first, 300)}")
        if part.get("figures"):
            kinds = {"scheme": "sxema", "illustration": "rasm", "table": "jadval"}
            lines.append("🖼 " + ", ".join(f"{kinds[f['kind']]}: {esc(f['caption'], 60)}" for f in part["figures"]))
    text = "\n\n".join(lines)
    return text if len(text) <= limit else text[:limit - 1] + "…"


async def show_part(message: Message, diploma_id, key, edit=None):
    row, project = storage.load(diploma_id)
    keys = service.parts(project)
    position = f"{keys.index(key) + 1}/{len(keys)}"
    name = esc(service.part_name(project, key), 160)
    if not service.has_text(project, key):
        await show_write_all(message, diploma_id, edit)
        return
    approved = service.part_of(project, key).get("status") == "approved"
    text = (
        f"🎓 <b>{name}</b> ({position}){' — ✅ tayyor' if approved else ''}\n\n{part_preview(project, key)}\n\n"
        "✏️ To'liq matnni ilovada o'qib, istalgan xatboshini tahrirlashingiz, kengaytirishingiz yoki qisqartirishingiz "
        "mumkin (telefonda ham). «🔄 Qayta yozish» — shu qismni AI qaytadan yozadi."
    )
    rows = [[Button(text="🔄 Qayta yozish", callback_data=cb("rewrite", diploma_id, key)),
             Button(text="📄 Fayl olish", callback_data=cb("draft", diploma_id))]]
    if not approved:
        rows.insert(0, [Button(text="✅ Tasdiqlash va davom etish", callback_data=cb("ok", diploma_id, key))])
    if app_button(diploma_id):
        rows.insert(-1, [app_button(diploma_id, "✏️ Tahrirlash (ilovada)")])
    rows.append([Button(text="⬅️ Barcha qismlar", callback_data=cb("parts", diploma_id))])
    await send(message, text[:4000], InlineKeyboardMarkup(inline_keyboard=rows), edit)


async def show_write_all(message: Message, diploma_id, edit=None):
    """Reja tasdiqlangan, lekin ish (to'liq) yozilmagan — bitta tugma bilan hammasi yoziladi."""
    _, project = storage.load(diploma_id)
    keys = service.parts(project)
    written = sum(service.has_text(project, k) for k in keys)
    rows = [[Button(text="✍️ Hammasini yozish" if not written else "✍️ Qolganini yozish",
                    callback_data=cb("writeall", diploma_id))]]
    if app_button(diploma_id):
        rows.append([app_button(diploma_id)])
    await send(
        message,
        f"🎓 <b>{esc(project['info']['topic'])}</b>\n\n"
        + (f"✅ Yozilgan: {written}/{len(keys)} qism.\n\n" if written else "")
        + "Bitta tugma bilan kirish, barcha boblar (rasm, sxema va jadvallar bilan) va xulosa ketma-ket yoziladi, "
        "tayyor DOCX fayl shu chatga keladi. Keyin istalgan qismni tahrirlash yoki qayta yozdirish mumkin.",
        InlineKeyboardMarkup(inline_keyboard=rows), edit,
    )


async def write_all(callback: CallbackQuery, diploma_id):
    """Butun ishni yozadi, faylni chatga yuboradi va yakuniy menyuni ko'rsatadi."""
    _, project = storage.load(diploma_id)
    status = {"text": "Diplom ishi yozilmoqda..."}

    async def on_part(name, n, total):
        status["text"] = f"{n}/{total} · {name[:80]} yozilmoqda..."

    async def job():
        await service.generate_all(diploma_id, callback.from_user.id, on_part)
        status["text"] = "Fayl tayyorlanmoqda..."
        await service.export(callback.bot, diploma_id, callback.from_user.id)

    total = len(service.parts(project))
    hint = f"Butun ish ({total} qism) odatda {total * 1}–{total * 2} daqiqada yoziladi. Shu orada botdan foydalanishingiz mumkin."
    if await guarded(callback, diploma_id, lambda: status["text"], job, hint):
        await show_done(callback.message, diploma_id)
    elif not service.busy(diploma_id):
        await show_stage(callback.message, diploma_id)


@router.callback_query(F.data.startswith("dip:writeall:"))
async def write_all_button(callback: CallbackQuery):
    found = owned(callback)
    if not found:
        await callback.answer("Topilmadi", show_alert=True)
        return
    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(reply_markup=None)
    await write_all(callback, found[0])


@router.callback_query(F.data.startswith("dip:view:"))
async def view_button(callback: CallbackQuery):
    found = owned(callback)
    if not found or not found[1]:
        await callback.answer("Topilmadi", show_alert=True)
        return
    try:
        service.part_of(found[3], found[1])
    except DiplomaError:
        await callback.answer("Topilmadi", show_alert=True)
        return
    await callback.answer()
    await show_part(callback.message, found[0], found[1])


@router.callback_query(F.data.startswith("dip:parts:"))
async def parts_button(callback: CallbackQuery):
    found = owned(callback)
    if not found:
        await callback.answer("Topilmadi", show_alert=True)
        return
    await callback.answer()
    await show_stage(callback.message, found[0], callback.message)


async def write_part(callback: CallbackQuery, diploma_id, key, again=False):
    _, project = storage.load(diploma_id)
    title = f"{service.part_name(project, key)} yozilmoqda..."
    hint = "Bob yozilishi odatda 30–90 soniya oladi." if key.startswith("chapter") else "Odatda 20–40 soniya."
    if await guarded(callback, diploma_id, title[:120],
                     lambda: service.generate(diploma_id, callback.from_user.id, key, again), hint):
        await show_part(callback.message, diploma_id, key)


@router.callback_query(F.data.startswith("dip:write:"))
async def write_button(callback: CallbackQuery):
    found = owned(callback)
    if not found or not found[1]:
        await callback.answer("Topilmadi", show_alert=True)
        return
    await write_part(callback, found[0], found[1])


@router.callback_query(F.data.startswith("dip:rewrite:"))
async def rewrite_button(callback: CallbackQuery):
    found = owned(callback)
    if not found or not found[1]:
        await callback.answer("Topilmadi", show_alert=True)
        return
    diploma_id, key = found[0], found[1]
    await callback.answer()
    await callback.message.answer(
        f"🔄 <b>{esc(service.part_name(found[3], key))}</b> qaytadan yozilsinmi?\n\n"
        "Hozirgi matn (sizning tahrirlaringiz bilan) almashtiriladi.",
        reply_markup=inline([Button(text="✅ Ha, qayta yozilsin", callback_data=cb("rewrite_yes", diploma_id, key))],
                            [Button(text="❌ Yo'q", callback_data=cb("open", diploma_id))]),
    )


@router.callback_query(F.data.startswith("dip:rewrite_yes:"))
async def rewrite_yes(callback: CallbackQuery):
    found = owned(callback)
    if not found or not found[1]:
        await callback.answer("Topilmadi", show_alert=True)
        return
    with suppress(TelegramBadRequest):
        await callback.message.delete()
    await write_part(callback, found[0], found[1], again=True)


@router.callback_query(F.data.startswith("dip:ok:"))
async def approve_part(callback: CallbackQuery):
    found = owned(callback)
    if not found or not found[1]:
        await callback.answer("Topilmadi", show_alert=True)
        return
    diploma_id, key = found[0], found[1]
    try:
        service.approve_part(diploma_id, key)
    except DiplomaError as e:
        await callback.answer(str(e), show_alert=True)
        return
    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(reply_markup=None)
    _, project = storage.load(diploma_id)
    nxt = service.current_part(project)
    await callback.answer("Tasdiqlandi ✅")
    if nxt is None:
        await show_done(callback.message, diploma_id)
    elif service.has_text(project, nxt):
        await show_part(callback.message, diploma_id, nxt)
    else:
        await show_write_all(callback.message, diploma_id)


# ===== 4. Yakun va fayl =====
async def show_done(message: Message, diploma_id, edit=None):
    _, project = storage.load(diploma_id)
    rows = [[Button(text="📄 DOCX olish", callback_data=cb("export", diploma_id, "docx"))]]
    if PDF_AVAILABLE:
        rows[0].append(Button(text="📕 PDF olish", callback_data=cb("export", diploma_id, "pdf")))
    if app_button(diploma_id):
        rows.append([app_button(diploma_id, "✏️ Tahrirlash (ilovada)")])
    # Har bir qismni botning o'zida ko'rish va qayta yozdirish
    views = [Button(text=f"👁 {service.part_name(project, k).split(':')[0]}", callback_data=cb("view", diploma_id, k))
             for k in service.parts(project)]
    rows += [views[i:i + 3] for i in range(0, len(views), 3)]
    await send(
        message,
        f"🎉 <b>Diplom ishi tayyor!</b>\n\n📝 {esc(project['info']['topic'])}\n"
        f"📄 ~{round(service.word_count(project) / 280) + 6} bet  ·  📚 Manbalar: {len(project['sources'])} ta\n\n"
        "Faylni oling. Matnni «✏️ Tahrirlash» orqali (telefonda ham) o'zgartirishingiz, «👁» tugmalari bilan "
        "har bir qismni ko'rib, kerak bo'lsa qayta yozdirishingiz mumkin. Keyin faylni qayta oling.\n\n"
        "⚠️ Matnni ilmiy rahbaringiz bilan kelishib oling: raqamli ma'lumotlar va iqtiboslarni tekshiring.",
        InlineKeyboardMarkup(inline_keyboard=rows), edit,
    )


async def export_to_chat(callback: CallbackQuery, bot: Bot, diploma_id, fmt):
    await guarded(callback, diploma_id, "Fayl tayyorlanmoqda...",
                  lambda: service.export(bot, diploma_id, callback.from_user.id, fmt), "Odatda 5–30 soniya.")


@router.callback_query(F.data.startswith("dip:export:"))
async def export_button(callback: CallbackQuery, bot: Bot):
    found = owned(callback)
    if not found:
        await callback.answer("Topilmadi", show_alert=True)
        return
    await export_to_chat(callback, bot, found[0], "pdf" if found[1] == "pdf" else "docx")


@router.callback_query(F.data.startswith("dip:draft:"))
async def draft_button(callback: CallbackQuery, bot: Bot):
    found = owned(callback)
    if not found:
        await callback.answer("Topilmadi", show_alert=True)
        return
    await export_to_chat(callback, bot, found[0], "docx")


# Fayl ostidagi «🎨 Boshqa dizaynda olish» (umumiy «eskirgan tugma» handleridan oldin bo'lishi shart)
doc_design.register(router, "dip", service, owned, DiplomaError)


@router.callback_query(F.data.startswith("dip:"))
async def stale(callback: CallbackQuery):
    await callback.answer("Bu tugma eskirgan. «🎓 Diplom ishi» orqali davom ettiring.", show_alert=True)
