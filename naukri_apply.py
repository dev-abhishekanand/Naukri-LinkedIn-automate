"""
Naukri auto-apply. Requires session_naukri.json from login_capture.py.

Usage:
    python naukri_apply.py

Stops the ENTIRE run immediately and reports if it hits a CAPTCHA, a login
prompt, or a rate-limit warning. Never attempts to solve any of those --
that's the point. Everything else (a bad selector, a question it can't
answer, a stray page error) is handled per-listing: that one listing is
skipped and logged, and the run continues.
"""
import re
import csv
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from common.profile import Profile
from common import llm
from common import learned_answers
from common.human_input import ask_user
from google_sheets_logger import append_external_job, external_job_url_exists

SESSION_FILE = "session_naukri.json"
LOG_FILE = "applications_log.csv"
EXTERNAL_LOG_FILE = "external_jobs.csv"
PROCESSED_JOBS_FILE = "processed_jobs.csv"

def record_processed_job(card: dict, status: str):
    new_file = not Path(PROCESSED_JOBS_FILE).exists() or Path(PROCESSED_JOBS_FILE).stat().st_size == 0
    with open(PROCESSED_JOBS_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["job_id", "platform", "title", "company", "status", "processed_at", "job_url"])
        w.writerow([
            card.get("jobId", ""),
            "naukri",
            card.get("title", ""),
            card.get("company", ""),
            status,
            datetime.now().isoformat(),
            card.get("href", ""),
        ])


def load_processed_job_ids() -> set[str]:
    if not Path(PROCESSED_JOBS_FILE).exists():
        return set()
    with open(PROCESSED_JOBS_FILE, newline="") as f:
        return {row.get("job_id", "").strip() for row in csv.DictReader(f) if row.get("job_id", "").strip()}


STOP_PHRASES = [
    "too many requests", "unusual activity", "verify you are human",
    "captcha", "temporarily blocked", "please try again later and reduce",
    "there was an error while processing your request",
]

# Questions matching any of these should NEVER be answered by the LLM --
# these are exact personal facts an LLM could easily hallucinate wrong.
# Always routed straight to you (and then remembered for next time).
SENSITIVE_FIELD_HINTS = [
    "date of birth", "dob", "pan number", "pan card", "aadhar", "aadhaar",
    "passport", "bank account", "ifsc", "father's name", "father name",
    "mother's name", "mother name", "marital status", "blood group",
    "emergency contact", "voter id", "driving licence", "driving license",
]


# Specific phrases per answer-library key, checked as whole phrases (not
# single split words) so "current ctc" and "current city" can never collide
# just because they both start with "current". This is what the old
# key.split("_")[0] logic got wrong -- it reduced both to "current" and
# whichever key came first in the dict won, regardless of what was asked.
TRIGGER_PHRASES = {
    "years_experience": ["years of experience", "total experience", "how many years", "work experience"],
    "notice_period": ["notice period"],
    "current_ctc": ["current ctc", "current salary", "current compensation", "present ctc", "present salary"],
    "expected_ctc": ["expected ctc", "expected salary", "expected compensation"],
    "current_city": ["current city", "current location", "which city", "current place"],
    "relocate": ["relocate", "relocation", "willing to move"],
    "night_shift": ["night shift"],
    "weekend_work": ["weekend"],
}


def log_row(row: list):
    new_file = not Path(LOG_FILE).exists()
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["timestamp", "source", "title", "company", "status", "reason"])
        w.writerow(row)

def log_external_job(card: dict):
    new_file = not Path(EXTERNAL_LOG_FILE).exists()

    with open(EXTERNAL_LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)

        if new_file:
            w.writerow([
                "discovered_at",
                "platform",
                "job_id",
                "title",
                "company",
                "location",
                "experience",
                "job_url",
                "status",
                "notes",
            ])

        w.writerow([
            datetime.now(),
            "naukri",
            card.get("jobId"),
            card.get("title"),
            card.get("company"),
            card.get("location"),
            card.get("exp"),
            card.get("href"),
            "PENDING",
            "External company application - manual completion required",
        ])

    try:
        append_external_job({
            "discovered_at": datetime.now().isoformat(),
            "jobId": card.get("jobId"),
            "title": card.get("title"),
            "company": card.get("company"),
            "location": card.get("location"),
            "exp": card.get("exp"),
            "href": card.get("href"),
        })
        print("Google Sheets: external job logged")
    except Exception as e:
        print(f"Google Sheets logging failed: {e}")
        
