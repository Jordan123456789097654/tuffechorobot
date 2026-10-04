import discord
from discord import ui
import sqlite3
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger("BugTrackerSystem")
DB_PATH = "verifications.db"

def init_bugs_db():
    """Initializes tables for bug reporting and backlog management."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bug_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reporter_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                message_id INTEGER,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                reproduction_steps TEXT,
                severity TEXT DEFAULT 'Normal', -- 'Low', 'Normal', 'High', 'Critical'
                status TEXT DEFAULT 'Open', -- 'Open', 'Claimed', 'In Progress', 'Resolved', 'Closed'
                claimed_by INTEGER,
                dev_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

init_bugs_db()

def create_bug_report(
    reporter_id: int,
    guild_id: int,
    title: str,
    description: str,
    reproduction_steps: Optional[str] = None,
    severity: str = "Normal"
) -> int:
    """Inserts a new bug report into the database."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO bug_reports (reporter_id, guild_id, title, description, reproduction_steps, severity, status)
            VALUES (?, ?, ?, ?, ?, ?, 'Open');
        """, (reporter_id, guild_id, title, description, reproduction_steps or "Not specified", severity))
        conn.commit()
        return cursor.lastrowid

def set_bug_message(bug_id: int, message_id: int):
    """Binds the posted Discord backlog message ID to the bug report."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE bug_reports SET message_id = ? WHERE id = ?;", (message_id, bug_id))
        conn.commit()

