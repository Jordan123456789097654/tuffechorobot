import discord
from discord import ui, app_commands
import sqlite3
import json
import re
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
import config
from points_system import get_user_points

logger = logging.getLogger("HRSystem")
DB_PATH = "verifications.db"

def init_hr_db():
    """Initializes tables for staff strikes, suspensions, watchlist, blacklists, and appeals."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        # 1. Staff Strikes Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS staff_strikes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_id INTEGER NOT NULL,
                issuer_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                severity INTEGER DEFAULT 1, -- 1: Warning, 2: Moderate Strike, 3: Critical Strike
                active INTEGER DEFAULT 1,
                pardon_reason TEXT,
                pardoned_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                pardoned_at TIMESTAMP
            );
        """)

        # Migrate staff_strikes columns if missing
        cursor.execute("PRAGMA table_info(staff_strikes);")
        existing_cols = [row[1] for row in cursor.fetchall()]
        if "expires_at" not in existing_cols:
            try:
                cursor.execute("ALTER TABLE staff_strikes ADD COLUMN expires_at TIMESTAMP;")
            except Exception as e:
                logger.warning(f"Could not add expires_at column: {e}")

        # 2. Staff Suspensions Table (#5)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS staff_suspensions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_id INTEGER NOT NULL,
                issuer_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                roles_json TEXT NOT NULL, -- JSON array of stripped role IDs
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP NOT NULL,
                active INTEGER DEFAULT 1,
                unsuspended_by INTEGER DEFAULT NULL,
                unsuspend_reason TEXT DEFAULT NULL,
                unsuspended_at TIMESTAMP DEFAULT NULL
            );
        """)

        # 3. HR Watchlist Table (#6)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hr_watchlist (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER NOT NULL,
                reason TEXT NOT NULL,
                sensitivity TEXT DEFAULT 'medium', -- 'low', 'medium', 'high'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 4. Staff Blacklists Table (#7)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS staff_blacklists (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 5. Strike Appeals Table (#2)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strike_appeals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strike_id INTEGER NOT NULL,
                staff_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'denied'
                reviewer_id INTEGER DEFAULT NULL,
                review_reason TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TIMESTAMP DEFAULT NULL
            );
        """)

        conn.commit()

init_hr_db()


# ==========================================
# 🛑 STRIKES & PROGRESSIVE DISCIPLINE (#1)
# ==========================================

