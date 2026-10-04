import discord
from discord import ui, app_commands
import sqlite3
import logging
import re
import json
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timedelta, timezone
import config

logger = logging.getLogger("InviteCompSystem")
DB_PATH = "verifications.db"

def init_invite_comp_db():
    """Initializes SQLite tables and migrates schemas for invite competitions, security, and leaderboards."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Invite Competitions Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invite_competitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER DEFAULT NULL,
                title TEXT NOT NULL,
                prize TEXT NOT NULL,
                host_id INTEGER NOT NULL,
                end_time TIMESTAMP NOT NULL,
                ended INTEGER DEFAULT 0,
                winners_json TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # Invite Code Cache / Tracker Snapshot Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invite_tracker_cache (
                guild_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                inviter_id INTEGER NOT NULL,
                uses INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, code)
            );
        """)
        # User Joined By Tracking Table (Includes Security Flags & Leave Status)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invite_joins (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                inviter_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                is_fake INTEGER DEFAULT 0,
                left_server INTEGER DEFAULT 0,
                disqualified INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, user_id)
            );
        """)

        # ALTER TABLE Migrations for pre-existing tables
        cursor.execute("PRAGMA table_info(invite_joins);")
        existing_cols = [col[1] for col in cursor.fetchall()]
        if "is_fake" not in existing_cols:
            cursor.execute("ALTER TABLE invite_joins ADD COLUMN is_fake INTEGER DEFAULT 0;")
        if "left_server" not in existing_cols:
            cursor.execute("ALTER TABLE invite_joins ADD COLUMN left_server INTEGER DEFAULT 0;")
        if "disqualified" not in existing_cols:
            cursor.execute("ALTER TABLE invite_joins ADD COLUMN disqualified INTEGER DEFAULT 0;")

        # Inviter Previous Ranks Table for DM Notifications
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inviter_rank_history (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                previous_rank INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );
        """)
        conn.commit()

init_invite_comp_db()


def create_invite_competition(
    guild_id: int,
    channel_id: int,
    title: str,
    prize: str,
    host_id: int,
    end_time: datetime
) -> int:
    """Inserts a new invite competition record and returns its ID."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO invite_competitions (guild_id, channel_id, title, prize, host_id, end_time, ended)
            VALUES (?, ?, ?, ?, ?, ?, 0);
        """, (guild_id, channel_id, title, prize, host_id, end_time.isoformat()))
        conn.commit()
        return cursor.lastrowid

def set_invite_comp_message(comp_id: int, message_id: int):
    """Associates Discord message ID with competition record."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE invite_competitions SET message_id = ? WHERE id = ?;", (message_id, comp_id))
        conn.commit()

def edit_invite_competition(comp_id: int, new_title: Optional[str] = None, new_prize: Optional[str] = None, extend_minutes: Optional[int] = None) -> bool:
    """Updates an active competition's details or extends its duration."""
    comp = get_invite_competition(comp_id)
    if not comp or comp["ended"]:
        return False
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if new_title:
            cursor.execute("UPDATE invite_competitions SET title = ? WHERE id = ?;", (new_title, comp_id))
        if new_prize:
            cursor.execute("UPDATE invite_competitions SET prize = ? WHERE id = ?;", (new_prize, comp_id))
        if extend_minutes:
            end_dt = datetime.fromisoformat(comp["end_time"])
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            new_end = end_dt + timedelta(minutes=extend_minutes)
            cursor.execute("UPDATE invite_competitions SET end_time = ? WHERE id = ?;", (new_end.isoformat(), comp_id))
        conn.commit()
    return True

def get_invite_competition(comp_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves an invite competition record by ID."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM invite_competitions WHERE id = ?;", (comp_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_active_invite_competitions(guild_id: int) -> List[Dict[str, Any]]:
    """Retrieves all active (non-ended) competitions in a guild."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM invite_competitions
            WHERE guild_id = ? AND ended = 0
            ORDER BY end_time ASC;
        """, (guild_id,))
        return [dict(r) for r in cursor.fetchall()]

def record_member_join_invite(guild_id: int, user_id: int, inviter_id: int, code: str, is_fake: bool = False):
    """Records which inviter & invite code a member joined through with account safety checks."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO invite_joins (guild_id, user_id, inviter_id, code, is_fake, left_server, disqualified)
            VALUES (?, ?, ?, ?, ?, 0, 0);
        """, (guild_id, user_id, inviter_id, code, 1 if is_fake else 0))
        conn.commit()

