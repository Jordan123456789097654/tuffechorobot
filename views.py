import discord
from discord import ui
import time
from typing import Optional

from safe_words import generate_safe_verification_code
import config

class VerificationLaunchView(ui.View):
    """Persistent view attached to the public verification panel embed."""

    def __init__(self, roblox_api, db):
        super().__init__(timeout=None)
        self.roblox_api = roblox_api
        self.db = db

    @ui.button(
        label="Verify Roblox Account",
        style=discord.ButtonStyle.primary,
        emoji="🛡️",
        custom_id="roblox_verify_launch_button"
    )
    async def verify_button_callback(self, interaction: discord.Interaction, button: ui.Button):
        # Open modal popup asking for Roblox username
        modal = RobloxUsernameModal(self.roblox_api, self.db)
        await interaction.response.send_modal(modal)


class RobloxUsernameModal(ui.Modal, title="Roblox Verification"):
    """Modal forum popup asking user for their Roblox username."""

    username_input = ui.TextInput(
        label="Roblox Username",
        placeholder="Enter your exact Roblox username (e.g. Builderman)",
        min_length=3,
        max_length=20,
        required=True
    )

    def __init__(self, roblox_api, db):
        super().__init__()
        self.roblox_api = roblox_api
        self.db = db

    async def on_submit(self, interaction: discord.Interaction):
        # Defer immediately to allow async API calls (avoids Discord 3s timeout)
        await interaction.response.defer(ephemeral=True)

        input_username = self.username_input.value.strip()

        # Check existing verification
        existing = self.db.get_by_discord_id(interaction.user.id)
        if existing and existing["roblox_username"].lower() == input_username.lower():
            embed = discord.Embed(
                title="ℹ️ Already Verified",
                description=f"You are already verified as **{existing['roblox_display_name']}** (`@{existing['roblox_username']}`).",
                color=0x5865F2
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # 1. Look up user on Roblox
        user_info = await self.roblox_api.get_user_by_username(input_username)
        if not user_info:
            error_embed = discord.Embed(
                title="❌ Roblox Account Not Found",
                description=(
                    f"We could not find a Roblox account matching **{input_username}**.\n\n"
                    "• Double-check spelling and capitalization.\n"
                    "• Ensure you provided your **Username** (not only display name)."
                ),
                color=0xED4245
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
            return

        roblox_id = user_info["id"]
        username = user_info["name"]
        display_name = user_info.get("displayName", username)

        # 2. Get user details (creation date, bio) and avatar thumbnail
        details = await self.roblox_api.get_user_details(roblox_id)
        headshot_url = await self.roblox_api.get_user_headshot(roblox_id)

        # Parse account creation date
        joined_str = "Unknown"
        joined_ts = None
        if details and "created" in details:
            created_dt = self.roblox_api.parse_creation_date(details["created"])
            if created_dt:
                joined_ts = int(created_dt.timestamp())
                joined_str = f"<t:{joined_ts}:D> (<t:{joined_ts}:R>)"

        # 3. Generate censorship-proof code (guaranteed not tagged by Roblox filters)
        safe_code = generate_safe_verification_code(4)

        # 4. Build verification prompt embed
        embed = discord.Embed(
            title="🛡️ Roblox Account Verification",
            description=(
                f"Confirm ownership of the Roblox account below by adding the "
                f"safe verification code to your profile bio."
            ),
            color=0x5865F2
        )

        embed.add_field(
            name="👤 Roblox Username",
            value=f"**{display_name}** (`@{username}`)",
            inline=True
        )
        embed.add_field(
            name="🆔 Roblox ID",
            value=f"`{roblox_id}`",
            inline=True
        )
        embed.add_field(
            name="📅 Joined Roblox",
            value=joined_str,
            inline=False
        )

        embed.add_field(
            name="🔑 Verification Code (Put this in your Bio)",
            value=(
                f"```\n{safe_code}\n```\n"
                f"*Tap or copy the phrase above (Roblox safe, will not be censored with `####`)*"
            ),
            inline=False
        )

        instructions = (
            f"1. Copy the code above: `{safe_code}`\n"
            f"2. Go to your **[Roblox Profile](https://www.roblox.com/users/{roblox_id}/profile)**.\n"
            "3. Paste the code into your **About / Bio** section and click **Save**.\n"
            "4. Return here and click **Check Verification** below!\n\n"
            "*(You can safely remove the code from your bio once verified)*"
        )
        embed.add_field(name="📋 Step-by-Step Instructions", value=instructions, inline=False)

        if headshot_url:
            embed.set_thumbnail(url=headshot_url)

        embed.set_footer(text="Verification code expires in 15 minutes • Safe & Uncensored")

        # 5. Attach interactive check view
        check_view = VerificationCheckView(
            roblox_api=self.roblox_api,
            db=self.db,
            user_id=interaction.user.id,
            roblox_id=roblox_id,
            username=username,
            display_name=display_name,
            code=safe_code,
            headshot_url=headshot_url
        )

        await interaction.followup.send(embed=embed, view=check_view, ephemeral=True)


class VerificationCheckView(ui.View):
    """View shown during the verification step with Check and Cancel buttons."""

    def __init__(self, roblox_api, db, user_id: int, roblox_id: int, username: str, display_name: str, code: str, headshot_url: Optional[str]):
        super().__init__(timeout=900)  # 15 minute expiration
        self.roblox_api = roblox_api
        self.db = db
        self.target_user_id = user_id
        self.roblox_id = roblox_id
        self.username = username
        self.display_name = display_name
        self.code = code
        self.headshot_url = headshot_url

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target_user_id:
            await interaction.response.send_message("❌ This verification prompt is not for you.", ephemeral=True)
            return False
        return True

    @ui.button(label="Check Verification", style=discord.ButtonStyle.success, emoji="✅")
    async def check_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)

        # Fetch latest profile bio from Roblox API
        details = await self.roblox_api.get_user_details(self.roblox_id)
        if not details:
            await interaction.followup.send(
                "⚠️ Could not contact Roblox servers to check your bio. Please try again in a few seconds.",
                ephemeral=True
            )
            return

        current_bio = (details.get("description") or "").lower()
        required_words = self.code.lower().split()

        # Check if code or all required words exist in bio
        is_verified = (self.code.lower() in current_bio) or all(word in current_bio for word in required_words)

        if is_verified:
            # 1. Save link in persistent database
            self.db.link_user(
                discord_id=interaction.user.id,
                roblox_id=self.roblox_id,
                username=self.username,
                display_name=self.display_name
            )

            # 2. Assign verified role if configured
            role_assigned_msg = ""
            if config.VERIFIED_ROLE_ID and interaction.guild:
                role = interaction.guild.get_role(config.VERIFIED_ROLE_ID)
                if role:
                    try:
                        await interaction.user.add_roles(role, reason=f"Roblox verified as {self.username}")
                        role_assigned_msg = f"\n• Granted role: **{role.name}**"
                    except discord.Forbidden:
                        role_assigned_msg = "\n• *(Bot lacks permissions to assign the verified role)*"
                    except Exception as e:
                        role_assigned_msg = f"\n• *(Role assignment note: {e})*"

            # Remove unverified role (1556000025216163961) if present
            unverified_removed_msg = ""
            if config.UNVERIFIED_ROLE_ID and interaction.guild:
                unverified_role = interaction.guild.get_role(config.UNVERIFIED_ROLE_ID)
                if unverified_role and unverified_role in interaction.user.roles:
                    try:
                        await interaction.user.remove_roles(unverified_role, reason=f"Roblox verified as {self.username}")
                        unverified_removed_msg = f"\n• Removed unverified role: **{unverified_role.name}**"
                    except Exception:
                        pass

            # 3. Update server nickname if configured
            nick_updated_msg = ""
            if config.UPDATE_NICKNAME and interaction.guild:
                try:
                    await interaction.user.edit(nick=self.username, reason="Roblox verification sync")
                    nick_updated_msg = f"\n• Updated nickname to: **{self.username}**"
                except discord.Forbidden:
                    nick_updated_msg = "\n• *(Bot lacks permission to update your server nickname)*"
                except Exception:
                    pass

            # 3.5 Dispatch celebratory announcement to #welcome
            try:
                import asyncio
                from welcome_system import send_verification_announcement
                rbx_info = {
                    "roblox_id": self.roblox_id,
                    "roblox_username": self.username,
                    "roblox_display_name": self.display_name
                }
                asyncio.create_task(send_verification_announcement(interaction.client, interaction.user, rbx_info))
            except Exception:
                pass

            # 4. Display success embed
            success_embed = discord.Embed(
                title="🎉 Verification Successful!",
                description=(
                    f"Welcome, **{interaction.user.mention}**! Your Discord account has been "
                    f"successfully linked to your Roblox profile."
                ),
                color=0x57F287
            )
            success_embed.add_field(name="👤 Roblox Username", value=f"**{self.display_name}** (`@{self.username}`)", inline=True)
            success_embed.add_field(name="🆔 Roblox ID", value=f"`{self.roblox_id}`", inline=True)

            status_notes = f"• Saved verification link to database{role_assigned_msg}{unverified_removed_msg}{nick_updated_msg}"
            success_embed.add_field(name="📌 Status", value=status_notes, inline=False)
            success_embed.add_field(
                name="💡 Next Step",
                value="You may now remove the verification code from your Roblox profile About section if you wish.",
                inline=False
            )

            if self.headshot_url:
                success_embed.set_thumbnail(url=self.headshot_url)

            success_embed.set_footer(text="Roblox Verification Complete")

            # Disable buttons
            for item in self.children:
                item.disabled = True

            await interaction.edit_original_response(embed=success_embed, view=None)

        else:
            # Code not found
            bio_preview = details.get("description", "").strip()
            if not bio_preview:
                preview_text = "*(Your bio is currently empty)*"
            elif len(bio_preview) > 100:
                preview_text = f"\"{bio_preview[:100]}...\""
            else:
                preview_text = f"\"{bio_preview}\""

            fail_embed = discord.Embed(
                title="⚠️ Code Not Found in Roblox Bio",
                description=(
                    f"We could not find the code `{self.code}` in your Roblox profile bio yet!\n\n"
                    f"**Current Bio Detected:**\n{preview_text}\n\n"
                    "**Troubleshooting Checklist:**\n"
                    "1. Did you click **Save** after pasting the code on Roblox?\n"
                    "2. Make sure you edited the **About** section on the correct account: "
                    f"**[@{self.username}](https://www.roblox.com/users/{self.roblox_id}/profile)**.\n"
                    "3. Wait 5-10 seconds for Roblox cache to refresh, then click **Check Verification** again."
                ),
                color=0xFEE75C
            )
            await interaction.followup.send(embed=fail_embed, ephemeral=True)

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        cancel_embed = discord.Embed(
            title="🚫 Verification Cancelled",
            description="The verification process has been cancelled. You can click **Verify Roblox Account** anytime to restart.",
            color=0x747F8D
        )
        await interaction.response.edit_message(embed=cancel_embed, view=None)
