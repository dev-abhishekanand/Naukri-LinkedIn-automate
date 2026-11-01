"""
Portal Registry and URL Dispatcher
Maps portal identifiers and job URL domains to their respective portal applicant classes.
"""
import urllib.parse
from typing import Type, Optional
from core.base_portal import BaseJobPortal
from portals.instahyre import InstahyreApplicant
from portals.cutshort import CutshortApplicant
from portals.wellfound import WellfoundApplicant
from portals.hirist import HiristApplicant
from portals.indeed import IndeedApplicant
from core.universal_applicant import UniversalATSApplicant

PORTAL_MAP: dict[str, Type[BaseJobPortal]] = {
    "instahyre": InstahyreApplicant,
    "cutshort": CutshortApplicant,
    "wellfound": WellfoundApplicant,
    "hirist": HiristApplicant,
    "indeed": IndeedApplicant,
    "ats": UniversalATSApplicant,
    "universal": UniversalATSApplicant,
}

DOMAIN_MAP: dict[str, str] = {
    "indeed.com": "indeed",
    "in.indeed.com": "indeed",
    "www.indeed.com": "indeed",
    "secure.indeed.com": "indeed",
    "instahyre.com": "instahyre",
    "www.instahyre.com": "instahyre",
    "cutshort.io": "cutshort",
    "www.cutshort.io": "cutshort",
    "wellfound.com": "wellfound",
    "www.wellfound.com": "wellfound",
    "hirist.tech": "hirist",
    "www.hirist.tech": "hirist",
    "hirist.com": "hirist",
    "www.hirist.com": "hirist",
    "greenhouse.io": "ats",
    "boards.greenhouse.io": "ats",
    "job-boards.greenhouse.io": "ats",
    "jobs.lever.co": "ats",
    "lever.co": "ats",
    "myworkdayjobs.com": "ats",
    "workday.com": "ats",
    "ashbyhq.com": "ats",
    "jobs.ashbyhq.com": "ats",
    "smartrecruiters.com": "ats",
    "jobs.smartrecruiters.com": "ats",
    "naukri.com": "naukri",
    "linkedin.com": "linkedin",
    "wellfound.com": "wellfound",
}


def get_portal_class_by_name(portal_name: str) -> Optional[Type[BaseJobPortal]]:
    return PORTAL_MAP.get(portal_name.lower().strip())


def detect_portal_from_url(url: str) -> Optional[str]:
    parsed = urllib.parse.urlparse(url)
    netloc = parsed.netloc.lower()
    for domain, portal in DOMAIN_MAP.items():
        if domain in netloc:
            return portal
    # If it's a valid web URL, fallback to universal ats handler
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return "ats"
    return None


def get_portal_class_by_url(url: str) -> Optional[Type[BaseJobPortal]]:
    portal_name = detect_portal_from_url(url)
    if portal_name:
        return get_portal_class_by_name(portal_name)
    return UniversalATSApplicant


def register_portal(name: str, domains: list[str], portal_cls: Type[BaseJobPortal]):
    """Registers a new portal class dynamically."""
    PORTAL_MAP[name.lower()] = portal_cls
    for d in domains:
        DOMAIN_MAP[d.lower()] = name.lower()

