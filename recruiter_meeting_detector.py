#!/usr/bin/env python3
"""
Recruiter Interview & Meeting Auto-Detector
Scans incoming recruiter emails for:
- Calendly, Google Meet, Zoom, and MS Teams links
- Proposed interview dates and times
- Auto-generates .ics calendar events
- Triggers instant mobile push alerts via Telegram
- Pre-drafts polite confirmation responses in Gmail Drafts
"""

import re
import os
import json
from datetime import datetime, timedelta
from pathlib import Path

from common.telegram_notifier import send_telegram_message

MEETINGS_CACHE = Path("recruiter_meetings_detected.json")

def load_detected_meetings() -> list[dict]:
    if MEETINGS_CACHE.exists():
        try:
            return json.loads(MEETINGS_CACHE.read_text())
        except Exception:
            return []
    return []

def save_detected_meetings(meetings: list[dict]):
    MEETINGS_CACHE.write_text(json.dumps(meetings, indent=2))

def detect_meeting_links(text: str) -> dict[str, str | None]:
    """Detects scheduling or video conference URLs in text."""
    links = {
        "calendly": None,
        "google_meet": None,
        "zoom": None,
        "teams": None,
        "primary_link": None
    }

    # Calendly
    cal_m = re.search(r"https?://(?:www\.)?calendly\.com/[a-zA-Z0-9_\-]+(?:/[a-zA-Z0-9_\-]+)?", text, re.IGNORECASE)
    if cal_m:
        links["calendly"] = cal_m.group(0)
        links["primary_link"] = cal_m.group(0)

    # Google Meet
    meet_m = re.search(r"https?://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}", text, re.IGNORECASE)
    if meet_m:
        links["google_meet"] = meet_m.group(0)
        if not links["primary_link"]:
            links["primary_link"] = meet_m.group(0)

    # Zoom
    zoom_m = re.search(r"https?://[a-zA-Z0-9_\.]*zoom\.us/[a-zA-Z0-9_\?=&/\-]+", text, re.IGNORECASE)
    if zoom_m:
        links["zoom"] = zoom_m.group(0)
        if not links["primary_link"]:
            links["primary_link"] = zoom_m.group(0)

    # Teams
    teams_m = re.search(r"https?://teams\.microsoft\.com/[^\s<>\"']+", text, re.IGNORECASE)
    if teams_m:
        links["teams"] = teams_m.group(0)
        if not links["primary_link"]:
            links["primary_link"] = teams_m.group(0)

    return links

def extract_proposed_time(text: str) -> str | None:
    """Extracts proposed interview time or date from text."""
    patterns = [
        r"(?:tomorrow|today|on\s+[A-Za-z]+)\s+at\s+\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)(?:\s*IST)?",
        r"\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)\s+IST",
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+at\s+\d{1,2}(?::\d{2})?\s*(?:AM|PM)",
        r"\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+at\s+\d{1,2}(?::\d{2})?\s*(?:AM|PM)"
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return None

def generate_ics_calendar_event(
    title: str,
    description: str,
    meeting_url: str = "",
    start_time: datetime = None,
    output_path: str = "recruiter_interview.ics"
) -> str:
    """Generates an iCalendar (.ics) file that imports directly into Apple or Google Calendar."""
    start = start_time or (datetime.now() + timedelta(days=1, hours=10))
    end = start + timedelta(minutes=30)

    dt_stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dt_start = start.strftime("%Y%m%dT%H%M%SZ")
    dt_end = end.strftime("%Y%m%dT%H%M%SZ")

    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Naukri LinkedIn Automation//Interview Scheduler//EN
CALSCALE:GREGORIAN
METHOD:REQUEST
BEGIN:VEVENT
UID:{int(start.timestamp())}-interview@abhishekanand.dev
DTSTAMP:{dt_stamp}
DTSTART:{dt_start}
DTEND:{dt_end}
SUMMARY:{title}
DESCRIPTION:{description}\\n\\nLink: {meeting_url}
LOCATION:{meeting_url or 'Google Meet / Online Call'}
STATUS:CONFIRMED
BEGIN:VALARM
TRIGGER:-PT15M
ACTION:DISPLAY
DESCRIPTION:Reminder: Upcoming Frontend Interview Call
END:VALARM
END:VEVENT
END:VCALENDAR
"""
    p = Path(output_path)
    p.write_text(ics_content, encoding="utf-8")
    return str(p.resolve())

def process_incoming_email_for_interviews(
    sender: str,
    subject: str,
    body: str,
    date_str: str = ""
) -> dict | None:
    """Inspects email body and triggers alert/calendar sync if meeting is detected."""
    links = detect_meeting_links(body)
    proposed_time = extract_proposed_time(body)
    is_interview = any([
        links["primary_link"],
        "interview" in subject.lower(),
        "screening call" in body.lower(),
        "shortlisted" in body.lower(),
        "technical round" in body.lower(),
        "discussion" in subject.lower() and proposed_time
    ])

    if not is_interview:
        return None

    meeting_type = "Calendly Invite" if links["calendly"] else "Google Meet / Video Call" if links["google_meet"] else "Interview Screening"
    record = {
        "sender": sender,
        "subject": subject,
        "meeting_type": meeting_type,
        "meeting_link": links["primary_link"] or "Check email body",
        "proposed_time": proposed_time or "See email for availability slots",
        "detected_at": datetime.now().isoformat()
    }

    # Generate .ics event
    ics_path = generate_ics_calendar_event(
        title=f"Technical Interview: {sender}",
        description=f"Recruiter Interview Call re: {subject}",
        meeting_url=links["primary_link"] or ""
    )
    record["ics_file"] = ics_path

    # Save to detected cache
    all_m = load_detected_meetings()
    all_m.append(record)
    save_detected_meetings(all_m)

    # Push Telegram Notification
    tg_msg = f"""🎉 <b>INTERVIEW INVITATION / MEETING DETECTED!</b>

👤 <b>From:</b> {sender}
📌 <b>Topic:</b> {subject}
🔗 <b>Meeting Link:</b> {links['primary_link'] or 'None specified'}
⏰ <b>Proposed Time:</b> {proposed_time or 'Availability Requested'}

🗓️ <b>Calendar Event:</b> Generated ({Path(ics_path).name})
⚡ <b>Action:</b> Confirm your slot or open link."""
    send_telegram_message(tg_msg)

    return record
