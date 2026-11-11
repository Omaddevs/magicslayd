"""🔬 Dissertatsiya — bot chatidagi bosqichma-bosqich jarayon.

1) Turi → 2) Shaxsiy ma'lumotlar → 3) Mavzu (AI mavzu taklif qiladi) → 4) Metodik qo'llanma → 5) Materiallar
→ reja (bepul) → tasdiqlash (to'lov) → kirish, boblar, umumiy xulosa, annotatsiya (har biri tasdiqlanadi)
→ sifat nazorati → DOCX / PDF. Har bir javob darhol saqlanadi; batafsil tahrirlash — web ilovada (bitta loyiha)."""
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

from config import DISS_PAGE_PRICE, DISS_PAGES_MAX, DISS_PAGES_MIN, DISS_TYPES, WEBAPP_URL, money
from converter import PDF_AVAILABLE
from database import get_balance, save_user
from dissertation import service, storage
from dissertation.service import DissError
from handlers import doc_design
from handlers.diploma import animate_live
from handlers.presentation import animate, plain_text
from presentation.ai import LANGUAGES, GenerationError

router = Router()
Button = InlineKeyboardButton


class Dissertatsiya(StatesGroup):
    field = State()   # matnli javob kutilmoqda
    upload = State()  # fayl kutilmoqda (qo'llanma yoki material)


# (kalit, bosqich, sarlavha, nima uchun kerak, misol, majburiy)
FIELDS = [
    ("student", 2, "👤 F.I.Sh.", "Titul varag'iga yoziladi.", "Aliyev Vali Karimovich", False),
    ("university", 2, "🏛 Universitet yoki ilmiy muassasa", "Titul varag'i va mahalliy talablar uchun.",
     "Toshkent davlat iqtisodiyot universiteti", False),
    ("faculty", 2, "🏢 Fakultet yoki ilmiy tashkilot", "Titul varag'iga yoziladi.", "Iqtisodiyot fakulteti", False),
    ("specialty", 2, "🔖 Mutaxassislik nomi", "Tadqiqot qaysi ixtisoslik doirasida ekani — reja va uslubga ta'sir qiladi.",
     "Raqamli iqtisodiyot", False),
    ("specialty_code", 2, "🔢 Mutaxassislik kodi", "Titul va OAK talablari uchun.", "08.00.16", False),
    ("degree", 2, "🎓 Ilmiy daraja", "Qaysi daraja uchun yozilayotgani — titulga yoziladi.",
     "Iqtisodiyot fanlari bo'yicha falsafa doktori (PhD)", False),
    ("supervisor", 2, "👨‍🏫 Ilmiy rahbar yoki maslahatchi", "Titul varag'iga yoziladi.", "i.f.d., prof. Karimov A.B.", False),
    ("lang", 2, "🌐 Dissertatsiya tili", "Butun matn shu tilda yoziladi.", "", True),
    ("direction", 3, "🧭 Tadqiqot yo'nalishi", "AI shu soha bo'yicha reja va manbalarni tanlaydi, mavzu ham taklif qiladi.",
     "Raqamli iqtisodiyot, kichik biznes", True),
    ("problem", 3, "❓ O'rganilayotgan muammo", "Maqsad va vazifalar aniqroq bo'ladi.",
     "Kichik korxonalarda raqamli texnologiyalar sekin joriy etilmoqda", False),
    ("topic", 3, "📝 Dissertatsiya mavzusi", "Butun ish shu mavzu atrofida quriladi. Bilmasangiz — «💡 Mavzu taklif qilish».",
     "Kichik biznes subyektlarini raqamli transformatsiya qilish mexanizmlarini takomillashtirish", True),
    ("existing", 3, "📂 Mavzu bo'yicha mavjud ma'lumotlaringiz",
     "Natijalaringiz, maqolalaringiz yoki to'plagan ma'lumotlaringiz. Yo'q bo'lsa — AI ularni o'ylab topmaydi.",
     "2023–2024 yillarda 40 ta korxonada so'rovnoma o'tkazdim", False),
    ("pages", 3, "📄 Hajmi (betlar)", "Narx va har bir bob hajmi shunga qarab hisoblanadi.", "", True),
    ("extra", 3, "🗒 Qo'shimcha talablar", "Ilmiy rahbaringiz yoki kafedra talablari.", "Amaliy qism Toshkent viloyati misolida", False),
    ("method", 4, "📘 Metodik qo'llanma", "AI undan tuzilish, hajm, shrift, chetlar va adabiyotlar talablarini oladi.", "", False),
    ("materials", 5, "📎 Qo'shimcha materiallar",
     "Excel/CSV ma'lumotlar (grafik va statistika faqat shulardan), PDF/DOCX hujjatlar.", "", False),
]
KEYS = [f[0] for f in FIELDS]
FIELD = {f[0]: f for f in FIELDS}
STAGES = {1: "Turi", 2: "Shaxsiy ma'lumotlar", 3: "Mavzu", 4: "Metodik talablar", 5: "Materiallar"}
MAX_LEN = {"topic": 300, "existing": 1500, "extra": 1000, "problem": 600}
PROGRESS = ("🧠 Mavzu tahlil qilinmoqda", "📘 Metodik talablar o'rganilmoqda", "📋 Reja tuzilmoqda",
            "🔎 Ilmiy manbalar qidirilmoqda", "✍️ Ilmiy matn yozilmoqda", "🧩 Boblar bog'lanmoqda",
            "📊 Sxema, grafik va jadvallar tayyorlanmoqda", "🔍 Matn tekshirilmoqda")


