"""Glob tool executor: delegates to sandbox.glob_info()."""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING
from sdk.tool import ToolExecutor
from tools.sandbox.session_manager import get_default_session_manager
if TYPE_CHECKING:
    from sdk.agent.runner_context import RunnerContext
from tools.glob.definition import GlobAction, GlobObservation


class GlobExecutor(ToolExecutor[GlobAction, GlobObservation]):
    """Executor for glob pattern matching; backed by sandbox.glob_info()."""

    def __init__(self, working_dir: str) -> None:
        self.working_dir = working_dir
        self._sandbox_manager = get_default_session_manager()

    def _resolve_path(self, path: str | None) -> str:
        """Resolve path against working_dir if relative."""
        if not path:
            return self.working_dir
        p = Path(path)
        if not p.is_absolute():
            return str(Path(self.working_dir) / p)
        return path

    def __call__(self, action: GlobAction, context: "RunnerContext | None" = None) -> GlobObservation:
        session = self._sandbox_manager.resolve_context(context, self.working_dir)
        sandbox = self._sandbox_manager.get_or_create(session)
        search_path = self._resolve_path(action.path)
        infos = self._sandbox_manager.run_in_session(
            sandbox.glob_info(pattern=action.pattern, path=search_path),
        )
        files = [fi.path for fi in infos if not fi.is_directory]
        truncated = len(files) >= 100
        files = files[:100]
        if not files:
            content = (f"No files found matching pattern '{action.pattern}'"
                       f" in '{search_path}'")
        else:
            file_list = "\n".join(files)
            content = (f"Found {len(files)} file(s) matching pattern '{action.pattern}'"
                       f" in '{search_path}':\n{file_list}")
            if truncated:
                content += "\n\n[Results truncated to first 100 files.]"
        return GlobObservation.from_text(
            text=content, files=files, pattern=action.pattern,
            search_path=search_path, truncated=truncated,
        )

