#!/usr/bin/env python3
"""
LinkedIn Matched Profile Jobs Auto-Apply & Google Sheets Sync Engine
Scrapes and processes ALL jobs under LinkedIn's 'Jobs that match your profile' section:
1. Navigates to LinkedIn's Matched Jobs Collection (https://www.linkedin.com/jobs/collections/recommended/)
2. Harvests all available matched job postings across all pagination pages (e.g. ~240+ jobs).
3. For every job:
   - If 'Easy Apply' is available: Automatically generates an ATS-tailored resume, completes screening questions,
     submits the application, and logs it to Google Sheets ('Sheet1' Applied).
   - If 'Easy Apply' is NOT available (External Portal) OR if application requires manual review:
     Captures external application URL, links the tailored ATS resume, and logs it to Google Sheets
     ('Sheet1' & 'Apply Yourself' tabs) so no opportunities are lost.
4. Operates with stealth Chrome settings, rate-limiting, and error-resilient recovery.
"""

import os
import sys
import re
import csv
import json
import time
import argparse
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any, Optional

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from common.browser_factory import launch_chrome_browser, create_stealth_context
from common.profile import Profile
from location_filter import is_india_job
from common.ats_pipeline import prepare_tailored_resume
from google_sheets_logger import (
    append_applied_job,
    append_external_job,
    append_apply_yourself_job,
    external_job_url_exists,
)

SESSION_FILE = PROJECT_DIR / "session_linkedin.json"
STATE_FILE = PROJECT_DIR / ".linkedin_matched_jobs_processed.json"
SUMMARY_FILE = PROJECT_DIR / "linkedin_matched_jobs_summary.json"
APPLICATIONS_LOG = PROJECT_DIR / "applications_log.csv"
EXTERNAL_LOG = PROJECT_DIR / "external_jobs.csv"

STOP_PHRASES = [
    "easy apply limit", "unusual activity", "verify it's you",
    "captcha", "security verification", "we've restricted",
    "checkpoint challenge"
]


class SkipJob(Exception):
    pass


def load_processed_state() -> Dict[str, Any]:
    """Loads cache of already processed job IDs to ensure idempotency."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"applied": [], "external_logged": [], "skipped_foreign": [], "history": []}


def save_processed_state(state: Dict[str, Any]):
    """Persists processed state cache."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Note: Could not save processed state: {e}")


def close_modal(page):
    """Safely dismisses any open modal or dialog."""
    try:
        dismiss_btn = page.locator(
            'button[aria-label="Dismiss"], button[data-test-modal-close-btn], button[aria-label="Close"]'
        ).first
        if dismiss_btn.is_visible():
            dismiss_btn.click()
            time.sleep(1)
        else:
            page.keyboard.press("Escape")
            time.sleep(1)

        discard_btn = page.locator(
            'button[data-control-name="discard_application_confirm_btn"], button:has-text("Discard")'
        ).first
        if discard_btn.is_visible():
            discard_btn.click()
            time.sleep(1)
    except Exception:
        pass


def check_stop_signals(page) -> Optional[str]:
    """Checks page for security or rate limiting blocks."""
    try:
        text = page.inner_text("body").lower()
        for phrase in STOP_PHRASES:
            if phrase in text:
                return phrase
        if "/checkpoint/" in page.url or "/login" in page.url:
            return "session expired / checkpoint challenge"
    except Exception:
        pass
    return None


