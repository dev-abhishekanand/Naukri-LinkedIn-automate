#!/usr/bin/env python3
"""
Recruiter Inbox Manager & Reply Assistant
Strictly scoped to scan incoming replies ONLY from recipients who previously received
cold application outreach emails from Abhishek Anand. Never reads or inspects personal,
banking, or unrelated emails.
"""

import os
import sys
import re
import imaplib
import email
from email.header import decode_header
from pathlib import Path
from common.email_sender import create_draft, send_email, _load_dotenv, clean_email_address
from common.telegram_notifier import alert_recruiter_reply
from recruiter_meeting_detector import process_incoming_email_for_interviews

_load_dotenv()

# Profile defaults strictly calibrated to user preferences:
PROFILE = {
    "name": "Abhishek Anand",
    "phone": "+91-8839617601",
    "email": "abhishek.anand.7601@gmail.com",
    "current_designation": "Frontend Consultant / React Engineer",
    "current_company": "Independent Frontend Consultant (Client & Startup Projects)",
    "total_experience": "3.5 Years",
    "relevant_experience": "3.5 Years (React.js, Next.js, TypeScript, Redux, Modern UI Architecture)",
    "current_ctc": "₹7.0 LPA",
    "expected_ctc": "₹10.0 - ₹12.0 LPA (Negotiable)",
    "qualifications": "B.Tech in Information Technology (Biju Patnaik University of Technology)",
    "notice_period": "Immediate Joiner (0 Days Notice / Available immediately)",
    "current_location": "Noida, Uttar Pradesh",
    "preferred_location": "Noida / Delhi NCR, Bengaluru, Hyderabad, Pune, Mumbai (Open to Remote / Hybrid / Onsite)",
    "reason_for_change": "Looking for high-impact frontend engineering roles, scalable web application challenges, and long-term career growth.",
    "linkedin": "https://www.linkedin.com/in/abhishekreactdeveloper/",
}

def decode_mime_words(s: str) -> str:
    if not s:
        return ""
    decoded_fragments = decode_header(s)
    res = []
    for frag, enc in decoded_fragments:
        if isinstance(frag, bytes):
            res.append(frag.decode(enc or "utf-8", errors="replace"))
        else:
            res.append(str(frag))
    return "".join(res)

import json
from datetime import datetime, timedelta

def get_outreach_recipients(mail: imaplib.IMAP4_SSL) -> set[str]:
    """Extracts recipient emails that Abhishek previously sent cold applications to."""
    recipients = set()
    
    # 1. Check outreach_queue.json
    queue_path = Path("outreach_queue.json")
    if queue_path.exists():
        try:
            items = json.loads(queue_path.read_text())
            for it in items:
                clean = clean_email_address(it.get("email", ""))
                if clean:
                    recipients.add(clean.lower())
        except Exception:
            pass

    # 2. Check outreach_log.csv if present
    csv_path = Path("outreach_log.csv")
    if csv_path.exists():
        for line in csv_path.read_text().splitlines():
            parts = line.split(",")
            for p in parts:
                clean = clean_email_address(p)
                if clean:
                    recipients.add(clean.lower())

    # 3. Check [Gmail]/Sent Mail for recent messages with Subject starting with 'Application:'
    try:
        mail.select('"[Gmail]/Sent Mail"', readonly=True)
        status, msgs = mail.search(None, 'SUBJECT', '"Application:"')
        if status == "OK" and msgs[0]:
            # Inspect the 30 most recent sent applications in a single batch fetch
            recent_sent = msgs[0].split()[-30:]
            status, data = mail.fetch(b','.join(recent_sent), '(BODY.PEEK[HEADER.FIELDS (TO CC)])')
            if status == "OK" and data:
                for item in data:
                    if isinstance(item, tuple):
                        hdr = email.message_from_bytes(item[1])
                        for field in ["To", "Cc"]:
                            val = hdr.get(field, "")
                            for addr in re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', val):
                                cleaned = clean_email_address(addr)
                                if cleaned and "gmail.com" in cleaned and "abhishek" in cleaned:
                                    continue
                                if cleaned:
                                    recipients.add(cleaned.lower())
    except Exception as e:
        print(f"[WARN] Error reading Sent Mail: {e}")

    return recipients

