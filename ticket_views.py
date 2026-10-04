import discord
from discord import ui
import logging
from typing import Optional
import config

logger = logging.getLogger("TicketViews")

class TicketSectionSelect(ui.Select):
    """Dropdown for members to select which department/section their ticket belongs to."""

    def __init__(self, bot):
        self.bot = bot
        options = [
            discord.SelectOption(
                label="General Support",
                description="Common server inquiries, rules, and general help",
                emoji="💬",
                value="General Support"
            ),
            discord.SelectOption(
                label="High-Ranking Support",
                description="Staff inquiries, reports, appeals, and sensitive issues",
                emoji="🛡️",
                value="High-Ranking Support"
            ),
            discord.SelectOption(
                label="Development Ticket",
                description="Roblox game bugs, gameplay glitches, and technical issues",
                emoji="💻",
                value="Development Ticket"
            ),
            discord.SelectOption(
                label="Booster Perks",
                description="Server booster rewards, custom roles, and perks",
                emoji="🚀",
                value="Booster Perks"
            ),
        ]
        super().__init__(
            placeholder="Select Support Category / Section...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_section_select_menu"
        )

    async def callback(self, interaction: discord.Interaction):
        # Check blacklist
        if self.bot.ticket_manager.is_blacklisted(interaction.user.id):
            await interaction.response.send_message(
                "❌ You are blacklisted from opening support tickets. Please contact a server admin.",
                ephemeral=True
            )
            return

        # Check existing ticket
        existing_ticket = self.bot.ticket_manager.get_open_ticket_by_user(interaction.user.id)
        if existing_ticket:
            await interaction.response.send_message(
                f"⚠️ You already have an active ticket open (Ticket #{existing_ticket['id']}). Please check your **Direct Messages (DMs)** to continue chatting with our team.",
                ephemeral=True
            )
            return

        selected_section = self.values[0]
        modal = OpenTicketModal(self.bot, selected_section)
        await interaction.response.send_modal(modal)


class TicketLaunchView(ui.View):
    """Persistent view attached to the public support ticket panel embed."""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(TicketSectionSelect(bot))

    @ui.button(
        label="Quick Support Ticket",
        style=discord.ButtonStyle.primary,
        emoji="🎫",
        custom_id="ticket_launch_create_btn",
        row=1
    )
    async def quick_ticket_button(self, interaction: discord.Interaction, button: ui.Button):
        if self.bot.ticket_manager.is_blacklisted(interaction.user.id):
            await interaction.response.send_message(
                "❌ You are blacklisted from opening support tickets.",
                ephemeral=True
            )
            return

        existing = self.bot.ticket_manager.get_open_ticket_by_user(interaction.user.id)
        if existing:
            await interaction.response.send_message(
                f"⚠️ You already have an active ticket open (Ticket #{existing['id']}). Please check your **Direct Messages (DMs)** to continue chatting with our team.",
                ephemeral=True
            )
            return

        modal = OpenTicketModal(self.bot, "General Support")
        await interaction.response.send_modal(modal)


class OpenTicketModal(ui.Modal):
    """Modal asking user for subject and description."""

    topic_input = ui.TextInput(
        label="Subject / Topic",
        placeholder="Brief summary of your question or issue...",
        max_length=100,
        required=True
    )

    details_input = ui.TextInput(
        label="Details",
        placeholder="Describe your issue with as much detail as possible...",
        style=discord.TextStyle.paragraph,
        min_length=10,
        max_length=1500,
        required=True
    )

    def __init__(self, bot, section: str = "General Support"):
        super().__init__(title=f"Open {section[:22]}")
        self.bot = bot
        self.section = section

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        initial_msg = f"**Subject:** {self.topic_input.value.strip()}\n\n{self.details_input.value.strip()}"
        channel = await self.bot.create_support_ticket(
            user=interaction.user,
            initial_query=initial_msg,
            guild=interaction.guild,
            section=self.section
        )
        if channel:
            await interaction.followup.send(
                f"✅ Your **{self.section}** ticket has been opened! Please check your **Direct Messages (DMs)** — our AI Assistant has messaged you there. Reply directly in your DMs to communicate with our team!",
                ephemeral=True
            )
        else:
            await interaction.followup.send("❌ Failed to create ticket channel. Please check server permissions.", ephemeral=True)


