"""
External Job Auto-Applier & "Apply Yourself" Queue Manager.

Orchestrates automated applications for external company listings discovered
via Naukri and LinkedIn. 

Key Capabilities:
1. Reads pending external jobs from Google Sheets (Sheet1) / external_jobs.csv.
2. Selects existing tailored resume or generates a fresh ATS-tailored resume
   (.docx + .pdf) in `generated/` specifically for the job description.
3. Opens the job portal, follows redirects from Naukri/LinkedIn to the target ATS
   (Greenhouse, Lever, SmartRecruiters, Ashby, Workday, etc.).
4. Pre-fills form fields (Contact info, links, notice period, CTC, attaches tailored PDF).
5. If fully automatable: submits cleanly and marks APPLIED.
6. If manual intervention is required (CAPTCHA, Workday login wall, OTP, complex form):
   - Waits up to 60 seconds for manual action.
   - If user intervenes and completes -> logs APPLIED.
   - If 60 seconds elapses without action -> automatically pushes the job and its
     tailored resume link into the "Apply Yourself" Google Sheet tab, marks Sheet1
     as MOVED_TO_APPLY_YOURSELF, closes the tab, and advances to the next URL!
"""

import argparse
import csv
from datetime import datetime, date
import json
import os
from pathlib import Path
import re
import sys
import time

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from common.browser_factory import launch_chrome_browser

from common.ats_pipeline import prepare_tailored_resume
from common.pdf_converter import convert_docx_to_pdf
from common.profile import Profile
from google_sheets_logger import (
    _get_sheet,
    append_apply_yourself_job,
    update_job_status_in_sheet1,
)
from location_filter import is_india_job

MASTER_RESUME_DOCX = "Abhishek_Anand_Resume.docx"
MASTER_RESUME_PDF = "Abhishek_Anand_Resume.pdf"
GENERATED_DIR = Path("generated")
APPLICATIONS_LOG = "applications_log.csv"


def log_application(row: list):
    new_file = not Path(APPLICATIONS_LOG).exists()
    with open(APPLICATIONS_LOG, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["timestamp", "source", "title", "company", "status", "reason"])
        w.writerow(row)


def get_or_generate_tailored_resume(job: dict, profile: Profile) -> str:
    """
    Returns an ATS-tailored PDF (or DOCX) file path for the given job.
    Uses existing generated resume if present, or creates one on the fly.
    Falls back safely to Master Resume if tailoring is not applicable.
    """
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    existing_path = job.get("tailored_resume_path", "").strip()

    # 1. Check if existing tailored resume exists on disk
    if existing_path and Path(existing_path).exists():
        p = Path(existing_path)
        if p.suffix.lower() == ".pdf":
            return str(p)
        # If docx, ensure matching pdf exists
        pdf_path = p.with_suffix(".pdf")
        if pdf_path.exists():
            return str(pdf_path)
        try:
            return convert_docx_to_pdf(str(p))
        except Exception:
            return str(p)

    # 2. Check if a generated resume matching job_id exists in generated/
    job_id = str(job.get("job_id") or "").strip()
    if job_id:
        for f in GENERATED_DIR.glob(f"*{job_id}*"):
            if f.suffix.lower() == ".pdf":
                return str(f)
            if f.suffix.lower() == ".docx":
                pdf_f = f.with_suffix(".pdf")
                if pdf_f.exists():
                    return str(pdf_f)
                try:
                    return convert_docx_to_pdf(str(f))
                except Exception:
                    return str(f)

    # 3. On-the-fly generation from JD text if available
    jd_text = (job.get("description") or job.get("jd_keywords") or "").strip()
    if len(jd_text) >= 50:
        safe_title = re.sub(r"[^A-Za-z0-9]+", "_", str(job.get("title") or "job"))[:40].strip("_")
        safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", job_id or "ext")
        output_docx = str(GENERATED_DIR / f"Abhishek_Anand_Tailored_{safe_title}_{safe_id}.docx")
        try:
            print(f"Generating on-the-fly tailored resume for {job.get('title')}...")
            res = prepare_tailored_resume(
                job_description=jd_text,
                master_resume_path=MASTER_RESUME_DOCX,
                output_path=output_docx,
            )
            docx_path = str(res["tailored_resume_path"])
            try:
                return convert_docx_to_pdf(docx_path)
            except Exception:
                return docx_path
        except Exception as e:
            print(f"WARN in on-the-fly tailoring: {e}. Falling back to Master Resume.")

    # 4. Master Resume Fallback
    if Path(MASTER_RESUME_PDF).exists():
        return str(Path(MASTER_RESUME_PDF).resolve())
    if Path(MASTER_RESUME_DOCX).exists():
        try:
            return convert_docx_to_pdf(MASTER_RESUME_DOCX)
        except Exception:
            return str(Path(MASTER_RESUME_DOCX).resolve())

    return MASTER_RESUME_DOCX


