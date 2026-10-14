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

DATE_ROW_FORMAT = {
    "backgroundColor": {"red": 0.88, "green": 0.92, "blue": 0.99},  # Soft Executive Blue
    "textFormat": {
        "bold": True,
        "foregroundColor": {"red": 0.08, "green": 0.23, "blue": 0.53},  # Deep Navy
        "fontSize": 11,
    },
    "horizontalAlignment": "LEFT",
    "verticalAlignment": "MIDDLE",
}


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


def _parse_job_date(discovered_at_raw: str = None) -> tuple[str, str]:
    """Returns (dmy_date, iso_date), e.g. ('14-10-2026', '2026-10-14')."""
    if discovered_at_raw:
        clean = str(discovered_at_raw).strip()
        if "T" in clean:
            date_part = clean.split("T")[0]
        elif " " in clean:
            date_part = clean.split(" ")[0]
        else:
            date_part = clean
        try:
            dt = datetime.strptime(date_part, "%Y-%m-%d")
            return dt.strftime("%d-%m-%Y"), dt.strftime("%Y-%m-%d")
        except Exception:
            pass
    now = datetime.now()
    return now.strftime("%d-%m-%Y"), now.strftime("%Y-%m-%d")


def _append_job_row(sheet, job_values: list, discovered_at_raw: str = None) -> bool:
    """
    Appends a job row under the categorized daily date layout.
    - If today's date block does not exist yet:
      Inserts a styled Date Header row: '📅 DD-MM-YYYY (ISO: YYYY-MM-DD)' with background color.
      First job has Date = 'DD-MM-YYYY'.
    - If today's date block already exists:
      Job has Date = '' (subsequent fields have no dates).
    """
    _ensure_headers(sheet)
    dmy_date, iso_date = _parse_job_date(discovered_at_raw)
    date_header_text = f"📅 {dmy_date} (ISO: {iso_date})"

    rows = sheet.get_all_values()

    # Check if the active (latest) date header in the sheet matches today's date
    today_header_exists = False
    for r in reversed(rows):
        if r and (date_header_text in r[0] or f"(ISO: {iso_date})" in r[0] or f"📅 {dmy_date}" in r[0]):
            today_header_exists = True
            break
        if r and r[0].startswith("📅 "):
            break

    if not today_header_exists:
        date_header_row = [date_header_text] + [""] * (len(HEADERS) - 1)
        sheet.append_row(date_header_row, value_input_option="USER_ENTERED")
        new_row_num = len(rows) + 1
        try:
            sheet.format(f"A{new_row_num}:M{new_row_num}", DATE_ROW_FORMAT)
        except Exception as e:
            print(f"Warning: Failed to format date header row {new_row_num}: {e}")
        job_values[0] = dmy_date
    else:
        job_values[0] = ""

    sheet.append_row(job_values, value_input_option="RAW")
    return True


def append_applied_job(card: dict):
    """Log a verified successful application to the categorized job sheet."""
    sheet = _get_sheet()
    job_values = [
        "",
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
    ]
    return _append_job_row(sheet, job_values, card.get("discovered_at"))


def append_external_job(card: dict):
    """Log an external application to the categorized job sheet."""
    sheet = _get_sheet()
    job_values = [
        "",
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
    ]
    return _append_job_row(sheet, job_values, card.get("discovered_at"))


def append_tailored_job(card: dict):
    """Log a tailored resume job to the categorized job sheet."""
    sheet = _get_sheet()
    job_values = [
        "",
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
    ]
    return _append_job_row(sheet, job_values, card.get("discovered_at"))


def reorganize_job_sheet(sheet=None):
    """
    Restructures Sheet1 into the categorized daily date layout:
    - Inserts a styled Date Header row for each day with background color.
    - Lists all jobs for that day underneath.
    - Only the first job has the date; subsequent jobs have blank date cells.
    - Preserves all top dashboard formulas (Total Jobs, Pending, Remote, Unique Companies).
    """
    if sheet is None:
        sheet = _get_sheet()

    rows = sheet.get_all_values()
    if len(rows) <= 5:
        return False

    dashboard_rows = [
        ["Job Application Tracker"],
        ["Total Jobs", "", "Pending Applications", "", "Remote Roles", "", "Unique Companies"],
        ['=COUNTIF(D6:D, "?*")', '', '=COUNTIF(I6:I, "PENDING")', '', '=COUNTIF(F6:F, "*Remote*")', '', '=COUNTUNIQUE(E6:E)'],
        [""],
        [
            "Date Added", "Platform", "Job ID", "Job Title", "Company",
            "Location", "Experience", "Job Link", "Status", "Notes",
            "JD Keywords", "Missing Keywords", "Tailored Resume Path",
        ],
    ]

    header_index = 4  # Row 5 (0-indexed 4)
    data_rows = rows[header_index + 1:]

    # Filter out existing date header rows if previously reorganized
    filtered_jobs = []
    for r in data_rows:
        if r and r[0].startswith("📅 "):
            continue
        if not any(str(c).strip() for c in r):
            continue
        filtered_jobs.append(r)

    # Group jobs chronologically by date
    groups = {}
    current_date = None
    for r in filtered_jobs:
        raw_date = r[0].strip() if r else ""
        if raw_date and not raw_date.startswith("📅 "):
            d_str = raw_date.split("T")[0].split(" ")[0]
            try:
                dt = datetime.strptime(d_str, "%Y-%m-%d")
                current_date = dt.strftime("%Y-%m-%d")
            except Exception:
                pass
        if not current_date:
            current_date = "2026-10-11"
        if current_date not in groups:
            groups[current_date] = []
        groups[current_date].append(r)

    new_rows = []
    date_row_indices = []
    current_row_num = 6

    for iso_date, jobs in groups.items():
        dt = datetime.strptime(iso_date, "%Y-%m-%d")
        dmy_date = dt.strftime("%d-%m-%Y")

        date_header_row = [f"📅 {dmy_date} (ISO: {iso_date})"] + [""] * 12
        new_rows.append(date_header_row)
        date_row_indices.append(current_row_num)
        current_row_num += 1

        for i, job in enumerate(jobs):
            j_copy = list(job[:13])
            while len(j_copy) < 13:
                j_copy.append("")
            if i == 0:
                j_copy[0] = dmy_date
            else:
                j_copy[0] = ""
            new_rows.append(j_copy)
            current_row_num += 1

    total_needed_rows = 5 + len(new_rows) + 20
    if sheet.row_count < total_needed_rows:
        sheet.resize(rows=total_needed_rows)

    # Clear old data range
    sheet.batch_clear([f"A6:M{max(sheet.row_count, len(rows) + 50)}"])

    # Update dashboard and headers
    sheet.update(range_name="A1:M5", values=dashboard_rows, value_input_option="USER_ENTERED")

    # Update data rows
    sheet.update(range_name=f"A6:M{5 + len(new_rows)}", values=new_rows, value_input_option="RAW")

    # Reset any old formatting on data rows
    try:
        sheet.format(f"A6:M{5 + len(new_rows)}", {
            "backgroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
            "textFormat": {"bold": False, "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0}, "fontSize": 10},
        })
    except Exception as e:
        print(f"Note: Could not reset data background: {e}")

    # Format Date Rows with soft executive blue background and navy bold text
    format_ranges = [f"A{idx}:M{idx}" for idx in date_row_indices]
    sheet.format(format_ranges, DATE_ROW_FORMAT)
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

