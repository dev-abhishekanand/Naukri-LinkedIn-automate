"""
LinkedIn job discovery and safe Easy Apply automation.

Requires session_linkedin.json from login_capture.py.

Safety rules:
- Stop the entire run on CAPTCHA, login/checkpoint, security verification,
  Easy Apply limits, or other account-risk signals.
- A job must pass profile-based qualification before application is attempted.
- Easy Apply answers come only from the profile or learned answers. Unknown
  questions are never invented; the current listing is stopped for manual help.
- External/company-site applications are discovery/manual-action records; they
  are not automatically submitted by this script.

Usage:
    python linkedin_apply.py
    python linkedin_apply.py --discovery-only
    python linkedin_apply.py --retry-unsubmitted
"""
import csv
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from common import learned_answers
from common.profile import Profile

SESSION_FILE = "session_linkedin.json"
LOG_FILE = "applications_log.csv"
LINKEDIN_PROCESSED_FILE = "linkedin_processed_jobs.csv"

STOP_PHRASES = [
    "easy apply limit",
    "unusual activity",
    "verify it's you",
    "captcha",
    "security verification",
    "we've restricted",
    "account restricted",
    "temporarily restricted",
    "automated activity",
]

UNRELATED_TITLE_PATTERNS = [
    r"\bdata scientist\b",
    r"\bdata engineer\b",
    r"\bdevops\b",
    r"\bsite reliability\b",
    r"\bsre\b",
    r"\bjava developer\b",
    r"\bjava engineer\b",
    r"\b\.net developer\b",
    r"\bc# developer\b",
    r"\bangular developer\b",
    r"\bphp developer\b",
    r"\bruby developer\b",
    r"\bpython developer\b",
    r"\bmachine learning\b",
    r"\bml engineer\b",
    r"\bqa engineer\b",
    r"\btest engineer\b",
    r"\bqa automation\b",
    r"\bwordpress\b",
    r"\bshopify\b",
    r"\bmagento\b",
]

TARGET_TITLE_PATTERNS = [
    r"\breact(?:\.js|js)?\b",
    r"\bfrontend\b",
    r"\bfront[- ]end\b",
    r"\bnext(?:\.js|js)?\b",
    r"\bfull[- ]?stack\b",
    r"\bmern\b",
    r"\bui developer\b",
    r"\bweb developer\b",
]

INTERN_TITLE_PATTERNS = [
    r"\bintern\b",
    r"\binternship\b",
    r"\btrainee\b",
    r"\bfresher\b",
    r"\bstudent\b",
]

NEGATIVE_TECH_PATTERNS = [
    r"\bangular(?:\.js|js)?\b",
    r"\bvue(?:\.js|js)?\b",
    r"\bsvelte(?:\.js|js)?\b",
    r"\bember(?:\.js|js)?\b",
    r"\bbackbone(?:\.js|js)?\b",
    r"\breact native\b",
    r"\breact-native\b",
    r"\bflutter\b",
    r"\bionic\b",
]

PRIMARY_WEB_REACT_PATTERNS = [
    r"\breact(?:\.js|js)?\b",
    r"\bnext(?:\.js|js)?\b",
]

SUPPORTING_FRONTEND_PATTERNS = [
    r"\btypescript\b",
    r"\bjavascript\b",
    r"\bredux\b",
    r"\btanstack\b",
    r"\bgraphql\b",
    r"\bapollo\b",
    r"\bnode(?:\.js|js)?\b",
    r"\bexpress(?:\.js|js)?\b",
    r"\bmongodb\b",
    r"\bmern\b",
    r"\btailwind(?:\s+css)?\b",
    r"\bmaterial ui\b|\bmui\b",
    r"\bwebsockets?\b|\bsocket\.io\b",
]

FRESHNESS_DAYS = 2
MAX_LINKEDIN_APPLICATIONS_PER_RUN = 5
DRY_RUN = os.getenv("LINKEDIN_DRY_RUN", "true").strip().lower() not in {"0", "false", "no"}


def _cli_flag(name: str) -> bool:
    return name in sys.argv


