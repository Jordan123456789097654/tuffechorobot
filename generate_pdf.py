import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY

pdf_path = r"C:\Users\jorda\.gemini\antigravity\brain\98ea6ed6-4539-4183-a33c-ca792875d6b0\Echo_Support_Training_Manual.pdf"

doc = SimpleDocTemplate(
    pdf_path,
    pagesize=letter,
    rightMargin=54,
    leftMargin=54,
    topMargin=54,
    bottomMargin=54
)

styles = getSampleStyleSheet()

# Custom Palette (Dark Slate & Navy Theme)
PRIMARY_COLOR = colors.HexColor("#0F172A")    # Dark Slate
ACCENT_COLOR = colors.HexColor("#0284C7")     # Sky Blue
TEXT_COLOR = colors.HexColor("#1E293B")       # Deep Slate
MUTED_TEXT = colors.HexColor("#64748B")       # Slate Gray
BG_LIGHT = colors.HexColor("#F8FAFC")         # Very Light Slate
BORDER_COLOR = colors.HexColor("#CBD5E1")     # Border Gray
CODE_BG = colors.HexColor("#0F172A")          # Dark Code BG
CODE_TEXT = colors.HexColor("#38BDF8")        # Bright Blue Code Text
SUCCESS_BG = colors.HexColor("#ECFDF5")       # Light Emerald
DANGER_BG = colors.HexColor("#FEF2F2")        # Light Rose

# Typography Styles
styles.add(ParagraphStyle(
    name='DocTitle',
    fontName='Helvetica-Bold',
    fontSize=24,
    leading=28,
    textColor=PRIMARY_COLOR,
    alignment=TA_LEFT,
    spaceAfter=6
))

styles.add(ParagraphStyle(
    name='DocSubtitle',
    fontName='Helvetica-Bold',
    fontSize=13,
    leading=17,
    textColor=ACCENT_COLOR,
    alignment=TA_LEFT,
    spaceAfter=12
))

styles.add(ParagraphStyle(
    name='SectionHeading',
    fontName='Helvetica-Bold',
    fontSize=14,
    leading=18,
    textColor=PRIMARY_COLOR,
    spaceBefore=12,
    spaceAfter=6,
    keepWithNext=True
))

styles.add(ParagraphStyle(
    name='SubSectionHeading',
    fontName='Helvetica-Bold',
    fontSize=11,
    leading=15,
    textColor=ACCENT_COLOR,
    spaceBefore=8,
    spaceAfter=4,
    keepWithNext=True
))

styles.add(ParagraphStyle(
    name='BodyCustom',
    fontName='Helvetica',
    fontSize=9.5,
    leading=13.5,
    textColor=TEXT_COLOR,
    spaceAfter=6
))

styles.add(ParagraphStyle(
    name='BulletCustom',
    fontName='Helvetica',
    fontSize=9.5,
    leading=13.5,
    textColor=TEXT_COLOR,
    leftIndent=15,
    firstLineIndent=-10,
    spaceAfter=3
))

styles.add(ParagraphStyle(
    name='CodeBlock',
    fontName='Courier-Bold',
    fontSize=8.5,
    leading=11.5,
    textColor=CODE_TEXT,
    spaceBefore=3,
    spaceAfter=3
))

story = []

# --- HEADER / COVER BLOCK ---
story.append(Paragraph("ECHO TECHNOLOGIES • OFFICIAL HR TRAINING DIVISION", ParagraphStyle('SubHeader', fontName='Helvetica-Bold', fontSize=9, leading=11, textColor=ACCENT_COLOR)))
story.append(Paragraph("Master Support Staff Training Manual", styles['DocTitle']))
story.append(Paragraph("Official Standard Operating Procedures (SOPs), Security Directives & Final Exam Guide", styles['DocSubtitle']))
story.append(HRFlowable(width="100%", thickness=2, color=ACCENT_COLOR, spaceBefore=0, spaceAfter=12))

