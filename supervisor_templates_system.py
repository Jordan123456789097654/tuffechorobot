import discord
from discord import ui
import logging
import sqlite3
import os
from typing import List, Dict, Any, Optional
import config

logger = logging.getLogger("SupervisorTemplatesSystem")

DB_PATH = "verifications.db"

def init_supervisor_templates_db():
    """Initializes the SQLite database table for custom supervisor templates."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS custom_supervisor_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shortcut TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                steps TEXT NOT NULL,
                template_text TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

init_supervisor_templates_db()

def add_custom_supervisor_template(
    shortcut: str,
    category: str,
    title: str,
    template_text: str,
    steps: str = "",
    created_by: int = 0
) -> tuple[bool, str]:
    """Adds a new custom supervisor template to SQLite."""
    s_clean = shortcut.lower().strip()
    if not s_clean.isalnum() and "_" not in s_clean:
        return False, "Shortcut must contain only alphanumeric characters and underscores."

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO custom_supervisor_templates (shortcut, category, title, steps, template_text, created_by)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (s_clean, category.strip(), title.strip(), steps.strip(), template_text.strip(), created_by))
            conn.commit()
        return True, f"Successfully created custom supervisor template `{s_clean}`!"
    except sqlite3.IntegrityError:
        return False, f"Supervisor template shortcut `{s_clean}` already exists."
    except Exception as e:
        return False, f"Database error: {e}"

def delete_custom_supervisor_template(shortcut: str) -> tuple[bool, str]:
    """Deletes a custom supervisor template record."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM custom_supervisor_templates WHERE shortcut = ?;", (shortcut.lower().strip(),))
        conn.commit()
        if cursor.rowcount > 0:
            return True, f"Deleted supervisor template `{shortcut}`."
        return False, f"No supervisor template found with shortcut `{shortcut}`."

