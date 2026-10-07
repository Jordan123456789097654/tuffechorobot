import discord
from discord import app_commands, ui
from discord.ext import tasks
import asyncio
import aiohttp
import logging
import random
import time
import json
import urllib.parse
import imageio_ffmpeg
import yt_dlp
from typing import Optional, List, Dict, Any, Set

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

AUDIO_FILTERS: Dict[str, str] = {
    "off": "",
    "bassboost": "equalizer=f=60:width_type=h:width=50:g=12",
    "nightcore": "asetrate=44100*1.25,aresample=44100,atempo=1.05",
    "vaporwave": "asetrate=44100*0.8,aresample=44100,atempo=0.9",
    "8d": "apulsator=hz=0.125",
    "reverb": "aecho=0.8:0.88:60:0.4"
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
    'no_color': True,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'ios', 'mweb', 'tv'],
            'player_skip': ['webpage', 'configs']
        }
    }
}

YTDL_AUTOCOMPLETE_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'extract_flat': True,
    'skip_download': True,
    'quiet': True,
    'no_warnings': True,
    'no_color': True,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'ios', 'mweb', 'tv'],
            'player_skip': ['webpage', 'configs']
        }
    }
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "webpage_url": self.webpage_url,
            "duration": self.duration,
            "thumbnail": self.thumbnail,
            "uploader": self.uploader
        }

