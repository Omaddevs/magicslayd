"""Suhbat holati (FSM) bazada saqlanadi — bot qayta ishga tushsa yoki yangilansa ham
userlar qaysi qadamda turgan bo'lsa, o'sha yerdan davom etadi (tugmalar «eskirgan» bo'lib qolmaydi)."""
import json
from datetime import datetime, timedelta
from typing import Any, Mapping

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

from database import TIME_FORMAT, db, now_str


def _key(key: StorageKey):
    return ":".join(str(part) for part in (
        key.bot_id, key.chat_id, key.user_id, key.thread_id or "", key.business_connection_id or "", key.destiny,
    ))


class SQLiteStorage(BaseStorage):
    def __init__(self):
        db.execute(
            "CREATE TABLE IF NOT EXISTS fsm_states ("
            "key TEXT PRIMARY KEY, state TEXT, data TEXT NOT NULL DEFAULT '{}', updated_at TEXT)"
        )
        db.commit()

    def _row(self, key):
        return db.execute("SELECT state, data FROM fsm_states WHERE key = ?", (_key(key),)).fetchone()

    def _save(self, key, state, data):
        if state is None and not data:
            db.execute("DELETE FROM fsm_states WHERE key = ?", (_key(key),))
        else:
            db.execute(
                "INSERT INTO fsm_states (key, state, data, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET state = excluded.state, data = excluded.data, "
                "updated_at = excluded.updated_at",
                (_key(key), state, json.dumps(data, ensure_ascii=False), now_str()),
            )
        db.commit()

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        value = state.state if isinstance(state, State) else state
        self._save(key, value, await self.get_data(key))

    async def get_state(self, key: StorageKey) -> str | None:
        row = self._row(key)
        return row[0] if row else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        self._save(key, await self.get_state(key), dict(data))

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        row = self._row(key)
        return json.loads(row[1]) if row else {}

    async def close(self) -> None:
        pass

    @staticmethod
    def cleanup(days=30):
        """Uzoq vaqt tegilmagan (tashlab ketilgan) holatlar o'chiriladi."""
        cutoff = (datetime.now() - timedelta(days=days)).strftime(TIME_FORMAT)
        db.execute("DELETE FROM fsm_states WHERE updated_at < ?", (cutoff,))
        db.commit()
