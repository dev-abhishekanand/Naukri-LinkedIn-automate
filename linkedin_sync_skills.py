"""
Synchronizes and populates LinkedIn Profile Skills with a curated 50-skill taxonomy.

LinkedIn allows up to 50 skills. Recruiters on LinkedIn Recruiter search by exact skill
taxonomies and filter candidates matching required and preferred skills. Having all 50
slots occupied with standardized, high-demand frontend and web development keywords
dramatically maximizes search appearances and ranking.

Usage:
    python linkedin_sync_skills.py              # Syncs all 50 skills from profile.yaml
    python linkedin_sync_skills.py --dry-run    # Preview skills to be added without opening browser
    python linkedin_sync_skills.py --limit 5    # Add only 5 skills
"""

import argparse
from pathlib import Path
import sys
import time

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from common.profile import Profile

SESSION_FILE = "session_linkedin.json"
SKILLS_LIST_URL = "https://www.linkedin.com/in/abhishekreactdeveloper/details/skills/"
ADD_SKILL_URL = "https://www.linkedin.com/in/abhishekreactdeveloper/skills/edit/forms/new/"

DEFAULT_LINKEDIN_SKILLS = [
    # 1. Core React & UI Engineering (10)
    "React.js",
    "Next.js",
    "TypeScript",
    "JavaScript",
    "Redux Toolkit",
    "Redux",
    "Context API",
    "TanStack Query",
    "React Router",
    "Virtual DOM",

    # 2. Modern Web Fundamentals & Styling (8)
    "HTML5",
    "Cascading Style Sheets (CSS)",
    "Tailwind CSS",
    "Material-UI",
    "Sass",
    "Responsive Web Design",
    "CSS Modules",
    "Styled Components",

    # 3. Frontend Architecture & Web Performance (8)
    "Front-End Development",
    "Web Performance Optimization",
    "Single Page Applications (SPA)",
    "Server-Side Rendering (SSR)",
    "Code Splitting",
    "Micro Frontends",
    "Progressive Web Applications (PWAs)",
    "Component-Based Software Engineering",

    # 4. APIs, Data & Real-time (6)
    "RESTful APIs",
    "GraphQL",
    "Apollo GraphQL",
    "WebSockets",
    "Axios",
    "Fetch API",

    # 5. Build Tools, Quality & Testing (8)
    "Git",
    "GitHub",
    "Vite",
    "Webpack",
    "Babel",
    "ESLint",
    "Jest",
    "Unit Testing",

    # 6. Backend, Database & Cloud Integration (7)
    "Node.js",
    "Express.js",
    "MongoDB",
    "Docker",
    "Microsoft Azure",
    "Socket.io",
    "Postman API",

    # 7. Engineering Practices & Agile (3)
    "Agile Methodologies",
    "Scrum",
    "Cross-functional Team Leadership",
]


def get_existing_skills(page) -> set:
    """Navigates to the skills page and collects names of already added skills."""
    print("Checking existing live skills on profile...")
    page.goto(SKILLS_LIST_URL, wait_until="load", timeout=60000)
    time.sleep(3)

    # Scroll down to load all items
    for _ in range(3):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(1)

    labels = page.evaluate("""() => {
        const els = Array.from(document.querySelectorAll('a[aria-label*="Edit "]'));
        return els.map(e => {
            const raw = e.getAttribute('aria-label') || '';
            return raw.replace('Edit ', '').replace(' skill', '').trim().toLowerCase();
        });
    }""")
    return set(labels)


def sync_linkedin_skills(profile: Profile, dry_run: bool = False, limit: int | None = None) -> bool:
    session_path = Path(SESSION_FILE)
    if not session_path.exists():
        print(f"ERROR: Session file {SESSION_FILE} not found. Run login_capture.py first.")
        return False

    skills_to_sync = profile.data.get("linkedin_skills") or DEFAULT_LINKEDIN_SKILLS

    if dry_run:
        print(f"=== DRY RUN: LinkedIn Skills Sync ({len(skills_to_sync)} skills configured) ===")
        for i, s in enumerate(skills_to_sync, 1):
            print(f"  {i:2d}. {s}")
        print("==========================================================")
        return True

    print(f"\n[LinkedIn Skills Sync] Starting synchronization for {len(skills_to_sync)} skills...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-minimized"])
        context = browser.new_context(storage_state=str(session_path))
        page = context.new_page()

        try:
            existing = get_existing_skills(page)
            print(f"Profile currently has {len(existing)} existing skills: {list(existing)[:5]}...")

            added_count = 0
            skipped_count = 0

            for idx, skill in enumerate(skills_to_sync, 1):
                if limit and added_count >= limit:
                    print(f"\nReached requested limit of {limit} skills added.")
                    break

                if skill.lower() in existing:
                    print(f"[{idx}/{len(skills_to_sync)}] Skipped: '{skill}' already exists on profile.")
                    skipped_count += 1
                    continue

                print(f"[{idx}/{len(skills_to_sync)}] Adding: '{skill}'...")
                page.goto(ADD_SKILL_URL, wait_until="load", timeout=60000)
                time.sleep(2.5)

                # Locate input
                inp = page.locator('input[placeholder*="Skill (ex:"]').first
                if inp.count() == 0:
                    inp = page.locator('input[placeholder*="Skill"]').first

                if inp.count() == 0:
                    print(f"  ❌ Could not find skill input field on form for '{skill}'")
                    continue

                inp.click()
                inp.fill(skill)
                time.sleep(1.2)

                # Press ArrowDown then Enter to select first typeahead suggestion
                page.keyboard.press("ArrowDown")
                time.sleep(0.3)
                page.keyboard.press("Enter")
                time.sleep(1.0)

                # Click Save
                save_btn = page.locator('button:has-text("Save")').first
                if save_btn.count() == 0:
                    save_btn = page.locator('footer button:has-text("Save")').first

                if save_btn.count() > 0:
                    save_btn.click()
                    time.sleep(2.5)
                    print(f"  ✓ Successfully saved '{skill}'")
                    added_count += 1
                    existing.add(skill.lower())
                else:
                    print(f"  ❌ Save button not found for '{skill}'")

            print(f"\n=======================================================")
            print(f"LinkedIn Skills Sync Summary:")
            print(f"  Skills Added:   {added_count}")
            print(f"  Skills Skipped: {skipped_count}")
            print(f"  Total on Profile: {len(existing)}")
            print(f"=======================================================")
            return True

        except PWTimeout:
            print("ERROR: Timeout during skills synchronization.")
            return False
        except Exception as e:
            print(f"ERROR: Unexpected exception during skills sync: {e}")
            return False
        finally:
            try:
                context.close()
                browser.close()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="Synchronize curated 50 skills to LinkedIn profile.")
    parser.add_argument("--dry-run", action="store_true", help="Preview skills without saving")
    parser.add_argument("--limit", type=int, default=None, help="Limit maximum number of skills to add")
    args = parser.parse_args()

    profile = Profile.load()
    success = sync_linkedin_skills(profile, dry_run=args.dry_run, limit=args.limit)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
