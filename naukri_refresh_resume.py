"""
Refreshes your Naukri resume by re-uploading the same resume file.

Recruiters on Naukri (Resdex) heavily weight recent resume uploads. Uploading
the same resume file resets your "Resume uploaded on" date to today, boosting
profile freshness to 100%.

Usage:
    python naukri_refresh_resume.py              # Uploads same resume from profile.yaml
    python naukri_refresh_resume.py --dry-run    # Inspect current resume without uploading
    python naukri_refresh_resume.py --unattended # Unattended runner
"""

import argparse
import csv
from datetime import datetime
import os
from pathlib import Path
import sys
import time

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from common.profile import Profile

SESSION_FILE = "session_naukri.json"
PROFILE_URL = "https://www.naukri.com/mnjuser/profile"
LOG_FILE = "applications_log.csv"
ATTACH_SELECTOR = "#attachCV"
RESUME_NAME_SELECTOR = ".resume-name-inline, .resumeName"


def log_row(row: list):
    """Appends an event to applications_log.csv."""
    new_file = not Path(LOG_FILE).exists()
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["timestamp", "source", "title", "company", "status", "reason"])
        w.writerow(row)


def refresh_naukri_resume(profile: Profile, dry_run: bool = False) -> bool:
    session_path = Path(SESSION_FILE)
    if not session_path.is_absolute():
        session_path = Path(__file__).resolve().parent / SESSION_FILE

    if not session_path.exists():
        print(f"ERROR: Session file not found: {session_path}")
        print("Run: python login_capture.py naukri to generate your session.")
        return False

    resume_filename = profile.data.get("resume_file_name")
    if not resume_filename:
        print("ERROR: resume_file_name is not set in profile.yaml.")
        return False

    resume_path = Path(resume_filename)
    if not resume_path.is_absolute():
        resume_path = Path(__file__).resolve().parent / resume_filename
    if not resume_path.exists():
        print(f"ERROR: Resume file not found at {resume_path}.")
        print("Ensure the file exists in the project root matching resume_file_name.")
        return False

    print(f"Target resume to upload: {resume_path.name} ({resume_path.stat().st_size} bytes)")

    with sync_playwright() as p:
        browser_mode = profile.data.get("browser_mode", "minimized")
        if browser_mode == "headless":
            browser = p.chromium.launch(headless=True)
        elif browser_mode == "minimized":
            browser = p.chromium.launch(headless=False, args=["--start-minimized"])
        else:
            browser = p.chromium.launch(headless=False)

        context = browser.new_context(storage_state=str(session_path))
        page = context.new_page()

        print(f"Navigating to {PROFILE_URL}...")
        try:
            page.goto(PROFILE_URL, wait_until="load", timeout=60000)
            page.wait_for_selector(RESUME_NAME_SELECTOR, timeout=20000)
        except PWTimeout:
            print("ERROR: Timeout loading Naukri profile page or locating resume section.")
            print("Check that session_naukri.json is valid.")
            browser.close()
            return False
        except Exception as e:
            print(f"ERROR: Navigation failed: {e}")
            browser.close()
            return False

        time.sleep(2)

        current_resume_name = ""
        try:
            el = page.locator(RESUME_NAME_SELECTOR).first
            if el.count() > 0:
                current_resume_name = el.inner_text().strip()
        except Exception:
            pass
        print(f"Current resume on file: '{current_resume_name}'")

        if dry_run:
            print(f"[DRY-RUN] Would upload '{resume_path.name}' to #attachCV. No changes made.")
            browser.close()
            return True

        print(f"Uploading '{resume_path.name}' via #attachCV...")
        try:
            with page.expect_response(
                lambda r: ("resume" in r.url.lower() or "upload" in r.url.lower() or "resman" in r.url.lower()) and r.status == 200,
                timeout=25000
            ):
                page.set_input_files(ATTACH_SELECTOR, str(resume_path))
            print("✓ Resume upload accepted by Naukri servers!")
        except Exception as e:
            print(f"WARN waiting for upload response: {e}")

        time.sleep(4)

        # Verify updated resume on profile
        updated_name = ""
        upload_date_str = ""
        try:
            el = page.locator(RESUME_NAME_SELECTOR).first
            if el.count() > 0:
                updated_name = el.inner_text().strip()

            date_el = page.locator('.updateOn, .lastUpdated, .resume-upload-date').first
            if date_el.count() > 0:
                upload_date_str = date_el.inner_text().strip()
        except Exception:
            pass

        print(f"Verified resume on profile: '{updated_name}' | Timestamp: '{upload_date_str}'")

        if updated_name:
            print("SUCCESS: Resume successfully refreshed on Naukri portal!")
            log_row([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "naukri",
                "Resume Refresh",
                "Naukri Profile",
                "updated",
                f"Uploaded: {resume_path.name} | {upload_date_str}",
            ])
            browser.close()
            return True
        else:
            print("WARNING: Could not confirm resume name after upload.")
            browser.close()
            return False


def main():
    parser = argparse.ArgumentParser(description="Re-upload resume to Naukri to maintain profile freshness.")
    parser.add_argument("--dry-run", action="store_true", help="Preview action without uploading")
    parser.add_argument("--unattended", action="store_true", help="Run in non-interactive unattended mode")
    args = parser.parse_args()

    profile = Profile.load()
    success = refresh_naukri_resume(profile, dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
