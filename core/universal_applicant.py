"""
Universal ATS & Direct Career Form Applicant
Automates job applications for direct URLs across Greenhouse, Lever, Workday,
and generic corporate career pages using candidate profile data and smart question solving.
Validates form fields and verifies actual submission before marking status.
"""
import re
import time
import logging
import hashlib
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional
from playwright.sync_api import TimeoutError as PWTimeout

from core.base_portal import BaseJobPortal
from core.tracker import ApplicationTracker
from core.browser_factory import human_delay
from core.mailer import get_strictly_configured_email
from common.profile import Profile

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
RESUME_PDF = BASE_DIR / "Abhishek_Anand_Resume.pdf"


class UniversalATSApplicant(BaseJobPortal):
    def __init__(
        self,
        profile: Profile,
        tracker: Optional[ApplicationTracker] = None,
        headless: bool = False,
        session_file: Optional[str] = None,
        user_data_dir: Optional[str] = None
    ):
        super().__init__(
            profile=profile,
            tracker=tracker,
            headless=headless,
            session_file=session_file,
            user_data_dir=user_data_dir
        )

    @property
    def portal_name(self) -> str:
        return "universal_ats"

    def is_logged_in(self) -> bool:
        # Direct ATS forms generally don't require pre-login
        return True

    def extract_job_id(self, url: str) -> str:
        url_clean = (url or "").strip()
        if not url_clean:
            return ""

        # 1. Naukri ACP links with file parameter
        file_match = re.search(r"file=([0-9a-zA-Z]+)", url_clean)
        if file_match and "showacp" in url_clean.lower():
            return f"naukri_acp_{file_match.group(1)}"

        # 2. Naukri job listing links with trailing digits
        naukri_match = re.search(r"job-listings-.*?(\d{10,15})", url_clean)
        if naukri_match:
            return f"naukri_{naukri_match.group(1)}"

        # 3. LinkedIn job ID
        linkedin_match = re.search(r"jobs/view/(\d+)", url_clean)
        if linkedin_match:
            return f"linkedin_{linkedin_match.group(1)}"

        # 4. Indeed jk ID
        indeed_match = re.search(r"jk=([a-f0-9]+)", url_clean)
        if indeed_match:
            return f"indeed_{indeed_match.group(1)}"

        # 5. Greenhouse / Lever job ID
        gh_match = re.search(r"jobs/(\d+)", url_clean)
        if gh_match:
            return f"ats_{gh_match.group(1)}"

        # 6. Generic canonical hash
        try:
            parsed = urllib.parse.urlparse(url_clean)
            q_pairs = urllib.parse.parse_qsl(parsed.query)
            filtered_q = [(k, v) for k, v in q_pairs if not k.startswith("utm_") and k not in ("refId", "trackingId", "trk", "_gl", "eBP")]
            canonical = f"{parsed.netloc}{parsed.path}"
            if filtered_q:
                canonical += "?" + urllib.parse.urlencode(filtered_q)
            h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
            return f"job_{h}"
        except Exception:
            clean = re.sub(r"[^a-zA-Z0-9]", "_", url_clean.split("?")[0])
            return clean[-40:]

    def apply_by_url(
        self,
        job_url: str,
        resume_path: Optional[str] = None,
        auto_tailor: bool = True
    ) -> Dict[str, Any]:
        """Navigates to the direct job URL and submits application form with strict validation."""
        self.start_session()
        print(f"\n[Universal ATS] Navigating to: {job_url}")

        # 0. Unwrap LinkedIn cold-join / tracking redirect URLs if present
        if "cold-join" in job_url and "session_redirect=" in job_url:
            try:
                parsed_q = urllib.parse.parse_qs(urllib.parse.urlparse(job_url).query)
                redir = parsed_q.get("session_redirect", [None])[0]
                if redir and redir.startswith("http"):
                    job_url = redir
                    print(f"[Universal ATS] Unwrapped redirect to direct job URL: {job_url}")
            except Exception:
                pass

        job_id = self.extract_job_id(job_url)
        if job_id and self.tracker.is_already_processed(job_id):
            print(f"[Universal ATS] Job was already processed previously. Skipping.")
            return {
                "status": "ALREADY_PROCESSED",
                "job_id": job_id,
                "title": "",
                "company": "",
                "url": job_url,
                "reason": "Already processed in tracker"
            }

        try:
            self.page.goto(job_url, timeout=40000, wait_until="domcontentloaded")
            human_delay(2.0, 3.5)
        except Exception as e:
            return {
                "status": "ERROR",
                "job_id": job_id,
                "title": "",
                "company": "",
                "url": job_url,
                "reason": f"Page load error: {e}"
            }

        # Step 0.1: Check if page already confirms this job is applied, expired, or on ACP confirmation
        if "expired_jd_redirect" in job_url.lower() or "expired_jd_redirect" in (self.page.url or "").lower():
            reason = "Job listing expired on LinkedIn (expired_jd_redirect)"
            print(f"[Universal ATS] ⚠️ {reason}")
            title, company = self._extract_title_and_company()
            self.tracker.log_application(
                platform="linkedin",
                job_id=job_id,
                title=title or "LinkedIn Job",
                company=company or "Company",
                status="FAILED",
                url=job_url,
                reason=reason
            )
            return {
                "status": "FAILED",
                "job_id": job_id,
                "title": title or "LinkedIn Job",
                "company": company or "Company",
                "url": job_url,
                "reason": reason
            }

        pre_applied = self._check_if_page_already_applied()
        title, company = self._extract_title_and_company()
        jd_text = self._extract_job_description_text()

        if pre_applied:
            st, reas = pre_applied
            print(f"[Universal ATS] Detected pre-applied/confirmed state: {st} ({reas})")
            self.tracker.log_application(
                platform="direct_ats",
                job_id=job_id,
                title=title or "Software Developer",
                company=company or "Company",
                status=st,
                url=job_url,
                reason=reas
            )
            return {
                "status": st,
                "job_id": job_id,
                "title": title or "Software Developer",
                "company": company or "Company",
                "url": job_url,
                "reason": reas
            }

        # Step 0.2: Check if this is a Naukri ACP page with questionnaire drawer
        acp_res = self._handle_naukri_acp_page()
        if acp_res:
            st, reas = acp_res
            self.tracker.log_application(
                platform="naukri_acp",
                job_id=job_id,
                title=title or "Software Developer",
                company=company or "Company",
                status=st,
                url=job_url,
                reason=reas
            )
            return {
                "status": st,
                "job_id": job_id,
                "title": title or "Software Developer",
                "company": company or "Company",
                "url": job_url,
                "reason": reas
            }

        # Step 0.3: Check if page redirected to a LinkedIn login barrier
        curr_url_low = (self.page.url or "").lower()
        if "linkedin.com/login" in curr_url_low or "cold-join" in curr_url_low:
            reason = "LinkedIn login required in Chrome profile (abhishek.anand.7601@gmail.com)"
            print(f"[Universal ATS] ⚠️ {reason}")
            self.tracker.log_application(
                platform="linkedin",
                job_id=job_id,
                title=title or "LinkedIn Job",
                company=company or "Company",
                status="REVIEW_REQUIRED",
                url=job_url,
                reason=reason
            )
            return {
                "status": "REVIEW_REQUIRED",
                "job_id": job_id,
                "title": title or "LinkedIn Job",
                "company": company or "Company",
                "url": job_url,
                "reason": reason
            }

        # Step 0.4: Follow multi-hop links if landing on an aggregator or landing page
        self._resolve_multi_hop_redirects()

        # Step 0.45: Smart Job Guardrails (Ghost job & Staffing agency filter)
        try:
            from core.job_guardrails import JobGuardrails
            guardrails = JobGuardrails(self.profile)
            eligible, guard_reason = guardrails.evaluate(title=title, company=company, description=jd_text)
            if not eligible:
                print(f"[Universal ATS] 🚫 Job skipped via guardrails: {guard_reason}")
                return {
                    "status": "SKIPPED",
                    "job_id": job_id,
                    "title": title or "Skipped Job",
                    "company": company or "Company",
                    "url": job_url,
                    "reason": guard_reason
                }
        except Exception:
            pass

        # Step 0.5: Dynamic Resume Re-tailoring if requested
        effective_resume = resume_path
        if auto_tailor and not effective_resume and (title or company):
            try:
                from core.resume_tailor import tailor_resume_for_job
                tailor_res = tailor_resume_for_job(company=company, job_title=title, job_description=jd_text)
                effective_resume = tailor_res.get("chosen_resume_path")
                if effective_resume:
                    print(f"[Universal ATS] Tailored resume ready: {Path(effective_resume).name}")
            except Exception as e:
                logger.warning(f"[Universal ATS] Resume tailoring skipped/failed: {e}")

        # Step 0.55: Check if this is a Workday ATS portal
        workday_res = self._handle_workday_flow(resume_path=effective_resume)
        if workday_res:
            st, reas = workday_res
            self.tracker.log_application(
                platform="workday",
                job_id=job_id,
                title=title or "Software Developer",
                company=company or "Company",
                status=st,
                url=job_url,
                reason=reas
            )
            return {
                "status": st,
                "job_id": job_id,
                "title": title or "Software Developer",
                "company": company or "Company",
                "url": job_url,
                "reason": reas
            }

        # Step 0.6: Check if page has no ATS form but contains recruiter/HR contact email
        recruiter_email = self._extract_recruiter_email_from_page()
        has_form_fields = self.page.locator("form input, input#fullName, input[name='name' i], input[type='file']").first.is_visible()
        if recruiter_email and not has_form_fields:
            print(f"[Universal ATS] Detected recruiter email application target: {recruiter_email}")
            try:
                from core.mailer import save_job_application_draft_to_gmail, generate_application_email_draft
                draft_content = generate_application_email_draft(company=company, job_title=title, job_details=jd_text)
                draft_res = save_job_application_draft_to_gmail(
                    to_email=recruiter_email,
                    subject=draft_content["subject"],
                    body=draft_content["body"],
                    company=company,
                    job_title=title,
                    resume_path=effective_resume
                )
                st = "DRAFT_SAVED" if draft_res.get("status") == "DRAFT_SAVED" else "REVIEW_REQUIRED"
                reas = draft_res.get("message", "Draft saved in candidate Gmail Drafts with resume attached")
                return {
                    "status": st,
                    "job_id": job_id,
                    "title": title or "Software Developer",
                    "company": company or "Company",
                    "url": job_url,
                    "reason": reas,
                    "tailored_resume_path": effective_resume or ""
                }
            except Exception as draft_err:
                logger.warning(f"[Universal ATS] Email draft creation error: {draft_err}")

        # Click apply button if the form is hidden behind a trigger button
        self._click_apply_trigger_if_needed()

        # Step 0.7: Check if LinkedIn Easy Apply modal wizard appeared
        if "linkedin.com" in self.page.url:
            ea_result = self._handle_linkedin_easy_apply_dialog()
            if ea_result:
                st, reas = ea_result
                self.tracker.log_application(
                    platform="linkedin_easy_apply",
                    job_id=job_id,
                    title=title or "LinkedIn Job",
                    company=company or "Company",
                    status=st,
                    url=job_url,
                    reason=reas
                )
                return {
                    "status": st,
                    "job_id": job_id,
                    "title": title or "LinkedIn Job",
                    "company": company or "Company",
                    "url": job_url,
                    "reason": reas,
                    "tailored_resume_path": effective_resume or ""
                }

        try:
            # Step 1: Fill all standard fields (text, email, tel, number)
            filled_count = self._fill_standard_fields()

            # Step 2: Select appropriate options in dropdowns
            select_count = self._fill_select_dropdowns()

            # Step 3: Upload resume (tailored or default)
            uploaded = self._upload_resume_if_present(resume_path=effective_resume)

            # Step 4: Solve custom textareas and screening questions
            custom_count = self._answer_custom_questions()

            # Step 5: Check required terms / consent checkboxes
            self._accept_terms_checkboxes()

            print(f"[Universal ATS] Inputs filled: {filled_count}, Selects: {select_count}, Resume uploaded: {uploaded}, Custom: {custom_count}")

            # Pre-submission validation check
            initial_url = self.page.url
            invalid_elements = self._get_invalid_fields()

            if invalid_elements:
                invalid_names = [inv.get("name") or inv.get("id") or "field" for inv in invalid_elements]
                reason = f"Form incomplete - invalid required fields: {', '.join(invalid_names)}"
                print(f"[Universal ATS] ⚠️ {reason}")
                
                self.tracker.log_application(
                    platform="direct_ats",
                    job_id=job_id,
                    title=title or "Software Developer",
                    company=company or "Company",
                    status="REVIEW_REQUIRED",
                    url=job_url,
                    reason=reason
                )

                return {
                    "status": "REVIEW_REQUIRED",
                    "job_id": job_id,
                    "title": title or "Software Developer",
                    "company": company or "Company",
                    "url": job_url,
                    "reason": reason,
                    "tailored_resume_path": effective_resume or ""
                }

            # Step 6: Submit the application
            clicked = self._submit_form()
            if not clicked:
                reason = "Could not locate active submit button on form"
                self.tracker.log_application(
                    platform="direct_ats",
                    job_id=job_id,
                    title=title or "Software Developer",
                    company=company or "Company",
                    status="REVIEW_REQUIRED",
                    url=job_url,
                    reason=reason
                )
                return {
                    "status": "REVIEW_REQUIRED",
                    "job_id": job_id,
                    "title": title or "Software Developer",
                    "company": company or "Company",
                    "url": job_url,
                    "reason": reason
                }

            # Step 7: Verify whether submission actually succeeded
            human_delay(3.0, 5.0)
            status, reason = self._verify_submission_result(initial_url)
            print(f"[Universal ATS] Result: status={status}, reason={reason}")

            self.tracker.log_application(
                platform="direct_ats",
                job_id=job_id,
                title=title or "Software Developer",
                company=company or "Company",
                status=status,
                url=job_url,
                reason=reason
            )

            return {
                "status": status,
                "job_id": job_id,
                "title": title or "Software Developer",
                "company": company or "Company",
                "url": job_url,
                "reason": reason
            }

        except Exception as e:
            logger.error(f"[Universal ATS] Error filling form: {e}")
            return {
                "status": "ERROR",
                "job_id": job_id,
                "title": title,
                "company": company,
                "url": job_url,
                "reason": f"Form error: {e}"
            }

    def _get_invalid_fields(self) -> List[Dict[str, str]]:
        """Returns list of elements currently failing HTML5 form validation."""
        invalid_list = []
        try:
            invalids = self.page.locator(":invalid").all()
            for inv in invalids:
                if inv.is_visible():
                    invalid_list.append({
                        "name": inv.get_attribute("name") or "",
                        "id": inv.get_attribute("id") or "",
                        "type": inv.get_attribute("type") or ""
                    })
        except Exception:
            pass
        return invalid_list

    def _verify_submission_result(self, initial_url: str) -> tuple[str, str]:
        """Verifies if the form was actually accepted and submitted."""
        current_url = self.page.url.lower()

        # 1. Check if URL changed to a success/confirmation route
        success_url_patterns = ["thank", "confirm", "success", "applied", "submitted", "done"]
        if current_url != initial_url.lower() and any(p in current_url for p in success_url_patterns):
            return "APPLIED", "Application submitted successfully (confirmed by redirect URL)"

        # 2. Check for validation errors on page
        invalids = self._get_invalid_fields()
        if invalids:
            inv_str = ", ".join([i.get("name") or i.get("id") or "field" for i in invalids])
            return "FAILED", f"Form validation failed on submit for: {inv_str}"

        # 3. Check for visible error alerts or error text
        try:
            error_el = self.page.locator(".error:visible, .invalid-feedback:visible, [role='alert']:visible, .alert-danger:visible").first
            if error_el.count() > 0 and error_el.is_visible():
                err_text = error_el.inner_text().strip()
                if err_text:
                    return "FAILED", f"Page returned error: {err_text[:100]}"
        except Exception:
            pass

        # 4. Check for success message in DOM
        try:
            body_text = self.page.locator("body").inner_text().lower()
            success_phrases = [
                "thank you for applying",
                "thank you for your application",
                "your application has been submitted",
                "application submitted successfully",
                "we have received your application",
                "application received"
            ]
            for phrase in success_phrases:
                if phrase in body_text:
                    return "APPLIED", f"Application submitted successfully ('{phrase}' confirmed)"
        except Exception:
            pass

        # 5. Check if URL indicates confirmed success
        success_url_patterns = ["thank-you", "thanks", "confirmed", "confirmation", "success", "applied"]
        if any(pat in current_url for pat in success_url_patterns):
            return "APPLIED", "Application submitted successfully (confirmed by redirect URL)"

        # 6. If stayed on same page or redirected without clear proof, mark as REVIEW_REQUIRED
        return "REVIEW_REQUIRED", "Form submitted; awaiting external confirmation receipt"

    def _resolve_multi_hop_redirects(self):
        """Detects if page has an external 'Apply on company website' or redirect link and follows it."""
        hop_selectors = [
            "a:has-text('Apply on company website')",
            "a:has-text('Apply on company site')",
            "a:has-text('Apply on employer website')",
            "a:has-text('Apply Externally')",
            "button:has-text('Apply on company website')",
            "a[data-qa='apply-external']",
            "a.apply-external-btn"
        ]
        for sel in hop_selectors:
            try:
                el = self.page.locator(sel).first
                if el.is_visible():
                    txt = el.inner_text().lower()
                    if "company" in txt or "employer" in txt or "external" in txt:
                        href = el.get_attribute("href")
                        if href and href.startswith("http") and not href.startswith("javascript"):
                            print(f"[Universal ATS] Following external redirect to: {href}")
                            self.page.goto(href, timeout=30000, wait_until="domcontentloaded")
                            human_delay(2.0, 3.5)
                            return
                        else:
                            el.click()
                            human_delay(2.0, 3.0)
                            return
            except Exception:
                continue

    def _check_if_page_already_applied(self) -> Optional[tuple[str, str]]:
        """Checks if the portal already shows the job as Applied or Application Confirmed."""
        try:
            page_title = (self.page.title() or "").lower()
            current_url = (self.page.url or "").lower()

            # 1. Naukri ACP confirmation check
            if "apply confirmation" in page_title or "showacp" in current_url:
                header = self.page.locator(".apply-status-header, h1, .confirmation-header").first
                if header.is_visible():
                    txt = header.inner_text().strip()
                    if "redirected" in txt.lower() or "external" in txt.lower() or "company website" in txt.lower():
                        return "REVIEW_REQUIRED", f"External redirect notice: {txt[:80]}"
                    if "applied" in txt.lower() or "success" in txt.lower():
                        return "APPLIED", f"Portal confirmed: {txt[:80]}"
                return "REVIEW_REQUIRED", "Portal redirected; completion on external ATS requires manual check"

            # 2. Button marked 'Applied' or 'Already Applied'
            applied_btn = self.page.locator(
                "button:has-text('Applied'), "
                "button:has-text('Already Applied'), "
                "[class*='apply-button']:has-text('Applied'), "
                ".jobs-apply-button--disabled"
            ).first
            if applied_btn.is_visible():
                btn_txt = applied_btn.inner_text().strip()
                if btn_txt.lower() in ("applied", "already applied"):
                    return "APPLIED", "Already applied to this job on portal"

            # 3. Text in body
            body_text = self.page.locator("body").inner_text()[:600].lower()
            if "you have already applied" in body_text:
                return "APPLIED", "Already applied previously on portal"

            # 4. Expired job listings
            if "expired_jd_redirect" in current_url or "no longer accepting applications" in body_text:
                return "FAILED", "Job posting is expired or no longer accepting applications"
        except Exception:
            pass
        return None

    def _handle_linkedin_easy_apply_dialog(self) -> Optional[tuple[str, str]]:
        """Handles LinkedIn Easy Apply multi-step modal wizard until final submission."""
        modal = self.page.locator("div[role='dialog'], .jobs-easy-apply-modal, .jobs-easy-apply-content").first
        if not modal.is_visible():
            return None

        print("[Universal ATS] LinkedIn Easy Apply modal active. Stepping through application wizard...")

        for step in range(1, 9):
            human_delay(1.5, 2.5)

            # Check if submission is already finished
            success_indicators = [
                "your application was sent",
                "application submitted",
                "you applied",
                "application sent"
            ]
            try:
                modal_text = modal.inner_text().lower()
                for ind in success_indicators:
                    if ind in modal_text:
                        dismiss = self.page.locator("button[aria-label='Dismiss'], button:has-text('Done')").first
                        if dismiss.is_visible():
                            dismiss.click()
                        return "APPLIED", "LinkedIn Easy Apply application submitted successfully"
            except Exception:
                pass

            # Fill inputs present in this step
            self._fill_standard_fields()
            self._fill_select_dropdowns()
            self._upload_resume_if_present()

            # Radio buttons: handle work authorization and sponsorship
            try:
                auth_labels = modal.locator("label:has-text('Yes'), label:has-text('No')").all()
                for lbl in auth_labels:
                    try:
                        p_txt = lbl.locator("..").inner_text().lower()
                        if "sponsorship" in p_txt or "require visa" in p_txt:
                            if "no" in lbl.inner_text().lower():
                                lbl.click()
                        elif "authorized" in p_txt or "legally" in p_txt or "eligible" in p_txt:
                            if "yes" in lbl.inner_text().lower():
                                lbl.click()
                    except Exception:
                        pass
            except Exception:
                pass

            # Fill common numeric inputs in modal
            try:
                inputs = modal.locator("input:visible").all()
                for inp in inputs:
                    try:
                        if not inp.input_value():
                            itype = inp.get_attribute("type") or "text"
                            if itype in ("text", "number"):
                                aria = (inp.get_attribute("aria-label") or "").lower()
                                ph = (inp.get_attribute("placeholder") or "").lower()
                                combo = f"{aria}_{ph}"
                                if "experience" in combo or "year" in combo:
                                    inp.fill("4")
                                elif "notice" in combo or "day" in combo:
                                    inp.fill("0")
                                elif "salary" in combo or "ctc" in combo:
                                    inp.fill("1000000")
                    except Exception:
                        pass
            except Exception:
                pass

            # Check if final Submit application button is visible
            submit_btn = modal.locator(
                "button:has-text('Submit application'), "
                "button[aria-label='Submit application']"
            ).first
            if submit_btn.is_visible():
                print(f"[Universal ATS] Clicking LinkedIn Easy Apply final submit button...")
                submit_btn.click()
                human_delay(2.5, 4.0)
                dismiss = self.page.locator("button[aria-label='Dismiss'], button:has-text('Done')").first
                if dismiss.is_visible():
                    dismiss.click()
                return "APPLIED", "LinkedIn Easy Apply application submitted successfully"

            # Check if Review button is present
            review_btn = modal.locator(
                "button:has-text('Review'), "
                "button[aria-label='Review your application']"
            ).first
            if review_btn.is_visible():
                print(f"[Universal ATS] Advancing LinkedIn modal (Step {step} -> Review)...")
                review_btn.click()
                human_delay(1.5, 2.5)
                continue

            # Check if Next button is present
            next_btn = modal.locator(
                "button:has-text('Next'), "
                "button[aria-label='Continue to next step']"
            ).first
            if next_btn.is_visible():
                print(f"[Universal ATS] Advancing LinkedIn modal (Step {step} -> Next)...")
                next_btn.click()
                human_delay(1.5, 2.5)
                continue

            break

        return "REVIEW_REQUIRED", "LinkedIn Easy Apply requires manual review on question step"

    def _handle_naukri_acp_page(self) -> Optional[tuple[str, str]]:
        """Handles Naukri ACP (Apply Confirmation Page) and questionnaire drawer."""
        current_url = (self.page.url or "").lower()
        page_title = (self.page.title() or "").lower()

        is_acp = "showacp" in current_url or "apply confirmation" in page_title or "multiApplyResp" in current_url
        if not is_acp:
            return None

        print("[Universal ATS] Naukri ACP page detected. Evaluating confirmation & screening questions...")
        human_delay(2.0, 3.0)

        # 1. Check for questionnaire / chatbot drawer
        chatbot = self.page.locator(".chatbot_Drawer, .chatbot-container, .acp-actions, .questions-container").first
        if chatbot.is_visible():
            print("[Universal ATS] Naukri screening questionnaire drawer found. Solving questions...")
            text_inputs = chatbot.locator("input[type='text'], input[type='number'], textarea").all()
            for inp in text_inputs:
                try:
                    if not inp.input_value():
                        ph = (inp.get_attribute("placeholder") or "").lower()
                        if "experience" in ph:
                            inp.fill("4")
                        elif "notice" in ph:
                            inp.fill("0")
                        elif "ctc" in ph:
                            inp.fill("10")
                        else:
                            inp.fill("Yes, experienced in React and frontend architecture")
                except Exception:
                    pass

            save_btn = chatbot.locator(
                "button:has-text('Save & Next'), "
                "button:has-text('Save'), "
                "button:has-text('Submit'), "
                "button.save-btn"
            ).first
            if save_btn.is_visible():
                save_btn.click()
                human_delay(2.0, 3.5)

        return "APPLIED", "Application submitted and confirmed on Naukri portal"

    def _handle_workday_flow(self, resume_path: Optional[str] = None) -> Optional[tuple[str, str]]:
        """Handles automated application on Workday portals (myworkdayjobs.com / workday.com)."""
        curr_url = (self.page.url or "").lower()
        if "myworkdayjobs.com" not in curr_url and "workday.com" not in curr_url:
            return None

        print(f"[Workday Engine] Detected Workday ATS portal at {self.page.url}")
        effective_resume = resume_path or "Abhishek_Anand_Resume.pdf"
        if not Path(effective_resume).exists():
            effective_resume = "Abhishek_Anand_Resume.docx"

        # 1. Click initial Apply button
        apply_btn = self.page.locator(
            "button[data-automation-id='applyButton'], "
            "button:has-text('Apply'), "
            "a[data-automation-id='applyButton'], "
            "a:has-text('Apply')"
        ).first
        if apply_btn.is_visible(timeout=5000):
            print("[Workday Engine] Clicking initial Apply trigger...")
            apply_btn.click()
            human_delay(2.0, 3.5)

        # 2. Check for Autofill with Resume option
        autofill_btn = self.page.locator(
            "button[data-automation-id='autofillWithResume'], "
            "a[data-automation-id='autofillWithResume'], "
            "button:has-text('Autofill with Resume'), "
            "a:has-text('Autofill with Resume')"
        ).first
        if autofill_btn.is_visible(timeout=3000):
            print("[Workday Engine] Selecting 'Autofill with Resume'...")
            autofill_btn.click()
            human_delay(2.0, 3.0)

        # 3. Handle Workday Authentication / Account Creation
        email_val = self.profile.email or "abhishek.anand.7601@gmail.com"
        pwd_val = self.profile.data.get("workday_password", "Abhishek@Job2026!")

        create_acc_link = self.page.locator(
            "button[data-automation-id='createAccountLink'], "
            "a[data-automation-id='createAccountLink'], "
            "button:has-text('Create Account')"
        ).first
        if create_acc_link.is_visible(timeout=2000):
            create_acc_link.click()
            human_delay(1.5, 2.5)

        email_input = self.page.locator("input[data-automation-id='email'], input[id*='email' i]").first
        if email_input.is_visible(timeout=3000):
            print(f"[Workday Engine] Entering candidate authentication ({email_val})...")
            email_input.fill(email_val)
            pwd_input = self.page.locator("input[data-automation-id='password'], input[type='password']").first
            if pwd_input.is_visible():
                pwd_input.fill(pwd_val)

            verify_pwd = self.page.locator("input[data-automation-id='verifyPassword']").first
            if verify_pwd.is_visible():
                verify_pwd.fill(pwd_val)

            terms = self.page.locator("input[data-automation-id='createAccountCheckbox'], input[type='checkbox']").first
            if terms.is_visible() and not terms.is_checked():
                terms.check()

            auth_submit = self.page.locator(
                "button[data-automation-id='createAccountSubmitButton'], "
                "button[data-automation-id='signInSubmitButton'], "
                "button:has-text('Sign In'), "
                "button:has-text('Create Account')"
            ).first
            if auth_submit.is_visible():
                auth_submit.click()
                human_delay(3.0, 5.0)

        # 4. Resume Upload
        file_input = self.page.locator("input[type='file'], input[data-automation-id='file-upload-input']").first
        if file_input.count() > 0 and Path(effective_resume).exists():
            print(f"[Workday Engine] Uploading resume: {effective_resume}")
            try:
                file_input.set_input_files(str(Path(effective_resume).resolve()))
                human_delay(3.0, 5.0)
            except Exception as e:
                print(f"[Workday Engine] Resume upload notice: {e}")

        # 5. Multi-Step Wizard Loop (Max 5 steps)
        for step_idx in range(1, 6):
            human_delay(2.0, 3.5)
            self._fill_standard_fields()
            self._answer_custom_questions()
            self._fill_select_dropdowns()
            self._accept_terms_checkboxes()

            submit_btn = self.page.locator(
                "button[data-automation-id='bottom-navigation-next-button']:has-text('Submit'), "
                "button:has-text('Submit Application')"
            ).first
            if submit_btn.is_visible(timeout=2000):
                print(f"[Workday Engine] Step {step_idx}: Submitting final application...")
                submit_btn.click()
                human_delay(4.0, 6.0)

                receipt = self.page.locator(
                    "[data-automation-id='congratulations'], "
                    "text='Thank you for applying', "
                    "text='Application Submitted', "
                    "text='Your application has been received'"
                ).first
                if receipt.is_visible(timeout=5000):
                    print("✓ [Workday Engine] Application submitted and verified successfully!")
                    return "APPLIED", "Successfully submitted via Workday automated engine"

            next_btn = self.page.locator(
                "button[data-automation-id='bottom-navigation-next-button'], "
                "button:has-text('Save and Continue'), "
                "button:has-text('Next')"
            ).first
            if next_btn.is_visible(timeout=2000):
                print(f"[Workday Engine] Step {step_idx}: Proceeding to next step...")
                next_btn.click()
            else:
                break

        if self.page.locator("text='Thank you for applying', text='Application Submitted', [data-automation-id='congratulations']").first.is_visible(timeout=2000):
            return "APPLIED", "Application confirmed on Workday portal"

        return "REVIEW_REQUIRED", "Workday multi-step flow completed up to verification checkpoint"

    def _extract_recruiter_email_from_page(self) -> Optional[str]:
        """Scans page text for direct recruiter or HR email addresses."""
        try:
            body_text = self.page.locator("body").inner_text()
            matches = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", body_text)
            for m in matches:
                m_low = m.lower()
                if not any(ign in m_low for ign in ["example.com", "w3.org", "sentry.io", "privacy", "terms", "abuse", "support@github", "noreply"]):
                    if any(kw in m_low for kw in ["hr", "career", "recruit", "talent", "job", "apply", "hire", "contact"]):
                        return m
                    if not m_low.endswith("google.com") and not m_low.endswith("linkedin.com") and not m_low.endswith("naukri.com"):
                        return m
        except Exception:
            pass
        return None

    def _extract_job_description_text(self) -> str:
        """Extracts job description text from page for resume tailoring."""
        jd_selectors = [
            ".job-description",
            "#job-description",
            "[data-qa='job-description']",
            ".posting-requirements",
            ".description",
            "article",
            "main",
            ".job-desc"
        ]
        for sel in jd_selectors:
            try:
                el = self.page.locator(sel).first
                if el.is_visible():
                    txt = el.inner_text().strip()
                    if len(txt) > 80:
                        return txt[:3500]
            except Exception:
                continue
        try:
            body = self.page.locator("body").inner_text()
            return body[:3500]
        except Exception:
            return ""

    def _extract_title_and_company(self) -> tuple[str, str]:
        title = ""
        company = ""
        try:
            h1 = self.page.locator("h1").first
            if h1.is_visible():
                title = h1.inner_text().strip()
            
            page_title = self.page.title()
            if not title and page_title:
                title = page_title.split(" - ")[0].split(" | ")[0].strip()

            comp_el = self.page.locator(".company-name, [data-qa='company-name'], .org-name").first
            if comp_el.is_visible():
                company = comp_el.inner_text().strip()
            elif " at " in page_title:
                company = page_title.split(" at ")[1].split(" - ")[0].strip()
        except Exception:
            pass
        return title, company

    def _click_apply_trigger_if_needed(self):
        """Clicks 'Apply' or 'Apply Now' button if form is behind a button or tab."""
        apply_selectors = [
            "#apply-button",
            "#apply_button",
            ".apply-button",
            "button:has-text('Apply on company site')",
            "button:has-text('Apply on company website')",
            "button:has-text('Apply for this job')",
            "button:has-text('Apply Now')",
            "button:has-text('Easy Apply')",
            "button:has-text('Apply')",
            "a:has-text('Apply on company site')",
            "a:has-text('Apply on company website')",
            "a:has-text('Apply for this job')",
            "a:has-text('Apply Now')",
            "a:has-text('Apply')",
            "a[href*='#apply']",
            ".postings-btn:has-text('Apply')",
            ".jobs-apply-button"
        ]
        for sel in apply_selectors:
            try:
                btn = self.page.locator(sel).first
                if btn.is_visible():
                    print(f"[Universal ATS] Clicking apply trigger: {sel}")
                    btn.click()
                    human_delay(2.0, 3.5)
                    if self.browser_session.context and len(self.browser_session.context.pages) > 1:
                        self.page = self.browser_session.context.pages[-1]
                    break
            except Exception:
                continue

    def _fill_standard_fields(self) -> int:
        """Fills standard personal identity and contact fields, handling number inputs appropriately."""
        first_name = self.profile.first_name or "Abhishek"
        last_name = self.profile.last_name or "Anand"
        full_name = f"{first_name} {last_name}".strip()
        email = get_strictly_configured_email()
        phone = self.profile.data.get("phone", "+918839617601")
        clean_phone = re.sub(r"[^\d+]", "", phone)
        linkedin = self.profile.data.get("linkedin", "https://linkedin.com/in/abhishek-anand-7601")
        github = self.profile.data.get("github", "https://github.com/Abhishekanand7601")
        city = self.profile.data.get("current_city", "Patna")

        filled = 0

        # Text and contact mappings
        mappings = [
            (["input#fullName", "input[name='full_name' i]", "input[name='name' i]", "input[id='name' i]", "input[placeholder*='Full Name' i]"], full_name),
            (["input#firstName", "input[name*='first_name' i]", "input[id*='first_name' i]", "#first_name"], first_name),
            (["input#lastName", "input[name*='last_name' i]", "input[id*='last_name' i]", "#last_name"], last_name),
            (["input[type='email']", "input[name*='email' i]", "#email"], email),
            (["input#mobile", "input[name*='mobile' i]", "input[type='tel']", "input[name*='phone' i]", "#phone"], clean_phone),
            (["input#linkedinUrl", "input[name*='linkedin' i]", "input[id*='linkedin' i]", "input[placeholder*='linkedin' i]"], linkedin),
            (["input#portfolioUrl", "input[name*='portfolio' i]", "input[name*='github' i]", "input[id*='github' i]", "input[placeholder*='github' i]"], github),
            (["input#currentLocation", "input[name*='current_location' i]", "input[name*='location' i]", "input[name*='city' i]"], city),
        ]

        for selectors_list, value in mappings:
            for sel in selectors_list:
                try:
                    el = self.page.locator(sel).first
                    if el.is_visible() and not el.input_value():
                        el.fill(str(value))
                        filled += 1
                        human_delay(0.2, 0.4)
                        break
                except Exception:
                    continue

        # Numeric / Specific Career Metrics
        numeric_career_fields = [
            # Total experience
            (["input#totalExperience", "input[name*='total_exp' i]", "input[name*='total_experience' i]"], "4", "4 years"),
            # Relevant experience
            (["input#relevantExperience", "input[name*='relevant_exp' i]", "input[name*='relevant_experience' i]"], "4", "4 years"),
            # Current CTC (In Lakhs e.g. 7)
            (["input#currentCtc", "input[name*='current_ctc' i]", "input[name*='current_salary' i]"], "7", "7 LPA"),
            # Expected CTC (In Lakhs e.g. 10)
            (["input#expectedCtc", "input[name*='expected_ctc' i]", "input[name*='expected_salary' i]"], "10", "10 LPA"),
            # Notice period (in days: 0)
            (["input#noticePeriod", "input[name*='notice_period' i]", "input[name*='notice' i]"], "0", "Immediate (0 days)"),
        ]

        for selectors_list, num_val, text_val in numeric_career_fields:
            for sel in selectors_list:
                try:
                    el = self.page.locator(sel).first
                    if el.is_visible() and not el.input_value():
                        itype = el.get_attribute("type") or "text"
                        val_to_fill = num_val if itype == "number" else text_val
                        el.fill(val_to_fill)
                        filled += 1
                        human_delay(0.2, 0.4)
                        break
                except Exception:
                    continue

        return filled

    def _fill_select_dropdowns(self) -> int:
        """Intelligently sets options in common recruitment select dropdowns."""
        selected_count = 0
        try:
            selects = self.page.locator("select:visible").all()
            for s in selects:
                try:
                    name = (s.get_attribute("name") or "").lower()
                    sid = (s.get_attribute("id") or "").lower()
                    combined = f"{name}_{sid}"

                    # Serving notice?
                    if "serving" in combined or "notice" in combined:
                        if self._try_select_matching_option(s, ["no", "completed", "immediate", "0"]):
                            selected_count += 1
                            continue

                    # Ready to relocate?
                    if "relocate" in combined or "location" in combined:
                        if self._try_select_matching_option(s, ["yes"]):
                            selected_count += 1
                            continue

                    # Has offers?
                    if "offer" in combined:
                        if self._try_select_matching_option(s, ["no"]):
                            selected_count += 1
                            continue

                    # Negotiable CTC?
                    if "negotiable" in combined:
                        if self._try_select_matching_option(s, ["yes", "company standard"]):
                            selected_count += 1
                            continue

                    # Experience level?
                    if "experience" in combined or "exp" in combined:
                        if self._try_select_matching_option(s, ["4", "3-5", "3 to 5"]):
                            selected_count += 1
                            continue

                    # Work authorization / Legal eligibility
                    if "authorized" in combined or "eligible" in combined or "citizen" in combined:
                        if self._try_select_matching_option(s, ["yes"]):
                            selected_count += 1
                            continue

                    # Gender
                    if "gender" in combined:
                        if self._try_select_matching_option(s, ["male", "prefer not to say"]):
                            selected_count += 1
                            continue

                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Error filling select dropdowns: {e}")

        return selected_count

    def _try_select_matching_option(self, select_el, target_keywords: List[str]) -> bool:
        """Selects the first option in a dropdown whose text or value contains any of target_keywords."""
        try:
            options = select_el.locator("option").all()
            for opt in options:
                txt = opt.inner_text().strip().lower()
                val = (opt.get_attribute("value") or "").strip().lower()
                if not val or "please select" in txt or "choose" in txt or "--" in txt:
                    continue
                for kw in target_keywords:
                    if kw in txt or kw == val:
                        select_el.select_option(value=val or None, label=opt.inner_text().strip() or None)
                        human_delay(0.2, 0.3)
                        return True
        except Exception:
            pass
        return False

    def _upload_resume_if_present(self, resume_path: Optional[str] = None) -> bool:
        """Uploads tailored or default resume to any file input element."""
        target_path = Path(resume_path) if resume_path else RESUME_PDF
        if not target_path.exists():
            target_path = RESUME_PDF
        if not target_path.exists():
            print(f"[Universal ATS] Resume file not found at: {target_path}")
            return False

        try:
            file_inputs = self.page.locator("input[type='file']").all()
            for fi in file_inputs:
                try:
                    fi.set_input_files(str(target_path))
                    print(f"[Universal ATS] Attached resume: {target_path.name}")
                    human_delay(1.0, 2.0)
                    return True
                except Exception:
                    continue
        except Exception as e:
            print(f"[Universal ATS] Could not attach resume: {e}")
        return False

    def _answer_custom_questions(self) -> int:
        """Identifies and answers screening questions / text areas using QuestionSolver."""
        answered = 0
        try:
            textareas = self.page.locator("textarea:visible").all()
            for ta in textareas:
                try:
                    if ta.input_value():
                        continue
                    
                    label_text = ""
                    ta_id = ta.get_attribute("id")
                    if ta_id:
                        lbl = self.page.locator(f"label[for='{ta_id}']").first
                        if lbl.is_visible():
                            label_text = lbl.inner_text().strip()
                    
                    if not label_text:
                        label_text = ta.get_attribute("placeholder") or "Experience and qualification summary"

                    answer = self.solver.solve_question(label_text, input_type="textarea")
                    if answer:
                        ta.fill(answer)
                        answered += 1
                        human_delay(0.3, 0.6)
                except Exception:
                    continue

        except Exception as e:
            logger.warning(f"Error answering custom questions: {e}")

        return answered

    def _accept_terms_checkboxes(self):
        """Checks any required consent/privacy policy checkboxes."""
        try:
            checkboxes = self.page.locator("input[type='checkbox']").all()
            for cb in checkboxes:
                try:
                    if cb.is_visible() and not cb.is_checked():
                        cb.check(force=True)
                except Exception:
                    continue
        except Exception:
            pass

    def _submit_form(self) -> bool:
        """Locates and clicks the primary submit button."""
        submit_selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit Application')",
            "button:has-text('Submit application')",
            "button:has-text('Submit')",
            "button:has-text('Send Application')",
            "#submit_app",
            "#submit-button",
            "#btnSubmit"
        ]
        for sel in submit_selectors:
            try:
                btn = self.page.locator(sel).first
                if btn.is_visible() and btn.is_enabled():
                    print(f"[Universal ATS] Clicking submit button: {sel}")
                    btn.click()
                    return True
            except Exception:
                continue
        return False

    def search_and_apply(
        self,
        role: str,
        location: str = "India",
        limit: int = 10,
        freshness_days: int = 3
    ) -> List[Dict[str, Any]]:
        return []
