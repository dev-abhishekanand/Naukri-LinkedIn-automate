from datetime import datetime, date
import os
import csv
import re
import time
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
        card.get("jd_keywords", ""),
        card.get("missing_keywords", ""),
        card.get("tailored_resume_path", ""),
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


def make_hyperlink_formula(url: str, label: str = None) -> str:
    """Formats a URL string as a Google Sheets =HYPERLINK formula so it is clickable."""
    if not url or not str(url).strip().startswith("http"):
        return url or ""
    clean = str(url).strip()
    escaped = clean.replace('"', '""')
    display_label = label.replace('"', '""') if label else escaped
    return f'=HYPERLINK("{escaped}", "{display_label}")'


def format_cell_rich_text_links(spreadsheet, sheet_id: int, row_index_0: int, col_index_0: int, text: str):
    """Applies clickable hyperlink formatting to any URLs embedded inside a multiline text cell."""
    if not text:
        return
    matches = list(re.finditer(r'(https?://[^\s\)\"]+)', text))
    if not matches:
        return
    runs = [{'startIndex': 0, 'format': {}}]
    for match in matches:
        u = match.group(1).rstrip(".,;")
        start = match.start(1)
        end = start + len(u)
        runs.append({
            'startIndex': start,
            'format': {
                'link': {'uri': u},
                'underline': True,
                'foregroundColor': {'blue': 0.8, 'red': 0.05, 'green': 0.2}
            }
        })
        runs.append({
            'startIndex': end,
            'format': {
                'underline': False,
                'foregroundColor': {'blue': 0.0, 'red': 0.0, 'green': 0.0}
            }
        })
    try:
        req = {
            'updateCells': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': row_index_0,
                    'endRowIndex': row_index_0 + 1,
                    'startColumnIndex': col_index_0,
                    'endColumnIndex': col_index_0 + 1
                },
                'rows': [{
                    'values': [{
                        'userEnteredValue': {'stringValue': text},
                        'textFormatRuns': runs
                    }]
                }],
                'fields': 'userEnteredValue,textFormatRuns'
            }
        }
        spreadsheet.batch_update({'requests': [req]})
    except Exception as e:
        print(f"Note: rich text link formatting: {e}")


LINKEDIN_REFERRAL_HEADERS = [
    "Date Requested", "Company", "Role", "Job / Posting Link",
    "Referrer Name", "Referrer Title", "Channel", "Status", "Message Preview"
]


def append_referral_request(data: dict) -> bool:
    """Appends a referral request row to 'LinkedIn Referral Requests' with active clickable hyperlinks."""
    try:
        ss = _get_spreadsheet()
        sheet = ss.worksheet("LinkedIn Referral Requests")
        
        job_url = data.get("job_url") or data.get("posting_link") or data.get("profile_url") or ""
        job_link_val = make_hyperlink_formula(job_url)
        message_text = data.get("message") or data.get("message_preview") or ""
        
        channel = data.get("channel") or data.get("type", "Connection Request With Note")
        if channel == "CONNECTION_REQUEST_WITH_NOTE":
            channel = "LinkedIn Connection Note"
        elif channel == "DIRECT_MESSAGE":
            channel = "LinkedIn Direct Message"
            
        row_values = [
            data.get("timestamp") or datetime.now().strftime("%d-%m-%Y %H:%M"),
            data.get("company", ""),
            data.get("role") or data.get("job_title", ""),
            job_link_val,
            data.get("name") or data.get("referrer_name", ""),
            data.get("headline") or data.get("referrer_title", "Software Engineer / Tech Lead"),
            channel,
            data.get("status", "SENT"),
            message_text,
        ]
        
        sheet.append_row(row_values, value_input_option="USER_ENTERED")
        
        # If message preview has an embedded URL, format it as a clickable rich-text link
        if message_text and ("http://" in message_text or "https://" in message_text):
            try:
                row_count = len(sheet.get_all_values())
                format_cell_rich_text_links(ss, sheet.id, row_count - 1, 8, message_text)
            except Exception:
                pass
                
        print(f"✓ Logged referral request to Google Sheets: {data.get('name')} for {data.get('role')} @ {data.get('company')}")
        return True
    except Exception as e:
        print(f"Warning: Failed to log referral request to Google Sheets: {e}")
        return False


