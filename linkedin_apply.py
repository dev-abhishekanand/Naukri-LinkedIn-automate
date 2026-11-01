"""
LinkedIn Easy Apply. Requires session_linkedin.json from login_capture.py.

LinkedIn's automation detection is meaningfully tighter than Naukri's — keep
pace_seconds_between_actions generous, and expect this to need more manual
babysitting than the Naukri script. Stop instantly on any CAPTCHA, login
prompt, or "you've reached the Easy Apply limit" message.

Usage:
    python linkedin_apply.py
"""
import os
import sys
import argparse
import csv
import time
import re
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from common.browser_factory import launch_chrome_browser

from common.profile import Profile
from common import llm
from common.linkedin_referral_helper import (
    extract_people_from_job_page,
    send_referral_outreach,
    is_already_contacted,
)
from google_sheets_logger import append_applied_job, append_external_job, external_job_url_exists


class SkipJob(Exception):
    pass


def close_modal(page):
    try:
        dismiss_btn = page.locator('button[aria-label="Dismiss"], button[data-test-modal-close-btn]').first
        if dismiss_btn.is_visible():
            dismiss_btn.click()
            time.sleep(1)
        else:
            page.keyboard.press("Escape")
            time.sleep(1)
        discard_btn = page.locator('button[data-control-name="discard_application_confirm_btn"], button:has-text("Discard")').first
        if discard_btn.is_visible():
            discard_btn.click()
            time.sleep(1)
    except Exception:
        pass


SESSION_FILE = "session_linkedin.json"
LOG_FILE = "applications_log.csv"
EXTERNAL_LOG_FILE = "external_jobs.csv"

STOP_PHRASES = [
    "easy apply limit", "unusual activity", "verify it's you",
    "captcha", "security verification", "we've restricted",
]


def log_row(row: list):
    new_file = not Path(LOG_FILE).exists()
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["timestamp", "source", "title", "company", "status", "reason"])
        w.writerow(row)


