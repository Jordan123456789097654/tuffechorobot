import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal

import config
from hr_extended_system import (
    clock_in_staff, clock_out_staff, get_staff_shift_stats,
    add_commendation, get_user_commendations, PRESET_COMMENDATION_REWARDS,
    create_staff_meeting, set_meeting_message, StaffMeetingRSVPView, get_meeting_rsvp_counts
)
from hr_system import (
    add_strike, get_staff_strikes, pardon_strike, format_severity,
    suspend_staff_member, unsuspend_staff_member, get_active_suspension,
    add_staff_blacklist, remove_staff_blacklist, get_staff_blacklists, is_staff_blacklisted,
    add_staff_evaluation, get_staff_evaluations
)
from loa_system import (
    create_loa_request, get_user_active_loa, get_loa_requests, review_loa_request, LOAControlView
)

logger = logging.getLogger("roblox_bot.hr_commands")

def register_hr_commands(bot: commands.Bot):

    # 1. /duty <on/off>
    @bot.tree.command(name="duty", description="Clock in or out of your active support staff shift.")
    @app_commands.describe(action="Choose whether to clock ON or OFF duty")
    async def duty_cmd(interaction: discord.Interaction, action: Literal["on", "off"]):
        member = interaction.user
        on_duty_role = discord.utils.get(interaction.guild.roles, name="On Duty Staff")
        if not on_duty_role:
            # Create if missing
            try:
                on_duty_role = await interaction.guild.create_role(
                    name="On Duty Staff",
                    color=discord.Color.blue(),
                    reason="Created automatically for staff duty tracking"
                )
            except Exception:
                pass

        if action == "on":
            success = clock_in_staff(member.id)
            if not success:
                await interaction.response.send_message("⚠️ You are already clocked **ON duty**!", ephemeral=True)
                return

            if on_duty_role:
                try:
                    await member.add_roles(on_duty_role, reason="Clocked ON duty")
                except Exception:
                    pass

            embed = discord.Embed(
                title="🟢 CLOCKED ON DUTY",
                description=f"{member.mention} is now actively **ON DUTY**.",
                color=0x57F287
            )
            embed.set_footer(text="Echo Technologies • Shift Active")
            embed.timestamp = discord.utils.utcnow()

            await interaction.response.send_message(embed=embed)

        else:
            duration_sec = clock_out_staff(member.id)
            if duration_sec is None:
                await interaction.response.send_message("⚠️ You are not currently clocked ON duty!", ephemeral=True)
                return

            if on_duty_role and on_duty_role in member.roles:
                try:
                    await member.remove_roles(on_duty_role, reason="Clocked OFF duty")
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
            embed.set_footer(text="Echo Technologies • Shift Complete")
            embed.timestamp = discord.utils.utcnow()

            await interaction.response.send_message(embed=embed)

    # 2. /shift-stats
    @bot.tree.command(name="shift-stats", description="View shift hours and duty statistics for yourself or a staff member.")
    @app_commands.describe(member="Optional staff member to check")
    async def shift_stats_cmd(interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        stats = get_staff_shift_stats(target.id)

        tot_h = stats["total_seconds"] // 3600
        tot_m = (stats["total_seconds"] % 3600) // 60

        w_h = stats["weekly_seconds"] // 3600
        w_m = (stats["weekly_seconds"] % 3600) // 60

        status_str = "🟢 **ON DUTY**" if stats["is_on_duty"] else "🔴 **OFF DUTY**"

        embed = discord.Embed(
            title=f"⏱️ Shift Statistics — {target.display_name}",
            color=0x3498DB
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Current Status", value=status_str, inline=True)
        embed.add_field(name="Total Shifts Completed", value=f"`{stats['total_shifts']}`", inline=True)
        embed.add_field(name="Weekly Duty Hours (Past 7 Days)", value=f"`{w_h}h {w_m}m`", inline=False)
        embed.add_field(name="Lifetime Duty Hours", value=f"`{tot_h}h {tot_m}m`", inline=False)
        embed.set_footer(text="Echo Technologies • Staff HR Duty Records")
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed)

    # 3. /commend <member> <reward> <reason>
    @bot.tree.command(name="commend", description="[ADMIN] Issue an official HR commendation with preset rewards to a staff member.")
    @app_commands.describe(
        member="The staff member to commend",
        reward="Choose a preset commendation reward",
        reason="Reason for the commendation"
    )
    @app_commands.choices(reward=[
        app_commands.Choice(name="🎟️ 1-Week Staff Quota Exemption", value="quota_exemption"),
        app_commands.Choice(name="💰 1,000 Community Points", value="points_1000"),
        app_commands.Choice(name="🌟 Special Custom Role / Title", value="custom_role"),
        app_commands.Choice(name="⚡ Priority Ticket Assignment", value="priority_queue"),
        app_commands.Choice(name="💵 500 Robux Reward Code", value="robux_card"),
        app_commands.Choice(name="🎖️ Staff Commendation Badge", value="recognition_badge")
    ])
    async def commend_cmd(interaction: discord.Interaction, member: discord.Member, reward: app_commands.Choice[str], reason: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only Administrators can issue commendations.", ephemeral=True)
            return

        reward_display = PRESET_COMMENDATION_REWARDS.get(reward.value, reward.name)
        comm_id = add_commendation(member.id, interaction.user.id, reason, reward.value)

        embed = discord.Embed(
            title="🎖️ OFFICIAL HR COMMENDATION",
            description=(
                f"**Echo Technologies Management** has formally issued a Commendation to {member.mention}!\n\n"
                f"📜 **Commendation ID:** `#COMM-{comm_id:04d}`\n"
                f"🎁 **Preset Reward:** {reward_display}\n"
                f"📋 **Reason:** *\"{reason}\"*\n"
                f"👤 **Awarded By:** {interaction.user.mention}"
            ),
            color=0xF1C40F # Gold
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Echo Technologies • HR Honor & Recognition Division")
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed)

        # DM the staff member
        try:
            dm_embed = discord.Embed(
                title="🎖️ CONGRATULATIONS! You Received a Commendation!",
                description=(
                    f"You have been awarded an official HR Commendation by **Echo Technologies**!\n\n"
                    f"🎁 **Reward:** {reward_display}\n"
                    f"📋 **Reason:** *\"{reason}\"*"
                ),
                color=0xF1C40F
            )
            await member.send(embed=dm_embed)
        except Exception:
            pass

    # 4. /staff-meeting-announce
    @bot.tree.command(name="staff-meeting-announce", description="[ADMIN] Announce an official staff meeting in #staff-announcements with RSVP buttons.")
    @app_commands.describe(
        date_time="Date and time of meeting (e.g. Saturday Oct 10 @ 5:00 PM EST)",
        topic="Primary topic of discussion",
        mandatory="Whether attendance is mandatory for staff",
        location="Voice/Text channel location (e.g. Staff Voice Channel #1)",
        agenda="Key agenda points to cover",
        notes="Optional additional meeting notes",
        target_channel="Channel to send announcement (defaults to #staff-announcements)"
    )
    async def staff_meeting_announce_cmd(
        interaction: discord.Interaction,
        date_time: str,
        topic: str,
        mandatory: bool = True,
        location: str = "Staff Voice Channel #1",
        agenda: Optional[str] = None,
        notes: Optional[str] = None,
        target_channel: Optional[discord.TextChannel] = None
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only Administrators can announce staff meetings.", ephemeral=True)
            return

        guild = interaction.guild
        announce_ch = target_channel
        if not announce_ch and guild:
            announce_ch = discord.utils.get(guild.text_channels, name="staff-announcements")
            if not announce_ch:
                for ch in guild.text_channels:
                    if "staff-announc" in ch.name.lower() or "staff_announc" in ch.name.lower():
                        announce_ch = ch
                        break

        if not announce_ch:
            announce_ch = interaction.channel

        m_id = create_staff_meeting("Official Staff Meeting", date_time, topic, mandatory, notes, location, agenda)
        view = StaffMeetingRSVPView(m_id)

        embed = discord.Embed(
            title="📅 OFFICIAL STAFF MEETING ANNOUNCEMENT",
            description=(
                f"An official staff meeting has been scheduled by **Echo Technologies Management**.\n"
                f"All staff members are required to select their RSVP status below."
            ),
            color=0x9B59B6 # Purple
        )
        embed.add_field(name="🕒 Date & Time", value=f"```\n{date_time}\n```", inline=False)
        embed.add_field(name="📌 Primary Topic", value=topic, inline=False)
        embed.add_field(name="📍 Location", value=f"`{location}`", inline=True)
        embed.add_field(name="⚠️ Attendance Policy", value="`🔴 MANDATORY ATTENDANCE`" if mandatory else "`🟢 OPTIONAL ATTENDANCE`", inline=True)
        if agenda:
            embed.add_field(name="📋 Meeting Agenda", value=agenda, inline=False)
        if notes:
            embed.add_field(name="📝 Additional Notes", value=notes, inline=False)

        embed.add_field(
            name="📊 RSVP Status Summary",
            value="✅ **Attending:** `0` | ❌ **Cannot Attend:** `0` | ⏳ **Tentative:** `0`",
            inline=False
        )

        embed.set_footer(text=f"Echo Technologies • Staff Meeting #M-{m_id:03d}")
        embed.timestamp = discord.utils.utcnow()

        msg = await announce_ch.send(content="📢 **ATTENTION ALL STAFF MEMBERS:**", embed=embed, view=view)
        set_meeting_message(m_id, announce_ch.id, msg.id)

        await interaction.response.send_message(
            f"✅ **Staff Meeting `#M-{m_id:03d}` Announced!**\n"
            f"Embed posted in {announce_ch.mention}! (Message ID: `{msg.id}`)",
            ephemeral=True
        )

    # 4b. /staff-meeting-cancel
    @bot.tree.command(name="staff-meeting-cancel", description="[ADMIN] Cancel a scheduled staff meeting and notify staff.")
    @app_commands.describe(meeting_id="The Meeting ID to cancel (e.g. 1)", reason="Cancellation reason")
    async def staff_meeting_cancel_cmd(interaction: discord.Interaction, meeting_id: int, reason: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only Administrators can cancel staff meetings.", ephemeral=True)
            return

        from hr_extended_system import get_staff_meeting, update_meeting_status
        m = get_staff_meeting(meeting_id)
        if not m:
            await interaction.response.send_message(f"❌ Meeting `#M-{meeting_id:03d}` not found.", ephemeral=True)
            return

        update_meeting_status(meeting_id, "Cancelled", reason)

        # Try to edit original message
        if m["channel_id"] and m["message_id"]:
            try:
                ch = interaction.guild.get_channel(m["channel_id"]) or await interaction.guild.fetch_channel(m["channel_id"])
                msg = await ch.fetch_message(m["message_id"])

                cancel_embed = discord.Embed(
                    title=f"🔴 MEETING CANCELLED — #M-{meeting_id:03d}",
                    description=(
                        f"**This staff meeting has been officially CANCELLED.**\n\n"
                        f"📌 **Original Topic:** {m['topic']}\n"
                        f"🕒 **Scheduled Date:** `{m['date_time']}`\n\n"
                        f"📋 **Cancellation Reason:** *\"{reason}\"*\n"
                        f"👤 **Cancelled By:** {interaction.user.mention}"
                    ),
                    color=0xED4245
                )
                cancel_embed.set_footer(text="Echo Technologies • Staff HR Administration")
                cancel_embed.timestamp = discord.utils.utcnow()

                await msg.edit(content="🚨 **MEETING CANCELLED NOTICE:**", embed=cancel_embed, view=None)
            except Exception as e:
                logger.error(f"Error editing meeting embed: {e}")

        await interaction.response.send_message(f"✅ Staff Meeting `#M-{meeting_id:03d}` has been officially cancelled!", ephemeral=True)

    # 4c. /staff-meeting-end
    @bot.tree.command(name="staff-meeting-end", description="[ADMIN] Conclude a staff meeting and publish official meeting minutes.")
    @app_commands.describe(meeting_id="The Meeting ID (e.g. 1)", summary_notes="Meeting summary notes / key takeaways")
    async def staff_meeting_end_cmd(interaction: discord.Interaction, meeting_id: int, summary_notes: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only Administrators can conclude staff meetings.", ephemeral=True)
            return

        from hr_extended_system import get_staff_meeting, update_meeting_status, get_meeting_rsvp_counts
        m = get_staff_meeting(meeting_id)
        if not m:
            await interaction.response.send_message(f"❌ Meeting `#M-{meeting_id:03d}` not found.", ephemeral=True)
            return

        update_meeting_status(meeting_id, "Completed", summary_notes)
        counts = get_meeting_rsvp_counts(meeting_id)

        minutes_embed = discord.Embed(
            title=f"📜 OFFICIAL MEETING MINUTES — #M-{meeting_id:03d}",
            description=(
                f"**Staff Meeting Concluded & Summary Logged**\n\n"
                f"📌 **Topic:** {m['topic']}\n"
                f"🕒 **Held On:** `{m['date_time']}`\n"
                f"📊 **Attendance:** `{counts['attending']}` Attended | `{counts['cannot_attend']}` Absent\n\n"
                f"📝 **Meeting Minutes & Key Takeaways:**\n*{summary_notes}*"
            ),
            color=0x57F287
        )
        minutes_embed.set_footer(text="Echo Technologies • HR Records Archive")
        minutes_embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=minutes_embed)

    # 5. /promote
    @bot.tree.command(name="promote", description="[ADMIN] Formally promote a staff member and log to HR.")
    @app_commands.describe(member="Staff member to promote", new_role="Target new role", reason="Promotion rationale")
    async def promote_cmd(interaction: discord.Interaction, member: discord.Member, new_role: discord.Role, reason: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only Administrators can promote staff.", ephemeral=True)
            return

        try:
            await member.add_roles(new_role, reason=f"Promotion by {interaction.user}: {reason}")
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to assign role: `{e}`", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎉 OFFICIAL STAFF PROMOTION",
            description=(
                f"**Congratulations to {member.mention}!**\n\n"
                f"🎖️ **New Rank:** {new_role.mention}\n"
                f"📋 **Rationale:** *\"{reason}\"*\n"
                f"👤 **Promoted By:** {interaction.user.mention}"
            ),
            color=0x57F287
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Echo Technologies • HR Advancement Division")
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed)

    # 6. /demote
    @bot.tree.command(name="demote", description="[ADMIN] Formally demote a staff member.")
    @app_commands.describe(member="Staff member to demote", new_role="Target new role", reason="Demotion reason")
    async def demote_cmd(interaction: discord.Interaction, member: discord.Member, new_role: discord.Role, reason: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only Administrators can demote staff.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📉 OFFICIAL HR DEMOTION NOTICE",
            description=(
                f"An official rank adjustment has been executed for {member.mention}.\n\n"
                f"🔻 **New Rank:** {new_role.mention}\n"
                f"📋 **Reason:** *\"{reason}\"*\n"
                f"👤 **Processed By:** {interaction.user.mention}"
            ),
            color=0xED4245
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Echo Technologies • HR Administration")
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed)

    # 7. /staff-dossier <member>
    @bot.tree.command(name="staff-dossier", description="[ADMIN/STAFF] View the complete 360° HR file for a staff member.")
    @app_commands.describe(member="The staff member to inspect")
    async def staff_dossier_cmd(interaction: discord.Interaction, member: discord.Member):
        shift_data = get_staff_shift_stats(member.id)
        strikes = get_staff_strikes(member.id)
        evals = get_staff_evaluations(member.id)
        comms = get_user_commendations(member.id)

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
            value=(
                f"• **Status:** {'🟢 On Duty' if shift_data['is_on_duty'] else '🔴 Off Duty'}\n"
                f"• **Weekly Hours:** `{w_h}h` | **Lifetime:** `{tot_h}h` (`{shift_data['total_shifts']}` shifts)"
            ),
            inline=False
        )

        embed.add_field(
            name="📊 Performance & Evaluation",
            value=(
                f"• **Average Exam Score:** `{avg_eval:.1f} / 100`\n"
                f"• **Commendations Received:** `{len(comms)}` medals\n"
                f"• **Evaluations Completed:** `{len(evals)}`"
            ),
            inline=False
        )

        embed.add_field(
            name="⚠️ Disciplinary Record",
            value=(
                f"• **Active Strikes:** `{len(active_strikes)}` | **Lifetime:** `{len(strikes)}`\n"
                f"• **Blacklist Status:** {'🔴 BLACKLISTED' if is_staff_blacklisted(member.id) else '🟢 CLEAN'}"
            ),
            inline=False
        )

        embed.set_footer(text="Echo Technologies • Personnel File Confidential")
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed)