def get_bug_report(bug_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves a bug report by ID."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bug_reports WHERE id = ?;", (bug_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def claim_bug(bug_id: int, dev_id: int) -> bool:
    """Assigns a bug to a developer."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE bug_reports
            SET claimed_by = ?, status = 'Claimed', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
        """, (dev_id, bug_id))
        conn.commit()
        return cursor.rowcount > 0

def update_bug_status(bug_id: int, status: str, dev_id: int, dev_notes: Optional[str] = None) -> bool:
    """Updates bug status and developer notes."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if dev_notes:
            cursor.execute("""
                UPDATE bug_reports
                SET status = ?, dev_notes = ?, claimed_by = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
            """, (status, dev_notes, dev_id, bug_id))
        else:
            cursor.execute("""
                UPDATE bug_reports
                SET status = ?, claimed_by = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
            """, (status, dev_id, bug_id))
        conn.commit()
        return cursor.rowcount > 0

def get_recent_bugs(limit: int = 10, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves list of recent bug reports."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if status:
            cursor.execute("SELECT * FROM bug_reports WHERE status = ? ORDER BY id DESC LIMIT ?;", (status, limit))
        else:
            cursor.execute("SELECT * FROM bug_reports ORDER BY id DESC LIMIT ?;", (limit,))
        return [dict(r) for r in cursor.fetchall()]

def build_bug_embed(
    report: Dict[str, Any],
    reporter: Optional[discord.User] = None,
    dev: Optional[discord.User] = None
) -> discord.Embed:
    """Builds the structured Discord card for #dev-backlog."""
    severity = report.get("severity", "Normal")
    status = report.get("status", "Open")
    bid = report["id"]

    if severity == "Critical":
        color = 0xED4245
        sev_badge = "🔴 **Critical (P1)**"
    elif severity == "High":
        color = 0xE67E22
        sev_badge = "🟠 **High (P2)**"
    elif severity == "Normal":
        color = 0xFEE75C
        sev_badge = "🟡 **Normal (P3)**"
    else:
        color = 0x57F287
        sev_badge = "🟢 **Low (P4)**"

    if status == "Resolved":
        color = 0x57F287
        status_badge = "✅ **Resolved & Deployed**"
    elif status == "In Progress":
        color = 0x00A2FF
        status_badge = "🚧 **Active Investigation / Fix In Progress**"
    elif status == "Claimed":
        color = 0x5865F2
        dev_tag = dev.mention if dev else f"<@{report.get('claimed_by', 0)}>"
        status_badge = f"📌 **Claimed by {dev_tag}**"
    elif status == "Closed":
        color = 0x747F8D
        status_badge = "❌ **Closed / Cannot Reproduce / Won't Fix**"
    else:
        status_badge = "📋 **Open Backlog Issue**"

    embed = discord.Embed(
        title=f"🛠️ Bug Report #{bid}: {report['title']}",
        description=report["description"],
        color=color,
        timestamp=discord.utils.utcnow()
    )

    if reporter:
        embed.set_author(name=f"Reported by {reporter.display_name} (@{reporter.name})", icon_url=reporter.display_avatar.url)

    embed.add_field(name="Severity", value=sev_badge, inline=True)
    embed.add_field(name="Status", value=status_badge, inline=True)
    if dev:
        embed.add_field(name="Assigned Developer", value=dev.mention, inline=True)

    if report.get("reproduction_steps") and report["reproduction_steps"] != "Not specified":
        embed.add_field(name="Reproduction Steps", value=f"```\n{report['reproduction_steps'][:1000]}\n```", inline=False)

    if report.get("dev_notes"):
        embed.add_field(name="Developer Fix / Resolution Notes", value=f"> *\"{report['dev_notes']}\"*", inline=False)

    embed.set_footer(text=f"Echo Technologies Dev Tracker • Backlog #{bid}")
    return embed


class BugReportControlView(ui.View):
    """Interactive management buttons attached to the bug backlog card."""

    def __init__(self, bot, bug_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.bug_id = bug_id

        self.claim_btn.custom_id = f"bug_clm:{bug_id}"
        self.progress_btn.custom_id = f"bug_prg:{bug_id}"
        self.resolve_btn.custom_id = f"bug_res:{bug_id}"
        self.close_btn.custom_id = f"bug_cls:{bug_id}"

    @ui.button(label="Claim Issue", style=discord.ButtonStyle.primary, emoji="📌", custom_id="bug_clm_default", row=0)
    async def claim_btn(self, interaction: discord.Interaction, button: ui.Button):
        claim_bug(self.bug_id, interaction.user.id)
        report = get_bug_report(self.bug_id)
        if report:
            reporter = self.bot.get_user(report["reporter_id"])
            embed = build_bug_embed(report, reporter, interaction.user)
            await interaction.response.edit_message(embed=embed, view=self)
            await interaction.followup.send(f"📌 {interaction.user.mention} has claimed Bug #{self.bug_id}!", ephemeral=False)
        else:
            await interaction.response.defer()

    @ui.button(label="In Progress", style=discord.ButtonStyle.secondary, emoji="🚧", custom_id="bug_prg_default", row=0)
    async def progress_btn(self, interaction: discord.Interaction, button: ui.Button):
        update_bug_status(self.bug_id, "In Progress", interaction.user.id)
        report = get_bug_report(self.bug_id)
        if report:
            reporter = self.bot.get_user(report["reporter_id"])
            embed = build_bug_embed(report, reporter, interaction.user)
            await interaction.response.edit_message(embed=embed, view=self)
            await interaction.followup.send(f"🚧 Bug #{self.bug_id} marked **In Progress** by {interaction.user.mention}.", ephemeral=False)
        else:
            await interaction.response.defer()

    @ui.button(label="Resolve", style=discord.ButtonStyle.success, emoji="✅", custom_id="bug_res_default", row=1)
    async def resolve_btn(self, interaction: discord.Interaction, button: ui.Button):
        modal = ResolveBugModal(self.bot, self.bug_id)
        await interaction.response.send_modal(modal)

    @ui.button(label="Close / Won't Fix", style=discord.ButtonStyle.danger, emoji="❌", custom_id="bug_cls_default", row=1)
    async def close_btn(self, interaction: discord.Interaction, button: ui.Button):
        update_bug_status(self.bug_id, "Closed", interaction.user.id, "Closed / Won't Fix")
        report = get_bug_report(self.bug_id)
        if report:
            reporter = self.bot.get_user(report["reporter_id"])
            embed = build_bug_embed(report, reporter, interaction.user)
            await interaction.response.edit_message(embed=embed, view=self)
            await interaction.followup.send(f"❌ Bug #{self.bug_id} has been marked **Closed** by {interaction.user.mention}.", ephemeral=False)
        else:
            await interaction.response.defer()


class ResolveBugModal(ui.Modal, title="Resolve Bug Report"):
    """Modal allowing developers to document their fix and notify the reporter."""

    resolution_notes = ui.TextInput(
        label="Fix Details / Patch Notes",
        placeholder="Explain what was fixed, commit reference, or update release...",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )

    def __init__(self, bot, bug_id: int):
        super().__init__()
        self.bot = bot
        self.bug_id = bug_id

    async def on_submit(self, interaction: discord.Interaction):
        notes = self.resolution_notes.value.strip()
        update_bug_status(self.bug_id, "Resolved", interaction.user.id, notes)

        report = get_bug_report(self.bug_id)
        if report:
            reporter = self.bot.get_user(report["reporter_id"])
            if not reporter:
                try:
                    reporter = await self.bot.fetch_user(report["reporter_id"])
                except Exception:
                    reporter = None
            view = BugReportControlView(self.bot, self.bug_id)
            embed = build_bug_embed(report, reporter, interaction.user)

            if interaction.message:
                await interaction.message.edit(embed=embed, view=view)

            await interaction.response.send_message(f"✅ Bug #{self.bug_id} has been marked as **RESOLVED**!", ephemeral=True)

            # Notify reporter via DM
            if reporter:
                try:
                    dm = await reporter.create_dm()
                    dm_embed = discord.Embed(
                        title=f"🎉 Bug Report #{self.bug_id} Resolved!",
                        description=(
                            f"Hello **{reporter.name}**, great news! The issue you reported to **Echo Technologies** has been marked as resolved.\n\n"
                            f"• **Bug Title:** `{report['title']}`\n"
                            f"• **Resolved By:** {interaction.user.mention} (`{interaction.user.display_name}`)\n"
                            f"• **Resolution Notes:**\n> *\"{notes}\"*\n\n"
                            f"Thank you for helping keep our games and tools running smoothly! 🚀"
                        ),
                        color=0x57F287,
                        timestamp=discord.utils.utcnow()
                    )
                    await dm.send(embed=dm_embed)
                except Exception:
                    pass
