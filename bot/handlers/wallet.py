import html
import json
import logging
import re
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from admins import OWNER_ID, Can, admin_ids, display_name, notify_owner
from config import (
    PAYMENT_CARDS, PENDING_MAX, SUPPORT_USERNAME, TOPUP_MAX, TOPUP_MIN, document_price, money,
    presentation_price, price_lines,
)
from database import (
    add_paid_order, add_payment, change_balance, get_balance, get_payment, get_web_order, last_transactions, now_str,
    pending_payments, release_paid_order, review_payment, save_user, user_waiting_order,
)
from handlers.articles import order_params as article_params, price_for_article
from handlers.documents import doc_price
from handlers.presentation import price_for
from handlers.start import show
from keyboards import (
    admin_reply_cancel_menu,
    order_pay_menu,
    payment_done_menu,
    payment_review_menu,
    topup_amount_menu,
    topup_check_menu,
    topup_done_menu,
    topup_rejected_menu,
    wallet_back_menu,
    wallet_menu,
)
from states import AdminReply, MakeArticle, MakeDocument, MakePresentation, TopUp

router = Router()
can_pay = Can("payments")  # cheklarni ko'rish / tasdiqlash huquqi (admins.py)
TOPUP_STATES = (TopUp.amount.state, TopUp.check.state)
KIND_LABELS = {"topup": "➕ To'ldirish", "charge": "➖ Xarid", "refund": "↩️ Qaytarildi", "admin": "⚙️ Admin"}
receiving = set()  # hozir cheki saqlanayotgan userlar (albom yuborilsa ikki marta yozilmasligi uchun)


def not_command(message: Message):
    # Holat ichida ham /start, /help kabi buyruqlar o'z handleriga o'tib ketishi uchun
    return not (message.text or "").startswith("/")


def support_line():
    return f"\n\n💬 Savollar uchun: @{SUPPORT_USERNAME}" if SUPPORT_USERNAME else ""


async def render(callback: CallbackQuery, text, markup):
    """show() kabi menyuni almashtiradi, lekin ko'rsatilgan xabarni qaytaradi."""
    with suppress(TelegramBadRequest):
        return await callback.message.edit_text(text, reply_markup=markup)
    if callback.message.photo:
        with suppress(TelegramBadRequest):
            await callback.message.delete()
    return await callback.message.answer(text, reply_markup=markup)


async def drop_markup(bot: Bot, chat_id, message_id):
    if message_id:
        with suppress(TelegramBadRequest):
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)


# ===== Hamyon =====
def wallet_text(user_id):
    pending = pending_payments(user_id)
    text = f"💳 <b>Hamyon</b>\n\n👛 Balans: <b>{money(get_balance(user_id))}</b>\n"
    if pending:
        text += f"⏳ Tekshiruvda: <b>{len(pending)} ta chek</b> ({money(sum(p['amount'] for p in pending))})\n"
    return text + (
        f"\n💰 <b>Narxlar:</b>\n{price_lines()}\n\n"
        "Hisobni istalgan summaga to'ldirasiz, har bir buyurtma uchun pul shu yerdan yechib boriladi."
        f"{support_line()}"
    )


async def leave_topup(state: FSMContext):
    if await state.get_state() in TOPUP_STATES:
        await state.set_state(None)


@router.callback_query(F.data == "wallet")
async def wallet(callback: CallbackQuery, state: FSMContext):
    save_user(callback.from_user)
    await leave_topup(state)
    await show(callback, wallet_text(callback.from_user.id), wallet_menu)
    await callback.answer()


@router.message(Command("hamyon"))
async def wallet_command(message: Message, state: FSMContext):
    save_user(message.from_user)
    await leave_topup(state)
    await message.answer(wallet_text(message.from_user.id), reply_markup=wallet_menu)


