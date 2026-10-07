import sqlite3
import os
from contextlib import contextmanager
from typing import Optional, Dict, Any, List

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

    def get_total_verifications_count(self) -> int:
        """Returns total count of linked verified accounts."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM verifications;")
            return cursor.fetchone()[0]

    def save_bot_presence(self, activity_type: str, activity_text: str, visibility: str, rotate_mode: bool = False) -> None:
        """Saves current bot status, visibility, and rotation configuration."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_presence (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    activity_type TEXT,
                    activity_text TEXT,
                    visibility TEXT DEFAULT 'online',
                    rotate_mode INTEGER DEFAULT 0
                );
            """)
            try:
                cursor.execute("ALTER TABLE bot_presence ADD COLUMN rotate_mode INTEGER DEFAULT 0;")
            except Exception:
                pass

            cursor.execute("""
                INSERT INTO bot_presence (id, activity_type, activity_text, visibility, rotate_mode)
                VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    activity_type = excluded.activity_type,
                    activity_text = excluded.activity_text,
                    visibility = excluded.visibility,
                    rotate_mode = excluded.rotate_mode;
            """, (activity_type, activity_text, visibility, 1 if rotate_mode else 0))
            conn.commit()

    def get_bot_presence(self) -> Dict[str, Any]:
        """Retrieves stored bot presence configuration."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_presence (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    activity_type TEXT,
                    activity_text TEXT,
                    visibility TEXT DEFAULT 'online',
                    rotate_mode INTEGER DEFAULT 1
                );
            """)
            try:
                cursor.execute("ALTER TABLE bot_presence ADD COLUMN rotate_mode INTEGER DEFAULT 1;")
            except Exception:
                pass

            cursor.execute("SELECT * FROM bot_presence WHERE id = 1;")
            row = cursor.fetchone()
            if row:
                d = dict(row)
                d['rotate_mode'] = bool(d.get('rotate_mode', 1))
                return d
            return {"activity_type": "playing", "activity_text": "Roblox | !et help", "visibility": "online", "rotate_mode": True}

    def save_user_playlist(self, discord_id: int, playlist_name: str, tracks_data: List[Dict[str, Any]]) -> None:
        """Saves or updates a custom user playlist."""
        import json
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    discord_id INTEGER NOT NULL,
                    playlist_name TEXT NOT NULL,
                    tracks_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(discord_id, playlist_name)
                );
            """)
            cursor.execute("""
                INSERT INTO user_playlists (discord_id, playlist_name, tracks_json, created_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(discord_id, playlist_name) DO UPDATE SET
                    tracks_json = excluded.tracks_json,
                    created_at = CURRENT_TIMESTAMP;
            """, (discord_id, playlist_name.lower(), json.dumps(tracks_data)))
            conn.commit()

    def get_user_playlist(self, discord_id: int, playlist_name: str) -> Optional[List[Dict[str, Any]]]:
        """Retrieves tracks for a saved playlist."""
        import json
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    discord_id INTEGER NOT NULL,
                    playlist_name TEXT NOT NULL,
                    tracks_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(discord_id, playlist_name)
                );
            """)
            cursor.execute("""
                SELECT tracks_json FROM user_playlists WHERE discord_id = ? AND playlist_name = ?;
            """, (discord_id, playlist_name.lower()))
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None

    def get_user_playlists_list(self, discord_id: int) -> List[Dict[str, Any]]:
        """Lists all saved playlists for a user."""
        import json
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    discord_id INTEGER NOT NULL,
                    playlist_name TEXT NOT NULL,
                    tracks_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(discord_id, playlist_name)
                );
            """)
            cursor.execute("""
                SELECT playlist_name, tracks_json, created_at FROM user_playlists WHERE discord_id = ? ORDER BY created_at DESC;
            """, (discord_id,))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                tracks = json.loads(r[1])
                results.append({
                    "playlist_name": r[0],
                    "track_count": len(tracks),
                    "created_at": r[2]
                })
            return results

    def delete_user_playlist(self, discord_id: int, playlist_name: str) -> bool:
        """Deletes a saved user playlist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM user_playlists WHERE discord_id = ? AND playlist_name = ?;
            """, (discord_id, playlist_name.lower()))
            conn.commit()
            return cursor.rowcount > 0
