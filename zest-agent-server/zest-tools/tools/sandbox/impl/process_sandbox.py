"""ProcessSandbox: local-process sandbox.

Only execute_command() is implemented here. All file operations
are inherited from BaseSandbox and executed via this method.

Windows note: the shell command templates in BaseSandbox contain multi-line
python3 -c "..." strings. cmd.exe cannot execute multi-line inline scripts,
so on Windows we extract the embedded script body, write it to a temp file,
and run [sys.executable, tmpfile] instead.
"""
import asyncio
import logging
import os
import re
import sys
import tempfile

from tools.sandbox.base import BaseSandbox, ExecutionResult, SandboxInfo

logger = logging.getLogger(__name__)

# Matches:  python3 -c "<body>"  or  python3 -c "<body>" 2>/dev/null
# The body may span multiple lines; we capture everything between the outer quotes.
_PYTHON_INLINE_RE = re.compile(
    r'^python3\s+-c\s+"(.*?)"\s*(?:2>[^\s]*)?\s*$',
    re.DOTALL,
)


def _build_shell_args(cmd: str):
    """Build subprocess args for the given shell command string.

    Returns (args_list, tmp_path_or_None).
    On POSIX: always (["bash", "-c", cmd], None).
    On Windows: if cmd is a python3 -c script, writes body to a temp .py
    file and returns ([sys.executable, tmp_path], tmp_path); otherwise
    replaces python3 alias and uses cmd.exe.
    """
    if sys.platform != "win32":
        return ["bash", "-c", cmd], None

    m = _PYTHON_INLINE_RE.match(cmd.strip())
    if m:
        script_body = m.group(1)
        fd, tmp_path = tempfile.mkstemp(suffix=".py", prefix="_sbx_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(script_body)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return [sys.executable, tmp_path], tmp_path

    # Non-python / already-a-file command
    if "python3 " in cmd:
        cmd = cmd.replace("python3 ", sys.executable + " ", 1)
    return ["cmd.exe", "/d", "/c", cmd], None


class ProcessSandbox(BaseSandbox):
    """Local-process sandbox.

    Runs commands as subprocesses with cwd = work_dir.
    All file operations (read/write/edit/ls/glob/grep) come from
    BaseSandbox via embedded python3 shell scripts.
    """

    DEFAULT_TIMEOUT = 30

    def __init__(self, sandbox_info: SandboxInfo) -> None:
        super().__init__(sandbox_info)
        work_dir = sandbox_info.work_dir or sandbox_info.metadata.get("work_dir", "")
        if not work_dir:
            raise ValueError(
                f"No work_dir for sandbox {sandbox_info.sandbox_id}"
            )
        self.work_dir: str = work_dir

    async def execute_command(
        self,
        cmd: str,
        timeout: int = DEFAULT_TIMEOUT,
        work_dir: str | None = None,
    ) -> ExecutionResult:
        """Run cmd as a subprocess.

        On POSIX uses bash -c.
        On Windows extracts embedded python3 -c scripts to temp files to
        avoid cmd.exe single-line limitations.
        """
        cwd = work_dir or self.work_dir
        shell_args, tmp_path = _build_shell_args(cmd)
        try:
            process = await asyncio.create_subprocess_exec(
                *shell_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout_b, stderr_b = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
            stdout = stdout_b.decode("utf-8", errors="replace").rstrip("\r\n")
            stderr = stderr_b.decode("utf-8", errors="replace").rstrip("\r\n")
            exit_code = process.returncode if process.returncode is not None else -1
            return ExecutionResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                success=exit_code == 0,
                error_message="" if exit_code == 0 else (stderr or f"exit {exit_code}"),
            )
        except asyncio.TimeoutError:
            return ExecutionResult(
                stdout="", stderr="Command timed out",
                exit_code=-1, success=False, error_message="Command timed out",
            )
        except Exception as exc:
            msg = str(exc)
            logger.exception("execute_command failed: cmd=%r cwd=%r", cmd, cwd)
            return ExecutionResult(
                stdout="", stderr=msg,
                exit_code=-1, success=False, error_message=msg,
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
