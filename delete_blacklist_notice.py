import discord
import asyncio
import os
import traceback
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TARGET_CHANNEL_ID = 1557201912997216386
TARGET_MESSAGE_ID = 1557202304485036063

class DeleteBlacklistNoticeClient(discord.Client):
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
            print(f"Found Target Message: {msg.id}. Deleting...", flush=True)
            await msg.delete()
            print("Successfully deleted blacklist notice message!", flush=True)

        except Exception as e:
            print(f"Error deleting blacklist notice: {e}", flush=True)
            traceback.print_exc()
        finally:
            await self.close()

async def main():
    client = DeleteBlacklistNoticeClient()
    await client.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
