"""
Screening Question Solver
Intelligently answers screening questions across portals with a multi-tier resolution strategy:
1. Sensitive field guard: Never guesses personal documents/sensitive info.
2. Direct profile facts & heuristics: Answers common questions (experience, notice, CTC, location, visa, skills).
3. Learned answers cache: Reuses previous user-confirmed answers.
4. LLM Drafting: Uses Gemini Flash / Groq fallback based strictly on profile narrative without hallucinations.
5. Human input fallback: Prompts the user with timeout and remembers the answer.
"""
import re
from typing import Optional, Tuple
from common.profile import Profile
from common import learned_answers
from common import llm
from common.human_input import ask_user

SENSITIVE_FIELD_HINTS = [
    "date of birth", "dob", "pan number", "pan card", "aadhar", "aadhaar",
    "passport", "bank account", "ifsc", "father's name", "father name",
    "mother's name", "mother name", "marital status", "blood group",
    "emergency contact", "voter id", "driving licence", "driving license",
]

CORE_FRONTEND_SKILLS = {
    "react", "react.js", "reactjs", "next.js", "nextjs", "next", "typescript",
    "javascript", "js", "html", "html5", "css", "css3", "redux", "redux toolkit",
    "context api", "tanstack query", "react query", "rest api", "rest", "frontend",
    "front end", "web development", "ui", "tailwind", "material ui", "mui"
}

SECONDARY_SKILLS = {
    "node", "node.js", "nodejs", "express", "express.js", "mongodb", "mern",
    "graphql", "apollo", "websocket", "websockets", "git", "github", "docker",
    "azure", "vite", "jest"
}

UNSUPPORTED_OR_DIFFERENT_STACKS = {
    "angular", "vue", "vue.js", "php", "wordpress", "shopify", "laravel",
    "django", "spring boot", "java developer", "c#", ".net", "dotnet",
    "ios", "swift", "kotlin", "android", "flutter", "react native", "ruby", "rails"
}


