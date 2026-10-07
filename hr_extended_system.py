import sqlite3
import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

logger = logging.getLogger("roblox_bot.hr_extended_system")
DB_PATH = "verifications.db"

def init_hr_extended_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Shifts table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hr_shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER NOT NULL,
            clock_in TIMESTAMP NOT NULL,
            clock_out TIMESTAMP,
            duration_seconds INTEGER DEFAULT 0
        );
    """)

    # Active active shift tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hr_active_duty (
            discord_id INTEGER PRIMARY KEY,
            clock_in TIMESTAMP NOT NULL
        );
    """)

    # Commendations table with preset rewards
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hr_commendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER NOT NULL,
            issued_by INTEGER NOT NULL,
            reason TEXT NOT NULL,
            reward_type TEXT NOT NULL,
            issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Staff Meetings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hr_staff_meetings (
            meeting_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            date_time TEXT NOT NULL,
            topic TEXT NOT NULL,
            is_mandatory BOOLEAN NOT NULL,
            notes TEXT,
            message_id INTEGER,
            channel_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Staff Meeting RSVPs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hr_meeting_rsvps (
            meeting_id INTEGER NOT NULL,
            discord_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            reason TEXT,
            PRIMARY KEY (meeting_id, discord_id)
        );
    """)

    # Staff Resignations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hr_resignations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER NOT NULL,
            resignation_type TEXT NOT NULL,
            reason TEXT NOT NULL,
            processed_by INTEGER NOT NULL,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    conn.close()

init_hr_extended_db()

# PRESET COMMENDATION REWARDS
PRESET_COMMENDATION_REWARDS = {
    "quota_exemption": "🎟️ 1-Week Staff Quota Exemption",
    "points_1000": "💰 1,000 Community Points",
    "custom_role": "🌟 Special Custom Role / Title",
    "priority_queue": "⚡ Priority Ticket Assignment",
    "robux_card": "💵 500 Robux Reward Code",
    "recognition_badge": "🎖️ Staff Commendation Badge"
}

# --- SHIFT / DUTY FUNCTIONS ---
def clock_in_staff(discord_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    try:
        cursor.execute("INSERT INTO hr_active_duty (discord_id, clock_in) VALUES (?, ?)", (discord_id, now))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def clock_out_staff(discord_id: int) -> Optional[int]:
    """Clocks out staff member and returns duration in seconds."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT clock_in FROM hr_active_duty WHERE discord_id = ?", (discord_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    clock_in_dt = datetime.fromisoformat(row[0])
    now_dt = datetime.now(timezone.utc)
    duration = int((now_dt - clock_in_dt).total_seconds())

    cursor.execute("DELETE FROM hr_active_duty WHERE discord_id = ?", (discord_id,))
    cursor.execute("""
        INSERT INTO hr_shifts (discord_id, clock_in, clock_out, duration_seconds)
        VALUES (?, ?, ?, ?)
    """, (discord_id, row[0], now_dt.isoformat(), duration))

    conn.commit()
    conn.close()
    return duration

def get_staff_shift_stats(discord_id: int) -> Dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if currently active
    cursor.execute("SELECT clock_in FROM hr_active_duty WHERE discord_id = ?", (discord_id,))
    active_row = cursor.fetchone()

    # Total lifetime duration
    cursor.execute("SELECT SUM(duration_seconds), COUNT(id) FROM hr_shifts WHERE discord_id = ?", (discord_id,))
    total_row = cursor.fetchone()
    total_sec = total_row[0] or 0
    total_shifts = total_row[1] or 0

    # Past 7 days duration
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    cursor.execute("""
        SELECT SUM(duration_seconds) FROM hr_shifts
        WHERE discord_id = ? AND clock_in >= ?
    """, (discord_id, seven_days_ago))
    weekly_row = cursor.fetchone()
    weekly_sec = weekly_row[0] or 0

    conn.close()
    return {
        "is_on_duty": active_row is not None,
        "active_clock_in": active_row[0] if active_row else None,
        "total_seconds": total_sec,
        "weekly_seconds": weekly_sec,
        "total_shifts": total_shifts
    }

# --- COMMENDATION FUNCTIONS ---
def add_commendation(discord_id: int, issued_by: int, reason: str, reward_type: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hr_commendations (discord_id, issued_by, reason, reward_type)
        VALUES (?, ?, ?, ?)
    """, (discord_id, issued_by, reason, reward_type))
    comm_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return comm_id

def get_user_commendations(discord_id: int) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hr_commendations WHERE discord_id = ? ORDER BY issued_at DESC", (discord_id,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "discord_id": r[1],
            "issued_by": r[2],
            "reason": r[3],
            "reward_type": r[4],
            "issued_at": r[5]
        }
        for r in rows
    ]

# --- MEETING & RSVP FUNCTIONS ---
def create_staff_meeting(title: str, date_time: str, topic: str, is_mandatory: bool, notes: Optional[str] = None) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hr_staff_meetings (title, date_time, topic, is_mandatory, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (title, date_time, topic, is_mandatory, notes))
    m_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return m_id

def set_meeting_message(meeting_id: int, channel_id: int, message_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE hr_staff_meetings SET channel_id = ?, message_id = ? WHERE meeting_id = ?
    """, (channel_id, message_id, meeting_id))
    conn.commit()
    conn.close()

def record_meeting_rsvp(meeting_id: int, discord_id: int, status: str, reason: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hr_meeting_rsvps (meeting_id, discord_id, status, reason)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(meeting_id, discord_id) DO UPDATE SET
            status = excluded.status,
            reason = excluded.reason;
    """, (meeting_id, discord_id, status, reason))
    conn.commit()
    conn.close()

def get_meeting_rsvp_counts(meeting_id: int) -> Dict[str, int]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT status, COUNT(*) FROM hr_meeting_rsvps WHERE meeting_id = ? GROUP BY status
    """, (meeting_id,))
    rows = cursor.fetchall()
    conn.close()
    counts = {"attending": 0, "cannot_attend": 0, "tentative": 0}
    for status, count in rows:
        if status in counts:
            counts[status] = count
    return counts

# --- MEETING RSVP INTERACTIVE VIEW ---
class StaffMeetingRSVPView(discord.ui.View):
    def __init__(self, meeting_id: int):
        super().__init__(timeout=None)
        self.meeting_id = meeting_id

    @discord.ui.button(label="✅ Attending", style=discord.ButtonStyle.success, custom_id="rsvp_attending")
    async def attending_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        record_meeting_rsvp(self.meeting_id, interaction.user.id, "attending")
        await interaction.response.send_message("✅ Your RSVP status has been set to **Attending**!", ephemeral=True)
        await self.update_meeting_embed(interaction)

    @discord.ui.button(label="❌ Cannot Attend", style=discord.ButtonStyle.danger, custom_id="rsvp_cannot")
    async def cannot_attend_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = CannotAttendModal(self.meeting_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="⏳ Tentative", style=discord.ButtonStyle.secondary, custom_id="rsvp_tentative")
    async def tentative_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        record_meeting_rsvp(self.meeting_id, interaction.user.id, "tentative")
        await interaction.response.send_message("⏳ Your RSVP status has been set to **Tentative**!", ephemeral=True)
        await self.update_meeting_embed(interaction)

    async def update_meeting_embed(self, interaction: discord.Interaction):
        try:
            counts = get_meeting_rsvp_counts(self.meeting_id)
            embed = interaction.message.embeds[0]

            # Update RSVP field if present
            for i, f in enumerate(embed.fields):
                if "RSVP Status" in f.name:
                    embed.set_field_at(
                        i,
                        name="📊 RSVP Status Summary",
                        value=(
                            f"✅ **Attending:** `{counts['attending']}`\n"
                            f"❌ **Cannot Attend:** `{counts['cannot_attend']}`\n"
                            f"⏳ **Tentative:** `{counts['tentative']}`"
                        ),
                        inline=False
                    )
                    break
            await interaction.message.edit(embed=embed)
        except Exception as e:
            logger.error(f"Failed to update meeting embed: {e}")

class CannotAttendModal(discord.ui.Modal, title="Submit Absence Reason"):
    reason_input = discord.ui.TextInput(
        label="Reason for Absence",
        style=discord.TextStyle.paragraph,
        placeholder="Please detail why you cannot attend this mandatory staff meeting...",
        required=True,
        max_length=500
    )

    def __init__(self, meeting_id: int):
        super().__init__()
        self.meeting_id = meeting_id

    async def on_submit(self, interaction: discord.Interaction):
        record_meeting_rsvp(self.meeting_id, interaction.user.id, "cannot_attend", self.reason_input.value)
        await interaction.response.send_message(
            f"❌ Your absence notice has been submitted to HR:\n*\"{self.reason_input.value}\"*",
            ephemeral=True
        )
