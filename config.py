import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")

# The specific verification channel requested by user
VERIFICATION_CHANNEL_ID = int(os.getenv("VERIFICATION_CHANNEL_ID", "1556000182196506684"))

# Roles for verification flow
VERIFIED_ROLE_ID = int(os.getenv("VERIFIED_ROLE_ID", "1556000033604640949"))
UNVERIFIED_ROLE_ID = int(os.getenv("UNVERIFIED_ROLE_ID", "1556000025216163961")) # Removed upon verification

# Roles assigned automatically when a new member joins the server
JOIN_ROLE_IDS = [
    int(os.getenv("JOIN_ROLE_1", "1556000025216163961")),
    int(os.getenv("JOIN_ROLE_2", "1556000024712712272"))
]

# Automatically change Discord nickname to Roblox username
UPDATE_NICKNAME = os.getenv("UPDATE_NICKNAME", "true").lower() in ("true", "1", "yes")

# Groq AI Settings
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# Escalation settings
ESCALATION_ROLE_ID = int(os.getenv("ESCALATION_ROLE_ID", "1556000020434526228"))
ESCALATED_TICKETS_CHANNEL_ID = int(os.getenv("ESCALATED_TICKETS_CHANNEL_ID", "1556000170922221661"))

# AI Training channel ID (#ai-trainer)
AI_TRAINER_CHANNEL_ID = int(os.getenv("AI_TRAINER_CHANNEL_ID", "1556003671320559737"))

# Category where tickets will spawn
TICKETS_CATEGORY_ID = int(os.getenv("TICKETS_CATEGORY_ID", "1556000041309708390"))

# Transcripts destination channel
TRANSCRIPT_CHANNEL_ID = int(os.getenv("TRANSCRIPT_CHANNEL_ID", "1556000170922221661"))

# Optional: Guild ID for instant slash command sync during development
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

# Channel IDs for Extended Operations Systems
PUBLIC_LOGS_CHANNEL_ID = int(os.getenv("PUBLIC_LOGS_CHANNEL_ID", "1556021154756698192"))
APPROVALS_CHANNEL_ID = int(os.getenv("APPROVALS_CHANNEL_ID", "1556318687013638156"))
HR_LOGS_CHANNEL_ID = int(os.getenv("HR_LOGS_CHANNEL_ID", "1556000170922221661"))
SUGGESTIONS_CHANNEL_ID = int(os.getenv("SUGGESTIONS_CHANNEL_ID", "1556020755718996020"))
DEV_BACKLOG_CHANNEL_ID = int(os.getenv("DEV_BACKLOG_CHANNEL_ID", "1556020902422913168"))
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", "1556020970815365191"))
HALL_OF_FAME_CHANNEL_ID = int(os.getenv("HALL_OF_FAME_CHANNEL_ID", "1556026672606879824"))
ANNOUNCEMENTS_CHANNEL_ID = int(os.getenv("ANNOUNCEMENTS_CHANNEL_ID", "1556000095411904552"))
STARBOARD_THRESHOLD = int(os.getenv("STARBOARD_THRESHOLD", "3"))
CAREER_OPPORTUNITIES_CHANNEL_ID = int(os.getenv("CAREER_OPPORTUNITIES_CHANNEL_ID", "1556000180774379550"))
APPLICATIONS_SUBMISSIONS_CHANNEL_ID = int(os.getenv("APPLICATIONS_SUBMISSIONS_CHANNEL_ID", "1556318687013638156"))
MOD_LOGS_CHANNEL_ID = int(os.getenv("MOD_LOGS_CHANNEL_ID", "1556000170922221661"))
AFFILIATES_CHANNEL_ID = int(os.getenv("AFFILIATES_CHANNEL_ID", "1556000112692699157"))


# Role IDs for Team Assignments
DEVELOPMENT_TEAM_ROLE_ID = int(os.getenv("DEVELOPMENT_TEAM_ROLE_ID", "1556002109080608768"))
SUPPORT_TEAM_ROLE_ID = int(os.getenv("SUPPORT_TEAM_ROLE_ID", "1556000020434526228"))
PUBLIC_RELATIONS_ROLE_ID = int(os.getenv("PUBLIC_RELATIONS_ROLE_ID", "1556043106283946064"))
LOA_ROLE_ID = int(os.getenv("LOA_ROLE_ID", "1556000031847354509"))
CONTRIBUTOR_ROLE_ID = int(os.getenv("CONTRIBUTOR_ROLE_ID", "1556045803028615259"))
ECHO_ELITE_ROLE_ID = int(os.getenv("ECHO_ELITE_ROLE_ID", "1556045803821473873"))
PARTNER_REP_ROLE_ID = int(os.getenv("PARTNER_REP_ROLE_ID", "1556309041037447238"))
SERVER_INVITE_URL = os.getenv("SERVER_INVITE_URL", "https://discord.gg/8uQxRqbGrH")


# Available ticket sections
TICKET_SECTIONS = [
    "General Support",
    "High-Ranking Support",
    "Development Ticket",
    "Booster Perks"
]


