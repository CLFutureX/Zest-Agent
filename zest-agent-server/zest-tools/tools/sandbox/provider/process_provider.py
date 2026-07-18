import asyncio
from datetime import datetime
import logging
import threading
import time

from tools.sandbox.backend.process_backend import ProcessBackend
from tools.sandbox.base import Sandbox, SandboxInfo, SandboxStatus
from tools.sandbox.config.settings import RuntimeType, SandboxConfig
from tools.sandbox.exceptions import SandboxCreationError
from tools.sandbox.impl.process_sandbox import ProcessSandbox
from tools.sandbox.provider.base import SandboxProvider

logger = logging.getLogger(name=__name__)

class ProcessSandboxProvider(SandboxProvider):
    """本地进程沙箱提供者（编排层）。"""

    def __init__(self, config: SandboxConfig):
        if config.mode != RuntimeType.PROCESS:
            raise ValueError(f"Expected PROCESS mode, got {config.mode}")
        self.config = config
        self.backend = ProcessBackend(config)
        self.active_sandboxes: dict[str, SandboxInfo] = {}
        self._lock = threading.RLock()

        logger.info(f"ProcessSandboxProvider initialized with max_sandboxes={config.max_sandboxes}")
        
    
    async def get(
        self,
        sandbox_id: str,
        workspace_root: str | None = None,
    ) -> Sandbox:
        with self._lock:
            sandbox_info = self.active_sandboxes.get(sandbox_id)
            if sandbox_info is not None:
                if await self.backend.health_check(sandbox_info):
                    sandbox_info.last_used_at = datetime.now()
                    sandbox_info.usage_count += 1
                    sandbox_info.status = SandboxStatus.RUNNING
                    return ProcessSandbox(sandbox_info)
                await self._destroy_sandbox(sandbox_info)

            if len(self.active_sandboxes) >= self.config.max_sandboxes:
                await self._evict_idle_sandbox()

            sandbox_info = await self._create_sandbox(sandbox_id, workspace_root)
            self.active_sandboxes[sandbox_id] = sandbox_info
            return ProcessSandbox(sandbox_info)
    
    async def reclaim_idle(self) -> int:
        """
        回收空闲超时的沙箱
        
        Returns:
            int: 回收的沙箱数量
        """
        with self._lock:
            now = time.time()
            to_remove = [
                session_id
                for session_id, sandbox in self.active_sandboxes.items()
                if (now - sandbox.last_used_at.timestamp()) > self.config.idle_timeout
                or sandbox.status == SandboxStatus.IDLE
            ]
            for session_id in to_remove:
                await self._destroy_sandbox(self.active_sandboxes[session_id])
            return len(to_remove)
    
    def get_stats(self) -> dict:
        """
        获取沙箱统计信息
        
        Returns:
            Dict: 统计信息
        """
        return {
            "total_sandboxes": len(self.active_sandboxes),
            "max_sandboxes": self.config.max_sandboxes,
            "backend_type": "process",
            "sandboxes": {
                session_id: {
                    "status": sandbox.status.value,
                    "usage_count": sandbox.usage_count,
                    "last_used_at": sandbox.last_used_at.isoformat(),
                }
                for session_id, sandbox in self.active_sandboxes.items()
            },
        }
    async def health_check(self, session_id: str) -> bool:
        """
        检查沙箱健康状态
        
        Args:
            session_id: 会话 ID
            
        Returns:
            bool: 是否健康
        """
        sandbox = self.active_sandboxes.get(session_id)
        if sandbox is None:
            return False
        return await self.backend.health_check(sandbox)

    async def list_sandboxes(self) -> list[SandboxInfo]:
        """
        列出所有沙箱
        
        Returns:
            List[SandboxInfo]: 沙箱信息列表
        """
        return list(self.active_sandboxes.values())

    async def release(self, sandbox_id: str) -> None:
        with self._lock:
            sandbox = self.active_sandboxes.get(sandbox_id)
            if sandbox is not None:
                sandbox.last_used_at = datetime.now()
                sandbox.status = SandboxStatus.IDLE

    async def destroy(self, session_id: str) -> None:
        """
        销毁沙箱
        
        Args:
            session_id: 会话 ID
        """
        with self._lock:
            sandbox = self.active_sandboxes.get(session_id)
            if sandbox is not None:
                await self._destroy_sandbox(sandbox)
    
    async def destroy_all(self) -> None:
        """销毁所有沙箱"""

        with self._lock:
            sandboxes = list(self.active_sandboxes.values())
            for sandbox in sandboxes:
                await self._destroy_sandbox(sandbox)
    
    async def _create_sandbox(
        self,
        sandbox_id: str,
        workspace_root: str | None = None,
    ) -> SandboxInfo:
        try:
            sandbox = await self.backend.create_sandbox(sandbox_id, workspace_root)
            await self.backend.start_sandbox(sandbox)
            return sandbox
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to create sandbox for session %s: %s", sandbox_id, exc)
            raise SandboxCreationError(f"Failed to create sandbox: {exc}") from exc
    
    async def _destroy_sandbox(self, sandbox: SandboxInfo) -> None:
        try:
            await self.backend.destroy_sandbox(sandbox)
        finally:
            self.active_sandboxes.pop(sandbox.sandbox_id, None)

    async def _evict_idle_sandbox(self, num: int = 1) -> None:
        candidates = sorted(
            self.active_sandboxes.values(),
            key=lambda item: (item.status != SandboxStatus.IDLE, item.last_used_at),
        )
        for sandbox in candidates[:num]:
            await self._destroy_sandbox(sandbox)