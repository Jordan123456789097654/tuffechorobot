import discord
import asyncio
import os
import traceback
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TARGET_CHANNEL_ID = 1557201912997216386

class BlacklistNoticeClient(discord.Client):
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
                title="🚨 OFFICIAL BLACKLIST NOTICE",
                description=(
                    "An official Blacklist Notice has been formally issued by **Echo Technologies** against the organization specified below.\n\n"
                    "All staff members, partners, and affiliated personnel are instructed to review the directives immediately."
                ),
                color=0x992D22 # Dark Crimson Red
            )

            embed.add_field(
                name="🏢 Blacklisted Entity",
                value="```\nAxis Core Retail\n```",
                inline=False
            )

            embed.add_field(
                name="📋 Primary Reason",
                value="```\nClassified\n```",
                inline=False
            )

            embed.add_field(
                name="🔗 Server Reference / Identifier",
                value="`1557201912997216386`",
                inline=False
            )

            embed.add_field(
                name="⚠️ Mandatory Policy Directives",
                value=(
                    "• **Zero Engagement**: All Echo staff and representatives are strictly prohibited from conducting business, partnerships, or transactions with Axis Core Retail.\n"
                    "• **Security Warning**: Do not share proprietary assets, internal documentation, or bot configurations with associated members.\n"
                    "• **Compliance & Enforcement**: Failure to adhere to this directive may lead to administrative investigation, staff removal, or blacklisting."
                ),
                inline=False
            )

            embed.set_footer(
                text="Echo Technologies • Blacklist & Security Operations"
            )
            embed.timestamp = discord.utils.utcnow()

            if isinstance(channel, discord.ForumChannel):
                thread_with_msg = await channel.create_thread(
                    name="🚨 Blacklist Notice — Axis Core Retail",
                    embed=embed,
                    content="🚨 **OFFICIAL BLACKLIST DIRECTIVE**"
                )
                print(f"Successfully created forum post thread! Thread ID: {thread_with_msg.thread.id}", flush=True)
            else:
                msg = await channel.send(content="🚨 **OFFICIAL BLACKLIST NOTICE**", embed=embed)
                print(f"Successfully sent blacklist notice embed! Message ID: {msg.id}", flush=True)

        except Exception as e:
            print(f"Error during blacklist notice dispatch: {e}", flush=True)
            traceback.print_exc()
        finally:
            await self.close()

async def main():
    client = BlacklistNoticeClient()
    await client.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
