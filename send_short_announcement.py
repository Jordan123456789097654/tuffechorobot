import discord
import asyncio
import os
import traceback
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TARGET_CHANNEL_ID = 1556000123266531428

class AnnouncementClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        super().__init__(intents=intents)

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})", flush=True)
        try:
            channel = self.get_channel(TARGET_CHANNEL_ID)
            if not channel:
                print(f"Channel not in cache, fetching channel ID {TARGET_CHANNEL_ID}...", flush=True)
                channel = await self.fetch_channel(TARGET_CHANNEL_ID)

            print(f"Target Channel Found: {channel.name} ({channel.id}) [Type: {type(channel).__name__}]", flush=True)

            embed = discord.Embed(
                title="🦆 NEW PRODUCT RELEASE: Steal A Duck [CODED]",
                description=(
                    "**Steal A Duck [CODED]** is now officially available!\n\n"
                    "🦆 **25+ Custom Ducks** (`Glitch`, `King`, `Dio`, `Dominus`, & more)\n"
                    "🏰 **Base Assignment & Lock System**\n"
                    "💥 **Base Raiding & Realtime Theft Mechanics**\n"
                    "⚔️ **15+ Weapons & Slap Arsenal** (`Blackhole Slap`, `Ban Hammer`)\n"
                    "🌕 **Dynamic Blood Moon Event & Spin Wheel**\n"
                    "🛡️ **ExtisAdmin Suite & Full DataStore Engine**\n\n"
                    "💰 **Price:** `500 Robux`\n"
                    "🛒 **View details & purchase in <#1556000130694512730>!**"
                ),
                color=0xF1C40F # Vibrant Gold
            )

            embed.set_footer(
                text="Echo Technologies • Product Release"
            )
            embed.timestamp = discord.utils.utcnow()

            if isinstance(channel, discord.ForumChannel):
                thread_with_msg = await channel.create_thread(
                    name="🦆 Steal A Duck [CODED] — 500 Robux",
                    embed=embed,
                    content="🚀 **New Official Product Available Now!**"
                )
                print(f"Successfully created forum post thread! Thread ID: {thread_with_msg.thread.id}", flush=True)
            else:
                msg = await channel.send(content="📢 **NEW PRODUCT ANNOUNCEMENT**", embed=embed)
                print(f"Successfully sent short announcement embed! Message ID: {msg.id}", flush=True)

        except Exception as e:
            print(f"Error during announcement execution: {e}", flush=True)
            traceback.print_exc()
        finally:
            await self.close()

async def main():
    client = AnnouncementClient()
    await client.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
