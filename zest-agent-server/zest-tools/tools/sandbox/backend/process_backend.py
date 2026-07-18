import asyncio
from asyncio.subprocess import Process
import logging
import os
import shutil
import sys
import tempfile

from tools.sandbox.base import (
    BackendType,
    SandboxBackend,
    SandboxInfo,
    SandboxStatus,
)
from tools.sandbox.config.settings import SandboxConfig

logger = logging.getLogger(name=__name__)


class ProcessBackend(SandboxBackend):
    """本地进程后端实现。"""

    def __init__(self, config: SandboxConfig):
        self.config = config

    async def create_sandbox(
        self,
        sandbox_id: str,
        workspace_root: str | None = None,
    ) -> SandboxInfo:
        if workspace_root:
            os.makedirs(workspace_root, exist_ok=True)
            work_dir = workspace_root
        else:
            work_dir = tempfile.mkdtemp(prefix=f"sandbox_{sandbox_id}_")

        sandbox_info = SandboxInfo(
            id=sandbox_id,
            sandbox_id=sandbox_id,
            backend_type=BackendType.PROCESS,
            status=SandboxStatus.STARTING,
            work_dir=work_dir,
            metadata={
                "work_dir": work_dir,
                "workspace_root": workspace_root,
            },
        )
        logger.debug(
            "Created sandbox for session %s with work_dir %s",
            sandbox_id,
            work_dir,
        )
        return sandbox_info

    async def start_sandbox(self, sandbox: SandboxInfo) -> None:
        work_dir = sandbox.metadata.get("work_dir", sandbox.work_dir)
        if not work_dir:
            raise ValueError(f"No work directory found for sandbox {sandbox.sandbox_id}")

        shell_type = self._get_shell_type()
        sandbox.status = SandboxStatus.RUNNING
        sandbox.metadata["shell_type"] = shell_type
        logger.info(
            "Initialized one-shot process sandbox %s with shell %s",
            sandbox.sandbox_id,
            shell_type,
        )

    async def stop_sandbox(self, sandbox: SandboxInfo) -> None:
        sandbox.status = SandboxStatus.STOP

    async def destroy_sandbox(self, sandbox: SandboxInfo) -> None:
        await self.stop_sandbox(sandbox)
        work_dir = sandbox.metadata.get("work_dir", sandbox.work_dir)
        workspace_root = sandbox.metadata.get("workspace_root")
        if work_dir and work_dir != workspace_root:
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Error cleaning up work directory %s: %s", work_dir, exc)
        sandbox.status = SandboxStatus.DESTROYED

    async def health_check(self, sandbox: SandboxInfo) -> bool:
        return sandbox.status in {SandboxStatus.RUNNING, SandboxStatus.IDLE}

    def _prepare_environment(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(self.config.environment)
        env["SANDBOX_MODE"] = "process"
        return env

    async def get_sandbox_info(self, sandbox: SandboxInfo) -> SandboxInfo:
        return sandbox

    def _get_shell_type(self) -> str:
        if sys.platform == "win32":
            return "cmd"
        return "bash"

    def _set_resource_limits(self) -> None:
        try:
            import resource

            cpu_seconds = int(self.config.resources.cpu_limit * 60)
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))

            memory_bytes = self.config.resources.memory_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))

            resource.setrlimit(
                resource.RLIMIT_NPROC,
                (
                    self.config.resources.max_processes,
                    self.config.resources.max_processes,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to set resource limits: %s", exc)