LINKEDIN_HIRINGS_HEADERS = [
    "Date Added", "Target Role", "Recruiter / Poster", "Headline / Company",
    "HR Email", "Phone Number", "Post Link", "Outreach Status",
    "Notes / Outreach Subject", "Job / Post Content Preview"
]


def append_linkedin_hiring_lead(data: dict) -> bool:
    """Appends a discovered hiring post/lead to 'LinkedIn Hirings & Leads' with clickable links."""
    try:
        ss = _get_spreadsheet()
        sheet = ss.worksheet("LinkedIn Hirings & Leads")
        
        post_url = data.get("post_url") or data.get("href") or ""
        post_link_val = make_hyperlink_formula(post_url)
        content_text = data.get("content_preview") or data.get("notes") or ""
        
        row_values = [
            data.get("discovered_at") or datetime.now().strftime("%d-%m-%Y %H:%M"),
            data.get("role", "React Developer"),
            data.get("author") or data.get("poster", ""),
            data.get("headline") or data.get("company", ""),
            data.get("recipient_email", ""),
            data.get("phone", ""),
            post_link_val,
            data.get("status", "LEAD_DISCOVERED"),
            data.get("notes", ""),
            content_text,
        ]
        
        sheet.append_row(row_values, value_input_option="USER_ENTERED")
        if content_text and ("http://" in content_text or "https://" in content_text):
            try:
                row_count = len(sheet.get_all_values())
                format_cell_rich_text_links(ss, sheet.id, row_count - 1, 9, content_text)
            except Exception:
                pass
        return True
    except Exception as e:
        print(f"Warning: Failed to log hiring lead to Google Sheets: {e}")
        return False


def update_hiring_lead_status(identifier: str, new_status: str, notes: str = "") -> bool:
    """Updates status and notes for a lead in 'LinkedIn Hirings & Leads' by URL or HR email."""
    if not identifier:
        return False
    try:
        ss = _get_spreadsheet()
        sheet = ss.worksheet("LinkedIn Hirings & Leads")
        rows = sheet.get_all_values()
        if len(rows) <= 1:
            return False
        clean_id = identifier.strip().lower()
        for idx, r in enumerate(rows[1:], start=2):
            email_val = (r[4] if len(r) > 4 else "").strip().lower()
            link_val = (r[6] if len(r) > 6 else "").strip().lower()
            if clean_id in email_val or clean_id in link_val:
                sheet.update_cell(idx, 8, new_status)  # Column H: Status
                if notes:
                    sheet.update_cell(idx, 9, notes)   # Column I: Notes
                print(f"✓ Updated LinkedIn hiring lead ({identifier}) -> {new_status}")
                return True
        return False
    except Exception as e:
        print(f"Warning: Failed to update hiring lead status in Google Sheets: {e}")
        return False


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


# ==============================================================================
# DAILY APPLY METRICS (TAB: "Daily Apply Metrics")
# Tracks daily aggregates: Naukri Direct, LinkedIn Direct, External, Cold Emails
# ==============================================================================

DAILY_METRICS_SHEET_TITLE = "Daily Apply Metrics"

DAILY_METRICS_HEADERS = [
    "Date",
    "Naukri Direct Applied",
    "LinkedIn Direct Applied",
    "Total Direct Applied",
    "Naukri External / Tailored",
    "LinkedIn External / Manual",
    "Total External Logged",
    "Grand Total Processed",
    "Cold Outreach Emails",
    "Execution Status / Notes",
]

