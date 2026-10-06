"""Validate a generated resume against JD requirements and Master Resume evidence."""

from pathlib import Path

from .ats_matcher import match_keywords
from .resume_parser import load_resume_sections, load_resume_text


REQUIRED_SECTIONS = {
    "PROFESSIONAL SUMMARY",
    "TECHNICAL SKILLS",
    "PROFESSIONAL EXPERIENCE",
    "EDUCATION",
}

PROFILE_ONLY_KEYWORDS = {
    "mongodb",
    "docker",
    "azure",
    "apollo",
    "socket.io",
}


def validate_tailored_resume(
    keywords: list[str],
    tailored_path: str,
    master_path: str = "Abhishek_Anand_Resume.docx",
) -> dict[str, object]:
    """Return deterministic validation results for a tailored resume."""
    tailored = Path(tailored_path)

    if not tailored.exists():
        raise FileNotFoundError(
            f"Tailored resume not found: {tailored}"
        )

    master_sections = load_resume_sections(master_path)
    tailored_sections = load_resume_sections(tailored_path)
    tailored_text = load_resume_text(tailored_path).lower()

    matches = match_keywords(keywords, master_path)

    supported_keywords = [
        item["keyword"]
        for item in matches
        if item["status"] == "SUPPORTED"
    ]

    missing_supported = [
        keyword
        for keyword in supported_keywords
        if keyword.lower() not in tailored_text
    ]

    missing_sections = [
        section
        for section in REQUIRED_SECTIONS
        if section not in tailored_sections
    ]

    introduced_profile_only = [
        keyword
        for keyword in PROFILE_ONLY_KEYWORDS
        if keyword in tailored_text
        and keyword not in master_sections.get("TECHNICAL SKILLS", "").lower()
        and keyword not in master_sections.get("PROFESSIONAL EXPERIENCE", "").lower()
    ]

    passed = not (
        missing_supported
        or missing_sections
        or introduced_profile_only
    )

    return {
        "passed": passed,
        "supported_keywords": supported_keywords,
        "missing_supported_keywords": missing_supported,
        "missing_sections": missing_sections,
        "introduced_profile_only_keywords": introduced_profile_only,
    }
