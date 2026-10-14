#!/usr/bin/env python3
"""
==============================================================================
NAUKRI PROFILE OPTIMIZATION & SYNCHRONIZATION ENGINE
==============================================================================
Reads desired profile state from `profile.yaml` and synchronizes it directly
to the live Naukri candidate portal via authenticated Playwright session.

Key Capabilities:
1. IT Skills Matrix Sync:
   - Removes legacy bundled / 0-experience skill rows
   - Adds / updates individual skills with 2026 recency and proper experience
2. Key Skills Tags Sync:
   - Populates up to 30 high-impact recruiter search tags & variants
3. Compensation Sync:
   - Sets Current Annual Salary in Basic Details
   - Sets Preferred Annual Salary in Career Profile
4. Accomplishments Sync:
   - Adds GitHub Work Sample profile under Accomplishments
5. Dry-Run Mode:
   - Inspects live profile and prints a detailed diff without modifying anything

Usage:
  python naukri_sync_profile.py               # Full sync
  python naukri_sync_profile.py --dry-run     # Audit & compare only
  python naukri_sync_profile.py --section it  # Sync only IT skills
==============================================================================
"""

import argparse
import datetime
import os
import re
import sys
import time
import yaml
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_YAML = os.path.join(BASE_DIR, "profile.yaml")
SESSION_FILE = os.path.join(BASE_DIR, "session_naukri.json")
LOG_DIR = os.path.join(BASE_DIR, "scheduler_logs")
PROFILE_URL = "https://www.naukri.com/mnjuser/profile"


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def load_config():
    if not os.path.exists(PROFILE_YAML):
        log(f"ERROR: profile.yaml not found at {PROFILE_YAML}")
        sys.exit(1)
    with open(PROFILE_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def lpa_to_rupees_str(lpa):
    if lpa is None:
        return None
    val = int(round(float(lpa) * 100000))
    return str(val)


def scroll_page(page, times=6, step=700, delay=0.3):
    for _ in range(times):
        page.mouse.wheel(0, step)
        time.sleep(delay)


def close_modal(page):
    page.keyboard.press("Escape")
    time.sleep(1)


# ----------------------------------------------------------------------
# 1. BASIC DETAILS SYNC (Current Salary)
# ----------------------------------------------------------------------
def sync_basic_details(page, config, dry_run=False):
    log("Checking Basic Details (Current CTC)...")
    target_lpa = config.get("current_ctc_lpa")
    if target_lpa is None:
        log("No current_ctc_lpa in config. Skipping Basic Details.")
        return

    target_salary_str = lpa_to_rupees_str(target_lpa)

    btn = page.locator('[aria-label="Edit basic details"]').first
    if btn.count() == 0:
        log("WARN: Edit basic details button not found.")
        return

    btn.click()
    time.sleep(2)

    ctc_inp = page.locator('#totalAbsCtc_id, input[aria-label="Current salary"]').first
    if ctc_inp.count() == 0:
        log("WARN: CTC input not found in basic details.")
        close_modal(page)
        return

    curr_val = ctc_inp.input_value().strip()
    digits_curr = re.sub(r"[^\d]", "", curr_val)
    digits_target = re.sub(r"[^\d]", "", target_salary_str)

    log(f"Current CTC in portal: '{curr_val}' ({digits_curr} raw) | Target: '{target_salary_str}' ({target_lpa} LPA)")

    if digits_curr == digits_target and digits_curr != "":
        log("✓ Current CTC already matches target.")
        close_modal(page)
        return

    if dry_run:
        log(f"[DRY-RUN] Would update Current CTC from '{curr_val}' to '{target_salary_str}'")
        close_modal(page)
        return

    ctc_inp.click()
    ctc_inp.select_text()
    page.keyboard.press("Backspace")
    ctc_inp.press_sequentially(target_salary_str, delay=50)
    page.keyboard.press("Tab")
    time.sleep(1)

    try:
        with page.expect_response(lambda r: "resman-aggregator-services" in r.url, timeout=10000):
            page.locator('#saveBasicDetailsBtn').click()
        log(f"✓ Current CTC successfully updated to ₹{target_lpa} LPA ({target_salary_str})")
    except Exception as e:
        log(f"WARN: Error waiting for save response: {e}")
        close_modal(page)

    time.sleep(2)
    close_modal(page)


# ----------------------------------------------------------------------
# 2. KEY SKILLS SYNC
# ----------------------------------------------------------------------
def sync_key_skills(page, config, dry_run=False):
    log("Checking Key Skills tags...")
    target_skills = config.get("naukri_key_skills", [])
    if not target_skills:
        log("No naukri_key_skills in config. Skipping Key Skills.")
        return

    scroll_page(page, times=3, step=500)
    key_btn = page.locator('[aria-label="Edit key skills"]').first
    if key_btn.count() == 0:
        log("WARN: Edit key skills button not found.")
        return

    key_btn.click()
    time.sleep(2)

    chips = page.locator('.chipsContainer .chip .tagTxt').all_inner_texts()
    chips_normalized = {c.strip().lower(): c.strip() for c in chips}
    log(f"Portal currently has {len(chips)} key skills: {', '.join(chips)}")

    missing = []
    for s in target_skills:
        if s.strip().lower() not in chips_normalized:
            missing.append(s.strip())

    if not missing:
        log("✓ All configured key skills are already present.")
        close_modal(page)
        return

    log(f"Identified {len(missing)} missing key skills to add: {', '.join(missing)}")

    if dry_run:
        log(f"[DRY-RUN] Would add {len(missing)} tags to Key Skills.")
        close_modal(page)
        return

    sugg_input = page.locator('#keySkillSugg')
    added_count = 0
    current_total = len(chips)

    for skill in missing:
        if current_total >= 30:
            log("Reached maximum allowed Key Skills (30 tags). Stopping tag additions.")
            break

        # Check character limit
        chips_val = page.locator('#chipsVal').get_attribute('value') or ''
        if len(chips_val) + len(skill) + 1 > 248:
            log(f"Reached 250 character limit for Key Skills ({len(chips_val)}/250 chars). Cannot add '{skill}'.")
            break

        # Check if the skill is available in suggested chips first
        sugg_btn = page.locator(f'.suggChipsCont [aria-label="Add {skill}"]').first
        if sugg_btn.count() > 0:
            try:
                sugg_btn.scroll_into_view_if_needed()
                sugg_btn.click()
                time.sleep(1)
                current_total += 1
                added_count += 1
                log(f"  + Added skill from suggested chips: {skill}")
                continue
            except Exception as e:
                log(f"  WARN clicking suggested chip for {skill}: {e}")

        # Otherwise type into suggestion input
        try:
            sugg_input.click()
            sugg_input.press_sequentially(skill, delay=80)
            time.sleep(0.8)

            sug_items = page.locator('#sugLst_keySkillSugg li')
            if sug_items.count() > 0:
                sug_items.first.evaluate("el => el.click()")
            else:
                page.keyboard.press("Enter")

            time.sleep(0.8)
            current_total += 1
            added_count += 1
            log(f"  + Added skill tag: {skill}")
        except Exception as e:
            log(f"  WARN adding skill tag '{skill}': {e}")

    if added_count > 0:
        try:
            with page.expect_response(lambda r: "resman-aggregator-services" in r.url or "keySkill" in r.url or "profile" in r.url, timeout=10000):
                page.locator('#saveKeySkills').click()
            log(f"✓ Key Skills updated! Added {added_count} new tags.")
        except Exception as e:
            log(f"WARN saving key skills: {e}")
    else:
        log("No new key skills were added.")

    time.sleep(2)
    close_modal(page)


# ----------------------------------------------------------------------
# 3. IT SKILLS SYNC
# ----------------------------------------------------------------------
def sync_it_skills(page, config, dry_run=False):
    log("Checking IT Skills Matrix...")
    target_skills = config.get("naukri_it_skills", [])
    if not target_skills:
        log("No naukri_it_skills in config. Skipping IT skills.")
        return

    scroll_page(page, times=4, step=700)

    # 1. Clean up bundled rows
    it_widget = page.locator('#lazyITSkills, .itSkills').first
    if it_widget.count() == 0:
        log("WARN: IT skills widget not found.")
        return

    existing_rows = page.evaluate("""() => {
        const rows = Array.from(document.querySelectorAll('#lazyITSkills li.collection, .itSkills li.collection'));
        return rows.map(r => {
            const spans = Array.from(r.querySelectorAll('span'));
            const editBtn = r.querySelector('[aria-label*="Edit IT skill"]');
            return {
                name: spans[0] ? spans[0].innerText.trim() : '',
                version: spans[1] ? spans[1].innerText.trim() : '',
                lastUsed: spans[2] ? spans[2].innerText.trim() : '',
                exp: spans[3] ? spans[3].innerText.trim() : '',
                ariaLabel: editBtn ? editBtn.getAttribute('aria-label') : null
            };
        });
    }""")

    log(f"Found {len(existing_rows)} existing IT skill rows on portal.")

    # Detect bundled rows: comma in name or known bundled strings
    bundled_rows = [r for r in existing_rows if ("," in r["name"] or "chart.js" in r["name"].lower() or "handsontable" in r["name"].lower()) and r["ariaLabel"]]

    if bundled_rows:
        log(f"Found {len(bundled_rows)} legacy bundled skill rows to delete:")
        for b in bundled_rows:
            log(f"  - '{b['name']}' (Exp: {b['exp']})")

        if dry_run:
            log("[DRY-RUN] Would delete bundled rows.")
        else:
            for b in bundled_rows:
                log(f"Deleting bundled row: '{b['name']}'...")
                del_btn = page.locator(f'[aria-label="{b["ariaLabel"]}"]').first
                if del_btn.count() > 0:
                    del_btn.click()
                    time.sleep(2)
                    page.locator('.lightbox.model_open span.delete').first.click()
                    time.sleep(1)
                    page.locator('.lightbox.model_open button:has-text("Delete"), .lightbox.model_open .btn-dark-ot:has-text("Delete")').first.click()
                    time.sleep(3)
                    log(f"  ✓ Deleted: {b['name']}")
                else:
                    log(f"  WARN: Delete button for '{b['name']}' not found.")

    # Re-read existing rows after deletion
    existing_map = {}
    current_table = page.evaluate("""() => {
        const rows = Array.from(document.querySelectorAll('#lazyITSkills li.collection, .itSkills li.collection'));
        return rows.map(r => {
            const spans = Array.from(r.querySelectorAll('span'));
            const editBtn = r.querySelector('[aria-label*="Edit IT skill"]');
            return {
                name: spans[0] ? spans[0].innerText.trim() : '',
                version: spans[1] ? spans[1].innerText.trim() : '',
                lastUsed: spans[2] ? spans[2].innerText.trim() : '',
                exp: spans[3] ? spans[3].innerText.trim() : '',
                ariaLabel: editBtn ? editBtn.getAttribute('aria-label') : null
            };
        });
    }""")
    for r in current_table:
        existing_map[r["name"].lower()] = r

    # Process each target skill
    for target in target_skills:
        skill_name = target["skill"]
        ver = str(target.get("version", "") or "")
        last_used = str(target.get("last_used", "2026"))
        exp_yr = int(target.get("exp_years", 3))
        exp_mo = int(target.get("exp_months", 0))
        exp_yr_str = f"{exp_yr} Year" if exp_yr == 1 else f"{exp_yr} Years"
        exp_mo_str = f"{exp_mo} Month" if exp_mo == 1 else f"{exp_mo} Months"

        existing = existing_map.get(skill_name.lower())

        if existing:
            # Check if update is needed
            needs_update = (
                existing["lastUsed"] == "-" or
                existing["lastUsed"] != last_used or
                exp_yr_str not in existing["exp"]
            )
            if not needs_update:
                log(f"✓ IT skill '{skill_name}' is up to date ({existing['exp']}, Last Used: {existing['lastUsed']}).")
                continue

            if dry_run:
                log(f"[DRY-RUN] Would update IT skill '{skill_name}': Ver={ver}, LastUsed={last_used}, Exp={exp_yr_str} {exp_mo_str}")
                continue

            log(f"Updating IT skill '{skill_name}'...")
            edit_btn = page.locator(f'[aria-label="{existing["ariaLabel"]}"]').first
            if edit_btn.count() == 0:
                continue
            edit_btn.click()
            time.sleep(2)
        else:
            if dry_run:
                log(f"[DRY-RUN] Would add new IT skill '{skill_name}': Ver={ver}, LastUsed={last_used}, Exp={exp_yr_str} {exp_mo_str}")
                continue

            log(f"Adding new IT skill '{skill_name}'...")
            add_btn = page.locator('#lazyITSkills span[aria-label="Add IT skills"], #lazyITSkills .add:has-text("Add details")').first
            if add_btn.count() == 0:
                log("WARN: Add IT skills button not found.")
                continue
            add_btn.scroll_into_view_if_needed()
            time.sleep(0.5)
            try:
                add_btn.evaluate("el => el.click()")
            except Exception:
                add_btn.click(force=True)
            time.sleep(2)

            # Fill name
            s_inp = page.locator('#itSkillSugg')
            s_inp.click()
            s_inp.press_sequentially(skill_name, delay=80)
            time.sleep(1)
            sug_item = page.locator(f'#sugLst_itSkillSugg li:has-text("{skill_name}")').first
            if sug_item.count() > 0:
                sug_item.click()
            else:
                page.keyboard.press("Enter")
            time.sleep(0.5)

        # Version
        if ver:
            v_inp = page.locator('#version')
            if v_inp.count() > 0:
                v_inp.click()
                v_inp.select_text()
                page.keyboard.press("Backspace")
                v_inp.fill(ver)
                time.sleep(0.3)

        # Last Used Year
        try:
            lu_inp = page.locator('#lastUsedDroopeFor')
            lu_inp.click()
            time.sleep(0.4)
            page.locator(f'#dp_lastUsedDroope li:has-text("{last_used}")').first.click()
            time.sleep(0.3)
        except Exception as e:
            log(f"  WARN setting last used for '{skill_name}': {e}")

        # Exp Years
        try:
            ey_inp = page.locator('#expYearDroopeFor')
            ey_inp.click()
            time.sleep(0.4)
            page.locator(f'#dp_expYearDroope li:has-text("{exp_yr_str}")').first.click()
            time.sleep(0.3)
        except Exception as e:
            log(f"  WARN setting exp years for '{skill_name}': {e}")

        # Exp Months
        try:
            em_inp = page.locator('#expMonthDroopeFor')
            em_inp.click()
            time.sleep(0.4)
            page.locator(f'#dp_expMonthDroope li:has-text("{exp_mo_str}")').first.click()
            time.sleep(0.3)
        except Exception as e:
            log(f"  WARN setting exp months for '{skill_name}': {e}")

        # Save
        page.locator('#saveITSkills').click()
        time.sleep(2.5)
        close_modal(page)
        log(f"  ✓ Saved IT skill: {skill_name}")

    log("✓ IT Skills table synchronization complete.")


# ----------------------------------------------------------------------
# 4. CAREER PROFILE SYNC (Preferred Salary)
# ----------------------------------------------------------------------
def sync_career_profile(page, config, dry_run=False):
    log("Checking Career Profile (Preferred CTC)...")
    target_lpa = config.get("expected_ctc_lpa")
    if target_lpa is None:
        log("No expected_ctc_lpa in config. Skipping Career Profile.")
        return

    target_salary_str = lpa_to_rupees_str(target_lpa)

    scroll_page(page, times=6, step=700)
    career_btn = page.locator('[aria-label="Edit career profile"]').first
    if career_btn.count() == 0:
        log("WARN: Edit career profile button not found.")
        return

    career_btn.click()
    time.sleep(2)

    pref_salary = page.locator('form[name="desiredProfileForm"] input[aria-label="Preferred annual salary"], form[name="desiredProfileForm"] input.currency-input').first
    if pref_salary.count() == 0:
        log("WARN: Preferred salary input not found.")
        close_modal(page)
        return

    curr_val = pref_salary.input_value().strip()
    digits_curr = re.sub(r"[^\d]", "", curr_val)
    digits_target = re.sub(r"[^\d]", "", target_salary_str)

    log(f"Preferred CTC in portal: '{curr_val}' ({digits_curr} raw) | Target: '{target_salary_str}' ({target_lpa} LPA)")

    if digits_curr == digits_target and digits_curr != "":
        log("✓ Preferred CTC already matches target.")
        close_modal(page)
        return

    if dry_run:
        log(f"[DRY-RUN] Would update Preferred CTC from '{curr_val}' to '{target_salary_str}'")
        close_modal(page)
        return

    pref_salary.click()
    pref_salary.select_text()
    page.keyboard.press("Backspace")
    pref_salary.press_sequentially(target_salary_str, delay=50)
    page.keyboard.press("Tab")
    time.sleep(1)

    try:
        with page.expect_response(lambda r: "resman-aggregator-services" in r.url or "desired" in r.url or "profile" in r.url, timeout=10000):
            page.locator('#saveDesiredProfile').click()
        log(f"✓ Preferred CTC successfully updated to ₹{target_lpa} LPA ({target_salary_str})")
    except Exception as e:
        log(f"WARN saving career profile: {e}")
        close_modal(page)

    time.sleep(2)
    close_modal(page)


# ----------------------------------------------------------------------
# 5. WORK SAMPLE SYNC
# ----------------------------------------------------------------------
def sync_work_sample(page, config, dry_run=False):
    log("Checking Accomplishments (Work Sample / GitHub)...")
    ws_config = config.get("naukri_work_sample")
    if not ws_config:
        log("No naukri_work_sample in config. Skipping.")
        return

    target_url = ws_config.get("url", "")
    target_title = ws_config.get("title", "")
    target_desc = ws_config.get("description", "")

    scroll_page(page, times=6, step=700)

    # Check if GitHub link already exists on page
    already_added = page.evaluate("""(url) => {
        const bodyText = document.body.innerText;
        return bodyText.includes('github.com/dev-abhishekanand') || bodyText.includes(url);
    }""", target_url)

    if already_added:
        log("✓ Work sample GitHub profile already present on Naukri.")
        return

    add_btn = page.locator('a[aria-label="Add work sample"]').first
    if add_btn.count() == 0:
        log("Work sample Add button not found (already added or different layout).")
        return

    if dry_run:
        log(f"[DRY-RUN] Would add Work Sample: '{target_title}' ({target_url})")
        return

    log(f"Adding Work Sample: {target_title}...")
    add_btn.scroll_into_view_if_needed()
    time.sleep(0.5)
    try:
        add_btn.evaluate("el => el.click()")
    except Exception:
        add_btn.click(force=True)
    time.sleep(2)

    # Fill title and url without clicking out of viewport
    t_inp = page.locator('#workSample-title_0')
    t_inp.fill(target_title, force=True)
    time.sleep(0.4)

    u_inp = page.locator('#workSample-url_0')
    u_inp.fill(target_url, force=True)
    time.sleep(0.4)

    d_inp = page.locator('#workSample-description_0')
    if d_inp.count() > 0:
        d_inp.fill(target_desc, force=True)
        time.sleep(0.4)

    curr_cb = page.locator('label[for="currentlyWorkingOn_0"], #currentlyWorkingOn_0').first
    if curr_cb.count() > 0:
        try:
            curr_cb.evaluate("el => el.click()")
        except Exception:
            curr_cb.click(force=True)
        time.sleep(0.4)

    save_btn = page.locator('#saveWorkSampleBtn')
    try:
        with page.expect_response(lambda r: "resman-aggregator-services" in r.url or "workSample" in r.url or "profile" in r.url, timeout=10000):
            save_btn.evaluate("el => el.click()")
        log("✓ Work sample successfully added!")
    except Exception as e:
        log(f"WARN saving work sample: {e}")
        close_modal(page)

    time.sleep(2)
    close_modal(page)


# ----------------------------------------------------------------------
# MAIN CONTROLLER
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Synchronize profile.yaml with Naukri Portal")
    parser.add_argument("--dry-run", action="store_true", help="Inspect profile and report diff without saving changes")
    parser.add_argument("--section", choices=["all", "salary", "key_skills", "it_skills", "work_sample"], default="all", help="Target section to sync")
    args = parser.parse_args()

    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = os.path.join(LOG_DIR, f"profile_sync_{timestamp}.log")

    log("=" * 60)
    log(f"NAUKRI PROFILE SYNC STARTED [Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}]")
    log(f"Target Section: {args.section}")
    log("=" * 60)

    config = load_config()

    if not os.path.exists(SESSION_FILE):
        log(f"ERROR: Session file not found at {SESSION_FILE}. Run login_capture.py first.")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-minimized"])
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        try:
            log(f"Navigating to {PROFILE_URL}...")
            page.goto(PROFILE_URL, wait_until="load", timeout=60000)
            time.sleep(3)

            # Check if logged in
            if "login" in page.url.lower():
                log("ERROR: Session expired. Redirected to login page.")
                sys.exit(1)

            # Execute sections according to filter
            if args.section in ["all", "salary"]:
                sync_basic_details(page, config, dry_run=args.dry_run)
                sync_career_profile(page, config, dry_run=args.dry_run)
                page.goto(PROFILE_URL, wait_until="load", timeout=60000)
                time.sleep(2)

            if args.section in ["all", "key_skills"]:
                sync_key_skills(page, config, dry_run=args.dry_run)
                page.goto(PROFILE_URL, wait_until="load", timeout=60000)
                time.sleep(2)

            if args.section in ["all", "it_skills"]:
                sync_it_skills(page, config, dry_run=args.dry_run)
                page.goto(PROFILE_URL, wait_until="load", timeout=60000)
                time.sleep(2)

            if args.section in ["all", "work_sample"]:
                sync_work_sample(page, config, dry_run=args.dry_run)

            log("=" * 60)
            log(f"PROFILE SYNC COMPLETED SUCCESSFULLY [{'DRY-RUN ONLY' if args.dry_run else 'LIVE CHANGES COMMITTED'}]")
            log("=" * 60)

        except Exception as e:
            log(f"CRITICAL ERROR during sync: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
