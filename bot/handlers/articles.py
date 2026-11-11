"""📝 Maqola — Telegram bot oqimi: tur → mavzu → til → hajm → qo'shimcha talablar → tasdiqlash.

Yaratish web ilova bilan BIR XIL yo'ldan o'tadi: buyurtma web_orders navbatiga yoziladi, orders_worker
(handlers/web.py → run_order → make_article) uni bajaradi, pulni yechadi va tayyor faylni shu chatga yuboradi.
Bot xabarlari foydalanuvchi tilida: avval Telegram tilidan, maqola tili tanlangach — o'sha tilda."""
import asyncio
import html
import logging
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from articles import storage
from articles.export import build
from articles.model import (
    LANGS, NOTES_MAX, SIZES, TOPIC_MAX, TOPIC_MIN, TYPE_ICONS, TYPE_NAMES, TYPES, target_words, word_count,
)
from admins import has_perm
from config import ARTICLE_WORDS_MAX, ARTICLE_WORDS_MIN, WEBAPP_URL, article_price, money
from database import add_document, add_web_order, get_balance, get_document, save_user, user_waiting_order
from handlers.presentation import file_name, send_celebrating
from states import MakeArticle

router = Router()
Button = InlineKeyboardButton
plain_text = F.text & ~F.text.startswith("/")

FLAGS = {"uz": "🇺🇿 O'zbekcha", "ru": "🇷🇺 Русский", "en": "🇬🇧 English"}