def cb(action, item_id, arg=""):
    return f"dis:{action}:{item_id}" + (f":{arg}" if arg != "" else "")


def esc(value, limit=300):
    value = str(value or "")
    return html.escape(value if len(value) <= limit else value[:limit - 1] + "…")


def app_button(item_id, text="✏️ Ilovada ochish"):
    if not WEBAPP_URL:
        return None
    url = f"{WEBAPP_URL}{'&' if '?' in WEBAPP_URL else '?'}diss={item_id}"
    return Button(text=text, web_app=WebAppInfo(url=url))


def markup(*rows):
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows if r and all(r)])


async def send(message, text, keyboard=None, edit=None):
    if edit is not None and edit.text:
        with suppress(TelegramBadRequest):
            await edit.edit_text(text, reply_markup=keyboard)
            return edit
    return await message.answer(text, reply_markup=keyboard)


def owned(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) < 3 or not parts[2].isdecimal():
        return None
    loaded = storage.load(int(parts[2]), callback.from_user.id)
    # Qism kaliti o'zi ham «:» li bo'lishi mumkin («chapter:0») — qolgan hammasi bitta argument
    return (int(parts[2]), ":".join(parts[3:]), *loaded) if loaded else None


# ===== Boshlang'ich sahifa =====
GUIDE = (
    "📖 <b>Dissertatsiya yaratish bo'yicha yo'riqnoma</b>\n\n"
    "1. Turini tanlang (magistrlik, PhD, DSc) — tuzilma va hajm shunga moslashadi.\n"
    "2. Shaxsiy ma'lumotlar — titul varag'i uchun (keyin ham to'ldirsa bo'ladi).\n"
    "3. Mavzu va yo'nalish. Mavzuni bilmasangiz — AI 5 ta variant taklif qiladi.\n"
    "4. Metodik qo'llanmani yuklang — AI faqat unda yozilgan talablarni oladi.\n"
    "5. Ma'lumotlaringizni (Excel/CSV) yuklang — grafik va statistika FAQAT shulardan tuziladi.\n"
    "6. Reja (bepul) — o'zgartirasiz, qayta tuzdirasiz, keyin tasdiqlaysiz (shu payt pul yechiladi).\n"
    "7. Kirish, har bir bob, xulosa va annotatsiyani ko'rib chiqib tasdiqlaysiz.\n"
    "8. Sifat nazorati: takrorlar, iqtiboslar, manbalar, hajm, kirish va xulosa mosligi.\n"
    "9. DOCX / PDF — titul, annotatsiya, avtomatik mundarija, raqamlangan rasm va jadvallar bilan.\n\n"
    "⚠️ Manbalar — faqat OpenAlex/Crossref'dagi haqiqiy ishlar. Raqam, so'rovnoma va natijalar o'ylab topilmaydi: "
    "ma'lumot bo'lmasa, misollar «namunaviy» deb belgilanadi. Matnni ilmiy rahbaringiz bilan tekshiring."
)


