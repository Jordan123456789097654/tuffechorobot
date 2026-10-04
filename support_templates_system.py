import discord
from discord import ui
import sqlite3
import json
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone
import config

logger = logging.getLogger("SupportTemplatesSystem")
DB_PATH = "verifications.db"

# --- DATABASE SETUP FOR DYNAMIC TEMPLATES ---

def init_support_templates_db():
    """Initializes custom support templates database table."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS custom_support_templates (
                shortcut TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                steps TEXT,
                template_text TEXT NOT NULL,
                created_by INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

init_support_templates_db()

def add_custom_template(
    shortcut: str,
    category: str,
    title: str,
    template_text: str,
    steps: str = "",
    created_by: int = 0
) -> bool:
    """Adds or updates a custom support template record in SQLite."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO custom_support_templates (shortcut, category, title, steps, template_text, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(shortcut) DO UPDATE SET
                category = excluded.category,
                title = excluded.title,
                steps = excluded.steps,
                template_text = excluded.template_text,
                created_by = excluded.created_by,
                created_at = CURRENT_TIMESTAMP;
        """, (shortcut.lower().strip(), category.strip(), title.strip(), steps.strip(), template_text.strip(), created_by))
        conn.commit()
        return True

def delete_custom_template(shortcut: str) -> bool:
    """Deletes a custom support template record."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM custom_support_templates WHERE shortcut = ?;", (shortcut.lower().strip(),))
        conn.commit()
        return cursor.rowcount > 0

