"""
Unified Job Portal Auto-Apply CLI
Apply to jobs on your behalf across multiple platforms (Indeed, Instahyre, etc.)
using your configured profile, smart screening question answers, and stealth browser automation.

Commands:
    # 1. Apply to a specific job listing by its URL:
    python main.py apply --url "https://in.indeed.com/viewjob?jk=abcdef123456"

    # 2. Run automated search and apply on a portal:
    python main.py run --portal indeed --limit 5

    # 3. View status summary and recent applications:
    python main.py status

    # 4. Test screening question solver against sample questions:
    python main.py test-solver
"""
import sys
import argparse
from pathlib import Path

from common.profile import Profile
from core.tracker import ApplicationTracker
from core.question_solver import QuestionSolver
from portals.registry import get_portal_class_by_name, get_portal_class_by_url, detect_portal_from_url


def command_apply(args):
    url = args.url.strip()
    if not url:
        print("Error: Please provide a valid job URL using --url <job_url>")
        sys.exit(1)

    portal_cls = get_portal_class_by_url(url)
    if not portal_cls:
        from core.universal_applicant import UniversalATSApplicant
        portal_cls = UniversalATSApplicant

    print(f"\n[Auto-Apply] Applying via engine: {portal_cls.__name__}")
    profile = Profile.load()
    tracker = ApplicationTracker()

    headless = not args.visible
    portal_name = detect_portal_from_url(url) or "instahyre"
    session_file = f"session_{portal_name}.json"
    applicant = portal_cls(
        profile=profile,
        tracker=tracker,
        headless=headless,
        session_file=session_file
    )

    try:
        result = applicant.apply_by_url(url)
        print("\n================ Application Result ================")
        print(f"Status   : {result.get('status')}")
        print(f"Job Title: {result.get('title')}")
        print(f"Company  : {result.get('company')}")
        print(f"Job ID   : {result.get('job_id')}")
        if result.get("reason"):
            print(f"Reason   : {result.get('reason')}")
        print("===================================================\n")
    finally:
        applicant.close_session()


def command_run(args):
    portal_name = args.portal.lower().strip()
    portal_cls = get_portal_class_by_name(portal_name)
    if not portal_cls:
        print(f"Error: Unknown portal '{portal_name}'. Currently supported: instahyre, cutshort, wellfound, hirist, indeed")
        sys.exit(1)

    profile = Profile.load()
    tracker = ApplicationTracker()
    headless = not args.visible

    session_file = f"session_{portal_name}.json"
    if not Path(session_file).exists():
        print(f"\n[AUTH ERROR] No active session file '{session_file}' found!")
        print(f"Run 'python login_capture.py {portal_name}' to authenticate before running auto-apply.\n")
        sys.exit(1)

    applicant = portal_cls(
        profile=profile,
        tracker=tracker,
        headless=headless,
        session_file=session_file
    )

    roles = [args.role] if args.role else profile.data.get("target_roles", ["React Developer"])
    limit = args.limit or profile.data.get("stop_after_n_applications", 10)
    freshness = args.freshness or profile.data.get("job_freshness_days", 3)
    location = args.location or "India"

    # Battery Guardrail Check
    try:
        from common.power_manager import get_power_status
        power = get_power_status()
        if power.get("is_low_battery"):
            print(f"\n[BATTERY SAVER] 🛑 Mac is running on low battery ({power.get('battery_percent')}%).")
            print("Auto-apply paused to prevent device shutdown. Plug in AC power to resume batch apply.\n")
            sys.exit(0)
        elif power.get("should_throttle") and limit > 2:
            print(f"\n[BATTERY SAVER] ⚠️ Battery at {power.get('battery_percent')}% on Battery Power.")
            print(f"Limiting batch run from {limit} -> 2 applications to conserve battery life.\n")
            limit = 2
    except Exception:
        pass

    print(f"\n=======================================================")
    print(f"  Starting Auto-Apply Run on {portal_name.upper()}")
    print(f"  Candidate  : {profile.first_name} {profile.last_name}")
    print(f"  Target Roles: {roles}")
    print(f"  Location   : {location}")
    print(f"  Max Applies: {limit}")
    print(f"  Browser    : {'Visible' if args.visible else 'Headless'}")
    print(f"=======================================================\n")

    try:
        total_applied = 0
        if portal_name == "instahyre":
            # Instahyre presents a unified recommended opportunities feed
            role_filter = args.role if args.role else ""
            results = applicant.search_and_apply(
                role=role_filter,
                location=location,
                limit=limit,
                freshness_days=freshness
            )
            total_applied = sum(1 for r in results if r.get("status") == "APPLIED")
        else:
            for role in roles:
                if total_applied >= limit:
                    break
                remaining = limit - total_applied
                results = applicant.search_and_apply(
                    role=role,
                    location=location,
                    limit=remaining,
                    freshness_days=freshness
                )
                applied_in_role = sum(1 for r in results if r.get("status") == "APPLIED")
                total_applied += applied_in_role

        print(f"\n[Done] Run completed! Successfully applied to {total_applied} jobs.")
    except PermissionError as pe:
        print(f"\n[AUTH ERROR] {pe}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Task aborted with error: {e}")
        sys.exit(1)
    finally:
        applicant.close_session()


