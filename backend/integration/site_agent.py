"""Request-aware agent that proposes one `write_file` action per generated file.

It satisfies `AgentPort`: `plan` and `next_action` only return data. It never touches the
filesystem or a shell, keeps no per-project state (every step prompt carries what is needed
to regenerate its file), and never says a step succeeded: the runner records the
executor's verified result and `next_action` stops only after seeing it.
"""
import re
from typing import Any, Dict, List, Optional

from backend.integration.reference_generator import ReferenceSiteGenerator, spec_for

_DEFAULT_TITLES = {"blog": "My Blog", "portfolio": "My Portfolio", "landing": "My Product"}
_STEP = re.compile(r'^Write (?P<path>\S+) \((?P<kind>blog|portfolio|landing) site "(?P<title>[^"]*)"\)$')
_NAMED = re.compile(r"\b(?:called|named|titled|for)\s+(?P<name>.+)$", re.IGNORECASE)
_MAX_TITLE = 60


def site_type_for(request: str) -> str:
    text = request.lower()
    if "portfolio" in text or "resume" in text or re.search(r"\bcv\b", text):
        return "portfolio"
    if "blog" in text:
        return "blog"
    return "landing"


def title_for(request: str, site_type: str) -> str:
    match = _NAMED.search(request)
    name = match.group("name") if match else ""
    name = re.sub(r"[\x00-\x1f\x7f\"<>&]", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .!?'")[:_MAX_TITLE].strip()
    return name or _DEFAULT_TITLES[site_type]


class SiteAgent:
    def __init__(self, generator: Optional[Any] = None):
        self._generator = generator or ReferenceSiteGenerator()

    def plan(self, user_request: str) -> List[str]:
        if not isinstance(user_request, str):
            raise TypeError("user_request must be a string")
        if not user_request.strip():
            raise ValueError("user_request must not be empty")
        site_type = site_type_for(user_request)
        title = title_for(user_request, site_type)
        files = self._generate(site_type, title)
        # index.html first so a partial run still leaves something previewable.
        paths = sorted(files, key=lambda p: (p != "index.html", p))
        return ['Write %s (%s site "%s")' % (path, site_type, title) for path in paths]

    def next_action(self, task: Any, last_result: Optional[Any]) -> Optional[Dict[str, Any]]:
        if last_result is not None:
            return None  # one file per step; the runner decides success from the result
        match = _STEP.match(str(getattr(task, "prompt", "")))
        if match is None:
            raise ValueError("this agent did not plan task %r" % (getattr(task, "prompt", None),))
        files = self._generate(match.group("kind"), match.group("title"))
        path = match.group("path")
        if path not in files:
            raise ValueError("generator no longer produces %s" % path)
        return {
            "type": "write_file",
            "path": path,
            "content": files[path],
            "reason": "generated %s for a %s site" % (path, match.group("kind")),
        }

    def _generate(self, site_type: str, title: str) -> Dict[str, str]:
        files = self._generator.generate(spec_for(site_type, title))
        problems = self._generator.validate(files)
        if problems:
            raise ValueError("generated site is invalid: %s" % "; ".join(problems))
        return files
