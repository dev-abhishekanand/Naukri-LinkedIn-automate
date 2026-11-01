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
        while time.time() - start < 300:  # 5 minutes
            try:
                if not context.pages or all(pg.is_closed() for pg in context.pages):
                    print("  [✓] Browser window closed. Saving session...")
                    break

                active_page = context.pages[-1] if context.pages else page
                curr_url = active_page.url.lower()
                cookies = context.cookies()
                c_names = {c.get("name") for c in cookies}

                if portal_key in ("naukri", "naukri_secondary"):
                    if any(c in c_names for c in ["nauk_at", "nauk_user", "n_auth", "is_login"]) or "mnjuser" in curr_url or "homepage" in curr_url:
                        print("  [✓] Verified Naukri authentication tokens!")
                        time.sleep(2)
                        break

                elif portal_key == "linkedin":
                    if "li_at" in c_names and ("feed" in curr_url or "jobs" in curr_url or "mynetwork" in curr_url):
                        print("  [✓] Verified LinkedIn 'li_at' authentication token!")
                        time.sleep(2)
                        break

                elif portal_key == "instahyre":
                    if any(c in c_names for c in ["sessionid", "auth_token"]) or "candidate" in curr_url or "opportunities" in curr_url:
                        print("  [✓] Verified Instahyre candidate dashboard!")
                        time.sleep(2)
                        break

                elif portal_key == "cutshort":
                    if "cutshort_authentication" in c_names or "dashboard" in curr_url or "profile" in curr_url or "jobs" in curr_url:
                        print("  [✓] Verified Cutshort authentication token!")
                        time.sleep(2)
                        break

                elif portal_key == "wellfound":
                    if any(c in c_names for c in ["remember_user_token", "auth_token", "ajs_user_id"]) or "jobs" in curr_url or "profile" in curr_url:
                        print("  [✓] Verified Wellfound authentication token!")
                        time.sleep(2)
                        break

                elif portal_key == "hirist":
                    if any(c in c_names for c in ["hirist_session", "user_id"]) or "candidate" in curr_url or "dashboard" in curr_url:
                        print("  [✓] Verified Hirist candidate session!")
                        time.sleep(2)
                        break

                elif portal_key == "indeed":
                    has_auth = any(c in c_names for c in ["PPID", "SHARED_SESSION_TOKEN", "LOGGED_IN", "SOCK"])
                    if has_auth and "login" not in curr_url and "__cf_chl" not in curr_url:
                        print("  [✓] Verified Indeed candidate session!")
                        time.sleep(2)
                        break

            except Exception:
                pass
            time.sleep(1)

        # Save cookies
        context.storage_state(path=str(session_file))
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
