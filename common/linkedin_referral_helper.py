"""
LinkedIn Referral Outreach Helper.
Discovers hiring team members, recruiters, and company connections on job postings.
Sends polite connection requests with tailored referral notes (strictly <= 200 chars)
or direct messages/InMails if messaging is open, offering a 1-on-1 call and resume referral.
"""

import os
import re
import json
import time
from datetime import datetime
from pathlib import Path


REFERRAL_HISTORY_FILE = "linkedin_referrals_contacted.json"
MAX_DAILY_REFERRALS = 5


def load_referral_history() -> dict:
    p = Path(REFERRAL_HISTORY_FILE)
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_referral_history(history: dict):
    p = Path(REFERRAL_HISTORY_FILE)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def is_already_contacted(profile_url: str, history: dict = None) -> bool:
    if history is None:
        history = load_referral_history()
    clean_url = clean_profile_url(profile_url)
    return clean_url in history


def clean_profile_url(url: str) -> str:
    """Normalizes LinkedIn profile URLs to prevent duplicate outreach."""
    if not url:
        return ""
    m = re.search(r"(https?://(?:www\.|in\.)?linkedin\.com/in/[a-zA-Z0-9_\-]+)", url)
    if m:
        return m.group(1).rstrip("/").lower()
    return url.split("?")[0].rstrip("/").lower()


def extract_first_name(full_name: str) -> str:
    if not full_name:
        return "there"
    # Remove titles/emojis/pronouns like (He/Him) or Ph.D.
    clean = re.sub(r"\(.*?\)", "", full_name)
    clean = re.sub(r"[\u2000-\u3300\U00010000-\U0010ffff]", "", clean)  # emojis
    # Strip common honorific prefixes
    clean = re.sub(r"^(?:mr|mrs|ms|dr|prof)\.?\s+", "", clean, flags=re.I)
    tokens = clean.strip().split()
    if tokens:
        first = re.sub(r"[^a-zA-Z]", "", tokens[0]).title()
        if len(first) >= 2:
            return first
    return "there"


def generate_connection_note(name: str, job_title: str, company: str, role_type: str = "hiring_team") -> str:
    """
    Generates a personalized connection request note strictly <= 200 characters.
    Free LinkedIn strictly enforces a 200-character limit on invitations.
    Supports both hiring team/recruiters and company colleagues/alumni.
    """
    first_name = extract_first_name(name)
    clean_title = re.sub(r"\s*\(.*?\)", "", job_title).strip()
    clean_comp = re.sub(r"\s*(?:Pvt|Ltd|Inc|LLC|Corporation|Private Limited)\.?\s*", "", company, flags=re.I).strip()

    if len(clean_title) > 24:
        clean_title = clean_title[:21] + "..."
    if len(clean_comp) > 20:
        clean_comp = clean_comp[:17] + "..."

    if role_type == "connection":
        # Candidate note for company connection / alumni / colleague
        note = (
            f"Hi {first_name}, saw you're at {clean_comp}. Exploring the {clean_title} role. "
            f"With 3.5+ yrs in React/Next.js/TS, I'd value connecting! Open for referral if my profile fits. Thanks!"
        )
        if len(note) <= 200:
            return note
        note = (
            f"Hi {first_name}, saw you're at {clean_comp}. Exploring {clean_title}. "
            f"3.5+ yrs React/Next.js/TS. Open to connect & referral if profile fits. Thanks!"
        )
        if len(note) <= 200:
            return note
        return note[:197] + "..."

    # Candidate note for hiring team / recruiter (default)
    note = (
        f"Hi {first_name}, I saw the {clean_title} role at {clean_comp}. "
        f"With 3.5+ yrs in React/Next.js/TS, I'd love to connect! "
        f"Open to a quick chat or referral if my profile fits. Thank you!"
    )
    if len(note) <= 200:
        return note

    # Fallback note option 2 (shorter)
    note = (
        f"Hi {first_name}, saw the {clean_title} role at {clean_comp}. "
        f"3.5+ yrs in React/Next.js/TS. Open to connect for a quick chat "
        f"or referral if my profile fits. Thanks!"
    )
    if len(note) <= 200:
        return note

    # Hard trim guarantee
    return note[:197] + "..."


