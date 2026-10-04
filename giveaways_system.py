import discord
from discord import ui
from discord.ext import tasks
import sqlite3
import logging
import re
import json
import random
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("GiveawaysSystem")
DB_PATH = "verifications.db"

def parse_duration(duration_str: str) -> Optional[timedelta]:
    """Parses duration string like '10m', '2h', '1d', '30s' into timedelta."""
    match = re.match(r"^(\d+)\s*([smhdw])$", duration_str.strip().lower())
    if not match:
        return None
    val, unit = int(match.group(1)), match.group(2)
    if val <= 0:
        return None
    if unit == 's':
        return timedelta(seconds=val)
    elif unit == 'm':
        return timedelta(minutes=val)
    elif unit == 'h':
        return timedelta(hours=val)
    elif unit == 'd':
        return timedelta(days=val)
    elif unit == 'w':
        return timedelta(weeks=val)
    return None

def init_giveaways_db():
    """Initializes SQLite tables for giveaways and entry tracking."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS giveaways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER,
                prize TEXT NOT NULL,
                winners_count INTEGER DEFAULT 1,
                host_id INTEGER NOT NULL,
                end_time TIMESTAMP NOT NULL,
                ended INTEGER DEFAULT 0,
                winners TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS giveaway_entries (
                giveaway_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (giveaway_id, user_id),
                FOREIGN KEY (giveaway_id) REFERENCES giveaways(id) ON DELETE CASCADE
            );
        """)
        conn.commit()

init_giveaways_db()

def create_giveaway(
    guild_id: int,
    channel_id: int,
    prize: str,
    winners_count: int,
    host_id: int,
    end_time: datetime
) -> int:
    """Inserts a new giveaway record and returns its ID."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO giveaways (guild_id, channel_id, prize, winners_count, host_id, end_time, ended)
            VALUES (?, ?, ?, ?, ?, ?, 0);
        """, (guild_id, channel_id, prize, winners_count, host_id, end_time.isoformat()))
        conn.commit()
        return cursor.lastrowid

def set_giveaway_message(giveaway_id: int, message_id: int):
    """Associates Discord message ID with giveaway record."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE giveaways SET message_id = ? WHERE id = ?;", (message_id, giveaway_id))
        conn.commit()

def get_giveaway(giveaway_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves a giveaway record by ID."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM giveaways WHERE id = ?;", (giveaway_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_giveaway_by_message(message_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves a giveaway record by Discord message ID."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM giveaways WHERE message_id = ?;", (message_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_active_giveaways() -> List[Dict[str, Any]]:
    """Returns all giveaways that have not ended yet."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM giveaways WHERE ended = 0;")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def get_entry_count(giveaway_id: int) -> int:
    """Returns the total number of unique entries in a giveaway."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = ?;", (giveaway_id,))
        return cursor.fetchone()[0]

def get_entries(giveaway_id: int) -> List[int]:
    """Returns list of user IDs entered in the giveaway."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM giveaway_entries WHERE giveaway_id = ?;", (giveaway_id,))
        return [row[0] for row in cursor.fetchall()]