def record_member_leave_invite(guild_id: int, user_id: int) -> Optional[int]:
    """Marks a member as left, deducting 1 net invite count from their inviter."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT inviter_id FROM invite_joins WHERE guild_id = ? AND user_id = ?;", (guild_id, user_id))
        row = cursor.fetchone()
        if row:
            inviter_id = row[0]
            cursor.execute("UPDATE invite_joins SET left_server = 1 WHERE guild_id = ? AND user_id = ?;", (guild_id, user_id))
            conn.commit()
            return inviter_id
        return None

def disqualify_inviter(guild_id: int, inviter_id: int):
    """Disqualifies an inviter from competitions (e.g. for cheating/alt spam)."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE invite_joins SET disqualified = 1 WHERE guild_id = ? AND inviter_id = ?;", (guild_id, inviter_id))
        conn.commit()

def get_inviter_counts(guild_id: int) -> List[Tuple[int, int]]:
    """Returns sorted list of (inviter_id, valid_net_count) excluding alts, leaves, and disqualified users."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT inviter_id, COUNT(*) as cnt
            FROM invite_joins
            WHERE guild_id = ? AND is_fake = 0 AND left_server = 0 AND disqualified = 0
            GROUP BY inviter_id
            ORDER BY cnt DESC;
        """, (guild_id,))
        return cursor.fetchall()

def get_user_invite_stats(guild_id: int, user_id: int) -> Dict[str, Any]:
    """Returns comprehensive invite breakdown for a specific user (Valid, Leaves, Fakes, Net Total)."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, code, is_fake, left_server, disqualified, created_at FROM invite_joins
            WHERE guild_id = ? AND inviter_id = ?
            ORDER BY created_at DESC;
        """, (guild_id, user_id))
        rows = [dict(r) for r in cursor.fetchall()]
        
        valid = [r for r in rows if r["is_fake"] == 0 and r["left_server"] == 0 and r["disqualified"] == 0]
        leaves = [r for r in rows if r["left_server"] == 1]
        fakes = [r for r in rows if r["is_fake"] == 1]
        is_disqualified = any(r["disqualified"] == 1 for r in rows)

        return {
            "net_count": len(valid),
            "total_joins": len(rows),
            "leaves_count": len(leaves),
            "fakes_count": len(fakes),
            "is_disqualified": is_disqualified,
            "details": rows
        }

def build_invite_comp_embed(comp: Dict[str, Any], leaderboard: Optional[List[Tuple[int, int]]] = None) -> discord.Embed:
    """Constructs the official Discord competition announcement embed."""
    end_dt = datetime.fromisoformat(comp["end_time"])
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)
    end_ts = int(end_dt.timestamp())

    is_ended = bool(comp["ended"])
    color = 0xED4245 if is_ended else 0x5865F2

    embed = discord.Embed(
        title=f"🏆 INVITE COMPETITION • {comp['title'].upper()}",
        description=(
            f"# {comp['title']}\n"
            f"### Official Guild Recruitment Championship\n\n"
            f"Invite your friends and community members to join the server! The top recruiters at the end of the timer will win exclusive rewards!\n\n"
            f"--- \n"
            f"• **🏆 Competition Prize:** **{comp['prize']}**\n"
            f"• **👤 Hosted By:** <@{comp['host_id']}>\n"
            f"• **⏱️ Status:** {'🔴 **CONTEST ENDED**' if is_ended else f'Ends <t:{end_ts}:R> (<t:{end_ts}:F>)'}\n\n"
            f"--- \n"
            f"### 📋 How to Participate\n"
            f"1. Generate a personal invite link (`Server Dropdown -> Invite People`).\n"
            f"2. Set the link to **Never Expire**.\n"
            f"3. Share your link! Each member who joins increases your leaderboard rank.\n"
            f"4. Use `/invite-stats` to view your total invite count & rank anytime!"
        ),
        color=color,
        timestamp=discord.utils.utcnow()
    )

    if leaderboard and len(leaderboard) > 0:
        lb_text = ""
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        for idx, (inv_id, cnt) in enumerate(leaderboard[:10]):
            icon = medals[idx] if idx < len(medals) else f"`#{idx+1}`"
            lb_text += f"{icon} <@{inv_id}> — **{cnt}** invite(s)\n"
        embed.add_field(name="📊 Live Leaderboard Standings", value=lb_text, inline=False)
    else:
        embed.add_field(name="📊 Live Leaderboard Standings", value="*No invites recorded yet. Share your invite link to take 1st place!*", inline=False)

    if is_ended and comp.get("winners_json"):
        try:
            winners = json.loads(comp["winners_json"])
            w_text = "\n".join([f"🏆 **{place}:** <@{uid}> ({cnt} invites)" for place, uid, cnt in winners])
            embed.add_field(name="🎉 Official Contest Winners", value=w_text or "No eligible winners.", inline=False)
        except Exception:
            pass

    embed.set_footer(text=f"Echo Technologies Invite Engine • Contest ID #{comp['id']}")
    return embed


