"""
Unified Profile Manager & Question Solver Interface
Serves as the single source of truth for candidate attributes and screening question resolution.
"""
from pathlib import Path
from typing import Optional, Dict, Any, List

from common.profile import Profile
from core.question_solver import QuestionSolver

PROJECT_DIR = Path(__file__).resolve().parent.parent


class ProfileManager:
    """Singleton manager for Abhishek's candidate profile and screening questions."""

    _instance: Optional["ProfileManager"] = None
    _profile: Optional[Profile] = None
    _solver: Optional[QuestionSolver] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProfileManager, cls).__new__(cls)
            cls._profile = Profile.load(str(PROJECT_DIR / "profile.yaml"))
            cls._solver = QuestionSolver(cls._profile)
        return cls._instance

    @property
    def profile(self) -> Profile:
        return self._profile

    @property
    def solver(self) -> QuestionSolver:
        return self._solver

    @property
    def data(self) -> Dict[str, Any]:
        return self._profile.data

    def answers(self) -> Dict[str, str]:
        """Returns standard pre-computed answers dictionary."""
        return self._profile.answer_library()

    def solve_question(
        self,
        question: str,
        options: Optional[List[str]] = None,
        job_context: str = "",
        allow_human_input: bool = False,
        timeout_seconds: int = 15,
    ) -> Optional[str]:
        """Resolves any screening question using multi-tier resolution strategy."""
        return self._solver.solve(
            question=question,
            options=options,
            job_context=job_context,
            allow_human_input=allow_human_input,
            timeout_seconds=timeout_seconds,
        )


def get_profile_manager() -> ProfileManager:
    """Helper factory for accessing the unified ProfileManager."""
    return ProfileManager()
