"""
Unified Google Sheets Manager & Bidirectional Sync Controller
Connects the Harvester (producer) and Universal ATS Applicant (consumer) to the live Google Sheet.
Handles:
- Writing external/unapplied jobs to the 'Apply Yourself' tab
- Fetching pending external jobs from the 'Apply Yourself' tab
- Updating application status back to the live sheet ('APPLIED', 'FAILED', 'PENDING_USER_APPLY')
- Local state caching in 'google_sheets_status.json' for resilience
"""
import io
import os
import csv
import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent
STATUS_CACHE_FILE = PROJECT_DIR / "google_sheets_status.json"
APPLICATIONS_LOG = PROJECT_DIR / "applications_log.csv"

# Credentials candidates in order of priority
CREDENTIALS_CANDIDATES = [
    PROJECT_DIR / "naukri-sheets-integration-42556bd602fd.json",
    PROJECT_DIR / "google_sheets_credentials.json",
]

DEFAULT_SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "15EFmeEcqtEJNqYDSYdL755534yc9RHqIsiIm7COa94I")
APPLY_YOURSELF_TAB = "Apply Yourself"
SHEET1_TAB = "Sheet1"

APPLY_YOURSELF_HEADERS = [
    "Date Added", "Platform", "Company", "Job Title", "Location",
    "Experience", "Direct Apply URL", "Tailored Resume Path",
    "Reason for Manual Action", "Status"
]


