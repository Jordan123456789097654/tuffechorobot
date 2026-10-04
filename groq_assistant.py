import logging
import asyncio
import re
from typing import List, Dict, Tuple, Optional
from groq import AsyncGroq
import config

logger = logging.getLogger("GroqAssistant")

class GroqAssistant:
    """Manages AI conversation, ticket resolution attempts, and escalation detection via Groq."""

    def __init__(self, ai_trainer):
        self.ai_trainer = ai_trainer
        self.client: Optional[AsyncGroq] = None
        if config.GROQ_API_KEY:
            self.client = AsyncGroq(api_key=config.GROQ_API_KEY)

    def _ensure_client(self):
        if not self.client and config.GROQ_API_KEY:
            self.client = AsyncGroq(api_key=config.GROQ_API_KEY)
        return self.client

    async def _call_groq_with_fallback(self, client, messages, temperature=0.3, max_tokens=800):
        models = [config.GROQ_MODEL, "llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama3-70b-8192"]
        unique_models = []
        for m in models:
            if m and m not in unique_models:
                unique_models.append(m)

        last_err = None
        for m_name in unique_models:
            try:
                return await client.chat.completions.create(
                    messages=messages,
                    model=m_name,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            except Exception as e:
                err_str = str(e).lower()
                if any(k in err_str for k in ["404", "does not exist", "model_not_found", "413", "rate_limit", "tokens per minute", "payload too large"]):
                    logger.warning(f"Groq model '{m_name}' unavailable or rate-limited ({e}). Retrying with next model...")
                    last_err = e
                    continue
                raise e
        if last_err:
            raise last_err


    def _build_system_prompt(
        self,
        user_info: Optional[Dict] = None,
        section: str = "General Support",
        points_info: Optional[Dict] = None
    ) -> str:
        knowledge = self.ai_trainer.get_knowledge_prompt()

        user_context_str = "Discord Member"
        if user_info:
            user_context_str = (
                f"Discord Member linked to Roblox account: "
                f"Username: {user_info.get('roblox_username')} "
                f"(Display: {user_info.get('roblox_display_name')}, ID: {user_info.get('roblox_id')})"
            )

        points_context = ""
        if points_info:
            pts_balance = points_info.get("points", 0)
            pts_total = points_info.get("total_earned", 0)
            has_claimed = bool(points_info.get("has_claimed_reward", 0))

            points_context = f"""=== USER COMMUNITY POINTS & ECHO BLACKLIST SYSTEM REWARDS ===
• Current Points Balance: {pts_balance} Points
• Total Points Earned: {pts_total} Points
• Has Claimed Free Echo Blacklist System: {"YES (Already claimed)" if has_claimed else "NO (Eligible to claim if balance >= 5)"}

=== CRITICAL REWARD FULFILLMENT RULES (NO STAFF NEEDED) ===
The official file download link is: https://drive.google.com/file/d/1VZtIk0rc46BtzXZfpeApSqQPO5f34eOY/view?usp=sharing
Product: Echo Blacklist System (100 Robux Value) — Unlocked 100% FREE upon reaching 5 Community Points.

DIRECTIVE 1 — CLAIMING REWARD (BALANCE >= 5):
If the user mentions wanting to claim, download, or receive their free Echo Blacklist System (or mentions their 5 points reward), and their balance is {pts_balance} (>= 5):
1. You MUST provide them the direct Google Drive link: https://drive.google.com/file/d/1VZtIk0rc46BtzXZfpeApSqQPO5f34eOY/view?usp=sharing
2. You MUST include this exact tag in your response: `[CLAIM_BLACKLIST_SYSTEM]`
3. Congratulate them on reaching the 5-point milestone!
4. Highlight key features: Server-authoritative ban system, DataStore persistence (permanent & temporary bans), group-rank or UserId permissions, join enforcement, audit logging, and Discord webhook integration.
5. Provide installation guidance: Open Roblox Studio, right-click `ServerScriptService` in the Explorer, select `Insert from File...`, and select the downloaded `.rbxm` file.
6. DO NOT escalate to human staff for this! You can fulfill this completely on your own.

DIRECTIVE 2 — ALREADY CLAIMED:
If the user has already claimed the system (Has Claimed: YES) and asks for the link again because they lost or misplaced it:
- Provide the link again: https://drive.google.com/file/d/1VZtIk0rc46BtzXZfpeApSqQPO5f34eOY/view?usp=sharing
- Remind them they already claimed their official copy.

DIRECTIVE 3 — INSUFFICIENT POINTS (BALANCE < 5):
If the user asks to claim the Echo Blacklist System for free but has fewer than 5 points (Current: {pts_balance}/5):
- Politely inform them they have {pts_balance}/5 Community Points and need {5 - pts_balance} more point(s) to unlock it for 100% free!
- Explain how to earn points: provide helpful, high-quality answers to other developers in chat, give scripting advice, or offer constructive feedback.
- DO NOT provide the download link if they have under 5 points.

DIRECTIVE 4 — CLAIMING 50% DISCOUNT COUPON (COST: 8 POINTS):
If the user asks to claim, redeem, or use their Community Points for the "50% off discount", "discount coupon", or "50% off any asset", and their balance is {pts_balance}:
- If {pts_balance} >= 8:
  * Acknowledge that they are eligible and have sufficient points ({pts_balance} points).
  * State that you are verifying their account, deducting the 8 Community Points, and generating their unique single-use 50% discount voucher.
  * You MUST include this exact tag in your response: `[CLAIM_DISCOUNT_COUPON]`
  * DO NOT escalate to human staff! The automated voucher engine will process and issue their code directly.
- If {pts_balance} < 8:
  * Politely inform them that the 50% discount coupon requires 8 Community Points.
  * Tell them their current balance is {pts_balance}/8 points (they need {8 - pts_balance} more points).
  * Explain that points can be earned by helping fellow developers with scripting, UI, and feedback in chat.
  * DO NOT include the tag and DO NOT issue a coupon code.
"""

        section_name = section or "General Support"
        sec_lower = section_name.lower()
        if "high" in sec_lower or "rank" in sec_lower:
            section_directives = """=== DEPARTMENT DIRECTIVE: HIGH-RANKING SUPPORT ===
- Persona: Highly formal, discreet, confidential, and administrative.
- Scope: Inquiries intended for server leadership, staff conduct reports, appeals, and sensitive issues.
- Handling Rules:
  * Acknowledge the importance of their inquiry with respect, professionalism, and seriousness.
  * Calmly gather essential context: user IDs of parties involved, timestamps, screenshots/proof, and explanation.
  * Inform them that High-Ranking Administration reviews these cases with utmost priority.
  * If the user provides report/appeal details, reassure them and escalate to Senior Staff: `[ESCALATE: High-Ranking matter submitted for administrative review]`."""
        elif "dev" in sec_lower or "bug" in sec_lower or "tech" in sec_lower:
            section_directives = """=== DEPARTMENT DIRECTIVE: DEVELOPMENT TICKET ===
- Persona: Analytical, technical, diagnostic, and precise.
- Scope: In-game Roblox glitches, bugs, script errors, asset loading issues, exploits, or developer inquiries.
- Handling Rules:
  * Prompt the user for reproduction steps ("What were you doing when it occurred?").
  * Request their platform/device (PC, Mac, Mobile, Tablet, Console) and Roblox client version if known.
  * Ask for screenshots, video clips, or DevConsole (F9) error messages if available.
  * If it's a known gameplay mechanic or basic question in the knowledge base, provide the answer.
  * If it's an unresolved bug or code glitch, collect details and escalate to the engineering team: `[ESCALATE: Bug diagnostic ready for developer backlog]`."""
        elif "boost" in sec_lower or "perk" in sec_lower:
            section_directives = """=== DEPARTMENT DIRECTIVE: BOOSTER PERKS ===
- Persona: Enthusiastic, warm, appreciative VIP concierge.
- Scope: Server booster rewards, exclusive role colors/names, VIP channel access, and in-game booster bonuses.
- Handling Rules:
  * Express sincere gratitude to the member for boosting Echo Technologies!
  * Check the knowledge base for current booster perks (e.g., custom colored role, exclusive badges, VIP perks).
  * Guide them through claiming their perks: ask for their preferred custom role name and hex color (e.g. #FF007F).
  * When custom role details are given or if they need staff assignment, escalate for booster setup: `[ESCALATE: Booster custom role setup request]`."""
        else:
            section_directives = """=== DEPARTMENT DIRECTIVE: GENERAL SUPPORT ===
- Persona: Friendly, welcoming, patient, and resourceful community assistant.
- Scope: Roblox account verification, server navigation, community rules, roles, community point rewards, and general inquiries.
- Handling Rules:
  * Guide members through Roblox verification step-by-step using /verify or the verification channel.
  * Answer questions about Community Points, the Rewards Shop, and fulfill Echo Blacklist System claims according to the reward directives above.
  * Escalate only if the issue cannot be resolved or if the user explicitly asks for human staff."""

        system_prompt = f"""You are the official AI Support Assistant for Echo Technologies Discord server.
Your job is to assist members with support tickets and Modmail inquiries in a professional tone matching your department.

=== TICKET DEPARTMENT ===
Selected Department: {section_name}

{section_directives}

=== TICKET USER CONTEXT ===
{user_context_str}

{points_context}

=== SERVER KNOWLEDGE BASE (TRAINED FROM #AI-TRAINER & SERVER EMBEDS) ===
{knowledge}

=== BETA NOTICE & SYSTEM MATURITY ===
This ticket system is currently in BETA. You may not know everything yet because your knowledge is continuously being learned from the server's #ai-trainer channel and embeds.
- If a user asks something not covered in your knowledge base or if you are not 100% sure, DO NOT guess or invent information.
- Politely let the user know that this system is in Beta and you do not have all the details on that yet, and escalate the ticket using `[ESCALATE: Question outside beta knowledge base]`.

=== YOUR OPERATIONAL GUIDELINES ===
1. PRIMARY GOAL: Try to handle and resolve the ticket yourself whenever possible using the server knowledge base above and your department guidelines.
2. ACCURACY: Base your answers strictly on the server rules, #ai-trainer instructions, and Roblox verification procedures. Do not invent server rules or policies that are not in the knowledge base.
3. FORMATTING: Use clean Discord markdown (bullet points, bold text, codeblocks where appropriate). Keep responses concise and easy to read.

=== WHEN USER WANTS TO CLOSE TICKET ===
If the user indicates that their issue is resolved, thanks you and says you can close the ticket, or asks to close the ticket (e.g. "you can close this", "close ticket", "everything is working now", "issue resolved"):
- You MUST include this exact tag in your response: `[CLOSE_TICKET]`
- Politely thank them for contacting Echo Technologies support and confirm that the ticket is being closed.

=== WHEN TO ESCALATE TO HUMAN STAFF ===
You must ESCALATE the ticket to staff if:
- The user explicitly asks for human staff, moderator, admin, or support team (e.g. "I want a human", "talk to staff", "escalate this", "real person").
- The inquiry requires human authority (e.g., appealing bans/mutes, reporting server members with evidence, sensitive account issues, payment/robux disputes, custom role requests).
- The user's question cannot be answered using your knowledge base after trying to clarify.
- The user states that your solution didn't work and they are stuck.
- NOTE: Claiming the Echo Blacklist System with 5 Community Points does NOT require escalation! You can fulfill it directly using the file link.

=== HOW TO SIGNAL ACTIONS ===
- To escalate: Include `[ESCALATE: <brief reason>]`
- To close: Include `[CLOSE_TICKET]`
- To claim rewards: Include `[CLAIM_BLACKLIST_SYSTEM]` or `[CLAIM_DISCOUNT_COUPON]`
"""
        return system_prompt

    async def generate_response(
        self,
        messages_history: List[Dict[str, str]],
        user_info: Optional[Dict] = None,
        section: str = "General Support",
        points_info: Optional[Dict] = None
    ) -> Tuple[str, bool, str, bool, bool, bool]:
        """
        Sends conversation to Groq and returns:
        (reply_text, should_escalate, escalation_reason, claimed_blacklist, claimed_discount, should_close)
        """
        client = self._ensure_client()
        if not client:
            return (
                "⚠️ AI support is currently offline (GROQ_API_KEY missing). A staff member will assist you shortly.",
                True,
                "Groq API key not configured",
                False,
                False,
                False
            )

        # Check explicit user keyword triggers for instant escalation
        latest_user_text = messages_history[-1]["content"].lower() if messages_history else ""
        explicit_escalate_phrases = [
            "talk to human", "speak to human", "real person", "talk to staff",
            "speak to staff", "call staff", "escalate", "i want a human", "need admin",
            "need mod", "moderator please", "contact staff"
        ]
        if any(phrase in latest_user_text for phrase in explicit_escalate_phrases):
            return (
                "Understood! I am escalating your ticket to our staff team right away. A staff member will be with you shortly.",
                True,
                f"User requested human staff: \"{messages_history[-1]['content'][:80]}\"",
                False,
                False,
                False
            )

        # Check explicit user keyword triggers for instant ticket closing
        close_phrases = [
            "close this ticket", "close ticket", "you can close this", "close this inquiry",
            "close inquiry", "close the ticket", "close this ticket please", "please close this",
            "everything is working now, you can close", "issue is resolved, you can close"
        ]
        negated_close = bool(re.search(r"\b(don'?t|do not|dont|never|not|no need to|without)\b[^.!?]{0,20}\bclose\b", latest_user_text))
        wants_close = (
            any(phrase in latest_user_text for phrase in close_phrases)
            or bool(re.search(r"\bclose\b", latest_user_text) and re.search(r"\b(ticket|inquiry)\b", latest_user_text))
        )
        if wants_close and not negated_close:
            return (
                "Glad everything is resolved! I am closing this ticket channel now. Have a great day! 🎉",
                False,
                "",
                False,
                False,
                True
            )

        system_prompt = self._build_system_prompt(user_info, section=section, points_info=points_info)

        payload_messages = [{"role": "system", "content": system_prompt}]
        for m in messages_history:
            payload_messages.append({"role": m["role"], "content": m["content"]})

        try:
            chat_completion = await asyncio.wait_for(
                self._call_groq_with_fallback(
                    client=client,
                    messages=payload_messages,
                    temperature=0.3,
                    max_tokens=800
                ),
                timeout=12.0
            )


            raw_reply = chat_completion.choices[0].message.content or ""

            # Detect blacklist reward claim tag
            claimed_blacklist = False
            if "[CLAIM_BLACKLIST_SYSTEM]" in raw_reply:
                claimed_blacklist = True
                raw_reply = raw_reply.replace("[CLAIM_BLACKLIST_SYSTEM]", "").strip()

            # Detect discount coupon claim tag
            claimed_discount = False
            if "[CLAIM_DISCOUNT_COUPON]" in raw_reply:
                claimed_discount = True
                raw_reply = raw_reply.replace("[CLAIM_DISCOUNT_COUPON]", "").strip()

            # Detect close ticket tag
            should_close = False
            if "[CLOSE_TICKET]" in raw_reply:
                should_close = True
                raw_reply = raw_reply.replace("[CLOSE_TICKET]", "").strip()

            # Detect escalation tag
            should_escalate = False
            escalate_reason = ""

            if "[ESCALATE:" in raw_reply:
                should_escalate = True
                start_idx = raw_reply.find("[ESCALATE:")
                end_idx = raw_reply.find("]", start_idx)
                if end_idx != -1:
                    escalate_reason = raw_reply[start_idx + 10:end_idx].strip()
                    clean_reply = (raw_reply[:start_idx] + raw_reply[end_idx + 1:]).strip()
                else:
                    escalate_reason = "AI determined staff intervention is needed"
                    clean_reply = raw_reply.replace("[ESCALATE:", "").strip()
            else:
                clean_reply = raw_reply.strip()

            if not clean_reply and should_escalate:
                clean_reply = "I am escalating your ticket to our staff team. A representative will be with you shortly."

            return clean_reply, should_escalate, escalate_reason, claimed_blacklist, claimed_discount, should_close

        except asyncio.TimeoutError:
            logger.warning("Groq API timed out after 12s. Automatically escalating ticket to staff.")
            return (
                "⚠️ **AI Assistant Response Timeout:** The AI system is currently experiencing high load or delay. I have automatically escalated your ticket to our human staff team so you get immediate assistance!",
                True,
                "AI API timed out (12s threshold exceeded)",
                False,
                False,
                False
            )
        except Exception as e:
            err_str = str(e).lower()
            if "rate_limit" in err_str or "429" in err_str:
                logger.warning(f"Groq API Rate Limited (429): {e}. Automatically escalating to staff.")
                reason = "AI Service Rate Limited (HTTP 429)"
                msg = "⚠️ **AI Assistant Capacity Limit Reached:** The AI support engine is currently rate-limited. I have automatically escalated your ticket to our human staff team so you receive direct help right away!"
            else:
                logger.error(f"Error calling Groq API: {e}")
                reason = f"Groq API error: {e}"
                msg = "⚠️ **AI Service Interruption:** I encountered an error processing your inquiry. I am automatically escalating this ticket to our staff team for immediate assistance."

            return (
                msg,
                True,
                reason,
                False,
                False,
                False
            )

    async def generate_ticket_summary(self, messages_history: List[Dict[str, str]], reason: str = "") -> str:
        """Generates a concise 2-3 bullet summary of the ticket for staff escalation alert."""
        client = self._ensure_client()
        if not client or not messages_history:
            return f"• User requested assistance\n• Reason: {reason or 'Staff attention required'}"

        convo_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in messages_history[-8:]])
        prompt = [
            {
                "role": "system",
                "content": (
                    "You are a ticket summarizer for Discord moderators. "
                    "Provide a clean, bulleted summary (maximum 3 bullet points) describing: "
                    "1) What the user needs, 2) What the AI attempted, 3) Why it needs staff attention. "
                    "Keep it concise and factual."
                )
            },
            {
                "role": "user",
                "content": f"Ticket Conversation:\n{convo_text}\n\nEscalation Reason: {reason}\n\nPlease summarize:"
            }
        ]

        try:
            res = await self._call_groq_with_fallback(
                client=client,
                messages=prompt,
                temperature=0.2,
                max_tokens=250
            )

            return (res.choices[0].message.content or "").strip()
        except Exception as e:
            logger.error(f"Error generating ticket summary: {e}")
            return f"• Issue: {messages_history[0]['content'][:100]}\n• Escalated: {reason or 'Staff assistance requested'}"

    async def generate_suggested_reply(self, messages_history: List[Dict[str, str]], roblox_info: Optional[Dict] = None) -> str:
        """Drafts a recommended staff reply that human staff can inspect, edit, or dispatch in one click."""
        client = self._ensure_client()
        if not client or not messages_history:
            return "Hello, thank you for reaching out to our support team! How can we assist you today?"

        convo_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in messages_history[-10:]])
        user_rbx = f"@{roblox_info.get('roblox_username')}" if roblox_info else "the user"
        prompt = [
            {
                "role": "system",
                "content": (
                    f"You are drafting a response on behalf of a human support staff member for {user_rbx}. "
                    "Write a professional, warm, and helpful reply addressing the user's issue directly. "
                    "Do NOT include prefixes like 'Staff:' or quotes. Just output the ready-to-send text."
                )
            },
            {
                "role": "user",
                "content": f"Ticket History:\n{convo_text}\n\nDraft a staff reply to help this user:"
            }
        ]

        try:
            res = await self._call_groq_with_fallback(
                client=client,
                messages=prompt,
                temperature=0.3,
                max_tokens=300
            )

            return (res.choices[0].message.content or "").strip()
        except Exception as e:
            logger.error(f"Error drafting suggested reply: {e}")
            return "Hello! I am reviewing your ticket now. Could you please provide a few more details so I can help you resolve this?"

    def detect_urgency(self, content: str) -> Tuple[bool, str]:
        """Detects critical security/payment/urgent keywords to automatically flag urgent tickets."""
        lower = content.lower()
        urgent_keywords = {
            "hacked": "Account compromised/hacked",
            "stolen": "Stolen account or assets",
            "compromised": "Security breach",
            "chargeback": "Billing/Payment dispute",
            "scammed": "User reported a scam",
            "exploit": "Severe game exploit report",
            "doxx": "Harassment or safety concern"
        }
        for kw, reason in urgent_keywords.items():
            if kw in lower:
                return True, reason
        return False, ""

    async def generate_test_opening_prompt(self, scenario_title: str, scenario_details: str = "") -> str:
        """Generates the initial opening roleplay message from the fake member for a test ticket."""
        client = self._ensure_client()
        if not client:
            return f"WHY WAS MY ACCOUNT BANNED/DEMOTED??? Fix this right now or I am reporting your group!"

        prompt = [
            {
                "role": "system",
                "content": (
                    f"You are an AI Support Staff Examiner acting out a realistic, high-stress, demanding Roblox user in a Discord support ticket.\n"
                    f"SCENARIO TITLE: '{scenario_title}'\n"
                    f"SCENARIO DETAILS: '{scenario_details}'\n\n"
                    f"DIRECTIVE: Write an EXTREMELY realistic, angry, demanding, or panicked OPENING message for this scenario.\n"
                    f"Do NOT break character. Output ONLY the message as the user."
                )
            },
            {
                "role": "user",
                "content": f"Generate the initial opening message for scenario: {scenario_title}"
            }
        ]

        try:
            res = await self._call_groq_with_fallback(
                client=client,
                messages=prompt,
                temperature=0.7,
                max_tokens=300
            )
            return (res.choices[0].message.content or "").strip()
        except Exception as e:
            logger.error(f"Error generating test opening prompt: {e}")
            return f"WHY WAS MY ACCOUNT BANNED/DEMOTED??? Fix this right now or I am reporting your group games!"

    async def generate_test_roleplay_response(
        self,
        messages_history: List[Dict[str, str]],
        scenario_title: str,
        scenario_details: str = ""
    ) -> str:
        """Acts out the role of the challenging user during a /test-ticket simulation."""
        client = self._ensure_client()
        if not client or not messages_history:
            return "I don't care about your rules! Answer my question right now or I'm reporting your group!"

        convo_text = "\n".join([f"{m.get('sender_name', m['role']).upper()}: {m['content']}" for m in messages_history[-10:]])

        prompt = [
            {
                "role": "system",
                "content": (
                    f"You are an AI Support Staff Examiner acting as a realistic, challenging, demanding Roblox user in a Discord support ticket simulation.\n"
                    f"SCENARIO: '{scenario_title}' ({scenario_details})\n\n"
                    f"ROLEPLAY DIRECTIVES:\n"
                    f"1. Stay 100% in character as the demanding Roblox player.\n"
                    f"2. Respond dynamically to what the staff member says. Take 4 to 5 turns to test them thoroughly.\n"
                    f"3. Test if the staff member:\n"
                    f"   - Used the mandatory greeting ('Hello! My name is [Name] from Echo Technologies Support...').\n"
                    f"   - Refused unauthorized Robux/rank payouts.\n"
                    f"   - Cited the Evidence Privacy SOP if video/detection logs were mentioned.\n"
                    f"   - Cited the Permanent Global Blacklist penalty if alt evasion/raids were mentioned.\n"
                    f"   - Guided you to official appeal forms or /ticket-request-close.\n"
                    f"4. Keep responses realistic (2-5 sentences), emotional, and challenging.\n"
                    f"5. Output ONLY your message in character as the member."
                )
            },
            {
                "role": "user",
                "content": f"Ticket Transcript so far:\n{convo_text}\n\nRespond as the Roblox user in character:"
            }
        ]

        try:
            res = await self._call_groq_with_fallback(
                client=client,
                messages=prompt,
                temperature=0.6,
                max_tokens=400
            )
            return (res.choices[0].message.content or "").strip()
        except Exception as e:
            logger.error(f"Error generating test roleplay response: {e}")
            return "I don't care about your SOP procedure! Answer my question right now!"

    async def generate_curveball_prompt(
        self,
        messages_history: List[Dict[str, str]],
        scenario_title: str
    ) -> str:
        """Generates a surprise policy trick question or escalation curveball from the simulated member."""
        client = self._ensure_client()
        if not client or not messages_history:
            return "Wait, if you can't pay me Robux, can you at least rank me to Senior Developer right now? Or send me the private video proof of why I was banned?!"

        convo_text = "\n".join([f"{m.get('sender_name', m['role']).upper()}: {m['content']}" for m in messages_history[-6:]])

        prompt = [
            {
                "role": "system",
                "content": (
                    "You are a Support Trainer triggering a surprise policy curveball in a live staff simulation exam.\n"
                    f"SCENARIO: '{scenario_title}'\n\n"
                    "INSTRUCTIONS:\n"
                    "Generate a realistic, high-pressure CURVEBALL message from the Roblox user designed to test a specific SOP:\n"
                    "- Either demand unearned rank restoration / group funds payout\n"
                    "- Or demand to see confidential internal staff video clips / audit logs\n"
                    "- Or threat of an alt-account raid / mass-reporting the Discord server\n"
                    "Do NOT break character. Output ONLY the member's message."
                )
            },
            {
                "role": "user",
                "content": f"Ticket transcript so far:\n{convo_text}\n\nGenerate the surprise curveball:"
            }
        ]

        try:
            res = await self._call_groq_with_fallback(
                client=client,
                messages=prompt,
                temperature=0.7,
                max_tokens=300
            )
            return (res.choices[0].message.content or "").strip()
        except Exception as e:
            logger.error(f"Error generating curveball prompt: {e}")
            return "Fine! If you won't refund my Robux, give me Senior Developer rank right now and show me the staff audit logs, or I'm bringing 20 people to mass-report your server!"

    async def evaluate_staff_test_performance(
        self,
        messages_history: List[Dict[str, str]],
        scenario_title: str
    ) -> Dict[str, any]:
        """
        Uses Groq AI to evaluate staff performance against 6 core SOP criteria:
        1. Mandatory Greeting Delivered (+20 Pts)
        2. Security & Phishing SOP Cited (+20 Pts)
        3. Unauthorized Compensation Refused (+20 Pts)
        4. Evidence Privacy Policy Cited (+15 Pts)
        5. Anti-Evasion / Blacklist Warning Cited (+15 Pts)
        6. Ticket Closure Protocol Executed (+10 Pts)
        """
        client = self._ensure_client()
        default_eval = {
            "score": 85,
            "verdict": "Pass",
            "criteria_breakdown": {
                "greeting": True,
                "phishing_security": True,
                "no_compensation": True,
                "evidence_privacy": True,
                "anti_evasion": False,
                "closure": True
            },
            "feedback_notes": "Demonstrated solid overall SOP application. Ensure anti-evasion warnings are explicitly cited during threat scenarios.",
            "remediation_guide": "• **Study Module 5 (Anti-Evasion & Raids)** in the Support Training Manual.\n• **Copy-Paste Script:** *'Threats to organize raids or mass-report violate our Terms of Service and will result in an immediate Permanent Global Blacklist.'*"
        }

        if not client or not messages_history:
            return default_eval

        staff_msgs = [m["content"] for m in messages_history if m.get("role") == "staff" or m.get("role") == "assistant"]
        staff_text = "\n---\n".join(staff_msgs) if staff_msgs else "No staff replies found."
        full_transcript = "\n".join([f"{m.get('sender_name', m['role']).upper()}: {m['content']}" for m in messages_history])

        prompt = [
            {
                "role": "system",
                "content": (
                    "You are the Lead HR Evaluator for Echo Technologies Support Academy.\n"
                    "Grade the staff member's responses in this ticket transcript against these 6 MANDATORY SOP CRITERIA:\n\n"
                    "1. GREETING (20 pts): Did staff begin their initial response with an official introduction greeting (e.g., 'Hello! My name is [Name] from Echo Technologies Support...')?\n"
                    "2. PHISHING/SECURITY SOP (20 pts): Did staff state that official Echo staff NEVER DM users offering free ranks/giveaways or requesting off-site logins, and refer to roblox.com/support?\n"
                    "3. NO COMPENSATION (20 pts): Did staff refuse unauthorized Robux payouts or rank restorations without Foundership approval?\n"
                    "4. EVIDENCE PRIVACY (15 pts): Did staff state that internal audit logs / detection clips are strictly confidential per the Evidence Privacy Policy?\n"
                    "5. ANTI-EVASION / BLACKLIST (15 pts): Did staff warn that mass-report/raid threats result in a Permanent Global Blacklist?\n"
                    "6. CLOSURE (10 pts): Did staff execute or instruct ticket closure (/ticket-request-close or close prompt)?\n\n"
                    "OUTPUT FORMAT (STRICT JSON ONLY):\n"
                    "{\n"
                    '  "greeting": true/false,\n'
                    '  "phishing_security": true/false,\n'
                    '  "no_compensation": true/false,\n'
                    '  "evidence_privacy": true/false,\n'
                    '  "anti_evasion": true/false,\n'
                    '  "closure": true/false,\n'
                    '  "score": <0-100 integer>,\n'
                    '  "verdict": "<Exceptional|Pass|Conditional Pass|Fail>",\n'
                    '  "feedback_notes": "<2-3 sentence performance summary>",\n'
                    '  "remediation_guide": "<Bullet points with exact missed rules, recommended scripts, and Training Slide references>"\n'
                    "}"
                )
            },
            {
                "role": "user",
                "content": f"SCENARIO: {scenario_title}\n\nSTAFF REPLIES:\n{staff_text}\n\nFULL TICKET TRANSCRIPT:\n{full_transcript}\n\nGrade the staff member:"
            }
        ]

        try:
            res = await self._call_groq_with_fallback(
                client=client,
                messages=prompt,
                temperature=0.2,
                max_tokens=600
            )
            raw = (res.choices[0].message.content or "").strip()
            import json
            if "{" in raw and "}" in raw:
                j_start = raw.find("{")
                j_end = raw.rfind("}") + 1
                data = json.loads(raw[j_start:j_end])
                score = int(data.get("score", 80))
                verdict = data.get("verdict", "Pass" if score >= 85 else "Conditional Pass")
                return {
                    "score": score,
                    "verdict": verdict,
                    "criteria_breakdown": {
                        "greeting": bool(data.get("greeting", True)),
                        "phishing_security": bool(data.get("phishing_security", True)),
                        "no_compensation": bool(data.get("no_compensation", True)),
                        "evidence_privacy": bool(data.get("evidence_privacy", True)),
                        "anti_evasion": bool(data.get("anti_evasion", False)),
                        "closure": bool(data.get("closure", True))
                    },
                    "feedback_notes": data.get("feedback_notes", "Evaluation completed."),
                    "remediation_guide": data.get("remediation_guide", "Review Training Presentation Modules 1-10.")
                }
        except Exception as e:
            logger.error(f"Error evaluating staff test performance: {e}")

        return default_eval