def passes_filters(card: dict, profile: Profile, role: str) -> tuple[bool, str]:
    """
    Apply only hard filters that are available from the search card.

    IMPORTANT:
    Job title is intentionally NOT used as an eligibility filter.
    A generic title such as "Software Engineer" can still be a strong
    React/TypeScript/Node/etc. match once the full job page is opened.
    Description + Key Skills are evaluated later by classify_job_quality().
    """
    company = (card.get("company") or "").lower()

    for excl in profile.company_exclude:
        if excl.lower() in company:
            return False, f"company excluded ({excl})"

    if profile.company_include_only:
        if not any(inc.lower() in company for inc in profile.company_include_only):
            return False, "not in include-only list"

    exp_text = card.get("exp") or ""
    digits = [int(s) for s in exp_text.replace("Yrs", "").replace("yrs", "")
              .replace("-", " ").split() if s.isdigit()]
    if len(digits) >= 2:
        lo, hi = digits[0], digits[-1]
        if hi < profile.seniority_floor_years or lo > profile.seniority_ceiling_years:
            return False, f"experience range mismatch ({exp_text})"

    return True, ""


def safe_evaluate(page, script, arg=None, default=None):
    """Runs page.evaluate but never lets a destroyed-context or stray JS error
    crash the whole run -- returns `default` instead. Naukri's own chat widget
    and SPA navigation can tear down the page mid-script, which raises
    Playwright's 'Execution context was destroyed' error; that's expected
    occasionally, not something to crash over."""
    try:
        return page.evaluate(script, arg) if arg is not None else page.evaluate(script)
    except Exception as e:
        print(f"  (page.evaluate failed, continuing anyway: {e})")
        return default


def enumerate_cards(page):
    """Reads real job cards off the search results page. Card wrapper is
    div.srp-jobtuple-wrapper with a data-job-id attribute -- that attribute
    is the reliable marker; filter/promo widgets on the same page don't
    have it."""
    return safe_evaluate(page, """
        () => Array.from(document.querySelectorAll('.srp-jobtuple-wrapper[data-job-id]'))
          .map((c, i) => ({
            i,
            jobId: c.getAttribute('data-job-id'),
            title: c.querySelector('a.title')?.innerText.trim(),
            href: c.querySelector('a.title')?.href,
            company: c.querySelector('a.comp-name, .comp-dtls-wrap a')?.innerText.trim(),
            exp: c.querySelector('.expwdth')?.innerText,
            location: c.querySelector('.locWdth')?.innerText,
          }))
          .filter(c => c.title && c.href)
    """, default=[]) or []

def extract_job_details(page) -> dict:
    """Extract description and explicit key skills from an opened Naukri job page."""
    details = {
        "description": "",
        "key_skills": "",
    }

    try:
        description = page.locator(
            ".styles_JDC__dang-inner-html__h0K4t"
        ).first.inner_text(timeout=3000).strip()
        details["description"] = description
    except Exception:
        pass

    try:
        body = page.inner_text("body")

        marker = "Key Skills"
        start = body.find(marker)

        if start >= 0:
            section = body[start + len(marker):]

            for end_marker in [
                "Report this job",
                "About company",
                "About the company",
            ]:
                end = section.find(end_marker)
                if end >= 0:
                    section = section[:end]
                    break

            details["key_skills"] = " ".join(section.split()).strip()
    except Exception:
        pass

    return details

