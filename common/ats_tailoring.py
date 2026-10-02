"""Select safe Master Resume evidence for ATS-focused tailoring."""

from .ats_matcher import match_keywords


def select_tailoring_evidence(
    keywords: list[str],
    resume_path: str = "Abhishek_Anand_Resume.docx",
) -> dict[str, list[dict[str, object]]]:
    """
    Group JD keywords by safe tailoring status.

    SUPPORTED evidence may be emphasized.
    PARTIAL evidence may be reviewed manually before use.
    UNSUPPORTED keywords must not be added to the resume.
    """
    matches = match_keywords(keywords, resume_path)

    return {
        "supported": [
            result
            for result in matches
            if result["status"] == "SUPPORTED"
        ],
        "partial": [
            result
            for result in matches
            if result["status"] == "PARTIAL"
        ],
        "unsupported": [
            result
            for result in matches
            if result["status"] == "UNSUPPORTED"
        ],
    }


def tailoring_summary(
    keywords: list[str],
    resume_path: str = "Abhishek_Anand_Resume.docx",
) -> dict[str, object]:
    """Return a compact, deterministic tailoring decision summary."""
    grouped = select_tailoring_evidence(keywords, resume_path)

    return {
        "keywords": keywords,
        "supported_count": len(grouped["supported"]),
        "partial_count": len(grouped["partial"]),
        "unsupported_count": len(grouped["unsupported"]),
        "supported_keywords": [
            item["keyword"] for item in grouped["supported"]
        ],
        "partial_keywords": [
            item["keyword"] for item in grouped["partial"]
        ],
        "unsupported_keywords": [
            item["keyword"] for item in grouped["unsupported"]
        ],
    }
