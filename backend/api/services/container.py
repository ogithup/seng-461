"""Wires the services together.

`build_services()` with no arguments gives the Sprint 1 fake agent, SQLite storage at
`Settings.database_path` (env DATABASE_PATH) and mock execution. To integrate a real
module, pass it in:

    build_services(storage=Storage(...), agent=Orchestrator(...), executor=Executor(...))

Each argument must satisfy the matching port in `ports.py`.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from backend.agent import Orchestrator
from backend.api.config import Settings
from backend.api.services.actions import ActionService
from backend.api.services.approvals import ApprovalGate
from backend.api.services.chat import ChatService
from backend.api.services.guards import IdempotencyStore, RateLimiter
from backend.api.services.mocks import MockExecutor
from backend.api.services.ports import AgentPort, ExecutorPort, StoragePort
from backend.api.services.projects import ProjectService
from backend.api.services.runner import TaskRunner
from backend.api.services.tasks import TaskService
from backend.api.services.workspace import WorkspaceService
from backend.storage.sqlite_storage import SQLiteStorage


@dataclass
class Services:
    settings: Settings
    workspace: WorkspaceService
    projects: ProjectService
    tasks: TaskService
    chat: ChatService
    actions: ActionService
    idempotency: IdempotencyStore
    limiter: RateLimiter


def build_services(
    settings: Optional[Settings] = None,
    storage: Optional[StoragePort] = None,
    agent: Optional[AgentPort] = None,
    executor: Optional[ExecutorPort] = None,
    clock: Optional[Callable[[], datetime]] = None,
) -> Services:
    settings = settings or Settings.from_env()
    storage = storage or SQLiteStorage(settings.database_path)
    agent = agent or Orchestrator()
    executor = executor or MockExecutor()

    workspace = WorkspaceService(
        settings.workspace_root, settings.max_file_bytes, settings.max_listed_files
    )
    projects = ProjectService(storage, workspace)
    gate = ApprovalGate(storage, settings, clock)
    runner = TaskRunner(storage, agent, executor, workspace, gate, settings)
    tasks = TaskService(storage, projects, gate, settings)
    return Services(
        settings=settings,
        workspace=workspace,
        projects=projects,
        tasks=tasks,
        chat=ChatService(storage, agent, projects, gate, runner, tasks, settings),
        actions=ActionService(storage, gate, runner, tasks),
        idempotency=IdempotencyStore(),
        limiter=RateLimiter(settings.rate_limit_per_minute),
    )
