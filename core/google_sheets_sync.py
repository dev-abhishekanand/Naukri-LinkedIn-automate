"""
Google Sheets Sync Bridge Module
Maintains 100% backward compatibility with core/google_sheets_sync calls,
routing directly to the unified core/sheets_manager.py.
"""
from typing import Dict, Any, Optional
from core.sheets_manager import get_sheets_manager

_manager = get_sheets_manager()


def load_status_cache() -> Dict[str, Dict[str, Any]]:
    return _manager.load_status_cache()


def save_status_cache(cache: Dict[str, Dict[str, Any]]):
    _manager.save_status_cache(cache)


def fetch_sheet_jobs(
    sheet_id: Optional[str] = None,
    tab_name: Optional[str] = None
) -> Dict[str, Any]:
    return _manager.fetch_apply_yourself_jobs()


def update_job_status(
    direct_apply_url: str,
    status: str,
    reason: str = "",
    row_index: Optional[int] = None,
    company: str = "",
    job_title: str = "",
    tailored_resume_path: str = ""
):
    return _manager.update_job_status(
        direct_apply_url=direct_apply_url,
        status=status,
        reason=reason,
        row_index=row_index,
        company=company,
        job_title=job_title,
        tailored_resume_path=tailored_resume_path
    )