def log_unapplied_job(card: dict, reason: str):
    """Logs any job not applied via Easy Apply to external_jobs.csv and Google Sheets."""
    new_file = not Path(EXTERNAL_LOG_FILE).exists() or Path(EXTERNAL_LOG_FILE).stat().st_size == 0
    with open(EXTERNAL_LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow([
                "timestamp", "platform", "job_id", "title", "company",
                "location", "experience", "job_url", "status", "notes"
            ])
        w.writerow([
            datetime.now().isoformat(),
            "linkedin",
            card.get("jobId", ""),
            card.get("title", ""),
            card.get("company", ""),
            card.get("location", ""),
            card.get("exp", ""),
            card.get("href", ""),
            "PENDING",
            reason,
        ])

    job_url = card.get("href", "")
    try:
        if job_url and external_job_url_exists(job_url):
            print(f"Google Sheets: Job already in tracker ({job_url})")
            return

        append_external_job({
            "discovered_at": datetime.now().isoformat(),
            "platform": "linkedin",
            "jobId": card.get("jobId", ""),
            "title": card.get("title", ""),
            "company": card.get("company", ""),
            "location": card.get("location", ""),
            "exp": card.get("exp", ""),
            "href": job_url,
            "status": "PENDING",
            "notes": reason,
            "tailored_resume_path": card.get("tailored_resume_path", ""),
        })
        print(f"Google Sheets: unapplied LinkedIn job logged ({card.get('title')} @ {card.get('company')})")
    except Exception as e:
        print(f"Google Sheets logging failed: {e}")


def log_applied_job(card: dict):
    """Logs successfully applied LinkedIn Easy Apply jobs to Google Sheets."""
    try:
        append_applied_job({
            "discovered_at": datetime.now().isoformat(),
            "platform": "linkedin",
            "jobId": card.get("jobId", ""),
            "title": card.get("title", ""),
            "company": card.get("company", ""),
            "location": card.get("location", ""),
            "exp": card.get("exp", ""),
            "href": card.get("href", ""),
            "notes": "Applied via LinkedIn Easy Apply",
        })
        print(f"Google Sheets: applied LinkedIn job logged ({card.get('title')} @ {card.get('company')})")
    except Exception as e:
        print(f"Google Sheets logging failed: {e}")


def extract_linkedin_job_details(page, card: dict) -> dict:
    details = dict(card)
    try:
        page_info = page.evaluate("""
            () => {
                const title = document.querySelector('h1, .job-details-jobs-unified-top-card__job-title, .jobs-unified-top-card__job-title')?.innerText?.trim();
                const company = document.querySelector('.job-details-jobs-unified-top-card__company-name, .jobs-unified-top-card__company-name, .topcard__org-name-link')?.innerText?.trim();
                const location = document.querySelector('.job-details-jobs-unified-top-card__bullet, .jobs-unified-top-card__bullet, .topcard__flavor--bullet')?.innerText?.trim();
                return { title, company, location };
            }
        """)
        if page_info and page_info.get("title"):
            details["title"] = page_info["title"]
        if page_info and page_info.get("company"):
            details["company"] = page_info["company"]
        if page_info and page_info.get("location"):
            details["location"] = page_info["location"]
    except Exception:
        pass

    if not details.get("jobId"):
        match = re.search(r'/jobs/view/(\d+)', details.get("href", ""))
        details["jobId"] = match.group(1) if match else ""

    return details


def page_has_stop_signal(page) -> str | None:
    text = page.inner_text("body").lower()
    for phrase in STOP_PHRASES:
        if phrase in text:
            return phrase
    if "/checkpoint/" in page.url or "/login" in page.url:
        return "session expired / checkpoint challenge"
    return None


def describe_modal(page) -> dict:

    return page.evaluate("""
        () => {
            const modal = document.querySelector(
                '.jobs-easy-apply-modal, [role="dialog"], .artdeco-modal'
            ) || document.body;

            const out = {
                heading: modal.querySelector('h2')?.innerText,
                fields: [],
                buttons: []
            };

            modal.querySelectorAll('input, textarea, select').forEach(el => {
                if (el.type === 'hidden') return;

                let label = '';

                if (el.id) {
                    const lbl = document.querySelector(`label[for="${el.id}"]`);
                    if (lbl) label = lbl.innerText.trim();
                }

                out.fields.push({
                    tag: el.tagName,
                    type: el.type || '',
                    id: el.id,
                    label,
                    value: el.value,
                    checked: el.checked
                });
            });

            modal.querySelectorAll('button').forEach(b => {
                const t = b.innerText.trim();
                if (t) out.buttons.push(t);
            });

            return out;
        }
    """)


def fill_text_field(page, field_id: str, text: str):
    page.evaluate(
        """([id, text]) => {
            const el = document.getElementById(id);
            if (!el) return false;
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, text);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            return true;
        }""",
        [field_id, text],
    )


def fill_form_step(page, profile: Profile, job_context: str):
    answers = profile.answer_library()
    state = describe_modal(page)
    if state.get("error"):
        time.sleep(1.5)
        state = describe_modal(page)

    for field in state.get("fields", []):
        label = (field.get("label") or "").lower()
        if not label or field.get("value"):
            continue  # already filled or unlabeled, leave it

        matched = None
        for key, val in answers.items():
            if key.replace("_", " ") in label:
                matched = val
                break

        if matched is not None:
            if field["tag"] == "SELECT":
                pass  # dropdowns handled separately below if needed
            else:
                fill_text_field(page, field["id"], str(matched))
        elif field["tag"] in ("INPUT",) and field["type"] == "text":
            draft = llm.draft_answer(label, profile.data, job_context)
            if draft.startswith("[NEEDS_HUMAN_INPUT"):
                raise SkipJob(f"profile gap on '{label}': {draft}")
            fill_text_field(page, field["id"], draft)


def click_modal_button(page, text: str) -> bool:
    return page.evaluate(
        """(text) => {
            const modal = document.querySelector('.jobs-easy-apply-modal, [role="dialog"], .artdeco-modal');
            if (!modal) return false;
            const btn = [...modal.querySelectorAll('button')].find(b => b.innerText.trim() === text);
            if (!btn) return false;
            btn.click();
            return true;
        }""",
        text,
    )


def run_one_application(page, profile: Profile, job_title: str, company: str) -> bool:
    job_context = f"{job_title} at {company}"

    easy_apply = page.get_by_role("button", name="Easy Apply").first
    if not easy_apply.is_visible():
        return False
    easy_apply.click()
    time.sleep(2)

    print("AFTER EASY APPLY CLICK:")
    print("URL:", page.url)
    print("TITLE:", page.title())
    print("EASY APPLY VISIBLE:", page.get_by_role("button", name="Easy Apply").first.is_visible())
    print("SUBMIT VISIBLE:", page.get_by_role("button", name="Submit application").first.is_visible())
    print("REVIEW VISIBLE:", page.get_by_role("button", name="Review").first.is_visible())

    for _ in range(10):  # hard cap on steps per application
        stop = page_has_stop_signal(page)
        if stop:
            raise RuntimeError(f"stop signal mid-application: {stop}")

        state = describe_modal(page)
        buttons = state.get("buttons", [])

        if not buttons:
         print("DEBUG STATE:", state)
         print("DEBUG URL:", page.url)
         print("DEBUG BODY:", page.locator("body").inner_text()[:5000])

        fill_form_step(page, profile, job_context)
        time.sleep(0.8)

        if "Submit application" in buttons:
            # Read the full review text before submitting — this is the safety net.
            review_text = page.locator("body").inner_text()
            print("--- Review before submit ---")
            print(review_text[:800])
            click_modal_button(page, "Submit application")
            time.sleep(2)
            done_clicked = click_modal_button(page, "Done")
            
            body_text = page.locator("body").inner_text().lower()
            if done_clicked or "application was sent" in body_text or "your application was sent" in body_text:
                return True
            
            # Strict confirmation: check if validation errors blocked submission
            errors = page.locator(".artdeco-inline-feedback--error, [data-test-form-element-error-messages]").all_inner_texts()
            err_msg = ", ".join(errors) if errors else "Submission confirmation not detected (modal did not dismiss)"
            raise SkipJob(f"LinkedIn submission blocked by validation error: {err_msg}")
        elif "Review" in buttons:
            click_modal_button(page, "Review")
        elif "Next" in buttons:
            click_modal_button(page, "Next")
        else:
            raise SkipJob(f"unrecognized modal state, buttons={buttons}")
        time.sleep(1.2)

    raise SkipJob("exceeded step cap without reaching submit")


def run(unattended: bool = False, referrals_only: bool = False):
    profile = Profile.load()
    if not Path(SESSION_FILE).exists():
        print(f"NOTICE: {SESSION_FILE} not found. Skipping LinkedIn run.")
        print("To enable LinkedIn Easy Apply, run: python login_capture.py linkedin")
        log_row([datetime.now(), "linkedin", "-", "-", "skipped", f"{SESSION_FILE} not found"])
        return

    is_unattended = unattended or os.environ.get("UNATTENDED") == "1" or not sys.stdin.isatty()
    if is_unattended:
        print("Running LinkedIn in UNATTENDED mode: any prompt requiring human input will automatically skip.")

    enable_referrals = profile.data.get("linkedin_referral_outreach", True)
    max_referrals = profile.data.get("linkedin_max_referrals_per_run", 5)
    referrals_sent = 0
    applied = 0

    with sync_playwright() as p:
        browser_mode = profile.data.get("browser_mode", "minimized")
        browser = launch_chrome_browser(p, browser_mode=browser_mode, slow_mo=150)
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        for role in profile.target_roles:
            if applied >= profile.stop_after_n_applications and not referrals_only:
                break
            easy_apply_only = profile.data.get("linkedin_easy_apply_only", True) and not referrals_only
            easy_apply_filter = "&f_AL=true" if easy_apply_only else ""
            search_url = (
                "https://www.linkedin.com/jobs/search/?keywords="
                + role.replace(" ", "%20")
                + "&location=India&geoId=102713980"
                + easy_apply_filter
            )
            print(f"\n--- Searching LinkedIn: {role} ---")
            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                err_str = str(e)
                if "ERR_INTERNET_DISCONNECTED" in err_str or "ERR_NAME_NOT_RESOLVED" in err_str:
                    print(f"FATAL: Internet disconnected during LinkedIn search: {e}")
                    try:
                        browser.close()
                    except Exception:
                        pass
                    sys.exit(2)
                print(f"  (search navigation error for {role}: {e}, skipping role)")
                continue
            time.sleep(3)

            stop = page_has_stop_signal(page)
            if stop:
                print(f"STOPPING: {stop}")
                log_row([datetime.now(), "linkedin", "-", "-", "stopped", stop])
                browser.close()
                return

            cards = page.evaluate("""
                () => {
                    const seen = new Set();
                    return Array.from(document.querySelectorAll('a[href*="/jobs/view/"]'))
                        .map(a => ({
                            title: a.innerText?.trim().split("\\n")[0],
                            company: a.closest("li")?.innerText?.trim() || "",
                            href: a.href
                        }))
                        .filter(c => c.title && c.href && !seen.has(c.href))
                        .filter(c => {
                            seen.add(c.href);
                            return true;
                        });
                }
            """)

            print(f"Found {len(cards)} LinkedIn job candidates")
            for idx, card in enumerate(cards):
                print(f"Candidate {idx + 1}: {card.get('title')} | {card.get('href')}")

                if applied >= profile.stop_after_n_applications and not referrals_only:
                    break
                try:
                    print(f"ATTEMPTING: {card.get('title')}")
                    page.goto(card["href"], wait_until="commit", timeout=15000)
                    time.sleep(1.5)
                    card = extract_linkedin_job_details(page, card)

                    from location_filter import is_india_job
                    if not is_india_job(
                        location=card.get("location", ""),
                        title=card.get("title", ""),
                        company=card.get("company", ""),
                        url=card.get("href", ""),
                    ):
                        print(f"Skipping foreign / non-India job: {card.get('title')} @ {card.get('company')} ({card.get('location')})")
                        log_row([
                            datetime.now(),
                            "linkedin",
                            card.get("title"),
                            card.get("company"),
                            "skipped",
                            f"foreign location: {card.get('location')}",
                        ])
                        continue

                    # Extract JD text for tailoring
                    jd_text = page.evaluate("""
                        () => document.querySelector('.jobs-description__content, .jobs-box__html-content, .job-details-jobs-unified-top-card__content')?.innerText?.trim() || ''
                    """)

                    # Generate job-specific tailored resume in generated/
                    tailored_resume_path = ""
                    try:
                        from common.ats_pipeline import prepare_tailored_resume
                        safe_title = re.sub(r'[^A-Za-z0-9]+', '_', card.get("title", "job"))[:35]
                        safe_comp = re.sub(r'[^A-Za-z0-9]+', '_', card.get("company", "company"))[:25]
                        job_id = card.get("jobId") or str(int(time.time()))
                        out_path = f"generated/Abhishek_Anand_{safe_comp}_{safe_title}_{job_id}.docx"
                        os.makedirs("generated", exist_ok=True)
                        content_for_tailoring = jd_text if len(jd_text) > 40 else f"{card.get('title')} React Frontend Developer at {card.get('company')}"
                        ats_res = prepare_tailored_resume(content_for_tailoring, output_path=out_path)
                        tailored_resume_path = str(ats_res.get("tailored_resume_path", out_path))
                        card["tailored_resume_path"] = tailored_resume_path
                        print(f"  ✓ Tailored resume generated: {tailored_resume_path}")
                    except Exception as e:
                        tailored_resume_path = "Abhishek_Anand_Resume.docx"
                        card["tailored_resume_path"] = tailored_resume_path

                    success = False
                    if not referrals_only:
                        success = run_one_application(page, profile, card.get("title", ""), card.get("company", ""))
                        if success:
                            applied += 1
                            log_row([datetime.now(), "linkedin", card.get("title"),
                                      card.get("company"), "applied", ""])
                            print(f"Applied: {card.get('title')} @ {card.get('company')} ({applied} total)")
                            log_applied_job(card)
                        else:
                            close_modal(page)
                            reason = "no Easy Apply button (External company portal)"
                            log_row([datetime.now(), "linkedin", card.get("title"),
                                      card.get("company"), "skipped", reason])
                            print(f"Not applied via Easy Apply: {card.get('title')} @ {card.get('company')} — routing to Sheet1 & Apply Yourself")
                            log_unapplied_job(card, reason)
                            try:
                                from google_sheets_logger import append_apply_yourself_job
                                append_apply_yourself_job({
                                    "platform": "linkedin",
                                    "company": card.get("company", ""),
                                    "title": card.get("title", ""),
                                    "location": card.get("location", ""),
                                    "exp": card.get("exp", ""),
                                    "job_url": card.get("href", ""),
                                    "apply_url": card.get("href", ""),
                                    "tailored_resume_path": tailored_resume_path,
                                    "reason": "LinkedIn Easy Apply unavailable / External portal",
                                    "status": "PENDING_USER_APPLY"
                                })
                            except Exception as e:
                                print(f"  [Apply Yourself] Logging notice: {e}")

                    # --- REFERRAL OUTREACH & MESSAGING ---
                    # Check for hiring team, job poster, or company connections / alumni
                    if enable_referrals and referrals_sent < max_referrals:
                        try:
                            people = extract_people_from_job_page(page)
                            if people:
                                print(f"  [Referral] Found {len(people)} people associated with job ({card.get('title')} @ {card.get('company')})")
                            outreach_sent_for_job = False
                            for person in people:
                                if referrals_sent >= max_referrals:
                                    break
                                p_url = person.get("profile_url")
                                if p_url and not is_already_contacted(p_url):
                                    res = send_referral_outreach(
                                        page,
                                        person,
                                        card.get("title", ""),
                                        card.get("company", ""),
                                        job_url=card.get("href", ""),
                                        tailored_resume_path=tailored_resume_path,
                                    )
                                    if res.get("status") == "SENT":
                                        referrals_sent += 1
                                        outreach_sent_for_job = True
                                        time.sleep(2)
                                        # Return to job URL if navigated away
                                        if page.url != card.get("href"):
                                            try:
                                                page.goto(card["href"], wait_until="commit", timeout=15000)
                                                time.sleep(1.5)
                                            except Exception:
                                                pass

                            # If referral outreach could not be sent (e.g. limit reached, InMail lock, or skipping)
                            # and job wasn't submitted natively, ensure it is safely queued in Apply Yourself
                            if not outreach_sent_for_job and not success and not referrals_only:
                                try:
                                    from google_sheets_logger import append_apply_yourself_job
                                    append_apply_yourself_job({
                                        "platform": "linkedin",
                                        "company": card.get("company", ""),
                                        "title": card.get("title", ""),
                                        "location": card.get("location", ""),
                                        "exp": card.get("exp", ""),
                                        "job_url": card.get("href", ""),
                                        "apply_url": card.get("href", ""),
                                        "tailored_resume_path": tailored_resume_path,
                                        "reason": "Referral outreach restricted / External portal application needed",
                                        "status": "PENDING_USER_APPLY"
                                    })
                                except Exception as e:
                                    print(f"  [Apply Yourself] Fallback logging notice: {e}")
                        except Exception as e:
                            print(f"  [Referral Notice] Error checking people: {e}")

                except SkipJob as e:
                    reason = f"Easy Apply skipped: {e}"
                    print(f"Skipping job: {e} — routing to Sheet1 & Apply Yourself")
                    close_modal(page)
                    log_row([datetime.now(), "linkedin", card.get("title"),
                              card.get("company"), "skipped", reason])
                    log_unapplied_job(card, reason)
                    try:
                        from google_sheets_logger import append_apply_yourself_job
                        append_apply_yourself_job({
                            "platform": "linkedin",
                            "company": card.get("company", ""),
                            "title": card.get("title", ""),
                            "location": card.get("location", ""),
                            "exp": card.get("exp", ""),
                            "job_url": card.get("href", ""),
                            "apply_url": card.get("href", ""),
                            "tailored_resume_path": card.get("tailored_resume_path", "Abhishek_Anand_Resume.docx"),
                            "reason": f"Easy Apply skipped: {e}",
                            "status": "PENDING_USER_APPLY"
                        })
                    except Exception as e:
                        print(f"  [Apply Yourself] Logging notice: {e}")
                    continue
                except RuntimeError as e:
                    print(f"STOPPING: {e}")
                    close_modal(page)
                    log_row([datetime.now(), "linkedin", card.get("title"),
                              card.get("company"), "stopped", str(e)])
                    browser.close()
                    return
                except Exception as e:
                    err_str = str(e)
                    print(f"WARN: Error processing LinkedIn job {card.get('title')}: {e}")
                    log_row([datetime.now(), "linkedin", card.get("title"),
                              card.get("company"), "error", err_str[:100]])
                    if "TargetClosedError" in err_str or "target page, context or browser has been closed" in err_str.lower():
                        print("Browser or target page was closed. Terminating LinkedIn run gracefully.")
                        break
                    try:
                        close_modal(page)
                    except Exception:
                        pass
                    continue

                time.sleep(profile.pace_seconds_between_actions)

        browser.close()

    print(
        f"\nDone. {applied} applications submitted, {referrals_sent} referral outreach requests sent this run. "
        f"See {LOG_FILE} and linkedin_referrals_contacted.json for full logs."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LinkedIn auto-apply and referral bot")
    parser.add_argument("--unattended", action="store_true", help="Run in unattended mode")
    parser.add_argument("--referrals-only", action="store_true", help="Run referral outreach only (skip Easy Apply)")
    args = parser.parse_args()
    run(unattended=args.unattended, referrals_only=args.referrals_only)