def get_all_custom_supervisor_templates() -> List[Dict[str, Any]]:
    """Retrieves all custom supervisor templates stored in SQLite."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM custom_supervisor_templates ORDER BY category, title;")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

# --- BUILT-IN SUPERVISOR & HR TEMPLATES ---

BUILTIN_SUPERVISOR_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "staff_strike_notice": {
        "shortcut": "staff_strike_notice",
        "category": "👔 Staff Disciplinary & HR",
        "title": "Formal Disciplinary Strike Warning Notice",
        "emoji": "⚠️",
        "steps": (
            "1. Verify staff offense against Staff Code of Conduct in #hr-logs.\n"
            "2. Log strike using `/strike add member:@User severity:Minor/Moderate/Critical reason:Reason`.\n"
            "3. Issue formal HR strike notice to staff member."
        ),
        "template": (
            "**ECHO TECHNOLOGIES • HUMAN RESOURCES DIVISION**\n"
            "**OFFICIAL DISCIPLINARY STRIKE NOTICE**\n\n"
            "Dear {user},\n\n"
            "This communication serves as a formal notification that an **Official Disciplinary Strike** has been registered against your record in the Echo Technologies HR Database.\n\n"
            "📋 **Notice Parameters:**\n"
            "• **Action Type:** Official Disciplinary Strike\n"
            "• **Authority:** Foundership & Executive HR Leadership\n"
            "• **Policy Violation:** Non-compliance with Staff Protocol & Code of Conduct\n\n"
            "Please be advised that accumulating multiple strikes will result in immediate suspension, demotion, or permanent termination of staff credentials. If you wish to appeal this action, submit an appeal ticket via High-Ranking Support within 48 hours.\n\n"
            "Sincerely,\n"
            "**Echo Technologies Foundership & HR Operations**"
        )
    },
    "staff_suspension_notice": {
        "shortcut": "staff_suspension_notice",
        "category": "👔 Staff Disciplinary & HR",
        "title": "Temporary Administrative Suspension Notice",
        "emoji": "⛔",
        "steps": (
            "1. Execute suspension command `/suspend member:@User duration:Days reason:Reason`.\n"
            "2. Revoke staff channel permissions during active investigation.\n"
            "3. Schedule executive HR review session."
        ),
        "template": (
            "**ECHO TECHNOLOGIES • HUMAN RESOURCES DIVISION**\n"
            "**NOTICE OF ADMINISTRATIVE SUSPENSION**\n\n"
            "Dear {user},\n\n"
            "Please be informed that your staff privileges and access permissions have been **Temporarily Suspended** pending an active Human Resources administrative investigation.\n\n"
            "🔒 **Suspension Details:**\n"
            "• **Status:** Active Administrative Suspension\n"
            "• **Permission Level:** Restricted (All staff channels & administrative tools suspended)\n"
            "• **Mandate:** You are required to remain available for HR questioning regarding the pending inquiry.\n\n"
            "Do not attempt to bypass permissions or discuss active investigations in public channels. Executive Leadership will notify you upon conclusion of the review.\n\n"
            "Sincerely,\n"
            "**Executive HR Directorate • Echo Technologies**"
        )
    },
    "staff_demotion_notice": {
        "shortcut": "staff_demotion_notice",
        "category": "👔 Staff Disciplinary & HR",
        "title": "Notice of Demotion & Role Termination",
        "emoji": "🔻",
        "steps": (
            "1. Execute demotion or role revocation in Discord and Roblox Group.\n"
            "2. Audit entry posted to #staff-disciplinary.\n"
            "3. Archive staff folder."
        ),
        "template": (
            "**ECHO TECHNOLOGIES • HUMAN RESOURCES DIVISION**\n"
            "**NOTICE OF DEMOTION AND ROLE TERMINATION**\n\n"
            "Dear {user},\n\n"
            "Following a thorough performance and compliance audit by Foundership and Executive HR Operations, we regret to inform you that your appointment as a staff member at Echo Technologies has been **Terminated**.\n\n"
            "📋 **Executive Order Summary:**\n"
            "• **Action Taken:** Formal Demotion & Role Revocation\n"
            "• **Effective Date:** Immediate\n"
            "• **Reasoning:** Failure to uphold staff performance benchmarks and operational directives.\n\n"
            "All staff credentials, internal access keys, and administrative permissions have been revoked. We thank you for your past contributions.\n\n"
            "Sincerely,\n"
            "**Foundership & Board of Directors • Echo Technologies**"
        )
    },
    "staff_blacklist_notice": {
        "shortcut": "staff_blacklist_notice",
        "category": "👔 Staff Disciplinary & HR",
        "title": "Permanent Staff Blacklist & Misconduct Entry",
        "emoji": "🚫",
        "steps": (
            "1. Add entry using `/staff-blacklist add member:@User reason:Reason`.\n"
            "2. Log severe breach (leak, abuse, exploit) in global database.\n"
            "3. Enforce ban across all network servers."
        ),
        "template": (
            "**ECHO TECHNOLOGIES • HUMAN RESOURCES DIVISION**\n"
            "**CONFIDENTIAL DIRECTIVE: PERMANENT STAFF BLACKLIST**\n\n"
            "Dear {user},\n\n"
            "Due to a severe breach of trust, unauthorized disclosure, or major misconduct, your account has been placed on the **Permanent Echo Technologies Staff Blacklist**.\n\n"
            "🚫 **Blacklist Impact:**\n"
            "• **Staff Eligibility:** Permanently Ineligible for any future staff, developer, or affiliate roles.\n"
            "• **Global Network Enforcement:** Entry broadcasted across all Echo Technologies systems and partner networks.\n"
            "• **Appeals:** Final Order — Non-appealable.\n\n"
            "Sincerely,\n"
            "**Office of the Founders • Echo Technologies**"
        )
    },
    "promotion_appointment": {
        "shortcut": "promotion_appointment",
        "category": "👑 Executive & Leadership",
        "title": "Executive Appointment & Staff Promotion Letter",
        "emoji": "👑",
        "steps": (
            "1. Assign elevated team role in Discord & Roblox Group.\n"
            "2. Broadcast announcement to #announcements / #staff-announcements.\n"
            "3. Dispatch formal letter of promotion."
        ),
        "template": (
            "**ECHO TECHNOLOGIES • EXECUTIVE OFFICE**\n"
            "**OFFICIAL LETTER OF PROMOTION**\n\n"
            "Dear {user},\n\n"
            "On behalf of Foundership and Executive Leadership, it is our distinct honor to announce your official **Promotion** within the Echo Technologies organization!\n\n"
            "🎉 **Appointment Details:**\n"
            "• **New Position:** Elevated Leadership Role\n"
            "• **Status:** Active & Authorized\n\n"
            "Your dedication, leadership, and exemplary performance have distinguished you as a vital pillar of our team. We look forward to your continued excellence in this new capacity.\n\n"
            "Congratulations,\n"
            "**Foundership & Executive Directorate • Echo Technologies**"
        )
    },
    "appeal_ruling_approved": {
        "shortcut": "appeal_ruling_approved",
        "category": "👑 Executive & Leadership",
        "title": "Official Appeal Ruling — Approved & Restored",
        "emoji": "⚖️",
        "steps": (
            "1. Review appeal evidence with HR committee.\n"
            "2. Pardon strike/infraction using `/pardon-strike` or `/unban`.\n"
            "3. Restore clean record standing."
        ),
        "template": (
            "**ECHO TECHNOLOGIES • APPEALS COMMISSION**\n"
            "**OFFICIAL APPEAL DETERMINATION — APPROVED**\n\n"
            "Dear {user},\n\n"
            "The Echo Technologies Appeals Commission has concluded its formal review regarding your recent infraction appeal.\n\n"
            "⚖️ **Official Determination:** **APPROVED**\n"
            "• **Resolution:** The disciplinary action / penalty on record has been **Pardoned and Expunged**.\n"
            "• **Account Status:** Restored to Full Standing.\n\n"
            "Thank you for your patience during our administrative review process.\n\n"
            "Sincerely,\n"
            "**Appeals Directorate • Echo Technologies**"
        )
    },
    "appeal_ruling_denied": {
        "shortcut": "appeal_ruling_denied",
        "category": "👑 Executive & Leadership",
        "title": "Official Appeal Determination — Denied",
        "emoji": "❌",
        "steps": (
            "1. Review evidence provided in appeal.\n"
            "2. Confirm penalty validity against infraction logs.\n"
            "3. Dispatch final non-negotiable ruling."
        ),
        "template": (
            "**ECHO TECHNOLOGIES • APPEALS COMMISSION**\n"
            "**OFFICIAL APPEAL DETERMINATION — DENIED**\n\n"
            "Dear {user},\n\n"
            "The Echo Technologies Appeals Commission has thoroughly evaluated your submission and supporting evidence.\n\n"
            "⚖️ **Official Determination:** **DENIED**\n"
            "• **Finding:** The original disciplinary penalty was executed in full accordance with server protocols.\n"
            "• **Status:** The penalty remains active as issued.\n\n"
            "This determination represents the final administrative decision on this matter.\n\n"
            "Sincerely,\n"
            "**Appeals Directorate • Echo Technologies**"
        )
    },
    "loa_approval_formal": {
        "shortcut": "loa_approval_formal",
        "category": "👑 Executive & Leadership",
        "title": "Executive Leave of Absence Authorization",
        "emoji": "✈️",
        "steps": (
            "1. Log LOA duration in database.\n"
            "2. Assign LOA role to exempt staff member from weekly quotas.\n"
            "3. Set automatic return reminder."
        ),
        "template": (
            "**ECHO TECHNOLOGIES • HUMAN RESOURCES DIVISION**\n"
            "**LEAVE OF ABSENCE (LOA) AUTHORIZATION**\n\n"
            "Dear {user},\n\n"
            "Your formal request for a **Leave of Absence (LOA)** has been reviewed and **Authorized** by HR Operations.\n\n"
            "✈️ **LOA Parameters:**\n"
            "• **Status:** Approved / Exemption Granted\n"
            "• **Quota Requirement:** Temporarily Suspended\n\n"
            "Please ensure you notify HR upon your return to reactivate active duty status. We wish you well during your leave!\n\n"
            "Sincerely,\n"
            "**HR Operations • Echo Technologies**"
        )
    },
    "investigation_notice": {
        "shortcut": "investigation_notice",
        "category": "👑 Executive & Leadership",
        "title": "Notice of Formal HR Incident Investigation",
        "emoji": "🔍",
        "steps": (
            "1. Gather evidence logs and witness statements.\n"
            "2. Issue inquiry notice to involved parties.\n"
            "3. Hold confidential hearing in supervisor ticket."
        ),
        "template": (
            "**ECHO TECHNOLOGIES • SUPERVISORY BOARD**\n"
            "**CONFIDENTIAL INQUIRY & INVESTIGATION NOTICE**\n\n"
            "Dear {user},\n\n"
            "You are hereby notified that the Supervisory Board is conducting a formal inquiry regarding a recent server operational incident.\n\n"
            "🔍 **Directives:**\n"
            "1. Provide a comprehensive written statement regarding the matter in this channel.\n"
            "2. Submit all relevant screenshots, message links, or logs.\n"
            "3. Maintain strict confidentiality regarding this inquiry.\n\n"
            "A Supervisor will preside over this inquiry.\n\n"
            "Sincerely,\n"
            "**Supervisory Board • Echo Technologies**"
        )
    }
}

def get_combined_supervisor_template_list() -> List[Dict[str, Any]]:
    """Combines built-in supervisor templates and custom supervisor templates into a single master list."""
    builtins = list(BUILTIN_SUPERVISOR_TEMPLATES.values())
    customs = get_all_custom_supervisor_templates()

    custom_formatted = []
    for c in customs:
        custom_formatted.append({
            "shortcut": c["shortcut"],
            "category": f"⭐ Custom: {c['category']}",
            "title": c["title"],
            "emoji": "⭐",
            "steps": c.get("steps") or "Custom supervisor template.",
            "template": c["template_text"]
        })

    return builtins + custom_formatted

# --- PRESENTATION BUILDERS ---

async def build_supervisor_header_embed(bot=None) -> discord.Embed:
    """Builds header embed for #supervisor-templates (1556427867947278336)."""
    embed = discord.Embed(
        title="👑 Echo Technologies • Supervisor & HR Leadership Knowledge Base",
        description=(
            "Welcome to the official **Supervisor & HR Leadership Template Console**!\n\n"
            "This channel is strictly reserved for **Foundership, Executive Leadership, and HR Supervisors** "
            "handling high-level tickets, staff disciplinary actions, infractions, appeals, and formal promotions.\n\n"
            "────────────────────────────────────────\n"
            "**📋 Executive Standard Operating Guidelines:**\n"
            "• **Formal Tone:** Maintain strictly professional, executive, and non-negotiable tone in official HR notices.\n"
            "• **Due Process:** Verify evidence and check `#hr-logs` before executing strikes, suspensions, or demotions.\n"
            "• **Confidentiality:** HR directives and internal investigations are strictly confidential.\n"
            "• **Quick Template Selector:** Select a category below to inspect formal leadership templates & SOPs!"
        ),
        color=0x9B59B6,
        timestamp=discord.utils.utcnow()
    )
    embed.set_footer(text="Echo Technologies Executive Office • Supervisor SOP Panel")
    return embed

