"""Referat / mustaqil ish / kurs ishi loyihasini diskda saqlaydi — web ilovadagi muharrir uchun.
papers/<hujjat_id>/paper.json — matn va tuzilma, media/ — boblar rasmlari, file.docx (yoki file.pdf) — oxirgi fayl.
Saqlangan loyihani AI'siz istalgancha qayta yig'ish mumkin (presentation/storage.py bilan bir xil yondashuv)."""
import io
import json
import logging
import re
import shutil
import time

from PIL import Image

from config import DATA_DIR

PAPERS_DIR = DATA_DIR / "papers"
KEEP_DAYS = 60  # shundan eski loyihalar o'chiriladi (fayl Telegram'da qoladi, faqat tahrirlab bo'lmaydi)
SAFE_NAME = re.compile(r"^[\w.-]{1,80}$")


def paper_dir(document_id):
    return PAPERS_DIR / str(int(document_id))


def has_paper(document_id):
    return (paper_dir(document_id) / "paper.json").is_file()


def save_paper(document_id, user_id, kind, lang, fmt, title, content, file, imported=False):
    """Yangi yozilgan (yoki fayldan tiklangan) ishni saqlaydi. content — documents/ai.py natijasi
    (bob rasmlari bytes), title — muqovadagi titul ma'lumotlari (keyin muharrirda o'zgartirsa bo'ladi).
    file=None — fayl yozilmaydi: birinchi saqlashgacha yuklab olishda asl fayl beriladi."""
    folder = paper_dir(document_id)
    media = folder / "media"
    media.mkdir(parents=True, exist_ok=True)

    chapters = []
    for i, chapter in enumerate(content["chapters"], 1):
        image = None
        if chapter.get("image"):
            image = f"ch{i}.jpg"
            (media / image).write_bytes(chapter["image"])
        sections = []
        for j, s in enumerate(chapter["sections"], 1):
            section_image = None
            if s.get("image"):
                section_image = f"ch{i}s{j}.jpg"
                (media / section_image).write_bytes(s["image"])
            sections.append({"title": s["title"], "paragraphs": list(s["paragraphs"]), "image": section_image})
        chapters.append({"title": chapter["title"], "image": image, "sections": sections})

    project = {
        "version": 1,
        "user_id": user_id,
        "kind": kind,
        "lang": lang,
        "fmt": fmt,
        "imported": imported,
        "title_page": dict(title or {}),
        "content": {
            "title": content["title"],
            "intro": list(content["intro"]),
            "chapters": chapters,
            "conclusion": list(content["conclusion"]),
            "references": list(content["references"]),
        },
    }
    (folder / "paper.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
    if file is not None:
        save_paper_file(document_id, file, fmt)


def load_paper(document_id):
    """Qayta yig'ish uchun: (loyiha, rasmlari bytes bo'lgan content). Topilmasa — None."""
    folder = paper_dir(document_id)
    try:
        project = json.loads((folder / "paper.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    def read(name):
        """Rasm bytes. Buzuq rasm tashlab yuboriladi — butun hujjat buzilmasin."""
        file = folder / "media" / name if name and SAFE_NAME.match(name) else None
        if not file or not file.is_file():
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
    for chapter in content["chapters"]:
        chapter["image"] = read(chapter.get("image"))
        for section in chapter["sections"]:
            section["image"] = read(section.get("image"))  # eski loyihalarda yo'q — None
    return project, content


def save_paper_file(document_id, data, fmt):
    folder = paper_dir(document_id)
    (folder / f"file.{fmt}").write_bytes(data)
    # Format o'zgarmaydi, lekin eski boshqa formatdagi fayl qolib ketmasin (sayt shu fayllardan birini beradi)
    for other in ("docx", "pdf"):
        if other != fmt:
            (folder / f"file.{other}").unlink(missing_ok=True)


def cleanup_old_papers():
    """KEEP_DAYS dan beri o'zgarmagan loyihalarni o'chiradi (disk to'lib qolmasligi uchun)."""
    if not PAPERS_DIR.exists():
        return 0
    limit, removed = time.time() - KEEP_DAYS * 86400, 0
    for folder in PAPERS_DIR.iterdir():
        project = folder / "paper.json"
        if folder.is_dir() and (project if project.exists() else folder).stat().st_mtime < limit:
            shutil.rmtree(folder, ignore_errors=True)
            removed += 1
    return removed
