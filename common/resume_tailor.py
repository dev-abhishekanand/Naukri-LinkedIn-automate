"""Generate a conservative ATS-tailored resume from the Master Resume."""

from pathlib import Path

from docx import Document

from .ats_tailoring import select_tailoring_evidence


def _keyword_matches_skill(keyword: str, skill: str) -> bool:
    """Return whether a JD keyword matches an existing resume skill."""
    keyword = keyword.lower().strip()
    skill = skill.lower().strip()

    aliases = {
        "react": ("react", "react.js", "reactjs"),
        "next.js": ("next.js", "nextjs"),
        "typescript": ("typescript", "type script"),
        "javascript": ("javascript", "ecmascript"),
        "redux": ("redux", "redux toolkit", "redux-toolkit"),
        "tanstack query": ("tanstack query", "react query"),
        "rest api": ("rest api", "rest apis", "restful api"),
        "graphql": ("graphql",),
        "websockets": ("websocket", "websockets"),
        "jest": ("jest",),
        "react testing library": ("react testing library",),
        "tailwind css": ("tailwind css", "tailwind"),
        "material ui": ("material ui", "mui"),
    }

    terms = aliases.get(keyword, (keyword,))
    return any(term in skill for term in terms)


def _reorder_skills(skills_text: str, keywords: list[str]) -> str:
    """Prioritize existing skills that match supported JD keywords."""
    lines = [
        line.strip()
        for line in skills_text.splitlines()
        if line.strip()
    ]

    ordered_lines = []

    for line in lines:
        if ":" not in line:
            ordered_lines.append(line)
            continue

        category, values = line.split(":", 1)
        skills = [item.strip() for item in values.split(",") if item.strip()]

        prioritized = [
            skill
            for keyword in keywords
            for skill in skills
            if _keyword_matches_skill(keyword, skill)
        ]

        prioritized = list(dict.fromkeys(prioritized))
        remaining = [skill for skill in skills if skill not in prioritized]

        ordered_lines.append(
            f"{category.strip()}: {', '.join(prioritized + remaining)}"
        )

    return "\n".join(ordered_lines)


def generate_tailored_resume(
    keywords: list[str],
    source_path: str = "Abhishek_Anand_Resume.docx",
    output_path: str = "generated/Abhishek_Anand_Tailored_Resume.docx",
) -> str:
    """
    Generate an ATS-tailored DOCX without adding unsupported claims.

    Only existing Master Resume skills are reordered. All other resume
    content remains unchanged.
    """
    source = Path(source_path)
    output = Path(output_path)

    if not source.exists():
        raise FileNotFoundError(f"Master Resume not found: {source}")

    output.parent.mkdir(parents=True, exist_ok=True)

    document = Document(source)

    matches = select_tailoring_evidence(keywords, str(source))
    supported_keywords = [
        item["keyword"]
        for item in matches["supported"]
    ]

    headings = {
        "PROFESSIONAL SUMMARY",
        "TECHNICAL SKILLS",
        "PROFESSIONAL EXPERIENCE",
        "EDUCATION",
    }

    in_skills = False

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()

        if text == "TECHNICAL SKILLS":
            in_skills = True
            continue

        if text in headings and text != "TECHNICAL SKILLS":
            in_skills = False
            continue

        if in_skills and ":" in text:
            paragraph.text = _reorder_skills(
                text,
                supported_keywords,
            )

    document.save(output)

    return str(output)
