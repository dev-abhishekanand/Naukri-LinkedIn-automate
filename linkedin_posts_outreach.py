"""LinkedIn Hiring Posts Outreach: Discovers hiring posts, recovers HR email,
tailors resume, drafts high-converting cold email, and sends via Gmail with user review.

Usage:
    python linkedin_posts_outreach.py
    python linkedin_posts_outreach.py --role "React Developer"
    python linkedin_posts_outreach.py --dry-run
"""

import argparse
import csv
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

import json
from playwright.sync_api import sync_playwright
from common.browser_factory import launch_chrome_browser

from common.ats_pipeline import prepare_tailored_resume
from common.cold_email_drafter import draft_cold_email
from common.email_sender import create_draft, preprocess_text_for_emails, clean_email_address
from common.pdf_converter import convert_docx_to_pdf
from common.profile import Profile
from google_sheets_logger import (
    append_external_job,
    external_job_url_exists,
    append_linkedin_hiring_lead,
    update_hiring_lead_status,
)
from location_filter import is_india_job

SESSION_FILE = "session_linkedin.json"
OUTREACH_LOG_FILE = "outreach_log.csv"
OUTREACH_QUEUE_FILE = "outreach_queue.json"
MAX_DAILY_EMAILS = 10

IGNORE_EMAIL_DOMAINS = {
    "linkedin.com", "example.com", "yourcompany.com", "domain.com",
    "company.com", "test.com", "sample.com", "sentry.io",
}


def load_outreach_queue() -> list[dict]:
    p = Path(OUTREACH_QUEUE_FILE)
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_outreach_queue(queue: list[dict]):
    p = Path(OUTREACH_QUEUE_FILE)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)


def is_in_outreach_queue(post_url: str = "", recipient_email: str = "", queue: list[dict] = None) -> bool:
    if queue is None:
        queue = load_outreach_queue()
    clean_url = (post_url or "").strip().lower()
    clean_email = (recipient_email or "").strip().lower()
    for item in queue:
        if clean_url and item.get("post_url", "").strip().lower() == clean_url:
            return True
        if clean_email and item.get("recipient_email", "").strip().lower() == clean_email:
            return True
    return False


