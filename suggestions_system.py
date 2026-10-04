import discord
from discord import ui
import sqlite3
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime

logger = logging.getLogger("SuggestionsSystem")
DB_PATH = "verifications.db"

def init_suggestions_db():
    """Initializes tables for suggestions and vote tracking."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                author_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                message_id INTEGER,
                content TEXT NOT NULL,
                attachment_url TEXT,
                status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'in_progress', 'denied'
                staff_note TEXT,
                reviewed_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS suggestion_votes (
                suggestion_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                vote_type INTEGER NOT NULL, -- 1: Upvote, -1: Downvote
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (suggestion_id, user_id),
                FOREIGN KEY (suggestion_id) REFERENCES suggestions(id) ON DELETE CASCADE
            );
        """)
        conn.commit()

init_suggestions_db()

def create_suggestion(author_id: int, guild_id: int, content: str, attachment_url: Optional[str] = None) -> int:
    """Inserts a new suggestion record and returns its ID."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO suggestions (author_id, guild_id, content, attachment_url, status)
            VALUES (?, ?, ?, ?, 'pending');
        """, (author_id, guild_id, content, attachment_url))
        conn.commit()
        return cursor.lastrowid

def set_suggestion_message(suggestion_id: int, message_id: int):
    """Binds the posted Discord message ID to the suggestion record."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE suggestions SET message_id = ? WHERE id = ?;", (message_id, suggestion_id))
        conn.commit()

def get_suggestion(suggestion_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves a suggestion by ID."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM suggestions WHERE id = ?;", (suggestion_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_vote_counts(suggestion_id: int) -> Tuple[int, int]:
    """Returns (upvotes, downvotes) for a given suggestion."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM suggestion_votes WHERE suggestion_id = ? AND vote_type = 1;", (suggestion_id,))
        upvotes = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM suggestion_votes WHERE suggestion_id = ? AND vote_type = -1;", (suggestion_id,))
        downvotes = cursor.fetchone()[0]
        return upvotes, downvotes

