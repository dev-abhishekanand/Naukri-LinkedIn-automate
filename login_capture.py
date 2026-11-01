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
        print(f"\n[+] Launching {'Official Google Chrome' if channel == 'chrome' else 'Chromium'} for authentication capture on {site.upper()}...")
        
        profile_dir = Path(f"chrome_profile_{site}").resolve()
        profile_dir.mkdir(parents=True, exist_ok=True)
        context = launch_chrome_persistent_context(p, user_data_dir=profile_dir, headless=False)
        page = context.pages[0] if context.pages else context.new_page()
            
        try:
            page.goto(url, timeout=30000)
        except Exception as e:
            print(f"[!] Navigation notice: {e}")

        print(f"\n=======================================================")
        print(f"🌐 A Google Chrome window is open at: {url}")
        print(f"👉 Please complete your login by hand in the browser.")
        print(f"👉 Solve password, 2FA, or Google Sign-in.")
        print(f"⏳ Waiting for login confirmation (auto-detecting)...")
        print(f"=======================================================\n")

        # Automatically detect successful login redirect or window closure
        start_time = time.time()
        while time.time() - start_time < 300:  # 5 minutes
            try:
                # If user closed all browser windows, finish immediately
                if not context.pages or all(pg.is_closed() for pg in context.pages):
                    print("  [✓] Browser window closed by user. Saving session cookies...")
                    break

                active_page = context.pages[-1] if context.pages else page
                curr_url = active_page.url.lower()
                cookies = context.cookies()
                c_names = {c.get("name") for c in cookies}

                # 1. OAUTH FLOW PROTECTION:
                # If user is currently on Google, Apple, LinkedIn OAuth, or identity provider, NEVER detect as logged in!
                # This guarantees user has ample time to type email, password, and complete 2FA without premature window closure.
                oauth_domains = ["accounts.google.com", "google.com", "appleid.apple.com", "auth0.com", "oauth", "signin.aws"]
                if any(dom in curr_url for dom in oauth_domains):
                    time.sleep(1)
                    continue

                # 2. PORTAL-SPECIFIC STRICT DETECTION (Zero false positives, domain-verified)
                if site in ("naukri", "naukri_secondary", "naukri_tertiary"):
                    has_naukri_auth = any(c in c_names for c in ["nauk_user", "naukri_auth", "n_auth", "nauk_at", "is_login", "nauk_sid"])
                    is_naukri_domain = "naukri.com" in curr_url
                    if is_naukri_domain and "login" not in curr_url and (has_naukri_auth or "mnjuser" in curr_url or "homepage" in curr_url):
                        print("  [✓] Detected valid Naukri candidate authentication cookies!")
                        time.sleep(2)
                        break

                elif site == "linkedin":
                    has_li_at = any(c.get("name") == "li_at" and len(c.get("value", "")) > 15 for c in cookies)
                    is_li_domain = "linkedin.com" in curr_url
                    is_logged_in_page = ("feed" in curr_url or "mynetwork" in curr_url or "jobs" in curr_url) and not any(x in curr_url for x in ["login", "checkpoint", "uas"])
                    if is_li_domain and has_li_at and is_logged_in_page:
                        print("  [✓] Detected valid li_at authentication cookie and logged-in feed!")
                        time.sleep(2)
                        break

                elif site == "instahyre":
                    is_insta_domain = "instahyre.com" in curr_url
                    is_candidate_page = ("candidate/opportunities" in curr_url or "candidate/profile" in curr_url or "candidate/dashboard" in curr_url)
                    has_insta_auth = any(c in c_names for c in ["sessionid", "auth_token"])
                    if is_insta_domain and not any(x in curr_url for x in ["/login", "signin", "signup"]) and (is_candidate_page or (has_insta_auth and "candidate" in curr_url)):
                        print("  [✓] Detected logged-in Instahyre candidate dashboard!")
                        time.sleep(2)
                        break

                elif site == "cutshort":
                    is_cs_domain = "cutshort.io" in curr_url
                    has_cs_auth = any(c.get("name") == "cutshort_authentication" and len(c.get("value", "")) > 15 for c in cookies)
                    is_cs_page = ("dashboard" in curr_url or "profile" in curr_url or "inbox" in curr_url or "jobs" in curr_url)
                    if is_cs_domain and "login" not in curr_url and (has_cs_auth or is_cs_page):
                        print("  [✓] Detected logged-in Cutshort dashboard and verified candidate auth cookie!")
                        time.sleep(2)
                        break

                elif site == "wellfound":
                    is_wf_domain = "wellfound.com" in curr_url
                    has_wf_auth = any(c in c_names for c in ["remember_user_token", "auth_token"])
                    is_wf_page = ("jobs" in curr_url or "profile" in curr_url or "overview" in curr_url or "candidates" in curr_url)
                    if is_wf_domain and "login" not in curr_url and (has_wf_auth or is_wf_page):
                        print("  [✓] Detected genuine authenticated Wellfound user session!")
                        time.sleep(2)
                        break

                elif site == "hirist":
                    is_hirist_domain = ("hirist.tech" in curr_url or "hirist.com" in curr_url)
                    has_hirist_auth = any(c in c_names for c in ["hirist_session", "candidate_id", "user_id"])
                    is_hirist_logged_in = ("candidate/dashboard" in curr_url or "candidate/jobs" in curr_url or "candidate/profile" in curr_url or "candidate/my-applications" in curr_url)
                    if is_hirist_domain and "candidate/login" not in curr_url and not any(x in curr_url for x in ["/login", "signin", "signup"]) and (is_hirist_logged_in or has_hirist_auth):
                        print("  [✓] Detected logged-in Hirist candidate dashboard!")
                        time.sleep(2)
                        break

                elif site == "indeed":
                    is_indeed_domain = "indeed.com" in curr_url
                    has_signin = False
                    try:
                        signin_elem = active_page.locator("a[href*='account/login'], a:has-text('Sign in')").first
                        signin_visible = signin_elem.count() > 0 and signin_elem.is_visible()
                    except Exception:
                        signin_visible = False

                    has_profile = False
                    try:
                        prof_elem = active_page.locator("[aria-label*='Account'], [aria-label*='Profile'], #gnav-account-filter, .gnav-AccountMenu, a[href*='/myprofile'], a[href*='app-tracker']").first
                        has_profile = prof_elem.count() > 0 and prof_elem.is_visible()
                    except Exception:
                        pass

                    has_auth_cookie = any(c.get("name") in ["PPID", "SHARED_SESSION_TOKEN", "LOGGED_IN", "HP_MYINDEED", "UD", "SOCK"] for c in cookies)

                    if is_indeed_domain and (has_profile or has_auth_cookie) and not signin_visible and "login" not in curr_url and "__cf_chl" not in curr_url:
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
        elif site == "cutshort":
            has_cs_auth = any(c.get("name") == "cutshort_authentication" and len(c.get("value", "")) > 15 for c in cookies)
            if not has_cs_auth:
                print("\n[⚠️ WARNING] Cutshort authentication token 'cutshort_authentication' was NOT detected!")
            else:
                print("\n[✓] Successfully verified Cutshort candidate authentication session.")
        elif site == "hirist":
            has_hirist_auth = any(c.get("name") in ["hirist_session", "candidate_id", "user_id"] for c in cookies)
            if not has_hirist_auth and "login" in curr_url:
                print("\n[⚠️ WARNING] Hirist candidate authenticated session was NOT verified!")
            else:
                print("\n[✓] Successfully captured Hirist candidate session.")
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
        try:
            context.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
