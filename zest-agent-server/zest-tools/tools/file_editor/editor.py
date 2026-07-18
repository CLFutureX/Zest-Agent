import base64
import mimetypes
import os
import re
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_args

from binaryornot.check import is_binary

from sdk import ImageContent, TextContent
from common.logger import get_logger
from common.utils.truncate import maybe_truncate
from tools.file_editor.definition import (
    CommandLiteral,
    FileEditorObservation,
)
from tools.file_editor.exceptions import (
    EditorToolParameterInvalidError,
    EditorToolParameterMissingError,
    FileValidationError,
    ToolError,
)
from tools.file_editor.utils.config import SNIPPET_CONTEXT_WINDOW
from tools.file_editor.utils.constants import (
    BINARY_FILE_CONTENT_TRUNCATED_NOTICE,
    DIRECTORY_CONTENT_TRUNCATED_NOTICE,
    MAX_RESPONSE_LEN_CHAR,
    TEXT_FILE_CONTENT_TRUNCATED_NOTICE,
)
from tools.file_editor.utils.encoding import (
    EncodingManager,
    with_encoding,
)
from tools.file_editor.utils.history import FileHistoryManager
from tools.file_editor.utils.shell import run_shell_cmd
from tools.sandbox.base import FileInfo, Sandbox
from tools.sandbox.session_manager import run_async


logger = get_logger(__name__)

# Supported image extensions for viewing as base64-encoded content
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


