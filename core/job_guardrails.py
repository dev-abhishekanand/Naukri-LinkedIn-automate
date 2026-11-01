"""
Smart Job Guardrails & Ghost Listing Filtration Engine
Filters out ghost jobs, stale postings (>14 days), low-quality staffing agencies,
and misaligned titles before wasting rate limits or submitting applications.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Tuple, List, Optional

from common.profile import Profile

# Default staffing agency signatures often collecting resumes without live mandates
DEFAULT_BLACKLIST_COMPANIES = [
    "cybercoders",
    "robert half",
    "teksystems",
    "apex systems",
    "kforce",
    "jobot",
    "collabera",
    "compunnel",
    "pyramid consulting"
]

DEFAULT_BLACKLIST_KEYWORDS = [
    "internship",
    "unpaid",
    "freshers only",
    "entry level only",
    "0-1 years",
    "0 to 1 year",
    "junior only",
    "contract to hire w2 only",
    "us citizenship required",
    "security clearance required",
    "full stack java developer",
    "embedded c++"
]

def parse_relative_age_days(date_str: str) -> Optional[int]:
    """Parses relative age strings like '3 days ago', '2 weeks ago', '1 month ago' into integer days."""
    if not date_str:
        return None
    d_low = date_str.lower().strip()
    if "hour" in d_low or "minute" in d_low or "today" in d_low or "just now" in d_low:
        return 0
    if "yesterday" in d_low:
        return 1

    day_m = re.search(r"(\d+)\s+day", d_low)
    if day_m:
        return int(day_m.group(1))

    week_m = re.search(r"(\d+)\s+week", d_low)
    if week_m:
        return int(week_m.group(1)) * 7

    month_m = re.search(r"(\d+)\s+month", d_low)
    if month_m:
        return int(month_m.group(1)) * 30

    return None

class JobGuardrails:
    def __init__(self, profile: Optional[Profile] = None):
        self.profile = profile or Profile.load()
        cfg = self.profile.data.get("job_guardrails", {})
        self.max_age_days = cfg.get("max_age_days", 14)
        self.min_ctc_lpa = cfg.get("min_ctc_lpa", 8.0)
        self.blacklisted_companies = set([
            c.lower().strip() for c in (cfg.get("blacklisted_companies") or DEFAULT_BLACKLIST_COMPANIES)
        ])
        self.blacklisted_keywords = [
            k.lower().strip() for k in (cfg.get("blacklisted_keywords") or DEFAULT_BLACKLIST_KEYWORDS)
        ]

    def evaluate(
        self,
        title: str = "",
        company: str = "",
        description: str = "",
        date_posted_str: str = ""
    ) -> Tuple[bool, str]:
        """
        Evaluates a job listing against candidate guardrails.
        Returns (is_eligible, reason).
        """
        t_low = title.lower()
        c_low = company.lower()
        d_low = description.lower()

        # 1. Company Blacklist Check
        for bc in self.blacklisted_companies:
            if bc in c_low:
                return False, f"Blacklisted staffing company: '{company}'"

        # 2. Blacklisted Keywords in Title or Description
        for bk in self.blacklisted_keywords:
            if bk in t_low:
                return False, f"Title contains excluded keyword: '{bk}'"
            if len(d_low) > 0 and bk in d_low[:500]:
                return False, f"Description header contains excluded keyword: '{bk}'"

        # 3. Stale / Ghost Job Check (> 14 days)
        age_days = parse_relative_age_days(date_posted_str)
        if age_days is not None and age_days > self.max_age_days:
            return False, f"Stale listing: Posted {age_days} days ago (exceeds {self.max_age_days} day limit)"

        # 4. Lowball Salary Check
        # e.g. "3-5 LPA", "400000 - 500000"
        ctc_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?)", d_low)
        if ctc_match:
            max_offered = float(ctc_match.group(2))
            if max_offered < self.min_ctc_lpa:
                return False, f"Lowball compensation: Max offered {max_offered} LPA (below {self.min_ctc_lpa} LPA minimum)"

        # 5. Non-Frontend Role Filter
        # Must contain at least one frontend identifier
        if not any(kw in t_low for kw in ["frontend", "front end", "react", "next", "ui", "web developer", "javascript", "typescript", "software engineer"]):
            return False, f"Irrelevant job title: '{title}'"

        return True, "Eligible"
