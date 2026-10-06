"""Orchestrate the deterministic ATS tailoring pipeline."""

from .ats_tailoring import select_tailoring_evidence
from .ats_validator import validate_tailored_resume
from .jd_keywords import extract_keywords
from .resume_tailor import generate_tailored_resume


def prepare_tailored_resume(
    job_description: str,
    master_resume_path: str = "Abhishek_Anand_Resume.docx",
    output_path: str = "generated/Abhishek_Anand_Tailored_Resume.docx",
) -> dict[str, object]:
    """
    Run the complete ATS preparation pipeline for one job description.

    Returns the extracted keywords, evidence decisions, generated resume
    path, and validation result. The resume is only considered ready for
    application when validation passes.
    """
    if not job_description.strip():
        raise ValueError("Job description cannot be empty.")

    keywords = extract_keywords(job_description)

    tailoring = select_tailoring_evidence(
        keywords,
        master_resume_path,
    )

    tailored_path = generate_tailored_resume(
        keywords,
        master_resume_path,
        output_path,
    )

    validation = validate_tailored_resume(
        keywords,
        tailored_path,
        master_resume_path,
    )

    if not validation["passed"]:
        raise ValueError(
            "Tailored resume failed ATS validation: "
            f"{validation}"
        )

    return {
        "keywords": keywords,
        "tailoring": tailoring,
        "tailored_resume_path": tailored_path,
        "validation": validation,
    }
