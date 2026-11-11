"""Adminlar va ularning huquqlari — faqat bot egasi uchun (.env → ADMIN_ID).

/adminlar (yoki admin paneldagi «👥 Adminlar va huquqlar»): ro'yxat, qo'shish, o'chirish, huquq berish.
Qo'shish: Telegram'ning «foydalanuvchini tanlash» tugmasi (kontaktlardan bitta bosish) yoki Telegram ID yoziladi.
Yangi admin standart bo'yicha faqat cheklarni tasdiqlaydi (admins.DEFAULT_PERMS); qolgan huquqlarni ega «⚙️ Huquqlar»
ekranida yoqadi. Har bir adminning buyruqlar menyusi uning huquqlariga qarab o'rnatiladi.
Web admin panel ham shu funksiyalardan foydalanadi (handlers/web.py → «admins» buyurtmasi)."""
import html
import logging
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BotCommand, BotCommandScopeChat, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
    KeyboardButtonRequestUsers, Message, ReplyKeyboardMarkup,
)

from admins import (
    OWNER_ID, PERMS, AdminError, IsOwner, add_admin, admin_ids, display_name, extra_admins, is_admin, is_owner,
    perms_of, perms_text, remove_admin, set_perms,
)
from config import ADMINS_EXTRA_MAX
from keyboards import main_menu
from states import ManageAdmins

router = Router()
router.message.filter(IsOwner())
router.callback_query.filter(IsOwner())

Button = InlineKeyboardButton
PICK_REQUEST = 7  # KeyboardButtonRequestUsers.request_id
CANCEL_TEXT = "❌ Bekor qilish"

USER_COMMANDS = [
    BotCommand(command="start", description="Bosh menyu"),
    BotCommand(command="taqdimot", description="Taqdimot yaratish"),
    BotCommand(command="diplom", description="Diplom ishi"),
    BotCommand(command="dissertatsiya", description="Dissertatsiya"),
    BotCommand(command="maqola", description="Maqola yaratish"),
    BotCommand(command="hamyon", description="Balans va to'ldirish"),
    BotCommand(command="ai", description="AI yordamchi — tez reja va matn"),
    BotCommand(command="royxat", description="Ro'yxatdan o'tish (ilova uchun login)"),
    BotCommand(command="parol", description="Parolni o'zgartirish / tiklash"),
    BotCommand(command="help", description="Yordam"),
]
# Admin buyruqlari — qaysi huquq bilan ko'rinadi (None — har qanday admin)
ADMIN_COMMANDS = [
    (None, BotCommand(command="admin", description="🛠 Admin panel")),
    ("payments", BotCommand(command="tolovlar", description="Tekshiruvdagi cheklar")),
    ("stats", BotCommand(command="stats", description="Statistika")),
    ("stats", BotCommand(command="api", description="🔌 API limitlari va qoldiq")),
    ("balance", BotCommand(command="balans", description="User balansini o'zgartirish")),
    ("broadcast", BotCommand(command="ommabop", description="Ilovadagi ommabop materiallar")),
]


# ===== Buyruqlar menyusi =====
def commands_for(user_id):
    perms = perms_of(user_id)
    commands = USER_COMMANDS + [cmd for perm, cmd in ADMIN_COMMANDS if perm is None or perm in perms]
    if is_owner(user_id):
        commands.append(BotCommand(command="adminlar", description="👥 Adminlar va huquqlar"))
    return commands


async def set_admin_menu(bot: Bot, user_id):
    """Admin buyruqlari menyuda faqat adminga va faqat huquqiga mos ko'rinadi. /start bosmagan bo'lsa — jim o'tadi."""
    try:
        await bot.set_my_commands(commands_for(user_id), scope=BotCommandScopeChat(chat_id=user_id))
    except TelegramAPIError as error:
        logging.warning("Admin %s menyusi o'rnatilmadi (%s) — botga /start bosgach qayta o'rnatiladi", user_id, error)


async def clear_admin_menu(bot: Bot, user_id):
    with suppress(TelegramAPIError):
        await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=user_id))


async def setup_menus(bot: Bot):
    """Bot ishga tushganda: hamma uchun oddiy menyu, har bir adminga — huquqiga mos admin menyusi."""
    await bot.set_my_commands(USER_COMMANDS)
    for user_id in admin_ids():
        await set_admin_menu(bot, user_id)


# ===== Qo'shish / o'chirish / huquqlar (bot va web admin panel uchun umumiy) =====
async def notify(bot: Bot, user_id, text):
    try:
        await bot.send_message(user_id, text)
        return True
    except TelegramAPIError:
        return False


