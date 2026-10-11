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

from playwright.sync_api import sync_playwright

from common.ats_pipeline import prepare_tailored_resume
from common.cold_email_drafter import draft_cold_email
from common.email_sender import send_email
from common.pdf_converter import convert_docx_to_pdf
from common.profile import Profile
from google_sheets_logger import append_external_job, external_job_url_exists

SESSION_FILE = "session_linkedin.json"
OUTREACH_LOG_FILE = "outreach_log.csv"
MAX_DAILY_EMAILS = 10

IGNORE_EMAIL_DOMAINS = {
    "linkedin.com", "example.com", "yourcompany.com", "domain.com",
    "company.com", "test.com", "sample.com", "sentry.io",
}


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
            "exp": "3.6 Yrs",
            "href": post_url,
            "status": sheet_status,
            "notes": row.get("notes", f"HR Email: {row.get('recipient_email', 'N/A')} | Phone: {row.get('phone', 'N/A')}"),
            "tailored_resume_path": row.get("resume_path", ""),
        })
    except Exception as e:
        print(f"  (Google Sheets logging notice: {e})")


def extract_emails_from_text(text: str) -> list[str]:
    """Extracts valid email addresses from text, filtering platform and example addresses."""
    # Match standard email pattern
    raw_emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
    valid_emails = []
    seen = set()

    for e in raw_emails:
        clean = e.strip(".,;:()[]\"'<>").lower()
        if not clean or clean in seen:
            continue
        domain = clean.split("@")[-1]
        if domain in IGNORE_EMAIL_DOMAINS or any(domain.endswith(f".{d}") for d in IGNORE_EMAIL_DOMAINS):
            continue
        # Ensure valid domain format
        if "." not in domain or len(domain.split(".")[-1]) < 2:
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
    """Navigates to LinkedIn content search for a role and extracts hiring posts."""
    query = f"hiring {role}"
    url = f"https://www.linkedin.com/search/results/content/?keywords={urllib.parse.quote(query)}"
    print(f"\n🔍 Searching LinkedIn Posts: '{query}'")
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


