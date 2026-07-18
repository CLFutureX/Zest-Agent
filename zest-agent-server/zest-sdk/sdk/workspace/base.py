from abc import ABC, abstractmethod
from pathlib import Path
from typing import Annotated, Any

from pydantic import BeforeValidator, Field, field_validator

from sdk.git.models import GitChange, GitDiff
from common.logger import get_logger
from common.utils.models import DiscriminatedUnionMixin
from sdk.workspace.models import CommandResult, FileOperationResult


logger = get_logger(__name__)


def _resolve_working_dir(v: str | Path | None) -> str:
    """Normalize working_dir to an absolute, cross-platform path string.

    - Resolves relative paths to absolute using Path.resolve() (handles
      symlinks, removes '..' components, and works consistently on both
      Windows and Linux).
    - Returns an empty string only when input is None / empty.
    - This is the **single source of truth** — downstream code must NOT
      re-normalize working_dir.
    """
    if not v:
        return ""
    return str(Path(v).resolve())


class BaseWorkspace(DiscriminatedUnionMixin, ABC):
    """Abstract base class for workspace implementations.

    Workspaces provide a sandboxed environment where agents can execute commands,
    read/write files, and perform other operations. All workspace implementations
    support the context manager protocol for safe resource management.

    Example:
        >>> with workspace:
        ...     result = workspace.execute_command("echo 'hello'")
        ...     content = workspace.read_file("example.txt")
    """

    working_dir: Annotated[
        str,
        BeforeValidator(_resolve_working_dir),
        Field(
            default="",
            description=(
                "The working directory for agent operations and tool execution. "
                "Accepts both string paths and Path objects. "
                "Path objects and relative paths are automatically resolved to "
                "absolute paths. If empty, defaults to parent directory of "
                "current project."
            )
        ),
    ]

    # ===================== 核心优化 =====================
    @field_validator("working_dir", mode="before")
    @classmethod
    def set_default_working_dir(cls, v: str | Path | None) -> str | Path | None:
        """
        如果 working_dir 为空，自动设置为：当前项目父目录
        """
        # 如果传入空值，使用默认路径：当前文件的父目录（项目根）
        if not v:
            default_dir = Path(__file__).parent.parent  # 项目父目录
            return default_dir

        # 否则使用传入的值（BeforeValidator 会负责 resolve）
        return v
    # ====================================================

    def __enter__(self) -> "BaseWorkspace":
        """Enter the workspace context.

        Returns:
            Self for use in with statements
        """
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the workspace context and cleanup resources.

        Default implementation performs no cleanup. Subclasses should override
        to add cleanup logic (e.g., stopping containers, closing connections).

        Args:
            exc_type: Exception type if an exception occurred
            exc_val: Exception value if an exception occurred
            exc_tb: Exception traceback if an exception occurred
        """
        pass

    @abstractmethod
    def execute_command(
        self,
        command: str,
        cwd: str | Path | None = None,
        timeout: float = 30.0,
    ) -> CommandResult:
        """Execute a bash command on the system.

        Args:
            command: The bash command to execute
            cwd: Working directory for the command (optional)
            timeout: Timeout in seconds (defaults to 30.0)

        Returns:
            CommandResult: Result containing stdout, stderr, exit_code, and other
                metadata

        Raises:
            Exception: If command execution fails
        """
        ...

    @abstractmethod
    def file_upload(
        self,
        source_path: str | Path,
        destination_path: str | Path,
    ) -> FileOperationResult:
        """Upload a file to the system.

        Args:
            source_path: Path to the source file
            destination_path: Path where the file should be uploaded

        Returns:
            FileOperationResult: Result containing success status and metadata

        Raises:
            Exception: If file upload fails
        """
        ...

    @abstractmethod
    def file_download(
        self,
        source_path: str | Path,
        destination_path: str | Path,
    ) -> FileOperationResult:
        """Download a file from the system.

        Args:
            source_path: Path to the source file on the system
            destination_path: Path where the file should be downloaded

        Returns:
            FileOperationResult: Result containing success status and metadata

        Raises:
            Exception: If file download fails
        """
        ...

    @abstractmethod
    def git_changes(self, path: str | Path) -> list[GitChange]:
        """Get the git changes for the repository at the path given.

        Args:
            path: Path to the git repository

        Returns:
            list[GitChange]: List of changes

        Raises:
            Exception: If path is not a git repository or getting changes failed
        """

    @abstractmethod
    def git_diff(self, path: str | Path) -> GitDiff:
        """Get the git diff for the file at the file at the path given.

        Args:
            path: Path to the file

        Returns:
            GitDiff: Git diff

        Raises:
            Exception: If path is not a git repository or getting diff failed
        """

    def pause(self) -> None:
        """Pause the workspace to conserve resources.

        For local workspaces, this is a no-op.
        For container-based workspaces, this pauses the container.

        Raises:
            NotImplementedError: If the workspace type does not support pausing.
        """
        raise NotImplementedError(f"{type(self).__name__} does not support pause()")

    def resume(self) -> None:
        """Resume a paused workspace.

        For local workspaces, this is a no-op.
        For container-based workspaces, this resumes the container.

        Raises:
            NotImplementedError: If the workspace type does not support resuming.
        """
        raise NotImplementedError(f"{type(self).__name__} does not support resume()")