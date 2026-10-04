import discord
from discord import ui
from discord.ext import tasks
import sqlite3
import logging
import asyncio
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("EventsSystem")
DB_PATH = "verifications.db"

def init_events_db():
    """Initializes tables for events and RSVP tracking."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                host_id INTEGER NOT NULL,
                event_time TIMESTAMP NOT NULL,
                reminder_sent INTEGER DEFAULT 0,
                status TEXT DEFAULT 'scheduled', -- 'scheduled', 'completed', 'cancelled'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS event_rsvps (
                event_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                status TEXT NOT NULL, -- 'attending', 'maybe', 'declined'
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (event_id, user_id),
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
            );
        """)
        conn.commit()

init_events_db()

def create_event(
    guild_id: int,
    channel_id: int,
    title: str,
    description: str,
    host_id: int,
    event_time: datetime
) -> int:
    """Inserts a new event record and returns its ID."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO events (guild_id, channel_id, title, description, host_id, event_time, status)
            VALUES (?, ?, ?, ?, ?, ?, 'scheduled');
        """, (guild_id, channel_id, title, description, host_id, event_time.isoformat()))
        conn.commit()
        return cursor.lastrowid

def set_event_message(event_id: int, message_id: int):
    """Binds posted message ID to the event record."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE events SET message_id = ? WHERE id = ?;", (message_id, event_id))
        conn.commit()

def get_event(event_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves an event by ID."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events WHERE id = ?;", (event_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_upcoming_events() -> List[Dict[str, Any]]:
    """Returns all active scheduled events."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events WHERE status = 'scheduled' ORDER BY event_time ASC;")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def get_event_rsvp_counts(event_id: int) -> Dict[str, int]:
    """Returns count of attendees by status."""
    counts = {"attending": 0, "maybe": 0, "declined": 0}
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, COUNT(*) FROM event_rsvps WHERE event_id = ? GROUP BY status;", (event_id,))
        for status, cnt in cursor.fetchall():
            if status in counts:
                counts[status] = cnt
    return counts

