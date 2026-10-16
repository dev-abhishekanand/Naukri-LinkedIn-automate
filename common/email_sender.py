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

KNOWN_TLDS_SORTED = sorted([
    "co.in", "org.in", "net.in", "ac.in", "edu.in", "gov.in",
    "co.uk", "org.uk", "com.au", "net.au", "co.za", "co.nz", "co.jp", "com.sg",
    "com", "in", "org", "net", "io", "ai", "co", "tech", "dev", "app", "me",
    "info", "biz", "global", "agency", "careers", "jobs", "consulting",
    "solutions", "digital", "cloud", "us", "uk", "de", "ca", "fr", "au", "sg",
    "ae", "eu", "xyz", "pro", "online", "site"
], key=lambda x: (len(x), "." in x), reverse=True)

COMMON_WEBMAILS = ["gmail", "yahoo", "outlook", "hotmail", "icloud", "proton", "rediffmail", "zoho"]
DUMMY_EMAIL_LOCAL_PARTS = {"mail", "email", "example", "test", "sample", "yourname", "user", "name", "xyz", "abc", "your-email", "youremail"}
IGNORE_EMAIL_DOMAINS = {
    "linkedin.com", "example.com", "yourcompany.com", "domain.com",
    "company.com", "test.com", "sample.com", "sentry.io",
}


def preprocess_text_for_emails(text: str) -> str:
    """Normalizes whitespace and inserts spaces after domain extensions (.com, .co.in, etc.)
    when glued to trailing words (e.g. 'akashjaggi1123@gmail.comthank' -> 'akashjaggi1123@gmail.com thank')."""
    if not text:
        return ""
    # 1. Normalize spaces & zero-width characters
    text = re.sub(r'[\xa0\u200b\u200c\u200d\ufeff]+', ' ', text)

    # 2. Specifically insert a space after webmail .com: e.g. @gmail.comthank -> @gmail.com thank
    for wm in COMMON_WEBMAILS:
        text = re.sub(rf'(@{wm}\.com)(?=[A-Za-z0-9])', r'\1 ', text, flags=re.IGNORECASE)

    # 3. Insert space after 2-part ccTLDs: e.g. .co.inInterested -> .co.in Interested
    text = re.sub(r'(\.(?:co|org|net|ac|edu|gov)\.in)(?=[A-Za-z])', r'\1 ', text, flags=re.IGNORECASE)
    text = re.sub(r'(\.(?:co|org)\.uk)(?=[A-Za-z])', r'\1 ', text, flags=re.IGNORECASE)
    text = re.sub(r'(\.com\.au)(?=[A-Za-z])', r'\1 ', text, flags=re.IGNORECASE)

    # 4. Insert space after .com, .org, .net, .io, .ai when followed by uppercase word or common recruiter glued words
    glued_words = r'(?:thank|thanks|thx|pls|please|regards|interested|looking|immediate|joiner|apply|reach|call|contact|dm|send|share|mail|or|and|with|on|for|at)'
    text = re.sub(rf'(\.(?:com|org|net|io|ai|tech|dev|app))\s*\.?({glued_words}\b)', r'\1 \2', text, flags=re.IGNORECASE)
    text = re.sub(r'(\.(?:com|org|net|io|ai|tech|dev|app))([A-Z][a-z]+)', r'\1 \2', text)

    # 5. Insert space after .com / .org / .net if immediately followed by punctuation like . / - :
    # e.g. akashjaggi1123@gmail.com. Check -> akashjaggi1123@gmail.com . Check
    text = re.sub(r'(\.(?:com|org|net|io|ai|tech|dev|app|co\.in))\s*([.,;:/\\-])(?=\s|[A-Za-z])', r'\1 \2', text, flags=re.IGNORECASE)

    return text


def clean_email_address(raw_email: str) -> str | None:
    """Cleans an extracted email address:
    - Strips leading/trailing punctuation (. , : ; / - _ ! ? quotes brackets)
    - Strips prefix labels (mailto:, email:, mail_id:, id:)
    - Fixes glued domain endings (e.g. gmail.comthank -> gmail.com)
    - Rejects placeholder/dummy addresses (mail@gmail.com, example@domain.com)
    - Validates standard email RFC structure
    """
    if not raw_email:
        return None
    e = raw_email.strip().strip(".,;:()[]\"'<>/-_\\?!")
    if not e or "@" not in e:
        return None

    # Remove prefix if present: e.g. mailto:user@domain.com, email:user@domain.com, mail_id:user@domain.com, id:user@domain.com
    e = re.sub(r'^(?:mailto|email|mail_id|email_id|mailid|emailid|mail_address|email_address|contact|id)[:=-]+', '', e, flags=re.IGNORECASE)
    e = e.strip().strip(".,;:()[]\"'<>/-_\\?!")

    local, _, domain = e.partition("@")
    local = local.strip().strip(".,;:()[]\"'<>/-_\\?!")
    domain = domain.strip().lower().strip(".,;:()[]\"'<>/-_\\?!")

    if not local or not domain or "." not in domain:
        return None

    # Check if domain has glued text at the end: e.g. gmail.comthank or company.comthanks
    # 1. Known webmail domains
    for wm in COMMON_WEBMAILS:
        if domain.startswith(f"{wm}.com") and len(domain) > len(f"{wm}.com"):
            domain = f"{wm}.com"
            break
        elif domain.startswith(f"{wm}.") and len(domain) > len(f"{wm}."):
            for tld in KNOWN_TLDS_SORTED:
                if domain.startswith(f"{wm}.{tld}"):
                    domain = f"{wm}.{tld}"
                    break

    # 2. General domains:
    # Check 2-part TLD first: e.g. domain.co.inthank
    parts = domain.split(".")
    if len(parts) >= 3:
        two_part_tld = f"{parts[-2]}.{parts[-1]}"
        if two_part_tld not in KNOWN_TLDS_SORTED:
            for kt in [t for t in KNOWN_TLDS_SORTED if "." in t]:
                if two_part_tld.startswith(kt) and len(two_part_tld) > len(kt):
                    domain = ".".join(parts[:-2]) + "." + kt
                    break

    # Check single TLD: e.g. domain.comthank
    parts = domain.split(".")
    last_seg = parts[-1]
    if last_seg not in KNOWN_TLDS_SORTED:
        for kt in [t for t in KNOWN_TLDS_SORTED if "." not in t]:
            if last_seg.startswith(kt) and len(last_seg) > len(kt):
                trailing = last_seg[len(kt):]
                if trailing.isalpha():
                    parts[-1] = kt
                    domain = ".".join(parts)
                    break

    clean_addr = f"{local}@{domain}".lower()

    # Filter dummy / placeholder emails
    if local.lower() in DUMMY_EMAIL_LOCAL_PARTS and (any(domain == f"{wm}.com" for wm in COMMON_WEBMAILS) or domain in ["domain.com", "company.com", "example.com"]):
        return None

    if domain in IGNORE_EMAIL_DOMAINS or any(domain.endswith(f".{d}") for d in IGNORE_EMAIL_DOMAINS):
        return None

    # Final RFC structure check
    if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,24}$', clean_addr):
        return None

    return clean_addr


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

    cleaned_to = clean_email_address(to_email)
    if not cleaned_to:
        raise ValueError(f"Invalid recipient email address: '{to_email}' (malformed or placeholder address)")
    to_email = cleaned_to

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