def run_outreach(target_role_filter: str | None = None, dry_run: bool = False, max_emails: int = MAX_DAILY_EMAILS):
    """Main orchestrator for LinkedIn post scraping, resume tailoring, and email outreach."""
    profile = Profile.load()
    if not Path(SESSION_FILE).exists():
        raise SystemExit(
            f"ERROR: {SESSION_FILE} not found. "
            "Please run 'python login_capture.py linkedin' first."
        )

    roles = [target_role_filter] if target_role_filter else profile.target_roles
    sent_count = 0

    print("=" * 70)
    print("🚀 LinkedIn Hiring Posts Outreach Pipeline")
    print(f"Target Roles: {', '.join(roles)}")
    print(f"Daily Cap: {max_emails} emails")
    print(f"Mode: {'DRY RUN (no emails sent)' if dry_run else 'ACTIVE (with interactive review)'}")
    print("=" * 70)

    with sync_playwright() as p:
        browser_mode = profile.data.get("browser_mode", "minimized")
        if browser_mode == "headless":
            browser = p.chromium.launch(headless=True, slow_mo=150)
        elif browser_mode == "minimized":
            browser = p.chromium.launch(headless=False, slow_mo=150, args=["--start-minimized"])
        else:
            browser = p.chromium.launch(headless=False, slow_mo=150)

        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        for role in roles:
            if sent_count >= max_emails:
                print(f"\n✅ Reached daily email cap ({max_emails}). Stopping outreach.")
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

                # Extract emails and phone numbers
                emails = extract_emails_from_text(text)
                phones = extract_phone_numbers(text)
                phone_str = phones[0] if phones else "Not mentioned"

                # Check if already logged/processed
                if post_url and external_job_url_exists(post_url):
                    print(f"⏭️ Skipping: Post already logged in tracker ({post_url})")
                    continue

                # Check for Obstacle: Hiring post found, but no direct email in post text
                if not emails:
                    company = infer_company_name(text=text, headline=headline, email="")
                    print("\n" + "-" * 70)
                    print(f"⚠️ OBSTACLE: Post by {author} has no direct HR email")
                    print(f"Author:     {author} ({headline})")
                    print(f"Post URL:   {post_url}")
                    print(f"Action:     Logging obstacle to Google Sheets as PENDING_MANUAL_DM")
                    print("-" * 70)
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
                company = infer_company_name(text=text, headline=headline, email=recipient_email)

                print("\n" + "=" * 70)
                print(f"🎯 QUALIFIED HIRING POST FOUND")
                print(f"Author:     {author} ({headline})")
                print(f"Company:    {company}")
                print(f"HR Email:   {recipient_email}")
                print(f"Phone:      {phone_str}")
                print(f"Post URL:   {post_url}")
                print("-" * 70)
                print(f"Post Snippet:\n{text[:300]}...")
                print("=" * 70)

                # Step 1: Tailor the Resume and convert to PDF
                role_slug = re.sub(r'[^A-Za-z0-9]+', '_', role).strip('_')
                output_docx_path = f"generated/Abhishek_Anand_{role_slug}_{post_id}.docx"
                clean_resume_display_name = f"Abhishek_Anand_{role_slug}.pdf"
                print(f"\n📄 Preparing resume for {role}...")
                try:
                    prep = prepare_tailored_resume(
                        job_description=text,
                        master_resume_path="Abhishek_Anand_Resume.docx",
                        output_path=output_docx_path,
                    )
                    docx_path = prep["tailored_resume_path"]
                    pdf_path = convert_docx_to_pdf(docx_path)
                    resume_path = pdf_path
                    print(f"   Human-Styled PDF Resume Ready: {clean_resume_display_name} ({resume_path})")
                except Exception as e:
                    print(f"   ATS preparation notice: {e}. Using Master PDF Resume.")
                    if not Path("Abhishek_Anand_Resume.pdf").exists():
                        convert_docx_to_pdf("Abhishek_Anand_Resume.docx")
                    resume_path = "Abhishek_Anand_Resume.pdf"
                    clean_resume_display_name = "Abhishek_Anand_Resume.pdf"

                # Step 2: Draft Cold Email
                print(f"✍️ Drafting personalized cold email...")
                draft = draft_cold_email(
                    post_text=text,
                    author=author,
                    company=company,
                    role=role,
                )
                subject = draft["subject"]
                body = draft["body"]

                # Step 3: Interactive Review Mode
                print("\n" + "#" * 70)
                print(f"📧 COLD OUTREACH EMAIL PREVIEW")
                print(f"To:       {recipient_email}")
                print(f"Subject:  {subject}")
                print(f"Attach:   {clean_resume_display_name} (file: {resume_path})")
                print("-" * 70)
                print(body)
                print("#" * 70)

                if dry_run:
                    print("\n[DRY RUN]: Email draft created. Not sending.")
                    log_outreach({
                        "post_id": post_id,
                        "recipient_email": recipient_email,
                        "author": author,
                        "company": company,
                        "role": role,
                        "phone": phone_str,
                        "post_url": post_url,
                        "resume_path": resume_path,
                        "status": "dry_run",
                        "sheet_status": "DRAFT_DRY_RUN",
                        "notes": f"Dry run draft created for {recipient_email} ({author} at {company})",
                    })
                    continue

                # Ask user for permission in terminal
                while True:
                    choice = input("\nSend this email to HR? [Y]es / [s]kip / [e]dit body / [q]uit: ").strip().lower()
                    if choice in ("y", "yes", ""):
                        try:
                            send_email(
                                to_email=recipient_email,
                                subject=subject,
                                body_text=body,
                                attachment_path=resume_path,
                                attachment_display_name=clean_resume_display_name,
                            )
                            sent_count += 1
                            print(f"🎉 Email successfully sent to {recipient_email}! ({sent_count}/{max_emails})")
                            log_outreach({
                                "post_id": post_id,
                                "recipient_email": recipient_email,
                                "author": author,
                                "company": company,
                                "role": role,
                                "phone": phone_str,
                                "post_url": post_url,
                                "resume_path": resume_path,
                                "status": "sent",
                                "sheet_status": "EMAILED",
                                "notes": f"Cold outreach sent via Gmail to {recipient_email} ({author} at {company})",
                            })
                        except Exception as e:
                            print(f"❌ Failed to send email: {e}")
                            log_outreach({
                                "post_id": post_id,
                                "recipient_email": recipient_email,
                                "author": author,
                                "company": company,
                                "role": role,
                                "phone": phone_str,
                                "post_url": post_url,
                                "resume_path": resume_path,
                                "status": "failed",
                                "sheet_status": "SEND_FAILED",
                                "notes": f"Obstacle: Send error: {e}",
                            })
                        break
                    elif choice in ("s", "skip"):
                        print("⏭️ Skipped this post.")
                        log_outreach({
                            "post_id": post_id,
                            "recipient_email": recipient_email,
                            "author": author,
                            "company": company,
                            "role": role,
                            "phone": phone_str,
                            "post_url": post_url,
                            "resume_path": resume_path,
                            "status": "skipped",
                            "sheet_status": "SKIPPED",
                            "notes": f"User skipped sending cold email ({author})",
                        })
                        break
                    elif choice in ("e", "edit"):
                        print("\nEnter your custom email body (type EOF on a new line when done):")
                        lines = []
                        while True:
                            line = input()
                            if line.strip() == "EOF":
                                break
                            lines.append(line)
                        if lines:
                            body = "\n".join(lines)
                            print("Updated body. Ready to review.")
                    elif choice in ("q", "quit"):
                        print("🛑 Quitting outreach run.")
                        browser.close()
                        return

                time.sleep(3)

        browser.close()

    print(f"\n🏁 Finished outreach run. Total emails sent: {sent_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LinkedIn Hiring Posts Cold Outreach Bot")
    parser.add_argument("--role", type=str, default=None, help="Specific role to search for (e.g. 'React Developer')")
    parser.add_argument("--dry-run", action="store_true", help="Scrape and draft emails without sending")
    parser.add_argument("--max-emails", type=int, default=MAX_DAILY_EMAILS, help="Max emails to send this run")
    args = parser.parse_args()
    run_outreach(target_role_filter=args.role, dry_run=args.dry_run, max_emails=args.max_emails)
