import discord
from discord import ui
import sqlite3
import json
import logging
import secrets
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timezone, timedelta
from groq import AsyncGroq
import config

logger = logging.getLogger("PointsSystem")
DB_PATH = "verifications.db"

# In-memory cooldowns to prevent spamming Groq API per user
_user_eval_cooldowns: Dict[int, datetime] = {}
COOLDOWN_SECONDS = 120 # 2 minutes between AI point evaluations per user

# In-memory tipping cooldowns
_user_tip_cooldowns: Dict[int, datetime] = {}
TIP_COOLDOWN_SECONDS = 30

def init_points_db():
    """Initializes tables for community points, transactions, and rewards redemptions."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_points (
                user_id INTEGER PRIMARY KEY,
                points INTEGER DEFAULT 0,
                total_earned INTEGER DEFAULT 0,
                has_claimed_reward INTEGER DEFAULT 0,
                reward_notified INTEGER DEFAULT 0,
                last_point_at TIMESTAMP DEFAULT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS point_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                source TEXT NOT NULL, -- 'ai_evaluation', 'staff_add', 'staff_remove', 'staff_set', 'tip_sent', 'tip_received', 'reward_redeem'
                reason TEXT NOT NULL,
                moderator_id INTEGER DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_redemptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                reward_id TEXT NOT NULL,
                reward_name TEXT NOT NULL,
                cost INTEGER NOT NULL,
                coupon_code TEXT DEFAULT NULL,
                status TEXT DEFAULT 'completed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

init_points_db()

def get_user_points(user_id: int) -> Dict[str, Any]:
    """Retrieves point data for a member."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_points WHERE user_id = ?;", (user_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return {
            "user_id": user_id,
            "points": 0,
            "total_earned": 0,
            "has_claimed_reward": 0,
            "reward_notified": 0,
            "last_point_at": None,
            "updated_at": None
        }

def add_points(
    user_id: int,
    amount: int = 1,
    source: str = "staff_add",
    reason: str = "Community contribution",
    moderator_id: Optional[int] = None
) -> Tuple[int, bool]:
    """
    Adds points to a user.
    Returns: (new_points_total: int, just_unlocked_reward: bool)
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_points WHERE user_id = ?;", (user_id,))
        row = cursor.fetchone()

        if row:
            old_points = row["points"]
            new_points = old_points + amount
            total_earned = row["total_earned"] + (amount if amount > 0 else 0)
            reward_notified = row["reward_notified"]
            unlocked_reward = False

            if new_points >= 5 and not reward_notified:
                unlocked_reward = True
                reward_notified = 1

            cursor.execute("""
                UPDATE user_points
                SET points = ?, total_earned = ?, reward_notified = ?, last_point_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?;
            """, (new_points, total_earned, reward_notified, user_id))
        else:
            new_points = amount
            total_earned = amount if amount > 0 else 0
            unlocked_reward = new_points >= 5
            reward_notified = 1 if unlocked_reward else 0

            cursor.execute("""
                INSERT INTO user_points (user_id, points, total_earned, reward_notified, last_point_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP);
            """, (user_id, new_points, total_earned, reward_notified))

        # Log transaction
        cursor.execute("""
            INSERT INTO point_transactions (user_id, amount, source, reason, moderator_id)
            VALUES (?, ?, ?, ?, ?);
        """, (user_id, amount, source, reason, moderator_id))

        conn.commit()
        return new_points, unlocked_reward

def remove_points(
    user_id: int,
    amount: int = 1,
    source: str = "staff_remove",
    reason: str = "Deducted by staff",
    moderator_id: Optional[int] = None
) -> int:
    """Removes points from a user (floor at 0). Returns new total."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_points WHERE user_id = ?;", (user_id,))
        row = cursor.fetchone()
        if not row:
            return 0

        old_points = row["points"]
        new_points = max(0, old_points - amount)

        cursor.execute("""
            UPDATE user_points
            SET points = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?;
        """, (new_points, user_id))

        cursor.execute("""
            INSERT INTO point_transactions (user_id, amount, source, reason, moderator_id)
            VALUES (?, ?, ?, ?, ?);
        """, (user_id, -amount, source, reason, moderator_id))

        conn.commit()
        return new_points

