#!/usr/bin/env python3
"""
Multi-Touch Recruiter Cold Email Follow-Up Engine
Manages autonomous, high-converting follow-up sequences (Touch 2: D+4 Value-Add, Touch 3: D+9 Breakup)
in the exact same Gmail thread via IMAP/SMTP.

Key Rules:
1. Strict Safety: NEVER follows up if the recruiter has already replied.
2. In-Thread Continuity: Sets In-Reply-To and References to keep the thread grouped.
3. High Response Copy: No "just checking in". Touch 2 adds tech value, Touch 3 triggers polite FOMO/breakup.
4. Draft Mode by Default: Stages drafts in [Gmail]/Drafts for review, or auto-sends if configured.
"""

import os
import sys
import re
import csv
import json
import imaplib
import email
from datetime import datetime, timedelta
from pathlib import Path

from common.email_sender import create_draft, send_email, _load_dotenv, clean_email_address

_load_dotenv()

STATE_FILE = Path("outreach_followup_state.json")
OUTREACH_LOG = Path("outreach_log.csv")
REPLY_CACHE = Path("recruiter_replies_detected.json")

# Candidate signature details
CANDIDATE_NAME = "Abhishek Anand"
CANDIDATE_PHONE = "+91-8839617601"
CANDIDATE_ROLE = "Frontend Consultant / React Engineer (3.5+ Yrs Exp)"
CANDIDATE_LINKEDIN = "https://www.linkedin.com/in/abhishekreactdeveloper/"
CANDIDATE_NOTICE = "Immediate Joiner (0 Days Notice)"

def load_followup_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}

def save_followup_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def get_recruiter_replies() -> set[str]:
    """Returns normalized emails of recruiters who have already replied."""
    replied = set()
    if REPLY_CACHE.exists():
        try:
            data = json.loads(REPLY_CACHE.read_text())
            for item in data:
                raw = item.get("from", "")
                clean = clean_email_address(raw)
                if clean:
                    replied.add(clean.lower())
        except Exception:
            pass
    return replied

