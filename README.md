# 🛡️ Roblox Verification & Multi-Department AI Ticket Discord Bot

A complete, production-ready Discord bot built in Python (`discord.py`) featuring:
1. **Roblox Profile Verification** with censorship-proof bio phrases in channel `1556000182196506684`.
2. **Auto-Role on Join & Verify:** Auto-assigns join roles `1556000025216163961` and `1556000024712712272` on join, grants verified role `1556000033604640949`, and automatically strips unverified role `1556000025216163961`.
3. **Multi-Department AI Ticket System** powered by **Groq AI** (`openai/gpt-oss-120b`).
4. **4 Dedicated Ticket Categories / Sections:**
   - 💬 **General Support**
   - 🛡️ **High-Ranking Support**
   - 💻 **Development Ticket**
   - 🚀 **Booster Perks**
5. **Staff Transfer Feature:** Transfer tickets between categories via command or interactive button.
6. **Automatic HTML Transcripts:** Formatted Discord-styled HTML transcripts sent to channel `1556000161690292274` upon ticket closing.
7. **Experience Rating System:** 1–5 Star rating with optional written feedback prompt.
8. **Intelligent Escalation:** Alerts role `1556000020434526228` and sends AI summaries to `1556004251241545961`.

---

## 📋 Configured Channels & Roles Reference

| Feature | Snowflake ID | Purpose |
|---|---|---|
| **Verification Channel** | `1556000182196506684` | Verification panel embed location |
| **Auto-Join Role 1** | `1556000025216163961` | Given on join, **removed upon verification** |
| **Auto-Join Role 2** | `1556000024712712272` | Given on join |
| **Verified Role** | `1556000033604640949` | Awarded upon Roblox verification |
| **Ticket Spawning Category** | `1556000041309708390` | Category where ticket channels spawn |
| **AI Trainer Channel** | `1556003671320559737` | Channel `#ai-trainer` where AI pulls training messages & embeds |
| **Escalated Tickets Channel** | `1556004251241545961` | Channel where escalated ticket alerts and summaries are sent |
| **Escalation Role** | `1556000020434526228` | Role pinged when a ticket is escalated |
| **Transcripts Channel** | `1556000161690292274` | Channel where closed ticket HTML transcripts are sent |

---

## 💻 Full Slash Command Reference

### 👤 Member Self-Service
- **`/update [member: optional]`** — Re-sync your Roblox username, display name, and nickname/roles.
- **`/reverify`** — Unlinks your current Roblox profile and prompts you to link a new one.
- **`/whois [member: optional]`** — Displays avatar headshot, Roblox profile link, ID, and verification date.
- **`/verify-stats`** — Shows total verified members, server member count, and % verified.

### 👑 Staff & Administration
- **`/manual-verify [member] [roblox_username]`** — Bypasses bio check. Instantly links account, assigns verified role `1556000033604640949`, removes unverified role `1556000025216163961`, and syncs nickname.
- **`/force-verify [member] [roblox_id]`** — Verify a member directly using their numeric Roblox ID.
- **`/unlink [member]`** — Disconnect a user's Roblox account and remove verified roles.
- **`/lookup-roblox [query]`** — Reverse lookup: find which Discord account owns a given Roblox username or ID.
- **`/check-alt [member]`** — Analyzes account age and Roblox creation date to detect suspicious alt accounts.
- **`/send-panel [channel]`** — Deploys or refreshes the Roblox verification panel.
- **`/send-ticket-panel [channel]`** — Deploys the multi-department support ticket panel with category dropdown.

### 🎫 Ticket State Management (`/ticket ...`)
- **`/ticket close [reason]`** — Closes the ticket, uploads HTML transcript to `1556000161690292274`, and triggers the 1–5 star experience rating.
- **`/ticket force-close`** — Instantly deletes the ticket channel without countdown.
- **`/ticket rename [new_name]`** — Renames the current ticket channel.
- **`/ticket priority [Low|Normal|High|Urgent]`** — Updates ticket priority (Urgent alerts staff role `1556000020434526228`).
- **`/ticket slowmode [seconds]`** — Enforces slowmode in the ticket channel.

### 👥 Staff Assignment & Collaboration
- **`/ticket claim`** — Claims the ticket so other staff know who is handling it.
- **`/ticket unclaim`** — Releases claim back to the general staff pool.
- **`/ticket add [member]`** — Adds an extra user or specialist to the ticket channel.
- **`/ticket remove [member]`** — Removes a user from the ticket channel.
- **`/ticket transfer-category [category]`** — Transfers ticket between:
  - `General Support`
  - `High-Ranking Support`
  - `Development Ticket`
  - `Booster Perks`

### 🚨 Escalation Workflow
- **`/ticket escalate [reason]`** — Manually escalates ticket: pauses AI, pings role `1556000020434526228`, and posts AI summary to `1556004251241545961`.
- **`/ticket de-escalate`** — Re-enables AI assistant and returns ticket to open state.

### 🧠 Knowledge & AI Controls
- **`/train-ai`** — Re-trains the Groq AI from channel `1556003671320559737` and all server embeds.
- **`/ticket toggle-ai`** — Pauses or resumes AI auto-replies in the active ticket channel.
- **`/ai-summarize`** — Generates an instant bullet-point summary of the ticket conversation.
- **`/ai-add-note [note]`** — Injects a temporary rule/fact directly into AI memory.
- **`/ai-inspect`** — Displays active Groq model, total memory size, and indexed sources.

### 📁 Transcripts & Satisfaction Analytics
- **`/ticket transcript`** — Exports an HTML transcript file of the active ticket.
- **`/ticket stats`** — Dashboard showing total tickets, open/closed counts, average rating (e.g. `4.85 / 5.0 ⭐`), and star breakdown.
- **`/ticket reviews [limit]`** — Displays recent written feedback comments from members.

### 🚫 Anti-Spam & Moderation Controls
- **`/ticket blacklist-add [member] [reason]`** — Blocks a user from creating tickets or sending Modmail.
- **`/ticket blacklist-remove [member]`** — Unblocks a member from the ticket system.
- **`/ticket blacklist-list`** — Displays all blacklisted users and reasons.

---

## 🏃 Running the Bot

1. Open [.env](file:///C:/Users/jorda/.gemini/antigravity/scratch/roblox-verify-bot/.env) and ensure your `DISCORD_TOKEN` is entered.
2. Launch the bot:
```powershell
python bot.py
```
*(Or double-click [run.bat](file:///C:/Users/jorda/.gemini/antigravity/scratch/roblox-verify-bot/run.bat))*
