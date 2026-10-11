"""Generates high-converting, personalized cold emails for LinkedIn hiring posts."""

import json
from common import llm
from common.gemini import _get_client as _get_gemini_client, MODEL as GEMINI_MODEL
from common.groq_llm import _get_client as _get_groq_client, MODEL as GROQ_MODEL
from google.genai import types as genai_types


_PROMPT_TEMPLATE = """\
You are an expert tech recruiter and cold outreach copywriter writing a high-converting cold email for Abhishek Anand applying for a frontend/full-stack position seen on a LinkedIn hiring post.

--- APPLICANT PROFILE ---
Name: Abhishek Anand
Role: Frontend Engineer / React Developer
Experience: 3.6+ years professional experience
Core Stack: React.js, Next.js, TypeScript, JavaScript, Redux, TanStack Query, Tailwind CSS, REST APIs, GraphQL
Key Achievements:
- Scaled production web apps; reduced redundant API calls by 60% using TanStack Query.
- Built real-time monitoring dashboard for 500+ devices and 10,000-cell data grid for enterprise clients.
- Improved Core Web Vitals from Poor to Good on an app serving 10,000+ monthly users.
Notice Period: Immediate joiner (0 days notice period)
Location: Noida, India (open to Hybrid / Remote / Relocation)
Phone: +91-8839617601

--- POST DETAILS ---
Post Author: {author}
Company (if mentioned): {company}
Role Title: {role}
Post Content:
{post_text}

--- COLD EMAIL GUIDELINES ---
1. Subject line must be clean and professional: e.g. "Application: {role} - Abhishek Anand (3.6 Yrs Exp | Immediate Joiner)"
2. Length: Under 130 words. Extremely punchy, skimmable, no corporate fluff, no buzzwords like "delighted" or "esteemed".
3. Greeting: Professional (e.g. "Hi {author_first_name}," or "Hi {company} Hiring Team,").
4. Hook: Mention you came across their recent post on LinkedIn hiring for the {role} role.
5. Value proposition: Highlight direct tech stack match (React/TypeScript/Next.js) and 1-2 quantifiable metrics relevant to the post requirements.
6. Availability: Note that Abhishek is available to join immediately (0 days notice).
7. CTA: Mention the attached tailored resume and request a brief 10-minute conversation.
8. Sign-off:
   Best regards,
   Abhishek Anand
   +91-8839617601

Return a valid JSON object with keys "subject" and "body" ONLY. No markdown wrappers or additional text.
"""


def draft_cold_email(
    post_text: str,
    author: str = "Hiring Team",
    company: str = "your team",
    role: str = "React Developer",
) -> dict[str, str]:
    """Generates a tailored cold email subject and body from a hiring post."""
    author_first = author.split()[0] if author and author.strip() else "Hiring Team"
    prompt = _PROMPT_TEMPLATE.format(
        author=author,
        author_first_name=author_first,
        company=company or "your team",
        role=role or "React Developer",
        post_text=post_text[:2000],
    )

    # Try Gemini first
    try:
        client = _get_gemini_client()
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json",
            ),
        )
        data = json.loads(response.text.strip())
        return {
            "subject": data.get("subject", f"Application: {role} - Abhishek Anand (Immediate Joiner)"),
            "body": data.get("body", "").strip(),
        }
    except Exception as e:
        print(f"  (Gemini drafting failed — {e}. Falling back to Groq...)")

    # Fallback to Groq
    try:
        groq_client = _get_groq_client()
        completion = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        data = json.loads(completion.choices[0].message.content.strip())
        return {
            "subject": data.get("subject", f"Application: {role} - Abhishek Anand (Immediate Joiner)"),
            "body": data.get("body", "").strip(),
        }
    except Exception as e:
        print(f"  (Groq drafting failed — {e}. Using deterministic template.)")

    # Fallback deterministic template
    subject = f"Application: {role} - Abhishek Anand (3.6 Yrs Exp | Immediate Joiner)"
    body = (
        f"Hi {author_first},\n\n"
        f"I came across your recent LinkedIn post regarding the {role} position and wanted to reach out directly.\n\n"
        f"I am a Frontend Engineer with 3.6+ years of production experience specializing in React.js, Next.js, and TypeScript. "
        f"In my previous projects, I built real-time telemetry dashboards, reduced redundant API calls by 60% with TanStack Query, "
        f"and improved Core Web Vitals to 'Good' for 10k+ monthly users.\n\n"
        f"I am an immediate joiner (0 days notice period) and have attached my tailored resume for your review.\n\n"
        f"Would you be open to a quick 10-minute introductory conversation this week?\n\n"
        f"Best regards,\n"
        f"Abhishek Anand\n"
        f"+91-8839617601\n"
        f"abhishek.anand.7601@gmail.com"
    )
    return {"subject": subject, "body": body}
