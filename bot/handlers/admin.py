"""Admin paneli: /admin — statistika, hamma userlarga xabar (bot + ilova), forward, yuborilganlar, to'lovlar,
user qidirish (balans, shaxsiy xabar), Claude xarajati va web admin panelga havola.

Tarqatishni handlers/broadcast.py ishchisi bajaradi (Telegram limitlari, davom ettirish, statistika) —
xabar notifications jadvaliga yoziladi, shuning uchun web admin panelda ham ko'rinadi va to'xtatiladi."""
import html
import logging
import re
import uuid
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

import accounts
import ai_usage
import api_stats
from admins import Can, IsAdmin, has_perm, is_owner, notify_owner, perms_of, perms_text
from config import (
    CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, DATA_DIR, GEMINI_API_KEY, PEXELS_API_KEY, PIXABAY_API_KEY,
    WEBAPP_URL, money,
)
from database import change_balance, db, get_balance, now_str
from handlers.broadcast import KIND_ICONS, init_tables
from handlers.start import admin_costs, stats_text
from handlers.wallet import admin_pending
from states import AdminPanel

router = Router()
is_admin = IsAdmin()  # ega yoki u qo'shgan admin (admins.py)
router.message.filter(is_admin)
router.callback_query.filter(is_admin)
# Holatda turganda yozilgan /buyruq xabar sifatida tarqatilib ketmasin
not_command = ~F.text.startswith("/")

Button = InlineKeyboardButton
NEWS_DIR = DATA_DIR / "news"
KIND_NAMES = {"yangilik": "Yangilik", "aksiya": "Aksiya", "yangilanish": "Yangilanish", "muhim": "Muhim"}
STATUS = {"none": "📱 faqat ilova", "queued": "⏳ navbatda", "sending": "📤 yuborilmoqda", "done": "✅ yuborildi",
          "cancelled": "⏸ to'xtatildi"}


def kb(*rows):
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows])


def users_count():
    return db.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def pending_count():
    return db.execute("SELECT COUNT(*) FROM payments WHERE status = 'pending'").fetchone()[0]


# Har bir bo'lim (tugma prefiksi) qaysi huquqni talab qiladi — admins.PERMS. Ega hammasini ko'radi
CALLBACK_PERMS = (
    ("adm:stats", "stats"), ("adm:costs", "stats"), ("adm:api", "stats"), ("adm:credit", "stats"),
    ("adm:pay", "payments"),
    ("adm:bc", "broadcast"), ("adm:kind:", "broadcast"), ("adm:send:", "broadcast"), ("adm:fw", "broadcast"),
    ("adm:sent", "broadcast"), ("adm:stop:", "broadcast"),
    ("adm:find", "users"), ("adm:dm:", "users"),
    ("adm:bal:", "balance"),
)


def needed_perm(data):
    return next((perm for prefix, perm in CALLBACK_PERMS if (data or "").startswith(prefix)), None)


class Denied(BaseFilter):
    """Tugma bosildi, lekin adminda bu bo'lim uchun huquq yo'q."""

    async def __call__(self, callback: CallbackQuery) -> bool:
        perm = needed_perm(callback.data)
        return bool(perm) and not has_perm(callback.from_user.id, perm)


@router.callback_query(Denied())
async def admin_denied(callback: CallbackQuery):
    await callback.answer("🔒 Bu bo'lim uchun sizga ruxsat berilmagan. Bot egasidan so'rang.", show_alert=True)