def print_usage():
    print(
        "Usage: python linkedin_apply.py [--discovery-only] [--retry-unsubmitted]\n"
        "  --discovery-only   Search and qualify without applying or changing processed state.\n"
        "  --retry-unsubmitted Reconsider prior dry-run/manual-action records; never retry APPLIED/SKIPPED."
    )



def log_row(row: list):
    new_file = not Path(LOG_FILE).exists()
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["timestamp", "source", "title", "company", "status", "reason"])
        w.writerow(row)


def linkedin_job_id(job_url: str) -> str:
    match = re.search(r"/jobs/view/(\d+)", job_url or "")
    if match:
        return match.group(1)
    return (job_url or "").rstrip("/").split("/")[-1].split("?")[0]


def load_linkedin_processed_jobs() -> dict[str, dict]:
    path = Path(LINKEDIN_PROCESSED_FILE)
    if not path.exists():
        return {}

    with path.open(newline="") as f:
        return {
            row["job_id"]: row
            for row in csv.DictReader(f)
            if row.get("job_id")
        }


def record_linkedin_job(
    job_id: str,
    title: str,
    company: str,
    status: str,
    job_url: str,
):
    new_file = not Path(LINKEDIN_PROCESSED_FILE).exists()
    with open(LINKEDIN_PROCESSED_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow([
                "job_id",
                "title",
                "company",
                "status",
                "processed_at",
                "job_url",
            ])
        w.writerow([
            job_id,
            title,
            company,
            status,
            datetime.now().isoformat(timespec="seconds"),
            job_url,
        ])


def log_linkedin_external_job(
    job_id: str,
    title: str,
    company: str,
    location: str,
    job_url: str,
    status: str = "PENDING",
):
    """Log a LinkedIn external/manual application without changing Naukri logging."""
    try:
        # Reuse only the finalized logger's connection and sheet-schema handling.
        # Do not call append_external_job(), because that function is intentionally
        # Naukri-specific and writes platform="naukri".
        from google_sheets_logger import _ensure_headers, _get_sheet

        sheet = _get_sheet()
        _ensure_headers(sheet)

        sheet.append_row([
            datetime.now().isoformat(timespec="seconds"),
            "linkedin",
            job_id,
            title,
            company,
            location,
            "",
            job_url,
            status,
            "LinkedIn external/company-site application - manual completion required",
            "",
            "",
            "",
        ])
        return True
    except Exception as exc:
        print(f"WARNING: Google Sheets external-job logging failed: {exc}")
        log_row([
            datetime.now(),
            "linkedin",
            title,
            company,
            "sheet_logging_failed",
            str(exc),
        ])
        return False


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _extract_experience_range(text: str) -> tuple[float | None, float | None]:
    text = _normalize(text)

    ranges = re.findall(
        r"(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*years?",
        text,
        re.IGNORECASE,
    )
    if ranges:
        low, high = ranges[0]
        return float(low), float(high)

    plus = re.search(
        r"(?:minimum|min(?:imum)?|at least|more than)\s*(\d+(?:\.\d+)?)\s*\+?\s*years?",
        text,
        re.IGNORECASE,
    )
    if plus:
        return float(plus.group(1)), None

    simple_plus = re.search(r"\b(\d+(?:\.\d+)?)\s*\+\s*years?", text)
    if simple_plus:
        return float(simple_plus.group(1)), None

    return None, None


def _extract_location_signals(text: str) -> set[str]:
    normalized = _normalize(text)
    signals = set()
    if "remote" in normalized or "work from home" in normalized or "wfh" in normalized:
        signals.add("remote")

    known = [
        "patna",
        "hyderabad",
        "pune",
        "noida",
        "greater noida",
        "delhi",
        "new delhi",
        "gurgaon",
        "gurugram",
        "bengaluru",
        "bangalore",
    ]
    for city in known:
        if re.search(rf"\b{re.escape(city)}\b", normalized):
            signals.add(city)

    if normalized and not signals:
        signals.add("other")
    return signals


def _extract_freshness_days(text: str) -> float | None:
    normalized = _normalize(text)

    if re.search(r"\bjust now\b|\bmoments? ago\b|\btoday\b", normalized):
        return 0.0
    if re.search(r"\byesterday\b", normalized):
        return 1.0

    minutes = re.search(r"(\d+)\s+minutes?\s+ago", normalized)
    if minutes:
        return 0.0

    hours = re.search(r"(\d+)\s+hours?\s+ago", normalized)
    if hours:
        return float(hours.group(1)) / 24.0

    days = re.search(r"(\d+(?:\.\d+)?)\s+days?\s+ago", normalized)
    if days:
        return float(days.group(1))

    weeks = re.search(r"(\d+(?:\.\d+)?)\s+weeks?\s+ago", normalized)
    if weeks:
        return float(weeks.group(1)) * 7.0

    return None


def _title_relevance(title: str, profile: Profile) -> tuple[bool, str]:
    normalized = _normalize(title)

    if _matches_any(normalized, INTERN_TITLE_PATTERNS):
        return False, "internship/trainee/fresher role"

    if _matches_any(normalized, UNRELATED_TITLE_PATTERNS):
        if not _matches_any(
            normalized,
            [r"\breact(?:\.js|js)?\b", r"\bnext(?:\.js|js)?\b", r"\bmern\b"],
        ):
            return False, "unrelated primary role"

    configured_patterns = []
    role_keywords = profile.data.get("role_required_keywords", {}) or {}
    for keywords in role_keywords.values():
        configured_patterns.extend(str(k) for k in (keywords or []))

    if configured_patterns and _matches_any(
        normalized, [re.escape(k.lower()) for k in configured_patterns]
    ):
        return True, "title matches configured target role"

    if _matches_any(normalized, TARGET_TITLE_PATTERNS):
        return True, "title contains a target frontend/React signal"

    return False, "title lacks a configured target-role signal"


def _has_pattern(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text, re.IGNORECASE))


