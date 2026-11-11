import asyncio
import html
import logging
import re
import time
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from admins import admin_ids, has_perm
from config import (
    AI_CONCURRENCY, FIXED_SLIDES, IMAGES_MAX, PLAN_MAX, PLAN_MIN, SLIDE_PRICE, SLIDES_MAX, image_count,
    image_plan_text, money,
    presentation_price,
)
from converter import PDF_AVAILABLE, ConvertError, to_pdf
from database import add_document, add_presentation, charge_hold, get_balance, refund_hold, save_user, settle_hold
from handlers.start import show, welcome_text
from keyboards import (
    FORMAT_NAMES,
    format_menu,
    pres_author_menu,
    pres_back_row,
    pres_confirm_menu,
    pres_lang_menu,
    pres_plans_menu,
    pres_redesign_menu,
    pres_result_menu,
    pres_slides_menu,
    pres_theme_menu,
    pres_topic_menu,
)
from presentation import genimage
from presentation.ai import LANGUAGES, GenerationError, generate_content, split_slides
from presentation.builder import build_pptx
from presentation.preview import themes_collage
from presentation.storage import save_deck
from presentation.themes import THEMES
from states import MakePresentation

router = Router()

# Format qadami faqat PDF yaratish mumkin bo'lsa (LibreOffice o'rnatilgan bo'lsa) ko'rsatiladi
STEPS = ("topic", "plans", "slides", "lang", "theme", "author") + (("format",) if PDF_AVAILABLE else ()) + ("confirm",)
SETTINGS = ("topic", "plans", "slides", "lang", "theme", "author", "fmt")
TOPIC_MIN, TOPIC_MAX, AUTHOR_MAX = 3, 200, 70
PROGRESS = (  # har 5 soniyada keyingisi
    "🧠 Mavzu tahlil qilinmoqda",
    "📋 Reja tuzilmoqda",
    "✍️ Slaydlar matni yozilmoqda",
    "🏞 Mavzuga mos rasmlar tanlanmoqda",
    "🔎 Ma'lumotlar tekshirilmoqda",
    "🎨 Dizayn chizilmoqda",
)
ERRORS = (GenerationError, ConvertError)  # foydalanuvchiga matni ko'rsatiladigan xatolar
# Shablonlarning dizaynlar ro'yxatidagi raqamlari («7–10»)
_template_numbers = [i for i, theme in enumerate(THEMES.values(), 1) if theme.get("style")]
TEMPLATE_NUMBERS = f"{_template_numbers[0]}–{_template_numbers[-1]}" if _template_numbers else ""

ai_slots = asyncio.Semaphore(AI_CONCURRENCY)
generating = set()  # hozir buyurtmasi tayyorlanayotgan foydalanuvchilar
last_decks = {}  # user_id -> oxirgi taqdimot (boshqa dizaynda qayta yasash uchun; rasmlar bilan — xotira tejaladi)
LAST_DECKS_LIMIT = 50
collage_file_id = None  # dizaynlar rasmi bir marta yuklanadi, keyin file_id orqali yuboriladi
# Admin buyrug'i yoki noma'lum /buyruq mavzu/muallif sifatida qabul qilinib ketmasligi uchun
plain_text = F.text & ~F.text.startswith("/")


def next_step(step):
    return STEPS[STEPS.index(step) + 1]


def prev_step(step):
    return STEPS[STEPS.index(step) - 1]


# ===== Narx =====
def price_for(user_id, slides):
    return 0 if has_perm(user_id, "free") else presentation_price(slides)


def confirm_markup(user_id, slides):
    price = price_for(user_id, slides)
    return pres_confirm_menu(price, price - get_balance(user_id), prev_step("confirm"))


# ===== Qadamlar ekrani =====
def summary(data):
    lines = []
    if data.get("topic"):
        lines.append(f"📝 Mavzu: <b>{html.escape(data['topic'])}</b>")
    if data.get("plans"):
        lines.append(f"📋 Reja: <b>{data['plans']} ta</b>")
    if data.get("slides"):
        lines.append(f"🖼 Slaydlar: <b>{data['slides']} ta</b> (rasmlar: {image_count(data['slides'])} ta)")
    if data.get("lang"):
        lines.append(f"🌐 Til: <b>{LANGUAGES[data['lang']]}</b>")
    if data.get("theme"):
        lines.append(f"🎨 Dizayn: <b>{THEMES[data['theme']]['name']}</b>")
    if "author" in data:
        lines.append(f"👤 Muallif: <b>{html.escape(data['author']) if data['author'] else '—'}</b>")
    if PDF_AVAILABLE and data.get("fmt_chosen"):
        lines.append(f"📁 Format: <b>{FORMAT_NAMES[data['fmt']]}</b>")
    return "\n".join(lines)