def panel_markup(user_id=None):
    pending = pending_count()
    can = lambda perm: has_perm(user_id, perm)  # noqa: E731
    buttons = [
        ("stats", Button(text="📊 Statistika", callback_data="adm:stats")),
        ("stats", Button(text="🔌 API va limitlar", callback_data="adm:api")),
        ("broadcast", Button(text="📣 Xabar yuborish", callback_data="adm:bc")),
        ("broadcast", Button(text="↪️ Forward xabar", callback_data="adm:fw")),
        ("payments", Button(text=f"💳 To'lovlar{f' ({pending})' if pending else ''}", callback_data="adm:pay")),
        ("users", Button(text="👤 User qidirish", callback_data="adm:find")),
        ("broadcast", Button(text="📬 Yuborilganlar", callback_data="adm:sent")),
    ]
    allowed = [button for perm, button in buttons if can(perm)]
    rows = [allowed[i:i + 2] for i in range(0, len(allowed), 2)]
    if is_owner(user_id):  # adminlar va ularning huquqlari — faqat bot egasiga (handlers/admins.py)
        rows.append([Button(text="👥 Adminlar va huquqlar", callback_data="admins:list")])
    if WEBAPP_URL:
        url = f"{WEBAPP_URL}{'&' if '?' in WEBAPP_URL else '?'}admin=1"
        rows.append([Button(text="🌐 Web admin panel", web_app=WebAppInfo(url=url))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def panel_text(user_id=None):
    text = "🛠 <b>Admin panel</b>\n\n"
    if has_perm(user_id, "stats"):
        text += f"👥 Foydalanuvchilar: <b>{users_count()}</b>\n"
    if has_perm(user_id, "payments"):
        text += f"💳 Tekshiruvdagi to'lovlar: <b>{pending_count()}</b>\n"
    if not is_owner(user_id):
        text += f"\n🔑 <b>Sizning huquqlaringiz:</b>\n{perms_text(perms_of(user_id))}\n"
    return text + "\nKerakli bo'limni tanlang 👇"


back_markup = kb([Button(text="⬅️ Admin panel", callback_data="adm:home")])
cancel_markup = kb([Button(text="❌ Bekor qilish", callback_data="adm:home")])


@router.message(Command("admin"))
async def admin_command(message: Message, state: FSMContext):
    await state.set_state(None)
    await message.answer(panel_text(message.from_user.id), reply_markup=panel_markup(message.from_user.id))


@router.callback_query(F.data == "adm:home")
async def admin_home(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await callback.answer()
    markup = panel_markup(callback.from_user.id)
    try:
        await callback.message.edit_text(panel_text(callback.from_user.id), reply_markup=markup)
    except TelegramAPIError:
        await callback.message.answer(panel_text(callback.from_user.id), reply_markup=markup)


@router.callback_query(F.data == "adm:stats")
async def admin_stats_button(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(stats_text(), reply_markup=back_markup)


@router.callback_query(F.data == "adm:costs")
async def admin_costs_button(callback: CallbackQuery):
    await callback.answer()
    await admin_costs(callback.message)


# ===== 🔌 API va limitlar =====
CF_FREE_IMAGES = 130  # Cloudflare bepul tarifi: kuniga ~10 000 «neyron» ≈ 130 ta FLUX rasm (CF_STEPS=6)


def _status(state, ok="✅ ishlayapti"):
    if state.get("error"):
        return f"❗ {html.escape(state['error'])}"
    return ok


def api_report():
    """Barcha tashqi API'lar: bugungi sarf, limit va qoldiq (taxminiy), holat."""
    s = ai_usage.summary()
    claude = api_stats.get_state("claude")
    today_cost, today_n = s["today"]
    week_cost = s["week"][0]
    per_day = week_cost / 7 if week_cost else 0
    lines = ["🔌 <b>API va limitlar</b>\n", "🧠 <b>Claude</b> (matn yozish)", f"• Holat: {_status(claude)}"]
    lines.append(f"• Bugun: <b>${today_cost:.2f}</b> ({today_n} so'rov)")
    if s["budget"]:
        left = max(0.0, s["budget"] - today_cost)
        lines.append(f"• Kunlik chegara: ${s['budget']:.2f} → bugun qoldi <b>${left:.2f}</b> ({today_cost / s['budget']:.0%} ishlatildi)")
    lines.append(f"• 7 kun: ${week_cost:.2f} · o'rtacha kuniga ${per_day:.2f}")
    credit = api_stats.claude_credit()
    if credit:
        amount, spent, left, since = credit
        days = f" · ~{left / per_day:.0f} kunga yetadi" if per_day > 0 and left > 0 else ""
        warn = "⚠️ " if left < max(5.0, per_day * 3) else ""
        lines.append(f"• 💰 Balans: ${amount:.2f} ({since} da kiritilgan) − sarf ${spent:.2f} = "
                     f"{warn}<b>${left:.2f} qoldi</b>{days}")
    else:
        lines.append("• 💰 Balans: kiritilmagan — «💰 Claude balansi» tugmasi bilan kiriting")
    rate = api_stats.today("claude", "rate_limited")
    if rate:
        lines.append(f"• ⏳ Bugun tezlik limitiga {rate} marta urildi (so'rovlar kutib qayta yuborildi)")

    cf = api_stats.get_state("cloudflare")
    if CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN:
        made = api_stats.today("cloudflare", "images")
        status = _status(cf)
        if cf.get("limit_until"):
            status = f"⛔️ bepul limit tugadi (UTC {cf['limit_until'][11:16]} da tiklanadi)"
        lines += ["", "🎨 <b>Cloudflare FLUX</b> (AI rasm)", f"• Holat: {status}",
                  f"• Bugun (UTC): <b>{made}</b> rasm · bepul limit ~{CF_FREE_IMAGES} → qoldi ~<b>{max(0, CF_FREE_IMAGES - made)}</b>"]
    if GEMINI_API_KEY:
        gm = api_stats.get_state("gemini")
        lines += ["", "🍌 <b>Gemini</b> (AI rasm, pullik)", f"• Holat: {_status(gm)}",
                  f"• Bugun: <b>{api_stats.today('gemini', 'images')}</b> rasm"]
    for service, title, key in (("pexels", "📷 <b>Pexels</b> (foto)", PEXELS_API_KEY),
                                ("pixabay", "🖼 <b>Pixabay</b> (foto)", PIXABAY_API_KEY),
                                ("wikimedia", "🌐 <b>Wikimedia</b> (tarixiy foto, bepul)", True)):
        if not key:
            continue
        st = api_stats.get_state(service)
        calls, errors = api_stats.today(service), api_stats.today(service, "errors")
        lines += ["", title, f"• Holat: {_status(st)}", f"• Bugun: <b>{calls}</b> so'rov" + (f" · {errors} xato" if errors else "")]
        if st.get("remaining") is not None and st.get("limit"):
            lines.append(f"• Daqiqalik limit: {st['remaining']}/{st['limit']} qolgan (oxirgi so'rovda, {st.get('updated_at', '')[11:]})")
    if not PEXELS_API_KEY and not PIXABAY_API_KEY:
        lines += ["", "⚠️ Foto bazasi kaliti yo'q — faqat Wikimedia ishlatilmoqda. .env ga PIXABAY_API_KEY qo'shing."]
    lines += ["", "ℹ️ Claude qoldig'i — bot hisoblagan taxminiy summa. Aniq qoldiq: platform.claude.com → Billing. "
                  "Balansni to'ldirganingizda yangi summani shu yerga kiriting."]
    return "\n".join(lines)


api_markup = kb(
    [Button(text="💰 Claude balansi", callback_data="adm:credit"), Button(text="🔄 Yangilash", callback_data="adm:api")],
    [Button(text="💵 Batafsil xarajat", callback_data="adm:costs"), Button(text="⬅️ Admin panel", callback_data="adm:home")],
)


@router.message(Command("api"), Can("stats"))
async def api_command(message: Message):
    await message.answer(api_report(), reply_markup=api_markup, disable_web_page_preview=True)


@router.callback_query(F.data == "adm:api")
async def api_button(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_text(api_report(), reply_markup=api_markup, disable_web_page_preview=True)
    except TelegramAPIError:  # matn o'zgarmagan yoki xabar eski
        await callback.message.answer(api_report(), reply_markup=api_markup, disable_web_page_preview=True)


@router.callback_query(F.data == "adm:credit")
async def credit_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminPanel.credit)
    await callback.message.answer(
        "💰 Claude hisobingizdagi <b>hozirgi balansni</b> dollarda yozing (masalan: <code>50</code> yoki <code>23.40</code>).\n"
        "Uni platform.claude.com → Billing sahifasidan ko'rasiz. Shu paytdan boshlab bot sarfni ayirib, "
        "qancha qolganini ko'rsatib boradi.",
        reply_markup=cancel_markup,
    )


@router.message(AdminPanel.credit, F.text, not_command)
async def credit_entered(message: Message, state: FSMContext):
    raw = message.text.replace("$", "").replace(",", ".").replace(" ", "")
    try:
        amount = float(raw)
    except ValueError:
        amount = -1
    if not 0 <= amount <= 100_000:
        await message.answer("Summani raqamda yozing, masalan: <code>50</code>", reply_markup=cancel_markup)
        return
    api_stats.set_claude_credit(amount)
    await state.set_state(None)
    await message.answer(f"✅ Claude balansi saqlandi: <b>${amount:.2f}</b>", reply_markup=back_markup)
    await message.answer(api_report(), reply_markup=api_markup, disable_web_page_preview=True)


@router.callback_query(F.data == "adm:pay")
async def admin_payments_button(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    await admin_pending(callback.message, bot)


# ===== 📣 Hamma userlarga xabar =====
@router.callback_query(F.data == "adm:bc")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminPanel.broadcast)
    await callback.message.answer(
        "📣 <b>Hamma userlarga xabar</b>\n\n"
        "Yuboriladigan xabarni shu yerga yuboring: matn, rasm, video, fayl yoki ovozli xabar — "
        "formatlash (qalin, havola) saqlanadi.\n\n"
        "💡 Matnning <b>birinchi qatori</b> ilovadagi qo'ng'iroqchada sarlavha bo'ladi, qolgani — to'liq matn.",
        reply_markup=cancel_markup,
    )


def split_text(text):
    lines = [line.strip() for line in (text or "").strip().splitlines()]
    lines = [line for line in lines if line] or [""]
    title = lines[0][:120]
    body = "\n".join(lines[1:]).strip() or title
    return title, body[:2000]


def confirm_markup(kind, has_text):
    kinds = [Button(text=("● " if k == kind else "") + KIND_ICONS[k], callback_data=f"adm:kind:{k}") for k in KIND_NAMES]
    rows = [kinds]
    if has_text:
        rows.append([Button(text="✅ Bot + ilova qo'ng'iroqchasi", callback_data="adm:send:both")])
    rows.append([Button(text="🤖 Faqat botga", callback_data="adm:send:bot")])
    rows.append([Button(text="❌ Bekor qilish", callback_data="adm:home")])
    return kb(*rows)


@router.message(AdminPanel.broadcast, not_command)
async def broadcast_message(message: Message, state: FSMContext):
    text = message.text or message.caption or ""
    await state.update_data(src_chat=message.chat.id, src_msg=message.message_id, text=text, kind="yangilik",
                            photo=message.photo[-1].file_id if message.photo else None)
    await state.set_state(None)
    total = users_count()
    hint = ("Ilovada sarlavha: <b>{}</b>".format(html.escape(split_text(text)[0])) if text
            else "Xabarda matn yo'q — faqat botga yuboriladi (ilovada sarlavha kerak).")
    await message.answer(
        f"👆 Xabar shu ko'rinishda <b>{total}</b> ta userga yuboriladi.\n\n{hint}\n\n"
        "Tur (ilovadagi belgi): 📣 Yangilik · 🎁 Aksiya · 🚀 Yangilanish · ⚠️ Muhim",
        reply_markup=confirm_markup("yangilik", bool(text)),
    )


@router.callback_query(F.data.startswith("adm:kind:"))
async def broadcast_kind(callback: CallbackQuery, state: FSMContext):
    kind = callback.data.split(":")[2]
    data = await state.get_data()
    if not data.get("src_msg") or kind not in KIND_NAMES:
        await callback.answer("Xabar topilmadi — qaytadan boshlang.", show_alert=True)
        return
    await state.update_data(kind=kind)
    await callback.answer(KIND_NAMES[kind])
    with suppress(TelegramAPIError):
        await callback.message.edit_reply_markup(reply_markup=confirm_markup(kind, bool(data.get("text"))))


async def save_photo(bot: Bot, file_id):
    """Ilovada ko'rsatish uchun rasmni news/ papkasiga saqlaydi (web bilan umumiy)."""
    try:
        NEWS_DIR.mkdir(parents=True, exist_ok=True)
        name = f"news-{uuid.uuid4().hex[:12]}.jpg"
        await bot.download(file_id, destination=NEWS_DIR / name)
        return name
    except Exception:
        logging.exception("Admin xabari rasmini saqlab bo'lmadi")
        return None


@router.callback_query(F.data.startswith("adm:send:"))
async def broadcast_send(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if not data.get("src_msg"):
        await callback.answer("Xabar topilmadi — qaytadan boshlang.", show_alert=True)
        return
    in_app = callback.data.endswith(":both") and bool(data.get("text"))
    title, body = split_text(data.get("text"))
    image = await save_photo(bot, data["photo"]) if in_app and data.get("photo") else None
    init_tables()
    cursor = db.execute(
        "INSERT INTO notifications (kind, title, body, image, button, link, to_bot, bot_status, bot_total, created_at, "
        "mode, src_chat, src_msg, in_app) VALUES (?, ?, ?, ?, '', '', 1, 'queued', ?, ?, 'copy', ?, ?, ?)",
        (data.get("kind", "yangilik"), title or "Xabar", body or title or "Xabar", image, users_count(), now_str(),
         data["src_chat"], data["src_msg"], 1 if in_app else 0),
    )
    db.commit()
    await state.set_data({})
    await callback.answer("Navbatga qo'yildi 🚀")
    where = "📱 Ilova qo'ng'iroqchasida ham chiqadi." if in_app else "🤖 Faqat botda."
    with suppress(TelegramAPIError):
        await callback.message.edit_text(
            f"🚀 <b>Xabar #{cursor.lastrowid} navbatga qo'yildi</b>\n\n{where}\n"
            "Holatini «📬 Yuborilganlar» da kuzating.",
            reply_markup=kb([Button(text="📬 Yuborilganlar", callback_data="adm:sent")],
                            [Button(text="⬅️ Admin panel", callback_data="adm:home")]),
        )


# ===== ↪️ Forward =====
@router.callback_query(F.data == "adm:fw")
async def forward_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminPanel.forward)
    await callback.message.answer(
        "↪️ <b>Forward xabar</b>\n\n"
        "Kanal yoki chatdagi xabarni shu yerga forward qiling (yoki yangi xabar yozing). "
        "U hamma userlarga asl manbasi ko'rsatilgan holda forward qilinadi.",
        reply_markup=cancel_markup,
    )


@router.message(AdminPanel.forward, not_command)
async def forward_message(message: Message, state: FSMContext):
    await state.update_data(src_chat=message.chat.id, src_msg=message.message_id, text=message.text or message.caption or "")
    await state.set_state(None)
    origin = ""
    if message.forward_origin:
        chat = getattr(message.forward_origin, "chat", None) or getattr(message.forward_origin, "sender_user", None)
        name = getattr(chat, "title", None) or getattr(chat, "full_name", None)
        if name:
            origin = f"\nManba: <b>{html.escape(name)}</b>"
    await message.answer(
        f"👆 Shu xabar <b>{users_count()}</b> ta userga forward qilinadi.{origin}",
        reply_markup=kb([Button(text="✅ Forward qilish", callback_data="adm:fwgo")],
                        [Button(text="❌ Bekor qilish", callback_data="adm:home")]),
    )


@router.callback_query(F.data == "adm:fwgo")
async def forward_send(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("src_msg"):
        await callback.answer("Xabar topilmadi — qaytadan boshlang.", show_alert=True)
        return
    title, body = split_text(data.get("text") or "Forward xabar")
    init_tables()
    cursor = db.execute(
        "INSERT INTO notifications (kind, title, body, to_bot, bot_status, bot_total, created_at, mode, src_chat, src_msg, "
        "in_app) VALUES ('yangilik', ?, ?, 1, 'queued', ?, ?, 'forward', ?, ?, 0)",
        (title or "Forward xabar", body or "Forward xabar", users_count(), now_str(), data["src_chat"], data["src_msg"]),
    )
    db.commit()
    await state.set_data({})
    await callback.answer("Navbatga qo'yildi 🚀")
    with suppress(TelegramAPIError):
        await callback.message.edit_text(
            f"🚀 <b>Forward #{cursor.lastrowid} navbatga qo'yildi.</b>\nHolati — «📬 Yuborilganlar».",
            reply_markup=kb([Button(text="📬 Yuborilganlar", callback_data="adm:sent")],
                            [Button(text="⬅️ Admin panel", callback_data="adm:home")]),
        )


# ===== 📬 Yuborilganlar =====
def sent_text():
    init_tables()
    rows = db.execute(
        "SELECT n.id, n.kind, n.title, n.bot_status, n.bot_total, n.bot_sent, n.bot_failed, n.mode, n.in_app, n.created_at, "
        "(SELECT COUNT(*) FROM notification_reads r WHERE r.notification_id = n.id) FROM notifications n "
        "ORDER BY n.id DESC LIMIT 6"
    ).fetchall()
    if not rows:
        return "📬 Hali xabar yuborilmagan.", []
    lines, active = ["📬 <b>Oxirgi xabarlar</b>\n"], []
    for nid, kind, title, status, total, sent, failed, mode, in_app, created, reads in rows:
        mode_name = {"forward": "↪️ forward", "copy": "📣 xabar"}.get(mode, "📱 ilovadan")
        done = sent + failed
        pct = f" {round(done * 100 / total)}%" if total and status == "sending" else ""
        lines.append(
            f"<b>#{nid}</b> {KIND_ICONS.get(kind, '🔔')} {html.escape(title[:60])}\n"
            f"   {mode_name} · {STATUS.get(status, status)}{pct} · {created[5:]}\n"
            f"   ✅ {sent} · ⛔ {failed}" + (f" · 👁 ilovada {reads}" if in_app else "")
        )
        if status in ("queued", "sending"):
            active.append(nid)
    return "\n".join(lines), active


def sent_markup(active):
    rows = [[Button(text=f"⏸ #{nid} ni to'xtatish", callback_data=f"adm:stop:{nid}")] for nid in active]
    rows.append([Button(text="🔄 Yangilash", callback_data="adm:sent"), Button(text="⬅️ Panel", callback_data="adm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:sent")
async def sent_list(callback: CallbackQuery):
    text, active = sent_text()
    await callback.answer()
    try:
        await callback.message.edit_text(text, reply_markup=sent_markup(active))
    except TelegramAPIError:
        await callback.message.answer(text, reply_markup=sent_markup(active))


@router.callback_query(F.data.startswith("adm:stop:"))
async def sent_stop(callback: CallbackQuery):
    nid = int(callback.data.split(":")[2])
    db.execute("UPDATE notifications SET bot_status = 'cancelled' WHERE id = ? AND bot_status IN ('queued', 'sending')", (nid,))
    db.commit()
    await callback.answer(f"#{nid} to'xtatildi")
    text, active = sent_text()
    with suppress(TelegramAPIError):
        await callback.message.edit_text(text, reply_markup=sent_markup(active))


# ===== 👤 User qidirish =====
@router.callback_query(F.data == "adm:find")
async def find_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminPanel.find)
    await callback.message.answer(
        "👤 Userni toping: <b>Telegram ID</b>, <b>@username</b>, <b>telefon raqam</b> yoki <b>ism</b> yozing.",
        reply_markup=cancel_markup,
    )


def find_users(query):
    q = query.strip()
    digits = re.sub(r"\D", "", q)
    if q.lstrip("-").isdigit() and len(digits) <= 12 and not digits.startswith("998"):
        rows = db.execute("SELECT id FROM users WHERE id = ?", (int(q),)).fetchall()
        if rows:
            return [r[0] for r in rows]
    if len(digits) >= 9:
        phone = accounts.normalize_phone(digits)
        if phone:
            row = db.execute("SELECT user_id FROM accounts WHERE phone = ?", (phone,)).fetchone()
            if row:
                return [row[0]]
    like = f"%{q.lstrip('@')}%"
    return [r[0] for r in db.execute(
        "SELECT id FROM users WHERE username LIKE ? OR full_name LIKE ? ORDER BY id DESC LIMIT 5", (like, like)
    )]


def user_card(user_id):
    row = db.execute("SELECT full_name, username, joined_at, balance FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        return None
    name, username, joined, balance = row
    account = accounts.account_by_user(user_id)
    phone = accounts.format_phone(account["phone"]) if account else "ro'yxatdan o'tmagan"
    docs = db.execute("SELECT COUNT(*) FROM documents WHERE user_id = ?", (user_id,)).fetchone()[0]
    paid = db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE user_id = ? AND status = 'approved'", (user_id,)
    ).fetchone()[0]
    return (
        f"👤 <b>{html.escape(name or '—')}</b>{f' · @{html.escape(username)}' if username else ''}\n"
        f"🆔 <code>{user_id}</code>\n"
        f"📱 {phone}\n"
        f"👛 Balans: <b>{money(balance or 0)}</b> · 💳 to'lagan: {money(paid)}\n"
        f"📂 Hujjatlar: {docs} · 🗓 qo'shilgan: {joined or '—'}"
    )


def user_markup(user_id, viewer):
    """Topilgan user ostidagi tugmalar — admin huquqiga qarab (balans tugmalari faqat «balance» huquqi bilan)."""
    rows = []
    if has_perm(viewer, "balance"):
        rows.append([Button(text="➕ Balans", callback_data=f"adm:bal:{user_id}:+"),
                     Button(text="➖ Balans", callback_data=f"adm:bal:{user_id}:-")])
    rows.append([Button(text="💬 Xabar yozish", callback_data=f"adm:dm:{user_id}")])
    rows.append([Button(text="⬅️ Admin panel", callback_data="adm:home")])
    return kb(*rows)


@router.message(AdminPanel.find, F.text, not_command)
async def find_user(message: Message, state: FSMContext):
    found = find_users(message.text)
    if not found:
        await message.answer("🔎 Hech kim topilmadi. Boshqacha yozib ko'ring.", reply_markup=cancel_markup)
        return
    await state.set_state(None)
    for user_id in found[:5]:
        card = user_card(user_id)
        if card:
            await message.answer(card, reply_markup=user_markup(user_id, message.from_user.id))


@router.callback_query(F.data.regexp(r"^adm:bal:\d+:[+-]$"))
async def balance_start(callback: CallbackQuery, state: FSMContext):
    _, _, user_id, sign = callback.data.split(":")
    await state.set_state(AdminPanel.amount)
    await state.update_data(target=int(user_id), sign=sign)
    await callback.answer()
    action = "➕ Qo'shiladigan" if sign == "+" else "➖ Ayiriladigan"
    await callback.message.answer(
        f"{action} summani yozing (so'm), masalan: <code>20000</code>",
        reply_markup=cancel_markup,
    )


@router.message(AdminPanel.amount, F.text, not_command)
async def balance_apply(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    digits = re.sub(r"\D", "", message.text)
    if not digits or not 0 < int(digits) <= 100_000_000:
        await message.answer("Summani raqam bilan yozing, masalan: <code>20000</code>", reply_markup=cancel_markup)
        return
    amount = int(digits) * (1 if data.get("sign") == "+" else -1)
    user_id = data["target"]
    await state.set_state(None)
    if not change_balance(user_id, amount, "admin", "Admin tomonidan"):
        await message.answer("⚠️ User topilmadi yoki balans manfiy bo'lib qoladi.")
        return
    change = f"{'+' if amount > 0 else '−'}{money(abs(amount))}"
    balance = money(get_balance(user_id))
    await message.answer(f"✅ <code>{user_id}</code>: {change}\n👛 Yangi balans: <b>{balance}</b>", reply_markup=user_markup(user_id, message.from_user.id))
    await notify_owner(bot, message.from_user.id, f"<code>{user_id}</code> balansini o'zgartirdi: {change}")
    with suppress(TelegramAPIError):
        await bot.send_message(user_id, f"💳 Balansingiz admin tomonidan o'zgartirildi: <b>{change}</b>\n👛 Balans: <b>{balance}</b>")


@router.callback_query(F.data.regexp(r"^adm:dm:\d+$"))
async def dm_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminPanel.dm)
    await state.update_data(target=int(callback.data.split(":")[2]))
    await callback.answer()
    await callback.message.answer("💬 Userga yuboriladigan xabarni yozing (matn, rasm yoki fayl):", reply_markup=cancel_markup)


@router.message(AdminPanel.dm, not_command)
async def dm_send(message: Message, state: FSMContext, bot: Bot):
    user_id = (await state.get_data()).get("target")
    await state.set_state(None)
    try:
        await bot.send_message(user_id, "📩 <b>Admindan xabar</b>")
        await message.copy_to(user_id)
    except TelegramAPIError:
        await message.answer("⚠️ Yuborilmadi: user botni bloklagan yoki chat topilmadi.")
        return
    await message.answer("✅ Xabar yuborildi.", reply_markup=back_markup)
