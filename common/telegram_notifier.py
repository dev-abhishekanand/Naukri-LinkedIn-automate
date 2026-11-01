#!/usr/bin/env python3
"""
Telegram Real-Time Notifier & Mobile Alert Dispatcher
Sends instant notifications to the candidate's phone for:
- Recruiter replies detected in inbox
- Daily application velocity & milestone summaries
- Session expiration alerts & action items
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path

from common.email_sender import _load_dotenv

_load_dotenv()

def get_telegram_config() -> tuple[str | None, str | None, bool]:
    """Retrieves Telegram bot token and chat_id from environment or profile.yaml."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    enabled = True

    # Check profile.yaml fallback
    profile_path = Path("profile.yaml")
    if profile_path.exists():
        try:
            import yaml
            with open(profile_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                tg = data.get("telegram", {})
                if not token:
                    token = tg.get("bot_token")
                if not chat_id:
                    chat_id = tg.get("chat_id")
                if "enabled" in tg:
                    enabled = bool(tg.get("enabled"))
        except Exception:
            pass

    return token, chat_id, enabled

def send_telegram_message(text: str, parse_mode: str = "HTML") -> bool:
    """Dispatches a message to the configured Telegram chat."""
    token, chat_id, enabled = get_telegram_config()
    if not enabled:
        return False

    if not token or not chat_id:
        print("[Telegram Notifier] Notice: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }

    try:
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            if res_json.get("ok"):
                return True
            else:
                print(f"[Telegram Notifier] API Error: {res_json.get('description')}")
                return False
    except Exception as e:
        print(f"[Telegram Notifier] Error sending message: {e}")
        return False

# Alias for backwards compatibility
send_telegram_alert = send_telegram_message

def alert_recruiter_reply(sender: str, company: str, role: str, snippet: str, draft_saved: bool = True):
    """Sends high-priority mobile notification when a recruiter replies."""
    status_text = "✅ <b>Draft staged in Gmail Drafts</b>" if draft_saved else "⚠️ <b>Needs Manual Review</b>"
    msg = f"""🚨 <b>RECRUITER REPLY DETECTED!</b>

👤 <b>From:</b> {sender}
🏢 <b>Company:</b> {company}
💼 <b>Role:</b> {role}

💬 <b>Snippet:</b>
<i>"{snippet[:300]}"</i>

📬 <b>Status:</b> {status_text}
⚡ Serving 0 Days Notice | 12.0 LPA Expected"""
    return send_telegram_message(msg)

def alert_daily_summary(applied_total: int, by_portal: dict, pending_sheet: int, post_published: bool):
    """Sends end-of-day summary to candidate's phone."""
    p_breakdown = ", ".join([f"{k.capitalize()}: {v}" for k, v in by_portal.items() if v > 0]) or "None"
    post_icon = "✅ Published" if post_published else "⏳ Pending"
    msg = f"""📊 <b>Daily Automation Summary</b>

🎯 <b>Jobs Applied Today:</b> {applied_total}
📌 <b>By Channel:</b> {p_breakdown}
📑 <b>Sheet Queue Remaining:</b> {pending_sheet}
📰 <b>LinkedIn Tech Post:</b> {post_icon}

Status: 🟢 <b>All Systems Healthy</b>"""
    return send_telegram_message(msg)

def alert_session_expired(portal_name: str, re_login_cmd: str):
    """Sends urgent session alert if a portal session expires."""
    msg = f"""⚠️ <b>ACTION REQUIRED: {portal_name.upper()} Session Expired</b>

The authentication session for <b>{portal_name}</b> has expired. Auto-apply is paused for this portal.

To re-authenticate, run on your machine:
<code>{re_login_cmd}</code>"""
    return send_telegram_message(msg)

if __name__ == "__main__":
    if "--test" in sys.argv:
        t, c, en = get_telegram_config()
        print(f"Telegram Config: Enabled={en}, HasToken={bool(t)}, HasChatID={bool(c)}")
        if t and c:
            success = send_telegram_message("🤖 <b>Test Alert</b> from Naukri & LinkedIn Automation Engine!")
            print(f"Test message sent: {success}")
        else:
            print("Configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in profile.yaml or .env to enable.")