def screen(step, data, user_id):
    number = STEPS.index(step) + 1
    progress = "●" * number + "○" * (len(STEPS) - number)
    head = f"📊 <b>Prezentatsiya yaratish</b>\n<code>{progress}</code>  {number}/{len(STEPS)}\n\n"
    info = summary(data)
    if info:
        head += info + "\n\n"

    if step == "topic":
        return head + (
            "✍️ Taqdimot <b>mavzusini</b> yozing:\n\n"
            "<i>Masalan: Sun'iy intellektning ta'limdagi o'rni</i>"
        ), pres_topic_menu
    if step == "plans":
        return head + (
            "📋 Taqdimotda nechta <b>reja</b> bo'lsin?\n\n"
            f"💡 Kichik taqdimot kerak bo'lsa: <b>5 slayd</b> uchun 1 ta reja, <b>8 slayd</b> uchun 4 tagacha reja tanlang "
            f"(slaydlar soni kamida «reja + {FIXED_SLIDES}»).\n\n"
            f"Tugmani bosing yoki {PLAN_MIN}–{PLAN_MAX} oralig'ida son yozing."
        ), pres_plans_menu()
    if step == "slides":
        low = data["plans"] + FIXED_SLIDES
        return head + (
            "🖼 Nechta <b>slayd</b> bo'lsin?\n\n"
            f"💰 Har bir slayd — <b>{money(SLIDE_PRICE)}</b>\n"
            f"🏞 Slaydlarga mavzuga mos rasmlar qo'yiladi: {image_plan_text()} va undan ko'pga ham "
            f"{IMAGES_MAX} ta.\n\n"
            f"Kamida <b>{low}</b> ta kerak: muqova, mundarija, reja, har bir rejaga kamida 1 ta slayd va xulosa.\n"
            f"Tugmani bosing yoki {low}–{SLIDES_MAX} oralig'ida son yozing."
        ), pres_slides_menu(data["plans"])
    if step == "lang":
        return head + "🌐 Taqdimot qaysi <b>tilda</b> bo'lsin?", pres_lang_menu()
    if step == "theme":
        return head + (
            "🎨 Rasmdagi <b>dizaynlardan</b> birini tanlang 👇\n\n"
            f"✨ <b>{TEMPLATE_NUMBERS}</b> — shablonlar: o'z maketi bor, rasmlari mavzuga moslab shu uslubda chiziladi."
        ), pres_theme_menu(data.get("theme"))
    if step == "author":
        return head + (
            "👤 Muqovaga yoziladigan <b>muallif</b> ismini yuboring.\n\n"
            "<i>Masalan: Aliyev Vali, 10-«A» sinf o'quvchisi</i>"
        ), pres_author_menu()
    if step == "format":
        return head + (
            "📁 Fayl qaysi <b>formatda</b> bo'lsin?\n\n"
            "📊 <b>PowerPoint</b> — keyin istalgan joyini tahrirlash mumkin\n"
            "📕 <b>PDF</b> — telefon va kompyuterda bir xil ochiladi, tahrirlab bo'lmaydi"
        ), format_menu("pres_fmt:", "pptx", pres_back_row("author"))

    counts = split_slides(data["slides"], data["plans"])
    plan_lines, start = [], FIXED_SLIDES
    for i, n in enumerate(counts, 1):
        plan_lines.append(f"   {start}–{start + n - 1}-slayd → {i}-reja" if n > 1 else f"   {start}-slayd → {i}-reja")
        start += n
    price, balance = price_for(user_id, data["slides"]), get_balance(user_id)
    if balance >= price:
        payment = "Hammasi to'g'rimi? Unda yaratamiz 🚀"
    else:
        payment = (
            f"💳 Balansingizda yetarli emas — yana <b>{money(price - balance)}</b> kerak.\n\n"
            "«To'lash va olish» ni bosing: shu summani kartaga o'tkazasiz va chekni yuborasiz. "
            "Admin tasdiqlagach, taqdimot <b>avtomatik tayyorlanib</b>, shu chatga keladi."
        )
    return head + (
        "📐 <b>Tuzilma:</b>\n"
        "   1-slayd → muqova\n"
        "   2-slayd → mundarija\n"
        "   3-slayd → reja\n"
        + "\n".join(plan_lines) + "\n"
        f"   {data['slides']}-slayd → xulosa\n\n"
        f"💰 Narxi: <b>{money(price) if price else 'bepul (admin)'}</b>\n"
        f"👛 Balansingiz: <b>{money(balance)}</b>\n\n"
        f"{payment}"
    ), confirm_markup(user_id, data["slides"])


