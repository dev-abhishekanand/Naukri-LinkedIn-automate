"""
Application Tracking System
Tracks applied jobs, external ATS redirects, and processed job IDs across all portals
to avoid duplicate work and maintain a transparent record of all actions.
"""
import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

APPLICATIONS_LOG = Path("applications_log.csv")
EXTERNAL_LOG = Path("external_jobs.csv")
PROCESSED_LOG = Path("processed_jobs.csv")


class ApplicationTracker:
    def __init__(self):
        self._init_files()

    def _init_files(self):
        if not APPLICATIONS_LOG.exists() or APPLICATIONS_LOG.stat().st_size == 0:
            with APPLICATIONS_LOG.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp",
                    "platform",
                    "job_id",
                    "title",
                    "company",
                    "status",
                    "url",
                    "reason"
                ])

        if not EXTERNAL_LOG.exists() or EXTERNAL_LOG.stat().st_size == 0:
            with EXTERNAL_LOG.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "discovered_at",
                    "platform",
                    "job_id",
                    "title",
                    "company",
                    "location",
                    "job_url",
                    "status",
                    "notes"
                ])

        if not PROCESSED_LOG.exists() or PROCESSED_LOG.stat().st_size == 0:
            with PROCESSED_LOG.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "job_id",
                    "platform",
                    "title",
                    "company",
                    "status",
                    "processed_at",
                    "job_url"
                ])

    def load_processed_ids(self) -> set[str]:
        if not PROCESSED_LOG.exists():
            return set()
        with PROCESSED_LOG.open(newline="") as f:
            reader = csv.DictReader(f)
            return {
                row.get("job_id", "").strip()
                for row in reader
                if row.get("job_id", "").strip()
            }

    def is_already_processed(self, job_id: str) -> bool:
        if not job_id:
            return False
        return job_id.strip() in self.load_processed_ids()

    def is_applied(self, platform: str, job_id: str) -> bool:
        return self.is_already_processed(job_id)

    def record_application(self, portal: str, job_id: str, title: str, company: str, url: str, status: str = "APPLIED", metadata: Optional[dict] = None):
        self.log_application(portal, job_id, title, company, status, url)

    def record_processed(self, platform: str, job_id: str, title: str, company: str, status: str, url: str):
        if not job_id:
            return
        with PROCESSED_LOG.open("a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                job_id.strip(),
                platform,
                title,
                company,
                status,
                datetime.now().isoformat(),
                url
            ])

    def log_application(
        self,
        platform: str,
        job_id: str,
        title: str,
        company: str,
        status: str,
        url: str,
        reason: str = ""
    ):
        with APPLICATIONS_LOG.open("a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().isoformat(),
                platform,
                job_id,
                title,
                company,
                status,
                url,
                reason
            ])
        self.record_processed(platform, job_id, title, company, status, url)

    def log_external(
        self,
        platform: str,
        job_id: str,
        title: str,
        company: str,
        location: str,
        url: str,
        notes: str = "External company application - requires manual or ATS workflow"
    ):
        with EXTERNAL_LOG.open("a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().isoformat(),
                platform,
                job_id,
                title,
                company,
                location,
                url,
                "PENDING_MANUAL",
                notes
            ])
        self.record_processed(platform, job_id, title, company, "EXTERNAL", url)

    def get_summary(self) -> dict:
        total_processed = 0
        status_counts = {}
        platform_counts = {}

        if PROCESSED_LOG.exists():
            with PROCESSED_LOG.open(newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    total_processed += 1
                    st = row.get("status", "UNKNOWN")
                    pl = row.get("platform", "UNKNOWN")
                    status_counts[st] = status_counts.get(st, 0) + 1
                    platform_counts[pl] = platform_counts.get(pl, 0) + 1

        return {
            "total_processed": total_processed,
            "status_counts": status_counts,
            "platform_counts": platform_counts,
        }
