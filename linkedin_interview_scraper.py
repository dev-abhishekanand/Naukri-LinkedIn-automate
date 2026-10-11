"""LinkedIn Frontend & React Interview Experience Scraper.
Scrapes real interview experiences, questions asked, machine coding tasks,
and tips shared by developers on LinkedIn, structuring them with AI and saving
directly to a dedicated 'Frontend Interview Prep' worksheet in Google Sheets.

Usage:
    python linkedin_interview_scraper.py
    python linkedin_interview_scraper.py --query "React interview questions"
    python linkedin_interview_scraper.py --dry-run
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from common import llm
from common.gemini import _get_client as _get_gemini_client, MODEL as GEMINI_MODEL
from common.groq_llm import _get_client as _get_groq_client, MODEL as GROQ_MODEL
from common.profile import Profile
from google_sheets_logger import append_interview_prep, interview_post_url_exists

SESSION_FILE = "session_linkedin.json"
INTERVIEW_CSV_FILE = "interview_prep.csv"

DEFAULT_SEARCH_QUERIES = [
    "React interview questions asked",
    "Frontend interview experience",
    "React machine coding round",
    "Frontend engineer interview questions",
]

_ANALYSIS_PROMPT = """\
You are an expert technical interviewer and Frontend engineering specialist.
Analyze the following LinkedIn post to determine if it shares a Frontend / React interview experience, questions asked during technical rounds, machine coding challenges, or interview preparation tips.

--- POST AUTHOR ---
{author} ({headline})

--- POST TEXT ---
{post_text}

--- INSTRUCTIONS ---
1. Determine if this post contains real interview questions, coding tasks, or detailed interview experiences for Frontend / React / Web development.
2. If it is NOT an interview post (e.g. promotional ad, hiring job opening without questions, generic networking fluff), set "is_interview": false.
3. If it IS an interview post, extract and structure:
   - "company": The company/companies interviewed for (e.g. "Swiggy", "Walmart", "Razorpay", or "Startup / General" if not specified).
   - "role_level": Role or seniority level mentioned (e.g. "SDE-2 Frontend", "React Developer (3 YOE)", "Frontend Engineer").
   - "round_type": Technical round type (e.g. "Machine Coding", "Core JavaScript & React Internals", "System Design", "Technical Round 1 & 2").
   - "topics": Comma-separated technical topics (e.g. "Hooks, Redux Toolkit, Virtual DOM, Event Loop, Closures, Web Vitals, Hydration").
   - "questions_asked": Bulleted list of conceptual, theoretical, or tricky technical questions asked (clean bullet points with "• ").
   - "coding_tasks": Any coding problems, machine coding challenges, or polyfills asked to implement (e.g. "Implement Promise.allSettled", "Build nested comments component with recursion").
   - "system_design": Any frontend system design, architecture, or state management questions (e.g. "Design rich text editor", "Design infinite scroll feed").
   - "tips": Candidate's advice, key takeaways, or preparation tips.