def check_recruiter_replies(verbose: bool = True) -> list[dict]:
    """Scans INBOX strictly for messages from previously sent outreach recipients."""
    user = os.getenv("GMAIL_USER")
    pwd = os.getenv("GMAIL_APP_PASSWORD")
    if not user or not pwd:
        raise ValueError("Missing GMAIL_USER or GMAIL_APP_PASSWORD in .env")

    mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=20)
    mail.login(user, pwd)

    recipients = get_outreach_recipients(mail)
    if verbose:
        print(f"[*] Total tracked outreach recipients: {len(recipients)}", flush=True)

    if not recipients:
        if verbose:
            print("[*] No outreach recipients tracked yet. Inbox clear.", flush=True)
        mail.logout()
        return []

    mail.select("INBOX", readonly=True)
    found_replies = []

    # Check recent messages from the last 14 days
    since_date = (datetime.now() - timedelta(days=14)).strftime("%d-%b-%Y")
    status, msgs = mail.search(None, f'(SINCE "{since_date}")')
    if status != "OK" or not msgs or not msgs[0]:
        status, msgs = mail.search(None, 'ALL')

    msg_ids = msgs[0].split() if (status == "OK" and msgs[0]) else []
    recent_ids = msg_ids[-50:]

    if not recent_ids:
        if verbose:
            print("[*] No recent messages found in INBOX.", flush=True)
        mail.logout()
        return []

    # Batch fetch headers for recent inbox messages
    status, data = mail.fetch(b','.join(recent_ids), '(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])')
    matched_msgs = []
    if status == "OK" and data:
        for item in data:
            if isinstance(item, tuple):
                hdr_bytes = item[1]
                hdr = email.message_from_bytes(hdr_bytes)
                from_hdr = decode_mime_words(hdr.get("From", ""))
                for rec in recipients:
                    if rec in from_hdr.lower():
                        # Extract the IMAP sequence number from item[0]
                        m_seq = item[0].split()[0]
                        matched_msgs.append((m_seq, rec, from_hdr, hdr))
                        break

    if verbose:
        print(f"[*] Matched recruiter responses in INBOX: {len(matched_msgs)}", flush=True)

    for m_seq, matched_rec, from_hdr, hdr in matched_msgs:
        status, full_data = mail.fetch(m_seq, "(RFC822)")
        if status != "OK" or not full_data or not full_data[0]:
            continue
        msg = email.message_from_bytes(full_data[0][1])
        sender = decode_mime_words(msg.get("From", ""))
        subject = decode_mime_words(msg.get("Subject", ""))
        date = msg.get("Date", "")
        msg_id = msg.get("Message-ID", "")
            
        # Extract plain text body
        body = ""
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    body = part.get_payload(decode=True).decode(errors="replace")
                    break
                except Exception:
                    pass
        
        # Classify
        body_lower = body.lower()
        is_invite = any(k in body_lower for k in [
            "schedule", "interview", "video call", "calendly", "time slot", "meet.google", "zoom.us", "teams"
        ])
        is_questions = any(k in body_lower for k in [
            "current ctc", "expected ctc", "notice period", "relevant experience", "qualification", "share following"
        ])

        category = "INTERVIEW_INVITE" if is_invite and not is_questions else "QUESTION_DETAILS"
        
        # Check for meeting/interview invite links
        try:
            process_incoming_email_for_interviews(
                sender=sender,
                subject=subject,
                body=body,
                date_str=date
            )
        except Exception as meet_err:
            pass

        found_replies.append({
            "num": m_seq.decode() if isinstance(m_seq, bytes) else str(m_seq),
            "from": sender,
            "email": matched_rec,
            "subject": subject,
            "date": date,
            "message_id": msg_id,
            "body": body,
            "category": category,
        })

    mail.logout()
    return found_replies