async def diss_start(message: Message, state: FSMContext):
    """Pastdagi «🔬 Dissertatsiya» tugmasi va /dissertatsiya buyrug'i."""
    save_user(message.from_user)
    await state.set_state(None)
    items = storage.user_items(message.from_user.id)
    rows = [[Button(text="➕ Yangi dissertatsiya", callback_data="dis:new:0")]]
    rows += [[Button(text=f"▶️ {esc(d['title'], 40) or 'Mavzusiz'}", callback_data=cb("open", d["id"]))] for d in items]
    rows.append([Button(text="📖 Yo'riqnoma", callback_data="dis:guide:0")])
    await message.answer(
        "🔬 <b>Dissertatsiya yaratish</b>\n\nIlmiy mavzuingizni kiriting va AI yordamida dissertatsiya tayyorlash "
        "jarayonini boshlang. Har bir bosqichni o'zingiz ko'rib chiqasiz va tasdiqlaysiz.\n\n"
        f"💰 Narxi: har bir bet <b>{money(DISS_PAGE_PRICE)}</b> — pul faqat reja tasdiqlanganda bir marta yechiladi.\n"
        + ("\n📂 Saqlangan dissertatsiyalaringiz pastda — davom ettirishingiz mumkin." if items else ""),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.message(Command("dissertatsiya"))
async def diss_command(message: Message, state: FSMContext):
    await diss_start(message, state)


@router.callback_query(F.data == "dis:guide:0")
async def guide(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(GUIDE)


@router.callback_query(F.data == "dis:new:0")
async def new_item(callback: CallbackQuery):
    await callback.answer()
    rows = [[Button(text=f"{t['name']} (~{t['pages']} bet)", callback_data=f"dis:kind:0:{k}")] for k, t in DISS_TYPES.items()]
    await callback.message.answer(
        f"🔬 <b>Dissertatsiya</b> · 1-bosqich: <b>{STAGES[1]}</b>\n\nQaysi turdagi dissertatsiya?\n"
        "<i>Tanlovga qarab tuzilma (boblar soni), hajm va kirish talablari moslashadi.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("dis:kind:"))
async def choose_kind(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    kind = parts[3] if len(parts) > 3 else ""
    if kind not in DISS_TYPES:
        await callback.answer()
        return
    item_id = int(parts[2])
    if item_id:  # mavjud ishning turi o'zgartirilmoqda
        if not storage.load(item_id, callback.from_user.id):
            await callback.answer("Topilmadi", show_alert=True)
            return
        try:
            service.set_kind(item_id, kind)
        except DissError as e:
            await callback.answer(str(e), show_alert=True)
            return
        await callback.answer("Saqlandi ✅")
        await show_summary(callback.message, item_id, callback.message)
        return
    item_id = service.create(callback.from_user.id, kind)
    await callback.answer(DISS_TYPES[kind]["name"])
    await show_field(callback.message, state, item_id, KEYS[0], "wizard", callback.message)


# ===== Savollar =====
def field_prompt(item_id, key, project, mode):
    _, stage, label, why, example, required = FIELD[key]
    index = KEYS.index(key)
    head = (f"🔬 <b>Dissertatsiya</b> · {stage}-bosqich: <b>{STAGES[stage]}</b>\n"
            f"<code>savol {index + 1}/{len(KEYS)}</code> · {'majburiy' if required else 'ixtiyoriy'}\n\n")
    back = cb("field", item_id, KEYS[index - 1]) if index and mode == "wizard" else cb("summary", item_id)
    nav = [Button(text="⬅️ Orqaga", callback_data=back)]
    if not required:
        nav.append(Button(text="⏭ Keyinroq" if key != "materials" else "✅ Tayyor", callback_data=cb("skip", item_id, key)))
    cancel = [Button(text="❌ Bekor qilish", callback_data=cb("cancel", item_id))]
    info = project["info"]
    current = info.get(key) if key in info else None
    now = f"\n\nHozirgi qiymat: <b>{esc(current)}</b>" if current and key not in ("lang", "pages") else ""
    text = f"{head}<b>{label}</b>\n💡 <i>{why}</i>"
    if key == "lang":
        return text, markup([Button(text=n, callback_data=cb("set", item_id, f"lang={k}")) for k, n in LANGUAGES.items()], nav, cancel)
    if key == "pages":
        kind = DISS_TYPES.get(project["kind"], DISS_TYPES["other"])
        options = [Button(text=f"{'✅ ' if info['pages'] == n else ''}{n} bet · {money(n * DISS_PAGE_PRICE)}",
                          callback_data=cb("set", item_id, f"pages={n}")) for n in kind["options"]]
        rows = [options[i:i + 2] for i in range(0, len(options), 2)]
        return (text + f"\n\nTanlang yoki o'zingiz <b>{DISS_PAGES_MIN}–{DISS_PAGES_MAX}</b> oralig'ida son yozing. "
                f"{kind['name']} uchun odatda ~{kind['pages']} bet."), InlineKeyboardMarkup(inline_keyboard=rows + [nav, cancel])
    if key == "method":
        name = project["method"].get("name")
        return (text + "\n\nFaylni <b>PDF yoki DOCX</b> qilib yuboring. Yuklamasangiz — namunaviy tuzilma taklif qilinadi "
                "(alohida aytiladi)." + (f"\n\nYuklangan: <b>{esc(name)}</b>" if name else "")), markup(nav, cancel)
    if key == "materials":
        names = ", ".join(esc(m["name"], 40) for m in project["materials"]) or "—"
        return (text + "\n\nFayllarni bittadan yuboring (PDF, DOCX, XLSX, CSV, TXT). Tugatgach «✅ Tayyor» ni bosing."
                f"\n\nYuklangan: {names}"), markup(nav, cancel)
    rows = [nav, cancel]
    if key == "topic":
        rows.insert(0, [Button(text="💡 Mavzu taklif qilish", callback_data=cb("topics", item_id))])
    return text + f"\n\n✍️ Yozing. <i>Masalan: {example}</i>" + now, markup(*rows)


async def show_field(message, state: FSMContext, item_id, key, mode="wizard", edit=None):
    _, project = storage.load(item_id)
    await state.set_state(Dissertatsiya.upload if key in ("method", "materials") else Dissertatsiya.field)
    await state.update_data(dis_id=item_id, dis_field=key, dis_mode=mode)
    text, keyboard = field_prompt(item_id, key, project, mode)
    await send(message, text, keyboard, edit)


async def after_field(message, state: FSMContext, item_id, key, edit=None):
    data = await state.get_data()
    index = KEYS.index(key)
    if data.get("dis_mode") == "wizard" and index + 1 < len(KEYS):
        await show_field(message, state, item_id, KEYS[index + 1], "wizard", edit)
    else:
        await state.set_state(None)
        await show_summary(message, item_id, edit)


@router.message(Dissertatsiya.field, plain_text)
async def field_text(message: Message, state: FSMContext):
    data = await state.get_data()
    key, item_id = data.get("dis_field"), data.get("dis_id")
    if not item_id or key not in KEYS:
        await state.set_state(None)
        return
    value = " ".join(message.text.split())
    if key == "pages":
        if not value.isdecimal() or not DISS_PAGES_MIN <= int(value) <= DISS_PAGES_MAX:
            await message.answer(f"⚠️ {DISS_PAGES_MIN} dan {DISS_PAGES_MAX} gacha son yozing yoki tugmani bosing.")
            return
        value = int(value)
    elif key == "lang":
        await message.answer("Tilni tugma orqali tanlang 👆")
        return
    elif key in ("topic", "direction") and len(value) < 5:
        await message.answer("⚠️ Kamida 5 belgi yozing:")
        return
    elif len(value) > MAX_LEN.get(key, 200):
        await message.answer(f"⚠️ {MAX_LEN.get(key, 200)} belgidan oshmasin. Qayta yozing:")
        return
    service.save_info(item_id, {key: value})
    await after_field(message, state, item_id, key)


@router.message(Dissertatsiya.upload, F.document)
async def upload_file(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    item_id, key = data.get("dis_id"), data.get("dis_field")
    document = message.document
    if document.file_size and document.file_size > 20 * 1024 * 1024:
        await message.answer("⚠️ Fayl 20 MB dan katta. Kichikroq faylni yoki ilova orqali yuklang.")
        return
    try:
        content = (await bot.download(document.file_id)).getvalue()
        service.save_file(item_id, content, document.file_name or "fayl", "method" if key == "method" else "material")
    except DissError as e:
        await message.answer(f"⚠️ {html.escape(str(e))}")
        return
    except TelegramAPIError:
        await message.answer("⚠️ Faylni olib bo'lmadi. Qayta yuboring.")
        return
    if key == "method":
        await message.answer("✅ Metodik qo'llanma saqlandi — reja tuzishda AI uni tahlil qiladi.")
        await after_field(message, state, item_id, key)
    else:
        await message.answer("✅ Material saqlandi. Yana yuboring yoki «✅ Tayyor» ni bosing.")
        await show_field(message, state, item_id, "materials", data.get("dis_mode") or "wizard")


@router.message(Dissertatsiya.upload)
async def upload_wrong(message: Message):
    await message.answer("📎 Faylni <b>hujjat</b> sifatida yuboring yoki pastdagi tugmalardan birini bosing.")


@router.message(Dissertatsiya.field)
async def field_wrong(message: Message):
    await message.answer("Matn ko'rinishida yozing ✍️ yoki tugmalardan birini bosing.")


@router.callback_query(F.data.startswith("dis:cancel:"))
async def cancel(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await callback.answer("Bekor qilindi")
    with suppress(TelegramBadRequest):
        await callback.message.edit_text("❌ To'xtatildi. Hamma ma'lumotlar saqlangan — «🔬 Dissertatsiya» orqali davom ettirasiz.")


@router.callback_query(F.data.startswith("dis:field:"))
async def field_button(callback: CallbackQuery, state: FSMContext):
    found = owned(callback)
    if not found or found[1] not in KEYS:
        await callback.answer("Topilmadi", show_alert=True)
        return
    data = await state.get_data()
    await show_field(callback.message, state, found[0], found[1], data.get("dis_mode") or "edit", callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("dis:edit:"))
async def edit_field(callback: CallbackQuery, state: FSMContext):
    found = owned(callback)
    if not found or found[1] not in KEYS:
        await callback.answer("Topilmadi", show_alert=True)
        return
    if found[3]["plan"]["approved"] and found[1] in ("pages", "lang", "method"):
        await callback.answer("Reja tasdiqlangan — til, hajm va qo'llanmani endi o'zgartirib bo'lmaydi.", show_alert=True)
        return
    await show_field(callback.message, state, found[0], found[1], "edit", callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("dis:skip:"))
async def skip_field(callback: CallbackQuery, state: FSMContext):
    found = owned(callback)
    if not found or found[1] not in KEYS:
        await callback.answer()
        return
    await callback.answer()
    await after_field(callback.message, state, found[0], found[1], callback.message)


@router.callback_query(F.data.startswith("dis:set:"))
async def set_choice(callback: CallbackQuery, state: FSMContext):
    found = owned(callback)
    if not found or "=" not in found[1]:
        await callback.answer()
        return
    key, value = found[1].split("=", 1)
    if key == "lang" and value in LANGUAGES:
        service.save_info(found[0], {"lang": value})
    elif key == "pages" and value.isdecimal() and DISS_PAGES_MIN <= int(value) <= DISS_PAGES_MAX:
        service.save_info(found[0], {"pages": int(value)})
    else:
        await callback.answer()
        return
    await callback.answer("Saqlandi ✅")
    await after_field(callback.message, state, found[0], key, callback.message)


# ===== Mavzu takliflari =====
@router.callback_query(F.data.startswith("dis:topics:"))
async def topics_button(callback: CallbackQuery, state: FSMContext):
    found = owned(callback)
    if not found:
        await callback.answer("Topilmadi", show_alert=True)
        return
    item_id = found[0]
    if await guarded(callback, item_id, "Mavzular tayyorlanmoqda...", lambda: service.suggest_topics(item_id, callback.from_user.id)):
        _, project = storage.load(item_id)
        rows = [[Button(text=f"{i}. {t['title'][:60]}", callback_data=cb("pick", item_id, i - 1))]
                for i, t in enumerate(project["suggestions"], 1)]
        rows.append([Button(text="✍️ O'zim yozaman", callback_data=cb("field", item_id, "topic"))])
        text = "💡 <b>Mavzu takliflari</b>\n\n" + "\n\n".join(
            f"<b>{i}. {esc(t['title'])}</b>\n<i>{esc(t['why'])}</i>" for i, t in enumerate(project["suggestions"], 1))
        await callback.message.answer(text[:4000] + "\n\nBittasini tanlang (keyin tahrirlash mumkin) 👇",
                                      reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("dis:pick:"))
async def pick_topic(callback: CallbackQuery, state: FSMContext):
    found = owned(callback)
    if not found or not found[1].isdecimal() or int(found[1]) >= len(found[3]["suggestions"]):
        await callback.answer("Topilmadi", show_alert=True)
        return
    service.save_info(found[0], {"topic": found[3]["suggestions"][int(found[1])]["title"]})
    await callback.answer("Mavzu tanlandi ✅")
    await state.update_data(dis_mode=(await state.get_data()).get("dis_mode") or "wizard")
    await after_field(callback.message, state, found[0], "topic", callback.message)


# ===== Umumiy ko'rinish =====
def method_line(project):
    method = project["method"]
    if method["status"] == "analyzed":
        return f"📘 Metodika: <b>tahlil qilingan</b> ({len(method['found'])} ta talab)"
    if method["status"] == "uploaded":
        return f"📘 Metodika: <b>{esc(method['name'], 60)}</b> (reja tuzishda tahlil qilinadi)"
    return "📘 Metodika: yuklanmagan — namunaviy talablar"


async def show_summary(message, item_id, edit=None):
    _, project = storage.load(item_id)
    info = project["info"]
    lines = [f"📑 Turi: <b>{DISS_TYPES.get(project['kind'], DISS_TYPES['other'])['name']}</b>"]
    for key in KEYS:
        if key in ("method", "materials"):
            continue
        value = LANGUAGES.get(info["lang"]) if key == "lang" else f"{info['pages']} bet" if key == "pages" else info.get(key)
        lines.append(f"{FIELD[key][2]}: <b>{esc(value, 160) or '—'}</b>")
    lines.append(method_line(project))
    lines.append(f"📎 Materiallar: <b>{len(project['materials'])} ta</b>")
    price = service.price_for(message.chat.id, info["pages"])
    ready = len(info.get("topic") or "") >= 5 and len(info.get("direction") or "") >= 5
    text = ("🔬 <b>Dissertatsiya — ma'lumotlar</b>\n\n" + "\n".join(lines) +
            f"\n\n💰 Narxi: <b>{money(price) if price else 'bepul (admin)'}</b> — reja tasdiqlanganda yechiladi.\n\n"
            + ("Keyingi qadam — reja (bepul)." if ready else "⚠️ Reja uchun yo'nalish va mavzu kerak."))
    plan_ready = bool(project["plan"]["chapters"])
    rows = [
        [Button(text="📋 Rejaga o'tish" if plan_ready else "📋 Reja tuzish (bepul)",
                callback_data=cb("showplan" if plan_ready else "plan", item_id))] if ready or plan_ready else None,
        [Button(text="✏️ Ma'lumotlarni tahrirlash", callback_data=cb("fields", item_id))],
        [app_button(item_id)] if app_button(item_id) else None,
        [Button(text="❌ Yopish", callback_data=cb("cancel", item_id))],
    ]
    await send(message, text[:4000], InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r]), edit)


@router.callback_query(F.data.startswith("dis:summary:"))
async def summary_button(callback: CallbackQuery, state: FSMContext):
    found = owned(callback)
    if not found:
        await callback.answer("Topilmadi", show_alert=True)
        return
    await state.set_state(None)
    await show_summary(callback.message, found[0], callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("dis:fields:"))
async def fields_menu(callback: CallbackQuery):
    found = owned(callback)
    if not found:
        await callback.answer()
        return
    buttons = [Button(text=FIELD[k][2], callback_data=cb("edit", found[0], k)) for k in KEYS]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.insert(0, [Button(text="📑 Dissertatsiya turi", callback_data=cb("kindmenu", found[0]))])
    rows.append([Button(text="⬅️ Orqaga", callback_data=cb("summary", found[0]))])
    await send(callback.message, "✏️ Qaysi ma'lumotni o'zgartirasiz?", InlineKeyboardMarkup(inline_keyboard=rows), callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("dis:kindmenu:"))
async def kind_menu(callback: CallbackQuery):
    found = owned(callback)
    if not found:
        await callback.answer()
        return
    rows = [[Button(text=f"{'✅ ' if found[3]['kind'] == k else ''}{t['name']}", callback_data=f"dis:kind:{found[0]}:{k}")]
            for k, t in DISS_TYPES.items()]
    rows.append([Button(text="⬅️ Orqaga", callback_data=cb("summary", found[0]))])
    await send(callback.message, "📑 Dissertatsiya turi:", InlineKeyboardMarkup(inline_keyboard=rows), callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("dis:open:"))
async def open_item(callback: CallbackQuery, state: FSMContext):
    found = owned(callback)
    if not found:
        await callback.answer("Topilmadi", show_alert=True)
        return
    await callback.answer()
    await state.set_state(None)
    await show_stage(callback.message, found[0], callback.message)


async def show_stage(message, item_id, edit=None):
    _, project = storage.load(item_id)
    if not project["plan"]["chapters"]:
        await show_summary(message, item_id, edit)
    elif not project["plan"]["approved"]:
        await show_plan(message, item_id, edit)
    elif not all(service.has_text(project, k) for k in service.parts(project)):
        await show_write_all(message, item_id, edit)
    else:
        key = service.current_part(project)
        if key is None:
            await show_done(message, item_id, edit)
        else:
            await show_part(message, item_id, key, edit)


# ===== AI amallari (umumiy himoya) =====
async def guarded(callback: CallbackQuery, item_id, title, factory, hint="Odatda 15–60 soniya."):
    if service.busy(item_id):
        with suppress(TelegramBadRequest):
            await callback.answer("⏳ Hozir tayyorlanmoqda, biroz kuting.", show_alert=True)
        return False
    with suppress(TelegramBadRequest):
        await callback.answer("🚀 Boshladik!")
    async with service.lock(item_id):
        # title — matn yoki funksiya (jarayon davomida o'zgaradigan sarlavha, masalan «3/6 · II bob yozilmoqda»)
        progress = await callback.message.answer(f"⏳ <b>{html.escape(title()) if callable(title) else title}</b>")
        animation = asyncio.create_task(animate_live(progress, title, hint) if callable(title)
                                        else animate(progress, title, PROGRESS, hint))
        try:
            await factory()
            return True
        except DissError as e:
            keyboard = markup([Button(text="➕ Hisobni to'ldirish", callback_data="wallet_topup")],
                              [Button(text="🔄 Qayta urinish", callback_data=cb("approve", item_id))]) if e.need else None
            await callback.message.answer(f"⚠️ {html.escape(str(e))}", reply_markup=keyboard)
        except GenerationError as e:
            await callback.message.answer(f"😕 {html.escape(str(e))}")
        except Exception:
            logging.exception("Dissertatsiyada kutilmagan xato")
            await callback.message.answer("😕 Kutilmagan xato yuz berdi. Ishingiz saqlangan — qayta urinib ko'ring.")
        finally:
            animation.cancel()
            with suppress(TelegramBadRequest):
                await progress.delete()
    return False


# ===== Reja =====
def plan_lines(project):
    lines = []
    for i, chapter in enumerate(project["plan"]["chapters"]):
        lines.append(f"<b>{service.ROMAN[i]} BOB. {esc(chapter['title'], 160)}</b>")
        lines += [f"   {i + 1}.{j}. {esc(s['title'], 160)}" for j, s in enumerate(chapter["sections"], 1)]
    return "\n".join(lines)


async def show_plan(message, item_id, edit=None):
    _, project = storage.load(item_id)
    price = service.price_for(message.chat.id, project["info"]["pages"])
    note = ("✅ Metodik qo'llanma talablari asosida tuzildi." if project["method"]["status"] == "analyzed" else
            "ℹ️ Metodik qo'llanma yuklanmagan — bu <b>namunaviy</b> tuzilma (tanlangan tur uchun keng tarqalgan).")
    text = (f"📋 <b>Dissertatsiya rejasi</b>\n📝 {esc(project['info']['topic'])}\n\n"
            f"ANNOTATSIYA\nKIRISH\n{plan_lines(project)}\nXULOSA\nFOYDALANILGAN ADABIYOTLAR\nILOVALAR\n\n{note}\n\n"
            f"💰 Tasdiqlansangiz <b>{money(price) if price else 'bepul (admin)'}</b> yechiladi va yozish boshlanadi.\n"
            f"👛 Balansingiz: <b>{money(get_balance(message.chat.id))}</b>\n\n"
            "✏️ Bob va paragraflarni o'zgartirish, qo'shish, tartibini almashtirish — ilovada.")
    rows = [[Button(text=f"✅ Tasdiqlash — {money(price)}" if price else "✅ Tasdiqlash", callback_data=cb("approve", item_id))],
            [app_button(item_id, "✏️ Rejani ilovada tahrirlash")] if app_button(item_id) else None,
            [Button(text="🔄 Qayta tuzish", callback_data=cb("plan", item_id)),
             Button(text="⬅️ Ma'lumotlar", callback_data=cb("summary", item_id))]]
    await send(message, text[:4000], InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r]), edit)


@router.callback_query(F.data.startswith("dis:showplan:"))
async def showplan_button(callback: CallbackQuery):
    found = owned(callback)
    if not found:
        await callback.answer("Topilmadi", show_alert=True)
        return
    await callback.answer()
    await (show_plan(callback.message, found[0], callback.message) if not found[3]["plan"]["approved"]
           else show_stage(callback.message, found[0], callback.message))


@router.callback_query(F.data.startswith("dis:plan:"))
async def plan_button(callback: CallbackQuery):
    found = owned(callback)
    if not found:
        await callback.answer("Topilmadi", show_alert=True)
        return
    item_id, user_id = found[0], callback.from_user.id
    if await guarded(callback, item_id, "Reja tuzilmoqda...", lambda: service.make_plan(item_id, user_id)):
        await show_plan(callback.message, item_id)


@router.callback_query(F.data.startswith("dis:approve:"))
async def approve_button(callback: CallbackQuery):
    found = owned(callback)
    if not found:
        await callback.answer("Topilmadi", show_alert=True)
        return
    item_id, user_id = found[0], callback.from_user.id
    if found[3]["plan"]["approved"]:
        await callback.answer()
        await show_stage(callback.message, item_id)
        return
    if await guarded(callback, item_id, "Reja tasdiqlanmoqda, ilmiy manbalar qidirilmoqda...",
                     lambda: service.approve_plan(item_id, user_id)):
        with suppress(TelegramBadRequest):
            await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("✅ Reja tasdiqlandi, haqiqiy manbalar topildi. Endi butun dissertatsiyani yozamiz.")
        await write_all(callback, item_id)


# ===== Qismlar =====
def part_preview(project, key, limit=2600):
    part = service.part_of(project, key)
    if key == "intro":
        lines = [f"<b>{esc(i['label'])}.</b> {esc(i['paragraphs'][0], 220)}" for i in part["items"]]
    elif key in ("conclusion", "annotation"):
        lines = [esc(p, 400) for p in part["paragraphs"][:4]]
        if key == "annotation" and part.get("keywords"):
            lines.append("<b>Kalit so'zlar:</b> " + esc(", ".join(part["keywords"])))
    else:
        ci = int(key[8:])
        lines = [f"<b>{ci + 1}.{si}. {esc(s['title'], 120)}</b> ({len(s['paragraphs'])} xatboshi)\n"
                 f"{esc(s['paragraphs'][0] if s['paragraphs'] else '', 260)}" for si, s in enumerate(part["sections"], 1)]
        if part.get("figures"):
            kinds = {"scheme": "sxema", "illustration": "rasm", "table": "jadval", "chart": "grafik"}
            lines.append("📊 " + ", ".join(f"{kinds.get(f['kind'], f['kind'])}: {esc(f['caption'], 50)}" for f in part["figures"]))
    text = "\n\n".join(lines)
    return text if len(text) <= limit else text[:limit - 1] + "…"


async def show_part(message, item_id, key, edit=None):
    _, project = storage.load(item_id)
    keys = service.parts(project)
    name = esc(service.part_name(project, key), 160)
    position = f"{keys.index(key) + 1}/{len(keys)}"
    if not service.has_text(project, key):
        await show_write_all(message, item_id, edit)
        return
    approved = service.part_of(project, key).get("status") == "approved"
    text = (f"🔬 <b>{name}</b> ({position}){' — ✅ tayyor' if approved else ''}\n\n{part_preview(project, key)}\n\n"
            "✏️ To'liq matnni ilovada (telefonda ham) o'qib, xatboshilarni tahrirlash, kengaytirish, qisqartirish, "
            "imlosini tuzatish va oldingi versiyaga qaytish mumkin. «🔄 Qayta yozish» — shu qismni AI qaytadan yozadi.")
    rows = [[Button(text="✅ Tasdiqlash va davom etish", callback_data=cb("ok", item_id, key))] if not approved else None,
            [app_button(item_id, "✏️ Tahrirlash (ilovada)")] if app_button(item_id) else None,
            [Button(text="🔄 Qayta yozish", callback_data=cb("rewrite", item_id, key)),
             Button(text="📄 Fayl olish", callback_data=cb("export", item_id, "docx"))],
            [Button(text="⬅️ Barcha qismlar", callback_data=cb("open", item_id))]]
    await send(message, text[:4000], InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r]), edit)


