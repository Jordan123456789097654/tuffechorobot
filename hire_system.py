import discord
from discord import ui
import sqlite3
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger("HireSystem")
DB_PATH = "verifications.db"

def init_hire_db():
    """Ensures the hire_offers table exists in verifications.db."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hire_offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                member_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                issuer_id INTEGER NOT NULL,
                origin_channel_id INTEGER,
                role_name TEXT NOT NULL,
                status TEXT DEFAULT 'pending', -- 'pending', 'accepted', 'declined'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

init_hire_db()

def create_hire_offer(
    guild_id: int,
    member_id: int,
    role_id: int,
    issuer_id: int,
    origin_channel_id: Optional[int],
    role_name: str
) -> int:
    """Creates a new employment offer and returns its database ID."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO hire_offers (guild_id, member_id, role_id, issuer_id, origin_channel_id, role_name, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending');
        """, (guild_id, member_id, role_id, issuer_id, origin_channel_id or 0, role_name))
        conn.commit()
        return cursor.lastrowid

def get_hire_offer(offer_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves an offer by its ID."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hire_offers WHERE id = ?;", (offer_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def update_hire_offer_status(offer_id: int, status: str) -> bool:
    """Updates the status of an offer (accepted, declined)."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE hire_offers SET status = ? WHERE id = ?;", (status, offer_id))
        conn.commit()
        return cursor.rowcount > 0


class HireOfferView(ui.View):
    """Interactive DM view for candidate to Accept or Decline Echo Technologies employment offer."""

    def __init__(self, bot, offer_id: int, member_id: int):
        super().__init__(timeout=86400 * 7) # 7-day offer lifespan
        self.bot = bot
        self.offer_id = offer_id
        self.member_id = member_id

        # Clean, ultra-short custom_ids (e.g. hire_acc:1, well below 100 char limit)
        self.accept_button.custom_id = f"hire_acc:{offer_id}"
        self.decline_button.custom_id = f"hire_dec:{offer_id}"

    @ui.button(
        label="Accept Offer",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="hire_acc_btn"
    )
    async def accept_button(self, interaction: discord.Interaction, button: ui.Button):
        await handle_hire_action(
            bot=self.bot,
            interaction=interaction,
            offer_id=self.offer_id,
            action="accept"
        )

    @ui.button(
        label="Decline Offer",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id="hire_dec_btn"
    )
    async def decline_button(self, interaction: discord.Interaction, button: ui.Button):
        await handle_hire_action(
            bot=self.bot,
            interaction=interaction,
            offer_id=self.offer_id,
            action="decline"
        )


