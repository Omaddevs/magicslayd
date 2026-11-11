import asyncio
import html
import logging
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from admins import has_perm
from config import PAGE_PRICE, PAGE_RANGE, document_price, money
from converter import PDF_AVAILABLE, to_pdf
from database import (
    add_document, charge_hold, get_balance, get_document, get_title, refund_hold, save_title, save_user, settle_hold,
    user_documents,
)
from documents.ai import generate_document, word_count
from documents.builder import build_docx
from documents.storage import save_paper
from handlers.presentation import (
    ERRORS, SETTINGS, TOPIC_MAX, TOPIC_MIN, ai_slots, alert_admin, animate, file_name, generating, plain_text,
    send_celebrating, show_step,
)
from handlers.start import show
from keyboards import (
    DOC_BUTTONS, FILE_ICONS, FORMAT_NAMES, TITLE_FIELDS, doc_back_row, doc_confirm_menu, doc_lang_menu,
    doc_pages_menu, doc_result_menu, doc_topic_menu, file_menu, files_menu, format_menu, title_back_menu, title_menu,
)
from presentation.ai import LANGUAGES
from states import EditTitle, MakeDocument

router = Router()

DOC_NAMES = {"referat": "📄 Referat", "mustaqil": "✍️ Mustaqil ish", "kurs": "📚 Kurs ishi"}
# Format qadami faqat PDF yaratish mumkin bo'lsa ko'rsatiladi
DOC_STEPS = ("topic", "pages", "lang") + (("format",) if PDF_AVAILABLE else ()) + ("confirm",)
DOC_PROGRESS = (  # har 5 soniyada keyingisi
    "🧠 Mavzu tahlil qilinmoqda",
    "📋 Ish rejasi tuzilmoqda",
    "✍️ Kirish va boblar yozilmoqda",
    "📚 Adabiyotlar va rasmlar tanlanmoqda",
    "📝 Xulosa yozilmoqda",
    "🔎 Matn tekshirilmoqda",
    "📄 Fayl tayyorlanmoqda",
)
TITLE_MAX = 150
TITLE_EXAMPLES = {
    "university": "Masalan: Toshkent davlat iqtisodiyot universiteti",
    "faculty": "Masalan: Iqtisodiyot fakulteti, Moliya kafedrasi",
    "subject": "Masalan: Makroiqtisodiyot",
    "student": "Masalan: Aliyev Vali Karimovich",
    "group": "Masalan: IQ-21-01",
    "teacher": "Masalan: i.f.n., dots. Karimov A.B.",
    "city": "Masalan: Toshkent",
}


def doc_price(user_id, kind, pages):
    return 0 if has_perm(user_id, "free") else document_price(kind, pages)


def prev_doc_step(step):
    return DOC_STEPS[DOC_STEPS.index(step) - 1]


def doc_ready(data):
    return all(data.get(key) for key in ("doc_kind", "doc_topic", "doc_pages", "doc_lang"))


def doc_confirm_markup(user_id, data):
    price = doc_price(user_id, data["doc_kind"], data["doc_pages"])
    return doc_confirm_menu(price, price - get_balance(user_id), prev_doc_step("confirm"))