def log_outreach(row: dict):
    """Logs the email outreach to local CSV and Google Sheets."""
    new_file = not Path(OUTREACH_LOG_FILE).exists() or Path(OUTREACH_LOG_FILE).stat().st_size == 0
    with open(OUTREACH_LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow([
                "timestamp", "recipient_email", "author", "company", "role",
                "phone", "post_url", "resume_path", "status", "notes"
            ])
        w.writerow([
            datetime.now().isoformat(),
            row.get("recipient_email", ""),
            row.get("author", ""),
            row.get("company", ""),
            row.get("role", ""),
            row.get("phone", ""),
            row.get("post_url", ""),
            row.get("resume_path", ""),
            row.get("status", ""),
            row.get("notes", ""),
        ])

    post_url = row.get("post_url", "")
    sheet_status = row.get("sheet_status")
    if not sheet_status:
        st = row.get("status", "").lower()
        if st in ("sent", "emailed"):
            sheet_status = "EMAILED"
        elif st in ("dry_run", "draft"):
            sheet_status = "DRAFT_DRY_RUN"
        elif st in ("skipped", "skip"):
            sheet_status = "SKIPPED"
        elif st in ("failed", "send_failed"):
            sheet_status = "SEND_FAILED"
        elif st in ("obstacle_no_email", "no_email"):
            sheet_status = "PENDING_MANUAL_DM"
        else:
            sheet_status = "PENDING"

    try:
        append_external_job({
            "discovered_at": datetime.now().isoformat(),
            "platform": "linkedin_post",
            "jobId": str(row.get("post_id", "")),
            "title": row.get("role", ""),
            "company": row.get("company") or row.get("author", "LinkedIn Poster"),
            "location": row.get("location", "Remote/India"),
            "exp": "3.5+ Yrs",
            "href": post_url,
            "status": sheet_status,
            "notes": row.get("notes", f"HR Email: {row.get('recipient_email', 'N/A')} | Phone: {row.get('phone', 'N/A')}"),
            "tailored_resume_path": row.get("resume_path", ""),
        })
    except Exception as e:
        print(f"  (Google Sheets logging notice: {e})")


def extract_emails_from_text(text: str) -> list[str]:
    """Extracts valid email addresses from text, filtering platform and example addresses."""
    if not text:
        return []
    # Preprocess text to separate glued words after .com, .in, etc.
    preprocessed = preprocess_text_for_emails(text)
    # Match candidate email pattern
    raw_emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', preprocessed)
    valid_emails = []
    seen = set()

    for e in raw_emails:
        clean = clean_email_address(e)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        valid_emails.append(clean)

    return valid_emails


def extract_phone_numbers(text: str) -> list[str]:
    """Extracts Indian mobile numbers (+91...) or standard 10-digit numbers."""
    pattern = r'(?:\+?91[\s-]?)?[6789]\d{9}'
    matches = re.findall(pattern, text)
    cleaned = []
    seen = set()
    for m in matches:
        digits = re.sub(r'\D', '', m)
        if len(digits) == 10 and digits not in seen:
            seen.add(digits)
            cleaned.append(f"+91-{digits}")
        elif len(digits) == 12 and digits.startswith("91") and digits[2:] not in seen:
            seen.add(digits[2:])
            cleaned.append(f"+91-{digits[2:]}")
    return cleaned


def infer_company_name(text: str, headline: str, email: str = "") -> str:
    """Infers company name from recruiter headline, post text, or email domain."""
    # 1. Look in headline e.g. "HR at Happiest Minds", "Talent Acquisition @ Google"
    m = re.search(r'(?:at|@|with)\s+([A-Za-z0-9\s&]{2,30})', headline, re.IGNORECASE)
    if m:
        c = m.group(1).strip().rstrip("|,-")
        if c.lower() not in ("hiring", "urgent", "immediate", "looking", "present", "confidential", "stealth"):
            return c
    # 2. Look in post text e.g. "hiring for ABC Corp", "opening at XYZ"
    m_text = re.search(r'(?:at|for|with)\s+([A-Z][A-Za-z0-9\s&]{2,25}(?:Technologies|Solutions|Services|Corp|Pvt|Ltd|Inc|Labs|Software))', text)
    if m_text:
        return m_text.group(1).strip()
    # 3. Check professional email domain
    if email and "@" in email:
        domain = email.split("@")[-1].lower()
        domain_name = domain.split(".")[0]
        if domain_name not in ("gmail", "yahoo", "outlook", "hotmail", "icloud", "proton", "rediffmail"):
            return domain_name.capitalize()
    return "Hiring Organization"


def scrape_posts(page, role: str) -> list[dict]:
    """Navigates to LinkedIn content search for a role and extracts latest hiring posts."""
    # High-converting boolean syntax: targeted role + hiring/requirement keywords
    query = f'"{role}" AND ("hiring" OR "requirement")'
    url = f"https://www.linkedin.com/search/results/content/?keywords={urllib.parse.quote(query)}&sortBy=%22date_posted%22"
    print(f"\n🔍 Searching LinkedIn Posts (Sorted by Latest): '{query}'")
    page.goto(url, wait_until="commit", timeout=25000)
    time.sleep(5)

    # Click all available '... more' / 'see more' buttons to expand post contents
    try:
        page.evaluate("""
            () => {
                const moreButtons = Array.from(document.querySelectorAll("button, span")).filter(el => {
                    const t = el.innerText?.trim()?.toLowerCase();
                    return t === "… more" || t === "...more" || t === "see more";
                });
                moreButtons.forEach(b => { try { b.click(); } catch(e){} });
            }
        """)
        time.sleep(1.5)
    except Exception:
        pass

    # Extract posts using feed-post container traversal
    posts_data = page.evaluate("""
        () => {
            const feedNodes = Array.from(document.querySelectorAll("*")).filter(el => {
                return el.children.length === 0 && el.innerText?.trim() === "Feed post";
            });

            const seenUrns = new Set();
            return feedNodes.map(n => {
                let container = n.parentElement;
                for (let i = 0; i < 6; i++) {
                    if (container && container.innerText && container.innerText.length > 200 && container.getAttribute("componentkey")) {
                        break;
                    }
                    if (container && container.parentElement) container = container.parentElement;
                }
                if (!container) return null;

                const lines = container.innerText.split("\\n").map(l => l.trim()).filter(Boolean);
                const author = lines[1] || "";
                const headline = lines.find((l, idx) => idx > 1 && idx < 6 && (l.includes("|") || l.includes("Talent") || l.includes("HR") || l.includes("Engineer") || l.includes("Recruiter") || l.length > 25)) || "";

                const profileLink = container.querySelector("a[href*='/in/']")?.href || "";
                const postAnchor = container.querySelector("a[href*='/activity/'], a[href*='/feed/update/']");
                let directPostLink = postAnchor ? postAnchor.href : "";

                const urn = container.getAttribute("componentkey") || container.getAttribute("data-urn") || "";
                if (!directPostLink && urn && urn.includes("activity:")) {
                    const actId = urn.split("activity:")[1]?.split("~")[0]?.split(")")[0]?.split('"')[0];
                    if (actId) directPostLink = `https://www.linkedin.com/feed/update/urn:li:activity:${actId}/`;
                }

                if (urn && seenUrns.has(urn)) return null;
                if (urn) seenUrns.add(urn);

                const finalLink = directPostLink || profileLink || window.location.href;

                return {
                    author,
                    headline,
                    profileLink,
                    postLink: finalLink,
                    postUrl: finalLink,
                    text: container.innerText,
                    urn
                };
            }).filter(Boolean);
        }
    """)

    print(f"   Found {len(posts_data)} recent posts for '{role}'")
    return posts_data


def gather_and_queue_posts(target_role_filter: str | None = None, max_posts: int = 10, dry_run: bool = False) -> int:
    """
    Phase 1: Gathers fresh recruiter hiring posts, extracts HR emails,
    generates tailored PDF resumes, drafts cold emails, and saves them
    into outreach_queue.json and Google Sheets 'LinkedIn Hirings & Leads' tab with status QUEUED.
    """
    profile = Profile.load()
    if not Path(SESSION_FILE).exists():
        raise SystemExit(f"ERROR: {SESSION_FILE} not found. Run 'python login_capture.py linkedin' first.")

    roles = [target_role_filter] if target_role_filter else profile.target_roles
    queue = load_outreach_queue()
    queued_count = 0

    print("=" * 70)
    print("PHASE 1: GATHERING & QUEUEING RECRUITER HIRING POSTS")
    print(f"Target Roles: {roles}")
    print(f"Max Leads to Queue: {max_posts}")
    print("=" * 70)

    with sync_playwright() as p:
        browser_mode = profile.data.get("browser_mode", "minimized")
        browser = launch_chrome_browser(p, browser_mode=browser_mode, slow_mo=150)
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        for role in roles:
            if queued_count >= max_posts:
                break

            posts = scrape_posts(page, role)

            for post in posts:
                if queued_count >= max_posts:
                    break

                text = post.get("text", "")
                author = post.get("author", "Hiring Team")
                headline = post.get("headline", "")
                post_url = post.get("postUrl") or post.get("postLink") or post.get("profileLink") or ""
                post_id = re.sub(r'\D', '', post.get("urn", ""))[-10:] or str(int(time.time()))

                # Enforce India location
                if not is_india_job(title=role, notes=text, company=author, url=post_url):
                    print(f"⏭️ Skipping non-Indian hiring post ({author} / {role})")
                    continue

                # Check if already in queue or logged
                if is_in_outreach_queue(post_url=post_url, queue=queue):
                    print(f"⏭️ Skipping: Post already in outreach queue ({post_url})")
                    continue

                if post_url and external_job_url_exists(post_url):
                    print(f"⏭️ Skipping: Post already logged in tracker ({post_url})")
                    continue

                emails = extract_emails_from_text(text)
                phones = extract_phone_numbers(text)
                phone_str = phones[0] if phones else "Not mentioned"

                if not emails:
                    company = infer_company_name(text=text, headline=headline, email="")
                    log_outreach({
                        "post_id": post_id,
                        "recipient_email": "N/A (No email in post)",
                        "author": author,
                        "company": company,
                        "role": role,
                        "phone": phone_str,
                        "post_url": post_url,
                        "resume_path": "Abhishek_Anand_Resume.pdf",
                        "status": "obstacle_no_email",
                        "sheet_status": "PENDING_MANUAL_DM",
                        "notes": f"Obstacle: No direct email found in post. Manual LinkedIn DM needed with {author} ({headline})",
                    })
                    continue

                recipient_email = emails[0]
                if is_in_outreach_queue(recipient_email=recipient_email, queue=queue):
                    print(f"⏭️ Skipping: Recipient email already in outreach queue ({recipient_email})")
                    continue

                company = infer_company_name(text=text, headline=headline, email=recipient_email)

                print("\n" + "=" * 70)
                print(f"🎯 NEW QUALIFIED HIRING LEAD: {role} @ {company}")
                print(f"Author:     {author} ({headline})")
                print(f"HR Email:   {recipient_email}")
                print(f"Post URL:   {post_url}")
                print("=" * 70)

                # Tailor resume
                role_slug = re.sub(r'[^A-Za-z0-9]+', '_', role).strip('_')
                output_docx_path = f"generated/Abhishek_Anand_{role_slug}_{post_id}.docx"
                clean_resume_display_name = f"Abhishek_Anand_{role_slug}.pdf"
                try:
                    prep = prepare_tailored_resume(
                        job_description=text,
                        master_resume_path="Abhishek_Anand_Resume.docx",
                        output_path=output_docx_path,
                    )
                    docx_path = prep["tailored_resume_path"]
                    pdf_path = convert_docx_to_pdf(docx_path)
                    resume_path = pdf_path
                except Exception as e:
                    print(f"   ATS preparation note: {e}. Using Master PDF Resume.")
                    if not Path("Abhishek_Anand_Resume.pdf").exists():
                        convert_docx_to_pdf("Abhishek_Anand_Resume.docx")
                    resume_path = "Abhishek_Anand_Resume.pdf"
                    clean_resume_display_name = "Abhishek_Anand_Resume.pdf"

                # Draft personalized cold email
                draft = draft_cold_email(
                    post_text=text,
                    author=author,
                    company=company,
                    role=role,
                )
                subject = draft["subject"]
                body = draft["body"]

                lead_item = {
                    "post_id": post_id,
                    "recipient_email": recipient_email,
                    "author": author,
                    "company": company,
                    "role": role,
                    "phone": phone_str,
                    "post_url": post_url,
                    "resume_path": resume_path,
                    "display_resume_name": clean_resume_display_name,
                    "subject": subject,
                    "body": body,
                    "status": "QUEUED",
                    "queued_at": datetime.now().isoformat(),
                }

                if not dry_run:
                    # Automatically compose draft into Abhishek's Gmail Drafts folder
                    draft_success = False
                    try:
                        create_draft(
                            to_email=recipient_email,
                            subject=subject,
                            body_text=body,
                            attachment_path=resume_path,
                            attachment_display_name=clean_resume_display_name,
                        )
                        lead_item["status"] = "DRAFTED"
                        lead_item["drafted_at"] = datetime.now().isoformat()
                        draft_success = True
                        print(f"✓ Composed and saved draft in Gmail Drafts folder for {recipient_email} with tailored resume!")
                    except Exception as e:
                        print(f"⚠️ Could not create immediate Gmail draft ({e}). Kept in queue.")

                    queue.append(lead_item)
                    save_outreach_queue(queue)
                    queued_count += 1

                    status_label = "DRAFTED" if draft_success else "QUEUED"
                    note_msg = "Draft created in Gmail Drafts for manual review" if draft_success else "Queued for drafting"

                    # Log to Google Sheets LinkedIn Hirings & Leads tab
                    append_linkedin_hiring_lead({
                        "discovered_at": datetime.now().strftime("%d-%m-%Y %H:%M"),
                        "role": role,
                        "author": author,
                        "headline": headline or company,
                        "recipient_email": recipient_email,
                        "phone": phone_str,
                        "post_url": post_url,
                        "status": status_label,
                        "notes": f"{note_msg} ({subject})",
                        "content_preview": text[:250],
                    })
                    # Log locally
                    log_outreach({
                        "post_id": post_id,
                        "recipient_email": recipient_email,
                        "author": author,
                        "company": company,
                        "role": role,
                        "phone": phone_str,
                        "post_url": post_url,
                        "resume_path": resume_path,
                        "status": status_label.lower(),
                        "sheet_status": status_label,
                        "notes": f"{note_msg} ({company})",
                    })

        browser.close()

    print(f"\n🏁 Finished Phase 1. Total leads processed & drafted: {queued_count}")
    return queued_count


def dispatch_queued_emails(max_emails: int = 2) -> int:
    """
    Drafts queued cold emails into Abhishek's Gmail Drafts folder ([Gmail]/Drafts)
    with tailored PDF resumes attached.
    STRICT POLICY: Never sends emails directly to recruiters or HR contacts.
    Composes and places emails into Gmail Drafts for Abhishek's manual review.
    """
    queue = load_outreach_queue()
    queued_items = [item for item in queue if item.get("status") in ("QUEUED", "PENDING")]

    if not queued_items:
        print("[Drafts Manager] All queued cold emails are already drafted in Gmail Drafts folder. Queue is clear.")
        return 0

    print("=" * 70)
    print(f"📝 COMPOSING COLD EMAILS INTO GMAIL DRAFTS FOLDER (Up to {min(len(queued_items), max_emails)})")
    print(f"Total pending in queue: {len(queued_items)}")
    print("Policy: Drafts only. Never sends directly to recruiters.")
    print("=" * 70)

    drafted_count = 0
    for item in queued_items:
        if drafted_count >= max_emails:
            break

        recipient = item.get("recipient_email")
        subject = item.get("subject")
        body = item.get("body")
        resume_path = item.get("resume_path")
        display_name = item.get("display_resume_name", "Abhishek_Anand_Resume.pdf")
        author = item.get("author", "Recruiter")
        company = item.get("company", "Company")
        post_url = item.get("post_url", "")
        post_id = item.get("post_id", "")

        print(f"\n📝 Composing Gmail draft for {recipient} ({author} @ {company})...")
        print(f"   Subject: {subject}")
        print(f"   Attach:  {display_name} ({resume_path})")

        try:
            create_draft(
                to_email=recipient,
                subject=subject,
                body_text=body,
                attachment_path=resume_path,
                attachment_display_name=display_name,
            )
            item["status"] = "DRAFTED"
            item["drafted_at"] = datetime.now().isoformat()
            drafted_count += 1
            print(f"   ✓ Draft successfully created in Gmail Drafts folder for {recipient}!")

            # Update Google Sheets status to DRAFTED
            update_hiring_lead_status(
                identifier=recipient,
                new_status="DRAFTED",
                notes=f"Draft created in Gmail Drafts on {datetime.now().strftime('%d-%m-%Y %H:%M')}. Awaiting Abhishek's review.",
            )
            # Update local log
            log_outreach({
                "post_id": post_id,
                "recipient_email": recipient,
                "author": author,
                "company": company,
                "role": item.get("role", "React Developer"),
                "phone": item.get("phone", ""),
                "post_url": post_url,
                "resume_path": resume_path,
                "status": "drafted",
                "sheet_status": "DRAFTED",
                "notes": f"Draft created in Gmail Drafts for manual review ({company})",
            })

            # Save queue after each draft
            save_outreach_queue(queue)

            if drafted_count < max_emails:
                time.sleep(2)

        except Exception as e:
            print(f"   ❌ Error creating draft for {recipient}: {e}")
            item["status"] = "DRAFT_FAILED"
            item["error"] = str(e)
            save_outreach_queue(queue)
            update_hiring_lead_status(
                identifier=recipient,
                new_status="DRAFT_FAILED",
                notes=f"Draft error: {e}",
            )

    print(f"\n🏁 Finished Drafting Batch. Total drafts created: {drafted_count}")
    return drafted_count


def run_outreach(
    target_role_filter: str | None = None,
    dry_run: bool = False,
    max_emails: int = MAX_DAILY_EMAILS,
    gather_only: bool = False,
    dispatch_only: bool = False,
    dispatch_count: int = 2,
    unattended: bool = False,
):
    """Main orchestrator for LinkedIn post scraping, resume tailoring, and email outreach."""
    if gather_only:
        gather_and_queue_posts(target_role_filter=target_role_filter, max_posts=max_emails, dry_run=dry_run)
        return

    if dispatch_only:
        dispatch_queued_emails(max_emails=dispatch_count)
        return

    if unattended or os.environ.get("UNATTENDED") == "1":
        print("Running in UNATTENDED mode: gathering fresh leads, then dispatching queued batch.")
        gather_and_queue_posts(target_role_filter=target_role_filter, max_posts=max_emails, dry_run=dry_run)
        dispatch_queued_emails(max_emails=dispatch_count)
        return

    # Interactive manual mode
    profile = Profile.load()
    if not Path(SESSION_FILE).exists():
        raise SystemExit(f"ERROR: {SESSION_FILE} not found. Run 'python login_capture.py linkedin' first.")

    roles = [target_role_filter] if target_role_filter else profile.target_roles
    sent_count = 0

    print("=" * 70)
    print("🚀 LinkedIn Hiring Posts Outreach Pipeline (Interactive Mode)")
    print(f"Target Roles: {', '.join(roles)}")
    print(f"Daily Cap: {max_emails} emails")
    print("=" * 70)

    with sync_playwright() as p:
        browser_mode = profile.data.get("browser_mode", "minimized")
        browser = launch_chrome_browser(p, browser_mode=browser_mode, slow_mo=150)
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        for role in roles:
            if sent_count >= max_emails:
                break

            posts = scrape_posts(page, role)

            for post in posts:
                if sent_count >= max_emails:
                    break

                text = post.get("text", "")
                author = post.get("author", "Hiring Team")
                headline = post.get("headline", "")
                post_url = post.get("postUrl") or post.get("postLink") or post.get("profileLink") or ""
                post_id = re.sub(r'\D', '', post.get("urn", ""))[-10:] or str(int(time.time()))

                if not is_india_job(title=role, notes=text, company=author, url=post_url):
                    continue

                if post_url and external_job_url_exists(post_url):
                    continue

                emails = extract_emails_from_text(text)
                phones = extract_phone_numbers(text)
                phone_str = phones[0] if phones else "Not mentioned"

                if not emails:
                    continue

                recipient_email = emails[0]
                company = infer_company_name(text=text, headline=headline, email=recipient_email)

                # Tailor resume
                role_slug = re.sub(r'[^A-Za-z0-9]+', '_', role).strip('_')
                output_docx_path = f"generated/Abhishek_Anand_{role_slug}_{post_id}.docx"
                clean_resume_display_name = f"Abhishek_Anand_{role_slug}.pdf"
                try:
                    prep = prepare_tailored_resume(job_description=text, output_path=output_docx_path)
                    resume_path = convert_docx_to_pdf(prep["tailored_resume_path"])
                except Exception:
                    resume_path = "Abhishek_Anand_Resume.pdf"
                    clean_resume_display_name = "Abhishek_Anand_Resume.pdf"

                draft = draft_cold_email(post_text=text, author=author, company=company, role=role)
                subject = draft["subject"]
                body = draft["body"]

                print("\n" + "#" * 70)
                print(f"📧 COLD OUTREACH EMAIL PREVIEW")
                print(f"To:       {recipient_email}")
                print(f"Subject:  {subject}")
                print(f"Attach:   {clean_resume_display_name} ({resume_path})")
                print("-" * 70)
                print(body)
                print("#" * 70)

                choice = input("\nSave draft to your Gmail Drafts folder? [Y]es / [s]kip / [q]uit: ").strip().lower()
                if choice in ("y", "yes", ""):
                    try:
                        create_draft(to_email=recipient_email, subject=subject, body_text=body, attachment_path=resume_path, attachment_display_name=clean_resume_display_name)
                        sent_count += 1
                        print(f"🎉 Email draft saved to your Gmail Drafts folder for {recipient_email}!")
                        log_outreach({"post_id": post_id, "recipient_email": recipient_email, "author": author, "company": company, "role": role, "phone": phone_str, "post_url": post_url, "resume_path": resume_path, "status": "drafted", "sheet_status": "DRAFTED", "notes": "Draft saved in Gmail Drafts for manual review"})
                    except Exception as e:
                        print(f"❌ Draft error: {e}")
                elif choice in ("q", "quit"):
                    browser.close()
                    return

        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LinkedIn Hiring Posts Cold Outreach Drafter (Draft Mode Enforced)")
    parser.add_argument("--role", type=str, default=None, help="Specific role to search for (e.g. 'React Developer')")
    parser.add_argument("--dry-run", action="store_true", help="Scrape and prepare leads without saving drafts")
    parser.add_argument("--max-emails", type=int, default=MAX_DAILY_EMAILS, help="Max leads to gather and draft")
    parser.add_argument("--gather", action="store_true", help="Phase 1: Only gather & compose drafts for fresh leads")
    parser.add_argument("--dispatch", action="store_true", help="Phase 2: Process queued items into Gmail drafts")
    parser.add_argument("--dispatch-count", type=int, default=2, help="Number of queued emails to draft in this batch")
    parser.add_argument("--unattended", action="store_true", help="Run completely unattended")
    args = parser.parse_args()

    run_outreach(
        target_role_filter=args.role,
        dry_run=args.dry_run,
        max_emails=args.max_emails,
        gather_only=args.gather,
        dispatch_only=args.dispatch,
        dispatch_count=args.dispatch_count,
        unattended=args.unattended,
    )