def get_all_custom_templates() -> List[Dict[str, Any]]:
    """Retrieves all custom support templates stored in SQLite."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM custom_support_templates ORDER BY category, title;")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

# --- BUILT-IN TEMPLATES LIBRARY ---

BUILTIN_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "verification": {
        "shortcut": "verification",
        "category": "🔐 Verification & Accounts",
        "title": "Roblox Verification & Account Linking",
        "emoji": "🔐",
        "steps": (
            "1. Ask the member to run `/reverify` in the server to generate a fresh 4-word bio code.\n"
            "2. If Roblox chat filters censor the code (`###`), advise placing spaces between words.\n"
            "3. **Manual Bypass:** Verify their profile using `/manual-verify member:@User roblox_username:Username`."
        ),
        "template": (
            "Hello {user}! To complete your Roblox verification:\n\n"
            "1. Head over to <#1556000182196506684> and click 'Verify Roblox Account'.\n"
            "2. Enter your exact Roblox Username.\n"
            "3. Copy the 4-word code provided and paste it into your Roblox Profile 'About' / Bio section.\n"
            "4. Click 'Check Verification' when done!\n\n"
            "If your code gets tagged (###), reply here and we will verify your profile manually!"
        )
    },
    "studio_setup": {
        "shortcut": "studio_setup",
        "category": "🛠️ Studio Assets & Technical",
        "title": "Roblox Studio Assets & DataStore Setup",
        "emoji": "🛠️",
        "steps": (
            "1. Ensure **HTTP Requests** and **API Services (DataStores)** are ENABLED in Roblox Studio (`Home -> Game Settings -> Security`).\n"
            "2. Ensure the `.rbxm` file was inserted directly into `ServerScriptService`.\n"
            "3. Request Output Window error logs (`View -> Output`) from the user."
        ),
        "template": (
            "Hello {user}! Let's troubleshoot your asset setup step-by-step:\n\n"
            "1. Open your game in Roblox Studio.\n"
            "2. Click Home -> Game Settings -> Security.\n"
            "3. Ensure 'Allow HTTP Requests' and 'Enable Studio Access to API Services' are both turned ON.\n"
            "4. If you encounter an error, screenshot your Output Window (View -> Output) and reply here!"
        )
    },
    "billing": {
        "shortcut": "billing",
        "category": "💳 Billing & Gamepasses",
        "title": "Robux Billing & Gamepass Transfer Support",
        "emoji": "💳",
        "steps": (
            "1. Verify Robux or Gamepass purchase on Roblox profile/inventory.\n"
            "2. Check if purchase was made on an alt account or wrong Roblox ID.\n"
            "3. Instruct user to re-join game server or run `/update` to re-sync inventory."
        ),
        "template": (
            "Hello {user}! Regarding your billing or asset purchase inquiry:\n\n"
            "1. Please ensure you purchased the gamepass on your verified Roblox account.\n"
            "2. Try running `/update` in our Discord server to re-sync your permissions.\n"
            "3. If your pass is still locked, reply with your Roblox Transaction ID or purchase screenshot!"
        )
    },
    "bugs": {
        "shortcut": "bugs",
        "category": "🎮 Game Bugs & Server Issues",
        "title": "Game Bug & Server Crash Reports",
        "emoji": "🎮",
        "steps": (
            "1. Request device type (PC, Mobile, Console) and Roblox Client version.\n"
            "2. Request steps to reproduce the bug.\n"
            "3. Log bug in `#dev-backlog` if confirmed."
        ),
        "template": (
            "Hello {user}! Thank you for reporting this game issue to our dev team.\n\n"
            "To help us reproduce and fix this bug, please reply with:\n"
            "1. Device/Platform you are playing on (PC, Mobile, Console).\n"
            "2. Exact steps to reproduce the bug.\n"
            "3. Screenshots or video clips if available."
        )
    },
    "booster": {
        "shortcut": "booster",
        "category": "🚀 Booster Perks & Rewards",
        "title": "Server Booster Perks & Points Rewards",
        "emoji": "🚀",
        "steps": (
            "1. Verify active Server Booster badge on Discord member profile.\n"
            "2. Verify Community Points balance using `/points-shop`.\n"
            "3. Issue booster role or redemption coupon code."
        ),
        "template": (
            "Hello {user}! Thank you so much for boosting Echo Technologies! 🎉\n\n"
            "We have verified your server boost! Your Booster Perks have been activated. If your reward includes a custom role, coupon, or asset download link, reply here with your preferred role name and color!"
        )
    },
    "exploit": {
        "shortcut": "exploit",
        "category": "🚨 Exploit Reports & Scams",
        "title": "Exploit Reports, Scams & Player Disputes",
        "emoji": "🚨",
        "steps": (
            "1. Request uncropped video proof (Medal, YouTube, Streamable) showing username.\n"
            "2. Request numeric Roblox User ID of the reported player.\n"
            "3. Issue warning or global ban via moderation commands."
        ),
        "template": (
            "Hello {user}! Thank you for reporting this player to our moderation team.\n\n"
            "To take administrative action against the reported user, please reply with:\n"
            "1. Clear, uncropped video evidence or screenshots showing the incident.\n"
            "2. The exact Roblox Username or User ID of the player.\n\n"
            "Our moderation team will review your proof and take immediate action!"
        )
    },
    "appeals": {
        "shortcut": "appeals",
        "category": "🛡️ Ban & Penalty Appeals",
        "title": "Ban, Warning & Penalty Appeals",
        "emoji": "🛡️",
        "steps": (
            "1. Lookup infraction history in moderation log channel.\n"
            "2. Direct user to complete appeal format below.\n"
            "3. Escalate ticket to High-Ranking Support if management review is required."
        ),
        "template": (
            "Hello {user}! To submit your infraction appeal for review by leadership, please reply with:\n\n"
            "1. Your exact Roblox Username & Discord ID.\n"
            "2. Reason for your penalty/ban.\n"
            "3. Detailed explanation of why your penalty should be lifted or reduced.\n"
            "4. What steps you will take to follow server rules in the future."
        )
    },
    "whitelisting": {
        "shortcut": "whitelisting",
        "category": "🔑 License & Whitelisting",
        "title": "Asset License Keys & Hub Whitelisting",
        "emoji": "🔑",
        "steps": (
            "1. Verify Roblox Group ID / Place ID ownership.\n"
            "2. Add Place ID or Group ID to whitelist database.\n"
            "3. Issue product download link."
        ),
        "template": (
            "Hello {user}! Regarding your product licensing and hub whitelisting:\n\n"
            "Please provide your **Roblox Place ID** or **Roblox Group ID** where the asset will be installed. Once verified, our system will grant immediate whitelisting access!"
        )
    },
    "partnerships": {
        "shortcut": "partnerships",
        "category": "🤝 Affiliate Partnerships",
        "title": "Affiliate Partnerships & Ad Proof",
        "emoji": "🤝",
        "steps": (
            "1. Verify partner group meets minimum member count (100+ members).\n"
            "2. Verify ad proof posted in their server.\n"
            "3. Publish partnership using `/partner-add`."
        ),
        "template": (
            "Hello {user}! We are excited to partner with your group! 🤝\n\n"
            "Please provide:\n"
            "1. Link to your Discord Server & Roblox Group.\n"
            "2. Screenshot proof of posting our ad copy in your announcements/affiliates channel.\n"
            "3. The mention tag of your designated Partner Representative."
        )
    },
    "misconduct": {
        "shortcut": "misconduct",
        "category": "👔 Staff Misconduct",
        "title": "Staff Misconduct & Formal Complaints",
        "emoji": "👔",
        "steps": (
            "1. Request ticket ID or screenshot proof of staff misconduct.\n"
            "2. Escalate ticket immediately to Foundership / Supervisor role using `/supervisor-request`.\n"
            "3. Pause AI replies in channel."
        ),
        "template": (
            "Hello {user}, we take staff integrity very seriously at Echo Technologies.\n\n"
            "Your complaint has been escalated directly to our **Foundership & HR Leadership Team**. Please provide any screenshots or message links regarding your concern, and a Founding Director will assist you directly."
        )
    },
    "role_sync": {
        "shortcut": "role_sync",
        "category": "🔄 Discord Role Sync",
        "title": "Roblox Group Rank & Discord Role Re-Sync",
        "emoji": "🔄",
        "steps": (
            "1. Verify group rank on Roblox Group page.\n"
            "2. Execute `/update` or manually assign corresponding team role."
        ),
        "template": (
            "Hello {user}! To re-sync your Discord roles with your Roblox Group rank:\n\n"
            "1. Make sure your Roblox account is linked via <#1556000182196506684>.\n"
            "2. Run the `/update` slash command in any bot channel.\n"
            "3. If your group rank changed recently, please allow 1 minute for role sync to update!"
        )
    },
    "inactive": {
        "shortcut": "inactive",
        "category": "💤 Inactive Ticket Notices",
        "title": "Inactive Support Ticket Notice",
        "emoji": "💤",
        "steps": (
            "1. Check if member has not responded for 24+ hours.\n"
            "2. Send inactive ticket notice and close ticket."
        ),
        "template": (
            "Hello {user}, we haven't received a response from you recently, so we are closing this support ticket for now.\n\n"
            "If you still need assistance or have further questions, feel free to open a new ticket anytime. Thank you for choosing Echo Technologies!"
        )
    }
}

def get_combined_template_list() -> List[Dict[str, Any]]:
    """Combines built-in templates and SQLite custom templates into a single master list."""
    builtins = list(BUILTIN_TEMPLATES.values())
    customs = get_all_custom_templates()

    custom_formatted = []
    for c in customs:
        custom_formatted.append({
            "shortcut": c["shortcut"],
            "category": f"⭐ Custom: {c['category']}",
            "title": c["title"],
            "emoji": "⭐",
            "steps": c.get("steps") or "Custom staff template.",
            "template": c["template_text"]
        })

    return builtins + custom_formatted

# --- PRESENTATION BUILDERS ---

async def build_support_header_embed(bot=None) -> discord.Embed:
    """Builds header embed for #support-templates with live Roblox API Status Widget (#4)."""
    status_str = "🟢 **All Systems Operational**"
    if bot and hasattr(bot, "roblox_api"):
        try:
            results = await bot.roblox_api.check_roblox_system_status()
            lines = [f"• **{service}:** {st}" for service, st in results.items()]
            status_str = "\n".join(lines)
        except Exception:
            pass

    embed = discord.Embed(
        title="📚 Echo Technologies • Support Team Guide & Knowledge Base",
        description=(
            "Welcome to the official **Support Team Knowledge Base & Template Console**!\n\n"
            "This channel contains standard operating procedures (SOPs), troubleshooting workflows, "
            "and ready-to-use message templates for support team members handling tickets.\n\n"
            "🌐 **Real-Time Roblox API Status Widget:**\n"
            f"{status_str}\n\n"
            "────────────────────────────────────────\n"
            "**📋 Support Team Standard Operating Guidelines:**\n"
            "• **Professionalism:** Maintain a polite, helpful, and professional tone in all ticket communications.\n"
            "• **Accuracy:** Ensure member issues are thoroughly investigated before applying penalties or closing tickets.\n"
            "• **Modmail Relay Notice:** Member messages arrive via Direct Messages (DMs). Staff reply directly in ticket channels.\n"
            "• **Supervisor Escalation:** To ping Foundership/Supervisors, click `🚨 Request Supervisor` or use `/supervisor-request`.\n"
            "• **Quick Template Selector:** Select a category below to view specific staff templates & SOPs!"
        ),
        color=0x5865F2,
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text="Echo Technologies Support Division • Real-Time Status & SOP Panel")
    return embed