def command_status(args):
    tracker = ApplicationTracker()
    summary = tracker.get_summary()

    print("\n================ Application Status Summary ================")
    print(f"Total Processed Jobs: {summary['total_processed']}")
    print("\nBreakdown by Status:")
    for st, count in summary["status_counts"].items():
        print(f"  - {st:<18}: {count}")

    print("\nBreakdown by Platform:")
    for pl, count in summary["platform_counts"].items():
        print(f"  - {pl:<18}: {count}")
    print("============================================================\n")


def command_test_solver(args):
    profile = Profile.load()
    solver = QuestionSolver(profile)

    sample_questions = [
        "How many years of work experience do you have with React.js?",
        "What is your total professional experience?",
        "What is your current notice period?",
        "Are you available to join immediately?",
        "Are you legally authorized to work in India?",
        "Will you require visa sponsorship now or in the future?",
        "What is your expected salary (CTC)?",
        "Are you comfortable working in a hybrid model?",
        "Do you have experience with WordPress or Shopify?",
        "Are you willing to relocate to Bengaluru?",
        "What is your Date of Birth?",  # sensitive guard
    ]

    print("\n--- Testing Screening Question Solver ---")
    for q in sample_questions:
        if solver.is_sensitive(q):
            print(f"[Q] {q}\n    -> [GUARD TRIGGERED: Sensitive info, will never hallucinate, asks human]\n")
        else:
            ans = solver.solve(q, allow_human_input=False)
            print(f"[Q] {q}\n    -> Answer: {ans}\n")


