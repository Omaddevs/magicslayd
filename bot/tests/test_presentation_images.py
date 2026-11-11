"""Taqdimot rasmlari: soni (kam ham, ko'p ham emas), qaysi slaydga qo'yilishi, AI tekshiruvi va
mos rasm topilmaganda tartib (AI chizadi → boshqa slayd fotosi → mavzu fotosi)."""
import asyncio
import io
import os
import tempfile
import unittest
from unittest import mock

# Haqiqiy bazaga tegmaslik uchun — vaqtinchalik papka (config DATA_DIR ni import paytida o'qiydi)
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="slayd-test-"))

from PIL import Image  # noqa: E402

from config import FIXED_SLIDES, IMAGES_MAX, SLIDE_OPTIONS, image_count, image_plan_text  # noqa: E402
from presentation import ai, images  # noqa: E402


class ImageCountTest(unittest.TestCase):
    def test_table(self):
        expected = {5: 1, 8: 3, 10: 4, 15: 8, 20: 11, 30: 18, 40: 25, 50: 30, 80: 30}
        self.assertEqual({n: image_count(n) for n in expected}, expected)

    def test_never_too_few_or_too_many(self):
        for slides in range(5, 81):
            inner = slides - FIXED_SLIDES
            count = image_count(slides)
            self.assertGreaterEqual(count, 1)
            self.assertLessEqual(count, IMAGES_MAX)
            self.assertLess(count, inner + 1)
            if inner >= 4:
                self.assertLess(count, inner, "hamma slaydga emas — matnli slaydlar ham qoladi")
            # chegaragacha — ichki slaydlarning kamida ~65 % ida rasm
            if inner * 0.7 <= IMAGES_MAX:
                self.assertGreaterEqual(count, int(inner * 0.65))

    def test_help_text_matches(self):
        text = image_plan_text()
        for n in (5, 10, 20, 30, 50):
            self.assertIn(f"{n} slaydga — {image_count(n)} ta", text)

    def test_all_options_valid(self):
        for n in SLIDE_OPTIONS:
            self.assertTrue(1 <= image_count(n) <= IMAGES_MAX)


def make_flat(kinds):
    return [(0, {"title": f"S{i}", "kind": k, "image_query": f"query {i}"}) for i, k in enumerate(kinds)]


class SlotsTest(unittest.TestCase):
    def test_prefers_layouts_that_keep_their_design(self):
        flat = make_flat(["cards", "bullets", "timeline", "bullets", "stats", "quote", "cards", "bullets"])
        slots = ai.image_slots(flat, 3)
        self.assertEqual(len(slots), 3)
        self.assertTrue(all(flat[i][1]["kind"] in ai.IMAGE_FRIENDLY for i in slots))

    def test_fills_with_others_when_needed(self):
        flat = make_flat(["cards", "bullets", "timeline", "cards"])
        slots = ai.image_slots(flat, 3)
        self.assertEqual(len(slots), 3)
        self.assertIn(1, slots)
        self.assertEqual(len(set(slots)), 3)

    def test_spread_evenly(self):
        flat = make_flat(["bullets"] * 20)
        slots = ai.image_slots(flat, 5)
        gaps = [b - a for a, b in zip(slots, slots[1:])]
        self.assertTrue(all(3 <= g <= 5 for g in gaps), slots)

    def test_skip(self):
        flat = make_flat(["bullets"] * 6)
        self.assertFalse(set(ai.image_slots(flat, 3, skip={0, 2, 4})) & {0, 2, 4})


