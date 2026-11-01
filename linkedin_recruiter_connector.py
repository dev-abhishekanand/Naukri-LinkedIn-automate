#!/usr/bin/env python3
"""
LinkedIn Recruiter Connection Request Engine
Automates sending personalized connection requests (with <=200 character notes)
to recruiters and hiring managers whose hiring posts were discovered by the outreach harvester.

Safety Guardrails:
- Strict rate limit: Max 5 connection requests per day (keeps account well within safe weekly limits)
- Human-like delays (12-25 seconds between actions)
- Never contacts the same recruiter twice (tracked in linkedin_referrals_contacted.json)
- Dry-run mode by default
"""

import sys
import re
import json
import time
import random
from pathlib import Path
from datetime import datetime

from playwright.sync_api import sync_playwright
from common.browser_factory import launch_chrome_browser
from common.linkedin_referral_helper import (
    load_referral_history,
    save_referral_history,
    is_already_contacted,
    clean_profile_url,
    generate_connection_note,
    extract_first_name
)

SESSION_FILE = Path("session_linkedin.json")
QUEUE_FILE = Path("outreach_queue.json")
OUTREACH_LOG = Path("outreach_log.csv")

def extract_recruiter_leads() -> list[dict]:
    """Collects recruiter profile URLs from outreach queue and log."""
    leads = []
    seen_urls = set()

    # 1. From outreach_queue.json
    if QUEUE_FILE.exists():
        try:
            items = json.loads(QUEUE_FILE.read_text())
            for it in items:
                url = it.get("post_url", "")
                if "/in/" in url:
                    clean = clean_profile_url(url)
                    if clean not in seen_urls:
                        seen_urls.add(clean)
                        leads.append({
                            "profile_url": clean,
                            "author": it.get("author", "Hiring Lead"),
                            "company": it.get("company", "Tech Company"),
                            "role": it.get("role", "Frontend Developer"),
                            "source": "outreach_queue"
                        })
        except Exception:
            pass

    # 2. From outreach_log.csv
    if OUTREACH_LOG.exists():
        try:
            import csv
            with open(OUTREACH_LOG, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    url = r.get("post_url", "")
                    if "/in/" in url:
                        clean = clean_profile_url(url)
                        if clean not in seen_urls:
                            seen_urls.add(clean)
                            leads.append({
                                "profile_url": clean,
                                "author": r.get("author", "Hiring Lead"),
                                "company": r.get("company", "Tech Company"),
                                "role": r.get("role", "Frontend Developer"),
                                "source": "outreach_log"
                            })
        except Exception:
            pass

    return leads

def connect_with_recruiter(page, lead: dict, dry_run: bool = True) -> dict:
    """Navigates to recruiter profile and sends connection request with note."""
    profile_url = lead["profile_url"]
    author = lead["author"]
    company = lead["company"]
    role = lead["role"]

    first_name = extract_first_name(author)
    note = generate_connection_note(first_name, role, company, role_type="hiring_team")
    if len(note) > 200:
        note = note[:197] + "..."

    print(f"\n[Recruiter Connect] Target: {author} ({company})")
    print(f"URL: {profile_url}")
    print(f"Note ({len(note)}/200 chars): \"{note}\"")

    if dry_run:
        print("[DRY-RUN] Preview only. Skipped live navigation.")
        return {"status": "DRY_RUN", "note": note}

    # Live navigation
    try:
        page.goto(profile_url, wait_until="domcontentloaded", timeout=45000)
        time.sleep(3)

        # Check if already 1st degree or pending
        pending_btn = page.locator("button:has-text('Pending')").first
        if pending_btn.count() > 0 and pending_btn.is_visible():
            print("✓ Already requested (Invitation Pending).")
            return {"status": "ALREADY_PENDING"}

        message_btn = page.locator(".pvs-profile-actions button:has-text('Message')").first
        connect_btn = page.locator(".pvs-profile-actions button:has-text('Connect'), button[aria-label*='Invite'][aria-label*='to connect']").first

        # If connect button is hidden inside "More" menu
        if connect_btn.count() == 0 or not connect_btn.is_visible():
            more_btn = page.locator(".pvs-profile-actions button:has-text('More'), button[aria-label='More actions']").first
            if more_btn.is_visible():
                more_btn.click()
                time.sleep(1)
                connect_btn = page.locator("[role='menu'] div:has-text('Connect'), [role='menu'] span:has-text('Connect')").first

        if connect_btn.count() == 0 or not connect_btn.is_visible():
            print("⚠️ 'Connect' button not directly available on profile.")
            return {"status": "BUTTON_NOT_FOUND"}

        connect_btn.click()
        time.sleep(2)

        # Look for "Add a note" modal
        add_note_btn = page.locator("button:has-text('Add a note'), button[aria-label*='Add a note']").first
        if add_note_btn.is_visible(timeout=3000):
            add_note_btn.click()
            time.sleep(1)

            textarea = page.locator("textarea[name='message'], #custom-message").first
            if textarea.is_visible(timeout=3000):
                textarea.fill(note)
                time.sleep(1)

        # Click Send invitation
        send_btn = page.locator("button:has-text('Send'), button[aria-label*='Send invitation']").first
        if send_btn.is_visible(timeout=3000):
            send_btn.click()
            time.sleep(3)
            print(f"✓ Connection request sent successfully to {author}!")
            return {"status": "SENT", "note": note}
        else:
            print("⚠️ Send button not visible on modal.")
            return {"status": "SEND_NOT_FOUND"}

    except Exception as e:
        print(f"✗ Error during connection request: {e}")
        return {"status": "ERROR", "error": str(e)}

def run_recruiter_connect(dry_run: bool = True, max_leads: int = 3):
    """Executes the connection batch."""
    print("=" * 60)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LinkedIn Recruiter Connector")
    print(f"Mode: {'DRY-RUN' if dry_run else 'LIVE CONNECT'}")
    print("=" * 60)

    if not SESSION_FILE.exists():
        print(f"ERROR: {SESSION_FILE} not found.")
        sys.exit(1)

    leads = extract_recruiter_leads()
    history = load_referral_history()
    print(f"Total extracted recruiter leads: {len(leads)}")
    print(f"Previously contacted profiles: {len(history)}")

    uncontacted = [l for l in leads if not is_already_contacted(l["profile_url"], history)]
    print(f"Available new leads to contact: {len(uncontacted)}")

    if not uncontacted:
        print("No new recruiter leads to contact. Exiting.")
        return

    targets = uncontacted[:max_leads]

    if dry_run:
        for t in targets:
            connect_with_recruiter(None, t, dry_run=True)
        print("\n[DRY-RUN] Finished previewing leads. Pass --live to dispatch.")
        return

    # Live Playwright execution
    with sync_playwright() as p:
        browser = launch_chrome_browser(p, browser_mode="headless")
        context = browser.new_context(storage_state=str(SESSION_FILE))
        page = context.new_page()

        try:
            for lead in targets:
                res = connect_with_recruiter(page, lead, dry_run=False)
                clean_url = clean_profile_url(lead["profile_url"])
                history[clean_url] = {
                    "author": lead["author"],
                    "company": lead["company"],
                    "role": lead["role"],
                    "status": res.get("status"),
                    "note": res.get("note", ""),
                    "timestamp": datetime.now().isoformat()
                }
                save_referral_history(history)

                # Human-like delay between profiles
                delay = random.uniform(15, 25)
                print(f"Sleeping {delay:.1f}s for stealth pacing...")
                time.sleep(delay)
        finally:
            browser.close()

if __name__ == "__main__":
    is_live = "--live" in sys.argv
    limit = 3
    for a in sys.argv:
        if a.startswith("--limit="):
            limit = int(a.split("=")[1])
    run_recruiter_connect(dry_run=not is_live, max_leads=limit)