Return strictly a valid JSON object with the keys:
"is_interview", "company", "role_level", "round_type", "topics", "questions_asked", "coding_tasks", "system_design", "tips".
Do NOT include markdown formatting or extra text outside JSON.
"""


def analyze_interview_post(post_text: str, author: str = "", headline: str = "") -> dict:
    """Analyzes and structures interview post content using Gemini (Groq fallback)."""
    # Quick filter: skip very short posts
    if len(post_text.strip()) < 80:
        return {"is_interview": False}

    prompt = _ANALYSIS_PROMPT.format(
        author=author or "LinkedIn User",
        headline=headline or "",
        post_text=post_text[:3500],
    )

    raw_response = ""
    try:
        client = _get_gemini_client()
        from google.genai import types as genai_types
        config = genai_types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
        )
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=config,
        )
        raw_response = resp.text.strip()
    except Exception as e:
        if not llm._looks_like_quota_error(e):
            print(f"  (Gemini analysis error: {e}. Trying Groq...)")
        try:
            groq_client = _get_groq_client()
            resp = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            raw_response = resp.choices[0].message.content.strip()
        except Exception as e2:
            print(f"  (Groq analysis also failed: {e2})")
            return {"is_interview": False}

    try:
        # Strip code fences if present
        cleaned = re.sub(r'^```(?:json)?\s*', '', raw_response)
        cleaned = re.sub(r'\s*```$', '', cleaned).strip()
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else {"is_interview": False}
    except Exception:
        return {"is_interview": False}


def log_interview_to_csv(entry: dict):
    """Appends interview entry to local CSV."""
    csv_path = Path(INTERVIEW_CSV_FILE)
    new_file = not csv_path.exists() or csv_path.stat().st_size == 0
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow([
                "discovered_at", "company", "role_level", "round_type",
                "topics", "questions_asked", "coding_tasks", "system_design",
                "tips", "post_link", "author"
            ])
        w.writerow([
            entry.get("discovered_at", datetime.now().isoformat()),
            entry.get("company", ""),
            entry.get("role_level", ""),
            entry.get("round_type", ""),
            entry.get("topics", ""),
            entry.get("questions_asked", ""),
            entry.get("coding_tasks", ""),
            entry.get("system_design", ""),
            entry.get("tips", ""),
            entry.get("post_link", ""),
            entry.get("author", ""),
        ])


def scrape_posts_for_query(page, query: str) -> list[dict]:
    """Searches LinkedIn for a given query and extracts raw feed posts."""
    url = f"https://www.linkedin.com/search/results/content/?keywords={urllib.parse.quote(query)}"
    print(f"\n🔍 Searching LinkedIn Posts: '{query}'")
    page.goto(url, wait_until="commit", timeout=25000)
    time.sleep(4)

    # Click '... more' / 'see more' buttons
    try:
        page.evaluate("""
            () => {
                const moreButtons = Array.from(document.querySelectorAll("button, span")).filter(el => {
                    const t = el.innerText?.trim()?.toLowerCase();
                    return t === "… more" || t === "...more" || t === "see more";
                });
                moreButtons.forEach(b => { try { b.click(); } catch(e){} });
            }
        """)
        time.sleep(1.5)
    except Exception:
        pass

    # Scroll down twice to load more post content
    for _ in range(2):
        page.evaluate("window.scrollBy(0, 1000);")
        time.sleep(1.5)

    # Click more buttons again after scroll
    try:
        page.evaluate("""
            () => {
                const moreButtons = Array.from(document.querySelectorAll("button, span")).filter(el => {
                    const t = el.innerText?.trim()?.toLowerCase();
                    return t === "… more" || t === "...more" || t === "see more";
                });
                moreButtons.forEach(b => { try { b.click(); } catch(e){} });
            }
        """)
    except Exception:
        pass

    posts_data = page.evaluate("""
        () => {
            const feedNodes = Array.from(document.querySelectorAll("*")).filter(el => {
                return el.children.length === 0 && el.innerText?.trim() === "Feed post";
            });

            const seenUrns = new Set();
            return feedNodes.map(n => {
                let container = n.parentElement;
                for (let i = 0; i < 6; i++) {
                    if (container && container.innerText && container.innerText.length > 150 && container.getAttribute("componentkey")) {
                        break;
                    }
                    if (container && container.parentElement) container = container.parentElement;
                }
                if (!container) return null;

                const lines = container.innerText.split("\\n").map(l => l.trim()).filter(Boolean);
                const author = lines[1] || "";
                const headline = lines.find((l, idx) => idx > 1 && idx < 6 && (l.includes("|") || l.includes("Engineer") || l.includes("Developer") || l.includes("Lead") || l.length > 20)) || "";

                const profileLink = container.querySelector("a[href*='/in/']")?.href || "";
                const postAnchor = container.querySelector("a[href*='/activity/'], a[href*='/feed/update/']");
                let directPostLink = postAnchor ? postAnchor.href : "";

                const urn = container.getAttribute("componentkey") || container.getAttribute("data-urn") || "";
                if (!directPostLink && urn && urn.includes("activity:")) {
                    const actId = urn.split("activity:")[1]?.split("~")[0]?.split(")")[0]?.split('"')[0];
                    if (actId) directPostLink = `https://www.linkedin.com/feed/update/urn:li:activity:${actId}/`;
                }

                if (urn && seenUrns.has(urn)) return null;
                if (urn) seenUrns.add(urn);

                const finalLink = directPostLink || profileLink || window.location.href;

                return {
                    author,
                    headline,
                    profileLink,
                    postLink: finalLink,
                    text: container.innerText,
                    urn
                };
            }).filter(Boolean);
        }
    """)

    print(f"   Found {len(posts_data)} candidate posts for query: '{query}'")
    return posts_data


def run_interview_scraper(
    search_queries: list[str] | None = None,
    dry_run: bool = False,
    max_per_query: int = 10,
):
    """Main orchestrator for scraping and cataloging frontend interview experiences."""
    profile = Profile.load()
    if not Path(SESSION_FILE).exists():
        raise SystemExit(
            f"ERROR: {SESSION_FILE} not found. "
            "Please run 'python login_capture.py linkedin' first."
        )

    queries = search_queries or DEFAULT_SEARCH_QUERIES
    saved_count = 0

    print("=" * 75)
    print("📚 LinkedIn Frontend & React Interview Prep Scraper")
    print(f"Queries: {', '.join(queries)}")
    print(f"Target Sheet: 'Frontend Interview Prep' in Google Sheets")
    print(f"Mode: {'DRY RUN (no sheet updates)' if dry_run else 'ACTIVE (syncing to Google Sheets)'}")
    print("=" * 75)

    with sync_playwright() as p:
        browser_mode = profile.data.get("browser_mode", "minimized")
        if browser_mode == "headless":
            browser = p.chromium.launch(headless=True, slow_mo=150)
        elif browser_mode == "minimized":
            browser = p.chromium.launch(headless=False, slow_mo=150, args=["--start-minimized"])
        else:
            browser = p.chromium.launch(headless=False, slow_mo=150)

        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        for query in queries:
            posts = scrape_posts_for_query(page, query)

            for post in posts[:max_per_query]:
                text = post.get("text", "")
                author = post.get("author", "LinkedIn Member")
                headline = post.get("headline", "")
                post_link = post.get("postLink", "")

                # Dedup check in Google Sheets
                if post_link and not dry_run and interview_post_url_exists(post_link):
                    print(f"⏭️ Skipping: Post already logged in Interview Prep ({post_link})")
                    continue

                # Quick pre-filter: check for interview terms
                lower_text = text.lower()
                interview_indicators = [
                    "interview", "round", "asked", "question", "machine coding",
                    "experience", "dsa", "javascript", "react", "prep", "hiring manager"
                ]
                if not any(term in lower_text for term in interview_indicators):
                    continue

                print(f"\n🧠 Analyzing post by {author} ({headline[:40]}...)...")
                analysis = analyze_interview_post(text, author, headline)

                if not analysis.get("is_interview"):
                    continue

                saved_count += 1
                company = analysis.get("company", "Various / General")
                role_level = analysis.get("role_level", "Frontend / React Developer")
                round_type = analysis.get("round_type", "Technical Round")
                topics = analysis.get("topics", "")
                questions = analysis.get("questions_asked", "")
                coding = analysis.get("coding_tasks", "")
                sys_design = analysis.get("system_design", "")
                tips = analysis.get("tips", "")

                print("\n" + "=" * 75)
                print(f"💡 FRONTEND INTERVIEW EXPERIENCE DISCOVERED (#{saved_count})")
                print(f"Company:       {company}")
                print(f"Role / Level:  {role_level}")
                print(f"Round Type:    {round_type}")
                print(f"Topics:        {topics}")
                if questions:
                    print(f"Questions:\n{questions}")
                if coding:
                    print(f"Coding Tasks:  {coding}")
                if sys_design:
                    print(f"System Design: {sys_design}")
                if tips:
                    print(f"Tips:          {tips}")
                print(f"Post Link:     {post_link}")
                print(f"Author:        {author}")
                print("=" * 75)

                entry = {
                    "discovered_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "company": company,
                    "role_level": role_level,
                    "round_type": round_type,
                    "topics": topics,
                    "questions_asked": questions,
                    "coding_tasks": coding,
                    "system_design": sys_design,
                    "tips": tips,
                    "post_link": post_link,
                    "author": f"{author} ({headline})",
                }

                # Always log to local CSV
                log_interview_to_csv(entry)

                if not dry_run:
                    try:
                        append_interview_prep(entry)
                        print("✅ Successfully logged to Google Sheets 'Frontend Interview Prep' worksheet!")
                    except Exception as e:
                        print(f"⚠️ Google Sheets logging error: {e}")

                time.sleep(1)

        browser.close()

    print(f"\n🏁 Finished interview scraping. Total interview posts extracted: {saved_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LinkedIn Frontend Interview Experience Scraper")
    parser.add_argument("--query", type=str, default=None, help="Specific query to search for")
    parser.add_argument("--dry-run", action="store_true", help="Analyze posts without saving to Google Sheets")
    parser.add_argument("--max-posts", type=int, default=10, help="Max posts to analyze per query")
    args = parser.parse_args()

    queries = [args.query] if args.query else None
    run_interview_scraper(search_queries=queries, dry_run=args.dry_run, max_per_query=args.max_posts)
