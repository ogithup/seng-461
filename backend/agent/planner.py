"""Deterministic request classification for website-planning requests."""

import re
from typing import List, NamedTuple

_DEFAULT_TITLES = {
    "blog": "My Blog",
    "portfolio": "My Portfolio",
    "landing": "My Product",
}
_NAMED = re.compile(r"\b(?:called|named|titled|for)\s+(?P<name>.+)$", re.IGNORECASE)
_MAX_TITLE = 60


class _PlanningInfo(NamedTuple):
    site_type: str
    title: str


def _planning_info(user_request: str) -> _PlanningInfo:
    """Return the request's site type and title for the orchestrator."""
    if not isinstance(user_request, str):
        raise TypeError("user_request must be a string")
    if not user_request.strip():
        raise ValueError("user_request must not be empty")

    text = user_request.lower()
    if "portfolio" in text or "resume" in text or re.search(r"\bcv\b", text):
        site_type = "portfolio"
    elif "blog" in text:
        site_type = "blog"
    else:
        site_type = "landing"

    match = _NAMED.search(user_request)
    title = match.group("name") if match else ""
    title = re.sub(r"[\x00-\x1f\x7f\"<>&]", " ", title)
    title = re.sub(r"\s+", " ", title).strip(" .!?'")[:_MAX_TITLE].strip()
    return _PlanningInfo(site_type, title or _DEFAULT_TITLES[site_type])


def plan(user_request: str) -> List[str]:
    """Return a minimal request-aware plan without assuming generated file names.

    The orchestrator will define the final per-file task descriptions once it has
    coordinated with the site generator.
    """
    info = _planning_info(user_request)
    return ["Create a %s site titled '%s'" % (info.site_type, info.title)]
