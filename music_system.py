import discord
from discord import app_commands, ui
from discord.ext import tasks
import asyncio
import logging
import random
import time
import imageio_ffmpeg
import yt_dlp
from typing import Optional, List, Dict, Any

logger = logging.getLogger("roblox_bot.music")

# CONSTANTS FOR MUSIC SYSTEM
MUSIC_VOICE_CHANNEL_ID = 1557213851173519460
MUSIC_TEXT_CHANNEL_ID = 1557213895041486900

# Resolve FFmpeg Executable Path
def get_ffmpeg_executable() -> str:
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        logger.warning(f"Could not get imageio_ffmpeg binary, falling back to 'ffmpeg': {e}")
        return "ffmpeg"

FFMPEG_EXECUTABLE = get_ffmpeg_executable()
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

YTDL_AUTOCOMPLETE_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'extract_flat': True,
    'skip_download': True,
    'quiet': True,
    'no_warnings': True,
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class Track:
    def __init__(self, title: str, stream_url: str, webpage_url: str, duration: int, thumbnail: str, uploader: str, requester: discord.Member):
        self.title = title
        self.stream_url = stream_url
        self.webpage_url = webpage_url
        self.duration = duration  # seconds
        self.thumbnail = thumbnail
        self.uploader = uploader
        self.requester = requester
        self.added_at = time.time()

    def format_duration(self) -> str:
        if not self.duration:
            return "LIVE Stream"
        mins = self.duration // 60
        secs = self.duration % 60
        return f"{mins}:{secs:02d}"