T = {
    "uz": {
        "start": "📝 <b>Maqola yaratish</b>\n\nQanday maqola kerak? Turini tanlang 👇\n\n{types}",
        "topic": "✍️ <b>Mavzuni yozing</b>\n\n{type}\nMasalan: <i>Sun'iy intellektning ta'limdagi o'rni</i>",
        "topic_bad": "⚠️ Mavzu {min}–{max} belgi oralig'ida bo'lsin.",
        "lang": "🌐 <b>Maqola qaysi tilda yozilsin?</b>",
        "size": "📏 <b>Maqola hajmi</b>\n\nTayyor variantni tanlang yoki «Maxsus» orqali so'zlar sonini yozing.",
        "words": "✏️ So'zlar sonini yozing ({min}–{max}). Masalan: <b>1800</b>",
        "words_bad": "⚠️ {min} dan {max} gacha son yozing.",
        "extra": ("⚙️ <b>Qo'shimcha talablar</b> (ixtiyoriy)\n\nUslubni tanlang. Maqsad yoki maxsus talablaringiz "
                  "bo'lsa — «Talab yozish» ni bosing.\n\n{notes}"),
        "notes_now": "📌 Talablaringiz: <i>{notes}</i>",
        "notes_ask": f"✍️ Talablaringizni yozing (maqsad, uslub, format — {NOTES_MAX} belgigacha):",
        "notes_bad": f"⚠️ Matn {NOTES_MAX} belgidan oshmasin.",
        "confirm": ("📋 <b>Buyurtmani tekshiring</b>\n\n{icon} Turi: <b>{type}</b>\n📝 Mavzu: <b>{topic}</b>\n"
                    "🌐 Til: <b>{lang}</b>\n📏 Hajmi: <b>~{words} so'z</b>\n🎨 Uslub: <b>{style}</b>\n{notes}"
                    "\n💰 Narxi: <b>{price}</b>\n👛 Balansingiz: <b>{balance}</b>"),
        "need": "\n\n💳 Yana <b>{need}</b> kerak. To'lov tasdiqlangach maqola avtomatik tayyorlanadi.",
        "queued": ("⏳ <b>Maqola yozilmoqda...</b>\n\n📝 {topic}\n\nOdatda 1–3 daqiqa vaqt oladi. Tayyor bo'lgach shu "
                   "chatga Word fayl keladi — uni saytda tahrirlab, PDF yoki Word qilib yuklab olishingiz mumkin."),
        "busy": "⏳ Oldingi buyurtmangiz hali tayyorlanmoqda. Biroz kuting 🙏",
        "cancelled": "❌ Bekor qilindi.\n\n👇 Pastdagi menyudan kerakli xizmatni tanlang.",
        "hint": "Yuqoridagi tugmalardan birini tanlang 👆",
        "ready": "✅ <b>Maqola tayyor!</b>",
        "stats": "{icon} {type}  ·  ~<b>{words}</b> so'z  ·  🏞 {images}  ·  📚 {sources}",
        "tip": ("✏️ «Tahrirlash» — saytda matn, rasm va jadvallarni o'zgartirish (telefonda ham). "
                "So'ng PDF yoki Word qilib yuklab olasiz."),
        "no_sources": "⚠️ Mavzu bo'yicha ilmiy bazalarda (OpenAlex/Crossref) mos manba topilmadi — adabiyotlarni o'zingiz qo'shing.",
        "few_sources": "⚠️ Ilmiy bazalarda manba kam topildi — adabiyotlar ro'yxatini to'ldiring.",
        "verified": "📚 Adabiyotlar — OpenAlex/Crossref'dagi haqiqiy ishlar. Matnni baribir tekshirib chiqing.",
        "failed": "😕 Maqolani tayyorlab bo'lmadi: {reason}\n\nIltimos, qayta urinib ko'ring.",
        "not_found": "Maqola topilmadi.",
        "copied": "📑 <b>Yangi nusxa yaratildi</b>\n\n{title}\n\nUni alohida tahrirlashingiz mumkin 👇",
        "file": "📄 {title}",
        "b_create": "✨ Yaratish — {price}", "b_create_free": "✨ Maqola yaratish", "b_pay": "💳 To'lash va olish — {need}",
        "b_topup": "➕ Hisobni to'ldirish", "b_back": "⬅️ Orqaga", "b_cancel": "❌ Bekor qilish",
        "b_custom": "✏️ Maxsus", "b_notes": "✍️ Talab yozish", "b_next": "➡️ Davom etish", "b_edit": "✏️ Tahrirlash",
        "b_pdf": "📄 PDF yuklab olish", "b_docx": "📝 Word yuklab olish", "b_redo": "🔁 Qayta yaratish",
        "b_copy": "📑 Yangi nusxa",
        "styles": {"auto": "Avtomatik", "academic": "Ilmiy", "simple": "Sodda"},
        "sizes": {"short": "Qisqa", "medium": "O'rtacha", "long": "Kengaytirilgan"},
        "words_unit": "so'z",
        "desc": {"general": "sodda, ravon — kirish, asosiy qism, xulosa",
                 "scientific": "annotatsiya, kalit so'zlar, metodologiya, haqiqiy manbalar",
                 "analytical": "muammo, sabab va oqibatlar, dalillar, yechimlar",
                 "journalistic": "dolzarb mavzu, ta'sirchan uslub, hayotiy misollar",
                 "review": "tadqiqotlarni taqqoslash, bo'shliqlar, manbalar"},
    },
    "ru": {
        "start": "📝 <b>Создание статьи</b>\n\nКакая статья нужна? Выберите тип 👇\n\n{types}",
        "topic": "✍️ <b>Напишите тему</b>\n\n{type}\nНапример: <i>Роль искусственного интеллекта в образовании</i>",
        "topic_bad": "⚠️ Тема должна быть от {min} до {max} символов.",
        "lang": "🌐 <b>На каком языке написать статью?</b>",
        "size": "📏 <b>Объём статьи</b>\n\nВыберите готовый вариант или укажите число слов через «Свой объём».",
        "words": "✏️ Напишите число слов ({min}–{max}). Например: <b>1800</b>",
        "words_bad": "⚠️ Напишите число от {min} до {max}.",
        "extra": ("⚙️ <b>Дополнительные требования</b> (необязательно)\n\nВыберите стиль. Если есть цель или особые "
                  "требования — нажмите «Написать требования».\n\n{notes}"),
        "notes_now": "📌 Ваши требования: <i>{notes}</i>",
        "notes_ask": f"✍️ Напишите требования (цель, стиль, формат — до {NOTES_MAX} символов):",
        "notes_bad": f"⚠️ Текст не должен превышать {NOTES_MAX} символов.",
        "confirm": ("📋 <b>Проверьте заказ</b>\n\n{icon} Тип: <b>{type}</b>\n📝 Тема: <b>{topic}</b>\n"
                    "🌐 Язык: <b>{lang}</b>\n📏 Объём: <b>~{words} слов</b>\n🎨 Стиль: <b>{style}</b>\n{notes}"
                    "\n💰 Цена: <b>{price}</b>\n👛 Ваш баланс: <b>{balance}</b>"),
        "need": "\n\n💳 Не хватает <b>{need}</b>. После подтверждения оплаты статья будет подготовлена автоматически.",
        "queued": ("⏳ <b>Статья пишется...</b>\n\n📝 {topic}\n\nОбычно это занимает 1–3 минуты. Готовый Word-файл "
                   "придёт в этот чат — его можно отредактировать на сайте и скачать в PDF или Word."),
        "busy": "⏳ Предыдущий заказ ещё готовится. Пожалуйста, подождите 🙏",
        "cancelled": "❌ Отменено.\n\n👇 Выберите нужный раздел в меню ниже.",
        "hint": "Выберите одну из кнопок выше 👆",
        "ready": "✅ <b>Статья готова!</b>",
        "stats": "{icon} {type}  ·  ~<b>{words}</b> слов  ·  🏞 {images}  ·  📚 {sources}",
        "tip": ("✏️ «Редактировать» — изменить текст, картинки и таблицы на сайте (и на телефоне). "
                "Затем скачайте в PDF или Word."),
        "no_sources": "⚠️ В научных базах (OpenAlex/Crossref) не найдено подходящих источников — добавьте литературу сами.",
        "few_sources": "⚠️ В научных базах найдено мало источников — дополните список литературы.",
        "verified": "📚 Литература — реальные работы из OpenAlex/Crossref. Всё же проверьте текст.",
        "failed": "😕 Не удалось подготовить статью: {reason}\n\nПожалуйста, попробуйте ещё раз.",
        "not_found": "Статья не найдена.",
        "copied": "📑 <b>Создана новая копия</b>\n\n{title}\n\nЕё можно редактировать отдельно 👇",
        "file": "📄 {title}",
        "b_create": "✨ Создать — {price}", "b_create_free": "✨ Создать статью", "b_pay": "💳 Оплатить и получить — {need}",
        "b_topup": "➕ Пополнить баланс", "b_back": "⬅️ Назад", "b_cancel": "❌ Отмена",
        "b_custom": "✏️ Свой объём", "b_notes": "✍️ Написать требования", "b_next": "➡️ Продолжить",
        "b_edit": "✏️ Редактировать", "b_pdf": "📄 Скачать PDF", "b_docx": "📝 Скачать Word",
        "b_redo": "🔁 Создать заново", "b_copy": "📑 Новая копия",
        "styles": {"auto": "Автоматически", "academic": "Научный", "simple": "Простой"},
        "sizes": {"short": "Короткая", "medium": "Средняя", "long": "Расширенная"},
        "words_unit": "слов",
        "desc": {"general": "просто и понятно — введение, основная часть, заключение",
                 "scientific": "аннотация, ключевые слова, методология, реальные источники",
                 "analytical": "проблема, причины и последствия, доводы, решения",
                 "journalistic": "актуальная тема, яркий стиль, жизненные примеры",
                 "review": "сравнение исследований, пробелы, источники"},
    },
    "en": {
        "start": "📝 <b>Create an article</b>\n\nWhat kind of article do you need? Choose the type 👇\n\n{types}",
        "topic": "✍️ <b>Enter the topic</b>\n\n{type}\nFor example: <i>The role of artificial intelligence in education</i>",
        "topic_bad": "⚠️ The topic must be {min}–{max} characters long.",
        "lang": "🌐 <b>Which language should the article be written in?</b>",
        "size": "📏 <b>Article length</b>\n\nChoose a preset or enter the number of words via «Custom».",
        "words": "✏️ Enter the number of words ({min}–{max}). For example: <b>1800</b>",
        "words_bad": "⚠️ Enter a number from {min} to {max}.",
        "extra": ("⚙️ <b>Additional requirements</b> (optional)\n\nChoose the style. If you have a purpose or special "
                  "requirements, tap «Write requirements».\n\n{notes}"),
        "notes_now": "📌 Your requirements: <i>{notes}</i>",
        "notes_ask": f"✍️ Write your requirements (purpose, style, format — up to {NOTES_MAX} characters):",
        "notes_bad": f"⚠️ The text must not exceed {NOTES_MAX} characters.",
        "confirm": ("📋 <b>Check your order</b>\n\n{icon} Type: <b>{type}</b>\n📝 Topic: <b>{topic}</b>\n"
                    "🌐 Language: <b>{lang}</b>\n📏 Length: <b>~{words} words</b>\n🎨 Style: <b>{style}</b>\n{notes}"
                    "\n💰 Price: <b>{price}</b>\n👛 Your balance: <b>{balance}</b>"),
        "need": "\n\n💳 <b>{need}</b> more is needed. Once the payment is confirmed, the article is prepared automatically.",
        "queued": ("⏳ <b>Writing the article...</b>\n\n📝 {topic}\n\nUsually takes 1–3 minutes. The Word file will "
                   "arrive in this chat — you can edit it on the website and download it as PDF or Word."),
        "busy": "⏳ Your previous order is still being prepared. Please wait 🙏",
        "cancelled": "❌ Cancelled.\n\n👇 Choose a service from the menu below.",
        "hint": "Choose one of the buttons above 👆",
        "ready": "✅ <b>Your article is ready!</b>",
        "stats": "{icon} {type}  ·  ~<b>{words}</b> words  ·  🏞 {images}  ·  📚 {sources}",
        "tip": ("✏️ «Edit» — change the text, images and tables on the website (on your phone too). "
                "Then download it as PDF or Word."),
        "no_sources": "⚠️ No matching sources were found in scholarly databases (OpenAlex/Crossref) — please add references yourself.",
        "few_sources": "⚠️ Only a few sources were found in scholarly databases — please complete the reference list.",
        "verified": "📚 References are real works from OpenAlex/Crossref. Please still review the text.",
        "failed": "😕 The article could not be prepared: {reason}\n\nPlease try again.",
        "not_found": "Article not found.",
        "copied": "📑 <b>A new copy has been created</b>\n\n{title}\n\nYou can edit it separately 👇",
        "file": "📄 {title}",
        "b_create": "✨ Create — {price}", "b_create_free": "✨ Create Article", "b_pay": "💳 Pay and get — {need}",
        "b_topup": "➕ Top up balance", "b_back": "⬅️ Back", "b_cancel": "❌ Cancel",
        "b_custom": "✏️ Custom", "b_notes": "✍️ Write requirements", "b_next": "➡️ Continue", "b_edit": "✏️ Edit",
        "b_pdf": "📄 Download PDF", "b_docx": "📝 Download Word", "b_redo": "🔁 Regenerate", "b_copy": "📑 New copy",
        "styles": {"auto": "Automatic", "academic": "Academic", "simple": "Simple"},
        "sizes": {"short": "Short", "medium": "Medium", "long": "Extended"},
        "words_unit": "words",
        "desc": {"general": "simple and clear — introduction, main part, conclusion",
                 "scientific": "abstract, keywords, methodology, real references",
                 "analytical": "problem, causes and consequences, evidence, solutions",
                 "journalistic": "current topic, engaging style, real-life examples",
                 "review": "comparing studies, research gaps, references"},
    },
}


