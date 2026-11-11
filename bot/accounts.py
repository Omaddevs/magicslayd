"""Telefon + parol hisoblari (web ilova bilan umumiy: slayd-web/server/src/accounts.js).
Parol xeshi ikkala tomonda bir xil formatda: scrypt$N$r$p$salt$hash (base64)."""
import base64
import hashlib
import hmac
import os
import re
import unicodedata

from database import db, now_str

N, R, P, KEY_LEN = 16384, 8, 1, 64
PASSWORD_MIN, PASSWORD_MAX = 6, 64


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.scrypt(unicodedata.normalize("NFKC", password).encode(), salt=salt, n=N, r=R, p=P, dklen=KEY_LEN)
    return f"scrypt${N}${R}${P}${base64.b64encode(salt).decode()}${base64.b64encode(key).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        alg, n, r, p, salt, digest = stored.split("$")
        if alg != "scrypt":
            return False
        expected = base64.b64decode(digest)
        key = hashlib.scrypt(
            unicodedata.normalize("NFKC", password).encode(), salt=base64.b64decode(salt),
            n=int(n), r=int(r), p=int(p), dklen=len(expected), maxmem=64 * 1024 * 1024,
        )
        return hmac.compare_digest(key, expected)
    except (ValueError, TypeError):
        return False


def password_problem(password: str):
    """Xato bo'lsa — matn, to'g'ri bo'lsa — None (ilova bilan bir xil talablar)."""
    if len(password) < PASSWORD_MIN:
        return f"Parol kamida {PASSWORD_MIN} belgidan iborat bo'lsin."
    if len(password) > PASSWORD_MAX:
        return f"Parol {PASSWORD_MAX} belgidan oshmasin."
    if not any(ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password):
        return "Parolda kamida bitta harf va bitta raqam bo'lsin."
    return None


def normalize_phone(raw):
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) == 9:
        digits = "998" + digits
    return digits if re.fullmatch(r"998\d{9}", digits) else None


def format_phone(d: str) -> str:
    return f"+998 {d[3:5]} {d[5:8]} {d[8:10]} {d[10:12]}"


# ===== Baza =====
def account_by_user(user_id):
    row = db.execute("SELECT user_id, phone, verified FROM accounts WHERE user_id = ?", (user_id,)).fetchone()
    return {"user_id": row[0], "phone": row[1], "verified": bool(row[2])} if row else None


def account_by_phone(phone):
    row = db.execute("SELECT user_id, phone, verified FROM accounts WHERE phone = ?", (phone,)).fetchone()
    return {"user_id": row[0], "phone": row[1], "verified": bool(row[2])} if row else None


def save_verified_phone(user_id, phone):
    """Telegram kontakti (o'zining raqami) — tasdiqlangan. Hisob shu raqamda bo'lsa, u ham tasdiqlanadi."""
    db.execute(
        "INSERT INTO verified_phones (user_id, phone, created_at) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET phone = excluded.phone, created_at = excluded.created_at",
        (user_id, phone, now_str()),
    )
    db.execute("UPDATE accounts SET verified = 1 WHERE user_id = ? AND phone = ?", (user_id, phone))
    db.commit()


def remove_account(user_id):
    db.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM accounts WHERE user_id = ?", (user_id,))
    db.commit()


def create_account(user_id, phone, password_hash):
    """Bot orqali: raqam Telegram kontakti bilan kelgani uchun darhol tasdiqlangan."""
    now = now_str()
    db.execute(
        "INSERT INTO accounts (user_id, phone, password_hash, verified, source, created_at, updated_at) "
        "VALUES (?, ?, ?, 1, 'bot', ?, ?)",
        (user_id, phone, password_hash, now, now),
    )
    db.commit()


def set_password_hash(user_id, password_hash):
    """Parolni yangilaydi va barcha sessiyalarni yopadi (boshqa qurilmalardan chiqariladi)."""
    db.execute("UPDATE accounts SET password_hash = ?, updated_at = ? WHERE user_id = ?",
               (password_hash, now_str(), user_id))
    db.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
    db.commit()
