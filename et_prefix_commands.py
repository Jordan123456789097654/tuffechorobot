import discord
import logging
import sqlite3
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from hr_extended_system import (
    clock_in_staff, clock_out_staff, get_staff_shift_stats,
    add_commendation, PRESET_COMMENDATION_REWARDS,
    create_staff_meeting, set_meeting_message, StaffMeetingRSVPView,
    get_staff_meeting, update_meeting_status, get_meeting_rsvp_counts
)
from hr_system import (
    add_strike, get_staff_strikes, pardon_strike,
    add_staff_blacklist, remove_staff_blacklist, is_staff_blacklisted,
    add_staff_evaluation, get_staff_evaluations
)
from hiring_system import (
    add_ats_note, get_ats_notes, flag_application, get_application_flags,
    schedule_interview, log_interview_scorecard, create_custom_offer,
    start_onboarding, start_hiring_campaign, cancel_hiring_campaign, get_hiring_campaign
)
from license_wizard import execute_prefix_create_product

logger = logging.getLogger("roblox_bot.rn_prefix")

# DICTIONARY OF DETAILED COMMAND HELP MANUALS
COMMAND_HELP_MANUALS: Dict[str, Dict[str, str]] = {
    "say": {
        "name": "!rn say <message>",
        "description": "Bot says the specified message directly into the channel.",
        "usage": "`!rn say <message>` OR `!rn say #channel <message>`",
        "example": "`!rn say Hello everyonrn!`",
        "permissions": "Foundership / Executive Leadership"
    },
    "duty": {
        "name": "!rn duty [on/off]",
        "description": "Clock in or out of your active support staff shift. Manages your timer and assigns/removes the '@On Duty Staff' role.",
        "usage": "`!rn duty on` OR `!rn duty off` (or `!duty`)",
        "example": "`!rn duty on`",
        "permissions": "Support Team / Staff"
    },
    "shift-stats": {
        "name": "!rn shift-stats [@member]",
        "description": "Displays detailed duty metrics for yourself or a staff member, including weekly hours and lifetime shift count.",
        "usage": "`!rn shift-stats` OR `!rn shift-stats @User`",
        "example": "`!rn shift-stats @Jordan`",
        "permissions": "Support Team / Staff"
    },
    "commend": {
        "name": "!rn commend @member <reason>",
        "description": "Issue an official HR Commendation with preset rewards (e.g. 1-Week Quota Exemption, 1,000 Points) to an outstanding staff member.",
        "usage": "`!rn commend @member <reason>`",
        "example": "`!rn commend @Jordan Excellent resolution of emergency tickets`",
        "permissions": "HR / Administrators Only"
    },
    "dossier": {
        "name": "!rn dossier [@member]",
        "description": "Displays a 360° Master HR Personnel file showing shift hours, exam evaluation scores, commendations, active strikes, and blacklist status.",
        "usage": "`!rn dossier [@member]`",
        "example": "`!rn dossier @Jordan`",
        "permissions": "Staff / HR Administrators"
    },
    "meeting": {
        "name": "!rn meeting <announce/cancel/end> [args]",
        "description": "Manage official staff meetings. Auto-posts meeting announcements to #staff-announcements with interactive RSVP buttons (Attending, Cannot Attend, Tentative).",
        "usage": (
            "• `!rn meeting announce [topic]` — Announce staff meeting\n"
            "• `!rn meeting cancel <meeting_id> <reason>` — Cancel scheduled meeting\n"
            "• `!rn meeting end <meeting_id> <summary>` — Conclude meeting & log minutes"
        ),
        "example": "`!rn meeting announce Q4 Goal Overview`",
        "permissions": "HR / Administrators Only"
    },
    "campaign": {
        "name": "!rn campaign <start/cancel> [args]",
        "description": "Manage recruitment campaigns. Posts official hiring drive embeds with open positions to #announcements.",
        "usage": (
            "• `!rn campaign start <positions>` — Launch hiring campaign\n"
            "• `!rn campaign cancel <campaign_id> <reason>` — Cancel hiring campaign"
        ),
        "example": "`!rn campaign start Trial Support, Developer`",
        "permissions": "HR / Administrators Only"
    },
    "interview": {
        "name": "!rn interview <open/schedule> <candidate>",
        "description": "Manage applicant screening. Opens private #interview-username text channels or schedules formal 1-on-1 interview calendar notices.",
        "usage": (
            "• `!rn interview open @candidate` — Create private interview channel\n"
            "• `!rn interview schedule @candidate <time>` — Schedule 1-on-1 interview"
        ),
        "example": "`!rn interview open @Alex`",
        "permissions": "HR / Administrators Only"
    },
    "promote": {
        "name": "!rn promote @member [reason]",
        "description": "Formally promote a staff member, post official HR advancement embeds, and dispatch congratulations DMs.",
        "usage": "`!rn promote @member <reason>`",
        "example": "`!rn promote @Jordan Outstanding performance during probation`",
        "permissions": "HR / Administrators Only"
    },
    "demote": {
        "name": "!rn demote @member [reason]",
        "description": "Formally demote a staff member and log rationale to HR records.",
        "usage": "`!rn demote @member <reason>`",
        "example": "`!rn demote @Jordan Policy non-compliance`",
        "permissions": "HR / Administrators Only"
    },
    "strike": {
        "name": "!rn strike @member <severity 1-3> <reason>",
        "description": "Issue an official HR disciplinary strike (Severity 1: Warning, 2: Moderate, 3: Critical) with DM notices.",
        "usage": "`!rn strike @member <1/2/3> <reason>`",
        "example": "`!rn strike @Alex 2 Missed mandatory staff meeting`",
        "permissions": "HR / Administrators Only"
    },
    "warn": {
        "name": "!rn warn @member <reason>",
        "description": "Issues an official warning to a server member and logs it.",
        "usage": "`!rn warn @member <reason>`",
        "example": "`!rn warn @User Spamming in chat`",
        "permissions": "Moderators / Staff"
    },
    "kick": {
        "name": "!rn kick @member <reason>",
        "description": "Kicks a member from the server.",
        "usage": "`!rn kick @member <reason>`",
        "example": "`!rn kick @User Inappropriate behavior`",
        "permissions": "Moderators / Staff"
    },
    "ban": {
        "name": "!rn ban @member <reason>",
        "description": "Bans a member from the server.",
        "usage": "`!rn ban @member <reason>`",
        "example": "`!rn ban @User Severe violation`",
        "permissions": "Administrators / Leadership"
    },
    "purge": {
        "name": "!rn purge <amount>",
        "description": "Bulk deletes messages in the current channel.",
        "usage": "`!rn purge <amount>`",
        "example": "`!rn purge 20`",
        "permissions": "Moderators / Staff"
    },
    "verify": {
        "name": "!rn verify",
        "description": "Displays verification instructions for linking your Roblox account to Discord.",
        "usage": "`!rn verify`",
        "example": "`!rn verify`",
        "permissions": "All Members"
    },
    "whois": {
        "name": "!rn whois [@member]",
        "description": "Look up the verified Roblox account username, display name, and Roblox ID for a Discord member.",
        "usage": "`!rn whois @member`",
        "example": "`!rn whois @Jordan`",
        "permissions": "All Members"
    },
    "setstatus": {
        "name": "!rn setstatus <playing|watching|listening|competing|streaming|clear> <text>",
        "description": "Sets the bot's rich presence activity status text.",
        "usage": "`!rn setstatus watching RetailNetwork Server` OR `!rn setstatus playing Roblox` OR `!rn setstatus clear`",
        "example": "`!rn setstatus watching RetailNetwork Server`",
        "permissions": "Administrators Only"
    },
    "setvisibility": {
        "name": "!rn setvisibility <online|idle|dnd|invisible>",
        "description": "Changes the bot's status indicator dot (Online [🟢], Idle [🌙], Do Not Disturb [🔴], Invisible [⚪]).",
        "usage": "`!rn setvisibility online` OR `!rn setvisibility dnd` OR `!rn setvisibility idle`",
        "example": "`!rn setvisibility dnd`",
        "permissions": "Administrators Only"
    }
}

