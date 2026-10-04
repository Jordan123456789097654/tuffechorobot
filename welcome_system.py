import discord
import logging
from typing import Optional, Dict, Any
import config

logger = logging.getLogger("WelcomeSystem")

def build_welcome_embed(
    member: discord.Member,
    roblox_info: Optional[Dict[str, Any]] = None,
    headshot_url: Optional[str] = None
) -> discord.Embed:
    """Builds an onboarding greeting card for #welcome."""
    guild = member.guild
    member_count = guild.member_count if guild else "N/A"

    if roblox_info:
        embed = discord.Embed(
            title=f"👋 Welcome to Echo Technologies, {member.name}!",
            description=(
                f"Welcome {member.mention} to the official **Echo Technologies** community!\n"
                f"Your Roblox account has been recognized by our systems."
            ),
            color=0x00A2FF,
            timestamp=discord.utils.utcnow()
        )
        rbx_tag = f"**{roblox_info['roblox_display_name']}** (`@{roblox_info['roblox_username']}`)"
        embed.add_field(name="🎮 Verified Roblox Account", value=rbx_tag, inline=True)
        embed.add_field(name="🆔 Roblox ID", value=f"[{roblox_info['roblox_id']}](https://www.roblox.com/users/{roblox_info['roblox_id']}/profile)", inline=True)
        embed.add_field(name="🔒 Verification Status", value="✅ **Verified & Roles Assigned**", inline=True)
    else:
        embed = discord.Embed(
            title=f"👋 Welcome to Echo Technologies, {member.name}!",
            description=(
                f"Welcome {member.mention} to the official **Echo Technologies** community!\n\n"
                f"To unlock full access to our channels and games, please verify your Roblox account:"
            ),
            color=0x5865F2,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(
            name="🛡️ Get Verified",
            value=f"Head over to <#{config.VERIFICATION_CHANNEL_ID}> to link your Roblox account in seconds!",
            inline=False
        )

    embed.add_field(
        name="🚀 Explore Echo Technologies",
        value=(
            f"• 🛡️ **Account Verification:** <#{config.VERIFICATION_CHANNEL_ID}>\n"
            f"• 💡 **Community Suggestions:** <#{config.SUGGESTIONS_CHANNEL_ID}>\n"
            f"• 🎫 **Support Help Desk:** Send a direct message (DM) to this bot anytime!"
        ),
        inline=False
    )

    if headshot_url:
        embed.set_thumbnail(url=headshot_url)
    else:
        embed.set_thumbnail(url=member.display_avatar.url)

    embed.set_footer(text=f"Member #{member_count} • Echo Technologies Official Gateway")
    return embed


def build_verification_announcement_embed(
    member: discord.Member,
    roblox_info: Dict[str, Any],
    headshot_url: Optional[str] = None
) -> discord.Embed:
    """Builds a celebratory announcement embed when a member completes verification."""
    rbx_tag = f"**{roblox_info['roblox_display_name']}** (`@{roblox_info['roblox_username']}`)"
    rbx_link = f"[{roblox_info['roblox_id']}](https://www.roblox.com/users/{roblox_info['roblox_id']}/profile)"

    embed = discord.Embed(
        title="🎉 Roblox Account Verification Complete!",
        description=(
            f"Let's welcome {member.mention} to **Echo Technologies**!\n"
            f"They have successfully verified their Roblox account."
        ),
        color=0x57F287,
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(name="🎮 Roblox Player", value=rbx_tag, inline=True)
    embed.add_field(name="🆔 Profile Link", value=rbx_link, inline=True)
    embed.add_field(name="🎖️ Verified Role", value=f"<@&{config.VERIFIED_ROLE_ID}>", inline=True)

    if headshot_url:
        embed.set_thumbnail(url=headshot_url)
    else:
        embed.set_thumbnail(url=member.display_avatar.url)

    embed.set_footer(text="Echo Technologies Verification Gateway")
    return embed


async def send_welcome_greeting(bot, member: discord.Member):
    """Sends the initial greeting to #welcome when a member joins."""
    ch = bot.get_channel(config.WELCOME_CHANNEL_ID)
    if not ch:
        try:
            ch = await bot.fetch_channel(config.WELCOME_CHANNEL_ID)
        except Exception:
            ch = None

    if not ch or not isinstance(ch, discord.TextChannel):
        logger.warning(f"Welcome channel {config.WELCOME_CHANNEL_ID} not found.")
        return

    # Check if user is already verified
    roblox_info = bot.db.get_by_discord_id(member.id)
    headshot_url = None
    if roblox_info:
        headshot_url = await bot.roblox_api.get_user_headshot(roblox_info["roblox_id"])

    embed = build_welcome_embed(member, roblox_info, headshot_url)

    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Verify Roblox Account", url=f"https://discord.com/channels/{member.guild.id}/{config.VERIFICATION_CHANNEL_ID}", style=discord.ButtonStyle.link))
    view.add_item(discord.ui.Button(label="Suggestions", url=f"https://discord.com/channels/{member.guild.id}/{config.SUGGESTIONS_CHANNEL_ID}", style=discord.ButtonStyle.link))

    try:
        await ch.send(content=f"Welcome {member.mention}!", embed=embed, view=view)
        logger.info(f"Dispatched welcome greeting for {member.name} to #{ch.name}")
    except Exception as e:
        logger.error(f"Error sending welcome greeting: {e}")


async def send_verification_announcement(bot, member: discord.Member, roblox_info: Dict[str, Any]):
    """Dispatches verification celebration card to #welcome."""
    ch = bot.get_channel(config.WELCOME_CHANNEL_ID)
    if not ch:
        try:
            ch = await bot.fetch_channel(config.WELCOME_CHANNEL_ID)
        except Exception:
            ch = None

    if not ch or not isinstance(ch, discord.TextChannel):
        return

    headshot_url = await bot.roblox_api.get_user_headshot(roblox_info["roblox_id"])
    embed = build_verification_announcement_embed(member, roblox_info, headshot_url)

    try:
        await ch.send(embed=embed)
        logger.info(f"Dispatched verification announcement for {member.name} to #{ch.name}")
    except Exception as e:
        logger.error(f"Error dispatching verification announcement: {e}")
