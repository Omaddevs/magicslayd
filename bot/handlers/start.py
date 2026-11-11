import html
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import ai_usage
from admins import Can, is_admin
from config import (
    IMAGES_MAX, PAGE_RANGE, PLAN_MAX, PLAN_MIN, SLIDE_OPTIONS, SLIDES_MAX, image_plan_text, money, price_lines,
)
from database import (
    db, documents_stats, get_balance, last_presentations, payments_stats, presentations_stats, save_user, users_stats,
)
from keyboards import main_menu

router = Router()
# Hech bir boshqa handler ushlamagan xabarlar uchun — eng oxirida ulanadi
fallback_router = Router()


async def show(callback: CallbackQuery, text, markup):
    """Menyuni shu xabarning o'zida almashtiradi (chat to'lib ketmasligi uchun)."""
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        # Xabar rasm/fayl bo'lsa yoki matn o'zgarmagan bo'lsa — yangi xabar
        if callback.message.photo:
            with suppress(TelegramBadRequest):
                await callback.message.delete()
        await callback.message.answer(text, reply_markup=markup)


async def welcome_text(bot: Bot, user):
    me = await bot.me()
    name = html.escape(user.first_name)
    return (
        f"👋 <b>Assalomu alaykum, {name}!</b>\n\n"
        f"🤖 <b>{html.escape(me.first_name)}</b> — sun'iy intellekt yordamida 30 soniya ichida tayyorlab beradi:\n\n"
        f"📊 <b>Prezentatsiya</b> — {SLIDE_OPTIONS[0]}–{SLIDES_MAX} slayd, {PLAN_MIN}–{PLAN_MAX} reja, mavzuga mos rasmlar, "
        "chiroyli dizaynlar\n"
        f"📄 <b>Referat</b> va ✍️ <b>Mustaqil ish</b> — {PAGE_RANGE['referat'][0]}–{PAGE_RANGE['referat'][1]} bet\n"
        f"📚 <b>Kurs ishi</b> — {PAGE_RANGE['kurs'][0]}–{PAGE_RANGE['kurs'][1]} bet, boblar bilan\n\n"
        "Hajmini o'zingiz tanlaysiz, narx ham shunga qarab hisoblanadi.\n"
        "👤 «Titul ma'lumotlari»ni bir marta to'ldirsangiz, muqovaga avtomatik yoziladi.\n\n"
        f"👛 Balansingiz: <b>{money(get_balance(user.id))}</b>\n\n"
        "👇 Boshlash uchun pastdagi tugmani bosing"
    )


HELP_TEXT = (
    "ℹ️ <b>Yordam</b>\n\n"
    "1️⃣ «💎 Balans» orqali hisobingizni to'ldiring\n"
    "2️⃣ «👤 Titul ma'lumotlari»ni to'ldiring (referat va kurs ishi muqovasi uchun)\n"
    "3️⃣ Kerakli xizmatni tanlang, mavzuni yozing va hajmini (slayd / bet) tanlang\n"
    "4️⃣ Tilni, formatni (va taqdimot uchun dizaynni) belgilang\n"
    "5️⃣ Tayyor faylni oling 🎉 — u «📂 Hujjatlarim» da ham saqlanadi\n\n"
    f"💰 <b>Narxlar:</b>\n{price_lines()}\n"
    "Pul faqat fayl tayyorlanganda yechiladi — xato bo'lsa, hisobingizga avtomatik qaytadi.\n\n"
    "📐 <b>Taqdimot tuzilmasi:</b> muqova → mundarija → reja → har bir reja bo'yicha slaydlar → xulosa. "
    "Shuning uchun slaydlar soni kamida «reja soni + 4» bo'ladi.\n"
    f"🏞 Slaydlarga mavzuga mos rasmlar qo'yiladi: {image_plan_text()} va undan ko'pga ham {IMAGES_MAX} ta.\n"
    "📐 <b>Referat / kurs ishi:</b> muqova → mundarija → kirish → boblar → xulosa → adabiyotlar.\n\n"
    "🎨 Tayyor taqdimotni «Boshqa dizaynda olish» tugmasi orqali istalgan dizaynga bepul o'tkazish mumkin.\n\n"
    "/start — bosh menyu\n"
    "/taqdimot — taqdimot yaratish\n"
    "/hamyon — balans va to'ldirish\n"
    "/help — yordam"
)


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    save_user(message.from_user)
    await message.answer(await welcome_text(bot, message.from_user), reply_markup=main_menu)
    if is_admin(message.from_user.id):
        # Admin botga birinchi marta kirdi (yoki menyusi yo'qolgan) — admin buyruqlari menyusi o'rnatiladi
        from handlers.admins import set_admin_menu
        await set_admin_menu(bot, message.from_user.id)


