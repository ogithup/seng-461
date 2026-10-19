"""Fixed Sprint 1 plan; no model, filesystem, or executor access."""

from typing import List


def plan(user_request: str) -> List[str]:
    """Return fresh demo steps for any non-empty website request.

    These are task descriptions, not evidence that files were created.
    """
    if not isinstance(user_request, str):
        raise TypeError("user_request must be a string")
    if not user_request.strip():
        raise ValueError("user_request must not be empty")
    return ["create project", "create index.html"]