def _framework_signals(skill_text: str) -> dict:
    return {
        "react": _has_pattern(skill_text, r"\breact(?:\.js|js)?\b"),
        "next": _has_pattern(skill_text, r"\bnext(?:\.js|js)?\b"),
        "typescript": _has_pattern(skill_text, r"\btypescript\b|\bts\b"),
        "javascript": _has_pattern(skill_text, r"\bjavascript\b|\bjs\b"),
        "redux": _has_pattern(skill_text, r"\bredux\b"),
        "node": _has_pattern(skill_text, r"\bnode(?:\.js|js)?\b"),
        "express": _has_pattern(skill_text, r"\bexpress(?:\.js|js)?\b"),
        "graphql": _has_pattern(skill_text, r"\bgraphql\b|\bapollo\b"),
        "mongodb": _has_pattern(skill_text, r"\bmongodb\b"),
        "mern": _has_pattern(skill_text, r"\bmern\b"),
        "angular": _has_pattern(skill_text, r"\bangular(?:\.js|js)?\b"),
        "vue": _has_pattern(skill_text, r"\bvue(?:\.js|js)?\b"),
        "svelte": _has_pattern(skill_text, r"\bsvelte\b"),
        "react_native": _has_pattern(skill_text, r"\breact native\b|\breact-native\b"),
        "flutter": _has_pattern(skill_text, r"\bflutter\b"),
    }


