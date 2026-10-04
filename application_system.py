import discord
from discord import ui
import sqlite3
import json
import logging
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timezone
import config

logger = logging.getLogger("ApplicationSystem")
DB_PATH = "verifications.db"

# Positions & Questionnaire Configurations
APPLICATION_POSITIONS: Dict[str, Dict[str, Any]] = {
    "product_development": {
        "title": "Product Development",
        "emoji": "🛠️",
        "role_id": config.DEVELOPMENT_TEAM_ROLE_ID,
        "description": "Create innovative Roblox assets, game mechanics, 3D models, and studio systems for Echo Technologies.",
        "questions": [
            "What is your primary development specialization (e.g. Luau Scripting, 3D Modeling/Blender, Building, UI/UX Design, Animation, Sound Design) and how many years have you been developing in Roblox Studio?",
            "Please share links to your portfolio, DevForum profile, Roblox creations, GitHub, or upload screenshot/video attachments of your work right here in this DM!",
            "Describe a complex system or feature you created in the past. What technical challenges (e.g. performance, memory leaks, client-server replication) did you overcome and how?",
            "How familiar are you with clean code standards, modular script architecture (e.g. Knit, ModuleScripts, strict Luau typing), and Git / Rojo workflows?",
            "What is your estimated weekly availability (hours/week), your timezone, and how do you handle development deadlines and project feedback?",
            "How do you handle constructive criticism and peer reviews if a project lead asks for revisions on your work?",
            "What kind of products, assets, or gameplay systems are you most excited to create for Echo Technologies?"
        ]
    },
    "support_team": {
        "title": "Support Team",
        "emoji": "🛡️",
        "role_id": config.SUPPORT_TEAM_ROLE_ID,
        "description": "Assist community members, handle support tickets, and maintain a safe server environment.",
        "questions": [
            "What is your age/age range, your timezone, and approximately how many hours per week can you dedicate to staffing tickets and the server?",
            "Do you have any past experience in moderation, support teams, or customer service on Roblox or Discord? Please list servers or groups if applicable.",
            "Scenario A: A customer opens a ticket frustrated that an asset they purchased is not functioning properly in their game. How would you de-escalate their frustration and assist them in troubleshooting?",
            "Scenario B: A member opens a ticket claiming another player exploited or scammed them in our game. What steps and proof would you gather before taking administrative action?",
            "Scenario C: You encounter a situation in a ticket or chat where server rules are ambiguous, or you are unsure how to handle a customer's request. What is your course of action?",
            "How do you handle high-pressure situations or rude/provocative members while maintaining professional customer service?",
            "Why do you want to join the Echo Technologies Support Team specifically, and what qualities make you a great fit?"
        ]
    },
    "public_relations": {
        "title": "Public Relations",
        "emoji": "📢",
        "role_id": config.PUBLIC_RELATIONS_ROLE_ID,
        "description": "Manage community outreach, social media, studio announcements, affiliate partnerships, and brand marketing.",
        "questions": [
            "What is your timezone, estimated weekly availability, and prior experience in public relations, community outreach, or marketing for Roblox/Discord groups?",
            "How would you describe your communication style, and how comfortable are you drafting public announcements, event promos, and release notes on behalf of Echo Technologies?",
            "Scenario A: A community member starts public drama or spreads false rumors about Echo Technologies in chat or on social media. How would you de-escalate and address this professionally?",
            "Scenario B: We are releasing a major new Roblox asset or game update. How would you plan and promote the release across our Discord, Roblox group, and social channels to maximize engagement?",
            "How would you approach reaching out to and negotiating partnerships with other prominent Roblox studios, development groups, or content creators?",
            "What creative event ideas, community initiatives, or marketing strategies would you bring to Echo Technologies to grow active community participation?",
            "Why do you want to join our Public Relations team specifically, and what makes you the ideal brand ambassador for Echo Technologies?"
        ]
    }
}

