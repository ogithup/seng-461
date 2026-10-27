"""The loop that connects agent -> executor -> storage.

For each task the agent proposes actions one at a time. Each action either runs right
away (allowlisted) or parks the task until a human decides. The loop is bounded:
a task may take at most `max_actions_per_task` actions and tolerate at most
`max_repair_attempts` failed ones beyond the first, then it fails instead of looping.
"""
import logging
import threading
from contextlib import contextmanager
from enum import Enum
from typing import Dict, Iterator, List, Optional, Tuple

from backend.api.config import Settings
from backend.api.errors import conflict
from backend.api.schemas.contracts import (
    AgentAction,
    ExecutionRequest,
    ExecutionResult,
    WriteFileRequest,
)
from backend.api.schemas.enums import ExecutionStatus, TaskStatus
from backend.api.schemas.tasks import ExecutionOut, TaskOut
from backend.api.services.approvals import ApprovalGate
from backend.api.services.ports import AgentPort, ExecutorPort, StoragePort
from backend.api.services.workspace import WorkspaceService

logger = logging.getLogger("backend.api")

_HISTORY_LIMIT = 100


class _Outcome(Enum):
    DONE = "done"
    WAITING = "waiting"
    FAILED = "failed"


class TaskRunner:
    def __init__(
        self,
        storage: StoragePort,
        agent: AgentPort,
        executor: ExecutorPort,
        workspace: WorkspaceService,
        gate: ApprovalGate,
        settings: Settings,
    ):
        self._storage = storage
        self._agent = agent
        self._executor = executor
        self._workspace = workspace
        self._gate = gate
        self._settings = settings
        self._locks: Dict[int, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    @contextmanager
    def exclusive(self, project_id: int) -> Iterator[None]:
        """One request at a time per project; a second one gets a retryable 409."""
        with self._locks_guard:
            lock = self._locks.setdefault(project_id, threading.Lock())
        if not lock.acquire(blocking=False):
            raise conflict(
                "project_busy",
                "The agent is still working on this project. Try again in a moment.",
                project_id,
                retryable=True,
            )
        try:
            yield
        finally:
            lock.release()

    def run_pending(
        self,
        project_id: int,
        resume: Optional[Tuple[TaskOut, ExecutionResult]] = None,
    ) -> None:
        """Run the project's pending tasks in order until one waits for approval or fails.

        `resume` continues a task that was waiting, with the result of its approved command.
        """
        queue: List[Tuple[TaskOut, Optional[ExecutionResult]]] = []
        if resume is not None:
            queue.append(resume)
        pending = [TaskOut.model_validate(t) for t in self._storage.list_tasks(project_id)]
        queue.extend((t, None) for t in pending if t.status == TaskStatus.PENDING)

        for index, (task, last_result) in enumerate(queue):
            outcome = self._run_task(project_id, task, last_result)
            if outcome is _Outcome.WAITING:
                return
            if outcome is _Outcome.FAILED:
                for later, _ in queue[index + 1 :]:
                    self._storage.update_task_status(later.id, TaskStatus.SKIPPED.value)
                return

    def execute_approved(self, project_id: int, execution: ExecutionOut) -> ExecutionResult:
        result = self._invoke(project_id, execution.command, requires_approval=True, approved=True)
        self._storage.update_execution(
            execution.id,
            _status_for(result),
            stdout=result.stdout,
            stderr=result.stderr,
            retry_count=result.retry_count,
            duration_ms=result.duration_ms,
        )
        return result

    def _run_task(
        self, project_id: int, task: TaskOut, last_result: Optional[ExecutionResult]
    ) -> _Outcome:
        s = self._settings
        self._storage.update_task_status(task.id, TaskStatus.RUNNING.value)
        history = [
            ExecutionOut.model_validate(e)
            for e in self._storage.list_executions(project_id, task_id=task.id, limit=_HISTORY_LIMIT)
        ]
        ran = [e for e in history if e.status in (ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED)]
        actions_taken = len(ran)
        failures = sum(1 for e in ran if e.status == ExecutionStatus.FAILED)

        while True:
            if actions_taken >= s.max_actions_per_task or failures > s.max_repair_attempts:
                logger.warning(
                    "task %s stopped: %d actions, %d failures", task.id, actions_taken, failures
                )
                return self._fail(task)

            try:
                raw = self._agent.next_action(task, last_result)
                action = None if raw is None else AgentAction.model_validate(raw)
            except Exception:
                logger.exception("agent produced no usable action for task %s", task.id)
                return self._fail(task)

            if action is None:
                if last_result is not None and not last_result.success:
                    return self._fail(task)  # the agent gave up after a failing command
                self._storage.update_task_status(task.id, TaskStatus.SUCCEEDED.value)
                return _Outcome.DONE

            if action.type == "write_file":
                last_result = self._write_file(project_id, action)
                self._record(task, action.command, last_result)
                actions_taken += 1
                if not last_result.success:
                    failures += 1
                continue

            if action.requires_approval or not self._is_allowed(action.command):
                self._storage.save_execution(
                    task.id,
                    action.command,
                    ExecutionStatus.PENDING_APPROVAL.value,
                    reason=action.reason,
                )
                self._storage.update_task_status(task.id, TaskStatus.WAITING_FOR_APPROVAL.value)
                return _Outcome.WAITING

            last_result = self._invoke(
                project_id, action.command, requires_approval=False, approved=False
            )
            self._record(task, action.command, last_result)
            actions_taken += 1
            if not last_result.success:
                failures += 1

    def _record(self, task: TaskOut, command: str, result: ExecutionResult) -> None:
        """Store what the executor reported, and nothing the agent or runner assumed."""
        self._storage.save_execution(
            task.id,
            command,
            _status_for(result),
            stdout=result.stdout,
            stderr=result.stderr,
            retry_count=result.retry_count,
            duration_ms=result.duration_ms,
        )

    def _fail(self, task: TaskOut) -> _Outcome:
        self._storage.update_task_status(task.id, TaskStatus.FAILED.value)
        return _Outcome.FAILED

    def _is_allowed(self, command: str) -> bool:
        try:
            return bool(self._executor.is_allowed(command))
        except Exception:
            logger.exception("allowlist check failed; treating %r as needing approval", command)
            return False  # fail closed

    def _write_file(self, project_id: int, action: AgentAction) -> ExecutionResult:
        writer = getattr(self._executor, "write_file", None)
        if writer is None:
            return ExecutionResult(success=False, stderr="This executor cannot write files.")
        request = WriteFileRequest(
            working_directory=str(self._workspace.ensure_project_dir(project_id)),
            path=action.path,
            content=action.content,
        )
        try:
            return ExecutionResult.model_validate(writer(request))
        except Exception:
            logger.exception("file write failed for project %s", project_id)
            return ExecutionResult(success=False, stderr="The executor failed to write this file.")

    def _invoke(
        self, project_id: int, command: str, requires_approval: bool, approved: bool
    ) -> ExecutionResult:
        request = ExecutionRequest(
            command=command,
            working_directory=str(self._workspace.ensure_project_dir(project_id)),
            timeout=self._settings.command_timeout_seconds,
            requires_approval=requires_approval,
        )
        try:
            return ExecutionResult.model_validate(
                self._executor.run_command(request, approved=approved)
            )
        except Exception:
            logger.exception("executor failed for project %s", project_id)
            return ExecutionResult(success=False, stderr="The execution manager failed to run this command.")


def _status_for(result: ExecutionResult) -> str:
    return (ExecutionStatus.SUCCEEDED if result.success else ExecutionStatus.FAILED).value
