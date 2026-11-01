#!/usr/bin/env python3
"""
Scrapes live ground-truth performance data from Naukri and LinkedIn.
- Naukri: Search appearances, recruiter actions, profile views, top search keywords,
          and 'how your applies matched your profile' 7-day radar.
- LinkedIn: Profile views, search appearances, post impressions.
"""

import os
import sys
import json
import time
import re
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from common.browser_factory import launch_chrome_browser


def scrape_naukri_live(session_path: Path, label: str = "primary"):
    print(f"\n========================================================")
    print(f"🔍 [NAUKRI {label.upper()}] Launching Playwright to scrape live portal data...")
    print(f"========================================================")
    
    if not session_path.exists():
        print(f"❌ Session file not found: {session_path}")
        return {"error": "SESSION_FILE_NOT_FOUND", "session_path": str(session_path)}

    results = {
        "label": label,
        "scraped_at": datetime.now().isoformat(),
        "candidate": {},
        "metrics": {},
        "keywords": [],
        "match_radar": {},
        "raw_text_snippets": []
    }

    with sync_playwright() as p:
        browser = launch_chrome_browser(p, headless=True)
        context = browser.new_context(
            storage_state=str(session_path),
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # Step 1: Visit main profile page
        profile_url = "https://www.naukri.com/mnjuser/profile"
        print(f"[*] Navigating to {profile_url}...")
        try:
            page.goto(profile_url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(5)
            curr_url = page.url
            print(f"[*] Current URL: {curr_url}")

            if "login" in curr_url.lower():
                print(f"⚠️ Redirected to login page. Session is expired or invalid!")
                results["error"] = "SESSION_EXPIRED"
                browser.close()
                return results

            # Extract Candidate identity from profile page
            try:
                name_el = page.locator(".user-name, .fullname, .user-info .name, h1, [class*='userName']").first
                if name_el.is_visible(timeout=3000):
                    results["candidate"]["name"] = name_el.inner_text().strip()
            except Exception:
                pass

            # Search appearance numbers on profile page
            body_text = page.locator("body").inner_text()
            results["raw_text_snippets"].append(body_text[:2000])

            # Extract numbers via regex patterns
            # 1. Search appearances
            m_searches = re.findall(r"(\d+)\s+Search\s+appearance", body_text, re.IGNORECASE)
            if not m_searches:
                m_searches = re.findall(r"Search\s+appearance[s]?\D{0,15}(\d+)", body_text, re.IGNORECASE)
            if m_searches:
                results["metrics"]["search_appearances"] = int(m_searches[0])
                print(f"[✓] Search Appearances: {results['metrics']['search_appearances']}")

            # 2. Recruiter actions
            m_actions = re.findall(r"(\d+)\s+Recruiter\s+action", body_text, re.IGNORECASE)
            if not m_actions:
                m_actions = re.findall(r"Recruiter\s+action[s]?\D{0,15}(\d+)", body_text, re.IGNORECASE)
            if m_actions:
                results["metrics"]["recruiter_actions"] = int(m_actions[0])
                print(f"[✓] Recruiter Actions: {results['metrics']['recruiter_actions']}")

            # Check for candidate email or ID in page source
            m_email = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", body_text)
            if m_email:
                results["candidate"]["detected_email"] = m_email.group(0)

            # Look for Profile Performance link/button
            print("[*] Checking for Profile Performance or Analytics section...")
            perf_links = page.locator("a[href*='performance'], a[href*='search-appearance'], [class*='performance'], [class*='analytics']").all()
            for pl in perf_links:
                try:
                    href = pl.get_attribute("href")
                    txt = pl.inner_text()
                    print(f"  Found link: {txt} -> {href}")
                except Exception:
                    pass

        except Exception as e:
            print(f"❌ Error during profile page scrape: {e}")

        # Step 2: Visit Homepage / Dashboard where match radar usually appears
        home_url = "https://www.naukri.com/mnjuser/homepage"
        print(f"\n[*] Navigating to {home_url} to check match radar & activity...")
        try:
            page.goto(home_url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(5)
            curr_url = page.url
            print(f"[*] Home URL: {curr_url}")
            home_text = page.locator("body").inner_text()

            # Look for 'how your applies matched your profile'
            m_match = re.search(r"(\d+)\s+out\s+of\s+(\d+)\s+applied", home_text, re.IGNORECASE)
            if not m_match:
                m_match = re.search(r"(\d+)/(\d+)\s+applied", home_text, re.IGNORECASE)
            if m_match:
                results["match_radar"]["ratio"] = f"{m_match.group(1)} out of {m_match.group(2)}"
                print(f"[✓] Applies match ratio: {results['match_radar']['ratio']}")

            # Check percentage scores:
            for pattern, key in [
                (r"Early\s+applicant\D{0,10}(\d+)%", "early_applicant_pct"),
                (r"Work\s+experience\D{0,10}(\d+)%", "experience_match_pct"),
                (r"Location\D{0,10}(\d+)%", "location_match_pct"),
                (r"Key\s+skills\D{0,10}(\d+)%", "key_skills_match_pct"),
                (r"Industry\D{0,10}(\d+)%", "industry_match_pct"),
                (r"Department\D{0,10}(\d+)%", "department_match_pct"),
            ]:
                m = re.search(pattern, home_text, re.IGNORECASE)
                if m:
                    results["match_radar"][key] = int(m.group(1))
                    print(f"[✓] {key}: {m.group(1)}%")

            # Step 3: Extract top keywords searched by recruiters if present
            # Often listed as "Keywords recruiters used to find you"
            if "keyword" in home_text.lower():
                print("[*] Found 'keyword' in homepage text. Extracting keywords...")
                lines = [l.strip() for l in home_text.splitlines() if l.strip()]
                for i, line in enumerate(lines):
                    if "keyword" in line.lower() and i + 1 < len(lines):
                        for next_idx in range(i + 1, min(i + 15, len(lines))):
                            kw_candidate = lines[next_idx]
                            if len(kw_candidate) > 2 and len(kw_candidate) < 40 and not any(x in kw_candidate.lower() for x in ["view", "more", "search", "recruiter", "profile"]):
                                results["keywords"].append(kw_candidate)

            # Take debug screenshot of homepage
            shot_path = PROJECT_DIR / f"scratch_naukri_{label}_home.png"
            page.screenshot(path=str(shot_path), full_page=True)
            print(f"[✓] Saved screenshot to {shot_path}")

        except Exception as e:
            print(f"❌ Error during homepage scrape: {e}")

        browser.close()

    return results


def scrape_linkedin_live(session_path: Path):
    print(f"\n========================================================")
    print(f"🔍 [LINKEDIN] Launching Playwright to scrape live LinkedIn analytics...")
    print(f"========================================================")
    
    if not session_path.exists():
        print(f"❌ Session file not found: {session_path}")
        return {"error": "SESSION_FILE_NOT_FOUND"}

    results = {
        "scraped_at": datetime.now().isoformat(),
        "profile_views_7d": None,
        "search_appearances": None,
        "post_impressions": None
    }

    with sync_playwright() as p:
        browser = launch_chrome_browser(p, headless=True)
        context = browser.new_context(
            storage_state=str(session_path),
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # Step 1: Profile Views
        pv_url = "https://www.linkedin.com/analytics/profile-views/"
        print(f"[*] Navigating to {pv_url}...")
        try:
            page.goto(pv_url, wait_until="domcontentloaded", timeout=40000)
            time.sleep(4)
            if "login" not in page.url.lower():
                pv_text = page.locator("body").inner_text()
                m_views = re.search(r"(\d+)\s+profile\s+view", pv_text, re.IGNORECASE)
                if not m_views:
                    m_views = re.search(r"(\d+)\s+viewed\s+your\s+profile", pv_text, re.IGNORECASE)
                if not m_views:
                    m_views = re.search(r"profile\s+views?\D{0,15}(\d+)", pv_text, re.IGNORECASE)
                if m_views:
                    results["profile_views_7d"] = int(m_views.group(1))
                    print(f"[✓] LinkedIn Profile Views (7d): {results['profile_views_7d']}")
        except Exception as e:
            print(f"Note on LinkedIn profile views: {e}")

        # Step 2: Search Appearances
        search_url = "https://www.linkedin.com/analytics/search-appearances/"
        print(f"[*] Navigating to {search_url}...")
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=35000)
            time.sleep(3)
            if "login" not in page.url.lower():
                s_text = page.locator("body").inner_text()
                m_search = re.search(r"(\d+)\s+search\s+appearance", s_text, re.IGNORECASE)
                if not m_search:
                    m_search = re.search(r"appeared\s+in\s+(\d+)\s+search", s_text, re.IGNORECASE)
                if m_search:
                    results["search_appearances"] = int(m_search.group(1))
                    print(f"[✓] LinkedIn Search Appearances: {results['search_appearances']}")
        except Exception as e:
            print(f"Note on LinkedIn searches: {e}")

        # Step 3: Profile dashboard fallback
        if results["profile_views_7d"] is None or results["search_appearances"] is None:
            dash_url = "https://www.linkedin.com/in/abhishekreactdeveloper/"
            print(f"[*] Navigating to profile dashboard {dash_url}...")
            try:
                page.goto(dash_url, wait_until="domcontentloaded", timeout=40000)
                time.sleep(4)
                d_text = page.locator("body").inner_text()
                if results["profile_views_7d"] is None:
                    m = re.search(r"(\d+)\s+profile\s+view", d_text, re.IGNORECASE)
                    if m:
                        results["profile_views_7d"] = int(m.group(1))
                if results["search_appearances"] is None:
                    m = re.search(r"(\d+)\s+search\s+appearance", d_text, re.IGNORECASE)
                    if m:
                        results["search_appearances"] = int(m.group(1))
                m_post = re.search(r"(\d+)\s+post\s+impression", d_text, re.IGNORECASE)
                if m_post:
                    results["post_impressions"] = int(m_post.group(1))
            except Exception as e:
                print(f"Note on LinkedIn profile dashboard: {e}")

        shot_path = PROJECT_DIR / "scratch_linkedin_analytics.png"
        page.screenshot(path=str(shot_path), full_page=True)
        print(f"[✓] Saved screenshot to {shot_path}")
        browser.close()

    return results


def main():
    session_naukri = PROJECT_DIR / "session_naukri.json"
    session_naukri_sec = PROJECT_DIR / "session_naukri_secondary.json"
    session_li = PROJECT_DIR / "session_linkedin.json"

    out_report = {}

    # Scrape Naukri Primary
    if session_naukri.exists():
        out_report["naukri_primary"] = scrape_naukri_live(session_naukri, label="primary")
    else:
        out_report["naukri_primary"] = {"error": "NO_SESSION_FILE"}

    # Scrape Naukri Secondary (if session exists)
    if session_naukri_sec.exists():
        out_report["naukri_secondary"] = scrape_naukri_live(session_naukri_sec, label="secondary")
    else:
        out_report["naukri_secondary"] = {
            "error": "SESSION_FILE_NOT_FOUND",
            "message": "session_naukri_secondary.json does not exist. Needs authentication."
        }

    # Scrape LinkedIn
    if session_li.exists():
        out_report["linkedin"] = scrape_linkedin_live(session_li)
    else:
        out_report["linkedin"] = {"error": "NO_SESSION_FILE"}

    output_path = PROJECT_DIR / "live_scraped_analytics.json"
    with open(output_path, "w") as f:
        json.dump(out_report, f, indent=2)
    print(f"\n[✓] All scraped data written to {output_path}")


if __name__ == "__main__":
    main()
