"""FileEditor executor: all operations delegate to sandbox."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from sdk.tool import ToolExecutor
from tools.sandbox.session_manager import get_default_session_manager

if TYPE_CHECKING:
    from sdk.agent.runner_context import RunnerContext

from tools.file_editor.definition import (
    CommandLiteral,
    FileEditorAction,
    FileEditorObservation,
)


class FileEditorExecutor(ToolExecutor):
    """File editor executor backed by sandbox."""

    def __init__(
        self,
        workspace_root: str | None = None,
    ):
        # workspace_root already resolved to absolute path at source
        # (BaseWorkspace._resolve_working_dir); no re-normalization needed.
        self.workspace_root = workspace_root
        self._sandbox_manager = get_default_session_manager()

    def _resolve(self, path_str: str) -> str:
        """Resolve path against workspace_root if set."""
        path = Path(path_str.strip())
        # 如果没有工作区限制，直接返回规范化路径
        if self.workspace_root is None:
            return str(path.resolve())

        if not path.is_absolute():
            path = Path(self.workspace_root) / path
        return str(path.resolve())

    def __call__(
        self,
        action: FileEditorAction,
        context: "RunnerContext | None" = None,
    ) -> FileEditorObservation:
        if self.workspace_root is None:
            return FileEditorObservation.from_text(
                text="FileEditorExecutor requires workspace_root to be set.",
                command=action.command,
                is_error=True,
            )

        session = self._sandbox_manager.resolve_context(context, str(self.workspace_root))
        sandbox = self._sandbox_manager.get_or_create(session)

        file_path = self._resolve(action.path)

        if action.command == "view":
            return self._view(sandbox, file_path, action.view_range, action.offset, action.limit)
        elif action.command == "create":
            return self._create(sandbox, file_path, action.file_text or "")
        elif action.command == "str_replace":
            return self._str_replace(sandbox, file_path, action.old_str, action.new_str or "")
        elif action.command == "ls":
            return self._ls(sandbox, file_path)
        else:
            return FileEditorObservation.from_text(
                text=f"Unknown command: '{action.command}'",
                command=action.command,
                is_error=True,
            )

    def _view(
        self,
        sandbox,
        file_path: str,
        view_range: list[int] | None,
        offset: int | None,
        limit: int | None,
    ) -> FileEditorObservation:
        from tools.file_editor.definition import FileEditorObservation

        # Compute offset/limit from view_range or direct params
        if view_range:
            start = max(0, view_range[0] - 1)
            end_line = view_range[1]
            read_limit = (end_line - start) if end_line != -1 else 2000
        else:
            start = offset or 0
            read_limit = limit or 500

        content = self._sandbox_manager.run_in_session(
            sandbox.read(file_path, offset=start, limit=read_limit),
        )
        is_err = content.startswith("Error:")
        return FileEditorObservation.from_text(
            text=content,
            command="view",
            path=file_path,
            is_error=is_err,
        )

    def _create(self, sandbox, file_path: str, content: str) -> FileEditorObservation:
        error = self._sandbox_manager.run_in_session(
            sandbox.write(file_path, content),
        )
        if error:
            return FileEditorObservation.from_text(
                text=error, command="create", path=file_path, is_error=True
            )
        return FileEditorObservation.from_text(
            text=f"File created successfully: {file_path}",
            command="create",
            path=file_path,
            prev_exist=False,
            new_content=content,
        )

    def _str_replace(
        self, sandbox, file_path: str, old_str: str | None, new_str: str
    ) -> FileEditorObservation:
        if old_str is None:
            return FileEditorObservation.from_text(
                text="str_replace requires old_str parameter.",
                command="str_replace",
                is_error=True,
            )
        count, error = self._sandbox_manager.run_in_session(
            sandbox.edit(file_path, old_str, new_str),
        )
        if error:
            return FileEditorObservation.from_text(
                text=error, command="str_replace", path=file_path, is_error=True
            )
        return FileEditorObservation.from_text(
            text=f"Successfully replaced {count} occurrence(s) in '{file_path}'",
            command="str_replace",
            path=file_path,
        )

    def _ls(self, sandbox, file_path: str) -> FileEditorObservation:
        infos = self._sandbox_manager.run_in_session(
            sandbox.ls_info(file_path),
        )
        if not infos:
            lines = f"(empty directory or not found): {file_path}"
        else:
            lines = "\n".join(
                f"{'d' if fi.is_directory else 'f'}  {fi.name}" for fi in infos
            )
        return FileEditorObservation.from_text(
            text=lines, command="view", path=file_path
        )
