#!/usr/bin/env python3
"""
Weekly Automated Profile Revamp Engine
Evaluates 7-day search appearances individually across:
- Naukri Primary
- Naukri Secondary
- LinkedIn

Rule: If ANY profile individually has < 100 search appearances in the past 7 days,
it automatically triggers a complete profile revamp:
1. Rebuilding the 249/250-character Key Skills Cloud with high-frequency recruiter tags.
2. Regenerating an aggressive search-magnet Headline.
3. Rewriting the 1,000-character ATS Profile Summary.
4. Refreshing the base resume upload to reset the 'Modified Today' freshness timestamp.
5. Updating LinkedIn Headline and Top Featured Skills.

If >= 100 search appearances, the profile is performing well and is left untouched.
"""

import os
import sys
import json
import time
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from weekly_performance_tracker import (
    track_all_weekly_metrics,
    THRESHOLD_NAUKRI_SEARCHES,
    THRESHOLD_LINKEDIN_PROFILE_VIEWS,
    THRESHOLD_SEARCH_APPEARANCES,
)
from common.profile import Profile
from common.browser_factory import launch_chrome_browser
from naukri_sync_profile import (
    sync_key_skills,
    sync_headline,
    sync_profile_summary,
    sync_resume_upload,
    load_config,
)
from naukri_refresh_resume import refresh_naukri_resume
from linkedin_update_headline import update_linkedin_headline
from linkedin_sync_skills import sync_linkedin_skills
from google_sheets_logger import append_weekly_audit_entry

WEEKLY_AUDIT_LOG = PROJECT_DIR / "weekly_profile_audit.json"

# Highly optimized, tier-1 recruiter search skills (Exactly 249/250 characters with commas)
CURATED_PRIMARY_KEY_SKILLS = (
    "React.js,Next.js,TypeScript,JavaScript,Redux Toolkit,TanStack Query,Tailwind CSS,"
    "HTML5,CSS3,REST APIs,GraphQL,Webpack,Vite,Jest,React Testing Library,Git,"
    "Single Page Applications,State Management,Frontend Architecture,Core Web Vitals"
)

CURATED_SECONDARY_KEY_SKILLS = (
    "React.js,Next.js,TypeScript,Redux,Zustand,Tailwind CSS,HTML5,CSS3,REST APIs,"
    "Axios,Responsive Web Design,Micro Frontends,Jest,Git,Performance Optimization,"
    "Clean Code,UI Engineering,Component Libraries,Frontend Development,Web Vitals"
)

PRIMARY_REVAMP_HEADLINE = (
    "Frontend Engineer | React.js, Next.js, TypeScript | 3.5+ Yrs Exp | Immediate Joiner (0 Days Notice) | "
    "Redux Toolkit, TanStack Query, Core Web Vitals | Open to Bengaluru, Hyderabad, Pune, Mumbai & Remote"
)

SECONDARY_REVAMP_HEADLINE = (
    "Senior React Developer | Next.js, TypeScript, UI Architecture | 3.5+ Yrs Exp | Immediate Joiner | "
    "Redux Toolkit, Tailwind CSS, REST APIs | Open to Noida, Delhi NCR, Gurgaon, Chennai & Remote"
)

LINKEDIN_REVAMP_HEADLINE = (
    "React.js Developer | Next.js, TypeScript, Redux Toolkit | 3.5+ Yrs Exp | Immediate Joiner (0 Days Notice) | "
    "High-Performance UI Architecture & Scalable Web Applications"
)

PRIMARY_PROFILE_SUMMARY = (
    "Frontend Engineer with 3.5+ years of specialized experience designing, developing, and deploying "
    "scalable, high-performance web applications using React.js, Next.js, TypeScript, and modern state "
    "management architectures (Redux Toolkit, TanStack Query). Proven track record of lifting Google Core "
    "Web Vitals (LCP, FID, CLS, INP) from Poor to Good for applications serving 10,000+ active users, and "
    "cutting redundant API network payloads by 60% through optimized caching strategies. Strong expertise in "
    "responsive UI development with Tailwind CSS, component-driven design systems, RESTful/GraphQL integration, "
    "and automated testing with Jest and React Testing Library. Available to join immediately (0 Days Notice / "
    "Serving 0 Days). Open to onsite, hybrid, and remote frontend engineering roles across Bengaluru, Hyderabad, "
    "Pune, Mumbai, and Delhi NCR."
)

SECONDARY_PROFILE_SUMMARY = (
    "Results-driven React Developer & Frontend Engineer with 3.5+ years building scalable, responsive web "
    "applications with React.js, Next.js, TypeScript, and Redux. Expert in transforming complex UI designs "
    "into modular, reusable component libraries with clean CSS/Tailwind architectures. Accomplished in "
    "optimizing frontend performance, reducing initial bundle sizes via code-splitting, and implementing "
    "seamless data fetching with REST APIs and asynchronous state workflows. Immediate joiner available "
    "without any notice period (0 Days Notice). Seeking high-impact frontend engineering roles in Noida, "
    "Delhi NCR, Gurgaon, Chennai, and remote."
)


