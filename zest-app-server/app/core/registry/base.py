from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Optional
import logging
from datetime import datetime, timedelta

from app.core.models import AgentServerInfo, ServerStatus

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    REGISTRY = "registry"
    DEREGISTRY = "deregistry"
    MODIFY = "modify"


class AgentRegistryClient(ABC):
    @abstractmethod
    async def register_loop(self) -> None:
        """周期性上报服务信息。"""

    @abstractmethod
    async def deregister(self, service_id: str) -> None:
        """注销服务。"""


class AgentRegistryServer(ABC):
    """服务注册中心抽象。

    健康检查作为内部嵌套类 ``HealthChecker`` 提供：
    - 不再启动额外的 asyncio.Task，复用 ``watch_loop`` 维护的内存缓存
    - 通过 ``registry.health_checker().get_health_status()`` 取统计
    """

    def __init__(self, heartbeat_timeout: int):
        self.heartbeat_timeout = heartbeat_timeout

    def is_expired(self, server: AgentServerInfo, now: datetime = None) -> bool:
        if now is None:
            now = datetime.utcnow()
        return server.last_heartbeat < now - timedelta(seconds=self.heartbeat_timeout)

    @abstractmethod
    async def watch_loop(self) -> None:
        """监听并刷新服务变化。"""

    @abstractmethod
    async def get_server(self, server_id: str) -> Optional[AgentServerInfo]:
        """获取指定服务信息。"""

    @abstractmethod
    async def get_healthy_servers(self) -> List[AgentServerInfo]:
        """获取健康服务列表。"""

    @abstractmethod
    async def get_all_servers(self, refresh: bool = False) -> List[AgentServerInfo]:
        """获取所有服务列表。"""

    @abstractmethod
    async def close(self) -> None:
        """关闭注册中心连接。"""

    # ==============================
    # 健康检查（内部类）
    # ==============================
    class HealthChecker:
        """Registry 内部健康检查器。

        职责：基于 registry 维护的 servers 缓存做统计与查询。
        - 不启动额外 task（registry 的 watch_loop 已周期 refresh）
        - 不持有独立状态（每次查询都从 registry 缓存读取）
        """

        def __init__(self, registry: "AgentRegistryServer") -> None:
            self._registry = registry

        async def list_unhealthy(self) -> List[AgentServerInfo]:
            all_servers = await self._registry.get_all_servers()
            return [s for s in all_servers if s.status == ServerStatus.UNHEALTHY]

        async def get_health_status(self) -> dict:
            all_servers = await self._registry.get_all_servers()
            healthy = await self._registry.get_healthy_servers()
            unhealthy = [s for s in all_servers if s.status == ServerStatus.UNHEALTHY]
            return {
                "total": len(all_servers),
                "healthy": len(healthy),
                "unhealthy_count": len(unhealthy),
                "unhealthy_ids": [s.server_id for s in unhealthy],
                "heartbeat_timeout": self._registry.heartbeat_timeout,
            }

    def health_checker(self) -> "AgentRegistryServer.HealthChecker":
        """获取 registry 内部健康检查器实例。"""
        return self.HealthChecker(self)


ServiceRegistry = AgentRegistryServer