class InviteCompControlView(ui.View):
    """Interactive view attached to Invite Competition embeds."""
    def __init__(self, bot, comp_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.comp_id = comp_id

    @ui.button(label="📊 My Invite Stats", style=discord.ButtonStyle.primary, emoji="📊", custom_id="invite_comp_my_stats")
    async def my_stats_button(self, interaction: discord.Interaction, button: ui.Button):
        stats = get_user_invite_stats(interaction.guild.id, interaction.user.id)
        embed = discord.Embed(
            title=f"📊 Invite Dashboard — {interaction.user.display_name}",
            description=(
                f"Here is your official recruitment summary for **{interaction.guild.name}**:\n\n"
                f"• **⭐ Net Valid Invites:** **{stats['net_count']}**\n"
                f"• **👥 Total Member Joins:** `{stats['total_joins']}`\n"
                f"• **🚪 Member Leaves (-1):** `{stats['leaves_count']}`\n"
                f"• **⚠️ Flagged Alts (<7d):** `{stats['fakes_count']}`\n"
                f"• **🛡️ Contest Status:** {'❌ **DISQUALIFIED**' if stats['is_disqualified'] else '✅ **ELIGIBLE**'}"
            ),
            color=0xED4245 if stats['is_disqualified'] else 0x5865F2,
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        details = stats["details"]
        if details:
            recent_str = ""
            for d in details[:5]:
                status_tag = "✅ Valid"
                if d["is_fake"]:
                    status_tag = "⚠️ Flagged Alt"
                elif d["left_server"]:
                    status_tag = "🚪 Left Server"
                elif d["disqualified"]:
                    status_tag = "❌ Disqualified"
                recent_str += f"• <@{d['user_id']}> (`{d['code']}`) — {status_tag}\n"
            embed.add_field(name="📋 Recent Member Joins", value=recent_str, inline=False)
        else:
            embed.add_field(name="📋 Recent Member Joins", value="*You have not invited any members yet. Generate a link to get started!*", inline=False)
        
        embed.set_footer(text="Echo Technologies Anti-Alt & Invite Security Division")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="🏆 Live Leaderboard", style=discord.ButtonStyle.secondary, emoji="🏆", custom_id="invite_comp_leaderboard")
    async def leaderboard_button(self, interaction: discord.Interaction, button: ui.Button):
        comp = get_invite_competition(self.comp_id)
        if not comp:
            await interaction.response.send_message("❌ Competition record not found.", ephemeral=True)
            return
        lb = get_inviter_counts(interaction.guild.id)
        embed = build_invite_comp_embed(comp, leaderboard=lb)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def check_and_send_rank_movement_dms(bot, guild: discord.Guild):
    """Detects rank movements on the leaderboard and sends DM progress reports to members."""
    lb = get_inviter_counts(guild.id)
    if not lb:
        return

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for new_rank_idx, (inv_id, cnt) in enumerate(lb):
            new_rank = new_rank_idx + 1
            cursor.execute("SELECT previous_rank FROM inviter_rank_history WHERE guild_id = ? AND user_id = ?;", (guild.id, inv_id))
            row = cursor.fetchone()
            if row:
                old_rank = row[0]
                if old_rank != new_rank:
                    cursor.execute("UPDATE inviter_rank_history SET previous_rank = ? WHERE guild_id = ? AND user_id = ?;", (new_rank, guild.id, inv_id))
                    conn.commit()

                    user = bot.get_user(inv_id)
                    if user and old_rank <= 10 or new_rank <= 10:
                        try:
                            dm = await user.create_dm()
                            direction = "📈 **MOVED UP**" if new_rank < old_rank else "📉 **MOVED DOWN**"
                            color = 0x57F287 if new_rank < old_rank else 0xED4245
                            dm_embed = discord.Embed(
                                title=f"{direction} in Invite Competition!",
                                description=(
                                    f"Hello **{user.name}**, your rank on the leaderboard has changed!\n\n"
                                    f"• **Previous Rank:** `#{old_rank}`\n"
                                    f"• **Current Rank:** **#{new_rank}**\n"
                                    f"• **Total Net Invites:** **{cnt}**\n\n"
                                    f"Keep inviting new members to secure a top prize spot!"
                                ),
                                color=color,
                                timestamp=discord.utils.utcnow()
                            )
                            dm_embed.set_footer(text="Echo Technologies Leaderboard Monitor")
                            await dm.send(embed=dm_embed)
                        except Exception:
                            pass
            else:
                cursor.execute("INSERT INTO inviter_rank_history (guild_id, user_id, previous_rank) VALUES (?, ?, ?);", (guild.id, inv_id, new_rank))
                conn.commit()


async def update_invite_competition_embed(bot, comp_id: int):
    """Updates the announcement embed for an active or completed competition with the latest leaderboard."""
    comp = get_invite_competition(comp_id)
    if not comp or not comp.get("message_id"):
        return

    guild = bot.get_guild(comp["guild_id"])
    if not guild:
        try:
            guild = await bot.fetch_guild(comp["guild_id"])
        except Exception:
            return

    channel = guild.get_channel(comp["channel_id"])
    if not channel:
        try:
            channel = await bot.fetch_channel(comp["channel_id"])
        except Exception:
            return

    if not isinstance(channel, discord.TextChannel):
        return

    lb = get_inviter_counts(guild.id)
    embed = build_invite_comp_embed(comp, leaderboard=lb)
    try:
        msg = await channel.fetch_message(comp["message_id"])
        await msg.edit(embed=embed, view=InviteCompControlView(bot, comp_id))
    except discord.NotFound:
        # Message was deleted; clear message_id in DB to avoid repeated warning logs
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE invite_competitions SET message_id = NULL WHERE id = ?;", (comp_id,))
    except Exception as e:
        logger.warning(f"Could not update competition message #{comp['message_id']} for contest #{comp_id}: {e}")


    # Process rank movement DMs
    await check_and_send_rank_movement_dms(bot, guild)


async def end_invite_competition(bot, comp_id: int):
    """Concludes an invite competition, calculates winners, updates message, and posts winner announcement."""
    comp = get_invite_competition(comp_id)
    if not comp or comp["ended"]:
        return

    guild = bot.get_guild(comp["guild_id"]) or await bot.fetch_guild(comp["guild_id"])
    if not guild:
        return

    lb = get_inviter_counts(guild.id)
    winners = []
    places = ["1st Place Winner", "2nd Place Runner-Up", "3rd Place Runner-Up"]
    for idx, (inv_id, cnt) in enumerate(lb[:3]):
        winners.append((places[idx], inv_id, cnt))

    winners_json = json.dumps(winners)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE invite_competitions SET ended = 1, winners_json = ? WHERE id = ?;", (winners_json, comp_id))
        conn.commit()

    comp["ended"] = 1
    comp["winners_json"] = winners_json

    channel = guild.get_channel(comp["channel_id"])
    if not channel:
        try:
            channel = await bot.fetch_channel(comp["channel_id"])
        except Exception:
            channel = None
    if channel and isinstance(channel, discord.TextChannel):
        embed = build_invite_comp_embed(comp, leaderboard=lb)
        if comp.get("message_id"):
            try:
                msg = await channel.fetch_message(comp["message_id"])
                await msg.edit(embed=embed, view=InviteCompControlView(bot, comp_id))
            except Exception:
                pass

        # Post winner announcement message
        if winners:
            win_text = "\n".join([f"🏆 **{place}:** <@{uid}> with **{cnt} invites**!" for place, uid, cnt in winners])
            announce_embed = discord.Embed(
                title=f"🎉 INVITE COMPETITION CONCLUDED • {comp['title'].upper()}",
                description=(
                    f"# 🏆 Winner Announcement!\n\n"
                    f"The invite competition **{comp['title']}** has officially concluded!\n\n"
                    f"### 🎁 Prize Awarded\n"
                    f"> **{comp['prize']}**\n\n"
                    f"### 🥇 Top Recruiters\n"
                    f"{win_text}\n\n"
                    f"Congratulations to our top recruiters and thank you to everyone who invited new members!"
                ),
                color=0x57F287,
                timestamp=discord.utils.utcnow()
            )
            announce_embed.set_footer(text="Echo Technologies Recruitment Division")
            await channel.send(content=f"🎉 **CONGRATULATIONS TO OUR INVITE CHAMPIONS!** <@{winners[0][1]}>", embed=announce_embed)
        else:
            await channel.send(f"📢 The invite competition **{comp['title']}** has ended. No invites were recorded during this contest.")


async def check_invite_competitions_loop(bot):
    """Background task loop checking for expired invite competitions & updating live leaderboards."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        now_str = datetime.now(timezone.utc).isoformat()
        
        # Check expired competitions
        cursor.execute("SELECT id FROM invite_competitions WHERE ended = 0 AND end_time <= ?;", (now_str,))
        expired = [dict(r) for r in cursor.fetchall()]

        # Get active competitions to live update leaderboard
        cursor.execute("SELECT id FROM invite_competitions WHERE ended = 0 AND end_time > ?;", (now_str,))
        active = [dict(r) for r in cursor.fetchall()]

    for c in expired:
        try:
            await end_invite_competition(bot, c["id"])
        except Exception as e:
            logger.error(f"Error concluding invite competition #{c['id']}: {e}")

    for c in active:
        try:
            await update_invite_competition_embed(bot, c["id"])
        except Exception as e:
            logger.error(f"Error updating live leaderboard embed for competition #{c['id']}: {e}")


