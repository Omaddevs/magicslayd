"""Tayyor fayllarning xususiyatlari (Fayl → Ma'lumotlar → Xususiyatlar).
Kutubxonalar o'z izini qoldiradi: «python-docx» muallif, «Steve Canny» oxirgi tahrirchi, «generated using python-pptx»
izohi. Foydalanuvchi ishini topshirganda bular ko'rinmasligi kerak — hammasi tozalanadi, faqat sarlavha qoladi."""
from datetime import datetime


def clean_properties(core, title=""):
    """core — python-docx yoki python-pptx dagi `core_properties` (ikkalasida maydonlar bir xil)."""
    now = datetime.now().replace(microsecond=0)
    for field in ("author", "last_modified_by", "comments", "keywords", "subject", "category", "content_status",
                  "identifier", "language", "version"):
        setattr(core, field, "")
    core.title = (title or "")[:250]
    core.created = core.modified = now
    core.revision = 1
