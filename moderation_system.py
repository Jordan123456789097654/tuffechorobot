import discord
from discord import ui
import sqlite3
import re
import logging
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timedelta, timezone
import config

logger = logging.getLogger("ModerationSystem")
DB_PATH = "verifications.db"

def init_moderation_db():
    """Initializes tables for moderation cases, warnings, and global security bans."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Mod Cases History
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mod_cases (
                case_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                target_name TEXT NOT NULL,
                moderator_id INTEGER NOT NULL,
                moderator_name TEXT NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                duration TEXT DEFAULT NULL,
                log_message_id INTEGER DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # User Warnings
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                moderator_name TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # Global Bans
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS global_bans (
                user_id INTEGER PRIMARY KEY,
                reason TEXT NOT NULL,
                banned_by INTEGER NOT NULL,
                banned_by_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

init_moderation_db()

# --- DURATION PARSER ---

def parse_duration(time_str: str) -> Optional[timedelta]:
    """
    Parses a time string like '10m', '2h', '1d', '7d' into a timedelta.
    Maximum allowed Discord timeout duration is 28 days.
    """
    time_str = time_str.strip().lower()
    total_seconds = 0
    pattern = r"(\d+)\s*(s|sec|m|min|h|hr|hour|d|day|w|week)s?"
    matches = re.findall(pattern, time_str)
    if not matches:
        # Check if plain integer provided (assumed minutes)
        if time_str.isdigit():
            total_seconds = int(time_str) * 60
        else:
            return None
    else:
        for val, unit in matches:
            amount = int(val)
            if unit in ("s", "sec"):
                total_seconds += amount
            elif unit in ("m", "min"):
                total_seconds += amount * 60
            elif unit in ("h", "hr", "hour"):
                total_seconds += amount * 3600
            elif unit in ("d", "day"):
                total_seconds += amount * 86400
            elif unit in ("w", "week"):
                total_seconds += amount * 604800

    if total_seconds <= 0:
        return None
    # Cap at 28 days
    if total_seconds > 28 * 86400:
        total_seconds = 28 * 86400
    return timedelta(seconds=total_seconds)

def format_duration(td: timedelta) -> str:
    """Formats a timedelta into a clean human-readable duration."""
    total_secs = int(td.total_seconds())
    days, rem = divmod(total_secs, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 and not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts) if parts else "0s"


# --- WARNINGS DB MANAGEMENT ---

def add_warning(guild_id: int, user_id: int, moderator_id: int, moderator_name: str, reason: str) -> Tuple[int, int]:
    """Saves a warning to database and returns (warning_id, total_warnings_count)."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO warnings (guild_id, user_id, moderator_id, moderator_name, reason)
            VALUES (?, ?, ?, ?, ?);
        """, (guild_id, user_id, moderator_id, moderator_name, reason))
        warn_id = cursor.lastrowid
        cursor.execute("SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?;", (guild_id, user_id))
        count = cursor.fetchone()[0]
        conn.commit()
        return warn_id, count

def get_warnings(guild_id: int, user_id: int) -> List[Dict[str, Any]]:
    """Retrieves all warnings for a user in a guild."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM warnings
            WHERE guild_id = ? AND user_id = ?
            ORDER BY created_at DESC;
        """, (guild_id, user_id))
        return [dict(r) for r in cursor.fetchall()]

def clear_warnings(guild_id: int, user_id: int) -> int:
    """Clears all warnings for a user in a guild and returns count removed."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ?;", (guild_id, user_id))
        conn.commit()
        return cursor.rowcount


# --- GLOBAL BANS MANAGEMENT ---

def add_global_ban(user_id: int, reason: str, banned_by: int, banned_by_name: str):
    """Adds a user to the permanent global bans list."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO global_bans (user_id, reason, banned_by, banned_by_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                reason = excluded.reason,
                banned_by = excluded.banned_by,
                banned_by_name = excluded.banned_by_name,
                created_at = CURRENT_TIMESTAMP;
        """, (user_id, reason, banned_by, banned_by_name))
        conn.commit()

def remove_global_ban(user_id: int) -> bool:
    """Removes a user from the global bans list."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM global_bans WHERE user_id = ?;", (user_id,))
        conn.commit()
        return cursor.rowcount > 0

def is_globally_banned(user_id: int) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Checks if a user is actively on the global ban list."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM global_bans WHERE user_id = ?;", (user_id,))
        row = cursor.fetchone()
        return (True, dict(row)) if row else (False, None)

def get_all_global_bans() -> List[Dict[str, Any]]:
    """Returns all actively globally banned users."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM global_bans ORDER BY created_at DESC;")
        return [dict(r) for r in cursor.fetchall()]


