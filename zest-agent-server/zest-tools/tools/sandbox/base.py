"""Sandbox base: single execute() abstraction with shell-script file operations.

All file operations (read, write, edit, ls, glob, grep) are implemented in
BaseSandbox using embedded python3 shell scripts executed via execute_command().
Concrete subclasses only need to implement execute_command().
"""
from __future__ import annotations

import base64
import json
import os
import shlex
import sys
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from tools.sandbox.config.settings import SandboxConfig


# ---------------------------------------------------------------------------
# Status / Backend enums
# ---------------------------------------------------------------------------

class SandboxStatus(Enum):
    """沙箱状态"""
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOP = "STOPPED"
    IDLE = "IDLE"
    ERROR = "ERROR"
    DESTROYED = "DESTROYED"


class BackendType(Enum):
    PROCESS = "process"
    LOCAL_DOCKER = "local_docker"
    DISTRIBUTE_DOCKER = "distribute_docker"
    K8S = "k8s"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class ExecutionResult(BaseModel):
    """Shell command execution result."""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_time: float = 0.0
    success: bool = True
    error_message: str = ""

    @property
    def output(self) -> str:
        """Combined stdout + stderr, mirrors deepagents ExecuteResponse.output."""
        if self.stderr:
            return f"{self.stdout}\n{self.stderr}".strip()
        return self.stdout

    @property
    def truncated(self) -> bool:
        return False


class SandboxInfo(BaseModel):
    id: str
    sandbox_id: str
    backend_type: BackendType
    status: SandboxStatus
    session_api_key: Optional[str] = Field(default=None)
    exposed_url: str = Field(default_factory=str)
    created_at: datetime = Field(default_factory=datetime.now)

    work_dir: Optional[str] = None
    container_name: Optional[str] = None
    pod_name: Optional[str] = None
    namespace: Optional[str] = None
    image: Optional[str] = None
    metadata: dict = Field(default_factory=dict)

    last_used_at: datetime = Field(default_factory=datetime.now)
    usage_count: int = 0


class FileInfo(BaseModel):
    """File listing entry."""
    name: str
    path: str
    size: int
    is_directory: bool
    modified_time: float = 0.0


class GrepMatch(BaseModel):
    """Single grep result line."""
    path: str
    line: int
    text: str


# ---------------------------------------------------------------------------
# Shell command templates (mirrors deepagents BaseSandbox)
# ---------------------------------------------------------------------------

_GLOB_COMMAND_TEMPLATE = """python3 -c "
import glob
import os
import json
import base64

path = base64.b64decode('{path_b64}').decode('utf-8')
pattern = base64.b64decode('{pattern_b64}').decode('utf-8')

os.chdir(path)
matches = sorted(glob.glob(pattern, recursive=True))
for m in matches:
    stat = os.stat(m)
    result = {{
        'path': m,
        'size': stat.st_size,
        'mtime': stat.st_mtime,
        'is_dir': os.path.isdir(m)
    }}
    print(json.dumps(result))
" 2>/dev/null"""

_WRITE_COMMAND_TEMPLATE = """python3 -c "
import os
import sys
import base64

file_path = base64.b64decode('{file_path_b64}').decode('utf-8')

if os.path.exists(file_path):
    print(f'Error: File already exists: {{file_path}}', file=sys.stderr)
    sys.exit(1)

parent_dir = os.path.dirname(file_path) or '.'
os.makedirs(parent_dir, exist_ok=True)

content = base64.b64decode('{content_b64}').decode('utf-8')
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
" 2>&1"""

_OVERWRITE_COMMAND_TEMPLATE = """python3 -c "
import os
import base64

file_path = base64.b64decode('{file_path_b64}').decode('utf-8')
parent_dir = os.path.dirname(file_path) or '.'
os.makedirs(parent_dir, exist_ok=True)

content = base64.b64decode('{content_b64}').decode('utf-8')
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
" 2>&1"""

_EDIT_COMMAND_TEMPLATE = """python3 -c "
import sys
import base64

file_path = base64.b64decode('{file_path_b64}').decode('utf-8')

with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

old = base64.b64decode('{old_b64}').decode('utf-8')
new = base64.b64decode('{new_b64}').decode('utf-8')

count = text.count(old)

if count == 0:
    sys.exit(1)

if {replace_all}:
    result = text.replace(old, new)
else:
    result = text.replace(old, new, 1)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(result)

print(count)
" 2>&1"""

_READ_COMMAND_TEMPLATE = """python3 -c "
import os
import sys
import base64

file_path = base64.b64decode('{file_path_b64}').decode('utf-8')
offset = {offset}
limit = {limit}

if not os.path.isfile(file_path):
    print('Error: File not found')
    sys.exit(1)

if os.path.getsize(file_path) == 0:
    print('System reminder: File exists but has empty contents')
    sys.exit(0)

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

selected = lines[offset:offset + limit]
for i, line in enumerate(selected):
    line_num = offset + i + 1
    print(f'{{line_num:6d}}\\t{{line.rstrip(chr(10))}}')
" 2>&1"""


