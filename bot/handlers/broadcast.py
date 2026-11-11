"""Admin ilovadan yuborgan bildirishnomani barcha userlarga Telegram orqali tarqatadi.
Ilova (slayd-web) xabarni notifications jadvaliga bot_status='queued' bilan yozadi, shu ishchi uni oladi.
- Telegram limiti: sekundiga ~25 xabar (umumiy limit 30)
- Bot qayta ishga tushsa — bot_cursor dan davom etadi (hech kim ikki marta olmaydi)
- Botni bloklaganlar «yetkazilmadi» hisobiga yoziladi
- Admin «To'xtatish» yoki «O'chirish» bossa — tarqatish to'xtaydi"""
import asyncio
import html
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from config import DATA_DIR, WEBAPP_URL
from database import db

POLL_SECONDS = 5
SEND_GAP = 0.04  # ~25 xabar / soniya
BATCH = 50  # shuncha xabardan keyin hisoblagich bazaga yoziladi
NEWS_DIR = DATA_DIR / "news"
CAPTION_MAX = 1024

KIND_ICONS = {"yangilik": "📣", "aksiya": "🎁", "yangilanish": "🚀", "muhim": "⚠️"}


def init_tables():
    """Ilova jadvallarni yaratadi; bot birinchi ishga tushsa ham ishlasin."""
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL DEFAULT 'yangilik', title TEXT NOT NULL,
            body TEXT NOT NULL, image TEXT, button TEXT, link TEXT, to_bot INTEGER NOT NULL DEFAULT 1,
            bot_status TEXT NOT NULL DEFAULT 'none', bot_total INTEGER NOT NULL DEFAULT 0,
            bot_sent INTEGER NOT NULL DEFAULT 0, bot_failed INTEGER NOT NULL DEFAULT 0,
            bot_cursor INTEGER NOT NULL DEFAULT 0, created_at TEXT);
        CREATE TABLE IF NOT EXISTS notification_reads (
            user_id INTEGER NOT NULL, notification_id INTEGER NOT NULL, read_at TEXT,
            PRIMARY KEY (user_id, notification_id));
        """
    )
    # Botdagi /admin dan yuborilganlar: istalgan xabar nusxasi (copy) yoki forward.
    # in_app = 0 — faqat botda (ilova qo'ng'iroqchasida ko'rinmaydi)
    columns = {row[1] for row in db.execute("PRAGMA table_info(notifications)")}
    for column, definition in (("mode", "TEXT NOT NULL DEFAULT 'text'"), ("src_chat", "INTEGER"), ("src_msg", "INTEGER"),
                               ("in_app", "INTEGER NOT NULL DEFAULT 1")):
        if column not in columns:
            db.execute(f"ALTER TABLE notifications ADD COLUMN {column} {definition}")
    db.commit()


def _next_job():
    row = db.execute(
        "SELECT id, kind, title, body, image, button, link, mode, src_chat, src_msg, in_app FROM notifications "
        "WHERE bot_status IN ('queued', 'sending') ORDER BY id LIMIT 1"
    ).fetchone()
    if not row:
        return None
    keys = ("id", "kind", "title", "body", "image", "button", "link", "mode", "src_chat", "src_msg", "in_app")
    job = dict(zip(keys, row))
    # Navbatga olinganda auditoriya qayta hisoblanadi (orada yangi userlar qo'shilgan bo'lishi mumkin)
    db.execute(
        "UPDATE notifications SET bot_status = 'sending', "
        "bot_total = CASE WHEN bot_status = 'queued' THEN (SELECT COUNT(*) FROM users) ELSE bot_total END "
        "WHERE id = ?", (job["id"],)
    )
    db.commit()
    return job


def _status(notification_id):
    row = db.execute("SELECT bot_status FROM notifications WHERE id = ?", (notification_id,)).fetchone()
    return row[0] if row else None


def _progress(notification_id, cursor, sent, failed):
    # Holatidan qat'i nazar yoziladi — to'xtatilgan bo'lsa ham yetkazilganlar statistikada ko'rinsin
    db.execute(
        "UPDATE notifications SET bot_cursor = ?, bot_sent = bot_sent + ?, bot_failed = bot_failed + ? WHERE id = ?",
        (cursor, sent, failed, notification_id),
    )
    db.commit()


def _cursor(notification_id):
    row = db.execute("SELECT bot_cursor FROM notifications WHERE id = ?", (notification_id,)).fetchone()
    return row[0] if row else 0


def _users_after(cursor, limit=500):
    return [r[0] for r in db.execute("SELECT id FROM users WHERE id > ? ORDER BY id LIMIT ?", (cursor, limit))]


def _app_url(notification_id):
    if not WEBAPP_URL:
        return None
    return f"{WEBAPP_URL}{'&' if '?' in WEBAPP_URL else '?'}notif={notification_id}"


def build_message(job):
    icon = KIND_ICONS.get(job["kind"], "🔔")
    text = f"{icon} <b>{html.escape(job['title'])}</b>\n\n{html.escape(job['body'])}"
    rows = []
    link = job["link"] or ""
    if link.startswith("https://"):
        rows.append([InlineKeyboardButton(text=job["button"] or "Batafsil", url=link)])
    url = _app_url(job["id"]) if job.get("in_app", 1) else None
    if url:
        rows.append([InlineKeyboardButton(text="📱 Ilovada o'qish", web_app=WebAppInfo(url=url))])
    markup = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
    photo = None
    if job["image"]:
        path = NEWS_DIR / job["image"]
        if path.is_file():
            photo = path
    return text, markup, photo


async def _send_one(bot: Bot, user_id, text, markup, media, job=None):
    """True — yetkazildi, False — yetkazilmadi (bloklagan, o'chirilgan hisob va h.k.).
    media["photo"]: birinchi marta fayl yuklanadi, keyin Telegram'dagi file_id qayta ishlatiladi.
    job["mode"]: text — matn/rasm; copy — admin yuborgan xabar nusxasi (har qanday media); forward — asl manbasi bilan."""
    mode = (job or {}).get("mode") or "text"
    for _ in range(3):
        try:
            if mode == "forward":
                await bot.forward_message(user_id, job["src_chat"], job["src_msg"])
                return True
            if mode == "copy":
                await bot.copy_message(user_id, job["src_chat"], job["src_msg"], reply_markup=markup)
                return True
            photo = media.get("photo")
            if photo:
                source = photo if isinstance(photo, str) else FSInputFile(photo)
                caption = text if len(text) <= CAPTION_MAX else None
                message = await bot.send_photo(
                    user_id, source, caption=caption, reply_markup=markup if caption else None,
                )
                if not isinstance(photo, str) and message.photo:
                    media["photo"] = message.photo[-1].file_id
                if not caption:
                    await bot.send_message(user_id, text, reply_markup=markup, disable_web_page_preview=True)
            else:
                await bot.send_message(user_id, text, reply_markup=markup, disable_web_page_preview=True)
            return True
        except TelegramRetryAfter as error:
            await asyncio.sleep(error.retry_after + 1)
        except TelegramForbiddenError:
            return False
        except TelegramAPIError:
            return False
    return False


async def run_job(bot: Bot, job):
    text, markup, photo = build_message(job)
    media = {"photo": photo}
    cursor = _cursor(job["id"])
    sent = failed = 0
    while True:
        users = _users_after(cursor)
        if not users:
            break
        for user_id in users:
            if await _send_one(bot, user_id, text, markup, media, job):
                sent += 1
            else:
                failed += 1
            cursor = user_id
            if sent + failed >= BATCH:
                _progress(job["id"], cursor, sent, failed)
                sent = failed = 0
                if _status(job["id"]) != "sending":  # admin to'xtatdi yoki o'chirdi
                    logging.info("Bildirishnoma #%s tarqatish to'xtatildi", job["id"])
                    return
            await asyncio.sleep(SEND_GAP)
    _progress(job["id"], cursor, sent, failed)
    db.execute("UPDATE notifications SET bot_status = 'done' WHERE id = ? AND bot_status = 'sending'", (job["id"],))
    db.commit()
    logging.info("Bildirishnoma #%s barcha userlarga tarqatildi", job["id"])


async def broadcast_worker(bot: Bot):
    init_tables()
    while True:
        try:
            job = _next_job()
            if job:
                await run_job(bot, job)
                continue
        except Exception:
            logging.exception("Bildirishnomani tarqatishda xato")
        await asyncio.sleep(POLL_SECONDS)