# --- CASE REGISTRATION & AUDIT LOGGING ---

def create_mod_case(
    guild_id: int,
    target_id: int,
    target_name: str,
    moderator_id: int,
    moderator_name: str,
    action: str,
    reason: str,
    duration: Optional[str] = None
) -> int:
    """Creates a persistent moderation case record and returns its ID."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO mod_cases (guild_id, target_id, target_name, moderator_id, moderator_name, action, reason, duration)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, (guild_id, target_id, target_name, moderator_id, moderator_name, action, reason, duration))
        conn.commit()
        return cursor.lastrowid

def get_mod_case(case_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves a moderation case by ID."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM mod_cases WHERE case_id = ?;", (case_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def set_case_log_message_id(case_id: int, message_id: int):
    """Stores the Discord message ID for the audit log entry."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE mod_cases SET log_message_id = ? WHERE case_id = ?;", (message_id, case_id))
        conn.commit()


class InfractionAppealDMView(ui.View):
    """Interactive view attached to DM infraction notices allowing users to submit appeals."""
    def __init__(self, action_label: str = "Moderation Infraction", reason: str = "Disciplinary action"):
        super().__init__(timeout=None)
        self.action_label = action_label
        self.reason = reason
        self.add_item(ui.Button(label="🔗 Server Support / Invite", style=discord.ButtonStyle.link, url=config.SERVER_INVITE_URL))

    @ui.button(label="📜 Submit Appeal", style=discord.ButtonStyle.primary, emoji="📜", custom_id="dm_appeal_submit")
    async def appeal_button(self, interaction: discord.Interaction, button: ui.Button):
        act = self.action_label
        rsn = self.reason
        if interaction.message and interaction.message.embeds:
            emb = interaction.message.embeds[0]
            if "Mod Notice • You were " in (emb.title or ""):
                act = emb.title.replace("⚖️ Mod Notice • You were ", "").strip()
            match = re.search(r"\*\*Reason:\*\*\n>\s*(.*)", emb.description or "", re.DOTALL)
            if match:
                rsn = match.group(1).split("\n\n")[0].strip()

        modal = InfractionAppealModal(action_label=act, original_reason=rsn)
        await interaction.response.send_modal(modal)


