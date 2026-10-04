import discord
from discord import ui
import sqlite3
import re
import secrets
import aiohttp
import logging
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timezone, timedelta
import config
from points_system import add_points

logger = logging.getLogger("PartnershipSystem")
DB_PATH = "verifications.db"

PARTNER_CATEGORIES = [
    "Roblox Game Studio",
    "Asset Store & Marketplace",
    "Luau Scripting & Systems",
    "Roblox Clothing & UGC",
    "Gaming & Community Hub",
    "Services & Technology",
    "General Affiliate Partner"
]

# Official Formatted Echo Technologies Partnership Advertisement Copy
ECHO_AD_COPY = """# 🌟 ECHO TECHNOLOGIES • BRAND NEW ROBLOX TECH & SYSTEMS COMMUNITY!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
> **We just officially launched! Be one of our founding members and get free Roblox systems, automated tools, and exclusive launch perks!** 🚀

🎉 **SPECIAL BRAND NEW LAUNCH PERKS:**
• 🎁 **Active Robux & Nitro Competitions:** Win Robux and VIP perks just by joining & inviting friends!
• 📦 **FREE Roblox Blacklist System:** Get our server-authoritative ban system (`.rbxm`) 100% FREE!
• 🛠️ **Staff & Developer Positions OPEN:** We are actively hiring Support Staff, Scripters, UI Designers, and PR Reps!
• 🤖 **24/7 AI Support Assistant:** Groq AI helpdesk built directly into our DMs to solve your coding & verification issues instantly.
• 🪙 **Earn Points Just By Chatting:** Get rewarded with free Roblox scripts, store coupons, and roles just for being active!
• 🤝 **Fast & Easy Partnerships:** Instant ad swaps & cross-promotions for servers of all sizes!

🌐 **BECOME A FOUNDING MEMBER TODAY:**
💬 **Join Discord:** https://discord.gg/8uQxRqbGrH
⚡ **Roblox Group:** https://www.roblox.com/communities/465762008/Echo-Technologies-Roblox#!/about
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""


def init_partnerships_db():
    """Initializes tables for partnerships, applications, giveaways, blacklists, and PR stats."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS partnerships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                invite_url TEXT NOT NULL,
                description TEXT,
                category TEXT DEFAULT 'General Affiliate Partner',
                representative_id INTEGER DEFAULT NULL,
                banner_url TEXT DEFAULT NULL,
                roblox_group_id INTEGER DEFAULT NULL,
                thread_id INTEGER DEFAULT NULL,
                message_id INTEGER DEFAULT NULL,
                added_by INTEGER NOT NULL,
                tier TEXT DEFAULT 'Bronze',
                status TEXT DEFAULT 'active',
                coupon_code TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS partner_applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                server_name TEXT NOT NULL,
                invite_url TEXT NOT NULL,
                roblox_group_url TEXT DEFAULT NULL,
                member_count INTEGER DEFAULT 0,
                description TEXT NOT NULL,
                proof_link TEXT DEFAULT NULL,
                status TEXT DEFAULT 'pending',
                reviewer_id INTEGER DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS partner_giveaways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                partner_id INTEGER NOT NULL,
                prize TEXT NOT NULL,
                winners_count INTEGER DEFAULT 1,
                end_time TIMESTAMP NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                created_by INTEGER NOT NULL,
                ended INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS partner_giveaway_entries (
                giveaway_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (giveaway_id, user_id)
            );
        """)
        # Migrate existing partnerships table columns if missing
        cursor.execute("PRAGMA table_info(partnerships);")
        existing_cols = [row[1] for row in cursor.fetchall()]
        cols_to_add = {
            "roblox_group_id": "INTEGER DEFAULT NULL",
            "tier": "TEXT DEFAULT 'Bronze'",
            "status": "TEXT DEFAULT 'active'",
            "coupon_code": "TEXT DEFAULT NULL"
        }
        for col_name, col_def in cols_to_add.items():
            if col_name not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE partnerships ADD COLUMN {col_name} {col_def};")
                except Exception as e:
                    logger.warning(f"Could not add column {col_name}: {e}")

        conn.commit()

init_partnerships_db()


# --- DATABASE HELPERS ---

def add_partnership_record(
    name: str,
    invite_url: str,
    description: str,
    category: str,
    representative_id: Optional[int],
    banner_url: Optional[str],
    roblox_group_id: Optional[int],
    thread_id: Optional[int],
    message_id: Optional[int],
    added_by: int,
    tier: str = "Bronze",
    coupon_code: Optional[str] = None
) -> int:
    """Inserts a new partnership into the database."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO partnerships (
                name, invite_url, description, category, representative_id,
                banner_url, roblox_group_id, thread_id, message_id, added_by, tier, coupon_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (name, invite_url, description, category, representative_id, banner_url, roblox_group_id, thread_id, message_id, added_by, tier, coupon_code))
        conn.commit()
        return cursor.lastrowid