# ---------------------------------------------------------------------------
# BaseSandbox: all file ops implemented via execute_command()
# ---------------------------------------------------------------------------

class BaseSandbox(ABC):
    """Base sandbox: only execute_command() is abstract.

    All file operations are implemented using embedded python3 scripts
    executed through execute_command(). Subclasses only need to implement
    execute_command() itself.
    """

    def __init__(self, sandbox_info: SandboxInfo) -> None:
        self.sandboxInfo = sandbox_info
        # work_dir is the sandbox boundary; subclasses must set this
        self.work_dir: str = sandbox_info.work_dir or sandbox_info.metadata.get("work_dir", "")

    # ------------------------------------------------------------------
    # Path validation (mirrors deepagents _validate_path)
    # ------------------------------------------------------------------

    def _validate_path(self, path: str) -> str:
        """Validate and normalize a file path for security.

        Rules (adapted from deepagents _validate_path for real OS paths):
        1. Block directory traversal: '..' and '~' are rejected.
        2. Resolve to absolute path (relative paths are joined with work_dir).
        3. Normalise the path (remove redundant separators).
        4. Enforce sandbox boundary: path must remain inside work_dir.

        Args:
            path: Raw path from LLM or caller.

        Returns:
            Normalised absolute path string safe to pass to shell scripts.

        Raises:
            ValueError: If path is unsafe or escapes the sandbox.
        """
        import os as _os

        # 1. Reject traversal sequences
        if ".." in path or path.startswith("~"):
            raise ValueError(f"Path traversal not allowed: {path!r}")

        # 2. Resolve relative paths against work_dir
        if not _os.path.isabs(path):
            if not self.work_dir:
                raise ValueError(
                    f"Relative path {path!r} given but sandbox has no work_dir"
                )
            path = _os.path.join(self.work_dir, path)

        # 3. Normalise
        path = _os.path.normpath(path)

        # 4. Sandbox boundary check (only when work_dir is set)
        if self.work_dir:
            work_dir_norm = _os.path.normpath(self.work_dir)
            if not (path == work_dir_norm or path.startswith(work_dir_norm + _os.sep)):
                raise ValueError(
                    f"Path {path!r} is outside sandbox work_dir {work_dir_norm!r}"
                )

        return path

    # ------------------------------------------------------------------
    # Abstract: must be implemented by subclasses
    # ------------------------------------------------------------------

    @abstractmethod
    async def execute_command(
        self,
        cmd: str,
        timeout: int = 30,
        work_dir: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute a shell command and return ExecutionResult."""
        ...

    # ------------------------------------------------------------------
    # File read
    # ------------------------------------------------------------------

    async def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        """Read file with line numbers (cat -n format)."""
        file_path = self._validate_path(file_path)
        file_path_b64 = base64.b64encode(file_path.encode("utf-8")).decode("ascii")
        cmd = _READ_COMMAND_TEMPLATE.format(
            file_path_b64=file_path_b64, offset=offset, limit=limit
        )
        result = await self.execute_command(cmd)
        output = result.stdout.rstrip()
        if result.exit_code != 0 or "Error: File not found" in output:
            return f"Error: File '{file_path}' not found"
        return output

    # ------------------------------------------------------------------
    # File write (new file only)
    # ------------------------------------------------------------------

    async def write(self, file_path: str, content: str) -> str | None:
        """Create a new file. Returns error string on failure, None on success."""
        file_path = self._validate_path(file_path)
        file_path_b64 = base64.b64encode(file_path.encode("utf-8")).decode("ascii")
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        cmd = _WRITE_COMMAND_TEMPLATE.format(
            file_path_b64=file_path_b64, content_b64=content_b64
        )
        result = await self.execute_command(cmd)
        if result.exit_code != 0:
            err_text = result.stderr.strip() or result.stdout.strip() or f"Failed to write file '{file_path}'"
            return err_text
        return None

    async def overwrite(self, file_path: str, content: str) -> str | None:
        """Write file, creating or replacing it. Returns error string on failure."""
        file_path = self._validate_path(file_path)
        file_path_b64 = base64.b64encode(file_path.encode("utf-8")).decode("ascii")
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        cmd = _OVERWRITE_COMMAND_TEMPLATE.format(
            file_path_b64=file_path_b64, content_b64=content_b64
        )
        result = await self.execute_command(cmd)
        if result.exit_code != 0 or "Error:" in result.stdout:
            return result.stdout.strip() or f"Failed to overwrite file '{file_path}'"
        return None

    # ------------------------------------------------------------------
    # File edit (string replacement)
    # ------------------------------------------------------------------

    async def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> tuple[int | None, str | None]:
        """Edit file by replacing string. Returns (occurrences, error)."""
        file_path = self._validate_path(file_path)
        file_path_b64 = base64.b64encode(file_path.encode("utf-8")).decode("ascii")
        old_b64 = base64.b64encode(old_string.encode("utf-8")).decode("ascii")
        new_b64 = base64.b64encode(new_string.encode("utf-8")).decode("ascii")
        cmd = _EDIT_COMMAND_TEMPLATE.format(
            file_path_b64=file_path_b64,
            old_b64=old_b64,
            new_b64=new_b64,
            replace_all=replace_all,
        )
        result = await self.execute_command(cmd)
        if result.exit_code == 1:
            return None, f"Error: String not found in file: '{old_string}'"
        if result.exit_code != 0:
            return None, f"Error: File '{file_path}' not found"
        count = int(result.stdout.strip())
        return count, None

    # ------------------------------------------------------------------
    # Directory listing
    # ------------------------------------------------------------------

    async def ls_info(self, path: str) -> list[FileInfo]:
        """List directory entries."""
        path = self._validate_path(path)
        path_b64 = base64.b64encode(path.encode("utf-8")).decode("ascii")
        cmd = f"""python3 -c "
import os
import json
import base64

path = base64.b64decode('{path_b64}').decode('utf-8')
try:
    with os.scandir(path) as it:
        for entry in it:
            result = {{
                'path': entry.name,
                'size': 0,
                'is_dir': entry.is_dir(follow_symlinks=False),
                'mtime': 0.0
            }}
            try:
                stat = entry.stat()
                result['size'] = stat.st_size
                result['mtime'] = stat.st_mtime
            except OSError:
                pass
            print(json.dumps(result))
except (FileNotFoundError, PermissionError):
    pass
" 2>/dev/null"""
        result = await self.execute_command(cmd)
        infos: list[FileInfo] = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                infos.append(FileInfo(
                    name=data["path"],
                    path=data["path"],
                    size=data.get("size", 0),
                    is_directory=data["is_dir"],
                    modified_time=data.get("mtime", 0.0),
                ))
            except (json.JSONDecodeError, KeyError):
                continue
        return infos

    # ------------------------------------------------------------------
    # Glob
    # ------------------------------------------------------------------

    async def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """Find files matching a glob pattern."""
        path = self._validate_path(path)
        pattern_b64 = base64.b64encode(pattern.encode("utf-8")).decode("ascii")
        path_b64 = base64.b64encode(path.encode("utf-8")).decode("ascii")
        cmd = _GLOB_COMMAND_TEMPLATE.format(
            path_b64=path_b64, pattern_b64=pattern_b64
        )
        result = await self.execute_command(cmd)
        infos: list[FileInfo] = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                # Use os.path.basename-equivalent split to handle both / and \
                raw_path = data["path"]
                name = raw_path.replace("\\", "/").split("/")[-1]
                infos.append(FileInfo(
                    name=name,
                    path=raw_path,
                    size=data.get("size", 0),
                    is_directory=data["is_dir"],
                    modified_time=data.get("mtime", 0.0),
                ))
            except (json.JSONDecodeError, KeyError):
                continue
        return infos

    # ------------------------------------------------------------------
    # Grep
    # ------------------------------------------------------------------

    async def grep_raw(
        self,
        pattern: str,
        path: Optional[str] = None,
        glob: Optional[str] = None,
    ) -> list[GrepMatch] | str:
        """Search files for a literal text pattern.

        Pure-Python implementation using os.walk - no external commands,
        fully cross-platform (Linux, macOS, Windows).
        """
        import fnmatch as _fnmatch
        if path:
            path = self._validate_path(path)
        search_root = path or self.work_dir or "."
        matches: list[GrepMatch] = []
        for dirpath, _, files in os.walk(search_root):
            for fname in files:
                if glob and not _fnmatch.fnmatch(fname, glob):
                    continue
                fpath = os.path.join(dirpath, fname)
                try:
                    with open(fpath, encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            if pattern in line:
                                matches.append(GrepMatch(
                                    path=fpath, line=i, text=line.rstrip()
                                ))
                                if len(matches) >= 100:
                                    return matches
                except OSError:
                    continue
        return matches

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# SandboxBackend: lifecycle management (unchanged interface)
# ---------------------------------------------------------------------------

class SandboxBackend(ABC):
    """Sandbox backend: manages lifecycle (create/start/stop/destroy).

    Does NOT execute code or manage multiple sandboxes - that is Provider's job.
    """

    @abstractmethod
    async def create_sandbox(
        self,
        sandbox_id: str,
        workspace_root: str | None = None,
    ) -> SandboxInfo:
        pass

    @abstractmethod
    async def start_sandbox(self, sandbox: SandboxInfo) -> None:
        pass

    @abstractmethod
    async def stop_sandbox(self, sandbox: SandboxInfo) -> None:
        pass

    @abstractmethod
    async def destroy_sandbox(self, sandbox: SandboxInfo) -> None:
        pass

    @abstractmethod
    async def health_check(self, sandbox: SandboxInfo) -> bool:
        pass

    @abstractmethod
    async def get_sandbox_info(self, sandbox: SandboxInfo) -> SandboxInfo:
        pass


# Keep old name as alias for backwards compatibility
Sandbox = BaseSandbox