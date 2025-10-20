from __future__ import annotations
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Iterable, List, Tuple

from .models import PrivateRoom
from . import config

ISO = "%Y-%m-%dT%H:%M:%S.%f"

class DB:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self):
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS private_rooms (
            voice_channel_id INTEGER PRIMARY KEY,
            owner_id         INTEGER NOT NULL,
            panel_channel_id INTEGER,
            created_at       TEXT NOT NULL,
            is_locked        INTEGER NOT NULL DEFAULT 0,
            user_limit       INTEGER NOT NULL DEFAULT 3,
            preset_id        TEXT,
            panel_message_id INTEGER
        )
        """)
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS allowed_members (
            voice_channel_id INTEGER NOT NULL,
            user_id          INTEGER NOT NULL,
            UNIQUE(voice_channel_id, user_id)
        )
        """)
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS creations (
            user_id    INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS blocks (
            user_id        INTEGER PRIMARY KEY,
            blocked_until  TEXT NOT NULL
        )
        """)
        # мягкие ALTER'ы
        for stmt in (
                "ALTER TABLE private_rooms ADD COLUMN preset_id TEXT",
                "ALTER TABLE private_rooms ADD COLUMN panel_message_id INTEGER",
        ):
            try:
                self.conn.execute(stmt)
            except Exception:
                pass
        self.conn.commit()

    # -------- Private rooms
    def add_room(self, voice_id, owner_id, panel_channel_id, is_locked, user_limit, preset_id=None,
                 panel_message_id=None):
        self.conn.execute(
            "INSERT OR REPLACE INTO private_rooms(voice_channel_id, owner_id, panel_channel_id, created_at, is_locked, user_limit, preset_id, panel_message_id) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (voice_id, owner_id, panel_channel_id, datetime.utcnow().strftime(ISO), is_locked, user_limit, preset_id,
             panel_message_id)
        )
        self.conn.commit()

    def get_room(self, voice_id: int):
        cur = self.conn.execute(
            "SELECT voice_channel_id, owner_id, panel_channel_id, is_locked, user_limit, preset_id, panel_message_id "
            "FROM private_rooms WHERE voice_channel_id=?", (voice_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        from .models import PrivateRoom
        r = PrivateRoom(voice_channel_id=row[0], owner_id=row[1], panel_channel_id=row[2], is_locked=bool(row[3]),
                        user_limit=row[4])
        r.preset_id = row[5]
        r.panel_message_id = row[6]
        return r

    def set_panel_message(self, voice_id: int, message_id: int | None):
        self.conn.execute("UPDATE private_rooms SET panel_message_id=? WHERE voice_channel_id=?",
                          (message_id, voice_id))
        self.conn.commit()

    def set_owner(self, voice_id: int, new_owner_id: int):
        self.conn.execute("UPDATE private_rooms SET owner_id=? WHERE voice_channel_id=?", (new_owner_id, voice_id))
        self.conn.commit()

    def set_locked(self, voice_id: int, locked: int):
        self.conn.execute("UPDATE private_rooms SET is_locked=? WHERE voice_channel_id=?", (locked, voice_id))
        self.conn.commit()

    def set_limit(self, voice_id: int, limit_val: int):
        self.conn.execute("UPDATE private_rooms SET user_limit=? WHERE voice_channel_id=?", (limit_val, voice_id))
        self.conn.commit()

    def set_panel_channel(self, voice_id: int, panel_channel_id: Optional[int]):
        self.conn.execute("UPDATE private_rooms SET panel_channel_id=? WHERE voice_channel_id=?", (panel_channel_id, voice_id))
        self.conn.commit()

    def del_room(self, voice_id: int):
        self.conn.execute("DELETE FROM private_rooms WHERE voice_channel_id=?", (voice_id,))
        self.conn.execute("DELETE FROM allowed_members WHERE voice_channel_id=?", (voice_id,))
        self.conn.commit()

    def list_rooms(self) -> Iterable[PrivateRoom]:
        cur = self.conn.execute("SELECT voice_channel_id, owner_id, panel_channel_id, is_locked, user_limit FROM private_rooms")
        for row in cur.fetchall():
            yield PrivateRoom(voice_channel_id=row[0], owner_id=row[1], panel_channel_id=row[2], is_locked=bool(row[3]), user_limit=row[4])

    # -------- Anti-spam
    def record_creation(self, user_id: int):
        self.conn.execute("INSERT INTO creations(user_id, created_at) VALUES(?, ?)", (user_id, datetime.utcnow().strftime(ISO)))
        self.conn.commit()

    def count_creations_since(self, user_id: int, since_minutes: int) -> int:
        since = (datetime.utcnow() - timedelta(minutes=since_minutes)).strftime(ISO)
        cur = self.conn.execute("SELECT COUNT(*) FROM creations WHERE user_id=? AND created_at>=?", (user_id, since))
        return cur.fetchone()[0]

    def set_block(self, user_id: int, minutes: int):
        until = datetime.utcnow() + timedelta(minutes=minutes)
        self.conn.execute("INSERT OR REPLACE INTO blocks(user_id, blocked_until) VALUES(?, ?)", (user_id, until.strftime(ISO)))
        self.conn.commit()

    def get_block_until(self, user_id: int) -> Optional[datetime]:
        cur = self.conn.execute("SELECT blocked_until FROM blocks WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        return datetime.strptime(row[0], ISO)

    def clear_expired_blocks(self):
        now = datetime.utcnow().strftime(ISO)
        self.conn.execute("DELETE FROM blocks WHERE blocked_until < ?", (now,))
        self.conn.commit()
