"""
Email Dispatcher for Job Applications
Sends tailored job application emails with Abhishek Anand's resume attached
strictly using abhishek.anand7601@gmail.com.
"""
import os
import smtplib
import imaplib
import time
import re
from pathlib import Path
from email.message import EmailMessage
from email.utils import formataddr
from typing import Dict, Any, Optional

from common.profile import Profile
from common import llm

BASE_DIR = Path(__file__).resolve().parent.parent
RESUME_FILE = BASE_DIR / "Abhishek_Anand_Resume.pdf"
def get_strictly_configured_email() -> str:
    """Loads candidate email from .env (GMAIL_USER)."""
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == "GMAIL_USER":
                    return v.strip()
    return "abhishek.anand@gmail.com"


def _load_smtp_credentials() -> tuple[str, str]:
    """Loads active Gmail SMTP credentials from .env."""
    env_file = BASE_DIR / ".env"
    env_dict = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_dict[k.strip()] = v.strip()

    user = env_dict.get("GMAIL_USER", "")
    password = env_dict.get("GMAIL_APP_PASSWORD", "")
    return user, password


def update_gmail_credentials(new_email: str, new_app_password: Optional[str] = None):
    """Updates GMAIL_USER and optionally GMAIL_APP_PASSWORD in .env and profile.yaml."""
    env_file = BASE_DIR / ".env"
    lines = []
    has_user = False
    has_pass = False

    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("GMAIL_USER="):
                lines.append(f"GMAIL_USER={new_email.strip()}")
                has_user = True
            elif new_app_password and line.startswith("GMAIL_APP_PASSWORD="):
                lines.append(f"GMAIL_APP_PASSWORD={new_app_password.strip()}")
                has_pass = True
            else:
                lines.append(line)

    if not has_user:
        lines.append(f"GMAIL_USER={new_email.strip()}")
    if new_app_password and not has_pass:
        lines.append(f"GMAIL_APP_PASSWORD={new_app_password.strip()}")

    env_file.write_text("\n".join(lines) + "\n")

    # Also update profile.yaml
    profile_path = BASE_DIR / "profile.yaml"
    if profile_path.exists():
        content = profile_path.read_text()
        content = re.sub(r'email:\s*["\']?[^"\'\n]+["\']?', f'email: "{new_email.strip()}"', content)
        profile_path.write_text(content)



def generate_application_email_draft(
    company: str,
    job_title: str = "",
    job_details: str = "",
    profile: Optional[Profile] = None,
    recipient: str = "",
    role: str = ""
) -> Dict[str, str]:
    """
    Generates a tailored application email draft.
    Subject is strictly the title of the job hiring post.
    Body contains relevant keywords of that job hiring, and highlights candidate strengths + attached resume.
    """
    if not profile:
        profile = Profile.load()

    target_title = job_title or role or "React Developer"
    cleaned_title = target_title.strip() if target_title and target_title.strip() else "React Developer"
    default_subject = cleaned_title
    candidate_email = get_strictly_configured_email()

    prompt = (
        f"You are writing a professional, concise job application email on behalf of Abhishek Anand.\n"
        f"Candidate Details:\n"
        f"- Name: Abhishek Anand\n"
        f"- Total Experience: 4+ years\n"
        f"- Core Skills: React.js, Next.js, TypeScript, JavaScript (ES6+), Redux, Tailwind CSS, HTML5/CSS3, REST APIs\n"
        f"- Notice Period: Immediate / 0 days\n"
        f"- Current Location: Patna (Open to Pune, Bangalore, Hyderabad, Noida, Gurgaon, or Remote)\n"
        f"- Target Role: {cleaned_title}\n"
        f"- Target Company: {company}\n"
        f"- Job Context / Requirements: {job_details[:600]}\n\n"
        f"Write a polished, high-converting email to the hiring manager / recruiter.\n"
        f"CRITICAL REQUIREMENTS:\n"
        f"1. Subject MUST strictly be the title of the job hiring: '{cleaned_title}'.\n"
        f"2. The email body MUST contain the relevant keywords of this job hiring (e.g. React.js, Next.js, TypeScript, and specific requirements from the role).\n"
        f"3. Explicitly state that Abhishek Anand's resume is attached.\n"
        f"4. Concise (3 short paragraphs maximum).\n"
        f"5. Sign off with Abhishek Anand, Phone: +91-8839617601, Email: {candidate_email}.\n\n"
        f"Return ONLY valid JSON with keys 'subject' and 'body'. No markdown formatting outside JSON."
    )

    try:
        from common import gemini
        resp = gemini.generate_content(prompt)
        text = resp.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        import json
        data = json.loads(text)
        return {
            "subject": data.get("subject", default_subject).strip(),
            "body": data.get("body", "").strip(),
            "to_email": recipient,
            "attachment": str(RESUME_FILE)
        }
    except Exception:
        # High quality keyword-infused fallback template
        candidate_email = get_strictly_configured_email()
        body = (
            f"Hi Hiring Team,\n\n"
            f"I am writing to express my strong interest in the {cleaned_title} position at {company}.\n\n"
            f"With 4+ years of hands-on software engineering experience specializing in React.js, Next.js, "
            f"TypeScript, Redux Toolkit, and Tailwind CSS, I have architected high-performance web applications, "
            f"responsive web dashboards, and modular UI components with seamless REST/GraphQL API integration.\n\n"
            f"Key highlights aligned with {cleaned_title}:\n"
            f"• 4+ years frontend development experience: React.js, Next.js (SSR/SSG), TypeScript, JavaScript (ES6+).\n"
            f"• State management & UI architecture: Redux Toolkit, Context API, responsive Tailwind CSS styling.\n"
            f"• Immediate joiner: 0 days notice period, ready for immediate onboarding.\n"
            f"• Location: Open to Bangalore, Pune, Hyderabad, Gurgaon, Noida, or Remote.\n\n"
            f"I have attached my resume (Abhishek_Anand_Resume.pdf) for your review. I look forward to the opportunity to discuss how my technical expertise aligns with your team's objectives.\n\n"
            f"Best regards,\n"
            f"Abhishek Anand\n"
            f"Phone: +91-8839617601\n"
            f"Email: {candidate_email}\n"
            f"LinkedIn: https://linkedin.com/in/abhishek-anand-7601\n"
            f"GitHub: https://github.com/Abhishekanand7601"
        )
        return {
            "subject": default_subject,
            "body": body,
            "to_email": recipient,
            "attachment": str(RESUME_FILE)
        }


