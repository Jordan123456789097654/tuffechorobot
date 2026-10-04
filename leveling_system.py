import discord
import sqlite3
import logging
import random
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timezone

logger = logging.getLogger("LevelingSystem")
DB_PATH = "verifications.db"

def init_leveling_db():
    """Initializes table for member XP and leveling."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_levels (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0,
                message_count INTEGER DEFAULT 0,
                last_xp_time TIMESTAMP,
                PRIMARY KEY (user_id, guild_id)
            );
        """)
        conn.commit()

init_leveling_db()

def get_level_from_xp(xp: int) -> int:
    """Calculates level from total XP using a quadratic scale."""
    if xp <= 0:
        return 0
    return int((xp / 100) ** 0.5)

def get_xp_for_level(level: int) -> int:
    """Calculates total XP required to reach a level."""
    return 100 * (level ** 2)

def get_xp_progress(xp: int) -> Tuple[int, int, int, float]:
    """
    Returns (current_level, xp_into_level, xp_needed_for_next, progress_ratio).
    """
    lvl = get_level_from_xp(xp)
    base_xp = get_xp_for_level(lvl)
    next_xp = get_xp_for_level(lvl + 1)
    xp_into = xp - base_xp
    xp_needed = next_xp - base_xp
    ratio = min(1.0, max(0.0, xp_into / xp_needed)) if xp_needed > 0 else 1.0
    return lvl, xp_into, xp_needed, ratio

def render_progress_bar(ratio: float, length: int = 12) -> str:
    """Renders a text progress bar like [▓▓▓▓▓░░░░░░░] 42%."""
    filled = int(round(ratio * length))
    empty = length - filled
    pct = int(ratio * 100)
    bar = "▓" * filled + "░" * empty
    return f"`[{bar}]` **{pct}%**"

def award_message_xp(
    user_id: int,
    guild_id: int,
    cooldown_seconds: int = 60
) -> Tuple[bool, int, int, bool]:
    """
    Awards message XP with anti-spam cooldown.
    Returns: (awarded: bool, new_xp: int, new_level: int, leveled_up: bool)
    """
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_levels WHERE user_id = ? AND guild_id = ?;", (user_id, guild_id))
        row = cursor.fetchone()

        if row:
            last_time_raw = row["last_xp_time"]
            if last_time_raw:
                try:
                    last_time = datetime.fromisoformat(last_time_raw)
                    if last_time.tzinfo is None:
                        last_time = last_time.replace(tzinfo=timezone.utc)
                    if (now - last_time).total_seconds() < cooldown_seconds:
                        # Cooldown active -> only increment message_count
                        cursor.execute("""
                            UPDATE user_levels
                            SET message_count = message_count + 1
                            WHERE user_id = ? AND guild_id = ?;
                        """, (user_id, guild_id))
                        conn.commit()
                        return False, row["xp"], row["level"], False
                except Exception:
                    pass

            gain = random.randint(15, 25)
            new_xp = row["xp"] + gain
            old_level = row["level"]
            new_level = get_level_from_xp(new_xp)
            leveled_up = new_level > old_level

            cursor.execute("""
                UPDATE user_levels
                SET xp = ?, level = ?, message_count = message_count + 1, last_xp_time = ?
                WHERE user_id = ? AND guild_id = ?;
            """, (new_xp, new_level, now_iso, user_id, guild_id))
            conn.commit()
            return True, new_xp, new_level, leveled_up

        else:
            gain = random.randint(15, 25)
            new_level = get_level_from_xp(gain)
            cursor.execute("""
                INSERT INTO user_levels (user_id, guild_id, xp, level, message_count, last_xp_time)
                VALUES (?, ?, ?, ?, 1, ?);
            """, (user_id, guild_id, gain, new_level, now_iso))
            conn.commit()
            return True, gain, new_level, (new_level > 0)

def get_user_level_data(user_id: int, guild_id: int) -> Dict[str, Any]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_levels WHERE user_id = ? AND guild_id = ?;", (user_id, guild_id))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return {"user_id": user_id, "guild_id": guild_id, "xp": 0, "level": 0, "message_count": 0}