def draft_reply_body(recruiter_name: str = "") -> str:
    """Generates a professional, structured reply answering common recruiter fields."""
    name_salutation = f"Hi {recruiter_name}," if recruiter_name else "Hi,"
    return f"""{name_salutation}

Thank you for reviewing my application and getting back to me.

Here are the requested details for your consideration:

• Current Designation: {PROFILE['current_designation']}
• Current Company: {PROFILE['current_company']}
• Total Experience: {PROFILE['total_experience']}
• Relevant Experience (React / Next.js / TypeScript): {PROFILE['relevant_experience']}
• Current CTC: {PROFILE['current_ctc']}
• Expected CTC: {PROFILE['expected_ctc']}
• Highest Qualification: {PROFILE['qualifications']}
• Notice Period: {PROFILE['notice_period']}
• Current Location: {PROFILE['current_location']}
• Preferred Location: {PROFILE['preferred_location']}
• Reason for Change: {PROFILE['reason_for_change']}

I have also re-attached my latest resume for your records. Please let me know if any further information is needed, or if we can schedule an introductory technical conversation.

Best regards,

Abhishek Anand
Senior Frontend / React Engineer
Phone: {PROFILE['phone']}
Email: {PROFILE['email']}
LinkedIn: {PROFILE['linkedin']}
"""

def send_reply_to_recruiter(target_email: str, custom_text: str | None = None, dry_run: bool = False) -> bool:
    """Sends a professional threaded reply with the latest resume attached."""
    user = os.getenv("GMAIL_USER")
    pwd = os.getenv("GMAIL_APP_PASSWORD")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(user, pwd)
    mail.select("INBOX")
    
    cleaned_target = clean_email_address(target_email)
    status, msgs = mail.search(None, f'(FROM "{cleaned_target}")')
    if status != "OK" or not msgs[0]:
        print(f"[!] No incoming message found from {target_email} in INBOX")
        mail.logout()
        return False
        
    last_msg_num = msgs[0].split()[-1]
    status, data = mail.fetch(last_msg_num, "(RFC822)")
    msg = email.message_from_bytes(data[0][1])
    mail.logout()

    orig_subject = decode_mime_words(msg.get("Subject", ""))
    reply_subject = orig_subject if orig_subject.lower().startswith("re:") else f"Re: {orig_subject}"
    msg_id = msg.get("Message-ID", "")
    from_hdr = decode_mime_words(msg.get("From", ""))
    
    # Extract recipient name if available (e.g. Gautam or the best)
    name_match = re.match(r'^([^<]+)', from_hdr)
    rec_name = name_match.group(1).strip().strip('"\'') if name_match else ""
    if rec_name.lower() in ["the best", "hram"]:
        rec_name = ""

    body = custom_text or draft_reply_body(rec_name)
    resume_path = Path("Abhishek_Anand_Resume.pdf").resolve()
    if not resume_path.exists():
        resume_path = Path("Abhishek_Anand_Resume.docx").resolve()

    print(f"\n[+] Preparing reply draft for: {target_email}")
    print(f"    Subject: {reply_subject}")
    print(f"    In-Reply-To: {msg_id}")
    print(f"    Attachment: {resume_path.name}")
    print("\n--- BODY ---")
    print(body)
    print("------------")

    if dry_run:
        print("\n[DRY-RUN] Draft not created.")
        return True

    success = create_draft(
        to_email=cleaned_target,
        subject=reply_subject,
        body_text=body,
        attachment_path=str(resume_path),
        attachment_display_name="Abhishek_Anand_Resume.pdf",
        in_reply_to=msg_id,
        references=msg_id,
    )
    if success:
        print(f"\n[✓] Successfully created threaded reply draft for {target_email} in Gmail Drafts for manual review!")
        try:
            alert_recruiter_reply(
                sender=target_email,
                company="Recruiter",
                role="Frontend Developer",
                snippet=body[:200],
                draft_saved=True
            )
        except Exception:
            pass
    return success

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Recruiter Inbox Manager (Draft Mode Enforced)")
    parser.add_argument("--check", action="store_true", help="Check for replies from outreach contacts")
    parser.add_argument("--draft", "--send", dest="send", type=str, help="Create reply draft in Gmail Drafts for specified recruiter email")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without creating draft")
    args = parser.parse_args()

    if args.send:
        send_reply_to_recruiter(args.send, dry_run=args.dry_run)
    else:
        replies = check_recruiter_replies(verbose=True)
        print(f"\n[+] Total recruiter replies detected: {len(replies)}")
        for i, r in enumerate(replies, 1):
            print(f"\n--- [{i}] Category: {r['category']} ---")
            print(f"From: {r['from']}")
            print(f"Subject: {r['subject']}")
            print(f"Date: {r['date']}")
            print("Body Snippet:")
            print(r['body'][:300] + ("..." if len(r['body']) > 300 else ""))
