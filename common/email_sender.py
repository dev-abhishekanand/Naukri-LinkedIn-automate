"""Gmail SMTP sender for job application cold emails."""

import mimetypes
import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


def _load_dotenv():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key not in os.environ:
            os.environ[key] = value.strip()


import re


def send_email(
    to_email: str,
    subject: str,
    body_text: str,
    attachment_path: str | None = None,
    attachment_display_name: str | None = None,
    cc: str | None = None,
) -> bool:
    """Sends an email with optional resume attachment using Gmail SMTP.
    Attachment filename is guaranteed to be clean and human-styled (e.g. Abhishek_Anand_Resume.pdf)."""
    _load_dotenv()
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_user or not gmail_password:
        raise ValueError(
            "GMAIL_USER or GMAIL_APP_PASSWORD is not set in .env. "
            "Please configure your Gmail App Password first."
        )

    msg = MIMEMultipart()
    msg["From"] = f"Abhishek Anand <{gmail_user}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc

    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    if attachment_path:
        att_file = Path(attachment_path)
        if not att_file.exists():
            raise FileNotFoundError(f"Attachment file not found: {attachment_path}")

        # Human-presentable attachment filename:
        # Strip internal tags like 'Tailored_' and job ID suffixes
        if attachment_display_name:
            out_filename = attachment_display_name
        else:
            raw_name = att_file.name
            clean = re.sub(r'tailored[_\-\s]*', '', raw_name, flags=re.IGNORECASE)
            clean = re.sub(r'_\d+(\.\w+)$', r'\1', clean)  # strip trailing internal IDs
            clean = clean.strip('_')
            out_filename = clean or "Abhishek_Anand_Resume.pdf"

        ctype, encoding = mimetypes.guess_type(str(att_file))
        if ctype is None or encoding is not None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)

        with open(att_file, "rb") as f:
            part = MIMEBase(maintype, subtype)
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=out_filename)
        msg.attach(part)

    recipients = [to_email]
    if cc:
        recipients.append(cc)

    # Gmail SMTP over SSL (port 465) or TLS (port 587)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, recipients, msg.as_string())

    return True