# Metadata Box
meta_data = [
    [Paragraph("<b>Document Version:</b> 2.0 Master", styles['BodyCustom']), Paragraph("<b>Passing Exam Threshold:</b> 90 / 100", styles['BodyCustom'])],
    [Paragraph("<b>Target Audience:</b> Support Trainees & Staff", styles['BodyCustom']), Paragraph("<b>Exam Command:</b> /test-ticket", styles['BodyCustom'])],
    [Paragraph("<b>Classification:</b> Echo HR Confidential", styles['BodyCustom']), Paragraph("<b>Last Updated:</b> October 2026", styles['BodyCustom'])]
]
meta_table = Table(meta_data, colWidths=[3.2*inch, 3.2*inch])
meta_table.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT),
    ('BORDER', (0,0), (-1,-1), 1, BORDER_COLOR),
    ('PADDING', (0,0), (-1,-1), 6),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
]))
story.append(meta_table)
story.append(Spacer(1, 10))

# --- MODULE 1: ACADEMY ORIENTATION ---
story.append(Paragraph("Module 1: Orientation & Evaluation Standards", styles['SectionHeading']))
story.append(Paragraph(
    "Welcome to the official Echo Technologies Support Staff Training Curriculum. All support trainees must complete this comprehensive training manual and pass the automated AI practical examination (<b>/test-ticket</b>) with a score of <b>90/100 or higher</b> before live ticket permissions are granted.",
    styles['BodyCustom']
))
story.append(Paragraph("• <b>Primary Responsibility:</b> Deliver fast, accurate, professional support while adhering strictly to server SOPs.", styles['BulletCustom']))
story.append(Paragraph("• <b>Tone Requirement:</b> Formal, objective, empathetic, and de-escalating at all times.", styles['BulletCustom']))
story.append(Paragraph("• <b>Exam Format:</b> Automated Groq AI roleplay actor simulating demanding members in an isolated test channel.", styles['BulletCustom']))
story.append(Spacer(1, 8))

# --- MODULE 2: MANDATORY GREETING SOP ---
story.append(Paragraph("Module 2: Mandatory Initial Greeting SOP", styles['SectionHeading']))
story.append(Paragraph(
    "First impressions establish operational authority. Every initial response sent by a staff member in a ticket MUST begin with our official introduction greeting statement.",
    styles['BodyCustom']
))

greeting_box = [
    [Paragraph("<b>MANDATORY OFFICIAL INTRODUCTION SCRIPT (100% REQUIRED)</b>", ParagraphStyle('GHead', fontName='Helvetica-Bold', fontSize=8.5, textColor=colors.white))],
    [Paragraph('<i>"Hello @Member! My name is {staff_name} from the Echo Technologies Support Team. I will be assisting you today. Please state your inquiry or details below."</i>', styles['CodeBlock'])]
]
t_gbox = Table(greeting_box, colWidths=[6.4*inch])
t_gbox.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), PRIMARY_COLOR),
    ('BACKGROUND', (0,1), (-1,1), CODE_BG),
    ('PADDING', (0,0), (-1,-1), 6),
    ('BORDER', (0,0), (-1,-1), 1, PRIMARY_COLOR),
]))
story.append(t_gbox)
story.append(Spacer(1, 6))

# Do vs Don't Table
dodont_data = [
    [Paragraph("<b>✅ DO (CORRECT PRACTICE)</b>", ParagraphStyle('DoH', fontName='Helvetica-Bold', fontSize=8.5, textColor=colors.HexColor("#065F46"))), Paragraph("<b>❌ DON'T (STRIKE PENALTY)</b>", ParagraphStyle('DontH', fontName='Helvetica-Bold', fontSize=8.5, textColor=colors.HexColor("#991B1B")))],
    [
        Paragraph("Always open with your official name & department greeting before asking questions.", styles['BodyCustom']),
        Paragraph("Never skip the greeting or reply with blunt lines like 'send evidence'.", styles['BodyCustom'])
    ],
    [
        Paragraph("Maintain polite, empathetic tone even if the user is using ALL-CAPS or demanding.", styles['BodyCustom']),
        Paragraph("Never argue back, mock, or use informal/sarcastic language with members.", styles['BodyCustom'])
    ]
]
t_dodont = Table(dodont_data, colWidths=[3.2*inch, 3.2*inch])
t_dodont.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (0,-1), SUCCESS_BG),
    ('BACKGROUND', (1,0), (1,-1), DANGER_BG),
    ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
    ('PADDING', (0,0), (-1,-1), 5),
]))
story.append(t_dodont)
story.append(Spacer(1, 10))

