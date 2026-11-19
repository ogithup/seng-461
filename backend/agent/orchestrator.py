"""Stateless AgentPort implementation for generated website file actions."""

import base64
import binascii
import json
import re
import zlib
from typing import Any, Dict, List, Optional

from backend.generator import WebsiteGenerator, normalize_spec

from .interpreter import default_spec, interpret

_STEP = re.compile(
    r'^Write (?P<path>\S+) \((?P<site_type>blog|portfolio|landing) site "(?P<title>.*?)"\)(?: \[(?P<format>spec|delta):(?P<spec>[A-Za-z0-9_-]+)\])?$', re.DOTALL
)
# ChatService currently truncates longer steps; fail before task creation instead.
_MAX_STEP_LENGTH = 500


def _changes(base, value, path=()):
    """Express edits to a starter as paths and replacement JSON values."""
    if isinstance(base, dict) and isinstance(value, dict) and base.keys() == value.keys():
        return [change for key in base for change in _changes(base[key], value[key], path + (key,))]
    if isinstance(base, list) and isinstance(value, list) and len(base) <= len(value):
        changes = [change for i in range(len(base)) for change in _changes(base[i], value[i], path + (i,))]
        changes.extend([[list(path + (i,)), value[i]] for i in range(len(base), len(value))])
        return changes
    return [] if base == value else [[list(path), value]]


def _restore(base, changes):
    if not isinstance(changes, list):
        raise ValueError("invalid task spec delta")
    for change in changes:
        if not isinstance(change, list) or len(change) != 2 or not isinstance(change[0], list) or not change[0]:
            raise ValueError("invalid task spec delta")
        target = base
        try:
            for key in change[0][:-1]:
                target = target[key]
            key = change[0][-1]
            if isinstance(target, list) and isinstance(key, int) and key == len(target):
                target.append(change[1])
            else:
                target[key] = change[1]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("invalid task spec delta") from exc
    return base


class Orchestrator:
    """Coordinate planning and generation, leaving file writes to the executor."""

    def __init__(self, generator: Optional[Any] = None, interpreter: Optional[Any] = None):
        self._generator = generator if generator is not None else WebsiteGenerator()
        self._interpreter = interpreter if interpreter is not None else interpret

    def plan(self, user_request: str) -> List[str]:
        spec = normalize_spec(self._interpreter(user_request))
        files = self._generate(spec)
        paths = sorted(files, key=lambda path: (path != "index.html", path))
        site_type, title = spec["site_type"], spec["title"]
        changes = _changes(default_spec(site_type, title), spec)
        suffix = ""
        if changes:
            payload = json.dumps(changes, separators=(",", ":"), ensure_ascii=True).encode()
            suffix = " [delta:%s]" % base64.urlsafe_b64encode(zlib.compress(payload)).decode().rstrip("=")
        steps = ['Write %s (%s site "%s")%s' % (path, site_type, title, suffix) for path in paths]
        if any(len(step) > _MAX_STEP_LENGTH for step in steps):
            raise ValueError("website spec exceeds the task prompt limit")
        return steps

    def next_action(self, task: Any, last_result: Optional[Any]) -> Optional[Dict[str, Any]]:
        if last_result is not None:
            return None
        prompt = task.get("prompt") if isinstance(task, dict) else getattr(task, "prompt", None)
        if not isinstance(prompt, str):
            raise ValueError("task must contain a supported prompt")
        match = _STEP.fullmatch(prompt)
        if match is None:
            raise ValueError("unsupported task prompt: %r" % prompt)
        path, site_type, title = match.group("path", "site_type", "title")
        payload = match.group("spec")
        spec = default_spec(site_type, title)
        if payload:
            try:
                decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
                if match.group("format") == "delta":
                    decoded = zlib.decompress(decoded)
                    spec = _restore(spec, json.loads(decoded))
                else:
                    spec = json.loads(decoded)
            except (ValueError, UnicodeDecodeError, binascii.Error, zlib.error) as exc:
                raise ValueError("invalid task spec") from exc
            spec = normalize_spec(spec)
            if spec["site_type"] != site_type or spec["title"] != title:
                raise ValueError("task spec does not match description")
        files = self._generate(spec)
        if path not in files:
            raise ValueError("generator does not produce %s" % path)
        return {
            "type": "write_file", "path": path, "content": files[path],
            "reason": "generated %s for a %s site" % (path, site_type),
        }

    def _generate(self, spec: Dict[str, Any]) -> Dict[str, str]:
        spec = normalize_spec(spec)
        files = self._generator.generate(spec)
        if not isinstance(files, dict) or any(
            not isinstance(path, str) or not path or not isinstance(content, str)
            for path, content in files.items()
        ):
            raise ValueError("generator must return a mapping of file paths to text")
        problems = self._generator.validate(files)
        if problems:
            raise ValueError("generated site is invalid: %s" % "; ".join(problems))
        return files