def qualify_linkedin_job(
    title: str,
    description: str,
    profile: Profile,
    location: str = "",
) -> tuple[bool, str, dict]:
    """Strictly qualify a LinkedIn web job without guessing missing facts."""
    title_ok, title_reason = _title_relevance(title, profile)
    if not title_ok:
        return False, title_reason, {"quality": "SKIP_TITLE"}

    text = _normalize(f"{title} {description}")
    skill_text = _normalize(description)
    signals = _framework_signals(skill_text)

    # A real React/Next signal must exist in the JD for frontend/full-stack roles.
    target_web = signals["react"] or signals["next"] or signals["mern"]

    # Reject mobile-only or competing-framework roles unless React web is also explicit.
    competing = [
        name for name in ("angular", "vue", "svelte", "flutter", "react_native")
        if signals[name]
    ]
    if competing and not target_web:
        return False, "job is centered on a non-target framework", {
            "quality": "SKIP_NON_TARGET_FRONTEND",
            "frameworks": competing,
        }

    if not target_web:
        return False, "description does not contain a React/Next.js/MERN web signal", {
            "quality": "SKIP_NO_REACT_WEB_SIGNAL",
        }

    # Reject roles whose title is explicitly led by a competing frontend/mobile
    # framework unless the title itself also names the target stack. This avoids
    # accepting Angular/Vue/etc. jobs merely because React appears in a long JD.
    title_normalized = _normalize(title)
    title_has_target_stack = _has_pattern(
        title_normalized, r"\breact(?:\.js|js)?\b|\bnext(?:\.js|js)?\b|\bmern\b"
    )
    title_has_competing_stack = _has_pattern(
        title_normalized, r"\bangular(?:\.js|js)?\b|\bvue(?:\.js|js)?\b|\bsvelte\b|\bflutter\b|\breact native\b"
    )
    if title_has_competing_stack and not title_has_target_stack:
        return False, "title is led by a non-target framework", {
            "quality": "SKIP_NON_TARGET_TITLE",
            "frameworks": competing,
        }

    # If a competing frontend framework is present in the JD, require a strong
    # React/Next signal rather than accepting a single incidental mention.
    if competing and not signals["react"] and not signals["next"]:
        return False, "competing frontend framework without React/Next.js", {
            "quality": "SKIP_COMPETING_FRAMEWORK",
            "frameworks": competing,
        }
    if competing and signals["react"] and not signals["next"]:
        react_mentions = len(re.findall(r"\breact(?:\.js|js)?\b", skill_text))
        react_required = _has_pattern(
            skill_text,
            r"(required|must have|must-have|mandatory|strong experience|proficien|expert|years of experience).{0,100}\breact(?:\.js|js)?\b|\breact(?:\.js|js)?\b.{0,100}(required|must have|must-have|mandatory|strong experience|proficien|expert|years of experience)",
        )
        if react_mentions < 2 and not react_required:
            return False, "React is not a strong enough requirement in a competing-framework JD", {
                "quality": "SKIP_WEAK_REACT_SIGNAL",
                "frameworks": competing,
            }

    # Prevent unrelated jobs that happen to mention React once.
    frontend_context = _has_pattern(
        text,
        r"\bfrontend\b|\bfront[- ]end\b|\bweb\b|\breact\b|\bnext(?:\.js|js)?\b|\bui\b",
    )
    fullstack_context = _has_pattern(text, r"\bfull[- ]?stack\b|\bmern\b")
    if not frontend_context and not fullstack_context:
        return False, "insufficient frontend/full-stack context", {
            "quality": "SKIP_WEAK_CONTEXT",
        }

    supporting_matches = sum(
        bool(re.search(pattern, skill_text, re.IGNORECASE))
        for pattern in SUPPORTING_FRONTEND_PATTERNS
    )

    fullstack_signal = (
        fullstack_context
        and target_web
        and (
            signals["node"]
            or signals["express"]
            or signals["mongodb"]
            or signals["mern"]
        )
    )

    experience_min, experience_max = _extract_experience_range(description)
    candidate_years = float(profile.total_experience_years)
    floor = float(profile.seniority_floor_years)
    ceiling = float(profile.seniority_ceiling_years)

    if experience_min is not None and experience_min > candidate_years:
        return False, f"experience minimum {experience_min:g} years is above profile experience", {
            "quality": "SKIP_EXPERIENCE",
            "experience_min": experience_min,
            "experience_max": experience_max,
        }

    if experience_max is not None and experience_max < floor:
        return False, f"experience ceiling {experience_max:g} years is below profile floor", {
            "quality": "SKIP_EXPERIENCE",
            "experience_min": experience_min,
            "experience_max": experience_max,
        }

    location_signals = _extract_location_signals(location or description)
    allowed_cities = {_normalize(profile.current_city)}
    allowed_cities.update(_normalize(c) for c in (profile.relocate_cities or []))
    allowed_cities.discard("")

    location_known = bool(location_signals)
    location_ok = (
        not location_known
        or "remote" in location_signals
        or bool(location_signals & allowed_cities)
    )
    if not location_ok:
        return False, "location is outside current/relocation preferences", {
            "quality": "SKIP_LOCATION",
            "locations": sorted(location_signals),
        }

    work_mode = _normalize(profile.work_mode)
    if work_mode == "remote_only" and "remote" not in location_signals and location_known:
        return False, "job is not identified as remote", {"quality": "SKIP_WORK_MODE"}

    freshness_days = _extract_freshness_days(description)
    if freshness_days is not None and freshness_days > FRESHNESS_DAYS:
        return False, f"job is older than {FRESHNESS_DAYS} days", {
            "quality": "SKIP_STALE",
            "freshness_days": freshness_days,
        }

    if fullstack_signal:
        quality = "HIGH_FULLSTACK_REACT"
    elif signals["react"] and signals["typescript"] and supporting_matches >= 2:
        quality = "HIGH_REACT_TYPESCRIPT"
    elif signals["react"] or signals["next"]:
        quality = "MEDIUM_REACT_FRONTEND"
    else:
        quality = "MEDIUM_MERN"

    return True, f"qualified: {title_reason}; {quality}", {
        "quality": quality,
        "experience_min": experience_min,
        "experience_max": experience_max,
        "locations": sorted(location_signals),
        "supporting_skill_matches": supporting_matches,
        "freshness_days": freshness_days,
        "frameworks": [k for k, v in signals.items() if v],
    }


