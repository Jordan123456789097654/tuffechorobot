import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import sys
import logging
import os
import io
import secrets
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal


import config
from roblox_api import RobloxAPI
from database import VerificationDatabase
from views import VerificationLaunchView
from ai_trainer import AITrainer
from groq_assistant import GroqAssistant
from ticket_manager import TicketManager
from ticket_views import (
    TicketLaunchView,
    TicketControlView,
    TicketRatingView,
    SendSuggestedReplyView,
    CannedReplySelectView,
    InternalNoteModal,
    TestTicketTrainerControlView
)
from transcript_generator import generate_html_transcript, generate_application_html_transcript
from hire_system import HireOfferView, handle_hire_action, create_hire_offer
from hr_system import (
    add_strike, get_staff_strikes, get_strike, pardon_strike,
    format_severity, build_strike_dm_embed, build_strike_log_embed,
    evaluate_strike_escalation, suspend_staff_member, unsuspend_staff_member,
    get_active_suspension, check_expired_suspensions, check_strike_expiration,
    add_watchlist_user, remove_watchlist_user, get_watchlist, evaluate_watchlist_message,
    add_staff_blacklist, remove_staff_blacklist, get_staff_blacklists, is_staff_blacklisted,
    build_staff_dossier_embed, StrikeAppealModal, HRAppealControlView, StrikeDMAppealView, StrikeDMAppealModal,
    add_staff_evaluation, get_staff_evaluations, build_evaluation_dm_embed, build_evaluation_log_embed
)
from suggestions_system import (
    create_suggestion, set_suggestion_message, get_suggestion,
    get_vote_counts, vote_suggestion, update_suggestion_status,
    build_suggestion_embed, SuggestionVoteView, ReviewSuggestionModal
)
from bug_tracker_system import (
    create_bug_report, set_bug_message, get_bug_report,
    claim_bug, update_bug_status, get_recent_bugs,
    build_bug_embed, BugReportControlView, ResolveBugModal
)
from welcome_system import (
    send_welcome_greeting, send_verification_announcement,
    build_welcome_embed
)
from giveaways_system import (
    create_giveaway, set_giveaway_message, get_giveaway, get_giveaway_by_message,
    toggle_giveaway_entry, build_giveaway_embed, GiveawayView, end_giveaway,
    reroll_giveaway, parse_duration, check_active_giveaways_loop
)
from events_system import (
    create_event, set_event_message, get_event, get_upcoming_events,
    get_event_rsvp_counts, set_event_rsvp, cancel_event, build_event_embed,
    EventRsvpView, broadcast_event_dm_task, check_event_reminders_loop
)
from loa_system import (
    create_loa_request, set_loa_message_id, get_loa_request, get_user_active_loa,
    get_loa_requests, review_loa_request, build_loa_staff_embed, LOAControlView, DenyLOAModal
)
from leveling_system import (
    award_message_xp, get_user_level_data, get_user_rank_position,
    get_guild_leaderboard, build_rank_card_embed, build_leaderboard_embed,
    set_member_level
)
from starboard_system import handle_star_reaction
from application_system import (
    APPLICATION_POSITIONS, build_career_panel_embed, CareerLaunchView,
    start_dm_application_flow, handle_applicant_dm_message,
    get_application, review_application, build_application_dossier_embed,
    ApplicationControlView, DenyApplicationModal, AskApplicantModal,
    close_applications, open_applications, get_all_position_statuses,
    is_position_open, sync_career_panel_message, get_application_stats
)
from moderation_system import (
    dispatch_mod_log, parse_duration, format_duration,
    send_dm_infraction_notice, add_warning, get_warnings,
    clear_warnings, execute_global_ban, execute_global_unban,
    is_globally_banned, get_all_global_bans, get_mod_case,
    InfractionAppealDMView, ModAppealReviewView, InfractionAppealModal
)
from partnership_system import (
    publish_affiliate_partnership, update_affiliate_partnership, remove_affiliate_partnership,
    get_all_partnerships, get_partnership, PARTNER_CATEGORIES, ECHO_AD_COPY,
    PartnerPortalView, PartnerApplicationModal, PartnerDirectoryView, check_partner_health,
    verify_partner_ad_proof
)
from invite_comp_system import (
    create_invite_competition, set_invite_comp_message, get_invite_competition,
    get_active_invite_competitions, record_member_join_invite, record_member_leave_invite,
    disqualify_inviter, edit_invite_competition, update_invite_competition_embed,
    get_inviter_counts, get_user_invite_stats, build_invite_comp_embed, InviteCompControlView,
    end_invite_competition, check_invite_competitions_loop
)
from points_system import (
    get_user_points, add_points, remove_points, set_points,
    mark_reward_claimed, get_points_leaderboard, render_progress_bar,
    evaluate_message_for_point, build_reward_unlocked_embed,
    build_point_earned_embed, REWARD_CATALOGUE, redeem_reward,
    get_user_redemptions, tip_points, build_tip_embed,
    build_shop_embed, PointsShopView
)
from support_templates_system import sync_support_templates_channel
from supervisor_templates_system import sync_supervisor_templates_channel, SupervisorCategorySelectView






async def safe_fetch_user(client, user_id: int):
    """Returns a cached/fetched user or None if the account no longer exists / can't be fetched."""
    user = client.get_user(user_id)
    if user:
        return user
    try:
        return await client.fetch_user(user_id)
    except Exception:
        return None


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("RobloxVerifyBot")

# Set up required intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.dm_messages = True

class RobloxVerificationBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )
        self.roblox_api = RobloxAPI()
        self.db = VerificationDatabase()
        self.ai_trainer = AITrainer()
        self.groq_assistant = GroqAssistant(self.ai_trainer)
        self.ticket_manager = TicketManager()
        self.invite_cache = {}
        self.invite_lock = asyncio.Lock()

    async def setup_hook(self):
        # Register persistent views
        self.add_view(VerificationLaunchView(self.roblox_api, self.db))
        self.add_view(TicketLaunchView(self))
        self.add_view(TicketControlView(self))
        self.add_view(CareerLaunchView())
        self.add_view(PartnerPortalView(self))
        self.add_view(StrikeDMAppealView())
        self.add_view(HRAppealControlView(0))
        self.add_view(InfractionAppealDMView())
        self.add_view(ModAppealReviewView())
        self.add_view(InviteCompControlView(self, 0))
        self.add_view(SupervisorCategorySelectView())


        # Sync slash commands
        try:
            if config.GUILD_ID:
                guild_obj = discord.Object(id=config.GUILD_ID)
                self.tree.copy_global_to(guild=guild_obj)
                synced = await self.tree.sync(guild=guild_obj)
                logger.info(f"Synced {len(synced)} slash commands to guild {config.GUILD_ID}.")
            else:
                synced = await self.tree.sync()
                logger.info(f"Synced {len(synced)} global slash commands.")
        except Exception as e:
            logger.error(f"Error syncing application commands: {e}")

    async def close(self):
        await self.roblox_api.close()
        await super().close()

    async def get_escalated_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Finds or retrieves the escalated tickets channel."""
        if config.ESCALATED_TICKETS_CHANNEL_ID:
            ch = self.get_channel(config.ESCALATED_TICKETS_CHANNEL_ID) or (guild.get_channel(config.ESCALATED_TICKETS_CHANNEL_ID) if guild else None)
            if not ch:
                try:
                    ch = await self.fetch_channel(config.ESCALATED_TICKETS_CHANNEL_ID)
                except Exception as e:
                    logger.warning(f"Could not fetch escalated channel {config.ESCALATED_TICKETS_CHANNEL_ID}: {e}")
                    ch = None
            if isinstance(ch, discord.TextChannel):
                return ch

        if guild:
            for ch in guild.text_channels:
                if "escalat" in ch.name.lower():
                    return ch
        return None

    async def get_transcript_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Finds or retrieves the transcripts channel."""
        if config.TRANSCRIPT_CHANNEL_ID:
            ch = self.get_channel(config.TRANSCRIPT_CHANNEL_ID) or (guild.get_channel(config.TRANSCRIPT_CHANNEL_ID) if guild else None)
            if not ch:
                try:
                    ch = await self.fetch_channel(config.TRANSCRIPT_CHANNEL_ID)
                except Exception as e:
                    logger.warning(f"Could not fetch transcript channel {config.TRANSCRIPT_CHANNEL_ID}: {e}")
                    ch = None
            if isinstance(ch, discord.TextChannel):
                return ch

        if guild:
            for ch in guild.text_channels:
                if "transcript" in ch.name.lower():
                    return ch
        return None

    async def create_support_ticket(
        self,
        user: discord.User,
        initial_query: str,
        guild: Optional[discord.Guild] = None,
        section: str = "General Support"
    ) -> Optional[discord.TextChannel]:
        """Creates a ticket channel in the guild under config.TICKETS_CATEGORY_ID."""
        if not guild:
            guild = self.get_primary_guild()
        if not guild:
            logger.error("No guild found to create ticket in.")
            return None

        # Determine category (1556000041309708390)
        category = None
        if config.TICKETS_CATEGORY_ID:
            category = guild.get_channel(config.TICKETS_CATEGORY_ID)
            if not category:
                try:
                    category = await guild.fetch_channel(config.TICKETS_CATEGORY_ID)
                except Exception:
                    category = None
            if not isinstance(category, discord.CategoryChannel):
                category = None

        if not category:
            for cat in guild.categories:
                if "ticket" in cat.name.lower() or "support" in cat.name.lower():
                    category = cat
                    break

        # Setup channel permissions:
        # Strictly hidden from the user & @everyone! ONLY Support Team role & bot can view!
        escalation_role = guild.get_role(config.ESCALATION_ROLE_ID)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True, attach_files=True)
        }
        if escalation_role:
            overwrites[escalation_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )

        prefix = section.lower()[:3].replace(" ", "")
        channel_name = f"{prefix}-{user.name.lower().replace(' ', '-')[:15]}"
        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"[{section}] Support ticket for {user.name} ({user.id}) • Modmail Channel"
            )
        except Exception as e:
            logger.error(f"Error creating ticket channel: {e}")
            return None

        # Save ticket in database
        ticket_id = self.ticket_manager.create_ticket(user.id, channel.id, guild.id, section=section)
        self.ticket_manager.add_message(ticket_id, user.id, "user", initial_query, sender_name=user.name)

        # Retrieve Roblox info if verified
        roblox_info = self.db.get_by_discord_id(user.id)
        headshot_url = None
        roblox_joined_str = "Not Available"
        roblox_user_str = "❌ Not Verified"

        if roblox_info:
            roblox_id = roblox_info["roblox_id"]
            headshot_url = await self.roblox_api.get_user_headshot(roblox_id)
            details = await self.roblox_api.get_user_details(roblox_id)
            if details and "created" in details:
                rbx_dt = self.roblox_api.parse_creation_date(details["created"])
                if rbx_dt:
                    ts = int(rbx_dt.timestamp())
                    roblox_joined_str = f"<t:{ts}:D> (<t:{ts}:R>)"

            roblox_user_str = f"**{roblox_info['roblox_display_name']}** (`@{roblox_info['roblox_username']}`)"
            roblox_id_str = f"[{roblox_id}](https://www.roblox.com/users/{roblox_id}/profile)"
        else:
            roblox_id_str = "*None*"

        # Send welcome embed (Visible only to Support Staff)
        welcome_embed = discord.Embed(
            title=f"🎫 Support Ticket #{ticket_id} • {section}",
            description=(
                f"Support ticket opened by {user.mention} (`{user.name}` | `{user.id}`).\n\n"
                f"🔒 **Staff-Only Channel:** The user cannot view this channel. All interactions occur via their **Direct Messages (DMs)**.\n"
                f"• Messages sent by staff here will be forwarded directly to the user's DMs with an `✉️` indicator.\n"
                f"• Member replies from their DMs are relayed here automatically.\n"
                f"• Use the buttons below to manage, escalate, transfer, or close this ticket."
            ),
            color=0x5865F2
        )
        welcome_embed.add_field(name="👤 Member", value=f"{user.mention} (`{user.name}`)", inline=True)
        welcome_embed.add_field(name="📂 Category", value=f"**{section}**", inline=True)
        welcome_embed.add_field(name="🎮 Roblox Account", value=roblox_user_str, inline=True)
        welcome_embed.add_field(name="📝 Inquiry", value=initial_query[:1024], inline=False)
        welcome_embed.add_field(
            name="⚠️ System Status: Beta",
            value="This ticket system is in **Beta**. If the AI cannot solve the inquiry, staff can take over at any time.",
            inline=False
        )
        welcome_embed.set_footer(text="Staff Modmail Console • User communicates via Direct Messages")

        # Staff Overview Dossier Embed
        staff_dossier_embed = discord.Embed(
            title=f"📋 Support Staff Dossier • {user.name}",
            color=0x00A2FF if roblox_info else 0xED4245
        )
        staff_dossier_embed.add_field(name="👤 Roblox Username", value=roblox_user_str, inline=True)
        staff_dossier_embed.add_field(name="🆔 Roblox ID", value=roblox_id_str, inline=True)
        staff_dossier_embed.add_field(name="🔒 Status", value="✅ **Verified**" if roblox_info else "❌ **Unverified** (Run `/manual-verify`)", inline=True)
        if roblox_info:
            staff_dossier_embed.add_field(name="📅 Roblox Joined", value=roblox_joined_str, inline=True)
            staff_dossier_embed.add_field(name="🔗 Profile Link", value=f"[Open Roblox Profile](https://www.roblox.com/users/{roblox_info['roblox_id']}/profile)", inline=True)
            staff_dossier_embed.add_field(name="💬 Discord Member", value=f"{user.mention} (`{user.id}`)", inline=True)
        if headshot_url:
            staff_dossier_embed.set_thumbnail(url=headshot_url)
        staff_dossier_embed.set_footer(text="Staff Reference Panel • Roblox Verification System")

        view = TicketControlView(self)
        await channel.send(embed=welcome_embed, view=view)
        await channel.send(embed=staff_dossier_embed)

        # Send initial confirmation DM to the user so they know where the conversation lives
        try:
            user_dm = await user.create_dm()
            dm_welcome = discord.Embed(
                title=f"🎫 Support Ticket Opened • {section}",
                description=(
                    f"Hello **{user.name}**, your support inquiry has been received by our team!\n\n"
                    f"**Your Inquiry:**\n> {initial_query[:400]}\n\n"
                    f"🤖 Our **AI Support Assistant** is reviewing your message and will reply below shortly.\n\n"
                    f"💬 **How to reply:** Type your messages directly in this DM thread! "
                    f"All of your messages are delivered directly to our support team."
                ),
                color=0x5865F2
            )
            dm_welcome.add_field(
                name="⚠️ System Status: Beta",
                value="Our ticket system is currently in **Beta** and may not know everything yet. If the AI is unable to resolve your inquiry, a human support team member will assist you directly.",
                inline=False
            )
            dm_welcome.set_footer(text=f"Ticket #{ticket_id} • Direct Message Modmail System")
            await user_dm.send(embed=dm_welcome)
        except Exception as e:
            logger.warning(f"Could not send DM welcome to user {user.id}: {e}")

        # AI processes initial inquiry
        asyncio.create_task(self.process_ai_ticket_message(ticket_id, user, channel, initial_query, roblox_info))

        return channel

    async def create_staff_test_ticket(
        self,
        founder: discord.Member,
        target_staff: discord.Member,
        guild: discord.Guild,
        scenario_title: str = "Support Team Practical Assessment",
        scenario_details: str = ""
    ) -> Optional[discord.TextChannel]:
        """Creates an isolated testing ticket channel visible ONLY to the Founder, target staff member, and bot."""
        category = None
        if config.TICKETS_CATEGORY_ID:
            category = guild.get_channel(config.TICKETS_CATEGORY_ID)
            if not category:
                try:
                    category = await guild.fetch_channel(config.TICKETS_CATEGORY_ID)
                except Exception:
                    category = None
            if not isinstance(category, discord.CategoryChannel):
                category = None

        if not category:
            for cat in guild.categories:
                if "ticket" in cat.name.lower() or "support" in cat.name.lower():
                    category = cat
                    break

        support_role = guild.get_role(config.SUPPORT_TEAM_ROLE_ID)
        escalation_role = guild.get_role(config.ESCALATION_ROLE_ID)

        # Strictly isolated overwrites:
        # Hidden from @everyone and hidden from SUPPORT_TEAM_ROLE_ID!
        # Visible ONLY to target_staff, founder, and bot!
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            target_staff: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
            founder: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True, attach_files=True)
        }

        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(view_channel=False)
        if escalation_role:
            overwrites[escalation_role] = discord.PermissionOverwrite(view_channel=False)

        channel_name = f"test-{target_staff.name.lower().replace(' ', '-')[:15]}"
        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"[Support Staff Exam] Practical assessment for {target_staff.name} ({target_staff.id}) • Exam Channel"
            )
        except Exception as e:
            logger.error(f"Error creating staff test ticket channel: {e}")
            return None

        # Register ticket in DB with standard AI disabled (roleplay evaluator mode active)
        sec_label = f"Support Staff Exam: {scenario_title}"
        ticket_id = self.ticket_manager.create_ticket(target_staff.id, channel.id, guild.id, section=sec_label)
        self.ticket_manager.set_ai_enabled(ticket_id, False)
        self.ticket_manager.claim_ticket(ticket_id, founder.id)

        test_embed = discord.Embed(
            title="🧪 Echo Technologies • Automated AI Practical Assessment",
            description=(
                f"Welcome {target_staff.mention} to your live practical support evaluation!\n\n"
                f"👤 **Assessed Staff Member:** {target_staff.mention} (`{target_staff.name}`)\n"
                f"👑 **Exam Evaluator:** {founder.mention} (`{founder.name}`)\n"
                f"🎯 **Scenario Title:** `{scenario_title}`\n\n"
                f"📋 **Scenario Briefing / Task:**\n"
                f"```\n{scenario_details or 'Demonstrate standard support procedure, verify user inquiry, and apply appropriate response templates.'}\n```\n"
                f"────────────────────────────────────────\n"
                f"⚠️ **AUTOMATED AI ROLEPLAY EVALUATOR MODE:**\n"
                f"• **Groq AI Roleplay Actor:** **ACTIVE** (The AI will act out the role of the demanding/angry Roblox user on behalf of the scenario).\n"
                f"• **Realistic Delay:** The AI will type with realistic delays (3–6 seconds) as you reply.\n"
                f"• **Mandatory Checklist:** Remember your **Greeting SOP**, **Evidence Privacy SOP**, **Global Blacklist Citation**, and **Ticket Closure Protocol**!"
            ),
            color=0x9B59B6,
            timestamp=discord.utils.utcnow()
        )
        test_embed.set_footer(text=f"Exam Ticket #{ticket_id} • AI Roleplay Evaluator Mode Active")
        view = TicketControlView(self)
        await channel.send(content=f"{target_staff.mention} {founder.mention}", embed=test_embed, view=view)

        # Dispatch initial AI roleplay opening prompt
        asyncio.create_task(self.dispatch_ai_test_opening(ticket_id, channel, scenario_title, scenario_details or ""))

        return channel

    async def dispatch_ai_test_opening(self, ticket_id: int, channel: discord.TextChannel, scenario_title: str, scenario_details: str):
        """Generates and dispatches initial roleplay opening message for a staff test ticket."""
        await asyncio.sleep(2.0)
        async with channel.typing():
            await asyncio.sleep(3.5)
            opening_msg = await self.groq_assistant.generate_test_opening_prompt(scenario_title, scenario_details)

        self.ticket_manager.add_message(ticket_id, 0, "user", opening_msg, sender_name="Member (Simulated)")

        opening_embed = discord.Embed(
            title="👤 Member (Roleplay Inquiry)",
            description=opening_msg,
            color=0xE74C3C
        )
        opening_embed.set_footer(text="🤖 AI Evaluator Roleplay • Reply directly in this channel to respond to the member")
        await channel.send(embed=opening_embed)

    async def process_ai_test_roleplay_message(self, ticket_id: int, channel: discord.TextChannel, staff_user: discord.User, new_content: str):
        """Processes staff member's response during a test ticket, adding realistic typing delay and acting out the member."""
        ticket = self.ticket_manager.get_ticket_by_channel(channel.id)
        if not ticket or ticket["status"] == "closed":
            return

        sec = ticket.get("section", "Support Staff Exam")
        scen_title = sec.replace("Support Staff Exam: ", "") if "Support Staff Exam: " in sec else sec

        await asyncio.sleep(1.5)
        async with channel.typing():
            await asyncio.sleep(3.5)
            history = self.ticket_manager.get_history_for_llm(ticket_id)
            ai_reply = await self.groq_assistant.generate_test_roleplay_response(history, scen_title)

        self.ticket_manager.add_message(ticket_id, 0, "user", ai_reply, sender_name="Member (Simulated)")

        reply_embed = discord.Embed(
            title="👤 Member (Roleplay Response)",
            description=ai_reply,
            color=0xE74C3C
        )
        reply_embed.set_footer(text="🤖 AI Evaluator Roleplay Mode • Continue your response in character")
        await channel.send(embed=reply_embed)

    async def process_ai_ticket_message(
        self,
        ticket_id: int,
        user: discord.User,
        channel: discord.TextChannel,
        new_content: str,
        roblox_info: Optional[dict] = None
    ):
        """Asks Groq AI to process inquiry, responds, or triggers escalation."""
        ticket = self.ticket_manager.get_ticket_by_channel(channel.id)
        if not ticket or ticket["status"] == "closed" or not ticket.get("ai_enabled", 1) or "Support Staff Exam" in ticket.get("section", ""):
            return

        pts = get_user_points(user.id)
        async with channel.typing():
            history = self.ticket_manager.get_history_for_llm(ticket_id)
            reply_text, should_escalate, escalate_reason, claimed_blacklist, claimed_discount, should_close = await self.groq_assistant.generate_response(
                messages_history=history,
                user_info=roblox_info,
                section=ticket.get("section", "General Support"),
                points_info=pts
            )

        # Save AI reply
        self.ticket_manager.add_message(ticket_id, self.user.id, "ai", reply_text, sender_name="AI Assistant")

        # Establish DM channel if applicable
        dm_channel = None
        try:
            dm_channel = await user.create_dm()
        except Exception:
            pass

        # Send reply to channel
        ai_embed = discord.Embed(
            title="🤖 AI Support Assistant",
            description=reply_text,
            color=0x00A2FF
        )
        ai_embed.set_footer(text="⚠️ Beta System • AI may not know everything • Click Escalate for human staff")
        await channel.send(embed=ai_embed)
        if dm_channel:
            try:
                await dm_channel.send(embed=ai_embed)
            except Exception:
                pass

        # Handle automated ticket closing if requested by user
        if should_close and not should_escalate:
            await asyncio.sleep(2.0)
            try:
                await self.close_support_ticket(
                    ticket=ticket,
                    channel=channel,
                    closed_by=self.user,
                    reason="Automated AI close requested by user"
                )
            except Exception as e:
                logger.error(f"Error executing automated AI ticket close: {e}")

        # Never trust the AI's reward tags on their own: verify eligibility server-side
        if claimed_blacklist:
            fresh_pts = get_user_points(user.id)
            if fresh_pts["points"] < 5 or fresh_pts.get("has_claimed_reward"):
                logger.warning(f"Ignored ineligible blacklist claim tag for user {user.id} (pts={fresh_pts['points']}, claimed={fresh_pts.get('has_claimed_reward')})")
                claimed_blacklist = False
        if claimed_discount:
            fresh_pts = get_user_points(user.id)
            if fresh_pts["points"] < 8:
                logger.warning(f"Ignored ineligible coupon claim tag for user {user.id} (pts={fresh_pts['points']})")
                claimed_discount = False

        # If user unlocked and claimed the Echo Blacklist System, deliver official card & download button
        if claimed_blacklist:
            mark_reward_claimed(user.id, True)
            try:
                import sqlite3 as _sql
                with _sql.connect("verifications.db") as _c:
                    _cur = _c.cursor()
                    _cur.execute("""
                        INSERT INTO user_redemptions (user_id, reward_id, reward_name, cost, status)
                        VALUES (?, 'blacklist_system', 'Echo Blacklist System (100 Robux Value)', 0, 'completed');
                    """, (user.id,))
                    _cur.execute("""
                        INSERT INTO point_transactions (user_id, amount, source, reason)
                        VALUES (?, 0, 'reward_redeem', 'Claimed free Echo Blacklist System via AI Ticket Assistant');
                    """, (user.id,))
                    _c.commit()
            except Exception as e:
                logger.error(f"Error logging AI reward claim in DB: {e}")

            delivery_embed = discord.Embed(
                title="📦 Echo Blacklist System • Official Product Delivery",
                description=(
                    "### 🎉 Instant Automated Fulfillment (No Staff Needed!)\n"
                    f"Congratulations {user.mention}! Your **5 Community Points** milestone has been verified.\n\n"
                    "**Included Package Features:**\n"
                    "• Complete Server-Authoritative Blacklist (Ban) System (`.rbxm` model)\n"
                    "• Permanent & temporary bans with DataStore persistence\n"
                    "• Group-Rank or UserId permission checks & join enforcement\n"
                    "• Audit logging & optional Discord webhook integration\n"
                    "• Remote bridge for custom admin panels\n\n"
                    "📥 **Download File:** [Google Drive Direct Link](https://drive.google.com/file/d/1VZtIk0rc46BtzXZfpeApSqQPO5f34eOY/view?usp=sharing)\n\n"
                    "🛠️ **Installation Steps:**\n"
                    "1. Download the `.rbxm` file from Google Drive above.\n"
                    "2. In Roblox Studio, right-click `ServerScriptService` in the Explorer.\n"
                    "3. Select **Insert from File...** and choose the downloaded file.\n"
                    "4. Open `Configuration` module inside the system to configure group ranks & permissions!"
                ),
                color=0x57F287,
                timestamp=discord.utils.utcnow()
            )
            delivery_embed.set_footer(text="Echo Technologies Automated Fulfillment • Free Community Reward")
            delivery_view = discord.ui.View(timeout=None)
            delivery_view.add_item(
                discord.ui.Button(
                    label="Download Echo Blacklist System",
                    url="https://drive.google.com/file/d/1VZtIk0rc46BtzXZfpeApSqQPO5f34eOY/view?usp=sharing",
                    emoji="💾",
                    style=discord.ButtonStyle.link
                )
            )
            await channel.send(embed=delivery_embed, view=delivery_view)
            if dm_channel:
                try:
                    await dm_channel.send(embed=delivery_embed, view=delivery_view)
                except Exception:
                    pass

        # If user redeemed the 50% Off Discount Coupon (8 Points), execute 3-step live processing sequence
        if claimed_discount:
            # Deduct points and mint the code FIRST (before the animated steps) so the
            # balance check and deduction can't be raced by a second message.
            balance_before = get_user_points(user.id)["points"]
            coupon_code = f"ECHO-50-{secrets.token_hex(3).upper()}"
            new_pts = remove_points(
                user_id=user.id,
                amount=8,
                source="reward_redeem",
                reason=f"Redeemed 50% Off Coupon ({coupon_code}) via AI Ticket Assistant"
            )
            try:
                with sqlite3.connect("verifications.db") as _c:
                    _c.execute(
                        """
                        INSERT INTO user_redemptions (user_id, reward_id, reward_name, cost, coupon_code, status)
                        VALUES (?, 'coupon_discount', '50% Off Any Asset Store Coupon', 8, ?, 'completed');
                        """,
                        (user.id, coupon_code)
                    )
            except Exception as e:
                logger.error(f"Error logging coupon redemption in DB: {e}")

            # Step 1/3: Verification Message
            async with channel.typing():
                await asyncio.sleep(1.8)
                step1_embed = discord.Embed(
                    title="🔍 System Authentication & Points Verification",
                    description=(
                        f"**[Step 1/3: Account Audit & Balance Check]**\n\n"
                        f"• **Member:** {user.mention} (`{user.name}`)\n"
                        f"• **Current Balance:** `{balance_before} Points` *(Minimum 8 Points required)*\n"
                        f"• **Eligibility:** 🟢 **VERIFIED & APPROVED**\n\n"
                        f"⏳ *Accessing cryptographic voucher engine and preparing ledger transaction...*"
                    ),
                    color=0x5865F2
                )
                step1_embed.set_footer(text="Echo Technologies Rewards Engine • Step 1 of 3")
                await channel.send(embed=step1_embed)
                if dm_channel:
                    try:
                        await dm_channel.send(embed=step1_embed)
                    except Exception:
                        pass

            # Step 2/3: Deduction & Key Generation Message
            async with channel.typing():
                await asyncio.sleep(2.4)
                step2_embed = discord.Embed(
                    title="⚙️ Ledger Transaction & Key Minting",
                    description=(
                        f"**[Step 2/3: Points Deduction & Hash Minting]**\n\n"
                        f"• **Points Deducted:** `-8 Community Points`\n"
                        f"• **Updated Balance:** `{new_pts} Points`\n"
                        f"• **Ledger Status:** 🟢 **TRANSACTION COMMITTED**\n\n"
                        f"⏳ *Minting cryptographic single-use discount voucher and registering in database...*"
                    ),
                    color=0xFEE75C
                )
                step2_embed.set_footer(text="Echo Technologies Rewards Engine • Step 2 of 3")
                await channel.send(embed=step2_embed)
                if dm_channel:
                    try:
                        await dm_channel.send(embed=step2_embed)
                    except Exception:
                        pass

            # Step 3/3: Final Delivery Message
            async with channel.typing():
                await asyncio.sleep(2.0)
                step3_embed = discord.Embed(
                    title="🎟️ 50% OFF Discount Voucher • Officially Issued!",
                    description=(
                        f"**[Step 3/3: Voucher Successfully Activated!]** 🎉\n\n"
                        f"Congratulations {user.mention}! Your **50% discount coupon** has been generated and activated.\n\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🏷️ **Your Single-Use Coupon Code:**\n"
                        f"```\n{coupon_code}\n```\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"📋 **How to Use Your Coupon:**\n"
                        f"• Present this code in any ticket when purchasing any current or upcoming Echo Technologies asset.\n"
                        f"• Grants a **50% discount** off the regular price.\n"
                        f"• Cryptographically unique and registered to Discord User ID `{user.id}`.\n\n"
                        f"🪙 **Remaining Community Points:** `{new_pts} Points`"
                    ),
                    color=0x57F287,
                    timestamp=discord.utils.utcnow()
                )
                step3_embed.set_footer(text="Echo Technologies Rewards Engine • Step 3 of 3 • Single-Use Validated")
                await channel.send(embed=step3_embed)
                if dm_channel:
                    try:
                        await dm_channel.send(embed=step3_embed)
                    except Exception:
                        pass

        if should_escalate:
            await self.handle_escalation(ticket, channel, reason=escalate_reason)

    async def handle_escalation(self, ticket: dict, channel: discord.TextChannel, reason: str = ""):
        """Pings the escalation role, posts summary to escalated-tickets, and updates status."""
        ticket_id = ticket["id"]
        user_id = ticket["user_id"]
        self.ticket_manager.escalate_ticket(ticket_id, reason=reason)

        user = self.get_user(user_id)
        if not user:
            try:
                user = await self.fetch_user(user_id)
            except Exception:
                user = None

        user_mention = user.mention if user else f"<@{user_id}>"
        user_name = user.name if user else f"User {user_id}"

        # Retrieve Roblox info for support team
        roblox_info = self.db.get_by_discord_id(user_id)
        headshot_url = None
        roblox_field_str = "❌ Not Verified (Run `/manual-verify`)"
        roblox_id_str = "*None*"
        roblox_joined_str = "Unknown"

        if roblox_info:
            roblox_id = roblox_info["roblox_id"]
            headshot_url = await self.roblox_api.get_user_headshot(roblox_id)
            details = await self.roblox_api.get_user_details(roblox_id)
            if details and "created" in details:
                rbx_dt = self.roblox_api.parse_creation_date(details["created"])
                if rbx_dt:
                    ts = int(rbx_dt.timestamp())
                    roblox_joined_str = f"<t:{ts}:D> (<t:{ts}:R>)"

            roblox_field_str = f"**{roblox_info['roblox_display_name']}** (`@{roblox_info['roblox_username']}`)"
            roblox_id_str = f"[{roblox_id}](https://www.roblox.com/users/{roblox_id}/profile)"

        # 1. Ping escalation role in the ticket channel
        escalate_embed = discord.Embed(
            title="🚨 Ticket Escalated to Staff",
            description=(
                f"Attention <@&{config.ESCALATION_ROLE_ID}>: This ticket requires human assistance.\n\n"
                f"**Reason:** {reason or 'Issue could not be resolved automatically.'}\n\n"
                f"*(AI auto-replies are now paused. A human staff member will assist you shortly.)*"
            ),
            color=0xED4245
        )
        escalate_embed.add_field(name="👤 Member", value=f"{user_mention} (`{user_name}`)", inline=True)
        escalate_embed.add_field(name="🎮 Roblox Username", value=roblox_field_str, inline=True)
        escalate_embed.add_field(name="🆔 Roblox ID", value=roblox_id_str, inline=True)
        if roblox_info:
            escalate_embed.add_field(name="📅 Joined Roblox", value=roblox_joined_str, inline=True)
            escalate_embed.add_field(name="🔗 Profile", value=f"[Open Roblox Profile](https://www.roblox.com/users/{roblox_info['roblox_id']}/profile)", inline=True)
            escalate_embed.add_field(name="🔒 Status", value="✅ **Verified**", inline=True)
        else:
            escalate_embed.add_field(name="🔒 Status", value="❌ **Unverified**", inline=True)

        if headshot_url:
            escalate_embed.set_thumbnail(url=headshot_url)

        escalate_embed.set_footer(text=f"Ticket #{ticket_id} • Support Team Reference")

        try:
            await channel.send(content=f"<@&{config.ESCALATION_ROLE_ID}>", embed=escalate_embed)
            logger.info(f"Escalation ping sent in #{channel.name} for ticket #{ticket_id}")
        except Exception as e:
            logger.error(f"Error sending escalation embed to ticket channel {channel.id}: {e}")

        # Also notify user in DM
        if user:
            try:
                dm_ch = await user.create_dm()
                await dm_ch.send(
                    f"🚨 **Your ticket #{ticket_id} has been escalated to Staff!**\n"
                    f"A human staff member has been summoned and will reply to you shortly."
                )
            except Exception:
                pass

        # 2. Generate AI summary and send report to escalated-tickets channel
        escalated_ch = await self.get_escalated_channel(channel.guild)
        if escalated_ch:
            try:
                history = self.ticket_manager.get_history_for_llm(ticket_id, limit=10)
                summary = await self.groq_assistant.generate_ticket_summary(history, reason)

                roblox_text = "❌ Not Verified"
                if roblox_info:
                    roblox_id = roblox_info["roblox_id"]
                    roblox_text = f"**{roblox_info['roblox_display_name']}** (`@{roblox_info['roblox_username']}`)\nID: [{roblox_id}](https://www.roblox.com/users/{roblox_id}/profile)"

                report_embed = discord.Embed(
                    title=f"🚨 Escalated Ticket #{ticket_id} • {ticket.get('section', 'General')}",
                    description=f"<@&{config.ESCALATION_ROLE_ID}> - Action Required",
                    color=0xED4245,
                    timestamp=discord.utils.utcnow()
                )
                report_embed.add_field(name="👤 User", value=f"{user_mention} (`{user_name}` | `{user_id}`)", inline=True)
                report_embed.add_field(name="📂 Category", value=f"{ticket.get('section', 'General')}", inline=True)
                report_embed.add_field(name="🎮 Roblox", value=roblox_text, inline=True)
                report_embed.add_field(name="📍 Ticket Channel", value=channel.mention, inline=False)
                report_embed.add_field(name="⚠️ Escalation Reason", value=f"`{reason or 'Requires human staff'}`", inline=False)
                report_embed.add_field(name="📋 AI Summary & Attempted Solution", value=summary[:1024], inline=False)

                if headshot_url:
                    report_embed.set_thumbnail(url=headshot_url)

                view = discord.ui.View()
                view.add_item(discord.ui.Button(label="Go to Ticket", url=channel.jump_url, style=discord.ButtonStyle.link))

                await escalated_ch.send(content=f"<@&{config.ESCALATION_ROLE_ID}>", embed=report_embed, view=view)
                logger.info(f"Escalation report sent to #{escalated_ch.name} for ticket #{ticket_id}")
            except Exception as e:
                logger.error(f"Error posting escalation summary to #{escalated_ch.name}: {e}")
        else:
            logger.warning(f"Escalated channel not found in guild {channel.guild.name} (config ID: {config.ESCALATED_TICKETS_CHANNEL_ID})")

    async def close_support_ticket(self, ticket: dict, channel: discord.TextChannel, closed_by: discord.User, reason: str = "Closed by staff"):
        """Closes the ticket, exports transcript to channel, prompts for an experience rating, and cleans up."""
        ticket_id = ticket["id"]
        user_id = ticket["user_id"]
        self.ticket_manager.close_ticket(ticket_id, closed_by=closed_by.id if closed_by else None, reason=reason)

        user = self.get_user(user_id)
        if not user:
            try:
                user = await self.fetch_user(user_id)
            except Exception:
                user = None  # user deleted their account / left; still finish the close flow

        # 1. Generate and upload HTML transcript to transcript channel (1556000161690292274)
        transcript_ch = await self.get_transcript_channel(channel.guild)
        messages = self.ticket_manager.get_all_ticket_messages(ticket_id)
        roblox_info = self.db.get_by_discord_id(user_id)
        rating_info = self.ticket_manager.get_rating(ticket_id)

        user_details = {
            "discord_name": user.name if user else f"User {user_id}",
            "roblox_username": roblox_info.get("roblox_username") if roblox_info else None,
            "roblox_display_name": roblox_info.get("roblox_display_name") if roblox_info else None,
            "roblox_id": roblox_info.get("roblox_id") if roblox_info else None
        }

        html_content = generate_html_transcript(ticket, messages, user_details, rating_info)
        file_bytes = io.BytesIO(html_content.encode("utf-8"))
        transcript_file = discord.File(file_bytes, filename=f"transcript-ticket-{ticket_id}.html")

        if transcript_ch:
            tr_embed = discord.Embed(
                title=f"📁 Ticket Transcript #{ticket_id} • {ticket.get('section', 'General')}",
                description=f"Ticket closed by {closed_by.mention}.",
                color=0x5865F2,
                timestamp=discord.utils.utcnow()
            )
            tr_embed.add_field(name="User", value=f"<@{user_id}> (`{user_id}`)", inline=True)
            tr_embed.add_field(name="Category", value=ticket.get("section", "General"), inline=True)
            tr_embed.add_field(name="Total Messages", value=str(len(messages)), inline=True)
            tr_embed.add_field(name="Close Reason", value=f"`{reason}`", inline=False)
            try:
                await transcript_ch.send(embed=tr_embed, file=transcript_file)
            except Exception as e:
                logger.error(f"Failed to send transcript to channel {config.TRANSCRIPT_CHANNEL_ID}: {e}")

        # 2. Build Experience Rating Embed
        rating_embed = discord.Embed(
            title="⭐ Rate Your Support Experience",
            description=(
                f"Your support ticket **#{ticket_id}** has been marked closed by {closed_by.mention}.\n\n"
                f"**How was your support experience today?**\n"
                f"Please take a moment to rate the service using the star buttons below (1 to 5 Stars):"
            ),
            color=0xFEE75C
        )
        rating_embed.add_field(name="⭐⭐⭐⭐⭐", value="Excellent", inline=True)
        rating_embed.add_field(name="⭐⭐⭐", value="Average", inline=True)
        rating_embed.add_field(name="⭐", value="Needs Improvement", inline=True)
        rating_embed.set_footer(text="Your feedback directly helps us improve our AI and staff support")

        rating_view = TicketRatingView(self, ticket_id, user_id)

        dm_delivered = False
        if user:
            try:
                dm_ch = await user.create_dm()
                await dm_ch.send(embed=rating_embed, view=rating_view)
                dm_delivered = True
            except Exception:
                dm_delivered = False

        if dm_delivered:
            close_embed = discord.Embed(
                title="🔒 Ticket Closed",
                description=(
                    f"This ticket was closed by {closed_by.mention}.\n\n"
                    f"⭐ An **experience rating prompt** has been sent to {user.mention}'s direct messages!\n"
                    f"📁 Transcript saved to <#{config.TRANSCRIPT_CHANNEL_ID}>.\n"
                    f"This channel will close in 5 seconds."
                ),
                color=0x747F8D
            )
            await channel.send(embed=close_embed)
            await asyncio.sleep(5)
            try:
                await channel.delete(reason=f"Ticket #{ticket_id} closed by {closed_by.name}")
            except Exception as e:
                logger.error(f"Error deleting ticket channel: {e}")
        else:
            close_embed = discord.Embed(
                title="🔒 Ticket Closed",
                description=(
                    f"This ticket was closed by {closed_by.mention}.\n\n"
                    f"*(Direct messages could not be delivered to {user.mention if user else 'the user'})*\n"
                    f"Please rate your experience using the buttons below before this channel is removed in 30 seconds!"
                ),
                color=0x747F8D
            )
            await channel.send(embed=close_embed)
            await channel.send(embed=rating_embed, view=rating_view)
            await asyncio.sleep(30)
            try:
                await channel.delete(reason=f"Ticket #{ticket_id} closed by {closed_by.name}")
            except Exception as e:
                logger.error(f"Error deleting ticket channel: {e}")

    def get_primary_guild(self) -> Optional[discord.Guild]:
        if config.GUILD_ID:
            g = self.get_guild(config.GUILD_ID)
            if g:
                return g
        if self.guilds:
            return self.guilds[0]
        return None