def add_strike(staff_id: int, issuer_id: int, guild_id: int, reason: str, severity: int = 1, expire_days: int = 30) -> int:
    """Records an HR infraction/strike against a staff member with a 30-day auto-decay timer."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=expire_days)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO staff_strikes (staff_id, issuer_id, guild_id, reason, severity, active, expires_at)
            VALUES (?, ?, ?, ?, ?, 1, ?);
        """, (staff_id, issuer_id, guild_id, reason, severity, expires_at.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        return cursor.lastrowid

def get_staff_strikes(staff_id: int, active_only: bool = False) -> List[Dict[str, Any]]:
    """Retrieves all strikes for a staff member."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if active_only:
            cursor.execute("SELECT * FROM staff_strikes WHERE staff_id = ? AND active = 1 ORDER BY id DESC;", (staff_id,))
        else:
            cursor.execute("SELECT * FROM staff_strikes WHERE staff_id = ? ORDER BY id DESC;", (staff_id,))
        return [dict(row) for row in cursor.fetchall()]

def get_strike(strike_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves a single strike record."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM staff_strikes WHERE id = ?;", (strike_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def pardon_strike(strike_id: int, pardoned_by: int, reason: str) -> bool:
    """Pardons/expunges an active strike."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE staff_strikes
            SET active = 0, pardoned_by = ?, pardon_reason = ?, pardoned_at = CURRENT_TIMESTAMP
            WHERE id = ? AND active = 1;
        """, (pardoned_by, reason, strike_id))
        conn.commit()
        return cursor.rowcount > 0

def check_strike_expiration() -> int:
    """(#3) Deactivates active strikes that have passed their 30-day expiration date."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE staff_strikes
            SET active = 0, pardon_reason = 'Auto-expired after 30 days clean conduct decay'
            WHERE active = 1 AND expires_at IS NOT NULL AND expires_at <= ?;
        """, (now_str,))
        conn.commit()
        return cursor.rowcount

async def evaluate_strike_escalation(bot, guild: discord.Guild, staff_member: discord.Member, issuer: discord.User, new_strike_id: int) -> Tuple[str, Optional[discord.Embed]]:
    """
    (#1) Progressive Discipline Escalator:
    - 2 Active Strikes: Automatic 3-Day Suspension.
    - 3+ Active Strikes: Automatic Demotion Alert & Staff Permission Stripping.
    """
    active_strikes = get_staff_strikes(staff_member.id, active_only=True)
    count = len(active_strikes)

    if count == 2:
        # Escalation 1: 3-Day Suspension
        success, msg = await suspend_staff_member(
            bot=bot,
            guild=guild,
            staff_member=staff_member,
            issuer=issuer,
            reason=f"Automated Progressive Discipline Escalation (Accumulated {count} active strikes).",
            duration_days=3
        )
        embed = discord.Embed(
            title="⚡ HR Progressive Discipline Escalation: 3-Day Suspension",
            description=(
                f"**Staff Member:** {staff_member.mention} (`@{staff_member.name}`)\n"
                f"**Infraction Threshold Reached:** `{count}` Active Strikes\n"
                f"**Action Taken:** Staff member suspended for **3 Days**. All staff roles temporarily removed.\n\n"
                f"*{msg}*"
            ),
            color=0xE67E22,
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text="Echo Technologies HR Automated Escalation")
        return "SUSPENDED_3D", embed

    elif count >= 3:
        # Escalation 2: Demotion Alert & Role Stripping
        staff_roles = [
            config.SUPPORT_TEAM_ROLE_ID,
            config.DEVELOPMENT_TEAM_ROLE_ID,
            config.PUBLIC_RELATIONS_ROLE_ID
        ]
        removed = []
        for rid in staff_roles:
            role = guild.get_role(rid)
            if role and role in staff_member.roles:
                try:
                    await staff_member.remove_roles(role, reason=f"Automated HR Demotion (Accumulated {count} active strikes).")
                    removed.append(role.name)
                except Exception as e:
                    logger.warning(f"Could not remove role {role.name} during demotion: {e}")

        embed = discord.Embed(
            title="🚨 CRITICAL HR ESCALATION: AUTOMATED DEMOTION WARNING",
            description=(
                f"**Staff Member:** {staff_member.mention} (`@{staff_member.name}` | `{staff_member.id}`)\n"
                f"**Critical Threshold Reached:** `{count}` Active Infractions!\n\n"
                f"**Automated System Actions Executed:**\n"
                f"• Stripped Staff Roles: {', '.join([f'`{r}`' for r in removed]) if removed else 'None'}\n"
                f"• Disciplinary Ticket Flagged for Executive Leadership Review.\n\n"
                f"⚠️ **Leadership Action Required:** Senior Management must inspect this member's dossier and execute formal dishonorable discharge if appropriate."
            ),
            color=0xED4245,
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=staff_member.display_avatar.url)
        embed.set_footer(text="Echo Technologies Executive HR Security Notice")
        return "CRITICAL_DEMOTION", embed

    return "NORMAL", None


# ==========================================
# ⏸️ STAFF SUSPENSION MANAGER (#5)
# ==========================================

async def suspend_staff_member(
    bot,
    guild: discord.Guild,
    staff_member: discord.Member,
    issuer: discord.User,
    reason: str,
    duration_days: int = 3
) -> Tuple[bool, str]:
    """Suspends a staff member, stripping staff roles and storing them for restoration."""
    staff_roles = [
        config.SUPPORT_TEAM_ROLE_ID,
        config.DEVELOPMENT_TEAM_ROLE_ID,
        config.PUBLIC_RELATIONS_ROLE_ID,
        config.PARTNER_REP_ROLE_ID
    ]
    to_strip = [r.id for r in staff_member.roles if r.id in staff_roles]

    # Strip roles
    for rid in to_strip:
        role = guild.get_role(rid)
        if role:
            try:
                await staff_member.remove_roles(role, reason=f"HR Suspension issued by {issuer}: {reason}")
            except Exception as e:
                logger.warning(f"Failed to strip role {rid} from {staff_member.id}: {e}")

    end_time = datetime.now(timezone.utc) + timedelta(days=duration_days)
    roles_json = json.dumps(to_strip)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Deactivate any previous active suspensions
        cursor.execute("UPDATE staff_suspensions SET active = 0 WHERE staff_id = ? AND active = 1;", (staff_member.id,))
        cursor.execute("""
            INSERT INTO staff_suspensions (staff_id, issuer_id, guild_id, reason, roles_json, end_time, active)
            VALUES (?, ?, ?, ?, ?, ?, 1);
        """, (staff_member.id, issuer.id, guild.id, reason, roles_json, end_time.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()

    return True, f"Suspended {staff_member.mention} for **{duration_days} days**. Stripped `{len(to_strip)}` staff roles."

async def unsuspend_staff_member(
    bot,
    guild: discord.Guild,
    staff_member: discord.Member,
    unsuspended_by: discord.User,
    reason: str = "Suspension completed / Manual Unsuspension"
) -> Tuple[bool, str]:
    """Restores saved staff roles and clears active suspension record."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM staff_suspensions WHERE staff_id = ? AND active = 1;", (staff_member.id,))
        row = cursor.fetchone()
        if not row:
            return False, f"Member {staff_member.mention} has no active suspension."

        roles_to_restore = json.loads(row["roles_json"])
        cursor.execute("""
            UPDATE staff_suspensions
            SET active = 0, unsuspended_by = ?, unsuspend_reason = ?, unsuspended_at = CURRENT_TIMESTAMP
            WHERE id = ?;
        """, (unsuspended_by.id, reason, row["id"]))
        conn.commit()

    # Restore roles
    restored_names = []
    for rid in roles_to_restore:
        role = guild.get_role(rid)
        if role:
            try:
                await staff_member.add_roles(role, reason=f"Restored from HR suspension: {reason}")
                restored_names.append(role.name)
            except Exception as e:
                logger.warning(f"Could not restore role {rid} to {staff_member.id}: {e}")

    return True, f"Unsuspended {staff_member.mention}. Restored roles: {', '.join([f'`{r}`' for r in restored_names]) or 'None'}."

def get_active_suspension(staff_id: int) -> Optional[Dict[str, Any]]:
    """Checks if a staff member is currently under active suspension."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM staff_suspensions WHERE staff_id = ? AND active = 1;", (staff_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

async def check_expired_suspensions(bot):
    """Background check for ended suspensions to automatically restore roles."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    expired = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM staff_suspensions WHERE active = 1 AND end_time <= ?;", (now_str,))
        expired = [dict(r) for r in cursor.fetchall()]

    for rec in expired:
        guild = bot.get_guild(rec["guild_id"])
        if guild:
            member = guild.get_member(rec["staff_id"])
            if member:
                await unsuspend_staff_member(
                    bot=bot,
                    guild=guild,
                    staff_member=member,
                    unsuspended_by=bot.user,
                    reason="Automated Suspension Expiration Timer"
                )
                # Send DM notice
                try:
                    embed = discord.Embed(
                        title="✅ Echo Technologies • HR Suspension Lifted",
                        description=(
                            f"Hello **{member.display_name}**,\n\n"
                            f"Your temporary HR suspension has expired. Your staff roles and access have been automatically restored.\n"
                            f"Please maintain full compliance with Echo Technologies staff guidelines going forward."
                        ),
                        color=0x57F287
                    )
                    await member.send(embed=embed)
                except Exception:
                    pass


# ==========================================
# 👁️ HR WATCHLIST & AI SENSITIVITY ANALYZER (#6)
# ==========================================

def add_watchlist_user(user_id: int, added_by: int, reason: str, sensitivity: str = "medium") -> bool:
    """Adds a user or staff member to the active HR Watchlist."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO hr_watchlist (user_id, added_by, reason, sensitivity)
            VALUES (?, ?, ?, ?);
        """, (user_id, added_by, reason, sensitivity))
        conn.commit()
        return True

