"""Tashqi API'lar hisoblagichi va holati — admin panel (bot /admin → «🔌 API va limitlar», web → Admin → API).

Claude xarajati alohida — ai_usage.py (har bir javob narxi). Bu yerda qolganlari:
  • api_stats jadvali — kunlik sanoq: (kun, xizmat, ko'rsatkich) → son. Masalan pixabay/calls, cloudflare/images.
  • meta jadvali, «api_state:<xizmat>» — oxirgi holat (JSON): limit tugagani, qolgan so'rovlar, oxirgi xato.
  • meta «claude_credit» — admin kiritgan Claude hisobi balansi: {"amount": 50, "since": "2026-11-06 14:00"}.
    Qoldiq = amount − shu vaqtdan beri ai_usage dagi sarf (taxminiy: narxlar ai_usage.PRICES dan).
Hisoblagich xatosi hech qachon asosiy ishni to'xtatmaydi."""
import json
import logging
from datetime import datetime, timezone

from database import db, now_str, set_meta, today_str

db.execute(
    "CREATE TABLE IF NOT EXISTS api_stats (day TEXT, service TEXT, metric TEXT, value INTEGER NOT NULL DEFAULT 0, "
    "PRIMARY KEY (day, service, metric))"
)
db.commit()

# Cloudflare va Gemini bepul limiti UTC yarim tunda yangilanadi — ular uchun kun UTC bo'yicha
UTC_SERVICES = {"cloudflare", "gemini"}


def utc_day():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def day_of(service):
    return utc_day() if service in UTC_SERVICES else today_str()


def bump(service, metric="calls", n=1):
    try:
        db.execute(
            "INSERT INTO api_stats (day, service, metric, value) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(day, service, metric) DO UPDATE SET value = value + excluded.value",
            (day_of(service), service, metric, n),
        )
        db.commit()
    except Exception:  # noqa: BLE001
        logging.exception("API hisoblagichiga yozib bo'lmadi")


def get_state(service):
    row = db.execute("SELECT value FROM meta WHERE key = ?", (f"api_state:{service}",)).fetchone()
    try:
        return json.loads(row[0]) if row else {}
    except (TypeError, ValueError):
        return {}


_last_state = {}  # bir xil holatni har safar bazaga yozmaslik uchun


def set_state(service, **values):
    """Holatni yangilaydi (berilgan maydonlar). None — maydonni o'chiradi."""
    try:
        state = {**get_state(service), **values}
        state = {k: v for k, v in state.items() if v is not None}
        if _last_state.get(service) == state:
            return
        _last_state[service] = dict(state)
        set_meta(f"api_state:{service}", json.dumps({**state, "updated_at": now_str()}, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        logging.exception("API holatini yozib bo'lmadi")


def today(service, metric="calls"):
    row = db.execute(
        "SELECT value FROM api_stats WHERE day = ? AND service = ? AND metric = ?", (day_of(service), service, metric)
    ).fetchone()
    return int(row[0]) if row else 0


def claude_credit():
    """(balans, sarf, qoldiq, qachondan) yoki None — admin balans kiritmagan bo'lsa."""
    row = db.execute("SELECT value FROM meta WHERE key = 'claude_credit'").fetchone()
    try:
        data = json.loads(row[0]) if row else None
        amount, since = float(data["amount"]), str(data["since"])
    except (TypeError, ValueError, KeyError):
        return None
    spent = db.execute("SELECT COALESCE(SUM(cost), 0) FROM ai_usage WHERE created_at >= ?", (since,)).fetchone()[0]
    return amount, float(spent or 0), amount - float(spent or 0), since


def set_claude_credit(amount):
    set_meta("claude_credit", json.dumps({"amount": round(float(amount), 2), "since": now_str()}))