# --- MODULE 3: PHISHING & ACCOUNT SECURITY ---
story.append(Paragraph("Module 3: Phishing Scams & Compromised Accounts", styles['SectionHeading']))
story.append(Paragraph(
    "Phishing scams (fake rank claim DMs, unauthorized developer giveaway links) represent the highest volume ticket category. Support staff must enforce the 4-Step Security Protocol:",
    styles['BodyCustom']
))
story.append(Paragraph("1. <b>Deliver Phishing Disclaimer:</b> Explicitly state that official Echo staff NEVER DM users offering free ranks, requesting passwords/cookies, or asking for off-site logins.", styles['BulletCustom']))
story.append(Paragraph("2. <b>Account Recovery Steps:</b> Instruct member to reset Roblox password, enable 2-Step Verification (2FA), and clear unauthorized sessions.", styles['BulletCustom']))
story.append(Paragraph("3. <b>Refer to Roblox Support:</b> Provide official link: <u>https://www.roblox.com/support</u>. State clearly that account recovery and stolen Robux are handled solely by Roblox Trust & Safety.", styles['BulletCustom']))
story.append(Paragraph("4. <b>Scam Evidence Request:</b> Ask member for uncropped screenshots showing the scammer's Discord ID, DM history, and fake link for staff audit.", styles['BulletCustom']))
story.append(Spacer(1, 8))

# --- MODULE 4: COMPENSATION POLICIES ---
story.append(Paragraph("Module 4: Zero-Tolerance Compensation & Refund Rules", styles['SectionHeading']))
story.append(Paragraph(
    "Compromised players often demand Robux refunds or unearned group rank restorations. Support staff have <b>ZERO AUTHORITY</b> to issue or promise compensation.",
    styles['BodyCustom']
))

comp_box = [
    [Paragraph("<b>STRICT COMPENSATION PROHIBITION SCRIPT</b>", ParagraphStyle('CHead', fontName='Helvetica-Bold', fontSize=8.5, textColor=colors.white))],
    [Paragraph('<i>"Echo Technologies is not responsible for off-site phishing scams or compromised personal accounts. We do not issue Robux payouts, group funds, or unearned group rank restorations without explicit Foundership authorization."</i>', styles['CodeBlock'])]
]
t_cbox = Table(comp_box, colWidths=[6.4*inch])
t_cbox.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#B91C1C")),
    ('BACKGROUND', (0,1), (-1,1), CODE_BG),
    ('PADDING', (0,0), (-1,-1), 6),
    ('BORDER', (0,0), (-1,-1), 1, colors.HexColor("#B91C1C")),
]))
story.append(t_cbox)
story.append(Spacer(1, 10))

# --- MODULE 5: EVIDENCE PRIVACY ---
story.append(Paragraph("Module 5: Evidence Privacy & Internal Audit Logs", styles['SectionHeading']))
story.append(Paragraph(
    "When banned or demoted users demand internal detection clips, anti-cheat logs, or staff discussion transcripts, staff MUST cite the Evidence Privacy SOP:",
    styles['BodyCustom']
))
story.append(Paragraph('<i>"Per our Evidence Privacy Policy, internal moderation audit logs, anti-cheat detection clips, and staff discussion evidence are strictly confidential and reserved for staff review only."</i>', styles['BodyCustom']))
story.append(Spacer(1, 8))