ALLOWED_PREFIXES = ("!rn", "?rn", ".rn", "rn!", "rn!", "!rn", "?rn", ".rn", "!duty", "?duty", ".duty")
MODERATION_COMMANDS = ("say", "warn", "kick", "ban", "timeout", "purge", "lock", "unlock", "strike", "demote", "promote")

async def delete_trigger_message(message: discord.Message):
    """Safely deletes the user's trigger message for moderation actions."""
    try:
        await message.delete()
    except Exception:
        pass

async def handle_et_prefix_command(bot, message: discord.Message) -> bool:
    """
    Handles prefix commands and subcommands for !rn, ?rn, .rn, rn!, rn!, !rn, etc.
    Returns True if handled.
    """
    if message.author.bot or not message.content:
        return False

    content = message.content.strip()
    matched_prefix = None
    content_lower = content.lower()

    for p in ALLOWED_PREFIXES:
        if content_lower.startswith(p):
            matched_prefix = p
            break

    if not matched_prefix:
        return False

    parts = content.split()
    cmd = parts[0].lower()

    # Shortcut: !duty, ?duty, .duty [on/off]
    if cmd in ("!duty", "?duty", ".duty"):
        sub = parts[1].lower() if len(parts) > 1 else "on"
        await execute_duty(message, sub)
        return True

    # !rn root command or !rn help
    if len(parts) == 1:
        await send_et_help_directory(message)
        return True

    subcmd = parts[1].lower()
    args = parts[2:]

    # Auto-delete trigger message if it is a moderation action or !rn say
    if subcmd in MODERATION_COMMANDS:
        await delete_trigger_message(message)

    # Help router: !rn help [command_name]
    if subcmd in ("help", "commands", "manual"):
        if args:
            target_help = args[0].lower().replace("!rn", "").strip()
            await send_command_specific_help(message, target_help)
        else:
            await send_et_help_directory(message)
        return True

    # Subcommand routing
    if subcmd in ("create-product", "createproduct", "newproduct"):
        await execute_prefix_create_product(bot, message)
        return True

    elif subcmd == "say":
        await execute_say(message, args)

    elif subcmd in ("duty", "on-duty", "off-duty"):
        action = args[0].lower() if args else ("off" if subcmd == "off-duty" else "on")
        await execute_duty(message, action)

    elif subcmd in ("shift-stats", "shifts", "shift"):
        member = message.mentions[0] if message.mentions else message.author
        await execute_shift_stats(message, member)

    elif subcmd in ("commend", "award"):
        await execute_commend(message, args)

    elif subcmd in ("dossier", "profile", "hr-file"):
        member = message.mentions[0] if message.mentions else message.author
        await execute_dossier(message, member)

    elif subcmd == "meeting":
        await execute_meeting(message, args)

    elif subcmd == "campaign":
        await execute_campaign(message, args)

    elif subcmd == "interview":
        await execute_interview(message, args)

    elif subcmd in ("promote", "demote"):
        await execute_rank_change(message, subcmd, args)

    elif subcmd in ("strike", "warn"):
        await execute_strike(message, args)

    elif subcmd in ("kick", "ban"):
        await execute_mod_action(message, subcmd, args)

    elif subcmd == "purge":
        await execute_purge(message, args)

    elif subcmd in ("shutdown", "stop", "stopbot", "kill"):
        await execute_shutdown(bot, message)

    elif subcmd in ("setstatus", "status", "setactivity", "activity"):
        await execute_setstatus(bot, message, args)

    elif subcmd in ("setvisibility", "visibility", "setpresence", "presence"):
        await execute_setvisibility(bot, message, args)

    elif subcmd in ("play", "p"):
        await execute_music_play_prefix(bot, message, args)

    elif subcmd in ("skip", "next"):
        await execute_music_skip_prefix(bot, message)

    elif subcmd in ("filter", "eq"):
        await execute_music_filter_prefix(bot, message, args)

    elif subcmd == "autoplay":
        await execute_music_autoplay_prefix(bot, message, args)

    elif subcmd in ("lyrics", "lyric"):
        await execute_music_lyrics_prefix(bot, message, args)

    elif subcmd in ("seek", "jump"):
        await execute_music_seek_prefix(bot, message, args)

    elif subcmd in ("forward", "ff"):
        await execute_music_forward_prefix(bot, message, args)

    elif subcmd in ("rewind", "rw"):
        await execute_music_rewind_prefix(bot, message, args)

    elif subcmd in ("voteskip", "votesk"):
        await execute_music_voteskip_prefix(bot, message)

    elif subcmd in ("playlist", "pl"):
        await execute_music_playlist_prefix(bot, message, args)

    elif subcmd in ("music-debug", "debug-music", "musicdebug"):
        from music_system import debug_music_system
        await debug_music_system(bot, message.channel)

    elif subcmd in ("whois", "lookup"):
        member = message.mentions[0] if message.mentions else message.author
        await execute_whois(message, member)

    else:
        await send_et_help_directory(message)

    return True