def toggle_giveaway_entry(giveaway_id: int, user_id: int) -> Tuple[bool, int]:
    """
    Toggles user participation in the giveaway.
    Returns: (is_entered: bool, new_total_count: int)
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM giveaway_entries WHERE giveaway_id = ? AND user_id = ?;", (giveaway_id, user_id))
        exists = cursor.fetchone()
        if exists:
            cursor.execute("DELETE FROM giveaway_entries WHERE giveaway_id = ? AND user_id = ?;", (giveaway_id, user_id))
            entered = False
        else:
            cursor.execute("INSERT INTO giveaway_entries (giveaway_id, user_id) VALUES (?, ?);", (giveaway_id, user_id))
            entered = True
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = ?;", (giveaway_id,))
        count = cursor.fetchone()[0]
        return entered, count

def mark_giveaway_ended(giveaway_id: int, winners: List[int]):
    """Marks the giveaway as ended in the database and records winners."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE giveaways
            SET ended = 1, winners = ?
            WHERE id = ?;
        """, (json.dumps(winners), giveaway_id))
        conn.commit()

def pick_random_winners(giveaway_id: int, count: int, exclude: Optional[List[int]] = None) -> List[int]:
    """Selects fair random winners from entries."""
    entries = get_entries(giveaway_id)
    if exclude:
        entries = [uid for uid in entries if uid not in exclude]
    if not entries:
        return []
    if len(entries) <= count:
        return entries
    return random.sample(entries, count)

def build_giveaway_embed(
    giveaway_data: Dict[str, Any],
    entry_count: int,
    winners: Optional[List[int]] = None,
    is_ended: bool = False
) -> discord.Embed:
    """Builds a rich presentation embed for active or ended giveaways."""
    prize = giveaway_data["prize"]
    host_id = giveaway_data["host_id"]
    gw_id = giveaway_data["id"]
    winners_count = giveaway_data["winners_count"]

    # Parse end timestamp
    end_raw = giveaway_data["end_time"]
    try:
        if isinstance(end_raw, str):
            end_dt = datetime.fromisoformat(end_raw)
        else:
            end_dt = end_raw
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        end_ts = int(end_dt.timestamp())
    except Exception:
        end_ts = int(datetime.now(timezone.utc).timestamp())

    if not is_ended:
        embed = discord.Embed(
            title=f"🎉 GIVEAWAY: {prize}",
            description=(
                f"A new giveaway has begun! Click the **🎉 Enter ({entry_count})** button below to participate!\n\n"
                f"🎁 **Prize:** `{prize}`\n"
                f"👑 **Hosted by:** <@{host_id}>\n"
                f"🏆 **Winners:** `{winners_count}`\n"
                f"👥 **Entries:** `{entry_count}`\n"
                f"⏳ **Ends:** <t:{end_ts}:R> (<t:{end_ts}:F>)"
            ),
            color=0x5865F2
        )
        embed.set_footer(text=f"Giveaway #{gw_id} • Echo Technologies Community Events")
    else:
        if winners and len(winners) > 0:
            winners_str = ", ".join([f"<@{w}>" for w in winners])
        else:
            winners_str = "*No valid entries were received.*"

        embed = discord.Embed(
            title=f"🎉 GIVEAWAY CONCLUDED: {prize}",
            description=(
                f"This giveaway has officially ended!\n\n"
                f"🎁 **Prize:** `{prize}`\n"
                f"👑 **Hosted by:** <@{host_id}>\n"
                f"🏆 **Winner(s):** {winners_str}\n"
                f"👥 **Total Entries:** `{entry_count}`\n"
                f"🕒 **Ended:** <t:{end_ts}:R>"
            ),
            color=0x2B2D31
        )
        embed.set_footer(text=f"Giveaway #{gw_id} • Concluded")

    return embed

class GiveawayView(ui.View):
    """Interactive persistent view with entry button for giveaways."""

    def __init__(self, giveaway_id: int, entry_count: int = 0, ended: bool = False):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        btn_label = f"Enter ({entry_count})" if not ended else f"Ended ({entry_count})"
        btn_style = discord.ButtonStyle.success if not ended else discord.ButtonStyle.secondary
        self.add_item(
            ui.Button(
                label=btn_label,
                style=btn_style,
                emoji="🎉",
                custom_id=f"g_enter:{giveaway_id}",
                disabled=ended
            )
        )

async def end_giveaway(bot, giveaway_id: int) -> Tuple[bool, str, List[int]]:
    """Concludes a giveaway, chooses winners, updates the message, and announces results."""
    gw = get_giveaway(giveaway_id)
    if not gw:
        return False, "Giveaway not found.", []
    if gw["ended"]:
        return False, "Giveaway has already concluded.", []

    winners = pick_random_winners(giveaway_id, gw["winners_count"])
    mark_giveaway_ended(giveaway_id, winners)
    entry_count = get_entry_count(giveaway_id)

    channel = bot.get_channel(gw["channel_id"])
    if not channel:
        try:
            channel = await bot.fetch_channel(gw["channel_id"])
        except Exception:
            channel = None

    if channel:
        # Edit giveaway embed
        msg = None
        if gw.get("message_id"):
            try:
                msg = await channel.fetch_message(gw["message_id"])
            except Exception:
                msg = None

        new_embed = build_giveaway_embed(gw, entry_count, winners=winners, is_ended=True)
        new_view = GiveawayView(giveaway_id, entry_count, ended=True)

        if msg:
            try:
                await msg.edit(embed=new_embed, view=new_view)
            except Exception as e:
                logger.warning(f"Could not edit giveaway message #{gw['message_id']}: {e}")

        # Send win announcement
        if winners:
            winner_mentions = ", ".join([f"<@{w}>" for w in winners])
            congrats_embed = discord.Embed(
                title="🏆 Winner Announcement!",
                description=(
                    f"🎉 Congratulations {winner_mentions}!\n\n"
                    f"You won **{gw['prize']}**!\n"
                    f"Hosted by <@{gw['host_id']}>. Please contact the host or open a ticket to claim your prize."
                ),
                color=0x57F287
            )
            congrats_embed.set_footer(text=f"Giveaway #{giveaway_id} • Echo Technologies")
            jump_view = None
            if msg:
                jump_view = ui.View()
                jump_view.add_item(ui.Button(label="View Giveaway", url=msg.jump_url, style=discord.ButtonStyle.link))
            try:
                await channel.send(content=f"🎉 {winner_mentions}", embed=congrats_embed, view=jump_view)
            except Exception as e:
                logger.error(f"Could not send winner announcement: {e}")
        else:
            try:
                await channel.send(f"⚠️ Giveaway #{giveaway_id} for **{gw['prize']}** ended with 0 entries.")
            except Exception:
                pass

    return True, "Giveaway concluded successfully.", winners

async def reroll_giveaway(bot, giveaway_id: int, winners_count: int = 1) -> Tuple[bool, str, List[int]]:
    """Rerolls winners for an ended giveaway."""
    gw = get_giveaway(giveaway_id)
    if not gw:
        return False, "Giveaway not found.", []
    if not gw["ended"]:
        return False, "This giveaway is still active! Use `/giveaway end` to conclude it first.", []

    prev_winners = []
    if gw.get("winners"):
        try:
            prev_winners = json.loads(gw["winners"])
        except Exception:
            pass

    new_winners = pick_random_winners(giveaway_id, winners_count, exclude=prev_winners)
    if not new_winners:
        # If no entries excluding previous, try picking without exclusion
        new_winners = pick_random_winners(giveaway_id, winners_count)

    if not new_winners:
        return False, "No valid entries available to reroll.", []

    # Update winners in DB
    all_winners = list(set(prev_winners + new_winners))
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE giveaways SET winners = ? WHERE id = ?;", (json.dumps(all_winners), giveaway_id))
        conn.commit()

    channel = bot.get_channel(gw["channel_id"])
    if not channel:
        try:
            channel = await bot.fetch_channel(gw["channel_id"])
        except Exception:
            channel = None

    if channel:
        winner_mentions = ", ".join([f"<@{w}>" for w in new_winners])
        reroll_embed = discord.Embed(
            title="🎲 Giveaway Winner Rerolled!",
            description=(
                f"🎉 Congratulations {winner_mentions}!\n\n"
                f"You are the new selected winner(s) for **{gw['prize']}**!\n"
                f"Hosted by <@{gw['host_id']}>."
            ),
            color=0xFEE75C
        )
        reroll_embed.set_footer(text=f"Reroll for Giveaway #{giveaway_id}")
        await channel.send(content=f"🎉 {winner_mentions}", embed=reroll_embed)

    return True, f"Rerolled {len(new_winners)} winner(s).", new_winners

@tasks.loop(seconds=20)
async def check_active_giveaways_loop(bot):
    """Periodically checks if any active giveaways have reached their end time."""
    try:
        active = get_active_giveaways()
        now = datetime.now(timezone.utc)
        for gw in active:
            end_raw = gw["end_time"]
            try:
                if isinstance(end_raw, str):
                    end_dt = datetime.fromisoformat(end_raw)
                else:
                    end_dt = end_raw
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                if end_dt <= now:
                    await end_giveaway(bot, gw["id"])
            except Exception as e:
                logger.error(f"Error checking giveaway #{gw['id']}: {e}")
    except Exception as e:
        logger.error(f"Error in check_active_giveaways_loop: {e}")