# --- MODULE 6: ANTI-EVASION & RAIDS ---
story.append(Paragraph("Module 6: Anti-Evasion, Blacklisting & Raid Protocols", styles['SectionHeading']))
story.append(Paragraph(
    "Hostile members threatening alt account raids, server disruption, or mass-report campaigns MUST receive the formal Permanent Global Blacklist warning:",
    styles['BodyCustom']
))
story.append(Paragraph('<i>"Threats to organize raids, mass-report our Discord server, or bypass moderation actions violate Echo Technologies Terms of Service and will result in an immediate Permanent Global Blacklist across all associated servers and services."</i>', styles['BodyCustom']))
story.append(Spacer(1, 10))

# --- MODULE 7 & 8: VERIFICATION & EXPLOIT REPORTS ---
story.append(Paragraph("Module 7 & 8: Verification & Exploit Evidence", styles['SectionHeading']))
story.append(Paragraph("• <b>Unverified Accounts:</b> Run <code>/manual-verify target_user:@User roblox_username:Username</code> if bio codes are censored.", styles['BulletCustom']))
story.append(Paragraph("• <b>Exploit Video Proof:</b> Exploit reports require uncropped video evidence clearly showing the player's Roblox Username above their character and the in-game scoreboard (F9 / Tab menu).", styles['BulletCustom']))
story.append(Spacer(1, 8))

# --- MODULE 9: DE-ESCALATION MATRIX ---
story.append(Paragraph("Module 9: De-Escalation & Conflict Resolution Matrix", styles['SectionHeading']))

matrix_data = [
    [Paragraph("<b>User Threat Level</b>", styles['SubSectionHeading']), Paragraph("<b>Required Staff Action & Phrasing</b>", styles['SubSectionHeading'])],
    [
        Paragraph("<b>Level 1: Frustrated / CAPS</b>", styles['BodyCustom']),
        Paragraph("Acknowledge frustration calmly, restate server rules objectively, and maintain supportive tone.", styles['BodyCustom'])
    ],
    [
        Paragraph("<b>Level 2: Insults & Abuse</b>", styles['BodyCustom']),
        Paragraph("Issue 1 formal warning: <i>'Please maintain a respectful tone so we can assist you. Continued abuse will result in ticket closure.'</i>", styles['BodyCustom'])
    ],
    [
        Paragraph("<b>Level 3: Raid / Mass Threat</b>", styles['BodyCustom']),
        Paragraph("Cite Permanent Global Blacklist penalty, escalate user ID to Foundership, and execute ticket closure.", styles['BodyCustom'])
    ]
]
t_matrix = Table(matrix_data, colWidths=[2.2*inch, 4.2*inch])
t_matrix.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), BG_LIGHT),
    ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
    ('PADDING', (0,0), (-1,-1), 5),
]))
story.append(t_matrix)
story.append(Spacer(1, 10))

# --- MODULE 10, 11, 12: CASE STUDIES ---
story.append(Paragraph("Module 10–12: Master Exam Case Studies", styles['SectionHeading']))
story.append(Paragraph("<b>Case Study Sample (Pass 100/100):</b>", styles['SubSectionHeading']))
story.append(Paragraph(
    "<i>'Hello @Jordan! My name is Alex from the Echo Technologies Support Team. I will be assisting you today.<br/>"
    "I am very sorry to hear about your account. Please note that official Echo staff will NEVER DM users offering free ranks or requesting off-site logins.<br/>"
    "Please reset your password, enable 2FA, and submit a recovery ticket to Roblox Support (https://www.roblox.com/support).<br/>"
    "Echo Technologies does not issue Robux payouts for off-site scams. Additionally, mass-report threats violate our TOS and result in a Permanent Global Blacklist.<br/>"
    "If you have screenshots of the scammer's DMs, please reply here!'</i>",
    styles['BodyCustom']
))
story.append(Spacer(1, 8))