def price_for_article(user_id, words):
    """Narx so'zlar soniga qarab; admin uchun bepul (taqdimot va referat bilan bir xil qoida)."""
    return 0 if has_perm(user_id, "free") else article_price(words)


def ui_of(user):
    code = (getattr(user, "language_code", "") or "").lower()
    return "ru" if code.startswith(("ru", "uk", "be", "kk")) else "en" if code.startswith("en") else "uz"


def tr(ui, key, **kwargs):
    text = T.get(ui, T["uz"])[key]
    return text.format(**kwargs) if kwargs else text


def kb(*rows):
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows if r])


def nav(ui, back=None):
    row = [Button(text=tr(ui, "b_back"), callback_data=f"art_back:{back}")] if back else []
    return row + [Button(text=tr(ui, "b_cancel"), callback_data="art_cancel")]


def edit_url(document_id):
    return f"{WEBAPP_URL}{'&' if '?' in WEBAPP_URL else '?'}article={document_id}" if WEBAPP_URL else None


def result_menu(ui, document_id):
    url = edit_url(document_id)
    return kb(
        [Button(text=tr(ui, "b_edit"), web_app=WebAppInfo(url=url))] if url else None,
        [Button(text=tr(ui, "b_pdf"), callback_data=f"art_file:pdf:{document_id}"),
         Button(text=tr(ui, "b_docx"), callback_data=f"art_file:docx:{document_id}")],
        [Button(text=tr(ui, "b_redo"), callback_data=f"art_redo:{document_id}"),
         Button(text=tr(ui, "b_copy"), callback_data=f"art_copy:{document_id}")],
    )