def get_user_rank_position(user_id: int, guild_id: int) -> Tuple[int, int]:
    """Returns (rank_position, total_users)."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM user_levels WHERE guild_id = ?;", (guild_id,))
        total = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) + 1 FROM user_levels
            WHERE guild_id = ? AND xp > (SELECT COALESCE(xp, 0) FROM user_levels WHERE user_id = ? AND guild_id = ?);
        """, (guild_id, user_id, guild_id))
        pos = cursor.fetchone()[0]
        return pos, max(1, total)

def get_guild_leaderboard(guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM user_levels
            WHERE guild_id = ?
            ORDER BY xp DESC, message_count DESC
            LIMIT ?;
        """, (guild_id, limit))
        return [dict(r) for r in cursor.fetchall()]

def set_member_level(user_id: int, guild_id: int, new_level: int) -> int:
    """Manually adjusts member level (for administrators)."""
    target_xp = get_xp_for_level(new_level)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_levels (user_id, guild_id, xp, level, message_count, last_xp_time)
            VALUES (?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, guild_id) DO UPDATE SET xp = ?, level = ?;
        """, (user_id, guild_id, target_xp, new_level, target_xp, new_level))
        conn.commit()
    return target_xp

def build_rank_card_embed(
    user: discord.User,
    level_data: Dict[str, Any],
    rank_pos: int,
    total_ranks: int,
    roblox_info: Optional[Dict[str, Any]] = None,
    headshot_url: Optional[str] = None
) -> discord.Embed:
    """Builds a rank card profile embed."""
    xp = level_data.get("xp", 0)
    level, xp_into, xp_needed, ratio = get_xp_progress(xp)
    msg_count = level_data.get("message_count", 0)

    embed = discord.Embed(
        title=f"🏆 Level & Rank Profile • {user.display_name}",
        color=0x5865F2,
        timestamp=discord.utils.utcnow()
    )
    embed.set_thumbnail(url=headshot_url or user.display_avatar.url)

    embed.add_field(name="🎖️ Level", value=f"**Level {level}**", inline=True)
    embed.add_field(name="📊 Server Rank", value=f"**#{rank_pos}** of {total_ranks}", inline=True)
    embed.add_field(name="💬 Messages", value=f"**{msg_count:,}**", inline=True)

    progress_str = f"{render_progress_bar(ratio)}\n`{xp_into:,} / {xp_needed:,} XP` (Total: `{xp:,} XP`)"
    embed.add_field(name="📈 Level Progress", value=progress_str, inline=False)

    if roblox_info:
        rbx_str = f"**{roblox_info['roblox_display_name']}** (`@{roblox_info['roblox_username']}`)"
        embed.add_field(name="🎮 Linked Roblox", value=rbx_str, inline=True)
    else:
        embed.add_field(name="🎮 Linked Roblox", value="*Not verified*", inline=True)

    embed.set_footer(text="Echo Technologies Leveling • Chat to earn XP")
    return embed

def build_leaderboard_embed(
    guild: discord.Guild,
    top_entries: List[Dict[str, Any]],
    bot
) -> discord.Embed:
    """Builds top member XP leaderboard."""
    embed = discord.Embed(
        title=f"🌟 {guild.name} • XP Leaderboard",
        description="Top active community members ranked by chat activity & level:\n",
        color=0xFEE75C,
        timestamp=discord.utils.utcnow()
    )

    medals = ["🥇", "🥈", "🥉"]

    if not top_entries:
        embed.description += "\n*No member XP recorded yet. Start chatting to gain XP!*"
    else:
        lines = []
        for i, entry in enumerate(top_entries):
            uid = entry["user_id"]
            user = bot.get_user(uid)
            user_name = user.display_name if user else f"User {uid}"
            medal = medals[i] if i < 3 else f"`#{i+1}`"

            # Check if verified
            rbx = bot.db.get_by_discord_id(uid)
            rbx_tag = f" • @{rbx['roblox_username']}" if rbx else ""

            lines.append(
                f"{medal} **{user_name}**{rbx_tag}\n"
                f"   └ **Level {entry['level']}** • `{entry['xp']:,} XP` • `{entry['message_count']:,} msgs`"
            )
        embed.description = "\n".join(lines)

    embed.set_footer(text="Echo Technologies Community Leaderboard")
    return embed
