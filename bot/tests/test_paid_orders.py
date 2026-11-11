"""Pullik buyurtma zanjiri: narx → «to'lov kutilmoqda» → admin cheki tasdiqlaydi → buyurtma navbatga
(bot tayyorlab yuboradi), rad etsa — bekor. Haqiqiy bot.db ga tegmaydi (vaqtinchalik DATA_DIR)."""
import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="slayd-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ADMIN_ID, DB_PATH, PAGE_PRICE, SLIDE_PRICE  # noqa: E402
from database import (  # noqa: E402
    add_paid_order, add_payment, db, get_balance, get_payment, get_web_order,
)
from handlers import wallet  # noqa: E402
from handlers.documents import doc_price  # noqa: E402
from handlers.presentation import price_for  # noqa: E402

USER = 900001


class PaidOrderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not str(DB_PATH).startswith(tempfile.gettempdir()):
            raise RuntimeError(f"Test haqiqiy bazani ochdi ({DB_PATH}) — to'xtatildi")

    def setUp(self):
        db.execute("INSERT OR REPLACE INTO users (id, full_name, balance) VALUES (?, 'Test', 0)", (USER,))
        db.commit()
        self.bot = mock.AsyncMock()

    def review(self, payment_id, approve):
        return asyncio.run(wallet.apply_review(self.bot, payment_id, approve))

    def test_prices_depend_on_kind_and_size(self):
        self.assertEqual(price_for(USER, 15), 15 * SLIDE_PRICE)
        self.assertEqual(doc_price(USER, "referat", 10), 10 * PAGE_PRICE["referat"])
        self.assertEqual(doc_price(USER, "mustaqil", 10), 10 * PAGE_PRICE["mustaqil"])
        self.assertEqual(doc_price(USER, "kurs", 25), 25 * PAGE_PRICE["kurs"])
        self.assertNotEqual(doc_price(USER, "kurs", 10), doc_price(USER, "referat", 10), "kurs ishi qimmatroq")
        self.assertEqual(price_for(ADMIN_ID, 15), 0, "admin uchun bepul")

    def test_approve_releases_order_and_tops_up(self):
        price = doc_price(USER, "kurs", 25)
        order_id = add_paid_order(USER, "kurs", {"topic": "Marketing", "pages": 25, "lang": "uz"}, price)
        self.assertEqual(get_web_order(order_id)["status"], "awaiting_payment")
        payment_id = add_payment(USER, price, "FILE", "photo", order_id)
        ok, _, _ = self.review(payment_id, True)
        self.assertTrue(ok)
        self.assertEqual(get_payment(payment_id)["status"], "approved")
        self.assertEqual(get_balance(USER), price, "pul balansga tushdi — buyurtma uni yechib oladi")
        self.assertEqual(get_web_order(order_id)["status"], "pending", "buyurtma navbatga o'tdi — bot tayyorlaydi")
        self.bot.send_message.assert_awaited()  # userga xabar

    def test_reject_cancels_order(self):
        order_id = add_paid_order(USER, "pres", {"topic": "AI", "slides": 15, "plans": 3, "lang": "uz"}, 7500)
        payment_id = add_payment(USER, 7500, "FILE", "photo", order_id)
        ok, _, _ = self.review(payment_id, False)
        self.assertTrue(ok)
        self.assertEqual(get_web_order(order_id)["status"], "failed")
        self.assertEqual(get_balance(USER), 0, "rad etilsa pul qo'shilmaydi")

    def test_double_review_ignored(self):
        order_id = add_paid_order(USER, "referat", {"topic": "Tarix", "pages": 10, "lang": "uz"}, 5000)
        payment_id = add_payment(USER, 5000, "FILE", "photo", order_id)
        self.review(payment_id, True)
        ok, text, _ = self.review(payment_id, True)
        self.assertFalse(ok)
        self.assertEqual(get_balance(USER), 5000, "ikki marta tasdiqlash pulni ikki baravar qo'shmaydi")


if __name__ == "__main__":
    unittest.main()
