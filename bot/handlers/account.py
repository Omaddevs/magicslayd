"""Ro'yxatdan o'tish (telefon + parol) — web ilovaga istalgan qurilmadan kirish uchun.
Raqam Telegram kontakti orqali olinadi (o'zingizniki ekani Telegram tomonidan tasdiqlangan).
Parol yozilgan xabarlar darhol o'chiriladi, botda faqat xesh saqlanadi."""
import asyncio
import html
import sqlite3
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo,
)

import accounts
from config import WEBAPP_URL
from database import save_user
from keyboards import main_menu
from states import ChangePassword, Register

router = Router()

BTN_CANCEL = "❌ Bekor qilish"
contact_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)], [KeyboardButton(text=BTN_CANCEL)]],
    resize_keyboard=True,
    input_field_placeholder="Pastdagi tugmani bosing 👇",
)
password_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_CANCEL)]], resize_keyboard=True, input_field_placeholder="Parolni yozing…",
)

RULES = "• kamida 6 belgi\n• harf va raqam aralash (masalan: <code>Slayd2026</code>)"
HIDDEN = "<i>🛡 Xavfsizlik uchun parolli xabaringiz darhol o'chiriladi.</i>"


def app_markup(*rows):
    buttons = [list(row) for row in rows]
    if WEBAPP_URL:
        buttons.append([InlineKeyboardButton(text="📱 Ilovani ochish", web_app=WebAppInfo(url=WEBAPP_URL))])
    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None


async def delete_quietly(message: Message):
    with suppress(TelegramAPIError):
        await message.delete()


# ===== Hisob holati: «🔐 Hisobim», /hisob =====
async def account_show(message: Message, state: FSMContext, user_id=None):
    await state.clear()
    user_id = user_id or message.from_user.id
    account = accounts.account_by_user(user_id)
    if account:
        status = "✅ Raqam Telegram orqali tasdiqlangan" if account["verified"] else "⚠️ Raqam hali tasdiqlanmagan"
        rows = [[InlineKeyboardButton(text="🔑 Parolni o'zgartirish", callback_data="acc_pass")]]
        if not account["verified"]:
            rows.append([InlineKeyboardButton(text="✅ Raqamni tasdiqlash", callback_data="acc_verify")])
        await message.answer(
            "🔐 <b>Hisobingiz</b>\n\n"
            f"📱 Login: <b>{accounts.format_phone(account['phone'])}</b>\n{status}\n\n"
            "Ilovaga istalgan qurilmadan (telefon, kompyuter, brauzer) shu raqam va parolingiz bilan kirasiz.\n"
            "Parolni unutsangiz — shu yerda «🔑 Parolni o'zgartirish» yoki ilovadagi «Parolni unutdingizmi?».",
            reply_markup=app_markup(*rows),
        )
        return
    await message.answer(
        "🔐 <b>Ro'yxatdan o'tish</b>\n\n"
        "Telefon raqam va parol bilan hisob yarating — so'ng ilovada ish yaratish, saqlash va yoqtirish ochiladi, "
        "istalgan qurilmadan kirish mumkin bo'ladi.\n\n"
        "💎 Balansingiz va 📂 hujjatlaringiz o'zgarmaydi — hisobga bog'lanadi.\n"
        "⏱ Bor-yo'g'i 2 qadam: raqamni yuborish → parol o'ylab topish.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Ro'yxatdan o'tish", callback_data="acc_register")],
        ]),
    )


async def register_start(message: Message, state: FSMContext, user_id):
    if accounts.account_by_user(user_id):
        await account_show(message, state, user_id)
        return
    await state.clear()
    await state.set_state(Register.phone)
    await message.answer(
        "📱 <b>1-qadam / 2 — telefon raqam</b>\n\n"
        "Pastdagi «📱 Raqamni yuborish» tugmasini bosing. Telegram raqamingizni avtomatik yuboradi va u siznikiligi "
        "tasdiqlanadi — qo'lda yozish shart emas.",
        reply_markup=contact_kb,
    )


# Deep link: t.me/<bot>?start=royxat (ilovadagi «Bot orqali ro'yxatdan o'tish»)
@router.message(CommandStart(deep_link=True, magic=F.args == "royxat"))
async def start_register(message: Message, state: FSMContext):
    save_user(message.from_user)
    await register_start(message, state, message.from_user.id)