async def show_write_all(message, item_id, edit=None):
    """Reja tasdiqlangan, lekin ish (to'liq) yozilmagan — bitta tugma bilan hammasi yoziladi."""
    _, project = storage.load(item_id)
    keys = service.parts(project)
    written = sum(service.has_text(project, k) for k in keys)
    rows = [[Button(text="✍️ Hammasini yozish" if not written else "✍️ Qolganini yozish", callback_data=cb("writeall", item_id))],
            [app_button(item_id)] if app_button(item_id) else None]
    await send(
        message,
        f"🔬 <b>{esc(project['info']['topic'])}</b>\n\n"
        + (f"✅ Yozilgan: {written}/{len(keys)} qism.\n\n" if written else "")
        + "Bitta tugma bilan kirish, barcha boblar (rasm, sxema, grafik va jadvallar bilan), umumiy xulosa va "
        "annotatsiya ketma-ket yoziladi, sifat nazorati o'tkaziladi va tayyor DOCX fayl shu chatga keladi. "
        "Keyin istalgan qismni tahrirlash yoki qayta yozdirish mumkin.",
        InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r]), edit,
    )


async def write_all(callback: CallbackQuery, item_id):
    """Butun dissertatsiyani yozadi, faylni chatga yuboradi va yakuniy menyuni ko'rsatadi."""
    _, project = storage.load(item_id)
    status = {"text": "Dissertatsiya yozilmoqda..."}

    async def on_part(name, n, total):
        status["text"] = ("Sifat nazorati o'tkazilmoqda..." if name == "Sifat nazorati"
                          else f"{n}/{total} · {name[:80]} yozilmoqda...")

    async def job():
        await service.generate_all(item_id, callback.from_user.id, on_part)
        status["text"] = "Fayl tayyorlanmoqda va tekshirilmoqda..."
        await service.export(callback.bot, item_id, callback.from_user.id)

    total = len(service.parts(project))
    hint = f"Butun ish ({total} qism) odatda {total}–{total * 2} daqiqada yoziladi. Shu orada botdan foydalanishingiz mumkin."
    if await guarded(callback, item_id, lambda: status["text"], job, hint):
        await show_done(callback.message, item_id)
    elif not service.busy(item_id):
        await show_stage(callback.message, item_id)