def command_sheet_sync(args):
    from core.google_sheets_sync import fetch_sheet_jobs, update_job_status
    from core.universal_applicant import UniversalATSApplicant
    from common.profile import Profile
    from core.tracker import ApplicationTracker

    sheet_id = args.sheet_id or "15EFmeEcqtEJNqYDSYdL755534yc9RHqIsiIm7COa94I"
    tab_name = args.tab or "Apply Yourself"
    limit = args.limit or 1
    visible = args.visible

    print(f"\n=======================================================")
    print(f"  Google Sheet Auto-Apply: '{tab_name}'")
    print(f"  Spreadsheet ID: {sheet_id}")
    print(f"  Max Jobs to Process: {limit}")
    print(f"  Browser Mode: {'Visible' if visible else 'Headless'}")
    print(f"=======================================================\n")

    res = fetch_sheet_jobs(sheet_id=sheet_id, tab_name=tab_name)
    if not res.get("success"):
        print(f"Error fetching sheet: {res.get('error')}")
        return

    jobs = res.get("jobs", [])
    print(f"Fetched {len(jobs)} rows from Google Sheet.")
    print(f"Stats: {res.get('stats')}")

    profile = Profile.load()
    tracker = ApplicationTracker()
    applicant = UniversalATSApplicant(
        profile=profile,
        tracker=tracker,
        headless=not visible,
        session_file="session_universal_ats.json"
    )

    # Filter pending jobs (or match single row if specified)
    if args.row:
        pending_jobs = [j for j in jobs if j["row_index"] == args.row]
    else:
        pending_jobs = []
        for j in jobs:
            url = j.get("direct_apply_url", "").strip()
            if (
                j["status"] == "PENDING"
                and url.startswith("http")
                and not url.startswith("chrome-error")
            ):
                job_id = applicant.extract_job_id(url)
                if not tracker.is_already_processed(job_id):
                    pending_jobs.append(j)

    if getattr(args, "role", None):
        role_kw = args.role.lower().strip()
        pending_jobs = [j for j in pending_jobs if role_kw in j["job_title"].lower()]

    if not pending_jobs:
        print("No pending jobs found to process!")
        return

    if getattr(args, "all", False):
        limit = len(pending_jobs)

    if getattr(args, "random", False):
        import random
        to_process = random.sample(pending_jobs, min(limit, len(pending_jobs)))
    else:
        to_process = pending_jobs[:limit]

    print(f"Queue prepared: {len(to_process)} fresh job(s) ready.\n")

    applied_jobs = []
    unapplied_jobs = []

    try:
        for idx, job in enumerate(to_process, 1):
            url = job["direct_apply_url"]
            company = job["company"]
            title = job["job_title"]
            row_idx = job["row_index"]

            print(f"\n[{idx}/{len(to_process)}] Processing Row {row_idx}: {title} @ {company}")
            print(f"    URL: {url}")

            if not url or not url.startswith("http"):
                print("    ⚠️ Invalid URL. Skipping.")
                update_job_status(
                    direct_apply_url=url,
                    status="FAILED",
                    reason="Invalid or missing URL in sheet",
                    row_index=row_idx,
                    company=company,
                    job_title=title
                )
                unapplied_jobs.append({
                    "company": company,
                    "title": title,
                    "url": url,
                    "row_index": row_idx,
                    "status": "FAILED",
                    "reason": "Invalid or missing URL in sheet"
                })
                continue

            try:
                apply_res = applicant.apply_by_url(url, auto_tailor=True)
                final_status = apply_res.get("status", "REVIEW_REQUIRED")
                reason = apply_res.get("reason", "")
                tailored_resume = apply_res.get("tailored_resume_path", "")

                print(f"    -> Result: {final_status}")
                if reason:
                    print(f"    -> Reason: {reason}")

                update_job_status(
                    direct_apply_url=url,
                    status=final_status,
                    reason=reason,
                    row_index=row_idx,
                    company=company,
                    job_title=title,
                    tailored_resume_path=tailored_resume
                )

                if final_status in ("APPLIED", "SUCCESS"):
                    applied_jobs.append({
                        "company": company,
                        "title": title,
                        "url": url,
                        "row_index": row_idx,
                        "status": final_status
                    })
                else:
                    unapplied_jobs.append({
                        "company": company,
                        "title": title,
                        "url": url,
                        "row_index": row_idx,
                        "status": final_status,
                        "reason": reason
                    })

            except Exception as e:
                print(f"    ❌ Exception while applying: {e}")
                err_msg = f"Application error: {e}"
                update_job_status(
                    direct_apply_url=url,
                    status="REVIEW_REQUIRED",
                    reason=err_msg,
                    row_index=row_idx,
                    company=company,
                    job_title=title
                )
                unapplied_jobs.append({
                    "company": company,
                    "title": title,
                    "url": url,
                    "row_index": row_idx,
                    "status": "REVIEW_REQUIRED",
                    "reason": err_msg
                })

            # Human-like delay between applications
            if idx < len(to_process):
                from core.browser_factory import human_delay
                print("Waiting before next application...")
                human_delay(4.0, 7.0)

    finally:
        applicant.close_session()

    from datetime import datetime
    import json
    batch_outcome = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_processed": len(to_process),
        "applied_count": len(applied_jobs),
        "unapplied_count": len(unapplied_jobs),
        "applied_jobs": applied_jobs,
        "unapplied_jobs": unapplied_jobs,
        "message": f"{len(unapplied_jobs)} jobs left for apply. Just go and apply yourself!" if unapplied_jobs else "All processed jobs were successfully applied!"
    }
    outcome_file = PROJECT_DIR / "sheet_batch_outcome.json"
    try:
        with open(outcome_file, "w", encoding="utf-8") as f:
            json.dump(batch_outcome, f, indent=2)
    except Exception as e:
        print(f"Error saving batch outcome: {e}")

    print("\n" + "=" * 70)
    print("📊 GOOGLE SHEET BATCH RUN OUTCOME REPORT")
    print("=" * 70)
    print(f"✓ Total Jobs Processed: {len(to_process)}")
    print(f"✓ Successfully Applied: {len(applied_jobs)}")
    if unapplied_jobs:
        print(f"⚠️ Unapplied / Review Required: {len(unapplied_jobs)}")
        print(f"\n👉 {len(unapplied_jobs)} jobs left for apply. Just go and apply yourself!")
        print("\nDirect Links to visit and apply yourself:")
        for u_idx, u_job in enumerate(unapplied_jobs, 1):
            print(f"  [{u_idx}] {u_job['title']} @ {u_job['company']} (Row #{u_job['row_index']})")
            print(f"      🔗 {u_job['url']}")
            if u_job.get("reason"):
                print(f"      Note: {u_job['reason']}")
    else:
        print("🎉 All processed jobs were applied automatically without intervention!")
    print("=" * 70 + "\n")
    print("✅ Batch execution completed. All statuses updated in Application History.")