def set_event_rsvp(event_id: int, user_id: int, status: str) -> Tuple[str, Dict[str, int]]:
    """Sets or toggles user RSVP and returns (final_status, updated_counts)."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM event_rsvps WHERE event_id = ? AND user_id = ?;", (event_id, user_id))
        row = cursor.fetchone()
        if row and row[0] == status:
            # User clicked the same status again -> toggle off
            cursor.execute("DELETE FROM event_rsvps WHERE event_id = ? AND user_id = ?;", (event_id, user_id))
            final_status = "none"
        else:
            cursor.execute("""
                INSERT INTO event_rsvps (event_id, user_id, status, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(event_id, user_id) DO UPDATE SET status = excluded.status, updated_at = CURRENT_TIMESTAMP;
            """, (event_id, user_id, status))
            final_status = status
        conn.commit()
    return final_status, get_event_rsvp_counts(event_id)

def get_event_attendees(event_id: int, statuses: Optional[List[str]] = None) -> List[int]:
    """Gets user IDs of participants who responded with the given statuses."""
    if statuses is None:
        statuses = ["attending", "maybe"]
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        placeholders = ",".join("?" for _ in statuses)
        query = f"SELECT user_id FROM event_rsvps WHERE event_id = ? AND status IN ({placeholders});"
        cursor.execute(query, [event_id] + statuses)
        return [r[0] for r in cursor.fetchall()]

def mark_event_reminded(event_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE events SET reminder_sent = 1 WHERE id = ?;", (event_id,))
        conn.commit()

def cancel_event(event_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE events SET status = 'cancelled' WHERE id = ?;", (event_id,))
        conn.commit()
        return cursor.rowcount > 0

def build_event_embed(event_data: Dict[str, Any], counts: Dict[str, int], is_cancelled: bool = False) -> discord.Embed:
    """Builds presentation embed for community events."""
    title = event_data["title"]
    description = event_data["description"]
    host_id = event_data["host_id"]
    event_id = event_data["id"]

    end_raw = event_data["event_time"]
    try:
        if isinstance(end_raw, str):
            dt = datetime.fromisoformat(end_raw)
        else:
            dt = end_raw
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ts = int(dt.timestamp())
    except Exception:
        ts = int(datetime.now(timezone.utc).timestamp())

    color = 0xED4245 if is_cancelled else 0x5865F2
    status_tag = " [CANCELLED]" if is_cancelled else ""

    embed = discord.Embed(
        title=f"📅 Community Event: {title}{status_tag}",
        description=(
            f"{description}\n\n"
            f"**⏰ Scheduled Time:** <t:{ts}:F> (<t:{ts}:R>)\n"
            f"**👑 Hosted By:** <@{host_id}>\n"
            f"**📍 Location:** <#{event_data['channel_id']}>\n\n"
            f"**RSVP Status:**\n"
            f"• ✅ **Attending:** `{counts['attending']}`\n"
            f"• ❓ **Maybe:** `{counts['maybe']}`\n"
            f"• ❌ **Can't Make It:** `{counts['declined']}`"
        ),
        color=color
    )
    embed.set_footer(text=f"Event #{event_id} • Echo Technologies Events • Automated 15m Reminder Active")
    return embed

class EventRsvpView(ui.View):
    """Persistent interactive RSVP buttons for event posts."""

    def __init__(self, event_id: int, counts: Dict[str, int], disabled: bool = False):
        super().__init__(timeout=None)
        self.event_id = event_id
        self.add_item(
            ui.Button(
                label=f"Attending ({counts.get('attending', 0)})",
                emoji="✅",
                style=discord.ButtonStyle.success,
                custom_id=f"ev_att:{event_id}",
                disabled=disabled
            )
        )
        self.add_item(
            ui.Button(
                label=f"Maybe ({counts.get('maybe', 0)})",
                emoji="❓",
                style=discord.ButtonStyle.secondary,
                custom_id=f"ev_myb:{event_id}",
                disabled=disabled
            )
        )
        self.add_item(
            ui.Button(
                label=f"Can't Make It ({counts.get('declined', 0)})",
                emoji="❌",
                style=discord.ButtonStyle.danger,
                custom_id=f"ev_dec:{event_id}",
                disabled=disabled
            )
        )

async def broadcast_event_dm_task(bot, event_data: Dict[str, Any], guild: discord.Guild, jump_url: str):
    """
    Safely broadcasts an event invitation DM to server members in the background.
    Includes rate-limiting delays and error handling.
    """
    logger.info(f"Starting event invitation broadcast for Event #{event_data['id']} in {guild.name}...")
    success_count = 0
    fail_count = 0

    end_raw = event_data["event_time"]
    try:
        if isinstance(end_raw, str):
            dt = datetime.fromisoformat(end_raw)
        else:
            dt = end_raw
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ts = int(dt.timestamp())
    except Exception:
        ts = int(datetime.now(timezone.utc).timestamp())

    invite_embed = discord.Embed(
        title=f"🎉 You're Invited: {event_data['title']}",
        description=(
            f"Echo Technologies has scheduled a new community event!\n\n"
            f"**Event:** **{event_data['title']}**\n"
            f"**When:** <t:{ts}:F> (<t:{ts}:R>)\n"
            f"**Host:** <@{event_data['host_id']}>\n\n"
            f"**Description:**\n{event_data['description']}\n\n"
            f"Click the button below to view the announcement and RSVP!"
        ),
        color=0x5865F2
    )
    invite_embed.set_footer(text="Echo Technologies Events • RSVP in server for 15m reminder")

    view = ui.View()
    view.add_item(ui.Button(label="View Event & RSVP", url=jump_url, style=discord.ButtonStyle.link))

    for member in guild.members:
        if member.bot:
            continue
        try:
            dm = await member.create_dm()
            await dm.send(embed=invite_embed, view=view)
            success_count += 1
            await asyncio.sleep(0.7) # Respect Discord rate limits
        except (discord.Forbidden, discord.HTTPException):
            fail_count += 1
        except Exception as e:
            logger.debug(f"Could not send event DM to {member.id}: {e}")
            fail_count += 1

    logger.info(f"Completed event DM broadcast for Event #{event_data['id']}: {success_count} sent, {fail_count} skipped/closed DMs.")

@tasks.loop(seconds=30)
async def check_event_reminders_loop(bot):
    """
    Background monitor that sends automated DM reminders 15 minutes before event start.
    """
    try:
        upcoming = get_upcoming_events()
        now = datetime.now(timezone.utc)
        for ev in upcoming:
            if ev.get("reminder_sent"):
                continue

            end_raw = ev["event_time"]
            try:
                if isinstance(end_raw, str):
                    dt = datetime.fromisoformat(end_raw)
                else:
                    dt = end_raw
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue

            # Check if event starts in <= 15 minutes (and hasn't passed)
            time_until_start = (dt - now).total_seconds()
            if 0 <= time_until_start <= 900: # 15 minutes or less
                mark_event_reminded(ev["id"])
                attendees = get_event_attendees(ev["id"], ["attending", "maybe"])
                logger.info(f"Dispatching 15m reminder DMs for Event #{ev['id']} to {len(attendees)} RSVP'd members...")

                ts = int(dt.timestamp())
                reminder_embed = discord.Embed(
                    title=f"⏰ Event Starting Soon: {ev['title']}",
                    description=(
                        f"Friendly reminder! The event you RSVP'd for is starting **in 15 minutes**!\n\n"
                        f"**Event:** **{ev['title']}**\n"
                        f"**Start Time:** <t:{ts}:R> (<t:{ts}:t>)\n"
                        f"**Location:** <#{ev['channel_id']}>\n"
                        f"**Host:** <@{ev['host_id']}>\n\n"
                        f"Get ready and join in!"
                    ),
                    color=0xFEE75C
                )
                reminder_embed.set_footer(text=f"Event #{ev['id']} Reminder • Echo Technologies")

                for uid in attendees:
                    try:
                        user = bot.get_user(uid) or await bot.fetch_user(uid)
                        if user and not user.bot:
                            dm = await user.create_dm()
                            await dm.send(embed=reminder_embed)
                            await asyncio.sleep(0.3)
                    except Exception as e:
                        logger.debug(f"Could not send 15m reminder DM to user {uid}: {e}")
    except Exception as e:
        logger.error(f"Error in check_event_reminders_loop: {e}")