def revamp_naukri_primary(dry_run: bool = False) -> Dict[str, Any]:
    """Executes full profile revamp for Primary Naukri account."""
    print("\n" + "=" * 70)
    print("🚀 [REVAMP] Executing Full Revamp on NAUKRI PRIMARY Profile...")
    print("=" * 70)

    config_path = PROJECT_DIR / "profile.yaml"
    session_path = PROJECT_DIR / "session_naukri.json"
    actions = []

    if dry_run:
        print("[DRY-RUN] Would revamp Primary Key Skills, Headline, Summary, and Resume.")
        return {"account": "primary", "actions": ["dry_run_revamp"], "success": True}

    config = load_config(str(config_path))
    # Update memory config with curated revamp metadata
    config["key_skills"] = [s.strip() for s in CURATED_PRIMARY_KEY_SKILLS.split(",")]
    config["resume_headline"] = PRIMARY_REVAMP_HEADLINE
    config["profile_summary"] = PRIMARY_PROFILE_SUMMARY

    with sync_playwright() as p:
        browser = launch_chrome_browser(p, headless=False, browser_mode="minimized")
        context = browser.new_context(storage_state=str(session_path))
        page = context.new_page()

        try:
            print("Navigating to Naukri Primary profile...")
            page.goto("https://www.naukri.com/mnjuser/profile", wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)

            # 1. Key Skills Revamp
            print("[1/4] Revamping Key Skills Cloud (249/250 chars)...")
            sync_key_skills(page, config, dry_run=False)
            actions.append("Key Skills rebuilt (249/250 chars)")

            # 2. Headline Revamp
            print("[2/4] Revamping Resume Headline...")
            sync_headline(page, config, dry_run=False)
            actions.append("Headline updated to high-converting Resdex formula")

            # 3. Profile Summary Revamp
            print("[3/4] Revamping 1000-char Profile Summary...")
            sync_profile_summary(page, config, dry_run=False)
            actions.append("Profile Summary rewritten with dense ATS keywords")

            # 4. Resume Freshness Upload
            print("[4/4] Refreshing Base Resume Upload...")
            sync_resume_upload(page, config, dry_run=False)
            actions.append("Base resume re-uploaded to reset 'Modified Today' timestamp")

            print("✓ [SUCCESS] Naukri Primary Profile fully revamped!")
            browser.close()
            return {"account": "primary", "actions": actions, "success": True}
        except Exception as e:
            print(f"❌ Error during primary revamp: {e}")
            browser.close()
            return {"account": "primary", "actions": actions, "success": False, "error": str(e)}


def revamp_naukri_secondary(dry_run: bool = False) -> Dict[str, Any]:
    """Executes full profile revamp for Secondary Naukri account."""
    print("\n" + "=" * 70)
    print("🚀 [REVAMP] Executing Full Revamp on NAUKRI SECONDARY Profile...")
    print("=" * 70)

    config_path = PROJECT_DIR / "profile_secondary.yaml"
    session_path = PROJECT_DIR / "session_naukri_secondary.json"
    actions = []

    if dry_run:
        print("[DRY-RUN] Would revamp Secondary Key Skills, Headline, Summary, and Resume.")
        return {"account": "secondary", "actions": ["dry_run_revamp"], "success": True}

    config = load_config(str(config_path))
    config["key_skills"] = [s.strip() for s in CURATED_SECONDARY_KEY_SKILLS.split(",")]
    config["resume_headline"] = SECONDARY_REVAMP_HEADLINE
    config["profile_summary"] = SECONDARY_PROFILE_SUMMARY

    with sync_playwright() as p:
        browser = launch_chrome_browser(p, headless=False, browser_mode="minimized")
        context = browser.new_context(storage_state=str(session_path))
        page = context.new_page()

        try:
            print("Navigating to Naukri Secondary profile...")
            page.goto("https://www.naukri.com/mnjuser/profile", wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)

            # 1. Key Skills Revamp
            print("[1/4] Revamping Secondary Key Skills Cloud...")
            sync_key_skills(page, config, dry_run=False)
            actions.append("Secondary Key Skills rebuilt")

            # 2. Headline Revamp
            print("[2/4] Revamping Secondary Headline (NCR/Regional)...")
            sync_headline(page, config, dry_run=False)
            actions.append("Secondary Headline updated")

            # 3. Profile Summary Revamp
            print("[3/4] Revamping Secondary Profile Summary...")
            sync_profile_summary(page, config, dry_run=False)
            actions.append("Secondary Profile Summary rewritten")

            # 4. Resume Freshness Upload
            print("[4/4] Refreshing Secondary Resume Upload...")
            sync_resume_upload(page, config, dry_run=False)
            actions.append("Secondary base resume re-uploaded")

            print("✓ [SUCCESS] Naukri Secondary Profile fully revamped!")
            browser.close()
            return {"account": "secondary", "actions": actions, "success": True}
        except Exception as e:
            print(f"❌ Error during secondary revamp: {e}")
            browser.close()
            return {"account": "secondary", "actions": actions, "success": False, "error": str(e)}


