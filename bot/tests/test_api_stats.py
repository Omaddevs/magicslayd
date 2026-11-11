"""API hisoblagichi (api_stats.py) va admin paneldagi «🔌 API va limitlar» hisoboti.
Haqiqiy bot.db ga tegmaydi — har bir test xotiradagi alohida bazada ishlaydi."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Haqiqiy bazaga tegmaslik uchun — vaqtinchalik papka (config DATA_DIR ni import paytida o'qiydi).
# Bu fayl alifbo bo'yicha birinchi yuklanadi, shuning uchun boshqa testlar ham shu vaqtinchalik bazani oladi
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="slayd-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import api_stats  # noqa: E402


def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);"
        "CREATE TABLE api_stats (day TEXT, service TEXT, metric TEXT, value INTEGER NOT NULL DEFAULT 0, "
        "PRIMARY KEY (day, service, metric));"
        "CREATE TABLE ai_usage (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, day TEXT, model TEXT, "
        "input_tokens INTEGER, output_tokens INTEGER, cache_read INTEGER, cache_write INTEGER, cost REAL);"
    )
    return conn


class ApiStatsTest(unittest.TestCase):
    def setUp(self):
        self.db = memory_db()

        def set_meta(key, value):
            self.db.execute("INSERT INTO meta (key, value) VALUES (?, ?) "
                            "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

        patches = [mock.patch.object(api_stats, "db", self.db), mock.patch.object(api_stats, "set_meta", set_meta)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        api_stats._last_state.clear()
        self.addCleanup(api_stats._last_state.clear)

    def test_bump_counts_per_day(self):
        api_stats.bump("pixabay")
        api_stats.bump("pixabay", n=2)
        api_stats.bump("pixabay", "errors")
        self.assertEqual(api_stats.today("pixabay"), 3)
        self.assertEqual(api_stats.today("pixabay", "errors"), 1)
        self.assertEqual(api_stats.today("wikimedia"), 0)

    def test_cloudflare_counts_by_utc_day(self):
        api_stats.bump("cloudflare", "images")
        day = self.db.execute("SELECT day FROM api_stats WHERE service = 'cloudflare'").fetchone()[0]
        self.assertEqual(day, api_stats.utc_day())

    def test_state_merge_and_clear(self):
        api_stats.set_state("pixabay", error="Kalit noto'g'ri", remaining=5)
        self.assertEqual(api_stats.get_state("pixabay")["error"], "Kalit noto'g'ri")
        api_stats.set_state("pixabay", error=None)
        state = api_stats.get_state("pixabay")
        self.assertNotIn("error", state)
        self.assertEqual(state["remaining"], 5)
        self.assertIn("updated_at", state)

    def test_credit_left(self):
        api_stats.set_claude_credit(20)
        since = json.loads(self.db.execute("SELECT value FROM meta WHERE key = 'claude_credit'").fetchone()[0])["since"]
        self.db.execute("INSERT INTO ai_usage (created_at, day, cost) VALUES (?, ?, 1.5)", (since, since[:10]))
        self.db.execute("INSERT INTO ai_usage (created_at, day, cost) VALUES ('2000-01-01 00:00', '2000-01-01', 99)")
        amount, spent, left, _ = api_stats.claude_credit()
        self.assertEqual((amount, spent, left), (20.0, 1.5, 18.5), "balans kiritilgandan oldingi sarf hisoblanmaydi")

    def test_credit_missing(self):
        self.assertIsNone(api_stats.claude_credit())

    def test_report_renders(self):
        from handlers import admin
        with mock.patch.object(admin.ai_usage, "summary", return_value={
            "today": (0.5, 10), "recent": (0, 0), "week": (3.5, 70), "total": (9, 200), "by_model": [], "budget": 3.0,
        }):
            api_stats.set_claude_credit(10)
            text = admin.api_report()
        self.assertIn("API va limitlar", text)
        self.assertIn("$10.00", text)
        self.assertIn("qoldi", text)


if __name__ == "__main__":
    unittest.main()