def remove_watchlist_user(user_id: int) -> bool:
    """Removes a user from the HR Watchlist."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM hr_watchlist WHERE user_id = ?;", (user_id,))
        conn.commit()
        return cursor.rowcount > 0

def is_watchlisted(user_id: int) -> Optional[Dict[str, Any]]:
    """Checks if a user is currently on the HR Watchlist."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hr_watchlist WHERE user_id = ?;", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_watchlist() -> List[Dict[str, Any]]:
    """Retrieves all watchlisted users."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hr_watchlist ORDER BY created_at DESC;")
        return [dict(r) for r in cursor.fetchall()]

async def evaluate_watchlist_message(bot, message: discord.Message):
    """
    (#6) Analyzes messages sent by watchlisted users or staff members using Groq AI.
    Flags unprofessionalism, leaks, toxicity, hostility, or staff policy breaches.
    """
    if message.author.bot or not message.guild or not message.content:
        return

    # Check if author is watchlisted OR has a staff role
    entry = is_watchlisted(message.author.id)
    is_staff = any(r.id in [config.SUPPORT_TEAM_ROLE_ID, config.DEVELOPMENT_TEAM_ROLE_ID, config.PUBLIC_RELATIONS_ROLE_ID] for r in getattr(message.author, "roles", []))

    if not entry and not is_staff:
        return

    # If it's a staff member or watchlisted user, evaluate message content
    groq_assistant = getattr(bot, "groq_assistant", None)
    if not groq_assistant or not groq_assistant.client:
        return

    prompt = (
        f"You are an expert HR Security Auditor for Echo Technologies Roblox tech studio.\n"
        f"Analyze this chat message sent by a {'watchlisted member' if entry else 'staff member'} for policy breaches, toxicity, leak attempts, staff unprofessionalism, or hostility.\n"
        f"User: @{message.author.name} (ID: {message.author.id})\n"
        f"Channel: #{message.channel.name}\n"
        f"Message Content: \"{message.content}\"\n\n"
        f"Respond in EXACT JSON format:\n"
        f"{{\n"
        f"  \"flagged\": true/false,\n"
        f"  \"risk_score\": 0.0 to 1.0,\n"
        f"  \"category\": \"Toxicity/Unprofessionalism/Leak/Hostility/Safe\",\n"
        f"  \"reason\": \"Short explanation of why it was flagged or safe\"\n"
        f"}}"
    )

    try:
        response = await groq_assistant.client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=200
        )
        raw_text = response.choices[0].message.content.strip()

        # Extract JSON block
        if "{" in raw_text and "}" in raw_text:
            json_str = raw_text[raw_text.find("{"):raw_text.rfind("}")+1]
            data = json.loads(json_str)

            risk_score = float(data.get("risk_score", 0.0))
            if data.get("flagged") and risk_score >= 0.65:
                # 1. Automated Message Deletion
                msg_deleted = False
                try:
                    await message.delete()
                    msg_deleted = True
                except Exception as e:
                    logger.warning(f"Could not auto-delete flagged message: {e}")

                # 2. Automated HR Infraction / Strike Logging
                severity = 3 if risk_score >= 0.90 else (2 if risk_score >= 0.75 else 1)
                reason_str = f"Automated AI Sentinel Enforcement ({data.get('category')}): {data.get('reason')}"
                strike_id = add_strike(
                    staff_id=message.author.id,
                    issuer_id=bot.user.id,
                    guild_id=message.guild.id,
                    reason=reason_str,
                    severity=severity
                )

                # 3. Progressive Discipline Escalation & Automated Termination Check
                escalation_code = "NORMAL"
                is_terminated = False
                is_banned = False

                if isinstance(message.author, discord.Member):
                    if risk_score >= 0.92:
                        is_terminated = True
                        escalation_code = "🔴 AUTOMATED STAFF TERMINATION"

                        # A. Permanently Strip All Staff Roles
                        staff_roles = [
                            config.SUPPORT_TEAM_ROLE_ID,
                            config.DEVELOPMENT_TEAM_ROLE_ID,
                            config.PUBLIC_RELATIONS_ROLE_ID,
                            config.PARTNER_REP_ROLE_ID
                        ]
                        for rid in staff_roles:
                            role = message.guild.get_role(rid)
                            if role and role in message.author.roles:
                                try:
                                    await message.author.remove_roles(role, reason=f"Automated AI HR Termination ({data.get('category')}): {data.get('reason')}")
                                except Exception as e:
                                    logger.warning(f"Could not strip role {rid} during termination: {e}")

                        # B. Add to Recruitment Blacklist (Dishonorable Discharge)
                        add_staff_blacklist(
                            user_id=message.author.id,
                            added_by=bot.user.id,
                            reason=f"Automated AI HR Sentinel Termination: {data.get('category')} - {data.get('reason')}"
                        )

                        # C. Automated Server Ban for Critical Violations (risk_score >= 0.95)
                        if risk_score >= 0.95:
                            try:
                                await message.guild.ban(message.author, reason=f"Automated AI Sentinel Security Ban: {data.get('reason')}")
                                is_banned = True
                                escalation_code = "🔴 AUTOMATED TERMINATION & GUILD BAN"
                            except Exception as e:
                                logger.warning(f"Could not ban user during termination: {e}")
                    else:
                        escalation_code, _ = await evaluate_strike_escalation(
                            bot=bot,
                            guild=message.guild,
                            staff_member=message.author,
                            issuer=bot.user,
                            new_strike_id=strike_id
                        )

                # 4. DM Direct Infraction / Termination Notice to Offender
                dm_delivered = False
                try:
                    dm = await message.author.create_dm()
                    if is_terminated:
                        dm_embed = discord.Embed(
                            title="🚨 ECHO TECHNOLOGIES • NOTICE OF STAFF TERMINATION & DISHONORABLE DISCHARGE",
                            description=(
                                f"Dear **{message.author.display_name}**,\n\n"
                                f"This notice serves as official confirmation that your staff status with **Echo Technologies** has been **TERMINATED** effective immediately.\n\n"
                                f"### 📋 Termination Summary\n"
                                f"• **Flagged Violation:** `{data.get('category', 'Critical Misconduct')}`\n"
                                f"• **AI Risk Score:** `{risk_score:.2f}` / 1.00\n"
                                f"• **Reason:** {data.get('reason')}\n"
                                f"• **Enforcement Actions:** All staff roles stripped & permanent recruitment blacklist applied.\n"
                                f"• **Guild Status:** {'🔨 Server Ban Executed' if is_banned else '⚠️ Staff Access Revoked'}\n\n"
                                f"Echo Technologies maintains zero tolerance for severe policy violations."
                            ),
                            color=0xED4245,
                            timestamp=discord.utils.utcnow()
                        )
                    else:
                        dm_embed = discord.Embed(
                            title="🚨 Echo Technologies • Automated HR Security Enforcement",
                            description=(
                                f"Hello **{message.author.display_name}**,\n\n"
                                f"Your message in {message.channel.mention} was automatically removed by the **Echo Technologies Real-Time HR AI Sentinel**.\n\n"
                                f"### 📋 Enforcement Summary\n"
                                f"• **Flagged Category:** `{data.get('category', 'Unprofessionalism')}`\n"
                                f"• **AI Risk Score:** `{risk_score:.2f}` / 1.00\n"
                                f"• **Diagnostic Reason:** {data.get('reason')}\n"
                                f"• **Recorded HR Strike:** `Record #{strike_id}` ({format_severity(severity)})\n"
                                f"• **Message Status:** {'🗑️ Deleted from Channel' if msg_deleted else '⚠️ Deletion Failed'}\n\n"
                                f"Please maintain full compliance with Echo Technologies professionalism standards."
                            ),
                            color=0xED4245,
                            timestamp=discord.utils.utcnow()
                        )
                    await dm.send(embed=dm_embed)
                    dm_delivered = True
                except Exception:
                    pass

                # 5. Dispatch Real-Time Audit Log Embed to #hr-logs / #discord-updates
                hr_channel = message.guild.get_channel(config.HR_LOGS_CHANNEL_ID) or message.guild.get_channel(config.MOD_LOGS_CHANNEL_ID)
                if hr_channel:
                    embed_title = "🚨 CRITICAL HR SECURITY: AUTOMATED USER TERMINATION EXECUTED" if is_terminated else "⚡ HR AI Sentinel: Automated Security Action Executed"
                    embed = discord.Embed(
                        title=embed_title,
                        description=(
                            f"**Author:** {message.author.mention} (`@{message.author.name}` | `{message.author.id}`)\n"
                            f"**Status:** `{'👁️ Watchlisted User' if entry else '🛡️ Staff Member'}`\n"
                            f"**Channel:** {message.channel.mention}\n\n"
                            f"### 🔍 AI Diagnostics\n"
                            f"• **Risk Score:** `{risk_score:.2f}` / 1.00\n"
                            f"• **Category:** `{data.get('category', 'Unprofessionalism')}`\n"
                            f"• **Reason:** {data.get('reason')}\n\n"
                            f"### ⚡ Automated Actions Executed\n"
                            f"• **Message Deletion:** {'🗑️ Message Deleted' if msg_deleted else '⚠️ Deletion Failed'}\n"
                            f"• **HR Strike Logged:** `Record #{strike_id}` ({format_severity(severity)})\n"
                            f"• **Recruitment Blacklist:** {'🚫 Added to Blacklist' if is_terminated else 'N/A'}\n"
                            f"• **DM Warning Notice:** {'📨 Delivered' if dm_delivered else '⚠️ DM Failed'}\n"
                            f"• **Enforcement Status:** `{escalation_code}`\n\n"
                            f"### 💬 Content Processed\n"
                            f"> {message.content[:1024]}"
                        ),
                        color=0xED4245 if is_terminated else 0xE67E22,
                        timestamp=discord.utils.utcnow()
                    )
                    embed.set_thumbnail(url=message.author.display_avatar.url)
                    embed.set_footer(text="Echo Technologies Real-Time Automated HR Enforcement System")
                    await hr_channel.send(embed=embed)
    except Exception as e:
        logger.debug(f"AI Watchlist Evaluation error: {e}")


# ==========================================
# 🚫 DISHONORABLE DISCHARGE & BLACKLIST (#7)
# ==========================================

def add_staff_blacklist(user_id: int, added_by: int, reason: str) -> bool:
    """Adds a former staff member to the recruitment blacklist."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO staff_blacklists (user_id, added_by, reason)
            VALUES (?, ?, ?);
        """, (user_id, added_by, reason))
        conn.commit()
        return True

def remove_staff_blacklist(user_id: int) -> bool:
    """Removes a user from the recruitment blacklist."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM staff_blacklists WHERE user_id = ?;", (user_id,))
        conn.commit()
        return cursor.rowcount > 0