@router.message(Command("royxat"))
async def register_command(message: Message, state: FSMContext):
    save_user(message.from_user)
    await register_start(message, state, message.from_user.id)


@router.message(Command("hisob"))
async def account_command(message: Message, state: FSMContext):
    await account_show(message, state)


@router.callback_query(F.data == "acc_register")
async def register_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await register_start(callback.message, state, callback.from_user.id)


@router.callback_query(F.data == "acc_verify")
async def verify_button(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "Pastdagi tugma orqali raqamingizni yuboring — hisobingizdagi raqam bilan bir xil bo'lsa, tasdiqlanadi.",
        reply_markup=contact_kb,
    )


# ===== Bekor qilish (istalgan qadamda) =====
@router.message(Register.phone, F.text == BTN_CANCEL)
@router.message(Register.password, F.text == BTN_CANCEL)
@router.message(Register.confirm, F.text == BTN_CANCEL)
@router.message(ChangePassword.password, F.text == BTN_CANCEL)
@router.message(ChangePassword.confirm, F.text == BTN_CANCEL)
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Bekor qilindi. Istalgan vaqtda «🔐 Hisobim» orqali davom ettirishingiz mumkin.", reply_markup=main_menu)


# ===== 1-qadam: kontakt =====
@router.message(Register.phone, F.contact)
async def register_contact(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    contact = message.contact
    if contact.user_id != user_id:
        await message.answer("❗ Faqat o'zingizning raqamingizni yuboring — pastdagi tugmani bosing.", reply_markup=contact_kb)
        return
    phone = accounts.normalize_phone(contact.phone_number)
    if not phone:
        await state.clear()
        await message.answer("😔 Hozircha faqat O'zbekiston (+998) raqamlari qabul qilinadi.", reply_markup=main_menu)
        return
    accounts.save_verified_phone(user_id, phone)

    taken = accounts.account_by_phone(phone)
    if taken and taken["user_id"] != user_id:
        if taken["verified"]:
            await state.clear()
            await message.answer(
                "❗ Bu raqam boshqa Telegram hisobiga bog'langan. Agar u sizniki bo'lsa, o'sha hisobdan kiring "
                "yoki admin bilan bog'laning.",
                reply_markup=main_menu,
            )
            return
        # Tasdiqlanmagan (begona yozib qo'ygan bo'lishi mumkin) hisob — raqamning haqiqiy egasiga o'tadi
        accounts.remove_account(taken["user_id"])
        with suppress(TelegramAPIError):
            await bot.send_message(
                taken["user_id"],
                f"⚠️ {accounts.format_phone(phone)} raqamining haqiqiy egasi uni tasdiqladi — hisob sizdan uzildi.",
            )

    await state.update_data(phone=phone)
    await state.set_state(Register.password)
    await message.answer(
        f"✅ Raqam tasdiqlandi: <b>{accounts.format_phone(phone)}</b>\n\n"
        f"🔑 <b>2-qadam / 2 — parol</b>\n\nParol o'ylab toping va yozing:\n{RULES}\n\n{HIDDEN}",
        reply_markup=password_kb,
    )


@router.message(Register.phone)
async def register_phone_text(message: Message):
    await message.answer("👇 Pastdagi «📱 Raqamni yuborish» tugmasini bosing.", reply_markup=contact_kb)


# ===== 2-qadam: parol va takrori =====
async def take_password(message: Message, state: FSMContext, next_state):
    await delete_quietly(message)
    password = message.text or ""
    problem = accounts.password_problem(password)
    if problem:
        await message.answer(f"❗ {problem}\n\nBoshqa parol yozing:", reply_markup=password_kb)
        return
    # Xotirada parolning o'zi emas, xeshi turadi
    await state.update_data(pending=await asyncio.to_thread(accounts.hash_password, password))
    await state.set_state(next_state)
    await message.answer("🔁 Parolni yana bir marta yozing (tasdiqlash uchun):", reply_markup=password_kb)


async def confirmed_hash(message: Message, state: FSMContext, back_state):
    """Takroriy parol to'g'ri bo'lsa — xesh, aks holda None (va parolni qaytadan so'raydi)."""
    await delete_quietly(message)
    data = await state.get_data()
    if not await asyncio.to_thread(accounts.verify_password, message.text or "", data.get("pending", "")):
        await state.set_state(back_state)
        await message.answer("❗ Parollar bir xil emas. Parolni qaytadan yozing:", reply_markup=password_kb)
        return None
    return data["pending"]


@router.message(Register.password, F.text)
async def register_password(message: Message, state: FSMContext):
    await take_password(message, state, Register.confirm)


@router.message(Register.confirm, F.text)
async def register_confirm(message: Message, state: FSMContext):
    password_hash = await confirmed_hash(message, state, Register.password)
    if not password_hash:
        return
    phone = (await state.get_data())["phone"]
    user = message.from_user
    save_user(user)
    await state.clear()
    try:
        accounts.create_account(user.id, phone, password_hash)
    except sqlite3.IntegrityError:
        await message.answer(
            "❗ Bu raqam yoki Telegram hisobi allaqachon ro'yxatdan o'tgan. «🔐 Hisobim» ni bosing.",
            reply_markup=main_menu,
        )
        return
    await message.answer(
        "🎉 <b>Ro'yxatdan o'tdingiz!</b>\n\n"
        f"📱 Login: <b>{accounts.format_phone(phone)}</b>\n"
        "🔑 Parol: siz o'ylab topgan parol\n\n"
        "Endi ilovaga istalgan qurilmadan shu raqam va parol bilan kirasiz. Parolni hech kimga bermang.",
        reply_markup=main_menu,
    )
    if WEBAPP_URL:
        await message.answer("👇 Ilovani ochib, hoziroq boshlang", reply_markup=app_markup())


@router.message(Register.password)
@router.message(Register.confirm)
@router.message(ChangePassword.password)
@router.message(ChangePassword.confirm)
async def password_not_text(message: Message):
    await message.answer("✍️ Parolni matn ko'rinishida yozing.", reply_markup=password_kb)


# ===== Parolni o'zgartirish / unutilgan parol: /parol =====
async def change_start(message: Message, state: FSMContext, user_id):
    account = accounts.account_by_user(user_id)
    if not account:
        await account_show(message, state, user_id)
        return
    await state.clear()
    await state.set_state(ChangePassword.password)
    await message.answer(
        f"🔑 <b>Yangi parol</b> — {accounts.format_phone(account['phone'])}\n\n"
        f"Yangi parolni yozing:\n{RULES}\n\n{HIDDEN}",
        reply_markup=password_kb,
    )


@router.message(Command("parol"))
async def change_command(message: Message, state: FSMContext):
    await change_start(message, state, message.from_user.id)


@router.callback_query(F.data == "acc_pass")
async def change_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await change_start(callback.message, state, callback.from_user.id)


@router.message(ChangePassword.password, F.text)
async def change_password(message: Message, state: FSMContext):
    await take_password(message, state, ChangePassword.confirm)


@router.message(ChangePassword.confirm, F.text)
async def change_confirm(message: Message, state: FSMContext):
    password_hash = await confirmed_hash(message, state, ChangePassword.password)
    if not password_hash:
        return
    await state.clear()
    accounts.set_password_hash(message.from_user.id, password_hash)
    await message.answer(
        "✅ <b>Parol yangilandi!</b>\n\nBoshqa qurilmalardagi sessiyalar yopildi — u yerda yangi parol bilan kiring.",
        reply_markup=main_menu,
    )


# ===== Ilovadagi «Telegram raqamimni olish» (yoki shunchaki yuborilgan kontakt) =====
@router.message(F.contact)
async def contact_shared(message: Message):
    contact = message.contact
    if contact.user_id != message.from_user.id:
        await message.answer("❗ Faqat o'zingizning raqamingizni yuborish mumkin.", reply_markup=main_menu)
        return
    phone = accounts.normalize_phone(contact.phone_number)
    if not phone:
        await message.answer("😔 Hozircha faqat O'zbekiston (+998) raqamlari qabul qilinadi.", reply_markup=main_menu)
        return
    accounts.save_verified_phone(message.from_user.id, phone)
    account = accounts.account_by_user(message.from_user.id)
    if account and account["phone"] == phone:
        text = f"✅ Raqamingiz tasdiqlandi: <b>{html.escape(accounts.format_phone(phone))}</b>"
    elif account:
        text = "ℹ️ Raqam qabul qilindi, lekin hisobingiz boshqa raqamga bog'langan («🔐 Hisobim»)."
    else:
        text = (f"✅ Raqam tasdiqlandi: <b>{html.escape(accounts.format_phone(phone))}</b>\n\n"
                "Ilovada parol o'ylab topib, ro'yxatdan o'tishni yakunlang.")
    await message.answer(text, reply_markup=main_menu)
