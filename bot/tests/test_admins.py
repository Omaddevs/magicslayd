"""Adminlar: ega (.env ADMIN_ID) + u qo'shgan ko'pi bilan ADMINS_EXTRA_MAX ta admin. Faqat ega boshqaradi.
Haqiqiy bot.db ga tegmaydi (vaqtinchalik DATA_DIR)."""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="slayd-test-"))
os.environ["ADMIN_ID"] = os.environ.get("ADMIN_ID") or "1349914760"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import admins  # noqa: E402
from admins import (  # noqa: E402
    PERMS, AdminError, add_admin, admin_ids, extra_admins, has_perm, is_admin, is_owner, perms_of, remove_admin,
    set_perms,
)
from config import ADMINS_EXTRA_MAX, DB_PATH  # noqa: E402
from database import add_web_order, db, get_web_order  # noqa: E402
from handlers.documents import doc_price  # noqa: E402
from handlers.presentation import price_for  # noqa: E402

OWNER = admins.OWNER_ID
A, B, C, USER = 900201, 900202, 900203, 900299


class AdminsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not str(DB_PATH).startswith(tempfile.gettempdir()):
            raise RuntimeError(f"Test haqiqiy bazani ochdi ({DB_PATH}) — to'xtatildi")
        if not OWNER:
            raise unittest.SkipTest("ADMIN_ID yo'q")

    def setUp(self):
        db.execute("DELETE FROM admins")
        db.commit()

    def test_owner_is_admin(self):
        self.assertTrue(is_owner(OWNER))
        self.assertTrue(is_admin(OWNER))
        self.assertFalse(is_admin(USER))
        self.assertEqual(admin_ids(), [OWNER])

    def test_owner_adds_up_to_limit(self):
        self.assertEqual(ADMINS_EXTRA_MAX, 2)
        add_admin(A, OWNER, "Ali")
        add_admin(B, OWNER)
        self.assertTrue(is_admin(A) and is_admin(B))
        self.assertEqual(admin_ids(), [OWNER, A, B])
        self.assertEqual(extra_admins()[0]["full_name"], "Ali", "ism users jadvalida bo'lmasa ham ko'rinadi")
        with self.assertRaisesRegex(AdminError, "Ko'pi bilan 2"):
            add_admin(C, OWNER)
        self.assertFalse(is_admin(C))

    def test_only_owner_manages(self):
        add_admin(A, OWNER)
        with self.assertRaisesRegex(AdminError, "faqat bot egasi"):
            add_admin(B, A)
        with self.assertRaisesRegex(AdminError, "faqat bot egasi"):
            remove_admin(A, A)
        self.assertFalse(is_admin(B))

    def test_owner_cannot_be_removed_or_added_twice(self):
        with self.assertRaises(AdminError):
            remove_admin(OWNER, OWNER)
        with self.assertRaises(AdminError):
            add_admin(OWNER, OWNER)
        add_admin(A, OWNER)
        with self.assertRaisesRegex(AdminError, "allaqachon"):
            add_admin(A, OWNER)

    def test_removed_admin_loses_rights(self):
        add_admin(A, OWNER)
        remove_admin(A, OWNER)
        self.assertFalse(is_admin(A))
        with self.assertRaisesRegex(AdminError, "admin emas"):
            remove_admin(A, OWNER)

    def test_new_admin_only_approves_receipts(self):
        add_admin(A, OWNER)
        self.assertEqual(perms_of(A), {"payments"})
        self.assertTrue(has_perm(A, "payments"))
        for perm in ("users", "balance", "broadcast", "stats", "free"):
            self.assertFalse(has_perm(A, perm), perm)
        self.assertEqual(perms_of(OWNER), set(PERMS), "ega — barcha huquqlar")
        self.assertEqual(perms_of(USER), set())

    def test_only_owner_grants_permissions(self):
        add_admin(A, OWNER)
        add_admin(B, OWNER)
        self.assertEqual(set_perms(A, ["payments", "stats", "nonsense"], OWNER), ["payments", "stats"])
        self.assertTrue(has_perm(A, "stats"))
        with self.assertRaisesRegex(AdminError, "faqat bot egasi"):
            set_perms(B, list(PERMS), A)
        self.assertEqual(perms_of(B), {"payments"})
        with self.assertRaises(AdminError):
            set_perms(OWNER, [], OWNER)
        with self.assertRaisesRegex(AdminError, "admin emas"):
            set_perms(USER, ["stats"], OWNER)

    def test_receipts_only_to_payment_admins(self):
        add_admin(A, OWNER)
        add_admin(B, OWNER)
        set_perms(B, ["broadcast"], OWNER)
        self.assertEqual(admin_ids("payments"), [OWNER, A])
        self.assertEqual(admin_ids("broadcast"), [OWNER, B])

    def test_free_orders_need_permission(self):
        add_admin(A, OWNER)
        self.assertGreater(price_for(A, 15), 0, "standart admin buyurtmasi pullik")
        set_perms(A, ["payments", "free"], OWNER)
        self.assertEqual(price_for(A, 15), 0)
        self.assertEqual(doc_price(A, "kurs", 30), 0)
        self.assertEqual(price_for(OWNER, 15), 0)
        self.assertGreater(price_for(USER, 15), 0)
        self.assertGreater(doc_price(USER, "kurs", 30), 0)

    def test_panel_sections_follow_permissions(self):
        from handlers import admin as panel

        add_admin(A, OWNER)
        buttons = [b.callback_data for row in panel.panel_markup(A).inline_keyboard for b in row if b.callback_data]
        self.assertIn("adm:pay", buttons)
        for hidden in ("adm:stats", "adm:bc", "adm:find", "admins:list"):
            self.assertNotIn(hidden, buttons)
        owner_buttons = [b.callback_data for row in panel.panel_markup(OWNER).inline_keyboard for b in row if b.callback_data]
        self.assertIn("admins:list", owner_buttons)
        self.assertEqual(panel.needed_perm("adm:bal:5:+"), "balance")
        self.assertEqual(panel.needed_perm("adm:stop:3"), "broadcast")
        self.assertIsNone(panel.needed_perm("adm:home"))


