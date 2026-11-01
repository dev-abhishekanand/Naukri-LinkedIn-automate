#!/usr/bin/env python3
"""
Scrapes live ground-truth metrics from Naukri Secondary Account (session_naukri_secondary.json).
"""

import sys
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from common.browser_factory import launch_chrome_browser, create_stealth_context

SESSION_FILE = PROJECT_DIR / "session_naukri_secondary.json"
OUTPUT_FILE = PROJECT_DIR / "secondary_scraped_analytics.json"


def main():
    print(f"[*] Checking session file: {SESSION_FILE}")
    if not SESSION_FILE.exists():
        print("❌ Error: session_naukri_secondary.json not found!")
        sys.exit(1)

    results = {
        "account": "abhishekanand171295@gmail.com",
        "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "candidate": {},
        "metrics": {},
        "keywords": {},
        "match_radar": {},
        "raw_text": ""
    }

    captured_apis = {}

    with sync_playwright() as p:
        print("[*] Launching minimized Google Chrome with stealth context...")
        browser = launch_chrome_browser(p, browser_mode="minimized")
        context = create_stealth_context(browser, storage_state=SESSION_FILE, viewport={"width": 1440, "height": 1000})
        page = context.new_page()

        def on_response(response):
            url = response.url
            if any(x in url.lower() for x in ["profile-performance", "search-impressions", "resman-aggregator", "dashboard"]):
                if "static" not in url and "css" not in url and "png" not in url and "svg" not in url:
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            captured_apis[url] = response.json()
                            print(f"[✓] Captured API: {url[:80]}...")
                    except Exception:
                        pass

        page.on("response", on_response)

        # 1. Profile Page
        print("[*] Navigating to https://www.naukri.com/mnjuser/profile...")
        page.goto("https://www.naukri.com/mnjuser/profile", wait_until="domcontentloaded", timeout=45000)
        time.sleep(4)
        p_text = page.locator("body").inner_text()
        with open(PROJECT_DIR / "secondary_profile_dump.txt", "w") as f:
            f.write(p_text)

        # 2. Homepage (for Match Radar)
        print("[*] Navigating to https://www.naukri.com/mnjuser/homepage...")
        page.goto("https://www.naukri.com/mnjuser/homepage", wait_until="domcontentloaded", timeout=45000)
        time.sleep(4)
        h_text = page.locator("body").inner_text()
        with open(PROJECT_DIR / "secondary_homepage_dump.txt", "w") as f:
            f.write(h_text)

        # 3. Performance Page (for CloudGateway API & Chart.js)
        print("[*] Navigating to https://www.naukri.com/mnjuser/performance...")
        page.goto("https://www.naukri.com/mnjuser/performance", wait_until="networkidle", timeout=45000)
        time.sleep(5)
        perf_text = page.locator("body").inner_text()
        with open(PROJECT_DIR / "secondary_perf_dump.txt", "w") as f:
            f.write(perf_text)

        # Extract Chart.js instances if any
        chart_instances = page.evaluate('''() => {
            if (window.Chart && window.Chart.instances) {
                return Object.values(window.Chart.instances).map(inst => ({
                    id: inst.id,
                    labels: inst.data && inst.data.labels,
                    datasets: inst.data && inst.data.datasets.map(ds => ({
                        label: ds.label,
                        data: ds.data
                    }))
                }));
            }
            return [];
        }''')
        results["chart_instances"] = chart_instances

        # Save screenshot
        page.screenshot(path=str(PROJECT_DIR / "secondary_performance_page.png"), full_page=True)
        print("[✓] Screenshot saved to secondary_performance_page.png")

        browser.close()

    results["captured_apis"] = captured_apis

    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[✓] Results successfully saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