# --- DETAILED HELP ROUTERS ---
async def send_et_help_directory(message: discord.Message):
    embed = discord.Embed(
        title="🤖 RetailNetwork • Master Command Directory",
        description=(
            "Welcome to the official **RetailNetwork** Command System!\n"
            "Use **`!rn help [command]`** for detailed usage instructions & examples for any command (e.g. `!rn help say`, `!rn help duty`, `!rn help play`)."
        ),
        color=0x3498DB
    )

    embed.add_field(
        name="📢 Announcements, Status & Bot Control",
        value="`!rn say <message>` • `!rn setstatus <type> <text>` • `!rn setvisibility <status>` • `!rn shutdown` • `!rn help [command]`",
        inline=False
    )

    embed.add_field(
        name="🎧 24/7 Jukebox & Music Suite",
        value="`/play <song/link>` • `/skip` • `/pause` • `/resume` • `/stop` • `/queue` • `/nowplaying` • `/volume <1-100>` • `/loop <mode>`",
        inline=False
    )

    embed.add_field(
        name="⏱️ Staff Duty & Shift Tracking",
        value="`!rn duty [on/off]` (or `!duty`) • `!rn shift-stats [@user]`",
        inline=False
    )

    embed.add_field(
        name="💼 HR Administration & Personnel Files",
        value="`!rn commend @user <reason>` • `!rn dossier [@user]` • `!rn promote @user [reason]` • `!rn demote @user [reason]` • `!rn strike @user <1-3> <reason>` • `!rn pardon <strike_id> <reason>` • `!rn eval @user <score> <feedback>` • `!rn eval-history [@user]`",
        inline=False
    )

    embed.add_field(
        name="🛡️ Moderation & Server Security",
        value="`!rn warn @user <reason>` • `!rn warnings [@user]` • `!rn clear-warnings @user` • `!rn kick @user <reason>` • `!rn ban @user <reason>` • `!rn unban <user_id>` • `!rn global-ban @user <reason>` • `!rn purge <count>` • `!rn lock` • `!rn unlock` • `!rn slowmode <sec>` • `!rn mod-case <id>`",
        inline=False
    )

    embed.add_field(
        name="📅 Staff Meetings & RSVPs",
        value="`!rn meeting announce [topic]` • `!rn meeting cancel <id> <reason>` • `!rn meeting end <id> <notes>` • `!rn meeting rsvp <id> <yes/no/maybe>`",
        inline=False
    )

    embed.add_field(
        name="📢 Hiring, Recruitment & ATS Suite",
        value="`!rn campaign start [positions]` • `!rn campaign cancel <id> <reason>` • `!rn interview open @candidate` • `!rn offer create @candidate <role> [salary]` • `!rn onboard start @candidate` • `!rn ats note @candidate <notes>` • `!rn ats flag @candidate <reason>`",
        inline=False
    )

    embed.add_field(
        name="🎟️ AI Support Tickets & Staff Exams",
        value="`!rn ticket panel` • `!rn ticket force-open @user` • `!rn ticket test-staff @user` • `!rn ticket close [reason]` • `!rn supervisor-request <reason>`",
        inline=False
    )

    embed.add_field(
        name="🏆 Community Points, Rewards & Leveling",
        value="`!rn points [@user]` • `!rn shop` • `!rn tip @user <points>` • `!rn rank [@user]` • `!rn top` (or `!rn leaderboard`)",
        inline=False
    )

    embed.add_field(
        name="🤝 Partnerships, Verification & Utility",
        value="`!rn partner add <name> <category>` • `!rn ad` • `!rn suggest <idea>` • `!rn verify` • `!rn whois [@user]` • `!rn check-alt @user`",
        inline=False
    )

    embed.set_footer(text="Type '!rn help [command]' for specific manual & syntax • RetailNetwork")
    embed.timestamp = datetime.now(timezone.utc)

    await message.channel.send(embed=embed)

async def send_command_specific_help(message: discord.Message, cmd_name: str):
    manual = COMMAND_HELP_MANUALS.get(cmd_name)
    if not manual:
        for k, v in COMMAND_HELP_MANUALS.items():
            if cmd_name in k or k in cmd_name:
                manual = v
                break

    if not manual:
        await message.channel.send(
            f"❌ Unknown command **`{cmd_name}`**. Type `!rn help` to see the full list of available commands!"
        )
        return

    embed = discord.Embed(
        title=f"📖 Command Manual — {manual['name']}",
        description=manual['description'],
        color=0x9B59B6
    )
    embed.add_field(name="📌 Syntax / Usage", value=manual['usage'], inline=False)
    embed.add_field(name="💡 Example", value=manual['example'], inline=False)
    embed.add_field(name="🔒 Required Permissions", value=f"`{manual['permissions']}`", inline=False)

    embed.set_footer(text="RetailNetwork • Command Reference System")
    embed.timestamp = datetime.now(timezone.utc)

    await message.channel.send(embed=embed)

# --- COMMAND EXECUTORS ---
async def execute_say(message: discord.Message, args: List[str]):
    if not message.author.guild_permissions.administrator:
        await message.channel.send("❌ Only Administrators can use !rn say.")
        return

    if not args:
        await message.channel.send("❌ Usage: `!rn say <message>`")
        return

    target_ch = message.channel
    say_text = " ".join(args)

    if message.channel_mentions and args[0].startswith("<#"):
        target_ch = message.channel_mentions[0]
        say_text = " ".join(args[1:])

    if say_text:
        await target_ch.send(say_text)

async def execute_duty(message: discord.Message, action: str):
    member = message.author
    guild = message.guild
    on_duty_role = discord.utils.get(guild.roles, name="On Duty Staff")

    if action in ("on", "start", "in"):
        success = clock_in_staff(member.id)
        if not success:
            await message.channel.send(f"⚠️ {member.mention}, you are already clocked **ON duty**!")
            return

        if on_duty_role:
            try:
                await member.add_roles(on_duty_role, reason="Clocked ON duty via !rn duty")
            except Exception:
                pass

        embed = discord.Embed(
            title="🟢 CLOCKED ON DUTY",
            description=f"{member.mention} is now actively **ON DUTY**.",
            color=0x57F287
        )
        embed.set_footer(text="RetailNetwork • Shift Active")
        embed.timestamp = datetime.now(timezone.utc)
        await message.channel.send(embed=embed)

    else:
        duration_sec = clock_out_staff(member.id)
        if duration_sec is None:
            await message.channel.send(f"⚠️ {member.mention}, you are not currently clocked ON duty!")
            return

        if on_duty_role and on_duty_role in member.roles:
            try:
                await member.remove_roles(on_duty_role, reason="Clocked OFF duty via !rn duty")
            except Exception:
                pass

        hours = duration_sec // 3600
        mins = (duration_sec % 3600) // 60
        secs = duration_sec % 60

        embed = discord.Embed(
            title="🔴 CLOCKED OFF DUTY",
            description=(
                f"{member.mention} has clocked **OFF DUTY**.\n\n"
                f"⏱️ **Shift Duration:** `{hours}h {mins}m {secs}s`"
            ),
            color=0xED4245
        )
        embed.set_footer(text="RetailNetwork • Shift Complete")
        embed.timestamp = datetime.now(timezone.utc)
        await message.channel.send(embed=embed)