def init_applications_db():
    """Initializes tables for staff & developer applications and status settings."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                position_key TEXT NOT NULL,
                position_title TEXT NOT NULL,
                status TEXT DEFAULT 'in_progress', -- 'in_progress', 'pending_review', 'approved', 'denied', 'cancelled'
                current_step INTEGER DEFAULT 0,
                answers TEXT, -- JSON array of strings
                attachments TEXT, -- JSON array of attachment URLs
                reviewed_by INTEGER,
                review_note TEXT,
                log_message_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS application_settings (
                position_key TEXT PRIMARY KEY,
                is_open INTEGER DEFAULT 1,
                closed_reason TEXT DEFAULT '',
                closed_by INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

init_applications_db()

def get_position_status(position_key: str) -> Dict[str, Any]:
    """Returns status dictionary for a specific position."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM application_settings WHERE position_key = ?;", (position_key,))
        row = cursor.fetchone()
        if row:
            return {
                "position_key": row["position_key"],
                "is_open": bool(row["is_open"]),
                "closed_reason": row["closed_reason"] or "",
                "closed_by": row["closed_by"] or 0,
                "updated_at": row["updated_at"]
            }
        return {
            "position_key": position_key,
            "is_open": True,
            "closed_reason": "",
            "closed_by": 0,
            "updated_at": None
        }

def is_position_open(position_key: str) -> Tuple[bool, str]:
    """Returns (is_open: bool, closed_reason: str)."""
    status = get_position_status(position_key)
    return status["is_open"], status["closed_reason"]

def get_all_position_statuses() -> Dict[str, Dict[str, Any]]:
    """Returns statuses for all known application positions."""
    statuses = {}
    for key in APPLICATION_POSITIONS.keys():
        statuses[key] = get_position_status(key)
    return statuses

def set_position_status(
    position_key: str,
    is_open: bool,
    closed_reason: str = "",
    closed_by: int = 0
) -> List[str]:
    """
    Sets open/closed status for a position or 'all' positions.
    Returns list of affected position keys.
    """
    keys_to_update = list(APPLICATION_POSITIONS.keys()) if position_key.lower() == "all" else [position_key]
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for key in keys_to_update:
            cursor.execute("""
                INSERT INTO application_settings (position_key, is_open, closed_reason, closed_by, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(position_key) DO UPDATE SET
                    is_open = excluded.is_open,
                    closed_reason = excluded.closed_reason,
                    closed_by = excluded.closed_by,
                    updated_at = excluded.updated_at;
            """, (key, 1 if is_open else 0, closed_reason, closed_by))
        conn.commit()
    return keys_to_update

def close_applications(position_key: str = "all", reason: str = "", closed_by: int = 0) -> List[str]:
    """Closes applications for one or all positions."""
    return set_position_status(position_key, is_open=False, closed_reason=reason, closed_by=closed_by)

def open_applications(position_key: str = "all", opened_by: int = 0) -> List[str]:
    """Re-opens applications for one or all positions."""
    return set_position_status(position_key, is_open=True, closed_reason="", closed_by=opened_by)

def get_application_stats() -> Dict[str, int]:
    """Returns counts of applications grouped by status."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, COUNT(*) FROM applications GROUP BY status;")
        rows = cursor.fetchall()
        stats = {status: count for status, count in rows}
        cursor.execute("SELECT COUNT(*) FROM applications;")
        stats["total"] = cursor.fetchone()[0]
        return stats

def get_active_application_session(user_id: int) -> Optional[Dict[str, Any]]:
    """Checks if a user currently has an in-progress application session."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM applications
            WHERE user_id = ? AND status = 'in_progress'
            ORDER BY created_at DESC LIMIT 1;
        """, (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_pending_review_application(user_id: int) -> Optional[Dict[str, Any]]:
    """Checks if a user has an application currently pending review."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM applications
            WHERE user_id = ? AND status = 'pending_review'
            ORDER BY created_at DESC LIMIT 1;
        """, (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_application(app_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves an application record by ID."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM applications WHERE id = ?;", (app_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def create_application_session(user_id: int, guild_id: int, position_key: str) -> Tuple[bool, str, Optional[int]]:
    """Starts a new application session if position is open and no active session or pending application exists."""
    pos_data = APPLICATION_POSITIONS.get(position_key)
    if not pos_data:
        return False, "Invalid position selected.", None

    is_open, closed_reason = is_position_open(position_key)
    if not is_open:
        reason_msg = f"\n**Reason:** *{closed_reason}*" if closed_reason else ""
        return False, f"❌ Applications for **{pos_data['title']}** are currently closed.{reason_msg}", None

    active = get_active_application_session(user_id)
    if active:
        return False, f"You already have an active application session for **{active['position_title']}** in your DMs. Complete it or type `cancel` to start over.", active["id"]

    pending = get_pending_review_application(user_id)
    if pending:
        return False, f"You already have an application for **{pending['position_title']}** under review by management! Please await our decision.", pending["id"]

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO applications (user_id, guild_id, position_key, position_title, status, current_step, answers, attachments)
            VALUES (?, ?, ?, ?, 'in_progress', 0, '[]', '[]');
        """, (user_id, guild_id, position_key, pos_data["title"]))
        conn.commit()
        return True, "Application started.", cursor.lastrowid

