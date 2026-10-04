import sqlite3
import os
from contextlib import contextmanager
from typing import Optional, Dict, Any

class VerificationDatabase:
    """SQLite persistent storage for Roblox to Discord verifications."""

    def __init__(self, db_path: str = "verifications.db"):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS verifications (
                    discord_id INTEGER PRIMARY KEY,
                    roblox_id INTEGER NOT NULL,
                    roblox_username TEXT NOT NULL,
                    roblox_display_name TEXT,
                    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_roblox_id ON verifications (roblox_id);
            """)
            conn.commit()

    def link_user(self, discord_id: int, roblox_id: int, username: str, display_name: str) -> None:
        """Saves or updates a verified user link."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO verifications (discord_id, roblox_id, roblox_username, roblox_display_name, verified_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(discord_id) DO UPDATE SET
                    roblox_id = excluded.roblox_id,
                    roblox_username = excluded.roblox_username,
                    roblox_display_name = excluded.roblox_display_name,
                    verified_at = CURRENT_TIMESTAMP;
            """, (discord_id, roblox_id, username, display_name))
            conn.commit()

    def get_by_discord_id(self, discord_id: int) -> Optional[Dict[str, Any]]:
        """Look up verified Roblox info by Discord user ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM verifications WHERE discord_id = ?", (discord_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def get_by_roblox_id(self, roblox_id: int) -> Optional[Dict[str, Any]]:
        """Look up verification info by Roblox ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM verifications WHERE roblox_id = ?", (roblox_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def unlink_user(self, discord_id: int) -> bool:
        """Unlink a Discord user."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM verifications WHERE discord_id = ?", (discord_id,))
            conn.commit()
            return cursor.rowcount > 0
