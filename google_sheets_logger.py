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


def _load_dotenv():
    if os.environ.get(SPREADSHEET_ID_ENV):
        return
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == SPREADSHEET_ID_ENV:
            os.environ[SPREADSHEET_ID_ENV] = value.strip()
            return


def _get_sheet():
    _load_dotenv()
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
    client.set_timeout((10, 20))
    spreadsheet = client.open_by_key(spreadsheet_id)

    return spreadsheet.sheet1


def _ensure_headers(sheet):
    rows = sheet.get_all_values()

    if not rows:
        sheet.append_row(HEADERS)
        return

    # Find the existing job-log header row. The sheet may contain
    # dashboard/title rows above the actual application table.
    header_row_index = None
    for index, row in enumerate(rows):
        normalized = [str(cell).strip().lower() for cell in row]
        if "job id" in normalized or "job_id" in normalized:
            header_row_index = index
            break

    if header_row_index is None:
        raise RuntimeError(
            "Google Sheet job-log header row could not be found."
        )

    current = rows[header_row_index]

    # Existing sheet uses human-readable headers.
    expected_existing = [
        "date added",
        "platform",
        "job id",
        "job title",
        "company",
        "location",
        "experience",
        "job link",
        "status",
        "notes",
    ]

    normalized_current = [
        str(cell).strip().lower() for cell in current[:10]
    ]

    if normalized_current == expected_existing:
        expanded_headers = [
            "Date Added",
            "Platform",
            "Job ID",
            "Job Title",
            "Company",
            "Location",
            "Experience",
            "Job Link",
            "Status",
            "Notes",
            "JD Keywords",
            "Missing Keywords",
            "Tailored Resume Path",
        ]
        row_number = header_row_index + 1
        sheet.update(
            f"A{row_number}:M{row_number}",
            [expanded_headers],
        )
        return

    if current == HEADERS:
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
