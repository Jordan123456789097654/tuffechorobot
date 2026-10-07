import sqlite3
import discord
import logging
from contextlib import contextmanager

logger = logging.getLogger("roblox_bot.sorry_system")
DB_PATH = "verifications.db"
BLACKLISTS_CHANNEL_ID = 1557201912997216386
SORRY_CHANNEL_ID = 1557203224317005967

def init_sorry_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sorry_tracker (
            discord_id INTEGER PRIMARY KEY,
            count INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    conn.close()

init_sorry_db()

def get_sorry_count(discord_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT count FROM sorry_tracker WHERE discord_id = ?", (discord_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

def set_sorry_count(discord_id: int, count: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sorry_tracker (discord_id, count)
        VALUES (?, ?)
        ON CONFLICT(discord_id) DO UPDATE SET count = ?;
    """, (discord_id, count, count))
    conn.commit()
    conn.close()

def increment_sorry_count(discord_id: int) -> int:
    current = get_sorry_count(discord_id) + 1
    set_sorry_count(discord_id, current)
    return current

def reset_sorry_count(discord_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sorry_tracker WHERE discord_id = ?", (discord_id,))
    conn.commit()
    conn.close()

async def remove_blacklist_notice_from_channel(guild: discord.Guild, user_id: int):
    """Searches for and deletes the user's blacklist notice message in #blacklists."""
    try:
        blacklists_ch = guild.get_channel(BLACKLISTS_CHANNEL_ID)
        if not blacklists_ch:
            try:
                blacklists_ch = await guild.fetch_channel(BLACKLISTS_CHANNEL_ID)
            except Exception:
                blacklists_ch = discord.utils.get(guild.text_channels, name="blacklists")

        if not blacklists_ch:
            return

        async for msg in blacklists_ch.history(limit=50):
            # Check if message mentions user ID or contains their ID / username
            if str(user_id) in msg.content or (msg.embeds and any(str(user_id) in (e.description or "") or any(str(user_id) in str(f.value) for f in e.fields) for e in msg.embeds)):
                try:
                    await msg.delete()
                    logger.info(f"Deleted blacklist notice message {msg.id} for user {user_id}")
                except Exception as e:
                    logger.error(f"Error deleting blacklist notice: {e}")
    except Exception as e:
        logger.error(f"Failed to search/delete blacklist notice: {e}")

async def handle_sorry_message(bot, message: discord.Message) -> bool:
    """
    Handles messages sent in #say-sorry-100-times-to-get-unblacklisted.
    Increments count when 'sorry' is typed.
    When 100 sorries is reached:
      1. Removes Blacklisted role.
      2. Deletes the Blacklist Notice message from #blacklists channel!
      3. Sends forgiveness notification.
    """
    if message.author.bot or not message.guild:
        return False

    is_sorry_channel = (
        message.channel.name == "say-sorry-100-times-to-get-unblacklisted"
        or message.channel.id == SORRY_CHANNEL_ID
    )
    if not is_sorry_channel:
        return False

    content = message.content.lower().strip()
    if "sorry" not in content:
        try:
            warn = await message.channel.send(
                f"⚠️ <@{message.author.id}>, your message must contain **`sorry`** to count towards your unblacklist requirement!"
            )
            await message.delete(delay=4)
        except Exception:
            pass
        return True

    # Increment counter
    new_count = increment_sorry_count(message.author.id)

    if new_count >= 100:
        reset_sorry_count(message.author.id)

        # 1. Remove Blacklisted Role
        blacklisted_role = discord.utils.get(message.guild.roles, name="Blacklisted")
        if blacklisted_role and blacklisted_role in message.author.roles:
            try:
                await message.author.remove_roles(blacklisted_role, reason="Completed 100 apologies requirement!")
            except Exception as e:
                logger.error(f"Failed to remove Blacklisted role from {message.author}: {e}")

        # 2. Automatically REMOVE the blacklist notice from #blacklists channel!
        await remove_blacklist_notice_from_channel(message.guild, message.author.id)

        # 3. Send Unblacklisted Forgiveness Embed
        unban_embed = discord.Embed(
            title="🎉 UNBLACK-LISTED & FORGIVEN!",
            description=(
                f"Congratulations <@{message.author.id}>!\n\n"
                "You have officially typed **`sorry` 100 times**!\n\n"
                "✅ **Actions Completed:**\n"
                "• The **Blacklisted** role has been removed from your account.\n"
                "• Your **Blacklist Notice message** has been removed from <#1557201912997216386>.\n"
                "• Full server access has been restored."
            ),
            color=0x57F287 # Bright Green
        )
        unban_embed.set_footer(text="Echo Technologies • Automated Redemption System")
        unban_embed.timestamp = discord.utils.utcnow()

        await message.channel.send(content=f"🔔 <@{message.author.id}> **YOUR REDEMPTION IS COMPLETE!**", embed=unban_embed)

        try:
            log_ch = discord.utils.get(message.guild.text_channels, name="public-logs")
            if log_ch:
                await log_ch.send(embed=unban_embed)
        except Exception:
            pass

    else:
        progress_embed = discord.Embed(
            title="📊 Apology Counter Progress",
            description=(
                f"<@{message.author.id}> said **sorry**!\n\n"
                f"📈 **Progress:** `{new_count} / 100` Sorries\n"
                f"⏳ **Remaining:** `{100 - new_count}` more to go!"
            ),
            color=0xF1C40F # Gold
        )
        progress_embed.set_footer(text="Keep typing 'sorry' in this channel to reach 100!")
        await message.channel.send(embed=progress_embed)

    return True
