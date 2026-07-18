"""Grep tool executor: delegates to sandbox.grep_raw()."""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING
from sdk.tool import ToolExecutor
from tools.sandbox.session_manager import get_default_session_manager
if TYPE_CHECKING:
    from sdk.agent.runner_context import RunnerContext
from tools.grep.definition import GrepAction, GrepObservation


class GrepExecutor(ToolExecutor[GrepAction, GrepObservation]):
    """Executor for grep content search; backed by sandbox.grep_raw()."""

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

    def __call__(self, action: GrepAction, context: "RunnerContext | None" = None) -> GrepObservation:
        session = self._sandbox_manager.resolve_context(context, self.working_dir)
        sandbox = self._sandbox_manager.get_or_create(session)
        search_path = self._resolve_path(action.path)
        result = self._sandbox_manager.run_in_session(
            sandbox.grep_raw(pattern=action.pattern, path=search_path, glob=action.include),
        )
        if isinstance(result, str):
            return GrepObservation.from_text(
                text=result, matches=[], pattern=action.pattern,
                search_path=search_path, include_pattern=action.include, is_error=True,
            )
        truncated = len(result) >= 100
        matches_trimmed = result[:100]
        match_paths = list({m.path for m in matches_trimmed})
        if not match_paths:
            include_info = f" (filtered by '{action.include}')" if action.include else ""
            text = (f"No files found containing pattern '{action.pattern}'"
                    f" in '{search_path}'{include_info}")
        else:
            include_info = f" (filtered by '{action.include}')" if action.include else ""
            lines_out = "\n".join(f"{m.path}:{m.line}: {m.text}" for m in matches_trimmed)
            text = (f"Found {len(matches_trimmed)} match(es) for '{action.pattern}'"
                    f" in '{search_path}'{include_info}:\n{lines_out}")
            if truncated:
                text += "\n\n[Results truncated to first 100 matches.]"
        return GrepObservation.from_text(
            text=text, matches=match_paths, pattern=action.pattern,
            search_path=search_path, include_pattern=action.include, truncated=truncated,
        )