def vote_suggestion(suggestion_id: int, user_id: int, vote_type: int) -> Tuple[int, int, str]:
    """Records or toggles a user's vote. Returns (upvotes, downvotes, status_message)."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT vote_type FROM suggestion_votes WHERE suggestion_id = ? AND user_id = ?;", (suggestion_id, user_id))
        row = cursor.fetchone()

        if row:
            existing = row[0]
            if existing == vote_type:
                # Toggle off (remove vote)
                cursor.execute("DELETE FROM suggestion_votes WHERE suggestion_id = ? AND user_id = ?;", (suggestion_id, user_id))
                conn.commit()
                msg = "Vote removed."
            else:
                # Switch vote
                cursor.execute("UPDATE suggestion_votes SET vote_type = ? WHERE suggestion_id = ? AND user_id = ?;", (vote_type, suggestion_id, user_id))
                conn.commit()
                msg = "Vote switched to " + ("Upvote 👍" if vote_type == 1 else "Downvote 👎")
        else:
            # New vote
            cursor.execute("INSERT INTO suggestion_votes (suggestion_id, user_id, vote_type) VALUES (?, ?, ?);", (suggestion_id, user_id, vote_type))
            conn.commit()
            msg = "Voted " + ("Upvote 👍" if vote_type == 1 else "Downvote 👎")

    ups, downs = get_vote_counts(suggestion_id)
    return ups, downs, msg

def update_suggestion_status(suggestion_id: int, status: str, reviewer_id: int, staff_note: str) -> bool:
    """Updates the decision status and staff note on a suggestion."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE suggestions
            SET status = ?, reviewed_by = ?, staff_note = ?
            WHERE id = ?;
        """, (status.lower(), reviewer_id, staff_note, suggestion_id))
        conn.commit()
        return cursor.rowcount > 0

def build_suggestion_embed(
    suggestion: Dict[str, Any],
    upvotes: int,
    downvotes: int,
    author: Optional[discord.User] = None,
    reviewer: Optional[discord.User] = None
) -> discord.Embed:
    """Renders the comprehensive Echo Technologies suggestion card."""
    status = suggestion.get("status", "pending").lower()
    sid = suggestion["id"]

    if status == "approved":
        color = 0x57F287 # Green
        status_tag = "✅ **Approved by Staff**"
    elif status == "in_progress":
        color = 0x00A2FF # Blue
        status_tag = "🚧 **In Development / Consideration**"
    elif status == "denied":
        color = 0xED4245 # Red
        status_tag = "❌ **Denied / Declined**"
    else:
        color = 0xFEE75C # Yellow
        status_tag = "⏳ **Under Community Review**"

    embed = discord.Embed(
        title=f"💡 Echo Technologies Suggestion #{sid}",
        description=suggestion["content"],
        color=color,
        timestamp=discord.utils.utcnow()
    )

    if author:
        embed.set_author(name=f"Submitted by {author.display_name} (@{author.name})", icon_url=author.display_avatar.url)

    embed.add_field(name="Status", value=status_tag, inline=True)
    total_votes = upvotes + downvotes
    ratio_str = f"👍 `{upvotes}`  •  👎 `{downvotes}`  ({total_votes} total)"
    embed.add_field(name="Community Feedback", value=ratio_str, inline=True)

    if suggestion.get("staff_note"):
        rev_tag = reviewer.mention if reviewer else f"<@{suggestion['reviewed_by']}>"
        embed.add_field(name=f"Staff Decision ({rev_tag})", value=f"> *\"{suggestion['staff_note']}\"*", inline=False)

    if suggestion.get("attachment_url"):
        embed.set_image(url=suggestion["attachment_url"])

    embed.set_footer(text=f"Echo Technologies Ideas & Feedback • #{sid}")
    return embed


class SuggestionVoteView(ui.View):
    """Interactive voting and management buttons for suggestions."""

    def __init__(self, bot, suggestion_id: int, upvotes: int = 0, downvotes: int = 0):
        super().__init__(timeout=None)
        self.bot = bot
        self.suggestion_id = suggestion_id

        # Update button labels and custom IDs
        self.upvote_btn.label = f"👍 {upvotes}"
        self.upvote_btn.custom_id = f"sug_up:{suggestion_id}"

        self.downvote_btn.label = f"👎 {downvotes}"
        self.downvote_btn.custom_id = f"sug_dn:{suggestion_id}"

        self.review_btn.custom_id = f"sug_rev:{suggestion_id}"

    @ui.button(style=discord.ButtonStyle.success, emoji="👍", custom_id="sug_up_default")
    async def upvote_btn(self, interaction: discord.Interaction, button: ui.Button):
        ups, downs, msg = vote_suggestion(self.suggestion_id, interaction.user.id, 1)
        button.label = f"👍 {ups}"
        self.downvote_btn.label = f"👎 {downs}"

        # Update embed
        sug = get_suggestion(self.suggestion_id)
        if sug:
            author = self.bot.get_user(sug["author_id"])
            reviewer = self.bot.get_user(sug.get("reviewed_by") or 0)
            new_embed = build_suggestion_embed(sug, ups, downs, author, reviewer)
            await interaction.response.edit_message(embed=new_embed, view=self)
        else:
            await interaction.response.defer()

    @ui.button(style=discord.ButtonStyle.danger, emoji="👎", custom_id="sug_dn_default")
    async def downvote_btn(self, interaction: discord.Interaction, button: ui.Button):
        ups, downs, msg = vote_suggestion(self.suggestion_id, interaction.user.id, -1)
        self.upvote_btn.label = f"👍 {ups}"
        button.label = f"👎 {downs}"

        sug = get_suggestion(self.suggestion_id)
        if sug:
            author = self.bot.get_user(sug["author_id"])
            reviewer = self.bot.get_user(sug.get("reviewed_by") or 0)
            new_embed = build_suggestion_embed(sug, ups, downs, author, reviewer)
            await interaction.response.edit_message(embed=new_embed, view=self)
        else:
            await interaction.response.defer()

    @ui.button(label="Review Status", style=discord.ButtonStyle.secondary, emoji="⚖️", custom_id="sug_rev_default")
    async def review_btn(self, interaction: discord.Interaction, button: ui.Button):
        # Ensure only staff/administrators can change status
        is_admin = interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator
        if not is_admin:
            await interaction.response.send_message("❌ Only management staff may review and change suggestion statuses.", ephemeral=True)
            return

        modal = ReviewSuggestionModal(self.bot, self.suggestion_id)
        await interaction.response.send_modal(modal)


class ReviewSuggestionModal(ui.Modal, title="Review Suggestion"):
    """Modal for staff to approve, mark in progress, or deny a suggestion with feedback."""

    decision = ui.TextInput(
        label="Decision (Approved, In Progress, Denied)",
        placeholder="Type: Approved, In Progress, or Denied",
        max_length=20,
        required=True
    )

    feedback = ui.TextInput(
        label="Feedback / Note to Community",
        placeholder="Explain the reasoning or outline development plans...",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )

    def __init__(self, bot, suggestion_id: int):
        super().__init__()
        self.bot = bot
        self.suggestion_id = suggestion_id

    async def on_submit(self, interaction: discord.Interaction):
        raw_dec = self.decision.value.strip().lower()
        if "app" in raw_dec:
            status = "approved"
        elif "prog" in raw_dec or "dev" in raw_dec:
            status = "in_progress"
        elif "den" in raw_dec or "rej" in raw_dec:
            status = "denied"
        else:
            await interaction.response.send_message("❌ Invalid decision! Please enter: Approved, In Progress, or Denied.", ephemeral=True)
            return

        note = self.feedback.value.strip()
        update_suggestion_status(self.suggestion_id, status, interaction.user.id, note)

        # Update Discord message
        sug = get_suggestion(self.suggestion_id)
        if sug:
            ups, downs = get_vote_counts(self.suggestion_id)
            author = self.bot.get_user(sug["author_id"]) or await self.bot.fetch_user(sug["author_id"])
            view = SuggestionVoteView(self.bot, self.suggestion_id, ups, downs)
            new_embed = build_suggestion_embed(sug, ups, downs, author, interaction.user)

            if interaction.message:
                await interaction.message.edit(embed=new_embed, view=view)

            await interaction.response.send_message(f"✅ Suggestion #{self.suggestion_id} status updated to **{status.upper()}**!", ephemeral=True)

            # Notify author via DM
            if author:
                try:
                    dm = await author.create_dm()
                    dm_embed = discord.Embed(
                        title=f"💡 Suggestion #{self.suggestion_id} Update",
                        description=(
                            f"Hello **{author.name}**, your suggestion submitted to **Echo Technologies** has been reviewed!\n\n"
                            f"• **Status:** **{status.upper()}**\n"
                            f"• **Reviewer:** {interaction.user.mention} (`{interaction.user.display_name}`)\n"
                            f"• **Feedback Note:**\n> *\"{note}\"*\n\n"
                            f"Thank you for helping us innovate and improve!"
                        ),
                        color=0x57F287 if status == "approved" else (0x00A2FF if status == "in_progress" else 0xED4245),
                        timestamp=discord.utils.utcnow()
                    )
                    await dm.send(embed=dm_embed)
                except Exception:
                    pass