class PaymentFanoutTest(unittest.TestCase):
    def test_receipt_goes_to_all_admins_and_review_updates_others(self):
        from handlers import wallet

        db.execute("DELETE FROM admins")
        db.commit()
        add_admin(A, OWNER)
        bot = mock.AsyncMock()
        sent = iter(range(100, 200))
        bot.send_photo.side_effect = lambda chat, *a, **k: mock.Mock(message_id=next(sent))
        payment = {"id": 77, "user_id": USER, "amount": 10000, "file_id": "F", "file_type": "photo",
                   "full_name": "U", "username": None, "created_at": "2026-11-10 12:00", "order_id": None}
        asyncio.run(wallet.send_payment_to_admin(bot, payment))
        self.assertEqual([c.args[0] for c in bot.send_photo.call_args_list], [OWNER, A])

        asyncio.run(wallet.mark_reviewed(bot, payment, True, A, skip=(A, 101)))
        edited = [c.kwargs["chat_id"] for c in bot.edit_message_caption.call_args_list]
        self.assertEqual(edited, [OWNER], "ko'rib chiqqan admindan boshqa hammada yangilanadi")


class WebAdminsJobTest(unittest.TestCase):
    def run_job(self, actor, action, target):
        from handlers import web

        order_id = add_web_order(actor, "admins", {"action": action, "user_id": target})
        order = dict(get_web_order(order_id), params=json.dumps({"action": action, "user_id": target}))
        asyncio.run(web.run_admins(mock.AsyncMock(), order))
        return get_web_order(order_id)

    def test_owner_adds_via_web(self):
        db.execute("DELETE FROM admins")
        db.commit()
        self.assertEqual(self.run_job(OWNER, "add", B)["status"], "done")
        self.assertTrue(is_admin(B))
        self.assertEqual(self.run_job(OWNER, "remove", B)["status"], "done")
        self.assertFalse(is_admin(B))

    def test_owner_sets_permissions_via_web(self):
        from handlers import web

        db.execute("DELETE FROM admins")
        db.commit()
        add_admin(A, OWNER)
        params = {"action": "perms", "user_id": A, "perms": ["payments", "users"]}
        order_id = add_web_order(OWNER, "admins", params)
        order = dict(get_web_order(order_id), params=json.dumps(params))
        asyncio.run(web.run_admins(mock.AsyncMock(), order))
        self.assertEqual(get_web_order(order_id)["status"], "done")
        self.assertEqual(perms_of(A), {"payments", "users"})

    def test_admin_cannot_add_via_web(self):
        db.execute("DELETE FROM admins")
        db.commit()
        add_admin(A, OWNER)
        result = self.run_job(A, "add", C)
        self.assertEqual(result["status"], "failed")
        self.assertIn("egasi", result["error"])
        self.assertFalse(is_admin(C))


if __name__ == "__main__":
    unittest.main()