# --- MODULE 13 & 14: CLOSURE & KNOWLEDGE CHECK ---
story.append(Paragraph("Module 13 & 14: Ticket Closure & Knowledge Check", styles['SectionHeading']))
story.append(Paragraph("• <b>Formal Closure:</b> Execute <code>/ticket-request-close</code> or click 'Request Close' on the Modmail console embed.", styles['BulletCustom']))
story.append(Paragraph("• <b>Quiz Q1:</b> User demands 4,500 Robux compensation. <b>Correct Action:</b> Refuse payout, state Echo rules, refer to roblox.com/support.", styles['BulletCustom']))
story.append(Paragraph("• <b>Quiz Q2:</b> User demands internal video proof. <b>Correct Action:</b> Cite Evidence Privacy Policy.", styles['BulletCustom']))
story.append(Spacer(1, 8))

# --- MODULE 15: EXAM SCORING RUBRIC ---
story.append(Paragraph("Module 15: Final Exam Launch & Scoring Rubric", styles['SectionHeading']))

rubric_data = [
    [Paragraph("<b>SOP Evaluation Criteria</b>", styles['SubSectionHeading']), Paragraph("<b>Points</b>", styles['SubSectionHeading']), Paragraph("<b>Requirement</b>", styles['SubSectionHeading'])],
    [Paragraph("1. Mandatory Greeting Delivered", styles['BodyCustom']), Paragraph("20 Pts", styles['BodyCustom']), Paragraph("Must introduce name & department", styles['BodyCustom'])],
    [Paragraph("2. Security & Phishing SOP Cited", styles['BodyCustom']), Paragraph("20 Pts", styles['BodyCustom']), Paragraph("Warn fake DMs & roblox.com/support", styles['BodyCustom'])],
    [Paragraph("3. Refused Unauthorized Compensation", styles['BodyCustom']), Paragraph("20 Pts", styles['BodyCustom']), Paragraph("Strict zero Robux payout policy", styles['BodyCustom'])],
    [Paragraph("4. Evidence Privacy SOP Cited", styles['BodyCustom']), Paragraph("15 Pts", styles['BodyCustom']), Paragraph("Confidential audit log citation", styles['BodyCustom'])],
    [Paragraph("5. Anti-Evasion / Blacklist Warning", styles['BodyCustom']), Paragraph("15 Pts", styles['BodyCustom']), Paragraph("Cite Permanent Global Blacklist", styles['BodyCustom'])],
    [Paragraph("6. Ticket Closure Protocol Executed", styles['BodyCustom']), Paragraph("10 Pts", styles['BodyCustom']), Paragraph("Execute /ticket-request-close", styles['BodyCustom'])],
    [Paragraph("<b>TOTAL PASSING SCORE THRESHOLD</b>", ParagraphStyle('TotH', fontName='Helvetica-Bold', fontSize=8.5, textColor=PRIMARY_COLOR)), Paragraph("<b>90 / 100</b>", ParagraphStyle('TotH2', fontName='Helvetica-Bold', fontSize=8.5, textColor=ACCENT_COLOR)), Paragraph("<b>90% OR HIGHER REQUIRED TO PASS</b>", styles['BodyCustom'])]
]
t_rubric = Table(rubric_data, colWidths=[2.8*inch, 1.0*inch, 2.6*inch])
t_rubric.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), BG_LIGHT),
    ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#E2E8F0")),
    ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
    ('PADDING', (0,0), (-1,-1), 4),
]))
story.append(t_rubric)
story.append(Spacer(1, 10))

# Footer Notice
story.append(Paragraph("<b>HOW TO LAUNCH FINAL EXAM:</b> Request a Foundership / Trainer to execute <code>/test-ticket</code> in Discord.", ParagraphStyle('FNot', fontName='Helvetica-Bold', fontSize=8.5, textColor=ACCENT_COLOR, alignment=TA_CENTER)))

doc.build(story)
print(f"PDF successfully generated at: {pdf_path}")
