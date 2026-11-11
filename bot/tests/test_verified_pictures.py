"""Har bir rasm (foto ham, AI chizgani ham) tekshiruvdan o'tadi: mos kelmagan AI rasmi qayta chiziladi,
yana mos kelmasa — tashlanadi; referat / kurs ishi / diplomda mos foto bo'lmasa AI chizadi (rasmlar kamaymaydi)."""
import asyncio
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="slayd-test-"))

from presentation import ai  # noqa: E402


def run(coro):
    return asyncio.run(coro)


class DrawVerifiedTest(unittest.TestCase):
    def draw(self, verdicts, first=("A1", "B1"), second=("A2", "B2")):
        rounds = iter([list(first), list(second)])
        calls = []

        async def fake_generate(prompts):
            calls.append(list(prompts))
            batch = next(rounds)
            return batch[:len(prompts)] if len(prompts) == len(first) else [batch[i] for i in range(len(prompts))]

        async def check(image, drawn=False):
            self.assertTrue(drawn, "AI rasmi «chizilgan» rejimida tekshiriladi")
            return verdicts.get(image)

        with mock.patch.object(ai.genimage, "enabled", return_value=True), \
                mock.patch.object(ai.genimage, "generate_images", fake_generate):
            result = run(ai.draw_verified(["p1", "p2"], [check, check]))
        return result, calls

    def test_good_drawings_kept(self):
        result, calls = self.draw({"A1": True, "B1": True})
        self.assertEqual(result, ["A1", "B1"])
        self.assertEqual(len(calls), 1, "qayta chizish kerak emas")

    def test_rejected_drawing_redrawn(self):
        result, calls = self.draw({"A1": False, "B1": True, "A2": True}, second=("A2",))
        self.assertEqual(result, ["A2", "B1"])
        self.assertEqual(len(calls), 2)
        self.assertIn("literally", calls[1][0], "qayta chizishda aniqroq tavsif")

    def test_rejected_twice_dropped(self):
        result, _ = self.draw({"A1": False, "B1": True, "A2": False}, second=("A2",))
        self.assertEqual(result, [None, "B1"])

    def test_unverifiable_drawing_kept(self):
        result, _ = self.draw({"A1": None, "B1": None})
        self.assertEqual(result, ["A1", "B1"], "AI javob bermasa — tavsif bo'yicha chizilgan rasm qoladi")


class BestPicturesTest(unittest.TestCase):
    targets = [{"title": f"Bo'lim {i}", "text": "", "items": [], "image_query": f"q{i}", "image_prompt": f"p{i}"}
               for i in range(3)]

    def pick(self, photos, drawings, prefer_ai=False):
        order = []

        async def fake_find(queries, used, fallback, checks):
            order.append("photo")
            self.assertTrue(all(c is not None for c in checks), "har bir foto tekshiriladi")
            return [photos.get(q) for q in queries]

        async def fake_draw(prompts, checks):
            order.append("ai")
            return [drawings.get(p) for p in prompts]

        with mock.patch.object(ai, "find_images", fake_find), mock.patch.object(ai, "draw_verified", fake_draw):
            result = run(ai.best_pictures(self.targets, "Mavzu", prefer_ai=prefer_ai,
                                          draw_prompt=lambda t: t["image_prompt"]))
        return result, order

    def test_missing_photos_are_drawn(self):
        result, order = self.pick({"q0": "F0"}, {"p1": "D1", "p2": "D2"})
        self.assertEqual(result, [("F0", "photo"), ("D1", "ai"), ("D2", "ai")])
        self.assertEqual(order, ["photo", "ai"])

    def test_prefer_ai_for_theses(self):
        result, order = self.pick({"q2": "F2"}, {"p0": "D0", "p1": "D1"}, prefer_ai=True)
        self.assertEqual(result, [("D0", "ai"), ("D1", "ai"), ("F2", "photo")])
        self.assertEqual(order, ["ai", "photo"])

    def test_nothing_suitable_stays_empty(self):
        result, _ = self.pick({}, {})
        self.assertEqual(result, [(None, None)] * 3)

    def test_topic_photo_as_last_resort(self):
        queries = []

        async def fake_find(q, used, fallback, checks):
            queries.append(list(q))
            return ["T"] * len(q) if q[0] == "mavzu" else [None] * len(q)

        async def fake_draw(prompts, checks):
            return [None] * len(prompts)

        with mock.patch.object(ai, "find_images", fake_find), mock.patch.object(ai, "draw_verified", fake_draw):
            result = run(ai.best_pictures(self.targets, "Mavzu", fallback="mavzu"))
        self.assertEqual(result, [("T", "photo")] * 3)
        self.assertEqual(queries[-1], ["mavzu"] * 3, "oxirgi chora — mavzu bo'yicha")


if __name__ == "__main__":
    unittest.main()
