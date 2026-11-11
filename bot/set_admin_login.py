"""Admin uchun web ilovaga kirish (telefon + parol) — ADMIN_ID ga bog'lanadi.
Foydalanish:  python set_admin_login.py +998901234567 "YangiParol1"
Parol bazada faqat xesh ko'rinishida saqlanadi; eski sessiyalar yopiladi."""
import sys

import accounts
from config import ADMIN_ID
from database import db, now_str


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    if not ADMIN_ID:
        sys.exit(".env da ADMIN_ID yozilmagan.")
    phone = accounts.normalize_phone(sys.argv[1])
    password = sys.argv[2]
    if not phone:
        sys.exit("Telefon raqam noto'g'ri (+998 XX XXX XX XX).")
    problem = accounts.password_problem(password)
    if problem:
        sys.exit(problem)
    other = accounts.account_by_phone(phone)
    if other and other["user_id"] != ADMIN_ID:
        sys.exit(f"Bu raqam boshqa userga ({other['user_id']}) bog'langan — avval uni o'chiring.")
    db.execute(
        "INSERT INTO users (id, full_name, joined_at) VALUES (?, 'Admin', ?) ON CONFLICT(id) DO NOTHING",
        (ADMIN_ID, now_str()),
    )
    password_hash = accounts.hash_password(password)
    if accounts.account_by_user(ADMIN_ID):
        db.execute("UPDATE accounts SET phone = ?, verified = 1 WHERE user_id = ?", (phone, ADMIN_ID))
        accounts.set_password_hash(ADMIN_ID, password_hash)
    else:
        accounts.create_account(ADMIN_ID, phone, password_hash)
    db.commit()
    print(f"✅ Admin login tayyor: {accounts.format_phone(phone)} → Telegram ID {ADMIN_ID}")


if __name__ == "__main__":
    main()
