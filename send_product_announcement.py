import discord
import asyncio
import os
import traceback
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TARGET_CHANNEL_ID = 1556000130694512730

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
                    "**Steal A Duck [CODED]** is now officially available for purchase!\n"
                    "A complete, feature-rich Roblox base defense and duck theft engine built with enterprise modularity and full source code included."
                ),
                color=0xF1C40F # Vibrant Gold
            )

            embed.add_field(
                name="💵 Product Price",
                value="```\n500 Robux\n```",
                inline=False
            )

            embed.add_field(
                name="✨ Key Gameplay Features",
                value=(
                    "• **25+ Unique Duck Collectibles**: From `Normal Duck` & `Cool Duck` to `Glitch Duck`, `King Duck`, `Dio Duck`, `Dominus Duck`, and `Dev Duck`!\n"
                    "• **Base & Lock System**: Dynamic base assignment (`BaseManager`) with customizable security door locking (`BaseLockRemote`).\n"
                    "• **Real-Time Theft & Combat**: Infiltrate rival bases and snatch rare ducks using full hit-detection and theft mechanics (`TheftManager`).\n"
                    "• **Full Weapons & Arsenal**: 15+ pre-scripted tools including `Blackhole Slap`, `Ban Hammer`, `Lazer Gun`, `Bee Launcher`, `Flying Carpet`, `Gravity Coil`, and Slap variants (`Diamond`, `Emerald`, `Ruby`, `Gold`)."
                ),
                inline=False
            )

            embed.add_field(
                name="🌙 Events, Systems & Admin Tools",
                value=(
                    "• **Dynamic Blood Moon Event**: Sky illumination system (`RedNight`) with global timer notifications, server luck multipliers, and secret god duck spawns.\n"
                    "• **Spin Wheel & Daily Rewards**: Fully functional spin wheel (`SpinData`, `SpinModule`), playtime reward drops, and daily chest timers.\n"
                    "• **Enterprise DataStore Engine**: Production-ready data saving (`DataManager`) with auto-save, data versioning, gamepass persistence, and soft-shutdown handler.\n"
                    "• **ExtisAdmin System Included**: Pre-configured admin panel featuring player moderation (`Freeze`, `Jail`, `Fling`), command/chat logs, ban manager, and live spectate mode."
                ),
                inline=False
            )

            embed.add_field(
                name="📦 What's Included in Purchase?",
                value=(
                    "✅ Full Place File (`.rbxl`) with uncopylocked Luau scripts\n"
                    "✅ Clean UI Layouts, custom sound effects, & surface shaders\n"
                    "✅ Modular codebase ready for monetization and expansion"
                ),
                inline=False
            )

            embed.set_footer(
                text="Echo Technologies • Steal A Duck [CODED] • Product Release Announcement"
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
                msg = await channel.send(embed=embed)
                print(f"Successfully sent product announcement embed! Message ID: {msg.id}", flush=True)

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