def load_pending_external_jobs(max_jobs: int = 10) -> list[dict]:
    """Reads pending external jobs from Google Sheets (Sheet1) or fallback CSV."""
    jobs = []
    seen_urls = set()

    # Try Google Sheets first
    try:
        sheet = _get_sheet()
        rows = sheet.get_all_values()
        if len(rows) > 1:
            for idx, r in enumerate(rows[1:], start=2):
                if len(r) < 9:
                    continue
                status = r[8].strip().upper()
                job_url = r[7].strip()
                if not job_url or job_url in seen_urls:
                    continue
                # Skip already finalized jobs
                if status in ["MOVED_TO_APPLY_YOURSELF", "APPLIED", "EXPIRED", "SKIPPED", "REJECTED", "FAILED", "SKIPPED_NOT_INDIA"]:
                    continue

                # Filter: Only process postings located in India
                loc_val = r[5].strip() if len(r) > 5 else ""
                title_val = r[3].strip() if len(r) > 3 else ""
                comp_val = r[4].strip() if len(r) > 4 else ""
                notes_val = r[9].strip() if len(r) > 9 else ""
                if not is_india_job(location=loc_val, title=title_val, company=comp_val, notes=notes_val, url=job_url):
                    continue

                # Pick pending external / manual jobs
                notes_text = r[9].upper() if len(r) > 9 else ""
                if status in ["PENDING", ""] or "EXTERNAL" in notes_text or "NO EASY APPLY" in notes_text:
                    jobs.append({
                        "row_num": idx,
                        "date_added": r[0].strip(),
                        "platform": r[1].strip() or "external",
                        "job_id": r[2].strip(),
                        "title": title_val,
                        "company": comp_val,
                        "location": loc_val,
                        "exp": r[6].strip(),
                        "job_url": job_url,
                        "status": status,
                        "notes": notes_val,
                        "tailored_resume_path": r[12].strip() if len(r) > 12 else "",
                    })
                    seen_urls.add(job_url)
                    if len(jobs) >= max_jobs:
                        break
            if jobs:
                print(f"Loaded {len(jobs)} pending external jobs in India from Google Sheets.")
                return jobs
    except Exception as e:
        print(f"WARN loading from Google Sheets: {e}. Checking local external_jobs.csv...")

    # Fallback to external_jobs.csv
    csv_file = Path("external_jobs.csv")
    if csv_file.exists():
        with open(csv_file, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = (row.get("job_url") or "").strip()
                if not url or url in seen_urls:
                    continue
                status = (row.get("status") or "").strip().upper()
                if status in ["PENDING", ""]:
                    jobs.append({
                        "job_id": row.get("job_id", ""),
                        "platform": row.get("platform", "naukri"),
                        "title": row.get("title", ""),
                        "company": row.get("company", ""),
                        "location": row.get("location", ""),
                        "exp": row.get("experience", ""),
                        "job_url": url,
                        "status": status,
                        "notes": row.get("notes", ""),
                        "tailored_resume_path": "",
                    })
                    seen_urls.add(url)
                    if len(jobs) >= max_jobs:
                        break
        print(f"Loaded {len(jobs)} pending external jobs from external_jobs.csv.")

    return jobs


def check_internet_connection(timeout: int = 5) -> bool:
    import socket
    for host in [("8.8.8.8", 53), ("1.1.1.1", 53), ("oauth2.googleapis.com", 443)]:
        try:
            socket.setdefaulttimeout(timeout)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(host)
            s.close()
            return True
        except Exception:
            pass
    return False


def wait_for_internet_connection(max_wait_seconds: int = 1800) -> bool:
    """If internet drops, pauses and polls until reconnected instead of burning through jobs."""
    if check_internet_connection():
        return True
    print("\n⚠️  [NETWORK WARNING] Internet connection appears disconnected! Pausing runner...")
    waited = 0
    while waited < max_wait_seconds:
        time.sleep(10)
        waited += 10
        if check_internet_connection():
            print(f"✓ Internet reconnected after {waited}s! Resuming runner...")
            time.sleep(3)
            return True
        if waited % 60 == 0:
            print(f"  ⏳ Waiting for internet connection to restore... ({waited // 60}m elapsed)")
    print("❌ Internet connection timed out after 30 minutes.")
    return False


def resolve_direct_apply_url(page, job_url: str) -> str:
    """
    Opens Naukri or LinkedIn listing and triggers the external apply button
    to capture the target career portal URL (Lever, Greenhouse, Workday, etc.).
    """
    print(f"Navigating to listing: {job_url}")
    try:
        page.goto(job_url, wait_until="load", timeout=30000)
        time.sleep(2)
    except Exception as e:
        err_str = str(e)
        print(f"Navigation warning: {err_str}")
        if any(term in err_str for term in ["ERR_INTERNET_DISCONNECTED", "ERR_NETWORK_CHANGED", "ERR_NAME_NOT_RESOLVED"]):
            if wait_for_internet_connection():
                try:
                    page.goto(job_url, wait_until="load", timeout=30000)
                    time.sleep(2)
                except Exception:
                    return job_url
            else:
                return job_url
        else:
            return job_url

    # Check if already a direct company site
    curr_url = page.url
    if not any(domain in curr_url for domain in ["naukri.com", "linkedin.com"]):
        return curr_url

    # Handle Naukri Apply on Company Site or Direct Apply
    if "naukri.com" in curr_url:
        company_btn = page.locator('#company-site-button, a[href*="apply"], button:has-text("Apply on Company Site"), a:has-text("Apply on Company Site")').first
        if company_btn.count() > 0:
            href = company_btn.get_attribute("href") or ""
            if href.startswith("http") and "naukri.com" not in href and not href.startswith("chrome-error"):
                print(f"Direct external href found: {href}")
                return href
            try:
                with page.context.expect_page(timeout=7000) as new_page_info:
                    company_btn.click(timeout=5000, force=True)
                new_page = new_page_info.value
                new_page.wait_for_load_state(timeout=10000)
                time.sleep(2)
                resolved = new_page.url
                new_page.close()
                if resolved and "naukri.com" not in resolved and not resolved.startswith("chrome-error") and resolved.startswith("http"):
                    print(f"Resolved direct company portal: {resolved}")
                    return resolved
            except Exception:
                pass

        # Also check native apply button if not company-site
        apply_btn = page.locator('#apply-button, button:has-text("Apply")').first
        if apply_btn.count() > 0:
            try:
                apply_btn.click(timeout=5000, force=True)
                time.sleep(2)
            except Exception:
                pass

    # Handle LinkedIn Apply
    if "linkedin.com" in curr_url:
        btn = page.locator('button.jobs-apply-button, a[href*="apply"], button:has-text("Apply")').first
        if btn.count() > 0:
            href = btn.get_attribute("href") or ""
            if href.startswith("http") and "linkedin.com" not in href and not href.startswith("chrome-error"):
                return href
            try:
                with page.context.expect_page(timeout=7000) as new_page_info:
                    btn.click(timeout=5000, force=True)
                new_page = new_page_info.value
                new_page.wait_for_load_state(timeout=10000)
                time.sleep(2)
                resolved = new_page.url
                new_page.close()
                if resolved and "linkedin.com" not in resolved and not resolved.startswith("chrome-error") and resolved.startswith("http"):
                    print(f"Resolved direct company portal: {resolved}")
                    return resolved
            except Exception:
                pass

    return page.url


def auto_fill_application_form(page, profile: Profile, resume_path: str) -> dict:
    """
    Inspects and pre-fills common fields in external ATS forms.
    Returns status: {'can_auto_submit': bool, 'manual_reason': str}
    """
    pdata = profile.data
    first_name = pdata.get("first_name", "Abhishek")
    last_name = pdata.get("last_name", "Anand")
    full_name = f"{first_name} {last_name}".strip()
    email = pdata.get("email", "abhishek.anand.7601@gmail.com")
    phone = pdata.get("phone", "+91-8839617601")
    city = pdata.get("current_city", "Patna")
    linkedin = "https://linkedin.com/in/abhishekreactdeveloper"
    github = "https://github.com/dev-abhishekanand"
    exp = str(pdata.get("total_experience_years", "3.5"))
    current_ctc = str(pdata.get("current_ctc_lpa", "7.0"))
    expected_ctc = str(pdata.get("expected_ctc_lpa", "10.0"))

    # 1. Attach Resume
    file_input = page.locator('input[type="file"]').first
    if file_input.count() > 0 and resume_path and Path(resume_path).exists():
        try:
            file_input.set_input_files(str(Path(resume_path).resolve()))
            print(f"  ✓ Attached tailored resume: {Path(resume_path).name}")
            time.sleep(1.5)
        except Exception as e:
            print(f"  WARN uploading resume: {e}")

    # 2. Text Inputs
    inputs = page.locator('input[type="text"], input[type="email"], input[type="tel"], input:not([type])').all()
    for inp in inputs:
        try:
            if not inp.is_visible():
                continue
            name_attr = (inp.get_attribute("name") or "").lower()
            id_attr = (inp.get_attribute("id") or "").lower()
            placeholder = (inp.get_attribute("placeholder") or "").lower()
            aria = (inp.get_attribute("aria-label") or "").lower()
            combined = f"{name_attr} {id_attr} {placeholder} {aria}"

            val = inp.input_value().strip()
            if val:
                continue  # Skip already populated fields

            if any(k in combined for k in ["first", "fname"]) and not any(k in combined for k in ["last", "full"]):
                inp.fill(first_name)
            elif any(k in combined for k in ["last", "lname", "surname"]):
                inp.fill(last_name)
            elif any(k in combined for k in ["full_name", "fullname", "name"]) and not any(k in combined for k in ["company", "user"]):
                inp.fill(full_name)
            elif any(k in combined for k in ["email", "e-mail"]):
                inp.fill(email)
            elif any(k in combined for k in ["phone", "mobile", "tel", "contact"]):
                inp.fill(phone)
            elif any(k in combined for k in ["linkedin"]):
                inp.fill(linkedin)
            elif any(k in combined for k in ["github", "git"]):
                inp.fill(github)
            elif any(k in combined for k in ["city", "location", "address"]):
                inp.fill(city)
            elif any(k in combined for k in ["experience", "years"]):
                inp.fill(exp)
            elif any(k in combined for k in ["current ctc", "current salary", "present ctc"]):
                inp.fill(current_ctc)
            elif any(k in combined for k in ["expected ctc", "expected salary"]):
                inp.fill(expected_ctc)
            elif any(k in combined for k in ["notice", "days"]):
                inp.fill("0")
        except Exception:
            continue

    # 0. Check for Closed / Expired Listings
    body_text = page.locator("body").inner_text().lower()
    closed_signals = [
        "no longer accepting applications",
        "job is no longer available",
        "this job has expired",
        "this posting has been closed",
        "this vacancy has been closed",
        "job is closed",
        "position has been filled",
        "page not found",
        "404 not found",
        "job not found",
        "job you are looking for is no longer active",
        "job you are looking for is no longer available",
        "this job is no longer active",
        "job posting has expired",
    ]
    curr_url_lower = page.url.lower()
    is_naukri_search_redirect = "naukri.com" in curr_url_lower and ("expjd=true" in curr_url_lower or "-jobs-in-" in curr_url_lower or "/jobs-in-" in curr_url_lower)
    if "expired_jd_redirect" in curr_url_lower or is_naukri_search_redirect or any(sig in body_text for sig in closed_signals):
        return {"can_auto_submit": False, "is_expired": True, "manual_reason": "Listing expired or closed"}

    # 3. Check for Manual Intervention Blockers
    if page.locator('iframe[src*="recaptcha"], iframe[src*="hcaptcha"], div[class*="captcha"], div[class*="turnstile"]').count() > 0:
        return {"can_auto_submit": False, "manual_reason": "CAPTCHA verification required"}

    if any(k in body_text for k in ["create account", "sign in to apply", "workday login", "password"]):
        return {"can_auto_submit": False, "manual_reason": "Account creation / login required"}

    if any(k in body_text for k in ["take assessment", "video interview", "recorded response"]):
        return {"can_auto_submit": False, "manual_reason": "Online assessment / video interview required"}

    # Look for submit button
    if "linkedin.com" in curr_url_lower:
        submit_btn = page.locator('button[aria-label="Submit application"], button:has-text("Submit application")').first
    else:
        submit_btn = page.locator('button[type="submit"], input[type="submit"], button:has-text("Submit Application"), button:has-text("Submit Application"), button:has-text("Submit")').first
    if submit_btn.count() == 0:
        return {"can_auto_submit": False, "manual_reason": "Complex multi-step form (Submit button not immediate)"}

    return {"can_auto_submit": True, "submit_btn": submit_btn, "manual_reason": ""}


def process_external_job(page, job: dict, profile: Profile, timeout_seconds: int = 60, dry_run: bool = False) -> str:
    """
    Processes one external job:
    - Prepares tailored resume
    - Resolves portal URL
    - Attempts automated fill
    - Handles 60-second manual intervention window
    - Queues to 'Apply Yourself' on timeout
    """
    title = job.get("title", "Frontend Engineer")
    company = job.get("company", "Company")
    source_url = job.get("job_url", "")
    job_id = job.get("job_id", "")
    row_num = job.get("row_num")

    print(f"\n========================================================")
    print(f"PROCESSING EXTERNAL JOB: {title} @ {company}")
    print(f"Source URL: {source_url}")
    print(f"========================================================")

    # 0. Strict India Location Verification
    loc = job.get("location", "")
    if not is_india_job(location=loc, title=title, company=company, notes=job.get("notes", ""), url=source_url):
        print(f"Skipping non-India listing: {title} @ {company} (Location: {loc})")
        update_job_status_in_sheet1(job_id or source_url, "SKIPPED_NOT_INDIA", f"Location outside India ({loc})", row_num=row_num)
        return "SKIPPED_NOT_INDIA"

    # 1. Prepare Tailored Resume (.docx + .pdf)
    resume_path = get_or_generate_tailored_resume(job, profile)
    print(f"Active Tailored Resume: {resume_path}")

    # 2. Resolve Direct Apply Portal
    direct_url = resolve_direct_apply_url(page, source_url)
    if not direct_url or direct_url.startswith("chrome-error") or not direct_url.startswith("http"):
        direct_url = source_url

    if dry_run:
        print(f"[DRY-RUN] Direct Portal: {direct_url} | Tailored Resume: {resume_path}")
        return "DRY_RUN_OK"

    # 3. Navigate to Direct Application Portal
    try:
        if page.url != direct_url:
            page.goto(direct_url, wait_until="load", timeout=30000)
            time.sleep(2)
    except Exception as e:
        err_str = str(e)
        print(f"WARN navigating to direct URL: {err_str}")
        if any(term in err_str for term in ["ERR_INTERNET_DISCONNECTED", "ERR_NETWORK_CHANGED", "ERR_NAME_NOT_RESOLVED"]):
            if wait_for_internet_connection():
                try:
                    page.goto(direct_url, wait_until="load", timeout=30000)
                    time.sleep(2)
                except Exception:
                    pass

    # Check if page failed to load due to connection loss
    if page.url.startswith("chrome-error"):
        if not check_internet_connection():
            if wait_for_internet_connection():
                try:
                    page.goto(direct_url, wait_until="load", timeout=30000)
                    time.sleep(2)
                except Exception:
                    pass

    if page.url.startswith("chrome-error"):
        print("Company portal connection failed (chrome-error). Routing directly to Apply Yourself.")
        append_apply_yourself_job({
            "platform": job.get("platform", "naukri"),
            "company": company,
            "title": title,
            "location": job.get("location", ""),
            "exp": job.get("exp", ""),
            "apply_url": source_url,
            "job_url": source_url,
            "tailored_resume_path": resume_path,
            "reason": "Portal connection blocked/failed",
        })
        update_job_status_in_sheet1(
            job_id or source_url,
            "MOVED_TO_APPLY_YOURSELF",
            "Portal connection blocked (Ready in Apply Yourself tab with tailored resume)",
            row_num=row_num,
        )
        return "PORTAL_BLOCKED"

    # 4. Fill Application Form
    form_res = auto_fill_application_form(page, profile, resume_path)

    # Check if listing expired
    if form_res.get("is_expired"):
        print(f"Listing is expired/closed on portal. Marking EXPIRED in Sheet1.")
        update_job_status_in_sheet1(
            job_id or source_url,
            "EXPIRED",
            "Listing expired or closed on company portal",
            row_num=row_num,
        )
        return "EXPIRED"

    CONFIRMATION_PHRASES = [
        "application submitted",
        "application successfully submitted",
        "successfully submitted",
        "thank you for applying",
        "thank you for your application",
        "we have received your application",
        "your application has been received",
        "your application has been sent",
        "your application was submitted",
        "application received",
    ]

    # 5. Case A: Fully Automatable Form
    if form_res["can_auto_submit"] and "submit_btn" in form_res:
        submit_btn = form_res["submit_btn"]
        try:
            print("Form successfully filled. Submitting application automatically...")
            submit_btn.scroll_into_view_if_needed(timeout=3000)
            submit_btn.click(timeout=5000)
            time.sleep(4)

            # Verify submission
            page_text = page.locator("body").inner_text().lower()
            if any(phrase in page_text for phrase in CONFIRMATION_PHRASES):
                print(f"✓ Application successfully submitted for {title} @ {company}!")
                log_application([
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "external (automated)",
                    title,
                    company,
                    "applied",
                    f"Direct ATS: {direct_url}",
                ])
                update_job_status_in_sheet1(job_id or source_url, "APPLIED", "Automated external submission confirmed", row_num=row_num)
                return "AUTO_APPLIED"
        except Exception as e:
            print(f"WARN during auto-submit: {e}. Falling back to manual intervention.")
            form_res["manual_reason"] = f"Submit error: {e}"

    # 6. Case B: Manual Intervention Required (60-Second Window)
    reason = form_res.get("manual_reason") or "Manual intervention needed"
    print(f"\n********************************************************")
    print(f"[ACTION REQUIRED] Manual intervention required!")
    print(f"  Reason:          {reason}")
    print(f"  Target URL:      {direct_url}")
    print(f"  Tailored Resume: {resume_path}")
    print(f"  Waiting {timeout_seconds}s for you to complete. If not completed,")
    print(f"  this job will be automatically queued into 'Apply Yourself'.")
    print(f"********************************************************")

    completed = False
    for remaining in range(timeout_seconds, 0, -2):
        if remaining % 10 == 0 or remaining <= 6:
            print(f"  ⏳ Waiting for manual action... {remaining}s remaining")
        try:
            body_text = page.locator("body").inner_text().lower()
            if any(phrase in body_text for phrase in CONFIRMATION_PHRASES):
                print(f"✓ Manual application verified within window!")
                completed = True
                break
        except Exception:
            pass
        time.sleep(2)

    if completed:
        log_application([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "external (manual)",
            title,
            company,
            "applied",
            f"Manual submission confirmed within window",
        ])
        update_job_status_in_sheet1(job_id or source_url, "APPLIED", "Manual submission confirmed", row_num=row_num)
        return "MANUAL_APPLIED"

    # 7. Case C: 60-Second Timeout Exceeded -> Move to "Apply Yourself"
    print(f"\n[TIMEOUT] 60s window elapsed without manual completion.")
    print(f"Queueing to 'Apply Yourself' Google Sheet tab for later manual apply...")

    append_apply_yourself_job({
        "platform": job.get("platform", "naukri"),
        "company": company,
        "title": title,
        "location": job.get("location", ""),
        "exp": job.get("exp", ""),
        "apply_url": direct_url,
        "job_url": source_url,
        "tailored_resume_path": resume_path,
        "reason": reason,
    })

    update_job_status_in_sheet1(
        job_id or source_url,
        "MOVED_TO_APPLY_YOURSELF",
        f"{reason} (Ready in Apply Yourself tab with tailored resume)",
        row_num=row_num,
    )

    log_application([
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "external (queued)",
        title,
        company,
        "queued",
        f"Moved to Apply Yourself tab: {reason}",
    ])

    return "MOVED_TO_APPLY_YOURSELF"


def run_external_applier(batch_size: int = 5, timeout_seconds: int = 60, dry_run: bool = False):
    profile = Profile.load("profile.yaml")
    jobs = load_pending_external_jobs(max_jobs=batch_size)

    if not jobs:
        print("No pending external jobs found to apply.")
        return 0

    print(f"\nStarting External Apply Runner (Batch size: {len(jobs)}, Manual Timeout: {timeout_seconds}s)...")

    session_naukri = Path("session_naukri.json")
    session_linkedin = Path("session_linkedin.json")
    storage_state = str(session_naukri) if session_naukri.exists() else None

    processed_count = 0
    with sync_playwright() as p:
        browser = launch_chrome_browser(p, browser_mode="minimized")
        context = browser.new_context(storage_state=storage_state) if storage_state else browser.new_context()
        if session_linkedin.exists():
            try:
                li_data = json.loads(session_linkedin.read_text())
                if "cookies" in li_data:
                    context.add_cookies(li_data["cookies"])
                    print("✓ Loaded LinkedIn session cookies.")
            except Exception as e:
                print(f"WARN loading LinkedIn session: {e}")

        for idx, job in enumerate(jobs, start=1):
            print(f"\n>>> [{idx}/{len(jobs)}] Processing queue: {job.get('title')} @ {job.get('company')}...")
            page = context.new_page()
            try:
                res = process_external_job(
                    page,
                    job,
                    profile,
                    timeout_seconds=timeout_seconds,
                    dry_run=dry_run,
                )
                processed_count += 1
            except Exception as e:
                print(f"ERROR processing job {job.get('title')}: {e}")
            finally:
                page.close()
                time.sleep(2)

        browser.close()

    print(f"\n========================================================")
    print(f"External Apply Runner completed: {processed_count} jobs processed.")
    print(f"========================================================")
    return processed_count


def main():
    parser = argparse.ArgumentParser(description="External Job Auto-Applier with Apply Yourself Queue")
    parser.add_argument("--batch-size", type=int, default=10, help="Number of external jobs to process in this run")
    parser.add_argument("--all", action="store_true", help="Process all pending external jobs in Sheet1")
    parser.add_argument("--timeout", type=int, default=60, help="Seconds to wait for manual intervention before moving to Apply Yourself")
    parser.add_argument("--dry-run", action="store_true", help="Preview form filling and resume selection without applying")
    args = parser.parse_args()

    batch_size = 2500 if args.all else args.batch_size
    run_external_applier(batch_size=batch_size, timeout_seconds=args.timeout, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
