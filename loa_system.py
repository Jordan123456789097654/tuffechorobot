import discord
from discord import ui
import sqlite3
import logging
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timezone
import config

logger = logging.getLogger("LOASystem")
DB_PATH = "verifications.db"

def init_loa_db():
    """Initializes tables for staff leave of absence requests."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS loa_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                duration TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'denied', 'expired'
                reviewed_by INTEGER,
                review_note TEXT,
                log_message_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TIMESTAMP
            );
        """)
        conn.commit()

init_loa_db()

def create_loa_request(user_id: int, guild_id: int, duration: str, reason: str) -> int:
    """Creates a new LOA request record and returns ID."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO loa_requests (user_id, guild_id, duration, reason, status)
            VALUES (?, ?, ?, ?, 'pending');
        """, (user_id, guild_id, duration, reason))
        conn.commit()
        return cursor.lastrowid

def set_loa_message_id(loa_id: int, message_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE loa_requests SET log_message_id = ? WHERE id = ?;", (message_id, loa_id))
        conn.commit()

def get_loa_request(loa_id: int) -> Optional[Dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM loa_requests WHERE id = ?;", (loa_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_user_active_loa(user_id: int) -> Optional[Dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM loa_requests
            WHERE user_id = ? AND status IN ('pending', 'approved')
            ORDER BY created_at DESC LIMIT 1;
        """, (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_loa_requests(status: Optional[str] = None, limit: int = 15) -> List[Dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if status:
            cursor.execute("SELECT * FROM loa_requests WHERE status = ? ORDER BY created_at DESC LIMIT ?;", (status, limit))
        else:
            cursor.execute("SELECT * FROM loa_requests ORDER BY created_at DESC LIMIT ?;", (limit,))
        return [dict(r) for r in cursor.fetchall()]

def review_loa_request(
    loa_id: int,
    reviewer_id: int,
    status: str,
    review_note: Optional[str] = None
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Approve or deny an LOA request."""
    loa = get_loa_request(loa_id)
    if not loa:
        return False, "LOA request not found.", None
    if loa["status"] != "pending":
        return False, f"LOA request has already been marked **{loa['status']}**.", loa

    now_iso = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE loa_requests
            SET status = ?, reviewed_by = ?, review_note = ?, reviewed_at = ?
            WHERE id = ?;
        """, (status, reviewer_id, review_note, now_iso, loa_id))
        conn.commit()

    updated = get_loa_request(loa_id)
    return True, f"LOA #{loa_id} marked {status}.", updated

def build_loa_staff_embed(
    loa_data: Dict[str, Any],
    staff_member: Optional[discord.User] = None,
    reviewer: Optional[discord.User] = None
) -> discord.Embed:
    """Builds the HR / management embed for reviewing an LOA request."""
    status = loa_data["status"]
    status_colors = {
        "pending": 0xFEE75C,
        "approved": 0x57F287,
        "denied": 0xED4245,
        "expired": 0x747F8D
    }
    color = status_colors.get(status, 0x5865F2)
    staff_name = staff_member.name if staff_member else f"Staff `{loa_data['user_id']}`"
    staff_mention = staff_member.mention if staff_member else f"<@{loa_data['user_id']}>"

    embed = discord.Embed(
        title=f"🏖️ Leave of Absence Request #{loa_data['id']}",
        description=f"Status: **{status.upper()}**",
        color=color,
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(name="👤 Staff Member", value=f"{staff_mention} (`{staff_name}`)", inline=True)
    embed.add_field(name="⏳ Requested Duration", value=f"`{loa_data['duration']}`", inline=True)
    embed.add_field(name="📝 Reason", value=loa_data["reason"], inline=False)

    if reviewer:
        embed.add_field(name="⚖️ Reviewed By", value=reviewer.mention, inline=True)
    if loa_data.get("review_note"):
        embed.add_field(name="💬 Review Note", value=f"`{loa_data['review_note']}`", inline=False)

    embed.set_footer(text="Echo Technologies HR • Leave of Absence Management")
    return embed

class LOAControlView(ui.View):
    """Management view with one-click approve/deny buttons."""

    def __init__(self, loa_id: int, disabled: bool = False):
        super().__init__(timeout=None)
        self.loa_id = loa_id
        self.add_item(
            ui.Button(
                label="Approve LOA",
                emoji="✅",
                style=discord.ButtonStyle.success,
                custom_id=f"loa_app:{loa_id}",
                disabled=disabled
            )
        )
        self.add_item(
            ui.Button(
                label="Deny LOA",
                emoji="❌",
                style=discord.ButtonStyle.danger,
                custom_id=f"loa_den:{loa_id}",
                disabled=disabled
            )
        )

class DenyLOAModal(ui.Modal):
    """Modal for HR to specify reason when denying an LOA request."""

    note_input = ui.TextInput(
        label="Denial Reason",
        placeholder="Explain why this LOA request cannot be approved at this time...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )

    def __init__(self, bot, loa_id: int):
        super().__init__(title=f"Deny LOA #{loa_id}")
        self.bot = bot
        self.loa_id = loa_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        success, msg, updated = review_loa_request(
            self.loa_id,
            interaction.user.id,
            "denied",
            review_note=self.note_input.value.strip()
        )
        if not success:
            await interaction.followup.send(f"⚠️ {msg}", ephemeral=True)
            return

        # Update message
        staff_user = self.bot.get_user(updated["user_id"])
        embed = build_loa_staff_embed(updated, staff_user, interaction.user)
        view = LOAControlView(self.loa_id, disabled=True)
        try:
            await interaction.message.edit(embed=embed, view=view)
        except Exception:
            pass

        # Send DM to staff member
        if staff_user:
            try:
                dm = await staff_user.create_dm()
                dm_embed = discord.Embed(
                    title=f"🏖️ LOA Request #{self.loa_id} Denied",
                    description=(
                        f"Hello {staff_user.name}, your Leave of Absence request has been **denied** by {interaction.user.mention}.\n\n"
                        f"**Reason:**\n> {self.note_input.value.strip()}\n\n"
                        f"Please contact management if you have any questions."
                    ),
                    color=0xED4245
                )
                await dm.send(embed=dm_embed)
            except Exception:
                pass

        await interaction.followup.send(f"❌ LOA #{self.loa_id} has been denied.", ephemeral=True)
