"""Extract normalized ATS-relevant keywords from a job description."""

import re


KEYWORD_ALIASES = {
    "react": ("react", "react.js", "reactjs"),
    "next.js": ("next.js", "nextjs"),
    "typescript": ("typescript", "type script"),
    "javascript": ("javascript", "ecmascript"),
    "redux": ("redux", "redux toolkit", "redux-toolkit"),
    "context api": ("context api", "react context"),
    "tanstack query": ("tanstack query", "react query"),
    "rest api": ("rest api", "restful api", "rest apis"),
    "graphql": ("graphql",),
    "apollo": ("apollo", "apollo client"),
    "websockets": ("websocket", "websockets"),
    "socket.io": ("socket.io", "socket io"),
    "node.js": ("node.js", "nodejs"),
    "express.js": ("express.js", "expressjs"),
    "mongodb": ("mongodb", "mongo db"),
    "mern": ("mern",),
    "tailwind css": ("tailwind css", "tailwind"),
    "material ui": ("material ui", "mui"),
    "html5": ("html5",),
    "css3": ("css3",),
    "jest": ("jest",),
    "react testing library": ("react testing library",),
    "storybook": ("storybook",),
    "vite": ("vite",),
    "webpack": ("webpack",),
    "docker": ("docker",),
    "azure": ("azure",),
}


def normalize_text(text: str) -> str:
    """Normalize whitespace and casing for deterministic matching."""
    return re.sub(r"\s+", " ", text.lower()).strip()


def extract_keywords(job_description: str) -> list[str]:
    """Return supported technical keywords found in the job description."""
    normalized = normalize_text(job_description)
    found = []

    for canonical, aliases in KEYWORD_ALIASES.items():
        if any(
            re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized)
            for alias in aliases
        ):
            found.append(canonical)

    return found
