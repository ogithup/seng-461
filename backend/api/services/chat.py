import logging
from typing import List

from backend.api.config import Settings
from backend.api.errors import ApiError, conflict
from backend.api.schemas.chat import ChatResponse
from backend.api.schemas.common import has_control_chars
from backend.api.services.approvals import ApprovalGate
from backend.api.services.ports import AgentPort, StoragePort
from backend.api.services.projects import ProjectService
from backend.api.services.runner import TaskRunner
from backend.api.services.tasks import TaskService, describe

logger = logging.getLogger("backend.api")

_MAX_STEP_LENGTH = 500
_MAX_USER_MESSAGE = 300
_UNSUPPORTED = "unsupported_request"


def _unsupported_message(exc: Exception):
    """The agent's explanation for a request it deliberately declines, or None.

    Contract (docs/sprint4-contracts.md): the exception has `code == "unsupported_request"` and a
    `user_message` meant for the user. Nothing else an agent raises is shown to the browser.
    """
    if getattr(exc, "code", None) != _UNSUPPORTED:
        return None
    message = getattr(exc, "user_message", None)
    if not isinstance(message, str) or not message.strip() or has_control_chars(message):
        return "This kind of website is not supported yet."
    return message.strip()[:_MAX_USER_MESSAGE]


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
        except Exception as exc:
            unsupported = _unsupported_message(exc)
            if unsupported is not None:
                raise ApiError(422, _UNSUPPORTED, unsupported, project_id=project_id)
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