DAILY_HEADER_FORMAT = {
    "backgroundColor": {"red": 0.05, "green": 0.17, "blue": 0.45},  # Deep Navy Blue
    "textFormat": {
        "bold": True,
        "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},  # White
        "fontSize": 10,
    },
    "horizontalAlignment": "CENTER",
    "verticalAlignment": "MIDDLE",
}

TOTAL_DIRECT_FORMAT = {
    "backgroundColor": {"red": 0.90, "green": 0.96, "blue": 0.90},  # Soft mint green
    "textFormat": {"bold": True, "foregroundColor": {"red": 0.10, "green": 0.40, "blue": 0.15}},
    "horizontalAlignment": "CENTER",
}

GRAND_TOTAL_FORMAT = {
    "backgroundColor": {"red": 0.88, "green": 0.92, "blue": 0.99},  # Soft executive blue
    "textFormat": {"bold": True, "foregroundColor": {"red": 0.05, "green": 0.20, "blue": 0.50}},
    "horizontalAlignment": "CENTER",
}


def get_or_create_daily_metrics_sheet():
    """Gets or creates the 'Daily Apply Metrics' worksheet with executive formatting."""
    spreadsheet = _get_spreadsheet()
    try:
        sheet = spreadsheet.worksheet(DAILY_METRICS_SHEET_TITLE)
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=DAILY_METRICS_SHEET_TITLE, rows=150, cols=len(DAILY_METRICS_HEADERS))

    rows = sheet.get_all_values()
    if not rows or rows[0][:len(DAILY_METRICS_HEADERS)] != DAILY_METRICS_HEADERS:
        if not rows:
            sheet.append_row(DAILY_METRICS_HEADERS, value_input_option="USER_ENTERED")
        else:
            sheet.insert_row(DAILY_METRICS_HEADERS, index=1, value_input_option="USER_ENTERED")
        try:
            sheet.format("A1:J1", DAILY_HEADER_FORMAT)
            sheet.freeze(rows=1)
        except Exception as e:
            print(f"Warning: Failed to format header in {DAILY_METRICS_SHEET_TITLE}: {e}")
    return sheet