@router.callback_query(F.data == "wallet_history")
async def wallet_history(callback: CallbackQuery):
    lines = [
        f"{KIND_LABELS.get(kind, kind)} <b>{'+' if amount > 0 else '−'}{money(abs(amount))}</b>"
        f"{' — ' + html.escape(note) if note else ''} <i>({created[5:]})</i>"
        for amount, kind, note, created in last_transactions(callback.from_user.id)
    ]
    await show(callback, "📜 <b>Oxirgi amallar</b>\n\n" + ("\n".join(lines) or "Hali amallar yo'q."), wallet_back_menu)
    await callback.answer()


# ===== Hisobni to'ldirish =====
def topup_error(user_id):
    """To'ldirish mumkin bo'lmasa — sababini qaytaradi."""
    if not PAYMENT_CARDS or not OWNER_ID:
        return "To'lov hozircha sozlanmagan. Birozdan so'ng urinib ko'ring."
    if len(pending_payments(user_id)) >= PENDING_MAX:
        return f"Sizda {PENDING_MAX} ta chek tekshiruvda turibdi. Admin tasdiqlashini kuting 🙏"
    return None


def parse_amount(text):
    text = re.sub(r"so['‘’`]?m|сум|uzs", "", text.lower())
    digits = re.sub(r"[\s,.'‘’`]", "", text)
    return int(digits) if digits.isdecimal() and len(digits) <= 9 else None


def check_text(amount):
    cards = "\n\n".join(
        f"💳 <code>{number}</code>" + (f"\n👤 {html.escape(holder)}" if holder else "") for number, holder in PAYMENT_CARDS
    )
    return (
        "💳 <b>To'lov</b>\n\n"
        f"Quyidagi kartaga <b>{money(amount)}</b> o'tkazing:\n\n"
        f"{cards}\n\n"
        "<i>Karta raqamini bosib nusxalash mumkin.</i>\n\n"
        "So'ng to'lov <b>chekining rasmini</b> (skrinshot yoki PDF) shu yerga yuboring 📸\n"
        "Admin tekshirgach, summa hamyoningizga tushadi."
    )