bot = RobloxVerificationBot()

# --- EVENTS ---

def build_verification_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🛡️ Roblox Account Verification",
        description=(
            "Welcome! To gain full access to the server, please verify ownership "
            "of your Roblox account.\n\n"
            "**How It Works:**\n"
            "1. Click the **Verify Roblox Account** button below.\n"
            "2. Enter your Roblox username in the popup form.\n"
            "3. We will display your Roblox profile and a **censorship-safe** code phrase.\n"
            "4. Paste the phrase into your Roblox profile's **About / Bio** section and save.\n"
            "5. Click **Check Verification** and you're all set!"
        ),
        color=0x00A2FF
    )
    embed.add_field(
        name="🔒 Safe & Uncensored",
        value="Our verification codes use filtered-safe dictionary words that **never** get tagged (`####`) by Roblox.",
        inline=False
    )
    embed.set_footer(text="Official Roblox Verification • Click the button below to start")
    return embed

def build_ticket_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🎫 Server Support & Help Desk",
        description=(
            "Need help with Roblox verification, game issues, or reporting a problem?\n\n"
            "Select a department from the dropdown menu below to open a ticket. Our **Groq AI Support Assistant** "
            "will assist you directly and privately in your **Direct Messages (DMs)**!\n\n"
            f"If the AI cannot resolve your inquiry, human staff (<@&{config.ESCALATION_ROLE_ID}>) will take over."
        ),
        color=0x5865F2
    )
    embed.add_field(name="💬 General Support", value="General questions, verification, and rules", inline=True)
    embed.add_field(name="🛡️ High-Ranking", value="Staff matters, reports, appeals", inline=True)
    embed.add_field(name="💻 Development", value="Bugs, glitches, and technical help", inline=True)
    embed.add_field(name="🚀 Booster Perks", value="Custom roles and booster rewards", inline=True)
    embed.add_field(
        name="⚠️ System Status: Beta",
        value="The AI ticket system is currently in **Beta** and continuously learning. It may not know everything yet. If the AI cannot resolve your inquiry, you can speak with human staff at any time.",
        inline=False
    )
    embed.add_field(
        name="📬 Private Direct Message System",
        value="Your ticket is handled privately in your **Direct Messages (DMs)**! Please ensure your Discord privacy settings allow DMs from server members.",
        inline=False
    )
    embed.set_footer(text="Support Help Desk (Beta) • Handled via Direct Messages • Select a category below")
    return embed

@tasks.loop(minutes=15)
async def check_ticket_inactivity():
    """Checks for inactive tickets (24h warning, 48h auto-close)."""
    # 1. 24h Inactivity Warning
    try:
        to_warn = bot.ticket_manager.get_inactive_tickets_for_warning(hours=24)
        for ticket in to_warn:
            bot.ticket_manager.mark_inactivity_warning_sent(ticket["id"])
            user_id = ticket["user_id"]
            user = await safe_fetch_user(bot, user_id)
            if user:
                try:
                    dm = await user.create_dm()
                    warn_embed = discord.Embed(
                        title=f"⚠️ Ticket #{ticket['id']} Inactivity Notice",
                        description=(
                            f"Hello {user.name}, your support ticket has had no activity for over **24 hours**.\n\n"
                            f"💬 **Still need assistance?** Simply reply in this DM thread!\n"
                            f"🔒 If no response is received within another 24 hours, this ticket will automatically close."
                        ),
                        color=0xFEE75C,
                        timestamp=discord.utils.utcnow()
                    )
                    warn_embed.set_footer(text="Automated Inactivity Reminder • Support Help Desk")
                    await dm.send(embed=warn_embed)
                except Exception as e:
                    logger.warning(f"Could not send inactivity warning DM to user {user_id}: {e}")

            channel_id = ticket.get("channel_id")
            if channel_id:
                ch = bot.get_channel(channel_id)
                if ch and isinstance(ch, discord.TextChannel):
                    try:
                        await ch.send("⚠️ **Inactivity Alert:** No messages detected for 24 hours. An automated reminder DM has been dispatched to the member.")
                    except Exception:
                        pass
    except Exception as e:
        logger.error(f"Error in inactivity warning loop: {e}")

    # 2. 48h Inactivity Auto-Close
    try:
        to_close = bot.ticket_manager.get_inactive_tickets_for_close(hours=48)
        for ticket in to_close:
            channel_id = ticket.get("channel_id")
            if channel_id:
                ch = bot.get_channel(channel_id)
                if ch and isinstance(ch, discord.TextChannel):
                    try:
                        await ch.send("🔒 **Auto-Closing Ticket:** Ticket has been inactive for over 48 hours without response.")
                        await bot.close_support_ticket(ticket, ch, bot.user, reason="Auto-closed due to 48 hours of inactivity")
                    except Exception as e:
                        logger.error(f"Error auto-closing inactive ticket #{ticket['id']}: {e}")
    except Exception as e:
        logger.error(f"Error in inactivity auto-close loop: {e}")

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    logger.info(f"Target verification channel ID: {config.VERIFICATION_CHANNEL_ID}")

    # 0. Start Inactivity Monitor Loop
    if not check_ticket_inactivity.is_running():
        check_ticket_inactivity.start()
        logger.info("Started ticket inactivity background monitor loop (15-min interval).")

    # 0.5. Start Giveaway Monitor Loop
    if not check_active_giveaways_loop.is_running():
        check_active_giveaways_loop.start(bot)
        logger.info("Started giveaway background monitor loop (20s interval).")

    # 0.8. Start HR Maintenance Loop (1-hour interval)
    if not check_hr_maintenance_loop.is_running():
        check_hr_maintenance_loop.start()
        logger.info("Started HR maintenance background monitor loop (1-hour interval).")

    # 0.9. Start Invite Competition Monitor Loop (30s interval)
    if not check_invite_comp_loop.is_running():
        check_invite_comp_loop.start()
        logger.info("Started invite competition background monitor loop (30s interval).")

    # 0.95. Start Partner Health Monitor Loop (6-hour interval)
    if not partner_health_monitor_loop.is_running():
        partner_health_monitor_loop.start()
        logger.info("Started partner health background monitor loop (6-hour interval).")

    # 0.97. Snapshot invite usage counts for accurate invite tracking
    for g in bot.guilds:
        await refresh_invite_cache(g)

    # 1. Post Verification Panel if needed
    channel = bot.get_channel(config.VERIFICATION_CHANNEL_ID)
    if channel and isinstance(channel, discord.TextChannel):
        try:
            already_posted = False
            async for msg in channel.history(limit=20):
                if msg.author.id == bot.user.id and msg.embeds:
                    for em in msg.embeds:
                        if em.title and "Roblox Account Verification" in em.title:
                            already_posted = True
                            break
                if already_posted:
                    break

            if not already_posted:
                embed = build_verification_panel_embed()
                view = VerificationLaunchView(bot.roblox_api, bot.db)
                await channel.send(embed=embed, view=view)
                logger.info(f"Posted verification panel in #{channel.name}!")
        except Exception as e:
            logger.error(f"Could not auto-post verification panel: {e}")

    # 1.5. Post or Refresh Career Opportunities Panel (Sync buttons and open/closed states)
    try:
        await sync_career_panel_message(bot)
        logger.info("Synced live career opportunities recruitment panel.")
    except Exception as e:
        logger.error(f"Could not sync career panel: {e}")

    # 1.6. Post or Refresh Support Templates & Guide in #support-templates (1556425130752876626)
    try:
        await sync_support_templates_channel(bot)
        logger.info("Synced support templates knowledge base in #support-templates.")
    except Exception as e:
        logger.error(f"Could not sync support templates channel: {e}")


    # 2. Train AI from guild knowledge (#ai-trainer & embeds)
    guild = bot.get_primary_guild()
    if guild:
        report = await bot.ai_trainer.train_from_guild(guild)
        logger.info(f"AI Knowledge Initialized: {report['trainer_messages']} msgs, {report['embeds_parsed']} embeds parsed.")

@tasks.loop(seconds=30)
async def check_invite_comp_loop():
    """Background loop to conclude expired invite competitions."""
    try:
        await check_invite_competitions_loop(bot)
    except Exception as e:
        logger.error(f"Error in invite competition loop: {e}")

@tasks.loop(hours=1)
async def check_hr_maintenance_loop():
    """Background task to run 30-day strike decay and lift expired staff suspensions."""
    try:
        expired_count = check_strike_expiration()
        if expired_count > 0:
            logger.info(f"Deactivated {expired_count} expired strike records (30-day clean conduct decay).")
        await check_expired_suspensions(bot)
    except Exception as e:
        logger.error(f"Error in HR maintenance loop: {e}")

@tasks.loop(hours=6)
async def partner_health_monitor_loop():
    """Checks for broken invite links across active affiliate partners."""
    try:
        await check_partner_health(bot)
    except Exception as e:
        logger.error(f"Error in partner health monitor loop: {e}")

async def evaluate_and_award_chat_point(message: discord.Message):
    """
    Evaluates helpful chat messages using Groq AI and awards Community Points.
    At 5 points, triggers celebratory announcement to claim the Echo Blacklist System for free!
    """
    try:
        content = message.content.strip()
        if len(content) < 22 or len(content.split()) < 5:
            return
        if content.startswith(("/", "!", "?", ".", "-", "$", ";", "\\")):
            return

        should_award, reason = await evaluate_message_for_point(message)
        if should_award:
            new_total, unlocked_reward = add_points(
                user_id=message.author.id,
                amount=1,
                source="ai_evaluation",
                reason=reason
            )
            logger.info(f"Awarded AI Community Point to {message.author} ({message.author.id}): {reason} (Total: {new_total})")

            try:
                await message.add_reaction("⭐")
            except Exception:
                pass

            if unlocked_reward:
                # 5 Points Milestone Reached!
                reward_embed, reward_view = build_reward_unlocked_embed(message.author)
                try:
                    await message.channel.send(
                        content=f"🎉 {message.author.mention} **REWARD UNLOCKED!**",
                        embed=reward_embed,
                        view=reward_view
                    )
                except Exception as e:
                    logger.warning(f"Could not post reward milestone in channel: {e}")

                try:
                    dm = await message.author.create_dm()
                    await dm.send(embed=reward_embed, view=reward_view)
                except Exception as e:
                    logger.warning(f"Could not DM reward milestone to {message.author}: {e}")
            else:
                point_embed = build_point_earned_embed(message.author, new_total, reason)
                try:
                    await message.reply(embed=point_embed, mention_author=False)
                except Exception:
                    try:
                        await message.channel.send(embed=point_embed)
                    except Exception:
                        pass
    except Exception as e:
        logger.error(f"Error evaluating message for points: {e}")

async def refresh_invite_cache(guild: discord.Guild) -> None:
    """Stores the current use-count of every invite in the guild."""
    try:
        invites = await guild.invites()
    except (discord.Forbidden, discord.HTTPException):
        bot.invite_cache.pop(guild.id, None)
        return
    bot.invite_cache[guild.id] = {inv.code: (inv.uses or 0) for inv in invites}

async def detect_used_invite(guild: discord.Guild) -> Optional[discord.Invite]:
    """Finds which invite was used by comparing use-counts against the cached snapshot."""
    async with bot.invite_lock:
        old = bot.invite_cache.get(guild.id)
        try:
            invites = await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            return None
        bot.invite_cache[guild.id] = {inv.code: (inv.uses or 0) for inv in invites}
        if old is None:
            return None
        for inv in invites:
            if (inv.uses or 0) > old.get(inv.code, 0):
                return inv
        return None

@bot.event
async def on_invite_create(invite: discord.Invite):
    if invite.guild:
        bot.invite_cache.setdefault(invite.guild.id, {})[invite.code] = invite.uses or 0

@bot.event
async def on_invite_delete(invite: discord.Invite):
    if invite.guild:
        bot.invite_cache.get(invite.guild.id, {}).pop(invite.code, None)

@bot.event
async def on_guild_join(guild: discord.Guild):
    await refresh_invite_cache(guild)

@bot.event
async def on_member_join(member: discord.Member):
    """Global-ban enforcement, invite tracking, anti-alt checks, auto-roles and welcome greeting."""
    guild = member.guild

    # 1. Global Ban Security Auto-Enforcement
    banned, ban_data = is_globally_banned(member.id)
    if banned:
        ban_reason = ban_data.get("reason", "Echo Technologies Global Security Blacklist") if ban_data else "Blacklisted"
        try:
            await member.ban(reason=f"[SECURITY ENFORCED] Globally Banned User: {ban_reason}")
            logger.warning(f"Enforced global ban on {member.name} ({member.id})")
            await dispatch_mod_log(
                bot=bot,
                guild=guild,
                action="global_ban",
                target=member,
                moderator=bot.user,
                reason=f"Attempted to join server while on global blacklist.\nOriginal Reason: {ban_reason}",
                extra_field=("🚨 Automatic Security Enforcement", "User was automatically banned on server join.")
            )
            return
        except Exception as e:
            logger.error(f"Failed to auto-enforce global ban on {member.id}: {e}")

    # 2. Anti-Alt / Account Age Security Check (< 7 days old)
    created_at = member.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    account_age_days = (datetime.now(timezone.utc) - created_at).days
    is_alt = account_age_days < 7

    # 3. Invite tracking (only credit the invite whose use-count actually increased)
    used_inviter_id = None
    used_code = None
    try:
        used_invite = await detect_used_invite(guild)
        if used_invite and used_invite.inviter:
            used_inviter_id = used_invite.inviter.id
            used_code = used_invite.code
            record_member_join_invite(guild.id, member.id, used_inviter_id, used_code, is_fake=is_alt)
    except Exception as e:
        logger.debug(f"Invite tracking error on member join: {e}")

    # Audit Log Alert for Flagged Alts
    if is_alt and used_inviter_id:
        audit_ch = guild.get_channel(config.MOD_LOGS_CHANNEL_ID) or guild.get_channel(config.PUBLIC_LOGS_CHANNEL_ID)
        if audit_ch and isinstance(audit_ch, discord.TextChannel):
            try:
                audit_embed = discord.Embed(
                    title="🛡️ Security Alert: Flagged Alt / Suspicious Invite",
                    description=(
                        f"**Member Joined:** {member.mention} (`{member.name}` | `{member.id}`)\n"
                        f"**Account Age:** `{account_age_days} day(s) old` *(Flagged < 7d threshold)*\n"
                        f"**Invited By:** <@{used_inviter_id}>\n"
                        f"**Invite Code:** `{used_code}`\n\n"
                        f"⚠️ *This invite has been marked as **Flagged Alt** and excluded from net contest counts.*"
                    ),
                    color=0xED4245,
                    timestamp=discord.utils.utcnow()
                )
                audit_embed.set_footer(text="Echo Security & Anti-Alt Protection")
                await audit_ch.send(embed=audit_embed)
            except Exception:
                pass

    # 4. Auto-Assign Join Roles (e.g. Unverified & Member roles)
    for r_id in config.JOIN_ROLE_IDS:
        if r_id:
            role = guild.get_role(r_id)
            if role:
                try:
                    await member.add_roles(role, reason="Auto-assigned join role")
                    logger.info(f"Auto-assigned join role '{role.name}' ({role.id}) to {member.name}")
                except Exception as e:
                    logger.warning(f"Failed to assign join role {r_id} to {member.name}: {e}")

    # 5. Dispatch welcome greeting
    try:
        await send_welcome_greeting(bot, member)
    except Exception as e:
        logger.error(f"Welcome greeting error for {member.name}: {e}")

@bot.event
async def on_member_remove(member: discord.Member):
    """Deducts 1 net invite count from an inviter when an invited member leaves the server."""
    guild = member.guild
    inviter_id = record_member_leave_invite(guild.id, member.id)
    if inviter_id:
        logger.info(f"Member {member} left guild {guild.id}. Deducted 1 net invite count from inviter {inviter_id}.")

@bot.event
async def on_raw_message_delete(payload: discord.RawMessageDeleteEvent):
    """Automatically detects when a message is deleted in #ai-trainer and un-trains / purges it from AI memory."""
    guild = bot.get_guild(payload.guild_id) if payload.guild_id else None
    if guild:
        trainer_ch = bot.ai_trainer.find_ai_trainer_channel(guild)
        if trainer_ch and payload.channel_id == trainer_ch.id:
            logger.info(f"Message deleted in #{trainer_ch.name}! Retraining AI knowledge base to purge deleted info...")
            await bot.ai_trainer.train_from_guild(guild)