async def send_collage(bot: Bot, chat_id, caption, markup):
    global collage_file_id
    photo = collage_file_id or BufferedInputFile(themes_collage(), filename="dizaynlar.png")
    sent = await bot.send_photo(chat_id, photo, caption=caption, reply_markup=markup)
    collage_file_id = sent.photo[-1].file_id
    return sent


async def show_step(bot: Bot, chat_id, state: FSMContext, step, edit: Message | None = None):
    """Qadam ekranini ko'rsatadi. Iloji bo'lsa eski xabarni tahrirlaydi, aks holda
    eski xabarni o'chirib yangisini yuboradi — chat toza turadi."""
    await state.set_state(getattr(MakePresentation, step))
    data = await state.get_data()
    text, markup = screen(step, data, chat_id)
    if edit is not None and edit.text and step != "theme":
        try:
            await edit.edit_text(text, reply_markup=markup)
            await state.update_data(wid=edit.message_id)
            return
        except TelegramBadRequest:
            pass
    old_after = data.get("wid") or (edit.message_id if edit else None)
    if step == "theme":
        with suppress(Exception):
            await bot.send_chat_action(chat_id, ChatAction.UPLOAD_PHOTO)
        sent = await send_collage(bot, chat_id, text, markup)
    else:
        sent = await bot.send_message(chat_id, text, reply_markup=markup)
    await state.update_data(wid=sent.message_id)
    # Yangi ekran chiqqandan keyin eskisini o'chiramiz (oldin o'chirilsa, bir necha soniya bo'sh qolardi)
    if old_after:
        with suppress(TelegramBadRequest):
            await bot.delete_message(chat_id, old_after)


# ===== Boshlash va bekor qilish =====
async def begin(state: FSMContext):
    await state.clear()
    await state.update_data(fmt="pptx")


@router.callback_query(F.data == "pres")
async def pres_start(callback: CallbackQuery, state: FSMContext, bot: Bot):
    save_user(callback.from_user)
    await begin(state)
    # Tayyor fayl ostidagi tugma bosilsa — faylga tegmaymiz, yangi xabar ochamiz
    edit = callback.message if callback.message.text else None
    await show_step(bot, callback.message.chat.id, state, "topic", edit)
    await callback.answer()


@router.message(Command("taqdimot"))
async def pres_command(message: Message, state: FSMContext, bot: Bot):
    save_user(message.from_user)
    await begin(state)
    await show_step(bot, message.chat.id, state, "topic")