def classify_job_quality(
    title: str,
    description: str,
    key_skills: str,
    profile: Profile | None = None,
) -> str:
    """
    Classify a job using ONLY the opened job's description and key skills.

    The title is deliberately ignored for eligibility. It is passed in only
    to preserve the existing call shape/logging compatibility.

    The decision is based on overlap with the user's configured skills,
    with stronger treatment for the user's core React/frontend/JavaScript
    stack and explicit competing stacks.
    """
    _ = title  # Title must never influence eligibility.

    text = f"{description or ''} {key_skills or ''}".lower()

    def has(pattern: str) -> bool:
        return bool(re.search(pattern, text))

    # Strong/profile-specific signals.
    skills = {
        "react": has(r"(?<!\w)react(?:\.js|js)?(?!\w)"),
        "next": has(r"(?<!\w)next(?:\.js|js)?(?!\w)"),
        "typescript": has(r"(?<!\w)typescript(?!\w)"),
        "javascript": has(r"(?<!\w)javascript(?!\w)"),
        "redux": has(r"(?<!\w)redux(?!\w)"),
        "tanstack": has(r"(?<!\w)tanstack(?:\s+query)?(?!\w)"),
        "graphql": has(r"(?<!\w)graphql(?!\w)"),
        "apollo": has(r"(?<!\w)apollo(?!\w)"),
        "node": has(r"(?<!\w)node(?:\.js|js)?(?!\w)"),
        "express": has(r"(?<!\w)express(?:\.js|js)?(?!\w)"),
        "mongodb": has(r"(?<!\w)mongodb(?!\w)"),
        "mern": has(r"(?<!\w)mern(?!\w)"),
        "tailwind": has(r"(?<!\w)tailwind(?:\s+css)?(?!\w)"),
        "mui": has(r"(?<!\w)(?:material\s+ui|mui)(?!\w)"),
        "websockets": has(r"(?<!\w)(?:websocket|websockets|socket\.io|socketio)(?!\w)"),
        "html": has(r"(?<!\w)html5?(?!\w)"),
        "css": has(r"(?<!\w)css3?(?!\w)"),
    }

    # If a Profile is available, require actual overlap with configured skills.
    # Generic words such as HTML/CSS/Git are not enough by themselves.
    profile_terms = set()
    if profile is not None:
        for key in ("skills_primary", "skills_adjacent"):
            for skill in profile.data.get(key, []) or []:
                profile_terms.add(str(skill).lower())

    strong_frontend = (
        skills["react"]
        or skills["next"]
        or skills["typescript"] and skills["javascript"]
        or skills["redux"]
        or skills["tanstack"]
    )

    fullstack_js = (
        skills["mern"]
        or (skills["react"] and skills["node"])
        or (skills["react"] and skills["node"] and skills["express"])
        or (skills["react"] and skills["node"] and skills["mongodb"])
    )

    react_native = "react native" in text or "react-native" in text
    web_react_signals = (
    skills["next"]
    or skills["typescript"]
    or skills["redux"]
    or skills["tanstack"]
    or skills["node"]
    or skills["express"]
    or skills["graphql"]
    or skills["apollo"]
    or skills["mongodb"]
    or skills["mern"]
    )
    if react_native and not web_react_signals:
     return "SKIP_REACT_NATIVE"

    # Competing primary stacks are still relevant only when the job content
    # substantively includes the user's React/frontend skills.
    java = has(r"(?<!\w)java(?!script)(?!\w)")
    dotnet = has(r"(?<!\w)\.net(?!\w)") or has(r"(?<!\w)c#(?!\w)")
    angular = has(r"(?<!\w)angular(?!\w)")
    python = has(r"(?<!\w)python(?!\w)")

    if fullstack_js:
        return "HIGH_FULLSTACK_JAVASCRIPT"

    if strong_frontend and (java or dotnet or angular):
        return "MEDIUM_REACT_COMPETING_STACK"

    if strong_frontend and python:
        return "MEDIUM_REACT_PYTHON"

    # Count meaningful configured/core skills found in the actual content.
    core_matches = sum([
        skills["react"],
        skills["next"],
        skills["typescript"],
        skills["javascript"],
        skills["redux"],
        skills["tanstack"],
        skills["graphql"],
        skills["apollo"],
        skills["node"],
        skills["express"],
        skills["mongodb"],
        skills["mern"],
        skills["tailwind"],
        skills["mui"],
        skills["websockets"],
    ])

    # Explicitly frontend-oriented content with at least one strong skill.
    frontend_context = any(
        phrase in text
        for phrase in [
            "frontend", "front end", "front-end",
            "user interface", "ui development", "web application",
            "responsive web", "client-side",
        ]
    )

    if strong_frontend and frontend_context:
        return "HIGH_REACT_FRONTEND"

    if strong_frontend and core_matches >= 2:
        return "MEDIUM_REACT_SOFTWARE_ENGINEER"

    # If configured profile skills are present but only weakly, don't auto-apply.
    # This keeps incidental mentions from becoming applications.
    if profile_terms:
        meaningful_profile_matches = 0
        for term in profile_terms:
            normalized = term.strip()
            if len(normalized) >= 3 and normalized in text:
                meaningful_profile_matches += 1
        if meaningful_profile_matches >= 2 and core_matches >= 1:
            return "MEDIUM_REACT_SOFTWARE_ENGINEER"

    if core_matches >= 1:
        return "LOW_REACT_MINOR"

    return "SKIP_NO_RELEVANT_PROFILE_SKILLS"

def check_apply_button(page) -> str:
    """Returns 'external', 'native', or 'none' based on the detail page's apply button."""
    if page.query_selector('#company-site-button'):
        return "external"
    if page.query_selector('#apply-button'):
        return "native"
    return "none"


