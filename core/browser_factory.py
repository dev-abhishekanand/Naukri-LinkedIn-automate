"""
Browser Factory with Playwright Stealth & Human-like Behavior
Provides configured Chromium instances equipped with stealth scripts, realistic headers,
persistent session loading, and human-like typing and clicking delays.
"""
import time
import random
from pathlib import Path
from typing import Optional, Tuple
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Locator
from playwright_stealth import Stealth

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
)

BASE_DIR = Path(__file__).resolve().parent.parent
PRIMARY_PROFILE_EMAIL = "abhishek.anand.7601@gmail.com"
DEFAULT_PROFILE_DIR = BASE_DIR / "chrome_profile_abhishek_anand_7601"
DEFAULT_SESSION_FILE = BASE_DIR / "session_abhishek_anand_7601.json"


def get_profile_paths(email: Optional[str] = None) -> Tuple[Path, Path]:
    """
    Returns (user_data_dir, session_file) for the candidate profile.
    Defaults to the primary profile for abhishek.anand.7601@gmail.com.
    If a secondary email is specified, routes to a dedicated secondary profile.
    """
    if not email or email.strip().lower() == PRIMARY_PROFILE_EMAIL.lower():
        return DEFAULT_PROFILE_DIR, DEFAULT_SESSION_FILE
    import re
    safe_name = re.sub(r"[^a-zA-Z0-9]", "_", email.strip().lower())
    return BASE_DIR / f"chrome_profile_{safe_name}", BASE_DIR / f"session_{safe_name}.json"


class BrowserSession:
    def __init__(
        self,
        headless: bool = False,
        session_file: Optional[str] = None,
        user_data_dir: Optional[str] = None,
        profile_email: Optional[str] = None
    ):
        self.headless = headless
        p_dir, p_sess = get_profile_paths(profile_email)
        self.user_data_dir = user_data_dir
        self.session_file = session_file or str(p_sess)

        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def start(self) -> Page:
        self.playwright = sync_playwright().start()

        storage_state = None
        if self.session_file and Path(self.session_file).exists():
            storage_state = self.session_file

        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=IsolateOrigins,site-per-process",
        ]

        if self.user_data_dir:
            Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)
            # Persistent context mode with real Google Chrome
            try:
                self.context = self.playwright.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir,
                    channel="chrome",
                    headless=self.headless,
                    user_agent=DEFAULT_USER_AGENT,
                    locale="en-US",
                    timezone_id="Asia/Kolkata",
                    viewport={"width": 1366, "height": 768},
                    args=args,
                )
            except Exception as e:
                # Fallback to bundled Chromium with persistent user_data_dir
                self.context = self.playwright.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir,
                    headless=self.headless,
                    user_agent=DEFAULT_USER_AGENT,
                    locale="en-US",
                    timezone_id="Asia/Kolkata",
                    viewport={"width": 1366, "height": 768},
                    args=args,
                )
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

            # Ensure saved cookies from the targeted portal session file and candidate profile session files are injected
            cookie_sources = []
            if self.session_file and Path(self.session_file).exists():
                cookie_sources.append(Path(self.session_file))
            cookie_sources.extend([DEFAULT_SESSION_FILE, BASE_DIR / "session_naukri.json", BASE_DIR / "session_universal_ats.json"])
            for c_src in cookie_sources:
                if c_src.exists():
                    try:
                        import json
                        with open(c_src, "r", encoding="utf-8") as f:
                            sdata = json.load(f)
                            ck_list = sdata.get("cookies", [])
                            if ck_list:
                                self.context.add_cookies(ck_list)
                    except Exception:
                        pass
        else:
            from common.browser_factory import launch_chrome_browser, create_stealth_context
            self.browser = launch_chrome_browser(self.playwright, headless=self.headless)
            self.context = create_stealth_context(self.browser, storage_state=storage_state)
            self.page = self.context.new_page()

        return self.page

    def save_session(self, output_path: str):
        if self.context:
            self.context.storage_state(path=output_path)
            try:
                # Also synchronize primary profile session file
                self.context.storage_state(path=str(DEFAULT_SESSION_FILE))
            except Exception:
                pass

    def close(self):
        try:
            if self.context:
                if self.session_file:
                    try:
                        self.context.storage_state(path=self.session_file)
                    except Exception:
                        pass
                try:
                    self.context.storage_state(path=str(DEFAULT_SESSION_FILE))
                except Exception:
                    pass
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass


def human_type(locator: Locator, text: str, delay_min_ms: int = 25, delay_max_ms: int = 70):
    """Types text character by character with randomized human intervals."""
    locator.focus()
    for char in text:
        locator.type(char, delay=random.randint(delay_min_ms, delay_max_ms))


def human_delay(min_s: float = 1.0, max_s: float = 2.5):
    """Sleeps for a randomized human duration."""
    time.sleep(random.uniform(min_s, max_s))


def safe_evaluate(page: Page, script: str, arg=None, default=None):
    """Safely executes page.evaluate without crashing on destroyed contexts or transient JS errors."""
    try:
        return page.evaluate(script, arg) if arg is not None else page.evaluate(script)
    except Exception:
        return default
