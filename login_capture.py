"""
Run this once per site (Naukri, LinkedIn) before running the apply scripts.

It opens a real, visible Chromium window. YOU log in by hand — type your
password, complete 2FA, solve any CAPTCHA yourself. Once you're on the
logged-in homepage, come back to this terminal and press Enter. The script
then saves your session (cookies + local storage) to a local file so the
apply scripts can reuse it without ever seeing your password.

Usage:
    python login_capture.py naukri
    python login_capture.py linkedin
"""
import sys
import time
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright
from common.browser_factory import (
    launch_chrome_browser,
    create_stealth_context,
    launch_chrome_persistent_context,
    CHROME_PROFILE_PRIMARY,
    CHROME_PROFILE_SECONDARY,
    get_browser_channel,
)

SITES = {
    "naukri": "https://www.naukri.com/nlogin/login",
    "naukri_secondary": "https://www.naukri.com/nlogin/login",
    "naukri_tertiary": "https://www.naukri.com/nlogin/login",
    "linkedin": "https://www.linkedin.com/login",
    "instahyre": "https://www.instahyre.com/login/",
    "cutshort": "https://cutshort.io/login",
    "wellfound": "https://wellfound.com/login",
    "hirist": "https://www.hirist.tech/candidate/login",
    "indeed": "https://secure.indeed.com/account/login?hl=en&continue=https%3A%2F%2Fin.indeed.com",
    "google": "https://accounts.google.com/signin",
}


