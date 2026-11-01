"""
Intake Feed & Direct Job URL Suitability Evaluator
Processes raw text notifications, emails, WhatsApp messages, or direct job URLs (Indeed, etc.),
extracts structured requirements, and evaluates candidate fit against profile.yaml.
"""
import os
import re
import json
import urllib.parse
from typing import Dict, Any, List, Optional
from pathlib import Path

from common.profile import Profile
from common.gemini import generate_content
from portals.registry import get_portal_class_by_url, detect_portal_from_url


def extract_urls(text: str) -> List[str]:
    """Finds all URLs present in a raw text snippet."""
    pattern = r'(https?://[^\s<>"]+|www\.[^\s<>"]+)'
    return re.findall(pattern, text)


def evaluate_text_suitability(
    role_title: str,
    company: str,
    location: str,
    skills: List[str],
    jd_text: str,
    profile_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Evaluates candidate fit against profile.yaml (3.5+ Yrs React/Frontend, Immediate Joiner).
    """
    if profile_data is None:
        prof = Profile.load()
        profile_data = prof.data

    full_text = f"{role_title} {company} {location} {' '.join(skills)} {jd_text}".lower()

    # 1. Disqualifiers
    disqualifiers = []
    if any(term in full_text for term in ["8+ years", "10+ years", "12+ years", "principal architect", "staff engineer", "vp of engineering"]):
        disqualifiers.append("Seniority exceeds candidate profile (Requires 8+ Years / Staff / Principal)")
    if "angular only" in full_text or ("angular" in full_text and "react" not in full_text):
        disqualifiers.append("Pure Angular position with no React or Next.js")
    if "c++" in full_text or "embedded linux" in full_text or "firmware" in full_text:
        disqualifiers.append("Low-level / Embedded systems engineering role")
    if "us citizen only" in full_text or "us citizenship required" in full_text:
        disqualifiers.append("Restricted to US Citizenship / Security Clearance")

    # 2. Positive Keyword Matching
    core_skills = [
        "react", "react.js", "next.js", "nextjs", "typescript", "javascript",
        "redux", "tailwind", "tailwind css", "frontend", "front-end", "ui developer",
        "web developer", "html5", "css3", "rest api", "graphql", "jest",
        "unit testing", "responsive web design", "node.js"
    ]

    matched_skills = []
    for s in core_skills:
        if s in full_text:
            matched_skills.append(s.title())

    # De-duplicate
    matched_skills = list(dict.fromkeys(matched_skills))

    # Calculate match percentage
    base_score = min(85, int((len(matched_skills) / 5.0) * 80))
    if any(t in role_title.lower() for t in ["react", "frontend", "front end", "ui developer", "next"]):
        base_score = max(base_score, 75)

    # Location affinity
    pref_locations = ["bengaluru", "bangalore", "remote", "pune", "hyderabad", "delhi", "gurgaon", "noida", "india"]
    loc_match = any(loc in location.lower() or loc in full_text for loc in pref_locations) or not location
    if loc_match:
        base_score = min(100, base_score + 10)
    else:
        disqualifiers.append(f"Location '{location}' is outside candidate target hubs")

    if disqualifiers:
        recommendation = "SKIP"
        score = min(base_score, 45)
    elif base_score >= 70:
        recommendation = "APPLY"
        score = base_score
    elif base_score >= 50:
        recommendation = "REVIEW"
        score = base_score
    else:
        recommendation = "SKIP"
        score = base_score

    # Construct verdict reasoning
    if recommendation == "APPLY":
        verdict = f"Strong {score}% match for 3.5+ Yrs Frontend/React Consultant (Immediate Joiner). Key requirements ({', '.join(matched_skills[:4])}) match candidate core stack."
    elif recommendation == "REVIEW":
        verdict = f"Moderate {score}% match. Needs manual inspection of role responsibilities or technology overlaps."
    else:
        verdict = f"Not recommended ({score}%). Reasons: {'; '.join(disqualifiers) or 'Low technology alignment with Frontend stack'}."

    return {
        "score": score,
        "recommendation": recommendation,
        "verdict": verdict,
        "matched_skills": matched_skills,
        "disqualifiers": disqualifiers
    }


def analyze_feed_message(feed_text: str) -> Dict[str, Any]:
    """
    Parses a raw message, email alert, in-app notification, or SMS and evaluates fit.
    """
    feed_text = feed_text.strip()
    if not feed_text:
        return {"success": False, "error": "Empty message feed provided"}

    extracted_urls = extract_urls(feed_text)
    primary_url = extracted_urls[0] if extracted_urls else ""

    # Attempt LLM extraction via Gemini if available
    llm_prompt = f"""
Analyze this job notification / recruitment message and extract the following JSON fields:
- role_title: Job title or designation
- company: Hiring company or client name
- location: Location or remote/hybrid status
- experience_req: Required years of experience (e.g. "3-5 years")
- key_skills: List of technical skills or tools mentioned
- job_url: Any URL to view or apply for the job (or empty string if none)
- summary: A 1-2 sentence clean summary of the opportunity

Input Text:
\"\"\"{feed_text}\"\"\"

Respond ONLY with valid JSON conforming to:
{{
  "role_title": "string",
  "company": "string",
  "location": "string",
  "experience_req": "string",
  "key_skills": ["string"],
  "job_url": "string",
  "summary": "string"
}}
"""
    extracted = None
    try:
        raw_response = generate_content(llm_prompt)
        # Parse JSON from response
        clean_json = raw_response.strip()
        if "```json" in clean_json:
            clean_json = clean_json.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```", 1)[1].split("```", 1)[0].strip()
        extracted = json.loads(clean_json)
    except Exception:
        pass

    # Fallback heuristic extraction if Gemini is unavailable
    if not extracted or not isinstance(extracted, dict):
        role_guess = "Frontend Developer"
        for r in ["React Developer", "Frontend Engineer", "Next.js Developer", "UI Developer", "Full Stack Developer"]:
            if r.lower() in feed_text.lower():
                role_guess = r
                break

        company_guess = "Hiring Team"
        for line in feed_text.splitlines():
            if any(k in line.lower() for k in ["at ", "hiring at ", "company:", "client:"]):
                company_guess = line.strip()[:40]
                break

        extracted = {
            "role_title": role_guess,
            "company": company_guess,
            "location": "Bengaluru / Remote" if "remote" in feed_text.lower() else "India",
            "experience_req": "3+ years",
            "key_skills": ["React", "TypeScript", "JavaScript", "Next.js"],
            "job_url": primary_url,
            "summary": feed_text[:200]
        }

    # If LLM didn't catch the URL but we found one via regex
    if not extracted.get("job_url") and primary_url:
        extracted["job_url"] = primary_url

    # Run Candidate Fit Evaluation
    evaluation = evaluate_text_suitability(
        role_title=extracted.get("role_title", "Frontend Developer"),
        company=extracted.get("company", "Company"),
        location=extracted.get("location", "India"),
        skills=extracted.get("key_skills", []),
        jd_text=feed_text
    )

    portal_detected = detect_portal_from_url(extracted.get("job_url", "")) if extracted.get("job_url") else None

    return {
        "success": True,
        "extracted": extracted,
        "evaluation": evaluation,
        "portal_detected": portal_detected,
        "can_apply_direct": bool(extracted.get("job_url"))
    }


def analyze_direct_job_url(job_url: str) -> Dict[str, Any]:
    """
    Visits a direct job URL (Indeed, LinkedIn, or external ATS) using stealth automation,
    extracts the live JD, and evaluates suitability.
    """
    job_url = job_url.strip()
    if not job_url:
        return {"success": False, "error": "Missing job URL"}

    portal_name = detect_portal_from_url(job_url)

    # 1. Specialized Handler for Indeed
    if portal_name == "indeed":
        from portals.indeed.applicant import IndeedApplicant
        applicant = IndeedApplicant(profile=Profile.load(), headless=True)
        try:
            details = applicant.parse_job_details(job_url)
            suitability = applicant.evaluate_job_suitability(details)
            return {
                "success": True,
                "portal": "indeed",
                "details": details,
                "evaluation": {
                    "score": suitability["score"],
                    "recommendation": suitability["recommendation"],
                    "verdict": f"Indeed Job Analysis: {suitability['score']}% match. {' '.join(suitability['disqualifiers']) if suitability['disqualifiers'] else 'High alignment with your 3.5+ Yrs React stack.'}",
                    "matched_skills": suitability["matched_keywords"],
                    "disqualifiers": suitability["disqualifiers"]
                },
                "apply_mode": "Easily Apply (In-Portal)" if details.get("is_easily_apply") else "External Company Site"
            }
        except Exception as e:
            return {"success": False, "error": f"Failed inspecting Indeed URL: {str(e)}"}
        finally:
            applicant.close_session()

    # 2. Generic ATS / URL Handler
    try:
        from core.universal_applicant import UniversalATSApplicant
        applicant = UniversalATSApplicant(profile=Profile.load(), headless=True)
        try:
            details = applicant.parse_job_details(job_url)
            evaluation = evaluate_text_suitability(
                role_title=details.get("title", "Frontend Developer"),
                company=details.get("company", "Company"),
                location=details.get("location", "India"),
                skills=[],
                jd_text=details.get("description", "")
            )
            return {
                "success": True,
                "portal": portal_name or "ats",
                "details": details,
                "evaluation": evaluation,
                "apply_mode": "Direct ATS Portal Form"
            }
        finally:
            applicant.close_session()
    except Exception as e:
        return {"success": False, "error": f"Failed inspecting job URL: {str(e)}"}