@router.callback_query(F.data == "pres_resume")
async def pres_resume(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Eski xabarlardagi tugma: saqlangan taqdimotga qaytaradi; saqlangani bo'lmasa — yangisini boshlaydi."""
    data = await state.get_data()
    if all(data.get(key) is not None for key in SETTINGS):
        await show_step(bot, callback.message.chat.id, state, "confirm")
        await callback.answer()
    else:
        await pres_start(callback, state, bot)


@router.callback_query(F.data == "pres_cancel")
async def pres_cancel(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.clear()
    await show(callback, await welcome_text(bot, callback.from_user), None)
    await callback.answer("Bekor qilindi")


async def designs(message: Message, bot: Bot):
    # «🎨 Taqdimot dizaynlari» tugmasi (handlers/menu.py da ulanadi)
    await send_collage(
        bot, message.chat.id,
        "🎨 <b>Mavjud dizaynlar</b>\n\nTaqdimot yaratishda shulardan birini tanlaysiz. "
        "Tayyor taqdimotni keyin istalgan boshqa dizaynga ham o'tkazish mumkin.",
        None,
    )


@router.callback_query(F.data.startswith("pres_back:"), StateFilter(MakePresentation))
async def pres_back(callback: CallbackQuery, state: FSMContext, bot: Bot):
    step = callback.data.split(":", 1)[1]
    if step in STEPS:
        await show_step(bot, callback.message.chat.id, state, step, callback.message)
    await callback.answer()


# ===== 1. Mavzu =====
@router.message(MakePresentation.topic, plain_text)
async def pres_topic(message: Message, state: FSMContext, bot: Bot):
    topic = " ".join(message.text.split())
    if not TOPIC_MIN <= len(topic) <= TOPIC_MAX:
        await message.answer(f"⚠️ Mavzu {TOPIC_MIN}–{TOPIC_MAX} belgi oralig'ida bo'lsin. Qayta yozing:")
        return
    await state.update_data(topic=topic)
    await show_step(bot, message.chat.id, state, "plans")


# ===== 2. Reja soni =====
async def set_plans(bot: Bot, chat_id, state: FSMContext, plans, edit=None):
    data = await state.get_data()
    await state.update_data(plans=plans)
    # Reja ko'paysa, avval tanlangan slaydlar soni yetmay qolishi mumkin
    if data.get("slides") and data["slides"] < plans + FIXED_SLIDES:
        await state.update_data(slides=None)
    await show_step(bot, chat_id, state, "slides", edit)


@router.callback_query(MakePresentation.plans, F.data.startswith("pres_plans:"))
async def pres_plans_button(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await set_plans(bot, callback.message.chat.id, state, int(callback.data.split(":")[1]), callback.message)
    await callback.answer()


@router.message(MakePresentation.plans, F.text)
async def pres_plans_text(message: Message, state: FSMContext, bot: Bot):
    text = message.text.strip()
    if not (text.isdecimal() and PLAN_MIN <= int(text) <= PLAN_MAX):
        await message.answer(f"⚠️ {PLAN_MIN} dan {PLAN_MAX} gacha son yozing yoki tugmani bosing.")
        return
    await set_plans(bot, message.chat.id, state, int(text))


# ===== 3. Slaydlar soni =====
@router.callback_query(MakePresentation.slides, F.data.startswith("pres_slides:"))
async def pres_slides_button(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.update_data(slides=int(callback.data.split(":")[1]))
    await show_step(bot, callback.message.chat.id, state, "lang", callback.message)
    await callback.answer()


@router.message(MakePresentation.slides, F.text)
async def pres_slides_text(message: Message, state: FSMContext, bot: Bot):
    low = (await state.get_data())["plans"] + FIXED_SLIDES
    text = message.text.strip()
    if not (text.isdecimal() and low <= int(text) <= SLIDES_MAX):
        await message.answer(f"⚠️ {low} dan {SLIDES_MAX} gacha son yozing yoki tugmani bosing.")
        return
    await state.update_data(slides=int(text))
    await show_step(bot, message.chat.id, state, "lang")


# ===== 4. Til =====
@router.callback_query(MakePresentation.lang, F.data.startswith("pres_lang:"))
async def pres_lang(callback: CallbackQuery, state: FSMContext, bot: Bot):
    lang = callback.data.split(":")[1]
    # Tugmadagi «soat» darhol yo'qolsin — dizaynlar rasmini yuborish bir necha soniya olishi mumkin
    await callback.answer("🎨 Dizaynlar yuklanmoqda..." if lang in LANGUAGES else None)
    if lang not in LANGUAGES:
        return
    await state.update_data(lang=lang)
    await show_step(bot, callback.message.chat.id, state, "theme", callback.message)


# ===== 5. Dizayn =====
@router.callback_query(MakePresentation.theme, F.data.startswith("pres_theme:"))
async def pres_theme(callback: CallbackQuery, state: FSMContext, bot: Bot):
    theme = callback.data.split(":")[1]
    await callback.answer(THEMES[theme]["name"] if theme in THEMES else None)
    if theme not in THEMES:
        return
    await state.update_data(theme=theme)
    await show_step(bot, callback.message.chat.id, state, "author", callback.message)


# ===== 6. Muallif =====
@router.message(MakePresentation.author, plain_text)
async def pres_author(message: Message, state: FSMContext, bot: Bot):
    author = " ".join(message.text.split())
    if len(author) > AUTHOR_MAX:
        await message.answer(f"⚠️ Muallif ismi {AUTHOR_MAX} belgidan oshmasin. Qayta yozing:")
        return
    await state.update_data(author=author)
    await show_step(bot, message.chat.id, state, next_step("author"))


@router.callback_query(MakePresentation.author, F.data == "pres_author_skip")
async def pres_author_skip(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.update_data(author="")
    await show_step(bot, callback.message.chat.id, state, next_step("author"), callback.message)
    await callback.answer()


# ===== 7. Format (PDF mavjud bo'lsa) =====
@router.callback_query(MakePresentation.format, F.data.startswith("pres_fmt:"))
async def pres_format(callback: CallbackQuery, state: FSMContext, bot: Bot):
    fmt = callback.data.split(":")[1]
    if fmt in ("pptx", "pdf"):
        await state.update_data(fmt=fmt, fmt_chosen=True)
        await show_step(bot, callback.message.chat.id, state, "confirm", callback.message)
    await callback.answer()


@router.message(StateFilter(MakePresentation))
async def pres_wrong_input(message: Message, state: FSMContext):
    step = (await state.get_state()).split(":")[1]
    hints = {
        "topic": "Mavzuni matn ko'rinishida yozing ✍️",
        "plans": "Reja sonini yozing yoki tugmani bosing 👆",
        "slides": "Slaydlar sonini yozing yoki tugmani bosing 👆",
        "author": "Muallif ismini matn ko'rinishida yozing yoki «⏭ O'tkazib yuborish» ni bosing.",
    }
    await message.answer(hints.get(step, "Yuqoridagi tugmalardan birini tanlang 👆"))


# ===== 8. Yaratish =====
def file_name(title, ext="pptx"):
    name = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE).strip()
    name = re.sub(r"\s+", "_", name)[:60] or "hujjat"
    return f"{name}.{ext}"


def result_caption(deck):
    content = deck["content"]
    tip = (
        "💡 PDF fayl istalgan qurilmada bir xil ochiladi." if deck["fmt"] == "pdf"
        else "💡 PowerPoint, Google Slides yoki WPS Office'da ochib, istalgan joyini tahrirlashingiz mumkin."
    )
    return (
        "✅ <b>Taqdimot tayyor!</b>\n\n"
        f"📝 {html.escape(content['title'])}\n"
        f"📋 Reja: <b>{len(content['plans'])} ta</b>  ·  🖼 Slaydlar: <b>{deck['slides']} ta</b>  ·  "
        f"🏞 Rasmlar: <b>{deck['images']} ta</b>\n"
        f"🎨 Dizayn: <b>{THEMES[deck['theme']]['name']}</b>\n\n"
        f"{tip}"
    )


CONFETTI = "5046509860389126442"  # 🎉 Telegram xabar effekti — fayl kelganda ekranga konfetti sochiladi


async def send_celebrating(bot: Bot, chat_id, document, celebrate=True, **kwargs):
    """Tayyor faylni 🎉 effekti bilan yuboradi. Effekt qo'llab-quvvatlanmasa — oddiy yuboriladi."""
    if celebrate:
        try:
            return await bot.send_document(chat_id, document, message_effect_id=CONFETTI, **kwargs)
        except TelegramBadRequest:
            logging.warning("Xabar effekti ishlamadi, fayl oddiy yuboriladi")
    return await bot.send_document(chat_id, document, **kwargs)


async def send_deck(bot: Bot, chat_id, deck, celebrate=True):
    pptx = await asyncio.to_thread(build_pptx, deck["content"], deck["theme"], deck["lang"], deck["author"])
    data = await to_pdf(pptx, "pptx") if deck["fmt"] == "pdf" else pptx
    sent = await send_celebrating(
        bot, chat_id,
        BufferedInputFile(data, filename=file_name(deck["content"]["title"], deck["fmt"])),
        celebrate,
        caption=result_caption(deck),
        reply_markup=pres_result_menu(),
    )
    # «Hujjatlarim» dagi yozuv ID'si (web ilova buyurtmasiga bog'lanadi)
    document_id = add_document(chat_id, "pres", deck["content"]["title"], sent.document.file_id)
    try:
        # Web ilovadagi muharrir uchun loyiha diskka saqlanadi; xato bo'lsa ham fayl allaqachon yetkazilgan
        await asyncio.to_thread(save_deck, document_id, chat_id, deck, pptx)
    except OSError:
        logging.exception("Taqdimot loyihasini saqlab bo'lmadi")
    # Hujjat ID'si faqat yuborilgandan keyin ma'lum — «✏️ Tahrirlash» tugmasi shundan keyin qo'shiladi
    with suppress(TelegramBadRequest):
        await sent.edit_reply_markup(reply_markup=pres_result_menu(document_id))
    return document_id


_last_alert = 0.0


async def alert_admin(bot: Bot, error):
    """Kredit tugashi kabi jiddiy xatolarni barcha adminlarga yuboradi (10 daqiqada ko'pi bilan bir marta)."""
    global _last_alert
    alert = getattr(error, "admin_alert", None)
    if not alert or not admin_ids("stats") or time.monotonic() - _last_alert < 600:
        return
    _last_alert = time.monotonic()
    for admin_id in admin_ids("stats"):
        with suppress(Exception):
            await bot.send_message(admin_id, alert)


def remember_deck(user_id, deck):
    last_decks.pop(user_id, None)
    last_decks[user_id] = deck
    while len(last_decks) > LAST_DECKS_LIMIT:
        last_decks.pop(next(iter(last_decks)))


async def animate(message: Message, title="Taqdimot tayyorlanmoqda...", steps=PROGRESS, hint="Odatda 20–30 soniya vaqt oladi."):
    """AI ishlayotganda progress xabarini jonlantirib turadi."""
    step = 0
    while True:
        bar = "▰" * (step % 10 + 1) + "▱" * (9 - step % 10)
        text = f"⏳ <b>{title}</b>\n\n{steps[min(step, len(steps) - 1)]}\n<code>{bar}</code>\n\n<i>{hint}</i>"
        with suppress(TelegramBadRequest):
            await message.edit_text(text)
        with suppress(Exception):
            await message.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
        step += 1
        await asyncio.sleep(5)


@router.callback_query(MakePresentation.confirm, F.data == "pres_go")
async def pres_generate(callback: CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    if user_id in generating:
        await callback.answer("⏳ Oldingi buyurtmangiz hali tayyorlanmoqda, biroz kuting.", show_alert=True)
        return
    # Ikki marta tez bosilsa ikki marta pul yechilmasligi uchun — birinchi await'dan oldin band qilamiz
    generating.add(user_id)
    try:
        await generate_paid(callback, state, bot)
    finally:
        generating.discard(user_id)


async def generate_paid(callback: CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    data = await state.get_data()
    price = price_for(user_id, data["slides"])
    # Pul AI ishga tushishidan oldin yechiladi; fayl yetkazilmasa (xato yoki bot to'xtab qolsa ham) — qaytariladi
    hold = charge_hold(user_id, price, f"Taqdimot: {data['topic'][:40]}")
    if hold is None:
        await callback.answer("Balans yetarli emas. Avval hisobni to'ldiring 💳", show_alert=True)
        await show_step(bot, callback.message.chat.id, state, "confirm", callback.message)
        return
    await state.clear()
    await callback.answer("🚀 Boshladik!")

    progress = callback.message
    if THEMES[data["theme"]].get("image_style") and genimage.enabled():
        hint = "Rasmlar shablon uslubida chizilmoqda — odatda 40–70 soniya vaqt oladi."
    else:
        hint = "Odatda 30–40 soniya vaqt oladi." if data["slides"] > 30 else "Odatda 20–30 soniya vaqt oladi."
    animation = asyncio.create_task(animate(progress, hint=hint))
    try:
        async with ai_slots:
            # Matn va rasmlar bir vaqtda tayyorlanadi
            content, images = await generate_content(
                data["topic"], data["plans"], data["slides"], data["lang"], image_count(data["slides"]), data["theme"]
            )
        animation.cancel()
        deck = {
            "content": content, "theme": data["theme"], "lang": data["lang"], "author": data.get("author") or "",
            "slides": data["slides"], "fmt": data.get("fmt", "pptx"), "images": images,
        }
        with suppress(TelegramBadRequest):
            await progress.edit_text("🎨 <b>Dizayn chizilmoqda...</b>")
        await send_deck(bot, callback.message.chat.id, deck)
        settle_hold(hold)
    except Exception as e:
        animation.cancel()
        if isinstance(e, ERRORS):
            reason = str(e)
            await alert_admin(bot, e)
        else:
            logging.exception("Taqdimot yaratishda xato")
            reason = "Kutilmagan xato yuz berdi."
        refunded = refund_hold(hold, f"Xato: {data['topic'][:40]}")
        refund_text = f"\n💰 {money(price)} hisobingizga qaytarildi." if refunded else ""
        text, markup = f"😕 {reason}{refund_text}\n\nIltimos, qayta urinib ko'ring.", None
        if await state.get_state() is None:  # foydalanuvchi kutish paytida boshqa amal boshlamagan bo'lsa
            # Tanlovlar saqlanib qoladi — qayta urinish uchun hammasini boshidan kiritish shart emas
            await state.set_data(data)
            await state.set_state(MakePresentation.confirm)
            text = f"😕 {reason}{refund_text}\n\nSozlamalaringiz saqlandi — pastdagi tugma orqali qayta urinib ko'ring."
            markup = confirm_markup(user_id, data["slides"])
        with suppress(TelegramBadRequest):
            await progress.edit_text(text, reply_markup=markup)
        return
    finally:
        animation.cancel()

    remember_deck(user_id, deck)
    add_presentation(user_id, data["topic"], data["slides"], price)
    with suppress(TelegramBadRequest):
        await progress.delete()


# ===== Boshqa dizaynda qayta yasash (AI'siz, darhol) =====
def document_of(data):
    """Tugmadagi hujjat ID'si: «pres_redesign:12» → 12 (eski xabarlarda ID yo'q → None)."""
    last = data.rsplit(":", 1)[-1]
    return int(last) if last.isdecimal() else None


@router.callback_query(F.data.regexp(r"^pres_redesign(:\d+)?$"))
async def pres_redesign(callback: CallbackQuery):
    deck = last_decks.get(callback.from_user.id)
    if not deck:
        await callback.answer("Taqdimot ma'lumoti topilmadi. Yangi taqdimot yarating.", show_alert=True)
        return
    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(
            reply_markup=pres_redesign_menu(deck["theme"], document_of(callback.data))
        )
    await callback.answer("Yangi dizaynni tanlang 🎨")


@router.callback_query(F.data.regexp(r"^pres_result(:\d+)?$"))
async def pres_result(callback: CallbackQuery):
    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(reply_markup=pres_result_menu(document_of(callback.data)))
    await callback.answer()


@router.callback_query(F.data.startswith("pres_retheme:"))
async def pres_retheme(callback: CallbackQuery, bot: Bot):
    theme, document_id = callback.data.split(":")[1], document_of(callback.data)
    deck = last_decks.get(callback.from_user.id)
    if not deck or theme not in THEMES:
        await callback.answer("Taqdimot ma'lumoti topilmadi. Yangi taqdimot yarating.", show_alert=True)
        return
    if theme == deck["theme"]:
        await callback.answer("Bu dizayn allaqachon tanlangan 🙂")
        return
    await callback.answer("🎨 Qayta chizilmoqda...")
    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(reply_markup=None)
    try:
        await send_deck(bot, callback.message.chat.id, {**deck, "theme": theme}, celebrate=False)
    except Exception:
        logging.exception("Taqdimotni qayta dizaynlashda xato")
        # Tugmalarni qaytaramiz — user yana urinib ko'rishi mumkin
        with suppress(TelegramBadRequest):
            await callback.message.edit_reply_markup(reply_markup=pres_result_menu(document_id))
        await bot.send_message(callback.message.chat.id, "😕 Qayta chizishda xato yuz berdi. Iltimos, qayta urinib ko'ring.")
        return
    remember_deck(callback.from_user.id, {**deck, "theme": theme})


@router.callback_query(F.data.startswith("pres_"))
async def pres_stale(callback: CallbackQuery):
    # Eski xabardagi tugma (holat allaqachon o'zgargan)
    await callback.answer("Bu tugma eskirgan. «📊 Prezentatsiya» dan qaytadan boshlang.", show_alert=True)