def get_partnership(partner_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves a single partnership record."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM partnerships WHERE id = ?;", (partner_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_all_partnerships(status: str = "active") -> List[Dict[str, Any]]:
    """Retrieves all partnerships matching a status."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM partnerships WHERE status = ? ORDER BY created_at DESC;", (status,))
        return [dict(r) for r in cursor.fetchall()]

def update_partnership_record(partner_id: int, updates: Dict[str, Any]) -> bool:
    """Updates fields of an existing partnership record."""
    if not updates:
        return False
    keys = list(updates.keys())
    set_clause = ", ".join([f"{k} = ?" for k in keys])
    values = list(updates.values()) + [partner_id]
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE partnerships SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?;", values)
        conn.commit()
        return cursor.rowcount > 0

def delete_partnership_record(partner_id: int) -> bool:
    """Removes a partnership from the database."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM partnerships WHERE id = ?;", (partner_id,))
        conn.commit()
        return cursor.rowcount > 0


# --- REPUTATION SCANNER & BLACKLIST FILTER (#9) ---

SCAM_KEYWORDS = [
    "free robux", "token grabber", "cookie stealer", "nitro gen",
    "generator", "hack tool", "beam account", "pass log"
]

def check_partner_reputation(
    user: discord.User,
    server_name: str,
    invite_url: str,
    description: str
) -> Tuple[bool, str]:
    """
    Scans an applying user and server for scam risk, blacklists, and account maturity.
    Returns: (is_safe: bool, reason_if_flagged: str)
    """
    # 1. Account age check (Minimum 7 days old)
    if hasattr(user, "created_at") and user.created_at:
        age_days = (datetime.now(timezone.utc) - user.created_at).days
        if age_days < 7:
            return False, f"User account is too new (`{age_days}` days old). Minimum 7 days required."

    combined = f"{server_name} {invite_url} {description}".lower()

    # 2. Scam keyword scanner
    for word in SCAM_KEYWORDS:
        if word in combined:
            return False, f"Flagged for security keyword: `{word}`."

    # 3. DB Blacklist check
    code = extract_discord_invite_code(invite_url)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM partner_blacklists;")
        rows = cursor.fetchall()
        for r in rows:
            ttype = r["target_type"]
            val = r["target_val"].lower()
            if ttype == "user_id" and str(user.id) == val:
                return False, f"Representative user ID is blacklisted: {r['reason']}"
            elif ttype == "invite_code" and code and code.lower() == val:
                return False, f"Invite code is blacklisted: {r['reason']}"
            elif ttype == "keyword" and val in combined:
                return False, f"Blacklisted keyword match (`{val}`): {r['reason']}"

    return True, "Safe"


# --- AD PROOF VERIFIER (#2) ---

async def verify_partner_ad_proof(bot, proof_url: str) -> Tuple[bool, str]:
    """
    Verifies if a submitted proof message link contains Echo Technologies' invite code.
    Returns: (verified: bool, details_msg: str)
    """
    if not proof_url or "discord.com/channels/" not in proof_url:
        return False, "Proof must be a valid Discord message link (`https://discord.com/channels/...`)."

    parts = proof_url.strip().split("/")
    if len(parts) < 7:
        return False, "Invalid Discord message link format."

    try:
        guild_id = int(parts[-3])
        channel_id = int(parts[-2])
        message_id = int(parts[-1])
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        if channel:
            msg = await channel.fetch_message(message_id)
            if msg:
                content = (msg.content or "") + " " + " ".join([e.description or "" for e in msg.embeds])
                if "discord.gg" in content.lower() or "echotech" in content.lower() or "8uqxrqbgrh" in content.lower():
                    return True, "✅ Verified: Echo Technologies ad / invite link detected in proof message!"
                return False, "❌ Proof message fetched, but no Echo Technologies invite code was found in it."
    except Exception as e:
        return False, f"⚠️ Could not fetch message from proof link: {e}"

    return False, "Could not verify message proof."


# --- INVITE & ROBLOX METADATA RESOLVER (#7) ---

def extract_discord_invite_code(url: str) -> Optional[str]:
    """Extracts invite code from various Discord invite URL formats."""
    patterns = [
        r"(?:https?://)?(?:www\.)?(?:discord\.gg|discordapp\.com/invite|discord\.com/invite)/([a-zA-Z0-9\-]+)",
        r"^[a-zA-Z0-9\-]{4,16}$"
    ]
    for p in patterns:
        m = re.search(p, url.strip())
        if m:
            return m.group(1) if m.groups() else url.strip()
    return None

def extract_roblox_group_id(url: str) -> Optional[int]:
    """Extracts group ID from a Roblox group URL."""
    if not url:
        return None
    m = re.search(r"roblox\.com/groups/(\d+)", url.strip())
    if m:
        return int(m.group(1))
    if url.strip().isdigit():
        return int(url.strip())
    return None

async def resolve_invite_metadata(bot, invite_url: str, roblox_group_input: Optional[str] = None) -> Dict[str, Any]:
    """
    Attempts to fetch live guild metadata from a Discord invite URL and Roblox group API.
    Returns dictionary with live stats, icons, banners, and group owner.
    """
    meta = {
        "icon_url": None,
        "banner_url": None,
        "member_count": None,
        "presence_count": None,
        "server_description": None,
        "guild_name": None,
        "roblox_group_id": None,
        "roblox_group_name": None,
        "roblox_group_members": None,
        "roblox_group_owner": None,
        "roblox_group_icon": None
    }

    # 1. Try Discord invite
    code = extract_discord_invite_code(invite_url)
    if code:
        try:
            invite: discord.Invite = await bot.fetch_invite(code, with_counts=True)
            if invite.guild:
                meta["guild_name"] = invite.guild.name
                meta["member_count"] = invite.approximate_member_count
                meta["presence_count"] = invite.approximate_presence_count
                meta["server_description"] = invite.guild.description
                if invite.guild.icon:
                    meta["icon_url"] = invite.guild.icon.url
                if invite.guild.banner:
                    meta["banner_url"] = invite.guild.banner.url
                elif invite.guild.splash:
                    meta["banner_url"] = invite.guild.splash.url
        except Exception as e:
            logger.warning(f"Could not fetch Discord invite info for code {code}: {e}")

    # 2. Try Roblox group ID (if passed or in invite_url)
    gid = extract_roblox_group_id(roblox_group_input or invite_url)
    if gid:
        meta["roblox_group_id"] = gid
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://groups.roblox.com/v1/groups/{gid}") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        meta["roblox_group_name"] = data.get("name")
                        meta["roblox_group_members"] = data.get("memberCount")
                        owner = data.get("owner")
                        if owner:
                            meta["roblox_group_owner"] = owner.get("username") or owner.get("displayName")
                # Group emblem
                async with session.get(f"https://thumbnails.roblox.com/v1/groups/icons?groupIds={gid}&size=420x420&format=Png&isCircular=false") as t_resp:
                    if t_resp.status == 200:
                        t_data = await t_resp.json()
                        items = t_data.get("data", [])
                        if items and items[0].get("imageUrl"):
                            meta["roblox_group_icon"] = items[0]["imageUrl"]
        except Exception as e:
            logger.warning(f"Could not fetch Roblox group info for group {gid}: {e}")

    return meta

def calculate_partner_tier(member_count: Optional[int]) -> str:
    """Calculates partnership tier based on member count."""
    if not member_count:
        return "Bronze"
    if member_count >= 5000:
        return "👑 Premier Studio"
    elif member_count >= 1000:
        return "🥇 Gold Partner"
    elif member_count >= 250:
        return "🥈 Silver Partner"
    return "🥉 Bronze Partner"


# --- PRESENTATION BUILDERS ---

class PartnerLinkView(ui.View):
    """Button row providing a direct join link for the affiliate partner."""
    def __init__(self, invite_url: str, partner_name: str):
        super().__init__(timeout=None)
        clean_url = invite_url if invite_url.startswith("http") else f"https://{invite_url}"
        self.add_item(
            ui.Button(
                label=f"Join {partner_name[:30]}",
                url=clean_url,
                emoji="🌐",
                style=discord.ButtonStyle.link
            )
        )

def build_partner_embed(
    name: str,
    invite_url: str,
    description: str,
    category: str,
    meta: Dict[str, Any],
    representative: Optional[discord.Member] = None,
    custom_banner: Optional[str] = None,
    partner_id: Optional[int] = None,
    coupon_code: Optional[str] = None,
    tier: str = "Bronze"
) -> discord.Embed:
    """Builds a comprehensive, detailed partnership showcase embed."""
    embed = discord.Embed(
        title=f"⭐ Official Affiliate Partner • {name}",
        description=(
            f"**Echo Technologies** is thrilled to announce our official partnership with **{name}**!\n\n"
            f"🏆 **Partnership Tier:** `{tier}`\n"
            f"🏷️ **Category:** `{category}`\n"
            f"🔗 **Direct Access:** [Click Here to Join / Visit]({invite_url if invite_url.startswith('http') else 'https://' + invite_url})\n\n"
            f"────────────────────────────────────────\n"
            f"**About {name}:**\n"
            f"> {description}\n"
            f"────────────────────────────────────────"
        ),
        color=0x5865F2,
        timestamp=discord.utils.utcnow()
    )

    # Community & Roblox Group Stats
    stats_parts = []
    if meta.get("member_count"):
        stats_parts.append(f"👥 **Discord Members:** `{meta['member_count']:,}`")
    if meta.get("presence_count"):
        stats_parts.append(f"🟢 **Online:** `{meta['presence_count']:,}`")
    if meta.get("roblox_group_name"):
        stats_parts.append(f"🎮 **Roblox Group:** `{meta['roblox_group_name']}` ({meta.get('roblox_group_members', 0):,} members)")
    if stats_parts:
        embed.add_field(name="📊 Live Community Stats", value="\n".join(stats_parts), inline=False)

    if representative:
        embed.add_field(
            name="👤 Official Ambassador / Representative",
            value=f"{representative.mention} (`{representative.name}`)",
            inline=True
        )

    if coupon_code:
        embed.add_field(
            name="🎟️ Member Perks & Store Discount",
            value=f"Use code **`{coupon_code}`** for **20% OFF** store products!",
            inline=True
        )

    embed.add_field(
        name="🔒 Status",
        value="✅ **Verified Echo Affiliate**",
        inline=True
    )

    # Icons & Banners
    icon_target = meta.get("icon_url") or meta.get("roblox_group_icon")
    if icon_target:
        embed.set_thumbnail(url=icon_target)

    banner_target = custom_banner or meta.get("banner_url")
    if banner_target and banner_target.startswith("http"):
        embed.set_image(url=banner_target)

    footer_text = "Echo Technologies Official Affiliates Network"
    if partner_id:
        footer_text += f" • Partner #{partner_id}"
    embed.set_footer(text=footer_text)

    return embed


# --- POSTING, UPDATING & MANAGEMENT LOGIC ---

async def publish_affiliate_partnership(
    bot,
    guild: discord.Guild,
    name: str,
    invite_url: str,
    description: str,
    category: str = "General Affiliate Partner",
    representative: Optional[discord.Member] = None,
    banner_url: Optional[str] = None,
    roblox_group_url: Optional[str] = None,
    added_by: int = 0
) -> Tuple[bool, str, Optional[int]]:
    """
    Publishes the partnership to config.AFFILIATES_CHANNEL_ID (1556000112692699157).
    Pings @here on post, assigns Representative Role, and awards PR points.
    """
    ch_id = config.AFFILIATES_CHANNEL_ID
    ch = guild.get_channel(ch_id) if guild else None
    if not ch:
        ch = bot.get_channel(ch_id)
    if not ch:
        try:
            ch = await bot.fetch_channel(ch_id)
        except Exception as e:
            return False, f"❌ Could not find affiliates channel `{ch_id}`: {e}", None

    # Resolve live metadata & calculate tier
    meta = await resolve_invite_metadata(bot, invite_url, roblox_group_url)
    tier = calculate_partner_tier(meta.get("member_count"))

    # Generate custom partner coupon code
    clean_short_name = re.sub(r'[^A-Z0-9]', '', name.upper())[:6] or "PARTNER"
    coupon_code = f"PARTNER-{clean_short_name}-20"

    embed = build_partner_embed(
        name=name,
        invite_url=invite_url,
        description=description,
        category=category,
        meta=meta,
        representative=representative,
        custom_banner=banner_url,
        coupon_code=coupon_code,
        tier=tier
    )
    view = PartnerLinkView(invite_url=invite_url, partner_name=name)

    thread_id = None
    message_id = None

    try:
        # 1. Post to Affiliates Channel with @here ping!
        announcement_content = f"@here 🌟 **New Official Affiliate:** Echo Technologies is proud to announce our partnership with **{name}**!"
        
        if isinstance(ch, discord.ForumChannel):
            post = await ch.create_thread(
                name=f"🤝・{name}"[:100],
                content=announcement_content,
                embed=embed,
                view=view
            )
            thread_id = post.thread.id
            message_id = post.message.id
        elif isinstance(ch, discord.TextChannel):
            msg = await ch.send(
                content=announcement_content,
                embed=embed,
                view=view
            )
            message_id = msg.id
        else:
            return False, f"❌ Channel `{ch.name}` is neither a text nor forum channel.", None

        # 2. Save DB Record
        rep_id = representative.id if representative else None
        pid = add_partnership_record(
            name=name,
            invite_url=invite_url,
            description=description,
            category=category,
            representative_id=rep_id,
            banner_url=banner_url or meta.get("banner_url"),
            roblox_group_id=meta.get("roblox_group_id"),
            thread_id=thread_id,
            message_id=message_id,
            added_by=added_by,
            tier=tier,
            coupon_code=coupon_code
        )

        # 3. Assign Partner Representative Role if representative provided
        if representative and guild and config.PARTNER_REP_ROLE_ID:
            role = guild.get_role(config.PARTNER_REP_ROLE_ID)
            if role:
                try:
                    await representative.add_roles(role, reason=f"Official Ambassador for Partner #{pid} ({name})")
                except Exception as e:
                    logger.warning(f"Could not assign Partner Rep role: {e}")

        # 4. Award Community Points (+3 pts) to PR / staff member who brought in partnership
        if added_by:
            add_points(added_by, 3, source="staff_add", reason=f"Published official partnership with {name} (#{pid})")

        return True, f"✅ Successfully published partnership for **{name}** in <#{ch.id}> (Partner `#{pid}`)!", pid

    except Exception as e:
        logger.error(f"Error publishing partnership: {e}")
        return False, f"❌ Failed to publish partnership post: {e}", None


async def update_affiliate_partnership(
    bot,
    guild: discord.Guild,
    partner_id: int,
    name: Optional[str] = None,
    invite_url: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[str] = None,
    representative: Optional[discord.Member] = None,
    roblox_group_url: Optional[str] = None,
    banner_url: Optional[str] = None
) -> Tuple[bool, str]:
    """Updates an existing partnership's database record and live Discord post."""
    partner = get_partnership(partner_id)
    if not partner:
        return False, f"❌ Partnership `#{partner_id}` was not found."

    # Update DB fields
    updates = {}
    if name: updates["name"] = name.strip()
    if invite_url: updates["invite_url"] = invite_url.strip()
    if description: updates["description"] = description.strip()
    if category: updates["category"] = category
    if representative: updates["representative_id"] = representative.id
    if banner_url: updates["banner_url"] = banner_url.strip()
    if roblox_group_url: updates["roblox_group_id"] = extract_roblox_group_id(roblox_group_url)

    if not updates:
        return False, "⚠️ No fields were provided to update."

    update_partnership_record(partner_id, updates)
    updated_partner = get_partnership(partner_id)

    # Re-fetch metadata and update live embed
    meta = await resolve_invite_metadata(bot, updated_partner["invite_url"], roblox_group_url)
    tier = calculate_partner_tier(meta.get("member_count"))

    rep_member = None
    if updated_partner.get("representative_id") and guild:
        rep_member = guild.get_member(updated_partner["representative_id"])

    new_embed = build_partner_embed(
        name=updated_partner["name"],
        invite_url=updated_partner["invite_url"],
        description=updated_partner["description"],
        category=updated_partner["category"],
        meta=meta,
        representative=rep_member,
        custom_banner=updated_partner.get("banner_url"),
        partner_id=partner_id,
        coupon_code=updated_partner.get("coupon_code"),
        tier=tier
    )
    new_view = PartnerLinkView(invite_url=updated_partner["invite_url"], partner_name=updated_partner["name"])

    # Edit thread / message
    thread_id = updated_partner.get("thread_id")
    message_id = updated_partner.get("message_id")

    if thread_id:
        try:
            th = bot.get_channel(thread_id) or await bot.fetch_channel(thread_id)
            if th:
                async for msg in th.history(limit=5):
                    if msg.author.id == bot.user.id:
                        await msg.edit(embed=new_embed, view=new_view)
                        break
        except Exception:
            pass

    if message_id and not thread_id:
        try:
            ch_id = config.AFFILIATES_CHANNEL_ID
            ch = bot.get_channel(ch_id) or await bot.fetch_channel(ch_id)
            if isinstance(ch, discord.TextChannel):
                msg = await ch.fetch_message(message_id)
                if msg:
                    await msg.edit(embed=new_embed, view=new_view)
        except Exception:
            pass

    return True, f"✅ Successfully updated Partnership `#{partner_id}` (**{updated_partner['name']}**)!"


async def remove_affiliate_partnership(bot, partner_id: int) -> Tuple[bool, str]:
    """Deletes the forum thread or message, revokes representative role, and deletes DB record."""
    partner = get_partnership(partner_id)
    if not partner:
        return False, f"❌ Partnership `#{partner_id}` was not found."

    # Try to revoke representative role
    if partner.get("representative_id") and config.PARTNER_REP_ROLE_ID:
        guild = bot.get_primary_guild()
        if guild:
            rep = guild.get_member(partner["representative_id"])
            role = guild.get_role(config.PARTNER_REP_ROLE_ID)
            if rep and role and role in rep.roles:
                try:
                    await rep.remove_roles(role, reason=f"Partnership #{partner_id} removed")
                except Exception:
                    pass

    # Delete Discord thread or message
    thread_id = partner.get("thread_id")
    message_id = partner.get("message_id")

    if thread_id:
        try:
            th = bot.get_channel(thread_id) or await bot.fetch_channel(thread_id)
            if th:
                await th.delete(reason=f"Partnership #{partner_id} removed")
        except Exception:
            pass

    if message_id and not thread_id:
        try:
            ch_id = config.AFFILIATES_CHANNEL_ID
            ch = bot.get_channel(ch_id) or await bot.fetch_channel(ch_id)
            if isinstance(ch, discord.TextChannel):
                msg = await ch.fetch_message(message_id)
                if msg:
                    await msg.delete()
        except Exception:
            pass

    delete_partnership_record(partner_id)
    return True, f"🗑️ Partnership `#{partner_id}` (**{partner['name']}**) removed."


# --- SELF-SERVICE APPLICATION & PORTAL (#6) ---

class PartnerApplicationModal(ui.Modal, title="📝 Partnership Application"):
    server_name = ui.TextInput(label="Server / Studio Name", placeholder="e.g. Korona POS Studio", max_length=60)
    invite_url = ui.TextInput(label="Discord Invite Link", placeholder="https://discord.gg/yourserver", max_length=100)
    roblox_group = ui.TextInput(label="Roblox Group Link / ID (Optional)", placeholder="https://www.roblox.com/groups/12345", required=False, max_length=100)
    description = ui.TextInput(label="Server Description & Ad Copy", style=discord.TextStyle.paragraph, placeholder="Tell us about your studio, community size, and services...", max_length=1000)
    proof_link = ui.TextInput(label="Ad Proof Link (Message Link with our ad)", placeholder="https://discord.com/channels/guild/channel/message", required=False, max_length=200)

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # 1. Reputation & Scam Check
        is_safe, flag_reason = check_partner_reputation(
            user=interaction.user,
            server_name=self.server_name.value,
            invite_url=self.invite_url.value,
            description=self.description.value
        )
        if not is_safe:
            await interaction.followup.send(f"❌ **Application Auto-Declined:** {flag_reason}", ephemeral=True)
            return

        # 2. Proof Link check if provided
        proof_status = "Not Provided"
        if self.proof_link.value:
            verified, proof_msg = await verify_partner_ad_proof(self.bot, self.proof_link.value)
            proof_status = proof_msg

        # 3. Resolve metadata
        meta = await resolve_invite_metadata(self.bot, self.invite_url.value, self.roblox_group.value)

        # 4. Save Application
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO partner_applications (user_id, server_name, invite_url, roblox_group_url, member_count, description, proof_link)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (
                interaction.user.id,
                self.server_name.value.strip(),
                self.invite_url.value.strip(),
                self.roblox_group.value.strip() if self.roblox_group.value else None,
                meta.get("member_count", 0),
                self.description.value.strip(),
                self.proof_link.value.strip() if self.proof_link.value else None
            ))
            conn.commit()
            app_id = cursor.lastrowid

        # 5. Dispatch Review Dossier to #mod-logs
        mod_ch = self.bot.get_channel(config.MOD_LOGS_CHANNEL_ID)
        if mod_ch and isinstance(mod_ch, discord.TextChannel):
            review_embed = discord.Embed(
                title=f"🤝 Partnership Application `#{app_id}` • {self.server_name.value}",
                description=(
                    f"**Applicant:** {interaction.user.mention} (`{interaction.user.name}` • `{interaction.user.id}`)\n"
                    f"**Link:** [Visit Server]({self.invite_url.value})\n"
                    f"**Members:** `{meta.get('member_count', 'Unknown')}` | **Online:** `{meta.get('presence_count', 'Unknown')}`\n"
                    f"**Ad Proof:** {proof_status}\n\n"
                    f"**Description:**\n> {self.description.value}"
                ),
                color=0x5865F2,
                timestamp=discord.utils.utcnow()
            )
            if meta.get("icon_url"):
                review_embed.set_thumbnail(url=meta["icon_url"])

            review_view = PartnerReviewControlView(app_id, self.bot)
            await mod_ch.send(embed=review_embed, view=review_view)

        await interaction.followup.send(
            f"✅ **Application Submitted!** Application `#{app_id}` for **{self.server_name.value}** is under review by our PR team.",
            ephemeral=True
        )