@bot.event
async def on_raw_message_edit(payload: discord.RawMessageUpdateEvent):
    """Automatically detects when a message/embed is edited in #ai-trainer and re-syncs AI memory."""
    guild = bot.get_guild(payload.guild_id) if payload.guild_id else None
    if guild:
        trainer_ch = bot.ai_trainer.find_ai_trainer_channel(guild)
        if trainer_ch and payload.channel_id == trainer_ch.id:
            logger.info(f"Message edited in #{trainer_ch.name}! Re-syncing AI knowledge base...")
            await bot.ai_trainer.train_from_guild(guild)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # AI Watchlist & Staff Sensitivity Analyzer (#6)
    if message.guild:
        asyncio.create_task(evaluate_watchlist_message(bot, message))

    # Check if a message or embed was posted in #ai-trainer -> Auto-train in real-time!
    trainer_channel = None
    if message.guild:
        trainer_channel = bot.ai_trainer.find_ai_trainer_channel(message.guild)
    if trainer_channel and message.channel.id == trainer_channel.id:
        logger.info("New message/embed detected in #ai-trainer! Refreshing knowledge base...")
        await bot.ai_trainer.train_from_guild(message.guild)
        try:
            await message.add_reaction("🧠")
        except Exception:
            pass
        return

    # Activity Leveling: Award XP for chatting in guild channels
    if message.guild:
        awarded, new_xp, new_lvl, leveled_up = award_message_xp(message.author.id, message.guild.id)
        if leveled_up:
            try:
                lvl_embed = discord.Embed(
                    title="🎉 Level Up!",
                    description=f"Congratulations {message.author.mention}! You've reached **Level {new_lvl}**!",
                    color=0x57F287
                )
                lvl_embed.set_thumbnail(url=message.author.display_avatar.url)
                lvl_embed.set_footer(text="Echo Technologies Leveling System • Run /rank to view stats")
                await message.channel.send(embed=lvl_embed)
            except Exception:
                pass

    # Case A: Modmail DM / Application Interview
    if isinstance(message.channel, discord.DMChannel):
        # 0. Check if user is actively answering a staff or developer application in DMs!
        handled_app = await handle_applicant_dm_message(bot, message)
        if handled_app:
            return

        if bot.ticket_manager.is_blacklisted(message.author.id):
            await message.channel.send("❌ You are currently blacklisted from opening support tickets.")
            return


        existing_ticket = bot.ticket_manager.get_open_ticket_by_user(message.author.id)
        if existing_ticket:
            ticket_channel = bot.get_channel(existing_ticket["channel_id"])
            if ticket_channel:
                att_urls = [a.url for a in message.attachments]
                bot.ticket_manager.add_message(
                    existing_ticket["id"],
                    message.author.id,
                    "user",
                    message.content,
                    sender_name=message.author.name,
                    attachments=att_urls
                )
                desc_text = message.content or ("*(Uploaded file attachment)*" if message.attachments else "")
                relay_embed = discord.Embed(
                    description=desc_text,
                    color=0x5865F2,
                    timestamp=discord.utils.utcnow()
                )
                roblox_info = bot.db.get_by_discord_id(message.author.id)
                roblox_tag = f" • Roblox: @{roblox_info['roblox_username']} ({roblox_info['roblox_id']})" if roblox_info else " • Roblox: Unverified"
                relay_embed.set_author(name=f"{message.author.name} (DM){roblox_tag}", icon_url=message.author.display_avatar.url)

                if message.attachments:
                    first_att = message.attachments[0]
                    if any(first_att.filename.lower().endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                        relay_embed.set_image(url=first_att.url)

                relay_files = []
                for a in message.attachments:
                    try:
                        relay_files.append(await a.to_file())
                    except Exception:
                        pass

                await ticket_channel.send(embed=relay_embed, files=relay_files if relay_files else None)
                try:
                    await message.add_reaction("📨")
                except Exception:
                    pass

                # Automatic Urgency Detection
                if message.content:
                    is_urgent, urgent_reason = bot.groq_assistant.detect_urgency(message.content)
                    if is_urgent and existing_ticket.get("priority") != "Urgent":
                        bot.ticket_manager.set_priority(existing_ticket["id"], "Urgent")
                        await ticket_channel.send(
                            f"🚨 **URGENT ISSUE DETECTED BY AI:** `{urgent_reason}`! Priority upgraded to **Urgent** (<@&{config.ESCALATION_ROLE_ID}>)."
                        )

                if existing_ticket.get("ai_enabled", 1) and existing_ticket["status"] != "closed":
                    roblox_info = bot.db.get_by_discord_id(message.author.id)
                    await bot.process_ai_ticket_message(existing_ticket["id"], message.author, ticket_channel, message.content, roblox_info)
            else:
                bot.ticket_manager.close_ticket(existing_ticket["id"], bot.user.id, "Ticket channel missing")
                expired_embed = discord.Embed(
                    title="🎫 Support Ticket Expired",
                    description=(
                        "Your previous support ticket channel is no longer active.\n\n"
                        f"To open a new ticket, please visit our server and select a department from the **Support Help Desk Panel** in <#{config.VERIFICATION_CHANNEL_ID}>!"
                    ),
                    color=0xED4245
                )
                expired_embed.set_footer(text="Echo Technologies • Support Help Desk")
                await message.channel.send(embed=expired_embed)
        else:
            panel_embed = discord.Embed(
                title="🎫 Support Ticket Required",
                description=(
                    "Support tickets **cannot** be created directly via Direct Message.\n\n"
                    f"Please visit our server and select a department from the **Support Help Desk Panel** in <#{config.VERIFICATION_CHANNEL_ID}> to open your ticket!"
                ),
                color=0xFEE75C
            )
            panel_embed.add_field(
                name="📂 Available Departments",
                value=(
                    "• 💬 **General Support** - Roblox verification, rules, general questions\n"
                    "• 🛡️ **High-Ranking Support** - Staff matters, incident reports, appeals\n"
                    "• 💻 **Development Ticket** - Bugs, glitches, technical diagnostics\n"
                    "• 🚀 **Booster Perks** - Custom roles, perks, booster claims"
                ),
                inline=False
            )
            panel_embed.set_footer(text="Echo Technologies • Support Help Desk Panel")
            await message.channel.send(embed=panel_embed)
        return


    # Case B: Inside Ticket Channel
    ticket = bot.ticket_manager.get_or_recover_ticket(message.channel.id, channel_obj=message.channel)
    if ticket:
        ticket_id = ticket["id"]
        ticket_user_id = ticket["user_id"]
        ai_active = bool(ticket.get("ai_enabled", 1))

        # Case B1: Staff Examination / AI Roleplay Evaluator Ticket!
        if "Support Staff Exam" in ticket.get("section", ""):
            if not message.author.bot:
                att_urls = [a.url for a in message.attachments]
                bot.ticket_manager.add_message(
                    ticket_id,
                    message.author.id,
                    "staff",
                    message.content,
                    sender_name=message.author.display_name,
                    attachments=att_urls
                )
                if ticket.get("status") != "closed":
                    asyncio.create_task(bot.process_ai_test_roleplay_message(ticket_id, message.channel, message.author, message.content))
                    try:
                        await message.add_reaction("🧠")
                    except Exception:
                        pass
                await bot.process_commands(message)
                return

        # Determine whether this message is from staff or the user
        if message.author.id != ticket_user_id:
            # Different person than ticket opener -> Definitely staff!
            is_staff = True
        else:
            # Message is from the ticket opener:
            # - If AI is active, they are interacting as the client with the AI
            # - If AI is NOT active (paused/escalated), and they claimed it or have admin/staff roles,
            #   they are acting as staff
            has_staff_role = any(r.id == config.ESCALATION_ROLE_ID for r in getattr(message.author, 'roles', []))
            is_mod = message.author.guild_permissions.manage_channels or message.author.guild_permissions.administrator
            is_claimed_handler = (ticket.get("claimed_by") == message.author.id)

            if not ai_active and (is_claimed_handler or (ticket["status"] == "escalated" and (has_staff_role or is_mod))):
                is_staff = True
            else:
                is_staff = False

        if is_staff and not message.author.bot:
            att_urls = [a.url for a in message.attachments]
            bot.ticket_manager.add_message(
                ticket_id,
                message.author.id,
                "staff",
                message.content,
                sender_name=message.author.display_name,
                attachments=att_urls
            )
            target_user = bot.get_user(ticket_user_id)
            if not target_user:
                try:
                    target_user = await bot.fetch_user(ticket_user_id)
                except Exception:
                    target_user = None
            if target_user:
                try:
                    staff_desc = message.content or ("*(Uploaded file attachment)*" if message.attachments else "")
                    staff_embed = discord.Embed(
                        description=staff_desc,
                        color=0x57F287,
                        timestamp=discord.utils.utcnow()
                    )
                    staff_embed.set_author(name=f"Staff Response ({message.author.display_name})", icon_url=message.author.display_avatar.url)
                    if message.attachments:
                        first_att = message.attachments[0]
                        if any(first_att.filename.lower().endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                            staff_embed.set_image(url=first_att.url)

                    staff_files = []
                    for a in message.attachments:
                        try:
                            staff_files.append(await a.to_file())
                        except Exception:
                            pass

                    dm_ch = await target_user.create_dm()
                    await dm_ch.send(embed=staff_embed, files=staff_files if staff_files else None)
                    await message.add_reaction("✉️")
                except discord.Forbidden:
                    await message.add_reaction("⚠️")
                    await message.channel.send(
                        f"⚠️ *(Notice: Could not forward to {target_user.mention}'s DMs because their direct messages are closed. They can read your message here in this channel.)*",
                        delete_after=12
                    )
                except Exception as e:
                    logger.warning(f"Could not forward staff reply to DM: {e}")

        elif not message.author.bot:
            att_urls = [a.url for a in message.attachments]
            bot.ticket_manager.add_message(
                ticket_id,
                message.author.id,
                "user",
                message.content,
                sender_name=message.author.name,
                attachments=att_urls
            )
            if ai_active and ticket["status"] != "closed":
                roblox_info = bot.db.get_by_discord_id(message.author.id)
                await bot.process_ai_ticket_message(ticket_id, message.author, message.channel, message.content, roblox_info)
            else:
                try:
                    await message.add_reaction("📨")
                except Exception:
                    pass

    # Case C: Regular Guild Chat Channel (AI Community Points Evaluation)
    if message.guild and not ticket and message.content:
        system_channel_ids = {
            config.MOD_LOGS_CHANNEL_ID,
            config.HR_LOGS_CHANNEL_ID,
            config.DEV_BACKLOG_CHANNEL_ID,
            config.CAREER_OPPORTUNITIES_CHANNEL_ID,
            config.APPLICATIONS_SUBMISSIONS_CHANNEL_ID,
            config.AI_TRAINER_CHANNEL_ID,
            config.TRANSCRIPT_CHANNEL_ID,
            config.VERIFICATION_CHANNEL_ID
        }
        if message.channel.id not in system_channel_ids:
            asyncio.create_task(evaluate_and_award_chat_point(message))

    await bot.process_commands(message)


# ==========================================
# ⭐ STARBOARD / HALL OF FAME LISTENERS
# ==========================================

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    await handle_star_reaction(bot, payload, is_add=True)

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    await handle_star_reaction(bot, payload, is_add=False)


# ==========================================
# 🛡️ ROBLOX VERIFICATION SLASH COMMANDS
# ==========================================


@bot.tree.command(name="manual-verify", description="Manually verify a user with a Roblox username (bypasses bio code).")
@app_commands.describe(member="Discord member to verify", roblox_username="Exact Roblox username")
@app_commands.default_permissions(manage_roles=True)
async def manual_verify(interaction: discord.Interaction, member: discord.Member, roblox_username: str):
    await interaction.response.defer(ephemeral=True)

    # 1. Lookup on Roblox
    user_info = await bot.roblox_api.get_user_by_username(roblox_username)
    if not user_info:
        await interaction.followup.send(f"❌ Roblox account `{roblox_username}` could not be found.", ephemeral=True)
        return

    roblox_id = user_info["id"]
    username = user_info["name"]
    display_name = user_info.get("displayName", username)

    # 2. Save in database
    bot.db.link_user(member.id, roblox_id, username, display_name)

    # 3. Assign verified role (1556000033604640949)
    role_msg = ""
    if config.VERIFIED_ROLE_ID:
        role = interaction.guild.get_role(config.VERIFIED_ROLE_ID)
        if role:
            try:
                await member.add_roles(role, reason=f"Manual verify as {username}")
                role_msg = f"\n• Granted role: **{role.name}**"
            except Exception:
                role_msg = "\n• *(Could not assign verified role)*"

    # 4. Remove unverified role (1556000025216163961)
    unverify_msg = ""
    if config.UNVERIFIED_ROLE_ID:
        unv_role = interaction.guild.get_role(config.UNVERIFIED_ROLE_ID)
        if unv_role and unv_role in member.roles:
            try:
                await member.remove_roles(unv_role, reason=f"Manual verify as {username}")
                unverify_msg = f"\n• Removed unverified role: **{unv_role.name}**"
            except Exception:
                pass

    # 5. Nickname sync
    nick_msg = ""
    if config.UPDATE_NICKNAME:
        try:
            await member.edit(nick=username, reason="Manual verify sync")
            nick_msg = f"\n• Updated nickname to **{username}**"
        except Exception:
            pass

    embed = discord.Embed(
        title="✅ Member Manually Verified",
        description=f"Successfully linked {member.mention} to Roblox profile **{display_name}** (`@{username}`).",
        color=0x57F287
    )
    embed.add_field(name="Roblox ID", value=f"[{roblox_id}](https://www.roblox.com/users/{roblox_id}/profile)", inline=True)
    embed.add_field(name="Changes", value=f"• Saved to database{role_msg}{unverify_msg}{nick_msg}", inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)

    # Dispatch celebration card to #welcome
    rbx_info = {
        "roblox_id": roblox_id,
        "roblox_username": username,
        "roblox_display_name": display_name
    }
    asyncio.create_task(send_verification_announcement(bot, member, rbx_info))


@bot.tree.command(name="force-verify", description="Verify a member directly using a numeric Roblox User ID.")
@app_commands.describe(member="Discord member to verify", roblox_id="Numeric Roblox User ID")
@app_commands.default_permissions(manage_roles=True)
async def force_verify(interaction: discord.Interaction, member: discord.Member, roblox_id: int):
    await interaction.response.defer(ephemeral=True)
    details = await bot.roblox_api.get_user_details(roblox_id)
    if not details:
        await interaction.followup.send(f"❌ Roblox User ID `{roblox_id}` not found.", ephemeral=True)
        return

    username = details["name"]
    display_name = details.get("displayName", username)
    bot.db.link_user(member.id, roblox_id, username, display_name)

    if config.VERIFIED_ROLE_ID:
        role = interaction.guild.get_role(config.VERIFIED_ROLE_ID)
        if role:
            try:
                await member.add_roles(role, reason="Force verify")
            except Exception:
                pass

    if config.UNVERIFIED_ROLE_ID:
        unv_role = interaction.guild.get_role(config.UNVERIFIED_ROLE_ID)
        if unv_role and unv_role in member.roles:
            try:
                await member.remove_roles(unv_role, reason="Force verify")
            except Exception:
                pass

    if config.UPDATE_NICKNAME:
        try:
            await member.edit(nick=username)
        except Exception:
            pass

    await interaction.followup.send(f"✅ Force verified {member.mention} as **{display_name}** (`@{username}`) [ID: `{roblox_id}`]!", ephemeral=True)


@bot.tree.command(name="update", description="Re-sync your Roblox username, display name, and nickname/roles.")
@app_commands.describe(member="Member to update (leave blank for self)")
async def update(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target = member or interaction.user
    if member and member != interaction.user and not interaction.user.guild_permissions.manage_nicknames:
        await interaction.response.send_message("❌ You lack permission to update other members.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    record = bot.db.get_by_discord_id(target.id)
    if not record:
        await interaction.followup.send(f"❌ {target.mention} is not verified.", ephemeral=True)
        return

    details = await bot.roblox_api.get_user_details(record["roblox_id"])
    if not details:
        await interaction.followup.send("⚠️ Could not contact Roblox API to refresh info.", ephemeral=True)
        return

    new_username = details["name"]
    new_display = details.get("displayName", new_username)
    bot.db.link_user(target.id, record["roblox_id"], new_username, new_display)

    # Sync roles
    if config.VERIFIED_ROLE_ID:
        role = interaction.guild.get_role(config.VERIFIED_ROLE_ID)
        if role and role not in target.roles:
            try:
                await target.add_roles(role)
            except Exception:
                pass

    if config.UNVERIFIED_ROLE_ID:
        unv_role = interaction.guild.get_role(config.UNVERIFIED_ROLE_ID)
        if unv_role and unv_role in target.roles:
            try:
                await target.remove_roles(unv_role)
            except Exception:
                pass

    # Sync nickname
    if config.UPDATE_NICKNAME:
        try:
            await target.edit(nick=new_username)
        except Exception:
            pass

    await interaction.followup.send(f"🔄 Updated {target.mention}! Linked as **{new_display}** (`@{new_username}`).", ephemeral=True)


@bot.tree.command(name="reverify", description="Unlink your current account and reverify.")
async def reverify(interaction: discord.Interaction):
    bot.db.unlink_user(interaction.user.id)
    if config.VERIFIED_ROLE_ID:
        role = interaction.guild.get_role(config.VERIFIED_ROLE_ID)
        if role and role in interaction.user.roles:
            try:
                await interaction.user.remove_roles(role)
            except Exception:
                pass
    await interaction.response.send_message(
        f"ℹ️ Your Roblox link has been reset. Please head to <#{config.VERIFICATION_CHANNEL_ID}> to verify your new account!",
        ephemeral=True
    )


@bot.tree.command(name="lookup-roblox", description="Reverse lookup: Find which Discord user owns a Roblox account.")
@app_commands.describe(query="Roblox username or Roblox ID")
@app_commands.default_permissions(manage_roles=True)
async def lookup_roblox(interaction: discord.Interaction, query: str):
    await interaction.response.defer(ephemeral=True)
    record = None
    if query.isdigit():
        record = bot.db.get_by_roblox_id(int(query))

    if not record:
        user_info = await bot.roblox_api.get_user_by_username(query)
        if user_info:
            record = bot.db.get_by_roblox_id(user_info["id"])

    if not record:
        await interaction.followup.send(f"ℹ️ No Discord member is linked to Roblox account `{query}`.", ephemeral=True)
        return

    member = interaction.guild.get_member(record["discord_id"])
    member_mention = member.mention if member else f"`{record['discord_id']}` (Left Server)"

    embed = discord.Embed(
        title=f"🔎 Reverse Lookup: {record['roblox_display_name']}",
        color=0x00A2FF
    )
    embed.add_field(name="Roblox Username", value=f"`@{record['roblox_username']}`", inline=True)
    embed.add_field(name="Roblox ID", value=f"[{record['roblox_id']}](https://www.roblox.com/users/{record['roblox_id']}/profile)", inline=True)
    embed.add_field(name="Discord Owner", value=member_mention, inline=False)
    embed.add_field(name="Verified Date", value=f"{record['verified_at']} UTC", inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="check-alt", description="Check account age and Roblox creation date to detect alt accounts.")
@app_commands.describe(member="Member to inspect")
@app_commands.default_permissions(manage_roles=True)
async def check_alt(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)
    record = bot.db.get_by_discord_id(member.id)

    discord_created = member.created_at
    discord_age_days = (datetime.now(timezone.utc) - discord_created).days

    embed = discord.Embed(title=f"🕵️ Alt Account Check: {member.name}", color=0xFEE75C)
    embed.add_field(name="Discord Age", value=f"{discord_age_days} days old (<t:{int(discord_created.timestamp())}:D>)", inline=False)

    if record:
        details = await bot.roblox_api.get_user_details(record["roblox_id"])
        if details and "created" in details:
            rbx_dt = bot.roblox_api.parse_creation_date(details["created"])
            if rbx_dt:
                rbx_age_days = (datetime.now(timezone.utc) - rbx_dt).days
                embed.add_field(name="Roblox Account", value=f"**{record['roblox_username']}** (ID: `{record['roblox_id']}`)", inline=True)
                embed.add_field(name="Roblox Age", value=f"{rbx_age_days} days old", inline=True)
                if rbx_age_days < 30 or discord_age_days < 7:
                    embed.color = 0xED4245
                    embed.add_field(name="⚠️ Risk Alert", value="Account flagged: Very young Roblox or Discord account!", inline=False)
                else:
                    embed.color = 0x57F287
    else:
        embed.add_field(name="Roblox Status", value="Not verified", inline=False)

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="verify-stats", description="View server Roblox verification statistics.")
async def verify_stats(interaction: discord.Interaction):
    with bot.db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS total FROM verifications")
        total_verified = cursor.fetchone()["total"]

    total_members = interaction.guild.member_count
    pct = round((total_verified / total_members) * 100, 1) if total_members else 0

    embed = discord.Embed(title="📊 Verification Statistics", color=0x00A2FF)
    embed.add_field(name="Verified Members", value=f"**{total_verified}**", inline=True)
    embed.add_field(name="Server Members", value=f"**{total_members}**", inline=True)
    embed.add_field(name="Verification Rate", value=f"**{pct}%**", inline=True)
    await interaction.response.send_message(embed=embed)


# ==========================================
# 🎫 TICKET COMMAND GROUP (/ticket ...)
# ==========================================

ticket_group = app_commands.Group(name="ticket", description="Ticket and Modmail commands")

@ticket_group.command(name="close", description="Close the current ticket channel and request a rating.")
@app_commands.describe(reason="Reason for closing the ticket")
async def ticket_close(interaction: discord.Interaction, reason: Optional[str] = "No reason provided"):
    ticket = bot.ticket_manager.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        await interaction.response.send_message("❌ This command can only be used inside a ticket channel.", ephemeral=True)
        return

    await interaction.response.defer()
    await bot.close_support_ticket(ticket, interaction.channel, closed_by=interaction.user)

@ticket_group.command(name="force-close", description="Immediately close and delete the ticket channel.")
@app_commands.default_permissions(manage_channels=True)
async def ticket_force_close(interaction: discord.Interaction):
    ticket = bot.ticket_manager.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        await interaction.response.send_message("❌ Not a ticket channel.", ephemeral=True)
        return

    bot.ticket_manager.close_ticket(ticket["id"])
    await interaction.response.send_message("⚡ Force closing ticket immediately...")
    await asyncio.sleep(1)
    await interaction.channel.delete(reason=f"Force closed by {interaction.user.name}")

@ticket_group.command(name="rename", description="Rename the current ticket channel.")
@app_commands.describe(new_name="New name for this channel")
@app_commands.default_permissions(manage_channels=True)
async def ticket_rename(interaction: discord.Interaction, new_name: str):
    ticket = bot.ticket_manager.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        await interaction.response.send_message("❌ Not a ticket channel.", ephemeral=True)
        return

    clean_name = new_name.lower().replace(" ", "-")[:30]
    await interaction.channel.edit(name=clean_name)
    await interaction.response.send_message(f"✅ Renamed ticket channel to `#{clean_name}`.")

@ticket_group.command(name="priority", description="Set ticket priority level.")
@app_commands.describe(level="Priority level")
@app_commands.default_permissions(manage_channels=True)
async def ticket_priority(interaction: discord.Interaction, level: Literal["Low", "Normal", "High", "Urgent"]):
    ticket = bot.ticket_manager.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        await interaction.response.send_message("❌ Not a ticket channel.", ephemeral=True)
        return

    bot.ticket_manager.set_priority(ticket["id"], level)
    await interaction.channel.edit(topic=f"[{level}] [{ticket.get('section', 'General')}] Ticket for user {ticket['user_id']}")
    if level == "Urgent":
        await interaction.channel.send(f"🚨 **URGENT PRIORITY SET!** Notifying <@&{config.ESCALATION_ROLE_ID}>!")
    await interaction.response.send_message(f"✅ Priority updated to **{level}**.")

@ticket_group.command(name="claim", description="Claim this ticket as the active staff handler.")
@app_commands.default_permissions(manage_channels=True)
async def ticket_claim(interaction: discord.Interaction):
    ticket = bot.ticket_manager.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        await interaction.response.send_message("❌ Not a ticket channel.", ephemeral=True)
        return

    bot.ticket_manager.claim_ticket(ticket["id"], interaction.user.id)
    await interaction.response.send_message(f"📌 {interaction.user.mention} has claimed Ticket #{ticket['id']}!")

@ticket_group.command(name="unclaim", description="Release your claim on this ticket.")
@app_commands.default_permissions(manage_channels=True)
async def ticket_unclaim(interaction: discord.Interaction):
    ticket = bot.ticket_manager.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        await interaction.response.send_message("❌ Not a ticket channel.", ephemeral=True)
        return

    bot.ticket_manager.unclaim_ticket(ticket["id"])
    await interaction.response.send_message(f"🔓 Ticket #{ticket['id']} has been unclaimed.")

@ticket_group.command(name="add", description="Add another member to this ticket channel.")
@app_commands.describe(member="Member to add")
@app_commands.default_permissions(manage_channels=True)
async def ticket_add(interaction: discord.Interaction, member: discord.Member):
    ticket = bot.ticket_manager.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        await interaction.response.send_message("❌ Not a ticket channel.", ephemeral=True)
        return

    await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
    await interaction.response.send_message(f"👋 Added {member.mention} to this ticket channel.")

@ticket_group.command(name="remove", description="Remove a member from this ticket channel.")
@app_commands.describe(member="Member to remove")
@app_commands.default_permissions(manage_channels=True)
async def ticket_remove(interaction: discord.Interaction, member: discord.Member):
    ticket = bot.ticket_manager.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        await interaction.response.send_message("❌ Not a ticket channel.", ephemeral=True)
        return

    await interaction.channel.set_permissions(member, overwrite=None)
    await interaction.response.send_message(f"🚪 Removed {member.mention} from this ticket.")

@ticket_group.command(name="transfer-category", description="Transfer ticket to a different category/section.")
@app_commands.describe(category="Target category")
@app_commands.default_permissions(manage_channels=True)
async def ticket_transfer(interaction: discord.Interaction, category: Literal["General Support", "High-Ranking Support", "Development Ticket", "Booster Perks"]):
    ticket = bot.ticket_manager.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        await interaction.response.send_message("❌ Not a ticket channel.", ephemeral=True)
        return

    bot.ticket_manager.update_section(ticket["id"], category)
    await interaction.channel.edit(topic=f"[{category}] Ticket for user {ticket['user_id']}")
    await interaction.response.send_message(f"🔄 Ticket #{ticket['id']} transferred to **{category}**!")

@ticket_group.command(name="escalate", description="Manually escalate ticket to human staff.")
@app_commands.describe(reason="Reason for escalation")
async def ticket_escalate(interaction: discord.Interaction, reason: Optional[str] = "Manual staff escalation"):
    ticket = bot.ticket_manager.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        await interaction.response.send_message("❌ Not a ticket channel.", ephemeral=True)
        return

    await interaction.response.defer()
    await bot.handle_escalation(ticket, interaction.channel, reason=reason)

@ticket_group.command(name="de-escalate", description="De-escalate ticket and re-enable AI assistant.")
@app_commands.default_permissions(manage_channels=True)
async def ticket_de_escalate(interaction: discord.Interaction):
    ticket = bot.ticket_manager.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        await interaction.response.send_message("❌ Not a ticket channel.", ephemeral=True)
        return

    bot.ticket_manager.de_escalate_ticket(ticket["id"])
    embed = discord.Embed(
        title="✅ Ticket De-Escalated",
        description="This ticket has been returned to standard AI handling. Staff claims have been cleared and AI auto-replies are active.",
        color=0x57F287
    )
    await interaction.response.send_message(embed=embed)

@ticket_group.command(name="toggle-ai", description="Pause or resume AI auto-replies in this ticket.")
@app_commands.default_permissions(manage_channels=True)
async def ticket_toggle_ai(interaction: discord.Interaction):
    ticket = bot.ticket_manager.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        await interaction.response.send_message("❌ Not a ticket channel.", ephemeral=True)
        return

    new_state = bot.ticket_manager.toggle_ai(ticket["id"])
    if new_state:
        embed = discord.Embed(
            title="🤖 AI Support Resumed",
            description="The AI Assistant is now **active** and will respond to inquiries.\n*(Staff claims & escalation have been cleared)*",
            color=0x57F287
        )
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(
            title="⏸️ AI Support Paused",
            description="The AI Assistant is now **paused**. Human staff are handling inquiries.",
            color=0xED4245
        )
        await interaction.response.send_message(embed=embed)

@ticket_group.command(name="reset-all", description="[ADMIN] Reset all tickets, transcripts, and ratings back to #1.")
@app_commands.default_permissions(administrator=True)
async def ticket_reset_all(interaction: discord.Interaction):
    count = bot.ticket_manager.reset_all_tickets()
    embed = discord.Embed(
        title="🧹 Ticket Data Reset Complete",
        description=f"Successfully wiped all **{count}** ticket records, transcripts, and ratings. The next ticket opened will start fresh at **#1**.",
        color=0x57F287
    )
    await interaction.response.send_message(embed=embed)

@ticket_group.command(name="transcript", description="Download a full HTML transcript of this ticket.")
async def ticket_transcript(interaction: discord.Interaction):
    ticket = bot.ticket_manager.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        await interaction.response.send_message("❌ Not a ticket channel.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    messages = bot.ticket_manager.get_all_ticket_messages(ticket["id"])
    roblox_info = bot.db.get_by_discord_id(ticket["user_id"])
    rating_info = bot.ticket_manager.get_rating(ticket["id"])

    user = bot.get_user(ticket["user_id"])
    user_details = {
        "discord_name": user.name if user else f"User {ticket['user_id']}",
        "roblox_username": roblox_info.get("roblox_username") if roblox_info else None,
        "roblox_display_name": roblox_info.get("roblox_display_name") if roblox_info else None,
        "roblox_id": roblox_info.get("roblox_id") if roblox_info else None
    }

    html_content = generate_html_transcript(ticket, messages, user_details, rating_info)
    file_bytes = io.BytesIO(html_content.encode("utf-8"))
    tr_file = discord.File(file_bytes, filename=f"transcript-ticket-{ticket['id']}.html")

    await interaction.followup.send("📁 Here is the HTML transcript for this ticket:", file=tr_file, ephemeral=True)

@ticket_group.command(name="stats", description="View overall ticket and satisfaction analytics.")
@app_commands.default_permissions(manage_channels=True)
async def ticket_stats(interaction: discord.Interaction):
    stats = bot.ticket_manager.get_ticket_stats()
    embed = discord.Embed(title="📊 Support Ticket Analytics", color=0x5865F2)
    embed.add_field(name="Total Tickets", value=str(stats["total"]), inline=True)
    embed.add_field(name="Open Tickets", value=str(stats["open"]), inline=True)
    embed.add_field(name="Escalated Tickets", value=str(stats["escalated"]), inline=True)
    embed.add_field(name="Closed Tickets", value=str(stats["closed"]), inline=True)
    embed.add_field(name="Average Rating", value=f"⭐ **{stats['avg_rating']} / 5.0** ({stats['ratings_count']} reviews)", inline=True)

    dist_str = "\n".join([f"{k} Stars: {'⭐' * k} ({v})" for k, v in sorted(stats["distribution"].items(), reverse=True)]) or "No ratings yet"
    embed.add_field(name="Star Distribution", value=dist_str, inline=False)
    await interaction.response.send_message(embed=embed)

@ticket_group.command(name="reviews", description="View recent user feedback comments.")
@app_commands.describe(limit="Number of reviews to display (max 10)")
@app_commands.default_permissions(manage_channels=True)
async def ticket_reviews(interaction: discord.Interaction, limit: Optional[int] = 5):
    reviews = bot.ticket_manager.get_recent_reviews(min(limit, 10))
    if not reviews:
        await interaction.response.send_message("ℹ️ No feedback reviews found.", ephemeral=True)
        return

    embed = discord.Embed(title="💬 Recent Support Feedback", color=0xFEE75C)
    for r in reviews:
        stars = "⭐" * r["rating"]
        embed.add_field(
            name=f"Ticket #{r['ticket_id']} &bull; {stars} ({r['rating']}/5)",
            value=f"_{r['feedback']}_\n<t:{int(datetime.fromisoformat(r['created_at']).timestamp())}:R>",
            inline=False
        )
    await interaction.response.send_message(embed=embed)

# Subgroup: /ticket blacklist <add|remove|list>
ticket_blacklist_group = app_commands.Group(name="blacklist", description="Ticket blacklist controls", parent=ticket_group)

@ticket_blacklist_group.command(name="add", description="Prevent a member from opening tickets.")
@app_commands.describe(member="Member to blacklist", reason="Reason for blacklist")
@app_commands.default_permissions(manage_channels=True)
async def blacklist_add(interaction: discord.Interaction, member: discord.Member, reason: str):
    bot.ticket_manager.add_blacklist(member.id, reason, interaction.user.id)
    await interaction.response.send_message(f"🚫 Blacklisted {member.mention} from tickets. Reason: `{reason}`.")

@ticket_blacklist_group.command(name="remove", description="Remove a member from the ticket blacklist.")
@app_commands.describe(member="Member to unblacklist")
@app_commands.default_permissions(manage_channels=True)
async def blacklist_remove(interaction: discord.Interaction, member: discord.Member):
    success = bot.ticket_manager.remove_blacklist(member.id)
    if success:
        await interaction.response.send_message(f"✅ Removed {member.mention} from the ticket blacklist.")
    else:
        await interaction.response.send_message(f"ℹ️ {member.mention} is not blacklisted.", ephemeral=True)

@ticket_blacklist_group.command(name="list", description="List all blacklisted ticket users.")
@app_commands.default_permissions(manage_channels=True)
async def blacklist_list(interaction: discord.Interaction):
    lists = bot.ticket_manager.get_blacklists()
    if not lists:
        await interaction.response.send_message("ℹ️ No blacklisted ticket users.", ephemeral=True)
        return

    embed = discord.Embed(title="🚫 Ticket Blacklist", color=0xED4245)
    for item in lists[:20]:
        embed.add_field(name=f"User ID: {item['user_id']}", value=f"Reason: {item['reason']}", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@ticket_group.command(name="slowmode", description="Set slowmode in this ticket channel.")
@app_commands.describe(seconds="Slowmode in seconds (0 to disable)")
@app_commands.default_permissions(manage_channels=True)
async def ticket_slowmode(interaction: discord.Interaction, seconds: int):
    ticket = bot.ticket_manager.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        await interaction.response.send_message("❌ Not a ticket channel.", ephemeral=True)
        return

    await interaction.channel.edit(slowmode_delay=seconds)
    await interaction.response.send_message(f"⏱️ Slowmode set to **{seconds} seconds**.")

@ticket_group.command(name="note", description="Add an internal staff note (never visible to member).")
@app_commands.describe(text="Internal note content")
@app_commands.default_permissions(manage_channels=True)
async def ticket_note(interaction: discord.Interaction, text: str):
    ticket = bot.ticket_manager.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        await interaction.response.send_message("❌ This command must be used in a ticket channel.", ephemeral=True)
        return

    bot.ticket_manager.add_message(
        ticket["id"],
        interaction.user.id,
        "internal_note",
        text,
        sender_name=interaction.user.display_name
    )
    embed = discord.Embed(
        title="📝 Internal Staff Note",
        description=text,
        color=0xFEE75C,
        timestamp=discord.utils.utcnow()
    )
    embed.set_author(name=f"{interaction.user.display_name} (Staff)", icon_url=interaction.user.display_avatar.url)
    embed.set_footer(text="🔒 Staff Only • Hidden from member DMs & transcripts")
    await interaction.response.send_message(embed=embed)

@ticket_group.command(name="ai-suggest", description="Generate an AI draft response for staff to review/send.")
@app_commands.default_permissions(manage_channels=True)
async def ticket_ai_suggest(interaction: discord.Interaction):
    ticket = bot.ticket_manager.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        await interaction.response.send_message("❌ This command must be used in a ticket channel.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    history = bot.ticket_manager.get_history_for_llm(ticket["id"], limit=10)
    roblox_info = bot.db.get_by_discord_id(ticket["user_id"])
    suggestion = await bot.groq_assistant.generate_suggested_reply(history, roblox_info)

    suggest_embed = discord.Embed(
        title="💡 AI Suggested Staff Response",
        description=f"Review the draft below before sending it to the member's DMs:\n\n```\n{suggestion}\n```",
        color=0x00A2FF
    )
    suggest_embed.set_footer(text="Only visible to you • Click 'Send to Member' or edit before sending")
    view = SendSuggestedReplyView(bot, ticket, suggestion)
    await interaction.followup.send(embed=suggest_embed, view=view, ephemeral=True)

# Subgroup: /ticket canned <send|add|list|delete>
ticket_canned_group = app_commands.Group(name="canned", description="Canned response templates", parent=ticket_group)

@ticket_canned_group.command(name="send", description="Send a canned response template directly to the member.")
@app_commands.describe(shortcut="Shortcut name of the canned template")
@app_commands.default_permissions(manage_channels=True)
async def ticket_canned_send(interaction: discord.Interaction, shortcut: str):
    ticket = bot.ticket_manager.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        await interaction.response.send_message("❌ This command must be used in a ticket channel.", ephemeral=True)
        return

    canned = bot.ticket_manager.get_canned_response(shortcut)
    if not canned:
        await interaction.response.send_message(f"❌ Canned template `{shortcut}` not found. Use `/ticket canned list`.", ephemeral=True)
        return

    target_user = await safe_fetch_user(bot, ticket["user_id"])
    if target_user:
        try:
            staff_embed = discord.Embed(
                title=f"📁 {canned['title']}",
                description=canned["content"],
                color=0x57F287,
                timestamp=discord.utils.utcnow()
            )
            staff_embed.set_author(name=f"Staff Response ({interaction.user.display_name})", icon_url=interaction.user.display_avatar.url)
            dm = await target_user.create_dm()
            await dm.send(embed=staff_embed)

            bot.ticket_manager.add_message(
                ticket["id"],
                interaction.user.id,
                "staff",
                f"[Canned: {canned['title']}] {canned['content']}",
                sender_name=interaction.user.display_name
            )
            await interaction.response.send_message(
                f"📁 **Canned Response `/{shortcut}` dispatched to member by {interaction.user.mention}:**\n> {canned['content']}"
            )
        except discord.Forbidden:
            await interaction.response.send_message("❌ Member has DMs closed.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error delivering canned reply: {e}", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Could not locate member.", ephemeral=True)

@ticket_canned_group.command(name="add", description="Add or update a canned response template.")
@app_commands.describe(shortcut="Shortcut key (e.g. verify, appeal)", title="Template title", content="Full response message")
@app_commands.default_permissions(manage_guild=True)
async def ticket_canned_add(interaction: discord.Interaction, shortcut: str, title: str, content: str):
    clean_shortcut = shortcut.lower().strip()
    bot.ticket_manager.add_canned_response(clean_shortcut, title, content, interaction.user.id)
    await interaction.response.send_message(f"✅ Saved canned template `/{clean_shortcut}`: **{title}**!", ephemeral=True)

@ticket_canned_group.command(name="list", description="List all available canned response templates.")
@app_commands.default_permissions(manage_channels=True)
async def ticket_canned_list(interaction: discord.Interaction):
    templates = bot.ticket_manager.list_canned_responses()
    if not templates:
        await interaction.response.send_message("ℹ️ No canned response templates available.", ephemeral=True)
        return

    embed = discord.Embed(title="📁 Support Canned Response Templates", color=0x5865F2)
    for t in templates:
        embed.add_field(
            name=f"`/{t['shortcut']}` • {t['title']}",
            value=t["content"][:150] + ("..." if len(t["content"]) > 150 else ""),
            inline=False
        )
    embed.set_footer(text="Use /ticket canned send <shortcut> or the 📁 Canned Reply button to send")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@ticket_canned_group.command(name="delete", description="Delete a canned response template.")
@app_commands.describe(shortcut="Shortcut key to delete")
@app_commands.default_permissions(manage_guild=True)
async def ticket_canned_delete(interaction: discord.Interaction, shortcut: str):
    clean_shortcut = shortcut.lower().strip()
    deleted = bot.ticket_manager.delete_canned_response(clean_shortcut)
    if deleted:
        await interaction.response.send_message(f"✅ Deleted canned template `/{clean_shortcut}`.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Canned template `/{clean_shortcut}` was not found.", ephemeral=True)

@ticket_group.command(name="staff-stats", description="View performance analytics for a support staff member.")
@app_commands.describe(member="Staff member to inspect (defaults to you)")
@app_commands.default_permissions(manage_channels=True)
async def ticket_staff_stats(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target = member or interaction.user
    stats = bot.ticket_manager.get_staff_stats(target.id)

    embed = discord.Embed(
        title=f"📊 Staff Performance • {target.display_name}",
        color=0x5865F2,
        timestamp=discord.utils.utcnow()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="💬 Replies Sent", value=f"`{stats['replies_sent']}`", inline=True)
    embed.add_field(name="📌 Tickets Claimed", value=f"`{stats['tickets_claimed']}`", inline=True)
    embed.add_field(name="🔒 Tickets Closed", value=f"`{stats['tickets_closed']}`", inline=True)
    embed.add_field(name="⭐ Reviews Received", value=f"`{stats['ratings_count']}` reviews", inline=True)
    embed.add_field(name="✨ Average Rating", value=f"⭐ **{stats['avg_rating']} / 5.0**", inline=True)
    embed.set_footer(text="Support Team Analytics")
    await interaction.response.send_message(embed=embed)

@ticket_group.command(name="leaderboard", description="View the support staff performance leaderboard.")
@app_commands.default_permissions(manage_channels=True)
async def ticket_leaderboard(interaction: discord.Interaction):
    lb = bot.ticket_manager.get_staff_leaderboard(limit=10)
    if not lb:
        await interaction.response.send_message("ℹ️ No staff activity recorded yet.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🏆 Support Staff Leaderboard",
        color=0xFEE75C,
        timestamp=discord.utils.utcnow()
    )
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, entry in enumerate(lb):
        icon = medals[i] if i < 3 else f"`#{i+1}`"
        lines.append(
            f"{icon} <@{entry['staff_id']}> — **{entry['replies_count']}** replies | "
            f"**{entry['claims_count']}** claims | **{entry['closed_count']}** closed | "
            f"⭐ **{entry['avg_rating']}**"
        )
    embed.description = "\n".join(lines)
    embed.set_footer(text="Top 10 Active Support Team Members")
    await interaction.response.send_message(embed=embed)

bot.tree.add_command(ticket_group)


# ==========================================
# 🤖 AI COMMANDS
# ==========================================

@bot.tree.command(name="ai-summarize", description="Ask Groq AI to generate a quick summary of this ticket.")
async def ai_summarize(interaction: discord.Interaction):
    ticket = bot.ticket_manager.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        await interaction.response.send_message("❌ This command must be used in a ticket channel.", ephemeral=True)
        return

    await interaction.response.defer()
    history = bot.ticket_manager.get_history_for_llm(ticket["id"], limit=10)
    summary = await bot.groq_assistant.generate_ticket_summary(history)

    embed = discord.Embed(
        title=f"📋 AI Summary: Ticket #{ticket['id']}",
        description=summary,
        color=0x00A2FF
    )
    embed.set_footer(text=f"Model: {config.GROQ_MODEL}")
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="ai-inspect", description="Inspect currently loaded AI knowledge base statistics.")
@app_commands.default_permissions(manage_guild=True)
async def ai_inspect(interaction: discord.Interaction):
    text_len = len(bot.ai_trainer.knowledge_text)
    sources = bot.ai_trainer.training_sources

    embed = discord.Embed(title="🧠 Groq AI Memory Stats", color=0x57F287)
    embed.add_field(name="Model", value=f"`{config.GROQ_MODEL}`", inline=True)
    embed.add_field(name="Knowledge Characters", value=f"`{text_len}` chars", inline=True)
    embed.add_field(name="Indexed Sources", value="\n".join(sources) or "None", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="ai-add-note", description="Add a quick temporary fact or rule to the AI knowledge base.")
@app_commands.describe(note="The knowledge or rule note to inject")
@app_commands.default_permissions(manage_guild=True)
async def ai_add_note(interaction: discord.Interaction, note: str):
    bot.ai_trainer.knowledge_text += f"\n• [ADMIN NOTE]: {note.strip()}"
    bot.ai_trainer._save_cache()
    await interaction.response.send_message(f"✅ Injected note into AI memory: \"{note}\"", ephemeral=True)


# ==========================================
# ⚙️ ADMIN DEPLOYMENT COMMANDS
# ==========================================

@bot.tree.command(name="send-panel", description="Post the Roblox verification embed panel.")
@app_commands.describe(channel="Target channel to send the verification panel (defaults to config channel)")
@app_commands.default_permissions(manage_guild=True)
async def send_panel(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    target_channel = channel or bot.get_channel(config.VERIFICATION_CHANNEL_ID) or interaction.channel
    if not isinstance(target_channel, discord.TextChannel):
        await interaction.response.send_message("❌ Target channel is invalid.", ephemeral=True)
        return

    embed = build_verification_panel_embed()
    view = VerificationLaunchView(bot.roblox_api, bot.db)

    try:
        await target_channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Verification panel sent to {target_channel.mention}!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to send panel: {e}", ephemeral=True)


@bot.tree.command(name="send-ticket-panel", description="Post the multi-department AI Support Ticket embed panel.")
@app_commands.describe(channel="Target channel to send the ticket panel")
@app_commands.default_permissions(manage_guild=True)
async def send_ticket_panel(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    target_channel = channel or interaction.channel
    if not isinstance(target_channel, discord.TextChannel):
        await interaction.response.send_message("❌ Target channel is invalid.", ephemeral=True)
        return

    embed = build_ticket_panel_embed()
    view = TicketLaunchView(bot)
    try:
        await target_channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Multi-category Ticket panel sent to {target_channel.mention}!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to send ticket panel: {e}", ephemeral=True)


@bot.tree.command(name="train-ai", description="Re-train the AI on #ai-trainer messages and server embeds.")
@app_commands.default_permissions(manage_guild=True)
async def train_ai(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    report = await bot.ai_trainer.train_from_guild(interaction.guild)

    embed = discord.Embed(
        title="🧠 AI Training Sync Complete",
        description="The Groq AI knowledge base has been re-indexed from your server.",
        color=0x57F287
    )
    embed.add_field(name="💬 #ai-trainer Messages", value=str(report["trainer_messages"]), inline=True)
    embed.add_field(name="📦 Embeds Indexed", value=str(report["embeds_parsed"]), inline=True)
    embed.add_field(name="📚 Total Knowledge Size", value=f"{report['total_chars']} chars", inline=True)
    embed.add_field(name="📂 Sources", value="\n".join(report["sources"]) or "None", inline=False)
    embed.set_footer(text=f"Model: {config.GROQ_MODEL} • Groq AI")
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="whois", description="View Roblox verification details for a Discord member.")
@app_commands.describe(member="The Discord member to look up (defaults to you)")
async def whois(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target_member = member or interaction.user
    record = bot.db.get_by_discord_id(target_member.id)

    if not record:
        await interaction.response.send_message(f"ℹ️ {target_member.mention} is not verified with any Roblox account.", ephemeral=True)
        return

    roblox_id = record["roblox_id"]
    headshot_url = await bot.roblox_api.get_user_headshot(roblox_id)

    embed = discord.Embed(title=f"Roblox Verification: {target_member.name}", color=0x00A2FF)
    embed.add_field(name="👤 Roblox Username", value=f"**{record['roblox_display_name']}** (`@{record['roblox_username']}`)", inline=True)
    embed.add_field(name="🆔 Roblox ID", value=f"[{roblox_id}](https://www.roblox.com/users/{roblox_id}/profile)", inline=True)
    embed.add_field(name="📅 Verified At", value=f"{record['verified_at']} UTC", inline=False)
    embed.add_field(name="💬 Discord User", value=target_member.mention, inline=True)

    if headshot_url:
        embed.set_thumbnail(url=headshot_url)

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="unlink", description="Unlink a Discord user's Roblox verification.")
@app_commands.describe(member="Member to unlink")
@app_commands.default_permissions(manage_roles=True)
async def unlink(interaction: discord.Interaction, member: discord.Member):
    record = bot.db.get_by_discord_id(member.id)
    if not record:
        await interaction.response.send_message(f"ℹ️ {member.mention} is not verified.", ephemeral=True)
        return

    success = bot.db.unlink_user(member.id)
    if success:
        if config.VERIFIED_ROLE_ID and interaction.guild:
            role = interaction.guild.get_role(config.VERIFIED_ROLE_ID)
            if role and role in member.roles:
                try:
                    await member.remove_roles(role, reason="Unlinked by moderator")
                except Exception:
                    pass

        await interaction.response.send_message(f"✅ Unlinked {member.mention} from Roblox account **{record['roblox_username']}**.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Failed to unlink user.", ephemeral=True)


# ==========================================
# 🏢 ECHO TECHNOLOGIES HR & HIRING COMMANDS
# ==========================================

@bot.tree.command(name="hire", description="Send an official Echo Technologies employment/role offer to a member via DM.")
@app_commands.describe(
    member="The member to extend an offer to",
    role="The role being offered to the candidate",
    note="Optional personalized note or executive message in the offer letter"
)
@app_commands.guild_only()
@app_commands.default_permissions(manage_roles=True)
async def hire_command(
    interaction: discord.Interaction,
    member: discord.Member,
    role: discord.Role,
    note: Optional[str] = None
):
    if member.bot:
        await interaction.response.send_message("❌ Bots cannot be offered positions or roles.", ephemeral=True)
        return

    if role in member.roles:
        await interaction.response.send_message(f"ℹ️ {member.mention} already has the {role.mention} role.", ephemeral=True)
        return

    if role >= interaction.guild.me.top_role:
        await interaction.response.send_message(
            f"❌ I cannot offer {role.mention} because it is higher than or equal to my highest role ({interaction.guild.me.top_role.mention}). "
            f"Please drag my bot role higher in Server Settings > Roles.",
            ephemeral=True
        )
        return

    if interaction.user != interaction.guild.owner and role >= interaction.user.top_role:
        await interaction.response.send_message(
            f"❌ You cannot offer a role higher than or equal to your own highest role ({interaction.user.top_role.mention}).",
            ephemeral=True
        )
        return

    if role.is_default() or role.is_bot_managed() or role.is_premium_subscriber():
        await interaction.response.send_message("❌ This role cannot be offered via employment offers.", ephemeral=True)
        return

    now_ts = int(discord.utils.utcnow().timestamp())
    offer_embed = discord.Embed(
        title="🏢 Echo Technologies • Official Employment & Role Offer",
        description=(
            f"# Echo Technologies\n"
            f"### Official Offer of Employment\n\n"
            f"Dear, **{member.display_name}** (`@{member.name}`).\n\n"
            f"On behalf of **Echo Technologies**, we would like to offer you the role **{role.name}**!\n\n"
            f"We have been extremely impressed by your dedication, contributions, and presence in our community. "
            f"We believe your talents will make a tremendous impact on our team and vision.\n\n"
            f"---\n"
            f"### 📋 Position Overview\n"
            f"• **Offered Role:** {role.mention} (`{role.name}`)\n"
            f"• **Organization:** **Echo Technologies**\n"
            f"• **Hiring Authority:** {interaction.user.mention} (`{interaction.user.display_name}`)\n"
            f"• **Date Issued:** <t:{now_ts}:D> (<t:{now_ts}:R>)\n"
            + (f"• **Executive Note:**\n> *\"{note.strip()}\"*\n" if note else "")
            + f"---\n"
            f"Please click **Accept Offer** or **Decline Offer** below to submit your decision."
        ),
        color=0x00A2FF,
        timestamp=discord.utils.utcnow()
    )

    if interaction.guild.icon:
        offer_embed.set_thumbnail(url=interaction.guild.icon.url)
    offer_embed.set_footer(text="Echo Technologies • Official Staff Recruitment Portal")

    offer_id = create_hire_offer(
        guild_id=interaction.guild.id,
        member_id=member.id,
        role_id=role.id,
        issuer_id=interaction.user.id,
        origin_channel_id=interaction.channel_id,
        role_name=role.name
    )

    offer_view = HireOfferView(
        bot=bot,
        offer_id=offer_id,
        member_id=member.id
    )

    try:
        dm = await member.create_dm()
        await dm.send(embed=offer_embed, view=offer_view)
    except discord.Forbidden:
        await interaction.response.send_message(
            f"❌ Could not deliver offer to {member.mention}: Their Direct Messages are closed or blocked.",
            ephemeral=True
        )
        return
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to dispatch offer DM: {e}", ephemeral=True)
        return

    confirm_embed = discord.Embed(
        title="📨 Employment Offer Dispatched",
        description=(
            f"An official Echo Technologies employment offer for **{role.mention}** has been delivered directly to {member.mention}'s DMs.\n\n"
            f"• **Candidate:** {member.mention} (`@{member.name}`)\n"
            f"• **Offered Role:** {role.mention}\n"
            f"• **Offer ID:** `#{offer_id}`\n"
            f"• **Automated Grant:** The role will be automatically granted immediately once they click **Accept Offer**."
        ),
        color=0x57F287,
        timestamp=discord.utils.utcnow()
    )
    confirm_embed.set_footer(text="Echo Technologies HR System")
    await interaction.response.send_message(embed=confirm_embed)


# ==========================================
# ⚠️ STAFF DISCIPLINARY & STRIKE SYSTEM (/strike)
# ==========================================

# ==========================================
# ⚠️ STAFF DISCIPLINARY & HR MANAGEMENT SUITE (/staff & /strike)
# ==========================================

staff_group = app_commands.Group(name="staff", description="HR Disciplinary & Staff Management Suite")

@staff_group.command(name="strike", description="Issue an HR disciplinary strike or warning to a staff member.")
@app_commands.describe(
    staff="Staff member receiving the strike",
    reason="Official reason or documentation for this disciplinary action",
    severity="Severity tier: 1 = Warning, 2 = Moderate Strike, 3 = Critical"
)
@app_commands.default_permissions(manage_guild=True)
async def staff_strike_cmd(
    interaction: discord.Interaction,
    staff: discord.Member,
    reason: str,
    severity: Literal[1, 2, 3] = 1
):
    if staff.bot:
        await interaction.response.send_message("❌ Bots cannot receive HR strikes.", ephemeral=True)
        return

    strike_id = add_strike(
        staff_id=staff.id,
        issuer_id=interaction.user.id,
        guild_id=interaction.guild.id if interaction.guild else 0,
        reason=reason,
        severity=severity
    )

    active_strikes = get_staff_strikes(staff.id, active_only=True)
    total_active = len(active_strikes)

    # 1. Send DM Notice to Staff
    dm_delivered = False
    try:
        dm = await staff.create_dm()
        dm_embed = build_strike_dm_embed(
            strike_id=strike_id,
            staff=staff,
            issuer=interaction.user,
            reason=reason,
            severity=severity,
            total_active=total_active
        )
        view = StrikeDMAppealView(strike_id=strike_id)
        await dm.send(embed=dm_embed, view=view)
        dm_delivered = True
    except Exception as e:
        logger.warning(f"Could not deliver strike DM to {staff.name}: {e}")

    # 2. Dispatch HR Audit Log to #hr-logs
    hr_ch = bot.get_channel(config.HR_LOGS_CHANNEL_ID) or bot.get_channel(config.MOD_LOGS_CHANNEL_ID)
    if hr_ch:
        try:
            log_embed = build_strike_log_embed(
                strike_id=strike_id,
                staff=staff,
                issuer=interaction.user,
                reason=reason,
                severity=severity,
                total_active=total_active
            )
            await hr_ch.send(embed=log_embed)
        except Exception as e:
            logger.error(f"Failed to post strike to HR channel: {e}")

    # 3. Progressive Discipline Escalation Check (#1)
    escalation_code, escalation_embed = await evaluate_strike_escalation(
        bot=bot,
        guild=interaction.guild,
        staff_member=staff,
        issuer=interaction.user,
        new_strike_id=strike_id
    )
    if escalation_embed and hr_ch:
        try:
            await hr_ch.send(embed=escalation_embed)
        except Exception:
            pass

    confirm_embed = discord.Embed(
        title="✅ HR Disciplinary Action Recorded",
        description=(
            f"Successfully recorded **{format_severity(severity)}** for {staff.mention} (`@{staff.name}`).\n\n"
            f"• **Record ID:** `#{strike_id}`\n"
            f"• **Total Active Strikes:** `{total_active}`\n"
            f"• **Direct Message Notice:** {'📨 Delivered' if dm_delivered else '⚠️ Failed (DMs Closed)'}\n"
            f"• **Progressive Escalation:** `{escalation_code}`"
        ),
        color=0x57F287,
        timestamp=discord.utils.utcnow()
    )
    confirm_embed.set_footer(text="Echo Technologies HR Systems")
    await interaction.response.send_message(embed=confirm_embed, ephemeral=True)


@staff_group.command(name="list-strikes", description="View disciplinary records and strike history for a staff member.")
@app_commands.describe(staff="Staff member to inspect")
@app_commands.default_permissions(manage_channels=True)
async def staff_list_strikes_cmd(interaction: discord.Interaction, staff: discord.Member):
    strikes = get_staff_strikes(staff.id, active_only=False)
    if not strikes:
        await interaction.response.send_message(f"ℹ️ {staff.mention} has a clean record with **0** recorded infractions.", ephemeral=True)
        return

    active_count = sum(1 for s in strikes if s["active"])
    embed = discord.Embed(
        title=f"📋 HR Record: {staff.display_name}",
        description=f"Showing disciplinary history for {staff.mention} (`{staff.id}`).\n**Active Strikes:** `{active_count}` | **Total History:** `{len(strikes)}` records",
        color=0xE67E22 if active_count > 0 else 0x57F287,
        timestamp=discord.utils.utcnow()
    )
    embed.set_thumbnail(url=staff.display_avatar.url)

    for s in strikes[:10]:
        status_icon = "🔴 Active" if s["active"] else f"🟢 Expunged"
        embed.add_field(
            name=f"Record #{s['id']} • {format_severity(s['severity'])} ({status_icon})",
            value=f"**Reason:** {s['reason']}\n**Supervisor:** <@{s['issuer_id']}>",
            inline=False
        )

    embed.set_footer(text="Echo Technologies HR Internal Records")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@staff_group.command(name="pardon", description="Pardon or expunge an active staff disciplinary strike.")
@app_commands.describe(strike_id="ID of the strike record to pardon", reason="Justification for pardon or appeal result")
@app_commands.default_permissions(manage_guild=True)
async def staff_pardon_cmd(interaction: discord.Interaction, strike_id: int, reason: str):
    strike = get_strike(strike_id)
    if not strike or not strike["active"]:
        await interaction.response.send_message(f"❌ Active strike record `#{strike_id}` was not found.", ephemeral=True)
        return

    pardon_strike(strike_id, interaction.user.id, reason)

    hr_ch = bot.get_channel(config.HR_LOGS_CHANNEL_ID)
    if hr_ch and isinstance(hr_ch, discord.TextChannel):
        try:
            p_embed = discord.Embed(
                title=f"🟢 HR Record Expunged: Strike #{strike_id}",
                description=(
                    f"Strike `#{strike_id}` issued to <@{strike['staff_id']}> has been **pardoned**.\n\n"
                    f"• **Pardoned By:** {interaction.user.mention} (`{interaction.user.name}`)\n"
                    f"• **Original Reason:** {strike['reason']}\n"
                    f"• **Pardon Reason:** {reason}"
                ),
                color=0x57F287,
                timestamp=discord.utils.utcnow()
            )
            await hr_ch.send(embed=p_embed)
        except Exception:
            pass

    staff_user = await safe_fetch_user(bot, strike["staff_id"])
    if staff_user:
        try:
            dm = await staff_user.create_dm()
            await dm.send(
                f"🟢 **Disciplinary Record Update:** Strike `#{strike_id}` has been pardoned and expunged by {interaction.user.mention}!\n"
                f"**Reason:** {reason}"
            )
        except Exception:
            pass

    await interaction.response.send_message(f"✅ Strike `#{strike_id}` for <@{strike['staff_id']}> has been pardoned.", ephemeral=True)


@staff_group.command(name="dossier", description="Generate a 360-degree HR dossier for any staff member.")
@app_commands.describe(member="Staff member to inspect (defaults to yourself)")
async def staff_dossier_cmd(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target = member or interaction.user
    embed = build_staff_dossier_embed(target, interaction.user)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@staff_group.command(name="suspend", description="Suspend a staff member's permissions and strip staff roles.")
@app_commands.describe(staff="Staff member to suspend", duration_days="Number of days for suspension", reason="Reason for suspension")
@app_commands.default_permissions(manage_guild=True)
async def staff_suspend_cmd(interaction: discord.Interaction, staff: discord.Member, duration_days: int, reason: str):
    await interaction.response.defer(ephemeral=True)
    success, msg = await suspend_staff_member(
        bot=bot,
        guild=interaction.guild,
        staff_member=staff,
        issuer=interaction.user,
        reason=reason,
        duration_days=duration_days
    )
    if success:
        # DM Notification
        try:
            dm = await staff.create_dm()
            s_embed = discord.Embed(
                title="⏸️ Echo Technologies • Notice of Staff Suspension",
                description=(
                    f"Hello **{staff.display_name}**,\n\n"
                    f"Your staff privileges have been temporarily **SUSPENDED** for `{duration_days}` days.\n\n"
                    f"• **Reason:** {reason}\n"
                    f"• **Issuing Supervisor:** {interaction.user.mention}\n"
                    f"• **Duration:** `{duration_days}` Days\n\n"
                    f"Your staff roles will be automatically restored when the suspension expires."
                ),
                color=0xE67E22,
                timestamp=discord.utils.utcnow()
            )
            await dm.send(embed=s_embed)
        except Exception:
            pass

        hr_ch = interaction.guild.get_channel(config.HR_LOGS_CHANNEL_ID) or interaction.guild.get_channel(config.MOD_LOGS_CHANNEL_ID)
        if hr_ch:
            embed = discord.Embed(
                title="⏸️ HR Notice: Staff Member Suspended",
                description=(
                    f"**Staff Member:** {staff.mention} (`@{staff.name}`)\n"
                    f"**Issuer:** {interaction.user.mention}\n"
                    f"**Duration:** `{duration_days}` Days\n"
                    f"**Reason:** {reason}"
                ),
                color=0xE67E22,
                timestamp=discord.utils.utcnow()
            )
            await hr_ch.send(embed=embed)
        await interaction.followup.send(f"✅ {msg}", ephemeral=True)
    else:
        await interaction.followup.send(f"❌ {msg}", ephemeral=True)


@staff_group.command(name="unsuspend", description="Lift a staff member's active suspension and restore staff roles.")
@app_commands.describe(staff="Staff member to unsuspend", reason="Reason for unsuspension")
@app_commands.default_permissions(manage_guild=True)
async def staff_unsuspend_cmd(interaction: discord.Interaction, staff: discord.Member, reason: str = "Manual Unsuspension by HR"):
    await interaction.response.defer(ephemeral=True)
    success, msg = await unsuspend_staff_member(
        bot=bot,
        guild=interaction.guild,
        staff_member=staff,
        unsuspended_by=interaction.user,
        reason=reason
    )
    if success:
        await interaction.followup.send(f"✅ {msg}", ephemeral=True)
    else:
        await interaction.followup.send(f"❌ {msg}", ephemeral=True)


@bot.tree.command(name="invite-comp", description="Host a new recruitment invite competition.")
@app_commands.describe(
    title="Competition title (e.g., Autumn Recruitment Race)",
    prize="Reward or prize description (e.g., 1000 Robux + Custom Role)",
    duration="Duration string (e.g., '7d', '24h', '3d')",
    channel="Target channel to post the competition embed (defaults to current channel)"
)
@app_commands.default_permissions(manage_guild=True)
async def invite_comp_cmd(
    interaction: discord.Interaction,
    title: str,
    prize: str,
    duration: str,
    channel: Optional[discord.TextChannel] = None
):
    td = parse_duration(duration)
    if not td:
        await interaction.response.send_message("❌ Invalid duration format! Use e.g. `7d`, `24h`, `3d`, `1w`.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    target_ch = channel or interaction.channel
    end_dt = datetime.now(timezone.utc) + td

    comp_id = create_invite_competition(
        guild_id=interaction.guild.id,
        channel_id=target_ch.id,
        title=title.strip(),
        prize=prize.strip(),
        host_id=interaction.user.id,
        end_time=end_dt
    )

    comp = get_invite_competition(comp_id)
    lb = get_inviter_counts(interaction.guild.id)
    embed = build_invite_comp_embed(comp, leaderboard=lb)
    view = InviteCompControlView(bot, comp_id)

    try:
        msg = await target_ch.send(embed=embed, view=view)
        set_invite_comp_message(comp_id, msg.id)
        await interaction.followup.send(f"🎉 **Invite Competition #{comp_id} Published!** Dispatched embed to {target_ch.mention}.", ephemeral=True)
    except Exception as e:
        logger.error(f"Error publishing invite competition: {e}")
        await interaction.followup.send(f"❌ Failed to post competition embed: {e}", ephemeral=True)


@bot.tree.command(name="invite-comp-edit", description="[HOST/ADMIN] Edit an active invite competition's details or extend duration.")
@app_commands.describe(
    comp_id="Competition ID number",
    new_title="Updated competition title",
    new_prize="Updated prize description",
    extend_minutes="Minutes to extend duration by (e.g. 60 for +1 hour)"
)
@app_commands.default_permissions(manage_guild=True)
async def invite_comp_edit_cmd(
    interaction: discord.Interaction,
    comp_id: int,
    new_title: Optional[str] = None,
    new_prize: Optional[str] = None,
    extend_minutes: Optional[int] = None
):
    success = edit_invite_competition(comp_id, new_title, new_prize, extend_minutes)
    if success:
        await update_invite_competition_embed(bot, comp_id)
        await interaction.response.send_message(f"✅ **Competition #{comp_id} updated!** Announcement embed refreshed.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Could not edit competition #{comp_id} (not found or already ended).", ephemeral=True)


@bot.tree.command(name="invite-comp-end", description="[HOST/ADMIN] Prematurely conclude an invite competition and announce winners.")
@app_commands.describe(comp_id="Competition ID number")
@app_commands.default_permissions(manage_guild=True)
async def invite_comp_end_cmd(interaction: discord.Interaction, comp_id: int):
    comp = get_invite_competition(comp_id)
    if not comp or comp["ended"]:
        await interaction.response.send_message(f"❌ Competition #{comp_id} not found or already concluded.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await end_invite_competition(bot, comp_id)
    await interaction.followup.send(f"🏆 **Competition #{comp_id} concluded!** Winners announced in the contest channel.", ephemeral=True)


@bot.tree.command(name="invite-disqualify", description="[HOST/ADMIN] Disqualify a member from invite competitions for cheating/alt spam.")
@app_commands.describe(member="Member to disqualify")
@app_commands.default_permissions(manage_guild=True)
async def invite_disqualify_cmd(interaction: discord.Interaction, member: discord.Member):
    disqualify_inviter(interaction.guild.id, member.id)
    await interaction.response.send_message(f"❌ {member.mention} (`@{member.name}`) has been **Disqualified** from invite competitions.", ephemeral=True)


@bot.tree.command(name="my-invite", description="Generate your trackable personal vanity invite link and view your stats card.")
async def my_invite_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    invite_url = f"https://discord.gg/{guild.id}"
    
    # Try creating or fetching channel invite link
    try:
        channels = [c for c in guild.text_channels if c.permissions_for(guild.me).create_instant_invite]
        if channels:
            inv = await channels[0].create_invite(max_age=0, max_uses=0, unique=False, reason=f"Personal link for {interaction.user.name}")
            invite_url = inv.url
    except Exception:
        pass

    stats = get_user_invite_stats(guild.id, interaction.user.id)
    embed = discord.Embed(
        title=f"🔗 Personal Invite Link — {interaction.user.display_name}",
        description=(
            f"Here is your official personal recruitment link for **{guild.name}**:\n\n"
            f"👉 **{invite_url}**\n\n"
            f"--- \n"
            f"### 📊 Your Recruitment Summary\n"
            f"• **⭐ Net Valid Invites:** **{stats['net_count']}**\n"
            f"• **👥 Total Member Joins:** `{stats['total_joins']}`\n"
            f"• **🚪 Member Leaves (-1):** `{stats['leaves_count']}`\n"
            f"• **⚠️ Flagged Alts (<7d):** `{stats['fakes_count']}`\n"
            f"• **🛡️ Status:** {'❌ **DISQUALIFIED**' if stats['is_disqualified'] else '✅ **ELIGIBLE**'}\n\n"
            f"Share this link with your friends to climb the live contest leaderboard!"
        ),
        color=0x5865F2,
        timestamp=discord.utils.utcnow()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="Echo Technologies Personal Invite Hub")
    
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Copy & Share Link", url=invite_url, emoji="🚀", style=discord.ButtonStyle.link))
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)


@bot.tree.command(name="invite-stats", description="View your personal invite statistics or another member's invites.")
@app_commands.describe(member="Member to inspect (leave empty for self)")
async def invite_stats_cmd(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target = member or interaction.user
    stats = get_user_invite_stats(interaction.guild.id, target.id)

    embed = discord.Embed(
        title=f"📊 Invite Statistics — {target.display_name}",
        description=(
            f"{target.mention} has recruited **{stats['net_count']} valid member(s)** into **{interaction.guild.name}**!\n\n"
            f"• **⭐ Net Valid Invites:** **{stats['net_count']}**\n"
            f"• **👥 Total Joins:** `{stats['total_joins']}`\n"
            f"• **🚪 Member Leaves:** `{stats['leaves_count']}`\n"
            f"• **⚠️ Flagged Alts:** `{stats['fakes_count']}`"
        ),
        color=0x5865F2,
        timestamp=discord.utils.utcnow()
    )
    embed.set_thumbnail(url=target.display_avatar.url)

    details = stats["details"]
    if details:
        recent_text = ""
        for d in details[:8]:
            status_tag = "✅ Valid"
            if d["is_fake"]:
                status_tag = "⚠️ Flagged Alt"
            elif d["left_server"]:
                status_tag = "🚪 Left Server"
            elif d["disqualified"]:
                status_tag = "❌ Disqualified"
            recent_text += f"• <@{d['user_id']}> (`{d['code']}`) — {status_tag}\n"
        embed.add_field(name="👥 Recrypted Members", value=recent_text, inline=False)
    else:
        embed.add_field(name="👥 Recrypted Members", value="*No invite records logged yet.*", inline=False)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="invite-leaderboard", description="View the current recruitment leaderboard.")
async def invite_leaderboard_cmd(interaction: discord.Interaction):
    lb = get_inviter_counts(interaction.guild.id)
    if not lb:
        await interaction.response.send_message("ℹ️ No invite records currently logged for this server.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"🏆 Recruitment Leaderboard — {interaction.guild.name}",
        description="Top community members who have invited new members:",
        color=0x5865F2,
        timestamp=discord.utils.utcnow()
    )
    embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    lb_text = ""
    for idx, (inv_id, cnt) in enumerate(lb[:10]):
        icon = medals[idx] if idx < len(medals) else f"`#{idx+1}`"
        lb_text += f"{icon} <@{inv_id}> — **{cnt}** invites\n"

    embed.add_field(name="📊 Top Recruiters", value=lb_text, inline=False)
    await interaction.response.send_message(embed=embed)


@staff_group.command(name="appeal", description="Open the modal to submit an appeal for an active strike.")
@app_commands.describe(strike_id="Optional HR Strike Record ID")
async def staff_appeal_cmd(interaction: discord.Interaction, strike_id: Optional[int] = None):
    if strike_id:
        modal = StrikeDMAppealModal(strike_id=strike_id)
        await interaction.response.send_modal(modal)
    else:
        await interaction.response.send_modal(StrikeAppealModal())


@staff_group.command(name="watchlist-add", description="Add a member or staff to the AI Sensitivity HR Watchlist.")
@app_commands.describe(member="Member to watchlist", reason="Reason for placing under monitoring", sensitivity="Sensitivity level")
@app_commands.choices(sensitivity=[
    app_commands.Choice(name="Low Sensitivity", value="low"),
    app_commands.Choice(name="Medium Sensitivity", value="medium"),
    app_commands.Choice(name="High Sensitivity", value="high")
])
@app_commands.default_permissions(manage_guild=True)
async def staff_watchlist_add_cmd(interaction: discord.Interaction, member: discord.Member, reason: str, sensitivity: str = "medium"):
    add_watchlist_user(member.id, interaction.user.id, reason, sensitivity)
    try:
        dm = await member.create_dm()
        w_embed = discord.Embed(
            title="👁️ Echo Technologies • HR Monitoring Notice",
            description=(
                f"Hello **{member.display_name}**,\n\n"
                f"This notice serves to inform you that your account has been placed under active **HR Sensitivity Monitoring**.\n\n"
                f"• **Reason:** {reason}\n"
                f"• **Sensitivity Level:** `{sensitivity}`\n\n"
                f"Please ensure all communications strictly follow Echo Technologies conduct guidelines."
            ),
            color=0xE67E22,
            timestamp=discord.utils.utcnow()
        )
        await dm.send(embed=w_embed)
    except Exception:
        pass

    await interaction.response.send_message(f"👁️ Added {member.mention} (`@{member.name}`) to the HR Watchlist (`{sensitivity}` sensitivity).", ephemeral=True)


@staff_group.command(name="watchlist-remove", description="Remove a member from the HR Watchlist.")
@app_commands.describe(member="Member to remove from watchlist")
@app_commands.default_permissions(manage_guild=True)
async def staff_watchlist_remove_cmd(interaction: discord.Interaction, member: discord.Member):
    success = remove_watchlist_user(member.id)
    if success:
        await interaction.response.send_message(f"✅ Removed {member.mention} from the HR Watchlist.", ephemeral=True)
    else:
        await interaction.response.send_message(f"ℹ️ {member.mention} was not on the HR Watchlist.", ephemeral=True)


@staff_group.command(name="watchlist-list", description="View all members on the HR Watchlist.")
@app_commands.default_permissions(manage_guild=True)
async def staff_watchlist_list_cmd(interaction: discord.Interaction):
    wlist = get_watchlist()
    if not wlist:
        await interaction.response.send_message("ℹ️ HR Watchlist is currently empty.", ephemeral=True)
        return
    embed = discord.Embed(
        title="👁️ Echo Technologies • HR Watchlist",
        description=f"Currently monitoring **{len(wlist)}** member(s) for sensitivity breaches:",
        color=0xE67E22
    )
    for entry in wlist[:15]:
        embed.add_field(
            name=f"User ID: {entry['user_id']}",
            value=f"**Reason:** {entry['reason']}\n**Added By:** <@{entry['added_by']}> | **Sensitivity:** `{entry['sensitivity']}`",
            inline=False
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@staff_group.command(name="blacklist-add", description="Dishonorably discharge and blacklist a former staff member from recruitment.")
@app_commands.describe(user="User to blacklist", reason="Reason for recruitment ban")
@app_commands.default_permissions(manage_guild=True)
async def staff_blacklist_add_cmd(interaction: discord.Interaction, user: discord.User, reason: str):
    add_staff_blacklist(user.id, interaction.user.id, reason)
    try:
        dm = await user.create_dm()
        b_embed = discord.Embed(
            title="🚫 Echo Technologies • Notice of Recruitment Blacklist",
            description=(
                f"Hello **{user.name}**,\n\n"
                f"Your account has been **DISHONORABLY DISCHARGED & BLACKLISTED** from Echo Technologies staff recruitment.\n\n"
                f"• **Reason:** {reason}\n"
                f"• **Issued By:** {interaction.user.mention}\n\n"
                f"You are barred from applying for any staff or developer positions."
            ),
            color=0xED4245,
            timestamp=discord.utils.utcnow()
        )
        await dm.send(embed=b_embed)
    except Exception:
        pass

    await interaction.response.send_message(f"🚫 Dishonorably discharged and blacklisted {user.mention} (`@{user.name}`) from applying for staff positions.", ephemeral=True)


@staff_group.command(name="blacklist-remove", description="Remove a user from the recruitment blacklist.")
@app_commands.describe(user="User to un-blacklist")
@app_commands.default_permissions(manage_guild=True)
async def staff_blacklist_remove_cmd(interaction: discord.Interaction, user: discord.User):
    success = remove_staff_blacklist(user.id)
    if success:
        await interaction.response.send_message(f"✅ Removed {user.mention} from the recruitment blacklist.", ephemeral=True)
    else:
        await interaction.response.send_message(f"ℹ️ {user.mention} was not on the recruitment blacklist.", ephemeral=True)


@staff_group.command(name="blacklist-list", description="View all recruitment-blacklisted former staff.")
@app_commands.default_permissions(manage_guild=True)
async def staff_blacklist_list_cmd(interaction: discord.Interaction):
    blist = get_staff_blacklists()
    if not blist:
        await interaction.response.send_message("ℹ️ Recruitment blacklist is currently empty.", ephemeral=True)
        return
    embed = discord.Embed(
        title="🚫 Echo Technologies • Recruitment Blacklist",
        description=f"Currently blocking **{len(blist)}** blacklisted former staff member(s):",
        color=0xED4245
    )
    for entry in blist[:15]:
        embed.add_field(
            name=f"User ID: {entry['user_id']}",
            value=f"**Reason:** {entry['reason']}\n**Added By:** <@{entry['added_by']}>",
            inline=False
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)

bot.tree.add_command(staff_group)


# ==========================================
# 💡 COMMUNITY SUGGESTIONS & VOTING DESK
# ==========================================

@bot.tree.command(name="suggest", description="Submit a community suggestion or idea for Echo Technologies.")
@app_commands.describe(
    idea="Your idea, feature request, or suggestion",
    attachment="Optional screenshot, mockup, or image attachment"
)
async def suggest_command(
    interaction: discord.Interaction,
    idea: str,
    attachment: Optional[discord.Attachment] = None
):
    if len(idea.strip()) < 10:
        await interaction.response.send_message("❌ Suggestions must be at least 10 characters in length.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    att_url = attachment.url if (attachment and attachment.content_type and "image" in attachment.content_type) else None
    sug_id = create_suggestion(
        author_id=interaction.user.id,
        guild_id=interaction.guild.id if interaction.guild else 0,
        content=idea.strip(),
        attachment_url=att_url
    )

    sug_channel = bot.get_channel(config.SUGGESTIONS_CHANNEL_ID)
    if not sug_channel:
        try:
            sug_channel = await bot.fetch_channel(config.SUGGESTIONS_CHANNEL_ID)
        except Exception:
            sug_channel = None

    if not sug_channel or not isinstance(sug_channel, discord.TextChannel):
        await interaction.followup.send("❌ Suggestions channel is currently unavailable. Please contact staff.", ephemeral=True)
        return

    sug_record = get_suggestion(sug_id)
    embed = build_suggestion_embed(sug_record, upvotes=0, downvotes=0, author=interaction.user)
    view = SuggestionVoteView(bot, sug_id, upvotes=0, downvotes=0)

    try:
        msg = await sug_channel.send(embed=embed, view=view)
        set_suggestion_message(sug_id, msg.id)
        await interaction.followup.send(
            f"✅ **Suggestion #{sug_id} Submitted!** Your idea has been posted in {sug_channel.mention} for community voting.",
            ephemeral=True
        )
    except Exception as e:
        logger.error(f"Error posting suggestion: {e}")
        await interaction.followup.send(f"❌ Failed to post suggestion: {e}", ephemeral=True)


# ==========================================
# 🧠 AI KNOWLEDGE BASE RETRAIN (/ai-retrain)
# ==========================================

@bot.tree.command(name="ai-retrain", description="[ADMIN] Instantly retrain and resync Groq AI knowledge base from #ai-trainer.")
@app_commands.default_permissions(administrator=True)
async def ai_retrain_cmd(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    report = await bot.ai_trainer.train_from_guild(interaction.guild)

    embed = discord.Embed(
        title="🧠 AI Knowledge Base Sync Complete",
        description=(
            f"Successfully resynced Groq AI assistant knowledge base!\n\n"
            f"• **Knowledge Size:** `{report['chars']} characters`\n"
            f"• **Messages Scraped:** `{report['trainer_messages']}`\n"
            f"• **Embeds Parsed:** `{report['embeds_parsed']}`\n"
            f"• **Sources:** {', '.join(report['sources']) if report['sources'] else 'None'}\n\n"
            f"Any deleted or edited messages in `#ai-trainer` have been completely purged from AI memory."
        ),
        color=0x57F287,
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text="Echo Technologies AI Assistant • Real-Time Memory Sync")
    await interaction.followup.send(embed=embed, ephemeral=True)


# ==========================================
# 🛠️ DEVELOPMENT BUG TRACKER (/bug)
# ==========================================

bug_group = app_commands.Group(name="bug", description="Development bug tracking and backlog")

@bug_group.command(name="report", description="Submit a bug report to the development backlog.")
@app_commands.describe(
    title="Short summary of the bug",
    description="Detailed explanation of what went wrong",
    reproduction_steps="Optional step-by-step instructions to trigger the bug",
    severity="Estimated severity tier"
)
async def bug_report_cmd(
    interaction: discord.Interaction,
    title: str,
    description: str,
    reproduction_steps: Optional[str] = None,
    severity: Literal["Low", "Normal", "High", "Critical"] = "Normal"
):
    await interaction.response.defer(ephemeral=True)

    bug_id = create_bug_report(
        reporter_id=interaction.user.id,
        guild_id=interaction.guild.id if interaction.guild else 0,
        title=title.strip(),
        description=description.strip(),
        reproduction_steps=reproduction_steps.strip() if reproduction_steps else None,
        severity=severity
    )

    dev_ch = bot.get_channel(config.DEV_BACKLOG_CHANNEL_ID)
    if not dev_ch:
        try:
            dev_ch = await bot.fetch_channel(config.DEV_BACKLOG_CHANNEL_ID)
        except Exception:
            dev_ch = None

    if not dev_ch or not isinstance(dev_ch, discord.TextChannel):
        await interaction.followup.send("❌ Development backlog channel is currently unavailable. Please inform staff.", ephemeral=True)
        return

    report = get_bug_report(bug_id)
    embed = build_bug_embed(report, reporter=interaction.user)
    view = BugReportControlView(bot, bug_id)

    try:
        msg = await dev_ch.send(embed=embed, view=view)
        set_bug_message(bug_id, msg.id)
        await interaction.followup.send(
            f"✅ **Bug Report #{bug_id} Logged!** Dispatched to {dev_ch.mention} for developer review.",
            ephemeral=True
        )
    except Exception as e:
        logger.error(f"Error dispatching bug report: {e}")
        await interaction.followup.send(f"❌ Failed to dispatch bug report: {e}", ephemeral=True)


@bug_group.command(name="list", description="List recent development bug reports.")
@app_commands.describe(status="Filter by status")
@app_commands.default_permissions(manage_channels=True)
async def bug_list_cmd(interaction: discord.Interaction, status: Optional[Literal["Open", "Claimed", "In Progress", "Resolved", "Closed"]] = None):
    bugs = get_recent_bugs(limit=10, status=status)
    if not bugs:
        await interaction.response.send_message(f"ℹ️ No bug reports found{' with status ' + status if status else ''}.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🛠️ Echo Technologies Bug Backlog",
        description=f"Showing recent bug reports{' (Status: ' + status + ')' if status else ''}:",
        color=0x00A2FF,
        timestamp=discord.utils.utcnow()
    )
    for b in bugs:
        embed.add_field(
            name=f"#{b['id']}: {b['title']} [{b['severity']}]",
            value=f"Status: **{b['status']}** • Reporter: <@{b['reporter_id']}> • Assigned: <@{b.get('claimed_by', 0)}>",
            inline=False
        )
    embed.set_footer(text="Echo Technologies Dev Backlog")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bug_group.command(name="info", description="View full details and resolution notes for a bug.")
@app_commands.describe(bug_id="Bug Report ID")
async def bug_info_cmd(interaction: discord.Interaction, bug_id: int):
    report = get_bug_report(bug_id)
    if not report:
        await interaction.response.send_message(f"❌ Bug Report `#{bug_id}` was not found.", ephemeral=True)
        return

    reporter = bot.get_user(report["reporter_id"])
    dev = bot.get_user(report.get("claimed_by", 0))
    embed = build_bug_embed(report, reporter, dev)
    await interaction.response.send_message(embed=embed, ephemeral=True)

bot.tree.add_command(bug_group)


# ==========================================
# 🎨 WELCOME TEST COMMAND (/welcome-test)
# ==========================================

@bot.tree.command(name="welcome-test", description="[ADMIN] Preview a welcome greeting card in #welcome.")
@app_commands.describe(member="Member to preview card for (defaults to you)")
@app_commands.default_permissions(administrator=True)
async def welcome_test(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target = member or interaction.user
    await interaction.response.defer(ephemeral=True)
    await send_welcome_greeting(bot, target)
    await interaction.followup.send(f"✅ Dispatched welcome test card for {target.mention} to <#{config.WELCOME_CHANNEL_ID}>!", ephemeral=True)


# ==========================================
# 🎁 COMMUNITY GIVEAWAY & EVENT SYSTEM
# ==========================================

giveaway_group = app_commands.Group(name="giveaway", description="Community giveaways and events")

@giveaway_group.command(name="start", description="Launch an interactive community giveaway.")
@app_commands.describe(
    prize="What is being given away (e.g. 1,000 Robux, VIP Rank, Nitro)",
    duration="Duration string (e.g. 30s, 10m, 2h, 1d, 3d, 1w)",
    winners="Number of winners to select (default: 1)",
    channel="Target channel for giveaway (defaults to current channel)"
)
@app_commands.default_permissions(manage_guild=True)
async def giveaway_start_cmd(
    interaction: discord.Interaction,
    prize: str,
    duration: str,
    winners: Optional[int] = 1,
    channel: Optional[discord.TextChannel] = None
):
    await interaction.response.defer(ephemeral=True)
    dur = parse_duration(duration)
    if not dur:
        await interaction.followup.send(
            "❌ Invalid duration format! Use formats like `30s`, `10m`, `2h`, `1d`, or `1w`.",
            ephemeral=True
        )
        return

    winners_cnt = max(1, min(winners or 1, 20))
    target_ch = channel or interaction.channel
    if not isinstance(target_ch, discord.TextChannel):
        await interaction.followup.send("❌ Giveaway must be hosted in a text channel.", ephemeral=True)
        return

    end_time = datetime.now(timezone.utc) + dur
    gw_id = create_giveaway(
        guild_id=interaction.guild.id,
        channel_id=target_ch.id,
        prize=prize.strip(),
        winners_count=winners_cnt,
        host_id=interaction.user.id,
        end_time=end_time
    )

    gw_data = get_giveaway(gw_id)
    embed = build_giveaway_embed(gw_data, entry_count=0, is_ended=False)
    view = GiveawayView(gw_id, entry_count=0, ended=False)

    try:
        msg = await target_ch.send(embed=embed, view=view)
        set_giveaway_message(gw_id, msg.id)
        await interaction.followup.send(
            f"🎉 **Giveaway #{gw_id} Launched!** Dispatched to {target_ch.mention}.",
            ephemeral=True
        )
    except Exception as e:
        logger.error(f"Error posting giveaway message: {e}")
        await interaction.followup.send(f"❌ Failed to post giveaway message: {e}", ephemeral=True)

@giveaway_group.command(name="end", description="End an active giveaway early and pick winners.")
@app_commands.describe(
    giveaway_id="Giveaway ID (or leave empty to check by message ID)",
    message_id="Discord message ID of the giveaway"
)
@app_commands.default_permissions(manage_guild=True)
async def giveaway_end_cmd(
    interaction: discord.Interaction,
    giveaway_id: Optional[int] = None,
    message_id: Optional[str] = None
):
    await interaction.response.defer(ephemeral=True)
    target_id = giveaway_id
    if not target_id and message_id:
        try:
            m_id = int(message_id.strip())
            gw = get_giveaway_by_message(m_id)
            if gw:
                target_id = gw["id"]
        except Exception:
            pass

    if not target_id:
        await interaction.followup.send("❌ Please provide a valid `giveaway_id` or `message_id`.", ephemeral=True)
        return

    success, msg, winners = await end_giveaway(bot, target_id)
    if success:
        w_str = ", ".join([f"<@{w}>" for w in winners]) if winners else "None"
        await interaction.followup.send(f"✅ **Giveaway #{target_id} ended!** Winners: {w_str}", ephemeral=True)
    else:
        await interaction.followup.send(f"⚠️ {msg}", ephemeral=True)

@giveaway_group.command(name="reroll", description="Reroll new winner(s) for a concluded giveaway.")
@app_commands.describe(
    giveaway_id="Giveaway ID (or leave empty to check by message ID)",
    message_id="Discord message ID of the giveaway",
    winners="Number of winners to reroll (default: 1)"
)
@app_commands.default_permissions(manage_guild=True)
async def giveaway_reroll_cmd(
    interaction: discord.Interaction,
    giveaway_id: Optional[int] = None,
    message_id: Optional[str] = None,
    winners: Optional[int] = 1
):
    await interaction.response.defer(ephemeral=True)
    target_id = giveaway_id
    if not target_id and message_id:
        try:
            m_id = int(message_id.strip())
            gw = get_giveaway_by_message(m_id)
            if gw:
                target_id = gw["id"]
        except Exception:
            pass

    if not target_id:
        await interaction.followup.send("❌ Please provide a valid `giveaway_id` or `message_id`.", ephemeral=True)
        return

    cnt = max(1, min(winners or 1, 20))
    success, msg, new_winners = await reroll_giveaway(bot, target_id, winners_count=cnt)
    if success:
        w_str = ", ".join([f"<@{w}>" for w in new_winners])
        await interaction.followup.send(f"🎲 **Giveaway #{target_id} rerolled!** New winner(s): {w_str}", ephemeral=True)
    else:
        await interaction.followup.send(f"⚠️ {msg}", ephemeral=True)

bot.tree.add_command(giveaway_group)


# ==========================================
# 🎟️ COMMUNITY EVENT CALENDAR & RSVP SYSTEM
# ==========================================

event_group = app_commands.Group(name="event", description="Community event calendar and RSVP")

@event_group.command(name="schedule", description="Schedule a community event with RSVP buttons and member DM broadcast.")
@app_commands.describe(
    title="Name/Title of the event",
    duration="Time until event starts (e.g. 30m, 2h, 1d, 3d, 1w)",
    description="Details, instructions, and info about the event",
    channel="Channel to announce event in (defaults to current channel)",
    broadcast_dm="Send an invitation DM to all server members (default: True)"
)
@app_commands.default_permissions(manage_events=True)
async def event_schedule_cmd(
    interaction: discord.Interaction,
    title: str,
    duration: str,
    description: str,
    channel: Optional[discord.TextChannel] = None,
    broadcast_dm: Optional[bool] = True
):
    await interaction.response.defer(ephemeral=True)
    dur = parse_duration(duration)
    if not dur:
        await interaction.followup.send(
            "❌ Invalid time duration format! Use formats like `30s`, `10m`, `2h`, `1d`, `3d`, or `1w`.",
            ephemeral=True
        )
        return

    target_ch = channel or interaction.channel
    if not isinstance(target_ch, discord.TextChannel):
        await interaction.followup.send("❌ Events must be announced in a text channel.", ephemeral=True)
        return

    event_time = datetime.now(timezone.utc) + dur
    ev_id = create_event(
        guild_id=interaction.guild.id,
        channel_id=target_ch.id,
        title=title.strip(),
        description=description.strip(),
        host_id=interaction.user.id,
        event_time=event_time
    )

    ev_data = get_event(ev_id)
    counts = {"attending": 0, "maybe": 0, "declined": 0}
    embed = build_event_embed(ev_data, counts)
    view = EventRsvpView(ev_id, counts)

    try:
        msg = await target_ch.send(embed=embed, view=view)
        set_event_message(ev_id, msg.id)

        # Broadcast DM to all server members if requested
        if broadcast_dm and interaction.guild:
            asyncio.create_task(broadcast_event_dm_task(bot, ev_data, interaction.guild, msg.jump_url))
            broadcast_note = " 📬 **Dispatched invitation DMs to all server members!**"
        else:
            broadcast_note = ""

        await interaction.followup.send(
            f"🎉 **Event #{ev_id} Scheduled!** Dispatched to {target_ch.mention}.{broadcast_note}",
            ephemeral=True
        )
    except Exception as e:
        logger.error(f"Error publishing event: {e}")
        await interaction.followup.send(f"❌ Failed to post event: {e}", ephemeral=True)

@event_group.command(name="list", description="List upcoming scheduled community events.")
async def event_list_cmd(interaction: discord.Interaction):
    upcoming = get_upcoming_events()
    if not upcoming:
        await interaction.response.send_message("ℹ️ No upcoming events currently scheduled.", ephemeral=True)
        return

    embed = discord.Embed(
        title="📅 Upcoming Echo Technologies Events",
        color=0x5865F2,
        timestamp=discord.utils.utcnow()
    )
    for ev in upcoming[:10]:
        counts = get_event_rsvp_counts(ev["id"])
        end_raw = ev["event_time"]
        try:
            dt = datetime.fromisoformat(end_raw) if isinstance(end_raw, str) else end_raw
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            ts = int(dt.timestamp())
            time_str = f"<t:{ts}:F> (<t:{ts}:R>)"
        except Exception:
            time_str = str(end_raw)

        embed.add_field(
            name=f"#{ev['id']}: {ev['title']}",
            value=(
                f"**When:** {time_str}\n"
                f"**Host:** <@{ev['host_id']}> • **Channel:** <#{ev['channel_id']}>\n"
                f"**RSVP:** ✅ `{counts['attending']}` | ❓ `{counts['maybe']}` | ❌ `{counts['declined']}`"
            ),
            inline=False
        )
    embed.set_footer(text="Echo Technologies Community Calendar")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@event_group.command(name="cancel", description="Cancel a scheduled community event.")
@app_commands.describe(event_id="ID of the event to cancel")
@app_commands.default_permissions(manage_events=True)
async def event_cancel_cmd(interaction: discord.Interaction, event_id: int):
    ev = get_event(event_id)
    if not ev:
        await interaction.response.send_message(f"❌ Event `#{event_id}` was not found.", ephemeral=True)
        return

    cancel_event(event_id)
    counts = get_event_rsvp_counts(event_id)
    embed = build_event_embed(ev, counts, is_cancelled=True)
    view = EventRsvpView(event_id, counts, disabled=True)

    ch = bot.get_channel(ev["channel_id"])
    if ch and ev.get("message_id"):
        try:
            msg = await ch.fetch_message(ev["message_id"])
            await msg.edit(embed=embed, view=view)
        except Exception:
            pass

    await interaction.response.send_message(f"🛑 Event `#{event_id}` has been cancelled.", ephemeral=True)

bot.tree.add_command(event_group)


# ==========================================
# 🏖️ LEAVE OF ABSENCE (LOA) PORTAL
# ==========================================

loa_group = app_commands.Group(name="loa", description="Staff Leave of Absence portal")

@loa_group.command(name="request", description="Submit a formal Leave of Absence request to management.")
@app_commands.describe(
    duration="Requested duration (e.g. 3 days, 1 week, Oct 10 - Oct 15)",
    reason="Explanation / reason for the leave"
)
async def loa_request_cmd(interaction: discord.Interaction, duration: str, reason: str):
    await interaction.response.defer(ephemeral=True)
    active = get_user_active_loa(interaction.user.id)
    if active and active["status"] == "pending":
        await interaction.followup.send(
            f"⚠️ You already have a pending LOA request (ID: `#{active['id']}`). Please await management review.",
            ephemeral=True
        )
        return

    loa_id = create_loa_request(
        user_id=interaction.user.id,
        guild_id=interaction.guild.id if interaction.guild else 0,
        duration=duration.strip(),
        reason=reason.strip()
    )

    loa_data = get_loa_request(loa_id)
    embed = build_loa_staff_embed(loa_data, interaction.user)
    view = LOAControlView(loa_id)

    # Dispatch to HR logs channel
    hr_ch = interaction.guild.get_channel(config.HR_LOGS_CHANNEL_ID) if interaction.guild else None
    if hr_ch and isinstance(hr_ch, discord.TextChannel):
        try:
            log_msg = await hr_ch.send(embed=embed, view=view)
            set_loa_message_id(loa_id, log_msg.id)
        except Exception as e:
            logger.error(f"Error posting LOA to HR channel: {e}")

    await interaction.followup.send(
        f"🏖️ **Leave of Absence Request #{loa_id} Submitted!** Management has been notified for review.",
        ephemeral=True
    )

@loa_group.command(name="list", description="View recent staff Leave of Absence requests.")
@app_commands.describe(status="Filter by status (pending, approved, denied)")
@app_commands.default_permissions(manage_roles=True)
async def loa_list_cmd(interaction: discord.Interaction, status: Optional[Literal["pending", "approved", "denied"]] = None):
    requests = get_loa_requests(status=status, limit=10)
    if not requests:
        await interaction.response.send_message(f"ℹ️ No LOA requests found{' with status ' + status if status else ''}.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🏖️ Staff Leave of Absence (LOA) Registry",
        description=f"Showing recent requests{' (Filter: ' + status + ')' if status else ''}:",
        color=0x5865F2,
        timestamp=discord.utils.utcnow()
    )
    for r in requests:
        embed.add_field(
            name=f"#{r['id']} • <@{r['user_id']}> [{r['status'].upper()}]",
            value=f"**Duration:** `{r['duration']}`\n**Reason:** {r['reason'][:100]}\n**Logged:** <t:{int(datetime.fromisoformat(r['created_at']).timestamp())}:R>",
            inline=False
        )
    embed.set_footer(text="Echo Technologies HR Operations")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@loa_group.command(name="approve", description="[HR/ADMIN] Approve a staff member's Leave of Absence.")
@app_commands.describe(loa_id="ID of the LOA request")
@app_commands.default_permissions(manage_roles=True)
async def loa_approve_cmd(interaction: discord.Interaction, loa_id: int):
    await interaction.response.defer(ephemeral=True)
    success, msg, updated = review_loa_request(loa_id, interaction.user.id, "approved")
    if not success:
        await interaction.followup.send(f"⚠️ {msg}", ephemeral=True)
        return

    staff_user = bot.get_user(updated["user_id"])
    if staff_user:
        try:
            dm = await staff_user.create_dm()
            dm_embed = discord.Embed(
                title=f"🏖️ LOA Request #{loa_id} Approved!",
                description=(
                    f"Hello {staff_user.name}, your Leave of Absence request has been **Approved** by {interaction.user.mention}!\n\n"
                    f"**Duration:** `{updated['duration']}`\n"
                    f"Take care, and we look forward to having you back."
                ),
                color=0x57F287
            )
            await dm.send(embed=dm_embed)
        except Exception:
            pass

    await interaction.followup.send(f"✅ LOA `#{loa_id}` has been approved.", ephemeral=True)

@loa_group.command(name="deny", description="[HR/ADMIN] Deny a staff member's Leave of Absence.")
@app_commands.describe(loa_id="ID of the LOA request", reason="Explanation for denial")
@app_commands.default_permissions(manage_roles=True)
async def loa_deny_cmd(interaction: discord.Interaction, loa_id: int, reason: str):
    await interaction.response.defer(ephemeral=True)
    success, msg, updated = review_loa_request(loa_id, interaction.user.id, "denied", review_note=reason)
    if not success:
        await interaction.followup.send(f"⚠️ {msg}", ephemeral=True)
        return

    staff_user = bot.get_user(updated["user_id"])
    if staff_user:
        try:
            dm = await staff_user.create_dm()
            dm_embed = discord.Embed(
                title=f"🏖️ LOA Request #{loa_id} Denied",
                description=(
                    f"Hello {staff_user.name}, your Leave of Absence request was **Denied** by {interaction.user.mention}.\n\n"
                    f"**Reason:** {reason}"
                ),
                color=0xED4245
            )
            await dm.send(embed=dm_embed)
        except Exception:
            pass

    await interaction.followup.send(f"❌ LOA `#{loa_id}` has been denied.", ephemeral=True)

bot.tree.add_command(loa_group)


# ==========================================
# 💬 LEVELING & RANK COMMANDS (/rank, /top)
# ==========================================

@bot.tree.command(name="rank", description="Check your or another member's chat level, rank, and XP progress.")
@app_commands.describe(member="Member to view (defaults to you)")
async def rank_cmd(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target = member or interaction.user
    await interaction.response.defer()

    level_data = get_user_level_data(target.id, interaction.guild.id if interaction.guild else 0)
    rank_pos, total_ranks = get_user_rank_position(target.id, interaction.guild.id if interaction.guild else 0)
    roblox_info = bot.db.get_by_discord_id(target.id)

    headshot_url = None
    if roblox_info:
        headshot_url = await bot.roblox_api.get_user_headshot(roblox_info["roblox_id"])

    embed = build_rank_card_embed(
        user=target,
        level_data=level_data,
        rank_pos=rank_pos,
        total_ranks=total_ranks,
        roblox_info=roblox_info,
        headshot_url=headshot_url
    )
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="top", description="View the top 10 most active members on the server XP leaderboard.")
async def top_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    top_users = get_guild_leaderboard(interaction.guild.id if interaction.guild else 0, limit=10)
    embed = build_leaderboard_embed(interaction.guild, top_users, bot)
    await interaction.followup.send(embed=embed)


# ==========================================
# 💼 CAREER APPLICATION COMMANDS
# ==========================================

async def _post_career_panel_logic(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    await interaction.response.defer(ephemeral=True)
    target_ch = channel or bot.get_channel(config.CAREER_OPPORTUNITIES_CHANNEL_ID) or interaction.channel
    if not isinstance(target_ch, discord.TextChannel):
        await interaction.followup.send("❌ Target channel must be a text channel.", ephemeral=True)
        return

    embed = build_career_panel_embed()
    view = CareerLaunchView()
    try:
        await target_ch.send(embed=embed, view=view)
        await interaction.followup.send(f"✅ Career recruitment panel posted to {target_ch.mention}!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to post career panel: {e}", ephemeral=True)

@bot.tree.command(name="post-career-panel", description="[ADMIN] Post the interactive career recruitment panel.")
@app_commands.describe(channel="Target channel to post in (defaults to #career-opportunities)")
@app_commands.default_permissions(administrator=True)
async def post_career_panel_cmd(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    await _post_career_panel_logic(interaction, channel)

@bot.tree.command(name="apply", description="Apply for an open position at Echo Technologies via Direct Message.")
@app_commands.describe(position="Position you are applying for")
@app_commands.choices(position=[
    app_commands.Choice(name="🛠️ Product Development", value="product_development"),
    app_commands.Choice(name="🛡️ Support Team", value="support_team"),
    app_commands.Choice(name="📢 Public Relations", value="public_relations"),
    app_commands.Choice(name="🧪 QA Game Tester", value="qa_tester")
])
async def apply_cmd(interaction: discord.Interaction, position: str):
    await interaction.response.defer(ephemeral=True)
    success, reply_msg = await start_dm_application_flow(
        bot=bot,
        user=interaction.user,
        guild=interaction.guild or bot.get_primary_guild(),
        position_key=position
    )
    await interaction.followup.send(reply_msg, ephemeral=True)


async def _execute_close_applications(
    interaction: discord.Interaction,
    position: str = "all",
    reason: Optional[str] = None
):
    is_staff = interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.manage_roles
    if not is_staff:
        await interaction.response.send_message("❌ Only management staff can manage applications.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    close_reason = reason.strip() if reason else "Applications are currently closed."
    updated_keys = close_applications(position_key=position, reason=close_reason, closed_by=interaction.user.id)

    synced = await sync_career_panel_message(bot)

    names = [APPLICATION_POSITIONS[k]["title"] for k in updated_keys if k in APPLICATION_POSITIONS]
    names_str = ", ".join(f"**{n}**" for n in names) if names else f"**{position}**"

    embed = discord.Embed(
        title="🔒 Applications Closed",
        description=(
            f"Successfully closed applications for: {names_str}\n\n"
            f"**Reason:** {close_reason}\n"
            f"**Closed By:** {interaction.user.mention}\n\n"
            + (f"✅ Recruitment panel in <#{config.CAREER_OPPORTUNITIES_CHANNEL_ID}> has been updated live!"
               if synced else
               f"⚠️ Note: Could not auto-update panel in <#{config.CAREER_OPPORTUNITIES_CHANNEL_ID}>.")
        ),
        color=0xED4245,
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text="Echo Technologies Recruitment Management")
    await interaction.followup.send(embed=embed)

async def _execute_open_applications(
    interaction: discord.Interaction,
    position: str = "all"
):
    is_staff = interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.manage_roles
    if not is_staff:
        await interaction.response.send_message("❌ Only management staff can manage applications.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    updated_keys = open_applications(position_key=position, opened_by=interaction.user.id)

    synced = await sync_career_panel_message(bot)

    names = [APPLICATION_POSITIONS[k]["title"] for k in updated_keys if k in APPLICATION_POSITIONS]
    names_str = ", ".join(f"**{n}**" for n in names) if names else f"**{position}**"

    embed = discord.Embed(
        title="🔓 Applications Re-Opened",
        description=(
            f"Successfully re-opened applications for: {names_str}\n\n"
            f"**Opened By:** {interaction.user.mention}\n\n"
            + (f"✅ Recruitment panel in <#{config.CAREER_OPPORTUNITIES_CHANNEL_ID}> has been updated live!"
               if synced else
               f"⚠️ Note: Could not auto-update panel in <#{config.CAREER_OPPORTUNITIES_CHANNEL_ID}>.")
        ),
        color=0x57F287,
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text="Echo Technologies Recruitment Management")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="close-applications", description="Close staff and developer applications.")
@app_commands.describe(
    position="The position to close (or all positions)",
    reason="Optional reason for closing (e.g. Positions filled, hiring freeze)"
)
@app_commands.choices(position=[
    app_commands.Choice(name="🌐 All Positions", value="all"),
    app_commands.Choice(name="🛠️ Product Development", value="product_development"),
    app_commands.Choice(name="🛡️ Support Team", value="support_team"),
    app_commands.Choice(name="📢 Public Relations", value="public_relations"),
    app_commands.Choice(name="🧪 QA Game Tester", value="qa_tester")
])
@app_commands.default_permissions(administrator=True)
async def close_applications_cmd(
    interaction: discord.Interaction,
    position: str = "all",
    reason: Optional[str] = None
):
    await _execute_close_applications(interaction, position, reason)

@bot.tree.command(name="open-applications", description="Re-open staff and developer applications.")
@app_commands.describe(
    position="The position to open (or all positions)"
)
@app_commands.choices(position=[
    app_commands.Choice(name="🌐 All Positions", value="all"),
    app_commands.Choice(name="🛠️ Product Development", value="product_development"),
    app_commands.Choice(name="🛡️ Support Team", value="support_team"),
    app_commands.Choice(name="📢 Public Relations", value="public_relations"),
    app_commands.Choice(name="🧪 QA Game Tester", value="qa_tester")
])
@app_commands.default_permissions(administrator=True)
async def open_applications_cmd(
    interaction: discord.Interaction,
    position: str = "all"
):
    await _execute_open_applications(interaction, position)

@bot.tree.command(name="application-transcript", description="[STAFF] Export an HTML transcript of an application dossier.")
@app_commands.describe(app_id="The application ID to export")
@app_commands.default_permissions(manage_roles=True)
async def application_transcript_cmd(interaction: discord.Interaction, app_id: int):
    await interaction.response.defer(ephemeral=True)
    app = get_application(app_id)
    if not app:
        await interaction.followup.send("❌ Application not found.", ephemeral=True)
        return

    pos_data = APPLICATION_POSITIONS.get(app["position_key"], {})
    questions = pos_data.get("questions", [])
    user_info = bot.db.get_by_discord_id(app["user_id"])
    candidate = bot.get_user(app["user_id"])
    if candidate and user_info:
        user_info["discord_name"] = candidate.name
    elif candidate:
        user_info = {"discord_name": candidate.name}

    reviewer = bot.get_user(app["reviewed_by"]) if app.get("reviewed_by") else None
    reviewer_name = reviewer.name if reviewer else None

    html_content = generate_application_html_transcript(
        app_data=app,
        questions=questions,
        user_info=user_info,
        reviewer_name=reviewer_name
    )
    filename = f"application_{app_id}_dossier.html"
    file = discord.File(io.BytesIO(html_content.encode("utf-8")), filename=filename)

    await interaction.followup.send(
        content=f"📥 **HTML Dossier Transcript generated for Application #{app_id}** (`{app['position_title']}`):",
        file=file,
        ephemeral=True
    )

# --- Applications Subcommand Group ---
applications_group = app_commands.Group(name="applications", description="Manage staff and developer recruitment positions")

@applications_group.command(name="close", description="Close staff and developer applications.")
@app_commands.describe(
    position="The position to close (or all positions)",
    reason="Optional reason for closing (e.g. Positions filled, hiring freeze)"
)
@app_commands.choices(position=[
    app_commands.Choice(name="🌐 All Positions", value="all"),
    app_commands.Choice(name="🛠️ Product Development", value="product_development"),
    app_commands.Choice(name="🛡️ Support Team", value="support_team"),
    app_commands.Choice(name="📢 Public Relations", value="public_relations"),
    app_commands.Choice(name="🧪 QA Game Tester", value="qa_tester")
])
async def app_grp_close(interaction: discord.Interaction, position: str = "all", reason: Optional[str] = None):
    await _execute_close_applications(interaction, position, reason)

@applications_group.command(name="open", description="Re-open staff and developer applications.")
@app_commands.describe(
    position="The position to open (or all positions)"
)
@app_commands.choices(position=[
    app_commands.Choice(name="🌐 All Positions", value="all"),
    app_commands.Choice(name="🛠️ Product Development", value="product_development"),
    app_commands.Choice(name="🛡️ Support Team", value="support_team"),
    app_commands.Choice(name="📢 Public Relations", value="public_relations"),
    app_commands.Choice(name="🧪 QA Game Tester", value="qa_tester")
])
async def app_grp_open(interaction: discord.Interaction, position: str = "all"):
    await _execute_open_applications(interaction, position)


@applications_group.command(name="status", description="Check current vacancy status and statistics for all application positions.")
async def app_grp_status(interaction: discord.Interaction):
    statuses = get_all_position_statuses()
    stats = get_application_stats()

    embed = discord.Embed(
        title="📋 Recruitment & Applications Status",
        description="Current vacancy status for Echo Technologies recruitment:",
        color=0x5865F2,
        timestamp=discord.utils.utcnow()
    )
    for key, data in APPLICATION_POSITIONS.items():
        st = statuses.get(key, {"is_open": True, "closed_reason": ""})
        if st["is_open"]:
            val = "🟢 **OPEN** — Accepting submissions via DMs"
        else:
            reason = f"\n> **Reason:** *{st['closed_reason']}*" if st['closed_reason'] else ""
            val = f"🔴 **CLOSED**{reason}"
        embed.add_field(name=f"{data['emoji']} {data['title']}", value=val, inline=False)

    pending_count = stats.get("pending_review", 0)
    approved_count = stats.get("approved", 0)
    denied_count = stats.get("denied", 0)
    total_count = stats.get("total", 0)

    embed.add_field(
        name="📊 Application Statistics",
        value=(
            f"• ⏳ **Pending Review:** `{pending_count}`\n"
            f"• ✅ **Approved / Hired:** `{approved_count}`\n"
            f"• ❌ **Denied:** `{denied_count}`\n"
            f"• 📁 **Total Submissions:** `{total_count}`"
        ),
        inline=False
    )
    embed.set_footer(text=f"Recruitment: #{config.CAREER_OPPORTUNITIES_CHANNEL_ID} • Submissions: #{config.APPLICATIONS_SUBMISSIONS_CHANNEL_ID}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@applications_group.command(name="panel", description="Refresh or repost the career recruitment panel in #career-opportunities.")
@app_commands.describe(channel="Text channel to post or refresh the recruitment panel (defaults to configured channel)")
async def app_grp_panel(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    await _post_career_panel_logic(interaction, channel)

bot.tree.add_command(applications_group)


@bot.tree.command(name="poll", description="Create an interactive community vote poll.")
@app_commands.describe(
    question="The topic or question for the poll",
    option1="Option 1",
    option2="Option 2",
    option3="Optional Option 3",
    option4="Optional Option 4"
)
async def poll_cmd(
    interaction: discord.Interaction,
    question: str,
    option1: str,
    option2: str,
    option3: Optional[str] = None,
    option4: Optional[str] = None
):
    await interaction.response.defer()
    options = [opt for opt in [option1, option2, option3, option4] if opt]
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]

    desc_lines = [f"**{question}**\n"]
    for idx, opt in enumerate(options):
        desc_lines.append(f"{emojis[idx]} {opt}")

    embed = discord.Embed(
        title="📊 Community Poll",
        description="\n".join(desc_lines),
        color=0x5865F2,
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text=f"Poll created by {interaction.user.name} • React below to vote!")
    msg = await interaction.followup.send(embed=embed, wait=True)
    for idx in range(len(options)):
        try:
            await msg.add_reaction(emojis[idx])
        except Exception:
            pass

@bot.tree.command(name="post-support-templates", description="[ADMIN] Post or refresh support guidelines and response templates in #support-templates.")
@app_commands.describe(channel="Target channel (defaults to #support-templates)")
@app_commands.default_permissions(administrator=True)
async def post_support_templates_cmd(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    await interaction.response.defer(ephemeral=True)
    target_ch = channel or bot.get_channel(config.SUPPORT_TEMPLATES_CHANNEL_ID)
    success = await sync_support_templates_channel(bot, channel=target_ch)
    if success:
        ch_mention = target_ch.mention if target_ch else f"<#{config.SUPPORT_TEMPLATES_CHANNEL_ID}>"
        await interaction.followup.send(f"✅ **Support response templates and guidelines posted to {ch_mention}!**", ephemeral=True)
    else:
        await interaction.followup.send("❌ Failed to post support templates.", ephemeral=True)




# ==========================================
# 🛡️ ADVANCED MODERATION & SECURITY SYSTEM
# ==========================================

@bot.tree.command(name="warn", description="Issue an official warning to a server member.")
@app_commands.describe(member="Member to warn", reason="Reason for warning")
@app_commands.default_permissions(moderate_members=True)
async def warn_cmd(interaction: discord.Interaction, member: discord.Member, reason: str):
    if member.id == interaction.user.id:
        await interaction.response.send_message("❌ You cannot warn yourself.", ephemeral=True)
        return
    if member.id == bot.user.id:
        await interaction.response.send_message("❌ You cannot warn the bot.", ephemeral=True)
        return
    if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ You cannot warn a member with an equal or higher role than you.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    warn_id, total = add_warning(interaction.guild_id, member.id, interaction.user.id, interaction.user.name, reason)
    await send_dm_infraction_notice(member, "Warned", reason, interaction.guild.name)

    case_id = await dispatch_mod_log(
        bot=bot,
        guild=interaction.guild,
        action="warn",
        target=member,
        moderator=interaction.user,
        reason=reason,
        extra_field=("⚠️ Warning Statistics", f"Warning #{warn_id} • Member now has **{total}** total warning(s).")
    )

    embed = discord.Embed(
        title="⚠️ Member Warned",
        description=f"Successfully issued a warning to {member.mention}.\n\n**Reason:** {reason}\n**Total Warnings:** `{total}`\n**Case:** `#{case_id}`",
        color=0xFEE75C
    )
    embed.set_footer(text=f"Audit logged in #{config.MOD_LOGS_CHANNEL_ID}")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="warnings", description="View all warnings issued to a member.")
@app_commands.describe(member="Member to check")
@app_commands.default_permissions(moderate_members=True)
async def warnings_cmd(interaction: discord.Interaction, member: discord.Member):
    warns = get_warnings(interaction.guild_id, member.id)
    if not warns:
        await interaction.response.send_message(f"ℹ️ {member.mention} has no warnings on record.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"⚠️ Warnings History • {member.name}",
        description=f"Showing all **{len(warns)}** recorded warning(s) for {member.mention}:",
        color=0xFEE75C,
        timestamp=discord.utils.utcnow()
    )
    for i, w in enumerate(warns[:10], 1):
        ts = w['created_at']
        embed.add_field(
            name=f"#{i} • Warn ID {w['id']} ({ts})",
            value=f"**Mod:** <@{w['moderator_id']}> (`{w['moderator_name']}`)\n**Reason:** {w['reason']}",
            inline=False
        )
    if len(warns) > 10:
        embed.set_footer(text=f"Showing 10 of {len(warns)} total warnings")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="clear-warnings", description="Clear all warnings from a member.")
@app_commands.describe(member="Member whose warnings will be wiped")
@app_commands.default_permissions(manage_messages=True)
async def clear_warnings_cmd(interaction: discord.Interaction, member: discord.Member):
    count = clear_warnings(interaction.guild_id, member.id)
    if count == 0:
        await interaction.response.send_message(f"ℹ️ {member.mention} has no warnings to clear.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    case_id = await dispatch_mod_log(
        bot=bot,
        guild=interaction.guild,
        action="untimeout",
        target=member,
        moderator=interaction.user,
        reason=f"Cleared {count} past warnings.",
        extra_field=("🧹 Action", f"Wiped all `{count}` historical warnings from database.")
    )

    embed = discord.Embed(
        title="🧹 Warnings Cleared",
        description=f"Successfully wiped **{count}** warning(s) from {member.mention}.\n**Case:** `#{case_id}`",
        color=0x57F287
    )
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="timeout", description="Timeout (mute) a member for a specified duration.")
@app_commands.describe(
    member="Member to timeout",
    duration="Duration (e.g. 10m, 1h, 1d, 7d)",
    reason="Reason for timeout"
)
@app_commands.default_permissions(moderate_members=True)
async def timeout_cmd(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str):
    if member.id == interaction.user.id:
        await interaction.response.send_message("❌ You cannot timeout yourself.", ephemeral=True)
        return
    if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ You cannot timeout a member with an equal or higher role than you.", ephemeral=True)
        return

    td = parse_duration(duration)
    if not td:
        await interaction.response.send_message("❌ Invalid duration format! Use formats like `10m`, `1h`, `12h`, `1d`, or `7d` (Max 28 days).", ephemeral=True)
        return

    dur_str = format_duration(td)
    await interaction.response.defer(ephemeral=False)

    try:
        await member.timeout(td, reason=reason)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to timeout member: {e}", ephemeral=True)
        return

    await send_dm_infraction_notice(member, "Timed Out", reason, interaction.guild.name, duration=dur_str)

    case_id = await dispatch_mod_log(
        bot=bot,
        guild=interaction.guild,
        action="timeout",
        target=member,
        moderator=interaction.user,
        reason=reason,
        duration=dur_str
    )

    embed = discord.Embed(
        title="⏱️ Member Timed Out",
        description=f"Successfully timed out {member.mention} for **{dur_str}**.\n\n**Reason:** {reason}\n**Case:** `#{case_id}`",
        color=0xE67E22
    )
    embed.set_footer(text=f"Audit logged in #{config.MOD_LOGS_CHANNEL_ID}")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="untimeout", description="Remove timeout from a member.")
@app_commands.describe(member="Member to remove timeout from", reason="Reason for removal")
@app_commands.default_permissions(moderate_members=True)
async def untimeout_cmd(interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
    rem_reason = reason or "Timeout removed by moderator"
    await interaction.response.defer(ephemeral=False)

    try:
        await member.timeout(None, reason=rem_reason)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to remove timeout: {e}", ephemeral=True)
        return

    await send_dm_infraction_notice(member, "Untimed Out", rem_reason, interaction.guild.name)

    case_id = await dispatch_mod_log(
        bot=bot,
        guild=interaction.guild,
        action="untimeout",
        target=member,
        moderator=interaction.user,
        reason=rem_reason
    )

    embed = discord.Embed(
        title="🔓 Timeout Removed",
        description=f"Successfully removed timeout for {member.mention}.\n**Case:** `#{case_id}`",
        color=0x57F287
    )
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="kick", description="Kick a member from the server.")
@app_commands.describe(member="Member to kick", reason="Reason for kick")
@app_commands.default_permissions(kick_members=True)
async def kick_cmd(interaction: discord.Interaction, member: discord.Member, reason: str):
    if member.id == interaction.user.id:
        await interaction.response.send_message("❌ You cannot kick yourself.", ephemeral=True)
        return
    if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ You cannot kick a member with an equal or higher role than you.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    await send_dm_infraction_notice(member, "Kicked", reason, interaction.guild.name)

    try:
        await member.kick(reason=reason)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to kick member: {e}", ephemeral=True)
        return

    case_id = await dispatch_mod_log(
        bot=bot,
        guild=interaction.guild,
        action="kick",
        target=member,
        moderator=interaction.user,
        reason=reason
    )

    embed = discord.Embed(
        title="🚪 Member Kicked",
        description=f"Successfully kicked {member.mention} (`{member.name}`).\n\n**Reason:** {reason}\n**Case:** `#{case_id}`",
        color=0xED4245
    )
    embed.set_footer(text=f"Audit logged in #{config.MOD_LOGS_CHANNEL_ID}")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="ban", description="Ban a member or user from the server.")
@app_commands.describe(
    user="User to ban",
    reason="Reason for ban",
    delete_days="Days of messages to delete (0 to 7)"
)
@app_commands.default_permissions(ban_members=True)
async def ban_cmd(interaction: discord.Interaction, user: discord.User, reason: str, delete_days: Optional[int] = 0):
    if user.id == interaction.user.id:
        await interaction.response.send_message("❌ You cannot ban yourself.", ephemeral=True)
        return

    # Check hierarchy if target is member in this guild
    member = interaction.guild.get_member(user.id)
    if member and member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("❌ You cannot ban a member with an equal or higher role than you.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    await send_dm_infraction_notice(user, "Banned", reason, interaction.guild.name)

    days = max(0, min(7, delete_days or 0))
    try:
        await interaction.guild.ban(user, reason=reason, delete_message_days=days)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to ban user: {e}", ephemeral=True)
        return

    case_id = await dispatch_mod_log(
        bot=bot,
        guild=interaction.guild,
        action="ban",
        target=user,
        moderator=interaction.user,
        reason=reason,
        extra_field=("🗑️ Message History", f"Deleted `{days}` day(s) of recent messages.")
    )

    embed = discord.Embed(
        title="🔨 Member Banned",
        description=f"Successfully banned {user.mention} (`{user.name}`).\n\n**Reason:** {reason}\n**Case:** `#{case_id}`",
        color=0x992D22
    )
    embed.set_footer(text=f"Audit logged in #{config.MOD_LOGS_CHANNEL_ID}")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="unban", description="Unban a user by Discord User ID.")
@app_commands.describe(user_id="Discord User ID to unban", reason="Reason for unban")
@app_commands.default_permissions(ban_members=True)
async def unban_cmd(interaction: discord.Interaction, user_id: str, reason: Optional[str] = None):
    try:
        uid = int(user_id.strip())
    except ValueError:
        await interaction.response.send_message("❌ Invalid user ID. Please provide a numeric Discord ID.", ephemeral=True)
        return

    unban_reason = reason or "Unbanned by moderator"
    await interaction.response.defer(ephemeral=False)

    try:
        user_obj = discord.Object(id=uid)
        await interaction.guild.unban(user_obj, reason=unban_reason)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to unban user `{uid}`: {e}", ephemeral=True)
        return

    fetched_user = bot.get_user(uid)
    if not fetched_user:
        try:
            fetched_user = await bot.fetch_user(uid)
        except Exception:
            fetched_user = discord.Object(id=uid)

    case_id = await dispatch_mod_log(
        bot=bot,
        guild=interaction.guild,
        action="unban",
        target=fetched_user,
        moderator=interaction.user,
        reason=unban_reason
    )

    embed = discord.Embed(
        title="🔓 User Unbanned",
        description=f"Successfully revoked ban for `<@{uid}>` (`{uid}`).\n\n**Reason:** {unban_reason}\n**Case:** `#{case_id}`",
        color=0x57F287
    )
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="global-ban", description="[ADMIN] Ban a malicious user across all servers and blacklist permanently.")
@app_commands.describe(user_id="Discord User ID to globally ban", reason="Reason for the network security ban")
@app_commands.default_permissions(administrator=True)
async def global_ban_cmd(interaction: discord.Interaction, user_id: str, reason: str):
    try:
        uid = int(user_id.strip())
    except ValueError:
        await interaction.response.send_message("❌ Invalid user ID. Please provide a numeric Discord ID.", ephemeral=True)
        return

    if uid == interaction.user.id:
        await interaction.response.send_message("❌ You cannot globally ban yourself.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    success_count, failed_guilds, case_id = await execute_global_ban(bot, uid, reason, interaction.user)

    embed = discord.Embed(
        title="🚨 Global Security Ban Enforced",
        description=(
            f"Successfully executed a **Network Global Ban** for user `<@{uid}>` (`{uid}`)!\n\n"
            f"**Enforced Across:** `{success_count} / {len(bot.guilds)}` servers\n"
            f"**Permanent Blacklist:** ✅ **Active** (Auto-banned on join)\n"
            f"**Reason:** {reason}\n"
            f"**Case:** `#{case_id}`"
        ),
        color=0x1F1F1F,
        timestamp=discord.utils.utcnow()
    )
    if failed_guilds:
        embed.add_field(name="⚠️ Failed Servers", value=", ".join(failed_guilds)[:500], inline=False)
    embed.set_footer(text=f"Security Audit Logged in #{config.MOD_LOGS_CHANNEL_ID}")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="global-unban", description="[ADMIN] Revoke a global ban from a user across all servers.")
@app_commands.describe(user_id="Discord User ID to globally unban", reason="Reason for revoking global ban")
@app_commands.default_permissions(administrator=True)
async def global_unban_cmd(interaction: discord.Interaction, user_id: str, reason: Optional[str] = None):
    try:
        uid = int(user_id.strip())
    except ValueError:
        await interaction.response.send_message("❌ Invalid user ID. Please provide a numeric Discord ID.", ephemeral=True)
        return

    unban_reason = reason or "Global ban revoked by server administrator"
    await interaction.response.defer(ephemeral=False)
    success_count, failed_guilds, case_id = await execute_global_unban(bot, uid, unban_reason, interaction.user)

    embed = discord.Embed(
        title="🌐 Global Ban Revoked",
        description=(
            f"Successfully revoked global ban for `<@{uid}>` (`{uid}`).\n\n"
            f"**Unbanned Across:** `{success_count} / {len(bot.guilds)}` servers\n"
            f"**Removed From Blacklist:** ✅ Complete\n"
            f"**Case:** `#{case_id}`"
        ),
        color=0x57F287,
        timestamp=discord.utils.utcnow()
    )
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="global-ban-list", description="[ADMIN] View all permanently blacklisted global ban records.")
@app_commands.default_permissions(administrator=True)
async def global_ban_list_cmd(interaction: discord.Interaction):
    bans = get_all_global_bans()
    if not bans:
        await interaction.response.send_message("ℹ️ No users are currently on the global ban blacklist.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🛡️ Echo Global Security Blacklist",
        description=f"Total blacklisted users: **{len(bans)}**\n*(Any of these users will be auto-banned immediately upon joining.)*",
        color=0x1F1F1F,
        timestamp=discord.utils.utcnow()
    )
    for b in bans[:15]:
        embed.add_field(
            name=f"User ID: `{b['user_id']}`",
            value=f"**Reason:** {b['reason']}\n**Banned By:** `{b['banned_by_name']}` (<@{b['banned_by']}>) • {b['created_at']}",
            inline=False
        )
    if len(bans) > 15:
        embed.set_footer(text=f"Showing 15 of {len(bans)} total blacklisted users")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="mod-case", description="Look up details of a moderation case by ID.")
@app_commands.describe(case_id="Case ID number")
@app_commands.default_permissions(moderate_members=True)
async def mod_case_cmd(interaction: discord.Interaction, case_id: int):
    case = get_mod_case(case_id)
    if not case:
        await interaction.response.send_message(f"❌ Case `#{case_id}` was not found in the records.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"⚖️ Moderation Case #{case['case_id']} • {case['action'].upper()}",
        description=f"Details for moderation infraction `#{case_id}`:",
        color=0x5865F2,
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(name="Target User", value=f"<@{case['target_id']}> (`{case['target_name']}` • `{case['target_id']}`)", inline=True)
    embed.add_field(name="Moderator", value=f"<@{case['moderator_id']}> (`{case['moderator_name']}`)", inline=True)
    embed.add_field(name="Action", value=f"`{case['action']}`", inline=True)
    if case.get("duration"):
        embed.add_field(name="Duration", value=f"`{case['duration']}`", inline=True)
    embed.add_field(name="Reason", value=f"> {case['reason']}", inline=False)
    embed.add_field(name="Timestamp", value=f"`{case['created_at']}`", inline=True)
    if case.get("log_message_id"):
        embed.add_field(name="Log Message ID", value=f"`{case['log_message_id']}`", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="slowmode", description="Set slowmode delay for a channel (0 to disable).")
@app_commands.describe(
    seconds="Slowmode duration in seconds (0 to 21600)",
    channel="Channel to configure (defaults to current channel)"
)
@app_commands.default_permissions(manage_channels=True)
async def slowmode_cmd(interaction: discord.Interaction, seconds: int, channel: Optional[discord.TextChannel] = None):
    target_ch = channel or interaction.channel
    if not isinstance(target_ch, discord.TextChannel):
        await interaction.response.send_message("❌ Slowmode can only be configured in text channels.", ephemeral=True)
        return

    sec = max(0, min(21600, seconds))
    await target_ch.edit(slowmode_delay=sec)

    case_id = await dispatch_mod_log(
        bot=bot,
        guild=interaction.guild,
        action="slowmode",
        target=interaction.user,
        moderator=interaction.user,
        reason=f"Configured slowmode to {sec}s in #{target_ch.name}",
        duration=f"{sec}s"
    )

    msg = f"⏲️ Slowmode disabled in {target_ch.mention}." if sec == 0 else f"⏲️ Slowmode set to **{sec} seconds** in {target_ch.mention}."
    await interaction.response.send_message(f"✅ {msg} (Case `#{case_id}`)", ephemeral=True)

@bot.tree.command(name="lock", description="Lock a channel to prevent regular members from sending messages.")
@app_commands.describe(
    channel="Channel to lock (defaults to current channel)",
    reason="Optional reason for the lockdown"
)
@app_commands.default_permissions(manage_channels=True)
async def lock_cmd(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None, reason: Optional[str] = None):
    target_ch = channel or interaction.channel
    if not isinstance(target_ch, discord.TextChannel):
        await interaction.response.send_message("❌ Only text channels can be locked.", ephemeral=True)
        return

    lock_reason = reason or "Channel locked by staff."
    await target_ch.set_permissions(interaction.guild.default_role, send_messages=False, reason=lock_reason)

    lock_embed = discord.Embed(
        title="🔒 Channel Locked",
        description=f"This channel has been temporarily locked by staff.\n\n**Reason:** {lock_reason}",
        color=0xED4245
    )
    await target_ch.send(embed=lock_embed)

    case_id = await dispatch_mod_log(
        bot=bot,
        guild=interaction.guild,
        action="lock",
        target=interaction.user,
        moderator=interaction.user,
        reason=lock_reason,
        extra_field=("Channel", target_ch.mention)
    )
    await interaction.response.send_message(f"🔒 {target_ch.mention} has been locked. (Case `#{case_id}`)", ephemeral=True)

@bot.tree.command(name="unlock", description="Unlock a previously locked channel.")
@app_commands.describe(channel="Channel to unlock (defaults to current channel)")
@app_commands.default_permissions(manage_channels=True)
async def unlock_cmd(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    target_ch = channel or interaction.channel
    if not isinstance(target_ch, discord.TextChannel):
        await interaction.response.send_message("❌ Only text channels can be unlocked.", ephemeral=True)
        return

    await target_ch.set_permissions(interaction.guild.default_role, send_messages=None, reason="Channel unlocked by staff.")

    unlock_embed = discord.Embed(
        title="🔓 Channel Unlocked",
        description="This channel has been unlocked. Members may resume chatting!",
        color=0x57F287
    )
    await target_ch.send(embed=unlock_embed)

    case_id = await dispatch_mod_log(
        bot=bot,
        guild=interaction.guild,
        action="unlock",
        target=interaction.user,
        moderator=interaction.user,
        reason="Channel lockdown lifted",
        extra_field=("Channel", target_ch.mention)
    )
    await interaction.response.send_message(f"🔓 {target_ch.mention} has been unlocked. (Case `#{case_id}`)", ephemeral=True)

@bot.tree.command(name="purge", description="Bulk delete messages in the current channel.")
@app_commands.describe(
    amount="Number of messages to delete (1-100)",
    member="Only delete messages sent by this member",
    contains="Only delete messages containing this phrase"
)
@app_commands.default_permissions(manage_messages=True)
async def purge_cmd(
    interaction: discord.Interaction,
    amount: int,
    member: Optional[discord.Member] = None,
    contains: Optional[str] = None
):
    if amount < 1 or amount > 100:
        await interaction.response.send_message("❌ Amount must be between 1 and 100.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    def check_msg(m: discord.Message) -> bool:
        if member and m.author.id != member.id:
            return False
        if contains and contains.lower() not in m.content.lower():
            return False
        return True

    try:
        deleted = await interaction.channel.purge(limit=amount, check=check_msg)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to purge messages: {e}", ephemeral=True)
        return

    filters = []
    if member:
        filters.append(f"from {member.mention}")
    if contains:
        filters.append(f'containing "{contains}"')
    filter_str = f" ({', '.join(filters)})" if filters else ""

    case_id = await dispatch_mod_log(
        bot=bot,
        guild=interaction.guild,
        action="purge",
        target=member or interaction.user,
        moderator=interaction.user,
        reason=f"Bulk deleted {len(deleted)} messages in #{interaction.channel.name}{filter_str}",
        extra_field=("🧹 Summary", f"Deleted `{len(deleted)}` messages in {interaction.channel.mention}.")
    )

    await interaction.followup.send(f"🧹 Successfully deleted **{len(deleted)}** message(s){filter_str}. (Case `#{case_id}`)", ephemeral=True)


# ==========================================
# 🤝 OFFICIAL PARTNERSHIP & AFFILIATES SYSTEM
# ==========================================

partner_group = app_commands.Group(name="partner", description="Manage official community partnerships & affiliates")

@partner_group.command(name="post", description="Post a detailed affiliate partnership to #our-affiliates.")
@app_commands.describe(
    name="Partner / Server / Studio name",
    invite_url="Discord invite URL or Roblox group link",
    description="Detailed description, perks, and about the partner",
    category="Partner category",
    representative="Optional partner representative / ambassador",
    banner_url="Optional banner image URL"
)
@app_commands.choices(category=[
    app_commands.Choice(name="🛠️ Roblox Game Studio", value="Roblox Game Studio"),
    app_commands.Choice(name="🎨 Asset Store & Marketplace", value="Asset Store & Marketplace"),
    app_commands.Choice(name="💻 Luau Scripting & Systems", value="Luau Scripting & Systems"),
    app_commands.Choice(name="👕 Roblox Clothing & UGC", value="Roblox Clothing & UGC"),
    app_commands.Choice(name="👥 Gaming & Community Hub", value="Gaming & Community Hub"),
    app_commands.Choice(name="⚙️ Services & Technology", value="Services & Technology"),
    app_commands.Choice(name="🤝 General Affiliate Partner", value="General Affiliate Partner")
])
@app_commands.default_permissions(manage_guild=True)
async def partner_post_cmd(
    interaction: discord.Interaction,
    name: str,
    invite_url: str,
    description: str,
    category: str = "General Affiliate Partner",
    representative: Optional[discord.Member] = None,
    banner_url: Optional[str] = None
):
    await interaction.response.defer(ephemeral=False)

    success, msg, pid = await publish_affiliate_partnership(
        bot=bot,
        guild=interaction.guild,
        name=name.strip(),
        invite_url=invite_url.strip(),
        description=description.strip(),
        category=category,
        representative=representative,
        banner_url=banner_url.strip() if banner_url else None,
        added_by=interaction.user.id
    )

    if success:
        embed = discord.Embed(
            title="🎉 Partnership Successfully Published!",
            description=(
                f"**Partner:** **{name}** (Partner `#{pid}`)\n"
                f"**Category:** `{category}`\n"
                f"**Channel:** <#{config.AFFILIATES_CHANNEL_ID}>\n"
                + (f"**Ambassador:** {representative.mention}\n" if representative else "")
                + f"\n{msg}"
            ),
            color=0x57F287,
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text="Echo Technologies Official Affiliates")
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send(msg, ephemeral=True)

@partner_group.command(name="list", description="List all active community partnerships.")
@app_commands.default_permissions(manage_guild=True)
async def partner_list_cmd(interaction: discord.Interaction):
    partners = get_all_partnerships()
    if not partners:
        await interaction.response.send_message("ℹ️ No active partnerships recorded yet. Use `/partner post` to publish one!", ephemeral=True)
        return

    embed = discord.Embed(
        title="🤝 Echo Technologies • Active Affiliates",
        description=f"Currently showcasing **{len(partners)}** official affiliate partner(s):",
        color=0x5865F2,
        timestamp=discord.utils.utcnow()
    )
    for p in partners[:15]:
        th_link = f"<#{p['thread_id']}>" if p.get("thread_id") else "*Posted*"
        rep_str = f" • Rep: <@{p['representative_id']}>" if p.get("representative_id") else ""
        embed.add_field(
            name=f"#{p['id']} • {p['name']}",
            value=f"**Category:** `{p['category']}`\n**Link:** [Visit Partner]({p['invite_url']})\n**Forum Thread:** {th_link}{rep_str}",
            inline=False
        )
    embed.set_footer(text=f"Total: {len(partners)} partners • Affiliates Channel: #{config.AFFILIATES_CHANNEL_ID}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@partner_group.command(name="remove", description="Remove an affiliate partnership and delete its forum thread.")
@app_commands.describe(partner_id="Partnership ID number to remove")
@app_commands.default_permissions(manage_guild=True)
async def partner_remove_cmd(interaction: discord.Interaction, partner_id: int):
    await interaction.response.defer(ephemeral=False)
    success, msg = await remove_affiliate_partnership(bot, partner_id)
    if success:
        await interaction.followup.send(msg)
    else:
        await interaction.followup.send(msg, ephemeral=True)

@partner_group.command(name="update", description="Update an existing partnership's info and live post.")
@app_commands.describe(
    partner_id="ID of the partnership to update",
    name="Updated partner name",
    invite_url="Updated invite URL",
    description="Updated description",
    category="Updated category",
    representative="Updated partner representative / ambassador",
    roblox_group_url="Updated Roblox group link",
    banner_url="Updated banner image URL"
)
@app_commands.choices(category=[
    app_commands.Choice(name="🛠️ Roblox Game Studio", value="Roblox Game Studio"),
    app_commands.Choice(name="🎨 Asset Store & Marketplace", value="Asset Store & Marketplace"),
    app_commands.Choice(name="💻 Luau Scripting & Systems", value="Luau Scripting & Systems"),
    app_commands.Choice(name="👕 Roblox Clothing & UGC", value="Roblox Clothing & UGC"),
    app_commands.Choice(name="👥 Gaming & Community Hub", value="Gaming & Community Hub"),
    app_commands.Choice(name="⚙️ Services & Technology", value="Services & Technology"),
    app_commands.Choice(name="🤝 General Affiliate Partner", value="General Affiliate Partner")
])
@app_commands.default_permissions(manage_guild=True)
async def partner_update_cmd(
    interaction: discord.Interaction,
    partner_id: int,
    name: Optional[str] = None,
    invite_url: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[str] = None,
    representative: Optional[discord.Member] = None,
    roblox_group_url: Optional[str] = None,
    banner_url: Optional[str] = None
):
    await interaction.response.defer(ephemeral=False)
    success, msg = await update_affiliate_partnership(
        bot=bot,
        guild=interaction.guild,
        partner_id=partner_id,
        name=name,
        invite_url=invite_url,
        description=description,
        category=category,
        representative=representative,
        roblox_group_url=roblox_group_url,
        banner_url=banner_url
    )
    if success:
        await interaction.followup.send(msg)
    else:
        await interaction.followup.send(msg, ephemeral=True)

@partner_group.command(name="ad", description="Get Echo Technologies' official partnership advertisement copy.")
async def partner_ad_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"📋 **Echo Technologies Official Partnership Ad Copy**\n```markdown\n{ECHO_AD_COPY}\n```",
        ephemeral=True
    )

@partner_group.command(name="post-portal", description="Post the self-service Partnership Application Portal in current channel.")
@app_commands.default_permissions(manage_guild=True)
async def partner_post_portal_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤝 Echo Technologies • Official Partnership Portal",
        description=(
            "Welcome to the **Echo Technologies Partnership & Affiliates Hub**!\n\n"
            "We collaborate with high-quality Roblox game studios, software developers, clothing brands, "
            "and active gaming communities.\n\n"
            "**Partner Benefits:**\n"
            "• 📢 Instant `@here` Ping & Dedicated Showcase Thread in `#our-affiliates`\n"
            "• 👑 `@Partner Representative` Discord Role & VIP Perks\n"
            "• 🪙 +3 Community Points reward for PR team members\n\n"
            "**Requirements:**\n"
            "• Minimum 50+ active Discord members or Roblox group members\n"
            "• Safe community, 7+ day old representative account, & no scam history\n"
            "• Proof of posting Echo Technologies' advertisement in your server\n\n"
            "Click **Apply for Partnership** below to submit your application!"
        ),
        color=0x5865F2
    )
    embed.set_footer(text="Echo Technologies • Self-Service Partner Network")
    view = PartnerPortalView(bot)
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ Partnership portal panel posted successfully!", ephemeral=True)

@partner_group.command(name="directory", description="View the interactive affiliate directory.")
async def partner_directory_cmd(interaction: discord.Interaction):
    partners = get_all_partnerships()
    if not partners:
        await interaction.response.send_message("ℹ️ No active affiliate partners found.", ephemeral=True)
        return
    embed = discord.Embed(
        title="🌐 Echo Technologies • Official Affiliates Directory",
        description="Select a partner from the dropdown menu below to view full details, perks, and invite links.",
        color=0x5865F2
    )
    view = PartnerDirectoryView(partners)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@partner_group.command(name="check-health", description="Run an instant health check on all affiliate invite links.")
@app_commands.default_permissions(manage_guild=True)
async def partner_check_health_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await check_partner_health(bot)
    await interaction.followup.send("✅ Partner health check complete. Any dead or invalid invite links have been logged to `#mod-logs`.", ephemeral=True)

@partner_group.command(name="pr-stats", description="View PR staff member partnership leaderboard & stats.")
@app_commands.default_permissions(manage_guild=True)
async def partner_pr_stats_cmd(interaction: discord.Interaction):
    partners = get_all_partnerships()
    stats = {}
    for p in partners:
        added_by = p.get("added_by")
        if added_by:
            stats[added_by] = stats.get(added_by, 0) + 1

    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    embed = discord.Embed(
        title="📊 Echo Technologies • PR Staff Partnership Stats",
        description="Top PR representatives by published affiliate partnerships:",
        color=0xFEE75C
    )
    if not sorted_stats:
        embed.description = "No partnership additions recorded yet."
    else:
        for idx, (uid, count) in enumerate(sorted_stats[:10], 1):
            embed.add_field(
                name=f"#{idx} • User ID: {uid}",
                value=f"**Partnerships:** `{count}` | **Points Earned:** `{count * 3}` pts",
                inline=False
            )
    await interaction.response.send_message(embed=embed, ephemeral=True)

bot.tree.add_command(partner_group)

@bot.tree.command(name="our-ad", description="Copy Echo Technologies' official partnership advertisement.")
async def our_ad_top_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"📋 **Echo Technologies Official Partnership Ad Copy**\n```markdown\n{ECHO_AD_COPY}\n```",
        ephemeral=True
    )


# ==========================================
# 🪙 COMMUNITY POINTS & BLACKLIST SYSTEM REWARDS
# ==========================================

points_group = app_commands.Group(name="points", description="Community Points & Blacklist System rewards")

@points_group.command(name="check", description="View your community points balance or another member's points.")
@app_commands.describe(member="Member to inspect (defaults to yourself)")
async def points_check_cmd(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target = member or interaction.user
    pts = get_user_points(target.id)
    balance = pts["points"]
    total = pts["total_earned"]
    has_claimed = bool(pts.get("has_claimed_reward", 0))

    embed = discord.Embed(
        title=f"⭐ Community Points • {target.display_name}",
        description=(
            f"Community points are awarded automatically by AI when you provide helpful answers, "
            f"creative ideas, and constructive feedback in chat!\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 **Current Balance:** `{balance} Points`\n"
            f"📈 **Total Earned:** `{total} Points`\n"
            f"🎯 **Blacklist System Goal:** {render_progress_bar(balance, 5)}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0xFEE75C,
        timestamp=discord.utils.utcnow()
    )
    if hasattr(target, "display_avatar") and target.display_avatar:
        embed.set_thumbnail(url=target.display_avatar.url)

    if has_claimed:
        embed.add_field(
            name="🎁 Echo Blacklist System (100 Robux)",
            value="✅ **CLAIMED!** You have claimed your free server-authoritative blacklist system.",
            inline=False
        )
        await interaction.response.send_message(embed=embed)
    elif balance >= 5:
        embed.add_field(
            name="🎁 Echo Blacklist System (100 Robux)",
            value=(
                "🎉 **REWARD UNLOCKED & READY TO CLAIM!**\n"
                "Please open a General Support ticket in <#1556000081877147771> (`#ticket-center`) "
                "to receive your free product files from staff!"
            ),
            inline=False
        )
        view = discord.ui.View(timeout=None)
        view.add_item(
            discord.ui.Button(
                label="Open Ticket to Claim Free Product",
                url="https://discord.com/channels/1555641543480713226/1556000081877147771",
                emoji="🎫",
                style=discord.ButtonStyle.link
            )
        )
        await interaction.response.send_message(embed=embed, view=view)
    else:
        remaining = 5 - balance
        embed.add_field(
            name="🎁 Echo Blacklist System (100 Robux)",
            value=(
                f"🔒 **Locked** — Need **`{remaining}` more point{'s' if remaining > 1 else ''}** to get it for **100% FREE**!\n"
                f"Help fellow developers with scripting, UI, or feedback to earn points automatically!"
            ),
            inline=False
        )
        await interaction.response.send_message(embed=embed)

@points_group.command(name="leaderboard", description="View the top community points leaderboard.")
@app_commands.describe(limit="Number of members to display (default: 10, max: 25)")
async def points_leaderboard_cmd(interaction: discord.Interaction, limit: int = 10):
    limit = max(1, min(25, limit))
    leaders = get_points_leaderboard(limit=limit)

    embed = discord.Embed(
        title="🏆 Echo Technologies • Points Leaderboard",
        description="Top contributors earning points through helpful discussions & community support!\n",
        color=0xFEE75C,
        timestamp=discord.utils.utcnow()
    )

    if not leaders:
        embed.description += "\n*No community points awarded yet. Start chatting and helping others to earn points!*"
    else:
        medals = ["🥇", "🥈", "🥉"]
        for idx, row in enumerate(leaders, start=1):
            badge = medals[idx - 1] if idx <= 3 else f"`#{idx}`"
            u_id = row["user_id"]
            pts = row["points"]
            tot = row["total_earned"]
            claimed = " • 🎁 *Claimed*" if row.get("has_claimed_reward") else (" • 🌟 *Ready to Claim!*" if pts >= 5 else "")
            embed.add_field(
                name=f"{badge} Member <@{u_id}>",
                value=f"**{pts} Points** (Total Earned: `{tot}`){claimed}",
                inline=False
            )

    embed.set_footer(text="Reach 5 points to claim Echo Blacklist System (100 Robux) for free!")
    await interaction.response.send_message(embed=embed)

@points_group.command(name="add", description="[STAFF] Award community points to a member.")
@app_commands.describe(
    member="Target member to receive points",
    amount="Number of points to grant (default: 1)",
    reason="Official reason for awarding points"
)
@app_commands.default_permissions(manage_messages=True)
async def points_add_cmd(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: int = 1,
    reason: str = "Staff reward for positive contribution"
):
    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be at least 1 point.", ephemeral=True)
        return

    new_total, unlocked_reward = add_points(
        user_id=member.id,
        amount=amount,
        source="staff_add",
        reason=reason,
        moderator_id=interaction.user.id
    )

    embed = discord.Embed(
        title="⭐ Community Points Added",
        description=(
            f"Successfully awarded **+{amount} Point(s)** to {member.mention}!\n\n"
            f"• **New Balance:** `{new_total} Points`\n"
            f"• **Progress:** {render_progress_bar(new_total, 5)}\n"
            f"• **Reason:** *{reason}*\n"
            f"• **Issued By:** {interaction.user.mention}"
        ),
        color=0x57F287,
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text="Echo Technologies Points Management")
    await interaction.response.send_message(embed=embed)

    if unlocked_reward:
        reward_embed, reward_view = build_reward_unlocked_embed(member)
        try:
            await interaction.channel.send(
                content=f"🎉 {member.mention} **REWARD UNLOCKED!**",
                embed=reward_embed,
                view=reward_view
            )
        except Exception:
            pass

        try:
            dm = await member.create_dm()
            await dm.send(embed=reward_embed, view=reward_view)
        except Exception:
            pass

@points_group.command(name="remove", description="[STAFF] Deduct community points from a member.")
@app_commands.describe(
    member="Target member to deduct points from",
    amount="Number of points to deduct (default: 1)",
    reason="Official reason for deducting points"
)
@app_commands.default_permissions(manage_messages=True)
async def points_remove_cmd(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: int = 1,
    reason: str = "Deducted by staff"
):
    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be at least 1 point.", ephemeral=True)
        return

    new_total = remove_points(
        user_id=member.id,
        amount=amount,
        source="staff_remove",
        reason=reason,
        moderator_id=interaction.user.id
    )

    embed = discord.Embed(
        title="🔻 Community Points Deducted",
        description=(
            f"Deducted **-{amount} Point(s)** from {member.mention}.\n\n"
            f"• **New Balance:** `{new_total} Points`\n"
            f"• **Progress:** {render_progress_bar(new_total, 5)}\n"
            f"• **Reason:** *{reason}*\n"
            f"• **Actioned By:** {interaction.user.mention}"
        ),
        color=0xED4245,
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text="Echo Technologies Points Management")
    await interaction.response.send_message(embed=embed)

@points_group.command(name="set", description="[STAFF] Set a member's community points balance directly.")
@app_commands.describe(
    member="Target member whose points will be set",
    amount="Exact new points balance (0 or greater)",
    reason="Reason for adjusting points balance"
)
@app_commands.default_permissions(manage_messages=True)
async def points_set_cmd(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: int,
    reason: str = "Points balance set by staff"
):
    if amount < 0:
        await interaction.response.send_message("❌ Amount cannot be negative.", ephemeral=True)
        return

    new_total, unlocked_reward = set_points(
        user_id=member.id,
        amount=amount,
        reason=reason,
        moderator_id=interaction.user.id
    )

    embed = discord.Embed(
        title="⚙️ Community Points Updated",
        description=(
            f"Set points for {member.mention} to **{new_total} Point(s)**.\n\n"
            f"• **Progress:** {render_progress_bar(new_total, 5)}\n"
            f"• **Reason:** *{reason}*\n"
            f"• **Updated By:** {interaction.user.mention}"
        ),
        color=0x5865F2,
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text="Echo Technologies Points Management")
    await interaction.response.send_message(embed=embed)

    if unlocked_reward:
        reward_embed, reward_view = build_reward_unlocked_embed(member)
        try:
            await interaction.channel.send(
                content=f"🎉 {member.mention} **REWARD UNLOCKED!**",
                embed=reward_embed,
                view=reward_view
            )
        except Exception:
            pass

        try:
            dm = await member.create_dm()
            await dm.send(embed=reward_embed, view=reward_view)
        except Exception:
            pass

@points_group.command(name="claim", description="[STAFF] Mark that a member has claimed their free Echo Blacklist System.")
@app_commands.describe(
    member="Member who claimed their reward",
    claimed="Mark as Claimed (True) or Unclaimed (False)"
)
@app_commands.default_permissions(manage_messages=True)
async def points_claim_cmd(interaction: discord.Interaction, member: discord.Member, claimed: bool = True):
    mark_reward_claimed(member.id, claimed)
    status_str = "CLAIMED ✅" if claimed else "UNCLAIMED ⏳"
    embed = discord.Embed(
        title="🎁 Reward Claim Status Updated",
        description=(
            f"Echo Blacklist System reward status for {member.mention} is now marked as **{status_str}**.\n\n"
            f"• **Actioned By:** {interaction.user.mention}"
        ),
        color=0x57F287 if claimed else 0xFEE75C,
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text="Echo Technologies Community Rewards")
    await interaction.response.send_message(embed=embed)

bot.tree.add_command(points_group)

@bot.tree.command(name="mypoints", description="Quick check of your community points and reward progress.")
async def mypoints_cmd(interaction: discord.Interaction):
    pts = get_user_points(interaction.user.id)
    balance = pts["points"]
    total = pts["total_earned"]
    has_claimed = bool(pts.get("has_claimed_reward", 0))

    embed = discord.Embed(
        title=f"⭐ Your Community Points • {interaction.user.display_name}",
        description=(
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 **Current Balance:** `{balance} Points`\n"
            f"📈 **Total Earned:** `{total} Points`\n"
            f"🎯 **Blacklist System Goal:** {render_progress_bar(balance, 5)}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0xFEE75C,
        timestamp=discord.utils.utcnow()
    )
    if hasattr(interaction.user, "display_avatar") and interaction.user.display_avatar:
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

    if has_claimed:
        embed.add_field(
            name="🎁 Echo Blacklist System (100 Robux)",
            value="✅ **CLAIMED!** You received your free server-authoritative blacklist system.",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    elif balance >= 5:
        embed.add_field(
            name="🎁 Echo Blacklist System (100 Robux)",
            value=(
                "🎉 **REWARD UNLOCKED & READY TO CLAIM!**\n"
                "Please open a General Support ticket in <#1556000081877147771> (`#ticket-center`) "
                "to receive your free product files from staff!"
            ),
            inline=False
        )
        view = discord.ui.View(timeout=None)
        view.add_item(
            discord.ui.Button(
                label="Open Ticket to Claim Free Product",
                url="https://discord.com/channels/1555641543480713226/1556000081877147771",
                emoji="🎫",
                style=discord.ButtonStyle.link
            )
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    else:
        remaining = 5 - balance
        embed.add_field(
            name="🎁 Echo Blacklist System (100 Robux)",
            value=(
                f"🔒 **Locked** — Need **`{remaining}` more point{'s' if remaining > 1 else ''}** to get it for **100% FREE**!\n"
                f"Help fellow developers with scripting, UI, or feedback to earn points automatically!"
            ),
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@points_group.command(name="shop", description="Browse and redeem exclusive rewards in the Community Rewards Shop.")
async def points_shop_cmd(interaction: discord.Interaction):
    pts = get_user_points(interaction.user.id)
    embed = build_shop_embed(interaction.user, pts)
    view = PointsShopView(pts["points"])
    await interaction.response.send_message(embed=embed, view=view)

@points_group.command(name="redeem", description="Redeem a specific reward from the shop with your points.")
@app_commands.describe(reward="The reward to redeem from the catalogue")
@app_commands.choices(reward=[
    app_commands.Choice(name="🌟 Community Contributor Role (3 Pts)", value="role_contributor"),
    app_commands.Choice(name="🛡️ Echo Blacklist System - Free Milestone (5 Pts)", value="blacklist_system"),
    app_commands.Choice(name="🎟️ 50% Off Any Asset Store Coupon (8 Pts)", value="coupon_discount"),
    app_commands.Choice(name="💻 Premium Luau Script Asset Pack (10 Pts)", value="script_pack"),
    app_commands.Choice(name="👑 Echo Elite Role & Beta Access (15 Pts)", value="role_elite")
])
async def points_redeem_cmd(interaction: discord.Interaction, reward: str):
    success, message, data = await redeem_reward(
        user_id=interaction.user.id,
        reward_id=reward,
        guild=interaction.guild,
        member=interaction.user if isinstance(interaction.user, discord.Member) else None
    )
    if success:
        embed = discord.Embed(
            title="🎉 Reward Redeemed Successfully!",
            description=message,
            color=0x57F287,
            timestamp=discord.utils.utcnow()
        )
        if data and data.get("coupon_code"):
            embed.add_field(
                name="🎟️ Your Coupon Code",
                value=f"```\n{data['coupon_code']}\n```\n*(Present this code in a support ticket or at checkout!)*",
                inline=False
            )
        pts = get_user_points(interaction.user.id)
        embed.set_footer(text=f"Updated Balance: {pts['points']} Points • Echo Technologies")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ {message}", ephemeral=True)

@points_group.command(name="tip", description="Tip Community Points to a fellow member who helped you.")
@app_commands.describe(
    member="The member you want to tip",
    amount="Number of points to tip (minimum 1)",
    note="A thank-you note or reason for the tip"
)
async def points_tip_cmd(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: int = 1,
    note: str = "Thank you for the help!"
):
    if member.bot:
        await interaction.response.send_message("❌ You cannot tip bot accounts.", ephemeral=True)
        return
    if member.id == interaction.user.id:
        await interaction.response.send_message("❌ You cannot tip points to yourself.", ephemeral=True)
        return
    if amount <= 0:
        await interaction.response.send_message("❌ Tip amount must be at least 1 point.", ephemeral=True)
        return

    success, msg, tipper_new, recipient_new, recipient_unlocked = tip_points(
        tipper_id=interaction.user.id,
        recipient_id=member.id,
        amount=amount,
        note=note
    )

    if not success:
        await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
        return

    tip_embed = build_tip_embed(interaction.user, member, amount, note, recipient_new)
    await interaction.response.send_message(embed=tip_embed)

    # If recipient unlocked the 5-point milestone through this tip:
    if recipient_unlocked:
        reward_embed, reward_view = build_reward_unlocked_embed(member)
        try:
            await interaction.channel.send(
                content=f"🎉 {member.mention} **REWARD MILESTONE UNLOCKED!**",
                embed=reward_embed,
                view=reward_view
            )
        except Exception:
            pass

        try:
            dm = await member.create_dm()
            await dm.send(embed=reward_embed, view=reward_view)
        except Exception:
            pass

@points_group.command(name="history", description="View your recent points transactions, tips, and redemptions.")
@app_commands.describe(member="Member whose history to view (defaults to yourself)")
async def points_history_cmd(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target = member or interaction.user
    with sqlite3.connect("verifications.db") as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM point_transactions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 8;
        """, (target.id,))
        txs = [dict(r) for r in cursor.fetchall()]

    embed = discord.Embed(
        title=f"📜 Points History • {target.display_name}",
        color=0xFEE75C,
        timestamp=discord.utils.utcnow()
    )

    if not txs:
        embed.description = "*No transactions found for this account yet. Chat constructively to earn points!*"
    else:
        lines = []
        for t in txs:
            prefix = "+" if t["amount"] > 0 else ""
            amt_str = f"**{prefix}{t['amount']} pts**" if t["amount"] != 0 else "**0 pts (Claim)**"
            date_str = t["created_at"].split()[0] if t["created_at"] else "Recently"
            lines.append(f"• `{date_str}` — {amt_str} | *{t['reason']}*")
        embed.description = "\n".join(lines)

    pts = get_user_points(target.id)
    embed.set_footer(text=f"Current Balance: {pts['points']} Points • Total Earned: {pts['total_earned']}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="tip", description="Tip Community Points to a fellow server member who helped you.")
@app_commands.describe(
    member="The member you want to tip",
    amount="Number of points to tip (minimum 1)",
    note="A thank-you note or reason for the tip"
)
async def top_level_tip_cmd(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: int = 1,
    note: str = "Thank you for the help!"
):
    await points_tip_cmd.callback(interaction, member, amount, note)

@bot.tree.command(name="shop", description="Browse and redeem exclusive rewards in the Community Points Shop.")
async def top_level_shop_cmd(interaction: discord.Interaction):
    await points_shop_cmd.callback(interaction)


# ==========================================
# 🚨 SUPERVISOR & SUPPORT TEMPLATES COMMANDS
# ==========================================

@bot.tree.command(name="supervisor-request", description="Request emergency supervisor & foundership escalation for your ticket.")
@app_commands.describe(reason="Reason for requesting supervisor assistance")
async def supervisor_request_cmd(interaction: discord.Interaction, reason: Optional[str] = "Requesting Foundership / Supervisor Assistance"):
    await interaction.response.defer(ephemeral=False)
    ticket = bot.ticket_manager.get_ticket_by_channel(interaction.channel_id)
    if not ticket:
        await interaction.followup.send("❌ This command must be used inside an active support ticket channel.", ephemeral=True)
        return

    # Escalate ticket & disable AI
    bot.ticket_manager.escalate_ticket(ticket["id"], reason=reason)
    bot.ticket_manager.set_ai_enabled(ticket["id"], False)

    await bot.handle_escalation(
        ticket=ticket,
        channel=interaction.channel,
        reason=f"🚨 Supervisor Requested by {interaction.user.mention}: {reason}"
    )
    await interaction.followup.send(
        f"🚨 **Supervisor Request Dispatched!** <@&{config.FOUNDERSHIP_ROLE_ID}> has been pinged and notified.",
        ephemeral=False
    )

support_template_group = app_commands.Group(name="support-template", description="Manage official support team templates and SOPs.")

@support_template_group.command(name="add", description="Add a new custom support template & SOP.")
@app_commands.describe(
    shortcut="Unique shortcut name (e.g. refund_policy)",
    category="Category name (e.g. Billing, Verification)",
    title="Template Title",
    template_text="The text of the template sent to members (use {user} for mention)",
    steps="Standard operating procedures / staff instructions"
)
async def tpl_add_cmd(
    interaction: discord.Interaction,
    shortcut: str,
    category: str,
    title: str,
    template_text: str,
    steps: Optional[str] = ""
):
    await interaction.response.defer(ephemeral=True)
    from support_templates_system import add_custom_template
    success, msg = add_custom_template(
        shortcut=shortcut,
        category=category,
        title=title,
        template_text=template_text,
        steps=steps or "Custom staff template.",
        created_by=interaction.user.id
    )
    if success:
        embed = discord.Embed(
            title="✅ Custom Template Added",
            description=f"**Shortcut:** `{shortcut}`\n**Title:** {title}\n**Category:** {category}\n\n**Template:**\n```\n{template_text}\n```",
            color=0x57F287
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.followup.send(f"❌ {msg}", ephemeral=True)

@support_template_group.command(name="remove", description="Remove a custom support template by shortcut.")
@app_commands.describe(shortcut="Shortcut name of custom template to remove")
async def tpl_remove_cmd(interaction: discord.Interaction, shortcut: str):
    await interaction.response.defer(ephemeral=True)
    from support_templates_system import delete_custom_template
    success, msg = delete_custom_template(shortcut)
    if success:
        await interaction.followup.send(f"✅ Removed custom template `{shortcut}`.", ephemeral=True)
    else:
        await interaction.followup.send(f"❌ {msg}", ephemeral=True)

@support_template_group.command(name="list", description="List all built-in and custom support templates.")
async def tpl_list_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    from support_templates_system import get_combined_template_list
    tpls = get_combined_template_list()
    embed = discord.Embed(
        title="📚 Echo Support Templates Directory",
        description=f"Total Templates Available: **{len(tpls)}**\n\n",
        color=0x5865F2
    )
    for t in tpls[:25]:
        embed.add_field(
            name=f"{t.get('emoji', '💬')} {t['title']} (`{t['shortcut']}`)",
            value=f"**Cat:** {t.get('category', 'General')}\n{t['template'][:100]}...",
            inline=False
        )
    await interaction.followup.send(embed=embed, ephemeral=True)

bot.tree.add_command(support_template_group)

@bot.tree.command(name="setup-templates-channel", description="Initialize or refresh the #support-templates channel guide & status widget.")
async def setup_templates_channel_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    success = await sync_support_templates_channel(bot, channel=interaction.channel)
    if success:
        await interaction.followup.send("✅ Support templates guide & Roblox API status widget successfully synchronized in this channel!", ephemeral=True)
    else:
        await interaction.followup.send("❌ Failed to synchronize support templates channel.", ephemeral=True)


supervisor_template_group = app_commands.Group(name="supervisor-template", description="Manage official supervisor & executive HR templates.")

@supervisor_template_group.command(name="add", description="Add a new custom supervisor/executive template & SOP.")
@app_commands.describe(
    shortcut="Unique shortcut name (e.g. exec_notice)",
    category="Category name (e.g. Disciplinary, Leadership)",
    title="Template Title",
    template_text="The formal text of the template sent to members (use {user} for mention)",
    steps="Standard operating procedures / supervisor instructions"
)
async def exec_tpl_add_cmd(
    interaction: discord.Interaction,
    shortcut: str,
    category: str,
    title: str,
    template_text: str,
    steps: Optional[str] = ""
):
    await interaction.response.defer(ephemeral=True)
    from supervisor_templates_system import add_custom_supervisor_template
    success, msg = add_custom_supervisor_template(
        shortcut=shortcut,
        category=category,
        title=title,
        template_text=template_text,
        steps=steps or "Custom executive supervisor template.",
        created_by=interaction.user.id
    )
    if success:
        embed = discord.Embed(
            title="✅ Custom Supervisor Template Added",
            description=f"**Shortcut:** `{shortcut}`\n**Title:** {title}\n**Category:** {category}\n\n**Template:**\n```\n{template_text}\n```",
            color=0x9B59B6
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.followup.send(f"❌ {msg}", ephemeral=True)

@supervisor_template_group.command(name="remove", description="Remove a custom supervisor template by shortcut.")
@app_commands.describe(shortcut="Shortcut name of custom supervisor template to remove")
async def exec_tpl_remove_cmd(interaction: discord.Interaction, shortcut: str):
    await interaction.response.defer(ephemeral=True)
    from supervisor_templates_system import delete_custom_supervisor_template
    success, msg = delete_custom_supervisor_template(shortcut)
    if success:
        await interaction.followup.send(f"✅ Removed custom supervisor template `{shortcut}`.", ephemeral=True)
    else:
        await interaction.followup.send(f"❌ {msg}", ephemeral=True)

@supervisor_template_group.command(name="list", description="List all built-in and custom supervisor templates.")
async def exec_tpl_list_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    from supervisor_templates_system import get_combined_supervisor_template_list
    tpls = get_combined_supervisor_template_list()
    embed = discord.Embed(
        title="👑 Echo Supervisor & Executive HR Templates Directory",
        description=f"Total Supervisor Templates Available: **{len(tpls)}**\n\n",
        color=0x9B59B6
    )
    for t in tpls[:25]:
        embed.add_field(
            name=f"{t.get('emoji', '👑')} {t['title']} (`{t['shortcut']}`)",
            value=f"**Cat:** {t.get('category', 'Executive HR')}\n{t['template'][:100]}...",
            inline=False
        )
    await interaction.followup.send(embed=embed, ephemeral=True)

bot.tree.add_command(supervisor_template_group)

@bot.tree.command(name="setup-supervisor-templates", description="Initialize or refresh the #supervisor-templates channel guide.")
async def setup_supervisor_templates_channel_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    success = await sync_supervisor_templates_channel(bot, channel=interaction.channel)
    if success:
        await interaction.followup.send("✅ Supervisor templates guide successfully synchronized in this channel!", ephemeral=True)
    else:
        await interaction.followup.send("❌ Failed to synchronize supervisor templates channel.", ephemeral=True)


# ==========================================
# 👑 FOUNDERSHIP FORCE OPEN TICKET COMMANDS
# ==========================================

@bot.tree.command(name="force-open-ticket", description="[Foundership Only] Force open a support/modmail ticket on behalf of a member or staff.")
@app_commands.describe(
    user="Target member or staff to open ticket for",
    section="Support category section",
    subject="Reason or subject for opening this ticket"
)
@app_commands.choices(section=[
    app_commands.Choice(name="High-Ranking Support (HR / Staff Inquiry)", value="High-Ranking Support"),
    app_commands.Choice(name="General Support", value="General Support"),
    app_commands.Choice(name="Development Ticket", value="Development Ticket"),
    app_commands.Choice(name="Booster Perks", value="Booster Perks")
])
async def force_open_ticket_cmd(
    interaction: discord.Interaction,
    user: discord.Member,
    section: Optional[str] = None,
    subject: Optional[str] = "Formal Executive Inquiry & Staff Communication"
):
    await interaction.response.defer(ephemeral=True)

    # Permission check: Must have Foundership role or Administrator permission
    foundership_role = interaction.guild.get_role(config.FOUNDERSHIP_ROLE_ID)
    is_foundership = (
        (foundership_role in interaction.user.roles) if foundership_role else False
    ) or interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild

    if not is_foundership:
        await interaction.followup.send("❌ Only **Foundership & Executive Leadership** can force open tickets for members.", ephemeral=True)
        return

    sec_name = section.value if hasattr(section, 'value') else (section or "High-Ranking Support")
    initial_msg = f"**👑 FORCED TICKET CREATION BY FOUNDERSHIP ({interaction.user.name})**\n\n**Subject:** {subject.strip()}"

    channel = await bot.create_support_ticket(
        user=user,
        initial_query=initial_msg,
        guild=interaction.guild,
        section=sec_name
    )

    if not channel:
        await interaction.followup.send("❌ Failed to create ticket channel. Please check server permissions.", ephemeral=True)
        return

    ticket = bot.ticket_manager.get_ticket_by_channel(channel.id)
    if ticket:
        bot.ticket_manager.claim_ticket(ticket["id"], interaction.user.id)
        bot.ticket_manager.set_ai_enabled(ticket["id"], False)

    exec_embed = discord.Embed(
        title="👑 Executive Foundership Direct Ticket",
        description=(
            f"This direct ticket was **Forcibly Opened** by {interaction.user.mention} (`{interaction.user.name}`).\n\n"
            f"👤 **Target Member:** {user.mention} (`{user.name}` | ID: `{user.id}`)\n"
            f"📂 **Category:** `{sec_name}`\n"
            f"📝 **Subject / Reason:** {subject}\n\n"
            f"*(AI auto-replies are paused. Staff messages sent in this channel will be relayed directly to the user's DMs.)*"
        ),
        color=0x9B59B6,
        timestamp=discord.utils.utcnow()
    )
    exec_embed.set_author(name=f"Opened by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
    exec_embed.set_footer(text=f"Ticket #{ticket['id'] if ticket else 'N/A'} • Foundership Executive Action")

    await channel.send(content=f"<@&{config.FOUNDERSHIP_ROLE_ID}>", embed=exec_embed)

    dm_sent = False
    try:
        dm = await user.create_dm()
        dm_embed = discord.Embed(
            title="👑 Echo Technologies • Foundership Direct Ticket Opened",
            description=(
                f"Hello **{user.name}**,\n\n"
                f"A member of **Foundership & Executive Leadership** ({interaction.user.mention}) has opened a direct support ticket for you.\n\n"
                f"📂 **Category:** `{sec_name}`\n"
                f"📝 **Subject:** {subject}\n\n"
                f"💬 **How to Communicate:** Reply directly to this DM to speak directly with Foundership!"
            ),
            color=0x9B59B6,
            timestamp=discord.utils.utcnow()
        )
        dm_embed.set_footer(text=f"Direct Ticket #{ticket['id'] if ticket else 'N/A'} • Echo Technologies HR")
        await dm.send(embed=dm_embed)
        dm_sent = True
    except Exception as e:
        logger.warning(f"Could not send DM to user {user.id} on force open ticket: {e}")

    dm_status = "✅ Direct DM dispatched to member!" if dm_sent else "⚠️ Member DMs are closed or failed to receive DM."
    await interaction.followup.send(
        f"✅ **Ticket #{ticket['id'] if ticket else 'N/A'} successfully opened for {user.mention}!**\n"
        f"📍 Channel: {channel.mention}\n"
        f"{dm_status}",
        ephemeral=True
    )

@bot.tree.command(name="ticket-force-open", description="[Foundership Only] Alias for /force-open-ticket.")
@app_commands.describe(
    user="Target member or staff to open ticket for",
    section="Support category section",
    subject="Reason or subject for opening this ticket"
)
@app_commands.choices(section=[
    app_commands.Choice(name="High-Ranking Support (HR / Staff Inquiry)", value="High-Ranking Support"),
    app_commands.Choice(name="General Support", value="General Support"),
    app_commands.Choice(name="Development Ticket", value="Development Ticket"),
    app_commands.Choice(name="Booster Perks", value="Booster Perks")
])
async def ticket_force_open_cmd(
    interaction: discord.Interaction,
    user: discord.Member,
    section: Optional[str] = None,
    subject: Optional[str] = "Formal Executive Inquiry & Staff Communication"
):
    await force_open_ticket_cmd.callback(interaction, user, section, subject)


@bot.tree.command(name="ticket-request-close", description="Request to close an active support ticket by sending a DM prompt to the member.")
@app_commands.describe(reason="Reason or notes for requesting ticket closure")
async def ticket_request_close_cmd(interaction: discord.Interaction, reason: Optional[str] = "Your support inquiry has been marked as resolved."):
    await interaction.response.defer(ephemeral=True)
    ticket = await bot.get_or_recover_ticket(interaction.channel)
    if not ticket:
        await interaction.followup.send("❌ This command must be used inside an active support ticket channel.", ephemeral=True)
        return

    from ticket_views import RequestCloseModal
    modal = RequestCloseModal(bot, ticket)
    modal.reason_input.default = reason
    await interaction.followup.send(f"🔔 Dispatched Close Request dialog for Ticket #{ticket['id']}!", ephemeral=True)


@bot.tree.command(name="test-ticket", description="[Foundership Only] Open practical assessment ticket for support staff (AI disabled).")
@app_commands.describe(
    target_staff="Support team member to test",
    scenario_title="Preset assessment scenario",
    custom_details="Custom scenario task details or prompt"
)
@app_commands.choices(scenario_title=[
    app_commands.Choice(name="Master Phishing & Account Security Simulation", value="Master Phishing & Account Security Simulation"),
    app_commands.Choice(name="Hostile Member & Threat De-Escalation Simulation", value="Hostile Member & Threat De-Escalation Simulation"),
    app_commands.Choice(name="False Ban Appeal & Confidential Evidence Request", value="False Ban Appeal & Confidential Evidence Request"),
    app_commands.Choice(name="Exploit Report & Player Dispute Video Verification", value="Exploit Report & Player Dispute Video Verification"),
    app_commands.Choice(name="Rogue Mod Impersonation & Rank Restoration Fraud", value="Rogue Mod Impersonation & Rank Restoration Fraud"),
    app_commands.Choice(name="Booster Perks Claim & Verification Fraud", value="Booster Perks Claim & Verification Fraud"),
    app_commands.Choice(name="Custom Practical Assessment Scenario", value="Custom Practical Assessment Scenario")
])
async def test_ticket_cmd(
    interaction: discord.Interaction,
    target_staff: discord.Member,
    scenario_title: Optional[str] = None,
    custom_details: Optional[str] = "Demonstrate standard support procedure, verify user inquiry, and apply appropriate response templates."
):
    await interaction.response.defer(ephemeral=True)

    foundership_role = interaction.guild.get_role(config.FOUNDERSHIP_ROLE_ID)
    is_foundership = (
        (foundership_role in interaction.user.roles) if foundership_role else False
    ) or interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild

    if not is_foundership:
        await interaction.followup.send("❌ Only **Foundership & Executive Leadership** can open practical test tickets for support staff.", ephemeral=True)
        return

    scen_name = scenario_title.value if hasattr(scenario_title, 'value') else (scenario_title or "Support Team Practical Assessment")

    channel = await bot.create_staff_test_ticket(
        founder=interaction.user,
        target_staff=target_staff,
        guild=interaction.guild,
        scenario_title=scen_name,
        scenario_details=custom_details
    )

    if not channel:
        await interaction.followup.send("❌ Failed to create staff test ticket channel. Please check server permissions.", ephemeral=True)
        return

    ticket = bot.ticket_manager.get_ticket_by_channel(channel.id)

    # DM notification to target staff member
    dm_sent = False
    try:
        dm = await target_staff.create_dm()
        dm_embed = discord.Embed(
            title="🧪 Echo Technologies • Support Team Evaluation Notice",
            description=(
                f"Hello **{target_staff.name}**!\n\n"
                f"You have been assigned a practical **Support SOP Assessment** by Foundership member {interaction.user.mention}.\n\n"
                f"🎯 **Scenario:** `{scen_name}`\n"
                f"📍 **Test Channel:** {channel.mention}\n\n"
                f"⚠️ **Note:** The AI Assistant is **Disabled** in this channel. Please head to your test channel to complete your practical examination!"
            ),
            color=0x9B59B6,
            timestamp=discord.utils.utcnow()
        )
        dm_embed.set_footer(text=f"Exam Ticket #{ticket['id'] if ticket else 'N/A'} • Echo HR Operations")
        await dm.send(embed=dm_embed)
        dm_sent = True
    except Exception as e:
        logger.warning(f"Could not send DM notice to staff member {target_staff.id}: {e}")

    dm_status = "✅ Sent test notice directly to staff member's DMs!" if dm_sent else "⚠️ Staff member DMs are closed or failed to receive DM."
    await interaction.followup.send(
        f"🧪 **Practical Test Ticket #{ticket['id'] if ticket else 'N/A'} created for {target_staff.mention}!**\n"
        f"📍 Channel: {channel.mention}\n"
        f"🔒 Visible ONLY to {interaction.user.mention}, {target_staff.mention}, and the Bot (AI Disabled).\n"
        f"{dm_status}",
        ephemeral=True
    )

@bot.tree.command(name="ticket-test-staff", description="[Foundership Only] Alias for /test-ticket.")
@app_commands.describe(
    target_staff="Support team member to test",
    scenario_title="Preset assessment scenario",
    custom_details="Custom scenario task details or prompt"
)
@app_commands.choices(scenario_title=[
    app_commands.Choice(name="Master Phishing & Account Security Simulation", value="Master Phishing & Account Security Simulation"),
    app_commands.Choice(name="Hostile Member & Threat De-Escalation Simulation", value="Hostile Member & Threat De-Escalation Simulation"),
    app_commands.Choice(name="False Ban Appeal & Confidential Evidence Request", value="False Ban Appeal & Confidential Evidence Request"),
    app_commands.Choice(name="Exploit Report & Player Dispute Video Verification", value="Exploit Report & Player Dispute Video Verification"),
    app_commands.Choice(name="Rogue Mod Impersonation & Rank Restoration Fraud", value="Rogue Mod Impersonation & Rank Restoration Fraud"),
    app_commands.Choice(name="Booster Perks Claim & Verification Fraud", value="Booster Perks Claim & Verification Fraud"),
    app_commands.Choice(name="Custom Practical Assessment Scenario", value="Custom Practical Assessment Scenario")
])
async def ticket_test_staff_cmd(
    interaction: discord.Interaction,
    target_staff: discord.Member,
    scenario_title: Optional[str] = None,
    custom_details: Optional[str] = "Demonstrate standard support procedure, verify user inquiry, and apply appropriate response templates."
):
    await test_ticket_cmd.callback(interaction, target_staff, scenario_title, custom_details)

@bot.tree.command(name="staff-test-ticket", description="[Foundership Only] Alias for /test-ticket.")
@app_commands.describe(
    target_staff="Support team member to test",
    scenario_title="Preset assessment scenario",
    custom_details="Custom scenario task details or prompt"
)
@app_commands.choices(scenario_title=[
    app_commands.Choice(name="Master Phishing & Account Security Simulation", value="Master Phishing & Account Security Simulation"),
    app_commands.Choice(name="Hostile Member & Threat De-Escalation Simulation", value="Hostile Member & Threat De-Escalation Simulation"),
    app_commands.Choice(name="False Ban Appeal & Confidential Evidence Request", value="False Ban Appeal & Confidential Evidence Request"),
    app_commands.Choice(name="Exploit Report & Player Dispute Video Verification", value="Exploit Report & Player Dispute Video Verification"),
    app_commands.Choice(name="Rogue Mod Impersonation & Rank Restoration Fraud", value="Rogue Mod Impersonation & Rank Restoration Fraud"),
    app_commands.Choice(name="Booster Perks Claim & Verification Fraud", value="Booster Perks Claim & Verification Fraud"),
    app_commands.Choice(name="Custom Practical Assessment Scenario", value="Custom Practical Assessment Scenario")
])
async def staff_test_ticket_cmd(
    interaction: discord.Interaction,
    target_staff: discord.Member,
    scenario_title: Optional[str] = None,
    custom_details: Optional[str] = "Demonstrate standard support procedure, verify user inquiry, and apply appropriate response templates."
):
    await test_ticket_cmd.callback(interaction, target_staff, scenario_title, custom_details)


# ==========================================
# 🧪 STAFF EVALUATION & EXAM LOGGING SYSTEM
# ==========================================

class LogStaffEvaluationModal(discord.ui.Modal, title="Log Staff Evaluation & Feedback"):
    def __init__(self, bot, target_staff: discord.Member, score: int, verdict: str, scenario: str):
        super().__init__()
        self.bot = bot
        self.target_staff = target_staff
        self.score = score
        self.verdict = verdict
        self.scenario = scenario

        self.notes_input = discord.ui.TextInput(
            label="Feedback & Detailed Evaluation Notes",
            style=discord.TextStyle.paragraph,
            placeholder="Enter detailed evaluation notes, strengths, areas for improvement, and grading breakdown...",
            required=True,
            max_length=2000
        )
        self.add_item(self.notes_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        notes = self.notes_input.value.strip()

        eval_data = add_staff_evaluation(
            staff_id=self.target_staff.id,
            evaluator_id=interaction.user.id,
            guild_id=interaction.guild_id or config.GUILD_ID,
            score=self.score,
            verdict=self.verdict,
            scenario=self.scenario,
            feedback_notes=notes
        )

        # 1. DM Trainee (Staff Member)
        trainee_dm_sent = False
        try:
            dm = await self.target_staff.create_dm()
            dm_embed = build_evaluation_dm_embed(eval_data, self.target_staff, interaction.user)
            await dm.send(embed=dm_embed)
            trainee_dm_sent = True
        except Exception as e:
            logger.warning(f"Could not send evaluation DM to trainee {self.target_staff.id}: {e}")

        # 2. DM Trainer / Evaluator (Foundership)
        trainer_dm_sent = False
        try:
            trainer_dm = await interaction.user.create_dm()
            trainer_embed = build_evaluation_dm_embed(eval_data, self.target_staff, interaction.user)
            trainer_embed.title = f"🧾 Trainer Audit Receipt • Evaluation #{eval_data['id']} ({self.target_staff.name})"
            trainer_embed.set_footer(text=f"Trainer/Evaluator Audit Record • Echo HR Operations")
            await trainer_dm.send(embed=trainer_embed)
            trainer_dm_sent = True
        except Exception as e:
            logger.warning(f"Could not send evaluation DM copy to trainer {interaction.user.id}: {e}")

        # Post to public/staff logs channel (#staff-disciplinary / 1556021154756698192)
        pub_ch = interaction.guild.get_channel(config.PUBLIC_LOGS_CHANNEL_ID) if interaction.guild else None
        if pub_ch and isinstance(pub_ch, discord.TextChannel):
            try:
                log_embed = build_evaluation_log_embed(eval_data, self.target_staff, interaction.user)
                await pub_ch.send(embed=log_embed)
            except Exception as e:
                logger.warning(f"Could not post evaluation log to channel: {e}")

        trainee_status = "✅ Sent DM to Trainee!" if trainee_dm_sent else "⚠️ Trainee DMs closed."
        trainer_status = "✅ Sent receipt DM to Trainer!" if trainer_dm_sent else "⚠️ Trainer DMs closed."
        await interaction.followup.send(
            f"✅ **Staff Evaluation Record #{eval_data['id']} successfully logged for {self.target_staff.mention}!**\n"
            f"📊 **Score:** `{self.score}/100` | 🏆 **Verdict:** `{self.verdict}`\n"
            f"📩 **DM Status:** {trainee_status} | {trainer_status}",
            ephemeral=True
        )


@bot.tree.command(name="staff-eval-log", description="[Foundership Only] Log staff test results with score & feedback.")
@app_commands.describe(
    target_staff="Support team member evaluated",
    score="Numerical score (0 to 100)",
    verdict="Final exam verdict",
    scenario="Evaluation scenario title",
    feedback_notes="Optional feedback notes (or leave empty to open modal)"
)
@app_commands.choices(verdict=[
    app_commands.Choice(name="Exceptional (95-100)", value="Exceptional"),
    app_commands.Choice(name="Pass (85-94)", value="Pass"),
    app_commands.Choice(name="Conditional Pass (70-84)", value="Conditional Pass"),
    app_commands.Choice(name="Fail (0-69)", value="Fail")
])
async def staff_eval_log_cmd(
    interaction: discord.Interaction,
    target_staff: discord.Member,
    score: int,
    verdict: Optional[str] = "Pass",
    scenario: Optional[str] = "Hostile Member Wrongful Ban & SOP Exam",
    feedback_notes: Optional[str] = None
):
    foundership_role = interaction.guild.get_role(config.FOUNDERSHIP_ROLE_ID) if interaction.guild else None
    is_foundership = (
        (foundership_role in interaction.user.roles) if foundership_role else False
    ) or interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild

    if not is_foundership:
        await interaction.response.send_message("❌ Only **Foundership & Executive Leadership** can log staff evaluations.", ephemeral=True)
        return

    verdict_val = verdict.value if hasattr(verdict, 'value') else (verdict or "Pass")
    score_clamped = max(0, min(100, score))

    if not feedback_notes:
        modal = LogStaffEvaluationModal(bot, target_staff, score_clamped, verdict_val, scenario or "Support SOP Evaluation")
        await interaction.response.send_modal(modal)
        return

    await interaction.response.defer(ephemeral=True)
    eval_data = add_staff_evaluation(
        staff_id=target_staff.id,
        evaluator_id=interaction.user.id,
        guild_id=interaction.guild_id or config.GUILD_ID,
        score=score_clamped,
        verdict=verdict_val,
        scenario=scenario or "Support SOP Evaluation",
        feedback_notes=feedback_notes.strip()
    )

    # 1. DM Trainee (Staff Member)
    trainee_dm_sent = False
    try:
        dm = await target_staff.create_dm()
        dm_embed = build_evaluation_dm_embed(eval_data, target_staff, interaction.user)
        await dm.send(embed=dm_embed)
        trainee_dm_sent = True
    except Exception as e:
        logger.warning(f"Could not send evaluation DM to trainee {target_staff.id}: {e}")

    # 2. DM Trainer / Evaluator (Foundership)
    trainer_dm_sent = False
    try:
        trainer_dm = await interaction.user.create_dm()
        trainer_embed = build_evaluation_dm_embed(eval_data, target_staff, interaction.user)
        trainer_embed.title = f"🧾 Trainer Audit Receipt • Evaluation #{eval_data['id']} ({target_staff.name})"
        trainer_embed.set_footer(text=f"Trainer/Evaluator Audit Record • Echo HR Operations")
        await trainer_dm.send(embed=trainer_embed)
        trainer_dm_sent = True
    except Exception as e:
        logger.warning(f"Could not send evaluation DM copy to trainer {interaction.user.id}: {e}")

    # Log to staff public channel
    pub_ch = interaction.guild.get_channel(config.PUBLIC_LOGS_CHANNEL_ID) if interaction.guild else None
    if pub_ch and isinstance(pub_ch, discord.TextChannel):
        try:
            log_embed = build_evaluation_log_embed(eval_data, target_staff, interaction.user)
            await pub_ch.send(embed=log_embed)
        except Exception as e:
            logger.warning(f"Could not post evaluation log: {e}")

    trainee_status = "✅ Sent DM to Trainee!" if trainee_dm_sent else "⚠️ Trainee DMs closed."
    trainer_status = "✅ Sent receipt DM to Trainer!" if trainer_dm_sent else "⚠️ Trainer DMs closed."
    await interaction.followup.send(
        f"✅ **Staff Evaluation Record #{eval_data['id']} successfully logged for {target_staff.mention}!**\n"
        f"📊 **Score:** `{score_clamped}/100` | 🏆 **Verdict:** `{verdict_val}`\n"
        f"📩 **DM Status:** {trainee_status} | {trainer_status}",
        ephemeral=True
    )


@bot.tree.command(name="log-test-result", description="[Foundership Only] Alias for /staff-eval-log.")
@app_commands.describe(
    target_staff="Support team member evaluated",
    score="Numerical score (0 to 100)",
    verdict="Final exam verdict",
    scenario="Evaluation scenario title",
    feedback_notes="Optional feedback notes (or leave empty to open modal)"
)
@app_commands.choices(verdict=[
    app_commands.Choice(name="Exceptional (95-100)", value="Exceptional"),
    app_commands.Choice(name="Pass (85-94)", value="Pass"),
    app_commands.Choice(name="Conditional Pass (70-84)", value="Conditional Pass"),
    app_commands.Choice(name="Fail (0-69)", value="Fail")
])
async def log_test_result_cmd(
    interaction: discord.Interaction,
    target_staff: discord.Member,
    score: int,
    verdict: Optional[str] = "Pass",
    scenario: Optional[str] = "Hostile Member Wrongful Ban & SOP Exam",
    feedback_notes: Optional[str] = None
):
    await staff_eval_log_cmd.callback(interaction, target_staff, score, verdict, scenario, feedback_notes)


@bot.tree.command(name="staff-test-log", description="[Foundership Only] Alias for /staff-eval-log.")
@app_commands.describe(
    target_staff="Support team member evaluated",
    score="Numerical score (0 to 100)",
    verdict="Final exam verdict",
    scenario="Evaluation scenario title",
    feedback_notes="Optional feedback notes (or leave empty to open modal)"
)
@app_commands.choices(verdict=[
    app_commands.Choice(name="Exceptional (95-100)", value="Exceptional"),
    app_commands.Choice(name="Pass (85-94)", value="Pass"),
    app_commands.Choice(name="Conditional Pass (70-84)", value="Conditional Pass"),
    app_commands.Choice(name="Fail (0-69)", value="Fail")
])
async def staff_test_log_cmd(
    interaction: discord.Interaction,
    target_staff: discord.Member,
    score: int,
    verdict: Optional[str] = "Pass",
    scenario: Optional[str] = "Hostile Member Wrongful Ban & SOP Exam",
    feedback_notes: Optional[str] = None
):
    await staff_eval_log_cmd.callback(interaction, target_staff, score, verdict, scenario, feedback_notes)


@bot.tree.command(name="staff-eval-history", description="View historical evaluation scores and feedback for a staff member.")
@app_commands.describe(target_staff="Support team member to inspect")
async def staff_eval_history_cmd(interaction: discord.Interaction, target_staff: discord.Member):
    await interaction.response.defer(ephemeral=False)
    evals = get_staff_evaluations(target_staff.id)
    if not evals:
        await interaction.followup.send(f"ℹ️ No training or evaluation records found for {target_staff.mention}.", ephemeral=True)
        return

    avg_score = round(sum(e["score"] for e in evals) / len(evals), 1)
    color = 0x57F287 if avg_score >= 85 else (0xFEE75C if avg_score >= 70 else 0xED4245)

    embed = discord.Embed(
        title=f"📊 Staff Evaluation Dossier • {target_staff.name}",
        description=(
            f"**Member:** {target_staff.mention} (`@{target_staff.name}` | `{target_staff.id}`)\n"
            f"**Total Assessments:** `{len(evals)}` exams logged\n"
            f"**Average Score:** `{avg_score} / 100`\n\n"
            f"### 📜 Evaluation History"
        ),
        color=color,
        timestamp=discord.utils.utcnow()
    )

    for e in evals[:5]:
        v_emoji = "🌟" if e["score"] >= 95 else ("✅" if e["score"] >= 85 else ("🟡" if e["score"] >= 70 else "❌"))
        evaluator = interaction.guild.get_member(e["evaluator_id"]) if interaction.guild else None
        evaluator_name = evaluator.name if evaluator else f"User {e['evaluator_id']}"
        embed.add_field(
            name=f"Record #{e['id']} • Score: {e['score']}/100 ({e['verdict']} {v_emoji})",
            value=(
                f"**Scenario:** `{e['scenario']}`\n"
                f"**Evaluator:** `{evaluator_name}`\n"
                f"**Feedback:** {e['feedback_notes'][:300]}\n"
                f"**Date:** <t:{int(datetime.fromisoformat(e['created_at'].replace('Z','+00:00')).timestamp() if 'T' in e['created_at'] else int(datetime.strptime(e['created_at'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp()))}:R>"
            ),
            inline=False
        )

    embed.set_footer(text="Echo Technologies HR Leadership Dossier")
    if target_staff.display_avatar:
        embed.set_thumbnail(url=target_staff.display_avatar.url)

    await interaction.followup.send(embed=embed)


@bot.tree.command(name="staff-test-history", description="[Foundership Only] Alias for /staff-eval-history.")
@app_commands.describe(target_staff="Support team member to inspect")
async def staff_test_history_cmd(interaction: discord.Interaction, target_staff: discord.Member):
    await staff_eval_history_cmd.callback(interaction, target_staff)



# ==========================================
# 🔄 UNIFIED PERSISTENT COMPONENT LISTENER
# ==========================================




@bot.listen("on_interaction")
async def on_persistent_components_listener(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        cid = interaction.data.get("custom_id", "")
        # 1. Hire System
        if cid.startswith("hire_acc:") or cid.startswith("hire_dec:"):
            parts = cid.split(":")
            if len(parts) >= 2:
                action = "accept" if parts[0] == "hire_acc" else "decline"
                try:
                    offer_id = int(parts[1])
                    await handle_hire_action(
                        bot=bot,
                        interaction=interaction,
                        offer_id=offer_id,
                        action=action
                    )
                except Exception as e:
                    logger.error(f"Error executing hire interaction: {e}")

        # 1b. Ticket Close Request System
        elif cid.startswith("req_close_acc:") or cid.startswith("req_close_keep:"):
            parts = cid.split(":")
            if len(parts) >= 2:
                try:
                    ticket_id = int(parts[1])
                    action = "accept" if parts[0] == "req_close_acc" else "keep"
                    ticket = bot.ticket_manager.get_ticket_by_id(ticket_id)
                    if not ticket or ticket["status"] == "closed":
                        await interaction.response.send_message("ℹ️ This ticket has already been closed.", ephemeral=True)
                    else:
                        if action == "accept":
                            await interaction.response.defer()
                            channel = bot.get_channel(ticket["channel_id"])
                            await interaction.followup.send("✅ Thank you! Your ticket has been closed. Please rate your experience below:", ephemeral=False)
                            await bot.close_support_ticket(ticket, channel, closed_by=interaction.user)
                        else:
                            await interaction.response.defer()
                            channel = bot.get_channel(ticket["channel_id"])
                            if channel:
                                keep_embed = discord.Embed(
                                    title="💬 Member Requested to Keep Ticket Open",
                                    description=f"Member {interaction.user.mention} rejected the close request and requested to keep **Ticket #{ticket_id}** open.",
                                    color=0xFEE75C
                                )
                                await channel.send(embed=keep_embed)
                            bot.ticket_manager.set_ai_enabled(ticket_id, True)
                            await interaction.followup.send("💬 Your request to keep the ticket open has been sent to our team! Reply here anytime to continue.", ephemeral=False)
                except Exception as e:
                    logger.error(f"Error handling close request interaction: {e}")

        # 2. Suggestions System
        elif cid.startswith("sug_up:") or cid.startswith("sug_dn:") or cid.startswith("sug_rev:"):
            parts = cid.split(":")
            if len(parts) >= 2:
                try:
                    sug_id = int(parts[1])
                    if parts[0] == "sug_up":
                        ups, downs, msg = vote_suggestion(sug_id, interaction.user.id, 1)
                        sug = get_suggestion(sug_id)
                        if sug:
                            author = bot.get_user(sug["author_id"])
                            reviewer = bot.get_user(sug.get("reviewed_by") or 0)
                            new_embed = build_suggestion_embed(sug, ups, downs, author, reviewer)
                            view = SuggestionVoteView(bot, sug_id, ups, downs)
                            await interaction.response.edit_message(embed=new_embed, view=view)
                    elif parts[0] == "sug_dn":
                        ups, downs, msg = vote_suggestion(sug_id, interaction.user.id, -1)
                        sug = get_suggestion(sug_id)
                        if sug:
                            author = bot.get_user(sug["author_id"])
                            reviewer = bot.get_user(sug.get("reviewed_by") or 0)
                            new_embed = build_suggestion_embed(sug, ups, downs, author, reviewer)
                            view = SuggestionVoteView(bot, sug_id, ups, downs)
                            await interaction.response.edit_message(embed=new_embed, view=view)
                    elif parts[0] == "sug_rev":
                        is_admin = interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator
                        if not is_admin:
                            await interaction.response.send_message("❌ Only management staff can review suggestions.", ephemeral=True)
                        else:
                            modal = ReviewSuggestionModal(bot, sug_id)
                            await interaction.response.send_modal(modal)
                except Exception as e:
                    logger.error(f"Error handling suggestion interaction: {e}")

        # 3. Bug Tracker System
        elif cid.startswith("bug_clm:") or cid.startswith("bug_prg:") or cid.startswith("bug_res:") or cid.startswith("bug_cls:"):
            parts = cid.split(":")
            if len(parts) >= 2:
                try:
                    bug_id = int(parts[1])
                    if parts[0] == "bug_clm":
                        claim_bug(bug_id, interaction.user.id)
                        report = get_bug_report(bug_id)
                        if report:
                            reporter = bot.get_user(report["reporter_id"])
                            embed = build_bug_embed(report, reporter, interaction.user)
                            view = BugReportControlView(bot, bug_id)
                            await interaction.response.edit_message(embed=embed, view=view)
                            await interaction.followup.send(f"📌 {interaction.user.mention} has claimed Bug #{bug_id}!", ephemeral=False)
                    elif parts[0] == "bug_prg":
                        update_bug_status(bug_id, "In Progress", interaction.user.id)
                        report = get_bug_report(bug_id)
                        if report:
                            reporter = bot.get_user(report["reporter_id"])
                            embed = build_bug_embed(report, reporter, interaction.user)
                            view = BugReportControlView(bot, bug_id)
                            await interaction.response.edit_message(embed=embed, view=view)
                            await interaction.followup.send(f"🚧 Bug #{bug_id} marked **In Progress** by {interaction.user.mention}.", ephemeral=False)
                    elif parts[0] == "bug_res":
                        modal = ResolveBugModal(bot, bug_id)
                        await interaction.response.send_modal(modal)
                    elif parts[0] == "bug_cls":
                        update_bug_status(bug_id, "Closed", interaction.user.id, "Closed / Won't Fix")
                        report = get_bug_report(bug_id)
                        if report:
                            reporter = bot.get_user(report["reporter_id"])
                            embed = build_bug_embed(report, reporter, interaction.user)
                            view = BugReportControlView(bot, bug_id)
                            await interaction.response.edit_message(embed=embed, view=view)
                            await interaction.followup.send(f"❌ Bug #{bug_id} has been marked **Closed** by {interaction.user.mention}.", ephemeral=False)
                except Exception as e:
                    logger.error(f"Error handling bug interaction: {e}")

        # 4. Giveaway System
        elif cid.startswith("g_enter:"):
            parts = cid.split(":")
            if len(parts) >= 2:
                try:
                    gw_id = int(parts[1])
                    gw = get_giveaway(gw_id)
                    if not gw or gw.get("ended"):
                        await interaction.response.send_message("❌ This giveaway has already ended!", ephemeral=True)
                    else:
                        entered, new_count = toggle_giveaway_entry(gw_id, interaction.user.id)
                        new_embed = build_giveaway_embed(gw, new_count, is_ended=False)
                        new_view = GiveawayView(gw_id, new_count, ended=False)
                        await interaction.response.edit_message(embed=new_embed, view=new_view)
                        msg_text = (
                            f"🎉 **Entered!** You are now entered in the giveaway for **{gw['prize']}**!"
                            if entered
                            else f"👋 **Removed!** You left the giveaway for **{gw['prize']}**."
                        )
                        await interaction.followup.send(msg_text, ephemeral=True)
                except Exception as e:
                    logger.error(f"Error handling giveaway interaction: {e}")

        # 5. Event RSVP System
        elif cid.startswith("ev_att:") or cid.startswith("ev_myb:") or cid.startswith("ev_dec:"):
            parts = cid.split(":")
            if len(parts) >= 2:
                try:
                    ev_id = int(parts[1])
                    ev_data = get_event(ev_id)
                    if not ev_data or ev_data.get("status") != "scheduled":
                        await interaction.response.send_message("❌ This event is no longer active.", ephemeral=True)
                    else:
                        status_map = {"ev_att": "attending", "ev_myb": "maybe", "ev_dec": "declined"}
                        status = status_map.get(parts[0], "attending")
                        final_status, counts = set_event_rsvp(ev_id, interaction.user.id, status)
                        new_embed = build_event_embed(ev_data, counts)
                        new_view = EventRsvpView(ev_id, counts)
                        await interaction.response.edit_message(embed=new_embed, view=new_view)

                        responses = {
                            "attending": "✅ You are registered as **Attending**! You will receive a reminder DM 15 minutes before the event.",
                            "maybe": "❓ You are marked as **Maybe**! You will receive a reminder DM 15 minutes before the event.",
                            "declined": "❌ You are marked as **Can't Make It**.",
                            "none": "👋 Your RSVP has been cleared."
                        }
                        await interaction.followup.send(responses.get(final_status, "RSVP updated!"), ephemeral=True)
                except Exception as e:
                    logger.error(f"Error handling event RSVP: {e}")

        # 6. Leave of Absence (LOA) Management
        elif cid.startswith("loa_app:") or cid.startswith("loa_den:"):
            parts = cid.split(":")
            if len(parts) >= 2:
                try:
                    loa_id = int(parts[1])
                    is_admin = interaction.user.guild_permissions.manage_roles or interaction.user.guild_permissions.administrator
                    if not is_admin:
                        await interaction.response.send_message("❌ Only HR and management staff can review LOA requests.", ephemeral=True)
                    else:
                        if parts[0] == "loa_app":
                            success, msg, updated = review_loa_request(loa_id, interaction.user.id, "approved")
                            if success:
                                staff_user = bot.get_user(updated["user_id"])
                                new_embed = build_loa_staff_embed(updated, staff_user, interaction.user)
                                new_view = LOAControlView(loa_id, disabled=True)
                                await interaction.response.edit_message(embed=new_embed, view=new_view)
                                await interaction.followup.send(f"✅ Approved LOA #{loa_id} for <@{updated['user_id']}>!", ephemeral=False)
                                if staff_user:
                                    try:
                                        dm = await staff_user.create_dm()
                                        await dm.send(f"🏖️ **LOA Request #{loa_id} Approved!** Your leave duration: `{updated['duration']}`.")
                                    except Exception:
                                        pass
                            else:
                                await interaction.response.send_message(f"⚠️ {msg}", ephemeral=True)
                        elif parts[0] == "loa_den":
                            modal = DenyLOAModal(bot, loa_id)
                            await interaction.response.send_modal(modal)
                except Exception as e:
                    logger.error(f"Error handling LOA interaction: {e}")

        # 7. Staff & Developer Applications System
        elif cid.startswith("app_start:"):
            pos_key = cid.split("app_start:")[1]
            success, reply_msg = await start_dm_application_flow(
                bot=bot,
                user=interaction.user,
                guild=interaction.guild or bot.get_primary_guild(),
                position_key=pos_key
            )
            await interaction.response.send_message(reply_msg, ephemeral=True)

        elif cid.startswith("app_acc:") or cid.startswith("app_dec:") or cid.startswith("app_ask:") or cid.startswith("app_html:"):
            parts = cid.split(":")
            if len(parts) >= 2:
                try:
                    app_id = int(parts[1])
                    if parts[0] == "app_html":
                        await interaction.response.defer(ephemeral=True)
                        app = get_application(app_id)
                        if not app:
                            await interaction.followup.send("❌ Application not found.", ephemeral=True)
                        else:
                            pos_data = APPLICATION_POSITIONS.get(app["position_key"], {})
                            questions = pos_data.get("questions", [])
                            user_info = bot.db.get_by_discord_id(app["user_id"])
                            candidate = bot.get_user(app["user_id"])
                            if candidate and user_info:
                                user_info["discord_name"] = candidate.name
                            elif candidate:
                                user_info = {"discord_name": candidate.name}

                            reviewer = bot.get_user(app["reviewed_by"]) if app.get("reviewed_by") else None
                            reviewer_name = reviewer.name if reviewer else None

                            html_content = generate_application_html_transcript(
                                app_data=app,
                                questions=questions,
                                user_info=user_info,
                                reviewer_name=reviewer_name
                            )
                            filename = f"application_{app_id}_dossier.html"
                            file = discord.File(io.BytesIO(html_content.encode("utf-8")), filename=filename)

                            await interaction.followup.send(
                                content=f"📥 **HTML Dossier Transcript generated for Application #{app_id}** (`{app['position_title']}`):",
                                file=file,
                                ephemeral=True
                            )
                        return

                    is_admin = interaction.user.guild_permissions.manage_roles or interaction.user.guild_permissions.administrator
                    if not is_admin:
                        await interaction.response.send_message("❌ Only management staff can review applications.", ephemeral=True)
                    else:
                        if parts[0] == "app_acc":

                            await interaction.response.defer(ephemeral=True)
                            app = get_application(app_id)
                            if not app:
                                await interaction.followup.send("❌ Application not found.", ephemeral=True)
                            else:
                                pos_data = APPLICATION_POSITIONS.get(app["position_key"])
                                role_id = pos_data["role_id"] if pos_data else config.SUPPORT_TEAM_ROLE_ID
                                role_name = pos_data["title"] if pos_data else "Staff"

                                success, msg, updated = review_application(app_id, interaction.user.id, "approved", f"Approved by {interaction.user.name}")
                                if not success:
                                    await interaction.followup.send(f"⚠️ {msg}", ephemeral=True)
                                else:
                                    # Create official job offer via hire_system
                                    offer_id = create_hire_offer(
                                        guild_id=app["guild_id"],
                                        member_id=app["user_id"],
                                        role_id=role_id,
                                        issuer_id=interaction.user.id,
                                        origin_channel_id=interaction.channel.id,
                                        role_name=role_name
                                    )
                                    candidate = bot.get_user(app["user_id"])
                                    if candidate:
                                        try:
                                            dm = await candidate.create_dm()
                                            offer_embed = discord.Embed(
                                                title="Echo Technologies • Official Employment Offer",
                                                description=(
                                                    f"Dear **{candidate.name}**,\n\n"
                                                    f"On behalf of Echo Technologies, we are thrilled to inform you that your application for "
                                                    f"**{role_name}** has been **ACCEPTED**!\n\n"
                                                    f"We would like to formally offer you the role of **{role_name}**.\n"
                                                    f"Please click **Accept Offer** below to receive your role and join our team!"
                                                ),
                                                color=0x57F287,
                                                timestamp=discord.utils.utcnow()
                                            )
                                            offer_embed.set_footer(text="Echo Technologies Official Job Offer")
                                            offer_view = HireOfferView(bot, offer_id, role_name)
                                            await dm.send(embed=offer_embed, view=offer_view)
                                        except Exception as e:
                                            logger.warning(f"Could not send hire offer DM to candidate: {e}")

                                    # Update review embed
                                    roblox_info = bot.db.get_by_discord_id(app["user_id"])
                                    new_embed = build_application_dossier_embed(updated, candidate, roblox_info, interaction.user)
                                    new_view = ApplicationControlView(app_id, disabled=True)
                                    try:
                                        await interaction.message.edit(embed=new_embed, view=new_view)
                                    except Exception:
                                        pass

                                    # Post public log to PUBLIC_LOGS_CHANNEL_ID (#staff-disciplinary / 1556021154756698192)
                                    pub_ch = interaction.guild.get_channel(config.PUBLIC_LOGS_CHANNEL_ID)
                                    if pub_ch and isinstance(pub_ch, discord.TextChannel):
                                        try:
                                            p_embed = discord.Embed(
                                                title=f"🎉 Public Staff Log: New Team Member Appointed",
                                                description=(
                                                    f"**Staff Member:** <@{app['user_id']}>\n"
                                                    f"**Position Appointed:** `{role_name}`\n"
                                                    f"**Approved By:** {interaction.user.mention}\n"
                                                    f"**Date:** <t:{int(discord.utils.utcnow().timestamp())}:F>"
                                                ),
                                                color=0x57F287,
                                                timestamp=discord.utils.utcnow()
                                            )
                                            await pub_ch.send(embed=p_embed)
                                        except Exception:
                                            pass
                                    await interaction.followup.send(f"🎉 **Application #{app_id} Approved!** Formal employment offer dispatched to candidate's DMs.", ephemeral=False)

                        elif parts[0] == "app_dec":
                            modal = DenyApplicationModal(bot, app_id)
                            await interaction.response.send_modal(modal)

                        elif parts[0] == "app_ask":
                            modal = AskApplicantModal(bot, app_id)
                            await interaction.response.send_modal(modal)
                except Exception as e:
                    logger.error(f"Error handling application interaction: {e}")


import socket

_instance_lock_socket = None

def ensure_single_instance(port: int = 47829):
    """Enforces a strict single-instance process lock via socket binding."""
    global _instance_lock_socket
    _instance_lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _instance_lock_socket.bind(("127.0.0.1", port))
    except socket.error:
        print("\n" + "="*70)
        print("[SINGLE-INSTANCE LOCK TRIGGERED] Another bot process is already running!")
        print("Preventing duplicate process startup to protect API tokens and quota.")
        print("="*70 + "\n")
        sys.exit(0)

def main():
    ensure_single_instance()
    if not config.DISCORD_TOKEN or config.DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("\n" + "="*70)
        print("ERROR: DISCORD_TOKEN is missing or not configured in .env!")
        print("Please open the .env file and paste your Discord bot token.")
        print("="*70 + "\n")
        sys.exit(1)

    logger.info("Starting Roblox Verification & Multi-Category AI Ticket Bot...")
    bot.run(config.DISCORD_TOKEN)

if __name__ == "__main__":
    main()