class FileEditor:
    """
    An filesystem editor tool that allows the agent to
    - view
    - create
    - navigate
    - edit files
    The tool parameters are defined by Anthropic and are not editable.

    Original implementation: https://github.com/anthropics/anthropic-quickstarts/blob/main/computer-use-demo/computer_use_demo/tools/edit.py
    """

    MAX_FILE_SIZE_MB: int = 10  # Maximum file size in MB
    _history_manager: FileHistoryManager
    _max_file_size: int
    _encoding_manager: EncodingManager
    _cwd: str
    _sandbox: Sandbox | None

    def __init__(
        self,
        workspace_root: str | None = None,
        max_file_size_mb: int | None = None,
    ):
        """Initialize the editor.

        Args:
            max_file_size_mb: Maximum file size in MB. If None, uses the default
                MAX_FILE_SIZE_MB.
            workspace_root: Root directory that serves as the current working
                directory for relative path suggestions. Must be an absolute path.
                If None, no path suggestions will be provided for relative paths.
        """
        self._history_manager = FileHistoryManager(max_history_per_file=10)
        self._max_file_size = (
            (max_file_size_mb or self.MAX_FILE_SIZE_MB) * 1024 * 1024
        )  # Convert to bytes

        # Initialize encoding manager
        self._encoding_manager = EncodingManager()
        self._sandbox: Sandbox | None = None
        self._sandbox_runner: Callable[[Any], Any] = run_async

        # Set cwd (current working directory) if workspace_root is provided
        if workspace_root is not None:
            workspace_path = Path(workspace_root)
            # Ensure workspace_root is an absolute path
            if not workspace_path.is_absolute():
                workspace_path = workspace_path.resolve()
            self._cwd = str(workspace_path)
        else:
            self._cwd = os.path.abspath(os.getcwd())
        logger.info(f"FileEditor initialized with cwd: {self._cwd}")

    def set_sandbox(self, sandbox: Sandbox | None) -> None:
        self._sandbox = sandbox

    def set_sandbox_runner(self, runner: Callable[[Any], Any] | None) -> None:
        self._sandbox_runner = runner or run_async

    def _run_sandbox(self, coro):
        return self._sandbox_runner(coro)

    def _path_exists(self, path: Path) -> bool:
        if self._sandbox is None:
            return path.exists()
        return bool(self._run_sandbox(self._sandbox.exists(str(path))))

    def _path_is_dir(self, path: Path) -> bool:
        if self._sandbox is None:
            return path.is_dir()
        return bool(self._run_sandbox(self._sandbox.is_dir(str(path))))

    def _path_is_file(self, path: Path) -> bool:
        if self._sandbox is None:
            return path.is_file()
        return bool(self._run_sandbox(self._sandbox.is_file(str(path))))

    def _get_file_size(self, path: Path) -> int:
        if self._sandbox is None:
            return os.path.getsize(path)
        return int(self._run_sandbox(self._sandbox.get_size(str(path))))

    def _read_text_content(self, path: Path, encoding: str = "utf-8") -> str:
        if self._sandbox is None:
            with open(path, encoding=encoding) as f:
                return f.read()
        return self._run_sandbox(self._sandbox.read(str(path)))

    def _read_binary_content(self, path: Path) -> bytes:
        if self._sandbox is None:
            with open(path, "rb") as f:
                return f.read()
        return self._run_sandbox(self._sandbox.read_bytes(str(path)))

    def _write_text_content(self, path: Path, file_text: str, encoding: str = "utf-8") -> None:
        if self._sandbox is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding=encoding) as f:
                f.write(file_text)
            return
        self._run_sandbox(self._sandbox.write(str(path), file_text))

    def _list_directory(self, path: Path, max_depth: int = 2) -> list[FileInfo]:
        if self._sandbox is None:
            _, stdout, stderr = run_shell_cmd(
                rf"find -L {path} -maxdepth {max_depth} -not \( -path '{path}/\.*' -o "
                rf"-path '{path}/*/\.*' \) | sort",
                truncate_notice=DIRECTORY_CONTENT_TRUNCATED_NOTICE,
            )
            if stderr:
                raise ToolError(stderr)
            paths = stdout.strip().split("\n") if stdout.strip() else []
            results: list[FileInfo] = []
            for item in paths:
                item_path = Path(item)
                if not self._path_exists(item_path):
                    continue
                item_stat = item_path.stat()
                results.append(
                    FileInfo(
                        name=item_path.name,
                        path=str(item_path),
                        size=int(item_stat.st_size),
                        is_directory=self._path_is_dir(item_path),
                        modified_time=float(item_stat.st_mtime),
                    )
                )
            return results
        return self._run_sandbox(self._sandbox.list_dir(str(path), max_depth=max_depth))

    def __call__(
        self,
        *,
        command: CommandLiteral,
        path: str,
        file_text: str | None = None,
        view_range: list[int] | None = None,
        old_str: str | None = None,
        new_str: str | None = None,
        insert_line: int | None = None,
    ) -> FileEditorObservation:
        _path = Path(path)
        self.validate_path(command, _path)
        if command == "view":
            return self.view(_path, view_range)
        elif command == "create":
            if file_text is None:
                raise EditorToolParameterMissingError(command, "file_text")
            self.write_file(_path, file_text)
            self._history_manager.add_history(_path, file_text)
            return FileEditorObservation.from_text(
                text=f"File created successfully at: {_path}",
                command=command,
                path=str(_path),
                new_content=file_text,
                prev_exist=False,
            )
        elif command == "str_replace":
            if old_str is None:
                raise EditorToolParameterMissingError(command, "old_str")
            if new_str is None:
                raise EditorToolParameterMissingError(command, "new_str")
            if new_str == old_str:
                raise EditorToolParameterInvalidError(
                    "new_str",
                    new_str,
                    "No replacement was performed. `new_str` and `old_str` must be "
                    "different.",
                )
            return self.str_replace(_path, old_str, new_str)
        elif command == "insert":
            if insert_line is None:
                raise EditorToolParameterMissingError(command, "insert_line")
            if new_str is None:
                raise EditorToolParameterMissingError(command, "new_str")
            return self.insert(_path, insert_line, new_str)
        elif command == "undo_edit":
            return self.undo_edit(_path)

        raise ToolError(
            f"Unrecognized command {command}. The allowed commands for "
            f"{self.__class__.__name__} tool are: {', '.join(get_args(CommandLiteral))}"
        )

    @with_encoding
    def _count_lines(self, path: Path, encoding: str = "utf-8") -> int:
        """
        Count the number of lines in a file safely.

        Args:
            path: Path to the file
            encoding: The encoding to use when reading the file (auto-detected by
                decorator)

        Returns:
            The number of lines in the file
        """
        content = self._read_text_content(path, encoding=encoding)
        return len(content.splitlines())

    @with_encoding
    def str_replace(
        self,
        path: Path,
        old_str: str,
        new_str: str | None,
    ) -> FileEditorObservation:
        """
        Implement the str_replace command, which replaces old_str with new_str in
        the file content.

        Args:
            path: Path to the file
            old_str: String to replace
            new_str: Replacement string
            enable_linting: Whether to run linting on the changes
            encoding: The encoding to use (auto-detected by decorator)
        """
        self.validate_file(path)
        new_str = new_str or ""

        # Read the entire file first to handle both single-line and multi-line
        # replacements
        file_content = self.read_file(path)

        # Find all occurrences using regex
        # Escape special regex characters in old_str to match it literally
        pattern = re.escape(old_str)
        occurrences = [
            (
                file_content.count("\n", 0, match.start()) + 1,  # line number
                match.group(),  # matched text
                match.start(),  # start position
            )
            for match in re.finditer(pattern, file_content)
        ]

        if not occurrences:
            # We found no occurrences, possibly because of extra white spaces at
            # either the front or back of the string.
            # Remove the white spaces and try again.
            old_str = old_str.strip()
            new_str = new_str.strip()
            pattern = re.escape(old_str)
            occurrences = [
                (
                    file_content.count("\n", 0, match.start()) + 1,  # line number
                    match.group(),  # matched text
                    match.start(),  # start position
                )
                for match in re.finditer(pattern, file_content)
            ]
            if not occurrences:
                raise ToolError(
                    f"No replacement was performed, old_str `{old_str}` did not "
                    f"appear verbatim in {path}."
                )
        if len(occurrences) > 1:
            line_numbers = sorted(set(line for line, _, _ in occurrences))
            raise ToolError(
                f"No replacement was performed. Multiple occurrences of old_str "
                f"`{old_str}` in lines {line_numbers}. Please ensure it is unique."
            )

        # We found exactly one occurrence
        replacement_line, matched_text, idx = occurrences[0]

        # Create new content by replacing just the matched text
        new_file_content = (
            file_content[:idx] + new_str + file_content[idx + len(matched_text) :]
        )

        # Write the new content to the file
        self.write_file(path, new_file_content)

        # Save the content to history
        self._history_manager.add_history(path, file_content)

        # Create a snippet of the edited section
        start_line = max(0, replacement_line - SNIPPET_CONTEXT_WINDOW)
        end_line = replacement_line + SNIPPET_CONTEXT_WINDOW + new_str.count("\n")

        # Read just the snippet range
        snippet = self.read_file(path, start_line=start_line + 1, end_line=end_line)

        # Prepare the success message
        success_message = f"The file {path} has been edited. "
        success_message += self._make_output(
            snippet, f"a snippet of {path}", start_line + 1
        )

        success_message += (
            "Review the changes and make sure they are as expected. Edit the "
            "file again if necessary."
        )
        return FileEditorObservation.from_text(
            text=success_message,
            command="str_replace",
            prev_exist=True,
            path=str(path),
            old_content=file_content,
            new_content=new_file_content,
        )

    def view(
        self, path: Path, view_range: list[int] | None = None
    ) -> FileEditorObservation:
        """
        View the contents of a file or a directory.
        """
        if self._path_is_dir(path):
            if view_range:
                raise EditorToolParameterInvalidError(
                    "view_range",
                    str(view_range),
                    "The `view_range` parameter is not allowed when `path` points to "
                    "a directory.",
                )

            entries = self._list_directory(path, max_depth=2)
            formatted_paths = []
            hidden_count = 0
            for entry in entries:
                entry_path = entry.path + ("/" if entry.is_directory else "")
                if Path(entry.path).name.startswith("."):
                    hidden_count += 1
                    continue
                formatted_paths.append(entry_path)

            msg = [
                f"Here's the files and directories up to 2 levels deep in {path}, "
                "excluding hidden items:\n" + "\n".join(formatted_paths)
            ]
            if hidden_count > 0:
                msg.append(
                    f"\n{hidden_count} hidden files/directories in this directory "
                    f"are excluded. You can use 'ls -la {path}' to see them."
                )
            stdout = "\n".join(msg)
            return FileEditorObservation.from_text(
                text=stdout,
                command="view",
                path=str(path),
                prev_exist=True,
            )

        # Check if the file is an image
        file_extension = path.suffix.lower()
        if file_extension in IMAGE_EXTENSIONS:
            # Read image file as base64
            try:
                image_bytes = self._read_binary_content(path)
                image_base64 = base64.b64encode(image_bytes).decode("utf-8")

                mime_type, _ = mimetypes.guess_type(str(path))
                if not mime_type or not mime_type.startswith("image/"):
                    mime_type = "image/png"
                output_msg = (
                    f"Image file {path} read successfully. Displaying image content."
                )
                image_url = f"data:{mime_type};base64,{image_base64}"
                return FileEditorObservation(
                    command="view",
                    content=[
                        TextContent(text=output_msg),
                        ImageContent(image_urls=[image_url]),
                    ],
                    path=str(path),
                    prev_exist=True,
                )
            except Exception as e:
                raise ToolError(f"Failed to read image file {path}: {e}") from None

        # Validate file and count lines
        self.validate_file(path)
        try:
            num_lines = self._count_lines(path)
        except UnicodeDecodeError as e:
            raise ToolError(
                f"Cannot view {path}: file contains binary content that cannot be "
                f"decoded as text. Error: {e}"
            ) from None

        start_line = 1
        if not view_range:
            file_content = self.read_file(path)
            output = self._make_output(file_content, str(path), start_line)

            return FileEditorObservation.from_text(
                text=output,
                command="view",
                path=str(path),
                prev_exist=True,
            )

        if len(view_range) != 2 or not all(isinstance(i, int) for i in view_range):
            raise EditorToolParameterInvalidError(
                "view_range",
                str(view_range),
                "It should be a list of two integers.",
            )

        start_line, end_line = view_range
        if start_line < 1 or start_line > num_lines:
            raise EditorToolParameterInvalidError(
                "view_range",
                str(view_range),
                f"Its first element `{start_line}` should be within the range of "
                f"lines of the file: {[1, num_lines]}.",
            )

        # Normalize end_line and provide a warning if it exceeds file length
        warning_message: str | None = None
        if end_line == -1:
            end_line = num_lines
        elif end_line > num_lines:
            warning_message = (
                f"We only show up to {num_lines} since there're only {num_lines} "
                "lines in this file."
            )
            end_line = num_lines

        if end_line < start_line:
            raise EditorToolParameterInvalidError(
                "view_range",
                str(view_range),
                f"Its second element `{end_line}` should be greater than or equal "
                f"to the first element `{start_line}`.",
            )

        file_content = self.read_file(path, start_line=start_line, end_line=end_line)

        # Get the detected encoding
        output = self._make_output(
            "\n".join(file_content.splitlines()), str(path), start_line
        )  # Remove extra newlines

        # Prepend warning if we truncated the end_line
        if warning_message:
            output = f"NOTE: {warning_message}\n{output}"

        return FileEditorObservation.from_text(
            text=output,
            command="view",
            path=str(path),
            prev_exist=True,
        )

    @with_encoding
    def write_file(self, path: Path, file_text: str, encoding: str = "utf-8") -> None:
        """
        Write the content of a file to a given path; raise a ToolError if an
        error occurs.

        Args:
            path: Path to the file to write
            file_text: Content to write to the file
            encoding: The encoding to use when writing the file (auto-detected by
                decorator)
        """
        try:
            self._write_text_content(path, file_text, encoding=encoding)
        except Exception as e:
            raise ToolError(f"Ran into {e} while trying to write to {path}") from None

    @with_encoding
    def insert(
        self,
        path: Path,
        insert_line: int,
        new_str: str,
        encoding: str = "utf-8",
    ) -> FileEditorObservation:
        """
        Implement the insert command, which inserts new_str at the specified line
        in the file content.

        Args:
            path: Path to the file
            insert_line: Line number where to insert the new content
            new_str: Content to insert
            enable_linting: Whether to run linting on the changes
            encoding: The encoding to use (auto-detected by decorator)
        """
        # Validate file and count lines
        self.validate_file(path)
        num_lines = self._count_lines(path)

        if insert_line < 0 or insert_line > num_lines:
            raise EditorToolParameterInvalidError(
                "insert_line",
                str(insert_line),
                f"It should be within the range of allowed values: {[0, num_lines]}",
            )

        new_str_lines = new_str.split("\n")
        file_text = self.read_file(path)
        existing_lines = file_text.splitlines()
        if file_text.endswith("\n"):
            existing_lines.append("")

        updated_lines = existing_lines[:insert_line] + new_str_lines + existing_lines[insert_line:]
        new_file_text = "\n".join(updated_lines)
        self.write_file(path, new_file_text)

        # Read just the snippet range
        start_line = max(0, insert_line - SNIPPET_CONTEXT_WINDOW)
        end_line = min(
            num_lines + len(new_str_lines),
            insert_line + SNIPPET_CONTEXT_WINDOW + len(new_str_lines),
        )
        snippet = self.read_file(path, start_line=start_line + 1, end_line=end_line)

        # Save history - we already have the lines in memory
        self._history_manager.add_history(path, file_text)

        # Read new content for result
        new_file_text = self.read_file(path)

        success_message = f"The file {path} has been edited. "
        success_message += self._make_output(
            snippet,
            "a snippet of the edited file",
            max(1, insert_line - SNIPPET_CONTEXT_WINDOW + 1),
        )

        success_message += (
            "Review the changes and make sure they are as expected (correct "
            "indentation, no duplicate lines, etc). Edit the file again if necessary."
        )
        return FileEditorObservation.from_text(
            text=success_message,
            command="insert",
            prev_exist=True,
            path=str(path),
            old_content=file_text,
            new_content=new_file_text,
        )

    def validate_path(self, command: CommandLiteral, path: Path) -> None:
        """
        Check that the path/command combination is valid.

        Validates:
        1. Path is absolute
        2. Path and command are compatible
        """
        # Check if its an absolute path
        if not path.is_absolute():
            suggestion_message = (
                "The path should be an absolute path, starting with `/`."
            )

            # Only suggest the absolute path if cwd is provided and the path exists
            if self._cwd is not None:
                suggested_path = Path(self._cwd) / path
                if self._path_exists(suggested_path):
                    suggestion_message += f" Maybe you meant {suggested_path}?"

            raise EditorToolParameterInvalidError(
                "path",
                str(path),
                suggestion_message,
            )

        # Check if path and command are compatible
        if command == "create" and self._path_exists(path):
            raise EditorToolParameterInvalidError(
                "path",
                str(path),
                f"File already exists at: {path}. Cannot overwrite files using "
                "command `create`.",
            )
        if command != "create" and not self._path_exists(path):
            raise EditorToolParameterInvalidError(
                "path",
                str(path),
                f"The path {path} does not exist. Please provide a valid path.",
            )
        if command != "view":
            if self._path_is_dir(path):
                raise EditorToolParameterInvalidError(
                    "path",
                    str(path),
                    f"The path {path} is a directory and only the `view` command can "
                    "be used on directories.",
                )

    def undo_edit(self, path: Path) -> FileEditorObservation:
        """
        Implement the undo_edit command.
        """
        current_text = self.read_file(path)
        old_text = self._history_manager.pop_last_history(path)
        if old_text is None:
            raise ToolError(f"No edit history found for {path}.")

        self.write_file(path, old_text)

        return FileEditorObservation.from_text(
            text=(
                f"Last edit to {path} undone successfully. "
                f"{self._make_output(old_text, str(path))}"
            ),
            command="undo_edit",
            path=str(path),
            prev_exist=True,
            old_content=current_text,
            new_content=old_text,
        )

    def validate_file(self, path: Path) -> None:
        """
        Validate a file for reading or editing operations.

        Args:
            path: Path to the file to validate

        Raises:
            FileValidationError: If the file fails validation
        """
        # Skip validation for directories or non-existent files (for create command)
        if not self._path_exists(path) or not self._path_is_file(path):
            return

        # Check file size
        file_size = self._get_file_size(path)
        max_size = self._max_file_size
        if file_size > max_size:
            raise FileValidationError(
                path=str(path),
                reason=(
                    f"File is too large ({file_size / 1024 / 1024:.1f}MB). "
                    f"Maximum allowed size is {int(max_size / 1024 / 1024)}MB."
                ),
            )

        # Check file type - allow image files
        file_extension = path.suffix.lower()
        if is_binary(str(path)) and file_extension not in IMAGE_EXTENSIONS:
            raise FileValidationError(
                path=str(path),
                reason=(
                    "File appears to be binary and this file type cannot be read "
                    "or edited by this tool."
                ),
            )

    @with_encoding
    def read_file(
        self,
        path: Path,
        start_line: int | None = None,
        end_line: int | None = None,
        encoding: str = "utf-8",  # Default will be overridden by decorator
    ) -> str:
        """
        Read the content of a file from a given path; raise a ToolError if an
        error occurs.

        Args:
            path: Path to the file to read
            start_line: Optional start line number (1-based). If provided with
                end_line, only reads that range.
            end_line: Optional end line number (1-based). Must be provided with
                start_line.
            encoding: The encoding to use when reading the file (auto-detected by
                decorator)
        """
        self.validate_file(path)
        try:
            content = self._read_text_content(path, encoding=encoding)
            if start_line is not None and end_line is not None:
                lines = content.splitlines(keepends=True)
                return "".join(lines[start_line - 1 : end_line])
            elif start_line is not None or end_line is not None:
                raise ValueError(
                    "Both start_line and end_line must be provided together"
                )
            else:
                return content
        except Exception as e:
            raise ToolError(f"Ran into {e} while trying to read {path}") from None

    def _make_output(
        self,
        snippet_content: str,
        snippet_description: str,
        start_line: int = 1,
        is_converted_markdown: bool = False,
    ) -> str:
        """
        Generate output for the CLI based on the content of a code snippet.
        """
        # If the content is converted from Markdown, we don't need line numbers
        if is_converted_markdown:
            snippet_content = maybe_truncate(
                snippet_content,
                truncate_after=MAX_RESPONSE_LEN_CHAR,
                truncate_notice=BINARY_FILE_CONTENT_TRUNCATED_NOTICE,
            )
            return (
                f"Here's the content of the file {snippet_description} displayed in "
                "Markdown format:\n" + snippet_content + "\n"
            )

        snippet_content = maybe_truncate(
            snippet_content,
            truncate_after=MAX_RESPONSE_LEN_CHAR,
            truncate_notice=TEXT_FILE_CONTENT_TRUNCATED_NOTICE,
        )

        snippet_content = "\n".join(
            [
                f"{i + start_line:6}\t{line}"
                for i, line in enumerate(snippet_content.split("\n"))
            ]
        )
        return (
            f"Here's the result of running `cat -n` on {snippet_description}:\n"
            + snippet_content
            + "\n"
        )