"""Diplom ishi loyihasi: bazada (diplomas jadvali) bitta JSON, fayllar diskda (diplomas/<id>/).

Web ilova ham shu jadvalga yozadi (slayd-web/server/src/routes/diplomas.js). Ikkala tomon ham o'zgartirishni
«o'qi → o'zgartir → yoz» ko'rinishida BITTA tranzaksiyada qiladi — uzoq AI ishi tugagach, loyiha qaytadan
o'qiladi va faqat o'sha qism yoziladi, foydalanuvchining shu paytdagi tahrirlari yo'qolmaydi."""
import copy
import json
import re
import shutil

from config import DATA_DIR
from database import as_dicts, db, now_str

DIPLOMAS_DIR = DATA_DIR / "diplomas"
SAFE_NAME = re.compile(r"^[\w.-]{1,80}$")

INFO_FIELDS = ("topic", "student", "university", "faculty", "direction", "specialty", "course_group", "supervisor",
               "lang", "pages", "extra")

EMPTY = {
    "version": 1,
    "stage": "info",  # info → plan → writing → done
    "info": {"topic": "", "student": "", "university": "", "faculty": "", "direction": "", "specialty": "",
             "course_group": "", "supervisor": "", "lang": "uz", "pages": 60, "extra": ""},
    # Metodik qo'llanma: status none | uploaded | analyzed | sample (qo'llanma yo'q — namunaviy talablar)
    "method": {"file": None, "name": None, "status": "none", "rules": {}, "found": [], "notes": ""},
    "materials": [],  # amaliy qism uchun fayllar: {"file", "name", "chars"}
    "plan": {"field": "", "chapters": [], "approved": False, "sample": True},
    "intro": {"items": [], "status": "empty"},
    "chapters": [],
    "conclusion": {"paragraphs": [], "status": "empty"},
    "sources": [],
    "ops": {"date": "", "count": 0, "plans": 0},
    "export": {"document_id": None, "at": None},
}


def init():
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS diplomas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT, data TEXT NOT NULL,
            paid INTEGER NOT NULL DEFAULT 0, document_id INTEGER, created_at TEXT, updated_at TEXT);
        CREATE INDEX IF NOT EXISTS diplomas_user ON diplomas (user_id, id);
        """
    )
    db.commit()


def folder(diploma_id):
    return DIPLOMAS_DIR / str(int(diploma_id))


def file_path(diploma_id, name):
    """Loyiha fayli (yuklangan qo'llanma, material, rasm). Xavfsiz nom bo'lmasa — None."""
    if not name or not SAFE_NAME.match(name):
        return None
    path = folder(diploma_id) / name
    return path if path.is_file() else None


def new_project(info=None):
    project = copy.deepcopy(EMPTY)
    project["info"].update({k: v for k, v in (info or {}).items() if k in INFO_FIELDS})
    return project


def create(user_id, info=None):
    project = new_project(info)
    cursor = db.execute(
        "INSERT INTO diplomas (user_id, title, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, project["info"]["topic"], json.dumps(project, ensure_ascii=False), now_str(), now_str()),
    )
    db.commit()
    return cursor.lastrowid


def _row(diploma_id, user_id=None):
    sql, args = "SELECT * FROM diplomas WHERE id = ?", [diploma_id]
    if user_id is not None:
        sql, args = sql + " AND user_id = ?", args + [user_id]
    rows = as_dicts(db.execute(sql, args))
    return rows[0] if rows else None


def load(diploma_id, user_id=None):
    """(qator, loyiha) yoki None. user_id berilsa — faqat egasiniki."""
    row = _row(diploma_id, user_id)
    if not row:
        return None
    project = new_project()
    project.update(json.loads(row["data"]))
    return row, project


def update(diploma_id, change):
    """change(project) loyihani joyida o'zgartiradi (await'siz — tranzaksiya qisqa bo'lsin).
    Qaytaradi: change() natijasi. Loyiha topilmasa — KeyError."""
    db.commit()  # ochiq qolgan yashirin tranzaksiya bo'lsa — yopamiz
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute("SELECT data FROM diplomas WHERE id = ?", (diploma_id,)).fetchone()
        if row is None:
            raise KeyError(diploma_id)
        project = new_project()
        project.update(json.loads(row[0]))
        result = change(project)
        db.execute(
            "UPDATE diplomas SET data = ?, title = ?, updated_at = ? WHERE id = ?",
            (json.dumps(project, ensure_ascii=False), project["info"]["topic"], now_str(), diploma_id),
        )
        db.commit()
        return result
    except BaseException:
        db.rollback()
        raise


def user_diplomas(user_id, limit=5):
    return as_dicts(db.execute(
        "SELECT id, title, paid, updated_at, data FROM diplomas WHERE user_id = ? ORDER BY updated_at DESC, id DESC LIMIT ?",
        (user_id, limit),
    ))


def mark_paid(diploma_id, amount):
    """Pul yechilishidan oldin «to'langan» belgisi (faqat bir marta). True — shu chaqiruv belgiladi."""
    cursor = db.execute("UPDATE diplomas SET paid = ? WHERE id = ? AND paid = 0", (max(1, amount), diploma_id))
    db.commit()
    return cursor.rowcount == 1


def unmark_paid(diploma_id):
    db.execute("UPDATE diplomas SET paid = 0 WHERE id = ?", (diploma_id,))
    db.commit()


def is_paid(diploma_id):
    row = db.execute("SELECT paid FROM diplomas WHERE id = ?", (diploma_id,)).fetchone()
    return bool(row and row[0])


def set_document(diploma_id, document_id):
    db.execute("UPDATE diplomas SET document_id = ? WHERE id = ?", (document_id, diploma_id))
    db.commit()


def replace_document_file(document_id, file_id, title):
    """«Hujjatlarim» dagi yozuv yangi faylga ishora qilsin (qayta eksport qilinganda)."""
    db.execute("UPDATE documents SET file_id = ?, title = ? WHERE id = ?", (file_id, title, document_id))
    db.commit()


def delete(diploma_id):
    db.execute("DELETE FROM diplomas WHERE id = ?", (diploma_id,))
    db.commit()
    shutil.rmtree(folder(diploma_id), ignore_errors=True)


init()
