#!/usr/bin/env python3
"""
Interactive Portal Login & Session Re-authenticator
Allows manual or menu-driven login capture across all portals:
- Naukri (Primary, Secondary)
- LinkedIn
- Indeed
- Instahyre
- Cutshort
- Wellfound
- Hirist
"""
import sys
import os
import shutil
import time
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from common.browser_factory import (
    launch_chrome_persistent_context,
    get_browser_channel
)
from verify_all_portals import verify_all, print_report, PORTALS

LOGIN_URLS = {
    "naukri": "https://www.naukri.com/nlogin/login",
    "naukri_secondary": "https://www.naukri.com/nlogin/login",
    "linkedin": "https://www.linkedin.com/login",
    "indeed": "https://secure.indeed.com/account/login?hl=en&continue=https%3A%2F%2Fin.indeed.com",
    "instahyre": "https://www.instahyre.com/login/",
    "cutshort": "https://cutshort.io/login",
    "wellfound": "https://wellfound.com/login",
    "hirist": "https://www.hirist.tech/candidate/login",
}

SESSION_FILES = {
    "naukri": "session_naukri.json",
    "naukri_secondary": "session_naukri_secondary.json",
    "linkedin": "session_linkedin.json",
    "indeed": "session_indeed.json",
    "instahyre": "session_instahyre.json",
    "cutshort": "session_cutshort.json",
    "wellfound": "session_wellfound.json",
    "hirist": "session_hirist.json",
}


def backup_and_clean_all():
    """Backs up all existing session files to archive_sessions_backup/ and removes them."""
    backup_dir = PROJECT_DIR / "archive_sessions_backup"
    backup_dir.mkdir(exist_ok=True)
    
    cleaned = 0
    for key, fname in SESSION_FILES.items():
        src = PROJECT_DIR / fname
        if src.exists():
            dst = backup_dir / f"{src.stem}_{int(time.time())}.json"
            shutil.copy2(src, dst)
            src.unlink()
            cleaned += 1
            print(f"  ✓ Archived & cleared: {fname}")
            
    # Also clean profile locks
    for p_dir in PROJECT_DIR.glob("chrome_profile_*"):
        if p_dir.is_dir():
            lock = p_dir / "SingletonLock"
            if lock.exists():
                try:
                    lock.unlink()
                except Exception:
                    pass

    print(f"\n[✓] Successfully cleaned {cleaned} old session files. Ready for fresh authentication!\n")


def clean_single(portal_key: str):
    """Clears a single portal session."""
    fname = SESSION_FILES.get(portal_key)
    if fname:
        p = PROJECT_DIR / fname
        if p.exists():
            p.unlink()
            print(f"  ✓ Removed old session file: {fname}")


