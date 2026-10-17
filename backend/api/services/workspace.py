"""Read-only access to a project's workspace folder.

Everything the API shows from the workspace goes through `resolve`, which keeps paths
inside <workspace_root>/project_<id>/: no `..`, no absolute or drive paths, no symlink
that resolves outside, and nothing hidden (dotfiles such as `.env`, `.git`).
"""
import os
from pathlib import Path, PurePosixPath
from typing import List, Tuple

from backend.api.errors import ApiError, forbidden, not_found
from backend.api.schemas.files import FileInfo

_SKIPPED_DIRS = frozenset({"node_modules", "__pycache__"})


def _is_hidden(name: str) -> bool:
    return name.startswith(".") or name in _SKIPPED_DIRS


def _is_inside(real_base: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(real_base)
    except ValueError:
        return False
    return True


class WorkspaceService:
    def __init__(self, root: Path, max_file_bytes: int, max_listed_files: int):
        self._root = Path(root).resolve()
        self._max_file_bytes = max_file_bytes
        self._max_listed_files = max_listed_files

    def project_dir(self, project_id: int) -> Path:
        return self._root / ("project_%d" % project_id)

    def ensure_project_dir(self, project_id: int) -> Path:
        path = self.project_dir(project_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def resolve(self, project_id: int, relative_path: str) -> Path:
        base = self.project_dir(project_id).resolve()
        denied = forbidden(
            "path_not_allowed", "That path is outside the project workspace.", project_id
        )
        if not relative_path or "\x00" in relative_path:
            raise denied
        rel = PurePosixPath(relative_path.replace("\\", "/"))
        if rel.is_absolute():
            raise denied
        for part in rel.parts:
            # ":" blocks Windows drive letters and alternate data streams.
            if part == ".." or ":" in part or _is_hidden(part):
                raise denied
        target = base.joinpath(*rel.parts).resolve()  # follows symlinks and junctions
        if not _is_inside(base, target):
            raise denied
        return target

    def list_files(self, project_id: int) -> Tuple[List[FileInfo], bool]:
        base = self.project_dir(project_id)
        files: List[FileInfo] = []
        if not base.is_dir():
            return files, False
        real_base = base.resolve()
        for dirpath, dirnames, filenames in os.walk(str(base), followlinks=False):
            current = Path(dirpath)
            # is_symlink() misses Windows junctions on Python < 3.12, so also require that
            # what we are about to descend into or list really lives inside the workspace.
            dirnames[:] = sorted(
                d
                for d in dirnames
                if not _is_hidden(d) and _is_inside(real_base, current / d)
            )
            for name in sorted(filenames):
                full = current / name
                if _is_hidden(name) or not full.is_file() or not _is_inside(real_base, full):
                    continue
                if len(files) >= self._max_listed_files:
                    return files, True
                files.append(
                    FileInfo(path=full.relative_to(base).as_posix(), size=full.stat().st_size)
                )
        return files, False

    def read_text(self, project_id: int, relative_path: str) -> Tuple[str, int, str]:
        """Returns (normalized relative path, size, content)."""
        target = self.resolve(project_id, relative_path)
        if not target.is_file():
            raise not_found("file_not_found", "No such file in the project.", project_id)
        size = target.stat().st_size
        if size > self._max_file_bytes:
            raise ApiError(
                413,
                "file_too_large",
                "File is larger than the %d byte viewer limit." % self._max_file_bytes,
                project_id=project_id,
            )
        try:
            content = target.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            raise ApiError(
                415, "unsupported_file_type", "Only UTF-8 text files can be viewed.", project_id=project_id
            )
        base = self.project_dir(project_id).resolve()
        return target.relative_to(base).as_posix(), size, content

    def has_index_html(self, project_id: int) -> bool:
        index = self.project_dir(project_id) / "index.html"
        return index.is_file() and not index.is_symlink()

    def preview_file(self, project_id: int, relative_path: str) -> Path:
        target = self.resolve(project_id, relative_path or "index.html")
        if not target.is_file():
            raise not_found("file_not_found", "No such file in the project.", project_id)
        return target
