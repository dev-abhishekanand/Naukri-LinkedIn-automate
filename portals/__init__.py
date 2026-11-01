"""Job portals automation package."""
from portals.registry import (
    get_portal_class_by_name,
    get_portal_class_by_url,
    detect_portal_from_url,
    register_portal,
)

__all__ = [
    "get_portal_class_by_name",
    "get_portal_class_by_url",
    "detect_portal_from_url",
    "register_portal",
]
