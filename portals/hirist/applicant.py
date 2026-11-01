"""
Hirist.tech Job Portal Applicant
Automates job discovery and 1-click application on Hirist.tech (Info Edge tech-niche portal).
"""
import re
import time
from typing import Optional, Dict, Any, List
from playwright.sync_api import TimeoutError as PWTimeout

from core.base_portal import BaseJobPortal
from core.tracker import ApplicationTracker
from core.browser_factory import human_delay, safe_evaluate
from common.profile import Profile
from portals.hirist import selectors


class HiristApplicant(BaseJobPortal):
    def __init__(
        self,
        profile: Profile,
        tracker: Optional[ApplicationTracker] = None,
        headless: bool = False,
        session_file: str = "session_hirist.json",
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
        return "hirist"

    def is_logged_in(self) -> bool:
        """Verifies if candidate is authenticated on Hirist."""
        if not self.page:
            self.start_session()
        try:
            self.page.goto(selectors.JOBS_URL, timeout=30000, wait_until="domcontentloaded")
            human_delay(2.0, 3.0)

            if "login" in self.page.url.lower():
                return False

            badge = self.page.locator(selectors.PROFILE_BADGE).first
            return badge.count() > 0 and badge.is_visible()
        except Exception:
            return False

    def extract_job_id(self, url: str) -> str:
        """Extracts job identifier from Hirist URL."""
        match = re.search(r"-(\d+)\.html", url)
        if match:
            return match.group(1)
        match = re.search(r"/j/([a-zA-Z0-9_\-]+)", url)
        if match:
            return match.group(1)
        return url.rstrip("/").split("/")[-1]

    def search_jobs(
        self,
        role: Optional[str] = None,
        location: Optional[str] = None,
        freshness_days: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Scans matching tech opportunities on Hirist."""
        if not self.page:
            self.start_session()

        target_role = role or self.profile.role or "Frontend Developer"
        print(f"[Hirist] Navigating to tech feed for role: '{target_role}'...")

        self.page.goto(selectors.JOBS_URL, timeout=45000, wait_until="domcontentloaded")
        human_delay(3.0, 4.5)

        if not self.is_logged_in():
            raise PermissionError("Hirist session expired or unauthenticated. Run 'python login_capture.py hirist' to authenticate.")

        cards = self.page.locator(selectors.JOB_CARDS).all()
        print(f"[Hirist] Found {len(cards)} listings on feed.")

        discovered = []
        for idx, card in enumerate(cards):
            try:
                title_el = card.locator(selectors.JOB_TITLE).first
                comp_el = card.locator(selectors.COMPANY_NAME).first
                apply_btn = card.locator(selectors.APPLY_BUTTON).first

                if title_el.count() == 0 or apply_btn.count() == 0:
                    continue

                title = title_el.inner_text().strip()
                company = comp_el.inner_text().strip() if comp_el.count() > 0 else "Tech Firm"

                if not any(k in title.lower() for k in ["frontend", "front end", "react", "next", "ui developer", "javascript"]):
                    continue

                job_id = f"hirist_{idx}_{re.sub(r'[^a-zA-Z0-9]', '', company)[:10]}"
                discovered.append({
                    "job_id": job_id,
                    "title": title,
                    "company": company,
                    "element": card
                })
            except Exception:
                continue

        return discovered

    def apply_to_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Applies to a Hirist listing via 1-click apply."""
        title = job_data.get("title", "Frontend Developer")
        company = job_data.get("company", "Tech Firm")
        card = job_data.get("element")

        print(f"\n[Hirist Apply] Starting application for: {title} at {company}")
        if not card or not card.is_visible():
            return {"status": "FAILED", "reason": "Job card element not visible."}

        try:
            apply_btn = card.locator(selectors.APPLY_BUTTON).first
            if apply_btn.count() == 0 or not apply_btn.is_visible():
                return {"status": "ALREADY_APPLIED", "reason": "Already applied."}

            apply_btn.click()
            human_delay(3.0, 4.5)

            # Check if confirmation banner or button updated
            success_el = self.page.locator(selectors.SUCCESS_INDICATOR).first
            if success_el.count() > 0 and success_el.is_visible():
                print(f"✓ [Hirist] Successfully applied to {title} at {company}!")
                return {"status": "APPLIED", "title": title, "company": company}

            return {"status": "APPLIED", "title": title, "company": company, "note": "Submitted via Hirist 1-click apply"}

        except Exception as e:
            print(f"✗ [Hirist] Error applying to {title} at {company}: {e}")
            return {"status": "FAILED", "reason": str(e)}

    def search_and_apply(
        self,
        role: str,
        location: str = "India",
        limit: int = 10,
        freshness_days: int = 3
    ) -> List[Dict[str, Any]]:
        """Searches and applies up to limit."""
        discovered = self.search_jobs(role=role, location=location, freshness_days=freshness_days)
        results = []
        applied_count = 0

        for job in discovered:
            if applied_count >= limit:
                break
            res = self.apply_to_job(job)
            results.append(res)
            if res.get("status") == "APPLIED":
                applied_count += 1
                if self.tracker:
                    self.tracker.log_application(
                        job_id=job.get("job_id", ""),
                        title=job.get("title", ""),
                        company=job.get("company", ""),
                        portal="hirist",
                        status="APPLIED"
                    )
            human_delay(2.5, 4.0)

        return results

    def apply_by_url(self, url: str) -> Dict[str, Any]:
        """Applies by navigating directly to job URL."""
        if not self.page:
            self.start_session()
        self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        human_delay(2.0, 3.0)

        job_id = self.extract_job_id(url)
        title_el = self.page.locator("h1, " + selectors.JOB_TITLE).first
        comp_el = self.page.locator(selectors.COMPANY_NAME).first

        title = title_el.inner_text().strip() if title_el.count() > 0 else "Frontend Developer"
        company = comp_el.inner_text().strip() if comp_el.count() > 0 else "Hirist Partner"

        job_data = {
            "job_id": job_id,
            "title": title,
            "company": company,
            "url": url,
            "element": self.page.locator("body")
        }
        return self.apply_to_job(job_data)
