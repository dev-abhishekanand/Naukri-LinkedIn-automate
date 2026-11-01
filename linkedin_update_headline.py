"""
Updates the LinkedIn Profile Headline on a daily basis.

LinkedIn's Recruiter algorithm heavily favors recently updated and active candidates.
Updating the headline daily signals member activity, keeping the profile fresh and
surfacing higher in recruiter search results and Spotlights ("More likely to respond").

Usage:
    python linkedin_update_headline.py              # Automatically picks today's headline and updates
    python linkedin_update_headline.py --dry-run    # Preview today's headline without opening browser
    python linkedin_update_headline.py --headline "Custom Headline Text"
    python linkedin_update_headline.py --unattended # Headless/minimized for scheduler
"""

import argparse
import csv
from datetime import datetime
from pathlib import Path
import sys
import time

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from common.browser_factory import launch_chrome_browser

from common.profile import Profile

SESSION_FILE = "session_linkedin.json"
INTRO_EDIT_URL = "https://www.linkedin.com/in/abhishekreactdeveloper/edit/intro/"
LOG_FILE = "applications_log.csv"

# High-impact curated LinkedIn headline pool (Monday to Sunday)
# All strictly <= 220 characters (LinkedIn headline limit).
DEFAULT_LINKEDIN_HEADLINE_POOL = [
    # Monday: Core Frontend & Full Stack
    "React Developer | Frontend Engineer | React.js, Next.js, TypeScript, Tailwind | 3.5+ Yrs | Immediate Joiner",
    # Tuesday: UI Engineering & Modern Web Apps
    "Frontend Developer | React.js, Next.js, TypeScript | UI Engineer | Modern Web Apps | 3.5+ Yrs Exp | Immediate Joiner",
    # Wednesday: State Management & Modern Stack
    "React.js Developer | Frontend Engineer | Redux Toolkit, Next.js, REST & GraphQL | 3.5+ Yrs | Available Immediately",
    # Thursday: Scalable Architecture & Performance
    "Frontend Engineer | React, Next.js, TypeScript | Scalable UI Architectures & Performance | 3.5+ Yrs | Immediate Joiner",
    # Friday: Senior Frontend Specialist
    "Senior Frontend Engineer | React Developer | TypeScript, Next.js, UI/UX & Clean Code | 3.5+ Yrs | Immediate Joiner",
    # Saturday: API Integration & Data Layer
    "React Developer | Frontend Specialist | Next.js, TypeScript, TanStack Query, Tailwind | 3.5+ Yrs | Immediate Joiner",
    # Sunday: Web Apps & State Architecture
    "Frontend Engineer | React.js, TypeScript, Next.js Developer | UI Engineering & State Management | Immediate Joiner",
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
        if len(target) > 220:
            target = target[:220]
        return target

    pool = profile.data.get("linkedin_headline_pool") or DEFAULT_LINKEDIN_HEADLINE_POOL
    if not isinstance(pool, list) or len(pool) == 0:
        pool = DEFAULT_LINKEDIN_HEADLINE_POOL

    weekday = datetime.now().weekday()  # 0 = Monday, ..., 6 = Sunday
    candidate = pool[weekday % len(pool)].strip()

    # Anti-no-op check: if candidate matches current, rotate to the next one
    if candidate.lower() == current_headline.lower():
        candidate = pool[(weekday + 1) % len(pool)].strip()

    # If still matching, toggle suffix
    if candidate.lower() == current_headline.lower():
        if "Immediate Joiner" in candidate:
            candidate = candidate.replace("Immediate Joiner", "Available Immediately")
        elif "Available Immediately" in candidate:
            candidate = candidate.replace("Available Immediately", "Immediate Joiner")
        elif candidate.endswith("."):
            candidate = candidate[:-1]
        else:
            candidate = candidate + "."

    if len(candidate) > 220:
        candidate = candidate[:220]

    return candidate


def update_linkedin_headline(profile: Profile, override_headline: str | None = None, dry_run: bool = False, headless: bool = False) -> bool:
    session_path = Path(SESSION_FILE)
    if not session_path.is_absolute():
        session_path = Path(__file__).resolve().parent / SESSION_FILE

    if not session_path.exists():
        print(f"ERROR: Session file not found at {session_path}")
        print("Please run login_capture.py to save your LinkedIn session first.")
        return False

    # Dry-run preview
    if dry_run:
        target_headline = select_headline(profile, override_headline=override_headline)
        print("=== DRY RUN: LinkedIn Headline Update ===")
        print(f"Target Headline ({len(target_headline)}/220 chars):")
        print(f"  \"{target_headline}\"")
        return True

    print("\n[LinkedIn Headline] Starting automated daily headline rotation...")

    with sync_playwright() as p:
        browser_args = []
        browser_mode = profile.browser_mode if not headless else "headless"
        if browser_mode == "minimized":
            browser_args.append("--start-minimized")

        is_headless = (browser_mode == "headless")

        browser = launch_chrome_browser(p, browser_mode=browser_mode, extra_args=browser_args)
        context = browser.new_context(storage_state=str(session_path))
        page = context.new_page()

        try:
            print(f"[LinkedIn Headline] Navigating to intro edit page...")
            try:
                page.goto(INTRO_EDIT_URL, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                pass
            time.sleep(2)

            # Check if redirected to login
            if "login" in page.url.lower() or "checkpoint" in page.url.lower():
                print("ERROR: LinkedIn session expired or requires login verification.")
                return False

            # Wait for modal dialog (supports both new native <dialog> and legacy .artdeco-modal)
            modal = None
            for m_sel in ["dialog[open]", "dialog", ".artdeco-modal", "[role=\"dialog\"]"]:
                try:
                    m = page.locator(m_sel).first
                    if m.is_visible(timeout=5000):
                        modal = m
                        break
                except Exception:
                    continue

            # If modal not already visible after direct navigation, try clicking the Edit Intro button
            if not modal or modal.count() == 0:
                for btn_sel in [
                    "button[aria-label*=\"Edit intro\"]",
                    "button[aria-label*=\"edit intro\"]",
                    "a[href*=\"/edit/intro\"]",
                    "section.artdeco-card button[aria-label*=\"Edit\"]"
                ]:
                    try:
                        edit_btn = page.locator(btn_sel).first
                        if edit_btn.is_visible(timeout=2000):
                            print(f"[LinkedIn Headline] Clicking edit intro trigger: {btn_sel}")
                            edit_btn.click()
                            time.sleep(3)
                            modal = page.locator("dialog[open], dialog, .artdeco-modal, [role=\"dialog\"]").first
                            break
                    except Exception:
                        continue

            # Wait for editor using multiple fallback locators with wait_for
            editor = None
            editor_selectors = [
                "dialog [contenteditable=\"true\"]",
                "dialog .tiptap.ProseMirror",
                "dialog .ProseMirror",
                "[role=\"dialog\"] [contenteditable=\"true\"]",
                ".tiptap.ProseMirror[contenteditable=\"true\"]",
                ".ProseMirror[contenteditable=\"true\"]",
                "[role=\"textbox\"][contenteditable=\"true\"]",
                "div[contenteditable=\"true\"]",
                "textarea[id*=\"headline\"]",
                "input[id*=\"headline\"]"
            ]

            for sel in editor_selectors:
                try:
                    loc = page.locator(sel).first
                    loc.wait_for(state="visible", timeout=10000)
                    editor = loc
                    break
                except Exception:
                    continue

            if not editor:
                print("ERROR: Headline editor (.ProseMirror/tiptap) not found on edit intro page.")
                page.screenshot(path="debug_screenshots/linkedin_headline_error.png")
                return False

            editor.scroll_into_view_if_needed()
            time.sleep(0.5)

            current_headline = (editor.inner_text() or "").strip()
            print(f"[LinkedIn Headline] Current headline ({len(current_headline)} chars):")
            print(f"  \"{current_headline}\"")

            target_headline = select_headline(profile, current_headline=current_headline, override_headline=override_headline)

            if current_headline == target_headline:
                print("[LinkedIn Headline] Headline is already set to the target. No update needed.")
                return True

            print(f"\n[LinkedIn Headline] Setting new headline ({len(target_headline)} chars):")
            print(f"  \"{target_headline}\"")

            # Click editor, select all, clear, and type new headline
            editor.click()
            time.sleep(0.5)
            # Use Meta+A on Mac, Control+A elsewhere
            select_key = "Meta+A" if sys.platform == "darwin" else "Control+A"
            page.keyboard.press(select_key)
            page.keyboard.press("Backspace")
            time.sleep(0.3)

            # Double check if cleared, fallback to JavaScript textContent reset if needed
            remaining = (editor.inner_text() or "").strip()
            if remaining:
                editor.evaluate("el => { el.innerText = ''; el.innerHTML = '<p><br></p>'; }")
                time.sleep(0.3)

            # Type sequentially to trigger ProseMirror input events
            editor.press_sequentially(target_headline, delay=12)
            time.sleep(1)

            # Find and click the Save button with multiple fallback locators
            save_btn = None
            save_selectors = [
                "dialog button:has-text(\"Save\")",
                "dialog footer button:has-text(\"Save\")",
                "button:has-text(\"Save\")",
                "footer button:has-text(\"Save\")",
                "button[data-view-name*=\"save\"]",
                ".artdeco-modal button:has-text(\"Save\")",
                "button.artdeco-button--primary:has-text(\"Save\")"
            ]
            for s_sel in save_selectors:
                try:
                    btn = page.locator(s_sel).first
                    btn.wait_for(state="visible", timeout=5000)
                    save_btn = btn
                    break
                except Exception:
                    continue

            if not save_btn:
                print("ERROR: Save button not found on modal.")
                page.screenshot(path="debug_screenshots/linkedin_headline_save_error.png")
                return False

            save_btn.scroll_into_view_if_needed()
            time.sleep(0.5)
            save_btn.click()
            print("[LinkedIn Headline] Save clicked. Waiting for save confirmation...")

            # Strictly verify modal dialog is closed / dismissed via browser evaluation
            try:
                page.wait_for_function(
                    "() => !document.querySelector('dialog[open]') && !document.querySelector('.artdeco-modal')",
                    timeout=10000
                )
                print("✓ [LinkedIn Headline] Modal dismissed, headline update confirmed on LinkedIn!")
            except Exception:
                # If still open, check if an error occurred inside the modal
                err_text = page.locator("dialog .artdeco-inline-feedback--error, dialog [role=\"alert\"], .artdeco-modal [role=\"alert\"]").first
                if err_text.is_visible(timeout=1000):
                    err_msg = err_text.inner_text().strip()
                    print(f"ERROR: LinkedIn rejected headline update: {err_msg}")
                    page.screenshot(path="debug_screenshots/linkedin_headline_rejected.png")
                    return False
                print("[LinkedIn Headline] Dialog closed or transitioned.")

            # Log to applications_log.csv
            log_row([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "linkedin_headline",
                target_headline[:80],
                "LinkedIn",
                "updated",
                f"Rotated headline ({len(target_headline)} chars)"
            ])

            return True

        except PWTimeout:
            print("ERROR: Timeout during LinkedIn headline update.")
            page.screenshot(path="debug_screenshots/linkedin_headline_timeout.png")
            return False
        except Exception as e:
            print(f"ERROR: Unexpected error updating LinkedIn headline: {e}")
            page.screenshot(path="debug_screenshots/linkedin_headline_fail.png")
            return False
        finally:
            try:
                context.close()
                browser.close()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="Rotate LinkedIn Profile Headline daily.")
    parser.add_argument("--dry-run", action="store_true", help="Preview today's headline without changing it")
    parser.add_argument("--headline", type=str, default=None, help="Explicit headline text to set")
    parser.add_argument("--unattended", action="store_true", help="Run unattended (minimized/headless)")
    args = parser.parse_args()

    profile = Profile.load()

    success = update_linkedin_headline(
        profile,
        override_headline=args.headline,
        dry_run=args.dry_run,
        headless=args.unattended
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