# ===== Buyurtma qadamlari =====
def doc_screen(step, data, user_id):
    kind = data["doc_kind"]
    number = DOC_STEPS.index(step) + 1
    progress = "●" * number + "○" * (len(DOC_STEPS) - number)
    text = f"{DOC_NAMES[kind]}\n<code>{progress}</code>  {number}/{len(DOC_STEPS)}\n\n"
    lines = []
    if data.get("doc_topic"):
        lines.append(f"📝 Mavzu: <b>{html.escape(data['doc_topic'])}</b>")
    if data.get("doc_pages"):
        lines.append(f"📄 Hajmi: <b>{data['doc_pages']} bet</b>")
    if data.get("doc_lang"):
        lines.append(f"🌐 Til: <b>{LANGUAGES[data['doc_lang']]}</b>")
    if PDF_AVAILABLE and data.get("doc_fmt_chosen"):
        lines.append(f"📁 Format: <b>{FORMAT_NAMES[data['doc_fmt']]}</b>")
    if lines:
        text += "\n".join(lines) + "\n\n"

    if step == "topic":
        return text + "✍️ Ish <b>mavzusini</b> yozing:\n\n<i>Masalan: O'zbekistonda raqamli iqtisodiyotning rivojlanishi</i>", doc_topic_menu
    if step == "pages":
        low, high = PAGE_RANGE[kind]
        return text + (
            "📄 Ish necha <b>bet</b> bo'lsin?\n\n"
            f"💰 Har bir bet — <b>{money(PAGE_PRICE[kind])}</b>\n"
            f"Tugmani bosing yoki o'zingizga kerakli sonni yozing ({low}–{high} bet)."
        ), doc_pages_menu(kind)
    if step == "lang":
        return text + "🌐 Ish qaysi <b>tilda</b> bo'lsin?", doc_lang_menu()
    if step == "format":
        return text + (
            "📁 Fayl qaysi <b>formatda</b> bo'lsin?\n\n"
            "📝 <b>Word</b> — keyin istalgan joyini tahrirlash mumkin\n"
            "📕 <b>PDF</b> — telefon va kompyuterda bir xil ochiladi, tahrirlab bo'lmaydi"
        ), format_menu("doc_fmt:", "docx", doc_back_row("lang"))

    title = get_title(user_id)
    if title:
        filled = ", ".join(TITLE_FIELDS[key].split(" ", 1)[1] for key in TITLE_FIELDS if title.get(key))
        text += f"👤 Titul: <b>to'ldirilgan</b> ({filled})\n"
    else:
        text += "⚠️ Titul ma'lumotlari to'ldirilmagan — muqovada faqat ish turi va mavzu bo'ladi.\n"
    price, balance = doc_price(user_id, kind, data["doc_pages"]), get_balance(user_id)
    text += (
        "\n📐 <b>Tuzilma:</b> muqova → mundarija → kirish → boblar → xulosa → adabiyotlar\n\n"
        f"💰 Narxi: <b>{money(price) if price else 'bepul (admin)'}</b>\n"
        f"👛 Balansingiz: <b>{money(balance)}</b>\n\n"
    )
    if balance >= price:
        text += "Hammasi to'g'rimi? Unda yozamiz 🚀"
    else:
        text += (
            f"💳 Balansingizda yetarli emas — yana <b>{money(price - balance)}</b> kerak.\n\n"
            "«To'lash va olish» ni bosing: shu summani kartaga o'tkazasiz va chekni yuborasiz. "
            "Admin tasdiqlagach, ish <b>avtomatik yozilib</b>, shu chatga keladi."
        )
    return text, doc_confirm_markup(user_id, data)


async def show_doc_step(bot: Bot, chat_id, state: FSMContext, step, edit: Message | None = None):
    """Qadam ekranini ko'rsatadi: iloji bo'lsa eski xabarni tahrirlaydi, aks holda yangisini yuboradi."""
    await state.set_state(getattr(MakeDocument, step))
    data = await state.get_data()
    text, markup = doc_screen(step, data, chat_id)
    if edit is not None and edit.text:
        try:
            await edit.edit_text(text, reply_markup=markup)
            await state.update_data(wid=edit.message_id)
            return
        except TelegramBadRequest:
            pass
    if data.get("wid"):
        with suppress(TelegramBadRequest):
            await bot.delete_message(chat_id, data["wid"])
    sent = await bot.send_message(chat_id, text, reply_markup=markup)
    await state.update_data(wid=sent.message_id)


async def doc_start(message: Message, state: FSMContext, bot: Bot):
    # Pastdagi «Referat / Mustaqil ish / Kurs ishi» tugmalari (handlers/menu.py da ulanadi)
    save_user(message.from_user)
    await state.clear()
    await state.update_data(doc_kind=DOC_BUTTONS[message.text], doc_fmt="docx")
    await show_doc_step(bot, message.chat.id, state, "topic")