class GenerateTest(unittest.TestCase):
    """generate_content: AI, rasm qidiruvi va rasm chizish soxta — faqat rasm taqsimoti tekshiriladi."""

    def run_generate(self, slides, kinds, available, drawable=frozenset()):
        """available — qaysi so'rovlar uchun «mos foto» bor; drawable — AI qaysilarini chiza oladi.
        Mavzu bo'yicha foto har doim bor."""
        content_count = slides - FIXED_SLIDES
        calls = []

        async def fake_outline(topic, counts, lang):
            n = sum(counts)
            return {"title": "T", "subtitle": "", "image_query": "TOPIC", "image_prompt": "",
                    "plans": [{"title": "P", "slides": [{"title": f"S{i}", "kind": kinds[i % len(kinds)]} for i in range(n)]}]}

        async def fake_chunk(topic, lang, outline, chunk):
            for _, slide in chunk:
                slide["image_query"] = f"q{slide['title'][1:]}"

        async def fake_conclusion(*a):
            return ["x"]

        async def fake_find(queries, used=None, fallback=None, checks=None):
            self.assertEqual(len(checks), len(queries), "har bir rasm AI tekshiruvidan o'tadi")
            self.assertTrue(all(callable(c) for c in checks))
            calls.append((list(queries), fallback))
            return [f"IMG:{q}" if q in available else (f"TOPIC:{q}" if fallback else None) for q in queries]

        async def fake_draw(slides, topic, style=None, outline=None):
            calls.append(("draw", [s["image_query"] for s in slides]))
            return [f"AI:{s['image_query']}" if s["image_query"] in drawable else None for s in slides]

        with mock.patch.object(ai, "make_outline", fake_outline), mock.patch.object(ai, "write_chunk", fake_chunk), \
                mock.patch.object(ai, "write_conclusion", fake_conclusion), mock.patch.object(ai, "find_images", fake_find), \
                mock.patch.object(ai, "draw_missing", fake_draw):
            outline, found = asyncio.run(ai.generate_content("topic", 1, slides, "uz", image_count(slides)))
        flat = [s for p in outline["plans"] for s in p["slides"]]
        self.assertEqual(len(flat), content_count)
        self.assertEqual(found, sum(1 for s in flat if s.get("image")))
        return flat, found, calls

    def test_all_found_on_own_topic(self):
        kinds = ["bullets", "cards", "timeline", "bullets", "quote", "stats"]
        flat, found, calls = self.run_generate(20, kinds, {f"q{i}" for i in range(16)})
        self.assertEqual(found, image_count(20))
        images_ = [s for s in flat if s.get("image")]
        self.assertTrue(all(s["image"].startswith("IMG:") for s in images_), "hammasi o'z mavzusi bo'yicha")
        self.assertTrue(all(c[1] is None for c in calls if c[0] != "draw"), "umumiy mavzu kerak bo'lmadi")
        friendly = [s for s in flat if s["kind"] in ai.IMAGE_FRIENDLY]
        self.assertTrue(all(s.get("image") for s in friendly), "avval maketi buzilmaydigan slaydlarga")

    def test_thirty_slides_get_eighteen(self):
        flat, found, _ = self.run_generate(30, ["bullets", "cards"], {f"q{i}" for i in range(26)})
        self.assertEqual(found, 18)

    def test_ai_draws_missing_instead_of_generic(self):
        kinds = ["bullets"] * 16
        selected = set(ai.image_slots([(0, {"kind": "bullets"})] * 16, image_count(20)))
        missing = {i for i in selected if i % 3 == 0}
        available = {f"q{i}" for i in range(16) if i not in missing}
        flat, found, calls = self.run_generate(20, kinds, available, drawable={f"q{i}" for i in missing})
        self.assertEqual(found, image_count(20))
        for i in missing:
            self.assertEqual(flat[i]["image"], f"AI:q{i}", "aynan shu slayd uchun AI chizgan")
        self.assertFalse(any(s.get("image", "").startswith("TOPIC:") for s in flat))

    def test_other_slide_when_ai_unavailable(self):
        kinds = ["bullets"] * 16
        selected = set(ai.image_slots([(0, {"kind": "bullets"})] * 16, image_count(20)))
        # 4 ta tanlangan slaydga foto yo'q — rasmsiz 5 ta slayddan 4 tasining o'z fotosi olinadi
        available = {f"q{i}" for i in range(16) if i not in selected or i % 5}
        flat, found, calls = self.run_generate(20, kinds, available)
        self.assertEqual(found, image_count(20))
        self.assertTrue(all(s["image"].startswith("IMG:") for s in flat if s.get("image")),
                        "umumiy mavzu rasmi o'rniga boshqa slaydning mos rasmi")

    def test_generic_topic_only_as_last_resort(self):
        flat, found, calls = self.run_generate(10, ["bullets"], set())
        self.assertEqual(found, image_count(10))
        self.assertTrue(all(s["image"].startswith("TOPIC:") for s in flat if s.get("image")))
        self.assertIsNotNone(calls[-1][1], "oxirgi chorada mavzu bo'yicha qidirildi")

    def test_no_more_than_planned(self):
        flat, found, _ = self.run_generate(80, ["bullets", "cards"], {f"q{i}" for i in range(76)})
        self.assertEqual(found, IMAGES_MAX)