def extract_job_details(page, card: dict) -> dict:
    """Extracts enriched title, company, location, and description from the job view page."""
    details = dict(card)
    try:
        page_info = page.evaluate("""
            () => {
                const title = document.querySelector('h1, .job-details-jobs-unified-top-card__job-title, .jobs-unified-top-card__job-title')?.innerText?.trim();
                const company = document.querySelector('.job-details-jobs-unified-top-card__company-name, .jobs-unified-top-card__company-name, .topcard__org-name-link')?.innerText?.trim();
                const location = document.querySelector('.job-details-jobs-unified-top-card__bullet, .jobs-unified-top-card__bullet, .topcard__flavor--bullet, .job-details-jobs-unified-top-card__workplace-type')?.innerText?.trim();
                const jd = document.querySelector('.jobs-description__content, .jobs-box__html-content, .job-details-jobs-unified-top-card__content')?.innerText?.trim() || '';
                return { title, company, location, jd };
            }
        """)
        if page_info:
            if page_info.get("title"):
                details["title"] = page_info["title"]
            if page_info.get("company"):
                details["company"] = page_info["company"]
            if page_info.get("location"):
                details["location"] = page_info["location"]
            details["jd_text"] = page_info.get("jd", "")
    except Exception as e:
        print(f"  Note during job details extraction: {e}")

    if not details.get("jobId"):
        match = re.search(r'/jobs/view/(\d+)', details.get("href", ""))
        details["jobId"] = match.group(1) if match else ""

    return details


def fill_form_inputs(page, profile: Profile, tailored_resume_path: str = ""):
    """
    Intelligently fills screening questions in LinkedIn Easy Apply modal:
    - Text inputs (phone, years experience, notice period, expected salary)
    - Radio buttons (authorization = Yes, sponsorship = No, relocation = Yes)
    - Select dropdowns
    - File upload (tailored ATS resume)
    """
    answers = profile.answer_library()

    # 1. Fill Text & Numeric Fields via JS
    page.evaluate("""
        ([phone, email, expYears, noticeDays]) => {
            const inputs = document.querySelectorAll('.jobs-easy-apply-modal input, [role="dialog"] input, .jobs-easy-apply-modal textarea, [role="dialog"] textarea');
            inputs.forEach(el => {
                if (el.type === 'hidden' || el.type === 'file' || el.type === 'radio' || el.type === 'checkbox') return;
                const val = (el.value || '').trim();
                
                // Get label or placeholder text
                let labelText = '';
                if (el.id) {
                    const lbl = document.querySelector(`label[for="${el.id}"]`);
                    if (lbl) labelText = lbl.innerText.toLowerCase();
                }
                if (!labelText) {
                    labelText = (el.getAttribute('aria-label') || el.placeholder || '').toLowerCase();
                }

                // Phone
                if (!val && (labelText.includes('phone') || labelText.includes('mobile') || labelText.includes('contact'))) {
                    el.value = phone;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }
                // Email
                else if (!val && labelText.includes('email')) {
                    el.value = email;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }
                // Years of experience (React / Frontend / JavaScript / General)
                else if (!val && (labelText.includes('year') || labelText.includes('experience') || labelText.includes('how many'))) {
                    el.value = expYears;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }
                // Notice Period
                else if (!val && (labelText.includes('notice') || labelText.includes('how soon') || labelText.includes('joining'))) {
                    el.value = "0";
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }
                // Salary / CTC
                else if (!val && (labelText.includes('ctc') || labelText.includes('salary') || labelText.includes('compensation') || labelText.includes('expected'))) {
                    el.value = "1400000";
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }
                // City / Location
                else if (!val && (labelText.includes('city') || labelText.includes('location'))) {
                    el.value = "Bengaluru";
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }
            });
        }
    """, [
        answers.get("phone", "+91-8839617601"),
        answers.get("email", "abhishek.anand.7601@gmail.com"),
        answers.get("years_experience", "3.5"),
        "0"
    ])

    # 2. Handle Radio Buttons (Yes/No questions)
    page.evaluate("""
        () => {
            const fieldsets = document.querySelectorAll('.jobs-easy-apply-modal fieldset, [role="dialog"] fieldset');
            fieldsets.forEach(fs => {
                const legend = (fs.querySelector('legend')?.innerText || '').toLowerCase();
                const radios = fs.querySelectorAll('input[type="radio"]');
                if (!radios || radios.length === 0) return;

                // Check if already selected
                const anyChecked = Array.from(radios).some(r => r.checked);
                if (anyChecked) return;

                // Sponsorship questions -> Choose "No"
                if (legend.includes('sponsor') || legend.includes('visa') || legend.includes('require sponsorship')) {
                    const noRadio = Array.from(radios).find(r => {
                        const lbl = fs.querySelector(`label[for="${r.id}"]`)?.innerText.toLowerCase() || '';
                        return r.value.toLowerCase() === 'no' || lbl.includes('no');
                    });
                    if (noRadio) {
                        noRadio.click();
                        noRadio.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                }
                // Authorization, relocation, immediate joining, commute, degree -> Choose "Yes"
                else {
                    const yesRadio = Array.from(radios).find(r => {
                        const lbl = fs.querySelector(`label[for="${r.id}"]`)?.innerText.toLowerCase() || '';
                        return r.value.toLowerCase() === 'yes' || lbl.includes('yes');
                    });
                    if (yesRadio) {
                        yesRadio.click();
                        yesRadio.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                }
            });
        }
    """)

    # 3. Handle Select Dropdowns
    page.evaluate("""
        () => {
            const selects = document.querySelectorAll('.jobs-easy-apply-modal select, [role="dialog"] select');
            selects.forEach(sel => {
                if (sel.value && sel.value !== 'Select an option' && sel.selectedIndex > 0) return;
                
                // Prefer 'Yes' or first valid option
                for (let i = 0; i < sel.options.length; i++) {
                    const optText = sel.options[i].text.toLowerCase();
                    if (optText.includes('yes') || optText.includes('immediate') || optText.includes('0 days') || optText.includes('bachelor')) {
                        sel.selectedIndex = i;
                        sel.dispatchEvent(new Event('change', {bubbles: true}));
                        break;
                    }
                }
                if (sel.selectedIndex <= 0 && sel.options.length > 1) {
                    sel.selectedIndex = 1;
                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                }
            });
        }
    """)

    # 4. Handle Resume File Upload if file input exists and no resume chosen
    if tailored_resume_path and os.path.exists(tailored_resume_path):
        try:
            file_input = page.locator('.jobs-easy-apply-modal input[type="file"], [role="dialog"] input[type="file"]').first
            if file_input.count() > 0:
                file_input.set_input_files(tailored_resume_path)
                print(f"  ✓ Attached tailored ATS resume in modal: {os.path.basename(tailored_resume_path)}")
                time.sleep(1)
        except Exception:
            pass