def extract_linkedin_job_details(page) -> dict:
    """Extract stable text signals from a LinkedIn job detail page."""
    text = page.locator("body").inner_text()
    title = ""
    company = ""
    location = ""

    selectors = [
        "h1",
        ".job-details-jobs-unified-top-card__job-title",
        ".top-card-layout__title",
    ]
    for selector in selectors:
        try:
            value = page.locator(selector).first.inner_text(timeout=1500).strip()
            if value:
                title = value
                break
        except Exception:
            continue

    company_selectors = [
        ".job-details-jobs-unified-top-card__company-name",
        ".topcard__org-name-link",
        "a[href*='/company/']",
    ]
    for selector in company_selectors:
        try:
            value = page.locator(selector).first.inner_text(timeout=1500).strip()
            if value:
                company = value
                break
        except Exception:
            continue

    location_selectors = [
        ".job-details-jobs-unified-top-card__primary-description-container",
        ".topcard__flavor--bullet",
    ]
    for selector in location_selectors:
        try:
            value = page.locator(selector).first.inner_text(timeout=1500).strip()
            if value:
                location = value
                break
        except Exception:
            continue

    return {
        "title": title,
        "company": company,
        "location": location,
        "description": text,
        "text": text,
    }


def page_has_stop_signal(page) -> str | None:
    text = page.inner_text("body").lower()
    for phrase in STOP_PHRASES:
        if phrase in text:
            return phrase
    if "/checkpoint/" in page.url or "/login" in page.url:
        return "session expired / checkpoint challenge"
    return None


def describe_modal(page) -> dict:
    return page.evaluate("""
        () => {
            const modal = document.querySelector(
                '.jobs-easy-apply-modal, [role="dialog"], .artdeco-modal'
            ) || document.body;

            const out = {
                heading: modal.querySelector('h2')?.innerText || '',
                fields: [],
                buttons: []
            };

            modal.querySelectorAll('input, textarea, select').forEach(el => {
                if (el.type === 'hidden') return;

                let label = '';
                if (el.id) {
                    const lbl = document.querySelector(`label[for="${el.id}"]`);
                    if (lbl) label = lbl.innerText.trim();
                }
                if (!label) {
                    const parent = el.closest('label');
                    if (parent) label = parent.innerText.trim();
                }

                out.fields.push({
                    tag: el.tagName,
                    type: el.type || '',
                    id: el.id,
                    label,
                    value: el.value,
                    checked: el.checked,
                    options: el.tagName === 'SELECT'
                        ? Array.from(el.options).map(o => o.textContent.trim())
                        : []
                });
            });

            modal.querySelectorAll('button').forEach(b => {
                const t = b.innerText.trim();
                if (t) out.buttons.push(t);
            });

            return out;
        }
    """)