def compute_daily_counts(target_date_str: str = None) -> dict:
    """Computes application counts for a specific date (YYYY-MM-DD) from local logs."""
    if not target_date_str:
        target_date_str = date.today().isoformat()

    counts = {
        "naukri_direct": 0,
        "linkedin_direct": 0,
        "naukri_external": 0,
        "linkedin_external": 0,
        "cold_emails": 0,
    }

    # 1. Parse applications_log.csv
    app_log = Path(__file__).resolve().parent / "applications_log.csv"
    if app_log.exists():
        with open(app_log, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = (row.get("timestamp") or "").strip()
                if not ts or not ts.startswith(target_date_str):
                    continue
                source = (row.get("source") or "").lower()
                status = (row.get("status") or "").lower()
                reason = (row.get("reason") or "").lower()

                if status == "applied":
                    if "naukri" in source:
                        counts["naukri_direct"] += 1
                    elif "linkedin" in source:
                        counts["linkedin_direct"] += 1
                elif "external" in reason or status == "manual":
                    if "naukri" in source:
                        counts["naukri_external"] += 1
                    elif "linkedin" in source:
                        counts["linkedin_external"] += 1
                elif "linkedin" in source and status == "skipped":
                    counts["linkedin_external"] += 1

    # 2. Parse outreach_log.csv
    outreach_log = Path(__file__).resolve().parent / "outreach_log.csv"
    if outreach_log.exists():
        with open(outreach_log, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = (row.get("timestamp") or "").strip()
                if ts and ts.startswith(target_date_str):
                    counts["cold_emails"] += 1

    return counts


def record_daily_metrics(target_date_str: str = None, notes: str = "Automated Daily Run") -> bool:
    """Updates or appends a row for the target date in 'Daily Apply Metrics' tab."""
    if not target_date_str:
        target_date_str = date.today().isoformat()

    try:
        dt = datetime.strptime(target_date_str, "%Y-%m-%d")
        dmy_date = dt.strftime("%d-%m-%Y")
    except Exception:
        dmy_date = target_date_str

    counts = compute_daily_counts(target_date_str)
    
    # Resilient retry loop in case network is reconnecting after Mac wake
    sheet = None
    for attempt in range(1, 6):
        try:
            sheet = get_or_create_daily_metrics_sheet()
            break
        except Exception as e:
            if attempt == 5:
                raise
            print(f"[*] Network wait / retry {attempt}/5 for Google Sheets connection ({e})...")
            time.sleep(3)

    rows = []
    for attempt in range(1, 6):
        try:
            rows = sheet.get_all_values()
            break
        except Exception as e:
            if attempt == 5:
                raise
            print(f"[*] Network wait / retry {attempt}/5 reading rows ({e})...")
            time.sleep(3)

    # Search for existing date row (checking both DD-MM-YYYY and YYYY-MM-DD)
    existing_row_idx = None
    for idx, r in enumerate(rows, start=1):
        if r and len(r) > 0:
            val = r[0].strip()
            if val in [dmy_date, target_date_str]:
                existing_row_idx = idx
                break

    if existing_row_idx:
        row_num = existing_row_idx
        updated_values = [
            target_date_str,
            counts["naukri_direct"],
            counts["linkedin_direct"],
            f"=B{row_num}+C{row_num}",
            counts["naukri_external"],
            counts["linkedin_external"],
            f"=E{row_num}+F{row_num}",
            f"=D{row_num}+G{row_num}",
            counts["cold_emails"],
            notes,
        ]
        sheet.update(range_name=f"A{row_num}:J{row_num}", values=[updated_values], value_input_option="USER_ENTERED")
        print(f"✓ Updated Daily Apply Metrics row {row_num} for {target_date_str}")
    else:
        row_num = len(rows) + 1
        new_row = [
            target_date_str,
            counts["naukri_direct"],
            counts["linkedin_direct"],
            f"=B{row_num}+C{row_num}",
            counts["naukri_external"],
            counts["linkedin_external"],
            f"=E{row_num}+F{row_num}",
            f"=D{row_num}+G{row_num}",
            counts["cold_emails"],
            notes,
        ]
        sheet.append_row(new_row, value_input_option="USER_ENTERED")
        print(f"✓ Appended new Daily Apply Metrics row {row_num} for {dmy_date}")

    # Format totals cells
    try:
        sheet.format(f"D{row_num}", TOTAL_DIRECT_FORMAT)
        sheet.format(f"G{row_num}", TOTAL_DIRECT_FORMAT)
    except Exception as e:
        print(f"Note: Formatting cells D{row_num}:H{row_num}: {e}")

    return True


# ==============================================================================
# APPLY YOURSELF (TAB: "Apply Yourself")
# High-priority queue for external jobs requiring user review / manual submit
# ==============================================================================

APPLY_YOURSELF_SHEET_TITLE = "Apply Yourself"

APPLY_YOURSELF_HEADERS = [
    "Date Added",
    "Platform",
    "Company",
    "Job Title",
    "Location",
    "Experience",
    "Direct Apply URL",
    "Tailored Resume Path",
    "Reason for Manual Action",
    "Status",
]

APPLY_YOURSELF_HEADER_FORMAT = {
    "backgroundColor": {"red": 0.55, "green": 0.27, "blue": 0.07},  # Warm Executive Bronze/Amber
    "textFormat": {
        "bold": True,
        "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
        "fontSize": 10,
    },
    "horizontalAlignment": "CENTER",
    "verticalAlignment": "MIDDLE",
}


def get_or_create_apply_yourself_sheet():
    """Gets or creates the 'Apply Yourself' worksheet with executive formatting."""
    spreadsheet = _get_spreadsheet()
    try:
        sheet = spreadsheet.worksheet(APPLY_YOURSELF_SHEET_TITLE)
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=APPLY_YOURSELF_SHEET_TITLE, rows=200, cols=len(APPLY_YOURSELF_HEADERS))
        sheet.append_row(APPLY_YOURSELF_HEADERS, value_input_option="RAW")
        try:
            sheet.format("A1:J1", APPLY_YOURSELF_HEADER_FORMAT)
            sheet.freeze(rows=1)
        except Exception as e:
            print(f"Warning: Failed to format header row in Apply Yourself: {e}")
    return sheet


def append_apply_yourself_job(job_data: dict) -> bool:
    """Appends a job requiring manual action into 'Apply Yourself' tab with retry support."""
    apply_url = job_data.get("apply_url", "")
    if not apply_url or any(bad in apply_url.lower() for bad in ["/login", "signin", "fromsignin", "chrome-error"]):
        apply_url = job_data.get("job_url", "")
    row_values = [
        date.today().isoformat(),
        job_data.get("platform", "naukri"),
        job_data.get("company", ""),
        job_data.get("title", ""),
        job_data.get("location", ""),
        job_data.get("exp", ""),
        apply_url,
        job_data.get("tailored_resume_path", ""),
        job_data.get("reason", "Manual intervention needed"),
        "PENDING_USER_APPLY",
    ]

    for attempt in range(1, 4):
        try:
            sheet = get_or_create_apply_yourself_sheet()
            sheet.append_row(row_values, value_input_option="USER_ENTERED")
            print(f"✓ Added to 'Apply Yourself' tab: {job_data.get('title')} @ {job_data.get('company')}")
            return True
        except Exception as e:
            if attempt < 3:
                time.sleep(3)
            else:
                print(f"ERROR appending to Apply Yourself sheet: {e}")
                return False


def update_job_status_in_sheet1(job_id_or_url: str, new_status: str, notes: str = "", row_num: int = None) -> bool:
    """Finds a job by ID or URL in Sheet1 and updates its Status and Notes with retry support."""
    for attempt in range(1, 4):
        try:
            sheet = _get_sheet()
            if row_num and row_num > 1:
                sheet.update(range_name=f"I{row_num}:J{row_num}", values=[[new_status, notes]], value_input_option="USER_ENTERED")
                return True

            if not job_id_or_url:
                return False

            rows = sheet.get_all_values()
            for idx, r in enumerate(rows):
                if idx == 0:
                    continue
                curr_id = r[2].strip() if len(r) > 2 else ""
                curr_url = r[7].strip() if len(r) > 7 else ""
                if (job_id_or_url == curr_id) or (curr_url and (curr_url in job_id_or_url or job_id_or_url in curr_url)):
                    target_row = idx + 1
                    sheet.update(range_name=f"I{target_row}:J{target_row}", values=[[new_status, notes]], value_input_option="USER_ENTERED")
                    return True
            return False
        except Exception as e:
            if attempt < 3:
                time.sleep(3)
            else:
                print(f"WARN updating job status in Sheet1: {e}")
                return False


def backfill_daily_metrics_history():
    """Scans historical dates from applications_log.csv and populates 'Daily Apply Metrics'."""
    app_log = Path(__file__).resolve().parent / "applications_log.csv"
    if not app_log.exists():
        print("No applications_log.csv found.")
        return 0

    dates = set()
    with open(app_log, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = (row.get("timestamp") or "").strip()
            date_match = re.match(r"^(\d{4}-\d{2}-\d{2})", ts)
            if date_match:
                dates.add(date_match.group(1))

    sorted_dates = sorted(list(dates))
    print(f"Found {len(sorted_dates)} historical dates to sync: {sorted_dates}")
    for d in sorted_dates:
        record_daily_metrics(d, notes="Historical Application Sync")
    print(f"✓ Successfully synchronized all {len(sorted_dates)} dates into 'Daily Apply Metrics' tab!")
    return len(sorted_dates)


# ==============================================================================
# WEEKLY PROFILE AUDIT & REVAMP TRACKER (TAB: "Weekly Profile Audit")
# ==============================================================================

WEEKLY_AUDIT_SHEET_TITLE = "Weekly Profile Audit"

WEEKLY_AUDIT_HEADERS = [
    "Audit Date",
    "Naukri Primary (7D Searches)",
    "Primary Status",
    "Naukri Secondary (7D Searches)",
    "Secondary Status",
    "LinkedIn (7D Profile Views)",
    "LinkedIn Status",
    "Revamp Actions Taken",
    "Notes",
]

WEEKLY_AUDIT_HEADER_FORMAT = {
    "backgroundColor": {"red": 0.12, "green": 0.29, "blue": 0.53},  # Deep Navy Blue
    "textFormat": {
        "bold": True,
        "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
        "fontSize": 10,
    },
    "horizontalAlignment": "CENTER",
    "verticalAlignment": "MIDDLE",
}


def get_or_create_weekly_audit_sheet():
    """Gets or creates the 'Weekly Profile Audit' worksheet with executive styling."""
    spreadsheet = _get_spreadsheet()
    try:
        sheet = spreadsheet.worksheet(WEEKLY_AUDIT_SHEET_TITLE)
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=WEEKLY_AUDIT_SHEET_TITLE, rows=100, cols=len(WEEKLY_AUDIT_HEADERS))
        sheet.append_row(WEEKLY_AUDIT_HEADERS, value_input_option="RAW")
        try:
            sheet.format("A1:I1", WEEKLY_AUDIT_HEADER_FORMAT)
            sheet.freeze(rows=1)
        except Exception as e:
            print(f"Note: Header format error: {e}")
    return sheet


def append_weekly_audit_entry(audit_data: dict) -> bool:
    """Appends an individual profile audit and revamp decision row."""
    # Retry loop in case network is reconnecting
    for attempt in range(1, 4):
        try:
            sheet = get_or_create_weekly_audit_sheet()
            row = [
                audit_data.get("audit_date", date.today().isoformat()),
                audit_data.get("p1_searches", 0),
                audit_data.get("p1_status", "UNKNOWN"),
                audit_data.get("p2_searches", 0),
                audit_data.get("p2_status", "UNKNOWN"),
                audit_data.get("li_views", audit_data.get("li_searches", 0)),
                audit_data.get("li_status", "UNKNOWN"),
                audit_data.get("actions", "None"),
                audit_data.get("notes", "Weekly Automated Audit"),
            ]
            sheet.append_row(row, value_input_option="USER_ENTERED")
            return True
        except Exception as e:
            if attempt == 3:
                raise
            time.sleep(2)
    return False


def fetch_apply_yourself_jobs() -> dict:
    """Exposes unified SheetsManager fetch_apply_yourself_jobs."""
    from core.sheets_manager import get_sheets_manager
    return get_sheets_manager().fetch_apply_yourself_jobs()


def update_apply_yourself_status(
    direct_apply_url: str,
    status: str,
    reason: str = "",
    row_index: int = None,
    company: str = "",
    job_title: str = "",
    tailored_resume_path: str = ""
) -> bool:
    """Exposes unified SheetsManager update_job_status."""
    from core.sheets_manager import get_sheets_manager
    return get_sheets_manager().update_job_status(
        direct_apply_url=direct_apply_url,
        status=status,
        reason=reason,
        row_index=row_index,
        company=company,
        job_title=job_title,
        tailored_resume_path=tailored_resume_path
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Google Sheets Daily Apply Metrics Logger")
    parser.add_argument("--sync-today", action="store_true", help="Sync today's metrics to Google Sheets")
    parser.add_argument("--backfill", action="store_true", help="Backfill historical daily metrics from logs")
    parser.add_argument("--date", type=str, help="Specific date to sync (YYYY-MM-DD)")
    args = parser.parse_args()

    if args.backfill:
        backfill_daily_metrics_history()
    elif args.sync_today or args.date:
        record_daily_metrics(args.date)
    else:
        parser.print_help()