class MusicPlayer:
    def __init__(self, bot):
        self.bot = bot
        self.queue: List[Track] = []
        self.current: Optional[Track] = None
        self.voice_client: Optional[discord.VoiceClient] = None
        self.volume: float = 0.5  # 0.0 to 1.0
        self.loop_mode: str = "off"  # "off", "track", "queue"
        self.start_time: float = 0.0
        self.paused: bool = False
        self.panel_message: Optional[discord.Message] = None
        self.lock = asyncio.Lock()

    def is_playing(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_playing()

    def is_paused(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_paused()

    async def play_next(self):
        async with self.lock:
            if not self.voice_client or not self.voice_client.is_connected():
                return

            if self.loop_mode == "track" and self.current:
                next_track = self.current
            elif self.queue:
                next_track = self.queue.pop(0)
                if self.loop_mode == "queue" and self.current:
                    self.queue.append(self.current)
            else:
                self.current = None
                await self.update_panel()
                return

            self.current = next_track
            self.start_time = time.time()
            self.paused = False

            try:
                stream_url = next_track.stream_url
                if not stream_url or "manifest" in stream_url:
                    loop = asyncio.get_event_loop()
                    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(next_track.webpage_url, download=False))
                    stream_url = data.get('url', next_track.stream_url)

                audio_source = discord.FFmpegPCMAudio(stream_url, executable=FFMPEG_EXECUTABLE, **FFMPEG_OPTIONS)
                transformed_source = discord.PCMVolumeTransformer(audio_source, volume=self.volume)

                def after_playing(error):
                    if error:
                        logger.error(f"Playback error: {error}")
                    coro = self.play_next()
                    fut = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
                    try:
                        fut.result()
                    except Exception as ex:
                        logger.error(f"Error triggering next track: {ex}")

                self.voice_client.play(transformed_source, after=after_playing)
                await self.update_panel()
            except Exception as e:
                logger.error(f"Error playing track '{next_track.title}': {e}")
                await self.play_next()

    async def add_track(self, track: Track):
        self.queue.append(track)
        if not self.is_playing() and not self.is_paused():
            await self.play_next()
        else:
            await self.update_panel()

    async def skip(self):
        if self.voice_client and (self.is_playing() or self.is_paused()):
            self.voice_client.stop()

    async def pause(self):
        if self.voice_client and self.is_playing():
            self.voice_client.pause()
            self.paused = True
            await self.update_panel()

    async def resume(self):
        if self.voice_client and self.is_paused():
            self.voice_client.resume()
            self.paused = False
            await self.update_panel()

    async def stop(self):
        self.queue.clear()
        self.current = None
        if self.voice_client:
            self.voice_client.stop()
        await self.update_panel()

    async def shuffle(self):
        random.shuffle(self.queue)
        await self.update_panel()

    async def update_panel(self):
        channel = self.bot.get_channel(MUSIC_TEXT_CHANNEL_ID)
        if not channel:
            return

        embed = build_music_panel_embed(self)
        view = MusicControlView(self)

        try:
            if self.panel_message:
                await self.panel_message.edit(embed=embed, view=view)
            else:
                async for msg in channel.history(limit=10):
                    if msg.author == self.bot.user and msg.embeds and "Music Control Panel" in (msg.embeds[0].title or ""):
                        self.panel_message = msg
                        await msg.edit(embed=embed, view=view)
                        return
                self.panel_message = await channel.send(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error updating music channel panel: {e}")

global_music_player: Optional[MusicPlayer] = None

def get_music_player(bot) -> MusicPlayer:
    global global_music_player
    if global_music_player is None:
        global_music_player = MusicPlayer(bot)
    return global_music_player

async def music_play_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    if not current or len(current.strip()) < 2:
        return [
            app_commands.Choice(name="🎵 Type a song name or paste a YouTube / Spotify / SoundCloud URL...", value="https://www.youtube.com/watch?v=kffacxfA7G4")
        ]

    query = current.strip()

    if query.startswith("http://") or query.startswith("https://"):
        return [app_commands.Choice(name=f"🔗 Play Direct URL: {query[:80]}", value=query)]

    choices = []
    try:
        loop = asyncio.get_event_loop()
        def search_fn():
            with yt_dlp.YoutubeDL(YTDL_AUTOCOMPLETE_OPTIONS) as ydl:
                return ydl.extract_info(f"ytsearch10:{query}", download=False)

        data = await loop.run_in_executor(None, search_fn)
        entries = data.get('entries', []) if data else []

        for entry in entries:
            if not entry:
                continue
            title = entry.get('title', 'Unknown Title')
            duration = entry.get('duration')
            dur_str = f"{int(duration)//60}:{int(duration)%60:02d}" if duration else "LIVE"
            webpage_url = entry.get('webpage_url') or entry.get('url') or f"https://www.youtube.com/watch?v={entry.get('id')}"

            label = f"{title} ({dur_str})"
            if len(label) > 100:
                label = label[:97] + "..."

            choices.append(app_commands.Choice(name=label, value=webpage_url))
            if len(choices) >= 10:
                break
    except Exception as e:
        logger.error(f"Error in music autocomplete: {e}")

    if not choices:
        choices.append(app_commands.Choice(name=f"🔍 Search YouTube for: '{query[:80]}'", value=f"ytsearch:{query}"))

    return choices

async def extract_tracks(query: str, requester: discord.Member) -> List[Track]:
    loop = asyncio.get_event_loop()
    target_query = query if (query.startswith("http://") or query.startswith("https://") or query.startswith("ytsearch:")) else f"ytsearch:{query}"

    def do_extract():
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            return ydl.extract_info(target_query, download=False)

    data = await loop.run_in_executor(None, do_extract)

    tracks = []
    if 'entries' in data and data['entries']:
        entries = data['entries']
    else:
        entries = [data]

    for entry in entries:
        if not entry:
            continue
        title = entry.get('title', 'Unknown Title')
        stream_url = entry.get('url') or ''
        webpage_url = entry.get('webpage_url') or entry.get('url') or f"https://www.youtube.com/watch?v={entry.get('id')}"
        duration = int(entry.get('duration', 0))
        thumbnail = entry.get('thumbnail') or ""
        uploader = entry.get('uploader') or entry.get('channel') or "Unknown Artist"

        tracks.append(Track(
            title=title,
            stream_url=stream_url,
            webpage_url=webpage_url,
            duration=duration,
            thumbnail=thumbnail,
            uploader=uploader,
            requester=requester
        ))

    return tracks

def build_music_panel_embed(player: MusicPlayer) -> discord.Embed:
    embed = discord.Embed(
        title="🎵 Echo Technologies • Official 24/7 Music Control Panel",
        color=0x9B59B6
    )

    if player.current:
        cur = player.current
        elapsed = int(time.time() - player.start_time) if not player.paused else 0
        dur_str = cur.format_duration()

        if cur.duration > 0:
            pct = min(1.0, max(0.0, elapsed / cur.duration))
            bar_len = 12
            filled = int(pct * bar_len)
            bar = "🔘" + "━" * filled + "🔘" + "─" * (bar_len - filled)
        else:
            bar = "🔴 Live Audio Stream"

        status_icon = "⏸️ Paused" if player.paused else "▶️ Playing"

        embed.description = (
            f"### {status_icon} [{cur.title}]({cur.webpage_url})\n"
            f"**Artist / Channel:** `{cur.uploader}`\n"
            f"**Requested By:** {cur.requester.mention}\n\n"
            f"`{bar}` `{elapsed//60}:{elapsed%60:02d} / {dur_str}`"
        )
        if cur.thumbnail:
            embed.set_thumbnail(url=cur.thumbnail)
    else:
        embed.description = (
            "**No track currently playing.**\n\n"
            "Use **/play <song or URL>** in chat to add music to the queue!\n"
            "Supports YouTube, YouTube Music, Spotify, SoundCloud, and direct stream links."
        )

    if player.queue:
        queue_text = ""
        for idx, t in enumerate(player.queue[:5], start=1):
            queue_text += f"**{idx}.** [{t.title}]({t.webpage_url}) — `{t.format_duration()}` (by {t.requester.display_name})\n"
        if len(player.queue) > 5:
            queue_text += f"*...and {len(player.queue) - 5} more tracks in queue.*"
        embed.add_field(name=f"📜 Upcoming Queue ({len(player.queue)} tracks)", value=queue_text, inline=False)
    else:
        embed.add_field(name="📜 Upcoming Queue", value="*Queue is currently empty.*", inline=False)

    loop_label = player.loop_mode.capitalize()
    vol_pct = int(player.volume * 100)
    embed.add_field(
        name="⚙️ Control Settings",
        value=f"**Volume:** `{vol_pct}%` | **Loop Mode:** `{loop_label}` | **Voice Channel:** <#{MUSIC_VOICE_CHANNEL_ID}>",
        inline=False
    )

    embed.set_footer(text="Echo Technologies Official 24/7 Jukebox • Controls Below")
    embed.timestamp = discord.utils.utcnow()
    return embed

class MusicControlView(ui.View):
    def __init__(self, player: MusicPlayer):
        super().__init__(timeout=None)
        self.player = player

    @ui.button(label="Play/Pause", style=discord.ButtonStyle.primary, emoji="⏯️", custom_id="music_pause_toggle")
    async def pause_toggle(self, interaction: discord.Interaction, button: ui.Button):
        if self.player.is_paused():
            await self.player.resume()
            await interaction.response.send_message("▶️ Playback resumed.", ephemeral=True)
        elif self.player.is_playing():
            await self.player.pause()
            await interaction.response.send_message("⏸️ Playback paused.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)

    @ui.button(label="Skip", style=discord.ButtonStyle.secondary, emoji="⏭️", custom_id="music_skip")
    async def skip_track(self, interaction: discord.Interaction, button: ui.Button):
        if self.player.is_playing() or self.player.is_paused():
            await self.player.skip()
            await interaction.response.send_message("⏭️ Skipped current track.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nothing to skip.", ephemeral=True)

    @ui.button(label="Stop", style=discord.ButtonStyle.danger, emoji="⏹️", custom_id="music_stop")
    async def stop_music(self, interaction: discord.Interaction, button: ui.Button):
        await self.player.stop()
        await interaction.response.send_message("⏹️ Playback stopped and queue cleared.", ephemeral=True)

    @ui.button(label="Shuffle", style=discord.ButtonStyle.secondary, emoji="🔀", custom_id="music_shuffle")
    async def shuffle_queue(self, interaction: discord.Interaction, button: ui.Button):
        if self.player.queue:
            await self.player.shuffle()
            await interaction.response.send_message("🔀 Queue shuffled.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Queue is empty.", ephemeral=True)

    @ui.button(label="Loop", style=discord.ButtonStyle.secondary, emoji="🔁", custom_id="music_loop")
    async def toggle_loop(self, interaction: discord.Interaction, button: ui.Button):
        modes = ["off", "track", "queue"]
        idx = (modes.index(self.player.loop_mode) + 1) % len(modes)
        self.player.loop_mode = modes[idx]
        await self.player.update_panel()
        await interaction.response.send_message(f"🔁 Loop mode set to: **{self.player.loop_mode.capitalize()}**", ephemeral=True)

    @ui.button(label="Queue", style=discord.ButtonStyle.secondary, emoji="📜", custom_id="music_show_queue")
    async def show_queue(self, interaction: discord.Interaction, button: ui.Button):
        if not self.player.queue:
            await interaction.response.send_message("📜 Queue is currently empty.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📜 Full Music Queue",
            color=0x3498DB
        )
        description = ""
        for idx, track in enumerate(self.player.queue[:20], start=1):
            description += f"**{idx}.** [{track.title}]({track.webpage_url}) — `{track.format_duration()}` (by {track.requester.mention})\n"
        if len(self.player.queue) > 20:
            description += f"\n*...and {len(self.player.queue) - 20} more tracks.*"

        embed.description = description
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def ensure_voice_connection(bot):
    """Auto-connects and stays in the 24/7 music voice channel 1557213851173519460."""
    try:
        channel = bot.get_channel(MUSIC_VOICE_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            logger.warning(f"Music voice channel {MUSIC_VOICE_CHANNEL_ID} not found.")
            return

        player = get_music_player(bot)
        if player.voice_client is None or not player.voice_client.is_connected():
            logger.info(f"Connecting to 24/7 Music Voice Channel: {channel.name} ({channel.id})...")
            player.voice_client = await channel.connect(reconnect=True, timeout=30.0)
            await player.update_panel()
    except Exception as e:
        logger.error(f"Error ensuring music voice connection: {e}")

def register_music_commands(bot):
    """Registers music slash commands to the bot command tree."""

    @bot.tree.command(name="play", description="Play a song or playlist in the 24/7 music channel.")
    @app_commands.describe(input="Search song name or paste YouTube / Spotify / SoundCloud URL")
    @app_commands.autocomplete(input=music_play_autocomplete)
    async def play_command(interaction: discord.Interaction, input: str):
        await interaction.response.defer(ephemeral=False)
        await ensure_voice_connection(bot)

        player = get_music_player(bot)
        member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)

        try:
            tracks = await extract_tracks(input, member)
            if not tracks:
                await interaction.followup.send("❌ Could not find any audio for that search query.", ephemeral=True)
                return

            if len(tracks) == 1:
                track = tracks[0]
                await player.add_track(track)
                await interaction.followup.send(f"🎵 Added **[{track.title}]({track.webpage_url})** (`{track.format_duration()}`) to the queue!")
            else:
                for t in tracks:
                    await player.add_track(t)
                await interaction.followup.send(f"🎶 Added **{len(tracks)} tracks** from playlist to the queue!")
        except Exception as e:
            logger.error(f"Error in /play command: {e}")
            await interaction.followup.send(f"❌ Error loading track: `{e}`", ephemeral=True)

    @bot.tree.command(name="skip", description="Skip the currently playing song.")
    async def skip_command(interaction: discord.Interaction):
        player = get_music_player(bot)
        if player.is_playing() or player.is_paused():
            await player.skip()
            await interaction.response.send_message("⏭️ Skipped current track.")
        else:
            await interaction.response.send_message("❌ Nothing is playing to skip.", ephemeral=True)

    @bot.tree.command(name="pause", description="Pause playback.")
    async def pause_command(interaction: discord.Interaction):
        player = get_music_player(bot)
        if player.is_playing():
            await player.pause()
            await interaction.response.send_message("⏸️ Playback paused.")
        else:
            await interaction.response.send_message("❌ Nothing is playing.", ephemeral=True)

    @bot.tree.command(name="resume", description="Resume paused playback.")
    async def resume_command(interaction: discord.Interaction):
        player = get_music_player(bot)
        if player.is_paused():
            await player.resume()
            await interaction.response.send_message("▶️ Playback resumed.")
        else:
            await interaction.response.send_message("❌ Playback is not paused.", ephemeral=True)

    @bot.tree.command(name="stop", description="Stop music and clear the queue.")
    async def stop_command(interaction: discord.Interaction):
        player = get_music_player(bot)
        await player.stop()
        await interaction.response.send_message("⏹️ Playback stopped and queue cleared.")

    @bot.tree.command(name="queue", description="View the current music queue.")
    async def queue_command(interaction: discord.Interaction):
        player = get_music_player(bot)
        embed = build_music_panel_embed(player)
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="nowplaying", description="View the currently playing song.")
    async def nowplaying_command(interaction: discord.Interaction):
        player = get_music_player(bot)
        embed = build_music_panel_embed(player)
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="volume", description="Set playback volume (1-100%).")
    @app_commands.describe(level="Volume level from 1 to 100")
    async def volume_command(interaction: discord.Interaction, level: int):
        player = get_music_player(bot)
        level = max(1, min(100, level))
        player.volume = level / 100.0

        if player.voice_client and player.voice_client.source:
            try:
                player.voice_client.source.volume = player.volume
            except Exception:
                pass

        await player.update_panel()
        await interaction.response.send_message(f"🔊 Volume set to **{level}%**.")

    @bot.tree.command(name="loop", description="Set loop mode (off, track, queue).")
    @app_commands.describe(mode="Loop mode: off, track, or queue")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Track (Repeat single song)", value="track"),
        app_commands.Choice(name="Queue (Repeat entire queue)", value="queue")
    ])
    async def loop_command(interaction: discord.Interaction, mode: app_commands.Choice[str]):
        player = get_music_player(bot)
        player.loop_mode = mode.value
        await player.update_panel()
        await interaction.response.send_message(f"🔁 Loop mode set to **{mode.name}**.")
