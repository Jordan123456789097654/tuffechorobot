import html
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

def generate_html_transcript(
    ticket: Dict[str, Any],
    messages: List[Dict[str, Any]],
    user_info: Optional[Dict[str, Any]] = None,
    rating_info: Optional[Dict[str, Any]] = None
) -> str:
    """
    Generates a beautiful, standalone Discord-styled dark HTML transcript
    of a ticket conversation.
    """
    ticket_id = ticket.get("id", "Unknown")
    section = ticket.get("section", "General Support")
    status = ticket.get("status", "closed").upper()
    priority = ticket.get("priority", "Normal")
    created_at = ticket.get("created_at", "Unknown")
    closed_at = ticket.get("closed_at", "Unknown")

    username = user_info.get("discord_name", f"User {ticket.get('user_id')}") if user_info else f"User {ticket.get('user_id')}"
    roblox_str = "Not Verified"
    if user_info and user_info.get("roblox_username"):
        roblox_str = f"{user_info.get('roblox_display_name')} (@{user_info.get('roblox_username')}) [ID: {user_info.get('roblox_id')}]"

    rating_html = ""
    if rating_info:
        stars = "⭐" * rating_info.get("rating", 0)
        feedback = html.escape(rating_info.get("feedback") or "No comments provided.")
        rating_html = f"""
        <div class="meta-box rating-box">
            <strong>Customer Satisfaction:</strong> {stars} ({rating_info.get('rating')}/5 Stars)<br>
            <strong>Feedback:</strong> <em>{feedback}</em>
        </div>
        """

    messages_html = []
    for msg in messages:
        sender_type = msg.get("sender_type", "user").lower()
        sender_name = html.escape(msg.get("sender_name", "Unknown"))
        content = html.escape(msg.get("content", "")).replace("\n", "<br>")
        timestamp = msg.get("created_at", "")

        badge_class = "badge-user"
        badge_text = "MEMBER"
        if sender_type == "ai":
            badge_class = "badge-ai"
            badge_text = "AI BOT"
        elif sender_type == "staff":
            badge_class = "badge-staff"
            badge_text = "STAFF"
        elif sender_type == "internal_note":
            badge_class = "badge-note"
            badge_text = "INTERNAL NOTE"

        # Format attachments
        attachments_html = ""
        raw_att = msg.get("attachments")
        if raw_att:
            try:
                att_list = json.loads(raw_att) if isinstance(raw_att, str) else raw_att
                for url in att_list:
                    safe_url = html.escape(url)
                    is_img = any(safe_url.lower().endswith(ext) or ext in safe_url.lower() for ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp'))
                    if is_img:
                        attachments_html += f'<div class="attachment"><a href="{safe_url}" target="_blank"><img src="{safe_url}" alt="Attachment" style="max-width: 380px; max-height: 280px; border-radius: 8px; margin-top: 8px; border: 1px solid #4e5058; display: block;"></a></div>'
                    else:
                        attachments_html += f'<div class="attachment" style="margin-top: 6px;"><a href="{safe_url}" target="_blank" style="color: #00a2ff; text-decoration: underline; font-weight: 500;">📎 Download File Attachment</a></div>'
            except Exception:
                pass

        msg_block = f"""
        <div class="message {sender_type}">
            <div class="message-header">
                <span class="sender-name">{sender_name}</span>
                <span class="badge {badge_class}">{badge_text}</span>
                <span class="timestamp">{timestamp}</span>
            </div>
            <div class="message-content">{content}{attachments_html}</div>
        </div>
        """
        messages_html.append(msg_block)

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transcript - Ticket #{ticket_id}</title>
    <style>
        body {{
            background-color: #313338;
            color: #dbdee1;
            font-family: 'gg sans', 'Noto Sans', 'Helvetica Neue', Helvetica, Arial, sans-serif;
            margin: 0;
            padding: 24px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: #2b2d31;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.4);
        }}
        .header {{
            background: #1e1f22;
            padding: 24px;
            border-bottom: 2px solid #383a40;
        }}
        .header h1 {{
            margin: 0 0 12px 0;
            font-size: 24px;
            color: #5865f2;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
            font-size: 14px;
        }}
        .meta-box {{
            background: #232428;
            padding: 10px 14px;
            border-radius: 6px;
            border-left: 3px solid #5865f2;
        }}
        .rating-box {{
            grid-column: 1 / -1;
            border-left-color: #f1c40f;
            background: #2b281b;
        }}
        .messages {{
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}
        .message {{
            background: #313338;
            padding: 14px 18px;
            border-radius: 8px;
            border-left: 4px solid #4e5058;
        }}
        .message.ai {{
            border-left-color: #00a2ff;
            background: #263342;
        }}
        .message.staff {{
            border-left-color: #57f287;
            background: #25392e;
        }}
        .message.internal_note {{
            border-left-color: #fee75c;
            background: rgba(254, 231, 92, 0.08);
            border: 1px dashed #fee75c;
        }}
        .message.user {{
            border-left-color: #5865f2;
        }}
        .message-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 6px;
        }}
        .sender-name {{
            font-weight: 600;
            color: #f2f3f5;
        }}
        .badge {{
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: bold;
            text-transform: uppercase;
        }}
        .badge-user {{ background: #5865f2; color: white; }}
        .badge-ai {{ background: #00a2ff; color: white; }}
        .badge-staff {{ background: #57f287; color: black; }}
        .badge-note {{ background: #fee75c; color: black; font-weight: 800; }}
        .timestamp {{
            font-size: 12px;
            color: #949ba4;
            margin-left: auto;
        }}
        .message-content {{
            font-size: 15px;
            line-height: 1.45;
            color: #dbdee1;
            word-break: break-word;
        }}
        .footer {{
            background: #1e1f22;
            padding: 16px;
            text-align: center;
            font-size: 13px;
            color: #949ba4;
            border-top: 1px solid #383a40;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎫 Ticket #{ticket_id} &bull; {html.escape(section)}</h1>
            <div class="meta-grid">
                <div class="meta-box"><strong>User:</strong> {html.escape(username)}</div>
                <div class="meta-box"><strong>Roblox:</strong> {html.escape(roblox_str)}</div>
                <div class="meta-box"><strong>Priority:</strong> {html.escape(priority)}</div>
                <div class="meta-box"><strong>Status:</strong> {html.escape(status)}</div>
                <div class="meta-box"><strong>Created:</strong> {html.escape(str(created_at))}</div>
                <div class="meta-box"><strong>Closed:</strong> {html.escape(str(closed_at))}</div>
                {rating_html}
            </div>
        </div>
        <div class="messages">
            {"".join(messages_html) if messages_html else "<div class='message'><div class='message-content'>No messages recorded.</div></div>"}
        </div>
        <div class="footer">
            Generated by Roblox Verification & AI Ticket Bot &bull; {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}
        </div>
    </div>
</body>
</html>
"""
    return full_html


def generate_application_html_transcript(
    app_data: Dict[str, Any],
    questions: List[str],
    user_info: Optional[Dict[str, Any]] = None,
    reviewer_name: Optional[str] = None
) -> str:
    """
    Generates a standalone Discord-styled HTML dossier transcript for a staff/developer application.
    """
    app_id = app_data.get("id", "Unknown")
    pos_title = app_data.get("position_title", "Position")
    status = str(app_data.get("status", "pending_review")).upper()
    created_at = app_data.get("created_at", "Unknown")
    completed_at = app_data.get("completed_at", "Unknown")
    review_note = app_data.get("review_note") or "No notes provided."

    username = user_info.get("discord_name", f"User {app_data.get('user_id')}") if user_info else f"User {app_data.get('user_id')}"
    roblox_str = "Not Verified"
    if user_info and user_info.get("roblox_username"):
        roblox_str = f"{user_info.get('roblox_display_name')} (@{user_info.get('roblox_username')}) [ID: {user_info.get('roblox_id')}]"

    # AI Pre-screening info
    ai_html = ""
    raw_ai = app_data.get("ai_analysis")
    if raw_ai:
        try:
            ai_data = json.loads(raw_ai) if isinstance(raw_ai, str) else raw_ai
            score = ai_data.get("score", "N/A")
            quality = ai_data.get("quality", "Medium")
            summary = html.escape(ai_data.get("summary", ""))
            flags = ai_data.get("flags", [])
            flags_str = ", ".join(flags) if flags else "None"

            color_class = "score-high" if int(score) >= 7 else ("score-mid" if int(score) >= 5 else "score-low")
            ai_html = f"""
            <div class="meta-box ai-box">
                <div style="font-size: 16px; font-weight: bold; margin-bottom: 6px;">🤖 AI Pre-Screening Evaluation</div>
                <strong>Quality Score:</strong> <span class="{color_class}">{score}/10 ({quality})</span><br>
                <strong>Summary:</strong> {summary}<br>
                <strong>Flags / Warnings:</strong> <em>{html.escape(flags_str)}</em>
            </div>
            """
        except Exception:
            pass

    # Q&A Cards
    answers = json.loads(app_data.get("answers") or "[]")
    qa_html = []
    for i, ans in enumerate(answers):
        q_text = html.escape(questions[i] if i < len(questions) else f"Question {i+1}")
        a_text = html.escape(ans).replace("\n", "<br>")
        card = f"""
        <div class="qa-card">
            <div class="q-title">Question {i+1}: {q_text}</div>
            <div class="a-body">{a_text}</div>
        </div>
        """
        qa_html.append(card)

    # Attachments
    attachments_html = ""
    raw_att = app_data.get("attachments")
    if raw_att:
        try:
            att_list = json.loads(raw_att) if isinstance(raw_att, str) else raw_att
            if att_list:
                att_items = []
                for idx, url in enumerate(att_list):
                    safe_url = html.escape(url)
                    att_items.append(f'<li><a href="{safe_url}" target="_blank" style="color: #00a2ff;">Attachment #{idx+1}</a></li>')
                attachments_html = f"""
                <div class="qa-card" style="border-left-color: #fee75c;">
                    <div class="q-title">📎 Uploaded Portfolio & Attachments</div>
                    <ul style="margin: 8px 0 0 18px; padding: 0;">{"".join(att_items)}</ul>
                </div>
                """
        except Exception:
            pass

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Application Dossier - #{app_id} ({html.escape(pos_title)})</title>
    <style>
        body {{
            background-color: #313338;
            color: #dbdee1;
            font-family: 'gg sans', 'Noto Sans', 'Helvetica Neue', Helvetica, Arial, sans-serif;
            margin: 0;
            padding: 24px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: #2b2d31;
            border-radius: 10px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.4);
            overflow: hidden;
            border: 1px solid #1e1f22;
        }}
        .header {{
            background: #1e1f22;
            padding: 24px;
            border-bottom: 2px solid #5865f2;
        }}
        h1 {{
            margin: 0 0 16px 0;
            color: #ffffff;
            font-size: 24px;
        }}
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 12px;
        }}
        .meta-box {{
            background: #2b2d31;
            padding: 12px 14px;
            border-radius: 6px;
            font-size: 13px;
            border: 1px solid #383a40;
        }}
        .ai-box {{
            grid-column: 1 / -1;
            background: rgba(0, 162, 255, 0.08);
            border: 1px dashed #00a2ff;
        }}
        .score-high {{ color: #57f287; font-weight: bold; }}
        .score-mid {{ color: #fee75c; font-weight: bold; }}
        .score-low {{ color: #ed4245; font-weight: bold; }}
        .content-area {{
            padding: 24px;
        }}
        .qa-card {{
            background: #313338;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
            border-left: 4px solid #5865f2;
            border-top: 1px solid #383a40;
            border-right: 1px solid #383a40;
            border-bottom: 1px solid #383a40;
        }}
        .q-title {{
            font-weight: 700;
            color: #5865f2;
            margin-bottom: 8px;
            font-size: 15px;
        }}
        .a-body {{
            font-size: 14px;
            line-height: 1.5;
            color: #dbdee1;
        }}
        .footer {{
            background: #1e1f22;
            padding: 16px;
            text-align: center;
            font-size: 13px;
            color: #949ba4;
            border-top: 1px solid #383a40;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📋 Application #{app_id} &bull; {html.escape(pos_title)}</h1>
            <div class="meta-grid">
                <div class="meta-box"><strong>Candidate:</strong> {html.escape(username)}</div>
                <div class="meta-box"><strong>Roblox Account:</strong> {html.escape(roblox_str)}</div>
                <div class="meta-box"><strong>Status:</strong> {html.escape(status)}</div>
                <div class="meta-box"><strong>Submitted:</strong> {html.escape(str(completed_at or created_at))}</div>
                <div class="meta-box"><strong>Reviewed By:</strong> {html.escape(reviewer_name or "Pending")}</div>
                <div class="meta-box"><strong>Review Note:</strong> <em>{html.escape(review_note)}</em></div>
                {ai_html}
            </div>
        </div>
        <div class="content-area">
            {"".join(qa_html)}
            {attachments_html}
        </div>
        <div class="footer">
            Echo Technologies HR Application Dossier &bull; Generated {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}
        </div>
    </div>
</body>
</html>
"""
    return full_html