def generate_direct_message(name: str, job_title: str, company: str, role_type: str = "hiring_team") -> str:
    """Generates a complete message for 1st-degree connections or open InMail."""
    first_name = extract_first_name(name)
    if role_type == "connection":
        return (
            f"Hi {first_name},\n\n"
            f"I hope you are doing well. I noticed you work at {company} and wanted to reach out regarding the {job_title} opening.\n\n"
            f"I'm a Frontend / React & TypeScript Engineer with 3.5+ years of experience building high-performance web applications "
            f"(React.js, Next.js, Redux, modern UI architectures).\n\n"
            f"If you feel my background aligns with the team, would you be open to submitting an internal referral for me? "
            f"I have a tailored resume ready to share and would truly appreciate your support.\n\n"
            f"Portfolio & GitHub: https://github.com/Abhishekanand11\n"
            f"LinkedIn: https://www.linkedin.com/in/abhishekreactdeveloper/\n\n"
            f"Best regards,\n"
            f"Abhishek Anand\n"
            f"+91-8839617601\n"
            f"abhishek.anand.7601@gmail.com"
        )

    return (
        f"Hi {first_name},\n\n"
        f"I noticed the {job_title} role at {company} and wanted to reach out directly. "
        f"I'm a Frontend / React & TypeScript Engineer with 3.5+ years of experience "
        f"building high-performance enterprise web applications (React.js, Next.js, Redux Toolkit, TanStack Query, modern UI architectures).\n\n"
        f"I have tailored my resume specifically for this position to match your stack requirements. I'd welcome the chance for a brief 1-on-1 chat or technical screening call.\n\n"
        f"Portfolio & GitHub: https://github.com/Abhishekanand11\n"
        f"LinkedIn: https://www.linkedin.com/in/abhishekreactdeveloper/\n\n"
        f"Best regards,\n"
        f"Abhishek Anand\n"
        f"+91-8839617601\n"
        f"abhishek.anand.7601@gmail.com"
    )


def extract_people_from_job_page(page) -> list[dict]:
    """
    Extracts hiring team members, job posters, and company connections / alumni
    visible on the current LinkedIn job page.
    """
    return page.evaluate("""
        () => {
            const people = [];
            const seenUrls = new Set();

            function addPerson(href, name, headline, roleType, actionBtn) {
                if (!href || !href.includes('/in/')) return;
                const m = href.match(/https?:\\/\\/(?:www\\.|in\\.)?linkedin\\.com\\/in\\/[a-zA-Z0-9_\\-]+/i);
                const cleanHref = m ? m[0].toLowerCase() : href.split('?')[0].toLowerCase();
                if (seenUrls.has(cleanHref)) return;
                seenUrls.add(cleanHref);
                people.push({
                    role_type: roleType,
                    name: name || 'LinkedIn Member',
                    profile_url: cleanHref,
                    headline: headline || (roleType === 'hiring_team' ? 'Recruiter / Hiring Team' : 'Employee at company'),
                    action_button: actionBtn || 'Connect'
                });
            }

            // 1. Hiring team / Job Poster card
            const posterCards = document.querySelectorAll(
                '.hirer-card__hirer-information, .jobs-poster, [data-test-hiring-member], .job-details-jobs-unified-top-card__hiring-team, [data-view-name="job-details-hiring-team"]'
            );
            posterCards.forEach(card => {
                const linkEl = card.querySelector('a[href*="/in/"]');
                const nameEl = card.querySelector('.jobs-poster__name, strong, a') || linkEl;
                const headlineEl = card.querySelector('.hirer-card__hirer-job-title, .jobs-poster__headline');
                const btn = card.querySelector('button, a.artdeco-button');

                const href = linkEl ? linkEl.href : '';
                const name = nameEl ? nameEl.innerText.trim() : '';
                const headline = headlineEl ? headlineEl.innerText.trim() : 'Recruiter / Hiring Team';
                const buttonText = btn ? btn.innerText.trim() : '';

                addPerson(href, name, headline, 'hiring_team', buttonText);
            });

            // 2. Company connections / People you may know / Alumni cards
            const sections = Array.from(document.querySelectorAll('section, div.artdeco-card, .jobs-box, [data-view-name="job-details-connections"]'));
            sections.forEach(sec => {
                const text = sec.innerText || '';
                const isConnSec = /people you may know|connections? who work|alumni|who can refer you/i.test(text);
                if (isConnSec) {
                    sec.querySelectorAll('a[href*="/in/"]').forEach(link => {
                        const name = link.innerText.trim();
                        const card = link.closest('li, div.artdeco-entity-lockup, div');
                        const headlineEl = card ? card.querySelector('.artdeco-entity-lockup__subtitle, .entity-list-item__subtitle, p') : null;
                        const headline = headlineEl ? headlineEl.innerText.trim() : 'Connection / Colleague';
                        const btn = card ? card.querySelector('button') : null;
                        const buttonText = btn ? btn.innerText.trim() : 'Connect';
                        addPerson(link.href, name, headline, 'connection', buttonText);
                    });
                }
            });

            // 3. Fallback topcard connections list links
            const connLinks = Array.from(document.querySelectorAll(
                'a[href*="/search/results/people/?currentCompany="], .jobs-unified-top-card__connections-list a[href*="/in/"]'
            ));
            connLinks.forEach(link => {
                addPerson(link.href, link.innerText.trim(), 'Employee / Connection', 'connection', 'Connect');
            });

            return people;
        }
    """)


