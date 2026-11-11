"""Maqola loyihasini diskda saqlaydi (web muharrir va bot uchun umumiy).

articles/<hujjat_id>/
  article.json  — joriy versiya: {version, user_id, rev, params, title, blocks, notice, created_at, updated_at}
  original.json — AI yozgan dastlabki versiya (qayta tiklash uchun)
  versions/     — oxirgi tahrirlar (web server har saqlashda yozadi, oxirgi 10 tasi qoladi)
  media/        — rasmlar
  export.json   — qaysi versiyadan fayl yasalgan: {"docx": rev, "pdf": rev}; file.docx / file.pdf
Yuklab olishda doim JORIY versiyadan yasalgan fayl beriladi (rev mos kelmasa — qayta yasaladi)."""
import json
import shutil
import time

from config import DATA_DIR
from database import now_str

from articles.model import SAFE_NAME, normalize

ARTICLES_DIR = DATA_DIR / "articles"
KEEP_DAYS = 120


def article_dir(document_id):
    return ARTICLES_DIR / str(int(document_id))


def has_article(document_id):
    return (article_dir(document_id) / "article.json").is_file()


def _write_json(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)  # yozish yarim qolsa ham eski fayl buzilmaydi


def save_new(document_id, user_id, params, result):
    """AI yozgan maqolani saqlaydi. result — articles/ai.py natijasi (rasmlar bytes)."""
    folder = article_dir(document_id)
    media = folder / "media"
    media.mkdir(parents=True, exist_ok=True)
    for name, data in (result.get("images") or {}).items():
        if SAFE_NAME.match(name):
            (media / name).write_bytes(data)
    now = now_str()
    project = {
        "version": 1, "user_id": user_id, "rev": 1, "params": params, "author": params.get("author") or "",
        "title": result["title"], "blocks": result["blocks"], "notice": result.get("notice") or "",
        "created_at": now, "updated_at": now,
    }
    _write_json(folder / "article.json", project)
    _write_json(folder / "original.json", {"title": project["title"], "blocks": project["blocks"]})
    return project


def load(document_id):
    try:
        project = json.loads((article_dir(document_id) / "article.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    project["blocks"] = normalize(project.get("blocks"))
    return project


def media_reader(document_id):
    """Rasm nomidan bytes (topilmasa — None). Eksport shu orqali o'qiydi."""
    media = article_dir(document_id) / "media"

    def read(name):
        file = media / name if name and SAFE_NAME.match(name) else None
        return file.read_bytes() if file and file.is_file() else None
    return read


def export_path(document_id, fmt):
    return article_dir(document_id) / f"file.{fmt}"


def exported_rev(document_id, fmt):
    try:
        return json.loads((article_dir(document_id) / "export.json").read_text(encoding="utf-8")).get(fmt)
    except (OSError, ValueError):
        return None


def save_export(document_id, fmt, data, rev):
    folder = article_dir(document_id)
    export_path(document_id, fmt).write_bytes(data)
    try:
        meta = json.loads((folder / "export.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    meta[fmt] = rev
    _write_json(folder / "export.json", meta)


def copy_article(source_id, target_id, user_id, title_suffix=""):
    """«Yangi nusxa»: joriy versiya va rasmlar yangi hujjatga ko'chiriladi (tarix va eksport — yo'q)."""
    project = load(source_id)
    if project is None or project.get("user_id") != user_id:
        return None
    target = article_dir(target_id)
    (target / "media").mkdir(parents=True, exist_ok=True)
    source_media = article_dir(source_id) / "media"
    if source_media.is_dir():
        for file in source_media.iterdir():
            if file.is_file() and SAFE_NAME.match(file.name):
                shutil.copy2(file, target / "media" / file.name)
    now = now_str()
    copy = {**project, "rev": 1, "title": (project["title"] + title_suffix)[:300], "created_at": now, "updated_at": now}
    _write_json(target / "article.json", copy)
    _write_json(target / "original.json", {"title": copy["title"], "blocks": copy["blocks"]})
    return copy


def cleanup_old_articles():
    """KEEP_DAYS dan beri o'zgarmagan maqola loyihalari o'chiriladi (fayl Telegram chatda qoladi)."""
    if not ARTICLES_DIR.exists():
        return 0
    limit, removed = time.time() - KEEP_DAYS * 86400, 0
    for folder in ARTICLES_DIR.iterdir():
        project = folder / "article.json"
        if folder.is_dir() and (project if project.exists() else folder).stat().st_mtime < limit:
            shutil.rmtree(folder, ignore_errors=True)
            removed += 1
    return removed
