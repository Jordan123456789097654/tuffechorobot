import sqlite3
import discord
from discord import app_commands
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

logger = logging.getLogger("roblox_bot.hiring_system")
DB_PATH = "verifications.db"

def init_hiring_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ATS Notes Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hiring_ats_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            note TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # ATS Flags Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hiring_ats_flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL,
            flagged_by INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Scheduled Interviews & Scorecards Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hiring_interviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER NOT NULL,
            date_time TEXT NOT NULL,
            interviewer_id INTEGER NOT NULL,
            status TEXT DEFAULT 'Scheduled',
            channel_id INTEGER,
            comm_score INTEGER DEFAULT 0,
            knowledge_score INTEGER DEFAULT 0,
            recommend TEXT DEFAULT 'Pending',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Custom Offers Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hiring_custom_offers (
            offer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER NOT NULL,
            position TEXT NOT NULL,
            probation_days INTEGER DEFAULT 14,
            salary_terms TEXT,
            custom_terms TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Onboarding & Mentorship Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hiring_onboarding (
            discord_id INTEGER PRIMARY KEY,
            mentor_id INTEGER,
            start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            quiz_score INTEGER DEFAULT 0,
            status TEXT DEFAULT 'In Progress'
        );
    """)

    # Hiring Campaigns Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hiring_campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            positions TEXT NOT NULL,
            deadline TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    conn.close()

init_hiring_db()

# --- ATS & NOTES FUNCTIONS ---
def add_ats_note(application_id: int, author_id: int, note: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hiring_ats_notes (application_id, author_id, note)
        VALUES (?, ?, ?)
    """, (application_id, author_id, note))
    n_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return n_id

def get_ats_notes(application_id: int) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hiring_ats_notes WHERE application_id = ? ORDER BY created_at DESC", (application_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "application_id": r[1], "author_id": r[2], "note": r[3], "created_at": r[4]} for r in rows]

def flag_application(application_id: int, flagged_by: int, reason: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hiring_ats_flags (application_id, flagged_by, reason)
        VALUES (?, ?, ?)
    """, (application_id, flagged_by, reason))
    f_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return f_id

def get_application_flags(application_id: int) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hiring_ats_flags WHERE application_id = ? ORDER BY created_at DESC", (application_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "application_id": r[1], "flagged_by": r[2], "reason": r[3], "created_at": r[4]} for r in rows]

# --- INTERVIEW FUNCTIONS ---
def schedule_interview(discord_id: int, date_time: str, interviewer_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hiring_interviews (discord_id, date_time, interviewer_id)
        VALUES (?, ?, ?)
    """, (discord_id, date_time, interviewer_id))
    i_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return i_id

def log_interview_scorecard(interview_id: int, comm_score: int, knowledge_score: int, recommend: str, notes: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE hiring_interviews
        SET comm_score = ?, knowledge_score = ?, recommend = ?, notes = ?, status = 'Completed'
        WHERE id = ?
    """, (comm_score, knowledge_score, recommend, notes, interview_id))
    conn.commit()
    conn.close()

# --- CUSTOM OFFERS ---
def create_custom_offer(discord_id: int, position: str, probation_days: int, salary_terms: str, custom_terms: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hiring_custom_offers (discord_id, position, probation_days, salary_terms, custom_terms)
        VALUES (?, ?, ?, ?, ?)
    """, (discord_id, position, probation_days, salary_terms, custom_terms))
    offer_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return offer_id

def update_offer_status(offer_id: int, status: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE hiring_custom_offers SET status = ? WHERE offer_id = ?", (status, offer_id))
    conn.commit()
    conn.close()

# --- ONBOARDING & MENTORSHIP ---
def start_onboarding(discord_id: int, mentor_id: Optional[int] = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hiring_onboarding (discord_id, mentor_id)
        VALUES (?, ?)
        ON CONFLICT(discord_id) DO UPDATE SET mentor_id = excluded.mentor_id;
    """, (discord_id, mentor_id))
    conn.commit()
    conn.close()

def get_onboarding_status(discord_id: int) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hiring_onboarding WHERE discord_id = ?", (discord_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "discord_id": row[0],
            "mentor_id": row[1],
            "start_date": row[2],
            "quiz_score": row[3],
            "status": row[4]
        }
    return None

# --- HIRING CAMPAIGNS ---
def start_hiring_campaign(title: str, positions: str, deadline: Optional[str] = None) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hiring_campaigns (title, positions, deadline)
        VALUES (?, ?, ?)
    """, (title, positions, deadline))
    c_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return c_id