def save_job_application_draft_to_gmail(
    to_email: str,
    subject: str,
    body: str,
    company: str = "",
    job_title: str = "",
    resume_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Saves an application email directly into the candidate's Gmail [Gmail]/Drafts folder
    with Abhishek_Anand_Resume.pdf attached.
    Does NOT send the email. The candidate can review and manually send it from Gmail.
    """
    user, password = _load_smtp_credentials()

    if not user or not password:
        return {
            "status": "ERROR",
            "message": "Gmail credentials not configured in .env (GMAIL_USER & GMAIL_APP_PASSWORD required)"
        }

    # Verify resume file
    target_resume = Path(resume_path) if resume_path else RESUME_FILE
    if not target_resume.exists():
        return {
            "status": "ERROR",
            "message": f"Resume file not found at: {target_resume}"
        }

    sender_email = user or get_strictly_configured_email()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("Abhishek Anand", sender_email))
    msg["To"] = to_email
    msg.set_content(body)

    # Attach resume PDF
    with open(target_resume, "rb") as f:
        pdf_data = f.read()

    msg.add_attachment(
        pdf_data,
        maintype="application",
        subtype="pdf",
        filename="Abhishek_Anand_Resume.pdf"
    )

    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com")
        imap.login(user, password)
        now = imaplib.Time2Internaldate(time.time())

        # Dynamically discover Drafts folder from IMAP list
        drafts_folder = '"[Gmail]/Drafts"'
        try:
            res_code, mailboxes = imap.list()
            if res_code == "OK":
                for mb in mailboxes:
                    decoded = mb.decode("utf-8", errors="ignore")
                    if "\\Drafts" in decoded:
                        parts = decoded.split(' "/" ')
                        if len(parts) == 2:
                            drafts_folder = parts[1].strip()
                            break
        except Exception:
            pass

        imap.append(drafts_folder, '(\\Draft)', now, msg.as_bytes())
        imap.logout()

        # Log into applications_log.csv
        from core.tracker import ApplicationTracker
        tracker = ApplicationTracker()
        drafts_url = "https://mail.google.com/mail/#drafts"
        tracker.log_application(
            platform="email_draft",
            job_id=f"draft_{to_email}",
            title=job_title or "Job Application Draft",
            company=company or to_email,
            status="DRAFT_SAVED",
            url=drafts_url,
            reason="Draft saved in Gmail Drafts with resume attached for your review"
        )

        return {
            "status": "DRAFT_SAVED",
            "to": to_email,
            "from": sender_email,
            "subject": subject,
            "company": company,
            "draft_url": drafts_url,
            "message": f"Draft saved directly to your Gmail Drafts folder ({sender_email})! You can review and send it manually."
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "to": to_email,
            "from": sender_email,
            "message": f"Gmail IMAP Draft creation failed: {e}"
        }


def send_job_application_email(
    to_email: str,
    subject: str,
    body: str,
    company: str = "",
    job_title: str = "",
    resume_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Safely routes to save_job_application_draft_to_gmail to ensure no emails
    are ever sent automatically without manual user review in Gmail.
    """
    return save_job_application_draft_to_gmail(
        to_email=to_email,
        subject=subject,
        body=body,
        company=company,
        job_title=job_title,
        resume_path=resume_path
    )