def cancel_application_session(user_id: int) -> bool:
    """Cancels any in-progress application session for the user."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE applications SET status = 'cancelled' WHERE user_id = ? AND status = 'in_progress';", (user_id,))
        conn.commit()
        return cursor.rowcount > 0

def advance_application_step(
    app_id: int,
    answer_text: str,
    new_attachments: Optional[List[str]] = None
) -> Tuple[bool, int, bool]:
    """
    Saves the user's answer and attachments, advancing to the next question step.
    Returns: (success: bool, next_step: int, is_completed: bool)
    """
    app = get_application(app_id)
    if not app or app["status"] != "in_progress":
        return False, 0, False

    pos_key = app["position_key"]
    pos_data = APPLICATION_POSITIONS.get(pos_key)
    if not pos_data:
        return False, 0, False

    total_questions = len(pos_data["questions"])

    # Parse existing answers & attachments
    answers = json.loads(app["answers"] or "[]")
    attachments = json.loads(app["attachments"] or "[]")

    answers.append(answer_text.strip())
    if new_attachments:
        attachments.extend(new_attachments)

    next_step = app["current_step"] + 1
    is_completed = next_step >= total_questions

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if is_completed:
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
                UPDATE applications
                SET current_step = ?, answers = ?, attachments = ?, status = 'pending_review', completed_at = ?
                WHERE id = ?;
            """, (next_step, json.dumps(answers), json.dumps(attachments), now_iso, app_id))
        else:
            cursor.execute("""
                UPDATE applications
                SET current_step = ?, answers = ?, attachments = ?
                WHERE id = ?;
            """, (next_step, json.dumps(answers), json.dumps(attachments), app_id))
        conn.commit()

    return True, next_step, is_completed