def fill_text_field(page, field_id: str, text: str):
    page.evaluate(
        """([id, text]) => {
            const el = document.getElementById(id);
            if (!el) return false;
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, text);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            return true;
        }""",
        [field_id, text],
    )


def select_known_option(page, field_id: str, desired: str) -> bool:
    return page.evaluate(
        """([id, desired]) => {
            const el = document.getElementById(id);
            if (!el || el.tagName !== 'SELECT') return false;
            const wanted = desired.trim().toLowerCase();
            const option = Array.from(el.options).find(o =>
                o.textContent.trim().toLowerCase() === wanted ||
                o.value.trim().toLowerCase() === wanted
            );
            if (!option) return false;
            el.value = option.value;
            el.dispatchEvent(new Event('change', {bubbles: true}));
            return true;
        }""",
        [field_id, desired],
    )


def _known_answer(label: str, answers: dict) -> str | None:
    normalized = _normalize(label)
    for key, value in answers.items():
        if _normalize(key.replace("_", " ")) in normalized:
            return str(value)
    return None


def fill_form_step(page, profile: Profile):
    """Fill only trusted profile/learned answers. Never invent an answer."""
    answers = profile.answer_library()
    state = describe_modal(page)

    for field in state.get("fields", []):
        label = (field.get("label") or "").strip()
        if not label or field.get("value") or field.get("checked"):
            continue

        stored = learned_answers.get_answer(label)
        matched = stored or _known_answer(label, answers)

        if matched is None:
            raise RuntimeError(f"unknown screening question requires manual input: {label}")

        if field["tag"] == "SELECT":
            if not select_known_option(page, field["id"], matched):
                raise RuntimeError(
                    f"known answer '{matched}' does not match available options for: {label}"
                )
        elif field["tag"] == "INPUT" and field["type"] in ("text", "email", "tel", "number"):
            fill_text_field(page, field["id"], matched)
        elif field["tag"] == "TEXTAREA":
            fill_text_field(page, field["id"], matched)
        else:
            raise RuntimeError(f"unsupported screening field requires manual input: {label}")


def click_modal_button(page, text: str) -> bool:
    return page.evaluate(
        """(text) => {
            const modal = document.querySelector('.jobs-easy-apply-modal, [role="dialog"], .artdeco-modal');
            if (!modal) return false;
            const btn = [...modal.querySelectorAll('button')].find(b => b.innerText.trim() === text);
            if (!btn) return false;
            btn.click();
            return true;
        }""",
        text,
    )


def run_one_application(page, profile: Profile, job_title: str, company: str) -> bool:
    """Run one Easy Apply flow. Unknown fields or safety signals stop this listing."""
    easy_apply = page.get_by_role("button", name="Easy Apply").first
    try:
        if not easy_apply.is_visible():
            return False
    except Exception:
        return False

    if DRY_RUN:
        print(f"DRY RUN: would Easy Apply -> {job_title} @ {company}")
        return True

    easy_apply.click()
    time.sleep(2)

    for step in range(12):
        stop = page_has_stop_signal(page)
        if stop:
            raise RuntimeError(f"stop signal mid-application: {stop}")

        state = describe_modal(page)
        buttons = state.get("buttons", [])
        if not buttons:
            raise RuntimeError("Easy Apply modal did not expose a recognized state")

        fill_form_step(page, profile)
        time.sleep(0.8)

        buttons = describe_modal(page).get("buttons", [])

        if "Submit application" in buttons:
            print("--- Review before submit ---")
            review_text = page.locator("body").inner_text()
            print(review_text[:1200])

            # Never submit if LinkedIn is presenting a new verification/security state.
            stop = page_has_stop_signal(page)
            if stop:
                raise RuntimeError(f"stop signal before submit: {stop}")

            if not click_modal_button(page, "Submit application"):
                raise RuntimeError("Submit application button could not be clicked")

            time.sleep(2)
            stop = page_has_stop_signal(page)
            if stop:
                raise RuntimeError(f"stop signal after submit: {stop}")

            click_modal_button(page, "Done")
            return True

        if "Review" in buttons:
            if not click_modal_button(page, "Review"):
                raise RuntimeError("Review button could not be clicked")
        elif "Next" in buttons:
            if not click_modal_button(page, "Next"):
                raise RuntimeError("Next button could not be clicked")
        else:
            raise RuntimeError(
                f"unrecognized Easy Apply modal state at step {step + 1}: {buttons}"
            )

        time.sleep(1.2)

    raise RuntimeError("exceeded Easy Apply step cap without reaching submit")