class SheetsManager:
    """Unified controller for all Google Sheets bidirectional operations."""

    _instance: Optional["SheetsManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SheetsManager, cls).__new__(cls)
            cls._instance._init_manager()
        return cls._instance

    def _init_manager(self):
        self.spreadsheet_id = self._get_env_spreadsheet_id()
        self.credentials_file = self._find_credentials_file()
        self._client = None
        self._spreadsheet = None

    def _get_env_spreadsheet_id(self) -> str:
        sid = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
        if sid:
            return sid
        env_file = PROJECT_DIR / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("GOOGLE_SHEETS_SPREADSHEET_ID="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        return DEFAULT_SPREADSHEET_ID

    def _find_credentials_file(self) -> Optional[Path]:
        for c in CREDENTIALS_CANDIDATES:
            if c.exists() and c.stat().st_size > 100:
                return c
        return None

    def get_client(self) -> Optional[gspread.Client]:
        if self._client is not None:
            return self._client
        if not self.credentials_file or not self.credentials_file.exists():
            return None
        try:
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(str(self.credentials_file), scopes=scopes)
            self._client = gspread.authorize(creds)
            return self._client
        except Exception as e:
            logger.warning(f"Failed to authorize Google Sheets client: {e}")
            return None

    def get_spreadsheet(self):
        if self._spreadsheet is not None:
            return self._spreadsheet
        client = self.get_client()
        if not client:
            return None
        try:
            self._spreadsheet = client.open_by_key(self.spreadsheet_id)
            return self._spreadsheet
        except Exception as e:
            logger.warning(f"Failed to open Google Spreadsheet {self.spreadsheet_id}: {e}")
            return None

    # --------------------------------------------------------------------------
    # Cache Management
    # --------------------------------------------------------------------------
    def load_status_cache(self) -> Dict[str, Dict[str, Any]]:
        """Loads locally cached statuses for 'Apply Yourself' rows."""
        if STATUS_CACHE_FILE.exists():
            try:
                with open(STATUS_CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not read status cache: {e}")
        return {}

    def save_status_cache(self, cache: Dict[str, Dict[str, Any]]):
        """Saves local status cache."""
        try:
            with open(STATUS_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save status cache: {e}")

    # --------------------------------------------------------------------------
    # Producer: Append Jobs
    # --------------------------------------------------------------------------
    def append_apply_yourself_job(self, job_data: dict) -> bool:
        """Appends an external / review-required job to 'Apply Yourself' tab."""
        from google_sheets_logger import append_apply_yourself_job as _legacy_append
        return _legacy_append(job_data)

    # --------------------------------------------------------------------------
    # Consumer: Fetch Pending Jobs
    # --------------------------------------------------------------------------
    def fetch_apply_yourself_jobs(self) -> Dict[str, Any]:
        """
        Fetches all rows from the 'Apply Yourself' tab via live CSV export or gspread.
        Overlays local status overrides and returns structured jobs and statistics.
        """
        tab = APPLY_YOURSELF_TAB
        sid = self.spreadsheet_id
        url = f"https://docs.google.com/spreadsheets/d/{sid}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(tab)}"

        content = None
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode("utf-8")
        except Exception as e:
            logger.warning(f"Live Google Sheet fetch failed via CSV URL ({e}). Attempting via gspread...")
            ss = self.get_spreadsheet()
            if ss:
                try:
                    sheet = ss.worksheet(tab)
                    rows = sheet.get_all_values()
                    if rows:
                        output = io.StringIO()
                        writer = csv.writer(output)
                        writer.writerows(rows)
                        content = output.getvalue()
                except Exception as gs_err:
                    logger.error(f"Failed gspread fetch: {gs_err}")

        if not content:
            # Fallback to local status cache if available
            cache = self.load_status_cache()
            cached_jobs = []
            for url_key, info in cache.items():
                cached_jobs.append({
                    "direct_apply_url": url_key,
                    "company": info.get("company", "Company"),
                    "job_title": info.get("job_title", "Software Developer"),
                    "status": info.get("status", "PENDING"),
                    "reason": info.get("reason", ""),
                    "tailored_resume_path": info.get("tailored_resume_path", ""),
                })
            return {
                "success": False,
                "error": "Could not connect to Google Sheets. Using cached records.",
                "jobs": cached_jobs,
                "stats": {"total": len(cached_jobs), "pending": len([j for j in cached_jobs if j['status'] == 'PENDING'])}
            }

        reader = csv.DictReader(io.StringIO(content))
        cache = self.load_status_cache()

        jobs = []
        stats = {"total": 0, "pending": 0, "applied": 0, "review_required": 0, "failed": 0}

        for idx, row in enumerate(reader, start=2):  # Row 1 is header
            direct_url = (row.get("Direct Apply URL") or "").strip()
            company = (row.get("Company") or "").strip()
            job_title = (row.get("Job Title") or "").strip()
            location = (row.get("Location") or "").strip()
            experience = (row.get("Experience") or "").strip()
            platform = (row.get("Platform") or "").strip()
            date_added = (row.get("Date Added") or "").strip()
            sheet_status = (row.get("Status") or "").strip()
            sheet_reason = (row.get("Reason for Manual Action") or "").strip()
            resume_path = (row.get("Tailored Resume Path") or "").strip()

            cache_entry = cache.get(direct_url) or cache.get(str(idx)) or {}
            local_status = cache_entry.get("status")
            local_reason = cache_entry.get("reason")
            local_timestamp = cache_entry.get("updated_at")

            if local_status:
                effective_status = local_status.upper()
                effective_reason = local_reason or sheet_reason
            elif sheet_status:
                effective_status = sheet_status.upper()
                effective_reason = sheet_reason
            else:
                effective_status = "PENDING"
                effective_reason = ""

            if effective_status in ("APPLIED", "SUCCESS"):
                norm_status = "APPLIED"
                stats["applied"] += 1
            elif effective_status in ("REVIEW_REQUIRED", "NEEDS_REVIEW", "PENDING_USER_APPLY"):
                norm_status = "PENDING" if effective_status == "PENDING_USER_APPLY" else "REVIEW_REQUIRED"
                if norm_status == "PENDING":
                    stats["pending"] += 1
                else:
                    stats["review_required"] += 1
            elif effective_status in ("FAILED", "ERROR"):
                norm_status = "FAILED"
                stats["failed"] += 1
            else:
                norm_status = "PENDING"
                stats["pending"] += 1

            stats["total"] += 1

            jobs.append({
                "row_index": idx,
                "company": company or "Unknown Company",
                "job_title": job_title or "Software Developer",
                "location": location,
                "experience": experience,
                "platform": platform,
                "direct_apply_url": direct_url,
                "date_added": date_added,
                "sheet_status": sheet_status,
                "status": norm_status,
                "reason": effective_reason,
                "tailored_resume_path": cache_entry.get("tailored_resume_path") or resume_path,
                "updated_at": local_timestamp or date_added,
            })

        return {
            "success": True,
            "sheet_id": sid,
            "tab_name": tab,
            "stats": stats,
            "jobs": jobs,
        }

    # --------------------------------------------------------------------------
    # Consumer: Update Job Status (Live Sheet + Local Cache)
    # --------------------------------------------------------------------------
    def update_job_status(
        self,
        direct_apply_url: str,
        status: str,
        reason: str = "",
        row_index: Optional[int] = None,
        company: str = "",
        job_title: str = "",
        tailored_resume_path: str = "",
    ) -> bool:
        """
        Updates the status for a given job URL:
        1. Saves locally in 'google_sheets_status.json'
        2. Logs to 'applications_log.csv'
        3. Updates the live Google Sheet cell (Row idx: Col 8 Resume, Col 9 Reason, Col 10 Status)
        """
        cache = self.load_status_cache()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = {
            "status": status.upper(),
            "reason": reason,
            "company": company,
            "job_title": job_title,
            "tailored_resume_path": tailored_resume_path,
            "updated_at": now_str,
            "row_index": row_index,
        }

        if direct_apply_url:
            cache[direct_apply_url] = entry
        if row_index:
            cache[str(row_index)] = entry

        self.save_status_cache(cache)

        # Append to applications_log.csv
        try:
            with open(APPLICATIONS_LOG, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([
                    datetime.now().isoformat(),
                    "apply_yourself_sync",
                    job_title or "Software Developer",
                    company or "Company",
                    status.lower(),
                    reason or direct_apply_url
                ])
        except Exception as e:
            logger.warning(f"Could not append to applications_log.csv: {e}")

        # Update live Google Sheet
        ss = self.get_spreadsheet()
        if ss:
            try:
                sheet = ss.worksheet(APPLY_YOURSELF_TAB)
                target_row = row_index

                # If row_index wasn't provided, find it by URL
                if not target_row and direct_url:
                    urls = sheet.col_values(7)  # Col 7 (G) is Direct Apply URL
                    for i, u in enumerate(urls, start=1):
                        if u.strip() == direct_apply_url.strip():
                            target_row = i
                            break

                if target_row and target_row > 1:
                    if tailored_resume_path:
                        sheet.update_cell(target_row, 8, tailored_resume_path)
                    if reason:
                        sheet.update_cell(target_row, 9, reason)
                    sheet.update_cell(target_row, 10, status.upper())
                    logger.info(f"Updated live Google Sheet row {target_row} to {status.upper()}")
                    return True
            except Exception as e:
                logger.error(f"Failed to update live Google Sheet: {e}")

        return False


_sheets_manager = None


def get_sheets_manager() -> SheetsManager:
    """Singleton accessor for SheetsManager."""
    global _sheets_manager
    if _sheets_manager is None:
        _sheets_manager = SheetsManager()
    return _sheets_manager
