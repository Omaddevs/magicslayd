"""Maqola moduli testlari (internet va Claude API'siz): model, saqlash, Word/PDF eksport, narx.
Ishga tushirish (bot papkasida):  python -m unittest discover -s tests -v"""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Haqiqiy bazaga tegmaslik uchun — vaqtinchalik papka (config DATA_DIR ni import paytida o'qiydi)
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="slayd-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from articles import storage  # noqa: E402
from articles.export import build  # noqa: E402
from articles.model import normalize, target_words, word_count  # noqa: E402
from config import ARTICLE_PRICE_MIN, ARTICLE_PRICE_PER_100, article_price  # noqa: E402


def png_bytes():
    import pymupdf
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 30), False)
    pix.set_rect(pix.irect, (40, 120, 200))
    return pix.tobytes("png")


BLOCKS = [
    {"t": "h", "level": 2, "align": "left", "runs": [{"text": "Kirish"}]},
    {"t": "p", "align": "justify", "runs": [{"text": "Oʻzbekiston ", "b": 1}, {"text": "gʻalla ", "i": 1, "color": "#C62828"},
                                            {"text": "manba", "link": "https://example.org", "u": 1, "size": 14}]},
    {"t": "ul", "items": [[{"text": "bir ikki"}], [{"text": "uch"}]]},
    {"t": "table", "head": True, "rows": [[[{"text": "A"}], [{"text": "B"}]], [[{"text": "1"}], [{"text": "2"}]]]},
    {"t": "img", "src": "img-1.png", "width": 60, "align": "right", "caption": "1-rasm. Namuna"},
    {"t": "h", "level": 2, "align": "left", "runs": [{"text": "Foydalanilgan adabiyotlar"}]},
    {"t": "ol", "items": [[{"text": "Muallif A. Kitob nomi. 2020."}]]},
]


class ModelTests(unittest.TestCase):
    def test_normalize_drops_bad_values(self):
        out = normalize([
            {"t": "p", "align": "weird", "runs": [{"text": "x", "color": "red", "size": 99, "link": "javascript:alert(1)"}]},
            {"t": "h", "level": 7, "runs": [{"text": "Sarlavha"}]},
            {"t": "p", "runs": [{"text": ""}]},
            {"t": "img", "src": "../secret.txt"},
            {"t": "script"},
            "garbage",
        ])
        self.assertEqual(out[0], {"t": "p", "align": "justify", "runs": [{"text": "x"}]})
        self.assertEqual(out[1]["t"], "h")
        self.assertIn(out[1]["level"], (1, 2, 3))
        self.assertEqual(len(out), 2)  # bo'sh xatboshi, xavfli rasm va noma'lum bloklar tashlandi

    def test_word_count_skips_tables_and_references(self):
        # Kirish(1) + "Oʻzbekiston gʻalla manba"(3) + ro'yxat(3) + "Foydalanilgan adabiyotlar"(2); jadval va adabiyotlar yo'q
        self.assertEqual(word_count(normalize(BLOCKS)), 9)

    def test_target_words_and_price(self):
        self.assertEqual(target_words("short"), 600)
        self.assertEqual(target_words("medium"), 1250)
        self.assertEqual(target_words("custom", 1800), 1800)
        self.assertEqual(article_price(300), max(ARTICLE_PRICE_MIN, 3 * ARTICLE_PRICE_PER_100))
        self.assertEqual(article_price(1250), max(ARTICLE_PRICE_MIN, 13 * ARTICLE_PRICE_PER_100))