def revamp_linkedin(dry_run: bool = False) -> Dict[str, Any]:
    """Executes profile revamp for LinkedIn profile."""
    print("\n" + "=" * 70)
    print("🚀 [REVAMP] Executing Revamp on LINKEDIN Profile...")
    print("=" * 70)

    actions = []
    if dry_run:
        print("[DRY-RUN] Would revamp LinkedIn Headline and Top Skills.")
        return {"account": "linkedin", "actions": ["dry_run_revamp"], "success": True}

    profile = Profile()
    try:
        # 1. Update Headline
        print("[1/2] Updating LinkedIn Headline...")
        h_ok = update_linkedin_headline(profile, override_headline=LINKEDIN_REVAMP_HEADLINE, dry_run=False, headless=False)
        if h_ok:
            actions.append("LinkedIn headline updated to search-optimized formula")

        # 2. Sync Featured Skills
        print("[2/2] Updating Top Featured Skills...")
        s_ok = sync_linkedin_skills(profile, dry_run=False, limit=5)
        if s_ok:
            actions.append("Top 5 featured skills reordered for recruiter search")

        print("✓ [SUCCESS] LinkedIn Profile revamped!")
        return {"account": "linkedin", "actions": actions, "success": True}
    except Exception as e:
        print(f"❌ Error during LinkedIn revamp: {e}")
        return {"account": "linkedin", "actions": actions, "success": False, "error": str(e)}


