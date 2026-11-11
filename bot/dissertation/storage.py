"""Dissertatsiya loyihasi: bazada (dissertations jadvali) bitta JSON, fayllar diskda (dissertations/<id>/).

Web ilova ham shu jadvalga yozadi (slayd-web/server/src/routes/dissertations.js). Ikkala tomon ham o'zgartirishni
«o'qi → o'zgartir → yoz» ko'rinishida BITTA tranzaksiyada qiladi — uzoq AI ishi tugagach loyiha qaytadan o'qiladi
va faqat o'sha qism yoziladi. Har bir qism AI qayta yozishidan oldin tarixga (oxirgi 5 versiya) saqlanadi."""
import copy
import json
import re
import shutil
import time

from config import DATA_DIR
from database import as_dicts, db, now_str

DIR = DATA_DIR / "dissertations"
SAFE_NAME = re.compile(r"^[\w.-]{1,80}$")
HISTORY_MAX = 5

INFO_FIELDS = ("student", "university", "faculty", "specialty", "specialty_code", "degree", "supervisor", "lang",
               "pages", "topic", "direction", "problem", "existing", "extra")

EMPTY = {
    "version": 1,
    "stage": "type",  # type → info → plan → writing → done
    "kind": "",       # master | phd | dsc | other
    "info": {"student": "", "university": "", "faculty": "", "specialty": "", "specialty_code": "", "degree": "",
             "supervisor": "", "lang": "uz", "pages": 80, "topic": "", "direction": "", "problem": "",
             "existing": "", "extra": ""},
    "suggestions": [],  # AI taklif qilgan mavzular
    "method": {"file": None, "name": None, "status": "none", "rules": {}, "found": [], "notes": ""},
    "materials": [],    # {"file", "name", "kind"} — pdf/docx/txt/csv/xlsx/png/jpg
    "plan": {"field": "", "chapters": [], "approved": False, "sample": True, "queries": []},
    "intro": {"items": [], "status": "empty"},
    "chapters": [],
    "conclusion": {"paragraphs": [], "status": "empty"},
    "annotation": {"paragraphs": [], "keywords": [], "status": "empty"},
    "sources": [],
    "history": {},      # qism kaliti → [{"at", "reason", "data"}] (eng yangisi oxirida)
    "quality": {"at": None, "checks": [], "review": []},
    "ops": {"date": "", "count": 0, "plans": 0},
}


def init():
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS dissertations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT, data TEXT NOT NULL,
            paid INTEGER NOT NULL DEFAULT 0, document_id INTEGER, created_at TEXT, updated_at TEXT);
        CREATE INDEX IF NOT EXISTS dissertations_user ON dissertations (user_id, id);
        """
    )
    db.commit()


def folder(item_id):
    return DIR / str(int(item_id))


def file_path(item_id, name):
    if not name or not SAFE_NAME.match(name):
        return None
    path = folder(item_id) / name
    return path if path.is_file() else None


def new_project(**values):
    project = copy.deepcopy(EMPTY)
    for key, value in values.items():
        if key == "info":
            project["info"].update({k: v for k, v in value.items() if k in INFO_FIELDS})
        else:
            project[key] = value
    return project


def _merge(data):
    project = new_project()
    project.update(json.loads(data))
    for key in ("info", "method", "plan", "intro", "conclusion", "annotation", "quality", "ops"):
        merged = copy.deepcopy(EMPTY[key])
        merged.update(project.get(key) or {})
        project[key] = merged
    return project


def create(user_id, kind, info=None):
    project = new_project(kind=kind, stage="info", info=info or {})
    cursor = db.execute(
        "INSERT INTO dissertations (user_id, title, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, project["info"]["topic"], json.dumps(project, ensure_ascii=False), now_str(), now_str()),
    )
    db.commit()
    return cursor.lastrowid


def load(item_id, user_id=None):
    sql, args = "SELECT * FROM dissertations WHERE id = ?", [item_id]
    if user_id is not None:
        sql, args = sql + " AND user_id = ?", args + [user_id]
    rows = as_dicts(db.execute(sql, args))
    return (rows[0], _merge(rows[0]["data"])) if rows else None


def update(item_id, change):
    """change(project) loyihani joyida o'zgartiradi (await'siz). Natijasini qaytaradi. Topilmasa — KeyError."""
    db.commit()
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute("SELECT data FROM dissertations WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise KeyError(item_id)
        project = _merge(row[0])
        result = change(project)
        db.execute(
            "UPDATE dissertations SET data = ?, title = ?, updated_at = ? WHERE id = ?",
            (json.dumps(project, ensure_ascii=False), project["info"]["topic"], now_str(), item_id),
        )
        db.commit()
        return result
    except BaseException:
        db.rollback()
        raise


def remember(project, key, part, reason):
    """Qismning hozirgi holatini tarixga qo'yadi (AI uni o'zgartirishidan oldin). Bo'sh qism saqlanmaydi."""
    if not part or not any(part.get(k) for k in ("items", "sections", "paragraphs")):
        return
    history = project["history"].setdefault(key, [])
    history.append({"at": time.strftime("%Y-%m-%d %H:%M"), "reason": reason, "data": copy.deepcopy(part)})
    del history[:-HISTORY_MAX]


def user_items(user_id, limit=5):
    return as_dicts(db.execute(
        "SELECT id, title, paid, updated_at FROM dissertations WHERE user_id = ? ORDER BY updated_at DESC, id DESC LIMIT ?",
        (user_id, limit),
    ))


def mark_paid(item_id, amount):
    """Pul yechilishidan oldin «to'langan» belgisi — faqat bir marta. True — shu chaqiruv belgiladi."""
    cursor = db.execute("UPDATE dissertations SET paid = ? WHERE id = ? AND paid = 0", (max(1, amount), item_id))
    db.commit()
    return cursor.rowcount == 1


def unmark_paid(item_id):
    db.execute("UPDATE dissertations SET paid = 0 WHERE id = ?", (item_id,))
    db.commit()


def set_document(item_id, document_id):
    db.execute("UPDATE dissertations SET document_id = ? WHERE id = ?", (document_id, item_id))
    db.commit()


def replace_document_file(document_id, file_id, title):
    db.execute("UPDATE documents SET file_id = ?, title = ? WHERE id = ?", (file_id, title, document_id))
    db.commit()


def delete(item_id):
    db.execute("DELETE FROM dissertations WHERE id = ?", (item_id,))
    db.commit()
    shutil.rmtree(folder(item_id), ignore_errors=True)


init()
