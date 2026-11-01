"""
Base Job Portal Interface
Defines the standard contract and lifecycle methods that every portal applicant
(Indeed, Instahyre, Wellfound, Naukri, etc.) must implement.
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from common.profile import Profile
from core.browser_factory import BrowserSession
from core.tracker import ApplicationTracker
from core.question_solver import QuestionSolver


class BaseJobPortal(ABC):
    def __init__(
        self,
        profile: Profile,
        tracker: Optional[ApplicationTracker] = None,
        headless: bool = False,
        session_file: Optional[str] = None,
        user_data_dir: Optional[str] = None
    ):
        self.profile = profile
        self.tracker = tracker or ApplicationTracker()
        self.headless = headless
        self.session_file = session_file
        self.user_data_dir = user_data_dir

        self.browser_session = BrowserSession(
            headless=self.headless,
            session_file=self.session_file,
            user_data_dir=self.user_data_dir
        )
        self.solver = QuestionSolver(self.profile)
        self.page = None

    @property
    @abstractmethod
    def portal_name(self) -> str:
        """Name of the portal (e.g. 'indeed', 'instahyre')."""
        pass

    def start_session(self):
        """Launches the stealth browser and prepares the session."""
        if not self.page:
            self.page = self.browser_session.start()
        return self.page

    def close_session(self):
        """Closes the browser session."""
        if self.browser_session:
            self.browser_session.close()
            self.page = None

    @abstractmethod
    def is_logged_in(self) -> bool:
        """Verifies if the current browser session has an active logged-in user."""
        pass

    @abstractmethod
    def apply_by_url(self, job_url: str) -> Dict[str, Any]:
        """
        Navigates to a specific job listing URL and attempts to apply.
        Returns a dictionary with at minimum:
        {
            "status": "APPLIED" | "EXTERNAL" | "SKIPPED" | "ALREADY_APPLIED" | "ERROR",
            "job_id": str,
            "title": str,
            "company": str,
            "url": str,
            "reason": str
        }
        """
        pass

    @abstractmethod
    def search_and_apply(
        self,
        role: str,
        location: str = "India",
        limit: int = 10,
        freshness_days: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Searches jobs for the specified role and location, iterates through matches,
        and applies to eligible listings up to `limit`.
        """
        pass
