import time
import json
import urllib.parse
from playwright.sync_api import sync_playwright
from common.browser_factory import launch_chrome_browser

# Define the target job alerts with their exact query parameters
ALERTS_CONFIG = [
    {
        "name": "React Developer (India)",
        "keywords": '"React Developer" OR "React.js Developer" OR "ReactJS Developer"',
        "location": "India",
        "geoId": "102713980",
        "filters": "&f_TPR=r86400&f_JT=F" # Past 24 hours, Full-time
    },
    {
        "name": "Next.js & TypeScript Developer (India)",
        "keywords": '("Next.js" OR "TypeScript") AND ("Frontend Developer" OR "Frontend Engineer")',
        "location": "India",
        "geoId": "102713980",
        "filters": "&f_JT=F"
    },
    {
        "name": "Immediate Joiner / Urgent React (India)",
        "keywords": '("React" OR "Frontend") AND ("immediate joiner" OR "immediate hiring" OR "0 days")',
        "location": "India",
        "geoId": "102713980",
        "filters": ""
    },
    {
        "name": "React Developer (Bengaluru)",
        "keywords": '"React Developer" OR "Frontend Engineer"',
        "location": "Bengaluru, Karnataka, India",
        "geoId": "105214831",
        "filters": "&f_JT=F"
    },
    {
        "name": "React Developer (Hyderabad)",
        "keywords": '"React Developer" OR "Frontend Engineer"',
        "location": "Hyderabad, Telangana, India",
        "geoId": "105556991",
        "filters": "&f_JT=F"
    },
    {
        "name": "React Developer (Pune)",
        "keywords": '"React Developer" OR "Frontend Engineer"',
        "location": "Pune, Maharashtra, India",
        "geoId": "103671728",
        "filters": "&f_JT=F"
    },
    {
        "name": "Remote Frontend Engineer (India)",
        "keywords": '"React Developer" OR "Frontend Engineer"',
        "location": "India",
        "geoId": "102713980",
        "filters": "&f_WT=2&f_JT=F" # Remote only, Full-time
    }
]

def build_search_url(alert):
    kw = urllib.parse.quote(alert["keywords"])
    loc = urllib.parse.quote(alert["location"])
    geo = alert["geoId"]
    extra = alert.get("filters", "")
    return f"https://www.linkedin.com/jobs/search/?keywords={kw}&location={loc}&geoId={geo}{extra}"

def setup_alerts():
    print("="*70)
    print("LINKEDIN AUTOMATED JOB ALERTS SETUP")
    print("="*70)
    
    with sync_playwright() as p:
        # Launch visible browser so if login is needed, user can enter password
        browser = launch_chrome_browser(p, headless=False, slow_mo=100)
        context = browser.new_context(
            storage_state="session_linkedin.json",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 850}
        )
        page = context.new_page()

        # Step 1: Check login status
        print("\nChecking login status on LinkedIn...")
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        def is_authenticated():
            cookies = context.cookies()
            has_li_at = any(c.get("name") == "li_at" and len(c.get("value", "")) > 10 for c in cookies)
            has_nav_profile = bool(page.query_selector(".global-nav__me, nav.global-nav, #global-nav"))
            has_signin_btn = bool(page.query_selector("a:has-text('Sign in'), a:has-text('Join now')"))
            return has_li_at and (has_nav_profile or not has_signin_btn)

        if not is_authenticated():
            print("\n" + "!"*70)
            print("NOT LOGGED IN: LinkedIn requires you to sign in.")
            print("A browser window is currently open.")
            print("Please enter your password / complete 2FA in the opened Chromium window.")
            print("Waiting for you to complete sign-in...")
            print("!"*70 + "\n")
            
            # Wait until user reaches feed and li_at cookie is present
            start_time = time.time()
            logged_in = False
            while time.time() - start_time < 300: # 5 minutes
                if is_authenticated():
                    logged_in = True
                    break
                time.sleep(2)
                
            if not logged_in:
                print("❌ Sign-in not completed. Aborting alert setup to avoid guest/unauthenticated actions.")
                browser.close()
                return
                
            print("✓ Sign-in confirmed! 'li_at' cookie verified. Updating session_linkedin.json...")
            context.storage_state(path="session_linkedin.json")
            time.sleep(2)
        else:
            print("✓ Confirmed logged in with valid 'li_at' session!")

        # Step 2: Iterate through each alert configuration
        results = []
        for idx, alert in enumerate(ALERTS_CONFIG, start=1):
            name = alert["name"]
            url = build_search_url(alert)
            print(f"\n[{idx}/{len(ALERTS_CONFIG)}] Setting Alert: {name}")
            print(f"URL: {url}")
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(4)
                
                # Verify we are STILL logged in
                if not is_authenticated():
                    print(f"  ❌ Lost login state while loading {name}. Skipping.")
                    results.append((name, "UNAUTHENTICATED", url))
                    continue
                
                # Check for "Set alert" toggle or button
                alert_toggle = page.query_selector(".jobs-search-create-alert__artdeco-toggle, button[aria-label*='Job alert' i], button[aria-label*='job alert' i], input[role='switch'], input[type='checkbox'][id*='alert']")
                
                if not alert_toggle:
                    toggle_label = page.query_selector("text='Set alert'")
                    if toggle_label:
                        alert_toggle = toggle_label.query_selector("xpath=..") or toggle_label

                if alert_toggle:
                    # Check current state
                    is_checked = alert_toggle.get_attribute("aria-checked") or alert_toggle.get_attribute("checked")
                    if is_checked in ["true", "checked", True]:
                        print(f"  ✓ Alert is ALREADY ACTIVE for: {name}")
                        page.screenshot(path=f"scratch/alert_{idx}_already_active.png")
                        results.append((name, "ALREADY_ACTIVE", url))
                    else:
                        print(f"  Clicking toggle to turn ON alert...")
                        alert_toggle.click()
                        time.sleep(2.5)
                        
                        # Handle LinkedIn alert preferences modal/drawer if it appears
                        modal = page.query_selector("div[role='dialog'], .artdeco-modal")
                        if modal:
                            print("  [Preferences Modal] Configuring alert preferences...")
                            # Try to select Daily if available
                            daily_opt = modal.query_selector("label:has-text('Daily'), input[value='DAILY']")
                            if daily_opt:
                                daily_opt.click()
                                time.sleep(0.5)
                                
                            # Click Save or Done
                            save_btn = modal.query_selector("button:has-text('Save'), button:has-text('Done')")
                            if save_btn:
                                save_btn.click()
                                time.sleep(2)
                                
                        page.screenshot(path=f"scratch/alert_{idx}_enabled.png")
                        print(f"  ✓ Successfully ENABLED alert for: {name}")
                        results.append((name, "ENABLED", url))
                else:
                    print(f"  ⚠️ Could not find 'Set alert' toggle element on page.")
                    page.screenshot(path=f"scratch/alert_{idx}_not_found.png")
                    results.append((name, "TOGGLE_NOT_FOUND", url))
                    
            except Exception as e:
                print(f"  ❌ Error setting alert '{name}': {e}")
                results.append((name, f"ERROR: {e}", url))

        # Step 3: Verify created alerts
        print("\n" + "="*70)
        print("SUMMARY OF JOB ALERTS:")
        print("="*70)
        for name, status, url in results:
            print(f"  • {name}: {status}")

        context.storage_state(path="session_linkedin.json")
        time.sleep(2)
        browser.close()
        print("\nFinished!")

if __name__ == "__main__":
    setup_alerts()
