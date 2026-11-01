#!/usr/bin/env python3
"""
Instant Job Alert Monitor for macOS.
Continuously or periodically checks for newly posted Indian Frontend & React developer jobs.
Triggers native macOS desktop banner notifications with sound when fresh roles appear.
"""
import sys
import os
import re
import html
import json
import time
import subprocess
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))
from location_filter import is_india_job

STATE_FILE = PROJECT_DIR / ".job_alerts_seen.json"
LOG_CSV = PROJECT_DIR / "job_alerts_log.csv"

# High-priority search streams targeting Abhishek Anand's core stack
SEARCH_TARGETS = [
    {
        "role": "React Developer",
        "keywords": '"React Developer" OR "React.js Developer"',
        "location": "India",
        "geoId": "102713980"
    },
    {
        "role": "Next.js & TypeScript",
        "keywords": '("Next.js" OR "TypeScript") AND "Frontend Developer"',
        "location": "India",
        "geoId": "102713980"
    },
    {
        "role": "Frontend Engineer",
        "keywords": '"Frontend Engineer" OR "UI Engineer"',
        "location": "India",
        "geoId": "102713980"
    }
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}


def load_seen_cache() -> set:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return set(data)
        except Exception:
            return set()
    return set()


def save_seen_cache(seen: set):
    try:
        # Keep latest 2,000 IDs to avoid indefinite cache growth
        lst = list(seen)[-2000:]
        with open(STATE_FILE, "w") as f:
            json.dump(lst, f)
    except Exception as e:
        print(f"Error saving seen cache: {e}")


def notify_mac(title: str, subtitle: str, message: str, sound: str = "Glass"):
    """Triggers an instant macOS notification banner."""
    # Sanitize inputs to prevent AppleScript injection
    def clean(s):
        return s.replace('"', "'").replace('\\', '/').strip()

    t = clean(title)
    sub = clean(subtitle)
    msg = clean(message)
    
    script = f'display notification "{msg}" with title "{t}" subtitle "{sub}" sound name "{sound}"'
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
    except Exception as e:
        print(f"Notification error: {e}")


def log_job(job: dict):
    new_file = not LOG_CSV.exists()
    try:
        with open(LOG_CSV, "a", encoding="utf-8") as f:
            if new_file:
                f.write("timestamp,title,company,location,time_posted,url\n")
            # Escape quotes
            def esc(s):
                return f'"{s.replace(chr(34), chr(34)*2)}"'
            row = [
                datetime.now().isoformat(),
                esc(job.get("title", "")),
                esc(job.get("company", "")),
                esc(job.get("location", "")),
                esc(job.get("time_posted", "")),
                esc(job.get("link", ""))
            ]
            f.write(",".join(row) + "\n")
    except Exception as e:
        print(f"Error logging job: {e}")


def fetch_jobs_for_query(keywords: str, location: str, geo_id: str) -> list:
    kw_encoded = urllib.parse.quote(keywords)
    loc_encoded = urllib.parse.quote(location)
    # Sort by Most Recent (DD) within past 24 hours (r86400)
    url = (
        f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
        f"keywords={kw_encoded}&location={loc_encoded}&geoId={geo_id}&sortBy=DD&f_TPR=r86400&start=0"
    )
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            content = resp.read().decode("utf-8")
    except Exception as e:
        print(f"  Fetch error for '{keywords}': {e}")
        return []

    cards = content.split("<li")
    jobs = []
    for item in cards[1:]:
        title_m = re.search(r"base-search-card__title[^>]*>([^<]+)<", item)
        comp_m = re.search(r"base-search-card__subtitle[^>]*>[\s\n]*<a[^>]*>([^<]+)<", item) or re.search(r"base-search-card__subtitle[^>]*>([^<]+)<", item)
        loc_m = re.search(r"job-search-card__location[^>]*>([^<]+)<", item)
        time_m = re.search(r"<time[^>]*datetime=\"[^\"]*\"[^>]*>[\s\n]*([^<]+)<", item) or re.search(r"<time[^>]*>[\s\n]*([^<]+)<", item)
        link_m = re.search(r"base-card__full-link[^>]*href=\"([^\"]+)\"", item) or re.search(r"href=\"(https://[a-z]+\.linkedin\.com/jobs/view/[^\"]+)\"", item)

        title = html.unescape(title_m.group(1).strip()) if title_m else ""
        comp = html.unescape(comp_m.group(1).strip()) if comp_m else ""
        loc = html.unescape(loc_m.group(1).strip()) if loc_m else ""
        t_posted = html.unescape(time_m.group(1).strip()) if time_m else ""
        link = link_m.group(1).split("?")[0] if link_m else ""

        job_id_m = re.search(r"view/(\d+)", link)
        job_id = job_id_m.group(1) if job_id_m else link

        if title and comp and link:
            # India location validation
            if is_india_job(location=loc, title=title, company=comp):
                jobs.append({
                    "job_id": job_id,
                    "title": title,
                    "company": comp,
                    "location": loc,
                    "time_posted": t_posted,
                    "link": link
                })
    return jobs