class MusicPlayer:
    def __init__(self, bot):
        self.bot = bot
        self.queue: List[Track] = []
        self.current: Optional[Track] = None
        self.voice_client: Optional[discord.VoiceClient] = None
        self.volume: float = 0.5  # 0.0 to 1.0
        self.loop_mode: str = "off"  # "off", "track", "queue"
        self.active_filter: str = "off"
        self.autoplay: bool = True
        self.start_time: float = 0.0
        self.seek_offset: int = 0
        self.paused: bool = False
        self.panel_message: Optional[discord.Message] = None
        self.voteskip_users: Set[int] = set()
        self.lock = asyncio.Lock()

    def is_playing(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_playing()

    def is_paused(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_paused()

    def get_ffmpeg_options(self, seek_sec: int = 0) -> Dict[str, str]:
        opts = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
        if seek_sec > 0:
            opts['before_options'] += f' -ss {seek_sec}'

        filter_str = AUDIO_FILTERS.get(self.active_filter, "")
        if filter_str:
            opts['options'] += f' -af "{filter_str}"'
        return opts

    async def play_next(self):
        async with self.lock:
            if not self.voice_client or not self.voice_client.is_connected():
                return

            self.voteskip_users.clear()
            self.seek_offset = 0

            if self.loop_mode == "track" and self.current:
                next_track = self.current
            elif self.queue:
                next_track = self.queue.pop(0)
                if self.loop_mode == "queue" and self.current:
                    self.queue.append(self.current)
            elif self.autoplay and self.current:
                # Autoplay recommendation logic
                try:
                    logger.info(f"Autoplay triggered for: {self.current.title}")
                    rec_query = f"ytsearch3:related to {self.current.title}"
                    rec_tracks = await extract_tracks(rec_query, self.bot.user)
                    if rec_tracks:
                        next_track = rec_tracks[0]
                    else:
                        self.current = None
                        await self.update_panel()
                        return
                except Exception as e:
                    logger.error(f"Autoplay recommendation error: {e}")
                    self.current = None
                    await self.update_panel()
                    return
            else:
                self.current = None
                await self.update_panel()
                return

            self.current = next_track
            self.start_time = time.time()
            self.paused = False

            await self.start_ffmpeg_stream(next_track, seek_sec=0)

    async def start_ffmpeg_stream(self, track: Track, seek_sec: int = 0):
        try:
            stream_url = track.stream_url
            if not stream_url or "manifest" in stream_url:
                fresh_tracks = await extract_tracks(track.webpage_url, track.requester)
                if fresh_tracks and fresh_tracks[0].stream_url:
                    stream_url = fresh_tracks[0].stream_url

            ffmpeg_opts = self.get_ffmpeg_options(seek_sec=seek_sec)
            audio_source = discord.FFmpegPCMAudio(stream_url, executable=FFMPEG_EXECUTABLE, **ffmpeg_opts)
            transformed_source = discord.PCMVolumeTransformer(audio_source, volume=self.volume)

            if self.voice_client.is_playing() or self.voice_client.is_paused():
                self.voice_client.stop()

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
            logger.error(f"Error starting FFmpeg stream for '{track.title}': {e}")
            await self.play_next()

    async def seek(self, target_seconds: int):
        if not self.current or not self.voice_client:
            return
        target_seconds = max(0, min(self.current.duration if self.current.duration else 3600, target_seconds))
        self.seek_offset = target_seconds
        self.start_time = time.time() - target_seconds
        await self.start_ffmpeg_stream(self.current, seek_sec=target_seconds)

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
            try:
                channel = await self.bot.fetch_channel(MUSIC_TEXT_CHANNEL_ID)
            except Exception as ex:
                logger.warning(f"Could not fetch music text channel {MUSIC_TEXT_CHANNEL_ID}: {ex}")
                channel = None
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
    target_query = query if (query.startswith("http://") or query.startswith("https://") or query.startswith("ytsearch:") or query.startswith("scsearch:")) else f"ytsearch:{query}"

    clients_to_try = [
        ['ios', 'android', 'mweb'],
        ['android', 'tv'],
        ['web', 'mweb']
    ]

    data = None
    last_error = None

    for client_list in clients_to_try:
        opts = dict(YTDL_OPTIONS)
        opts['extractor_args'] = {
            'youtube': {
                'player_client': client_list,
                'player_skip': ['webpage', 'configs']
            }
        }
        try:
            def do_extract(current_opts=opts):
                with yt_dlp.YoutubeDL(current_opts) as ydl:
                    return ydl.extract_info(target_query, download=False)

            data = await loop.run_in_executor(None, do_extract)
            if data:
                break
        except Exception as e:
            last_error = e

    if not data and not query.startswith("http://") and not query.startswith("https://"):
        try:
            sc_query = f"scsearch:{query}"
            def do_sc_extract():
                with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
                    return ydl.extract_info(sc_query, download=False)
            data = await loop.run_in_executor(None, do_sc_extract)
        except Exception as sc_err:
            logger.warning(f"SoundCloud fallback failed: {sc_err}")

    if not data:
        import re
        err_msg = str(last_error) if last_error else "Could not extract track data."
        err_msg = re.sub(r'\x1b\[[0-9;]*m', '', err_msg)
        raise Exception(err_msg)

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

async def fetch_lyrics(query: str) -> Optional[Dict[str, str]]:
    """Fetches plain song lyrics via public lrclib API."""
    encoded = urllib.parse.quote(query)
    url = f"https://lrclib.net/api/search?q={encoded}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data:
                        first = data[0]
                        lyrics = first.get('plainLyrics') or first.get('syncedLyrics') or ''
                        if lyrics:
                            return {
                                "title": f"{first.get('trackName', 'Unknown')} - {first.get('artistName', 'Unknown')}",
                                "lyrics": lyrics
                            }
    except Exception as e:
        logger.error(f"Error fetching lyrics for '{query}': {e}")
    return None

def build_music_panel_embed(player: MusicPlayer) -> discord.Embed:
    embed = discord.Embed(
        title="🎵 Echo Technologies • Official 24/7 Music Control Panel",
        color=0x9B59B6
    )

    if player.current:
        cur = player.current
        elapsed = (int(time.time() - player.start_time) + player.seek_offset) if not player.paused else player.seek_offset
        dur_str = cur.format_duration()

        if cur.duration > 0:
            pct = min(1.0, max(0.0, elapsed / cur.duration))
            bar_len = 12
            filled = int(pct * bar_len)
            bar = "🔘" + "━" * filled + "🔘" + "─" * (bar_len - filled)
        else:
            bar = "🔴 Live Audio Stream"

        status_icon = "⏸️ Paused" if player.paused else "▶️ Playing"
        req_mention = cur.requester.mention if isinstance(cur.requester, (discord.Member, discord.User)) else "@Bot System"

        embed.description = (
            f"### {status_icon} [{cur.title}]({cur.webpage_url})\n"
            f"**Artist / Channel:** `{cur.uploader}`\n"
            f"**Requested By:** {req_mention}\n\n"
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
            req_name = t.requester.display_name if isinstance(t.requester, (discord.Member, discord.User)) else "System"
            queue_text += f"**{idx}.** [{t.title}]({t.webpage_url}) — `{t.format_duration()}` (by {req_name})\n"
        if len(player.queue) > 5:
            queue_text += f"*...and {len(player.queue) - 5} more tracks in queue.*"
        embed.add_field(name=f"📜 Upcoming Queue ({len(player.queue)} tracks)", value=queue_text, inline=False)
    else:
        embed.add_field(name="📜 Upcoming Queue", value="*Queue is currently empty.*", inline=False)

    loop_label = player.loop_mode.capitalize()
    filter_label = player.active_filter.capitalize()
    auto_label = "Enabled 📻" if player.autoplay else "Disabled 🛑"
    vol_pct = int(player.volume * 100)

    embed.add_field(
        name="⚙️ Control Settings & Audio EQ",
        value=(
            f"**Volume:** `{vol_pct}%` | **Loop Mode:** `{loop_label}` | **Autoplay:** `{auto_label}`\n"
            f"**Audio EQ Filter:** `{filter_label}` | **Voice Channel:** <#{MUSIC_VOICE_CHANNEL_ID}>"
        ),
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

    @ui.button(label="Autoplay", style=discord.ButtonStyle.secondary, emoji="📻", custom_id="music_autoplay_toggle")
    async def toggle_autoplay(self, interaction: discord.Interaction, button: ui.Button):
        self.player.autoplay = not self.player.autoplay
        await self.player.update_panel()
        status_str = "Enabled 📻 (Will auto-queue recommended songs when queue ends)" if self.player.autoplay else "Disabled 🛑"
        await interaction.response.send_message(f"📻 Autoplay Mode set to **{status_str}**", ephemeral=True)

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
            req_name = track.requester.mention if isinstance(track.requester, (discord.Member, discord.User)) else "@System"
            description += f"**{idx}.** [{track.title}]({track.webpage_url}) — `{track.format_duration()}` (by {req_name})\n"
        if len(self.player.queue) > 20:
            description += f"\n*...and {len(self.player.queue) - 20} more tracks.*"

        embed.description = description
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def ensure_voice_connection(bot):
    """Auto-connects and stays in the 24/7 music voice channel 1557213851173519460."""
    try:
        channel = bot.get_channel(MUSIC_VOICE_CHANNEL_ID)
        if not channel:
            try:
                channel = await bot.fetch_channel(MUSIC_VOICE_CHANNEL_ID)
            except Exception as ex:
                logger.warning(f"Could not fetch music voice channel {MUSIC_VOICE_CHANNEL_ID}: {ex}")
                channel = None

        if not channel or not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            logger.warning(f"Music voice channel {MUSIC_VOICE_CHANNEL_ID} not found or not a voice channel.")
            return

        player = get_music_player(bot)
        if player.voice_client is None or not player.voice_client.is_connected():
            logger.info(f"Connecting to 24/7 Music Voice Channel: {channel.name} ({channel.id})...")
            guild = channel.guild
            if guild.voice_client:
                try:
                    await guild.voice_client.disconnect(force=True)
                    await asyncio.sleep(0.5)
                except Exception as ex:
                    logger.debug(f"Disconnect previous voice client exception: {ex}")

            player.voice_client = await channel.connect(reconnect=True, timeout=30.0)
        
        await player.update_panel()
    except Exception as e:
        logger.error(f"Error ensuring music voice connection: {e}")

@tasks.loop(seconds=15)
async def voice_keepalive_loop(bot):
    """Background keep-alive loop to enforce 24/7 voice channel presence."""
    try:
        await ensure_voice_connection(bot)
    except Exception as e:
        logger.error(f"Error in voice keepalive loop: {e}")

async def debug_music_system(bot, target_channel: Optional[discord.TextChannel] = None) -> str:
    import traceback
    lines = ["🔍 **Echo Technologies • Music System Telemetry & Diagnostics**\n"]

    # 1. Check PyNaCl voice support
    try:
        import nacl
        lines.append("✅ **PyNaCl / Voice Library**: Installed & Loaded")
    except Exception as e:
        lines.append(f"❌ **PyNaCl / Voice Library ERROR**: `{e}`")

    # 2. Check Voice Channel 1557213851173519460
    vc_obj = bot.get_channel(MUSIC_VOICE_CHANNEL_ID)
    if not vc_obj:
        try:
            vc_obj = await bot.fetch_channel(MUSIC_VOICE_CHANNEL_ID)
            lines.append(f"✅ **Voice Channel Fetched**: `{vc_obj.name}` (`{vc_obj.id}`)")
        except Exception as e:
            lines.append(f"❌ **Voice Channel 1557213851173519460 Fetch ERROR**: `{e}`")
    else:
        lines.append(f"✅ **Voice Channel Found**: `{vc_obj.name}` (`{vc_obj.id}`)")

    # 3. Check Text Channel 1557213895041486900
    txt_obj = bot.get_channel(MUSIC_TEXT_CHANNEL_ID)
    if not txt_obj:
        try:
            txt_obj = await bot.fetch_channel(MUSIC_TEXT_CHANNEL_ID)
            lines.append(f"✅ **Text Channel Fetched**: `{txt_obj.name}` (`{txt_obj.id}`)")
        except Exception as e:
            lines.append(f"❌ **Text Channel 1557213895041486900 Fetch ERROR**: `{e}`")
    else:
        lines.append(f"✅ **Text Channel Found**: `{txt_obj.name}` (`{txt_obj.id}`)")

    # 4. Check Bot Voice Permissions
    if vc_obj and hasattr(vc_obj, 'guild') and vc_obj.guild:
        me = vc_obj.guild.me
        perms = vc_obj.permissions_for(me) if me else None
        if perms:
            lines.append(f"🔒 **Permissions**: Connect=`{perms.connect}`, Speak=`{perms.speak}`, ViewChannel=`{perms.view_channel}`")

    # 5. Connection Test
    if vc_obj and isinstance(vc_obj, (discord.VoiceChannel, discord.StageChannel)):
        player = get_music_player(bot)
        try:
            if player.voice_client and player.voice_client.is_connected():
                lines.append(f"🟢 **Voice State**: Currently Connected to `{player.voice_client.channel.name}`")
            else:
                lines.append("⏳ **Attempting Connection Test...**")
                if vc_obj.guild.voice_client:
                    try:
                        await vc_obj.guild.voice_client.disconnect(force=True)
                        await asyncio.sleep(0.5)
                    except Exception:
                        pass
                player.voice_client = await vc_obj.connect(reconnect=True, timeout=15.0)
                lines.append(f"🎉 **Connection SUCCESS!** Bot connected to `{vc_obj.name}`")
                await player.update_panel()
        except Exception as e:
            tb_str = traceback.format_exc()
            logger.error(f"Debug Music Connection Failure:\n{tb_str}")
            lines.append(f"❌ **Connection FAILURE**: `{type(e).__name__}: {e}`")

    result_msg = "\n".join(lines)
    if target_channel:
        await target_channel.send(result_msg)
    return result_msg

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

    @bot.tree.command(name="filter", description="Apply Audio EQ filters (Bass Boost, Nightcore, Vaporwave, 8D Audio, Reverb).")
    @app_commands.describe(type="Audio filter effect to apply")
    @app_commands.choices(type=[
        app_commands.Choice(name="Off / Normal", value="off"),
        app_commands.Choice(name="🔊 Bass Boost", value="bassboost"),
        app_commands.Choice(name="⚡ Nightcore (Speed + Pitch)", value="nightcore"),
        app_commands.Choice(name="🐢 Vaporwave (Slowed + Reverb)", value="vaporwave"),
        app_commands.Choice(name="🎧 8D Spatial Audio Panning", value="8d"),
        app_commands.Choice(name="🏛️ Echo / Reverb", value="reverb")
    ])
    async def filter_command(interaction: discord.Interaction, type: app_commands.Choice[str]):
        player = get_music_player(bot)
        player.active_filter = type.value
        if player.current and (player.is_playing() or player.is_paused()):
            elapsed = int(time.time() - player.start_time) + player.seek_offset
            await player.seek(elapsed)
        else:
            await player.update_panel()
        await interaction.response.send_message(f"🎛️ Audio EQ filter set to **{type.name}**.")

    @bot.tree.command(name="autoplay", description="Toggle 24/7 Autoplay recommendation mode.")
    @app_commands.describe(mode="Enable or disable 24/7 autoplay recommendations")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Enabled (Auto-queue related songs when queue ends)", value="on"),
        app_commands.Choice(name="Disabled (Stop when queue ends)", value="off")
    ])
    async def autoplay_command(interaction: discord.Interaction, mode: app_commands.Choice[str]):
        player = get_music_player(bot)
        player.autoplay = (mode.value == "on")
        await player.update_panel()
        status_label = "Enabled 📻" if player.autoplay else "Disabled 🛑"
        await interaction.response.send_message(f"📻 Autoplay Mode set to **{status_label}**.")

    @bot.tree.command(name="lyrics", description="Fetch live lyrics for the currently playing song or search query.")
    @app_commands.describe(query="Song title or artist (defaults to current track)")
    async def lyrics_command(interaction: discord.Interaction, query: Optional[str] = None):
        await interaction.response.defer()
        player = get_music_player(bot)

        target_query = query
        if not target_query and player.current:
            target_query = f"{player.current.title} {player.current.uploader}"

        if not target_query:
            await interaction.followup.send("❌ No track currently playing. Please specify a song title!", ephemeral=True)
            return

        res = await fetch_lyrics(target_query)
        if not res or not res.get("lyrics"):
            await interaction.followup.send(f"❌ No lyrics found for **`{target_query}`**.", ephemeral=True)
            return

        lyrics_text = res["lyrics"]
        if len(lyrics_text) > 4000:
            lyrics_text = lyrics_text[:3990] + "\n..."

        embed = discord.Embed(
            title=f"📜 Lyrics • {res['title']}",
            description=lyrics_text,
            color=0x9B59B6
        )
        embed.set_footer(text="Echo Technologies Music System • Lyrics Service")
        await interaction.followup.send(embed=embed)

    @bot.tree.command(name="seek", description="Seek to a specific timestamp in the current song (e.g. 1:30 or 90).")
    @app_commands.describe(timestamp="Timestamp formatted as MM:SS or seconds (e.g. 1:30)")
    async def seek_command(interaction: discord.Interaction, timestamp: str):
        player = get_music_player(bot)
        if not player.current or not (player.is_playing() or player.is_paused()):
            await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
            return

        seconds = 0
        if ":" in timestamp:
            parts = timestamp.split(":")
            try:
                seconds = int(parts[0]) * 60 + int(parts[1])
            except Exception:
                await interaction.response.send_message("❌ Invalid timestamp format. Use `MM:SS` (e.g. `1:30`).", ephemeral=True)
                return
        elif timestamp.isdigit():
            seconds = int(timestamp)
        else:
            await interaction.response.send_message("❌ Invalid timestamp. Use `MM:SS` or total seconds.", ephemeral=True)
            return

        await player.seek(seconds)
        await interaction.response.send_message(f"⏩ Seeked to **{seconds//60}:{seconds%60:02d}**.")

    @bot.tree.command(name="forward", description="Fast-forward current song by specified seconds.")
    @app_commands.describe(seconds="Number of seconds to skip forward (default: 30)")
    async def forward_command(interaction: discord.Interaction, seconds: int = 30):
        player = get_music_player(bot)
        if not player.current or not (player.is_playing() or player.is_paused()):
            await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
            return

        elapsed = int(time.time() - player.start_time) + player.seek_offset
        new_pos = elapsed + max(1, seconds)
        await player.seek(new_pos)
        await interaction.response.send_message(f"⏩ Fast-forwarded {seconds}s to **{new_pos//60}:{new_pos%60:02d}**.")

    @bot.tree.command(name="rewind", description="Rewind current song by specified seconds.")
    @app_commands.describe(seconds="Number of seconds to rewind back (default: 15)")
    async def rewind_command(interaction: discord.Interaction, seconds: int = 15):
        player = get_music_player(bot)
        if not player.current or not (player.is_playing() or player.is_paused()):
            await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
            return

        elapsed = int(time.time() - player.start_time) + player.seek_offset
        new_pos = max(0, elapsed - max(1, seconds))
        await player.seek(new_pos)
        await interaction.response.send_message(f"⏪ Rewound {seconds}s to **{new_pos//60}:{new_pos%60:02d}**.")

    playlist_group = app_commands.Group(name="playlist", description="Manage custom saved user playlists.")

    @playlist_group.command(name="save", description="Save the current music queue as a personal playlist.")
    @app_commands.describe(name="Unique name for your playlist")
    async def playlist_save(interaction: discord.Interaction, name: str):
        player = get_music_player(bot)
        if not player.queue and not player.current:
            await interaction.response.send_message("❌ Queue is empty. Play some songs first!", ephemeral=True)
            return

        tracks_to_save = []
        if player.current:
            tracks_to_save.append(player.current.to_dict())
        for t in player.queue:
            tracks_to_save.append(t.to_dict())

        if hasattr(bot, 'db') and hasattr(bot.db, 'save_user_playlist'):
            bot.db.save_user_playlist(interaction.user.id, name, tracks_to_save)
            await interaction.response.send_message(f"💾 **Playlist Saved!** Created playlist **`{name}`** with **{len(tracks_to_save)} tracks**.")
        else:
            await interaction.response.send_message("❌ Database unavailable.", ephemeral=True)

    @playlist_group.command(name="load", description="Load a saved playlist into the queue.")
    @app_commands.describe(name="Name of saved playlist to load")
    async def playlist_load(interaction: discord.Interaction, name: str):
        await interaction.response.defer()
        await ensure_voice_connection(bot)

        if not hasattr(bot, 'db') or not hasattr(bot.db, 'get_user_playlist'):
            await interaction.followup.send("❌ Database unavailable.", ephemeral=True)
            return

        tracks_data = bot.db.get_user_playlist(interaction.user.id, name)
        if not tracks_data:
            await interaction.followup.send(f"❌ Saved playlist **`{name}`** not found.", ephemeral=True)
            return

        player = get_music_player(bot)
        member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)

        count = 0
        for td in tracks_data:
            t = Track(
                title=td.get("title", "Unknown"),
                stream_url="",
                webpage_url=td.get("webpage_url", ""),
                duration=td.get("duration", 0),
                thumbnail=td.get("thumbnail", ""),
                uploader=td.get("uploader", "Unknown"),
                requester=member
            )
            await player.add_track(t)
            count += 1

        await interaction.followup.send(f"🎶 Loaded **{count} tracks** from playlist **`{name}`** into the queue!")

    @playlist_group.command(name="list", description="List all your saved playlists.")
    async def playlist_list(interaction: discord.Interaction):
        if not hasattr(bot, 'db') or not hasattr(bot.db, 'get_user_playlists_list'):
            await interaction.response.send_message("❌ Database unavailable.", ephemeral=True)
            return

        playlists = bot.db.get_user_playlists_list(interaction.user.id)
        if not playlists:
            await interaction.response.send_message("📜 You have no saved playlists. Use `/playlist save name: <name>` to create one!", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"💾 Saved Playlists • {interaction.user.display_name}",
            color=0x3498DB
        )
        desc = ""
        for p in playlists:
            desc += f"• **`{p['playlist_name']}`** — `{p['track_count']} tracks` (created {p['created_at'][:10]})\n"

        embed.description = desc
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @playlist_group.command(name="delete", description="Delete a saved playlist.")
    @app_commands.describe(name="Name of saved playlist to delete")
    async def playlist_delete(interaction: discord.Interaction, name: str):
        if hasattr(bot, 'db') and hasattr(bot.db, 'delete_user_playlist'):
            success = bot.db.delete_user_playlist(interaction.user.id, name)
            if success:
                await interaction.response.send_message(f"🗑️ Deleted playlist **`{name}`**.", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Saved playlist **`{name}`** not found.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Database unavailable.", ephemeral=True)

    bot.tree.add_command(playlist_group)

    @bot.tree.command(name="voteskip", description="Vote to skip the currently playing song.")
    async def voteskip_command(interaction: discord.Interaction):
        player = get_music_player(bot)
        if not player.current or not (player.is_playing() or player.is_paused()):
            await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
            return

        member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)

        # Immediate skip for admins, requester, or DJ role
        is_admin = member.guild_permissions.administrator
        is_requester = (player.current.requester and player.current.requester.id == member.id)
        has_dj = any("dj" in r.name.lower() or "music" in r.name.lower() for r in member.roles)

        if is_admin or is_requester or has_dj:
            await player.skip()
            await interaction.response.send_message(f"⏭️ Instant skip executed by {member.mention}.")
            return

        # Vote calculation
        player.voteskip_users.add(member.id)
        vc = player.voice_client.channel if player.voice_client else None
        vc_members = [m for m in vc.members if not m.bot] if vc else [member]
        required_votes = max(1, (len(vc_members) + 1) // 2)

        if len(player.voteskip_users) >= required_votes:
            await player.skip()
            await interaction.response.send_message(f"⏭️ Vote skip passed! ({len(player.voteskip_users)}/{required_votes} votes). Skipped track.")
        else:
            await interaction.response.send_message(f"🗳️ Vote recorded! **{len(player.voteskip_users)}/{required_votes}** votes required to skip.")
