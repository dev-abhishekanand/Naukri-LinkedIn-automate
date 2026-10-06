"""Read the Master Resume DOCX into structured, deterministic text."""

from pathlib import Path

from docx import Document


def load_resume_text(path: str = "Abhishek_Anand_Resume.docx") -> str:
    """Return all non-empty resume paragraphs as normalized plain text."""
    resume_path = Path(path)

    if not resume_path.exists():
        raise FileNotFoundError(
            f"Resume not found at {resume_path}. "
            "Check profile.yaml resume_file_name."
        )

    document = Document(resume_path)

    paragraphs = [
        paragraph.text.strip()
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]

    if not paragraphs:
        raise ValueError(f"Resume contains no readable paragraphs: {resume_path}")

    return "\n".join(paragraphs)


def load_resume_sections(path: str = "Abhishek_Anand_Resume.docx") -> dict[str, str]:
    """Return the resume grouped by its existing section headings."""
    text = load_resume_text(path)
    lines = text.splitlines()

    headings = {
        "PROFESSIONAL SUMMARY",
        "TECHNICAL SKILLS",
        "PROFESSIONAL EXPERIENCE",
        "EDUCATION",
    }

    sections: dict[str, list[str]] = {}
    current = "HEADER"

    for line in lines:
        if line in headings:
            current = line
            sections.setdefault(current, [])
            continue

        sections.setdefault(current, []).append(line)

    return {
        section: "\n".join(content).strip()
        for section, content in sections.items()
        if content
    }