def execute_easy_apply(page, profile: Profile, job_title: str, company: str, tailored_resume_path: str = "") -> bool:
    """
    Submits a LinkedIn Easy Apply application through its multi-step modal.
    Returns True if successfully submitted, False otherwise.
    """
    easy_apply_btn = page.locator(
        'button.jobs-apply-button:has-text("Easy Apply"), button[aria-label*="Easy Apply"], button:has-text("Easy Apply")'
    ).first

    if not easy_apply_btn.is_visible():
        return False

    easy_apply_btn.click()
    time.sleep(2)

    # Multi-step loop (capped at 10 steps)
    for step in range(1, 11):
        stop = check_stop_signals(page)
        if stop:
            raise RuntimeError(f"Stop signal detected during application: {stop}")

        # Check modal buttons
        submit_btn = page.locator('button:has-text("Submit application"), button[aria-label="Submit application"]').first
        review_btn = page.locator('button:has-text("Review"), button[aria-label="Review your application"]').first
        next_btn = page.locator('button:has-text("Next"), button[aria-label="Continue to next step"]').first

        # Fill inputs on current step
        fill_form_inputs(page, profile, tailored_resume_path)
        time.sleep(0.8)

        if submit_btn.is_visible():
            print(f"  -> Reached final review step! Submitting application...")
            submit_btn.click()
            time.sleep(2.5)

            # Click post-submit 'Done' dismiss button
            done_btn = page.locator('button:has-text("Done"), button[aria-label="Dismiss"]').first
            if done_btn.is_visible():
                done_btn.click()
                time.sleep(1)
                return True

            body_lower = page.locator("body").inner_text().lower()
            if "application was sent" in body_lower or "your application was sent" in body_lower:
                return True

            # Strict confirmation: check if validation errors blocked submission
            errors = page.locator(".artdeco-inline-feedback--error, [data-test-form-element-error-messages]").all_inner_texts()
            err_msg = ", ".join(errors) if errors else "Required questions or validation blocked submission"
            print(f"  [⚠️ Warning] Submission validation blocked: {err_msg}")
            return False

        elif review_btn.is_visible():
            review_btn.click()
            time.sleep(1.2)

        elif next_btn.is_visible():
            next_btn.click()
            time.sleep(1.2)

        else:
            # Check if application already submitted or if stuck
            done_btn = page.locator('button:has-text("Done")').first
            if done_btn.is_visible():
                done_btn.click()
                return True
            raise SkipJob(f"Unknown modal step state (buttons not identifiable)")

    raise SkipJob("Exceeded 10 modal steps without reaching final submit")