@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(HELP_TEXT, reply_markup=main_menu)


@router.callback_query(F.data == "home")
async def home(callback: CallbackQuery, state: FSMContext, bot: Bot):
    # Eski xabarlardagi «Bosh menyu» tugmasi uchun — menyu endi pastdagi doimiy tugmalarda
    await state.clear()
    await show(callback, await welcome_text(bot, callback.from_user), None)
    await callback.answer()


# ===== Claude xarajati (ai_usage.py) =====
@router.message(Command("xarajat"), Can("stats"))
async def admin_costs(message: Message):
    s = ai_usage.summary()
    line = lambda pair: f"<b>${pair[0]:.3f}</b> ({pair[1]} so'rov)"  # noqa: E731
    budget = (f"${s['budget']:.2f} — bugun {s['today'][0] / s['budget']:.0%} i ishlatildi"
              if s["budget"] else "yo'q")
    models = "\n".join(
        f"• {html.escape(model)}: ${cost:.3f} · {count} so'rov · {inp // 1000}K kiruvchi / {out // 1000}K chiquvchi token"
        for model, cost, count, inp, out in s["by_model"]
    ) or "• hali so'rov yo'q"
    await message.answer(
        "💵 <b>Claude API xarajati</b>\n\n"
        f"⏱ Oxirgi 30 daqiqa: {line(s['recent'])}\n"
        f"📅 Bugun: {line(s['today'])}\n"
        f"🗓 Oxirgi 7 kun: {line(s['week'])}\n"
        f"Σ Jami (hisoblagich yoqilgandan beri): {line(s['total'])}\n\n"
        f"🛡 Kunlik chegara: {budget}\n\n"
        f"<b>Modellar bo'yicha (7 kun):</b>\n{models}\n\n"
        "💡 Bitta ish qancha turishini bilish: ishni yarating, keyin /xarajat — «Oxirgi 30 daqiqa» o'sha ish narxi.\n"
        "Rasmlar (Gemini) bu hisobga kirmaydi — ular Google hisobidan to'lanadi. "
        "Aniq qoldiq: platform.claude.com → Billing."
    )


# ===== Admin statistikasi =====
def stats_text():
    """Admin statistikasi (/stats va /admin → «📊 Statistika»)."""
    users = users_stats()
    total, today = presentations_stats()
    payments = payments_stats()
    docs = documents_stats()
    accounts = db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    recent = "\n".join(
        f"• {html.escape(topic[:50])} — {slides} slayd ({html.escape(name or '—')}, {created[5:]})"
        for topic, slides, created, name in last_presentations()
    )
    return (
        "📊 <b>Statistika</b>\n\n"
        "👥 <b>Foydalanuvchilar</b>\n"
        f"├ Jami: <b>{users['total']}</b>\n"
        f"├ Ro'yxatdan o'tgan (raqam + parol): <b>{accounts}</b>\n"
        f"├ Bugun: <b>+{users['today']}</b>\n"
        f"└ Oxirgi 7 kun: <b>+{users['week']}</b>\n\n"
        "📑 <b>Taqdimotlar</b>\n"
        f"├ Jami: <b>{total}</b>\n"
        f"└ Bugun: <b>+{today}</b>\n\n"
        "📄 <b>Matnli ishlar</b>\n"
        f"├ Referat: <b>{docs.get('referat', 0)}</b>\n"
        f"├ Mustaqil ish: <b>{docs.get('mustaqil', 0)}</b>\n"
        f"└ Kurs ishi: <b>{docs.get('kurs', 0)}</b>\n\n"
        "💰 <b>To'lovlar</b>\n"
        f"├ Jami tushum: <b>{money(payments['total'])}</b>\n"
        f"├ Bugun: <b>{money(payments['today'])}</b>\n"
        f"├ Userlar balansida: <b>{money(payments['balances'])}</b>\n"
        f"└ Tekshiruvni kutmoqda: <b>{payments['pending']}</b> ta (/tolovlar)\n\n"
        f"🕘 <b>Oxirgilari</b>\n{recent or '—'}"
    )


@router.message(Command("stats"), Can("stats"))
async def admin_stats(message: Message):
    await message.answer(stats_text())


@fallback_router.message()
async def unknown(message: Message):
    await message.answer("👇 Pastdagi menyudan kerakli xizmatni tanlang", reply_markup=main_menu)


@fallback_router.callback_query()
async def unknown_button(callback: CallbackQuery):
    await callback.answer()
