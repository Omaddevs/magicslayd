"""Adminlar: bot egasi (.env → ADMIN_ID) va u qo'shgan qo'shimcha adminlar (eng ko'pi ADMINS_EXTRA_MAX ta).

- Ega — doim admin va barcha huquqlarga ega, o'chirib bo'lmaydi. Faqat u adminlarni qo'shadi / o'chiradi va
  har biriga huquq beradi (botda /adminlar, web admin panelda «👑 Adminlar»).
- Qo'shimcha admin standart bo'yicha faqat cheklarni ko'radi va tasdiqlaydi (DEFAULT_PERMS). Qolgan huquqlarni
  (PERMS) ega o'zi yoqadi. Har bir bo'lim / buyruq shu huquqqa qarab ochiladi: botda Can("...") filtri,
  web serverda requirePerm("...") (web/server/src/admins.js — xuddi shu jadval va qoidalar).
- Qo'shimcha admin pul bilan bog'liq amal qilsa (chek, balans) — egaga Telegram'da xabar boradi."""
import html
import logging

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from config import ADMIN_ID, ADMINS_EXTRA_MAX
from database import add_column, as_dicts, db, now_str

OWNER_ID = ADMIN_ID

# Huquqlar (tartibi — ekrandagi tartib). Web server ham shu kalitlarni ishlatadi
PERMS = {
    "payments": "💳 Cheklarni ko'rish va tasdiqlash",
    "users": "👤 Userlar: qidirish, xabar yozish",
    "balance": "💰 Balansni o'zgartirish",
    "broadcast": "📣 Xabar tarqatish, yangilik, story, reklama",
    "stats": "📊 Statistika, xarajat va API",
    "free": "🎁 O'z buyurtmalari bepul",
}
DEFAULT_PERMS = ("payments",)

# name — qo'shilganda Telegram'dan olingan ism (botga hali /start bosmagan bo'lsa ham ro'yxatda ko'rinsin)
# perms — vergul bilan ajratilgan huquqlar (NULL — DEFAULT_PERMS)
db.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, added_by INTEGER, added_at TEXT, name TEXT)")
add_column("admins", "perms", "TEXT")
db.commit()


class AdminError(Exception):
    """Foydalanuvchiga ko'rsatiladigan xato (masalan «2 tadan ortiq admin bo'lmaydi»)."""


def parse_perms(value):
    if value is None:
        return set(DEFAULT_PERMS)
    return {p for p in str(value).split(",") if p in PERMS}


def is_owner(user_id):
    return bool(OWNER_ID) and user_id == OWNER_ID


def extra_admins():
    """Qo'shimcha adminlar (ega emas): [{user_id, full_name, username, added_at, perms}], qo'shilish tartibida."""
    rows = as_dicts(db.execute(
        "SELECT a.user_id, COALESCE(u.full_name, a.name) AS full_name, u.username, a.added_at, a.perms FROM admins a "
        "LEFT JOIN users u ON u.id = a.user_id WHERE a.user_id != ? ORDER BY a.added_at, a.user_id",
        (OWNER_ID or 0,),
    ))
    for row in rows:
        row["perms"] = [p for p in PERMS if p in parse_perms(row["perms"])]
    return rows


def perms_of(user_id):
    """Userning huquqlari (to'plam). Ega — hammasi, admin bo'lmasa — bo'sh."""
    if not user_id:
        return set()
    if is_owner(user_id):
        return set(PERMS)
    row = db.execute("SELECT perms FROM admins WHERE user_id = ?", (user_id,)).fetchone()
    return parse_perms(row[0]) if row else set()


def has_perm(user_id, perm):
    return perm in perms_of(user_id)


def admin_ids(perm=None):
    """Adminlar (avval ega). perm berilsa — faqat shu huquqi borlar (masalan cheklar faqat «payments» egalariga)."""
    ids = [OWNER_ID] if OWNER_ID else []
    return ids + [row["user_id"] for row in extra_admins() if perm is None or perm in row["perms"]]


def is_admin(user_id):
    """Ega yoki qo'shimcha admin (huquqidan qat'i nazar) — admin panelni ochadi, bo'limlari huquqqa qarab."""
    if not user_id:
        return False
    if is_owner(user_id):
        return True
    return db.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)).fetchone() is not None