def _wait_send_enabled(page, timeout_ms: int = 4000) -> bool:
    """Polls until the Send control's wrapper no longer has Naukri's
    'disabled' class. Confirmed real markup (from a debug HTML dump you
    sent): <div id="sendMsg__..." class="send disabled"> wraps the
    clickable <div class="sendMsg">Save</div>. It starts disabled and only
    becomes clickable after Naukri's frontend registers your selection and
    re-renders -- clicking Send before that happens is a silent no-op,
    which is what was causing radio/checkbox answers to never actually save."""
    waited = 0
    step = 300
    while waited <= timeout_ms:
        enabled = safe_evaluate(page, """
            () => {
                const wrapper = document.querySelector('[id^="sendMsg__"]');
                if (!wrapper) return true;  // no wrapper found -- don't block forever on a guess
                return !wrapper.className.includes('disabled');
            }
        """, default=True)
        if enabled:
            return True
        time.sleep(step / 1000)
        waited += step
    return False


def _js_click_send(page) -> bool:
    """Clicks Naukri's screening-chat Send/Save control -- a <div class="sendMsg">,
    not a <button>. A JS click bypasses the chatbot_Overlay div that sits
    visually on top of it and blocks Playwright's normal .click()."""
    return safe_evaluate(page, """
        () => {
            const el = document.querySelector('.sendMsg');
            if (!el) return false;
            el.click();
            return true;
        }
    """, default=False)


def click_native_apply(page) -> bool:
    """Clicks the Apply button and returns whether the click actually
    registered, so the caller can tell 'click failed' apart from 'clicked
    fine, just couldn't confirm success afterward' -- those need different
    handling."""
    return bool(safe_evaluate(page, """
        () => {
            const btn = document.getElementById('apply-button');
            if (btn) { btn.click(); return true; }
            return false;
        }
    """, default=False))


def page_has_stop_signal(page) -> str | None:
    try:
        text = page.inner_text("body").lower()
    except Exception:
        return None  # page mid-navigation -- checked again on the next loop iteration
    for phrase in STOP_PHRASES:
        if phrase in text:
            return phrase
    if "login" in page.url and "naukri.com/nlogin" in page.url:
        return "session expired / login prompt"
    return None


def _save_debug_screenshot(page, job_title: str) -> str:
    """Saves a screenshot when the outcome is uncertain, so it can be looked
    at afterward instead of needing to catch it live. Also saves the page's
    HTML for the same reason — a screenshot shows what it looked like, the
    HTML shows exactly why the confirmation-text check missed it."""
    debug_dir = Path("debug_screenshots")
    debug_dir.mkdir(exist_ok=True)
    safe_name = "".join(c if c.isalnum() else "_" for c in (job_title or "unknown"))[:60]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    png_path = debug_dir / f"{safe_name}_{timestamp}.png"
    html_path = debug_dir / f"{safe_name}_{timestamp}.html"
    try:
        page.screenshot(path=str(png_path))
    except Exception as e:
        print(f"  (couldn't save debug screenshot: {e})")
    try:
        html_path.write_text(page.content())
    except Exception as e:
        print(f"  (couldn't save debug HTML: {e})")
    return str(png_path)


def verify_applied(page) -> bool:
    """Best-effort check that the application actually went through. Confirmed
    real pattern: Naukri shows a green checkmark panel reading
    'Applied to "<job title>"' a few seconds after submit -- checking for
    that prefix specifically, plus a short wait since it isn't instant."""
    try:
        page.wait_for_timeout(3000)  # the confirmation panel takes a moment to appear
    except Exception:
        pass
    try:
        text = page.inner_text("body").lower()
    except Exception:
        return False
    success_phrases = [
        'applied to "', "application sent", "successfully applied",
        "you have applied", "applied successfully",
    ]
    if any(p in text for p in success_phrases):
        return True
    btn = page.query_selector('#apply-button')
    if btn:
        try:
            label = btn.inner_text().strip().lower()
            if label and label != "apply":
                return True
        except Exception:
            pass
    return False


class StopRun(Exception):
    """Something genuinely dangerous or account-risking happened -- CAPTCHA,
    login expired, rate-limit warning. Halts the entire run immediately."""


class SkipJob(Exception):
    """This one listing can't be completed -- logs it and moves to the next
    listing. Does NOT stop the run."""


