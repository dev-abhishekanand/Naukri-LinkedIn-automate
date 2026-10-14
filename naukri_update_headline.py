"""
Updates the Naukri Resume Headline on a daily basis.

Recruiters on Naukri frequently sort candidates by "Last Active" or "Profile Updated Date".
Updating the resume headline timestamps the profile as "Updated: Today", significantly
boosting visibility in recruiter search queries (Resdex).

Usage:
    python naukri_update_headline.py              # Automatically picks today's headline and updates
    python naukri_update_headline.py --dry-run    # Inspect current headline and preview today's text
    python naukri_update_headline.py --headline "Custom Headline Text"
"""

import argparse
import csv
from datetime import datetime
from pathlib import Path
import sys
import time

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from common.profile import Profile

SESSION_FILE = "session_naukri.json"
PROFILE_URL = "https://www.naukri.com/mnjuser/profile"
LOG_FILE = "applications_log.csv"

# High-impact curated headline pool (Monday to Sunday) if not provided in profile.yaml.
# All strictly <= 250 characters.
DEFAULT_HEADLINE_POOL = [
    # Monday
    "React Developer | Frontend & Full Stack Engineer | React.js, Next.js, TypeScript, Tailwind | 3.5+ Years | Remote | Immediate Joiner",
    # Tuesday
    "Frontend Developer | React.js, Next.js, TypeScript | UI Engineer | Modern Web Apps | 3.5+ Years Exp | Immediate Joiner",
    # Wednesday
    "React.js Developer | Frontend Engineer | Redux, Next.js, Tailwind CSS | 3.5+ Years Exp | Immediate Joiner",
    # Thursday
    "Full Stack JavaScript Developer | React, Node.js, TypeScript | 3.5+ Yrs Exp | Remote | Available Immediately",
    # Friday
    "Senior Frontend Engineer | React Developer | TypeScript, Next.js, Performance & UI | 3.5+ Years | Immediate Joiner",
    # Saturday
    "React Developer | Frontend Engineer | Next.js, TypeScript, REST & GraphQL APIs | 3.5+ Yrs | Immediate Joiner",
    # Sunday
    "Frontend Engineer | React.js, TypeScript, Next.js Developer | Scalable Web Apps | 3.5+ Years | Immediate Joiner",
]


def log_row(row: list):
    """Appends an event to applications_log.csv."""
    new_file = not Path(LOG_FILE).exists()
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["timestamp", "source", "title", "company", "status", "reason"])
        w.writerow(row)


def select_headline(profile: Profile, current_headline: str = "", override_headline: str | None = None) -> str:
    """Selects the best headline for today, guaranteeing a genuine change from current."""
    if override_headline:
        target = override_headline.strip()
        if len(target) > 250:
            target = target[:250]
        return target

    pool = profile.data.get("naukri_headline_pool") or DEFAULT_HEADLINE_POOL
    if not isinstance(pool, list) or len(pool) == 0:
        pool = DEFAULT_HEADLINE_POOL

    weekday = datetime.now().weekday()  # 0 = Monday, ..., 6 = Sunday
    candidate = pool[weekday % len(pool)].strip()

    # Anti-no-op check: if candidate matches current, rotate to the next one
    if candidate.lower() == current_headline.lower():
        candidate = pool[(weekday + 1) % len(pool)].strip()

    # If still matching (e.g. single item pool), slightly alter trailing text
    if candidate.lower() == current_headline.lower():
        if "Immediate Joiner" in candidate:
            candidate = candidate.replace("Immediate Joiner", "Available Immediately")
        elif "Available Immediately" in candidate:
            candidate = candidate.replace("Available Immediately", "Immediate Joiner")
        elif candidate.endswith("."):
            candidate = candidate[:-1]
        else:
            candidate = candidate + "."

    if len(candidate) > 250:
        candidate = candidate[:250]

    return candidate


