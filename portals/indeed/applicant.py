"""
Indeed Job Portal Applicant
Automates job discovery, suitability analysis, and 1-click tailored application on Indeed.com / in.indeed.com,
supporting both native 'Easily Apply' flows and external ATS redirections.
"""
import re
import time
import urllib.parse
from typing import Optional, Dict, Any, List
from playwright.sync_api import TimeoutError as PWTimeout

from core.base_portal import BaseJobPortal
from core.tracker import ApplicationTracker
from core.browser_factory import human_delay, safe_evaluate
from common.profile import Profile
from portals.indeed import selectors


class IndeedApplicant(BaseJobPortal):
    def __init__(
        self,
        profile: Profile,
        tracker: Optional[ApplicationTracker] = None,
        headless: bool = False,
        session_file: str = "session_indeed.json",
        user_data_dir: Optional[str] = None
    ):
        from pathlib import Path
        default_dir = str((Path(__file__).resolve().parent.parent.parent / "chrome_profile_indeed").resolve())
        super().__init__(
            profile=profile,
            tracker=tracker,
            headless=headless,
            session_file=session_file,
            user_data_dir=user_data_dir
        )

    @property
    def portal_name(self) -> str:
        return "indeed"

    def is_logged_in(self) -> bool:
        """Verifies if candidate is genuinely authenticated on Indeed."""
        if not self.page:
            self.start_session()
        try:
            self.page.goto(selectors.BASE_URL, timeout=30000, wait_until="domcontentloaded")
            human_delay(2.0, 3.0)

            curr_url = self.page.url.lower()
            if "auth" in curr_url or "login" in curr_url or "__cf_chl" in curr_url:
                return False

            # If Sign in link is clearly visible, candidate is unauthenticated
            signin_btn = self.page.locator("a[href*='account/login'], a:has-text('Sign in')").first
            if signin_btn.count() > 0 and signin_btn.is_visible():
                return False

            badge = self.page.locator(selectors.PROFILE_BADGE).first
            if badge.count() > 0 and badge.is_visible():
                return True

            # Check for logged-in profile URLs or navigation icons
            acc = self.page.locator("[aria-label*='Account'], [aria-label*='Profile'], #gnav-account-filter, .gnav-AccountMenu, a[href*='/myprofile']").first
            return acc.count() > 0 and acc.is_visible()
        except Exception:
            return False

    def extract_job_id(self, url: str) -> str:
        """Extracts job identifier ('jk' or slug) from Indeed URL."""
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        if "jk" in params:
            return params["jk"][0]
        match = re.search(r"jk=([a-zA-Z0-9]+)", url)
        if match:
            return match.group(1)
        match = re.search(r"/viewjob/([a-zA-Z0-9]+)", url)
        if match:
            return match.group(1)
        return url.rstrip("/").split("/")[-1]

    def parse_job_details(self, job_url: str) -> Dict[str, Any]:
        """Loads the Indeed job page and parses title, company, location, and full description."""
        if not self.page:
            self.start_session()

        self.page.goto(job_url, timeout=40000, wait_until="domcontentloaded")
        human_delay(2.0, 3.0)

        # Wait for any Cloudflare challenge to clear
        start_wait = time.time()
        while time.time() - start_wait < 25:
            curr_title = self.page.title()
            if any(term in curr_title for term in ["Additional Verification", "Security Check", "Just a moment"]):
                print(f"  [Waiting for Cloudflare] Current title: {curr_title}")
                # Auto-click Turnstile checkbox if available inside frame
                for f in self.page.frames:
                    if "challenges.cloudflare" in f.url:
                        try:
                            box = f.locator("input[type='checkbox'], #challenge-stage, .ctp-checkbox-label").first
                            if box.count() > 0:
                                box.click()
                        except Exception:
                            pass
                time.sleep(2.5)
            else:
                break

        title = ""
        company = ""
        location = ""
        jd = ""
        is_easily_apply = False
        is_external = False
        already_applied = False

        try:
            t_loc = self.page.locator(selectors.JOB_TITLE).first
            if t_loc.count() > 0:
                title = t_loc.inner_text().strip()
        except Exception:
            pass

        try:
            c_loc = self.page.locator(selectors.COMPANY_NAME).first
            if c_loc.count() > 0:
                company = c_loc.inner_text().strip()
        except Exception:
            pass

        try:
            l_loc = self.page.locator(selectors.COMPANY_LOCATION).first
            if l_loc.count() > 0:
                location = l_loc.inner_text().strip()
        except Exception:
            pass

        try:
            jd_loc = self.page.locator(selectors.JOB_DESCRIPTION).first
            if jd_loc.count() > 0:
                jd = jd_loc.inner_text().strip()
        except Exception:
            pass

        already_applied = self.page.locator(selectors.ALREADY_APPLIED_INDICATOR).first.count() > 0
        is_easily_apply = self.page.locator(selectors.EASILY_APPLY_BTN).first.count() > 0
        is_external = self.page.locator(selectors.EXTERNAL_APPLY_BTN).first.count() > 0

        return {
            "title": title or "Frontend Developer",
            "company": company or "Indeed Hiring Company",
            "location": location or "Bengaluru / Remote",
            "description": jd,
            "is_easily_apply": is_easily_apply,
            "is_external": is_external,
            "already_applied": already_applied,
            "url": job_url
        }

    def evaluate_job_suitability(self, job_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates whether candidate profile matches the job requirements.
        Returns match percentage, recommendation, and pros/cons.
        """
        title = job_details.get("title", "").lower()
        jd = job_details.get("description", "").lower()
        text = f"{title} {jd}"

        # Disqualifiers
        disqualifiers = []
        if any(term in text for term in ["8+ years", "10+ years", "12+ years", "principal architect", "staff engineer"]):
            disqualifiers.append("Requires senior/staff seniority beyond 3.5+ years experience")
        if "angular only" in text or ("angular" in text and "react" not in text):
            disqualifiers.append("Pure Angular position without React / Next.js")
        if "c++" in text or "embedded" in text or "firmware" in text:
            disqualifiers.append("Hardware / Systems engineering role")

        # Positive Keyword Match
        core_keywords = [
            "react", "react.js", "next.js", "nextjs", "typescript", "javascript",
            "frontend", "front-end", "redux", "tailwind", "ui developer",
            "web developer", "html5", "css3", "rest api", "graphql", "jest"
        ]
        matched_keywords = [kw for kw in core_keywords if kw in text]

        score = min(100, int((len(matched_keywords) / 6.0) * 85))
        if any(term in title for term in ["react", "frontend", "front end", "ui developer", "next"]):
            score = max(score, 75)

        if disqualifiers:
            recommendation = "SKIP"
            score = min(score, 45)
        elif score >= 70:
            recommendation = "APPLY"
        elif score >= 50:
            recommendation = "REVIEW"
        else:
            recommendation = "SKIP"

        return {
            "score": score,
            "recommendation": recommendation,
            "matched_keywords": matched_keywords,
            "disqualifiers": disqualifiers,
            "role_title": job_details.get("title"),
            "company": job_details.get("company"),
            "location": job_details.get("location")
        }

    def apply_by_url(self, job_url: str, force_apply: bool = False) -> Dict[str, Any]:
        """Navigates to an Indeed job URL and executes the application."""
        if not self.page:
            self.start_session()

        job_id = self.extract_job_id(job_url)
        details = self.parse_job_details(job_url)

        if details["already_applied"] or self.tracker.is_applied(self.portal_name, job_id):
            return {
                "status": "ALREADY_APPLIED",
                "job_id": job_id,
                "title": details["title"],
                "company": details["company"],
                "url": job_url,
                "reason": "Application already submitted previously."
            }

        # Check suitability
        suitability = self.evaluate_job_suitability(details)
        if not force_apply and suitability["recommendation"] == "SKIP":
            return {
                "status": "SKIPPED",
                "job_id": job_id,
                "title": details["title"],
                "company": details["company"],
                "url": job_url,
                "reason": f"Low match score ({suitability['score']}%) / Disqualifier: {'; '.join(suitability['disqualifiers']) or 'Keywords mismatch'}",
                "suitability": suitability
            }

        # Check for External Apply
        if details["is_external"] and not details["is_easily_apply"]:
            ext_btn = self.page.locator(selectors.EXTERNAL_APPLY_BTN).first
            target_url = job_url
            if ext_btn.count() > 0:
                try:
                    with self.page.context.expect_page(timeout=10000) as new_page_info:
                        ext_btn.click()
                    new_page = new_page_info.value
                    new_page.wait_for_load_state("domcontentloaded")
                    target_url = new_page.url
                    new_page.close()
                except Exception:
                    pass

            return {
                "status": "EXTERNAL",
                "job_id": job_id,
                "title": details["title"],
                "company": details["company"],
                "url": target_url,
                "reason": f"External application link dispatched to Universal ATS Engine: {target_url}",
                "suitability": suitability
            }

        # Execute Indeed Easily Apply flow
        apply_btn = self.page.locator(selectors.EASILY_APPLY_BTN).first
        if apply_btn.count() == 0:
            return {
                "status": "ERROR",
                "job_id": job_id,
                "title": details["title"],
                "company": details["company"],
                "url": job_url,
                "reason": "Apply button could not be located on the page."
            }

        try:
            apply_btn.click()
            human_delay(2.0, 3.5)

            # Handle multi-step modal flow (up to 7 steps)
            max_steps = 7
            step = 0
            submitted = False

            while step < max_steps:
                step += 1
                human_delay(1.5, 2.5)

                # 1. Check if success header is visible
                success = self.page.locator(selectors.SUCCESS_HEADER).first
                if success.count() > 0 and success.is_visible():
                    submitted = True
                    break

                # 2. Check for Submit button
                submit_btn = self.page.locator(selectors.SUBMIT_BTN).first
                if submit_btn.count() > 0 and submit_btn.is_visible():
                    submit_btn.click()
                    human_delay(3.0, 4.0)
                    submitted = True
                    break

                # 3. Check for Review button
                review_btn = self.page.locator(selectors.REVIEW_BTN).first
                if review_btn.count() > 0 and review_btn.is_visible():
                    review_btn.click()
                    human_delay(1.5, 2.5)
                    continue

                # 4. Handle Screener Questions on current step
                self._handle_screener_questions()

                # 5. Click Continue / Next
                continue_btn = self.page.locator(selectors.CONTINUE_BTN).first
                if continue_btn.count() > 0 and continue_btn.is_visible():
                    continue_btn.click()
                else:
                    # Break if no forward button found
                    break

            if submitted:
                self.tracker.record_application(
                    portal=self.portal_name,
                    job_id=job_id,
                    title=details["title"],
                    company=details["company"],
                    url=job_url,
                    status="APPLIED",
                    metadata={"match_score": suitability["score"]}
                )
                return {
                    "status": "APPLIED",
                    "job_id": job_id,
                    "title": details["title"],
                    "company": details["company"],
                    "url": job_url,
                    "reason": f"Application submitted successfully via Indeed Easily Apply ({suitability['score']}% match)."
                }
            else:
                return {
                    "status": "REVIEW_REQUIRED",
                    "job_id": job_id,
                    "title": details["title"],
                    "company": details["company"],
                    "url": job_url,
                    "reason": "Application requires manual questionnaire input or document verification."
                }

        except Exception as e:
            return {
                "status": "ERROR",
                "job_id": job_id,
                "title": details["title"],
                "company": details["company"],
                "url": job_url,
                "reason": f"Error during application steps: {str(e)}"
            }

    def _handle_screener_questions(self):
        """Answers standard Indeed screener questions (numerical years, notice period, yes/no)."""
        try:
            # Experience inputs (numbers)
            num_inputs = self.page.locator("input[type='number'], input[id*='experience'], input[id*='years']")
            for idx in range(num_inputs.count()):
                inp = num_inputs.nth(idx)
                if inp.is_visible() and not inp.input_value():
                    inp.fill("3")

            # Notice period inputs
            notice_inputs = self.page.locator("input[id*='notice'], input[name*='notice']")
            for idx in range(notice_inputs.count()):
                inp = notice_inputs.nth(idx)
                if inp.is_visible() and not inp.input_value():
                    inp.fill("0")

            # Radio buttons: default to 'Yes' for authorization / relocation / Bengaluru
            yes_radios = self.page.locator("input[type='radio'][value='yes'], input[type='radio'][value='true'], input[type='radio'][value='1']")
            for idx in range(yes_radios.count()):
                r = yes_radios.nth(idx)
                if r.is_visible() and not r.is_checked():
                    try:
                        r.check(force=True)
                    except Exception:
                        pass
        except Exception:
            pass

    def search_and_apply(
        self,
        role: str = "React Developer",
        location: str = "Bengaluru",
        limit: int = 10,
        freshness_days: int = 3
    ) -> List[Dict[str, Any]]:
        """Searches jobs on Indeed India and applies to matching listings."""
        if not self.page:
            self.start_session()

        query = urllib.parse.quote_plus(role)
        loc = urllib.parse.quote_plus(location)
        search_url = f"{selectors.SEARCH_URL}?q={query}&l={loc}&fromage={freshness_days}"

        self.page.goto(search_url, timeout=40000, wait_until="domcontentloaded")
        human_delay(2.5, 4.0)

        results = []
        links = self.page.locator("a[id*='job_'], a[data-jk]").all()
        urls = []
        for l in links[:limit * 2]:
            href = l.get_attribute("href")
            if href:
                full_url = urllib.parse.urljoin(selectors.BASE_URL, href)
                if "jk=" in full_url or "/viewjob" in full_url:
                    urls.append(full_url)

        urls = list(dict.fromkeys(urls))[:limit]
        for url in urls:
            res = self.apply_by_url(url)
            results.append(res)
            human_delay(3.0, 5.0)

        return results