def _get_options(page) -> list[dict]:
    """Reads radio/checkbox options in the chat drawer, with their visible labels."""
    return safe_evaluate(page, """
        () => {
            const root = document.querySelector('[class*="chatbot_Drawer"]') || document;
            const inputs = Array.from(root.querySelectorAll('input[type=radio], input[type=checkbox]'));
            return inputs.map((el, idx) => {
                let label = '';
                if (el.id) {
                    const lbl = root.querySelector(`label[for="${el.id}"]`);
                    if (lbl) label = lbl.innerText.trim();
                }
                if (!label) {
                    const parentLabel = el.closest('label');
                    if (parentLabel) label = parentLabel.innerText.trim();
                }
                if (!label && el.nextElementSibling) {
                    label = (el.nextElementSibling.innerText || '').trim();
                }
                return {idx, label, type: el.type};
            });
        }
    """, default=[]) or []


def _click_option(page, idx: int) -> bool:
    return safe_evaluate(page, """
        (idx) => {
            const root = document.querySelector('[class*="chatbot_Drawer"]') || document;
            const inputs = Array.from(root.querySelectorAll('input[type=radio], input[type=checkbox]'));
            if (inputs[idx]) { inputs[idx].click(); return true; }
            return false;
        }
    """, arg=idx, default=False)


def _is_sensitive_field(question: str) -> bool:
    lower_q = question.lower()
    return any(hint in lower_q for hint in SENSITIVE_FIELD_HINTS)


def _auto_decide_option(question: str, options: list[dict], profile: Profile) -> dict | None:
    """Tries to pick the correct option using known profile facts, for
    common Yes/No-style questions. Returns None (never guesses) if nothing
    in the profile clearly answers this specific question -- caller falls
    back to asking you directly rather than risk a wrong click."""
    lower_q = question.lower()
    by_label = {o["idx"]: o["label"].strip().lower() for o in options}

    def find_by_text(text: str):
        for idx, label in by_label.items():
            if label == text.lower():
                return next(o for o in options if o["idx"] == idx)
        return None

    rules = [
        (["relocate", "relocation", "willing to move"],
         "Yes" if profile.data.get("relocate_cities") else "No"),
        (["night shift"], "Yes" if profile.data.get("night_shift_ok") else "No"),
        (["weekend"], "Yes" if profile.data.get("weekend_ok") else "No"),
        (["immediately available", "immediate joiner"],
         "Yes" if profile.data.get("immediately_available") else "No"),
        (["currently employed", "currently working"],
         "Yes" if profile.data.get("current_employer") else "No"),
    ]
    for triggers, desired in rules:
        if any(t in lower_q for t in triggers):
            match = find_by_text(desired)
            if match:
                return match
    return None


def _handle_options_question(page, question: str, profile: Profile, timeout_s: int) -> bool:
    """Returns True if handled (clicked something), raises SkipJob otherwise."""
    options = _get_options(page)
    if not options:
        return False

    stored = learned_answers.get_answer(question)
    if stored:
        for opt in options:
            if opt["label"].strip().lower() == stored.strip().lower():
                _click_option(page, opt["idx"])
                print(f"  (used a remembered answer for: {question[:80]})")
                return True

    auto = _auto_decide_option(question, options, profile)
    if auto:
        _click_option(page, auto["idx"])
        learned_answers.save_answer(question, auto["label"])
        print(f"  (auto-picked '{auto['label']}' from your profile for: {question[:80]})")
        return True

    options_text = "\n".join(f"  {o['idx']}: {o['label']}" for o in options)
    response = ask_user(
        f"Screening question needs a choice:\n{question}\n\nOptions:\n{options_text}\n"
        f"Type the number of your choice (or numbers separated by commas for multi-select):",
        timeout_seconds=timeout_s,
    )
    if response is None:
        raise SkipJob(f"no response for options question: {question[:120]}")

    chosen_raw = [r.strip() for r in response.split(",") if r.strip()]
    matches = []
    for r in chosen_raw:
        try:
            idx = int(r)
            match = next((o for o in options if o["idx"] == idx), None)
        except ValueError:
            match = next((o for o in options if o["label"].strip().lower() == r.lower()), None)
        if match:
            matches.append(match)

    if not matches:
        raise SkipJob(f"couldn't match your response '{response}' to an option: {question[:120]}")

    for match in matches:
        _click_option(page, match["idx"])
    learned_answers.save_answer(question, matches[0]["label"] if len(matches) == 1 else response)
    return True


# If the chat's last message is one of these, it's wrapping up rather than
# asking something new -- stop cleanly instead of trying to draft an answer
# into a box that may no longer exist.
COMPLETION_PHRASES = [
    "thank you", "thanks for your response", "thanks for your time",
    "we will get back", "responses have been recorded", "no further questions",
    "application submitted", "that's all", "all the information we need",
]


