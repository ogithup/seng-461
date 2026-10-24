import logging
from typing import List

from backend.api.config import Settings
from backend.api.errors import ApiError, conflict
from backend.api.schemas.chat import ChatResponse
from backend.api.services.approvals import ApprovalGate
from backend.api.services.ports import AgentPort, StoragePort
from backend.api.services.projects import ProjectService
from backend.api.services.runner import TaskRunner
from backend.api.services.tasks import TaskService, describe

logger = logging.getLogger("backend.api")

_MAX_STEP_LENGTH = 500


class ChatService:
    """Frontend -> agent: turn a user message into tasks and run them."""

    def __init__(
        self,
        storage: StoragePort,
        agent: AgentPort,
        projects: ProjectService,
        gate: ApprovalGate,
        runner: TaskRunner,
        tasks: TaskService,
        settings: Settings,
    ):
        self._storage = storage
        self._agent = agent
        self._projects = projects
        self._gate = gate
        self._runner = runner
        self._tasks = tasks
        self._settings = settings

    def handle(self, project_id: int, message: str) -> ChatResponse:
        self._projects.require(project_id)
        with self._runner.exclusive(project_id):
            if self._gate.get_pending(project_id) is not None:
                raise conflict(
                    "pending_action_exists",
                    "Approve or reject the pending command before sending a new request.",
                    project_id,
                )
            for step in self._plan(project_id, message):
                self._storage.create_task(project_id, "step", step)
            self._runner.run_pending(project_id)

        state = self._tasks.state(project_id)
        return ChatResponse(**state.model_dump(), message=describe(state))

    def _plan(self, project_id: int, message: str) -> List[str]:
        try:
            raw = self._agent.plan(message)
        except Exception:
            logger.exception("agent failed to plan for project %s", project_id)
            raise ApiError(
                502, "agent_error", "The agent could not plan this request.",
                retryable=True, project_id=project_id,
            )
        if not isinstance(raw, (list, tuple)):
            logger.error("agent.plan returned %s, expected a list of steps", type(raw).__name__)
            raise ApiError(
                502, "agent_error", "The agent returned an unusable plan.", project_id=project_id
            )
        steps = [str(s).strip()[:_MAX_STEP_LENGTH] for s in raw if str(s).strip()]
        steps = steps[: self._settings.max_plan_steps]
        if not steps:
            raise ApiError(
                502, "agent_empty_plan", "The agent returned an empty plan.", project_id=project_id
            )
        return steps