class PartnerReviewControlView(ui.View):
    """Staff review buttons for partnership applications."""
    def __init__(self, app_id: int, bot):
        super().__init__(timeout=None)
        self.app_id = app_id
        self.bot = bot

    @ui.button(label="Approve Partnership", style=discord.ButtonStyle.success, emoji="✅", custom_id="part_app_acc")
    async def approve(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)

        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM partner_applications WHERE id = ?;", (self.app_id,))
            app = cursor.fetchone()

        if not app or app["status"] != "pending":
            await interaction.followup.send("❌ Application already processed.", ephemeral=True)
            return

        applicant = self.bot.get_user(app["user_id"]) or await self.bot.fetch_user(app["user_id"])
        rep_member = interaction.guild.get_member(app["user_id"]) if applicant and interaction.guild else None

        # Publish partnership
        success, msg, pid = await publish_affiliate_partnership(
            bot=self.bot,
            guild=interaction.guild,
            name=app["server_name"],
            invite_url=app["invite_url"],
            description=app["description"],
            category="General Affiliate Partner",
            representative=rep_member,
            roblox_group_url=app["roblox_group_url"],
            added_by=interaction.user.id
        )

        if success:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE partner_applications SET status = 'approved', reviewer_id = ? WHERE id = ?;", (interaction.user.id, self.app_id))
                conn.commit()

            # Disable buttons
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)

            await interaction.followup.send(f"🎉 Approved Application #{self.app_id}! Published as Partner #{pid}.", ephemeral=False)

            if applicant:
                try:
                    dm = await applicant.create_dm()
                    await dm.send(f"🎉 **Partnership Approved!** Your server **{app['server_name']}** has been published in <#{config.AFFILIATES_CHANNEL_ID}>!")
                except Exception:
                    pass
        else:
            await interaction.followup.send(f"⚠️ {msg}", ephemeral=True)

    @ui.button(label="Deny Partnership", style=discord.ButtonStyle.danger, emoji="❌", custom_id="part_app_den")
    async def deny(self, interaction: discord.Interaction, button: ui.Button):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE partner_applications SET status = 'denied', reviewer_id = ? WHERE id = ?;", (interaction.user.id, self.app_id))
            conn.commit()

        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_message(f"❌ Application #{self.app_id} marked Denied by {interaction.user.mention}.", ephemeral=False)