def jpeg(color):
    buffer = io.BytesIO()
    Image.new("RGB", (800, 500), color).save(buffer, "JPEG")
    return buffer.getvalue()


class CheckedSearchTest(unittest.TestCase):
    """images.find_images: AI tekshiruvi mos emas degan rasm olinmaydi, keyingi nomzodga o'tiladi."""

    def run_find(self, results, check):
        pictures = {url: jpeg(color) for url, color in
                    {"u1": (200, 30, 30), "u2": (30, 200, 30), "u3": (30, 30, 200)}.items()}
        # dHash bir xil rangli rasmlarda bir xil chiqadi — dublikat tekshiruvi aralashmasin
        marks = {pictures["u1"]: 1, pictures["u2"]: 2 ** 40, pictures["u3"]: 2 ** 63 - 1}

        async def fake_search(session, query, chosen=None):
            return results if chosen[0] == "pixabay" else []

        async def fake_download(session, url):
            return pictures.get(url)

        with mock.patch.object(images, "search", fake_search), mock.patch.object(images, "download", fake_download), \
                mock.patch.object(images, "fingerprint", lambda data: marks[data]), \
                mock.patch.object(images, "sources", lambda: [("pixabay", None), ("wikimedia", None)]):
            return asyncio.run(images.find_images(["teacher classroom"], set(), None, [check])), pictures

    def test_rejected_photo_is_skipped(self):
        seen = []

        async def check(image):
            seen.append(image)
            return len(seen) == 2  # birinchisi mos emas, ikkinchisi mos

        results = [("u1", "teacher classroom school"), ("u2", "teacher classroom lesson")]
        (found,), pictures = self.run_find(results, check)
        self.assertEqual(found, pictures["u2"])

    def test_loose_candidates_only_with_check(self):
        async def yes(image):
            return True

        results = [("u3", "teacher portrait")]  # faqat asosiy predmet mos — AI ko'rib qaror qiladi
        (found,), pictures = self.run_find(results, yes)
        self.assertEqual(found, pictures["u3"])
        (found,), _ = self.run_find(results, None)
        self.assertIsNone(found, "AI tekshiruvisiz — faqat teglari qat'iy mos rasm")

    def test_check_error_rejects_photo(self):
        """AI tekshira olmasa — foto olinmaydi (teglar yolg'on bo'lishi mumkin); slaydga AI rasm chizadi."""
        async def broken(image):
            return None

        results = [("u3", "teacher portrait"), ("u1", "teacher classroom")]
        (found,), _ = self.run_find(results, broken)
        self.assertIsNone(found)

    def test_check_limit(self):
        calls = []

        async def no(image):
            calls.append(1)
            return False

        results = [(f"u{i}", "teacher classroom") for i in (1, 2, 3)] * 3
        (found,), _ = self.run_find(results, no)
        self.assertIsNone(found)
        self.assertLessEqual(len(calls), images.MAX_CHECKS)


class TrimBarsTest(unittest.TestCase):
    def test_letterbox_removed(self):
        image = Image.new("RGB", (1000, 1000), (0, 0, 0))
        image.paste(Image.new("RGB", (1000, 750), (120, 160, 200)), (0, 125))
        self.assertEqual(images.trim_bars(image).size, (1000, 750))

    def test_dark_sky_kept(self):
        image = Image.new("RGB", (1000, 600), (120, 160, 200))
        image.paste(Image.new("RGB", (1000, 120), (5, 5, 10)), (0, 0))  # faqat tepasi qorong'i — tungi osmon
        self.assertEqual(images.trim_bars(image).size, (1000, 600))


if __name__ == "__main__":
    unittest.main()