async def execute_shift_stats(message: discord.Message, member: discord.Member):
    stats = get_staff_shift_stats(member.id)
    tot_h = stats["total_seconds"] // 3600
    tot_m = (stats["total_seconds"] % 3600) // 60
    w_h = stats["weekly_seconds"] // 3600
    w_m = (stats["weekly_seconds"] % 3600) // 60

    embed = discord.Embed(
        title=f"⏱️ Shift Statistics — {member.display_name}",
        color=0x3498DB
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Status", value="🟢 **ON DUTY**" if stats["is_on_duty"] else "🔴 **OFF DUTY**", inline=True)
    embed.add_field(name="Shifts Completed", value=f"`{stats['total_shifts']}`", inline=True)
    embed.add_field(name="Weekly Duty Hours", value=f"`{w_h}h {w_m}m`", inline=False)
    embed.add_field(name="Lifetime Duty Hours", value=f"`{tot_h}h {tot_m}m`", inline=False)
    embed.set_footer(text="RetailNetwork • Staff Duty Records")
    embed.timestamp = datetime.now(timezone.utc)

    await message.channel.send(embed=embed)

async def execute_commend(message: discord.Message, args: List[str]):
    if not message.author.guild_permissions.administrator:
        await message.channel.send("❌ Only Administrators can issue commendations.")
        return

    if not message.mentions:
        await message.channel.send("❌ Usage: `!rn commend @member <reason>`")
        return

    member = message.mentions[0]
    reason = " ".join([a for a in args if not a.startswith("<@")]) or "Outstanding HR & Support Performance"
    comm_id = add_commendation(member.id, message.author.id, reason, "quota_exemption")

    embed = discord.Embed(
        title="🎖️ OFFICIAL HR COMMENDATION",
        description=(
            f"**RetailNetwork Management** has formally issued a Commendation to {member.mention}!\n\n"
            f"📜 **Commendation ID:** `#COMM-{comm_id:04d}`\n"
            f"🎁 **Preset Reward:** 🎟️ 1-Week Staff Quota Exemption\n"
            f"📋 **Reason:** *\"{reason}\"*\n"
            f"👤 **Awarded By:** {message.author.mention}"
        ),
        color=0xF1C40F
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="RetailNetwork • HR Recognition")
    embed.timestamp = datetime.now(timezone.utc)

    await message.channel.send(embed=embed)

async def execute_dossier(message: discord.Message, member: discord.Member):
    shift_data = get_staff_shift_stats(member.id)
    strikes = get_staff_strikes(member.id)
    evals = get_staff_evaluations(member.id)

    tot_h = shift_data["total_seconds"] // 3600
    w_h = shift_data["weekly_seconds"] // 3600
    active_strikes = [s for s in strikes if not s["is_pardoned"]]
    avg_eval = (sum(e["score"] for e in evals) / len(evals)) if evals else 100.0

    embed = discord.Embed(
        title="📁 MASTER STAFF HR DOSSIER",
        description=f"Official Personnel File for {member.mention} (`ID: {member.id}`)",
        color=0x3498DB
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(
        name="⏱️ Duty & Shift Metrics",
        value=f"• **Status:** {'🟢 On Duty' if shift_data['is_on_duty'] else '🔴 Off Duty'}\n• **Weekly:** `{w_h}h` | **Lifetime:** `{tot_h}h`",
        inline=False
    )
    embed.add_field(
        name="📊 Performance & Evaluation",
        value=f"• **Average Exam Score:** `{avg_eval:.1f} / 100`\n• **Evaluations Completed:** `{len(evals)}`",
        inline=False
    )
    embed.add_field(
        name="⚠️ Disciplinary Record",
        value=f"• **Active Strikes:** `{len(active_strikes)}` | **Blacklist:** {'🔴 BLACKLISTED' if is_staff_blacklisted(member.id) else '🟢 CLEAN'}",
        inline=False
    )
    embed.set_footer(text="RetailNetwork • Personnel File Confidential")
    embed.timestamp = datetime.now(timezone.utc)

    await message.channel.send(embed=embed)

async def execute_meeting(message: discord.Message, args: List[str]):
    if not message.author.guild_permissions.administrator:
        await message.channel.send("❌ Only Administrators can manage meetings.")
        return

    sub = args[0].lower() if args else "announce"
    rest = " ".join(args[1:])

    if sub == "announce":
        topic = rest or "General Staff Operations Meeting"
        announce_ch = discord.utils.get(message.guild.text_channels, name="staff-announcements") or message.channel
        m_id = create_staff_meeting("Official Staff Meeting", "Upcoming Saturday @ 5:00 PM EST", topic, True)
        view = StaffMeetingRSVPView(m_id)

        embed = discord.Embed(
            title="📅 OFFICIAL STAFF MEETING ANNOUNCEMENT",
            description=(
                f"An official staff meeting has been scheduled by **RetailNetwork Management**.\n"
                f"All staff members are required to select their RSVP status below."
            ),
            color=0x9B59B6
        )
        embed.add_field(name="🕒 Date & Time", value="```\nUpcoming Saturday @ 5:00 PM EST\n```", inline=False)
        embed.add_field(name="📌 Primary Topic", value=topic, inline=False)
        embed.add_field(name="📍 Location", value="`Staff Voice Channel #1`", inline=True)
        embed.add_field(name="⚠️ Attendance Policy", value="`🔴 MANDATORY ATTENDANCE`", inline=True)
        embed.add_field(name="📊 RSVP Status Summary", value="✅ **Attending:** `0` | ❌ **Cannot Attend:** `0` | ⏳ **Tentative:** `0`", inline=False)
        embed.set_footer(text=f"RetailNetwork • Staff Meeting #M-{m_id:03d}")
        embed.timestamp = datetime.now(timezone.utc)

        msg = await announce_ch.send(content="📢 **ATTENTION ALL STAFF MEMBERS:**", embed=embed, view=view)
        set_meeting_message(m_id, announce_ch.id, msg.id)
        await message.channel.send(f"✅ Announced Staff Meeting `#M-{m_id:03d}` in {announce_ch.mention}!")

    elif sub == "cancel":
        if len(args) < 2 or not args[1].isdigit():
            await message.channel.send("❌ Usage: `!rn meeting cancel <meeting_id> <reason>`")
            return
        m_id = int(args[1])
        reason = " ".join(args[2:]) or "Scheduled operational conflict"
        m = get_staff_meeting(m_id)
        if not m:
            await message.channel.send(f"❌ Meeting `#M-{m_id:03d}` not found.")
            return

        update_meeting_status(m_id, "Cancelled", reason)
        await message.channel.send(f"✅ Staff Meeting `#M-{m_id:03d}` has been officially **CANCELLED**.")

async def execute_campaign(message: discord.Message, args: List[str]):
    if not message.author.guild_permissions.administrator:
        await message.channel.send("❌ Only Administrators can manage campaigns.")
        return

    sub = args[0].lower() if args else "start"
    rest = " ".join(args[1:])

    if sub == "start":
        c_id = start_hiring_campaign("Official Recruitment Drive", rest or "Trial Support, Moderator", "Open Until Filled")
        announce_ch = discord.utils.get(message.guild.text_channels, name="announcements") or message.channel

        embed = discord.Embed(
            title="📢 OFFICIAL HIRING CAMPAIGN LAUNCHED",
            description=(
                f"**RetailNetwork** is now officially accepting applications!\n\n"
                f"💼 **Open Positions:** `{rest or 'Trial Support, Moderator'}`\n"
                f"🚀 **How to Apply:** Use `/apply` or visit <#1556000041309708390>!"
            ),
            color=0x9B59B6
        )
        embed.set_footer(text=f"RetailNetwork • Recruitment Campaign #CAMP-{c_id:03d}")
        embed.timestamp = datetime.now(timezone.utc)

        await announce_ch.send(content="📢 **RECRUITMENT DRIVE ANNOUNCEMENT:**", embed=embed)
        await message.channel.send(f"✅ Launched Hiring Campaign `#CAMP-{c_id:03d}` in {announce_ch.mention}!")

    elif sub == "cancel":
        if len(args) < 2 or not args[1].isdigit():
            await message.channel.send("❌ Usage: `!rn campaign cancel <campaign_id> <reason>`")
            return
        c_id = int(args[1])
        reason = " ".join(args[2:]) or "Positions filled"
        cancel_hiring_campaign(c_id, reason)
        await message.channel.send(f"✅ Hiring Campaign `#CAMP-{c_id:03d}` has been officially **CANCELLED**.")

async def execute_interview(message: discord.Message, args: List[str]):
    if not message.author.guild_permissions.administrator:
        await message.channel.send("❌ Only Administrators can manage interviews.")
        return

    sub = args[0].lower() if args else "open"

    if sub == "open" and message.mentions:
        candidate = message.mentions[0]
        guild = message.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, view_channel=False),
            candidate: discord.PermissionOverwrite(read_messages=True, view_channel=True, send_messages=True),
            message.author: discord.PermissionOverwrite(read_messages=True, view_channel=True, send_messages=True)
        }
        ch = await guild.create_text_channel(name=f"interview-{candidate.name}", overwrites=overwrites)
        embed = discord.Embed(
            title=f"🎤 Interview Channel — {candidate.display_name}",
            description=f"Welcome {candidate.mention}! Your interview will begin shortly.",
            color=0x3498DB
        )
        await ch.send(content=f"👋 Hello {candidate.mention}!", embed=embed)
        await message.channel.send(f"✅ Created private interview channel {ch.mention}!")