def order_params(data):
    """Bot holatidan buyurtma parametrlari — web ilova yuboradigani bilan bir xil ko'rinish."""
    return {"type": data["art_type"], "topic": data["art_topic"], "lang": data["art_lang"],
            "words": data["art_words"], "style": data.get("art_style", "auto"), "purpose": "",
            "notes": data.get("art_notes", ""), "author": "", "source": "bot", "ui": data.get("art_ui", "uz")}


# ===== Ekranlar =====
def screen(step, data, user_id):
    ui = data.get("art_ui", "uz")
    if step == "type":
        types = "\n".join(f"{TYPE_ICONS[k]} <b>{TYPE_NAMES[ui][k]}</b> — {tr(ui, 'desc')[k]}" for k in TYPES)
        buttons = [[Button(text=f"{TYPE_ICONS[k]} {TYPE_NAMES[ui][k]}", callback_data=f"art_type:{k}")] for k in TYPES]
        return tr(ui, "start", types=types), InlineKeyboardMarkup(inline_keyboard=[*buttons, nav(ui)])
    if step == "topic":
        kind = data["art_type"]
        return tr(ui, "topic", type=f"{TYPE_ICONS[kind]} {TYPE_NAMES[ui][kind]}"), kb(nav(ui, "type"))
    if step == "lang":
        current = data.get("art_lang") or ui
        buttons = [Button(text=("✅ " if k == current else "") + FLAGS[k], callback_data=f"art_lang:{k}") for k in LANGS]
        return tr(ui, "lang"), kb(buttons, nav(ui, "topic"))
    if step == "size":
        unit = tr(ui, "words_unit")
        rows = [[Button(text=f"{tr(ui, 'sizes')[k]} · {low}–{high} {unit} · {money(price_for_article(user_id, target_words(k)))}",
                        callback_data=f"art_size:{k}")] for k, (low, high) in SIZES.items()]
        rows.append([Button(text=tr(ui, "b_custom"), callback_data="art_size:custom")])
        return tr(ui, "size"), InlineKeyboardMarkup(inline_keyboard=[*rows, nav(ui, "lang")])
    if step == "words":
        return tr(ui, "words", min=ARTICLE_WORDS_MIN, max=ARTICLE_WORDS_MAX), kb(nav(ui, "size"))
    if step == "extra":
        style = data.get("art_style", "auto")
        notes = tr(ui, "notes_now", notes=html.escape(data["art_notes"])) if data.get("art_notes") else ""
        styles = [Button(text=("✅ " if k == style else "") + name, callback_data=f"art_style:{k}")
                  for k, name in tr(ui, "styles").items()]
        return tr(ui, "extra", notes=notes), kb(
            styles, [Button(text=tr(ui, "b_notes"), callback_data="art_notes")],
            [Button(text=tr(ui, "b_next"), callback_data="art_next")], nav(ui, "size"),
        )
    if step == "notes":
        return tr(ui, "notes_ask"), kb(nav(ui, "extra"))
    # confirm
    price = price_for_article(user_id, data["art_words"])
    balance = get_balance(user_id)
    need = price - balance
    notes = f"📌 <i>{html.escape(data['art_notes'])}</i>\n" if data.get("art_notes") else ""
    text = tr(ui, "confirm", icon=TYPE_ICONS[data["art_type"]], type=TYPE_NAMES[ui][data["art_type"]],
              topic=html.escape(data["art_topic"]), lang=FLAGS[data["art_lang"]], words=data["art_words"],
              style=tr(ui, "styles")[data.get("art_style", "auto")], notes=notes, price=money(price),
              balance=money(balance))
    if need > 0:
        text += tr(ui, "need", need=money(need))
        rows = [[Button(text=tr(ui, "b_pay", need=money(need)), callback_data="order_pay")],
                [Button(text=tr(ui, "b_topup"), callback_data="wallet_topup")]]
    else:
        label = tr(ui, "b_create", price=money(price)) if price else tr(ui, "b_create_free")
        rows = [[Button(text=label, callback_data="art_go")]]
    return text, InlineKeyboardMarkup(inline_keyboard=[*rows, nav(ui, "extra")])