@router.callback_query(F.data == "wallet_topup")
async def topup_start(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    save_user(callback.from_user)
    error = topup_error(user_id)
    if error:
        await callback.answer(error, show_alert=True)
        return
    current = await state.get_state()
    if current not in TOPUP_STATES:
        # Buyurtma tasdiqlash qadamidan kelgan bo'lsa — «Orqaga» o'sha yerga qaytaradi
        from_order = current in (MakePresentation.confirm.state, MakeDocument.confirm.state, MakeArticle.confirm.state)
        await state.update_data(topup_back="resume" if from_order else "wallet")
    data = await state.get_data()
    back = data.get("topup_back", "wallet")

    balance = get_balance(user_id)
    need = 0
    if back == "resume" and data.get("art_words") and data.get("art_type"):
        need = price_for_article(user_id, data["art_words"]) - balance
    elif back == "resume" and data.get("doc_kind") and data.get("doc_pages"):
        need = document_price(data["doc_kind"], data["doc_pages"]) - balance
    elif back == "resume" and data.get("slides"):
        need = presentation_price(data["slides"]) - balance
    suggest = None
    if need > 0:
        suggest = min(max(-(-need // 1000) * 1000, TOPUP_MIN), TOPUP_MAX)  # minglikka yaxlitlab
    text = f"➕ <b>Hisobni to'ldirish</b>\n\n👛 Balans: <b>{money(balance)}</b>\n"
    if need > 0:
        text += f"⭐ Buyurtma uchun yana <b>{money(need)}</b> kerak.\n"
    text += f"\nSummani tanlang yoki {money(TOPUP_MIN)} – {money(TOPUP_MAX)} oralig'ida yozing:"

    await state.set_state(TopUp.amount)
    sent = await render(callback, text, topup_amount_menu(suggest, back))
    if isinstance(sent, Message):
        await state.update_data(topup_msg=sent.message_id)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^topup:\d+$"))
async def topup_amount_button(callback: CallbackQuery, state: FSMContext):
    amount = int(callback.data.split(":")[1])
    error = topup_error(callback.from_user.id) or (None if TOPUP_MIN <= amount <= TOPUP_MAX else "Noto'g'ri summa.")
    if error:
        await callback.answer(error, show_alert=True)
        return
    await state.set_state(TopUp.check)
    await state.update_data(topup_amount=amount)
    sent = await render(callback, check_text(amount), topup_check_menu)
    if isinstance(sent, Message):
        await state.update_data(topup_msg=sent.message_id)
    await callback.answer()


@router.message(TopUp.amount, F.text, not_command)
async def topup_amount_text(message: Message, state: FSMContext, bot: Bot):
    amount = parse_amount(message.text)
    if amount is None or not TOPUP_MIN <= amount <= TOPUP_MAX:
        await message.answer(f"⚠️ {money(TOPUP_MIN)} dan {money(TOPUP_MAX)} gacha summa yozing. Masalan: <b>20000</b>")
        return
    error = topup_error(message.from_user.id)
    if error:
        await leave_topup(state)
        await message.answer(f"⚠️ {error}")
        return
    await state.set_state(TopUp.check)
    await state.update_data(topup_amount=amount)
    await drop_markup(bot, message.chat.id, (await state.get_data()).get("topup_msg"))
    sent = await message.answer(check_text(amount), reply_markup=topup_check_menu)
    await state.update_data(topup_msg=sent.message_id)


@router.message(TopUp.amount, not_command)
async def topup_amount_wrong(message: Message):
    await message.answer("✍️ Avval summani tanlang yoki son bilan yozing. Chekni keyingi qadamda yuborasiz.")


@router.message(TopUp.check, F.photo | F.document)
async def topup_receipt(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    if message.photo:
        file_id, file_type = message.photo[-1].file_id, "photo"
    else:
        mime = message.document.mime_type or ""
        if not (mime.startswith("image/") or mime == "application/pdf"):
            await message.answer("⚠️ Chekni rasm yoki PDF ko'rinishida yuboring.")
            return
        file_id, file_type = message.document.file_id, "document"
    if user_id in receiving:
        return
    receiving.add(user_id)
    try:
        data = await state.get_data()
        amount = data.get("topup_amount")
        if await state.get_state() != TopUp.check.state or not amount:
            return  # bir nechta rasm birga yuborilgan — birinchisi allaqachon qabul qilindi
        error = topup_error(user_id)
        if error:
            await leave_topup(state)
            await message.answer(f"⚠️ {error}")
            return
        save_user(message.from_user)
        order_id = data.get("topup_order")
        payment_id = add_payment(user_id, amount, file_id, file_type, order_id)
        await state.set_state(None)
        await state.update_data(topup_amount=None, topup_msg=None, topup_order=None)
    finally:
        receiving.discard(user_id)

    await drop_markup(bot, message.chat.id, data.get("topup_msg"))
    if order_id:
        order = get_web_order(order_id)
        after = (f"📦 Buyurtma: {order_label(order)}\n\n"
                 "Admin tasdiqlagach, buyurtmangiz <b>avtomatik tayyorlanib</b>, shu chatga yuboriladi ⏳")
    else:
        after = "Admin tekshirgach, summa hamyoningizga tushadi va sizga xabar beramiz ⏳"
    await message.answer(
        "✅ <b>Chek qabul qilindi!</b>\n\n"
        f"🧾 To'lov #{payment_id} — <b>{money(amount)}</b>\n"
        f"{after}"
        f"{support_line()}"
    )
    await send_payment_to_admin(bot, get_payment(payment_id))


@router.message(TopUp.check, not_command)
async def topup_receipt_wrong(message: Message):
    await message.answer("📸 To'lov chekining <b>rasmini</b> yuboring yoki «❌ Bekor qilish» ni bosing.")


# ===== Buyurtma uchun to'lov: to'laydi → admin tasdiqlaydi → buyurtma o'zi tayyorlanadi =====
ORDER_PAY_MIN = 1000  # juda kichik qoldiq bo'lsa ham kamida shuncha (ortgani balansda qoladi)
KIND_NAMES = {"pres": "📊 Taqdimot", "referat": "📄 Referat", "mustaqil": "✍️ Mustaqil ish", "kurs": "📚 Kurs ishi",
              "maqola": "📝 Maqola"}


def order_label(order):
    """«📊 Taqdimot · 15 slayd — «Mavzu»» — admin va user uchun buyurtmaning qisqa tavsifi."""
    if not order:
        return "—"
    params = json.loads(order["params"])
    if order["kind"] == "maqola":
        size = f"~{params['words']} so'z"
    else:
        size = f"{params['slides']} slayd" if order["kind"] == "pres" else f"{params['pages']} bet"
    return f"{KIND_NAMES.get(order['kind'], order['kind'])} · {size} — «{html.escape(params['topic'][:80])}»"


def order_from_state(state_name, data, user_id):
    """Tasdiqlash qadamidagi sozlamalardan buyurtma: (kind, params, narx). Web ilova bilan bir xil ko'rinish."""
    if state_name == MakePresentation.confirm.state:
        params = {"topic": data["topic"], "plans": data["plans"], "slides": data["slides"], "lang": data["lang"],
                  "theme": data["theme"], "author": data.get("author") or "", "fmt": data.get("fmt", "pptx")}
        return "pres", params, price_for(user_id, data["slides"])
    if state_name == MakeArticle.confirm.state:
        params = article_params(data)
        return "maqola", params, price_for_article(user_id, params["words"])
    kind = data["doc_kind"]
    params = {"topic": data["doc_topic"], "pages": data["doc_pages"], "lang": data["doc_lang"],
              "fmt": data.get("doc_fmt", "docx")}
    return kind, params, doc_price(user_id, kind, data["doc_pages"])


@router.callback_query(F.data == "order_pay", StateFilter(MakePresentation.confirm, MakeDocument.confirm, MakeArticle.confirm))
async def order_pay(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    save_user(callback.from_user)
    kind, params, price = order_from_state(await state.get_state(), await state.get_data(), user_id)
    need = price - get_balance(user_id)
    if need <= 0:
        await callback.answer("Balansingiz yetarli — «✨ Yaratish» ni bosing 🙂", show_alert=True)
        return
    error = topup_error(user_id)
    if not error and user_waiting_order(user_id):
        error = "Oldingi buyurtmangiz hali tayyorlanmoqda yoki to'lovi tekshiruvda. Biroz kuting 🙏"
    if error:
        await callback.answer(error, show_alert=True)
        return

    amount = max(need, ORDER_PAY_MIN)
    order_id = add_paid_order(user_id, kind, params, price)
    await state.set_state(TopUp.check)
    await state.update_data(topup_amount=amount, topup_order=order_id, topup_back="wallet")
    extra = f"\n💡 {money(amount - need)} balansingizda qoladi." if amount > need else ""
    sent = await render(
        callback,
        check_text(amount).replace("💳 <b>To'lov</b>", f"💳 <b>Buyurtma uchun to'lov</b>\n📦 {order_label(get_web_order(order_id))}")
        + "\n\n✨ Admin tasdiqlagach, buyurtmangiz <b>avtomatik tayyorlanib</b>, shu chatga yuboriladi." + extra,
        order_pay_menu(order_id),
    )
    if isinstance(sent, Message):
        await state.update_data(topup_msg=sent.message_id)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^order_pay_cancel:\d+$"))
async def order_pay_cancel(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split(":")[1])
    order = get_web_order(order_id)
    if order and order["user_id"] == callback.from_user.id:
        release_paid_order(order_id, False, "Buyurtma bekor qilindi.")
    await leave_topup(state)
    await state.update_data(topup_order=None)
    await show(callback, "❌ Buyurtma bekor qilindi.\n\n👇 Pastdagi menyudan kerakli xizmatni tanlang.", None)
    await callback.answer("Bekor qilindi")


# ===== Admin: cheklarni tekshirish =====
def payment_caption(payment, status=""):
    name = html.escape(payment["full_name"] or "Noma'lum")
    username = f"@{payment['username']}" if payment["username"] else "yo'q"
    lines = [
        f"🧾 <b>To'lov #{payment['id']}</b>",
        "",
        f"👤 <a href=\"tg://user?id={payment['user_id']}\">{name}</a>",
        f"🔗 Username: {username}",
        f"🆔 ID: <code>{payment['user_id']}</code>",
        f"💰 Summa: <b>{money(payment['amount'])}</b>",
        f"👛 Hozirgi balansi: {money(get_balance(payment['user_id']))}",
        f"🕘 {payment['created_at']}",
    ]
    if payment.get("order_id"):
        order = get_web_order(payment["order_id"])
        lines += ["", f"📦 <b>Buyurtma uchun:</b> {order_label(order)}",
                  "✅ Tasdiqlasangiz — buyurtma avtomatik tayyorlanib, userga yuboriladi."]
    if status:
        lines += ["", status]
    return "\n".join(lines)


# To'lov → adminlarga yuborilgan chek xabarlari [(chat_id, message_id)]: bir admin ko'rib chiqsa, qolganlaridagi
# xabar ham «✅ Tasdiqlandi · kim» bo'lib yangilanadi (ikki admin bir chekni qayta ko'rmasin)
_review_messages = {}


async def send_payment_to_admin(bot: Bot, payment, to=None):
    """Chekni tekshiruvga yuboradi: barcha adminlarga (to=None) yoki bitta adminga (/tolovlar)."""
    send = bot.send_photo if payment["file_type"] == "photo" else bot.send_document
    for admin_id in ([to] if to else admin_ids("payments")):
        try:
            sent = await send(admin_id, payment["file_id"], caption=payment_caption(payment),
                              reply_markup=payment_review_menu(payment["id"]))
            _review_messages.setdefault(payment["id"], []).append((admin_id, sent.message_id))
        except Exception:
            # Admin botni ishga tushirmagan bo'lsa ham to'lov bazada qoladi — /tolovlar orqali ko'riladi
            logging.warning("To'lov #%s adminga (%s) yuborilmadi", payment["id"], admin_id)
    if len(_review_messages) > 500:  # xotira to'lib ketmasin — eng eskilari
        for old in sorted(_review_messages)[:100]:
            _review_messages.pop(old, None)


async def mark_reviewed(bot: Bot, payment, approve, reviewer_id, skip=None):
    """Barcha adminlardagi shu chek xabarini yakuniy holatga keltiradi."""
    status = (("✅ <b>Tasdiqlandi</b>" if approve else "❌ <b>Rad etildi</b>")
              + f" · {html.escape(display_name(reviewer_id))} · {now_str()}")
    for chat_id, message_id in _review_messages.pop(payment["id"], []):
        if (chat_id, message_id) == skip:
            continue
        with suppress(Exception):
            await bot.edit_message_caption(chat_id=chat_id, message_id=message_id,
                                           caption=payment_caption(payment, status),
                                           reply_markup=payment_done_menu(payment["id"]))
    return status


async def notify_user(bot: Bot, payment, approved):
    order = get_web_order(payment["order_id"]) if payment.get("order_id") else None
    if order and approved:
        text = (
            "✅ <b>To'lovingiz tasdiqlandi!</b>\n\n"
            f"📦 {order_label(order)}\n\n"
            "⏳ Buyurtmangiz tayyorlanmoqda — odatda 1 daqiqa. Tayyor bo'lishi bilan shu yerga yuboriladi 🚀"
        )
        markup = None
    elif order:
        text = (
            f"❌ <b>To'lov #{payment['id']} tasdiqlanmadi</b>\n\n"
            f"📦 {order_label(order)} — bekor qilindi.\n"
            "Chek noto'g'ri yoki pul kartaga kelib tushmagan bo'lishi mumkin. Tekshirib, buyurtmani qayta bering."
            f"{support_line()}"
        )
        markup = None
    elif approved:
        text = (
            "✅ <b>To'lovingiz tasdiqlandi!</b>\n\n"
            f"🧾 To'lov #{payment['id']}: <b>+{money(payment['amount'])}</b>\n"
            f"👛 Balans: <b>{money(get_balance(payment['user_id']))}</b>\n\n"
            "Endi buyurtma berishingiz mumkin 🚀"
        )
        markup = topup_done_menu
    else:
        text = (
            f"❌ <b>To'lov #{payment['id']} tasdiqlanmadi</b>\n\n"
            f"Summa: {money(payment['amount'])}\n"
            "Chek noto'g'ri yoki pul kartaga kelib tushmagan bo'lishi mumkin. Tekshirib, qayta yuboring."
            f"{support_line()}"
        )
        markup = topup_rejected_menu
    try:
        await bot.send_message(payment["user_id"], text, reply_markup=markup)
        return True
    except (TelegramForbiddenError, TelegramBadRequest):
        return False


async def apply_review(bot: Bot, payment_id, approve, reviewer_id=None, skip=None):
    """Chekni tasdiqlash / rad etish — bot tugmasi va web admin panel uchun umumiy.
    reviewer_id — kim ko'rib chiqdi (boshqa adminlardagi xabar yangilanadi, qo'shimcha admin bo'lsa egaga xabar).
    Natija: (ok, matn, payment). ok=False — o'zgarmadi (topilmadi yoki allaqachon ko'rilgan)."""
    if not review_payment(payment_id, approve):
        payment = get_payment(payment_id)
        if not payment:
            return False, "To'lov topilmadi.", None
        if payment["status"] == "pending":
            return False, "User bazada topilmadi — balansga qo'shib bo'lmadi.", payment
        return False, "Bu to'lov allaqachon ko'rib chiqilgan.", payment
    payment = get_payment(payment_id)
    # Buyurtma uchun to'lov: tasdiqlansa — buyurtma navbatga, bot uni tayyorlab userga yuboradi
    if payment.get("order_id"):
        release_paid_order(payment["order_id"], approve)
    if reviewer_id:
        await mark_reviewed(bot, payment, approve, reviewer_id, skip)
        await notify_owner(bot, reviewer_id, f"to'lov #{payment_id} ({money(payment['amount'])}) — "
                                             + ("✅ tasdiqladi" if approve else "❌ rad etdi"))
    if await notify_user(bot, payment, approve):
        return True, "Tasdiqlandi ✅" if approve else "Rad etildi ❌", payment
    return True, "Saqlandi, lekin userga xabar yetmadi (botni bloklagan).", payment


@router.callback_query(can_pay, F.data.regexp(r"^pay_(ok|no):\d+$"))
async def payment_review(callback: CallbackQuery, bot: Bot):
    approve = callback.data.startswith("pay_ok")
    payment_id = int(callback.data.split(":")[1])
    here = (callback.message.chat.id, callback.message.message_id)
    ok, text, payment = await apply_review(bot, payment_id, approve, callback.from_user.id, skip=here)
    if not ok:
        if payment and payment["status"] != "pending":
            with suppress(TelegramBadRequest):
                await callback.message.edit_reply_markup(reply_markup=payment_done_menu(payment_id))
        await callback.answer(text, show_alert=True)
        return
    status = (("✅ <b>Tasdiqlandi</b>" if approve else "❌ <b>Rad etildi</b>")
              + f" · {html.escape(display_name(callback.from_user.id))} · {now_str()}")
    with suppress(TelegramBadRequest):
        await callback.message.edit_caption(
            caption=payment_caption(payment, status), reply_markup=payment_done_menu(payment_id)
        )
    await callback.answer(text, show_alert="yetmadi" in text)


@router.callback_query(can_pay, F.data.regexp(r"^pay_msg:\d+$"))
async def admin_reply_start(callback: CallbackQuery, state: FSMContext):
    payment = get_payment(int(callback.data.split(":")[1]))
    if not payment:
        await callback.answer("To'lov topilmadi.", show_alert=True)
        return
    await state.set_state(AdminReply.text)
    await state.update_data(reply_to=payment["user_id"], reply_payment=payment["id"])
    await callback.message.answer(
        f"💬 <b>{html.escape(payment['full_name'] or 'User')}</b> ga (to'lov #{payment['id']}) "
        "yuboriladigan xabarni yozing.\nMatn, rasm yoki fayl bo'lishi mumkin.",
        reply_markup=admin_reply_cancel_menu,
    )
    await callback.answer()


@router.callback_query(can_pay, F.data == "pay_reply_cancel")
async def admin_reply_cancel(callback: CallbackQuery, state: FSMContext):
    if await state.get_state() == AdminReply.text.state:
        await state.set_state(None)
    with suppress(TelegramBadRequest):
        await callback.message.edit_text("Bekor qilindi.")
    await callback.answer()


@router.message(AdminReply.text, can_pay, not_command)
async def admin_reply_send(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.set_state(None)
    user_id = data.get("reply_to")
    if not user_id:
        await message.answer("⚠️ Qabul qiluvchi topilmadi. Chek ostidagi «💬 Userga yozish» ni qayta bosing.")
        return
    try:
        await bot.send_message(user_id, f"📩 <b>Admindan xabar</b> (to'lov #{data.get('reply_payment')})")
        await message.copy_to(user_id)
    except (TelegramForbiddenError, TelegramBadRequest):
        await message.answer("⚠️ Yuborilmadi: user botni bloklagan yoki chat topilmadi.")
        return
    await message.answer("✅ Xabar userga yuborildi.")


@router.message(Command("tolovlar"), can_pay)
async def admin_pending(message: Message, bot: Bot):
    payments = pending_payments()
    if not payments:
        await message.answer("✅ Tekshiruvni kutayotgan to'lov yo'q.")
        return
    await message.answer(f"⏳ Tekshiruvni kutmoqda: <b>{len(payments)} ta</b>")
    for payment in payments:
        await send_payment_to_admin(bot, payment, to=message.chat.id)


BALANCE_USAGE = (
    "Foydalanish:\n"
    "<code>/balans USER_ID</code> — balansni ko'rish\n"
    "<code>/balans USER_ID 20000</code> — qo'shish\n"
    "<code>/balans USER_ID -5000</code> — ayirish"
)


@router.message(Command("balans"), Can("balance"))
async def admin_balance(message: Message, command: CommandObject, bot: Bot):
    args = (command.args or "").split()
    if not args or not args[0].isdecimal() or len(args) > 2:
        await message.answer(BALANCE_USAGE)
        return
    user_id = int(args[0])
    if len(args) == 1:
        await message.answer(f"👛 <code>{user_id}</code> balansi: <b>{money(get_balance(user_id))}</b>")
        return
    if not re.fullmatch(r"[+-]?\d{1,9}", args[1]) or int(args[1]) == 0:
        await message.answer(BALANCE_USAGE)
        return
    amount = int(args[1])
    if not change_balance(user_id, amount, "admin", "Admin tomonidan"):
        await message.answer("⚠️ User topilmadi yoki balans manfiy bo'lib qoladi.")
        return
    change = f"{'+' if amount > 0 else '−'}{money(abs(amount))}"
    balance = money(get_balance(user_id))
    await message.answer(f"✅ <code>{user_id}</code>: {change}\n👛 Yangi balans: <b>{balance}</b>")
    await notify_owner(bot, message.from_user.id, f"<code>{user_id}</code> balansini o'zgartirdi: {change}")
    with suppress(TelegramForbiddenError, TelegramBadRequest):
        await bot.send_message(user_id, f"💳 Balansingiz admin tomonidan o'zgartirildi: <b>{change}</b>\n👛 Balans: <b>{balance}</b>")
