"""Build deterministic ATS evidence from the Master Resume."""

from .resume_parser import load_resume_sections


def extract_skill_categories(resume_path: str = "Abhishek_Anand_Resume.docx") -> dict[str, list[str]]:
    """Parse the Technical Skills section while preserving its categories."""
    sections = load_resume_sections(resume_path)
    skills_text = sections.get("TECHNICAL SKILLS", "")

    categories: dict[str, list[str]] = {}

    for line in skills_text.splitlines():
        if ":" not in line:
            continue

        category, values = line.split(":", 1)
        category = category.strip()
        items = [item.strip() for item in values.split(",") if item.strip()]

        if category and items:
            categories[category] = items

    return categories


def extract_experience_evidence(
    resume_path: str = "Abhishek_Anand_Resume.docx",
) -> list[dict[str, str]]:
    """Extract role/project/technology/bullet evidence from the experience section."""
    sections = load_resume_sections(resume_path)
    lines = [
        line.strip()
        for line in sections.get("PROFESSIONAL EXPERIENCE", "").splitlines()
        if line.strip()
    ]

    evidence: list[dict[str, str]] = []
    current_context = ""
    current_type = ""

    for line in lines:
        if line.startswith("Tech:"):
            evidence.append({
                "type": "technology",
                "context": current_context,
                "text": line[5:].strip(),
            })
        elif line.startswith(("Owned ", "Built ", "Integrated ", "Improved ",
                              "Implemented ", "Replaced ", "Delivered ",
                              "Reduced ", "Mentored ", "Added ")):
            evidence.append({
                "type": "achievement",
                "context": current_context,
                "text": line,
            })
        elif " — " in line:
            current_context = line
            current_type = "project"
            evidence.append({
                "type": current_type,
                "context": current_context,
                "text": line,
            })
        elif " | " in line and any(
            marker in line for marker in ("Software Engineer", "Frontend Developer")
        ):
            current_context = line
            current_type = "role"
            evidence.append({
                "type": current_type,
                "context": current_context,
                "text": line,
            })
        else:
            evidence.append({
                "type": "other",
                "context": current_context,
                "text": line,
            })

    return evidence
