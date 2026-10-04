import discord
from discord import ui
import sqlite3
import logging
from typing import Optional, Dict, Any, Tuple
import config

logger = logging.getLogger("StarboardSystem")
DB_PATH = "verifications.db"

def init_starboard_db():
    """Initializes tables for Starboard / Hall of Fame tracking."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS starboard_posts (
                orig_message_id INTEGER PRIMARY KEY,
                orig_channel_id INTEGER NOT NULL,
                starboard_message_id INTEGER NOT NULL,
                starboard_channel_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                star_count INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

init_starboard_db()

def get_starboard_post(orig_message_id: int) -> Optional[Dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM starboard_posts WHERE orig_message_id = ?;", (orig_message_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def save_starboard_post(
    orig_message_id: int,
    orig_channel_id: int,
    starboard_message_id: int,
    starboard_channel_id: int,
    author_id: int,
    star_count: int
):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO starboard_posts (orig_message_id, orig_channel_id, starboard_message_id, starboard_channel_id, author_id, star_count)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(orig_message_id) DO UPDATE SET star_count = excluded.star_count;
        """, (orig_message_id, orig_channel_id, starboard_message_id, starboard_channel_id, author_id, star_count))
        conn.commit()

def update_starboard_stars(orig_message_id: int, new_count: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE starboard_posts SET star_count = ? WHERE orig_message_id = ?;", (new_count, orig_message_id))
        conn.commit()

def build_starboard_embed(message: discord.Message) -> Tuple[discord.Embed, ui.View]:
    """Creates a presentation embed for a starred message."""
    embed = discord.Embed(
        description=message.content or "*(Media attachment)*",
        color=0xFEE75C,
        timestamp=message.created_at
    )
    embed.set_author(
        name=f"{message.author.display_name} (@{message.author.name})",
        icon_url=message.author.display_avatar.url
    )
    embed.add_field(name="📍 Channel", value=message.channel.mention, inline=True)

    # Attach images if present
    if message.attachments:
        first = message.attachments[0]
        if any(first.filename.lower().endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            embed.set_image(url=first.url)
    elif message.embeds:
        for em in message.embeds:
            if em.image and em.image.url:
                embed.set_image(url=em.image.url)
                break

    view = ui.View()
    view.add_item(ui.Button(label="Jump to Message", url=message.jump_url, style=discord.ButtonStyle.link))
    return embed, view

async def handle_star_reaction(bot, payload: discord.RawReactionActionEvent, is_add: bool):
    """Processes star reaction additions and removals."""
    if str(payload.emoji) != "⭐" and payload.emoji.name != "⭐":
        return

    # Don't star messages inside the starboard channel
    if payload.channel_id == config.HALL_OF_FAME_CHANNEL_ID:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    channel = guild.get_channel(payload.channel_id)
    if not channel or not isinstance(channel, discord.TextChannel):
        try:
            channel = await bot.fetch_channel(payload.channel_id)
        except Exception:
            return

    try:
        orig_msg = await channel.fetch_message(payload.message_id)
    except Exception:
        return

    # Count stars
    star_reaction = discord.utils.get(orig_msg.reactions, emoji="⭐")
    count = star_reaction.count if star_reaction else 0

    starboard_ch = guild.get_channel(config.HALL_OF_FAME_CHANNEL_ID)
    if not starboard_ch:
        # Search for channel by name
        for ch in guild.text_channels:
            if ch.name in ("hall-of-fame", "starboard"):
                starboard_ch = ch
                break

    if not starboard_ch or not isinstance(starboard_ch, discord.TextChannel):
        return

    post_record = get_starboard_post(orig_msg.id)
    threshold = config.STARBOARD_THRESHOLD

    if count >= threshold:
        header_text = f"⭐ **{count}** | {channel.mention}"
        embed, view = build_starboard_embed(orig_msg)

        if not post_record:
            # Post new starboard message
            try:
                sb_msg = await starboard_ch.send(content=header_text, embed=embed, view=view)
                save_starboard_post(
                    orig_message_id=orig_msg.id,
                    orig_channel_id=channel.id,
                    starboard_message_id=sb_msg.id,
                    starboard_channel_id=starboard_ch.id,
                    author_id=orig_msg.author.id,
                    star_count=count
                )
                logger.info(f"Message #{orig_msg.id} pinned to #{starboard_ch.name} with {count} stars.")
            except Exception as e:
                logger.error(f"Error posting to starboard: {e}")
        else:
            # Update existing starboard message
            sb_msg_id = post_record["starboard_message_id"]
            try:
                sb_msg = await starboard_ch.fetch_message(sb_msg_id)
                await sb_msg.edit(content=header_text, embed=embed, view=view)
                update_starboard_stars(orig_msg.id, count)
            except Exception as e:
                logger.warning(f"Could not update starboard message #{sb_msg_id}: {e}")
    else:
        # If count dropped below threshold but already on starboard, update count
        if post_record:
            update_starboard_stars(orig_msg.id, count)
            sb_msg_id = post_record["starboard_message_id"]
            try:
                sb_msg = await starboard_ch.fetch_message(sb_msg_id)
                header_text = f"⭐ **{count}** | {channel.mention}"
                embed, view = build_starboard_embed(orig_msg)
                await sb_msg.edit(content=header_text, embed=embed, view=view)
            except Exception:
                pass