class QuestionSolver:
    def __init__(self, profile: Profile):
        self.profile = profile

    def is_sensitive(self, question: str) -> bool:
        q_lower = question.lower()
        return any(hint in q_lower for hint in SENSITIVE_FIELD_HINTS)

    def resolve_direct_answer(self, question: str) -> Optional[str]:
        """Resolves common screening questions directly from profile configuration."""
        q = question.lower().strip()
        data = self.profile.data

        # 1. Total Experience
        if (
            ("total" in q and "experience" in q)
            or ("overall" in q and "experience" in q)
            or ("professional experience" in q)
            or ("years of work experience" in q)
            or ("how many years of experience" in q and not any(s in q for s in CORE_FRONTEND_SKILLS | SECONDARY_SKILLS | UNSUPPORTED_OR_DIFFERENT_STACKS))
        ):
            return str(int(data.get("total_experience_years", 4)))

        # 2. Skill specific experience: "How many years of experience do you have in <skill>?"
        if "years" in q or "experience" in q:
            for skill in CORE_FRONTEND_SKILLS:
                if re.search(rf"\b{re.escape(skill)}\b", q):
                    return str(int(data.get("total_experience_years", 4)))
            for skill in SECONDARY_SKILLS:
                if re.search(rf"\b{re.escape(skill)}\b", q):
                    return "3"
            for skill in UNSUPPORTED_OR_DIFFERENT_STACKS:
                if re.search(rf"\b{re.escape(skill)}\b", q):
                    return "0"

        # 3. Notice Period
        if "notice period" in q or "serving notice" in q or "how soon can you join" in q:
            days = data.get("notice_period_days", 0)
            if "serving" in q:
                return "No"
            if "day" in q or "number" in q or "how many" in q:
                return str(days)
            if days == 0 or data.get("immediately_available", True):
                return "Immediate"
            return f"{days} days"

        # 4. Immediate availability
        if any(p in q for p in ["available to join immediately", "immediate joiner", "join immediately"]):
            return "Yes"

        # 5. Work authorization & Visa
        if any(p in q for p in [
            "authorized to work in india", "legally authorized to work in india",
            "eligible to work in india", "citizen of india", "work permit in india"
        ]):
            return "Yes"
        if any(p in q for p in ["require sponsorship", "require visa sponsorship", "need sponsorship"]):
            return "No"

        # 6. Current CTC & Expected CTC
        if "current ctc" in q or "current salary" in q or "present ctc" in q:
            if "number" in q or "in inr" in q or "numeric" in q or "lakhs" in q:
                return str(data.get("current_ctc_lpa", 7.0))
            return f"{data.get('current_ctc_lpa', 7.0)} LPA"

        if "expected ctc" in q or "expected salary" in q:
            if "number" in q or "in inr" in q or "numeric" in q or "lakhs" in q:
                return str(data.get("expected_ctc_lpa", 12.0))
            return f"{data.get('expected_ctc_lpa', 12.0)} LPA"

        # 7. Relocation
        if "relocate" in q or "willing to move" in q:
            relocate_cities = [c.lower() for c in data.get("relocate_cities", [])]
            for city in relocate_cities:
                if city in q:
                    return "Yes"
            if len(relocate_cities) > 0:
                return "Yes"
            return "No"

        # 8. Current City / Location
        if "current city" in q or "current location" in q or "which city do you live" in q:
            return data.get("current_city", "Patna")

        # 9. Shifts & Work environment
        if "night shift" in q:
            return "Yes" if data.get("night_shift_ok", True) else "No"
        if "weekend" in q:
            return "Yes" if data.get("weekend_ok", False) else "No"
        if any(p in q for p in ["laptop", "desktop", "reliable internet", "wifi"]):
            return "Yes"
        if any(p in q for p in ["hybrid", "work from office", "onsite", "commute to"]):
            return "Yes"

        # 10. Qualification / Degree
        if any(p in q for p in ["highest qualification", "highest degree", "education level"]):
            return data.get("highest_qualification", "B.Tech")
        if any(p in q for p in ["bachelor", "degree", "b.tech", "graduation"]):
            return "Yes"

        return None

    def solve(
        self,
        question: str,
        options: Optional[list[str]] = None,
        job_context: str = "",
        allow_human_input: bool = True,
        timeout_seconds: int = 60
    ) -> Optional[str]:
        """
        Solves any screening question returning the best answer string, or None if skipped.
        If options are provided, maps the result to the closest valid option.
        """
        raw_question = question.strip()
        if not raw_question:
            return None

        # 1. Sensitive question check -> Force human input immediately
        if self.is_sensitive(raw_question):
            print(f"\n[Security Guard] Question asks for sensitive personal data: '{raw_question}'")
            if not allow_human_input:
                return None
            val = ask_user(f"Sensitive question: {raw_question}", timeout_seconds=timeout_seconds)
            if val:
                learned_answers.save_answer(raw_question, val)
            return val

        # 2. Check Learned Answers Cache
        cached = learned_answers.get_answer(raw_question)
        if cached:
            if options:
                matched = self._match_to_options(cached, options)
                if matched:
                    return matched
            return cached

        # 3. Direct Fact Resolution
        direct = self.resolve_direct_answer(raw_question)
        if direct:
            if options:
                matched = self._match_to_options(direct, options)
                if matched:
                    return matched
            return direct

        # 4. LLM Drafting
        llm_answer = None
        try:
            draft = llm.draft_answer(raw_question, self.profile.data, job_context)
            if draft and not draft.startswith("[NEEDS_HUMAN_INPUT"):
                llm_answer = draft.strip()
        except Exception as e:
            print(f"  (LLM drafting unavailable: {e})")

        if llm_answer:
            if options:
                matched = self._match_to_options(llm_answer, options)
                if matched:
                    return matched
            return llm_answer

        # 5. Human Input Fallback
        if allow_human_input:
            prompt = f"Screening question:\n{raw_question}"
            if options:
                prompt += f"\nOptions: {', '.join(options)}"
            user_val = ask_user(prompt, timeout_seconds=timeout_seconds)
            if user_val:
                if options:
                    matched = self._match_to_options(user_val, options)
                    user_val = matched or user_val
                learned_answers.save_answer(raw_question, user_val)
                return user_val

        return None

    def _match_to_options(self, target: str, options: list[str]) -> Optional[str]:
        """Matches a target answer string to one of the provided option choices."""
        target_norm = target.lower().strip()

        # Exact match
        for opt in options:
            if opt.lower().strip() == target_norm:
                return opt

        # Yes / No binary matching
        if target_norm in ("yes", "y", "true"):
            for opt in options:
                if opt.lower().strip() in ("yes", "y", "true", "i agree"):
                    return opt
        if target_norm in ("no", "n", "false"):
            for opt in options:
                if opt.lower().strip() in ("no", "n", "false", "i disagree"):
                    return opt

        # Substring / token matching
        for opt in options:
            opt_norm = opt.lower().strip()
            if target_norm in opt_norm or opt_norm in target_norm:
                return opt

        # Numeric matching (e.g. "4 years" matching "3-5 years")
        target_nums = re.findall(r"\d+", target_norm)
        if target_nums:
            target_num = int(target_nums[0])
            for opt in options:
                opt_nums = [int(n) for n in re.findall(r"\d+", opt)]
                if len(opt_nums) == 1 and opt_nums[0] == target_num:
                    return opt
                elif len(opt_nums) >= 2 and opt_nums[0] <= target_num <= opt_nums[-1]:
                    return opt

        return options[0] if options else None
