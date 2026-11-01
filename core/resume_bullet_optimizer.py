"""
Dynamic Resume Bullet Swapper & ATS Priority Optimizer
Analyzes the target Job Description (JD) keywords and dynamically re-orders
the candidate's experience bullet points so that the employer's highest-priority
technologies (Next.js vs Redux vs TypeScript vs Design Systems) appear at the very top.
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    from docx import Document
except ImportError:
    Document = None

# Master bullet points categorized by specialization for Abhishek Anand (3.5+ Yrs Frontend)
EXPERIENCE_BULLETS = [
    {
        "category": "nextjs_performance",
        "keywords": ["next.js", "nextjs", "ssr", "server side", "seo", "core web vitals", "lighthouse", "performance", "speed", "lazy loading"],
        "text": "Architected and optimized production Next.js single-page and server-rendered web applications, boosting Core Web Vitals to 95+ and reducing initial page load times by 40% across high-traffic user journeys."
    },
    {
        "category": "state_architecture",
        "keywords": ["redux", "redux toolkit", "rtk", "react query", "tanstack", "state management", "caching", "zustand", "context api"],
        "text": "Streamlined complex client-side state architectures using Redux Toolkit and TanStack Query, cutting redundant API roundtrips by 60% and enabling offline-first optimistic UI mutations."
    },
    {
        "category": "typescript_testing",
        "keywords": ["typescript", "ts", "jest", "unit testing", "react testing library", "rtl", "cypress", "code quality", "coverage"],
        "text": "Enforced end-to-end type safety with TypeScript strict mode and built robust automated test suites with Jest and React Testing Library, achieving 85%+ branch coverage on critical business workflows."
    },
    {
        "category": "ui_design_systems",
        "keywords": ["tailwind", "tailwind css", "material ui", "mui", "shadcn", "design system", "component library", "responsive", "css", "accessibility", "a11y"],
        "text": "Developed a modular, reusable UI component library using Tailwind CSS and Storybook, standardizing design tokens and accelerating engineering sprint velocity across cross-functional teams."
    },
    {
        "category": "api_fullstack",
        "keywords": ["rest", "rest api", "graphql", "node.js", "express", "backend", "microservices", "axios", "postman"],
        "text": "Engineered seamless RESTful and GraphQL API integration layers with Axios interceptors, token rotation, and robust error boundary fallbacks for enterprise web applications."
    }
]

def score_bullet(bullet: Dict[str, Any], jd_text: str) -> int:
    """Scores a bullet point based on frequency of matching keywords in JD."""
    jd_low = jd_text.lower()
    score = 0
    for kw in bullet["keywords"]:
        # Exact word boundary match
        matches = len(re.findall(rf"\b{re.escape(kw)}\b", jd_low))
        score += matches * 2
        if kw in jd_low and matches == 0:
            score += 1
    return score

def optimize_bullets_for_jd(jd_text: str) -> List[Dict[str, Any]]:
    """Sorts candidate experience bullet points in order of relevance to the JD."""
    scored = []
    for b in EXPERIENCE_BULLETS:
        sc = score_bullet(b, jd_text)
        scored.append({
            "score": sc,
            "category": b["category"],
            "text": b["text"]
        })

    # Sort descending by score, preserving high-impact base ordering
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored

def apply_bullet_optimization_to_docx(docx_path: str, jd_text: str, output_path: str = None) -> str:
    """
    Reads the docx resume, identifies experience bullet paragraphs,
    and replaces them with the dynamically prioritized bullet order.
    """
    if Document is None:
        return docx_path

    doc_file = Path(docx_path)
    if not doc_file.exists():
        return docx_path

    out_file = Path(output_path) if output_path else doc_file

    try:
        doc = Document(str(doc_file))
        optimized_bullets = optimize_bullets_for_jd(jd_text)

        # Find bullet paragraphs in experience section
        # Look for bullet character or list style
        bullet_paragraphs = []
        for p in doc.paragraphs:
            text = p.text.strip()
            if text.startswith("•") or text.startswith("-") or p.style.name.startswith("List"):
                if any(w in text.lower() for w in ["architected", "streamlined", "enforced", "developed", "engineered", "react"]):
                    bullet_paragraphs.append(p)

        # Replace text of identified bullet paragraphs with top prioritized bullets
        for idx, p in enumerate(bullet_paragraphs):
            if idx < len(optimized_bullets):
                new_text = "• " + optimized_bullets[idx]["text"]
                p.text = new_text

        doc.save(str(out_file))
        return str(out_file)
    except Exception as e:
        print(f"[Bullet Optimizer] Warning during docx update: {e}")
        return docx_path