def set_points(
    user_id: int,
    amount: int,
    reason: str = "Set by staff",
    moderator_id: Optional[int] = None
) -> Tuple[int, bool]:
    """Sets a member's points to an exact value."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_points WHERE user_id = ?;", (user_id,))
        row = cursor.fetchone()

        new_points = max(0, amount)
        unlocked_reward = False

        if row:
            reward_notified = row["reward_notified"]
            if new_points >= 5 and not reward_notified:
                unlocked_reward = True
                reward_notified = 1
            cursor.execute("""
                UPDATE user_points
                SET points = ?, reward_notified = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?;
            """, (new_points, reward_notified, user_id))
        else:
            unlocked_reward = new_points >= 5
            cursor.execute("""
                INSERT INTO user_points (user_id, points, total_earned, reward_notified)
                VALUES (?, ?, ?, ?);
            """, (user_id, new_points, new_points, 1 if unlocked_reward else 0))

        cursor.execute("""
            INSERT INTO point_transactions (user_id, amount, source, reason, moderator_id)
            VALUES (?, ?, 'staff_set', ?, ?);
        """, (user_id, new_points, reason, moderator_id))

        conn.commit()
        return new_points, unlocked_reward

def mark_reward_claimed(user_id: int, claimed: bool = True) -> bool:
    """Marks whether the user has claimed their free Echo Blacklist System."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE user_points
            SET has_claimed_reward = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?;
        """, (1 if claimed else 0, user_id))
        conn.commit()
        return cursor.rowcount > 0

def get_points_leaderboard(limit: int = 10) -> List[Dict[str, Any]]:
    """Returns top members ranked by current points balance."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM user_points
            ORDER BY points DESC, total_earned DESC
            LIMIT ?;
        """, (limit,))
        return [dict(r) for r in cursor.fetchall()]

def render_progress_bar(current: int, total: int = 5, length: int = 8) -> str:
    """Renders a clean text progress bar [████░] 4/5."""
    filled = min(length, int((min(current, total) / total) * length))
    empty = length - filled
    bar = "█" * filled + "░" * empty
    return f"[{bar}] `{current}/{total}`"


# --- GROQ AI CHAT EVALUATOR ---

async def evaluate_message_for_point(message: discord.Message) -> Tuple[bool, str]:
    """
    Evaluates whether a member's chat message deserves a community contribution point.
    Returns: (should_award: bool, reason: str)
    """
    if not config.GROQ_API_KEY:
        return False, "Groq API key not configured."

    uid = message.author.id
    now = datetime.now(timezone.utc)

    # Check cooldown
    last_eval = _user_eval_cooldowns.get(uid)
    if last_eval and (now - last_eval).total_seconds() < COOLDOWN_SECONDS:
        return False, "Evaluation on cooldown."

    content = message.content.strip()
    words = content.split()
    if len(words) < 5 or len(content) < 22:
        return False, "Message too short for point consideration."

    # Avoid bot commands
    if content.startswith(("/", "!", "?", ".", "-")):
        return False, "Command syntax."

    _user_eval_cooldowns[uid] = now

    prompt = (
        "You are the Echo Technologies Community AI Evaluator.\n"
        "Your task is to analyze a Discord member's chat message in a Roblox game development studio & asset store server.\n"
        "Determine if this message represents a genuine, high-quality, or helpful contribution deserving of a Community Point.\n\n"
        "Criteria to award a point:\n"
        "- Helping another community member with Roblox scripting, 3D modeling, UI, or technical questions.\n"
        "- Providing thoughtful, constructive feedback, creative ideas, or game development advice.\n"
        "- High-effort, welcoming, or positive engagement that improves community knowledge.\n\n"
        "DO NOT award points for:\n"
        "- Casual greetings ('hi', 'hey', 'wsp', 'how are you').\n"
        "- Short reactions, memes, laughs, slang ('lol', 'lmao', 'fr', 'gg', 'ok').\n"
        "- Basic server inquiries ('how do i buy', 'when is update').\n"
        "- Begging for points or low-effort filler text.\n\n"
        f"Message to analyze from user '{message.author.name}':\n"
        f'"{content}"\n\n'
        "Respond in strict JSON with no extra markdown formatting:\n"
        '{"award": true or false, "reason": "brief 1-sentence explanation"}'
    )

    try:
        groq_client = AsyncGroq(api_key=config.GROQ_API_KEY)
        response = await groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a fair, strict community evaluation AI. Output strictly JSON."},
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.2,
            max_tokens=150
        )
        reply = response.choices[0].message.content.strip()

        # Parse JSON
        if "```json" in reply:
            reply = reply.split("```json")[1].split("```")[0].strip()
        elif "```" in reply:
            reply = reply.split("```")[1].split("```")[0].strip()

        data = json.loads(reply)
        award = bool(data.get("award", False))
        reason = str(data.get("reason", "Constructive contribution."))
        return award, reason

    except Exception as e:
        logger.warning(f"Error evaluating chat message with Groq: {e}")
        return False, str(e)


# --- REWARD EMBED BUILDERS ---

def build_reward_unlocked_embed(user: discord.User) -> Tuple[discord.Embed, ui.View]:
    """
    Builds the celebratory reward embed when a member reaches 5 points,
    prompting them to open a support ticket to claim the Echo Blacklist System for free.
    """
    embed = discord.Embed(
        title="🎉 REWARD UNLOCKED • ECHO BLACKLIST SYSTEM (FREE)!",
        description=(
            f"Incredible work, {user.mention}! 🌟\n\n"
            f"You have accumulated **5 Community Points** through helpful and constructive engagement in **Echo Technologies**!\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎁 **Your Claimable Reward:**\n"
            f"• **Product:** **Echo Blacklist System** (Complete Server-Authoritative Ban System)\n"
            f"• **Value:** `100 Robux` 🪙\n"
            f"• **Cost to You:** **100% FREE!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎫 **How to Claim Your Product:**\n"
            f"1. Navigate to <#1556000081877147771> (`#ticket-center`)\n"
            f"2. Open a **General Support** ticket\n"
            f"3. Tell our staff: *\"I reached 5 Community Points and would like to claim my free Echo Blacklist System!\"*\n\n"
            f"Our team will review your points balance and deliver your product files!"
        ),
        color=0x57F287,
        timestamp=discord.utils.utcnow()
    )
    if hasattr(user, "display_avatar") and user.display_avatar:
        embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text="Echo Technologies Community Rewards • 5 Points Milestone Reached")

    view = ui.View(timeout=None)
    view.add_item(
        ui.Button(
            label="Open Ticket to Claim Free Product",
            url="https://discord.com/channels/1555641543480713226/1556000081877147771",
            emoji="🎫",
            style=discord.ButtonStyle.link
        )
    )
    return embed, view

def build_point_earned_embed(user: discord.User, new_total: int, reason: str) -> discord.Embed:
    """Builds an informative badge notification when +1 point is awarded."""
    embed = discord.Embed(
        title="⭐ Community Point Awarded!",
        description=(
            f"{user.mention} just earned **+1 Community Point** for positive contribution!\n\n"
            f"💡 **AI Note:** *{reason}*\n\n"
            f"📊 **Reward Progress:** {render_progress_bar(new_total, 5)}\n"
            f"*(Reach 5 points to unlock the **Echo Blacklist System** for free!)*"
        ),
        color=0xFEE75C
    )
    embed.set_footer(text=f"Echo Technologies Rewards • Total Points: {new_total}")
    return embed


# ==========================================
# 🛍️ REWARDS SHOP CATALOGUE & REDEMPTION
# ==========================================

REWARD_CATALOGUE = {
    "role_contributor": {
        "name": "🌟 Community Contributor Role",
        "cost": 3,
        "type": "role",
        "role_id": config.CONTRIBUTOR_ROLE_ID,
        "description": "Exclusive contributor badge & role with VIP chat lounge access.",
        "emoji": "🌟"
    },
    "blacklist_system": {
        "name": "🛡️ Echo Blacklist System (100 Robux Value)",
        "cost": 5,
        "type": "product",
        "description": "Complete server-authoritative Roblox ban system (FREE at 5 pts milestone!).",
        "emoji": "🛡️"
    },
    "coupon_discount": {
        "name": "🎟️ 50% Off Any Asset Store Coupon",
        "cost": 8,
        "type": "coupon",
        "description": "Unique single-use 50% off discount coupon code for your next store purchase.",
        "emoji": "🎟️"
    },
    "script_pack": {
        "name": "💻 Premium Luau Script Asset Pack",
        "cost": 10,
        "type": "asset",
        "description": "Custom developer utility pack (nametag system & admin modules).",
        "emoji": "💻"
    },
    "role_elite": {
        "name": "👑 Echo Elite Role & Beta Access",
        "cost": 15,
        "type": "role",
        "role_id": config.ECHO_ELITE_ROLE_ID,
        "description": "Lifetime elite rank + private beta testing channel access.",
        "emoji": "👑"
    }
}

async def redeem_reward(
    user_id: int,
    reward_id: str,
    guild: Optional[discord.Guild] = None,
    member: Optional[discord.Member] = None
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Redeems a reward from the rewards shop.
    Returns: (success: bool, message: str, data_dict: Optional[Dict])
    """
    if reward_id not in REWARD_CATALOGUE:
        return False, "Invalid reward selected.", None

    reward = REWARD_CATALOGUE[reward_id]
    cost = reward["cost"]
    user_data = get_user_points(user_id)
    current_points = user_data["points"]

    if current_points < cost:
        diff = cost - current_points
        return False, f"You need **{cost} Points** to redeem **{reward['name']}**, but you only have **{current_points} Points** (need {diff} more).", None

    # Handle Blacklist System special free milestone claim
    if reward_id == "blacklist_system":
        if user_data.get("has_claimed_reward"):
            return False, "You have already claimed your free Echo Blacklist System! Open a ticket in <#1556000081877147771> if you need your files re-sent.", None

        # Mark claimed
        mark_reward_claimed(user_id, True)

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_redemptions (user_id, reward_id, reward_name, cost, status)
                VALUES (?, ?, ?, ?, 'pending');
            """, (user_id, reward_id, reward["name"], 0))
            cursor.execute("""
                INSERT INTO point_transactions (user_id, amount, source, reason)
                VALUES (?, 0, 'reward_redeem', 'Claimed free Echo Blacklist System (5 pts milestone)');
            """, (user_id,))
            conn.commit()

        msg = (
            f"🎉 **Echo Blacklist System Claim Registered!**\n\n"
            f"Because you reached **5 Community Points**, this product is **100% FREE**!\n\n"
            f"Please open a General Support ticket in <#1556000081877147771> (`#ticket-center`) "
            f"and our staff team will deliver your server-authoritative blacklist system package immediately!"
        )
        return True, msg, {"type": "product"}

    # Handle Role rewards
    elif reward.get("type") == "role":
        role_id = reward.get("role_id")
        if member and role_id:
            role = guild.get_role(role_id) if guild else None
            if role and role in member.roles:
                return False, f"You already have the **{role.name}** role!", None

        # Deduct points
        new_balance = remove_points(
            user_id=user_id,
            amount=cost,
            source="reward_redeem",
            reason=f"Redeemed {reward['name']}"
        )

        role_assigned = False
        if member and role_id:
            role = guild.get_role(role_id) if guild else None
            if role:
                try:
                    await member.add_roles(role, reason=f"Points Shop: Redeemed {reward['name']}")
                    role_assigned = True
                except Exception as e:
                    logger.warning(f"Could not assign role {role_id}: {e}")

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_redemptions (user_id, reward_id, reward_name, cost, status)
                VALUES (?, ?, ?, ?, 'completed');
            """, (user_id, reward_id, reward["name"], cost))
            conn.commit()

        role_str = " Role assigned to you automatically!" if role_assigned else " Please open a ticket to receive your role."
        msg = f"🌟 You have redeemed **{reward['name']}** for `{cost}` Points!{role_str}\nRemaining balance: `{new_balance}` Points."
        return True, msg, {"type": "role", "role_id": role_id}

    # Handle Coupon codes
    elif reward.get("type") == "coupon":
        coupon_code = f"ECHO-50-{secrets.token_hex(3).upper()}"
        new_balance = remove_points(
            user_id=user_id,
            amount=cost,
            source="reward_redeem",
            reason=f"Redeemed 50% Off Coupon ({coupon_code})"
        )

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_redemptions (user_id, reward_id, reward_name, cost, coupon_code, status)
                VALUES (?, ?, ?, ?, ?, 'completed');
            """, (user_id, reward_id, reward["name"], cost, coupon_code))
            conn.commit()

        msg = (
            f"🎟️ You have redeemed **{reward['name']}** for `{cost}` Points!\n\n"
            f"Here is your exclusive single-use coupon code:\n"
            f"**`{coupon_code}`**\n\n"
            f"Present this code when ordering or opening a ticket to claim **50% OFF** any upcoming asset!\n"
            f"Remaining balance: `{new_balance}` Points."
        )
        return True, msg, {"type": "coupon", "coupon_code": coupon_code}

    # Handle Asset Packs
    elif reward.get("type") == "asset":
        new_balance = remove_points(
            user_id=user_id,
            amount=cost,
            source="reward_redeem",
            reason=f"Redeemed {reward['name']}"
        )

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_redemptions (user_id, reward_id, reward_name, cost, status)
                VALUES (?, ?, ?, ?, 'pending');
            """, (user_id, reward_id, reward["name"], cost))
            conn.commit()

        msg = (
            f"💻 You have redeemed **{reward['name']}** for `{cost}` Points!\n\n"
            f"Please open a General Support ticket in <#1556000081877147771> (`#ticket-center`) "
            f"to download your asset file package!\n"
            f"Remaining balance: `{new_balance}` Points."
        )
        return True, msg, {"type": "asset"}

    return False, "Unknown reward type.", None

