"""«🎨 Boshqa dizaynda olish» — diplom ishi va dissertatsiya fayli ostidagi tugma (taqdimotdagidek).

Tugma bosilganda shu xabarning o'zida dizaynlar ro'yxati ochiladi; tanlangach hujjat AI'siz, darhol yangi
dizaynda qayta yig'iladi va chatga yangi fayl bo'lib keladi. Matn o'zgarmaydi, pul yechilmaydi."""
import html
import logging
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from diploma.designs import DOC_DESIGNS, design_key

Button = InlineKeyboardButton


def design_menu(prefix, item_id, current):
    buttons = [
        Button(text=f"{'✅ ' if key == current else ''}{design['name']}", callback_data=f"{prefix}:redesign:{item_id}:{key}")
        for key, design in DOC_DESIGNS.items()
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([Button(text="⬅️ Orqaga", callback_data=f"{prefix}:result:{item_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def register(router: Router, prefix, service, owned, error_cls):
    """prefix — «dip» yoki «dis»; service — diploma.service / dissertation.service; owned — handlerdagi tekshiruv.
    Umumiy «eskirgan tugma» handleridan OLDIN chaqirilishi kerak."""

    @router.callback_query(F.data.startswith(f"{prefix}:design:"))
    async def show_designs(callback: CallbackQuery):
        found = owned(callback)
        if not found:
            await callback.answer("Topilmadi", show_alert=True)
            return
        with suppress(TelegramBadRequest):
            await callback.message.edit_reply_markup(reply_markup=design_menu(prefix, found[0], design_key(found[3])))
        await callback.answer("Yangi dizaynni tanlang 🎨")

    @router.callback_query(F.data.startswith(f"{prefix}:result:"))
    async def back_to_result(callback: CallbackQuery):
        found = owned(callback)
        if not found:
            await callback.answer("Topilmadi", show_alert=True)
            return
        with suppress(TelegramBadRequest):
            await callback.message.edit_reply_markup(reply_markup=service.edit_markup(found[0]))
        await callback.answer()

    @router.callback_query(F.data.startswith(f"{prefix}:redesign:"))
    async def redesign(callback: CallbackQuery, bot: Bot):
        found = owned(callback)
        if not found or found[1] not in DOC_DESIGNS:
            await callback.answer("Topilmadi", show_alert=True)
            return
        item_id, key, _, project = found
        if key == design_key(project):
            await callback.answer("Bu dizayn allaqachon tanlangan 🙂")
            return
        if service.busy(item_id):
            await callback.answer("⏳ Hozir tayyorlanmoqda, biroz kuting.", show_alert=True)
            return
        await callback.answer(f"🎨 {DOC_DESIGNS[key]['name']}: {DOC_DESIGNS[key]['about']}", show_alert=False)
        with suppress(TelegramBadRequest):
            await callback.message.edit_reply_markup(reply_markup=None)
        async with service.lock(item_id):
            try:
                service.set_design(item_id, key)
                await service.export(bot, item_id, callback.from_user.id, "docx")
                return
            except error_cls as e:
                text = f"⚠️ {html.escape(str(e))}"
            except Exception:
                logging.exception("Hujjatni boshqa dizaynda yig'ishda xato (%s %s)", prefix, item_id)
                text = "😕 Qayta rasmiylashtirishda xato yuz berdi. Iltimos, qayta urinib ko'ring."
        # Tugmalarni qaytaramiz — user yana urinib ko'rishi mumkin
        with suppress(TelegramBadRequest):
            await callback.message.edit_reply_markup(reply_markup=service.edit_markup(item_id))
        await callback.message.answer(text)