class StorageExportTests(unittest.TestCase):
    def setUp(self):
        self.image = png_bytes()
        result = {"title": "Sinov maqolasi", "blocks": BLOCKS, "images": {"img-1.png": self.image}, "notice": ""}
        params = {"type": "scientific", "topic": "Sinov", "lang": "uz", "words": 600, "author": "Ali Valiyev"}
        self.project = storage.save_new(901, 7, params, result)

    def test_save_and_load(self):
        loaded = storage.load(901)
        self.assertEqual(loaded["rev"], 1)
        self.assertEqual(loaded["user_id"], 7)
        self.assertEqual(loaded["author"], "Ali Valiyev")
        self.assertEqual(storage.media_reader(901)("img-1.png"), self.image)
        self.assertIsNone(storage.media_reader(901)("../article.json"))
        self.assertTrue(storage.has_article(901))

    def test_docx_contains_edited_text_link_table_and_image(self):
        from docx import Document
        project = storage.load(901)
        project["blocks"][1]["runs"][0]["text"] = "Tahrirlangan "
        data = build(project, storage.media_reader(901), "docx", project["author"])
        doc = Document(io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("Sinov maqolasi", text)
        self.assertIn("Tahrirlangan gʻalla", text)
        self.assertIn("Ali Valiyev", text)
        self.assertEqual(len(doc.tables), 1)
        self.assertEqual(len(doc.inline_shapes), 1)
        self.assertIn("https://example.org", [r.target_ref for r in doc.part.rels.values()])

    def test_pdf_renders_cyrillic_and_uzbek(self):
        import pymupdf
        project = storage.load(901)
        project["blocks"].append({"t": "p", "align": "left", "runs": [{"text": "Привет, мир"}]})
        data = build(project, storage.media_reader(901), "pdf", project["author"])
        pdf = pymupdf.open(stream=data, filetype="pdf")
        text = "".join(page.get_text() for page in pdf)
        self.assertIn("Oʻzbekiston", text)
        self.assertIn("Привет", text)
        self.assertGreaterEqual(len(pdf[0].get_images()), 1)

    def test_export_rev_and_copy(self):
        storage.save_export(901, "docx", b"x", 1)
        self.assertEqual(storage.exported_rev(901, "docx"), 1)
        self.assertIsNone(storage.exported_rev(901, "pdf"))
        self.assertIsNone(storage.copy_article(901, 902, user_id=8))  # boshqa user nusxa ololmaydi
        copy = storage.copy_article(901, 902, user_id=7)
        self.assertEqual(copy["rev"], 1)
        self.assertEqual(storage.media_reader(902)("img-1.png"), self.image)


class BotFlowTests(unittest.TestCase):
    """Botdagi «📝 Maqola» oqimining har bir ekrani 3 tilda to'g'ri chiziladi (Telegram cheklovlari bilan)."""

    def test_all_steps_all_languages(self):
        from handlers.articles import STEP_STATES, caption_for, result_menu, screen
        for ui in ("uz", "ru", "en"):
            data = {"art_ui": ui, "art_type": "scientific", "art_topic": "Sun'iy <intellekt>", "art_lang": "ru",
                    "art_words": 1250, "art_style": "academic", "art_notes": "Jadval qo'shing & misollar"}
            for step in STEP_STATES:
                text, markup = screen(step, data, 555001)  # oddiy user, balansi 0
                self.assertTrue(text and len(text) < 4096, (ui, step))
                self.assertNotIn("<intellekt>", text)  # HTML qochirilgan
                for row in markup.inline_keyboard:
                    for button in row:
                        self.assertTrue(button.text)
                        if button.callback_data:
                            self.assertLessEqual(len(button.callback_data.encode()), 64)
            # Balans yetmasa — to'lov tugmasi, «yaratish» emas
            _, confirm = screen("confirm", data, 555001)
            callbacks = [b.callback_data for row in confirm.inline_keyboard for b in row]
            self.assertIn("order_pay", callbacks)
            self.assertNotIn("art_go", callbacks)
            project = {"params": {"type": "scientific", "lang": "ru"}, "title": "T", "blocks": normalize(BLOCKS),
                       "notice": "few_sources"}
            self.assertLessEqual(len(caption_for(ui, project, 1)), 1024)
            menu = result_menu(ui, 42)
            labels = [b.callback_data for row in menu.inline_keyboard for b in row if b.callback_data]
            self.assertEqual(set(labels), {"art_file:pdf:42", "art_file:docx:42", "art_redo:42", "art_copy:42"})


if __name__ == "__main__":
    unittest.main()