def harvest_matched_jobs(page, max_jobs: int = 300) -> List[Dict[str, Any]]:
    """
    Harvests all available job postings from LinkedIn's 'Jobs that match your profile' section.
    Navigates to direct collections URL and iterates through pagination offsets.
    """
    print("\n" + "=" * 75)
    print("🔍 [HARVEST] Navigating to 'Jobs that match your profile' collection...")
    print("=" * 75)

    base_collection_url = "https://www.linkedin.com/jobs/collections/recommended/"
    jobs_discovered = {}

    try:
        page.goto(base_collection_url, wait_until="domcontentloaded", timeout=45000)
        time.sleep(3)
    except Exception as e:
        print(f"WARN: Error navigating to {base_collection_url}: {e}")

    # Verify if redirected or logged out
    if "login" in page.url.lower():
        print("ERROR: LinkedIn session expired. Please re-authenticate via: ./.venv/bin/python login_capture.py linkedin")
        return []

    # Pagination Loop: LinkedIn serves 25 jobs per page offset (start=0, 25, 50, 75, ...)
    consecutive_empty_pages = 0
    start_offset = 0

    while len(jobs_discovered) < max_jobs and consecutive_empty_pages < 2:
        page_url = f"{base_collection_url}?start={start_offset}"
        print(f"\n[Page Offset {start_offset}] Loading: {page_url} (Found {len(jobs_discovered)} unique jobs so far)")

        try:
            page.goto(page_url, wait_until="domcontentloaded", timeout=35000)
            time.sleep(2.5)

            # Scroll through the list container to force lazy DOM rendering
            page.evaluate("""
                () => {
                    const container = document.querySelector('.jobs-search-results-list, .scaffold-layout__list, div[tabindex="-1"]') || window;
                    container.scrollBy(0, 800);
                }
            """)
            time.sleep(1.2)
            page.evaluate("""
                () => {
                    const container = document.querySelector('.jobs-search-results-list, .scaffold-layout__list, div[tabindex="-1"]') || window;
                    container.scrollBy(0, 1500);
                }
            """)
            time.sleep(1.5)

            # Extract job cards
            cards = page.evaluate("""
                () => {
                    const list = [];
                    const seenIds = new Set();

                    // Find all job links and items
                    const items = document.querySelectorAll(
                        'li[data-occludable-job-id], [data-job-id], .job-card-container, a[href*="/jobs/view/"]'
                    );

                    items.forEach(el => {
                        let link = el.tagName === 'A' ? el : el.querySelector('a[href*="/jobs/view/"]');
                        if (!link) return;

                        const href = link.href.split('?')[0];
                        const match = href.match(/\/jobs\/view\/(\d+)/);
                        if (!match) return;
                        const jId = match[1];
                        if (seenIds.has(jId)) return;
                        seenIds.add(jId);

                        // Find title, company, location
                        const cardContainer = el.closest('li') || el.closest('.job-card-container') || el;
                        const titleEl = cardContainer.querySelector('.job-card-list__title, .artdeco-entity-lockup__title, strong, h3');
                        const compEl = cardContainer.querySelector('.job-card-container__primary-description, .artdeco-entity-lockup__subtitle, .job-card-container__company-name');
                        const locEl = cardContainer.querySelector('.job-card-container__metadata-item, .artdeco-entity-lockup__caption');

                        const title = titleEl ? titleEl.innerText.trim().split('\\n')[0] : (link.innerText.trim().split('\\n')[0] || '');
                        const company = compEl ? compEl.innerText.trim() : '';
                        const location = locEl ? locEl.innerText.trim() : '';

                        if (jId && href) {
                            list.push({
                                jobId: jId,
                                title: title,
                                company: company,
                                location: location,
                                href: `https://www.linkedin.com/jobs/view/${jId}/`
                            });
                        }
                    });
                    return list;
                }
            """)

            new_on_page = 0
            for c in cards:
                jid = c.get("jobId")
                if jid and jid not in jobs_discovered:
                    jobs_discovered[jid] = c
                    new_on_page += 1

            print(f"  -> Discovered {new_on_page} new jobs on offset {start_offset} (Total: {len(jobs_discovered)})")

            if new_on_page == 0:
                consecutive_empty_pages += 1
            else:
                consecutive_empty_pages = 0

            start_offset += 25
            time.sleep(1.5)

        except Exception as e:
            print(f"  Note during page load offset {start_offset}: {e}")
            consecutive_empty_pages += 1
            start_offset += 25

    print("\n" + "=" * 75)
    print(f"✓ [HARVEST COMPLETE] Discovered {len(jobs_discovered)} jobs in 'Jobs that match your profile' section.")
    print("=" * 75)
    return list(jobs_discovered.values())


