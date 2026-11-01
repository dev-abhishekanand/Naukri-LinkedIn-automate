"""
Post Analyzer & Eligibility Evaluator
Analyzes job posting text and flyer/screenshot images using Gemini.
Extracts job metadata, evaluates eligibility against Abhishek Anand's profile,
and generates ready-to-send application emails or application links.
"""
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from common.profile import Profile
from common.profile import Profile
from common import gemini
from core.mailer import generate_application_email_draft, get_strictly_configured_email

logger = logging.getLogger(__name__)

def _get_candidate_summary() -> str:
    email = get_strictly_configured_email()
    return f"""
Name: Abhishek Anand
Email: {email}
Phone: +91-8839617601
Total Experience: 4+ years
Current Role: React Developer / Frontend Engineer
Core Skills: React.js, Next.js, TypeScript, JavaScript (ES6+), Redux, Redux Toolkit, Tailwind CSS, HTML5, CSS3, REST APIs, Git, Responsive Design, Web Performance Optimization
Notice Period: Immediate (0 days)
Current CTC: 7 LPA
Expected CTC: 10 LPA
Current Location: Patna (Open to Pune, Bangalore, Hyderabad, Gurgaon, Noida, or Remote)
"""


def _get_analysis_system_instruction() -> str:
    candidate_summary = _get_candidate_summary()
    schema_desc = """{
  "company": "string (or 'Unknown Company')",
  "role_title": "string (e.g. 'React Developer', 'Frontend Engineer')",
  "experience_required": "string (e.g. '2-4 years', '3+ years', 'Not specified')",
  "skills_required": ["skill1", "skill2"],
  "location": "string (e.g. 'Remote', 'Bangalore', 'Hybrid')",
  "apply_url": "string or null (any https URL for applying)",
  "contact_email": "string or null (any recruiter or hr email found)",
  "summary": "2-sentence summary of the job",
  "eligibility_score": integer between 0 and 100,
  "verdict": "Strong Match" | "Moderate Match" | "Low Match",
  "is_eligible": boolean (true if eligibility_score >= 60),
  "match_reasons": ["reason 1", "reason 2"],
  "missing_skills": ["missing skill 1"] (skills in JD that Abhishek does not have)
}"""

    return f"""
You are an expert technical recruiter and career evaluator evaluating job postings for the candidate Abhishek Anand.

Candidate Profile:
{candidate_summary}


Analyze the provided job post (text or image) and output ONLY a valid JSON object with the following schema:
{schema_desc}

Rules:
1. If the job is for React, Frontend, Next.js, TypeScript, JavaScript, or Fullstack (with frontend focus), eligibility_score should be 75-95% depending on experience match.
2. If the post asks for 0-4 years or 3-5 years, Abhishek's 4+ years is an exact match.
3. If the post is for completely unrelated fields (e.g., Sales, HR, Android Native Kotlin, Senior DevOps 10+ yrs), score should be < 50.
4. Extract any valid recruiter email address (e.g. careers@company.com, hr@..., name@...).
5. Extract any application URL (forms.gle, bit.ly, greenhouse, lever, linkedin, etc.).
6. Output ONLY the raw JSON string without any Markdown fences or formatting around it.
"""


def _clean_json_response(raw_text: str) -> dict:
    """Extracts and parses JSON from model response text."""
    text = raw_text.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    
    # In case there's leading/trailing noise
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group(0)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to decode JSON from model response: {e}\nRaw: {raw_text}")
        return {
            "company": "Extracted Post",
            "role_title": "Software Developer",
            "experience_required": "Not specified",
            "skills_required": [],
            "location": "Not specified",
            "apply_url": None,
            "contact_email": None,
            "summary": "Job post analyzed.",
            "eligibility_score": 75,
            "verdict": "Moderate Match",
            "is_eligible": True,
            "match_reasons": ["Automated extraction fallback"],
            "missing_skills": []
        }


