"""Match JD keywords against evidence from the Master Resume."""

from .resume_evidence import extract_experience_evidence, extract_skill_categories


def _normalized(value: str) -> str:
    """Normalize text for case-insensitive evidence matching."""
    return " ".join(value.lower().split())


def _build_evidence(resume_path: str) -> tuple[list[str], list[dict[str, str]]]:
    """Load resume skills and experience evidence."""
    skills = extract_skill_categories(resume_path)
    experience = extract_experience_evidence(resume_path)
    return (
        [
            item
            for values in skills.values()
            for item in values
        ],
        experience,
    )


def _find_exact_evidence(
    keyword: str,
    skill_items: list[str],
    experience: list[dict[str, str]],
) -> list[str]:
    """Return resume evidence containing the requested keyword."""
    keyword_normalized = _normalized(keyword)
    matches = []

    for item in skill_items:
        if keyword_normalized in _normalized(item):
            matches.append(item)

    for item in experience:
        if keyword_normalized in _normalized(item["text"]):
            matches.append(item["text"])

    return matches


def match_keyword(
    keyword: str,
    resume_path: str = "Abhishek_Anand_Resume.docx",
) -> dict[str, object]:
    """
    Classify one JD keyword against Master Resume evidence.

    SUPPORTED: clear evidence exists.
    PARTIAL: related resume evidence exists but the exact keyword is not established.
    UNSUPPORTED: no relevant resume evidence found.
    """
    skill_items, experience = _build_evidence(resume_path)
    exact_matches = _find_exact_evidence(keyword, skill_items, experience)

    if exact_matches:
        return {
            "keyword": keyword,
            "status": "SUPPORTED",
            "evidence": exact_matches,
        }

    keyword_normalized = _normalized(keyword)

    partial_groups = {
        "react": ("next.js",),
        "javascript": ("typescript",),
        "rest api": ("graphql",),
        "websockets": ("socket.io",),
        "html5": ("css3",),
        "css3": ("html5",),
    }

    related_keywords = partial_groups.get(keyword_normalized, ())
    related_evidence = []

    for related in related_keywords:
        related_matches = _find_exact_evidence(
            related,
            skill_items,
            experience,
        )
        related_evidence.extend(related_matches)

    if related_evidence:
        return {
            "keyword": keyword,
            "status": "PARTIAL",
            "evidence": related_evidence,
        }

    return {
        "keyword": keyword,
        "status": "UNSUPPORTED",
        "evidence": [],
    }


def match_keywords(
    keywords: list[str],
    resume_path: str = "Abhishek_Anand_Resume.docx",
) -> list[dict[str, object]]:
    """Classify each JD keyword and return supporting resume evidence."""
    return [
        match_keyword(keyword, resume_path)
        for keyword in keywords
    ]