def send_referral_outreach(
    page,
    person: dict,
    job_title: str,
    company: str,
    job_url: str = "",
    tailored_resume_path: str = "",
) -> dict:
    """
    Attempts to send a direct message (if open) or a connection request with note.
    Returns result dict with status: 'SENT_MESSAGE', 'SENT_CONNECT', 'SKIPPED', or 'FAILED'.
    """
    name = person.get("name") or "there"
    profile_url = person.get("profile_url")
    role_type = person.get("role_type", "hiring_team")
    if not profile_url:
        return {"status": "SKIPPED", "reason": "No profile URL"}

    clean_url = clean_profile_url(profile_url)
    history = load_referral_history()
    if clean_url in history:
        print(f"  [Referral] Already contacted {name} ({clean_url}). Skipping.")
        return {"status": "SKIPPED", "reason": "Already contacted"}

    print(f"\n>>> [Referral Outreach] Reaching out to {name} ({person.get('headline')}, role={role_type}) for {job_title} @ {company}...")

    # Step 1: Navigate to their profile
    try:
        page.goto(clean_url, wait_until="domcontentloaded", timeout=25000)
        time.sleep(3)
    except Exception as e:
        print(f"  [Referral] Failed to load profile {clean_url}: {e}")
        return {"status": "FAILED", "reason": f"Profile load error: {e}"}

    # Step 2: Check for direct Message button (1st degree / open InMail)
    try:
        # Check if Message button exists
        msg_button = page.locator('button.artdeco-button:has-text("Message"), button[aria-label*="Message"]').first
        if msg_button.is_visible():
            print("  [Referral] Direct Message button visible. Attempting message...")
            msg_button.click()
            time.sleep(2)

            # Check if Premium paywall / upgrade prompt popped up
            premium_upsell = page.locator('text="Try Premium", text="Upgrade to message", [data-test-premium-upsell]').first
            if premium_upsell.is_visible():
                print("  [Referral] Message requires LinkedIn Premium/InMail. Falling back to Connection Request...")
                # Close message dialog or upsell if any
                try:
                    close_btn = page.locator('button[aria-label="Dismiss"], button[data-test-modal-close-btn]').first
                    if close_btn.is_visible():
                        close_btn.click()
                        time.sleep(1)
                except Exception:
                    pass
            else:
                # Textbox is open
                textbox = page.locator('.msg-form__contenteditable, div[role="textbox"][contenteditable="true"]').first
                if textbox.is_visible():
                    msg_text = generate_direct_message(name, job_title, company, role_type=role_type)
                    textbox.click()
                    textbox.fill(msg_text)
                    time.sleep(1.5)

                    send_btn = page.locator('button.msg-form__send-button, button[type="submit"]:has-text("Send")').first
                    if send_btn.is_visible() and not send_btn.is_disabled():
                        send_btn.click()
                        time.sleep(2)
                        print(f"  ✓ Direct message sent to {name}!")
                        result = {
                            "name": name,
                            "profile_url": clean_url,
                            "job_title": job_title,
                            "company": company,
                            "type": "DIRECT_MESSAGE",
                            "status": "SENT",
                            "timestamp": datetime.now().isoformat(),
                            "message": msg_text,
                            "job_url": job_url or clean_url,
                            "tailored_resume_path": tailored_resume_path,
                        }
                        history[clean_url] = result
                        save_referral_history(history)
                        try:
                            from google_sheets_logger import append_referral_request
                            append_referral_request({
                                "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M"),
                                "company": company,
                                "role": job_title,
                                "job_url": job_url or clean_url,
                                "name": name,
                                "headline": person.get("headline", "Software Engineer / Tech Lead"),
                                "type": "DIRECT_MESSAGE",
                                "status": "SENT",
                                "message": msg_text,
                                "tailored_resume_path": tailored_resume_path,
                            })
                        except Exception as e:
                            print(f"  [Referral] Google Sheets logging notice: {e}")
                        return result
    except Exception as e:
        print(f"  [Referral] Notice during message attempt: {e}. Trying connection request...")

    # Step 3: Send Connection Request with Note
    try:
        connect_btn = page.locator('button.artdeco-button:has-text("Connect"), button[aria-label*="Invite to connect"]').first
        if not connect_btn.is_visible():
            # Check under "More actions" (...)
            more_btn = page.locator('button.artdeco-button:has-text("More"), button[aria-label="More actions"]').first
            if more_btn.is_visible():
                more_btn.click()
                time.sleep(1)
                connect_opt = page.locator('[role="menu"] div:has-text("Connect"), [role="menu"] span:has-text("Connect")').first
                if connect_opt.is_visible():
                    connect_opt.click()
                    time.sleep(1.5)

        if connect_btn.is_visible():
            connect_btn.click()
            time.sleep(1.5)

        # Check if invitation modal opened
        modal = page.locator('.artdeco-modal, [role="dialog"]').first
        if modal.is_visible():
            # Check for "Add a note" button
            add_note_btn = page.locator('button:has-text("Add a note"), button[aria-label="Add a note"]').first
            if add_note_btn.is_visible():
                add_note_btn.click()
                time.sleep(1)

            note_box = page.locator('textarea#custom-message, textarea[name="message"]').first
            if note_box.is_visible():
                note_text = generate_connection_note(name, job_title, company, role_type=role_type)
                print(f"  [Referral] Writing connection note ({len(note_text)} chars): {note_text}")
                note_box.fill(note_text)
                time.sleep(1)

            # Click Send button
            send_btn = page.locator('button:has-text("Send"), button[aria-label="Send invitation"], button[aria-label="Send now"]').first
            if send_btn.is_visible() and not send_btn.is_disabled():
                send_btn.click()
                time.sleep(2)
                print(f"  ✓ Connection request with referral note sent to {name}!")
                result = {
                    "name": name,
                    "profile_url": clean_url,
                    "job_title": job_title,
                    "company": company,
                    "type": "CONNECTION_REQUEST_WITH_NOTE",
                    "status": "SENT",
                    "timestamp": datetime.now().isoformat(),
                    "message": note_text if 'note_text' in locals() else "",
                    "job_url": job_url or clean_url,
                    "tailored_resume_path": tailored_resume_path,
                }
                history[clean_url] = result
                save_referral_history(history)
                try:
                    from google_sheets_logger import append_referral_request
                    append_referral_request({
                        "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M"),
                        "company": company,
                        "role": job_title,
                        "job_url": job_url or clean_url,
                        "name": name,
                        "headline": person.get("headline", "Software Engineer / Tech Lead"),
                        "type": "CONNECTION_REQUEST_WITH_NOTE",
                        "status": "SENT",
                        "message": note_text if 'note_text' in locals() else "",
                        "tailored_resume_path": tailored_resume_path,
                    })
                except Exception as e:
                    print(f"  [Referral] Google Sheets logging notice: {e}")
                return result
    except Exception as e:
        print(f"  [Referral] Error during connection request: {e}")
        return {"status": "FAILED", "reason": str(e)}

    return {"status": "SKIPPED", "reason": "No connect or message button accessible"}