STEP_STATES = {"type": MakeArticle.type, "topic": MakeArticle.topic, "lang": MakeArticle.lang,
               "size": MakeArticle.size, "words": MakeArticle.words, "extra": MakeArticle.extra,
               "notes": MakeArticle.notes, "confirm": MakeArticle.confirm}


async def show_step(bot: Bot, chat_id, state: FSMContext, step, edit: Message | None = None):
    """Bitta xabarning o'zida qadamni almashtiradi (chat to'lib ketmasin)."""
    data = await state.get_data()
    text, markup = screen(step, data, chat_id)
    await state.set_state(STEP_STATES[step])
    if edit is not None:
        try:
            await edit.edit_text(text, reply_markup=markup)
            return
        except TelegramBadRequest:
            pass
    else:
        old = data.get("art_msg")
        if old:
            with suppress(TelegramBadRequest):
                await bot.edit_message_reply_markup(chat_id=chat_id, message_id=old, reply_markup=None)
    sent = await bot.send_message(chat_id, text, reply_markup=markup)
    await state.update_data(art_msg=sent.message_id)


# ===== Qadamlar =====
async def article_start(message: Message, state: FSMContext, bot: Bot):
    save_user(message.from_user)
    await state.clear()
    await state.update_data(art_ui=ui_of(message.from_user))
    await show_step(bot, message.chat.id, state, "type")