async def execute_rank_change(message: discord.Message, subcmd: str, args: List[str]):
    if not message.author.guild_permissions.administrator:
        await message.channel.send("❌ Only Administrators can change staff ranks.")
        return

    if not message.mentions:
        await message.channel.send(f"❌ Usage: `!rn {subcmd} @member <reason>`")
        return

    member = message.mentions[0]
    reason = " ".join([a for a in args if not a.startswith("<@")]) or f"Official HR {subcmd} by leadership"

    embed = discord.Embed(
        title=f"{'🎉 PROMOTION' if subcmd == 'promote' else '📉 DEMOTION'} NOTICE",
        description=f"{member.mention} has received a formal rank adjustment.\n\n📋 **Reason:** *\"{reason}\"*",
        color=0x57F287 if subcmd == "promote" else 0xED4245
    )
    await message.channel.send(embed=embed)

async def execute_strike(message: discord.Message, args: List[str]):
    if not message.author.guild_permissions.administrator:
        await message.channel.send("❌ Only Administrators can issue HR strikes.")
        return

    if not message.mentions:
        await message.channel.send("❌ Usage: `!rn strike @member <severity 1-3> <reason>`")
        return

    member = message.mentions[0]
    severity_val = 1
    for a in args:
        if a.isdigit() and int(a) in (1, 2, 3):
            severity_val = int(a)
            break

    reason = " ".join([a for a in args if not a.startswith("<@") and a != str(severity_val)]) or "Staff Policy Violation"
    strike_data = add_strike(member.id, message.author.id, message.guild.id, severity_val, reason)

    embed = discord.Embed(
        title="⚠️ HR DISCIPLINARY STRIKE ISSUED",
        description=(
            f"An official strike `#STRIKE-{strike_data['id']}` was issued to {member.mention}.\n\n"
            f"🔴 **Severity:** Level {severity_val}\n"
            f"📋 **Reason:** *\"{reason}\"*"
        ),
        color=0xED4245
    )
    await message.channel.send(embed=embed)

async def execute_mod_action(message: discord.Message, action: str, args: List[str]):
    if not message.author.guild_permissions.kick_members:
        await message.channel.send("❌ Only Staff / Moderators can execute moderation actions.")
        return

    if not message.mentions:
        await message.channel.send(f"❌ Usage: `!rn {action} @member <reason>`")
        return

    member = message.mentions[0]
    reason = " ".join([a for a in args if not a.startswith("<@")]) or f"Moderation action executed by {message.author.name}"

    try:
        if action == "kick":
            await member.kick(reason=reason)
            await message.channel.send(f"👢 Kicked {member.mention} | Reason: *\"{reason}\"*")
        elif action == "ban":
            await member.ban(reason=reason)
            await message.channel.send(f"🔨 Banned {member.mention} | Reason: *\"{reason}\"*")
    except Exception as e:
        await message.channel.send(f"❌ Failed to execute {action}: `{e}`")