def get_user_redemptions(user_id: int) -> List[Dict[str, Any]]:
    """Returns all redemption records for a user."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_redemptions WHERE user_id = ? ORDER BY created_at DESC;", (user_id,))
        return [dict(r) for r in cursor.fetchall()]


# ==========================================
# 💸 MEMBER TIPPING SYSTEM
# ==========================================

def tip_points(
    tipper_id: int,
    recipient_id: int,
    amount: int,
    note: str = ""
) -> Tuple[bool, str, int, int, bool]:
    """
    Tips community points from one member to another.
    Returns: (success: bool, error_or_success_msg: str, tipper_new: int, recipient_new: int, recipient_unlocked_reward: bool)
    """
    if tipper_id == recipient_id:
        return False, "You cannot tip points to yourself!", 0, 0, False

    if amount <= 0:
        return False, "Tip amount must be at least 1 point.", 0, 0, False

    now = datetime.now(timezone.utc)
    last_tip = _user_tip_cooldowns.get(tipper_id)
    if last_tip and (now - last_tip).total_seconds() < TIP_COOLDOWN_SECONDS:
        rem = int(TIP_COOLDOWN_SECONDS - (now - last_tip).total_seconds())
        return False, f"Please wait {rem}s before sending another tip.", 0, 0, False

    tipper_data = get_user_points(tipper_id)
    if tipper_data["points"] < amount:
        return False, f"Insufficient points! You have `{tipper_data['points']}` point(s), but tried to tip `{amount}`.", tipper_data["points"], 0, False

    _user_tip_cooldowns[tipper_id] = now

    clean_note = note.strip() or "Helpful community member"

    # Deduct from tipper
    tipper_new = remove_points(
        user_id=tipper_id,
        amount=amount,
        source="tip_sent",
        reason=f"Tipped to <@{recipient_id}>: {clean_note}"
    )

    # Add to recipient
    recipient_new, recipient_unlocked = add_points(
        user_id=recipient_id,
        amount=amount,
        source="tip_received",
        reason=f"Tip from <@{tipper_id}>: {clean_note}"
    )

    return True, f"Successfully tipped {amount} point(s)!", tipper_new, recipient_new, recipient_unlocked

def build_tip_embed(tipper: discord.User, recipient: discord.User, amount: int, note: str, recipient_new_total: int) -> discord.Embed:
    """Builds a celebratory tip announcement embed."""
    embed = discord.Embed(
        title="💸 Community Points Tip Dispatched!",
        description=(
            f"{tipper.mention} just tipped **{amount} Community Point{'s' if amount > 1 else ''}** to {recipient.mention}! 🎁\n\n"
            f"💬 **Note:** *\"{note}\"*\n\n"
            f"📊 **Recipient Progress:** {render_progress_bar(recipient_new_total, 5)}\n"
            f"*(Reach 5 points to unlock the **Echo Blacklist System** for free!)*"
        ),
        color=0x57F287,
        timestamp=discord.utils.utcnow()
    )
    if hasattr(tipper, "display_avatar") and tipper.display_avatar:
        embed.set_thumbnail(url=tipper.display_avatar.url)
    embed.set_footer(text="Echo Technologies Community Tipping System")
    return embed


# ==========================================
# 🛒 REWARDS SHOP UI COMPONENTS
# ==========================================

def build_shop_embed(user: discord.User, points_data: Dict[str, Any]) -> discord.Embed:
    """Builds the interactive Rewards Shop embed."""
    balance = points_data["points"]
    embed = discord.Embed(
        title="🛍️ Echo Technologies • Community Rewards Shop",
        description=(
            f"Earn points by helping fellow developers in chat with scripting, UI, and creative feedback!\n"
            f"Redeem your points below for exclusive roles, product discounts, and free assets.\n\n"
            f"👤 **Customer:** {user.mention}\n"
            f"🪙 **Your Balance:** `{balance} Points`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        ),
        color=0xFEE75C,
        timestamp=discord.utils.utcnow()
    )

    for rid, item in REWARD_CATALOGUE.items():
        status_icon = "🟢" if balance >= item["cost"] else "🔒"
        cost_badge = f"`{item['cost']} Points`"
        if rid == "blacklist_system":
            cost_badge += " *(FREE at 5 pts milestone!)*"
        embed.add_field(
            name=f"{status_icon} {item['name']} — {cost_badge}",
            value=f"> {item['description']}",
            inline=False
        )

    embed.set_footer(text="Select an item below to redeem • Echo Technologies Rewards")
    return embed

class PointsShopSelect(ui.Select):
    def __init__(self, user_points: int):
        options = []
        for rid, item in REWARD_CATALOGUE.items():
            can_afford = user_points >= item["cost"]
            cost_label = f"{item['cost']} Pts"
            desc = f"[{cost_label}] {item['description']}"[:100]
            options.append(
                discord.SelectOption(
                    label=item["name"],
                    value=rid,
                    description=desc,
                    emoji=item.get("emoji", "🎁")
                )
            )
        super().__init__(
            placeholder="🛒 Select a reward to redeem...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="shop_select_dropdown"
        )

    async def callback(self, interaction: discord.Interaction):
        reward_id = self.values[0]
        reward = REWARD_CATALOGUE.get(reward_id)
        if not reward:
            await interaction.response.send_message("❌ Reward not found.", ephemeral=True)
            return

        success, message, data = await redeem_reward(
            user_id=interaction.user.id,
            reward_id=reward_id,
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

class PointsShopView(ui.View):
    def __init__(self, user_points: int):
        super().__init__(timeout=180)
        self.add_item(PointsShopSelect(user_points))
        self.add_item(
            ui.Button(
                label="Open Ticket (#ticket-center)",
                url="https://discord.com/channels/1555641543480713226/1556000081877147771",
                emoji="🎫",
                style=discord.ButtonStyle.link,
                row=1
            )
        )