async def handle_hire_action(
    bot,
    interaction: discord.Interaction,
    offer_id: int,
    action: str
):
    """Processes employment offer acceptance or denial, assigns roles, and notifies stakeholders."""
    offer = get_hire_offer(offer_id)
    if not offer:
        await interaction.response.send_message(
            "❌ This employment offer was not found or has expired.",
            ephemeral=True
        )
        return

    # Ensure only the intended candidate can respond
    if interaction.user.id != offer["member_id"]:
        await interaction.response.send_message(
            "❌ This offer was addressed to another user and can only be accepted or declined by them.",
            ephemeral=True
        )
        return

    # Check if already processed
    if offer["status"] != "pending":
        await interaction.response.send_message(
            f"ℹ️ This offer has already been marked as **{offer['status'].capitalize()}**.",
            ephemeral=True
        )
        return

    guild_id = offer["guild_id"]
    member_id = offer["member_id"]
    role_id = offer["role_id"]
    issuer_id = offer["issuer_id"]
    origin_channel_id = offer["origin_channel_id"]

    guild = bot.get_guild(guild_id)
    if not guild:
        try:
            guild = await bot.fetch_guild(guild_id)
        except Exception as e:
            logger.error(f"Could not fetch guild {guild_id}: {e}")
            await interaction.response.send_message("❌ Server not found. Please contact staff directly.", ephemeral=True)
            return

    member = guild.get_member(member_id)
    if not member:
        try:
            member = await guild.fetch_member(member_id)
        except Exception:
            member = None

    if not member:
        await interaction.response.send_message(
            f"❌ You are no longer in the **{guild.name}** server.",
            ephemeral=True
        )
        return

    role = guild.get_role(role_id)
    if not role:
        await interaction.response.send_message(
            f"❌ The offered role could not be found in **{guild.name}**. It may have been renamed or deleted.",
            ephemeral=True
        )
        return

    issuer = bot.get_user(issuer_id)
    if not issuer:
        try:
            issuer = await bot.fetch_user(issuer_id)
        except Exception:
            issuer = None

    issuer_tag = issuer.mention if issuer else f"<@{issuer_id}>"

    # ==========================
    # ACTION: ACCEPT OFFER
    # ==========================
    if action == "accept":
        # Check bot permissions
        if role >= guild.me.top_role:
            await interaction.response.send_message(
                f"⚠️ The bot lacks permission to assign the **{role.name}** role (role is higher than the bot's highest role). Please inform server administrators.",
                ephemeral=True
            )
            return

        # Assign role
        try:
            await member.add_roles(role, reason=f"Accepted Echo Technologies employment offer issued by {issuer.name if issuer else issuer_id}")
            logger.info(f"Assigned role {role.name} ({role.id}) to {member.name} ({member.id}) following accepted offer #{offer_id}.")
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Bot has insufficient permissions to grant this role. Please reach out to server administrators.",
                ephemeral=True
            )
            return
        except Exception as e:
            logger.error(f"Error assigning role {role.id} to {member.id}: {e}")
            await interaction.response.send_message(f"❌ An error occurred while assigning the role: {e}", ephemeral=True)
            return

        # Update database status
        update_hire_offer_status(offer_id, "accepted")

        # Build Acceptance DM Embed
        accept_embed = discord.Embed(
            title="🎉 Welcome to the Team • Offer Accepted!",
            description=(
                f"# Echo Technologies\n"
                f"### Official Role Appointment Confirmation\n\n"
                f"Dear **{member.display_name}**,\n\n"
                f"Congratulations! We are thrilled to confirm that you have **accepted** the offer to join our team as a **{role.name}**!\n\n"
                f"✅ **Status:** **Offer Accepted & Processed**\n"
                f"🎖️ **Assigned Role:** {role.mention} (`{role.name}`)\n"
                f"🏢 **Organization:** **Echo Technologies** (`{guild.name}`)\n"
                f"🤝 **Appointed By:** {issuer_tag}\n"
                f"📅 **Effective Date:** <t:{int(discord.utils.utcnow().timestamp())}:F>\n\n"
                f"Your server permissions and staff access in **{guild.name}** have been activated. "
                f"Please check out the server channels for directives, resources, and team communication.\n\n"
                f"We are excited to build the future with you! 🚀"
            ),
            color=0x57F287,
            timestamp=discord.utils.utcnow()
        )
        if guild.icon:
            accept_embed.set_thumbnail(url=guild.icon.url)
        accept_embed.set_footer(text="Echo Technologies • Human Resources & Talent System")

        await interaction.response.edit_message(embed=accept_embed, view=None)

        # Notify Origin Channel
        if origin_channel_id and origin_channel_id != 0:
            origin_ch = bot.get_channel(origin_channel_id)
            if origin_ch and isinstance(origin_ch, discord.TextChannel):
                try:
                    staff_notify = discord.Embed(
                        title="🎉 Employment Offer Accepted!",
                        description=(
                            f"{member.mention} (`{member.name}`) has officially **accepted** the offer for **{role.mention}**!\n\n"
                            f"• **Role Assigned:** {role.mention}\n"
                            f"• **Offered By:** {issuer_tag}\n"
                            f"• **Timestamp:** <t:{int(discord.utils.utcnow().timestamp())}:R>"
                        ),
                        color=0x57F287
                    )
                    await origin_ch.send(embed=staff_notify)
                except Exception as e:
                    logger.warning(f"Could not notify origin channel of acceptance: {e}")

        # Notify Hiring Staff via DM
        if issuer and issuer.id != member.id:
            try:
                issuer_dm = await issuer.create_dm()
                notify_embed = discord.Embed(
                    title="🎉 Candidate Accepted Offer",
                    description=(
                        f"Great news! **{member.display_name}** (`@{member.name}`) has **accepted** your employment offer for **{role.name}** in **{guild.name}**.\n\n"
                        f"The role has been assigned automatically."
                    ),
                    color=0x57F287,
                    timestamp=discord.utils.utcnow()
                )
                await issuer_dm.send(embed=notify_embed)
            except Exception:
                pass

    # ==========================
    # ACTION: DECLINE OFFER
    # ==========================
    elif action == "decline":
        # Update database status
        update_hire_offer_status(offer_id, "declined")

        decline_embed = discord.Embed(
            title="Employment Offer Declined",
            description=(
                f"# Echo Technologies\n"
                f"### Offer Decision Confirmation\n\n"
                f"Dear **{member.display_name}**,\n\n"
                f"Thank you for informing us of your decision. You have respectfully **declined** the offer for the position of **{role.name}** at **Echo Technologies**.\n\n"
                f"We genuinely appreciate your time and consideration. If you ever have any questions or wish to explore opportunities with us in the future, please feel free to reach out to our management team.\n\n"
                f"We wish you all the best in your endeavors! ✨"
            ),
            color=0xED4245,
            timestamp=discord.utils.utcnow()
        )
        if guild.icon:
            decline_embed.set_thumbnail(url=guild.icon.url)
        decline_embed.set_footer(text="Echo Technologies • Human Resources & Talent System")

        await interaction.response.edit_message(embed=decline_embed, view=None)

        # Notify Origin Channel
        if origin_channel_id and origin_channel_id != 0:
            origin_ch = bot.get_channel(origin_channel_id)
            if origin_ch and isinstance(origin_ch, discord.TextChannel):
                try:
                    staff_notify = discord.Embed(
                        title="ℹ️ Employment Offer Declined",
                        description=(
                            f"{member.mention} (`{member.name}`) has **declined** the offer for **{role.mention}**.\n\n"
                            f"• **Offered By:** {issuer_tag}\n"
                            f"• **Timestamp:** <t:{int(discord.utils.utcnow().timestamp())}:R>"
                        ),
                        color=0xED4245
                    )
                    await origin_ch.send(embed=staff_notify)
                except Exception as e:
                    logger.warning(f"Could not notify origin channel of denial: {e}")

        # Notify Hiring Staff via DM
        if issuer and issuer.id != member.id:
            try:
                issuer_dm = await issuer.create_dm()
                notify_embed = discord.Embed(
                    title="ℹ️ Candidate Declined Offer",
                    description=(
                        f"**{member.display_name}** (`@{member.name}`) has **declined** your employment offer for **{role.name}** in **{guild.name}**."
                    ),
                    color=0xED4245,
                    timestamp=discord.utils.utcnow()
                )
                await issuer_dm.send(embed=notify_embed)
            except Exception:
                pass