def add_admin(user_id, added_by, name=None):
    """Faqat ega qo'shadi. Yangi admin huquqlari — DEFAULT_PERMS. Xato bo'lsa — AdminError (sababi bilan)."""
    if not is_owner(added_by):
        raise AdminError("Adminlarni faqat bot egasi qo'sha oladi.")
    if not isinstance(user_id, int) or user_id <= 0:
        raise AdminError("Telegram ID noto'g'ri.")
    if is_owner(user_id):
        raise AdminError("Siz bot egasisiz — allaqachon bosh adminsiz.")
    if is_admin(user_id):
        raise AdminError("Bu foydalanuvchi allaqachon admin.")
    if len(extra_admins()) >= ADMINS_EXTRA_MAX:
        raise AdminError(f"Ko'pi bilan {ADMINS_EXTRA_MAX} ta qo'shimcha admin bo'ladi. Avval birini o'chiring.")
    db.execute("INSERT INTO admins (user_id, added_by, added_at, name, perms) VALUES (?, ?, ?, ?, ?)",
               (user_id, added_by, now_str(), (name or "").strip()[:100] or None, ",".join(DEFAULT_PERMS)))
    db.commit()


def set_perms(user_id, perms, changed_by):
    """Faqat ega o'zgartiradi. perms — huquqlar ro'yxati (noma'lumlari tashlanadi)."""
    if not is_owner(changed_by):
        raise AdminError("Huquqlarni faqat bot egasi beradi.")
    if is_owner(user_id):
        raise AdminError("Bot egasi doim barcha huquqlarga ega.")
    if not is_admin(user_id):
        raise AdminError("Bu foydalanuvchi admin emas.")
    clean = [p for p in PERMS if p in set(perms)]
    db.execute("UPDATE admins SET perms = ? WHERE user_id = ?", (",".join(clean), user_id))
    db.commit()
    return clean


def remove_admin(user_id, removed_by):
    if not is_owner(removed_by):
        raise AdminError("Adminlarni faqat bot egasi o'chira oladi.")
    if is_owner(user_id):
        raise AdminError("Bot egasini o'chirib bo'lmaydi.")
    cursor = db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    db.commit()
    if not cursor.rowcount:
        raise AdminError("Bu foydalanuvchi admin emas.")


def perms_text(perms):
    """Huquqlar ro'yxati matni (xabarlar uchun)."""
    return "\n".join(f"• {PERMS[p]}" for p in PERMS if p in set(perms)) or "• (hech qanday huquq yo'q)"


def display_name(user_id):
    """«Ism (@username)» — bazada bo'lmasa ID."""
    row = db.execute("SELECT full_name, username FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        saved = db.execute("SELECT name FROM admins WHERE user_id = ?", (user_id,)).fetchone()
        return saved[0] if saved and saved[0] else f"ID {user_id}"
    name = row[0] or f"ID {user_id}"
    return f"{name} (@{row[1]})" if row[1] else name


async def notify_owner(bot, actor_id, text):
    """Qo'shimcha admin pul bilan bog'liq amal qilsa (chek, balans) — egaga qisqa xabar (nazorat uchun)."""
    if not OWNER_ID or is_owner(actor_id):
        return
    try:
        await bot.send_message(OWNER_ID, f"👮 <b>{html.escape(display_name(actor_id))}</b>: {text}")
    except Exception:  # noqa: BLE001 — nazorat xabari asosiy amalni to'xtatmasin
        logging.warning("Egaga nazorat xabari yuborilmadi")


class IsAdmin(BaseFilter):
    """aiogram filtri: xabar yoki tugma admin (ega yoki qo'shimcha) tomonidanmi."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return bool(event.from_user) and is_admin(event.from_user.id)


class Can(BaseFilter):
    """aiogram filtri: adminda shu huquq bormi (ega — doim bor). Masalan: @router.message(Command("stats"), Can("stats"))."""

    def __init__(self, perm):
        assert perm in PERMS, perm
        self.perm = perm

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return bool(event.from_user) and has_perm(event.from_user.id, self.perm)


class IsOwner(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return bool(event.from_user) and is_owner(event.from_user.id)