def _company_from_card(raw: str) -> str:
    lines = [line.strip() for line in (raw or "").splitlines() if line.strip()]
    return lines[1] if len(lines) > 1 else ""


def _discover_cards(page) -> list[dict]:
    return page.evaluate("""
        () => {
            const seen = new Set();
            return Array.from(document.querySelectorAll('a[href*="/jobs/view/"]'))
                .map(a => ({
                    title: a.innerText?.trim().split("\\n")[0],
                    company: a.closest("li")?.innerText?.trim() || "",
                    href: a.href
                }))
                .filter(c => c.title && c.href && !seen.has(c.href))
                .filter(c => {
                    seen.add(c.href);
                    return true;
                });
        }
    """)


def run(discovery_only: bool = False, retry_unsubmitted: bool = False):
    profile = Profile.load()
    if not Path(SESSION_FILE).exists():
        raise SystemExit(f"{SESSION_FILE} not found. Run: python login_capture.py linkedin")

    counters = {
        "discovered": 0,
        "already_processed": 0,
        "qualified": 0,
        "applications": 0,
        "manual_action": 0,
        "skipped": 0,
        "stopped": 0,
    }
    processed_jobs = load_linkedin_processed_jobs()
    # Discovery-only must be observational: it must not consume processed state.
    retryable_statuses = {"dry_run", "manual_action_required", "sheet_logging_failed"}
    run_cap = min(
        MAX_LINKEDIN_APPLICATIONS_PER_RUN,
        max(0, int(profile.stop_after_n_applications)),
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=200)
        context = browser.new_context(storage_state=SESSION_FILE)
        page = context.new_page()

        try:
            seen_this_run: set[str] = set()

            for role in profile.target_roles:
                if counters["applications"] >= run_cap:
                    break

                search_url = (
                    "https://www.linkedin.com/jobs/search/?keywords="
                    + quote_plus(role)
                    + "&f_TPR=r172800"
                )
                print(f"\n--- Searching LinkedIn: {role} ---")
                page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
                time.sleep(3)

                stop = page_has_stop_signal(page)
                if stop:
                    counters["stopped"] += 1
                    print(f"STOPPING: {stop}")
                    log_row([datetime.now(), "linkedin", "-", "-", "stopped", stop])
                    return

                cards = _discover_cards(page)
                counters["discovered"] += len(cards)
                print(f"Found {len(cards)} LinkedIn job candidates")

                for idx, card in enumerate(cards):
                    if counters["applications"] >= run_cap:
                        break

                    title = card.get("title", "")
                    card_company = _company_from_card(card.get("company", ""))
                    job_url = card.get("href", "")
                    job_id = linkedin_job_id(job_url)
                    print(f"Candidate {idx + 1}: {title} | {job_url}")

                    previous = processed_jobs.get(job_id)
                    previous_status = (previous or {}).get("status", "")
                    if previous and not (
                        retry_unsubmitted and previous_status in retryable_statuses
                    ):
                        counters["already_processed"] += 1
                        print(
                            f"SKIPPING ALREADY PROCESSED: {title} "
                            f"[{job_id}] ({previous_status or 'unknown'})"
                        )
                        continue

                    if job_id in seen_this_run:
                        print(f"SKIPPING DUPLICATE THIS RUN: {title} [{job_id}]")
                        continue
                    seen_this_run.add(job_id)

                    try:
                        page.goto(job_url, wait_until="commit", timeout=15000)
                        time.sleep(1.5)

                        stop = page_has_stop_signal(page)
                        if stop:
                            raise RuntimeError(f"stop signal: {stop}")

                        details = extract_linkedin_job_details(page)
                        detail_title = details.get("title") or title
                        company = details.get("company") or card_company
                        description = details.get("description", "")

                        qualified, reason, metadata = qualify_linkedin_job(
                            detail_title,
                            description,
                            profile,
                            details.get("location", ""),
                        )
                        print(
                            f"QUALIFICATION: {'PASS' if qualified else 'SKIP'} | {reason}"
                        )

                        if not qualified:
                            counters["skipped"] += 1
                            if not discovery_only:
                                record_linkedin_job(
                                    job_id, detail_title, company, "skipped", job_url
                                )
                                processed_jobs[job_id] = {
                                    "job_id": job_id,
                                    "status": "skipped",
                                }
                            log_row([
                                datetime.now(), "linkedin", detail_title, company,
                                "skipped", reason,
                            ])
                            continue

                        counters["qualified"] += 1

                        if discovery_only:
                            print(
                                f"DISCOVERY ONLY: {detail_title} | {company} | "
                                f"{metadata.get('quality')} | {job_url}"
                            )
                            continue

                        success = run_one_application(
                            page, profile, detail_title, company
                        )

                        if success:
                            status = "dry_run" if DRY_RUN else "applied"
                            if not DRY_RUN:
                                counters["applications"] += 1

                            record_linkedin_job(
                                job_id, detail_title, company, status, job_url
                            )
                            processed_jobs[job_id] = {
                                "job_id": job_id,
                                "status": status,
                            }
                            log_row([
                                datetime.now(), "linkedin", detail_title, company,
                                status, "",
                            ])
                            print(
                                f"{'DRY RUN' if DRY_RUN else 'Applied'}: "
                                f"{detail_title} @ {company}"
                            )
                        else:
                            counters["manual_action"] += 1
                            sheet_logged = log_linkedin_external_job(
                                job_id,
                                detail_title,
                                company,
                                details.get("location", ""),
                                job_url,
                            )
                            local_status = (
                                "manual_action_required"
                                if sheet_logged
                                else "sheet_logging_failed"
                            )
                            record_linkedin_job(
                                job_id,
                                detail_title,
                                company,
                                local_status,
                                job_url,
                            )
                            processed_jobs[job_id] = {
                                "job_id": job_id,
                                "status": local_status,
                            }
                            log_row([
                                datetime.now(), "linkedin", detail_title, company,
                                local_status,
                                "External/non-Easy-Apply application; "
                                + (
                                    "logged to Google Sheet"
                                    if sheet_logged
                                    else "Google Sheet logging failed"
                                ),
                            ])
                            print(
                                f"MANUAL ACTION REQUIRED: {detail_title} @ {company}"
                                + (
                                    " | logged to Google Sheet"
                                    if sheet_logged
                                    else " | WARNING: sheet logging failed"
                                )
                            )

                    except RuntimeError as e:
                        counters["stopped"] += 1
                        print(f"STOPPING: {e}")
                        log_row([
                            datetime.now(), "linkedin", title, card_company,
                            "stopped", str(e),
                        ])
                        return
                    except PWTimeout as e:
                        counters["skipped"] += 1
                        print(f"SKIPPING: LinkedIn page timeout: {e}")
                        log_row([
                            datetime.now(), "linkedin", title, card_company,
                            "skipped", "page timeout",
                        ])

                    time.sleep(profile.pace_seconds_between_actions)
        finally:
            browser.close()

    print("\n=== LinkedIn Run Summary ===")
    print(f"Discovered:         {counters['discovered']}")
    print(f"Already processed:  {counters['already_processed']}")
    print(f"Qualified:          {counters['qualified']}")
    print(f"Applications:       {counters['applications']}")
    print(f"Manual action:      {counters['manual_action']}")
    print(f"Skipped:            {counters['skipped']}")
    print(f"Stopped:            {counters['stopped']}")
    print(f"Dry run:            {DRY_RUN}")
    print(f"See {LOG_FILE} for the full log.")


if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print_usage()
        raise SystemExit(0)

    run(
        discovery_only=_cli_flag("--discovery-only"),
        retry_unsubmitted=_cli_flag("--retry-unsubmitted"),
    )