async def execute_purge(message: discord.Message, args: List[str]):
    if not message.author.guild_permissions.manage_messages:
        await message.channel.send("❌ Only Staff / Moderators can purge messages.")
        return

    count = 10
    if args and args[0].isdigit():
        count = int(args[0])

    try:
        deleted = await message.channel.purge(limit=min(count + 1, 100))
        msg = await message.channel.send(f"🧹 Purged `{len(deleted)-1}` messages.")
        await asyncio.sleep(3)
        await msg.delete()
    except Exception as e:
        await message.channel.send(f"❌ Failed to purge messages: `{e}`")

async def execute_whois(message: discord.Message, member: discord.Member):
    embed = discord.Embed(
        title=f"👤 Roblox Link Profile — {member.display_name}",
        description=f"Discord User: {member.mention} (`ID: {member.id}`)\nRoblox Account: **Verified Member**",
        color=0x3498DB
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    await message.channel.send(embed=embed)

async def execute_shutdown(bot, message: discord.Message):
    if not message.author.guild_permissions.administrator:
        await message.channel.send("❌ Only Administrators can shut down the bot.")
        return

    await message.channel.send("🛑 **RetailNetwork Bot is shutting down gracefully. Logging off Discord...**")
    logger.info(f"Shutdown initiated via !rn shutdown by {message.author.name} (ID: {message.author.id}).")
    await bot.close()

PREMADE_ACTIVITIES: Dict[str, Dict[str, str]] = {
    "1": {"type": "playing", "text": "Roblox | !rn help", "label": "🎮 Roblox & Account Verification"},
    "2": {"type": "watching", "text": "RetailNetwork Server", "label": "🛡️ Server Moderation & Security"},
    "3": {"type": "listening", "text": "24/7 Jukebox | /play", "label": "🎧 24/7 Music Jukebox"},
    "4": {"type": "listening", "text": "Groq AI Support Tickets", "label": "🤖 Multi-Department AI Assistant"},
    "5": {"type": "watching", "text": "Staff Shifts & Duty Timers", "label": "⏱️ Staff Shift & Duty Tracker"},
    "6": {"type": "playing", "text": "Echo Development Studio", "label": "💻 Roblox Studio Development"},
    "7": {"type": "competing", "text": "Recruitment & Invite Contests", "label": "🏆 Recruitment Leaderboard"},
    "8": {"type": "streaming", "text": "Official RetailNetwork Stream", "label": "📡 Official Twitch Stream"},
    "9": {"type": "watching", "text": "Community Verification Logs", "label": "🔒 Security Telemetry Logs"}
}

def build_discord_activity(act_type: str, act_text: str) -> Optional[discord.BaseActivity]:
    if not act_text or act_type in ("clear", "none", "off", "reset"):
        return None

    at_lower = act_type.lower()
    if at_lower in ("playing", "game", "play"):
        return discord.Game(name=act_text)
    elif at_lower in ("streaming", "stream"):
        return discord.Streaming(name=act_text, url="https://twitch.tv/echo_technologies")
    elif at_lower in ("listening", "listen"):
        return discord.Activity(type=discord.ActivityType.listening, name=act_text)
    elif at_lower in ("watching", "watch"):
        return discord.Activity(type=discord.ActivityType.watching, name=act_text)
    elif at_lower in ("competing", "compete"):
        return discord.Activity(type=discord.ActivityType.competing, name=act_text)
    elif at_lower in ("custom",):
        return discord.CustomActivity(name=act_text)
    else:
        full_text = f"{act_type} {act_text}".strip()
        return discord.Game(name=full_text)

def parse_discord_status(status_str: str) -> discord.Status:
    s_lower = status_str.lower()
    if s_lower in ("idle", "away", "yellow"):
        return discord.Status.idle
    elif s_lower in ("dnd", "do_not_disturb", "busy", "red"):
        return discord.Status.dnd
    elif s_lower in ("invisible", "offline", "hidden", "grey", "gray"):
        return discord.Status.invisible
    else:
        return discord.Status.online

async def execute_setstatus(bot, message: discord.Message, args: List[str]):
    if not message.author.guild_permissions.administrator:
        await message.channel.send("❌ Only Administrators can change the bot activity status.")
        return

    if not args:
        await message.channel.send(
            "❌ **Usage:** `!rn setstatus <playing|watching|listening|competing|preset|rotate|clear> [text/id]`\n"
            "• **Preset Menu:** `!rn setstatus preset` (Lists all premade activities)\n"
            "• **Apply Preset:** `!rn setstatus preset 3` (Selects Jukebox status)\n"
            "• **Auto-Rotate:** `!rn setstatus rotate on` (Auto-cycles activities every 45s)"
        )
        return

    act_type = args[0].lower()
    act_text = " ".join(args[1:]) if len(args) > 1 else ""

    # Preset Subcommand Routing
    if act_type in ("preset", "presets", "list"):
        if not act_text:
            embed = discord.Embed(
                title="✨ RetailNetwork • Premade Status Activity Presets",
                description="Use **`!rn setstatus preset <number>`** to activate any premade activity below!",
                color=0x3498DB
            )
            for k, v in PREMADE_ACTIVITIES.items():
                embed.add_field(
                    name=f"Preset #{k} • {v['label']}",
                    value=f"Type: `{v['type'].capitalize()}` | Text: **{v['text']}**",
                    inline=False
                )
            embed.set_footer(text="Example: !rn setstatus preset 3 • Auto-rotate: !rn setstatus rotate on")
            await message.channel.send(embed=embed)
            return
        else:
            p_id = act_text.strip()
            preset = PREMADE_ACTIVITIES.get(p_id)
            if not preset:
                for k, v in PREMADE_ACTIVITIES.items():
                    if p_id.lower() in v['label'].lower() or p_id.lower() in v['text'].lower():
                        preset = v
                        break
            if not preset:
                await message.channel.send(f"❌ Invalid preset **`{act_text}`**. Type `!rn setstatus preset` to view the list!")
                return

            act_type = preset['type']
            act_text = preset['text']

    # Rotate Subcommand Routing
    rotate_mode = False
    if act_type in ("rotate", "rotation"):
        if act_text.lower() in ("on", "enable", "true", "start"):
            rotate_mode = True
            act_type = "playing"
            act_text = "Roblox | !rn help"
            if hasattr(bot, 'rotation_enabled'):
                bot.rotation_enabled = True
            await message.channel.send("🔄 **Auto-Rotation Enabled!** The bot will now automatically cycle through all premade activities every 45 seconds.")
        else:
            rotate_mode = False
            if hasattr(bot, 'rotation_enabled'):
                bot.rotation_enabled = False
            await message.channel.send("🛑 **Auto-Rotation Disabled.**")

    if act_type in ("clear", "none", "off", "reset"):
        activity = None
        act_type_save = "none"
        act_text_save = ""
    else:
        if not act_text and act_type not in ("rotate", "rotation"):
            act_text = args[0]
            act_type = "playing"
        activity = build_discord_activity(act_type, act_text)
        act_type_save = act_type
        act_text_save = act_text

    current_status = message.guild.me.status if message.guild and message.guild.me else discord.Status.online
    if current_status == discord.Status.offline:
        current_status = discord.Status.online

    try:
        await bot.change_presence(activity=activity, status=current_status)
        if hasattr(bot, 'db') and hasattr(bot.db, 'save_bot_presence'):
            stored = bot.db.get_bot_presence() if hasattr(bot.db, 'get_bot_presence') else {}
            vis_save = stored.get("visibility", "online")
            bot.db.save_bot_presence(act_type_save, act_text_save, vis_save, rotate_mode=rotate_mode)

        if act_type not in ("rotate", "rotation"):
            if activity:
                await message.channel.send(f"✅ **Bot Status Updated!** Activity set to: **{act_type.capitalize()}** `{act_text}`")
            else:
                await message.channel.send("✅ **Bot Status Cleared!** Activity cleared.")
    except Exception as e:
        await message.channel.send(f"❌ Failed to set status: `{e}`")

async def execute_setvisibility(bot, message: discord.Message, args: List[str]):
    if not message.author.guild_permissions.administrator:
        await message.channel.send("❌ Only Administrators can change the bot visibility.")
        return

    if not args:
        await message.channel.send(
            "❌ **Usage:** `!rn setvisibility <online|idle|dnd|invisible>`\n"
            "**Example:** `!rn setvisibility dnd` (🔴 Do Not Disturb)"
        )
        return

    status_input = args[0].lower()
    new_status = parse_discord_status(status_input)
    status_names = {
        discord.Status.online: "🟢 Online",
        discord.Status.idle: "🌙 Idle (Away)",
        discord.Status.dnd: "🔴 Do Not Disturb (DND)",
        discord.Status.invisible: "⚪ Invisible (Offline)"
    }
    status_label = status_names.get(new_status, "🟢 Online")

    try:
        stored = bot.db.get_bot_presence() if hasattr(bot, 'db') and hasattr(bot.db, 'get_bot_presence') else {}
        act_type_save = stored.get("activity_type", "playing")
        act_text_save = stored.get("activity_text", "Roblox | !rn help")

        activity = build_discord_activity(act_type_save, act_text_save)
        await bot.change_presence(activity=activity, status=new_status)

        if hasattr(bot, 'db') and hasattr(bot.db, 'save_bot_presence'):
            rot_mode = stored.get("rotate_mode", True)
            bot.db.save_bot_presence(act_type_save, act_text_save, status_input, rotate_mode=rot_mode)

        await message.channel.send(f"✅ **Bot Visibility Updated!** Presence indicator set to **{status_label}**.")
    except Exception as e:
        await message.channel.send(f"❌ Failed to set visibility: `{e}`")

async def execute_music_play_prefix(bot, message: discord.Message, args: List[str]):
    if not args:
        await message.channel.send("❌ Usage: `!rn play <song name or link>`")
        return

    from music_system import ensure_voice_connection, get_music_player, extract_tracks
    await ensure_voice_connection(bot)
    player = get_music_player(bot)
    query = " ".join(args)

    member = message.author if isinstance(message.author, discord.Member) else message.guild.get_member(message.author.id)

    try:
        tracks = await extract_tracks(query, member)
        if not tracks:
            await message.channel.send("❌ Could not find any audio for that query.")
            return

        if len(tracks) == 1:
            track = tracks[0]
            await player.add_track(track)
            await message.channel.send(f"🎵 Added **[{track.title}]({track.webpage_url})** (`{track.format_duration()}`) to the queurn!")
        else:
            for t in tracks:
                await player.add_track(t)
            await message.channel.send(f"🎶 Added **{len(tracks)} tracks** to the queurn!")
    except Exception as e:
        await message.channel.send(f"❌ Error adding track: `{e}`")

async def execute_music_skip_prefix(bot, message: discord.Message):
    from music_system import get_music_player
    player = get_music_player(bot)
    if player.is_playing() or player.is_paused():
        await player.skip()
        await message.channel.send("⏭️ Skipped current track.")
    else:
        await message.channel.send("❌ Nothing is playing.")

async def execute_music_filter_prefix(bot, message: discord.Message, args: List[str]):
    if not args:
        await message.channel.send("❌ Usage: `!rn filter <off|bassboost|nightcore|vaporwave|8d|reverb>`")
        return
    from music_system import get_music_player, AUDIO_FILTERS
    player = get_music_player(bot)
    target = args[0].lower()
    if target not in AUDIO_FILTERS:
        await message.channel.send(f"❌ Invalid filter. Available filters: `{', '.join(AUDIO_FILTERS.keys())}`")
        return

    player.active_filter = target
    if player.current and (player.is_playing() or player.is_paused()):
        import time
        elapsed = int(time.time() - player.start_time) + player.seek_offset
        await player.seek(elapsed)
    else:
        await player.update_panel()
    await message.channel.send(f"🎛️ Audio EQ filter set to **{target.capitalize()}**.")

async def execute_music_autoplay_prefix(bot, message: discord.Message, args: List[str]):
    from music_system import get_music_player
    player = get_music_player(bot)
    if args and args[0].lower() in ("off", "disable", "false", "stop"):
        player.autoplay = False
    else:
        player.autoplay = True
    await player.update_panel()
    status_str = "Enabled 📻" if player.autoplay else "Disabled 🛑"
    await message.channel.send(f"📻 Autoplay Mode set to **{status_str}**.")

async def execute_music_lyrics_prefix(bot, message: discord.Message, args: List[str]):
    from music_system import get_music_player, fetch_lyrics
    player = get_music_player(bot)
    query = " ".join(args) if args else (f"{player.current.title} {player.current.uploader}" if player.current else "")
    if not query:
        await message.channel.send("❌ Usage: `!rn lyrics <song name>`")
        return

    res = await fetch_lyrics(query)
    if not res or not res.get("lyrics"):
        await message.channel.send(f"❌ No lyrics found for **`{query}`**.")
        return

    lyrics_text = res["lyrics"]
    if len(lyrics_text) > 4000:
        lyrics_text = lyrics_text[:3990] + "\n..."

    embed = discord.Embed(title=f"📜 Lyrics • {res['title']}", description=lyrics_text, color=0x9B59B6)
    await message.channel.send(embed=embed)

async def execute_music_seek_prefix(bot, message: discord.Message, args: List[str]):
    if not args:
        await message.channel.send("❌ Usage: `!rn seek <MM:SS or seconds>` (e.g. `!rn seek 1:30`)")
        return
    from music_system import get_music_player
    player = get_music_player(bot)
    if not player.current or not (player.is_playing() or player.is_paused()):
        await message.channel.send("❌ Nothing is currently playing.")
        return

    timestamp = args[0]
    seconds = 0
    if ":" in timestamp:
        parts = timestamp.split(":")
        try:
            seconds = int(parts[0]) * 60 + int(parts[1])
        except Exception:
            await message.channel.send("❌ Invalid timestamp format. Use `MM:SS` (e.g. `1:30`).")
            return
    elif timestamp.isdigit():
        seconds = int(timestamp)
    else:
        await message.channel.send("❌ Invalid timestamp format.")
        return

    await player.seek(seconds)
    await message.channel.send(f"⏩ Seeked to **{seconds//60}:{seconds%60:02d}**.")

async def execute_music_forward_prefix(bot, message: discord.Message, args: List[str]):
    from music_system import get_music_player
    player = get_music_player(bot)
    if not player.current or not (player.is_playing() or player.is_paused()):
        await message.channel.send("❌ Nothing is currently playing.")
        return
    sec = int(args[0]) if args and args[0].isdigit() else 30
    import time
    elapsed = int(time.time() - player.start_time) + player.seek_offset
    new_pos = elapsed + sec
    await player.seek(new_pos)
    await message.channel.send(f"⏩ Fast-forwarded {sec}s to **{new_pos//60}:{new_pos%60:02d}**.")

async def execute_music_rewind_prefix(bot, message: discord.Message, args: List[str]):
    from music_system import get_music_player
    player = get_music_player(bot)
    if not player.current or not (player.is_playing() or player.is_paused()):
        await message.channel.send("❌ Nothing is currently playing.")
        return
    sec = int(args[0]) if args and args[0].isdigit() else 15
    import time
    elapsed = int(time.time() - player.start_time) + player.seek_offset
    new_pos = max(0, elapsed - sec)
    await player.seek(new_pos)
    await message.channel.send(f"⏪ Rewound {sec}s to **{new_pos//60}:{new_pos%60:02d}**.")

async def execute_music_voteskip_prefix(bot, message: discord.Message):
    from music_system import get_music_player
    player = get_music_player(bot)
    if not player.current or not (player.is_playing() or player.is_paused()):
        await message.channel.send("❌ Nothing is currently playing.")
        return

    member = message.author if isinstance(message.author, discord.Member) else message.guild.get_member(message.author.id)
    is_admin = member.guild_permissions.administrator
    is_requester = (player.current.requester and player.current.requester.id == member.id)
    has_dj = any("dj" in r.name.lower() or "music" in r.name.lower() for r in member.roles)

    if is_admin or is_requester or has_dj:
        await player.skip()
        await message.channel.send(f"⏭️ Instant skip executed by {member.mention}.")
        return

    player.voteskip_users.add(member.id)
    vc = player.voice_client.channel if player.voice_client else None
    vc_members = [m for m in vc.members if not m.bot] if vc else [member]
    req_votes = max(1, (len(vc_members) + 1) // 2)

    if len(player.voteskip_users) >= req_votes:
        await player.skip()
        await message.channel.send(f"⏭️ Vote skip passed! ({len(player.voteskip_users)}/{req_votes} votes). Skipped track.")
    else:
        await message.channel.send(f"🗳️ Vote recorded! **{len(player.voteskip_users)}/{req_votes}** votes required to skip.")

async def execute_music_playlist_prefix(bot, message: discord.Message, args: List[str]):
    if not args:
        await message.channel.send("❌ Usage: `!rn playlist <save/load/list/delete> [name]`")
        return

    from music_system import get_music_player, Track, ensure_voice_connection
    player = get_music_player(bot)
    action = args[0].lower()
    name = " ".join(args[1:]) if len(args) > 1 else ""

    if action == "save":
        if not name:
            await message.channel.send("❌ Please specify a playlist name: `!rn playlist save my_vibe`")
            return
        tracks_to_save = []
        if player.current:
            tracks_to_save.append(player.current.to_dict())
        for t in player.queue:
            tracks_to_save.append(t.to_dict())

        if hasattr(bot, 'db') and hasattr(bot.db, 'save_user_playlist'):
            bot.db.save_user_playlist(message.author.id, name, tracks_to_save)
            await message.channel.send(f"💾 **Playlist Saved!** Playlist **`{name}`** saved with **{len(tracks_to_save)} tracks**.")

    elif action == "load":
        if not name:
            await message.channel.send("❌ Please specify a playlist name: `!rn playlist load my_vibe`")
            return
        await ensure_voice_connection(bot)
        if hasattr(bot, 'db') and hasattr(bot.db, 'get_user_playlist'):
            tracks_data = bot.db.get_user_playlist(message.author.id, name)
            if not tracks_data:
                await message.channel.send(f"❌ Saved playlist **`{name}`** not found.")
                return
            count = 0
            member = message.author if isinstance(message.author, discord.Member) else message.guild.get_member(message.author.id)
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
            await message.channel.send(f"🎶 Loaded **{count} tracks** from playlist **`{name}`**!")

    elif action == "list":
        if hasattr(bot, 'db') and hasattr(bot.db, 'get_user_playlists_list'):
            playlists = bot.db.get_user_playlists_list(message.author.id)
            if not playlists:
                await message.channel.send("📜 You have no saved playlists.")
                return
            embed = discord.Embed(title=f"💾 Saved Playlists • {message.author.display_name}", color=0x3498DB)
            desc = ""
            for p in playlists:
                desc += f"• **`{p['playlist_name']}`** — `{p['track_count']} tracks` (created {p['created_at'][:10]})\n"
            embed.description = desc
            await message.channel.send(embed=embed)

    elif action in ("delete", "remove"):
        if hasattr(bot, 'db') and hasattr(bot.db, 'delete_user_playlist'):
            success = bot.db.delete_user_playlist(message.author.id, name)
            if success:
                await message.channel.send(f"🗑️ Deleted playlist **`{name}`**.")
            else:
                await message.channel.send(f"❌ Saved playlist **`{name}`** not found.")
