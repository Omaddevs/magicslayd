"""Claude API xarajat hisoblagichi va kunlik chegara.

Har bir AI javobidan keyin token soni va narxi (USD) «ai_usage» jadvaliga yoziladi — shunda pul nimaga
ketgani doim ko'rinib turadi (botda /xarajat). AI_DAILY_BUDGET_USD (.env) — bir kunda Claude'ga sarflanadigan
eng ko'p summa: yetganda yangi AI so'rovlari to'xtaydi va adminga xabar boradi. 0 — chegara yo'q.

Narxlar — 1 mln token uchun USD (Anthropic API, 2026-10). Kesh: o'qish 0.1×, yozish 1.25× kiruvchi narx."""
import logging
import time

import aiohttp

from config import AI_DAILY_BUDGET_USD, BOT_TOKEN
from database import db, now_str, today_str

# model nomi boshlanishi → (kiruvchi, chiquvchi). Eng uzun mos keluvchi tanlanadi
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4": (5.00, 25.00),
    "claude-fable": (10.00, 50.00),
}
UNKNOWN = (5.00, 25.00)  # noma'lum model — kam ko'rsatib qo'ymaslik uchun qimmatroq hisoblanadi
WARN_AT = 0.8  # chegaraning 80% ida adminga ogohlantirish

db.execute(
    "CREATE TABLE IF NOT EXISTS ai_usage (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, day TEXT, "
    "model TEXT, input_tokens INTEGER, output_tokens INTEGER, cache_read INTEGER, cache_write INTEGER, cost REAL)"
)
db.execute("CREATE INDEX IF NOT EXISTS ai_usage_day ON ai_usage (day)")
db.commit()

_notified = {}  # (kun, tur) → True — bir kunda bir marta xabar


def price_of(model):
    model = str(model or "")
    match = max((key for key in PRICES if model.startswith(key)), key=len, default=None)
    return PRICES[match] if match else UNKNOWN


def record(model, usage):
    """Javobning usage'idan narxni hisoblab yozadi. Qaytaradi: narx (USD)."""
    if usage is None:
        return 0.0
    inp = int(getattr(usage, "input_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    write = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    price_in, price_out = price_of(model)
    if str(model).startswith("claude-haiku-5-5") and inp + read + write > 100_000:
        price_in, price_out = 0.50, 2.50  # Haiku 5.5: 100K dan uzun so'rov qimmatroq
    cost = (inp * price_in + read * price_in * 0.1 + write * price_in * 1.25 + out * price_out) / 1_000_000
    try:
        db.execute(
            "INSERT INTO ai_usage (created_at, day, model, input_tokens, output_tokens, cache_read, cache_write, cost) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (now_str(), today_str(), str(model), inp, out, read, write, cost),
        )
        db.commit()
    except Exception:  # noqa: BLE001 — hisoblagich xatosi asosiy ishni to'xtatmasin
        logging.exception("AI xarajatini yozib bo'lmadi")
    return cost


def spent_today():
    row = db.execute("SELECT COALESCE(SUM(cost), 0) FROM ai_usage WHERE day = ?", (today_str(),)).fetchone()
    return float(row[0] or 0)


def over_budget():
    return AI_DAILY_BUDGET_USD > 0 and spent_today() >= AI_DAILY_BUDGET_USD


async def notify_admin(kind, text):
    """Barcha adminlarga Telegram xabari (bir kunda bir tur — bir marta)."""
    from admins import admin_ids  # kech import: admins → database, aylanma import bo'lmasin

    key = (today_str(), kind)
    if not admin_ids("stats") or _notified.get(key):
        return
    _notified[key] = True
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            for admin_id in admin_ids("stats"):
                await session.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                   json={"chat_id": admin_id, "text": text, "parse_mode": "HTML"})
    except Exception:  # noqa: BLE001
        logging.warning("Adminga xarajat xabarini yuborib bo'lmadi")


async def after_request():
    """Har bir javobdan keyin: chegaraning 80% iga yetsa — ogohlantirish."""
    if AI_DAILY_BUDGET_USD <= 0:
        return
    spent = spent_today()
    if spent >= AI_DAILY_BUDGET_USD * WARN_AT:
        await notify_admin("warn", f"⚠️ <b>Claude xarajati:</b> bugun ${spent:.2f} "
                                   f"(kunlik chegara ${AI_DAILY_BUDGET_USD:.2f} ning {spent / AI_DAILY_BUDGET_USD:.0%} i).\n"
                                   "Batafsil: /xarajat")


def summary():
    """/xarajat uchun: bugun, oxirgi 30 daqiqa, 7 kun, jami va modellar bo'yicha."""
    def one(sql, *args):
        row = db.execute(sql, args).fetchone()
        return float(row[0] or 0), int(row[1] or 0)

    since = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() - 30 * 60))
    week = time.strftime("%Y-%m-%d", time.localtime(time.time() - 6 * 86400))
    by_model = db.execute(
        "SELECT model, SUM(cost), COUNT(*), SUM(input_tokens + cache_read + cache_write), SUM(output_tokens) "
        "FROM ai_usage WHERE day >= ? GROUP BY model ORDER BY SUM(cost) DESC", (week,)
    ).fetchall()
    return {
        "today": one("SELECT SUM(cost), COUNT(*) FROM ai_usage WHERE day = ?", today_str()),
        "recent": one("SELECT SUM(cost), COUNT(*) FROM ai_usage WHERE created_at >= ?", since),
        "week": one("SELECT SUM(cost), COUNT(*) FROM ai_usage WHERE day >= ?", week),
        "total": one("SELECT SUM(cost), COUNT(*) FROM ai_usage"),
        "by_model": by_model,
        "budget": AI_DAILY_BUDGET_USD,
    }