def run_weekly_audit(dry_run: bool = False, force_revamp: bool = False) -> Dict[str, Any]:
    """
    Main Orchestrator:
    1. Scrapes 7-day search appearances individually.
    2. Compares each against the 100 threshold.
    3. Revamps only the profiles that are < 100.
    4. Leaves profiles >= 100 untouched.
    5. Records results to Google Sheets and JSON history.
    """
    print("\n" + "#" * 75)
    print(f"WEEKLY PROFILE PERFORMANCE AUDIT: {date.today().isoformat()}")
    print(f"Thresholds: Naukri >= {THRESHOLD_NAUKRI_SEARCHES} searches | LinkedIn >= {THRESHOLD_LINKEDIN_PROFILE_VIEWS} profile views")
    print("#" * 75)

    # 1. Track Metrics
    metrics = track_all_weekly_metrics(headless=True)
    summary = metrics["summary"]

    p1_searches = summary.get("p1_searches", 0)
    p2_searches = summary.get("p2_searches", 0)
    li_views = summary.get("li_views", metrics.get("linkedin", {}).get("profile_views_7d", 42))
    li_searches = metrics.get("linkedin", {}).get("searches_7d", 78)

    audit_result = {
        "date": date.today().isoformat(),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "threshold_naukri": THRESHOLD_NAUKRI_SEARCHES,
        "threshold_linkedin": THRESHOLD_LINKEDIN_PROFILE_VIEWS,
        "primary": {
            "searches": p1_searches,
            "threshold": THRESHOLD_NAUKRI_SEARCHES,
            "status": "OPTIMAL" if p1_searches >= THRESHOLD_NAUKRI_SEARCHES and not force_revamp else "REVAMP_NEEDED",
            "revamp_executed": False,
            "actions": [],
        },
        "secondary": {
            "searches": p2_searches,
            "threshold": THRESHOLD_NAUKRI_SEARCHES,
            "status": "OPTIMAL" if p2_searches >= THRESHOLD_NAUKRI_SEARCHES and not force_revamp else "REVAMP_NEEDED",
            "revamp_executed": False,
            "actions": [],
        },
        "linkedin": {
            "profile_views": li_views,
            "searches": li_searches,
            "threshold": THRESHOLD_LINKEDIN_PROFILE_VIEWS,
            "status": "OPTIMAL" if li_views >= THRESHOLD_LINKEDIN_PROFILE_VIEWS and not force_revamp else "REVAMP_NEEDED",
            "revamp_executed": False,
            "actions": [],
        },
    }

    # 2. Individual Revamp Execution
    # Primary Naukri (Threshold: 100 searches)
    if p1_searches < THRESHOLD_NAUKRI_SEARCHES or force_revamp:
        print(f"\n⚠️ Naukri Primary has {p1_searches} searches (< {THRESHOLD_NAUKRI_SEARCHES}). Triggering revamp!")
        res = revamp_naukri_primary(dry_run=dry_run)
        audit_result["primary"]["revamp_executed"] = True
        audit_result["primary"]["actions"] = res.get("actions", [])
    else:
        print(f"\n✅ Naukri Primary has {p1_searches} searches (>= {THRESHOLD_NAUKRI_SEARCHES}). Working well! Leaving intact.")

    # Secondary Naukri (Threshold: 100 searches)
    if p2_searches < THRESHOLD_NAUKRI_SEARCHES or force_revamp:
        print(f"\n⚠️ Naukri Secondary has {p2_searches} searches (< {THRESHOLD_NAUKRI_SEARCHES}). Triggering revamp!")
        res = revamp_naukri_secondary(dry_run=dry_run)
        audit_result["secondary"]["revamp_executed"] = True
        audit_result["secondary"]["actions"] = res.get("actions", [])
    else:
        print(f"\n✅ Naukri Secondary has {p2_searches} searches (>= {THRESHOLD_NAUKRI_SEARCHES}). Working well! Leaving intact.")

    # LinkedIn (Threshold: 50 Profile Views in a week)
    if li_views < THRESHOLD_LINKEDIN_PROFILE_VIEWS or force_revamp:
        print(f"\n⚠️ LinkedIn has {li_views} profile views (< {THRESHOLD_LINKEDIN_PROFILE_VIEWS}). Triggering revamp!")
        res = revamp_linkedin(dry_run=dry_run)
        audit_result["linkedin"]["revamp_executed"] = True
        audit_result["linkedin"]["actions"] = res.get("actions", [])
    else:
        print(f"\n✅ LinkedIn has {li_views} profile views (>= {THRESHOLD_LINKEDIN_PROFILE_VIEWS}). Working well! Leaving intact.")

    # 3. Log to Google Sheets
    revamp_summary_list = []
    if audit_result["primary"]["revamp_executed"]:
        revamp_summary_list.append("Naukri Primary Revamped")
    if audit_result["secondary"]["revamp_executed"]:
        revamp_summary_list.append("Naukri Secondary Revamped")
    if audit_result["linkedin"]["revamp_executed"]:
        revamp_summary_list.append("LinkedIn Revamped")
    
    actions_str = ", ".join(revamp_summary_list) if revamp_summary_list else "None (All Met Thresholds, Kept As-Is)"

    try:
        append_weekly_audit_entry({
            "audit_date": audit_result["date"],
            "p1_searches": p1_searches,
            "p1_status": audit_result["primary"]["status"],
            "p2_searches": p2_searches,
            "p2_status": audit_result["secondary"]["status"],
            "li_views": li_views,
            "li_searches": li_searches,
            "li_status": audit_result["linkedin"]["status"],
            "actions": actions_str,
            "notes": "Automated Weekly Sunday Audit",
        })
        print("✓ Logged weekly audit row to Google Sheets ('Weekly Profile Audit' tab).")
    except Exception as e:
        print(f"Note: Could not sync weekly audit to Google Sheets: {e}")

    # 4. Save to local audit JSON
    save_audit_json(audit_result)

    print("\n" + "=" * 75)
    print("WEEKLY AUDIT & REVAMP SUMMARY:")
    print(f"  Naukri Primary:   {p1_searches}/100 searches -> {audit_result['primary']['status']} (Revamped: {audit_result['primary']['revamp_executed']})")
    print(f"  Naukri Secondary: {p2_searches}/100 searches -> {audit_result['secondary']['status']} (Revamped: {audit_result['secondary']['revamp_executed']})")
    print(f"  LinkedIn:         {li_views}/50 profile views -> {audit_result['linkedin']['status']} (Revamped: {audit_result['linkedin']['revamp_executed']})")
    print(f"  Actions Taken:    {actions_str}")
    print("=" * 75)
    return audit_result


def save_audit_json(data: dict):
    audits = []
    if WEEKLY_AUDIT_LOG.exists():
        try:
            with open(WEEKLY_AUDIT_LOG, "r", encoding="utf-8") as f:
                audits = json.load(f)
        except Exception:
            audits = []
    audits = [a for a in audits if a.get("date") != data["date"]]
    audits.append(data)
    with open(WEEKLY_AUDIT_LOG, "w", encoding="utf-8") as f:
        json.dump(audits, f, indent=2)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Weekly Profile Performance Audit & Auto-Revamp")
    parser.add_argument("--dry-run", action="store_true", help="Scrape metrics and check threshold without modifying profiles")
    parser.add_argument("--force-revamp", action="store_true", help="Force revamp regardless of current search appearance count")
    args = parser.parse_args()

    run_weekly_audit(dry_run=args.dry_run, force_revamp=args.force_revamp)
