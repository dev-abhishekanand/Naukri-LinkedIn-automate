import os
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials


CREDENTIALS_FILE = "naukri-sheets-integration-42556bd602fd.json"
SPREADSHEET_ID_ENV = "GOOGLE_SHEETS_SPREADSHEET_ID"

HEADERS = [
    "discovered_at",
    "platform",
    "job_id",
    "title",
    "company",
    "location",
    "experience",
    "job_url",
    "status",
    "notes",
    "jd_keywords",
    "missing_keywords",
    "tailored_resume_path",
]


def _get_sheet():
    spreadsheet_id = os.getenv(SPREADSHEET_ID_ENV)

    if not spreadsheet_id:
        raise RuntimeError(
            f"{SPREADSHEET_ID_ENV} is not set"
        )

    credentials_path = Path(CREDENTIALS_FILE)

    if not credentials_path.exists():
        raise RuntimeError(
            f"Google Sheets credentials file not found: {credentials_path}"
        )

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
    ]

    credentials = Credentials.from_service_account_file(
        credentials_path,
        scopes=scopes,
    )

    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(spreadsheet_id)

    return spreadsheet.sheet1


def _ensure_headers(sheet):
    rows = sheet.get_all_values()

    if not rows:
        sheet.append_row(HEADERS)
        return

    current = rows[0]

    if current == HEADERS:
        return

    if current == HEADERS[:len(current)]:
        sheet.update("A1:M1", [HEADERS])
        return

    raise RuntimeError(
        "Google Sheet headers do not match the expected job-log schema."
    )


def external_job_url_exists(job_url: str) -> bool:
    if not job_url:
        return False

    sheet = _get_sheet()
    rows = sheet.get_all_values()
    if not rows:
        return False

    headers = rows[0]
    try:
        url_index = headers.index("job_url")
    except ValueError:
        return False

    normalized = job_url.strip()
    return any(
        len(row) > url_index and row[url_index].strip() == normalized
        for row in rows[1:]
    )


def append_external_job(card: dict):
    sheet = _get_sheet()

    _ensure_headers(sheet)

    sheet.append_row([
        card.get("discovered_at", ""),
        "naukri",
        card.get("jobId", ""),
        card.get("title", ""),
        card.get("company", ""),
        card.get("location", ""),
        card.get("exp", ""),
        card.get("href", ""),
        "PENDING",
        "External company application - manual completion required",
        "",
        "",
        "",
    ])
    return True


def append_tailored_job(card: dict):
    """Log a relevant Naukri job requiring manual application."""
    sheet = _get_sheet()
    _ensure_headers(sheet)

    sheet.append_row([
        card.get("discovered_at", ""),
        "naukri",
        card.get("jobId", ""),
        card.get("title", ""),
        card.get("company", ""),
        card.get("location", ""),
        card.get("exp", ""),
        card.get("href", ""),
        "TAILORED_MANUAL",
        "Manual application required with tailored resume",
        card.get("jd_keywords", ""),
        card.get("missing_keywords", ""),
        card.get("tailored_resume_path", ""),
    ])
    return True