def _is_completion_message(text: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in COMPLETION_PHRASES)


def _has_answerable_input(page, timeout_ms: int = 3000) -> bool:
    """Checks for a text box or radio/checkbox to answer. Polls for up to
    timeout_ms instead of checking once -- the previous single-check version
    could wrongly conclude "nothing to answer" if the next question's input
    just hadn't rendered yet after the previous Save click, causing it to
    skip clicking Save on what was actually still a real question."""
    waited = 0
    step = 300
    while waited <= timeout_ms:
        found = safe_evaluate(page, """
            () => !!(document.querySelector('[id^="userInput"], [contenteditable="true"]') ||
                     document.querySelector('input[type=radio], input[type=checkbox]'))
        """, default=False)
        if found:
            return True
        time.sleep(step / 1000)
        waited += step
    return False


def _read_filled_text(page) -> str:
    return safe_evaluate(page, """
        () => {
            const ed = document.querySelector('[id^="userInput"], [contenteditable="true"]');
            return ed ? (ed.innerText || ed.textContent || '').trim() : '';
        }
    """, default="") or ""


def _fill_and_send(page, text: str, question: str):
    """Fills the answer box, VERIFIES the text actually landed before
    clicking Send, then sends. This is the fix for answers going through
    blank: previously Send could fire even if the fill silently failed
    (a timing hiccup, or the box wasn't there), which is what produces
    Naukri's "incomplete information" rejection on the final application."""
    _fill_freetext(page, text)
    time.sleep(0.4)
    filled = _read_filled_text(page)
    if not filled:
        _fill_freetext(page, text)  # one retry -- could be a focus/timing hiccup
        time.sleep(0.6)
        filled = _read_filled_text(page)
    if not filled:
        raise SkipJob(f"couldn't confirm the answer registered before sending: {question[:120]}")
    _wait_send_enabled(page)  # same disabled-until-registered pattern as the options branch
    _js_click_send(page)
    time.sleep(2.0)  # give Naukri's backend a moment to actually save it


def answer_screening_chat(page, profile: Profile, job_context: str, timeout_s: int):
    """Handles Naukri's post-apply screening chat drawer, if it appears."""
    answers = profile.answer_library()
    try:
        # Broadened on purpose: a pure radio/checkbox question has no text
        # box at all, so waiting only for contenteditable was causing the
        # function to give up immediately on those questions, thinking
        # there was no screening chat when there actually was one.
        page.wait_for_selector(
            '[contenteditable="true"], [contenteditable=""], '
            'input[type=radio], input[type=checkbox], .botMsg',
            timeout=4000,
        )
    except PWTimeout:
        return  # no screening chat for this listing

    for _ in range(15):
        stop = page_has_stop_signal(page)
        if stop:
            raise StopRun(f"stop signal during screening chat: {stop}")

        bubbles = page.query_selector_all('.botMsg')
        if not bubbles:
            break
        try:
            question = bubbles[-1].inner_text().strip()
        except Exception:
            break  # page likely navigated away mid-read; treat as chat finished
        if not question:
            break

        if _is_completion_message(question):
            time.sleep(1.5)  # let the "Applied" confirmation redirect begin before we check for it
            break  # chat is wrapping up, not asking a new question

        if not _has_answerable_input(page):
            break  # nothing to fill or click here — informational message only

        options = _get_options(page)
        if options:
            _handle_options_question(page, question, profile, timeout_s)
            if not _wait_send_enabled(page):
                raise SkipJob(f"Send button stayed disabled after selecting an option "
                               f"(selection may not have registered): {question[:120]}")
            _js_click_send(page)
            time.sleep(2.0)
            continue

        stored = learned_answers.get_answer(question)
        if stored:
            _fill_and_send(page, stored, question)
            print(f"  (used a remembered answer for: {question[:80]})")
            continue

        lower_q = question.lower()
        answered = False
        for key, phrases in TRIGGER_PHRASES.items():
            if key not in answers:
                continue
            if any(phrase in lower_q for phrase in phrases):
                _fill_and_send(page, str(answers[key]), question)
                answered = True
                break

        if answered:
            continue

        if _is_sensitive_field(question):
            response = ask_user(f"Screening question (personal detail):\n{question}", timeout_seconds=timeout_s)
            if response is None:
                raise SkipJob(f"no response for sensitive field: {question[:120]}")
            _fill_and_send(page, response, question)
            learned_answers.save_answer(question, response)
            continue

        draft = llm.draft_answer(question, profile.data, job_context)
        if draft.startswith("[NEEDS_HUMAN_INPUT"):
            response = ask_user(f"Screening question (AI couldn't answer from your profile):\n{question}",
                                 timeout_seconds=timeout_s)
            if response is None:
                raise SkipJob(f"no response for: {question[:120]}")
            _fill_and_send(page, response, question)
            learned_answers.save_answer(question, response)
        else:
            _fill_and_send(page, draft, question)