def set_application_log_message(app_id: int, message_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE applications SET log_message_id = ? WHERE id = ?;", (message_id, app_id))
        conn.commit()

def review_application(
    app_id: int,
    reviewer_id: int,
    status: str,
    review_note: Optional[str] = None
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Updates an application to approved or denied."""
    app = get_application(app_id)
    if not app:
        return False, "Application not found.", None
    if app["status"] not in ("pending_review", "in_progress"):
        return False, f"Application has already been marked **{app['status']}**.", app

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE applications
            SET status = ?, reviewed_by = ?, review_note = ?
            WHERE id = ?;
        """, (status, reviewer_id, review_note, app_id))
        conn.commit()

    updated = get_application(app_id)
    return True, f"Application #{app_id} marked {status}.", updated

# --- PRESENTATION BUILDERS ---

def build_career_panel_embed() -> discord.Embed:
    """Builds the public career recruitment panel for #career-opportunities reflecting current open/closed status."""
    statuses = get_all_position_statuses()
    all_closed = all(not s["is_open"] for s in statuses.values())

    embed = discord.Embed(
        title="💼 Echo Technologies • Career Opportunities",
        description=(
            "Join the official Echo Technologies team! We are looking for talented, passionate, "
            "and dedicated community members to help build our games, products, and community.\n\n"
            "**Open Positions & Current Vacancies:**\n\n"
        ),
        color=0xED4245 if all_closed else 0x5865F2
    )

    for key, data in APPLICATION_POSITIONS.items():
        st = statuses.get(key, {"is_open": True, "closed_reason": ""})
        if st["is_open"]:
            status_badge = "🟢 **OPEN**"
        else:
            reason_str = f" — *{st['closed_reason']}*" if st["closed_reason"] else ""
            status_badge = f"🔴 **CLOSED**{reason_str}"
        embed.description += (
            f"{data['emoji']} **{data['title']}** • {status_badge}\n"
            f"{data['description']}\n\n"
        )

    embed.description += (
        "────────────────────────────────────────\n"
        "**How to Apply:**\n"
    )
    if all_closed:
        embed.description += "⚠️ *All applications are currently closed. Please monitor announcements for future openings!*"
    else:
        embed.description += "Click an open position button below to begin your Direct Message (DM) application session!"

    embed.add_field(
        name="📋 Requirements",
        value=(
            "• Must have a linked & verified Roblox account\n"
            "• Must have Discord Direct Messages enabled from server members\n"
            "• Mature, responsible, and active within our community"
        ),
        inline=False
    )
    embed.set_footer(text="Echo Technologies Recruitment • Private Direct Message Application")
    return embed

class CareerLaunchView(ui.View):
    """Persistent button view attached to the #career-opportunities embed."""

    def __init__(self):
        super().__init__(timeout=None)
        statuses = get_all_position_statuses()

        pd_open = statuses.get("product_development", {}).get("is_open", True)
        self.add_item(
            ui.Button(
                label="Apply: Product Development" if pd_open else "Product Development (Closed)",
                emoji="🛠️" if pd_open else "🔒",
                style=discord.ButtonStyle.primary if pd_open else discord.ButtonStyle.secondary,
                disabled=not pd_open,
                custom_id="app_start:product_development"
            )
        )

        st_open = statuses.get("support_team", {}).get("is_open", True)
        self.add_item(
            ui.Button(
                label="Apply: Support Team" if st_open else "Support Team (Closed)",
                emoji="🛡️" if st_open else "🔒",
                style=discord.ButtonStyle.success if st_open else discord.ButtonStyle.secondary,
                disabled=not st_open,
                custom_id="app_start:support_team"
            )
        )

        pr_open = statuses.get("public_relations", {}).get("is_open", True)
        self.add_item(
            ui.Button(
                label="Apply: Public Relations" if pr_open else "Public Relations (Closed)",
                emoji="📢" if pr_open else "🔒",
                style=discord.ButtonStyle.primary if pr_open else discord.ButtonStyle.secondary,
                disabled=not pr_open,
                custom_id="app_start:public_relations"
            )
        )


def build_application_dossier_embed(
    app_data: Dict[str, Any],
    applicant: Optional[discord.User] = None,
    roblox_info: Optional[Dict[str, Any]] = None,
    reviewer: Optional[discord.User] = None
) -> discord.Embed:
    """Builds comprehensive HR review dossier embed for staff review."""
    pos_key = app_data["position_key"]
    pos_data = APPLICATION_POSITIONS.get(pos_key, {"title": app_data["position_title"], "questions": []})
    status = app_data["status"]

    colors = {
        "pending_review": 0x5865F2,
        "approved": 0x57F287,
        "denied": 0xED4245,
        "in_progress": 0xFEE75C,
        "cancelled": 0x747F8D
    }
    color = colors.get(status, 0x5865F2)

    app_id = app_data["id"]
    uid = app_data["user_id"]
    user_name = applicant.name if applicant else f"User {uid}"
    user_mention = applicant.mention if applicant else f"<@{uid}>"

    # Roblox Info format
    if roblox_info:
        rbx_id = roblox_info["roblox_id"]
        rbx_tag = f"**{roblox_info['roblox_display_name']}** (`@{roblox_info['roblox_username']}`)"
        rbx_link = f"[{rbx_id}](https://www.roblox.com/users/{rbx_id}/profile)"
        roblox_field = f"{rbx_tag}\nID: {rbx_link} • ✅ **Verified**"
    else:
        roblox_field = "❌ **Unverified Roblox Account**"

    embed = discord.Embed(
        title=f"📋 Application #{app_id} • {app_data['position_title']}",
        description=f"Status: **{status.replace('_', ' ').upper()}**",
        color=color,
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(name="👤 Candidate", value=f"{user_mention} (`{user_name}` | `{uid}`)", inline=True)
    embed.add_field(name="🎮 Roblox Profile", value=roblox_field, inline=True)
    embed.add_field(name="💼 Applied Role", value=f"**{app_data['position_title']}**", inline=True)

    # Question & Answer Breakdown
    answers = json.loads(app_data["answers"] or "[]")
    questions = pos_data.get("questions", [])

    for i, ans in enumerate(answers):
        q_text = questions[i] if i < len(questions) else f"Question {i+1}"
        # Truncate if long
        ans_display = ans[:1000] if ans else "*No response provided*"
        embed.add_field(
            name=f"Q{i+1}: {q_text[:120]}",
            value=f"> {ans_display}",
            inline=False
        )

    # Attachments
    attachments = json.loads(app_data["attachments"] or "[]")
    if attachments:
        att_links = "\n".join([f"• [Attachment {idx+1}]({url})" for idx, url in enumerate(attachments[:5])])
        embed.add_field(name="📎 Uploaded Portfolio / Files", value=att_links, inline=False)
        # Display first image as thumbnail/image
        first_img = next((u for u in attachments if any(u.lower().endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.webp', '.gif'))), None)
        if first_img:
            embed.set_image(url=first_img)

    if reviewer:
        embed.add_field(name="⚖️ Reviewed By", value=reviewer.mention, inline=True)
    if app_data.get("review_note"):
        embed.add_field(name="📝 HR Feedback Note", value=f"`{app_data['review_note']}`", inline=False)

    embed.set_footer(text=f"Application #{app_id} • Echo Technologies HR Desk")
    return embed

class ApplicationControlView(ui.View):
    """Interactive HR management buttons on the application dossier."""

    def __init__(self, app_id: int, disabled: bool = False):
        super().__init__(timeout=None)
        self.app_id = app_id
        self.add_item(
            ui.Button(
                label="Accept & Send Offer",
                emoji="✅",
                style=discord.ButtonStyle.success,
                custom_id=f"app_acc:{app_id}",
                disabled=disabled
            )
        )
        self.add_item(
            ui.Button(
                label="Deny Application",
                emoji="❌",
                style=discord.ButtonStyle.danger,
                custom_id=f"app_dec:{app_id}",
                disabled=disabled
            )
        )
        self.add_item(
            ui.Button(
                label="Ask Follow-up",
                emoji="💬",
                style=discord.ButtonStyle.secondary,
                custom_id=f"app_ask:{app_id}",
                disabled=disabled
            )
        )

class DenyApplicationModal(ui.Modal):
    """Modal for HR to supply feedback when declining an applicant."""

    feedback_input = ui.TextInput(
        label="Feedback / Reason for Candidate",
        placeholder="Explain constructively why the application was declined (experience, portfolio, etc.)...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=800
    )

    def __init__(self, bot, app_id: int):
        super().__init__(title=f"Deny Application #{app_id}")
        self.bot = bot
        self.app_id = app_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        feedback = self.feedback_input.value.strip()

        success, msg, updated = review_application(
            self.app_id,
            interaction.user.id,
            "denied",
            review_note=feedback
        )
        if not success:
            await interaction.followup.send(f"⚠️ {msg}", ephemeral=True)
            return

        # Update review embed
        candidate = self.bot.get_user(updated["user_id"])
        roblox_info = self.bot.db.get_by_discord_id(updated["user_id"])
        new_embed = build_application_dossier_embed(updated, candidate, roblox_info, interaction.user)
        new_view = ApplicationControlView(self.app_id, disabled=True)

        try:
            await interaction.message.edit(embed=new_embed, view=new_view)
        except Exception:
            pass

        # Send constructive feedback DM to candidate
        if candidate:
            try:
                dm = await candidate.create_dm()
                dm_embed = discord.Embed(
                    title=f"💼 Application Status Update • {updated['position_title']}",
                    description=(
                        f"Hello **{candidate.name}**,\n\n"
                        f"Thank you for your interest and for taking the time to apply for **{updated['position_title']}** at Echo Technologies.\n\n"
                        f"After careful review by our leadership team, we have decided not to move forward with your application at this time.\n\n"
                        f"**Feedback from Leadership:**\n> {feedback}\n\n"
                        f"You are welcome to reapply in the future as you gain more experience. We wish you the best in your endeavors!"
                    ),
                    color=0xED4245
                )
                dm_embed.set_footer(text="Echo Technologies Careers")
                await dm.send(embed=dm_embed)
            except Exception as e:
                logger.warning(f"Could not send denial feedback DM to candidate {candidate.id}: {e}")

        await interaction.followup.send(f"❌ Application `#{self.app_id}` marked **Denied** and feedback dispatched.", ephemeral=True)

class AskApplicantModal(ui.Modal):
    """Modal for HR to relay a specific follow-up question to the candidate's DM."""

    question_input = ui.TextInput(
        label="Follow-up Question for Candidate",
        placeholder="Type the question or interview prompt to send directly to the applicant's DM...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=800
    )

    def __init__(self, bot, app_id: int):
        super().__init__(title=f"Message Candidate • App #{app_id}")
        self.bot = bot
        self.app_id = app_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        app = get_application(self.app_id)
        if not app:
            await interaction.followup.send("❌ Application not found.", ephemeral=True)
            return

        candidate = self.bot.get_user(app["user_id"])
        if not candidate:
            try:
                candidate = await self.bot.fetch_user(app["user_id"])
            except Exception:
                candidate = None

        if not candidate:
            await interaction.followup.send("❌ Could not find candidate user.", ephemeral=True)
            return

        question_text = self.question_input.value.strip()
        try:
            dm = await candidate.create_dm()
            msg_embed = discord.Embed(
                title=f"💬 Question Regarding Your {app['position_title']} Application",
                description=(
                    f"Hello **{candidate.name}**,\n\n"
                    f"Our leadership team is reviewing your application for **{app['position_title']}** and has a follow-up question for you:\n\n"
                    f"> **{question_text}**\n\n"
                    f"*(Please reply directly in this DM thread so staff can review your response.)*"
                ),
                color=0x5865F2
            )
            msg_embed.set_footer(text=f"Echo Technologies HR • App #{self.app_id}")
            await dm.send(embed=msg_embed)
            await interaction.followup.send(f"✅ Dispatched follow-up question to {candidate.mention}'s DMs!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to DM candidate (DMs may be closed): {e}", ephemeral=True)


# --- INTERVIEW FLOW DISPATCHERS ---

async def start_dm_application_flow(
    bot,
    user: discord.User,
    guild: discord.Guild,
    position_key: str
) -> Tuple[bool, str]:
    """
    Initiates the Direct Message interview flow with the user.
    """
    pos_data = APPLICATION_POSITIONS.get(position_key)
    if not pos_data:
        return False, "❌ Invalid position selected."

    # Check recruitment blacklist (#7)
    from hr_system import is_staff_blacklisted
    bl = is_staff_blacklisted(user.id)
    if bl:
        return False, f"⛔ **Application Denied:** Your account is blacklisted from staff recruitment.\n**Reason:** {bl['reason']}"

    success, msg, app_id = create_application_session(user.id, guild.id, position_key)
    if not success:
        return False, msg

    questions = pos_data["questions"]
    q1 = questions[0]

    opening_embed = discord.Embed(
        title=f"🚀 Echo Technologies Application • {pos_data['title']}",
        description=(
            f"Hello **{user.name}**! Welcome to the application process for **{pos_data['title']}**.\n\n"
            f"We will ask you **{len(questions)} questions** one at a time. "
            f"Simply reply directly in this DM chat to submit your answer to each question.\n\n"
            f"💡 **Tips:**\n"
            f"• Take your time and provide detailed, thoughtful answers.\n"
            f"• You can upload images or file attachments with your messages.\n"
            f"• You can type `cancel` at any point to withdraw this application.\n\n"
            f"────────────────────────────────────────\n"
            f"**Question 1 of {len(questions)}:**\n"
            f"👉 {q1}"
        ),
        color=0x5865F2
    )
    opening_embed.set_footer(text=f"Application #{app_id} • Reply below to answer")

    try:
        dm = await user.create_dm()
        await dm.send(embed=opening_embed)
        return True, f"📬 **Application interview started!** Please check your **Direct Messages (DMs)** from {bot.user.name} to answer Question 1."
    except discord.Forbidden:
        # Revert session if bot cannot DM
        cancel_application_session(user.id)
        return False, "❌ Could not send you a Direct Message! Please enable **Allow direct messages from server members** in your Discord Privacy Settings and try again."
    except Exception as e:
        cancel_application_session(user.id)
        return False, f"❌ An error occurred while opening your application: {e}"

async def handle_applicant_dm_message(bot, message: discord.Message) -> bool:
    """
    Handles a message from an applicant in DMs who is currently filling out an application.
    Returns True if the message was consumed by the application system.
    """
    session = get_active_application_session(message.author.id)
    if not session:
        return False

    app_id = session["id"]
    pos_key = session["position_key"]
    pos_data = APPLICATION_POSITIONS.get(pos_key)
    if not pos_data:
        return False

    # Check for cancellation
    if message.content and message.content.strip().lower() == "cancel":
        cancel_application_session(message.author.id)
        cancel_embed = discord.Embed(
            title="🛑 Application Cancelled",
            description="Your application session has been cancelled. You may apply again from the server panel whenever you're ready!",
            color=0x747F8D
        )
        await message.channel.send(embed=cancel_embed)
        return True

    # Collect answer text + attachments
    att_urls = [a.url for a in message.attachments]
    answer_text = message.content or ("*(Uploaded file attachment)*" if att_urls else "")

    if not answer_text and not att_urls:
        await message.channel.send("⚠️ Please provide a written answer or file attachment for this question.")
        return True

    questions = pos_data["questions"]
    success, next_step, is_completed = advance_application_step(app_id, answer_text, att_urls)
    if not success:
        return False

    if not is_completed:
        next_q = questions[next_step]
        q_embed = discord.Embed(
            title=f"📝 Question {next_step + 1} of {len(questions)}",
            description=f"👉 **{next_q}**\n\n*(Type your response below, or upload attachments)*",
            color=0x5865F2
        )
        q_embed.set_footer(text=f"Application #{app_id} • Question {next_step + 1} of {len(questions)}")
        await message.channel.send(embed=q_embed)
        return True
    else:
        # Application Completed!
        finished_embed = discord.Embed(
            title="🎉 Application Submitted Successfully!",
            description=(
                f"Thank you for completing your application for **{pos_data['title']}**!\n\n"
                f"Our leadership team has received your submission and will review it thoroughly. "
                f"You will receive an update right here in your Direct Messages once a decision has been reached.\n\n"
                f"Best of luck from the Echo Technologies Team!"
            ),
            color=0x57F287
        )
        finished_embed.set_footer(text=f"Application #{app_id} • Received")
        await message.channel.send(embed=finished_embed)

        # Dispatch Dossier to Applications Review Channel (#applications: 1556027504429633738)
        app_record = get_application(app_id)
        guild = bot.get_guild(session["guild_id"]) or bot.get_primary_guild()
        if guild:
            app_ch = guild.get_channel(config.APPLICATIONS_SUBMISSIONS_CHANNEL_ID)
            if not app_ch:
                try:
                    app_ch = await bot.fetch_channel(config.APPLICATIONS_SUBMISSIONS_CHANNEL_ID)
                except Exception:
                    app_ch = guild.get_channel(config.HR_LOGS_CHANNEL_ID)

            if app_ch and isinstance(app_ch, discord.TextChannel):
                roblox_info = bot.db.get_by_discord_id(message.author.id)
                dossier_embed = build_application_dossier_embed(app_record, message.author, roblox_info)
                view = ApplicationControlView(app_id)
                try:
                    log_msg = await app_ch.send(
                        content=f"🚨 **New Staff Application Submitted:** <@{message.author.id}> applied for **{pos_data['title']}**!",
                        embed=dossier_embed,
                        view=view
                    )
                    set_application_log_message(app_id, log_msg.id)
                    logger.info(f"Application #{app_id} dossier dispatched to #{app_ch.name} ({app_ch.id})")
                except Exception as e:
                    logger.error(f"Error posting application dossier to applications channel: {e}")

        return True

async def sync_career_panel_message(bot) -> bool:
    """
    Finds and edits the active career panel message in #career-opportunities
    so the button states and open/closed badges reflect instantly.
    """
    ch_id = config.CAREER_OPPORTUNITIES_CHANNEL_ID
    ch = bot.get_channel(ch_id)
    if not ch:
        try:
            ch = await bot.fetch_channel(ch_id)
        except Exception as e:
            logger.warning(f"Could not fetch career channel {ch_id}: {e}")
            return False

    if not isinstance(ch, discord.TextChannel):
        return False

    new_embed = build_career_panel_embed()
    new_view = CareerLaunchView()

    try:
        async for msg in ch.history(limit=25):
            if msg.author.id == bot.user.id and msg.embeds:
                for em in msg.embeds:
                    if em.title and "Career Opportunities" in em.title:
                        await msg.edit(embed=new_embed, view=new_view)
                        logger.info(f"Updated live career panel message {msg.id}")
                        return True

        # If not found in history, send a new one
        await ch.send(embed=new_embed, view=new_view)
        logger.info("Sent new career recruitment panel message.")
        return True
    except Exception as e:
        logger.error(f"Error syncing career panel message: {e}")
        return False
