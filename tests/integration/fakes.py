"""Scripted stand-ins for Bejan's agent and Sam's executor, with call recording."""
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional


def run(command: str, **extra: Any) -> Dict[str, Any]:
    return {"type": "run_command", "command": command, **extra}


def ok(stdout: str = "ok") -> Dict[str, Any]:
    return {"success": True, "stdout": stdout, "stderr": "", "duration_ms": 5, "retry_count": 0}


def fail(stderr: str = "boom") -> Dict[str, Any]:
    return {"success": False, "stdout": "", "stderr": stderr, "duration_ms": 5, "retry_count": 0}


class ScriptedAgent:
    """plan() returns fixed steps; next_action() replays a per-step list of actions."""

    def __init__(
        self,
        steps: Iterable[str],
        script: Optional[Dict[str, List[Any]]] = None,
        plan_error: Optional[Exception] = None,
        plan_result: Any = None,
    ):
        self.steps = list(steps)
        self.script = {step: list(actions) for step, actions in (script or {}).items()}
        self.plan_error = plan_error
        self.plan_result = plan_result
        self.calls: List[Any] = []  # (step prompt, last_result)

    def plan(self, user_request: str) -> Any:
        if self.plan_error is not None:
            raise self.plan_error
        return self.plan_result if self.plan_result is not None else list(self.steps)

    def next_action(self, task: Any, last_result: Any) -> Any:
        self.calls.append((task.prompt, last_result))
        queue = self.script.get(task.prompt) or []
        return queue.pop(0) if queue else None


class RecordingExecutor:
    def __init__(
        self,
        allowed: Iterable[str] = (),
        results: Optional[List[Any]] = None,
        allowlist_error: Optional[Exception] = None,
        run_error: Optional[Exception] = None,
    ):
        self.allowed = set(allowed)
        self.results = list(results or [])
        self.allowlist_error = allowlist_error
        self.run_error = run_error
        self.calls: List[Any] = []

    def is_allowed(self, command: str) -> bool:
        if self.allowlist_error is not None:
            raise self.allowlist_error
        return command in self.allowed

    def run_command(self, request: Any, approved: bool = False) -> Any:
        self.calls.append(
            SimpleNamespace(
                command=request.command,
                approved=approved,
                working_directory=request.working_directory,
                requires_approval=request.requires_approval,
                timeout=request.timeout,
            )
        )
        if self.run_error is not None:
            raise self.run_error
        return self.results.pop(0) if self.results else ok()