@router.callback_query(F.data == "doc_cancel")
async def doc_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show(callback, "❌ Buyurtma bekor qilindi.\n\n👇 Pastdagi menyudan kerakli xizmatni tanlang.", None)
    await callback.answer("Bekor qilindi")


@router.callback_query(F.data.startswith("doc_back:"), StateFilter(MakeDocument))
async def doc_back(callback: CallbackQuery, state: FSMContext, bot: Bot):
    step = callback.data.split(":", 1)[1]
    if step in DOC_STEPS:
        await show_doc_step(bot, callback.message.chat.id, state, step, callback.message)
    await callback.answer()


@router.message(MakeDocument.topic, plain_text)
async def doc_topic(message: Message, state: FSMContext, bot: Bot):
    topic = " ".join(message.text.split())
    if not TOPIC_MIN <= len(topic) <= TOPIC_MAX:
        await message.answer(f"⚠️ Mavzu {TOPIC_MIN}–{TOPIC_MAX} belgi oralig'ida bo'lsin. Qayta yozing:")
        return
    await state.update_data(doc_topic=topic)
    await show_doc_step(bot, message.chat.id, state, "pages")


@router.callback_query(MakeDocument.pages, F.data.startswith("doc_pages:"))
async def doc_pages_button(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.update_data(doc_pages=int(callback.data.split(":")[1]))
    await show_doc_step(bot, callback.message.chat.id, state, "lang", callback.message)
    await callback.answer()


@router.message(MakeDocument.pages, F.text)
async def doc_pages_text(message: Message, state: FSMContext, bot: Bot):
    low, high = PAGE_RANGE[(await state.get_data())["doc_kind"]]
    text = message.text.strip()
    if not (text.isdecimal() and low <= int(text) <= high):
        await message.answer(f"⚠️ {low} dan {high} gacha son yozing yoki tugmani bosing.")
        return
    await state.update_data(doc_pages=int(text))
    await show_doc_step(bot, message.chat.id, state, "lang")


@router.callback_query(MakeDocument.lang, F.data.startswith("doc_lang:"))
async def doc_lang(callback: CallbackQuery, state: FSMContext, bot: Bot):
    lang = callback.data.split(":")[1]
    if lang in LANGUAGES:
        await state.update_data(doc_lang=lang)
        await show_doc_step(bot, callback.message.chat.id, state, DOC_STEPS[DOC_STEPS.index("lang") + 1],
                            callback.message)
    await callback.answer()


@router.callback_query(MakeDocument.format, F.data.startswith("doc_fmt:"))
async def doc_format(callback: CallbackQuery, state: FSMContext, bot: Bot):
    fmt = callback.data.split(":")[1]
    if fmt in ("docx", "pdf"):
        await state.update_data(doc_fmt=fmt, doc_fmt_chosen=True)
        await show_doc_step(bot, callback.message.chat.id, state, "confirm", callback.message)
    await callback.answer()


@router.message(StateFilter(MakeDocument))
async def doc_wrong_input(message: Message, state: FSMContext):
    hints = {
        MakeDocument.topic.state: "Mavzuni matn ko'rinishida yozing ✍️",
        MakeDocument.pages.state: "Betlar sonini yozing yoki tugmani bosing 👆",
    }
    await message.answer(hints.get(await state.get_state(), "Yuqoridagi tugmalardan birini tanlang 👆"))


@router.callback_query(F.data == "resume")
async def resume(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Hisob to'ldirilgandan (yoki titul tahrirlangandan) keyin saqlangan buyurtmaga qaytaradi."""
    data = await state.get_data()
    if all(data.get(key) for key in ("art_type", "art_topic", "art_lang", "art_words")):
        from handlers.articles import show_step as show_article_step  # maqola buyurtmasi (to'ldirishdan keyin)
        await show_article_step(bot, callback.message.chat.id, state, "confirm")
    elif doc_ready(data):
        await show_doc_step(bot, callback.message.chat.id, state, "confirm")
    elif all(data.get(key) is not None for key in SETTINGS):
        await show_step(bot, callback.message.chat.id, state, "confirm")
    else:
        await callback.answer("Saqlangan buyurtma yo'q. Pastdagi menyudan xizmatni tanlang 👇", show_alert=True)
        return
    await callback.answer()


# ===== Yaratish =====
@router.callback_query(MakeDocument.confirm, F.data == "doc_go")
async def doc_generate(callback: CallbackQuery, state: FSMContext, bot: Bot):
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


async def render_document(content, kind, lang, fmt, title):
    """Tayyor matndan fayl va uning izohini yasaydi: (fayl, caption). Web ilova buyurtmalari ham shuni ishlatadi."""
    name = DOC_NAMES[kind].split(" ", 1)[1]
    images = sum(bool(chapter.get("image")) + sum(1 for s in chapter["sections"] if s.get("image"))
                 for chapter in content["chapters"])
    file = await asyncio.to_thread(build_docx, content, kind, lang, title)
    if fmt == "pdf":
        file = await to_pdf(file, "docx")
    # ~280 so'z/bet + muqova, mundarija, adabiyotlar + har bir rasm ~yarim bet
    real_pages = word_count(content) // 280 + 3 + images // 2
    caption = (
        f"✅ <b>{name} tayyor!</b>\n\n"
        f"📝 {html.escape(content['title'])}\n"
        f"📄 Taxminan <b>{real_pages} bet</b>  ·  🏞 Rasmlar: <b>{images} ta</b>\n\n"
        + ("💡 PDF fayl istalgan qurilmada bir xil ochiladi." if fmt == "pdf"
           else "💡 Word, Google Docs yoki WPS Office'da ochib, istalgan joyini tahrirlashingiz mumkin.")
    )
    if not title:
        caption += "\n\n👤 «Titul ma'lumotlari»ni to'ldirsangiz, keyingi ishlarda muqovaga avtomatik yoziladi."
    return file, caption


async def deliver_document(bot: Bot, chat_id, content, kind, lang, fmt, title, celebrate=True):
    """Faylni yasab chatga yuboradi, «Hujjatlarim» ga yozadi va muharrir uchun loyihani saqlaydi.
    Bot chati va web ilova buyurtmalari uchun umumiy. Hujjat ID'sini qaytaradi."""
    file, caption = await render_document(content, kind, lang, fmt, title)
    sent = await send_celebrating(
        bot, chat_id, BufferedInputFile(file, filename=file_name(content["title"], fmt)), celebrate, caption=caption
    )
    document_id = add_document(chat_id, kind, content["title"], sent.document.file_id)
    try:
        # Xato bo'lsa ham fayl allaqachon yetkazilgan — faqat «✏️ Tahrirlash» chiqmaydi
        await asyncio.to_thread(save_paper, document_id, chat_id, kind, lang, fmt, title, content, file)
    except OSError:
        logging.exception("Hujjat loyihasini saqlab bo'lmadi")
        return document_id
    markup = doc_result_menu(document_id)
    if markup:
        with suppress(TelegramBadRequest):
            await sent.edit_reply_markup(reply_markup=markup)
    return document_id


async def generate_paid(callback: CallbackQuery, state: FSMContext, bot: Bot):
    user_id, chat_id = callback.from_user.id, callback.message.chat.id
    data = await state.get_data()
    kind, topic, lang, pages = data["doc_kind"], data["doc_topic"], data["doc_lang"], data["doc_pages"]
    fmt = data.get("doc_fmt", "docx")
    name = DOC_NAMES[kind].split(" ", 1)[1]
    price = doc_price(user_id, kind, pages)
    # Pul AI ishga tushishidan oldin yechiladi; fayl yetkazilmasa (xato yoki bot to'xtab qolsa ham) — qaytariladi
    hold = charge_hold(user_id, price, f"{name}: {topic[:40]}")
    if hold is None:
        await callback.answer("Balans yetarli emas. Avval hisobni to'ldiring 💳", show_alert=True)
        await show_doc_step(bot, chat_id, state, "confirm", callback.message)
        return
    await state.clear()
    await callback.answer("🚀 Boshladik!")

    progress = callback.message
    hint = ("Odatda 40–60 soniya vaqt oladi." if pages > 30 else
            "Odatda 30–40 soniya vaqt oladi." if pages > 15 else "Odatda 20–30 soniya vaqt oladi.")
    animation = asyncio.create_task(animate(progress, f"{name} yozilmoqda...", DOC_PROGRESS, hint))
    title = get_title(user_id)
    try:
        async with ai_slots:
            # Matn, adabiyotlar va rasmlar bir vaqtda tayyorlanadi
            content = await generate_document(kind, topic, lang, pages)
        animation.cancel()
        with suppress(TelegramBadRequest):
            await progress.edit_text("📝 <b>Fayl tayyorlanmoqda...</b>")
        await deliver_document(bot, chat_id, content, kind, lang, fmt, title)
        settle_hold(hold)
    except Exception as e:
        animation.cancel()
        if isinstance(e, ERRORS):
            reason = str(e)
            await alert_admin(bot, e)
        else:
            logging.exception("Hujjat yaratishda xato")
            reason = "Kutilmagan xato yuz berdi."
        refunded = refund_hold(hold, f"Xato: {topic[:40]}")
        refund_text = f"\n💰 {money(price)} hisobingizga qaytarildi." if refunded else ""
        text, markup = f"😕 {reason}{refund_text}\n\nIltimos, qayta urinib ko'ring.", None
        if await state.get_state() is None:  # foydalanuvchi kutish paytida boshqa amal boshlamagan bo'lsa
            await state.set_data(data)
            await state.set_state(MakeDocument.confirm)
            text = f"😕 {reason}{refund_text}\n\nBuyurtmangiz saqlandi — pastdagi tugma orqali qayta urinib ko'ring."
            markup = doc_confirm_markup(user_id, data)
        with suppress(TelegramBadRequest):
            await progress.edit_text(text, reply_markup=markup)
        return
    finally:
        animation.cancel()

    with suppress(TelegramBadRequest):
        await progress.delete()


@router.callback_query(F.data.startswith("doc_"))
async def doc_stale(callback: CallbackQuery):
    # Eski xabardagi tugma (holat allaqachon o'zgargan)
    await callback.answer("Bu tugma eskirgan. Pastdagi menyudan qaytadan boshlang.", show_alert=True)


# ===== Hujjatlarim =====
async def my_files(message: Message):
    docs = user_documents(message.from_user.id)
    if not docs:
        await message.answer("📂 Hali hujjatlaringiz yo'q.\n\nPastdagi menyudan taqdimot, referat yoki kurs ishi buyurtma qiling 👇")
        return
    await message.answer(
        f"📂 <b>Hujjatlarim</b>\n\nOxirgi {len(docs)} ta fayl. Qayta yuklab olish uchun bosing 👇",
        reply_markup=files_menu(docs),
    )


@router.callback_query(F.data.regexp(r"^file:\d+$"))
async def send_file(callback: CallbackQuery, bot: Bot):
    doc = get_document(int(callback.data.split(":")[1]), callback.from_user.id)
    if not doc:
        await callback.answer("Fayl topilmadi.", show_alert=True)
        return
    await callback.answer()
    caption = f"{FILE_ICONS.get(doc['kind'], '📄')} {html.escape(doc['title'])}\n🕘 {doc['created_at']}"
    if doc["kind"] == "maqola":
        # Maqola — doim oxirgi tahrirlangan versiyasi yuboriladi (saytda o'zgartirilgan bo'lsa ham)
        from handlers.articles import latest_file, result_menu
        try:
            project, data = await latest_file(doc["id"], "docx")
        except Exception:
            logging.exception("Maqola faylini yasab bo'lmadi")
            project, data = None, None
        if project is not None:
            ui = project["params"].get("ui") or project["params"]["lang"]
            await bot.send_document(callback.message.chat.id,
                                    BufferedInputFile(data, filename=file_name(project["title"], "docx")),
                                    caption=caption, reply_markup=result_menu(ui, doc["id"]))
            return
    # Har qanday fayl tahrirlanadi: loyihasi saqlanmagan bo'lsa, sayt uni fayldan tiklaydi
    try:
        await bot.send_document(callback.message.chat.id, doc["file_id"], caption=caption, reply_markup=file_menu(doc))
    except TelegramBadRequest:
        await callback.message.answer("⚠️ Bu faylni qayta yuborib bo'lmadi. Iltimos, yangisini buyurtma qiling.")


# ===== Titul ma'lumotlari =====
def title_text(user_id):
    title = get_title(user_id)
    lines = [f"{label}: <b>{html.escape(title[key])}</b>" if title.get(key) else f"{label}: —"
             for key, label in TITLE_FIELDS.items()]
    return (
        "👤 <b>Titul ma'lumotlari</b>\n\n"
        "Referat, mustaqil ish va kurs ishining muqovasiga shu ma'lumotlar yoziladi.\n\n"
        + "\n".join(lines)
        + "\n\nO'zgartirish uchun kerakli tugmani bosing 👇"
    )


async def title_markup(state: FSMContext):
    return title_menu(order_saved=doc_ready(await state.get_data()))


async def title_show(message: Message, state: FSMContext):
    # Pastdagi «👤 Titul ma'lumotlari» tugmasi (handlers/menu.py da ulanadi)
    save_user(message.from_user)
    await message.answer(title_text(message.from_user.id), reply_markup=await title_markup(state))


@router.callback_query(F.data == "titul")
async def title_back(callback: CallbackQuery, state: FSMContext):
    if await state.get_state() == EditTitle.value.state:
        await state.set_state(None)
    await show(callback, title_text(callback.from_user.id), await title_markup(state))
    await callback.answer()


@router.callback_query(F.data.startswith("titul:"))
async def title_edit(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":", 1)[1]
    if key not in TITLE_FIELDS:
        await callback.answer()
        return
    await state.set_state(EditTitle.value)
    await state.update_data(title_field=key, title_msg=callback.message.message_id)
    await show(callback, f"✍️ <b>{TITLE_FIELDS[key]}</b> ni yozing:\n\n<i>{TITLE_EXAMPLES[key]}</i>", title_back_menu)
    await callback.answer()


@router.callback_query(F.data == "titul_clear")
async def title_clear(callback: CallbackQuery, state: FSMContext):
    save_title(callback.from_user.id, {})
    await show(callback, title_text(callback.from_user.id), await title_markup(state))
    await callback.answer("Tozalandi")


@router.message(EditTitle.value, plain_text)
async def title_value(message: Message, state: FSMContext, bot: Bot):
    value = " ".join(message.text.split())
    if len(value) > TITLE_MAX:
        await message.answer(f"⚠️ {TITLE_MAX} belgidan oshmasin. Qayta yozing:")
        return
    data = await state.get_data()
    await state.set_state(None)
    title = get_title(message.from_user.id)
    title[data["title_field"]] = value
    save_title(message.from_user.id, title)
    if data.get("title_msg"):
        with suppress(TelegramBadRequest):
            await bot.delete_message(message.chat.id, data["title_msg"])
    await message.answer("✅ Saqlandi!\n\n" + title_text(message.from_user.id), reply_markup=await title_markup(state))


@router.message(EditTitle.value)
async def title_wrong_input(message: Message):
    await message.answer("Matn ko'rinishida yozing ✍️ yoki «⬅️ Orqaga» ni bosing.")