class TemplateCategorySelectView(ui.View):
    """Interactive category select menu attached to #support-templates header embed."""

    def __init__(self):
        super().__init__(timeout=None)
        select = ui.Select(
            placeholder="🔍 Select a Support Scenario / Template Category...",
            custom_id="supp_tpl_select",
            options=[
                discord.SelectOption(label="Roblox Verification & Accounts", value="verification", emoji="🔐", description="Code censored, reverify, manual verify steps"),
                discord.SelectOption(label="Roblox Studio Assets & Technical", value="studio_setup", emoji="🛠️", description="HTTP Requests, DataStores, script setup"),
                discord.SelectOption(label="Robux Billing & Gamepasses", value="billing", emoji="💳", description="Purchase verification, gamepass transfers"),
                discord.SelectOption(label="Game Bugs & Server Crashes", value="bugs", emoji="🎮", description="Bug report format & reproduction steps"),
                discord.SelectOption(label="Booster Perks & Rewards", value="booster", emoji="🚀", description="Booster role claim, community points shop"),
                discord.SelectOption(label="Exploit Reports & Scams", value="exploit", emoji="🚨", description="Evidence submission & player bans"),
                discord.SelectOption(label="Ban & Penalty Appeals", value="appeals", emoji="🛡️", description="Infraction appeal format & HR review"),
                discord.SelectOption(label="License & Whitelisting", value="whitelisting", emoji="🔑", description="Place ID / Group ID asset whitelisting"),
                discord.SelectOption(label="Affiliate Partnerships", value="partnerships", emoji="🤝", description="Partner requirements & ad proof submission"),
                discord.SelectOption(label="Staff Misconduct Complaints", value="misconduct", emoji="👔", description="Supervisor escalation & formal complaints"),
                discord.SelectOption(label="Discord Role Re-Sync", value="role_sync", emoji="🔄", description="Roblox group rank & Discord role sync"),
                discord.SelectOption(label="Inactive Ticket Notices", value="inactive", emoji="💤", description="24-hour inactive closure notice")
            ]
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        val = interaction.data["values"][0]
        all_tpls = {t["shortcut"]: t for t in get_combined_template_list()}
        tpl = all_tpls.get(val) or BUILTIN_TEMPLATES.get(val)

        if not tpl:
            await interaction.response.send_message("❌ Template not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"{tpl.get('emoji', '📚')} {tpl['title']}",
            description=(
                f"**Category:** `{tpl.get('category', 'General')}`\n\n"
                f"**📋 Standard Operating Procedure (SOP):**\n"
                f"{tpl.get('steps', 'No specific steps.')}\n\n"
                f"**💬 Official Staff Response Template (Copy & Paste):**\n"
                f"```\n{tpl['template']}\n```"
            ),
            color=0x5865F2
        )
        embed.set_footer(text=f"Template Shortcut: {tpl['shortcut']} • Echo Technologies SOP")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class SendTemplateSelectView(ui.View):
    """Interactive template picker for staff inside ticket channels to send templates directly to DMs."""

    def __init__(self, bot, ticket_id: int):
        super().__init__(timeout=180)
        self.bot = bot
        self.ticket_id = ticket_id

        all_tpls = get_combined_template_list()
        options = []
        for t in all_tpls[:25]: # Max 25 choices in discord select
            options.append(
                discord.SelectOption(
                    label=t["title"][:100],
                    value=t["shortcut"],
                    emoji=t.get("emoji", "💬"),
                    description=t.get("category", "")[:50]
                )
            )

        select = ui.Select(
            placeholder="✉️ Choose a template to send directly to candidate/member DMs...",
            custom_id=f"send_tpl_sel:{ticket_id}",
            options=options
        )
        select.callback = self.send_template_callback
        self.add_item(select)

    async def send_template_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        val = interaction.data["values"][0]
        all_tpls = {t["shortcut"]: t for t in get_combined_template_list()}
        tpl = all_tpls.get(val) or BUILTIN_TEMPLATES.get(val)

        if not tpl:
            await interaction.followup.send("❌ Template not found.", ephemeral=True)
            return

        ticket = self.bot.ticket_manager.get_ticket_by_id(self.ticket_id)
        if not ticket:
            await interaction.followup.send("❌ Ticket not found.", ephemeral=True)
            return

        candidate = self.bot.get_user(ticket["user_id"])
        if not candidate:
            try:
                candidate = await self.bot.fetch_user(ticket["user_id"])
            except Exception:
                candidate = None

        if not candidate:
            await interaction.followup.send("❌ Could not find ticket member.", ephemeral=True)
            return

        # Format template with user name
        formatted_text = tpl["template"].replace("{user}", candidate.mention)

        # Log message in ticket history
        self.bot.ticket_manager.add_message(
            self.ticket_id,
            interaction.user.id,
            "staff",
            formatted_text,
            sender_name=interaction.user.name
        )

        # Send embed to ticket channel
        channel_embed = discord.Embed(
            title=f"✉️ Staff Dispatched Template • {tpl['title']}",
            description=formatted_text,
            color=0x57F287,
            timestamp=discord.utils.utcnow()
        )
        channel_embed.set_author(name=f"Sent by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        channel_embed.set_footer(text=f"Template: {tpl['shortcut']} • Modmail Relayed to DM")
        await interaction.channel.send(embed=channel_embed)

        # Send DM to candidate
        try:
            dm = await candidate.create_dm()
            dm_embed = discord.Embed(
                title=f"💬 Echo Support • {tpl['title']}",
                description=formatted_text,
                color=0x5865F2,
                timestamp=discord.utils.utcnow()
            )
            dm_embed.set_footer(text=f"Support Ticket #{self.ticket_id} • Reply directly to answer")
            await dm.send(embed=dm_embed)
            await interaction.followup.send(f"✅ Dispatched **{tpl['title']}** template directly to {candidate.mention}'s DMs!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"⚠️ Sent template to ticket channel, but DM delivery failed: {e}", ephemeral=True)

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

    header_embed = await build_support_header_embed(bot)
    view = TemplateCategorySelectView()

    try:
        # Purge existing bot messages if any
        async for msg in target_ch.history(limit=25):
            if msg.author.id == bot.user.id:
                try:
                    await msg.delete()
                except Exception:
                    pass

        await target_ch.send(embed=header_embed, view=view)

        # Post all scenario cards
        all_tpls = get_combined_template_list()
        for tpl in all_tpls:
            em = discord.Embed(
                title=f"{tpl.get('emoji', '📚')} {tpl['title']}",
                description=(
                    f"**Category:** `{tpl.get('category', 'General')}`\n\n"
                    f"**📋 Standard Operating Procedure (SOP):**\n"
                    f"{tpl.get('steps', 'No specific steps.')}\n\n"
                    f"**💬 Staff Copy & Paste Template:**\n"
                    f"```\n{tpl['template']}\n```"
                ),
                color=0x5865F2
            )
            em.set_footer(text=f"Shortcut: {tpl['shortcut']} • Echo Technologies Support SOP")
            await target_ch.send(embed=em)

        logger.info(f"Posted support templates guide & status widget to #{target_ch.name} ({target_ch.id})")
        return True
    except Exception as e:
        logger.error(f"Error syncing support templates: {e}")
        return False
