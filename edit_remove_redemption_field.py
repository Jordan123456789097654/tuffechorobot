import discord
import asyncio
import os
import traceback
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TARGET_CHANNEL_ID = 1557201912997216386
TARGET_MESSAGE_ID = 1557204104038846549
OWNER_ID = 942205155733028944

class RemoveRedemptionFieldClient(discord.Client):
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

            print(f"Target Channel Found: {channel.name} ({channel.id})", flush=True)

            msg = await channel.fetch_message(TARGET_MESSAGE_ID)
            print(f"Found Target Message: {msg.id}. Removing redemption field...", flush=True)

            embed = discord.Embed(
                title="🚨 OFFICIAL BLACKLIST NOTICE",
                description=(
                    "An official Blacklist Notice has been formally issued by **Echo Technologies Management**.\n\n"
                    "All staff members, partners, and affiliated personnel are required to review and adhere to the directives below immediately."
                ),
                color=0x992D22 # Dark Crimson Red
            )

            embed.set_thumbnail(url="https://cdn.discordapp.com/embed/avatars/0.png")

            embed.add_field(
                name="🏢 Blacklisted Entity",
                value="```\nAxis Core Retail\n```",
                inline=True
            )

            embed.add_field(
                name="🔴 Severity Level",
                value="`TIER 1 (CRITICAL THREAT)`",
                inline=True
            )

            embed.add_field(
                name="👤 Key Associated Owner",
                value=f"<@{OWNER_ID}> (`{OWNER_ID}`)",
                inline=False
            )

            embed.add_field(
                name="🔗 Server Reference / Identifier",
                value="`1557201912997216386`",
                inline=False
            )

            embed.add_field(
                name="📋 Primary Offenses & Violations",
                value=(
                    "• **Asset Leaking**: Unauthorized distribution and leaking of proprietary assets.\n"
                    "• **Intellectual Property Theft**: Stealing game concepts, design ideas, and technical frameworks.\n"
                    "• **Security Breach**: Malicious attempts to compromise organizational intellectual property."
                ),
                inline=False
            )

            embed.add_field(
                name="⚠️ Enforceable Directives & Policy Rules",
                value=(
                    "• **Dual-Affiliation Prohibition**: Echo staff members affiliated with or employed by Axis Core Retail are subject to **immediate termination**.\n"
                    "• **Product & License Revocation**: All product licenses, scripts, and service access granted to associated personnel are **permanently voided**.\n"
                    "• **Zero Engagement Policy**: Strict prohibition on all business transactions, partnerships, or communications.\n"
                    "• **System Blacklist**: Automatic blacklisting across all Echo Technologies Discord servers, games, and verification systems."
                ),
                inline=False
            )

            embed.set_footer(
                text="Echo Technologies • Blacklist & Security Enforcement Division"
            )
            embed.timestamp = discord.utils.utcnow()

            await msg.edit(content="🚨 **OFFICIAL BLACKLIST NOTICE | TIER 1 DIRECTIVE**", embed=embed)
            print(f"Successfully edited blacklist notice message ID: {msg.id}", flush=True)

        except Exception as e:
            print(f"Error editing blacklist notice: {e}", flush=True)
            traceback.print_exc()
        finally:
            await self.close()

async def main():
    client = RemoveRedemptionFieldClient()
    await client.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
