"""Stateless AgentPort implementation for generated website file actions.

The default generator and specification helper are temporary integration-layer
couplings; callers can inject any object satisfying SiteGeneratorPort.
"""

import re
from typing import Any, Dict, List, Optional

from backend.integration.reference_generator import ReferenceSiteGenerator, spec_for

from .planner import _planning_info

_STEP = re.compile(
    r'^Write (?P<path>\S+) \((?P<site_type>blog|portfolio|landing) site "(?P<title>[^"]*)"\)$'
)


class Orchestrator:
    """Coordinate planning and generation, leaving file writes to the executor."""

    def __init__(self, generator: Optional[Any] = None):
        self._generator = generator if generator is not None else ReferenceSiteGenerator()

    def plan(self, user_request: str) -> List[str]:
        info = _planning_info(user_request)
        files = self._generate(info.site_type, info.title)
        paths = sorted(files, key=lambda path: (path != "index.html", path))
        return [
            'Write %s (%s site "%s")' % (path, info.site_type, info.title)
            for path in paths
        ]

    def next_action(self, task: Any, last_result: Optional[Any]) -> Optional[Dict[str, Any]]:
        if last_result is not None:
            return None

        prompt = task.get("prompt") if isinstance(task, dict) else getattr(task, "prompt", None)
        if not isinstance(prompt, str):
            raise ValueError("task must contain a supported prompt")
        match = _STEP.fullmatch(prompt)
        if match is None:
            raise ValueError("unsupported task prompt: %r" % prompt)

        path = match.group("path")
        site_type = match.group("site_type")
        title = match.group("title")
        files = self._generate(site_type, title)
        if path not in files:
            raise ValueError("generator does not produce %s" % path)

        return {
            "type": "write_file",
            "path": path,
            "content": files[path],
            "reason": "generated %s for a %s site" % (path, site_type),
        }

    def _generate(self, site_type: str, title: str) -> Dict[str, str]:
        files = self._generator.generate(spec_for(site_type, title))
        if not isinstance(files, dict) or any(
            not isinstance(path, str) or not path or not isinstance(content, str)
            for path, content in files.items()
        ):
            raise ValueError("generator must return a mapping of file paths to text")
        problems = self._generator.validate(files)
        if problems:
            raise ValueError("generated site is invalid: %s" % "; ".join(problems))
        return files
