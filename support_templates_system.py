import discord
import logging
from typing import Optional, List
import config

logger = logging.getLogger("SupportTemplatesSystem")

def build_support_header_embed() -> discord.Embed:
    embed = discord.Embed(
        title="📚 Echo Technologies • Support Team Response Guide & Templates",
        description=(
            "Welcome to the official **Support Team Knowledge Base & Template Library**!\n\n"
            "This channel contains standard operating procedures (SOPs), troubleshooting workflows, "
            "and ready-to-use message templates for support team members handling tickets.\n\n"
            "**📋 Support Team Standard Guidelines:**\n"
            "• **Professionalism:** Maintain a polite, helpful, and professional tone in all ticket communications.\n"
            "• **Accuracy:** Ensure member issues are thoroughly investigated before applying penalties or closing tickets.\n"
            "• **Modmail Relay Notice:** Member messages arrive via Direct Messages (DMs). Staff reply directly in ticket channels.\n"
            "• **Escalation Protocol:** If an inquiry exceeds your authorization level, click `Escalate Ticket` or use `/ticket escalate`."
        ),
        color=0x5865F2,
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text="Echo Technologies Support Division • Staff Reference Panel")
    return embed

def build_template_embeds() -> List[discord.Embed]:
    embeds = []

    # 1. Roblox Profile Verification & Account Linking
    verify_embed = discord.Embed(
        title="🔐 1. Roblox Verification & Account Linking",
        description=(
            "### Scenario: Verification Code Censored or Account Switching\n"
            "When a user experiences issues linking their Roblox account or their verification code is tagged by Roblox chat filters.\n\n"
            "**📋 Troubleshooting Steps:**\n"
            "1. Ask the member to run `/reverify` in the server to generate a fresh 4-word bio code.\n"
            "2. If Roblox censors the phrase (shows `###`), advise them to place spaces between words or use standard English punctuation.\n"
            "3. **Manual Bypass:** If bio check fails due to Roblox system maintenance, verify their profile manually using `/manual-verify member:@User roblox_username:Username`.\n\n"
            "**💬 Staff Copy & Paste Template:**\n"
            "```\n"
            "Hello {user}! To complete your Roblox verification:\n\n"
            "1. Head over to <#1556000182196506684> and click 'Verify Roblox Account'.\n"
            "2. Enter your exact Roblox Username.\n"
            "3. Copy the 4-word code provided and paste it into your Roblox Profile 'About' / Bio section.\n"
            "4. Click 'Check Verification' when done!\n\n"
            "If your code gets tagged (###), let us know here and we will verify your profile manually!"
            "```"
        ),
        color=0x00A2FF
    )
    embeds.append(verify_embed)

    # 2. Roblox Studio Assets & Technical Issues
    studio_embed = discord.Embed(
        title="🛠️ 2. Roblox Studio Assets & Technical Support",
        description=(
            "### Scenario: Asset Script Error, Model Download, or DataStore Permissions\n"
            "When a customer reports an issue with an Echo asset, script error, or studio setup failure.\n\n"
            "**📋 Troubleshooting Steps:**\n"
            "1. Ensure **HTTP Requests** and **API Services (DataStores)** are ENABLED in Roblox Studio (`Home -> Game Settings -> Security`).\n"
            "2. Ensure the `.rbxm` file was inserted directly into `ServerScriptService` or designated location.\n"
            "3. Ask the user for exact Output Window error logs (red error text in Studio console).\n\n"
            "**💬 Staff Copy & Paste Template:**\n"
            "```\n"
            "Hello {user}! Let's troubleshoot your asset setup step-by-step:\n\n"
            "1. Open your game in Roblox Studio.\n"
            "2. Click Home -> Game Settings -> Security.\n"
            "3. Ensure 'Allow HTTP Requests' and 'Enable Studio Access to API Services' are both turned ON.\n"
            "4. If you are still encountering an error, please screenshot the Output Window (View -> Output) and reply here!"
            "```"
        ),
        color=0x57F287
    )
    embeds.append(studio_embed)

    # 3. Booster Perks & Community Rewards
    booster_embed = discord.Embed(
        title="🚀 3. Server Booster Perks & Points Rewards",
        description=(
            "### Scenario: Claiming Booster Role, Custom Rewards, or Points Store\n"
            "When a member boosts the server or redeems community points for assets/coupons.\n\n"
            "**📋 Troubleshooting Steps:**\n"
            "1. Verify the member has an active Server Booster badge on their profile.\n"
            "2. For Points Shop redemptions, verify their balance using `/points-shop` or staff database records.\n"
            "3. If eligible, issue their custom reward or coupon code.\n\n"
            "**💬 Staff Copy & Paste Template:**\n"
            "```\n"
            "Hello {user}! Thank you so much for supporting Echo Technologies! 🎉\n\n"
            "We have verified your server boost! Your Booster Perks have been activated. If your reward includes a custom role, coupon, or asset download link, please reply with your preferred role name/color and we will issue it immediately!"
            "```"
        ),
        color=0xFEE75C
    )
    embeds.append(booster_embed)

    # 4. Exploit Reports & Player Disputes
    exploit_embed = discord.Embed(
        title="🚨 4. Exploit Reports, Scams & Player Disputes",
        description=(
            "### Scenario: Reporting an Exploiter, Scammer, or Rule Violation\n"
            "When a member reports another player for exploiting, scamming, or toxicity.\n\n"
            "**📋 Troubleshooting Steps:**\n"
            "1. Request uncropped video evidence (e.g. Medal, YouTube, Streamable) showing the accused user's name and behavior.\n"
            "2. Request the accused user's numeric Roblox User ID.\n"
            "3. Log the infraction via moderation command `/warn` or `/ban` if proof is conclusive.\n\n"
            "**💬 Staff Copy & Paste Template:**\n"
            "```\n"
            "Hello {user}! Thank you for bringing this player report to our attention.\n\n"
            "To take administrative action against the reported user, please provide:\n"
            "1. Clear, uncropped video evidence or screenshots showing the incident.\n"
            "2. The exact Roblox Username or User ID of the player.\n\n"
            "Once submitted, our moderation team will review the proof and take necessary action!"
            "```"
        ),
        color=0xED4245
    )
    embeds.append(exploit_embed)

    # 5. Ban & Infraction Appeals
    appeal_embed = discord.Embed(
        title="🛡️ 5. Ban & Infraction Appeals",
        description=(
            "### Scenario: Penalized Member Seeking Ban or Mute Appeal\n"
            "When a user opens a ticket to appeal a ban, warning, or staff disciplinary action.\n\n"
            "**📋 Troubleshooting Steps:**\n"
            "1. Lookup the infraction case details in moderation log channel <#1556000170922221661>.\n"
            "2. Direct the user to complete the formal appeal format below.\n"
            "3. Escalate the ticket to High-Ranking Support if management review is required.\n\n"
            "**💬 Staff Copy & Paste Template:**\n"
            "```\n"
            "Hello {user}! To submit your infraction appeal for review by leadership, please reply with:\n\n"
            "1. Your exact Roblox Username & Discord ID.\n"
            "2. Reason for your penalty/ban.\n"
            "3. Detailed explanation of why your penalty should be lifted or reduced.\n"
            "4. What steps you will take to ensure server rules are followed in the future.\n\n"
            "Our leadership team will review your appeal shortly!"
            "```"
        ),
        color=0x9B59B6
    )
    embeds.append(appeal_embed)

    # 6. Affiliate Partnerships & Ad Proof
    partner_embed = discord.Embed(
        title="🤝 6. Affiliate Partnerships & Ad Proof Submission",
        description=(
            "### Scenario: Group Partnership Inquiry or Advertising Verification\n"
            "When a representative from another Roblox group or server inquires about partnership.\n\n"
            "**📋 Troubleshooting Steps:**\n"
            "1. Verify partner group/server meets minimum member requirements (e.g. 100+ members).\n"
            "2. Verify they posted our official ad copy in their server.\n"
            "3. Use `/partner-add` to record the partnership in channel <#1556000112692699157>.\n\n"
            "**💬 Staff Copy & Paste Template:**\n"
            "```\n"
            "Hello {user}! We are excited to partner with your group! 🤝\n\n"
            "Please provide:\n"
            "1. Link to your Discord Server & Roblox Group.\n"
            "2. Screenshot proof of posting our ad copy in your announcements/affiliates channel.\n"
            "3. The mention tag of your designated Partner Representative.\n\n"
            "Once verified, we will publish your affiliate partnership in our server!"
            "```"
        ),
        color=0x1ABC9C
    )
    embeds.append(partner_embed)

    # 7. Inactive Ticket Closure Notice
    inactive_embed = discord.Embed(
        title="💤 7. Inactive Ticket Closure Notice",
        description=(
            "### Scenario: Member Has Not Responded for 24+ Hours\n"
            "When a member has stopped replying to support staff inquiries.\n\n"
            "**💬 Staff Copy & Paste Template:**\n"
            "```\n"
            "Hello {user}, we haven't received a response from you recently, so we are closing this support ticket for now.\n\n"
            "If you still need assistance or have further questions, feel free to open a new ticket anytime. Thank you for choosing Echo Technologies!"
            "```"
        ),
        color=0x747F8D
    )
    embeds.append(inactive_embed)

    return embeds

async def sync_support_templates_channel(bot, channel: Optional[discord.TextChannel] = None) -> bool:
    """Posts or refreshes the support templates in #support-templates (1556425130752876626)."""
    target_ch = channel or bot.get_channel(config.SUPPORT_TEMPLATES_CHANNEL_ID)
    if not target_ch:
        try:
            target_ch = await bot.fetch_channel(config.SUPPORT_TEMPLATES_CHANNEL_ID)
        except Exception as e:
            logger.warning(f"Could not fetch support templates channel {config.SUPPORT_TEMPLATES_CHANNEL_ID}: {e}")
            return False

    if not isinstance(target_ch, discord.TextChannel):
        return False

    header_embed = build_support_header_embed()
    template_embeds = build_template_embeds()

    try:
        # Purge existing bot messages if any, or edit in place
        async for msg in target_ch.history(limit=25):
            if msg.author.id == bot.user.id:
                try:
                    await msg.delete()
                except Exception:
                    pass

        await target_ch.send(embed=header_embed)
        for em in template_embeds:
            await target_ch.send(embed=em)

        logger.info(f"Posted support templates guide to #{target_ch.name} ({target_ch.id})")
        return True
    except Exception as e:
        logger.error(f"Error syncing support templates: {e}")
        return False
