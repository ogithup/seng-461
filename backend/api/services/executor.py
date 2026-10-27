"""The authorized workspace executor: the only code that writes generated files.

It does exactly two things. `write_file` writes one text file inside a project's workspace
and reports success only after reading it back. `run_command` is deliberately closed this
sprint: no shell command runs, whether or not a human approved it.
"""
import hashlib
import logging
import os
import tempfile
import time
from pathlib import Path, PurePosixPath

from backend.api.errors import ApiError
from backend.api.schemas.contracts import ExecutionRequest, ExecutionResult, WriteFileRequest
from backend.api.services.workspace import WorkspaceService

logger = logging.getLogger("backend.api")

# Static-site material only. Executable or opaque formats are refused outright.
ALLOWED_SUFFIXES = frozenset(
    {".html", ".css", ".js", ".json", ".svg", ".txt", ".md", ".xml", ".webmanifest"}
)


def _failure(message: str, started: float) -> ExecutionResult:
    return ExecutionResult(
        success=False, stderr=message, duration_ms=int((time.monotonic() - started) * 1000)
    )


class WorkspaceExecutor:
    def __init__(self, workspace: WorkspaceService, max_file_bytes: int, max_files: int):
        self._workspace = workspace
        self._max_file_bytes = max_file_bytes
        self._max_files = max_files

    # Commands: closed in Sprint 3.

    def is_allowed(self, command: str) -> bool:
        return False

    def run_command(self, request: ExecutionRequest, approved: bool = False) -> ExecutionResult:
        return ExecutionResult(
            success=False, stderr="Shell command execution is disabled in this release."
        )

    # Files.

    def write_file(self, request: WriteFileRequest) -> ExecutionResult:
        started = time.monotonic()
        base = Path(request.working_directory)
        project_id = _project_id_of(base)
        if project_id is None or self._workspace.project_dir(project_id).resolve() != base.resolve():
            return _failure("Working directory is not a project workspace.", started)

        try:
            target = self._workspace.resolve(project_id, request.path)
        except ApiError:
            return _failure("Path is outside the project workspace or not allowed.", started)

        rel = PurePosixPath(request.path.replace("\\", "/"))
        if rel.suffix.lower() not in ALLOWED_SUFFIXES:
            return _failure("File type %r is not allowed." % rel.suffix, started)
        data = request.content.encode("utf-8")
        if len(data) > self._max_file_bytes:
            return _failure("File is larger than %d bytes." % self._max_file_bytes, started)
        if target.is_dir():
            return _failure("Path is an existing directory.", started)
        if not target.exists() and len(self._workspace.list_files(project_id)[0]) >= self._max_files:
            return _failure("Project already has the maximum number of files.", started)

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Re-check after creating parents: nothing we made may point outside the workspace.
            if self._workspace.resolve(project_id, request.path) != target:
                return _failure("Path is outside the project workspace.", started)
            self._atomic_write(target, data)
            written = target.read_bytes()
        except (OSError, ApiError) as exc:
            logger.warning("write_file failed for project %s: %s", project_id, exc)
            return _failure("Could not write the file: %s" % exc.__class__.__name__, started)

        if written != data:
            return _failure("Read-back verification failed: file content differs.", started)
        digest = hashlib.sha256(data).hexdigest()[:12]
        return ExecutionResult(
            success=True,
            stdout="wrote %s (%d bytes, sha256 %s)" % (rel.as_posix(), len(data), digest),
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    @staticmethod
    def _atomic_write(target: Path, data: bytes) -> None:
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp, str(target))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def _project_id_of(base: Path):
    name = base.name
    if not name.startswith("project_") or not name[8:].isdigit():
        return None
    return int(name[8:])