class TicketControlView(ui.View):
    """Controls placed inside an active ticket channel."""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @ui.button(
        label="Request Supervisor",
        style=discord.ButtonStyle.danger,
        emoji="🚨",
        custom_id="ticket_ctrl_escalate_btn",
        row=0
    )
    async def escalate_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        ticket = self.bot.ticket_manager.get_or_recover_ticket(interaction.channel_id, channel_obj=interaction.channel)
        if not ticket:
            await interaction.followup.send("❌ No active ticket found in this channel.", ephemeral=True)
            return

        if ticket["status"] == "escalated":
            await interaction.followup.send("ℹ️ This ticket has already been escalated to supervisors.", ephemeral=True)
            return

        await self.bot.handle_escalation(
            ticket=ticket,
            channel=interaction.channel,
            reason=f"Supervisor requested by {interaction.user.name}"
        )

    @ui.button(
        label="Claim",
        style=discord.ButtonStyle.success,
        emoji="📌",
        custom_id="ticket_ctrl_claim_btn",
        row=0
    )
    async def claim_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=False)
        ticket = self.bot.ticket_manager.get_or_recover_ticket(interaction.channel_id, channel_obj=interaction.channel)
        if not ticket:
            await interaction.followup.send("❌ No active ticket found.", ephemeral=True)
            return

        if ticket.get("claimed_by"):
            claimed_user = self.bot.get_user(ticket["claimed_by"]) or await self.bot.fetch_user(ticket["claimed_by"])
            name = claimed_user.name if claimed_user else ticket["claimed_by"]
            await interaction.followup.send(f"ℹ️ Ticket is already claimed by **@{name}**.", ephemeral=True)
            return

        self.bot.ticket_manager.claim_ticket(ticket["id"], interaction.user.id)
        await interaction.followup.send(
            f"📌 Ticket #{ticket['id']} has been claimed by {interaction.user.mention}!",
            ephemeral=False
        )

    @ui.button(
        label="Toggle AI",
        style=discord.ButtonStyle.primary,
        emoji="🤖",
        custom_id="ticket_ctrl_ai_btn",
        row=0
    )
    async def toggle_ai_button(self, interaction: discord.Interaction, button: ui.Button):
        ticket = self.bot.ticket_manager.get_or_recover_ticket(interaction.channel_id, channel_obj=interaction.channel)
        if not ticket:
            await interaction.response.send_message("❌ No active ticket found.", ephemeral=True)
            return

        new_state = self.bot.ticket_manager.toggle_ai(ticket["id"])
        if new_state:
            embed = discord.Embed(
                title="🤖 AI Support Resumed",
                description="The AI Assistant is now **active** and will respond to inquiries.\n*(Human escalation and staff claims have been cleared)*",
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

    @ui.button(
        label="AI Suggest",
        style=discord.ButtonStyle.secondary,
        emoji="💡",
        custom_id="ticket_ctrl_ai_suggest_btn",
        row=0
    )
    async def ai_suggest_button(self, interaction: discord.Interaction, button: ui.Button):
        ticket = self.bot.ticket_manager.get_or_recover_ticket(interaction.channel_id, channel_obj=interaction.channel)
        if not ticket:
            await interaction.response.send_message("❌ No active ticket found.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        history = self.bot.ticket_manager.get_history_for_llm(ticket["id"], limit=10)
        roblox_info = self.bot.db.get_by_discord_id(ticket["user_id"])
        suggestion = await self.bot.groq_assistant.generate_suggested_reply(history, roblox_info)

        suggest_embed = discord.Embed(
            title="💡 AI Suggested Staff Response",
            description=f"Review the draft below before sending it to the member's DMs:\n\n```\n{suggestion}\n```",
            color=0x00A2FF
        )
        suggest_embed.set_footer(text="Only visible to you • Click 'Send to Member' or edit before sending")
        view = SendSuggestedReplyView(self.bot, ticket, suggestion)
        await interaction.followup.send(embed=suggest_embed, view=view, ephemeral=True)

    @ui.button(
        label="Close",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="ticket_ctrl_close_btn",
        row=0
    )
    async def close_button(self, interaction: discord.Interaction, button: ui.Button):
        ticket = self.bot.ticket_manager.get_or_recover_ticket(interaction.channel_id, channel_obj=interaction.channel)
        if not ticket:
            await interaction.response.send_message("❌ No active ticket found.", ephemeral=True)
            return

        view = ConfirmCloseView(self.bot, ticket)
        await interaction.response.send_message("Are you sure you want to close this ticket?", view=view, ephemeral=True)

    @ui.button(
        label="Transfer Category",
        style=discord.ButtonStyle.secondary,
        emoji="🔄",
        custom_id="ticket_ctrl_transfer_btn",
        row=1
    )
    async def transfer_button(self, interaction: discord.Interaction, button: ui.Button):
        ticket = self.bot.ticket_manager.get_or_recover_ticket(interaction.channel_id, channel_obj=interaction.channel)
        if not ticket:
            await interaction.response.send_message("❌ No active ticket found.", ephemeral=True)
            return

        view = TransferSectionView(self.bot, ticket["id"])
        await interaction.response.send_message("Select the category to transfer this ticket to:", view=view, ephemeral=True)

    @ui.button(
        label="Internal Note",
        style=discord.ButtonStyle.secondary,
        emoji="📝",
        custom_id="ticket_ctrl_note_btn",
        row=1
    )
    async def internal_note_button(self, interaction: discord.Interaction, button: ui.Button):
        ticket = self.bot.ticket_manager.get_or_recover_ticket(interaction.channel_id, channel_obj=interaction.channel)
        if not ticket:
            await interaction.response.send_message("❌ No active ticket found.", ephemeral=True)
            return

        modal = InternalNoteModal(self.bot, ticket["id"])
        await interaction.response.send_modal(modal)

    @ui.button(
        label="Canned Reply",
        style=discord.ButtonStyle.secondary,
        emoji="📁",
        custom_id="ticket_ctrl_canned_btn",
        row=1
    )
    async def canned_button(self, interaction: discord.Interaction, button: ui.Button):
        ticket = self.bot.ticket_manager.get_or_recover_ticket(interaction.channel_id, channel_obj=interaction.channel)
        if not ticket:
            await interaction.response.send_message("❌ No active ticket found.", ephemeral=True)
            return

        canned_list = self.bot.ticket_manager.list_canned_responses()
        if not canned_list:
            await interaction.response.send_message("ℹ️ No canned responses configured.", ephemeral=True)
            return

        view = CannedReplySelectView(self.bot, ticket, canned_list)
        await interaction.response.send_message("Select a canned response template to send to the member:", view=view, ephemeral=True)

    @ui.button(
        label="Send Template",
        style=discord.ButtonStyle.primary,
        emoji="✉️",
        custom_id="ticket_ctrl_send_tpl_btn",
        row=1
    )
    async def send_template_button(self, interaction: discord.Interaction, button: ui.Button):
        ticket = self.bot.ticket_manager.get_or_recover_ticket(interaction.channel_id, channel_obj=interaction.channel)
        if not ticket:
            await interaction.response.send_message("❌ No active ticket found.", ephemeral=True)
            return

        from support_templates_system import SendTemplateSelectView
        view = SendTemplateSelectView(self.bot, ticket["id"])
        await interaction.response.send_message("Choose an official support template to dispatch directly to the member's DMs:", view=view, ephemeral=True)


class TransferSectionSelect(ui.Select):
    """Dropdown for staff to transfer a ticket to another section."""

    def __init__(self, bot, ticket_id: int):
        self.bot = bot
        self.ticket_id = ticket_id
        options = [
            discord.SelectOption(label=sec, value=sec)
            for sec in config.TICKET_SECTIONS
        ]
        super().__init__(
            placeholder="Choose target category...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        new_section = self.values[0]
        self.bot.ticket_manager.update_section(self.ticket_id, new_section)

        # Notify channel
        transfer_embed = discord.Embed(
            title="🔄 Ticket Transferred",
            description=f"Ticket #{self.ticket_id} transferred to **{new_section}** by {interaction.user.mention}.",
            color=0x00A2FF
        )
        await interaction.channel.send(embed=transfer_embed)
        await interaction.response.edit_message(content=f"✅ Transferred to **{new_section}**.", view=None)


class TransferSectionView(ui.View):
    def __init__(self, bot, ticket_id: int):
        super().__init__(timeout=60)
        self.add_item(TransferSectionSelect(bot, ticket_id))


class ConfirmCloseView(ui.View):
    """Confirmation view to close a ticket."""

    def __init__(self, bot, ticket):
        super().__init__(timeout=60)
        self.bot = bot
        self.ticket = ticket

    @ui.button(label="Yes, Close Ticket", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm_close(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        await self.bot.close_support_ticket(self.ticket, interaction.channel, closed_by=interaction.user)

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel_close(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="Ticket closing cancelled.", view=None)


class TicketRatingView(ui.View):
    """Experience rating view displayed when a ticket closes (1-5 stars)."""

    def __init__(self, bot, ticket_id: int, user_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.ticket_id = ticket_id
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the ticket creator can rate this experience.", ephemeral=True)
            return False
        return True

    @ui.button(label="1 ⭐", style=discord.ButtonStyle.secondary, row=0)
    async def rate_1(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(TicketFeedbackModal(self.bot, self.ticket_id, 1, self))

    @ui.button(label="2 ⭐⭐", style=discord.ButtonStyle.secondary, row=0)
    async def rate_2(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(TicketFeedbackModal(self.bot, self.ticket_id, 2, self))

    @ui.button(label="3 ⭐⭐⭐", style=discord.ButtonStyle.primary, row=0)
    async def rate_3(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(TicketFeedbackModal(self.bot, self.ticket_id, 3, self))

    @ui.button(label="4 ⭐⭐⭐⭐", style=discord.ButtonStyle.primary, row=0)
    async def rate_4(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(TicketFeedbackModal(self.bot, self.ticket_id, 4, self))

    @ui.button(label="5 ⭐⭐⭐⭐⭐", style=discord.ButtonStyle.success, row=0)
    async def rate_5(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(TicketFeedbackModal(self.bot, self.ticket_id, 5, self))


class TicketFeedbackModal(ui.Modal):
    """Optional written feedback modal after selecting star rating."""

    feedback_input = ui.TextInput(
        label="Additional Feedback (Optional)",
        placeholder="How was the AI or staff response? What could we do better?",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False
    )

    def __init__(self, bot, ticket_id: int, rating: int, rating_view: Optional[TicketRatingView] = None):
        super().__init__(title=f"Rate Your Experience ({rating} Stars)")
        self.bot = bot
        self.ticket_id = ticket_id
        self.rating = rating
        self.rating_view = rating_view

    async def on_submit(self, interaction: discord.Interaction):
        feedback_text = self.feedback_input.value.strip()

        # Save rating to SQLite
        self.bot.ticket_manager.save_rating(
            ticket_id=self.ticket_id,
            user_id=interaction.user.id,
            rating=self.rating,
            feedback=feedback_text
        )

        stars_str = "⭐" * self.rating
        thank_you_embed = discord.Embed(
            title="⭐ Thank You for Your Feedback!",
            description=(
                f"You rated Ticket **#{self.ticket_id}**: **{stars_str} ({self.rating}/5 Stars)**\n\n"
                f"Your feedback helps us continuously improve our AI support and staff assistance!"
            ),
            color=0x57F287
        )
        if feedback_text:
            thank_you_embed.add_field(name="💬 Your Comments", value=feedback_text, inline=False)

        await interaction.response.edit_message(embed=thank_you_embed, view=None)

        # Post rating update to escalated tickets channel
        guild = interaction.guild or self.bot.get_primary_guild()
        if guild:
            escalated_ch = await self.bot.get_escalated_channel(guild)
            if escalated_ch:
                staff_rating_embed = discord.Embed(
                    title=f"📊 Experience Rating: Ticket #{self.ticket_id}",
                    description=f"{interaction.user.mention} rated their experience **{stars_str} ({self.rating}/5 Stars)**.",
                    color=0x00A2FF,
                    timestamp=discord.utils.utcnow()
                )
                if feedback_text:
                    staff_rating_embed.add_field(name="Feedback", value=feedback_text, inline=False)
                staff_rating_embed.set_footer(text=f"User ID: {interaction.user.id}")
                try:
                    await escalated_ch.send(embed=staff_rating_embed)
                except Exception as e:
                    logger.debug(f"Could not send rating log to escalated channel: {e}")


class InternalNoteModal(ui.Modal):
    """Modal for staff to save private notes inside the ticket channel."""

    note_input = ui.TextInput(
        label="Internal Staff Note",
        placeholder="Visible only to staff in this channel (never sent to user's DMs)...",
        style=discord.TextStyle.paragraph,
        max_length=1500,
        required=True
    )

    def __init__(self, bot, ticket_id: int):
        super().__init__(title="Add Internal Staff Note")
        self.bot = bot
        self.ticket_id = ticket_id

    async def on_submit(self, interaction: discord.Interaction):
        note_text = self.note_input.value.strip()
        self.bot.ticket_manager.add_message(
            self.ticket_id,
            interaction.user.id,
            "internal_note",
            note_text,
            sender_name=interaction.user.display_name
        )
        note_embed = discord.Embed(
            title="📝 Internal Staff Note",
            description=note_text,
            color=0xFEE75C,
            timestamp=discord.utils.utcnow()
        )
        note_embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        note_embed.set_footer(text="Staff Only • Excluded from user DMs & transcripts")
        await interaction.channel.send(embed=note_embed)
        await interaction.response.send_message("✅ Internal note added.", ephemeral=True)


class SendSuggestedReplyView(ui.View):
    """Preview controls for AI suggested staff response."""

    def __init__(self, bot, ticket: dict, suggested_text: str):
        super().__init__(timeout=180)
        self.bot = bot
        self.ticket = ticket
        self.suggested_text = suggested_text

    @ui.button(label="Send to Member", style=discord.ButtonStyle.success, emoji="✉️")
    async def send_btn(self, interaction: discord.Interaction, button: ui.Button):
        target_user = self.bot.get_user(self.ticket["user_id"]) or await self.bot.fetch_user(self.ticket["user_id"])
        if target_user:
            try:
                staff_embed = discord.Embed(
                    description=self.suggested_text,
                    color=0x57F287,
                    timestamp=discord.utils.utcnow()
                )
                staff_embed.set_author(name=f"Staff Response ({interaction.user.display_name})", icon_url=interaction.user.display_avatar.url)
                dm = await target_user.create_dm()
                await dm.send(embed=staff_embed)

                self.bot.ticket_manager.add_message(
                    self.ticket["id"],
                    interaction.user.id,
                    "staff",
                    self.suggested_text,
                    sender_name=interaction.user.display_name
                )
                await interaction.channel.send(
                    f"✉️ **Staff Reply sent by {interaction.user.mention}:**\n> {self.suggested_text}"
                )
                await interaction.response.edit_message(content="✅ **Delivered!** Reply sent directly to member's DMs.", embed=None, view=None)
            except discord.Forbidden:
                await interaction.response.send_message("❌ Member has DMs closed.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Error sending: {e}", ephemeral=True)

    @ui.button(label="Edit Before Sending", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_btn(self, interaction: discord.Interaction, button: ui.Button):
        modal = EditSuggestedReplyModal(self.bot, self.ticket, self.suggested_text)
        await interaction.response.send_modal(modal)

    @ui.button(label="Dismiss", style=discord.ButtonStyle.secondary, emoji="❌")
    async def dismiss_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="🗑️ Suggested reply dismissed.", embed=None, view=None)


class EditSuggestedReplyModal(ui.Modal):
    """Modal to edit the AI suggested draft before dispatching to member."""

    def __init__(self, bot, ticket: dict, initial_text: str):
        super().__init__(title="Edit Staff Reply")
        self.bot = bot
        self.ticket = ticket
        self.reply_input = ui.TextInput(
            label="Message to Member",
            default=initial_text[:1500],
            style=discord.TextStyle.paragraph,
            max_length=1500,
            required=True
        )
        self.add_item(self.reply_input)

    async def on_submit(self, interaction: discord.Interaction):
        content = self.reply_input.value.strip()
        target_user = self.bot.get_user(self.ticket["user_id"]) or await self.bot.fetch_user(self.ticket["user_id"])
        if target_user:
            try:
                staff_embed = discord.Embed(
                    description=content,
                    color=0x57F287,
                    timestamp=discord.utils.utcnow()
                )
                staff_embed.set_author(name=f"Staff Response ({interaction.user.display_name})", icon_url=interaction.user.display_avatar.url)
                dm = await target_user.create_dm()
                await dm.send(embed=staff_embed)

                self.bot.ticket_manager.add_message(
                    self.ticket["id"],
                    interaction.user.id,
                    "staff",
                    content,
                    sender_name=interaction.user.display_name
                )
                await interaction.channel.send(
                    f"✉️ **Staff Reply sent by {interaction.user.mention}:**\n> {content}"
                )
                await interaction.response.send_message("✅ Edited reply sent to member's DMs!", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ Member has DMs closed.", ephemeral=True)


class CannedReplySelectView(ui.View):
    """Select menu for dispatching canned response templates to the member."""

    def __init__(self, bot, ticket: dict, canned_list: list):
        super().__init__(timeout=120)
        self.bot = bot
        self.ticket = ticket
        options = [
            discord.SelectOption(
                label=f"/{c['shortcut']}",
                description=c['title'][:90],
                value=c['shortcut']
            )
            for c in canned_list[:25]
        ]
        select = ui.Select(placeholder="Select a canned response template to dispatch...", options=options)
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        shortcut = interaction.data["values"][0]
        canned = self.bot.ticket_manager.get_canned_response(shortcut)
        if not canned:
            await interaction.response.send_message("❌ Canned response not found.", ephemeral=True)
            return

        target_user = self.bot.get_user(self.ticket["user_id"]) or await self.bot.fetch_user(self.ticket["user_id"])
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

                self.bot.ticket_manager.add_message(
                    self.ticket["id"],
                    interaction.user.id,
                    "staff",
                    canned["content"],
                    sender_name=interaction.user.display_name
                )
                await interaction.channel.send(
                    f"📁 **Canned Response `/{shortcut}` dispatched by {interaction.user.mention}:**\n> {canned['content']}"
                )
                await interaction.response.edit_message(content=f"✅ Canned response `/{shortcut}` dispatched to member!", view=None)
            except discord.Forbidden:
                await interaction.response.send_message("❌ Member has DMs closed.", ephemeral=True)