def run_check_cycle(seen_cache: set, is_initial: bool = False) -> tuple:
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking live job postings across India...")
    new_jobs_found = []
    
    for target in SEARCH_TARGETS:
        jobs = fetch_jobs_for_query(target["keywords"], target["location"], target["geoId"])
        for j in jobs:
            jid = j["job_id"]
            if jid not in seen_cache:
                seen_cache.add(jid)
                new_jobs_found.append(j)
        time.sleep(1) # respectful interval between queries

    if is_initial:
        print(f"Initial baseline recorded: {len(seen_cache)} existing jobs cached.")
        # Trigger single startup confirmation notification
        notify_mac(
            "🚀 Job Alert Monitor Active",
            f"Monitoring India Tech Hubs",
            f"Watching for fresh React & Frontend openings...",
            sound="Pop"
        )
        return seen_cache, 0

    print(f"Check complete. {len(new_jobs_found)} newly published jobs detected.")
    
    # Notify for each newly published job (up to 3 per cycle to prevent notification flooding)
    for job in new_jobs_found[:3]:
        title = f"🚀 New: {job['company'][:25]}"
        subtitle = job['title'][:40]
        msg = f"📍 {job['location'][:30]} ({job['time_posted']})"
        print(f"ALERT: {subtitle} @ {job['company']} ({job['time_posted']})")
        notify_mac(title, subtitle, msg, sound="Glass")
        log_job(job)
        time.sleep(1.5)

    if len(new_jobs_found) > 3:
        # Batch summary for remaining jobs
        notify_mac(
            "🚀 Multiple New Openings!",
            f"+{len(new_jobs_found) - 3} more new React jobs posted",
            "Check job_alerts_log.csv for direct links.",
            sound="Submarine"
        )
        for job in new_jobs_found[3:]:
            log_job(job)

    return seen_cache, len(new_jobs_found)


def main():
    seen_cache = load_seen_cache()
    is_initial = len(seen_cache) == 0

    # If --daemon flag is passed, run continuously every N seconds
    if "--daemon" in sys.argv:
        interval = 900 # default 15 minutes
        for arg in sys.argv:
            if arg.startswith("--interval="):
                try:
                    interval = int(arg.split("=")[1])
                except ValueError:
                    pass
        print(f"Starting Job Alert Monitor Daemon (Interval: {interval} seconds)...")
        seen_cache, _ = run_check_cycle(seen_cache, is_initial=is_initial)
        save_seen_cache(seen_cache)
        
        while True:
            time.sleep(interval)
            try:
                seen_cache, _ = run_check_cycle(seen_cache, is_initial=False)
                save_seen_cache(seen_cache)
            except Exception as e:
                print(f"Error during check cycle: {e}")
    else:
        # Single-run mode (used by launchd periodic trigger)
        seen_cache, new_count = run_check_cycle(seen_cache, is_initial=is_initial)
        save_seen_cache(seen_cache)


if __name__ == "__main__":
    main()
