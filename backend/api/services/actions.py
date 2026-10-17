from typing import Optional, Tuple

from backend.api.errors import conflict, not_found
from backend.api.schemas.actions import ActionDecisionResponse
from backend.api.schemas.enums import ExecutionStatus
from backend.api.schemas.tasks import ExecutionOut, TaskOut
from backend.api.services.approvals import ApprovalGate
from backend.api.services.ports import StoragePort
from backend.api.services.runner import TaskRunner
from backend.api.services.tasks import TaskService, describe


class ActionService:
    """Human decisions on pending commands."""

    def __init__(
        self,
        storage: StoragePort,
        gate: ApprovalGate,
        runner: TaskRunner,
        tasks: TaskService,
    ):
        self._storage = storage
        self._gate = gate
        self._runner = runner
        self._tasks = tasks

    def decide(
        self, action_id: int, approve: bool, command_hash: Optional[str]
    ) -> ActionDecisionResponse:
        project_id, task = self._locate(action_id)

        with self._runner.exclusive(project_id):
            # Read again under the lock: another request may have decided it meanwhile.
            execution = self._load(action_id)
            repeated = self._is_repeat(execution, approve, project_id)

            if not repeated:
                self._check_still_valid(execution, project_id, command_hash)
                if approve:
                    result = self._runner.execute_approved(project_id, execution)
                    self._runner.run_pending(project_id, resume=(task, result))
                else:
                    self._storage.update_execution(execution.id, ExecutionStatus.REJECTED.value)
                    self._gate.cancel_open_tasks(project_id)

        state = self._tasks.state(project_id)
        decision = "approved" if approve else "rejected"
        message = describe(state)
        if repeated:
            message = "This request was already %s. %s" % (decision, message)
        return ActionDecisionResponse(
            **state.model_dump(), action_id=action_id, decision=decision, message=message
        )

    def _locate(self, action_id: int) -> Tuple[int, TaskOut]:
        execution = self._load(action_id)
        raw_task = self._storage.get_task(execution.task_id)
        if raw_task is None:
            raise not_found("action_not_found", "No such action.")
        task = TaskOut.model_validate(raw_task)
        return task.project_id, task

    def _load(self, action_id: int) -> ExecutionOut:
        raw = self._storage.get_execution(action_id)
        if raw is None:
            raise not_found("action_not_found", "No such action.")
        return ExecutionOut.model_validate(raw)

    def _check_still_valid(
        self, execution: ExecutionOut, project_id: int, command_hash: Optional[str]
    ) -> None:
        if command_hash is not None and command_hash != self._gate.hash_command(
            project_id, execution.command
        ):
            raise conflict(
                "approval_mismatch", "The pending command changed since you reviewed it.", project_id
            )
        if self._gate.is_expired(execution):
            self._gate.expire(project_id, execution)
            raise conflict("action_expired", "This approval request has expired.", project_id)

    @staticmethod
    def _is_repeat(execution: ExecutionOut, approve: bool, project_id: int) -> bool:
        """True if this same decision was already applied; raises if a different one was."""
        status = execution.status
        if status == ExecutionStatus.PENDING_APPROVAL:
            return False
        if status == ExecutionStatus.EXPIRED:
            raise conflict("action_expired", "This approval request has expired.", project_id)
        was_approved = status in (ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED)
        if (approve and was_approved) or (not approve and status == ExecutionStatus.REJECTED):
            return True
        raise conflict(
            "action_already_decided",
            "This request was already decided (%s)." % status.value,
            project_id,
        )
