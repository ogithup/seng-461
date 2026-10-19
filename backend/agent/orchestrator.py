"""AgentPort implementation for the Sprint 1 communication demo."""

from typing import Any, List, Optional

from . import planner
from .action_schema import AgentAction


class Orchestrator:
    """Produce fake plans; leave task persistence and execution to the API.

    Stateless so a shared instance cannot mix requests between projects.
    """

    def plan(self, user_request: str) -> List[str]:
        return planner.plan(user_request)

    def next_action(
        self, task: Any, last_result: Optional[Any]
    ) -> Optional[AgentAction]:
        """Finish the fake step without requesting a command.

        Accept the API's task/result objects (or dictionaries). Sprint 1 does
        not inspect them; the API runner owns success/failure transitions.
        """
        return None