def main():
    parser = argparse.ArgumentParser(
        description="Unified Job Application Automation System (Indeed, Instahyre, etc.)"
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # Apply command
    apply_parser = subparsers.add_parser("apply", help="Apply to a specific job listing by its URL")
    apply_parser.add_argument("--url", required=True, help="Job listing URL")
    apply_parser.add_argument("--visible", action="store_true", help="Launch visible browser window")

    # Sheet Sync command
    sheet_parser = subparsers.add_parser("sheet-sync", help="Sync and apply to jobs from Google Sheet")
    sheet_parser.add_argument("--sheet-id", help="Google Sheet Spreadsheet ID")
    sheet_parser.add_argument("--tab", default="Apply Yourself", help="Tab name (default: Apply Yourself)")
    sheet_parser.add_argument("--limit", type=int, default=1, help="Max jobs to process (default: 1)")
    sheet_parser.add_argument("--all", action="store_true", help="Process all pending jobs in the sheet")
    sheet_parser.add_argument("--row", type=int, help="Specific row index to process")
    sheet_parser.add_argument("--role", help="Filter by job role keyword (e.g. 'React Developer')")
    sheet_parser.add_argument("--random", action="store_true", help="Sample random jobs from matching pending list")
    sheet_parser.add_argument("--visible", action="store_true", help="Launch visible browser window")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run automated search and apply on a portal")
    run_parser.add_argument("--portal", default="instahyre", help="Portal name (default: instahyre)")
    run_parser.add_argument("--role", help="Specific role to search (default: from profile.yaml)")
    run_parser.add_argument("--location", default="India", help="Location (default: India)")
    run_parser.add_argument("--limit", type=int, help="Maximum number of applications to submit")
    run_parser.add_argument("--freshness", type=int, help="Job freshness in days (e.g. 1, 3, 7)")
    run_parser.add_argument("--visible", action="store_true", help="Launch visible browser window")

    # Status command
    subparsers.add_parser("status", help="Show application history summary")

    # Test solver command
    subparsers.add_parser("test-solver", help="Test screening question solver logic")

    args = parser.parse_args()

    if args.subcommand == "apply":
        command_apply(args)
    elif args.subcommand == "sheet-sync":
        command_sheet_sync(args)
    elif args.subcommand == "run":
        command_run(args)
    elif args.subcommand == "status":
        command_status(args)
    elif args.subcommand == "test-solver":
        command_test_solver(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
