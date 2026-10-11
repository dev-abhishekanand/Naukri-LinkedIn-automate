from datetime import datetime
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


def _get_spreadsheet():
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
    return client.open_by_key(spreadsheet_id)


def _get_sheet():
    return _get_spreadsheet().sheet1


def _ensure_headers(sheet):
    """Validate an existing job log or create one below dashboard data."""
    rows = sheet.get_all_values()
    expanded_headers = [
        "Date Added", "Platform", "Job ID", "Job Title", "Company",
        "Location", "Experience", "Job Link", "Status", "Notes",
        "JD Keywords", "Missing Keywords", "Tailored Resume Path",
    ]
    expected_existing = [
        "date added", "platform", "job id", "job title", "company",
        "location", "experience", "job link", "status", "notes",
    ]

    # Recognize either the internal snake_case schema or human-readable headers.
    for index, row in enumerate(rows):
        normalized = [
            str(cell).strip().lower().replace("_", " ") for cell in row
        ]
        if normalized[:len(HEADERS)] == [h.replace("_", " ") for h in HEADERS]:
            return

        if len(normalized) >= 10:
            comparable = normalized[:10].copy()
            if len(comparable) > 7 and comparable[7] == "job url":
                comparable[7] = "job link"
            if comparable != expected_existing:
                continue
            # Expand the older 10-column header in place, preserving job rows.
            if len(row) < 13 or normalized[7] == "job url":
                row_number = index + 1
                sheet.update(
                    f"A{row_number}:M{row_number}",
                    [expanded_headers],
                    value_input_option="RAW",
                )
            return

    # No log header exists. Keep dashboard rows intact and leave one blank row.
    header_row_number = len(rows) + 2 if rows else 1
    sheet.update(
        f"A{header_row_number}:M{header_row_number}",
        [expanded_headers],
        value_input_option="RAW",
    )


def append_test_job():
    """Insert one TEST_ONLY row for logger validation; never applies to a job."""
    test_url = "https://example.com/test-job-do-not-apply"
    if external_job_url_exists(test_url):
        return False

    sheet = _get_sheet()
    _ensure_headers(sheet)
    sheet.append_row(
        [
            "TEST_ONLY", "test", "TEST_ONLY", "TEST ONLY — safe logger check",
            "Example Company (not real)", "Not applicable", "", test_url,
            "TEST_ONLY", "Test row only; no application submitted", "", "", "",
        ],
        value_input_option="RAW",
    )
    return True


def external_job_url_exists(job_url: str) -> bool:
    if not job_url:
        return False

    sheet = _get_sheet()
    rows = sheet.get_all_values()
    if not rows:
        return False

    # The application table may sit below dashboard/title rows.
    header_row_index = None
    url_index = None

    for index, row in enumerate(rows):
        normalized_headers = [
            str(cell).strip().lower().replace("_", " ")
            for cell in row
        ]

        if "job id" in normalized_headers:
            header_row_index = index

            for candidate in ("job link", "job url"):
                if candidate in normalized_headers:
                    url_index = normalized_headers.index(candidate)
                    break

            break

    if header_row_index is None or url_index is None:
        return False

    normalized = job_url.strip()
    return any(
        len(row) > url_index and row[url_index].strip() == normalized
        for row in rows[header_row_index + 1:]
    )


def append_applied_job(card: dict):
    """Log a verified successful application to the existing job sheet."""
    sheet = _get_sheet()
    _ensure_headers(sheet)

    sheet.append_row([
        card.get("discovered_at", ""),
        card.get("platform", "naukri"),
        card.get("jobId", ""),
        card.get("title", ""),
        card.get("company", ""),
        card.get("location", ""),
        card.get("exp", ""),
        card.get("href", ""),
        "APPLIED",
        card.get("notes", "Application submission verified"),
        "",
        "",
        "",
    ])
    return True


def append_external_job(card: dict):
    sheet = _get_sheet()

    _ensure_headers(sheet)

    sheet.append_row([
        card.get("discovered_at", ""),
        card.get("platform", "naukri"),
        card.get("jobId", ""),
        card.get("title", ""),
        card.get("company", ""),
        card.get("location", ""),
        card.get("exp", ""),
        card.get("href", ""),
        card.get("status", "PENDING"),
        card.get("notes", "External company application - manual completion required"),
        card.get("jd_keywords", ""),
        card.get("missing_keywords", ""),
        card.get("tailored_resume_path", ""),
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


INTERVIEW_PREP_HEADERS = [
    "Date Added", "Company", "Role / Level", "Round Type",
    "Topics Asked", "Questions Asked", "Coding / Machine Coding Task",
    "Frontend System Design", "Tips & Insights", "Post Link", "Author",
]


def get_or_create_interview_prep_sheet():
    """Gets or creates the 'Frontend Interview Prep' worksheet."""
    spreadsheet = _get_spreadsheet()
    sheet_title = "Frontend Interview Prep"
    try:
        sheet = spreadsheet.worksheet(sheet_title)
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=sheet_title, rows=200, cols=len(INTERVIEW_PREP_HEADERS))

    rows = sheet.get_all_values()
    if not rows or rows[0][:len(INTERVIEW_PREP_HEADERS)] != INTERVIEW_PREP_HEADERS:
        if not rows:
            sheet.append_row(INTERVIEW_PREP_HEADERS, value_input_option="RAW")
        else:
            sheet.insert_row(INTERVIEW_PREP_HEADERS, index=1, value_input_option="RAW")
    return sheet


def append_interview_prep(entry: dict) -> bool:
    """Appends an interview experience entry to the 'Frontend Interview Prep' worksheet."""
    sheet = get_or_create_interview_prep_sheet()
    sheet.append_row([
        entry.get("discovered_at", datetime.now().strftime("%Y-%m-%d %H:%M")),
        entry.get("company", "Various / General"),
        entry.get("role_level", "Frontend / React Developer"),
        entry.get("round_type", "Technical Round"),
        entry.get("topics", ""),
        entry.get("questions_asked", ""),
        entry.get("coding_tasks", ""),
        entry.get("system_design", ""),
        entry.get("tips", ""),
        entry.get("post_link", ""),
        entry.get("author", ""),
    ], value_input_option="RAW")
    return True


def interview_post_url_exists(post_url: str) -> bool:
    """Checks if a LinkedIn interview post URL is already recorded."""
    if not post_url:
        return False
    try:
        sheet = get_or_create_interview_prep_sheet()
        rows = sheet.get_all_values()
        if len(rows) <= 1:
            return False
        clean_url = post_url.strip().lower()
        for r in rows[1:]:
            if len(r) > 9 and r[9].strip().lower() == clean_url:
                return True
        return False
    except Exception:
        return False