async def grant(bot: Bot, owner_id, user_id, name=None):
    """Admin qo'shadi (standart huquq — cheklar), unga xabar yuboradi va menyusini o'rnatadi."""
    add_admin(user_id, owner_id, name)  # AdminError — sababi bilan
    await set_admin_menu(bot, user_id)
    reached = await notify(
        bot, user_id,
        "🛠 <b>Siz MagicSlayd botida admin qilib tayinlandingiz!</b>\n\n"
        f"🔑 <b>Huquqlaringiz:</b>\n{perms_text(perms_of(user_id))}\n\n"
        "• /admin — admin panel\n"
        "• Yangi to'lov cheklari sizga keladi — ✅ / ❌ bilan ko'rib chiqasiz\n\n"
        "⚠️ Pul bilan bog'liq amallaringiz (chek, balans) haqida bot egasiga xabar boradi.",
    )
    name = html.escape(display_name(user_id))
    return f"✅ <b>{name}</b> admin qilindi (huquq: 💳 cheklar). Boshqa huquqlarni «⚙️ Huquqlar» da berasiz." + (
        "" if reached else "\n\n⚠️ Unga xabar yetmadi — u botga hali /start bosmagan. /start bosgach admin menyusi chiqadi.")


async def revoke(bot: Bot, owner_id, user_id):
    name = html.escape(display_name(user_id))
    remove_admin(user_id, owner_id)  # AdminError — sababi bilan
    await clear_admin_menu(bot, user_id)
    await notify(bot, user_id, "ℹ️ Sizning MagicSlayd botidagi admin huquqingiz bekor qilindi.")
    return f"🗑 <b>{name}</b> adminlikdan olindi."


async def update_perms(bot: Bot, owner_id, user_id, perms, announce=True):
    """Huquqlarni saqlaydi, menyuni yangilaydi va (announce) adminga yangi ro'yxatni yuboradi."""
    clean = set_perms(user_id, perms, owner_id)  # AdminError — sababi bilan
    await set_admin_menu(bot, user_id)
    if announce:
        await notify(bot, user_id, f"🔑 <b>Admin huquqlaringiz yangilandi:</b>\n{perms_text(clean)}\n\n/admin — admin panel")
    return clean


# ===== Ko'rinish =====
def short_perms(perms):
    return " ".join(PERMS[p].split(" ", 1)[0] for p in PERMS if p in perms) or "—"


def list_view():
    extras = extra_admins()
    lines = ["👥 <b>Adminlar va huquqlar</b>", "",
             f"👑 <b>{html.escape(display_name(OWNER_ID))}</b> — bot egasi (siz), barcha huquqlar"]
    for i, admin in enumerate(extras, 1):
        name = html.escape(admin["full_name"] or f"ID {admin['user_id']}")
        username = f" (@{html.escape(admin['username'])})" if admin.get("username") else ""
        lines.append(f"\n🛠 {i}. <b>{name}</b>{username} · <code>{admin['user_id']}</code>\n"
                     f"     Huquqlar: {short_perms(admin['perms'])}")
    lines += ["", f"Qo'shimcha adminlar: <b>{len(extras)}/{ADMINS_EXTRA_MAX}</b>",
              "Belgilar: " + " · ".join(PERMS[p] for p in PERMS),
              "", "Yangi admin faqat cheklarni tasdiqlaydi — qolgan huquqlarni «⚙️» orqali o'zingiz berasiz."]
    rows = []
    for admin in extras:
        label = (admin["full_name"] or str(admin["user_id"]))[:22]
        rows.append([Button(text=f"⚙️ {label}", callback_data=f"admins:perms:{admin['user_id']}"),
                     Button(text="❌ O'chirish", callback_data=f"admins:del:{admin['user_id']}")])
    if len(extras) < ADMINS_EXTRA_MAX:
        rows.append([Button(text="➕ Admin qo'shish", callback_data="admins:add")])
    rows.append([Button(text="⬅️ Admin panel", callback_data="adm:home")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def perms_view(user_id):
    perms = perms_of(user_id)
    text = (f"⚙️ <b>{html.escape(display_name(user_id))}</b> — huquqlar\n\n"
            "Bosib yoqing (✅) yoki o'chiring (⬜). O'zgarish darhol saqlanadi.\n"
            "«✅ Tayyor» bosilganda adminga yangi huquqlari ro'yxati yuboriladi.")
    rows = [[Button(text=f"{'✅' if perm in perms else '⬜'} {label}", callback_data=f"admins:perm:{user_id}:{perm}")]
            for perm, label in PERMS.items()]
    rows.append([Button(text="✅ Tayyor", callback_data=f"admins:done:{user_id}"),
                 Button(text="⬅️ Ro'yxat", callback_data="admins:list")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def edit_or_send(callback: CallbackQuery, text, markup):
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramAPIError:
        await callback.message.answer(text, reply_markup=markup)


def pick_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Kontaktlardan tanlash", request_users=KeyboardButtonRequestUsers(
                request_id=PICK_REQUEST, user_is_bot=False, max_quantity=1, request_name=True, request_username=True))],
            [KeyboardButton(text=CANCEL_TEXT)],
        ],
        resize_keyboard=True, one_time_keyboard=True,
    )