def main():
    parser = argparse.ArgumentParser(description="Capture browser session cookies for Naukri or LinkedIn")
    parser.add_argument("site", choices=list(SITES.keys()), help="Target platform (naukri or linkedin)")
    parser.add_argument("--out", "-o", default=None, help="Output path for session JSON (default: session_{site}.json)")
    args = parser.parse_args()

    site = args.site
    url = SITES[site]
    out_path = args.out or f"session_{site}.json"

    with sync_playwright() as p:
        channel = get_browser_channel()
        print(f"\n[+] Launching {'Official Google Chrome' if channel == 'chrome' else 'Chromium'} for authentication capture...")
        
        browser = None
        if site == "indeed":
            profile_dir = Path("chrome_profile_indeed").resolve()
            context = launch_chrome_persistent_context(p, user_data_dir=profile_dir, headless=False)
            page = context.pages[0] if context.pages else context.new_page()
        else:
            browser = launch_chrome_browser(p, headless=False)
            context = create_stealth_context(browser)
            page = context.new_page()
            
        page.goto(url)

        print(f"\nA browser window is open at {url}")
        print("Log in by hand: password, 2FA, any CAPTCHA — all of it.")
        print(f"Waiting for successful login to {site}...")

        # Automatically detect successful login redirect
        start_time = time.time()
        while time.time() - start_time < 300:  # 5 minutes
            try:
                curr_url = page.url.lower()
                cookies = context.cookies()
                
                if site in ("naukri", "naukri_secondary", "naukri_tertiary"):
                    has_naukri_auth = any(c["name"] in ["nauk_user", "naukri_auth", "n_auth", "nauk_at", "is_login", "nauk_sid"] for c in cookies)
                    if has_naukri_auth or "mnjuser" in curr_url or "homepage" in curr_url:
                        time.sleep(3)
                        break
                elif site == "linkedin":
                    # Must have li_at authentication cookie AND be on a logged-in page
                    has_li_at = any(c["name"] == "li_at" and len(c.get("value", "")) > 10 for c in cookies)
                    is_logged_in_page = ("feed" in curr_url or "mynetwork" in curr_url or "jobs" in curr_url) and "login" not in curr_url and "checkpoint" not in curr_url
                    if has_li_at and is_logged_in_page:
                        print("  [✓] Detected valid li_at authentication cookie and logged-in feed!")
                        time.sleep(3)
                        break
                elif site == "instahyre":
                    if "candidate" in curr_url or "opportunities" in curr_url or page.locator(".candidate-navbar, a[href*='opportunities'], #profile-dropdown").first.is_visible():
                        print("  [✓] Detected logged-in Instahyre candidate dashboard!")
                        time.sleep(2)
                        break
                elif site == "cutshort":
                    has_cs_auth = any(c.get("name") in ["cutshort_authentication", "user_logged_in_once", "cssid", "JSESSIONID"] for c in cookies)
                    if has_cs_auth and "login" not in curr_url and ("dashboard" in curr_url or "profile" in curr_url or "inbox" in curr_url or "jobs" in curr_url or "user" in curr_url):
                        print("  [✓] Detected logged-in Cutshort dashboard and verified candidate auth cookie!")
                        time.sleep(2)
                        break
                elif site == "wellfound":
                    has_wf_auth = any(c.get("name") in ["remember_user_token", "auth_token", "ajs_user_id"] for c in cookies)
                    if has_wf_auth and "login" not in curr_url and ("jobs" in curr_url or "profile" in curr_url or "overview" in curr_url):
                        print("  [✓] Detected genuine authenticated Wellfound user session!")
                        time.sleep(2)
                        break
                elif site == "hirist":
                    has_hirist_auth = any(c.get("name") in ["hirist_session", "user_id", "auth", "token", "candidate_id"] for c in cookies)
                    if (has_hirist_auth or "candidate" in curr_url or "dashboard" in curr_url) and "login" not in curr_url:
                        print("  [✓] Detected logged-in Hirist candidate dashboard!")
                        time.sleep(2)
                        break
                elif site == "indeed":
                    active_page = context.pages[-1] if context.pages else page
                    curr_url = active_page.url.lower()

                    has_signin = False
                    try:
                        signin_elem = active_page.locator("a[href*='account/login'], a:has-text('Sign in')").first
                        has_signin = signin_elem.count() > 0 and signin_elem.is_visible()
                    except Exception:
                        pass

                    has_profile = False
                    try:
                        prof_elem = active_page.locator("[aria-label*='Account'], [aria-label*='Profile'], #gnav-account-filter, .gnav-AccountMenu, a[href*='/myprofile'], a[href*='app-tracker']").first
                        has_profile = prof_elem.count() > 0 and prof_elem.is_visible()
                    except Exception:
                        pass

                    has_auth_cookie = any(c.get("name") in ["PPID", "SHARED_SESSION_TOKEN", "LOGGED_IN", "HP_MYINDEED", "UD", "SOCK"] for c in cookies)

                    if (has_profile or has_auth_cookie) and not has_signin and "login" not in curr_url and "__cf_chl" not in curr_url:
                        print("  [✓] Detected genuine authenticated Indeed candidate session!")
                        time.sleep(2)
                        break
            except Exception:
                pass
            time.sleep(1)

        # Check if login actually succeeded
        cookies = context.cookies()
        if site == "linkedin":
            has_li_at = any(c["name"] == "li_at" and len(c.get("value", "")) > 10 for c in cookies)
            if not has_li_at:
                print("\n[⚠️ WARNING] 'li_at' authentication cookie was NOT found!")
                print("It appears the login was not completed. The session file may not be authenticated.")
            else:
                print("\n[✓] Successfully verified 'li_at' authentication cookie.")
        elif site in ("naukri", "naukri_secondary", "naukri_tertiary"):
            has_nauk_at = any(c["name"] in ["nauk_at", "is_login", "nauk_sid"] for c in cookies)
            if not has_nauk_at:
                print("\n[⚠️ WARNING] Naukri authentication cookies were NOT detected!")
                print("It appears the login was not completed. The session file may not be authenticated.")
            else:
                print("\n[✓] Successfully verified Naukri authentication cookies.")
        elif site == "instahyre":
            has_instahyre_auth = any(
                c.get("name") in ["sessionid", "csrftoken", "auth_token"]
                for c in cookies
            )
            is_logged_in_page = ("candidate" in curr_url or "opportunities" in curr_url) and "login" not in curr_url
            if not has_instahyre_auth or not is_logged_in_page:
                print("\n[⚠️ WARNING] Instahyre authenticated session cookies were NOT detected!")
                print("It appears login was not completed. Please log in with your email/Google account until the candidate dashboard appears.")
            else:
                print("\n[✓] Successfully verified Instahyre authenticated session.")
        elif site == "wellfound":
            print("\n[✓] Successfully captured Wellfound authentication cookies.")
        elif site == "indeed":
            has_profile = False
            try:
                prof_elem = page.locator("[aria-label*='Account'], [aria-label*='Profile'], #gnav-account-filter, .gnav-AccountMenu, a[href*='/myprofile'], a[href*='app-tracker']").first
                has_profile = prof_elem.count() > 0 and prof_elem.is_visible()
            except Exception:
                pass
            if not has_profile:
                print("\n[⚠️ WARNING] Indeed authenticated candidate session was NOT verified!")
                print("If you closed the browser before completing login or 2FA, please rerun login_capture.py indeed.")
            else:
                print("\n[✓] Successfully captured Indeed authenticated candidate session and storage state.")

        context.storage_state(path=out_path)
        print(f"[✓] Session successfully saved to {out_path}.")
        if browser:
            browser.close()
        else:
            context.close()


if __name__ == "__main__":
    main()