class PartnerPortalView(ui.View):
    """Persistent partner portal view in #partner-portal."""
    def __init__(self, bot=None):
        super().__init__(timeout=None)
        self.bot = bot

    @ui.button(label="Apply for Partnership", style=discord.ButtonStyle.primary, emoji="📝", custom_id="part_portal_apply")
    async def apply_btn(self, interaction: discord.Interaction, button: ui.Button):
        modal = PartnerApplicationModal(bot=interaction.client)
        await interaction.response.send_modal(modal)

    @ui.button(label="Copy Echo Ad Copy", style=discord.ButtonStyle.secondary, emoji="📋", custom_id="part_portal_ad")
    async def ad_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(
            content=f"📋 **Echo Technologies Official Partnership Ad Copy:**\n\n```markdown\n{ECHO_AD_COPY}\n```",
            ephemeral=True
        )

    @ui.button(label="Check Affiliates Directory", style=discord.ButtonStyle.success, emoji="🔍", custom_id="part_portal_dir")
    async def dir_btn(self, interaction: discord.Interaction, button: ui.Button):
        partners = get_all_partnerships()
        embed = discord.Embed(
            title="🤝 Echo Technologies • Affiliates Directory",
            description=f"We currently have **{len(partners)} active affiliate partners**! Run `/partner directory` to browse categories.",
            color=0x5865F2
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# --- INTERACTIVE PUBLIC DIRECTORY (#10) ---

class PartnerDirectorySelect(ui.Select):
    def __init__(self, partners: List[Dict[str, Any]]):
        options = [discord.SelectOption(label="All Categories", value="ALL", emoji="🌐")]
        categories = sorted(list(set(p.get("category", "General Affiliate Partner") for p in partners)))
        for cat in categories:
            options.append(discord.SelectOption(label=cat[:100], value=cat[:100], emoji="📁"))
        super().__init__(placeholder="📂 Filter partners by category...", min_values=1, max_values=1, options=options)
        self.partners = partners

    async def callback(self, interaction: discord.Interaction):
        cat = self.values[0]
        filtered = [p for p in self.partners if p.get("category") == cat] if cat != "ALL" else self.partners

        embed = discord.Embed(
            title=f"🌐 Echo Affiliates • {cat}",
            description=f"Showing **{len(filtered)}** partners matching `{cat}`:\n",
            color=0x5865F2,
            timestamp=discord.utils.utcnow()
        )

        for p in filtered[:10]:
            rep_str = f" • Rep: <@{p['representative_id']}>" if p.get("representative_id") else ""
            embed.add_field(
                name=f"#{p['id']} • {p['name']} (`{p.get('tier', 'Bronze')}`)",
                value=f"> {p.get('description', '')[:120]}\n🔗 [Join Server]({p['invite_url']}){rep_str}",
                inline=False
            )

        embed.set_footer(text=f"Total: {len(self.partners)} partners • Use /partner directory to refresh")
        await interaction.response.edit_message(embed=embed)


class PartnerDirectoryView(ui.View):
    def __init__(self, partners: List[Dict[str, Any]]):
        super().__init__(timeout=180)
        self.add_item(PartnerDirectorySelect(partners))


# --- HEALTH MONITOR (#11) ---

async def check_partner_health(bot) -> List[Dict[str, Any]]:
    """
    Periodic health check verifying active partnership invite links.
    Returns list of broken/flagged partnerships.
    """
    partners = get_all_partnerships()
    flagged = []
    for p in partners:
        code = extract_discord_invite_code(p["invite_url"])
        if code:
            try:
                await bot.fetch_invite(code)
            except Exception:
                flagged.append(p)

    if flagged:
        mod_ch = bot.get_channel(config.MOD_LOGS_CHANNEL_ID)
        if mod_ch and isinstance(mod_ch, discord.TextChannel):
            embed = discord.Embed(
                title="🩺 Partnership Health Audit • Broken Links Detected",
                description=f"The health monitor found **{len(flagged)} partnership(s)** with expired or invalid invite links:\n",
                color=0xED4245,
                timestamp=discord.utils.utcnow()
            )
            for f in flagged:
                embed.add_field(
                    name=f"#{f['id']} • {f['name']}",
                    value=f"**Invite:** `{f['invite_url']}`\nRun `/partner remove partner_id:{f['id']}` to remove.",
                    inline=False
                )
            embed.set_footer(text="Echo Technologies Partnership Health Monitor")
            try:
                await mod_ch.send(embed=embed)
            except Exception:
                pass

    return flagged
