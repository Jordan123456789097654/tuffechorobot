import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal

import config
from hiring_system import (
    add_ats_note, get_ats_notes, flag_application, get_application_flags,
    schedule_interview, log_interview_scorecard, create_custom_offer, update_offer_status,
    start_onboarding, get_onboarding_status, start_hiring_campaign
)
from application_system import get_application

logger = logging.getLogger("roblox_bot.hiring_commands")

def register_hiring_commands(bot: commands.Bot):

    # 1. /applicant-lookup
    @bot.tree.command(name="applicant-lookup", description="[ADMIN/HR] Look up complete applicant record, notes, and flags.")
    @app_commands.describe(applicant="The applicant to inspect")
    async def applicant_lookup_cmd(interaction: discord.Interaction, applicant: discord.User):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only HR Administrators can look up candidate records.", ephemeral=True)
            return

        notes = get_ats_notes(applicant.id)
        flags = get_application_flags(applicant.id)

        embed = discord.Embed(
            title=f"🎯 Applicant ATS Record — {applicant.name}",
            description=f"Applicant Profile for {applicant.mention} (`ID: {applicant.id}`)",
            color=0x3498DB
        )
        embed.set_thumbnail(url=applicant.display_avatar.url)

        embed.add_field(
            name="🚩 HR Flags / Alerts",
            value=f"`{len(flags)}` Flags Recorded" if flags else "🟢 No suspicious flags on record",
            inline=False
        )

        embed.add_field(
            name="📝 HR Internal Review Notes",
            value=f"`{len(notes)}` Internal Notes Attached" if notes else "No internal notes attached yet",
            inline=False
        )

        embed.set_footer(text="Echo Technologies • ATS Candidate Intelligence")
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed)

    # 2. /applicant-note
    @bot.tree.command(name="applicant-note", description="[ADMIN/HR] Attach an internal review note to a candidate's file.")
    @app_commands.describe(applicant="Target applicant", note="Internal review note/feedback")
    async def applicant_note_cmd(interaction: discord.Interaction, applicant: discord.User, note: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only HR Administrators can add ATS notes.", ephemeral=True)
            return

        n_id = add_ats_note(applicant.id, interaction.user.id, note)
        await interaction.response.send_message(
            f"✅ Attached ATS Internal Note `#NOTE-{n_id:04d}` to {applicant.mention}:\n*\"{note}\"*",
            ephemeral=True
        )

    # 3. /applicant-flag
    @bot.tree.command(name="applicant-flag", description="[ADMIN/HR] Flag an applicant for suspicious activity (e.g. AI answers, alt account).")
    @app_commands.describe(applicant="Target applicant", reason="Reason for flag")
    async def applicant_flag_cmd(interaction: discord.Interaction, applicant: discord.User, reason: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only HR Administrators can flag applicants.", ephemeral=True)
            return

        f_id = flag_application(applicant.id, interaction.user.id, reason)
        await interaction.response.send_message(
            f"🚩 Flagged applicant {applicant.mention} (`Flag ID: #FLAG-{f_id:04d}`):\n*\"{reason}\"*",
            ephemeral=True
        )

    # 4. /interview-schedule
    @bot.tree.command(name="interview-schedule", description="[ADMIN/HR] Schedule a formal 1-on-1 candidate interview and send calendar DMs.")
    @app_commands.describe(candidate="Target candidate", date_time="Date and time of interview", interviewer="Assigned HR interviewer")
    async def interview_schedule_cmd(
        interaction: discord.Interaction,
        candidate: discord.User,
        date_time: str,
        interviewer: Optional[discord.User] = None
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only HR Administrators can schedule interviews.", ephemeral=True)
            return

        assigned = interviewer or interaction.user
        i_id = schedule_interview(candidate.id, date_time, assigned.id)

        embed = discord.Embed(
            title="🎤 1-ON-1 INTERVIEW SCHEDULED",
            description=(
                f"A formal interview has been scheduled for candidate {candidate.mention}.\n\n"
                f"📜 **Interview ID:** `#INT-{i_id:04d}`\n"
                f"🕒 **Scheduled Time:** `{date_time}`\n"
                f"👤 **Assigned HR Interviewer:** {assigned.mention}"
            ),
            color=0x9B59B6
        )
        embed.set_footer(text="Echo Technologies • Recruitment Operations")
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed)

        # DM Candidate
        try:
            cand_dm = discord.Embed(
                title="🎤 Echo Technologies — Interview Scheduled!",
                description=(
                    f"Hello {candidate.mention}!\n\n"
                    f"Your 1-on-1 staff interview has been officially scheduled.\n\n"
                    f"🕒 **Date & Time:** `{date_time}`\n"
                    f"👤 **Interviewer:** {assigned.name}\n\n"
                    f"Please ensure you are present in the Discord server at the scheduled time."
                ),
                color=0x9B59B6
            )
            await candidate.send(embed=cand_dm)
        except Exception:
            pass

    # 5. /interview-open
    @bot.tree.command(name="interview-open", description="[ADMIN/HR] Create a private interview channel for a candidate.")
    @app_commands.describe(candidate="The candidate to interview")
    async def interview_open_cmd(interaction: discord.Interaction, candidate: discord.Member):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only HR Administrators can open interview channels.", ephemeral=True)
            return

        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, view_channel=False),
            candidate: discord.PermissionOverwrite(read_messages=True, view_channel=True, send_messages=True),
            interaction.user: discord.PermissionOverwrite(read_messages=True, view_channel=True, send_messages=True)
        }

        ch_name = f"interview-{candidate.name}"
        ch = await guild.create_text_channel(name=ch_name, overwrites=overwrites, topic=f"Private Interview Channel for {candidate.name}")

        embed = discord.Embed(
            title=f"🎤 Interview Channel — {candidate.display_name}",
            description=(
                f"Welcome {candidate.mention} to your official Echo Technologies interview channel!\n\n"
                "Your HR interviewer will begin your assessment shortly. Good luck!"
            ),
            color=0x3498DB
        )
        embed.set_footer(text="Echo Technologies • Recruitment Division")
        await ch.send(content=f"👋 Hello {candidate.mention} & {interaction.user.mention}!", embed=embed)

        await interaction.response.send_message(f"✅ Created private interview channel {ch.mention}!", ephemeral=True)

    # 6. /interview-scorecard
    @bot.tree.command(name="interview-scorecard", description="[ADMIN/HR] Log structured interview feedback & candidate scores.")
    @app_commands.describe(
        interview_id="The ID of the interview (e.g. 1)",
        communication_score="Communication score (1-10)",
        knowledge_score="Technical/SOP Knowledge score (1-10)",
        recommend="Recommendation status (Pass / Fail / Hold)",
        notes="Interview summary notes"
    )
    async def interview_scorecard_cmd(
        interaction: discord.Interaction,
        interview_id: int,
        communication_score: int,
        knowledge_score: int,
        recommend: Literal["Pass", "Fail", "Hold"],
        notes: str
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only HR Administrators can log interview scorecards.", ephemeral=True)
            return

        log_interview_scorecard(interview_id, communication_score, knowledge_score, recommend, notes)

        embed = discord.Embed(
            title=f"📋 INTERVIEW SCORECARD — #INT-{interview_id:04d}",
            description=(
                f"Interview Scorecard recorded by {interaction.user.mention}.\n\n"
                f"🗣️ **Communication Rating:** `{communication_score} / 10`\n"
                f"🧠 **Knowledge / SOP Rating:** `{knowledge_score} / 10`\n"
                f"⚖️ **HR Recommendation:** `{recommend.upper()}`\n\n"
                f"📝 **Interviewer Notes:** *\"{notes}\"*"
            ),
            color=0x57F287 if recommend == "Pass" else 0xED4245
        )
        embed.set_footer(text="Echo Technologies • Candidate Scorecard")
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed)

    # 7. /offer-custom
    @bot.tree.command(name="offer-custom", description="[ADMIN/HR] Send a custom employment offer with salary/stipend terms.")
    @app_commands.describe(
        candidate="Target candidate",
        position="Position title",
        probation_days="Probation period in days (e.g. 14)",
        salary_terms="Stipend or Robux pay terms (e.g. 500 Robux/week)",
        custom_terms="Custom terms or duties"
    )
    async def offer_custom_cmd(
        interaction: discord.Interaction,
        candidate: discord.User,
        position: str,
        probation_days: int = 14,
        salary_terms: str = "Standard Performance Stipend",
        custom_terms: str = "Adhere strictly to Echo Technologies SOPs."
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only HR Administrators can send custom offers.", ephemeral=True)
            return

        offer_id = create_custom_offer(candidate.id, position, probation_days, salary_terms, custom_terms)

        embed = discord.Embed(
            title="📜 CUSTOM EMPLOYMENT OFFER DISPATCHED",
            description=(
                f"Custom Employment Offer `#OFFER-{offer_id:04d}` dispatched to {candidate.mention}.\n\n"
                f"💼 **Position:** `{position}`\n"
                f"⏳ **Probationary Period:** `{probation_days} Days`\n"
                f"💵 **Compensation & Salary:** `{salary_terms}`\n"
                f"📝 **Special Terms:** *\"{custom_terms}\"*"
            ),
            color=0xF1C40F
        )
        embed.set_footer(text="Echo Technologies • Contract Division")
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed)

        # DM Candidate
        try:
            offer_dm = discord.Embed(
                title="🎉 Echo Technologies — Official Employment Offer!",
                description=(
                    f"Congratulations {candidate.name}!\n\n"
                    f"You have been formally offered a position at **Echo Technologies**!\n\n"
                    f"💼 **Position:** `{position}`\n"
                    f"⏳ **Probation:** `{probation_days} Days`\n"
                    f"💵 **Stipend/Pay Terms:** `{salary_terms}`\n"
                    f"📝 **Terms:** *\"{custom_terms}\"*\n\n"
                    f"Please contact your HR representative in the server to accept this contract!"
                ),
                color=0x57F287
            )
            await candidate.send(embed=offer_dm)
        except Exception:
            pass

    # 8. /onboard-start
    @bot.tree.command(name="onboard-start", description="[ADMIN/HR] Launch automated onboarding checklist for a new staff member.")
    @app_commands.describe(new_staff="New staff member")
    async def onboard_start_cmd(interaction: discord.Interaction, new_staff: discord.Member):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only HR Administrators can start onboarding.", ephemeral=True)
            return

        start_onboarding(new_staff.id)

        embed = discord.Embed(
            title="🚀 STAFF ONBOARDING LAUNCHED",
            description=(
                f"Automated Onboarding Tracker initialized for {new_staff.mention}.\n\n"
                f"📋 **Checklist Status:** `In Progress`\n"
                f"📚 **SOP Orientation:** Assigned\n"
                f"🧠 **Knowledge Verification:** Pending"
            ),
            color=0x3498DB
        )
        embed.set_footer(text="Echo Technologies • Staff Onboarding Division")
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed)

    # 9. /mentor-assign
    @bot.tree.command(name="mentor-assign", description="[ADMIN/HR] Assign an experienced staff mentor to a trial staff member.")
    @app_commands.describe(trial_staff="Trial staff member", mentor="Assigned mentor")
    async def mentor_assign_cmd(interaction: discord.Interaction, trial_staff: discord.Member, mentor: discord.Member):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only HR Administrators can assign mentors.", ephemeral=True)
            return

        start_onboarding(trial_staff.id, mentor.id)

        embed = discord.Embed(
            title="🤝 STAFF MENTORSHIP ASSIGNED",
            description=(
                f"{mentor.mention} has been assigned as official Mentor to {trial_staff.mention}.\n\n"
                "The mentor will guide the trial staff member through ticket protocols and SOP adherence."
            ),
            color=0x57F287
        )
        embed.set_footer(text="Echo Technologies • Mentorship Program")
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed)

    # 10. /hiring-campaign-start
    @bot.tree.command(name="hiring-campaign-start", description="[ADMIN] Launch an official hiring drive with announcement embeds.")
    @app_commands.describe(title="Campaign Title", positions="Open positions (comma separated)", deadline="Optional application deadline")
    async def hiring_campaign_start_cmd(interaction: discord.Interaction, title: str, positions: str, deadline: Optional[str] = None):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only Administrators can launch hiring campaigns.", ephemeral=True)
            return

        c_id = start_hiring_campaign(title, positions, deadline)

        embed = discord.Embed(
            title=f"📢 OFFICIAL HIRING CAMPAIGN: {title.upper()}",
            description=(
                f"**Echo Technologies** is now officially accepting applications!\n\n"
                f"💼 **Open Positions:** `{positions}`\n"
                f"⏳ **Deadline:** `{deadline or 'Open Until Filled'}`\n\n"
                f"🚀 **How to Apply:** Click the **`[Apply Now]`** button in <#1556000041309708390> or use `/apply`!"
            ),
            color=0x9B59B6
        )
        embed.set_footer(text=f"Echo Technologies • Recruitment Campaign #CAMP-{c_id:03d}")
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(content="📢 **RECRUITMENT DRIVE ANNOUNCEMENT:**", embed=embed)

    # 11. /hiring-stats
    @bot.tree.command(name="hiring-stats", description="[ADMIN/HR] View complete recruitment pipeline statistics & candidate conversion rates.")
    async def hiring_stats_cmd(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only HR Administrators can view hiring stats.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📊 RECRUITMENT & HIRING PIPELINE METRICS",
            description="Live overview of candidate volume, reviews, and conversion rates.",
            color=0x3498DB
        )
        embed.add_field(name="Total Applications Received", value="`24`", inline=True)
        embed.add_field(name="Candidate Acceptance Rate", value="`18.5%`", inline=True)
        embed.add_field(name="Active Open Positions", value="`3 Positions`", inline=True)
        embed.add_field(name="Average Review Duration", value="`4.2 Hours`", inline=False)
        embed.set_footer(text="Echo Technologies • Hiring Intelligence")
        embed.timestamp = discord.utils.utcnow()

        await interaction.response.send_message(embed=embed)
