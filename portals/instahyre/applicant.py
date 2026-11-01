"""
Instahyre Job Portal Applicant
Automates job discovery and 1-click application on Instahyre (opportunities feed and direct URLs),
incorporating Sachin Shukla's (imsks) proven modal and bulk apply logic with smart role filtering.
"""
import re
import time
from typing import Optional, Dict, Any, List
from playwright.sync_api import TimeoutError as PWTimeout

from core.base_portal import BaseJobPortal
from core.tracker import ApplicationTracker
from core.browser_factory import human_delay, safe_evaluate
from common.profile import Profile
from portals.instahyre import selectors


class InstahyreApplicant(BaseJobPortal):
    def __init__(
        self,
        profile: Profile,
        tracker: Optional[ApplicationTracker] = None,
        headless: bool = False,
        session_file: str = "session_instahyre.json",
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
        return "instahyre"

    def is_logged_in(self) -> bool:
        """Verifies if user is logged in to Instahyre."""
        if not self.page:
            self.start_session()
        try:
            self.page.goto(selectors.OPPORTUNITIES_URL, timeout=30000, wait_until="domcontentloaded")
            human_delay(1.5, 2.5)

            if "login" in self.page.url:
                return False

            profile_badge = self.page.locator(".candidate-navbar, a[href*='profile'], #profile-dropdown").first
            return profile_badge.is_visible()
        except Exception:
            return False

    def extract_job_id(self, url: str) -> str:
        """Extracts job identifier from Instahyre URL."""
        match = re.search(r"job-([a-zA-Z0-9]+)", url)
        if match:
            return match.group(1)
        match = re.search(r"/job/([a-zA-Z0-9]+)", url)
        if match:
            return match.group(1)
        return ""

    def apply_by_url(self, job_url: str) -> Dict[str, Any]:
        """Applies to a specific Instahyre job listing URL."""
        self.start_session()
        print(f"\n[Instahyre] Navigating to: {job_url}")

        job_id = self.extract_job_id(job_url)
        if job_id and self.tracker.is_already_processed(job_id):
            print(f"[Instahyre] Job ID {job_id} was already processed previously. Skipping.")
            return {
                "status": "ALREADY_PROCESSED",
                "job_id": job_id,
                "title": "",
                "company": "",
                "url": job_url,
                "reason": "Already processed in tracker"
            }

        try:
            self.page.goto(job_url, timeout=30000, wait_until="domcontentloaded")
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

        # Check if redirected to login
        if "login" in self.page.url:
            print("[Instahyre] Session expired or not logged in. Run: python login_capture.py instahyre")
            return {
                "status": "AUTH_REQUIRED",
                "job_id": job_id,
                "title": "",
                "company": "",
                "url": job_url,
                "reason": "Active session required. Run: python login_capture.py instahyre"
            }

        # Extract Job Details
        title = ""
        company = ""

        try:
            title_el = self.page.locator(selectors.JOB_TITLE).first
            if title_el.is_visible():
                title = title_el.inner_text().strip()
        except Exception:
            pass

        try:
            comp_el = self.page.locator(selectors.COMPANY_NAME).first
            if comp_el.is_visible():
                company = comp_el.inner_text().strip()
        except Exception:
            pass

        if not title:
            title = self.page.title().split("-")[0].strip()

        print(f"[Instahyre] Listing: {title} @ {company}")

        # Check for Apply button
        apply_btn = self.page.locator(selectors.NORMAL_APPLY_BUTTON).first
        if not apply_btn.is_visible():
            # Check if already applied
            if self.page.locator("button:has-text('Applied'), span:has-text('Applied')").first.is_visible():
                self.tracker.log_application("instahyre", job_id, title, company, "ALREADY_APPLIED", job_url)
                return {"status": "ALREADY_APPLIED", "job_id": job_id, "title": title, "company": company, "url": job_url}

            return {
                "status": "SKIPPED",
                "job_id": job_id,
                "title": title,
                "company": company,
                "url": job_url,
                "reason": "No apply button found"
            }

        # Click Apply
        try:
            apply_btn.click()
            human_delay(2.0, 3.0)
            print(f"[Instahyre] Successfully submitted application for: {title} @ {company}")
            self.tracker.log_application("instahyre", job_id, title, company, "APPLIED", job_url)
            return {
                "status": "APPLIED",
                "job_id": job_id,
                "title": title,
                "company": company,
                "url": job_url,
                "reason": "Applied successfully via Instahyre 1-click apply"
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "job_id": job_id,
                "title": title,
                "company": company,
                "url": job_url,
                "reason": f"Apply click failed: {e}"
            }

    def search_and_apply(
        self,
        role: str = "",
        location: str = "India",
        limit: int = 10,
        freshness_days: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Processes Instahyre opportunities feed using Sachin Shukla's modal & bulk apply automation.
        """
        self.start_session()
        applied_results = []
        applied_count = 0

        print(f"\n[Instahyre] Opening Opportunities Feed: {selectors.OPPORTUNITIES_URL}")
        try:
            self.page.goto(selectors.OPPORTUNITIES_URL, timeout=45000, wait_until="domcontentloaded")
            human_delay(2.5, 4.0)
        except Exception as e:
            print(f"[Instahyre] Failed to load opportunities: {e}")
            return applied_results

        if "login" in self.page.url:
            print("\n[Instahyre Error] You are not logged in! Redirected to login page.")
            print("Please run: python login_capture.py instahyre to save your authenticated login session first.\n")
            raise PermissionError("Instahyre session expired or unauthenticated. Please re-authenticate via: python login_capture.py instahyre")

        # Step 0: Dismiss announcement popup if present
        try:
            got_it = self.page.locator(selectors.ANNOUNCEMENT_MODAL).first
            if got_it.is_visible():
                print("[Instahyre] Dismissing UI announcement popup...")
                got_it.click()
                human_delay(0.5, 1.0)
        except Exception:
            pass

        # Step 1: Open initial modal by clicking "View job »" or "Interested"
        print("[Instahyre] Looking for opportunity cards on page...")
        cards = self.page.locator(selectors.EMPLOYER_ROW).all()
        if len(cards) == 0:
            search_keyword = role if role else "React"
            print(f"[Instahyre] Recommended feed has 0 jobs. Executing search for '{search_keyword}'...")
            try:
                search_inp = self.page.locator("#skills-drop-select-job-search-selectized, input[placeholder*='skills or title']").first
                if search_inp.is_visible():
                    search_inp.fill(search_keyword)
                    self.page.keyboard.press("Enter")
                    human_delay(0.5, 1.0)
                search_btn = self.page.locator("button:has-text('Search'), [ng-click*='searchCustomJobs']").first
                if search_btn.is_visible():
                    search_btn.click()
                    human_delay(3.0, 4.5)
                    try:
                        self.page.wait_for_selector(selectors.EMPLOYER_ROW, timeout=10000)
                    except Exception:
                        pass
                    cards = self.page.locator(selectors.EMPLOYER_ROW).all()
            except Exception as e:
                print(f"[Instahyre] Search fallback error: {e}")

        print(f"[Instahyre] Found {len(cards)} opportunity cards on page.")

        view_btn = self.page.locator(selectors.VIEW_JOB_BUTTON).first
        if not view_btn.is_visible() and cards:
            view_btn = cards[0].locator("button:has-text('View job')").first
        if view_btn.is_visible():
            try:
                view_btn.scroll_into_view_if_needed()
                human_delay(0.5, 1.0)
                try:
                    view_btn.click(timeout=4000)
                except Exception:
                    view_btn.click(force=True)
                print("[Instahyre] Clicked 'View job' to open application modal.")
                human_delay(2.0, 3.0)
            except Exception as e:
                print(f"[Instahyre] Could not click view job: {e}")
        else:
            print("[Instahyre] Checking if modal is already open...")

        # Step 2: Loop to handle Bulk Apply and Single Apply inside the modal
        print(f"[Instahyre] Starting application loop (target limit: {limit})...")
        consecutive_idle = 0
        max_loop = 30

        for iteration in range(1, max_loop + 1):
            if applied_count >= limit:
                print(f"[Instahyre] Target application limit of {limit} reached!")
                break

            human_delay(1.5, 2.5)

            # Check for Bulk Apply Modal button
            bulk_btn = self.page.locator(selectors.BULK_APPLY_BUTTON).first
            if bulk_btn.is_visible() and bulk_btn.is_enabled():
                try:
                    btn_text = bulk_btn.inner_text().strip()
                    try:
                        bulk_btn.click(timeout=4000)
                    except Exception:
                        bulk_btn.click(force=True)
                    applied_count += 1
                    print(f"[Instahyre] [Apply #{applied_count}] Bulk Apply clicked: '{btn_text}'")
                    self.tracker.log_application(
                        platform="instahyre",
                        job_id=f"bulk_{int(time.time())}",
                        title="Bulk Opportunities",
                        company="Instahyre Recommended",
                        status="APPLIED",
                        url=selectors.OPPORTUNITIES_URL,
                        reason=f"Clicked bulk apply: {btn_text}"
                    )
                    applied_results.append({"status": "APPLIED", "type": "bulk"})
                    consecutive_idle = 0
                    human_delay(3.0, 4.5)
                    continue
                except Exception as e:
                    print(f"  (Bulk apply click failed: {e})")

            # Check for Standard Normal Apply Button inside current job modal
            normal_btn = self.page.locator(selectors.NORMAL_APPLY_BUTTON).first
            if normal_btn.is_visible() and normal_btn.is_enabled():
                # Extract current modal job title and company
                current_title = ""
                current_company = ""
                try:
                    t_el = self.page.locator(selectors.JOB_TITLE).first
                    if t_el.is_visible():
                        current_title = t_el.inner_text().strip()
                except Exception:
                    pass

                try:
                    c_el = self.page.locator(selectors.COMPANY_NAME).first
                    if c_el.is_visible():
                        current_company = c_el.inner_text().strip()
                        if " - " in current_company:
                            current_company = current_company.split(" - ")[0].strip()
                except Exception:
                    pass

                # If modal heading is generic or empty, try getting from active card or dialog text
                if not current_title or len(current_title) < 2:
                    try:
                        modal_text = self.page.locator(".application-modal, .modal-dialog").first.inner_text()
                        for line in modal_text.splitlines():
                            line_s = line.strip()
                            if any(k in line_s.lower() for k in ["engineer", "developer", "architect", "lead"]):
                                current_title = line_s
                                break
                    except Exception:
                        pass

                if not current_title:
                    current_title = "Opportunity"

                # Check if role matches user criteria
                if role and current_title and not self._is_title_relevant(current_title, role):
                    print(f"  [Skip] Title mismatch: '{current_title}' does not fit '{role}'. Skipping to next...")
                    decline_btn = self.page.locator(selectors.DECLINE_BUTTON).first
                    if decline_btn.is_visible() and decline_btn.is_enabled():
                        try:
                            decline_btn.click(timeout=4000)
                        except Exception:
                            decline_btn.click(force=True)
                        human_delay(1.5, 2.5)
                        continue
                    next_btn = self.page.locator(selectors.NEXT_JOB_BUTTON).first
                    if next_btn.is_visible() and next_btn.is_enabled():
                        try:
                            next_btn.click(timeout=4000)
                        except Exception:
                            next_btn.click(force=True)
                        human_delay(1.5, 2.5)
                        continue

                # Click Normal Apply
                try:
                    try:
                        normal_btn.click(timeout=4000)
                    except Exception:
                        normal_btn.click(force=True)
                    applied_count += 1
                    print(f"[Instahyre] [Apply #{applied_count}] Applied to: {current_title} @ {current_company}")
                    self.tracker.log_application(
                        platform="instahyre",
                        job_id=f"instahyre_{int(time.time())}",
                        title=current_title,
                        company=current_company,
                        status="APPLIED",
                        url=self.page.url,
                        reason="Clicked 1-click apply"
                    )
                    applied_results.append({
                        "status": "APPLIED",
                        "title": current_title,
                        "company": current_company
                    })
                    consecutive_idle = 0
                    human_delay(2.5, 4.0)
                    continue
                except Exception as e:
                    print(f"  (Normal apply click failed: {e})")

            # Try Next Job or Decline button if available
            next_btn = self.page.locator(selectors.NEXT_JOB_BUTTON).first
            if next_btn.is_visible() and next_btn.is_enabled():
                try:
                    try:
                        next_btn.click(timeout=4000)
                    except Exception:
                        next_btn.click(force=True)
                    print("[Instahyre] Moving to next opportunity in modal...")
                    consecutive_idle = 0
                    human_delay(2.0, 3.0)
                    continue
                except Exception:
                    pass

            # Card-by-card fallback if modal is closed
            remaining_view_btns = self.page.locator(selectors.VIEW_JOB_BUTTON).all()
            if remaining_view_btns and applied_count < limit:
                for vb in remaining_view_btns:
                    if vb.is_visible():
                        try:
                            vb.scroll_into_view_if_needed()
                            human_delay(0.5, 1.0)
                            try:
                                vb.click(timeout=4000)
                            except Exception:
                                vb.click(force=True)
                            print("[Instahyre] Opened next job card modal.")
                            human_delay(2.0, 3.0)
                            consecutive_idle = 0
                            break
                        except Exception:
                            continue
                else:
                    consecutive_idle += 1
            else:
                consecutive_idle += 1

            if consecutive_idle >= 2:
                print("[Instahyre] No more active apply buttons or opportunities found in feed.")
                break

        print(f"\n[Instahyre Done] Run finished. Total applications submitted: {applied_count}")
        return applied_results

    def _is_title_relevant(self, title: str, searched_role: str) -> bool:
        t_low = title.lower()
        unrelated = [
            "php developer", "wordpress", "shopify", "salesforce", "android developer",
            "ios developer", "flutter developer", ".net developer", "dot net", "c# developer",
            "data scientist", "machine learning", "devops engineer", "qa engineer", "tester",
            "sdet", "qa automation", "manual tester"
        ]
        if any(un in t_low for un in unrelated):
            return False

        if searched_role:
            searched_tokens = [tok for tok in searched_role.lower().split() if tok not in ("developer", "engineer", "roles", "jobs")]
            if any(tok in t_low for tok in searched_tokens):
                return True

        frontend_keywords = [
            "react", "frontend", "front end", "front-end", "next.js", "nextjs",
            "software development engineer", "software engineer", "full stack", "fullstack",
            "web developer", "ui developer", "javascript", "typescript"
        ]
        return any(kw in t_low for kw in frontend_keywords)