def is_staff_blacklisted(user_id: int) -> Optional[Dict[str, Any]]:
    """Checks if a user is blacklisted from applying for staff positions."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM staff_blacklists WHERE user_id = ?;", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_staff_blacklists() -> List[Dict[str, Any]]:
    """Retrieves all blacklisted former staff members."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM staff_blacklists ORDER BY created_at DESC;")
        return [dict(r) for r in cursor.fetchall()]


# ==========================================
# 📜 DISCIPLINARY APPEALS SYSTEM (#2)
# ==========================================

def create_strike_appeal(strike_id: int, staff_id: int, reason: str) -> Tuple[bool, str, Optional[int]]:
    """Submits a formal strike appeal."""
    strike = get_strike(strike_id)
    if not strike:
        return False, f"❌ Strike record `#{strike_id}` does not exist.", None
    if strike["staff_id"] != staff_id:
        return False, "❌ You can only appeal strikes issued against your own account.", None
    if not strike["active"]:
        return False, "❌ This strike is already pardoned or expired.", None

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM strike_appeals WHERE strike_id = ? AND status = 'pending';", (strike_id,))
        if cursor.fetchone():
            return False, "❌ An appeal for this strike is already pending review.", None

        cursor.execute("""
            INSERT INTO strike_appeals (strike_id, staff_id, reason, status)
            VALUES (?, ?, ?, 'pending');
        """, (strike_id, staff_id, reason))
        conn.commit()
        return True, f"✅ Appeal for Strike `#{strike_id}` successfully submitted!", cursor.lastrowid

