import discord
import asyncio
import os
import traceback
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TARGET_USER_ID = 942205155733028944
CHANNEL_NAME = "say-sorry-100-times-to-get-unblacklisted"
ROLE_NAME = "Blacklisted"

class SetupBlacklistSystemClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        super().__init__(intents=intents)

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})", flush=True)
        try:
            guild = self.guilds[0] if self.guilds else None
            if not guild:
                print("No guild found!", flush=True)
                await self.close()
                return

            print(f"Connected to Guild: {guild.name} ({guild.id})", flush=True)

            # 1. Get or Create "Blacklisted" Role
            role = discord.utils.get(guild.roles, name=ROLE_NAME)
            if not role:
                print(f"Creating role '{ROLE_NAME}'...", flush=True)
                role = await guild.create_role(
                    name=ROLE_NAME,
                    color=discord.Color.dark_red(),
                    reason="Blacklist punishment role created by system"
                )
                print(f"Created role: {role.name} ({role.id})", flush=True)
            else:
                print(f"Found existing role: {role.name} ({role.id})", flush=True)

            # 2. Get or Create punishment channel "say-sorry-100-times-to-get-unblacklisted"
            channel = discord.utils.get(guild.text_channels, name=CHANNEL_NAME)
            overrides = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False, view_channel=False),
                role: discord.PermissionOverwrite(read_messages=True, view_channel=True, send_messages=True, read_message_history=True)
            }

            if not channel:
                print(f"Creating channel '{CHANNEL_NAME}'...", flush=True)
                channel = await guild.create_text_channel(
                    name=CHANNEL_NAME,
                    overwrites=overrides,
                    topic="Say sorry 100 times to get unblacklisted from Echo Technologies.",
                    reason="Created punishment channel for blacklisted members"
                )
                print(f"Created channel: {channel.name} ({channel.id})", flush=True)
            else:
                print(f"Found existing channel: {channel.name} ({channel.id})", flush=True)
                await channel.edit(overwrites=overrides)

            # 3. Lock all other text and voice channels for the Blacklisted role
            for ch in guild.channels:
                if ch.id != channel.id:
                    try:
                        current_override = ch.overwrites_for(role)
                        if current_override.view_channel is not False or current_override.send_messages is not False:
                            await ch.set_permissions(role, view_channel=False, send_messages=False)
                    except Exception as e:
                        pass

            print("Updated channel permissions across guild for Blacklisted role.", flush=True)

            # 4. Fetch target member and assign role
            member = guild.get_member(TARGET_USER_ID)
            if not member:
                try:
                    member = await guild.fetch_member(TARGET_USER_ID)
                except Exception as e:
                    print(f"Could not fetch member {TARGET_USER_ID}: {e}", flush=True)

            if member:
                if role not in member.roles:
                    await member.add_roles(role, reason="Assigned Blacklisted punishment role")
                    print(f"Assigned '{ROLE_NAME}' role to {member} ({member.id})", flush=True)
                else:
                    print(f"{member} already has '{ROLE_NAME}' role.", flush=True)

                # Send welcome/instruction embed in the channel
                embed = discord.Embed(
                    title="🔒 BLACKLIST PUNISHMENT CHAMBER",
                    description=(
                        f"Welcome <@{TARGET_USER_ID}>,\n\n"
                        "You have been assigned the **Blacklisted** role and restricted to this channel.\n"
                        "To regain your access and get unblacklisted, you must type **`sorry`** in this channel **100 times**!\n\n"
                        "Each valid message containing `sorry` will advance your counter."
                    ),
                    color=0xE74C3C # Red
                )
                embed.add_field(
                    name="📊 Current Progress",
                    value="```\n0 / 100 Sorries\n```",
                    inline=False
                )
                embed.set_footer(text="Echo Technologies • Automated Apology System")
                embed.timestamp = discord.utils.utcnow()

                msg = await channel.send(content=f"⚠️ <@{TARGET_USER_ID}> **Read Your Requirements Below:**", embed=embed)
                print(f"Sent initial punishment embed! Message ID: {msg.id}", flush=True)

        except Exception as e:
            print(f"Error setting up blacklist system: {e}", flush=True)
            traceback.print_exc()
        finally:
            await self.close()

async def main():
    client = SetupBlacklistSystemClient()
    await client.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