@router.callback_query(F.data.startswith("dis:writeall:"))
async def write_all_button(callback: CallbackQuery):
    found = owned(callback)
    if not found:
        await callback.answer("Topilmadi", show_alert=True)
        return
    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(reply_markup=None)
    await write_all(callback, found[0])


@router.callback_query(F.data.startswith("dis:view:"))
async def view_button(callback: CallbackQuery):
    found = owned(callback)
    if not found or not found[1]:
        await callback.answer("Topilmadi", show_alert=True)
        return
    try:
        service.part_of(found[3], found[1])
    except DissError:
        await callback.answer("Topilmadi", show_alert=True)
        return
    await callback.answer()
    await show_part(callback.message, found[0], found[1])


async def write_part(callback: CallbackQuery, item_id, key, again=False):
    _, project = storage.load(item_id)
    hint = "Bob yozilishi odatda 40–120 soniya oladi." if key.startswith("chapter") else "Odatda 20–60 soniya."
    if await guarded(callback, item_id, f"{service.part_name(project, key)[:80]} yozilmoqda...",
                     lambda: service.generate(item_id, callback.from_user.id, key, again), hint):
        await show_part(callback.message, item_id, key)


@router.callback_query(F.data.startswith("dis:write:"))
async def write_button(callback: CallbackQuery):
    found = owned(callback)
    if not found or not found[1]:
        await callback.answer("Topilmadi", show_alert=True)
        return
    await write_part(callback, found[0], found[1])