def run_matched_jobs_pipeline(
    max_jobs: int = 300,
    unattended: bool = True,
    dry_run: bool = False,
    force: bool = False
) -> Dict[str, Any]:
    """
    Main execution pipeline for applying to all 'Jobs that match your profile' on LinkedIn.
    """
    profile = Profile.load()
    processed_state = load_processed_state()
    applied_ids = set(processed_state.get("applied", []))
    external_ids = set(processed_state.get("external_logged", []))

    if not SESSION_FILE.exists():
        print(f"ERROR: Session file {SESSION_FILE} not found. Please run login_capture.py first.")
        return {"error": "Missing session_linkedin.json"}

    stats = {
        "date": date.today().isoformat(),
        "started_at": datetime.now().isoformat(),
        "total_harvested": 0,
        "already_processed": 0,
        "applied_easy_apply": 0,
        "external_logged_to_sheets": 0,
        "skipped_foreign": 0,
        "errors": 0,
    }

    with sync_playwright() as p:
        browser_mode = profile.data.get("browser_mode", "minimized")
        browser = launch_chrome_browser(p, browser_mode=browser_mode, slow_mo=100)
        context = browser.new_context(storage_state=str(SESSION_FILE))
        page = context.new_page()

        # Step 1: Harvest all jobs from the Matched Profile section
        matched_jobs = harvest_matched_jobs(page, max_jobs=max_jobs)
        stats["total_harvested"] = len(matched_jobs)

        if not matched_jobs:
            print("No jobs found in 'Jobs that match your profile' section or session redirected.")
            browser.close()
            return stats

        # Step 2: Iterate through every harvested job and process
        print("\n" + "#" * 75)
        print(f"PROCESSING {len(matched_jobs)} MATCHED JOBS (Easy Apply or Route to Google Sheets)")
        print("#" * 75)

        for idx, job in enumerate(matched_jobs, start=1):
            job_id = job.get("jobId")
            title = job.get("title", "Frontend Engineer")
            company = job.get("company", "Company")
            location = job.get("location", "")
            job_url = job.get("href", f"https://www.linkedin.com/jobs/view/{job_id}/")

            print(f"\n[{idx}/{len(matched_jobs)}] Evaluating: {title} @ {company} (ID: {job_id})")

            # Check if already processed
            if not force and (job_id in applied_ids or job_id in external_ids):
                print(f"  -> Already processed previously (ID: {job_id}). Skipping.")
                stats["already_processed"] += 1
                continue

            try:
                # Navigate to the individual job view
                page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(1.8)

                stop = check_stop_signals(page)
                if stop:
                    print(f"STOPPING: Security block detected ({stop}). Exiting loop.")
                    break

                job_details = extract_job_details(page, job)
                loc = job_details.get("location") or location
                jd = job_details.get("jd_text", "")

                # Location verification (India & Remote only)
                if not is_india_job(location=loc, title=title, company=company, url=job_url):
                    print(f"  -> Skipping foreign / non-India location: '{loc}'")
                    stats["skipped_foreign"] += 1
                    processed_state.setdefault("skipped_foreign", []).append(job_id)
                    continue

                # Prepare tailored ATS resume
                safe_title = re.sub(r'[^A-Za-z0-9]+', '_', title)[:30]
                safe_comp = re.sub(r'[^A-Za-z0-9]+', '_', company)[:20]
                out_resume_path = str(PROJECT_DIR / f"generated/Abhishek_Anand_{safe_comp}_{safe_title}_{job_id}.docx")
                os.makedirs(PROJECT_DIR / "generated", exist_ok=True)

                tailored_resume_path = out_resume_path
                try:
                    ats_content = jd if len(jd) > 40 else f"{title} React Developer at {company}"
                    ats_res = prepare_tailored_resume(ats_content, output_path=out_resume_path)
                    tailored_resume_path = str(ats_res.get("tailored_resume_path", out_resume_path))
                    print(f"  ✓ Tailored ATS resume generated: {os.path.basename(tailored_resume_path)}")
                except Exception as e:
                    print(f"  Note during ATS tailoring: {e}")
                    tailored_resume_path = str(PROJECT_DIR / "Abhishek_Anand_Resume.docx")

                # Check if Easy Apply is available
                has_easy_apply = page.locator(
                    'button.jobs-apply-button:has-text("Easy Apply"), button[aria-label*="Easy Apply"], button:has-text("Easy Apply")'
                ).first.is_visible()

                # DRY-RUN handling
                if dry_run:
                    action_type = "EASY_APPLY" if has_easy_apply else "EXTERNAL_SHEETS"
                    print(f"  [DRY-RUN] Would process job as: {action_type}")
                    if has_easy_apply:
                        stats["applied_easy_apply"] += 1
                    else:
                        stats["external_logged_to_sheets"] += 1
                    continue

                # CASE 1: Easy Apply Available -> Execute Application
                application_successful = False
                if has_easy_apply:
                    try:
                        print(f"  -> Easy Apply detected! Submitting application...")
                        application_successful = execute_easy_apply(
                            page, profile, title, company, tailored_resume_path
                        )
                    except SkipJob as e:
                        print(f"  -> Easy Apply skipped ({e}). Routing to Google Sheets...")
                        close_modal(page)
                        application_successful = False
                    except Exception as e:
                        print(f"  -> Easy Apply encountered issue ({e}). Routing to Google Sheets...")
                        close_modal(page)
                        application_successful = False

                # Outcome A: Successfully submitted via Easy Apply
                if application_successful:
                    stats["applied_easy_apply"] += 1
                    applied_ids.add(job_id)
                    processed_state.setdefault("applied", []).append(job_id)
                    save_processed_state(processed_state)

                    # Log to CSV
                    with open(APPLICATIONS_LOG, "a", newline="", encoding="utf-8") as f:
                        w = csv.writer(f)
                        w.writerow([datetime.now().isoformat(), "linkedin_matched", title, company, "applied", "Easy Apply"])

                    # Log to Google Sheets (Sheet1 Applied)
                    try:
                        append_applied_job({
                            "discovered_at": datetime.now().isoformat(),
                            "platform": "linkedin",
                            "jobId": job_id,
                            "title": title,
                            "company": company,
                            "location": loc,
                            "exp": "3.5+ Yrs",
                            "href": job_url,
                            "notes": "Applied via LinkedIn Easy Apply (Matched Profile Section)",
                        })
                        print(f"  ✓ Applied and logged to Google Sheets ('Sheet1' Applied).")
                    except Exception as e:
                        print(f"  Note logging applied job to Google Sheets: {e}")

                # Outcome B: External Company Portal OR Unapplied -> Log to Google Sheets
                else:
                    stats["external_logged_to_sheets"] += 1
                    external_ids.add(job_id)
                    processed_state.setdefault("external_logged", []).append(job_id)
                    save_processed_state(processed_state)

                    reason_msg = "LinkedIn Matched Profile - External Portal Application" if not has_easy_apply else "Easy Apply skipped / Manual completion required"

                    # Log to CSV
                    with open(EXTERNAL_LOG, "a", newline="", encoding="utf-8") as f:
                        w = csv.writer(f)
                        w.writerow([
                            datetime.now().isoformat(), "linkedin_matched", job_id, title,
                            company, loc, "3.5+ Yrs", job_url, "PENDING", reason_msg
                        ])

                    # 1. Log to Google Sheets (Sheet1 Pending External)
                    try:
                        if not external_job_url_exists(job_url):
                            append_external_job({
                                "discovered_at": datetime.now().isoformat(),
                                "platform": "linkedin",
                                "jobId": job_id,
                                "title": title,
                                "company": company,
                                "location": loc,
                                "exp": "3.5+ Yrs",
                                "href": job_url,
                                "status": "PENDING_USER_APPLY",
                                "notes": reason_msg,
                                "tailored_resume_path": tailored_resume_path,
                            })
                    except Exception as e:
                        print(f"  Note logging to Sheet1: {e}")

                    # 2. Log to Google Sheets ('Apply Yourself' Tab)
                    try:
                        append_apply_yourself_job({
                            "platform": "linkedin",
                            "company": company,
                            "title": title,
                            "location": loc,
                            "exp": "3.5+ Yrs",
                            "job_url": job_url,
                            "apply_url": job_url,
                            "tailored_resume_path": tailored_resume_path,
                            "reason": reason_msg,
                            "status": "PENDING_USER_APPLY",
                        })
                        print(f"  ✓ Logged to Google Sheets ('Apply Yourself' tab) with tailored resume.")
                    except Exception as e:
                        print(f"  Note logging to Apply Yourself tab: {e}")

                # Gentle pacing between jobs (2-3 seconds)
                time.sleep(2.5)

            except Exception as e:
                print(f"  WARN: Error processing job {job_id} ({title}): {e}")
                stats["errors"] += 1
                close_modal(page)
                continue

        browser.close()

    # Final Summary Compilation
    stats["completed_at"] = datetime.now().isoformat()
    try:
        with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)
    except Exception:
        pass

    print("\n" + "=" * 75)
    print("🎯 LINKEDIN MATCHED PROFILE JOBS RUN SUMMARY:")
    print(f"  Total Harvested:           {stats['total_harvested']}")
    print(f"  Already Processed:         {stats['already_processed']}")
    print(f"  Applied via Easy Apply:    {stats['applied_easy_apply']}")
    print(f"  Unapplied -> Google Sheets:{stats['external_logged_to_sheets']}")
    print(f"  Skipped (Foreign):         {stats['skipped_foreign']}")
    print(f"  Errors / Interrupted:      {stats['errors']}")
    print("=" * 75)
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LinkedIn 'Jobs that match your profile' Auto-Apply & Sync")
    parser.add_argument("--max-jobs", type=int, default=300, help="Maximum number of matched jobs to process (default 300)")
    parser.add_argument("--dry-run", action="store_true", help="Harvest and evaluate jobs without final submit or sheets upload")
    parser.add_argument("--force", action="store_true", help="Force re-evaluation of previously processed jobs")
    args = parser.parse_args()

    run_matched_jobs_pipeline(
        max_jobs=args.max_jobs,
        dry_run=args.dry_run,
        force=args.force
    )
