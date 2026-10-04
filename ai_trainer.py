import discord
import logging
import json
import os
from typing import List, Dict, Any, Optional
import config

logger = logging.getLogger("AITrainer")

class AITrainer:
    """
    Manages the knowledge base for Groq AI by scraping and formatting:
    1. All messages and rich embeds from the #ai-trainer channel (ID: 1556003671320559737).
    2. Server rules, FAQs, announcement embeds, and server context.
    """

    def __init__(self, cache_file: str = "knowledge_cache.json"):
        self.cache_file = cache_file
        self.knowledge_text = ""
        self.training_sources: List[str] = []
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.knowledge_text = data.get("knowledge_text", "")
                    self.training_sources = data.get("training_sources", [])
                    logger.info(f"Loaded cached AI knowledge base ({len(self.knowledge_text)} characters).")
            except Exception as e:
                logger.warning(f"Could not load knowledge cache: {e}")

    def _save_cache(self):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump({
                    "knowledge_text": self.knowledge_text,
                    "training_sources": self.training_sources
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Could not save knowledge cache: {e}")

    @staticmethod
    def extract_embed_text(embed: discord.Embed) -> str:
        """Extracts structured text from an embed including title, description, and all fields."""
        parts = []
        if embed.title:
            parts.append(f"[Embed Title: {embed.title}]")
        if embed.description:
            parts.append(embed.description)
        for field in embed.fields:
            parts.append(f"• {field.name}: {field.value}")
        if embed.footer and embed.footer.text:
            parts.append(f"[Footer: {embed.footer.text}]")
        return "\n".join(parts)

    async def get_ai_trainer_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Locates the #ai-trainer channel by ID or by name, with cache and fetch support."""
        if config.AI_TRAINER_CHANNEL_ID:
            ch = guild.get_channel(config.AI_TRAINER_CHANNEL_ID)
            if not ch:
                try:
                    ch = await guild.fetch_channel(config.AI_TRAINER_CHANNEL_ID)
                except Exception:
                    ch = None
            if isinstance(ch, discord.TextChannel):
                return ch

        for ch in guild.text_channels:
            if "ai-trainer" in ch.name.lower() or "ai_trainer" in ch.name.lower():
                return ch
        return None

    def find_ai_trainer_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Synchronous helper for event handlers."""
        if config.AI_TRAINER_CHANNEL_ID:
            ch = guild.get_channel(config.AI_TRAINER_CHANNEL_ID)
            if isinstance(ch, discord.TextChannel):
                return ch
        for ch in guild.text_channels:
            if "ai-trainer" in ch.name.lower() or "ai_trainer" in ch.name.lower():
                return ch
        return None

    async def train_from_guild(self, guild: discord.Guild) -> Dict[str, Any]:
        """
        Scrapes and compiles knowledge from #ai-trainer and relevant info channels.
        Returns a summary report of the training sync.
        """
        logger.info(f"Starting AI knowledge training from guild: {guild.name} ({guild.id})")
        knowledge_sections = []
        sources = []
        trainer_msg_count = 0
        embed_count = 0

        # Section 1: Server Identity & Context
        server_info = [
            f"=== DISCORD SERVER CONTEXT ===",
            f"Server Name: {guild.name}",
            f"Server Description: {guild.description or 'Community server'}",
            f"Member Count: {guild.member_count}",
        ]
        knowledge_sections.append("\n".join(server_info))

        # Section 2: Scrape #ai-trainer channel (Primary source of truth)
        trainer_channel = await self.get_ai_trainer_channel(guild)
        if trainer_channel:
            logger.info(f"Reading messages and embeds from trainer channel #{trainer_channel.name} ({trainer_channel.id})...")
            trainer_notes = [f"\n=== #AI-TRAINER KNOWLEDGE BASE (PRIMARY INSTRUCTIONS & FAQ) ==="]

            try:
                # Read chronological history (oldest first so it builds narrative or reverse)
                messages = [msg async for msg in trainer_channel.history(limit=500, oldest_first=True)]
                for msg in messages:
                    if msg.content.strip():
                        trainer_msg_count += 1
                        trainer_notes.append(f"• {msg.content.strip()}")

                    # Scrape all rich embeds
                    for em in msg.embeds:
                        embed_text = self.extract_embed_text(em)
                        if embed_text:
                            embed_count += 1
                            trainer_notes.append(f"[EMBED CONTENT]:\n{embed_text}")

                knowledge_sections.append("\n".join(trainer_notes))
                sources.append(f"#{trainer_channel.name} ({trainer_msg_count} messages, {embed_count} embeds)")
            except Exception as e:
                logger.error(f"Error reading #ai-trainer channel: {e}")
        else:
            logger.warning(f"No #ai-trainer channel found (ID: {config.AI_TRAINER_CHANNEL_ID}).")

        # Section 3: Scrape rules, info, and faq channels for extra server context
        info_keywords = ["rules", "info", "faq", "welcome", "about"]
        for ch in guild.text_channels:
            if trainer_channel and ch.id == trainer_channel.id:
                continue
            if any(keyword in ch.name.lower() for keyword in info_keywords):
                try:
                    ch_texts = [f"\n=== CHANNEL: #{ch.name} ==="]
                    ch_msgs = [msg async for msg in ch.history(limit=30, oldest_first=True)]
                    if ch_msgs:
                        for msg in ch_msgs:
                            if msg.content.strip():
                                ch_texts.append(f"• {msg.content.strip()}")
                            for em in msg.embeds:
                                em_txt = self.extract_embed_text(em)
                                if em_txt:
                                    ch_texts.append(f"[EMBED]:\n{em_txt}")
                        knowledge_sections.append("\n".join(ch_texts))
                        sources.append(f"#{ch.name}")
                except Exception as e:
                    logger.debug(f"Could not read #{ch.name}: {e}")

        # Compile final knowledge base
        self.knowledge_text = "\n\n".join(knowledge_sections)
        self.training_sources = sources
        self._save_cache()

        logger.info(f"AI Knowledge training complete. Total size: {len(self.knowledge_text)} chars across {len(sources)} sources.")

        return {
            "sources": sources,
            "trainer_messages": trainer_msg_count,
            "embeds_parsed": embed_count,
            "total_chars": len(self.knowledge_text)
        }

    def get_knowledge_prompt(self) -> str:
        """Returns the compiled knowledge base formatted for system prompt injection, including support & supervisor templates."""
        base_text = self.knowledge_text or "No server-specific knowledge trained yet. Answer helpfully using general Discord/Roblox best practices."
        try:
            from support_templates_system import get_combined_template_list
            from supervisor_templates_system import get_combined_supervisor_template_list
            tpls = get_combined_template_list()
            exec_tpls = get_combined_supervisor_template_list()

            if tpls:
                tpl_lines = ["\n\n=== OFFICIAL SUPPORT TEAM TEMPLATES & STANDARD OPERATING PROCEDURES (SOP) ==="]
                for t in tpls:
                    tpl_lines.append(f"• [{t.get('category', 'General')}] {t['title']} (Shortcut: {t['shortcut']})")
                    tpl_lines.append(f"  SOP Steps: {t.get('steps', 'N/A')}")
                    tpl_lines.append(f"  Official Response Template:\n{t['template']}\n")
                base_text += "\n" + "\n".join(tpl_lines)

            if exec_tpls:
                exec_lines = ["\n\n=== EXECUTIVE SUPERVISOR & HR DIRECTIVES (STAFF DISCIPLINARY & PENALTIES) ==="]
                for t in exec_tpls:
                    exec_lines.append(f"• [{t.get('category', 'Executive HR')}] {t['title']} (Shortcut: {t['shortcut']})")
                    exec_lines.append(f"  Executive Protocol: {t.get('steps', 'N/A')}")
                    exec_lines.append(f"  Formal HR Notice:\n{t['template']}\n")
                base_text += "\n" + "\n".join(exec_lines)
        except Exception as e:
            logger.warning(f"Could not load support/supervisor templates into AI knowledge prompt: {e}")
        return base_text
