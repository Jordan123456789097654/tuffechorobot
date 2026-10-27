import io
import discord
from discord import app_commands
from discord.ui import Modal, TextInput, View, Button
from typing import Optional

from license_system import (
    create_product,
    issue_license,
    get_license,
    revoke_license,
    get_all_products,
    list_licenses_for_product,
    generate_roblox_loader_script
)

class CreateProductModal(Modal, title="Create RetailNetwork Product"):
    product_name = TextInput(
        label="Product Name",
        placeholder="e.g. Self-Checkout Register System V2",
        required=True,
        max_length=80
    )
    product_version = TextInput(
        label="Product Version",
        placeholder="e.g. 1.0.0",
        default="1.0.0",
        required=False,
        max_length=20
    )
    product_desc = TextInput(
        label="Product Description",
        placeholder="Describe what this asset or system does...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500
    )
    allowed_place = TextInput(
        label="Allowed Roblox Place ID (Optional)",
        placeholder="Leave 0 or blank for any place",
        default="0",
        required=False,
        max_length=25
    )
    allowed_group = TextInput(
        label="Allowed Roblox Group ID (Optional)",
        placeholder="Leave 0 or blank for any group",
        default="0",
        required=False,
        max_length=25
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        name = self.product_name.value.strip()
        ver = self.product_version.value.strip() or "1.0.0"
        desc = self.product_desc.value.strip() or "Standard RetailNetwork Product"

        try:
            place_id = int(self.allowed_place.value.strip() or "0")
        except ValueError:
            place_id = 0

        try:
            group_id = int(self.allowed_group.value.strip() or "0")
        except ValueError:
            group_id = 0

        # Create or update product and issue the first license key
        try:
            create_product(name, desc, ver, interaction.user.id)
        except Exception:
            pass # Already exists, we can still issue new license for it

        license_info = issue_license(
            product_name=name,
            created_by=interaction.user.id,
            allowed_place_id=place_id,
            allowed_group_id=group_id
        )

        key = license_info["license_key"]
        script_code = generate_roblox_loader_script(name, key, place_id, group_id)

        embed = discord.Embed(
            title="🛡️ Product License Created • RetailNetwork Security",
            description=(
                f"Your product **{name}** has been registered and a secure license key was generated!\n\n"
                f"**🔑 License Key:**\n```fix\n{key}\n```\n"
                f"**📦 Product Name:** `{name}` (v{ver})\n"
                f"**🏰 Bound Place ID:** `{place_id if place_id > 0 else 'Any Place (Universal)'}`\n"
                f"**👥 Bound Group ID:** `{group_id if group_id > 0 else 'Any Group (Universal)'}`\n"
                f"**🔒 Status:** `Active`\n\n"
                f"### 📜 How to protect your Roblox Product:\n"
                f"1. Open Roblox Studio and open your game / model.\n"
                f"2. Insert a **Server Script** under `ServerScriptService` (e.g., named `RetailNetworkLoader`).\n"
                f"3. Copy & paste the code from the attached file `RetailNetwork_Loader.lua`.\n"
                f"4. Ensure **Allow HTTP Requests** is enabled in `Game Settings -> Security`."
            ),
            color=0x2ECC71,
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text="RetailNetwork Anti-Leak & Licensing Engine")

        # Create file attachment with the lua script
        script_file = discord.File(
            fp=io.BytesIO(script_code.encode("utf-8")),
            filename=f"RetailNetwork_Loader_{name.replace(' ', '_')}.lua"
        )

        await interaction.followup.send(embed=embed, file=script_file, ephemeral=True)


def register_license_commands(bot):
    """Registers product licensing slash commands."""

    @bot.tree.command(name="create-product", description="Register a new Roblox product, generate a license key, and get the loader script.")
    async def create_product_cmd(interaction: discord.Interaction):
        # Admin / Dev check
        await interaction.response.send_modal(CreateProductModal())

    @bot.tree.command(name="issue-license", description="Generate a new license key for an existing RetailNetwork product.")
    @app_commands.describe(
        product_name="Name of the existing product",
        member="Optional buyer / recipient Discord user",
        place_id="Optional Place ID bound to this license (0 for any)",
        group_id="Optional Group ID bound to this license (0 for any)"
    )
    async def issue_license_cmd(
        interaction: discord.Interaction,
        product_name: str,
        member: Optional[discord.Member] = None,
        place_id: Optional[int] = 0,
        group_id: Optional[int] = 0
    ):
        await interaction.response.defer(ephemeral=True)

        owner_id = member.id if member else interaction.user.id
        pid = place_id or 0
        gid = group_id or 0

        license_info = issue_license(
            product_name=product_name,
            created_by=interaction.user.id,
            owner_discord_id=owner_id,
            allowed_place_id=pid,
            allowed_group_id=gid
        )

        key = license_info["license_key"]
        script_code = generate_roblox_loader_script(product_name, key, pid, gid)

        embed = discord.Embed(
            title="🔑 License Issued • RetailNetwork Security",
            description=(
                f"A new license key has been generated for **{product_name}**!\n\n"
                f"**🔑 License Key:**\n```fix\n{key}\n```\n"
                f"**👤 Assigned Licensee:** {member.mention if member else 'None (Unassigned)'}\n"
                f"**🏰 Bound Place ID:** `{pid if pid > 0 else 'Universal (Any)'}`\n"
                f"**👥 Bound Group ID:** `{gid if gid > 0 else 'Universal (Any)'}`\n"
                f"**🔒 Status:** `Active`"
            ),
            color=0x3498DB,
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text="RetailNetwork Anti-Leak & Licensing Engine")

        script_file = discord.File(
            fp=io.BytesIO(script_code.encode("utf-8")),
            filename=f"RetailNetwork_Loader_{product_name.replace(' ', '_')}.lua"
        )

        await interaction.followup.send(embed=embed, file=script_file, ephemeral=True)

    @bot.tree.command(name="check-license", description="Check the status and details of a RetailNetwork license key.")
    @app_commands.describe(license_key="The RN-XXXX-XXXX-XXXX-XXXX license key")
    async def check_license_cmd(interaction: discord.Interaction, license_key: str):
        await interaction.response.defer(ephemeral=True)
        lic = get_license(license_key)
        if not lic:
            await interaction.followup.send(f"❌ License key `{license_key}` was not found in the database.", ephemeral=True)
            return

        status_emoji = "✅" if lic["status"] == "active" else "❌"
        owner_str = f"<@{lic['owner_discord_id']}>" if lic["owner_discord_id"] else "None"
        last_ver = lic["last_verified_at"] or "Never"

        embed = discord.Embed(
            title=f"🔎 License Audit • {lic['license_key']}",
            color=0x2ECC71 if lic["status"] == "active" else 0xED4245,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="📦 Product", value=f"**{lic['product_name']}**", inline=True)
        embed.add_field(name="🔒 Status", value=f"{status_emoji} **{lic['status'].upper()}**", inline=True)
        embed.add_field(name="👤 Owner", value=owner_str, inline=True)
        embed.add_field(name="🏰 Allowed Place ID", value=str(lic["allowed_place_id"]), inline=True)
        embed.add_field(name="👥 Allowed Group ID", value=str(lic["allowed_group_id"]), inline=True)
        embed.add_field(name="🕒 Last Verified", value=str(last_ver), inline=True)
        embed.set_footer(text="RetailNetwork License Inspector")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @bot.tree.command(name="revoke-license", description="Revoke / blacklist a license key to terminate its in-game authorization.")
    @app_commands.describe(license_key="The RN-XXXX-XXXX-XXXX-XXXX license key to revoke")
    async def revoke_license_cmd(interaction: discord.Interaction, license_key: str):
        await interaction.response.defer(ephemeral=True)
        success = revoke_license(license_key)
        if success:
            embed = discord.Embed(
                title="🚫 License Revoked",
                description=f"License key `{license_key}` has been revoked. In-game products using this key will immediately fail authorization and terminate.",
                color=0xED4245
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Could not find license key `{license_key}`.", ephemeral=True)
