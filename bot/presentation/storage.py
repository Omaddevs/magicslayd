"""Taqdimot loyihasini diskda saqlaydi — web ilovadagi muharrir uchun.
decks/<hujjat_id>/deck.json — matn va tuzilma, media/ — rasm va videolar, file.pptx — oxirgi yig'ilgan fayl.
Saqlangan loyihani AI'siz istalgancha qayta yig'ish mumkin (tahrirlash, dizaynni almashtirish)."""
import io
import json
import logging
import re
import shutil
import time

from PIL import Image

from config import DATA_DIR

DECKS_DIR = DATA_DIR / "decks"
KEEP_DAYS = 60  # shundan eski loyihalar o'chiriladi (fayl Telegram'da qoladi, faqat tahrirlab bo'lmaydi)
SAFE_NAME = re.compile(r"^[\w.-]{1,80}$")
VIDEO_MIME = {".mp4": "video/mp4", ".mov": "video/quicktime", ".m4v": "video/mp4"}


def deck_dir(document_id):
    return DECKS_DIR / str(int(document_id))


def save_deck(document_id, user_id, deck, pptx):
    """Yangi yaratilgan taqdimotni saqlaydi. deck — handlers/presentation.py dagi lug'at (rasmlar bytes)."""
    folder = deck_dir(document_id)
    media = folder / "media"
    media.mkdir(parents=True, exist_ok=True)

    def store(image, name):
        if not image:
            return None
        (media / name).write_bytes(image)
        return name

    content, plans, number = deck["content"], [], 0
    for plan in content["plans"]:
        slides = []
        for slide in plan["slides"]:
            number += 1
            slides.append({
                "title": slide["title"], "kind": slide["kind"], "text": slide.get("text") or "",
                "items": slide.get("items") or [], "image": store(slide.get("image"), f"slide{number}.jpg"),
                "video": None,
            })
        plans.append({"title": plan["title"], "slides": slides})

    project = {
        "version": 1,
        "user_id": user_id,
        "theme": deck["theme"],
        "lang": deck["lang"],
        "author": deck.get("author") or "",
        "content": {
            "title": content["title"],
            "subtitle": content.get("subtitle") or "",
            "cover_image": store(content.get("cover_image"), "cover.jpg"),
            "plans": plans,
            "conclusion": content.get("conclusion") or [],
        },
    }
    (folder / "deck.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
    (folder / "file.pptx").write_bytes(pptx)


def load_deck(document_id):
    """Qayta yig'ish uchun: (loyiha, rasmlari bytes bo'lgan content). Topilmasa — None."""
    folder = deck_dir(document_id)
    try:
        project = json.loads((folder / "deck.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    media = folder / "media"

    def path_of(name):
        if not name or not SAFE_NAME.match(name):
            return None
        file = media / name
        return file if file.is_file() else None

    def read(name):
        """Rasm bytes. Buzuq rasm (yarim yuklangan va h.k.) tashlab yuboriladi — butun taqdimot buzilmasin."""
        file = path_of(name)
        if not file:
            return None
        data = file.read_bytes()
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.load()
        except (OSError, ValueError, Image.DecompressionBombError):
            logging.warning("Buzuq rasm tashlab yuborildi: %s", file)
            return None
        return data

    content = project["content"]
    content["cover_image"] = read(content.get("cover_image"))
    for plan in content["plans"]:
        for slide in plan["slides"]:
            slide["image"] = read(slide.get("image"))
            video = path_of(slide.get("video"))
            slide["video"] = {"path": str(video), "mime": VIDEO_MIME.get(video.suffix.lower(), "video/mp4")} if video else None
    return project, content


def save_file(document_id, pptx):
    (deck_dir(document_id) / "file.pptx").write_bytes(pptx)


def save_project(document_id, user_id, project, media):
    """Import qilingan (PPTX/PDF dan tiklangan) loyihani saqlaydi. file.pptx yozilmaydi —
    birinchi saqlashgacha yuklab olishda asl fayl beriladi."""
    folder = deck_dir(document_id)
    (folder / "media").mkdir(parents=True, exist_ok=True)
    for name, data in media.items():
        (folder / "media" / name).write_bytes(data)
    project["user_id"] = user_id
    (folder / "deck.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")


def read_source(document_id):
    """Saytdan yuklangan asl fayl (source.pptx / source.pdf), bo'lmasa None."""
    for name in ("source.pptx", "source.pdf"):
        file = deck_dir(document_id) / name
        if file.is_file():
            return file.read_bytes()
    return None


def cleanup_old_decks():
    """KEEP_DAYS dan beri o'zgarmagan loyihalarni o'chiradi (disk to'lib qolmasligi uchun)."""
    if not DECKS_DIR.exists():
        return 0
    limit, removed = time.time() - KEEP_DAYS * 86400, 0
    for folder in DECKS_DIR.iterdir():
        if not folder.is_dir():
            continue
        project = folder / "deck.json"
        if (project if project.exists() else folder).stat().st_mtime < limit:
            shutil.rmtree(folder, ignore_errors=True)
            removed += 1
    return removed
