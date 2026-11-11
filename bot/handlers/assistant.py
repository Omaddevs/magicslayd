"""🤖 AI yordamchi (bot): ish turi → mavzu → hajm → til → tayyor fayl.
Sayt bilan bir xil servis va limitlar (assistant/service.py)."""
import html
import logging
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from assistant.service import LANGUAGES, TYPES, AssistantError, check_limits, remaining, run, validate
from database import save_user
from handlers.presentation import plain_text
from handlers.start import show
from keyboards import AI_KIND_BUTTONS, ai_kind_menu, ai_lang_menu, ai_size_menu, ai_topic_menu
from states import AiAssistant

router = Router()
busy = set()  # hozir AI yordamchida natija kutayotgan userlar (takroriy bosish ikkinchi so'rov yubormasin)
NOTE = "⚠️ <i>AI tomonidan yaratilgan. Topshirishdan oldin tekshirib chiqing.</i>"


def user_key(user_id):
    return f"tg:{user_id}"


def left_line(user_id):
    return f"🎁 Bugun yana <b>{remaining(user_key(user_id))} ta</b> bepul yaratish mumkin."


def summary(data):
    lines = []
    if data.get("type"):
        lines.append(f"📌 Ish turi: <b>{AI_KIND_BUTTONS[data['type']]}</b>")
    if data.get("topic"):
        lines.append(f"📝 Mavzu: <b>{html.escape(data['topic'])}</b>")
    if data.get("size"):
        lines.append(f"📏 Hajm: <b>{data['size']} {TYPES[data['type']]['unit']}</b>")
    return "\n".join(lines) + ("\n\n" if lines else "")


# ===== Boshlash: pastki menyu tugmasi (handlers/menu.py da ulanadi) yoki /ai =====
@router.message(Command("ai"))
async def ai_start(message: Message, state: FSMContext):
    save_user(message.from_user)
    await state.clear()
    await state.set_state(AiAssistant.kind)
    await message.answer(
        "🤖 <b>AI yordamchi</b>\n\n"
        "Mavzuni yozing — reja va matn bir necha soniyada tayyor!\n"
        f"{left_line(message.from_user.id)}\n\n"
        "Ish turini tanlang 👇",
        reply_markup=ai_kind_menu(),
    )


@router.callback_query(F.data == "ai_cancel")
async def ai_cancel(callback: CallbackQuery, state: FSMContext):
    if (await state.get_state() or "").startswith("AiAssistant"):
        await state.clear()
    await show(callback, "❌ Bekor qilindi.\n\n👇 Pastdagi menyudan kerakli xizmatni tanlang.", None)
    await callback.answer()


# ===== 1. Ish turi =====
@router.callback_query(AiAssistant.kind, F.data.startswith("ai_kind:"))
async def ai_kind(callback: CallbackQuery, state: FSMContext):
    kind = callback.data.split(":", 1)[1]
    if kind not in TYPES:
        await callback.answer()
        return
    await state.update_data(type=kind)
    await state.set_state(AiAssistant.topic)
    await show(
        callback,
        summary(await state.get_data()) + "✍️ <b>Mavzuni</b> yozing (5–200 belgi):\n\n"
        "<i>Masalan: Oʻzbekistonda turizmning rivojlanish istiqbollari</i>",
        ai_topic_menu,
    )
    await callback.answer()


# ===== 2. Mavzu =====
@router.message(AiAssistant.topic, plain_text)
async def ai_topic(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        params = validate({"type": data["type"], "topic": message.text})
    except AssistantError as e:
        await message.answer(f"⚠️ {e}\nQayta yozing:", reply_markup=ai_topic_menu)
        return
    await state.update_data(topic=params["topic"])
    await state.set_state(AiAssistant.size)
    rules = TYPES[data["type"]]
    await message.answer(
        summary(await state.get_data()) + f"📏 Hajmini tanlang ({rules['unit']}):",
        reply_markup=ai_size_menu(rules),
    )


@router.message(AiAssistant.topic)
async def ai_topic_wrong(message: Message):
    await message.answer("Mavzuni matn ko'rinishida yozing ✍️", reply_markup=ai_topic_menu)


# ===== 3. Hajm =====
@router.callback_query(AiAssistant.size, F.data.startswith("ai_size:"))
async def ai_size(callback: CallbackQuery, state: FSMContext):
    size = int(callback.data.split(":", 1)[1])
    await state.update_data(size=size)
    await state.set_state(AiAssistant.lang)
    await show(callback, summary(await state.get_data()) + "🌐 Qaysi <b>tilda</b> bo'lsin?", ai_lang_menu(LANGUAGES))
    await callback.answer()


# ===== 4. Til → yaratish =====
@router.callback_query(AiAssistant.lang, F.data.startswith("ai_lang:"))
async def ai_generate(callback: CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    if user_id in busy:
        await callback.answer("⏳ Oldingi so'rovingiz tayyorlanmoqda, biroz kuting.", show_alert=True)
        return
    data = await state.get_data()
    try:
        params = validate({**data, "language": callback.data.split(":", 1)[1]})
        check_limits(user_key(user_id))
    except AssistantError as e:
        await callback.answer(str(e), show_alert=True)
        if e.code in ("daily_limit", "validation"):
            await state.clear()
            await show(callback, f"⚠️ {e}", None)
        return

    busy.add(user_id)  # birinchi await'dan oldin — ikki marta bosilsa ikkinchi so'rov ketmaydi
    await state.clear()
    await callback.answer("🚀 Boshladik!")
    wait = callback.message
    with suppress(TelegramBadRequest):
        await wait.edit_text(
            summary(params) + "⏳ <b>Tayyorlanmoqda...</b>\n\n<i>Odatda 15–60 soniya vaqt oladi.</i>", reply_markup=None
        )
    try:
        result, files = await run(user_key(user_id), "bot", params)
    except AssistantError as e:
        with suppress(TelegramBadRequest):
            await wait.edit_text(f"😕 {e}\n\n🤖 Qayta urinish uchun «AI yordamchi» tugmasini bosing.")
        return
    finally:
        busy.discard(user_id)

    caption = (
        f"✅ <b>Tayyor!</b>\n\n📝 {html.escape(result['title'])}\n\n{NOTE}\n\n{left_line(user_id)}"
    )
    try:
        for index, file in enumerate(files):
            await bot.send_document(
                user_id, BufferedInputFile(file["data"], filename=file["name"]),
                caption=caption if index == len(files) - 1 else None,
            )
    except TelegramBadRequest:
        logging.exception("AI yordamchi faylini yuborib bo'lmadi")
        with suppress(TelegramBadRequest):
            await wait.edit_text("😕 Faylni yuborib bo'lmadi. Iltimos, qayta urinib ko'ring.")
        return
    with suppress(TelegramBadRequest):
        await wait.delete()


@router.callback_query(F.data.startswith("ai_"))
async def ai_stale(callback: CallbackQuery):
    # Eski xabardagi tugma (holat allaqachon o'zgargan)
    await callback.answer("Bu tugma eskirgan. «🤖 AI yordamchi» dan qaytadan boshlang.", show_alert=True)