# ===== Ro'yxat =====
@router.message(Command("adminlar"))
async def admins_command(message: Message, state: FSMContext):
    await state.set_state(None)
    text, markup = list_view()
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "admins:list")
async def admins_list(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await callback.answer()
    await edit_or_send(callback, *list_view())


# ===== Qo'shish =====
@router.callback_query(F.data == "admins:add")
async def admins_add(callback: CallbackQuery, state: FSMContext):
    if len(extra_admins()) >= ADMINS_EXTRA_MAX:
        await callback.answer(f"Ko'pi bilan {ADMINS_EXTRA_MAX} ta qo'shimcha admin bo'ladi.", show_alert=True)
        return
    await state.set_state(ManageAdmins.pick)
    await callback.answer()
    await callback.message.answer(
        "➕ <b>Yangi admin</b>\n\n"
        "Pastdagi <b>«👤 Kontaktlardan tanlash»</b> tugmasini bosing va odamni tanlang.\n"
        "Yoki uning <b>Telegram ID</b> raqamini yozing (masalan <code>123456789</code> — @userinfobot dan biladi).\n\n"
        "🔑 Yangi admin faqat cheklarni tasdiqlaydi. Boshqa huquqlarni keyin «⚙️ Huquqlar» da berasiz.",
        reply_markup=pick_keyboard(),
    )


async def finish_pick(message: Message, state: FSMContext, bot: Bot, user_id, name=None):
    await state.set_state(None)
    try:
        result = await grant(bot, message.from_user.id, user_id, name)
    except AdminError as error:
        await message.answer(f"⚠️ {error}", reply_markup=main_menu)
        return
    await message.answer(result, reply_markup=main_menu)
    text, markup = list_view()
    await message.answer(text, reply_markup=markup)


@router.message(ManageAdmins.pick, F.users_shared)
async def admins_picked(message: Message, state: FSMContext, bot: Bot):
    shared = message.users_shared.users[0]
    name = " ".join(filter(None, (shared.first_name, shared.last_name))) or None
    await finish_pick(message, state, bot, shared.user_id, name)


@router.message(ManageAdmins.pick, F.text == CANCEL_TEXT)
async def admins_pick_cancel(message: Message, state: FSMContext):
    await state.set_state(None)
    await message.answer("Bekor qilindi.", reply_markup=main_menu)
    text, markup = list_view()
    await message.answer(text, reply_markup=markup)


@router.message(ManageAdmins.pick, F.text.regexp(r"^\s*\d{5,15}\s*$"))
async def admins_typed_id(message: Message, state: FSMContext, bot: Bot):
    await finish_pick(message, state, bot, int(message.text.strip()))


@router.message(ManageAdmins.pick)
async def admins_pick_wrong(message: Message):
    await message.answer("👆 «👤 Kontaktlardan tanlash» tugmasini bosing yoki Telegram ID raqamini yozing. "
                         f"Chiqish: «{CANCEL_TEXT}».")


# ===== Huquqlar =====
@router.callback_query(F.data.regexp(r"^admins:perms:\d+$"))
async def admins_perms(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[2])
    if not is_admin(user_id) or is_owner(user_id):
        await callback.answer("Bu foydalanuvchi qo'shimcha admin emas.", show_alert=True)
        return
    await callback.answer()
    await edit_or_send(callback, *perms_view(user_id))


@router.callback_query(F.data.regexp(r"^admins:perm:\d+:\w+$"))
async def admins_toggle(callback: CallbackQuery, bot: Bot):
    _, _, user_id, perm = callback.data.split(":")
    user_id = int(user_id)
    perms = perms_of(user_id)
    perms = perms - {perm} if perm in perms else perms | {perm}
    try:
        await update_perms(bot, callback.from_user.id, user_id, perms, announce=False)
    except AdminError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer(("✅ Berildi: " if perm in perms else "⬜ Olindi: ") + PERMS.get(perm, perm)[:150])
    await edit_or_send(callback, *perms_view(user_id))


@router.callback_query(F.data.regexp(r"^admins:done:\d+$"))
async def admins_perms_done(callback: CallbackQuery, bot: Bot):
    user_id = int(callback.data.split(":")[2])
    try:
        await update_perms(bot, callback.from_user.id, user_id, perms_of(user_id), announce=True)
    except AdminError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer("Saqlandi — adminga xabar yuborildi")
    await edit_or_send(callback, *list_view())


# ===== O'chirish =====
@router.callback_query(F.data.regexp(r"^admins:del:\d+$"))
async def admins_delete_ask(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[2])
    await callback.answer()
    await edit_or_send(
        callback,
        f"❓ <b>{html.escape(display_name(user_id))}</b> adminlikdan olinsinmi?\n\n"
        "U admin paneldan foydalana olmaydi va cheklar unga kelmaydi.",
        InlineKeyboardMarkup(inline_keyboard=[
            [Button(text="🗑 Ha, olib tashlash", callback_data=f"admins:delok:{user_id}")],
            [Button(text="⬅️ Yo'q, orqaga", callback_data="admins:list")],
        ]),
    )


@router.callback_query(F.data.regexp(r"^admins:delok:\d+$"))
async def admins_delete(callback: CallbackQuery, bot: Bot):
    user_id = int(callback.data.split(":")[2])
    try:
        result = await revoke(bot, callback.from_user.id, user_id)
    except AdminError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer("O'chirildi")
    text, markup = list_view()
    await edit_or_send(callback, f"{result}\n\n{text}", markup)
