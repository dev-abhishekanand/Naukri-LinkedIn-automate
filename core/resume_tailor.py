"""
Resume Tailor Bridge Module
Routes calls to the unified core/ats_engine.py.
"""
from typing import Dict, Any, Optional
from core.ats_engine import tailor_resume, get_ats_engine


def tailor_resume_for_job(
    company: str,
    job_title: str,
    job_description: str = ""
) -> Dict[str, Any]:
    """Bridges legacy tailor_resume_for_job calls to unified ATSEngine."""
    res = tailor_resume(
        job_description=job_description,
        company=company,
        job_title=job_title
    )
    return {
        "tailored_docx": res.get("tailored_docx_path"),
        "tailored_pdf": res.get("pdf_path"),
        "role_summary": f"{job_title} at {company}",
        "top_skills": res.get("keywords", [])[:8],
        "ats_score": res.get("ats_score", 90.0)
    }
