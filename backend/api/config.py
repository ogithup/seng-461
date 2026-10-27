"""Runtime configuration for the API layer.

Limits here are development defaults (see docs/api-contracts.md); calibrate them
once the real agent is connected.
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError("%s must be an integer, got %r" % (name, raw))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    # Where each project's isolated workspace lives: <workspace_root>/project_<id>/
    workspace_root: Path = _REPO_ROOT / "workspaces"
    # SQLite file holding projects, tasks and execution logs. Tests point this at a temp file.
    database_path: Path = _REPO_ROOT / "data" / "app.db"
    # Optional "package.module:Name" overrides for the agent and the site generator.
    agent_impl: Optional[str] = None
    generator_impl: Optional[str] = None
    # Origins allowed to call the API from a browser (Vite dev server by default).
    cors_origins: Tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

    # Submissions (POST /api/projects, POST /api/chat).
    require_idempotency_key: bool = False
    rate_limit_per_minute: int = 30  # 0 disables the limiter
    max_request_body_bytes: int = 1_048_576

    # Human approval of commands that are not on the executor's allowlist.
    approval_ttl_seconds: int = 900

    # Bounds on what one chat request may make the agent do.
    max_plan_steps: int = 20
    max_actions_per_task: int = 8
    max_repair_attempts: int = 2  # failed commands tolerated beyond the first
    command_timeout_seconds: int = 60

    # Output bounds for what the API returns to the browser.
    max_log_output_chars: int = 10_000
    max_file_bytes: int = 200_000
    max_listed_files: int = 1_000

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        workspace: Optional[str] = os.environ.get("WORKSPACE_ROOT")
        database: Optional[str] = os.environ.get("DATABASE_PATH")
        origins = os.environ.get("CORS_ORIGINS")
        return cls(
            workspace_root=Path(workspace) if workspace else defaults.workspace_root,
            agent_impl=os.environ.get("AGENT_IMPL") or None,
            generator_impl=os.environ.get("GENERATOR_IMPL") or None,
            database_path=Path(database) if database else defaults.database_path,
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip())
            if origins
            else defaults.cors_origins,
            require_idempotency_key=_env_bool(
                "REQUIRE_IDEMPOTENCY_KEY", defaults.require_idempotency_key
            ),
            rate_limit_per_minute=_env_int(
                "API_RATE_LIMIT_PER_MINUTE", defaults.rate_limit_per_minute
            ),
            approval_ttl_seconds=_env_int(
                "APPROVAL_TTL_SECONDS", defaults.approval_ttl_seconds
            ),
            command_timeout_seconds=_env_int(
                "COMMAND_TIMEOUT_SECONDS", defaults.command_timeout_seconds
            ),
        )