def _enrich_result(result: dict) -> dict:
    """Enriches the analysis result with email draft and verified URLs/emails."""
    # Find regex emails if not extracted
    raw_summary = result.get("summary", "")
    if not result.get("contact_email"):
        email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", raw_summary)
        if email_match:
            result["contact_email"] = email_match.group(0)

    # Ensure verdict consistency
    score = int(result.get("eligibility_score", 60))
    if score >= 75:
        result["verdict"] = "Strong Match"
        result["is_eligible"] = True
    elif score >= 60:
        result["verdict"] = "Moderate Match"
        result["is_eligible"] = True
    else:
        result["verdict"] = "Low Match"
        result["is_eligible"] = False

    # Pre-generate email draft if contact_email or company is available
    company = result.get("company") or "Hiring Team"
    role_title = result.get("role_title") or "React Developer"
    draft = generate_application_email_draft(
        company=company,
        job_title=role_title,
        recipient=result.get("contact_email") or "",
        job_details=f"Skills: {', '.join(result.get('skills_required', []))}. Location: {result.get('location', '')}"
    )
    result["email_draft"] = draft
    result["sender_email"] = get_strictly_configured_email()

    return result


def analyze_post_text(text: str, profile_data: Optional[dict] = None) -> dict:
    """
    Analyzes hiring post text (LinkedIn, Slack, Telegram, Twitter, etc.).
    Returns structured job details, eligibility score, and action triggers.
    """
    prompt = f"Analyze the following job post:\n\n{text}"
    try:
        raw_response = gemini.generate_content(
            prompt=prompt,
            system_instruction=_get_analysis_system_instruction()
        )
        data = _clean_json_response(raw_response)
    except Exception as e:
        logger.error(f"Error during Gemini text analysis: {e}")
        # Regex heuristics fallback
        emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
        urls = re.findall(r"https?://[^\s]+", text)
        data = {
            "company": "Hiring Organization",
            "role_title": "React Developer / Frontend Engineer",
            "experience_required": "3-5 years",
            "skills_required": ["React", "JavaScript", "TypeScript"],
            "location": "India / Remote",
            "apply_url": urls[0] if urls else None,
            "contact_email": emails[0] if emails else None,
            "summary": text[:200] + ("..." if len(text) > 200 else ""),
            "eligibility_score": 85 if any(k in text.lower() for k in ["react", "frontend", "typescript"]) else 65,
            "match_reasons": ["Candidate has 4+ years of experience in modern frontend development"],
            "missing_skills": []
        }

    return _enrich_result(data)


def analyze_post_image(image_bytes: bytes, mime_type: str = "image/png", profile_data: Optional[dict] = None) -> dict:
    """
    Analyzes hiring flyer or screenshot image using Gemini Multimodal Vision.
    Extracts text, job details, eligibility score, and action triggers.
    """
    prompt = (
        "Perform OCR on this hiring post / recruiter screenshot. "
        "Extract all job requirements, company name, role title, required skills, "
        "any apply URL, and any recruiter email address. "
        "Then evaluate Abhishek Anand's eligibility according to your system instructions."
    )
    try:
        raw_response = gemini.generate_multimodal(
            prompt=prompt,
            image_bytes=image_bytes,
            mime_type=mime_type,
            system_instruction=_get_analysis_system_instruction()
        )

        data = _clean_json_response(raw_response)
    except Exception as e:
        logger.error(f"Error during Gemini multimodal image analysis: {e}")
        data = {
            "company": "Hiring Organization",
            "role_title": "React / Frontend Developer",
            "experience_required": "Not specified",
            "skills_required": ["React", "TypeScript"],
            "location": "Remote",
            "apply_url": None,
            "contact_email": None,
            "summary": "Could not extract full image details via vision API.",
            "eligibility_score": 60,
            "verdict": "Moderate Match",
            "is_eligible": True,
            "match_reasons": ["Visual analysis fallback"],
            "missing_skills": []
        }

    return _enrich_result(data)