def run_login(portal_key: str):
    url = LOGIN_URLS.get(portal_key)
    if not url:
        print(f"Error: Unknown portal '{portal_key}'")
        return

    session_file = PROJECT_DIR / SESSION_FILES[portal_key]
    
    # Remove old session
    if session_file.exists():
        session_file.unlink()

    profile_dir = PROJECT_DIR / f"chrome_profile_{portal_key}"
    profile_dir.mkdir(parents=True, exist_ok=True)

    # Clean stale lock
    lock = profile_dir / "SingletonLock"
    if lock.exists():
        try:
            lock.unlink()
        except Exception:
            pass

    print(f"\n=======================================================")
    print(f"🚀 Launching Google Chrome for {portal_key.upper()}...")
    print(f"👉 Target URL: {url}")
    print(f"=======================================================\n")

    with sync_playwright() as p:
        channel = get_browser_channel()
        context = launch_chrome_persistent_context(
            p,
            user_data_dir=profile_dir,
            headless=False,
            browser_mode="visible"
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto(url, timeout=45000)
        except Exception as e:
            print(f"[!] Navigation notice: {e}")

        print("\n-------------------------------------------------------")
        print("1. Log in manually in the opened Chrome window.")
        print("2. Complete 2FA, OTP, or Google Sign-in.")
        print("3. Once on your candidate dashboard / feed:")
        print("   - You can just WAIT (it auto-detects in 2 seconds), OR")
        print("   - Close the browser window to finish immediately.")
        print("-------------------------------------------------------\n")

        start = time.time()
        login_authenticated = False
        captured_page_url = ""

        while time.time() - start < 360:  # 6 minutes
            try:
                if not context.pages or all(pg.is_closed() for pg in context.pages):
                    print("  [✓] Browser window closed. Saving session...")
                    break

                active_page = context.pages[-1] if context.pages else page
                curr_url = active_page.url.lower()
                captured_page_url = curr_url
                cookies = context.cookies()
                c_names = {c.get("name") for c in cookies}

                # OAUTH FLOW PROTECTION:
                # If user is currently on Google, Apple, LinkedIn OAuth, or identity provider, NEVER detect as logged in!
                oauth_domains = ["accounts.google.com", "google.com", "appleid.apple.com", "auth0.com", "oauth", "signin.aws"]
                if any(dom in curr_url for dom in oauth_domains):
                    time.sleep(1)
                    continue

                if portal_key in ("naukri", "naukri_secondary"):
                    is_naukri_domain = "naukri.com" in curr_url
                    if is_naukri_domain and "login" not in curr_url and (any(c in c_names for c in ["nauk_at", "nauk_user", "n_auth", "is_login"]) or "mnjuser" in curr_url or "homepage" in curr_url):
                        print("  [✓] Verified Naukri authentication tokens!")
                        time.sleep(2)
                        break

                elif portal_key == "linkedin":
                    is_li_domain = "linkedin.com" in curr_url
                    has_li_at = any(c.get("name") == "li_at" and len(c.get("value", "")) > 15 for c in cookies)
                    is_logged_in = ("feed" in curr_url or "jobs" in curr_url or "mynetwork" in curr_url) and not any(x in curr_url for x in ["login", "checkpoint", "uas"])
                    if is_li_domain and has_li_at and is_logged_in:
                        print("  [✓] Verified LinkedIn 'li_at' authentication token!")
                        time.sleep(2)
                        break

                elif portal_key == "instahyre":
                    is_insta_domain = "instahyre.com" in curr_url
                    is_candidate_page = any(route in curr_url for route in ["candidate/opportunities", "candidate/profile", "candidate/dashboard", "candidate/applications"])
                    has_sessionid = any(c.get("name") == "sessionid" and len(c.get("value", "")) > 15 for c in cookies)
                    if is_insta_domain and not any(x in curr_url for x in ["/login", "signin", "signup"]) and is_candidate_page and has_sessionid:
                        print("  [✓] Verified Instahyre candidate dashboard!")
                        login_authenticated = True
                        time.sleep(3)
                        break

                elif portal_key == "cutshort":
                    is_cs_domain = "cutshort.io" in curr_url
                    is_cs_page = any(route in curr_url for route in ["/profile", "/inbox", "/dashboard", "/jobs", "/candidate", "/messages", "/feed"])
                    has_cs_auth = any(c.get("name") == "cutshort_authentication" and len(c.get("value", "")) > 15 for c in cookies)
                    is_not_homepage = not any(x in curr_url for x in ["/login", "signup", "signin", "/candidate-login"]) and curr_url.rstrip("/") != "https://cutshort.io"
                    if is_cs_domain and is_not_homepage and is_cs_page and has_cs_auth:
                        print("  [✓] Verified Cutshort candidate dashboard!")
                        login_authenticated = True
                        time.sleep(3)
                        break

                elif portal_key == "wellfound":
                    is_wf_domain = "wellfound.com" in curr_url
                    has_wf_auth = any(c in c_names for c in ["remember_user_token", "auth_token"])
                    is_wf_page = ("jobs" in curr_url or "profile" in curr_url or "overview" in curr_url or "candidates" in curr_url)
                    if is_wf_domain and "login" not in curr_url and (has_wf_auth and is_wf_page):
                        print("  [✓] Verified Wellfound authentication token!")
                        login_authenticated = True
                        time.sleep(3)
                        break

                elif portal_key == "hirist":
                    is_hirist_domain = ("hirist.tech" in curr_url or "hirist.com" in curr_url)
                    has_hirist_auth = any(c in c_names for c in ["hirist_seeker_enc", "HIRIST_CK1", "chatSdkToken"])
                    is_hirist_page = any(route in curr_url for route in ["jobfeed", "candidate", "dashboard", "profile"])
                    if is_hirist_domain and not any(x in curr_url for x in ["/login", "candidate/login", "signin", "signup"]) and (has_hirist_auth or is_hirist_page):
                        print("  [✓] Verified Hirist candidate session!")
                        login_authenticated = True
                        time.sleep(3)
                        break

                elif portal_key == "indeed":
                    is_indeed_domain = "indeed.com" in curr_url
                    has_auth = any(c in c_names for c in ["PPID", "SHARED_SESSION_TOKEN", "LOGGED_IN", "SOCK"])
                    if is_indeed_domain and has_auth and "login" not in curr_url and "__cf_chl" not in curr_url:
                        print("  [✓] Verified Indeed candidate session!")
                        time.sleep(2)
                        break

            except Exception:
                pass
            time.sleep(1)

        # Save cookies
        context.storage_state(path=str(session_file))
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                saved_state = json.load(f)
            saved_state["metadata"] = {
                "portal": portal_key,
                "authenticated": login_authenticated,
                "captured_url": captured_page_url,
                "timestamp": int(time.time()),
            }
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(saved_state, f, indent=2)
        except Exception:
            pass
        print(f"\n[✓] Fresh session successfully saved to: {session_file.name}")
        try:
            context.close()
        except Exception:
            pass

    # Re-verify
    conf = PORTALS.get(portal_key) or PORTALS.get(f"{portal_key}_primary")
    if conf:
        from verify_all_portals import check_portal
        res = check_portal(portal_key, conf)
        icon = "🟢" if res["status"] == "LOGGED IN" else "🔴"
        print(f"\nResult: {icon} {res['name']}: {res['status']} ({res['reason']})\n")


def interactive_menu():
    while True:
        print("\n" + "=" * 55)
        print("🔑 CANDIDATE PORTAL AUTHENTICATION HUB")
        print("=" * 55)
        print("  1. Naukri (Primary Account)")
        print("  2. Naukri (Secondary Account)")
        print("  3. LinkedIn")
        print("  4. Indeed")
        print("  5. Instahyre")
        print("  6. Cutshort")
        print("  7. Wellfound")
        print("  8. Hirist")
        print("-------------------------------------------------------")
        print("  v. Verify All Portals Live Status")
        print("  c. Clear All Existing Sessions (Fresh Start)")
        print("  q. Quit")
        print("=" * 55)

        choice = input("👉 Enter choice (1-8, v, c, q): ").strip().lower()

        menu_map = {
            "1": "naukri",
            "2": "naukri_secondary",
            "3": "linkedin",
            "4": "indeed",
            "5": "instahyre",
            "6": "cutshort",
            "7": "wellfound",
            "8": "hirist"
        }

        if choice in menu_map:
            run_login(menu_map[choice])
        elif choice == "v":
            res = verify_all()
            print_report(res)
        elif choice == "c":
            confirm = input("⚠️ Are you sure you want to clear ALL session files? (y/N): ").strip().lower()
            if confirm == "y":
                backup_and_clean_all()
        elif choice == "q":
            print("\nGoodbye!\n")
            break
        else:
            print("Invalid choice. Please select from the menu.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Portal Interactive Login Tool")
    parser.add_argument("portal", nargs="?", choices=list(LOGIN_URLS.keys()) + ["all"], help="Portal to log in to")
    parser.add_argument("--clean-all", action="store_true", help="Archive and delete all sessions")
    parser.add_argument("--verify", action="store_true", help="Verify all portal sessions")
    args = parser.parse_args()

    if args.clean_all:
        backup_and_clean_all()
        sys.exit(0)

    if args.verify:
        results = verify_all()
        print_report(results)
        sys.exit(0)

    if args.portal:
        if args.portal == "all":
            for p in ["naukri", "linkedin", "indeed", "instahyre", "cutshort", "wellfound", "hirist"]:
                run_login(p)
        else:
            run_login(args.portal)
    else:
        interactive_menu()
