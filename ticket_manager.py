import sqlite3
import os
import json
from contextlib import contextmanager
from typing import Optional, Dict, Any, List

class TicketManager:
    """Manages ticket persistence, conversation logging, escalation states, sections, and ratings in SQLite."""

    def __init__(self, db_path: str = "verifications.db"):
        self.db_path = db_path
        self._init_tables()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_tables(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'open', -- 'open', 'escalated', 'closed'
                    escalate_reason TEXT,
                    section TEXT DEFAULT 'General Support',
                    claimed_by INTEGER,
                    priority TEXT DEFAULT 'Normal',
                    ai_enabled INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP
                );
            """)

            # Add columns if migrating from earlier schema
            cursor.execute("PRAGMA table_info(tickets);")
            columns = [row["name"] for row in cursor.fetchall()]
            if "section" not in columns:
                cursor.execute("ALTER TABLE tickets ADD COLUMN section TEXT DEFAULT 'General Support';")
            if "claimed_by" not in columns:
                cursor.execute("ALTER TABLE tickets ADD COLUMN claimed_by INTEGER;")
            if "priority" not in columns:
                cursor.execute("ALTER TABLE tickets ADD COLUMN priority TEXT DEFAULT 'Normal';")
            if "ai_enabled" not in columns:
                cursor.execute("ALTER TABLE tickets ADD COLUMN ai_enabled INTEGER DEFAULT 1;")
            if "closed_by" not in columns:
                cursor.execute("ALTER TABLE tickets ADD COLUMN closed_by INTEGER;")
            if "close_reason" not in columns:
                cursor.execute("ALTER TABLE tickets ADD COLUMN close_reason TEXT;")
            if "last_message_at" not in columns:
                cursor.execute("ALTER TABLE tickets ADD COLUMN last_message_at TIMESTAMP;")
                cursor.execute("UPDATE tickets SET last_message_at = created_at WHERE last_message_at IS NULL;")
            if "last_staff_reply_at" not in columns:
                cursor.execute("ALTER TABLE tickets ADD COLUMN last_staff_reply_at TIMESTAMP;")
            if "inactivity_warning_sent" not in columns:
                cursor.execute("ALTER TABLE tickets ADD COLUMN inactivity_warning_sent INTEGER DEFAULT 0;")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ticket_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id INTEGER NOT NULL,
                    sender_id INTEGER NOT NULL,
                    sender_name TEXT DEFAULT 'Unknown',
                    sender_type TEXT NOT NULL, -- 'user', 'ai', 'staff', 'internal_note'
                    content TEXT NOT NULL,
                    attachments TEXT, -- JSON array of file/image URLs
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(ticket_id) REFERENCES tickets(id)
                );
            """)
            cursor.execute("PRAGMA table_info(ticket_messages);")
            msg_cols = [row["name"] for row in cursor.fetchall()]
            if "sender_name" not in msg_cols:
                cursor.execute("ALTER TABLE ticket_messages ADD COLUMN sender_name TEXT DEFAULT 'Unknown';")
            if "attachments" not in msg_cols:
                cursor.execute("ALTER TABLE ticket_messages ADD COLUMN attachments TEXT;")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ticket_ratings (
                    ticket_id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    rating INTEGER NOT NULL,
                    feedback TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ticket_blacklists (
                    user_id INTEGER PRIMARY KEY,
                    reason TEXT,
                    blacklisted_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS canned_responses (
                    shortcut TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Seed default canned responses if table is empty
            cursor.execute("SELECT COUNT(*) as count FROM canned_responses;")
            if cursor.fetchone()["count"] == 0:
                default_canned = [
                    ("verify", "Verification Help", "To verify your Roblox account, please click the 'Verify Roblox Account' button in the verification channel, enter your username, and place the 4-word code in your Roblox profile Bio. Click 'Check Verification' when done!"),
                    ("appeal", "Ban / Infraction Appeal Format", "To submit an appeal, please reply with: 1) Your Roblox Username, 2) Reason you were penalized, 3) Why you believe the penalty should be reduced or lifted."),
                    ("bug", "Bug Report Format", "Thank you for reporting an issue! Please describe: 1) Exactly what happened, 2) Steps to reproduce the bug, 3) Screenshots, videos, or error logs if available."),
                    ("rules", "Server & Game Rules", "Please be sure to adhere to our server rules and the Roblox Terms of Use. Toxicity, exploiting, spamming, and scamming are strictly prohibited."),
                    ("closing", "Inactive Closure Notice", "We haven't received a response from you recently, so we are closing this ticket for now. Feel free to open a new ticket anytime if you need further help!")
                ]
                cursor.executemany("INSERT INTO canned_responses (shortcut, title, content, created_by) VALUES (?, ?, ?, 0);", default_canned)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets (user_id, status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_channel ON tickets (channel_id);")
            conn.commit()

    def create_ticket(self, user_id: int, channel_id: int, guild_id: int, section: str = "General Support") -> int:
        """Opens a new ticket and returns its ticket ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tickets (user_id, channel_id, guild_id, status, section, priority, ai_enabled)
                VALUES (?, ?, ?, 'open', ?, 'Normal', 1);
            """, (user_id, channel_id, guild_id, section))
            conn.commit()
            return cursor.lastrowid

    def get_open_ticket_by_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Finds any active (open or escalated) ticket for a user."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM tickets
                WHERE user_id = ? AND status IN ('open', 'escalated')
                ORDER BY id DESC LIMIT 1;
            """, (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_ticket_by_channel(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """Finds any ticket by its Discord channel ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM tickets
                WHERE channel_id = ?
                ORDER BY id DESC LIMIT 1;
            """, (channel_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_ticket_by_id(self, ticket_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_section(self, ticket_id: int, section: str) -> bool:
        """Transfers a ticket to a different category/section."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE tickets SET section = ? WHERE id = ?", (section, ticket_id))
            conn.commit()
            return cursor.rowcount > 0

    def claim_ticket(self, ticket_id: int, staff_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE tickets SET claimed_by = ? WHERE id = ?", (staff_id, ticket_id))
            conn.commit()
            return cursor.rowcount > 0

    def unclaim_ticket(self, ticket_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE tickets SET claimed_by = NULL WHERE id = ?", (ticket_id,))
            conn.commit()
            return cursor.rowcount > 0

    def set_priority(self, ticket_id: int, priority: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE tickets SET priority = ? WHERE id = ?", (priority, ticket_id))
            conn.commit()
            return cursor.rowcount > 0

    def toggle_ai(self, ticket_id: int, enabled: Optional[bool] = None) -> bool:
        """Toggles AI enabled state. If enabled is None, flips current state."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if enabled is None:
                cursor.execute("UPDATE tickets SET ai_enabled = CASE WHEN ai_enabled = 1 THEN 0 ELSE 1 END WHERE id = ?", (ticket_id,))
            else:
                cursor.execute("UPDATE tickets SET ai_enabled = ? WHERE id = ?", (1 if enabled else 0, ticket_id))
            conn.commit()
            cursor.execute("SELECT ai_enabled FROM tickets WHERE id = ?", (ticket_id,))
            row = cursor.fetchone()
            if not row:
                return False
            new_state = bool(row["ai_enabled"])
            # If AI is toggled back ON, reset status to open and clear claimed_by so AI takes back over
            if new_state:
                cursor.execute("UPDATE tickets SET status = 'open', claimed_by = NULL WHERE id = ?", (ticket_id,))
                conn.commit()
            return new_state

    def escalate_ticket(self, ticket_id: int, reason: str = "") -> bool:
        """Marks a ticket as escalated and pauses AI."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tickets
                SET status = 'escalated', escalate_reason = ?, ai_enabled = 0
                WHERE id = ?;
            """, (reason, ticket_id))
            conn.commit()
            return cursor.rowcount > 0

    def de_escalate_ticket(self, ticket_id: int) -> bool:
        """De-escalates a ticket back to open state, clears claim, and re-enables AI."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tickets
                SET status = 'open', ai_enabled = 1, claimed_by = NULL
                WHERE id = ?;
            """, (ticket_id,))
            conn.commit()
            return cursor.rowcount > 0

    def close_ticket(self, ticket_id: int, closed_by: Optional[int] = None, reason: str = "Closed by staff") -> bool:
        """Marks a ticket as closed with staff ID and closure reason."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tickets
                SET status = 'closed', closed_at = CURRENT_TIMESTAMP, closed_by = ?, close_reason = ?
                WHERE id = ?;
            """, (closed_by, reason, ticket_id))
            conn.commit()
            return cursor.rowcount > 0

    def reset_all_tickets(self) -> int:
        """Wipes all tickets, messages, ratings, and resets ID auto-increments back to 1."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM tickets;")
            row = cursor.fetchone()
            count = row["count"] if row else 0
            cursor.execute("DELETE FROM tickets;")
            cursor.execute("DELETE FROM ticket_messages;")
            cursor.execute("DELETE FROM ticket_ratings;")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('tickets', 'ticket_messages', 'ticket_ratings');")
            conn.commit()
            return count

    def add_message(
        self,
        ticket_id: int,
        sender_id: int,
        sender_type: str,
        content: str,
        sender_name: str = "Unknown",
        attachments: Optional[List[str]] = None
    ):
        """Logs a message and any attachments in the ticket transcript, updating activity timestamps."""
        attachments_json = json.dumps(attachments) if attachments else None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ticket_messages (ticket_id, sender_id, sender_name, sender_type, content, attachments)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (ticket_id, sender_id, sender_name, sender_type, content, attachments_json))

            # Update ticket activity
            if sender_type in ("staff", "ai"):
                cursor.execute("""
                    UPDATE tickets
                    SET last_message_at = CURRENT_TIMESTAMP, last_staff_reply_at = CURRENT_TIMESTAMP, inactivity_warning_sent = 0
                    WHERE id = ?;
                """, (ticket_id,))
            else:
                cursor.execute("""
                    UPDATE tickets
                    SET last_message_at = CURRENT_TIMESTAMP, inactivity_warning_sent = 0
                    WHERE id = ?;
                """, (ticket_id,))
            conn.commit()

    def get_history_for_llm(self, ticket_id: int, limit: int = 12) -> List[Dict[str, str]]:
        """Retrieves formatted message history for LLM chat input (excludes internal notes)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT sender_type, content FROM ticket_messages
                WHERE ticket_id = ? AND sender_type != 'internal_note'
                ORDER BY id ASC;
            """, (ticket_id,))
            rows = cursor.fetchall()

        history = []
        for r in rows[-limit:]:
            role = "assistant" if r["sender_type"] == "ai" else "user"
            # Attachment-only messages are stored with empty content; the LLM API rejects empty messages
            content = (r["content"] or "").strip() or "[The user sent an attachment/file with no text]"
            history.append({"role": role, "content": content})
        return history

    def get_all_ticket_messages(self, ticket_id: int) -> List[Dict[str, Any]]:
        """Retrieves complete transcript messages."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT sender_id, sender_name, sender_type, content, created_at
                FROM ticket_messages
                WHERE ticket_id = ?
                ORDER BY id ASC;
            """, (ticket_id,))
            return [dict(r) for r in cursor.fetchall()]

    def save_rating(self, ticket_id: int, user_id: int, rating: int, feedback: str = ""):
        """Saves a user's experience rating (1-5 stars) and optional feedback."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ticket_ratings (ticket_id, user_id, rating, feedback)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(ticket_id) DO UPDATE SET
                    rating = excluded.rating,
                    feedback = excluded.feedback,
                    created_at = CURRENT_TIMESTAMP;
            """, (ticket_id, user_id, rating, feedback))
            conn.commit()

    def get_rating(self, ticket_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves rating for a ticket."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ticket_ratings WHERE ticket_id = ?", (ticket_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    # Blacklist system
    def is_blacklisted(self, user_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM ticket_blacklists WHERE user_id = ?", (user_id,))
            return cursor.fetchone() is not None

    def add_blacklist(self, user_id: int, reason: str, staff_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ticket_blacklists (user_id, reason, blacklisted_by)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    reason = excluded.reason,
                    blacklisted_by = excluded.blacklisted_by,
                    created_at = CURRENT_TIMESTAMP;
            """, (user_id, reason, staff_id))
            conn.commit()
            return True

    def remove_blacklist(self, user_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ticket_blacklists WHERE user_id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_blacklists(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ticket_blacklists ORDER BY created_at DESC")
            return [dict(r) for r in cursor.fetchall()]

    # Stats and Analytics
    def get_ticket_stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS total FROM tickets")
            total = cursor.fetchone()["total"]

            cursor.execute("SELECT COUNT(*) AS open_count FROM tickets WHERE status = 'open'")
            open_count = cursor.fetchone()["open_count"]

            cursor.execute("SELECT COUNT(*) AS escalated_count FROM tickets WHERE status = 'escalated'")
            escalated_count = cursor.fetchone()["escalated_count"]

            cursor.execute("SELECT COUNT(*) AS closed_count FROM tickets WHERE status = 'closed'")
            closed_count = cursor.fetchone()["closed_count"]

            cursor.execute("SELECT AVG(rating) AS avg_rating, COUNT(*) AS count FROM ticket_ratings")
            rating_row = cursor.fetchone()
            avg_rating = round(rating_row["avg_rating"] or 0.0, 2)
            ratings_count = rating_row["count"]

            cursor.execute("SELECT rating, COUNT(*) AS count FROM ticket_ratings GROUP BY rating")
            distribution = {r["rating"]: r["count"] for r in cursor.fetchall()}

            return {
                "total": total,
                "open": open_count,
                "escalated": escalated_count,
                "closed": closed_count,
                "avg_rating": avg_rating,
                "ratings_count": ratings_count,
                "distribution": distribution
            }

    def get_recent_reviews(self, limit: int = 5) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ticket_id, user_id, rating, feedback, created_at
                FROM ticket_ratings
                WHERE feedback IS NOT NULL AND feedback != ''
                ORDER BY created_at DESC LIMIT ?
            """, (limit,))
            return [dict(r) for r in cursor.fetchall()]

    # Canned Responses / FAQ Shortcuts
    def get_canned_response(self, shortcut: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM canned_responses WHERE shortcut = ? COLLATE NOCASE", (shortcut.strip(),))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_canned_responses(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM canned_responses ORDER BY shortcut ASC")
            return [dict(r) for r in cursor.fetchall()]

    def add_canned_response(self, shortcut: str, title: str, content: str, created_by: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO canned_responses (shortcut, title, content, created_by)
                VALUES (?, ?, ?, ?);
            """, (shortcut.strip().lower(), title.strip(), content.strip(), created_by))
            conn.commit()
            return True

    def delete_canned_response(self, shortcut: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM canned_responses WHERE shortcut = ? COLLATE NOCASE", (shortcut.strip(),))
            conn.commit()
            return cursor.rowcount > 0

    # Staff Performance Analytics & Leaderboard
    def get_staff_stats(self, staff_id: int) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS claimed FROM tickets WHERE claimed_by = ?", (staff_id,))
            claimed = cursor.fetchone()["claimed"]

            cursor.execute("SELECT COUNT(*) AS closed FROM tickets WHERE closed_by = ?", (staff_id,))
            closed = cursor.fetchone()["closed"]

            # Ratings on tickets this staff handled (claimed or closed)
            cursor.execute("""
                SELECT AVG(r.rating) AS avg_rating, COUNT(r.rating) AS total_rated
                FROM ticket_ratings r
                JOIN tickets t ON t.id = r.ticket_id
                WHERE t.claimed_by = ? OR t.closed_by = ?;
            """, (staff_id, staff_id))
            rate_row = cursor.fetchone()
            avg_rating = round(rate_row["avg_rating"] or 0.0, 2)
            total_rated = rate_row["total_rated"]

            return {
                "staff_id": staff_id,
                "claimed": claimed,
                "closed": closed,
                "avg_rating": avg_rating,
                "total_rated": total_rated
            }

    def get_staff_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COALESCE(t.claimed_by, t.closed_by) AS staff_id,
                    COUNT(DISTINCT t.id) AS tickets_handled,
                    AVG(r.rating) AS avg_rating,
                    COUNT(r.rating) AS rated_count
                FROM tickets t
                LEFT JOIN ticket_ratings r ON r.ticket_id = t.id
                WHERE t.claimed_by IS NOT NULL OR t.closed_by IS NOT NULL
                GROUP BY staff_id
                ORDER BY tickets_handled DESC, avg_rating DESC
                LIMIT ?;
            """, (limit,))
            return [dict(r) for r in cursor.fetchall() if r["staff_id"]]

    # Inactivity Tracking & Automation
    def get_inactive_tickets_for_warning(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Finds open tickets where staff was the last to reply and >24h elapsed with no warning sent."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM tickets
                WHERE status IN ('open', 'escalated')
                AND inactivity_warning_sent = 0
                AND last_staff_reply_at IS NOT NULL
                AND last_staff_reply_at >= last_message_at
                AND datetime(last_staff_reply_at, '+' || ? || ' hours') <= datetime('now');
            """, (hours,))
            return [dict(r) for r in cursor.fetchall()]

    def mark_inactivity_warning_sent(self, ticket_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE tickets SET inactivity_warning_sent = 1 WHERE id = ?", (ticket_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_inactive_tickets_for_close(self, hours: int = 48) -> List[Dict[str, Any]]:
        """Finds open tickets where warning was sent (or >48h elapsed since staff reply) and user remained inactive."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM tickets
                WHERE status IN ('open', 'escalated')
                AND last_staff_reply_at IS NOT NULL
                AND last_staff_reply_at >= last_message_at
                AND datetime(last_staff_reply_at, '+' || ? || ' hours') <= datetime('now');
            """, (hours,))
            return [dict(r) for r in cursor.fetchall()]