class SupervisorCategorySelectView(ui.View):
    """Interactive category select menu attached to #supervisor-templates header embed."""

    def __init__(self):
        super().__init__(timeout=None)
        select = ui.Select(
            placeholder="🔍 Select a Supervisor / HR Leadership Template...",
            custom_id="supp_exec_tpl_select",
            options=[
                discord.SelectOption(label="Disciplinary Strike Warning", value="staff_strike_notice", emoji="⚠️", description="Formal Level 1/2/3 strike warning notice"),
                discord.SelectOption(label="Administrative Staff Suspension", value="staff_suspension_notice", emoji="⛔", description="Temporary suspension during HR inquiry"),
                discord.SelectOption(label="Demotion & Role Termination", value="staff_demotion_notice", emoji="🔻", description="Official staff demotion & role removal"),
                discord.SelectOption(label="Permanent Staff Blacklist", value="staff_blacklist_notice", emoji="🚫", description="Severe misconduct entry & global network ban"),
                discord.SelectOption(label="Executive Promotion Letter", value="promotion_appointment", emoji="👑", description="Official staff promotion & appointment notice"),
                discord.SelectOption(label="Appeal Approved Determination", value="appeal_ruling_approved", emoji="⚖️", description="Pardon penalty & restore clean standing"),
                discord.SelectOption(label="Appeal Denied Determination", value="appeal_ruling_denied", emoji="❌", description="Confirm penalty validity & final ruling"),
                discord.SelectOption(label="Executive LOA Authorization", value="loa_approval_formal", emoji="✈️", description="Approved leave of absence & quota exemption"),
                discord.SelectOption(label="Formal HR Incident Investigation", value="investigation_notice", emoji="🔍", description="Confidential inquiry directive & evidence call")
            ]
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        val = interaction.data["values"][0]
        all_tpls = {t["shortcut"]: t for t in get_combined_supervisor_template_list()}
        tpl = all_tpls.get(val) or BUILTIN_SUPERVISOR_TEMPLATES.get(val)

        if not tpl:
            await interaction.response.send_message("❌ Supervisor template not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"{tpl.get('emoji', '👑')} {tpl['title']}",
            description=(
                f"**Category:** `{tpl.get('category', 'Executive HR')}`\n\n"
                f"**📋 Executive Protocol (SOP):**\n"
                f"{tpl.get('steps', 'No specific steps.')}\n\n"
                f"**💬 Formal Executive Response Template:**\n"
                f"```\n{tpl['template']}\n```"
            ),
            color=0x9B59B6
        )
        embed.set_footer(text=f"Shortcut: {tpl['shortcut']} • Echo Technologies Executive SOP")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class SendSupervisorTemplateSelectView(ui.View):
    """Interactive template picker for Supervisors inside ticket channels to send executive responses directly to DMs."""

    def __init__(self, bot, ticket_id: int):
        super().__init__(timeout=180)
        self.bot = bot
        self.ticket_id = ticket_id

        all_tpls = get_combined_supervisor_template_list()
        options = []
        for t in all_tpls[:25]:
            options.append(
                discord.SelectOption(
                    label=t["title"][:100],
                    value=t["shortcut"],
                    emoji=t.get("emoji", "👑"),
                    description=t.get("category", "")[:50]
                )
            )

        select = ui.Select(
            placeholder="👑 Choose a formal Supervisor / HR directive to send to member DMs...",
            custom_id=f"send_exec_tpl_sel:{ticket_id}",
            options=options
        )
        select.callback = self.send_template_callback
        self.add_item(select)

    async def send_template_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        val = interaction.data["values"][0]
        all_tpls = {t["shortcut"]: t for t in get_combined_supervisor_template_list()}
        tpl = all_tpls.get(val) or BUILTIN_SUPERVISOR_TEMPLATES.get(val)

        if not tpl:
            await interaction.followup.send("❌ Supervisor template not found.", ephemeral=True)
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
            title=f"👑 Executive Directive Dispatched • {tpl['title']}",
            description=formatted_text,
            color=0x9B59B6,
            timestamp=discord.utils.utcnow()
        )
        channel_embed.set_author(name=f"Issued by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        channel_embed.set_footer(text=f"Supervisor Directive: {tpl['shortcut']} • Modmail Relayed to DM")
        await interaction.channel.send(embed=channel_embed)

        # Send DM to candidate
        try:
            dm = await candidate.create_dm()
            dm_embed = discord.Embed(
                title=f"👑 Echo Technologies Executive Directive • {tpl['title']}",
                description=formatted_text,
                color=0x9B59B6,
                timestamp=discord.utils.utcnow()
            )
            dm_embed.set_footer(text=f"Executive Reference #{self.ticket_id} • Official HR Communication")
            await dm.send(embed=dm_embed)
            await interaction.followup.send(f"✅ Dispatched **{tpl['title']}** formal directive directly to {candidate.mention}'s DMs!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"⚠️ Sent directive to ticket channel, but DM delivery failed: {e}", ephemeral=True)

async def sync_supervisor_templates_channel(bot, channel: Optional[discord.TextChannel] = None) -> bool:
    """Posts or refreshes the supervisor templates in #supervisor-templates (1556427867947278336)."""
    target_ch = channel or bot.get_channel(config.SUPERVISOR_TEMPLATES_CHANNEL_ID)
    if not target_ch:
        try:
            target_ch = await bot.fetch_channel(config.SUPERVISOR_TEMPLATES_CHANNEL_ID)
        except Exception as e:
            logger.warning(f"Could not fetch supervisor templates channel {config.SUPERVISOR_TEMPLATES_CHANNEL_ID}: {e}")
            return False

    if not isinstance(target_ch, discord.TextChannel):
        return False

    header_embed = await build_supervisor_header_embed(bot)
    view = SupervisorCategorySelectView()

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
        all_tpls = get_combined_supervisor_template_list()
        for tpl in all_tpls:
            em = discord.Embed(
                title=f"{tpl.get('emoji', '👑')} {tpl['title']}",
                description=(
                    f"**Category:** `{tpl.get('category', 'Executive HR')}`\n\n"
                    f"**📋 Executive Protocol (SOP):**\n"
                    f"{tpl.get('steps', 'No specific steps.')}\n\n"
                    f"**💬 Formal Executive Response Template:**\n"
                    f"```\n{tpl['template']}\n```"
                ),
                color=0x9B59B6
            )
            em.set_footer(text=f"Shortcut: {tpl['shortcut']} • Echo Technologies Executive Office")
            await target_ch.send(embed=em)

        logger.info(f"Posted supervisor templates guide to #{target_ch.name} ({target_ch.id})")
        return True
    except Exception as e:
        logger.error(f"Error syncing supervisor templates: {e}")
        return False