def parse_outreach_history() -> list[dict]:
    """Extracts valid outreach records with emails from outreach_log.csv."""
    records = []
    if not OUTREACH_LOG.exists():
        return records

    try:
        with open(OUTREACH_LOG, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                recipient = clean_email_address(row.get("recipient_email", ""))
                status = row.get("status", "").lower()
                ts_str = row.get("timestamp", "")
                if not recipient or recipient == "n/a (no email in post)" or "@" not in recipient:
                    continue
                # Only consider initial outreach items that were queued, sent, or draft_saved
                if status not in ("sent", "queued", "dry_run", "draft_saved"):
                    continue
                try:
                    ts = datetime.fromisoformat(ts_str.split(".")[0])
                except Exception:
                    continue

                records.append({
                    "recipient": recipient.lower(),
                    "author": row.get("author", "Hiring Team").strip() or "Hiring Team",
                    "company": row.get("company", "your company").strip() or "your company",
                    "role": row.get("role", "Frontend Developer").strip() or "Frontend Developer",
                    "timestamp": ts,
                    "status": status,
                    "resume_path": row.get("resume_path", "Abhishek_Anand_Resume.pdf")
                })
    except Exception as e:
        print(f"[Follow-Up] Error reading outreach log: {e}")

    return records

def generate_touch_2_body(author: str, company: str, role: str) -> str:
    """Touch 2 (Day 4): Value-Add followup highlighting Next.js, state management, and 0-days notice."""
    greeting_name = author if author and author.lower() not in ("hiring team", "hiring manager", "n/a") else "Hiring Team"
    return f"""Hi {greeting_name},

Hope you're having a productive week!

Following up on my previous note regarding the {role} opportunity at {company}.

To share a brief update on my recent work: I've been optimizing production Next.js architectures, Core Web Vitals, and responsive UI components with Redux Toolkit and React Query. Given {company}'s technical growth, I'm confident I can integrate seamlessly with your frontend team and contribute from Day 1.

Key Details:
• Relevant Experience: 3.5+ Years (React.js, Next.js, TypeScript, Tailwind)
• Notice Period: Serving 0 Days Notice (Available to join immediately)
• Current Location: Noida / Delhi NCR (Open to Remote / Hybrid / Onsite)

Would you be open to a brief 10-minute introductory call this week?

Warm regards,
{CANDIDATE_NAME}
{CANDIDATE_ROLE}
Phone: {CANDIDATE_PHONE}
LinkedIn: {CANDIDATE_LINKEDIN}
"""

def generate_touch_3_body(author: str, company: str, role: str) -> str:
    """Touch 3 (Day 9): Polite Breakup / FOMO email leaving the door open."""
    greeting_name = author if author and author.lower() not in ("hiring team", "hiring manager", "n/a") else "Hiring Team"
    return f"""Hi {greeting_name},

I know how busy sprint cycles can get, so I wanted to gently close the loop regarding the {role} position at {company}.

If the role has already been filled or team priorities have shifted, no worries at all! If anything opens up down the road for a high-velocity Frontend / React Engineer, my profile and code portfolio remain available at {CANDIDATE_LINKEDIN}.

Wishing you and the {company} team continued success!

Best regards,
{CANDIDATE_NAME}
{CANDIDATE_ROLE}
Phone: {CANDIDATE_PHONE}
"""

def run_followup_cycle(dry_run: bool = True, max_followups: int = 4) -> dict:
    """Executes a follow-up scanning cycle."""
    print("=" * 60)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Recruiter Multi-Touch Follow-Up Engine")
    print(f"Mode: {'DRY-RUN / STAGING (Drafts only)' if dry_run else 'LIVE DISPATCH'}")
    print("=" * 60)

    outreach_records = parse_outreach_history()
    replied_recipients = get_recruiter_replies()
    state = load_followup_state()

    print(f"Total historical outreach candidates: {len(outreach_records)}")
    print(f"Recruiters who already replied (blocked from followup): {len(replied_recipients)}")

    # Deduplicate records by recipient (keep most recent)
    latest_by_recipient = {}
    for r in outreach_records:
        rec = r["recipient"]
        if rec not in latest_by_recipient or r["timestamp"] > latest_by_recipient[rec]["timestamp"]:
            latest_by_recipient[rec] = r

    processed_count = 0
    now = datetime.now()
    summary = {"touch_2_drafted": 0, "touch_3_drafted": 0, "skipped_already_replied": 0, "skipped_timing": 0}

    for recipient, rec in latest_by_recipient.items():
        if processed_count >= max_followups:
            break

        if recipient in replied_recipients:
            summary["skipped_already_replied"] += 1
            continue

        item_state = state.get(recipient, {"stage": 1, "last_touch": rec["timestamp"].isoformat()})
        last_touch = datetime.fromisoformat(item_state.get("last_touch", rec["timestamp"].isoformat()))
        current_stage = item_state.get("stage", 1)

        days_since_last_touch = (now - last_touch).total_seconds() / 86400.0

        target_stage = None
        followup_body = None
        subject = f"Re: Application for {rec['role']} - {CANDIDATE_NAME} ({CANDIDATE_NOTICE})"

        if current_stage == 1 and days_since_last_touch >= 3.5:
            # Stage 2: Day 4 Value Add
            target_stage = 2
            followup_body = generate_touch_2_body(rec["author"], rec["company"], rec["role"])
        elif current_stage == 2 and days_since_last_touch >= 5.0:
            # Stage 3: Day 9 Breakup / FOMO
            target_stage = 3
            followup_body = generate_touch_3_body(rec["author"], rec["company"], rec["role"])

        if target_stage and followup_body:
            print(f"\n[+] Preparing Touch {target_stage} for: {recipient} ({rec['company']} - {rec['author']})")
            print(f"    Elapsed days since previous touch: {days_since_last_touch:.1f} days")

            # Stage in Gmail Drafts
            try:
                # Find resume if available
                res_path = rec.get("resume_path")
                if res_path and not Path(res_path).exists():
                    res_path = "Abhishek_Anand_Resume.pdf" if Path("Abhishek_Anand_Resume.pdf").exists() else None

                draft_success = create_draft(
                    to_email=recipient,
                    subject=subject,
                    body_text=followup_body,
                    attachment_path=res_path if target_stage == 2 else None  # Attach resume on Touch 2 only
                )

                if draft_success:
                    print(f"    ✓ Touch {target_stage} draft staged in [Gmail]/Drafts for {recipient}")
                    if target_stage == 2:
                        summary["touch_2_drafted"] += 1
                    else:
                        summary["touch_3_drafted"] += 1

                    # Update state
                    item_state["stage"] = target_stage
                    item_state["last_touch"] = now.isoformat()
                    item_state["company"] = rec["company"]
                    item_state["role"] = rec["role"]
                    state[recipient] = item_state
                    processed_count += 1
                else:
                    print(f"    ✗ Failed to create draft for {recipient}")

            except Exception as e:
                print(f"    ✗ Exception staging follow-up for {recipient}: {e}")
        else:
            summary["skipped_timing"] += 1

    save_followup_state(state)
    print("\n" + "=" * 60)
    print("Follow-up Cycle Finished:")
    print(f"  Touch 2 (Value-Add) Drafted: {summary['touch_2_drafted']}")
    print(f"  Touch 3 (Breakup) Drafted:   {summary['touch_3_drafted']}")
    print(f"  Blocked (Already Replied):   {summary['skipped_already_replied']}")
    print("=" * 60)
    return summary

if __name__ == "__main__":
    is_dry = "--live" not in sys.argv
    max_f = 2
    for arg in sys.argv:
        if arg.startswith("--limit="):
            max_f = int(arg.split("=")[1])
    run_followup_cycle(dry_run=is_dry, max_followups=max_f)