def get_strike_appeal(appeal_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves an appeal record."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM strike_appeals WHERE id = ?;", (appeal_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def review_strike_appeal(appeal_id: int, reviewer_id: int, status: str, review_reason: str) -> bool:
    """Updates appeal status and pardons strike if approved."""
    appeal = get_strike_appeal(appeal_id)
    if not appeal or appeal["status"] != "pending":
        return False

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE strike_appeals
            SET status = ?, reviewer_id = ?, review_reason = ?, reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?;
        """, (status, reviewer_id, review_reason, appeal_id))
        conn.commit()

    if status == "approved":
        pardon_strike(appeal["strike_id"], pardoned_by=reviewer_id, reason=f"Appeal Approved (#{appeal_id}): {review_reason}")

    return True


class StrikeAppealModal(ui.Modal, title="📜 Submit HR Strike Appeal"):
    strike_id = ui.TextInput(label="Strike Record ID", placeholder="e.g. 5", min_length=1, max_length=10)
    appeal_reason = ui.TextInput(label="Reason & Justification for Appeal", style=discord.TextStyle.paragraph, placeholder="Explain why this strike should be expunged...", min_length=20, max_length=1000)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            sid = int(self.strike_id.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ Invalid Strike Record ID. Must be a number.", ephemeral=True)
            return

        success, msg, appeal_id = create_strike_appeal(sid, interaction.user.id, self.appeal_reason.value.strip())
        if not success:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        # Send Appeal dossier embed to #hr-logs
        hr_ch = interaction.guild.get_channel(config.HR_LOGS_CHANNEL_ID) or interaction.guild.get_channel(config.MOD_LOGS_CHANNEL_ID)
        if hr_ch:
            embed = discord.Embed(
                title=f"📜 HR Disciplinary Appeal Submitted (#{appeal_id})",
                description=(
                    f"**Appellant:** {interaction.user.mention} (`@{interaction.user.name}` | `{interaction.user.id}`)\n"
                    f"**Target Strike ID:** `#{sid}`\n"
                    f"**Submitted:** <t:{int(discord.utils.utcnow().timestamp())}:F>\n\n"
                    f"### 📝 Appeal Statement\n"
                    f"> {self.appeal_reason.value.strip()}\n\n"
                    f"HR Leadership can review and decide using the controls below."
                ),
                color=0x5865F2,
                timestamp=discord.utils.utcnow()
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            view = HRAppealControlView(appeal_id)
            await hr_ch.send(embed=embed, view=view)

        await interaction.response.send_message(f"✅ Your appeal for Strike `#{sid}` has been lodged. HR Leadership will review it shortly.", ephemeral=True)


class HRAppealControlView(ui.View):
    def __init__(self, appeal_id: int):
        super().__init__(timeout=None)
        self.appeal_id = appeal_id

    @ui.button(label="✅ Approve & Expunge Strike", style=discord.ButtonStyle.success, custom_id="hr_appeal_approve")
    async def approve_button(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ HR Leadership permission required.", ephemeral=True)
            return

        success = review_strike_appeal(self.appeal_id, interaction.user.id, "approved", "Approved by HR Leadership")
        if success:
            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)
            await interaction.response.send_message(f"✅ Appeal `#{self.appeal_id}` APPROVED! Strike has been pardoned and active points updated.", ephemeral=False)
        else:
            await interaction.response.send_message("❌ Appeal already processed.", ephemeral=True)

    @ui.button(label="❌ Deny Appeal", style=discord.ButtonStyle.danger, custom_id="hr_appeal_deny")
    async def deny_button(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ HR Leadership permission required.", ephemeral=True)
            return

        success = review_strike_appeal(self.appeal_id, interaction.user.id, "denied", "Denied by HR Leadership")
        if success:
            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)
            await interaction.response.send_message(f"❌ Appeal `#{self.appeal_id}` DENIED.", ephemeral=False)
        else:
            await interaction.response.send_message("❌ Appeal already processed.", ephemeral=True)


# ==========================================
# 📊 STAFF DOSSIER GENERATOR (#4)
# ==========================================

def format_severity(severity: int) -> str:
    """Returns visual badge representation for severity level."""
    if severity == 1:
        return "🟡 Tier 1: Warning"
    elif severity == 2:
        return "🟠 Tier 2: Formal Strike"
    elif severity == 3:
        return "🔴 Tier 3: Critical Infraction"
    return f"Tier {severity}"

def build_staff_dossier_embed(staff_member: discord.Member, issuer: discord.User) -> discord.Embed:
    """(#4) Generates a comprehensive 360-degree HR dossier for any staff member."""
    strikes = get_staff_strikes(staff_member.id, active_only=False)
    active_strikes = [s for s in strikes if s["active"]]
    pardoned_strikes = [s for s in strikes if not s["active"]]

    suspension = get_active_suspension(staff_member.id)
    watchlist_entry = is_watchlisted(staff_member.id)
    blacklist_entry = is_staff_blacklisted(staff_member.id)
    points_info = get_user_points(staff_member.id)

    # Color & status calculation
    if blacklist_entry:
        status_str = "🔴 DISHONORABLY DISCHARGED & BLACKLISTED"
        color = 0x992D22
    elif suspension:
        status_str = f"🟠 SUSPENDED until `{suspension['end_time']}`"
        color = 0xE67E22
    elif len(active_strikes) >= 3:
        status_str = "🔴 CRITICAL CONDUCT WARNING (Demotion Flagged)"
        color = 0xED4245
    elif len(active_strikes) > 0:
        status_str = f"🟡 ACTIVE INFRACTIONS (`{len(active_strikes)}` Active)"
        color = 0xFEE75C
    else:
        status_str = "🟢 IN GOOD STANDING (Clean Conduct)"
        color = 0x57F287

    embed = discord.Embed(
        title=f"📊 Echo Technologies • HR Staff Dossier",
        description=(
            f"# Confidential Staff File\n"
            f"**Subject:** {staff_member.mention} (`@{staff_member.name}` | ID: `{staff_member.id}`)\n"
            f"**Current HR Status:** {status_str}\n"
            f"**Joined Server:** <t:{int(staff_member.joined_at.timestamp())}:R>\n"
            f"**Requested By:** {issuer.mention}\n"
        ),
        color=color,
        timestamp=discord.utils.utcnow()
    )
    embed.set_thumbnail(url=staff_member.display_avatar.url)

    # Roles Summary
    roles_str = ", ".join([r.mention for r in staff_member.roles if r.name != "@everyone"][:8]) or "None"
    embed.add_field(name="🛡️ Assigned Roles", value=roles_str, inline=False)

    # Disciplinary Statistics
    embed.add_field(name="⚠️ Active Strikes", value=f"`{len(active_strikes)}` active", inline=True)
    embed.add_field(name="🕊️ Pardoned / Expired", value=f"`{len(pardoned_strikes)}` records", inline=True)
    embed.add_field(name="🪙 Community Points", value=f"`{points_info.get('points', 0)}` pts", inline=True)

    # Flagged Status Badges
    flags = []
    if watchlist_entry:
        flags.append(f"👁️ **Watchlisted:** {watchlist_entry['reason']} (Added by <@{watchlist_entry['added_by']}>)")
    if blacklist_entry:
        flags.append(f"🚫 **Recruitment Blacklisted:** {blacklist_entry['reason']}")
    if suspension:
        flags.append(f"⏸️ **Active Suspension:** {suspension['reason']} (Ends: `{suspension['end_time']}`)")

    if flags:
        embed.add_field(name="🚨 Active HR Security Flags", value="\n".join(flags), inline=False)

    # Recent Infractions Breakdown
    if strikes:
        recent_text = ""
        for s in strikes[:5]:
            status_icon = "🔴 Active" if s["active"] else "🟢 Expunged"
            recent_text += f"• **`#{s['id']}`** [{status_icon}] - {format_severity(s['severity'])}\n  Reason: *{s['reason']}*\n"
        embed.add_field(name="📋 Recent Disciplinary Log", value=recent_text, inline=False)

    embed.set_footer(text="Echo Technologies HR Systems • Internal Staff Record")
    return embed


class StrikeDMAppealView(ui.View):
    """Interactive view attached to HR Strike DM notices allowing direct button appeals."""
    def __init__(self, strike_id: Optional[int] = None):
        super().__init__(timeout=None)
        self.strike_id = strike_id
        self.add_item(ui.Button(label="🔗 Server Support", style=discord.ButtonStyle.link, url=config.SERVER_INVITE_URL))

    @ui.button(label="📜 Appeal Strike", style=discord.ButtonStyle.primary, emoji="📜", custom_id="strike_dm_appeal_btn")
    async def appeal_button(self, interaction: discord.Interaction, button: ui.Button):
        sid = self.strike_id
        if sid is None and interaction.message and interaction.message.embeds:
            emb = interaction.message.embeds[0]
            # Parse Record ID from embed description (e.g. • **Record ID:** `#STRK-1049` or `1049`)
            match = re.search(r"Record ID:\*\* `#(?:STRK-)?(\d+)`", emb.description or "")
            if match:
                sid = int(match.group(1))

        if sid is None:
            await interaction.response.send_modal(StrikeAppealModal())
        else:
            modal = StrikeDMAppealModal(strike_id=sid)
            await interaction.response.send_modal(modal)


class StrikeDMAppealModal(ui.Modal, title="📜 HR Strike Appeal Submission"):
    def __init__(self, strike_id: int):
        super().__init__()
        self.strike_id = strike_id

    appeal_reason = ui.TextInput(
        label="Reason & Justification for Appeal",
        style=discord.TextStyle.paragraph,
        placeholder="Explain why this strike should be pardoned or expunged...",
        min_length=20,
        max_length=1000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        success, msg, appeal_id = create_strike_appeal(self.strike_id, interaction.user.id, self.appeal_reason.value.strip())
        if not success:
            await interaction.followup.send(msg, ephemeral=True)
            return

        guild = interaction.client.get_guild(config.GUILD_ID)
        hr_ch = None
        if guild:
            hr_ch = guild.get_channel(config.HR_LOGS_CHANNEL_ID) or guild.get_channel(config.MOD_LOGS_CHANNEL_ID)

        if hr_ch:
            embed = discord.Embed(
                title=f"📜 HR Disciplinary Appeal Submitted (#{appeal_id})",
                description=(
                    f"**Appellant:** {interaction.user.mention} (`@{interaction.user.name}` | `{interaction.user.id}`)\n"
                    f"**Target Strike ID:** `#{self.strike_id}`\n"
                    f"**Submitted:** <t:{int(discord.utils.utcnow().timestamp())}:F>\n\n"
                    f"### 📝 Appeal Statement\n"
                    f"> {self.appeal_reason.value.strip()}\n\n"
                    f"HR Leadership can review and decide using the controls below."
                ),
                color=0x5865F2,
                timestamp=discord.utils.utcnow()
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            view = HRAppealControlView(appeal_id)
            await hr_ch.send(embed=embed, view=view)

        await interaction.followup.send(f"✅ Your appeal for Strike `#{self.strike_id}` has been lodged with HR Leadership.", ephemeral=True)


def build_strike_dm_embed(
    strike_id: int,
    staff: discord.Member,
    issuer: discord.User,
    reason: str,
    severity: int,
    total_active: int
) -> discord.Embed:
    """Constructs the official Echo Technologies disciplinary DM notice."""
    color = 0xFEE75C if severity == 1 else (0xE67E22 if severity == 2 else 0xED4245)
    embed = discord.Embed(
        title="⚠️ Echo Technologies • Notice of Staff Disciplinary Action",
        description=(
            f"# Echo Technologies\n"
            f"### Human Resources & Internal Accountability\n\n"
            f"Dear **{staff.display_name}**,\n\n"
            f"This notice serves as official documentation that a disciplinary action has been issued regarding your conduct or duties as a staff member of **Echo Technologies**.\n\n"
            f"--- \n"
            f"### 📋 Disciplinary Record Overview\n"
            f"• **Record ID:** `#{strike_id}`\n"
            f"• **Staff Member:** {staff.mention} (`@{staff.name}`)\n"
            f"• **Issuing Supervisor:** {issuer.mention} (`{issuer.display_name}`)\n"
            f"• **Severity Level:** **{format_severity(severity)}**\n"
            f"• **Total Active Infractions:** `{total_active}` active strike(s)\n"
            f"• **Date Logged:** <t:{int(discord.utils.utcnow().timestamp())}:F>\n\n"
            f"### 📝 Reason & Justification\n"
            f"> {reason}\n\n"
            f"---\n"
            f"### 🛡️ Rights & Appeals Procedure\n"
            f"Echo Technologies values fairness. Click the **Appeal Strike** button below or use `/appeal strike_id:{strike_id}` to submit an appeal to HR Leadership."
        ),
        color=color,
        timestamp=discord.utils.utcnow()
    )
    if staff.guild and staff.guild.icon:
        embed.set_thumbnail(url=staff.guild.icon.url)
    embed.set_footer(text="Echo Technologies HR Portal • Confidential Staff Record")
    return embed

def build_strike_log_embed(
    strike_id: int,
    staff: discord.Member,
    issuer: discord.User,
    reason: str,
    severity: int,
    total_active: int
) -> discord.Embed:
    """Constructs the HR audit log embed sent to #hr-logs."""
    color = 0xFEE75C if severity == 1 else (0xE67E22 if severity == 2 else 0xED4245)
    embed = discord.Embed(
        title=f"📋 HR Audit Log: Staff Infraction #{strike_id}",
        color=color,
        timestamp=discord.utils.utcnow()
    )
    embed.set_thumbnail(url=staff.display_avatar.url)
    embed.add_field(name="Staff Member", value=f"{staff.mention} (`{staff.name}` | `{staff.id}`)", inline=True)
    embed.add_field(name="Supervisor", value=f"{issuer.mention} (`{issuer.name}`)", inline=True)
    embed.add_field(name="Severity", value=f"**{format_severity(severity)}**", inline=True)
    embed.add_field(name="Active Strikes", value=f"`{total_active}` total", inline=True)
    embed.add_field(name="Reason", value=reason[:1024], inline=False)
    embed.set_footer(text=f"Echo Technologies HR System • Record #{strike_id}")
    return embed
