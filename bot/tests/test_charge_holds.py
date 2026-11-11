"""Bot chatidagi buyurtma puli: yechiladi → fayl yetkazilsa saqlanadi, xato bo'lsa bir marta qaytariladi,
bot to'xtab qolsa — qayta ishga tushganda qaytariladi. Haqiqiy bot.db ga tegmaydi (vaqtinchalik DATA_DIR)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="slayd-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DB_PATH  # noqa: E402
from database import (  # noqa: E402
    add_paid_order, add_web_order, charge_hold, db, get_balance, get_web_order, refund_hold, refund_stale_holds,
    settle_hold,
)

USER = 900101


class ChargeHoldTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not str(DB_PATH).startswith(tempfile.gettempdir()):
            raise RuntimeError(f"Test haqiqiy bazani ochdi ({DB_PATH}) — to'xtatildi")

    def setUp(self):
        db.execute("DELETE FROM charge_holds")
        db.execute("INSERT OR REPLACE INTO users (id, full_name, balance) VALUES (?, 'Test', 10000)", (USER,))
        db.commit()

    def test_not_enough_money(self):
        self.assertIsNone(charge_hold(USER, 20000, "Taqdimot"))
        self.assertEqual(get_balance(USER), 10000)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM charge_holds").fetchone()[0], 0)

    def test_free_order_has_no_hold(self):
        self.assertEqual(charge_hold(USER, 0, "Admin"), 0)
        self.assertEqual(refund_hold(0), 0)
        self.assertEqual(get_balance(USER), 10000)

    def test_delivered_order_keeps_money(self):
        hold = charge_hold(USER, 4000, "Taqdimot")
        self.assertEqual(get_balance(USER), 6000)
        settle_hold(hold)
        self.assertEqual(refund_hold(hold), 0, "yetkazilgandan keyin qaytarilmaydi")
        self.assertEqual(refund_stale_holds(), [])
        self.assertEqual(get_balance(USER), 6000)

    def test_failed_order_refunded_once(self):
        hold = charge_hold(USER, 4000, "Referat")
        self.assertEqual(refund_hold(hold, "Xato"), 4000)
        self.assertEqual(refund_hold(hold, "Xato"), 0, "ikkinchi marta qaytarilmaydi")
        self.assertEqual(get_balance(USER), 10000)

    def test_restart_refunds_unfinished(self):
        charge_hold(USER, 3000, "Kurs ishi")
        self.assertEqual(get_balance(USER), 7000)
        self.assertEqual(refund_stale_holds(), [(USER, 3000)])
        self.assertEqual(get_balance(USER), 10000)
        self.assertEqual(refund_stale_holds(), [], "qayta ishga tushganda yana qaytarilmaydi")


class QueuedReceiptTest(unittest.TestCase):
    def test_order_with_queued_receipt_is_not_replaced(self):
        """Saytdan chek yuborilib, hali navbatda turgan buyurtma — yangi buyurtma uni bekor qilmaydi."""
        first = add_paid_order(USER, "referat", {"topic": "A", "pages": 10, "lang": "uz"}, 5000)
        add_web_order(USER, "receipt", {"amount": 5000, "file": "x.jpg", "type": "photo", "order_id": first})
        add_paid_order(USER, "kurs", {"topic": "B", "pages": 20, "lang": "uz"}, 12000)
        self.assertEqual(get_web_order(first)["status"], "awaiting_payment")


if __name__ == "__main__":
    unittest.main()
