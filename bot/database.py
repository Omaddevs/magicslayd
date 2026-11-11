import json
import sqlite3
from datetime import datetime, timedelta

from config import DB_PATH

TIME_FORMAT = "%Y-%m-%d %H:%M"

db = sqlite3.connect(DB_PATH, timeout=10)
# WAL — web ilova (slayd-web) ham shu bazaga yozadi; o'qish va yozish bir-birini to'sib qo'ymaydi
db.execute("PRAGMA journal_mode = WAL")


def now_str():
    return datetime.now().strftime(TIME_FORMAT)


def today_str():
    return datetime.now().strftime("%Y-%m-%d")


def as_dicts(cursor):
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def add_column(table, column, definition):
    """Eski bazaga yangi ustun qo'shadi (bor bo'lsa — tegmaydi)."""
    if column not in {row[1] for row in db.execute(f"PRAGMA table_info({table})")}:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, full_name TEXT, username TEXT, joined_at TEXT,
            balance INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS presentations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, topic TEXT, slides INTEGER, created_at TEXT,
            price INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, file_id TEXT, file_type TEXT,
            status TEXT NOT NULL DEFAULT 'pending', created_at TEXT, reviewed_at TEXT);
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, kind TEXT, note TEXT,
            created_at TEXT);
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, kind TEXT, title TEXT, file_id TEXT,
            created_at TEXT);
        CREATE TABLE IF NOT EXISTS titles (user_id INTEGER PRIMARY KEY, data TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS web_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, kind TEXT, params TEXT,
            price INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending',
            charged INTEGER NOT NULL DEFAULT 0, error TEXT, document_id INTEGER, created_at TEXT, finished_at TEXT);
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, title TEXT, pages INTEGER, file_id TEXT, file_type TEXT,
            downloads INTEGER NOT NULL DEFAULT 0, created_at TEXT);
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS ai_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_key TEXT, source TEXT, kind TEXT,
            status TEXT NOT NULL DEFAULT 'queued', error TEXT, created_at TEXT, finished_at TEXT);
        CREATE INDEX IF NOT EXISTS ai_requests_user ON ai_requests (user_key, created_at);
        -- Telefon + parol hisoblari (web ilova bilan umumiy). user_id — Telegram ID
        CREATE TABLE IF NOT EXISTS accounts (
            user_id INTEGER PRIMARY KEY, phone TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            verified INTEGER NOT NULL DEFAULT 0, source TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS auth_sessions (
            token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at TEXT, expires_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS auth_sessions_user ON auth_sessions (user_id);
        CREATE TABLE IF NOT EXISTS auth_codes (
            phone TEXT PRIMARY KEY, code_hash TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            expires_at INTEGER NOT NULL, sent_at INTEGER NOT NULL, reset_token_hash TEXT, reset_expires_at INTEGER);
        CREATE TABLE IF NOT EXISTS verified_phones (user_id INTEGER PRIMARY KEY, phone TEXT NOT NULL, created_at TEXT);
        -- Bot chatidagi buyurtma uchun yechilgan, lekin fayl hali yetkazilmagan pul. Bot to'xtab qolsa —
        -- qayta ishga tushganda shu yozuvlar bo'yicha pul qaytariladi (refund_stale_holds)
        CREATE TABLE IF NOT EXISTS charge_holds (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount INTEGER NOT NULL, note TEXT,
            created_at TEXT);
        """
    )
    add_column("users", "balance", "INTEGER NOT NULL DEFAULT 0")
    add_column("presentations", "price", "INTEGER NOT NULL DEFAULT 0")
    # To'lov qaysi buyurtma uchun (bo'sh — oddiy hisob to'ldirish). Tasdiqlansa buyurtma o'zi boshlanadi
    add_column("payments", "order_id", "INTEGER")
    db.commit()


# ===== Foydalanuvchilar =====
def save_user(user):
    db.execute(
        "INSERT INTO users (id, full_name, username, joined_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET full_name = excluded.full_name, username = excluded.username",
        (user.id, user.full_name, user.username, now_str()),
    )
    db.commit()


def users_stats():
    week_ago = (datetime.now() - timedelta(days=7)).strftime(TIME_FORMAT)
    one = lambda sql, *args: db.execute(sql, args).fetchone()[0]
    return {
        "total": one("SELECT COUNT(*) FROM users"),
        "today": one("SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", today_str() + "%"),
        "week": one("SELECT COUNT(*) FROM users WHERE joined_at >= ?", week_ago),
    }


# ===== Hamyon =====
def user_waiting_order(user_id):
    """Userning tayyorlanayotgan yoki cheki tekshiruvdagi buyurtmasi (bir vaqtda bittadan).
    Cheki hali yuborilmagan to'lov kutayotgan buyurtma hisoblanmaydi — yangisi uni almashtiradi."""
    rows = as_dicts(db.execute(
        "SELECT * FROM web_orders WHERE user_id = ? AND kind NOT IN ('edit', 'import', 'receipt', 'ai', 'diplom', 'diss', 'pay_review', 'admins') AND ("
        "status IN ('pending', 'working') OR (status = 'awaiting_payment' AND id IN "
        "(SELECT order_id FROM payments WHERE order_id IS NOT NULL AND status = 'pending'))"
        ") ORDER BY id DESC LIMIT 1", (user_id,)
    ))
    return rows[0] if rows else None


def get_balance(user_id):
    row = db.execute("SELECT balance FROM users WHERE id = ?", (user_id,)).fetchone()
    return row[0] if row else 0


def _apply(user_id, amount, kind, note):
    """Balansni o'zgartiradi (commit qilmaydi). Mablag' yetmasa yoki user topilmasa — False."""
    cursor = db.execute(
        "UPDATE users SET balance = balance + ? WHERE id = ? AND balance + ? >= 0", (amount, user_id, amount)
    )
    if cursor.rowcount == 0:
        return False
    db.execute(
        "INSERT INTO transactions (user_id, amount, kind, note, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, kind, note, now_str()),
    )
    return True


def change_balance(user_id, amount, kind, note=""):
    """amount > 0 — qo'shish, amount < 0 — yechish. Yechishda mablag' yetmasa hech narsa o'zgarmaydi."""
    ok = _apply(user_id, amount, kind, note)
    db.commit()
    return ok


def charge_hold(user_id, amount, note=""):
    """Buyurtma uchun pul yechadi va «ushlab turish» yozuvini qo'shadi (bitta tranzaksiyada).
    Qaytaradi: yozuv ID'si; narx 0 bo'lsa — 0; mablag' yetmasa — None."""
    if amount <= 0:
        return 0
    if not _apply(user_id, -amount, "charge", note):
        db.rollback()
        return None
    cursor = db.execute(
        "INSERT INTO charge_holds (user_id, amount, note, created_at) VALUES (?, ?, ?, ?)",
        (user_id, amount, note, now_str()),
    )
    db.commit()
    return cursor.lastrowid


def settle_hold(hold_id):
    """Fayl yetkazildi — pul endi qaytarilmaydi."""
    if hold_id:
        db.execute("DELETE FROM charge_holds WHERE id = ?", (hold_id,))
        db.commit()


def refund_hold(hold_id, note=""):
    """Xato bo'ldi — ushlab turilgan pul qaytariladi (faqat bir marta). Qaytarilsa — summa, aks holda 0."""
    if not hold_id:
        return 0
    row = db.execute("SELECT user_id, amount FROM charge_holds WHERE id = ?", (hold_id,)).fetchone()
    if not row:
        return 0
    cursor = db.execute("DELETE FROM charge_holds WHERE id = ?", (hold_id,))
    if cursor.rowcount == 0 or not _apply(row[0], row[1], "refund", note):
        db.rollback()
        return 0
    db.commit()
    return row[1]


def refund_stale_holds():
    """Bot qayta ishga tushganda: yarim yo'lda qolgan buyurtmalar puli qaytariladi. Qaytadi: [(user_id, summa)]."""
    refunded = []
    for hold_id, user_id in db.execute("SELECT id, user_id FROM charge_holds ORDER BY id").fetchall():
        amount = refund_hold(hold_id, "Bot qayta ishga tushdi")
        if amount:
            refunded.append((user_id, amount))
    return refunded


def last_transactions(user_id, limit=10):
    return db.execute(
        "SELECT amount, kind, note, created_at FROM transactions WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()


# ===== To'lovlar (cheklar) =====
PAYMENT_SELECT = (
    "SELECT p.id, p.user_id, p.amount, p.file_id, p.file_type, p.status, p.created_at, p.order_id, "
    "u.full_name, u.username FROM payments p LEFT JOIN users u ON u.id = p.user_id "
)


def add_payment(user_id, amount, file_id, file_type, order_id=None):
    cursor = db.execute(
        "INSERT INTO payments (user_id, amount, file_id, file_type, created_at, order_id) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, amount, file_id, file_type, now_str(), order_id),
    )
    db.commit()
    return cursor.lastrowid


def get_payment(payment_id):
    rows = as_dicts(db.execute(PAYMENT_SELECT + "WHERE p.id = ?", (payment_id,)))
    return rows[0] if rows else None


def pending_payments(user_id=None, limit=20):
    if user_id is None:
        return as_dicts(db.execute(PAYMENT_SELECT + "WHERE p.status = 'pending' ORDER BY p.id LIMIT ?", (limit,)))
    return as_dicts(db.execute(
        PAYMENT_SELECT + "WHERE p.status = 'pending' AND p.user_id = ? ORDER BY p.id LIMIT ?", (user_id, limit)
    ))


def review_payment(payment_id, approve):
    """Chekni tasdiqlaydi yoki rad etadi. Faqat bir marta ishlaydi: ikkinchi bosishda False."""
    cursor = db.execute(
        "UPDATE payments SET status = ?, reviewed_at = ? WHERE id = ? AND status = 'pending'",
        ("approved" if approve else "rejected", now_str(), payment_id),
    )
    if cursor.rowcount == 0:
        db.rollback()
        return False
    if approve:
        user_id, amount = db.execute("SELECT user_id, amount FROM payments WHERE id = ?", (payment_id,)).fetchone()
        if not _apply(user_id, amount, "topup", f"To'lov #{payment_id}"):
            db.rollback()
            return False
    db.commit()
    return True


def payments_stats():
    one = lambda sql, *args: db.execute(sql, args).fetchone()[0]
    return {
        "pending": one("SELECT COUNT(*) FROM payments WHERE status = 'pending'"),
        "total": one("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'approved'"),
        "today": one(
            "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'approved' AND reviewed_at LIKE ?",
            today_str() + "%",
        ),
        "balances": one("SELECT COALESCE(SUM(balance), 0) FROM users"),
    }


# ===== Taqdimotlar =====
def add_presentation(user_id, topic, slides, price):
    db.execute(
        "INSERT INTO presentations (user_id, topic, slides, created_at, price) VALUES (?, ?, ?, ?, ?)",
        (user_id, topic, slides, now_str(), price),
    )
    db.commit()


def presentations_stats():
    total = db.execute("SELECT COUNT(*) FROM presentations").fetchone()[0]
    today = db.execute("SELECT COUNT(*) FROM presentations WHERE created_at LIKE ?", (today_str() + "%",)).fetchone()[0]
    return total, today


def last_presentations(limit=10):
    return db.execute(
        "SELECT p.topic, p.slides, p.created_at, u.full_name FROM presentations p "
        "LEFT JOIN users u ON u.id = p.user_id ORDER BY p.id DESC LIMIT ?",
        (limit,),
    ).fetchall()


# ===== Hujjatlarim (yuborilgan fayllar — file_id orqali qayta yuboriladi) =====
def add_document(user_id, kind, title, file_id):
    cursor = db.execute(
        "INSERT INTO documents (user_id, kind, title, file_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, kind, title, file_id, now_str()),
    )
    db.commit()
    return cursor.lastrowid


def user_documents(user_id, limit=10):
    return as_dicts(db.execute(
        "SELECT id, kind, title, created_at FROM documents WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)
    ))


def get_document(doc_id, user_id):
    rows = as_dicts(db.execute("SELECT * FROM documents WHERE id = ? AND user_id = ?", (doc_id, user_id)))
    return rows[0] if rows else None


def documents_stats():
    rows = db.execute("SELECT kind, COUNT(*) FROM documents WHERE kind != 'pres' GROUP BY kind").fetchall()
    return dict(rows)


# ===== Titul ma'lumotlari =====
def get_title(user_id):
    row = db.execute("SELECT data FROM titles WHERE user_id = ?", (user_id,)).fetchone()
    return json.loads(row[0]) if row else {}


def save_title(user_id, data):
    db.execute(
        "INSERT INTO titles (user_id, data) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET data = excluded.data",
        (user_id, json.dumps(data, ensure_ascii=False)),
    )
    db.commit()


# ===== Web ilova (slayd-web) =====
def set_meta(key, value):
    db.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value)
    )
    db.commit()


def claim_web_order(busy):
    """Navbatdagi buyurtmani «working» qilib oladi. busy — hozir boshqa buyurtmasi tayyorlanayotgan userlar.
    «edit», «import» (muharrir) va «receipt» (to'lov cheki) ularni kutmaydi — tez bajariladi, AI ishlatmaydi.
    «diplom», «diss» — diplom va dissertatsiya amallari: o'z qulfi bor (service.py), boshqa buyurtmalarni kutmaydi."""
    skip = (f"AND (kind IN ('edit', 'import', 'receipt', 'ai', 'diplom', 'diss', 'pay_review', 'admins') OR user_id NOT IN ({','.join('?' * len(busy))}))"
            if busy else "")
    rows = as_dicts(db.execute(
        f"SELECT * FROM web_orders WHERE status = 'pending' {skip} ORDER BY id LIMIT 1", tuple(busy)
    ))
    if not rows:
        return None
    cursor = db.execute("UPDATE web_orders SET status = 'working' WHERE id = ? AND status = 'pending'", (rows[0]["id"],))
    db.commit()
    return rows[0] if cursor.rowcount else None


def set_web_order_charged(order_id, amount):
    db.execute("UPDATE web_orders SET charged = ? WHERE id = ?", (amount, order_id))
    db.commit()


def finish_web_order(order_id, error=None, document_id=None):
    db.execute(
        "UPDATE web_orders SET status = ?, error = ?, document_id = ?, finished_at = ? WHERE id = ?",
        ("failed" if error else "done", error, document_id, now_str(), order_id),
    )
    db.commit()


# Cheki yuborilmagan «to'lov kutilmoqda» buyurtma. Saytdan yuborilgan chek bir necha soniya navbatda (kind='receipt')
# turadi — u ham hisobga olinadi, aks holda shu orada buyurtma bekor bo'lib qolardi (server orders.js bilan bir xil)
UNPAID = (
    "status = 'awaiting_payment' "
    "AND id NOT IN (SELECT order_id FROM payments WHERE order_id IS NOT NULL AND status = 'pending') "
    "AND id NOT IN (SELECT CAST(json_extract(params, '$.order_id') AS INTEGER) FROM web_orders "
    "WHERE kind = 'receipt' AND status IN ('pending', 'working') AND json_extract(params, '$.order_id') IS NOT NULL)"
)


def add_paid_order(user_id, kind, params, price):
    """To'lov kutayotgan buyurtma (status «awaiting_payment»). Chek tasdiqlansa — navbatga o'tadi.
    Userning cheki yuborilmagan eski shunday buyurtmasi bekor qilinadi (yangisi uning o'rnini oladi)."""
    db.execute(
        f"UPDATE web_orders SET status = 'failed', error = 'Yangi buyurtma bilan almashtirildi.', finished_at = ? "
        f"WHERE user_id = ? AND {UNPAID}",
        (now_str(), user_id),
    )
    cursor = db.execute(
        "INSERT INTO web_orders (user_id, kind, params, price, status, created_at) "
        "VALUES (?, ?, ?, ?, 'awaiting_payment', ?)",
        (user_id, kind, json.dumps(params, ensure_ascii=False), price, now_str()),
    )
    db.commit()
    return cursor.lastrowid


def add_web_order(user_id, kind, params, price=0):
    """Navbatga yangi buyurtma (bot chatidan ham — web ilova bilan bir xil yo'l: orders_worker bajaradi)."""
    cursor = db.execute(
        "INSERT INTO web_orders (user_id, kind, params, price, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, kind, json.dumps(params, ensure_ascii=False), price, now_str()),
    )
    db.commit()
    return cursor.lastrowid


def get_web_order(order_id):
    rows = as_dicts(db.execute("SELECT * FROM web_orders WHERE id = ?", (order_id,)))
    return rows[0] if rows else None


def release_paid_order(order_id, approved, reason=None):
    """Admin chekni ko'rib chiqqach: tasdiqlansa — buyurtma navbatga (pending), aks holda bekor."""
    if approved:
        cursor = db.execute(
            "UPDATE web_orders SET status = 'pending' WHERE id = ? AND status = 'awaiting_payment'", (order_id,)
        )
    else:
        cursor = db.execute(
            "UPDATE web_orders SET status = 'failed', error = ?, finished_at = ? "
            "WHERE id = ? AND status = 'awaiting_payment'",
            (reason or "To'lov tasdiqlanmadi — buyurtma bekor qilindi. Chekni tekshirib, qayta yuboring.",
             now_str(), order_id),
        )
    db.commit()
    return cursor.rowcount > 0


def expire_unpaid_orders(hours=24):
    """Chek yuborilmagan (yoki rad etilgan) eski «to'lov kutilmoqda» buyurtmalarini bekor qiladi."""
    limit = (datetime.now() - timedelta(hours=hours)).strftime(TIME_FORMAT)
    cursor = db.execute(
        "UPDATE web_orders SET status = 'failed', error = 'To''lov kelmadi — buyurtma bekor qilindi.', finished_at = ? "
        f"WHERE created_at < ? AND {UNPAID}",
        (now_str(), limit),
    )
    db.commit()
    return cursor.rowcount


def stuck_web_orders():
    """Bot to'xtab qolganda yarim yo'lda qolgan buyurtmalar."""
    return as_dicts(db.execute("SELECT * FROM web_orders WHERE status = 'working'"))


def add_material(kind, title, pages, file_id, file_type):
    cursor = db.execute(
        "INSERT INTO materials (kind, title, pages, file_id, file_type, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (kind, title, pages, file_id, file_type, now_str()),
    )
    db.commit()
    return cursor.lastrowid


def delete_material(material_id):
    cursor = db.execute("DELETE FROM materials WHERE id = ?", (material_id,))
    db.commit()
    return cursor.rowcount > 0


def last_materials(limit=20):
    return as_dicts(db.execute(
        "SELECT id, kind, title, pages, downloads FROM materials ORDER BY id DESC LIMIT ?", (limit,)
    ))


# ===== AI yordamchi: so'rovlar logi (limit va statistika uchun; mavzu matni yozilmaydi) =====
SECONDS_FORMAT = "%Y-%m-%d %H:%M:%S"
AI_COUNTED = ("queued", "working", "ok")  # xato bilan tugaganlari kunlik limitga kirmaydi


def ai_usage(user_key):
    """(bugun ishlatilgan bepul so'rovlar, oxirgi 60 soniyadagi so'rovlar)."""
    now = datetime.now()
    today = db.execute(
        f"SELECT COUNT(*) FROM ai_requests WHERE user_key = ? AND created_at >= ? AND status IN {AI_COUNTED}",
        (user_key, now.strftime("%Y-%m-%d")),
    ).fetchone()[0]
    recent = db.execute(
        "SELECT COUNT(*) FROM ai_requests WHERE user_key = ? AND created_at >= ?",
        (user_key, (now - timedelta(seconds=60)).strftime(SECONDS_FORMAT)),
    ).fetchone()[0]
    return today, recent


def ai_request_start(user_key, source, kind, status="working"):
    cursor = db.execute(
        "INSERT INTO ai_requests (user_key, source, kind, status, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_key, source, kind, status, datetime.now().strftime(SECONDS_FORMAT)),
    )
    db.commit()
    return cursor.lastrowid


def ai_request_finish(request_id, status, error=None):
    """status: working | ok | error. error — faqat texnik tur (masalan «timeout»), foydalanuvchi matni emas."""
    db.execute(
        "UPDATE ai_requests SET status = ?, error = ?, finished_at = ? WHERE id = ?",
        (status, error, datetime.now().strftime(SECONDS_FORMAT), request_id),
    )
    db.commit()


init_db()