def _fill_freetext(page, text: str):
    safe_evaluate(page, """
        (text) => {
            const ed = document.querySelector('[id^="userInput"], [contenteditable="true"]');
            if (!ed) return;
            ed.focus();
            document.execCommand('insertText', false, text);
        }
    """, arg=text)


def run():
    profile = Profile.load()
    if not Path(SESSION_FILE).exists():
        raise SystemExit(f"{SESSION_FILE} not found. Run: python login_capture.py naukri")

    human_timeout = profile.data.get("human_input_timeout_seconds", 120)
    max_pages = profile.data.get("max_pages_per_role", 5)

    applied = 0
    processed_job_ids = load_processed_job_ids()

    with sync_playwright() as p:
        browser_mode = profile.data.get("browser_mode", "visible")
        if browser_mode == "headless":
            browser = p.chromium.launch(headless=True, slow_mo=150)
        elif browser_mode == "minimized":
            browser = p.chromium.launch(headless=False, slow_mo=150, args=["--start-minimized"])
        else:
            browser = p.chromium.launch(headless=False, slow_mo=150)
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        for role in profile.target_roles:
            if applied >= profile.stop_after_n_applications:
                break

            slug = role.lower().replace(" ", "-")
            exp_param = int(profile.total_experience_years)
            seen_job_ids = set()
            stopped_entirely = False

            for page_no in range(1, max_pages + 1):
                if applied >= profile.stop_after_n_applications:
                    break

                # Confirmed pattern: Naukri appends "-N" directly to the slug
                # for page N (page 1 has no suffix), e.g.
                # azure-data-engineer-jobs-2 for page 2.
                page_suffix = "" if page_no == 1 else f"-{page_no}"
                url = (
                    f"https://www.naukri.com/{slug}-jobs{page_suffix}"
                    f"?experience={exp_param}"
                    f"&jobAge={profile.job_freshness_days}"
                )
                print(f"\n--- Searching: {role}, page {page_no} ({url}) ---")
                try:
                    page.goto(url)
                    page.wait_for_selector('.srp-jobtuple-wrapper[data-job-id]', timeout=10000)
                except PWTimeout:
                    pass
                except Exception as e:
                    print(f"  (navigation error, treating as end of results for this role: {e})")
                    break
                time.sleep(1)

                stop = page_has_stop_signal(page)
                if stop:
                    print(f"STOPPING: {stop}")
                    log_row([datetime.now(), "naukri", "-", "-", "stopped", stop])
                    stopped_entirely = True
                    break

                cards = enumerate_cards(page)
                new_cards = [c for c in cards if c.get("jobId") not in seen_job_ids]
                print(f"Found {len(cards)} job cards ({len(new_cards)} new) on page {page_no}.")

                if not new_cards:
                    print("No new listings on this page -- treating as the last page for this role.")
                    break

                for card in new_cards:
                    seen_job_ids.add(card.get("jobId"))
                    if applied >= profile.stop_after_n_applications:
                        break

                    job_id = (card.get("jobId") or "").strip()
                    job_url = (card.get("href") or "").strip()

                    if job_id and job_id in processed_job_ids:
                        log_row([
                            datetime.now(), "naukri", card.get("title"),
                            card.get("company"), "skipped",
                            "already processed"
                        ])
                        print(
                            f"Skipped: {card.get('title')} @ {card.get('company')} "
                            f"— already processed"
                        )
                        continue

                    if job_url:
                        try:
                            if external_job_url_exists(job_url):
                                if job_id:
                                    record_processed_job(card, "EXTERNAL_ALREADY_LOGGED")
                                    processed_job_ids.add(job_id)

                                log_row([
                                    datetime.now(), "naukri", card.get("title"),
                                    card.get("company"), "skipped",
                                    "external URL already logged"
                                ])
                                print(
                                    f"Skipped: {card.get('title')} @ {card.get('company')} "
                                    f"— external URL already logged"
                                )
                                continue
                        except Exception as e:
                            print(f"  (Google Sheets dedup check failed: {e})")

                    ok, reason = passes_filters(card, profile, role)
                    if not ok:
                        log_row([datetime.now(), "naukri", card.get("title"),
                                  card.get("company"), "skipped", reason])
                        print(f"Skipped: {card.get('title')} @ {card.get('company')} — {reason}")
                        continue

                    try:
                        page.goto(card["href"])
                        time.sleep(2)

                        job_details = extract_job_details(page)
                        print(
                            f"Job details: description={len(job_details['description'])} chars, "
                            f"key_skills={len(job_details['key_skills'])} chars"
                        )
                        quality = classify_job_quality(
                            card.get("title", ""),
                            job_details["description"],
                            job_details["key_skills"],
                            profile,
                        )

                        print(f"Quality: {quality}")

                        allowed_quality = {
                            "HIGH_REACT_FRONTEND",
                            "HIGH_FULLSTACK_JAVASCRIPT",
                            "MEDIUM_REACT_SOFTWARE_ENGINEER",
                            "MEDIUM_REACT_PYTHON",
                        }

                        if quality not in allowed_quality:
                            log_row([
                                datetime.now(),
                                "naukri",
                                card.get("title", ""),
                                card.get("company", ""),
                                "skipped",
                                f"quality={quality}",
                            ])
                            print(f"SKIP: quality={quality}")
                            continue

                        stop = page_has_stop_signal(page)
                        if stop:
                            raise StopRun(f"stop signal: {stop}")

                        apply_state = check_apply_button(page)
                        if apply_state == "external":
                            log_external_job(card)

                            if job_id:
                                record_processed_job(card, "EXTERNAL_PENDING")
                                processed_job_ids.add(job_id)

                            log_row([datetime.now(), "naukri", card.get("title"),
                                     card.get("company"), "skipped", "external apply"])
                            print(f"Skipped: {card.get('title')} @ {card.get('company')} — external apply")
                            continue
                        if apply_state == "none":
                            log_row([datetime.now(), "naukri", card.get("title"),
                                      card.get("company"), "skipped", "no apply button found"])
                            print(f"Skipped: {card.get('title')} @ {card.get('company')} — no apply button found")
                            continue

                        clicked = click_native_apply(page)
                        if not clicked:
                            log_row([datetime.now(), "naukri", card.get("title"),
                                      card.get("company"), "skipped", "apply button click didn't register"])
                            print(f"Skipped: {card.get('title')} @ {card.get('company')} — apply click didn't register")
                            continue
                        time.sleep(2)

                        answer_screening_chat(page, profile, f"{card.get('title')} at {card.get('company')}",
                                               human_timeout)
                        time.sleep(1.5)

                        if verify_applied(page):
                            applied += 1

                            if job_id:
                                record_processed_job(card, "APPLIED")
                                processed_job_ids.add(job_id)

                            log_row([datetime.now(), "naukri", card.get("title"),
                                      card.get("company"), "applied", ""])
                            print(f"Applied: {card.get('title')} @ {card.get('company')} ({applied} total)")
                        else:
                            shot_path = _save_debug_screenshot(page, card.get("title"))
                            log_row([datetime.now(), "naukri", card.get("title"),
                                      card.get("company"), "uncertain",
                                      f"couldn't confirm submission — screenshot saved to {shot_path}"])
                            print(f"UNCERTAIN: {card.get('title')} @ {card.get('company')} — "
                                  f"couldn't confirm the application actually went through. Check it manually.")

                    except SkipJob as e:
                        log_row([datetime.now(), "naukri", card.get("title"),
                                  card.get("company"), "skipped", str(e)])
                        print(f"Skipped: {card.get('title')} @ {card.get('company')} — {e}")
                        continue

                    except StopRun as e:
                        print(f"STOPPING: {e}")
                        log_row([datetime.now(), "naukri", card.get("title"),
                                  card.get("company"), "stopped", str(e)])
                        browser.close()
                        return

                    except Exception as e:
                        # Anything unexpected (stray Playwright errors, torn-down
                        # page contexts, etc.) -- log it and move to the next
                        # listing instead of crashing the whole run.
                        log_row([datetime.now(), "naukri", card.get("title"),
                                  card.get("company"), "skipped", f"unexpected error: {e}"])
                        print(f"Skipped (unexpected error): {card.get('title')} @ {card.get('company')} — {e}")
                        continue

                    time.sleep(profile.pace_seconds_between_actions)

                if stopped_entirely:
                    break

            if stopped_entirely:
                break

        browser.close()

    print(f"\nDone. {applied} applications submitted this run. See {LOG_FILE} for the full log.")


if __name__ == "__main__":
    run()