def update_naukri_headline(profile: Profile, override_headline: str | None = None, dry_run: bool = False) -> bool:
    session_path = Path(SESSION_FILE)
    if not session_path.is_absolute():
        session_path = Path(__file__).resolve().parent / SESSION_FILE

    if not session_path.exists():
        print(f"ERROR: Session file not found: {session_path}")
        print("Run: python login_capture.py naukri to generate your session.")
        return False

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
            page.wait_for_selector('.resumeHeadline', timeout=20000)
        except PWTimeout:
            print("ERROR: Timeout loading Naukri profile page or finding .resumeHeadline.")
            print("Your session in session_naukri.json may have expired. Re-authenticate via login_capture.py naukri.")
            browser.close()
            return False
        except Exception as e:
            print(f"ERROR: Navigation failed: {e}")
            browser.close()
            return False

        time.sleep(2)

        # 1. Read current headline
        current_headline = ""
        try:
            headline_el = page.locator('.resumeHeadline .widgetCont .prefill').first
            if headline_el.count() > 0:
                current_headline = headline_el.inner_text().strip()
        except Exception as e:
            print(f"Warning: Could not read current headline: {e}")

        print(f"Current Headline:\n  '{current_headline}'")

        target_headline = select_headline(profile, current_headline, override_headline)
        print(f"Target Headline (length {len(target_headline)}/250):\n  '{target_headline}'")

        if dry_run:
            print("[DRY-RUN] No changes saved.")
            browser.close()
            return True

        if current_headline == target_headline:
            print("Headline is already up to date. No changes needed.")
            browser.close()
            return True

        # 2. Click Edit button
        print("Opening Resume Headline edit form...")
        try:
            edit_btn = page.locator('.resumeHeadline .widgetHead span.edit, [aria-label="Edit resume headline"]').first
            edit_btn.click(timeout=10000)
            page.wait_for_selector('form[name="resumeHeadlineForm"], textarea#resumeHeadlineTxt', timeout=10000)
        except PWTimeout:
            print("ERROR: Edit button or headline form not found.")
            browser.close()
            return False

        time.sleep(1)

        # 3. Enter new headline
        print("Writing new headline...")
        try:
            textarea = page.locator('textarea#resumeHeadlineTxt').first
            textarea.fill("")
            textarea.fill(target_headline)
            time.sleep(1)
        except Exception as e:
            print(f"ERROR: Failed writing to textarea: {e}")
            browser.close()
            return False

        # 4. Save form
        print("Saving updated headline...")
        try:
            save_btn = page.locator('form[name="resumeHeadlineForm"] button[type="submit"]').first
            save_btn.click(timeout=10000)
            time.sleep(3)
        except Exception as e:
            print(f"ERROR: Failed to click Save button: {e}")
            browser.close()
            return False

        # 5. Verify update on profile
        updated_headline = ""
        try:
            updated_el = page.locator('.resumeHeadline .widgetCont .prefill').first
            if updated_el.count() > 0:
                updated_headline = updated_el.inner_text().strip()
        except Exception:
            pass

        print(f"Live Profile Headline after update:\n  '{updated_headline}'")

        if updated_headline == target_headline:
            print("SUCCESS: Resume headline successfully updated and confirmed on Naukri!")
            log_row([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "naukri",
                "Resume Headline",
                "Naukri Profile",
                "updated",
                f"Updated to: {target_headline[:80]}...",
            ])
            browser.close()
            return True
        else:
            print("WARNING: Live headline does not match target. It may take a moment to refresh.")
            log_row([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "naukri",
                "Resume Headline",
                "Naukri Profile",
                "unverified_update",
                f"Target: {target_headline[:80]}...",
            ])
            browser.close()
            return True


def main():
    parser = argparse.ArgumentParser(description="Update Naukri Resume Headline on a daily basis.")
    parser.add_argument("--headline", type=str, default=None, help="Explicit headline text to set")
    parser.add_argument("--dry-run", action="store_true", help="Preview today's headline without saving")
    parser.add_argument("--unattended", action="store_true", help="Run in non-interactive unattended mode")
    args = parser.parse_args()

    profile = Profile.load()
    success = update_naukri_headline(profile, override_headline=args.headline, dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