@router.callback_query(F.data.startswith("dis:rewrite:"))
async def rewrite_button(callback: CallbackQuery):
    found = owned(callback)
    if not found or not found[1]:
        await callback.answer("Topilmadi", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer(
        f"🔄 <b>{esc(service.part_name(found[3], found[1]))}</b> qaytadan yozilsinmi?\n\n"
        "Hozirgi matn tarixga saqlanadi — ilovada «Oldingi versiyaga qaytish» mumkin.",
        reply_markup=markup([Button(text="✅ Ha", callback_data=cb("rewrite_yes", found[0], found[1]))],
                            [Button(text="❌ Yo'q", callback_data=cb("open", found[0]))]))


@router.callback_query(F.data.startswith("dis:rewrite_yes:"))
async def rewrite_yes(callback: CallbackQuery):
    found = owned(callback)
    if not found or not found[1]:
        await callback.answer("Topilmadi", show_alert=True)
        return
    with suppress(TelegramBadRequest):
        await callback.message.delete()
    await write_part(callback, found[0], found[1], again=True)


@router.callback_query(F.data.startswith("dis:ok:"))
async def approve_part(callback: CallbackQuery):
    found = owned(callback)
    if not found or not found[1]:
        await callback.answer("Topilmadi", show_alert=True)
        return
    item_id = found[0]
    try:
        service.approve_part(item_id, found[1])
    except DissError as e:
        await callback.answer(str(e), show_alert=True)
        return
    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(reply_markup=None)
    _, project = storage.load(item_id)
    nxt = service.current_part(project)
    await callback.answer("Tasdiqlandi ✅")
    if nxt is None:
        await show_done(callback.message, item_id)
    elif service.has_text(project, nxt):
        await show_part(callback.message, item_id, nxt)
    else:
        await show_write_all(callback.message, item_id)


# ===== Sifat nazorati va fayl =====
ICON = {"ok": "✅", "warn": "⚠️", "error": "❌", "skip": "➖"}


async def show_done(message, item_id, edit=None):
    _, project = storage.load(item_id)
    quality = project["quality"]
    text = (f"🎉 <b>Dissertatsiya tayyor!</b>\n\n📝 {esc(project['info']['topic'])}\n"
            f"📄 ~{round(service.word_count(project) / 280) + 7} bet  ·  📚 Manbalar: {len(project['sources'])} ta\n\n"
            "✏️ Matnni «Tahrirlash» orqali (telefonda ham) o'zgartirish, «👁» tugmalari bilan har bir qismni ko'rib, "
            "kerak bo'lsa qayta yozdirish mumkin. Keyin faylni qayta oling.\n\n")
    if quality["checks"]:
        text += f"🔍 <b>Sifat nazorati</b> ({quality['at']}):\n" + "\n".join(
            f"{ICON[c['status']]} {esc(c['label'])}: {esc(c['detail'], 180)}" for c in quality["checks"])
        if quality["review"]:
            text += "\n\n🧐 <b>Mazmuniy muvofiqlik</b>:\n" + "\n".join(
                f"• <b>{esc(r['part'], 60)}</b>: {esc(r['problem'], 200)}" for r in quality["review"][:6])
        elif quality["at"]:
            text += "\n\n🧐 Mazmuniy muvofiqlik: jiddiy nomuvofiqlik topilmadi."
    else:
        text += "Faylni olishdan oldin sifat nazoratini o'tkazing: takrorlar, iqtiboslar, manbalar, hajm, kirish va xulosa mosligi."
    rows = [[Button(text="🔍 Sifat nazorati" if not quality["checks"] else "🔍 Qayta tekshirish", callback_data=cb("quality", item_id))],
            [Button(text="📄 DOCX olish", callback_data=cb("export", item_id, "docx"))]
            + ([Button(text="📕 PDF olish", callback_data=cb("export", item_id, "pdf"))] if PDF_AVAILABLE else []),
            [app_button(item_id, "✏️ Tahrirlash (ilovada)")] if app_button(item_id) else None]
    views = [Button(text=f"👁 {service.part_name(project, k).split(':')[0]}", callback_data=cb("view", item_id, k))
             for k in service.parts(project)]
    rows += [views[i:i + 3] for i in range(0, len(views), 3)]
    await send(message, text[:4000], InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r]), edit)