class InfractionAppealModal(ui.Modal, title="⚖️ Moderation Appeal Submission"):
    def __init__(self, action_label: str, original_reason: str):
        super().__init__()
        self.action_label = action_label
        self.original_reason = original_reason

    appeal_statement = ui.TextInput(
        label="Reason for Appeal & Justification",
        style=discord.TextStyle.paragraph,
        placeholder="Explain why you believe this moderation action was issued in error or why it should be revoked...",
        min_length=20,
        max_length=1000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.client.get_guild(config.GUILD_ID)
        approvals_ch = None
        if guild:
            approvals_ch = guild.get_channel(config.APPROVALS_CHANNEL_ID) or guild.get_channel(config.MOD_LOGS_CHANNEL_ID)

        embed = discord.Embed(
            title=f"⚖️ Moderation Action Appeal Submitted",
            description=(
                f"**Appellant:** {interaction.user.mention} (`@{interaction.user.name}` | ID: `{interaction.user.id}`)\n"
                f"**Action Appealed:** `{self.action_label}`\n"
                f"**Original Reason:** {self.original_reason[:250]}\n"
                f"**Submitted At:** <t:{int(discord.utils.utcnow().timestamp())}:F>\n\n"
                f"### 📝 Appellant Statement\n"
                f"> {self.appeal_statement.value.strip()}"
            ),
            color=0x5865F2,
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Echo Technologies Moderation Appeals Division")

        if approvals_ch:
            view = ModAppealReviewView(appellant_id=interaction.user.id, action_label=self.action_label)
            await approvals_ch.send(embed=embed, view=view)
            await interaction.followup.send("✅ Your appeal has been successfully submitted to server staff for review.", ephemeral=True)
        else:
            await interaction.followup.send("✅ Your appeal was received. Staff will review it shortly.", ephemeral=True)


class ModAppealReviewView(ui.View):
    """Staff review controls for moderation appeals in approvals/mod-logs channel."""
    def __init__(self, appellant_id: Optional[int] = None, action_label: str = "Moderation Penalty"):
        super().__init__(timeout=None)
        self.appellant_id = appellant_id
        self.action_label = action_label

    @ui.button(label="✅ Approve & Revoke Penalty", style=discord.ButtonStyle.success, custom_id="mod_appeal_approve")
    async def approve_button(self, interaction: discord.Interaction, button: ui.Button):
        if not (interaction.user.guild_permissions.moderate_members or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("❌ You require moderator permissions to review appeals.", ephemeral=True)
            return

        for item in self.children:
            item.disabled = True
        
        embed = interaction.message.embeds[0]
        embed.color = 0x57F287
        embed.title = "✅ Moderation Action Appeal APPROVED"
        embed.add_field(name="Reviewed By", value=f"{interaction.user.mention} (`@{interaction.user.name}`)", inline=False)
        await interaction.message.edit(embed=embed, view=self)

        # Notify appellant in DM
        try:
            appellant = await interaction.client.fetch_user(self.appellant_id)
            if appellant:
                dm_embed = discord.Embed(
                    title="🎉 Moderation Appeal Approved!",
                    description=f"Your appeal regarding your **{self.action_label}** in **Echo Technologies** has been **APPROVED** by staff. The penalty has been revoked/expunged.",
                    color=0x57F287,
                    timestamp=discord.utils.utcnow()
                )
                await appellant.send(embed=dm_embed)
        except Exception:
            pass

        await interaction.response.send_message(f"✅ Appeal approved by {interaction.user.mention}.", ephemeral=True)

    @ui.button(label="❌ Reject Appeal", style=discord.ButtonStyle.danger, custom_id="mod_appeal_reject")
    async def reject_button(self, interaction: discord.Interaction, button: ui.Button):
        if not (interaction.user.guild_permissions.moderate_members or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("❌ You require moderator permissions to review appeals.", ephemeral=True)
            return

        for item in self.children:
            item.disabled = True
        
        embed = interaction.message.embeds[0]
        embed.color = 0xED4245
        embed.title = "❌ Moderation Action Appeal REJECTED"
        embed.add_field(name="Reviewed By", value=f"{interaction.user.mention} (`@{interaction.user.name}`)", inline=False)
        await interaction.message.edit(embed=embed, view=self)

        # Notify appellant in DM
        try:
            appellant = await interaction.client.fetch_user(self.appellant_id)
            if appellant:
                dm_embed = discord.Embed(
                    title="❌ Moderation Appeal Denied",
                    description=f"Your appeal regarding your **{self.action_label}** in **Echo Technologies** has been reviewed and **DENIED** by staff leadership.",
                    color=0xED4245,
                    timestamp=discord.utils.utcnow()
                )
                await appellant.send(embed=dm_embed)
        except Exception:
            pass

        await interaction.response.send_message(f"❌ Appeal rejected by {interaction.user.mention}.", ephemeral=True)


async def send_dm_infraction_notice(
    target: discord.User,
    action_label: str,
    reason: str,
    guild_name: str = "Echo Technologies",
    duration: Optional[str] = None
) -> bool:
    """Safely notifies a punished user in their Direct Messages with an Appeal button."""
    colors = {
        "Warned": 0xFEE75C,
        "Timed Out": 0xE67E22,
        "Kicked": 0xED4245,
        "Banned": 0x992D22,
        "Globally Banned": 0x000000,
        "Untimed Out": 0x57F287,
        "Unbanned": 0x57F287
    }
    embed = discord.Embed(
        title=f"⚖️ Mod Notice • You were {action_label}",
        description=(
            f"You have received a moderation action in **{guild_name}**.\n\n"
            f"**Action:** `{action_label}`\n"
            + (f"**Duration:** `{duration}`\n" if duration else "")
            + f"**Reason:**\n> {reason}\n\n"
            f"### 📜 Rights & Appeals\n"
            f"If you believe this action was issued in error, click the **Submit Appeal** button below to submit a formal appeal directly to server management."
        ),
        color=colors.get(action_label, 0xED4245),
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text=f"{guild_name} Security & Moderation Division")
    try:
        dm = await target.create_dm()
        view = InfractionAppealDMView(action_label=action_label, reason=reason)
        await dm.send(embed=embed, view=view)
        return True
    except Exception:
        return False


async def dispatch_mod_log(
    bot,
    guild: discord.Guild,
    action: str,
    target: discord.User,
    moderator: discord.User,
    reason: str,
    duration: Optional[str] = None,
    extra_field: Optional[Tuple[str, str]] = None
) -> Optional[int]:
    """
    Constructs and dispatches an official moderation log embed to config.MOD_LOGS_CHANNEL_ID (1556000170922221661).
    Returns the created case_id.
    """
    action_colors = {
        "warn": 0xFEE75C,         # Yellow
        "timeout": 0xE67E22,      # Orange
        "untimeout": 0x57F287,    # Green
        "kick": 0xED4245,         # Red
        "ban": 0x992D22,          # Dark Red
        "unban": 0x57F287,        # Green
        "global_ban": 0x1F1F1F,   # Obsidian Black / Crimson
        "global_unban": 0x57F287, # Green
        "lock": 0x5865F2,         # Blurple
        "unlock": 0x57F287,       # Green
        "slowmode": 0x3498DB,     # Blue
        "purge": 0x7289DA         # Blue-Grey
    }

    action_titles = {
        "warn": "⚠️ Member Warned",
        "timeout": "⏱️ Member Timed Out",
        "untimeout": "🔓 Member Timeout Removed",
        "kick": "🚪 Member Kicked",
        "ban": "🔨 Member Banned",
        "unban": "🔓 Member Unbanned",
        "global_ban": "🚨 GLOBAL BAN ENFORCED",
        "global_unban": "🌐 Global Ban Revoked",
        "lock": "🔒 Channel Locked",
        "unlock": "🔓 Channel Unlocked",
        "slowmode": "⏲️ Slowmode Configured",
        "purge": "🧹 Messages Purged"
    }

    color = action_colors.get(action.lower(), 0x5865F2)
    title = action_titles.get(action.lower(), f"🛡️ Action: {action.title()}")

    target_id = target.id if hasattr(target, "id") else 0
    target_name = target.name if hasattr(target, "name") else str(target)
    mod_id = moderator.id if hasattr(moderator, "id") else 0
    mod_name = moderator.name if hasattr(moderator, "name") else str(moderator)

    # 1. Register case in DB
    case_id = create_mod_case(
        guild_id=guild.id if guild else config.GUILD_ID,
        target_id=target_id,
        target_name=target_name,
        moderator_id=mod_id,
        moderator_name=mod_name,
        action=action,
        reason=reason,
        duration=duration
    )

    # 2. Check for linked Roblox account in verification database
    roblox_field = "❌ *Not Linked / Unverified*"
    roblox_avatar = None
    if target_id and hasattr(bot, "db"):
        try:
            rbx = bot.db.get_by_discord_id(target_id)
            if rbx:
                rbx_id = rbx["roblox_id"]
                rbx_tag = f"**{rbx['roblox_display_name']}** (`@{rbx['roblox_username']}`)"
                rbx_link = f"[Profile #{rbx_id}](https://www.roblox.com/users/{rbx_id}/profile)"
                roblox_field = f"{rbx_tag}\n{rbx_link} • ✅ **Verified**"
                if hasattr(bot, "roblox_api"):
                    roblox_avatar = await bot.roblox_api.get_user_headshot(rbx_id)
        except Exception as e:
            logger.warning(f"Error checking Roblox link for {target_id}: {e}")

    # 3. Build Embed
    embed = discord.Embed(
        title=f"{title} • Case #{case_id}",
        color=color,
        timestamp=discord.utils.utcnow()
    )

    target_mention = f"<@{target_id}>" if target_id else target_name
    embed.add_field(name="👤 Target Member", value=f"{target_mention}\n`{target_name}` (`{target_id}`)", inline=True)

    mod_mention = f"<@{mod_id}>" if mod_id else mod_name
    embed.add_field(name="🛡️ Moderator", value=f"{mod_mention}\n`{mod_name}`", inline=True)

    if duration:
        embed.add_field(name="⏱️ Duration", value=f"`{duration}`", inline=True)

    embed.add_field(name="🎮 Linked Roblox Account", value=roblox_field, inline=True)
    embed.add_field(name="📝 Reason", value=f"> {reason}", inline=False)

    if extra_field:
        embed.add_field(name=extra_field[0], value=extra_field[1], inline=False)

    # Thumbnail priority: Discord avatar, then Roblox avatar
    if hasattr(target, "display_avatar") and target.display_avatar:
        embed.set_thumbnail(url=target.display_avatar.url)
    elif roblox_avatar:
        embed.set_thumbnail(url=roblox_avatar)

    embed.set_footer(text=f"Echo Technologies Security Audit • Case #{case_id}")

    # 4. Dispatch to Log Channel (config.MOD_LOGS_CHANNEL_ID: 1556000170922221661)
    ch_id = config.MOD_LOGS_CHANNEL_ID
    log_ch = guild.get_channel(ch_id) if guild else None
    if not log_ch:
        log_ch = bot.get_channel(ch_id)
    if not log_ch:
        try:
            log_ch = await bot.fetch_channel(ch_id)
        except Exception as e:
            logger.warning(f"Could not fetch mod log channel {ch_id}: {e}")
            log_ch = None

    if log_ch and isinstance(log_ch, discord.TextChannel):
        try:
            msg = await log_ch.send(embed=embed)
            set_case_log_message_id(case_id, msg.id)
            logger.info(f"Mod Case #{case_id} logged to #{log_ch.name}")
        except Exception as e:
            logger.error(f"Failed to send mod log to #{log_ch.name}: {e}")

    return case_id


# --- GLOBAL BAN EXECUTORS ---

async def execute_global_ban(
    bot,
    user_id: int,
    reason: str,
    moderator: discord.User
) -> Tuple[int, List[str], int]:
    """
    Bans a user from ALL servers the bot resides in and permanently registers in global_bans.
    Returns: (successful_guilds_count, failed_guild_names, case_id)
    """
    target = bot.get_user(user_id)
    if not target:
        try:
            target = await bot.fetch_user(user_id)
        except Exception:
            target = discord.Object(id=user_id)

    mod_name = moderator.name if hasattr(moderator, "name") else str(moderator)
    add_global_ban(user_id, reason, moderator.id, mod_name)

    # Send DM notice if target is User
    if isinstance(target, discord.User):
        await send_dm_infraction_notice(
            target=target,
            action_label="Globally Banned",
            reason=reason,
            guild_name="Echo Technologies Network"
        )

    success_count = 0
    failed_guilds = []

    for g in bot.guilds:
        try:
            await g.ban(
                discord.Object(id=user_id),
                reason=f"[GLOBAL BAN by {mod_name}]: {reason}",
                delete_message_days=1
            )
            success_count += 1
        except Exception as e:
            logger.warning(f"Could not global-ban {user_id} in guild {g.name}: {e}")
            failed_guilds.append(g.name)

    primary_guild = bot.get_primary_guild() or (bot.guilds[0] if bot.guilds else None)
    case_id = await dispatch_mod_log(
        bot=bot,
        guild=primary_guild,
        action="global_ban",
        target=target,
        moderator=moderator,
        reason=reason,
        extra_field=("🌐 Global Enforcement", f"Banned across **{success_count} / {len(bot.guilds)}** servers.\nAuto-enforced on future joins: ✅ **Active**")
    )

    return success_count, failed_guilds, case_id


async def execute_global_unban(
    bot,
    user_id: int,
    reason: str,
    moderator: discord.User
) -> Tuple[int, List[str], int]:
    """
    Removes user from global_bans and unbans them across all servers.
    Returns: (successful_guilds_count, failed_guild_names, case_id)
    """
    target = bot.get_user(user_id)
    if not target:
        try:
            target = await bot.fetch_user(user_id)
        except Exception:
            target = discord.Object(id=user_id)

    remove_global_ban(user_id)

    success_count = 0
    failed_guilds = []

    for g in bot.guilds:
        try:
            await g.unban(discord.Object(id=user_id), reason=f"[GLOBAL UNBAN by {moderator.name}]: {reason}")
            success_count += 1
        except Exception as e:
            failed_guilds.append(g.name)

    primary_guild = bot.get_primary_guild() or (bot.guilds[0] if bot.guilds else None)
    case_id = await dispatch_mod_log(
        bot=bot,
        guild=primary_guild,
        action="global_unban",
        target=target,
        moderator=moderator,
        reason=reason,
        extra_field=("🌐 Global Status", f"Unbanned across **{success_count} / {len(bot.guilds)}** servers.\nRemoved from global security blacklist.")
    )

    return success_count, failed_guilds, case_id


def clear_all_moderation_logs() -> int:
    """Wipes all moderation and HR database tables clean."""
    tables = ['mod_cases', 'warnings', 'global_bans', 'staff_strikes', 'staff_suspensions', 'hr_watchlist', 'staff_blacklists', 'strike_appeals']
    deleted_count = 0
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for table in tables:
            cursor.execute(f"DELETE FROM {table};")
            deleted_count += cursor.rowcount
        conn.commit()
    return deleted_count