router.message.register(article_start, Command("maqola"))


@router.callback_query(F.data == "art_cancel")
async def article_cancel(callback: CallbackQuery, state: FSMContext):
    ui = (await state.get_data()).get("art_ui", ui_of(callback.from_user))
    await state.clear()
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(tr(ui, "cancelled"))
    await callback.answer()


@router.callback_query(F.data.startswith("art_back:"))
async def article_back(callback: CallbackQuery, state: FSMContext, bot: Bot):
    step = callback.data.split(":", 1)[1]
    if step in STEP_STATES and await state.get_state() and (await state.get_state()).startswith(MakeArticle.__name__):
        await show_step(bot, callback.message.chat.id, state, step, callback.message)
    await callback.answer()


@router.callback_query(MakeArticle.type, F.data.startswith("art_type:"))
async def article_type(callback: CallbackQuery, state: FSMContext, bot: Bot):
    kind = callback.data.split(":", 1)[1]
    if kind in TYPES:
        await state.update_data(art_type=kind)
        await show_step(bot, callback.message.chat.id, state, "topic", callback.message)
    await callback.answer()


@router.message(MakeArticle.topic, plain_text)
async def article_topic(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    topic = " ".join(message.text.split())
    if not TOPIC_MIN <= len(topic) <= TOPIC_MAX:
        await message.answer(tr(data.get("art_ui", "uz"), "topic_bad", min=TOPIC_MIN, max=TOPIC_MAX))
        return
    await state.update_data(art_topic=topic)
    await show_step(bot, message.chat.id, state, "lang")


@router.callback_query(MakeArticle.lang, F.data.startswith("art_lang:"))
async def article_lang(callback: CallbackQuery, state: FSMContext, bot: Bot):
    lang = callback.data.split(":", 1)[1]
    if lang in LANGS:
        await state.update_data(art_lang=lang, art_ui=lang)  # bundan keyingi xabarlar maqola tilida
        await show_step(bot, callback.message.chat.id, state, "size", callback.message)
    await callback.answer()


@router.callback_query(MakeArticle.size, F.data.startswith("art_size:"))
async def article_size(callback: CallbackQuery, state: FSMContext, bot: Bot):
    size = callback.data.split(":", 1)[1]
    if size == "custom":
        await show_step(bot, callback.message.chat.id, state, "words", callback.message)
    elif size in SIZES:
        await state.update_data(art_size=size, art_words=target_words(size))
        await show_step(bot, callback.message.chat.id, state, "extra", callback.message)
    await callback.answer()


@router.message(MakeArticle.words, plain_text)
async def article_words(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    digits = "".join(ch for ch in message.text if ch.isdigit())
    words = int(digits) if digits else 0
    if not ARTICLE_WORDS_MIN <= words <= ARTICLE_WORDS_MAX:
        await message.answer(tr(data.get("art_ui", "uz"), "words_bad", min=ARTICLE_WORDS_MIN, max=ARTICLE_WORDS_MAX))
        return
    await state.update_data(art_size="custom", art_words=words)
    await show_step(bot, message.chat.id, state, "extra")


@router.callback_query(MakeArticle.extra, F.data.startswith("art_style:"))
async def article_style(callback: CallbackQuery, state: FSMContext, bot: Bot):
    style = callback.data.split(":", 1)[1]
    if style in T["uz"]["styles"]:
        await state.update_data(art_style=style)
        await show_step(bot, callback.message.chat.id, state, "extra", callback.message)
    await callback.answer()


@router.callback_query(MakeArticle.extra, F.data == "art_notes")
async def article_notes_ask(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await show_step(bot, callback.message.chat.id, state, "notes", callback.message)
    await callback.answer()


@router.message(MakeArticle.notes, plain_text)
async def article_notes(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    notes = " ".join(message.text.split())
    if len(notes) > NOTES_MAX:
        await message.answer(tr(data.get("art_ui", "uz"), "notes_bad"))
        return
    await state.update_data(art_notes=notes)
    await show_step(bot, message.chat.id, state, "extra")


@router.callback_query(MakeArticle.extra, F.data == "art_next")
async def article_next(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await show_step(bot, callback.message.chat.id, state, "confirm", callback.message)
    await callback.answer()


@router.callback_query(MakeArticle.confirm, F.data == "art_go")
async def article_go(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    ui = data.get("art_ui", "uz")
    if user_waiting_order(user_id):
        await callback.answer(tr(ui, "busy"), show_alert=True)
        return
    params = order_params(data)
    if price_for_article(user_id, params["words"]) > get_balance(user_id):
        await callback.answer()
        await show_step(callback.bot, callback.message.chat.id, state, "confirm", callback.message)
        return
    # Pul bajaruvchi (run_order) tomonidan yechiladi — xato bo'lsa o'zi qaytaradi
    add_web_order(user_id, "maqola", params)
    await state.clear()
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(tr(ui, "queued", topic=html.escape(params["topic"])))
    await callback.answer("🚀")


@router.message(MakeArticle.type)
@router.message(MakeArticle.lang)
@router.message(MakeArticle.size)
@router.message(MakeArticle.extra)
@router.message(MakeArticle.confirm)
async def article_wrong_input(message: Message, state: FSMContext):
    await message.answer(tr((await state.get_data()).get("art_ui", "uz"), "hint"))


# ===== Tayyor maqola: yetkazish va amallar =====
def caption_for(ui, project, images):
    params = project["params"]
    lines = [tr(ui, "ready"), "", f"📝 {html.escape(project['title'])}",
             tr(ui, "stats", icon=TYPE_ICONS[params["type"]], type=TYPE_NAMES[ui][params["type"]],
                words=word_count(project["blocks"]), images=images,
                sources=sum(len(b["items"]) for b in project["blocks"] if b["t"] == "ol")
                if params["type"] in ("scientific", "review", "analytical") else "—")]
    notice = project.get("notice")
    if params["type"] in ("scientific", "review", "analytical"):
        lines += ["", tr(ui, notice) if notice in ("no_sources", "few_sources") else tr(ui, "verified")]
    lines += ["", tr(ui, "tip")]
    return "\n".join(lines)[:1024]


async def deliver_article(bot: Bot, user_id, params, result):
    """AI yozgan maqolani saqlaydi, Word faylni chatga yuboradi va «Hujjatlarim»ga yozadi. Hujjat ID'sini qaytaradi.
    Bot va web ilova buyurtmalari uchun umumiy (handlers/web.py → make_article)."""
    ui = params.get("ui") or params["lang"]
    images = result.get("images") or {}
    docx = await asyncio.to_thread(build, result, images.get, "docx", params.get("author", ""))
    caption = caption_for(ui, {"params": params, "title": result["title"], "blocks": result["blocks"],
                               "notice": result.get("notice")}, len(images))
    sent = await send_celebrating(bot, user_id, BufferedInputFile(docx, filename=file_name(result["title"], "docx")),
                                  caption=caption)
    document_id = add_document(user_id, "maqola", result["title"], sent.document.file_id)
    project = await asyncio.to_thread(storage.save_new, document_id, user_id, params, result)
    await asyncio.to_thread(storage.save_export, document_id, "docx", docx, project["rev"])
    with suppress(TelegramBadRequest):
        await sent.edit_reply_markup(reply_markup=result_menu(ui, document_id))
    return document_id


async def latest_file(document_id, fmt):
    """Joriy (oxirgi tahrirlangan) versiyadan fayl — yasalganmi tekshiradi, eskirgan bo'lsa qayta yasaydi."""
    project = await asyncio.to_thread(storage.load, document_id)
    if project is None:
        return None, None
    if storage.exported_rev(document_id, fmt) == project["rev"] and storage.export_path(document_id, fmt).is_file():
        return project, storage.export_path(document_id, fmt).read_bytes()
    data = await asyncio.to_thread(build, project, storage.media_reader(document_id), fmt, project.get("author", ""))
    await asyncio.to_thread(storage.save_export, document_id, fmt, data, project["rev"])
    return project, data


@router.callback_query(F.data.regexp(r"^art_file:(pdf|docx):\d+$"))
async def article_file(callback: CallbackQuery, bot: Bot):
    _, fmt, doc_id = callback.data.split(":")
    ui = ui_of(callback.from_user)
    document = get_document(int(doc_id), callback.from_user.id)
    if not document:
        await callback.answer(tr(ui, "not_found"), show_alert=True)
        return
    await callback.answer("⏳")
    try:
        project, data = await latest_file(document["id"], fmt)
    except Exception:
        logging.exception("Maqola faylini yasab bo'lmadi")
        project, data = None, None
    if project is None or project.get("user_id") != callback.from_user.id:
        await callback.message.answer(tr(ui, "not_found"))
        return
    ui = project["params"].get("ui") or project["params"]["lang"]
    await bot.send_document(callback.message.chat.id, BufferedInputFile(data, filename=file_name(project["title"], fmt)),
                            caption=tr(ui, "file", title=html.escape(project["title"])),
                            reply_markup=result_menu(ui, document["id"]))


@router.callback_query(F.data.regexp(r"^art_redo:\d+$"))
async def article_redo(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """«Qayta yaratish» — o'sha sozlamalar bilan tasdiqlash qadamiga qaytadi (yangi buyurtma)."""
    document = get_document(int(callback.data.split(":")[1]), callback.from_user.id)
    project = storage.load(document["id"]) if document else None
    if not project or project.get("user_id") != callback.from_user.id:
        await callback.answer(tr(ui_of(callback.from_user), "not_found"), show_alert=True)
        return
    p = project["params"]
    await state.clear()
    await state.update_data(art_ui=p.get("ui") or p["lang"], art_type=p["type"], art_topic=p["topic"],
                            art_lang=p["lang"], art_words=p["words"], art_style=p.get("style", "auto"),
                            art_notes=p.get("notes", ""))
    await callback.answer()
    await show_step(bot, callback.message.chat.id, state, "confirm")


@router.callback_query(F.data.regexp(r"^art_copy:\d+$"))
async def article_copy(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    document = get_document(int(callback.data.split(":")[1]), user_id)
    project = storage.load(document["id"]) if document else None
    if not project or project.get("user_id") != user_id:
        await callback.answer(tr(ui_of(callback.from_user), "not_found"), show_alert=True)
        return
    ui = project["params"].get("ui") or project["params"]["lang"]
    copy_id = add_document(user_id, "maqola", document["title"], document["file_id"])
    copy = await asyncio.to_thread(storage.copy_article, document["id"], copy_id, user_id)
    await callback.answer("📑")
    await callback.message.answer(tr(ui, "copied", title=html.escape(copy["title"])), reply_markup=result_menu(ui, copy_id))


async def notify_failed(bot: Bot, user_id, params, reason):
    """Bot chatidan berilgan buyurtma bajarilmasa — sababi foydalanuvchi tilida yuboriladi."""
    ui = params.get("ui") or params.get("lang") or "uz"
    with suppress(Exception):
        await bot.send_message(user_id, tr(ui, "failed", reason=html.escape(reason)))