@router.callback_query(F.data.startswith("dis:quality:"))
async def quality_button(callback: CallbackQuery):
    found = owned(callback)
    if not found:
        await callback.answer("Topilmadi", show_alert=True)
        return
    if await guarded(callback, found[0], "Dissertatsiya tekshirilmoqda...",
                     lambda: service.check_quality(found[0], callback.from_user.id)):
        await show_done(callback.message, found[0])


@router.callback_query(F.data.startswith("dis:export:"))
async def export_button(callback: CallbackQuery, bot: Bot):
    found = owned(callback)
    if not found:
        await callback.answer("Topilmadi", show_alert=True)
        return
    await guarded(callback, found[0], "Fayl tayyorlanmoqda va tekshirilmoqda...",
                  lambda: service.export(bot, found[0], callback.from_user.id, "pdf" if found[1] == "pdf" else "docx"),
                  "Odatda 5–40 soniya.")


# Fayl ostidagi «🎨 Boshqa dizaynda olish» (umumiy «eskirgan tugma» handleridan oldin bo'lishi shart)
doc_design.register(router, "dis", service, owned, DissError)


@router.callback_query(F.data.startswith("dis:"))
async def stale(callback: CallbackQuery):
    await callback.answer("Bu tugma eskirgan. «🔬 Dissertatsiya» orqali davom ettiring.", show_alert=True)
